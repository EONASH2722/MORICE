import csv
import difflib
import io
import json
import os
import queue
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import sounddevice as sd

try:
    from vosk import KaldiRecognizer, Model, SetLogLevel
except Exception:  # noqa: BLE001
    KaldiRecognizer = None
    Model = None
    SetLogLevel = None

from morice.settings import load_settings, normalize_wake_phrase, wake_signal_path


ROOT = Path(__file__).resolve().parent
EXE_PATH = ROOT / "dist" / "MORICE" / "MORICE.exe"
VOICE_MODELS = ROOT / "voice_models"
LOG_PATH = ROOT / "morice_wake_listener.log"
SAMPLE_RATE = 16000
BLOCK_SIZE = 640
DOUBLE_CLAP_WINDOW = 1.15
CLAP_DEBOUNCE = 0.10
SETTINGS_REFRESH_SECONDS = 2.0
STREAM_RETRY_SECONDS = 2.0
HEARD_LOG_GAP = 1.5


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def norm(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def magic_phrases(wake_phrase: str) -> list[str]:
    phrases = [wake_phrase, "wake up son", "wake up boy", "morice", "hey morice"]
    cleaned = []
    for phrase in phrases:
        phrase = norm(phrase)
        if phrase and phrase not in cleaned:
            cleaned.append(phrase)
    return cleaned


def phrase_matches(heard: str, wake_phrase: str) -> bool:
    heard_norm = norm(heard)
    wake_norm = norm(wake_phrase)
    if not heard_norm or not wake_norm:
        return False
    if wake_norm in heard_norm:
        return True

    wake_tokens = wake_norm.split()
    heard_tokens = heard_norm.split()
    if not wake_tokens or not heard_tokens:
        return False
    if len(wake_tokens) == 1:
        threshold = 0.74 if len(wake_norm) >= 5 else 0.86
        return any(difflib.SequenceMatcher(None, token, wake_norm).ratio() >= threshold for token in heard_tokens)
    if all(token in heard_tokens for token in wake_tokens):
        return True

    width = len(wake_tokens)
    for index in range(max(1, len(heard_tokens) - width + 1)):
        candidate = " ".join(heard_tokens[index : index + width])
        if difflib.SequenceMatcher(None, candidate, wake_norm).ratio() >= 0.78:
            return True
    return False


def find_vosk_model() -> Path | None:
    VOICE_MODELS.mkdir(exist_ok=True)
    candidates: list[Path] = []
    for base in (VOICE_MODELS, ROOT):
        for folder in base.glob("vosk-model*"):
            if folder.is_dir() and (folder / "conf").exists():
                candidates.append(folder)
    if candidates:
        return sorted(candidates, key=lambda p: (0 if "small" in p.name.lower() else 1, p.name.lower()))[0]

    zips = sorted(ROOT.glob("vosk-model*.zip"), key=lambda p: p.stat().st_size)
    if zips:
        zip_path = zips[0]
        log(f"extracting {zip_path.name}")
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(VOICE_MODELS)
        for folder in VOICE_MODELS.glob("vosk-model*"):
            if folder.is_dir() and (folder / "conf").exists():
                return folder
    return None


def morice_is_running() -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq MORICE.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        return False
    rows = csv.reader(io.StringIO(result.stdout))
    return any(row and row[0].strip('"').lower() == "morice.exe" for row in rows)


def write_wake_signal(source: str) -> None:
    path = wake_signal_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(source)


def wake_morice(source: str) -> None:
    write_wake_signal(source)
    if morice_is_running():
        log(f"wake signal sent by {source}")
        return

    env = os.environ.copy()
    env["MORICE_START_AWAKE"] = "1"
    env["MORICE_WAKE_SOURCE"] = source
    launchers = []
    if EXE_PATH.exists():
        launchers.append(([str(EXE_PATH)], EXE_PATH.parent, "exe"))
    cmd_path = ROOT / "morice.cmd"
    if cmd_path.exists():
        launchers.append((["cmd", "/c", str(cmd_path)], ROOT, "cmd"))
    launchers.append((["py", "-3.12", "-m", "morice.pyside_app"], ROOT, "python"))

    for args, cwd, label in launchers:
        try:
            subprocess.Popen(
                args,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            log(f"launched Morice by {source} using {label}")
            return
        except Exception as exc:  # noqa: BLE001
            log(f"launch failed with {label}: {exc}")
    log("all Morice launch methods failed")


def configured_wake_phrase() -> str:
    settings = load_settings()
    return normalize_wake_phrase(settings.get("wake_phrase", "wake up son"))


def make_recognizer(model, wake_phrase: str):
    if model is None or KaldiRecognizer is None:
        return None
    phrases = sorted(magic_phrases(wake_phrase), key=len, reverse=True)
    grammar = json.dumps(phrases + ["[unk]"])
    return KaldiRecognizer(model, SAMPLE_RATE, grammar)


def detect_clap(samples: np.ndarray, ambient_peak: float, ambient_rms: float) -> tuple[bool, float, float]:
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
    sharpness = peak / max(rms, 1.0)
    peak_threshold = max(1800.0, ambient_peak * 1.30)
    rms_threshold = max(130.0, ambient_rms * 1.12)
    loud_transient = peak >= peak_threshold and (rms >= rms_threshold or sharpness >= 2.65)
    sharp_snap = peak >= max(2600.0, ambient_peak * 1.15) and sharpness >= 2.35
    return loud_transient or sharp_snap, peak, rms


def update_ambient(current: float, value: float, limit: float) -> float:
    return (current * 0.992) + (min(value, limit) * 0.008)


def main() -> int:
    wake_phrase = configured_wake_phrase()
    log(f"listener starting; wake phrase={wake_phrase!r}")

    model_path = find_vosk_model()
    vosk_model = None
    recognizer = None
    if model_path:
        log(f"using Vosk model {model_path}")
        if SetLogLevel:
            SetLogLevel(-1)
        vosk_model = Model(str(model_path)) if Model is not None else None
        recognizer = make_recognizer(vosk_model, wake_phrase)
    else:
        log("no Vosk model found; double clap wake is active, but magic words are unavailable")

    last_clap = 0.0
    clap_times: list[float] = []
    last_settings_refresh = 0.0
    last_heard_log = 0.0
    ambient_peak = 2500.0
    ambient_rms = 250.0

    while True:
        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=96)

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            if status:
                log(f"audio status: {status}")
            try:
                audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                try:
                    audio_queue.get_nowait()
                    audio_queue.put_nowait(bytes(indata))
                except Exception:
                    pass

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                dtype="int16",
                channels=1,
                callback=callback,
            ):
                log("listening for two claps or magic words")
                while True:
                    data = audio_queue.get()
                    now = time.monotonic()

                    if now - last_settings_refresh >= SETTINGS_REFRESH_SECONDS:
                        last_settings_refresh = now
                        latest_wake_phrase = configured_wake_phrase()
                        if latest_wake_phrase != wake_phrase:
                            wake_phrase = latest_wake_phrase
                            recognizer = make_recognizer(vosk_model, wake_phrase)
                            log(f"wake phrase updated to {wake_phrase!r}")

                    samples = np.frombuffer(data, dtype=np.int16)
                    if samples.size:
                        is_clap, peak, rms = detect_clap(samples, ambient_peak, ambient_rms)
                        is_clap = is_clap and now - last_clap >= CLAP_DEBOUNCE
                        if is_clap:
                            last_clap = now
                            clap_times = [stamp for stamp in clap_times if now - stamp <= DOUBLE_CLAP_WINDOW]
                            clap_times.append(now)
                            log(f"clap heard ({min(len(clap_times), 2)}/2)")
                            if len(clap_times) >= 2:
                                wake_morice("double clap")
                                clap_times = []
                                if recognizer is not None and hasattr(recognizer, "Reset"):
                                    recognizer.Reset()
                        else:
                            ambient_peak = update_ambient(ambient_peak, peak, 8500.0)
                            ambient_rms = update_ambient(ambient_rms, rms, 1400.0)

                    if recognizer is not None:
                        heard = ""
                        if recognizer.AcceptWaveform(data):
                            heard = json.loads(recognizer.Result()).get("text", "")
                        else:
                            heard = json.loads(recognizer.PartialResult()).get("partial", "")
                        heard_norm = norm(heard)
                        if heard_norm and now - last_heard_log >= HEARD_LOG_GAP:
                            last_heard_log = now
                            log(f"heard: {heard_norm!r}")
                        if any(phrase_matches(heard, phrase) for phrase in magic_phrases(wake_phrase)):
                            wake_morice(f"magic words: {wake_phrase}")
                            clap_times = []
                            if recognizer is not None and hasattr(recognizer, "Reset"):
                                recognizer.Reset()
        except Exception as exc:  # noqa: BLE001
            log(f"audio stream error; retrying in {STREAM_RETRY_SECONDS:.0f}s: {exc}")
            time.sleep(STREAM_RETRY_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001
        log(f"fatal error: {exc}")
        raise
