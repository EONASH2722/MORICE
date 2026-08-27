import csv
import ctypes
import difflib
import io
import json
import math
import os
import queue
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd

try:
    from vosk import KaldiRecognizer, Model, SetLogLevel
except Exception:  # noqa: BLE001
    KaldiRecognizer = None
    Model = None
    SetLogLevel = None

from morice.settings import load_settings, normalize_wake_phrase
from morice.config import local_data_dir
from morice.wake_runtime import app_session_active, voice_session_active, write_wake_request


FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
PACKAGE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
EXE_PATH = Path(sys.executable).resolve() if FROZEN else ROOT / "dist" / "MORICE" / "MORICE.exe"
VOICE_MODELS = PACKAGE_ROOT / "voice_models" if FROZEN else ROOT / "voice_models"
LOG_PATH = local_data_dir() / "runtime" / "wake-listener.log"
SAMPLE_RATE = 16000
BLOCK_SIZE = 640
BLOCK_DURATION_SECONDS = BLOCK_SIZE / SAMPLE_RATE
DOUBLE_CLAP_WINDOW = 1.8
CLAP_DEBOUNCE = 0.11
# This is only event de-duplication, not a user-facing wake cooldown. A phrase
# or clap wake can immediately launch/wake MORICE again after a real new event.
WAKE_DEDUP_SECONDS = 0.75
SETTINGS_REFRESH_SECONDS = 2.0
STREAM_RETRY_SECONDS = 1.0
HEARD_LOG_GAP = 1.0
TRANSCRIPT_WINDOW_SECONDS = 4.5
DEVICE_SILENCE_ROTATE_SECONDS = 18.0
LOG_MAX_BYTES = 900_000
SENSITIVITY_PROFILES = {
    "conservative": {"target_rms": 1200.0, "max_gain": 7.0, "clap_scale": 1.10},
    "balanced": {"target_rms": 1500.0, "max_gain": 10.0, "clap_scale": 1.0},
    "high": {"target_rms": 1800.0, "max_gain": 14.0, "clap_scale": 0.82},
}
_LISTENER_MUTEX_HANDLE = None


def acquire_listener_instance() -> bool:
    """Keep one packaged wake daemon per signed-in Windows user."""

    global _LISTENER_MUTEX_HANDLE
    if os.name != "nt":
        return True
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(
            None,
            False,
            "Local\\MORICE.BackgroundWake.Listener",
        )
        error = ctypes.windll.kernel32.GetLastError()
    except Exception:
        # Audio stream ownership still prevents silent fake success if the
        # host cannot provide the ordinary Win32 mutex API.
        return True
    if not handle:
        return True
    if error == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(handle)
        return False
    _LISTENER_MUTEX_HANDLE = handle
    return True


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
            backup = LOG_PATH.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            LOG_PATH.replace(backup)
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def norm(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def magic_phrases(wake_phrase: str) -> list[str]:
    phrases = [
        wake_phrase,
        "wake up son",
        "wake up boy",
        "morice",
        "morris",
        "maurice",
        "hey morice",
        "hey morris",
        "hey maurice",
        "wake morice",
        "wake up morice",
        "morice wake up",
        "morris wake up",
    ]
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
        threshold = 0.67 if len(wake_norm) >= 5 else 0.80
        return any(difflib.SequenceMatcher(None, token, wake_norm).ratio() >= threshold for token in heard_tokens)
    if all(token in heard_tokens for token in wake_tokens):
        return True

    width = len(wake_tokens)
    for index in range(max(1, len(heard_tokens) - width + 1)):
        candidate = " ".join(heard_tokens[index : index + width])
        if difflib.SequenceMatcher(None, candidate, wake_norm).ratio() >= 0.70:
            return True
    return False


class RollingTranscript:
    """Collect incremental Vosk partials into a short, matchable phrase window."""

    def __init__(self, window_seconds: float = TRANSCRIPT_WINDOW_SECONDS):
        self.window_seconds = window_seconds
        self._entries: list[tuple[float, str]] = []
        self._partial_tokens: list[str] = []

    def reset(self) -> None:
        self._entries.clear()
        self._partial_tokens.clear()

    def add(self, heard: str, now: float, final: bool = False) -> str:
        tokens = norm(heard).split()
        if not tokens:
            if final:
                self._partial_tokens.clear()
            return self.text(now)

        if final:
            new_tokens = self._new_suffix(tokens)
            self._partial_tokens.clear()
        else:
            prefix = 0
            while (
                prefix < len(tokens)
                and prefix < len(self._partial_tokens)
                and tokens[prefix] == self._partial_tokens[prefix]
            ):
                prefix += 1
            new_tokens = tokens[prefix:]
            self._partial_tokens = tokens

        for token in new_tokens:
            self._entries.append((now, token))
        self._trim(now)
        return self.text(now)

    def _new_suffix(self, tokens: list[str]) -> list[str]:
        existing = [token for _, token in self._entries]
        max_overlap = min(len(existing), len(tokens))
        for overlap in range(max_overlap, 0, -1):
            if existing[-overlap:] == tokens[:overlap]:
                return tokens[overlap:]
        return tokens

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        self._entries = [(stamp, token) for stamp, token in self._entries if stamp >= cutoff]

    def text(self, now: float) -> str:
        self._trim(now)
        return " ".join(token for _, token in self._entries)


@dataclass(frozen=True)
class AudioMetrics:
    peak: float
    rms: float


class AdaptiveAudioFrontend:
    """Condition quiet microphone audio without teaching the AGC to amplify noise."""

    def __init__(self, sensitivity: str = "high"):
        self.sensitivity = normalize_sensitivity(sensitivity)
        profile = SENSITIVITY_PROFILES[self.sensitivity]
        self.target_rms = float(profile["target_rms"])
        self.max_gain = float(profile["max_gain"])
        self.noise_peak = 180.0
        self.noise_rms = 22.0
        self.gain = 1.0

    @staticmethod
    def metrics(samples: np.ndarray) -> AudioMetrics:
        if samples.size == 0:
            return AudioMetrics(0.0, 0.0)
        values = samples.astype(np.float32)
        return AudioMetrics(
            peak=float(np.max(np.abs(values))),
            rms=float(np.sqrt(np.mean(values * values))),
        )

    def observe_noise(self, metrics: AudioMetrics, transient: bool = False) -> None:
        if transient or metrics.peak <= 0.0:
            return
        # Follow a quieter room quickly, but let a rising noise floor move
        # slowly so speech does not immediately become the new "silence".
        peak_rate = 0.10 if metrics.peak < self.noise_peak else 0.008
        rms_rate = 0.10 if metrics.rms < self.noise_rms else 0.008
        if metrics.rms > max(80.0, self.noise_rms * 2.4):
            # A loud fan, USB hiss, or damaged microphone can remain above the
            # normal gate indefinitely. Learn it slowly enough that a brief
            # spoken phrase cannot poison the floor.
            peak_rate = min(peak_rate, 0.0015)
            rms_rate = min(rms_rate, 0.0015)
        self.noise_peak += (min(metrics.peak, 12_000.0) - self.noise_peak) * peak_rate
        self.noise_rms += (min(metrics.rms, 2_400.0) - self.noise_rms) * rms_rate
        self.noise_peak = max(18.0, self.noise_peak)
        self.noise_rms = max(3.0, self.noise_rms)

    def condition_for_speech(self, samples: np.ndarray) -> np.ndarray:
        if samples.size == 0:
            return samples.astype(np.int16, copy=False)
        centered = samples.astype(np.float32)
        centered -= float(np.mean(centered))
        rms = float(np.sqrt(np.mean(centered * centered)))
        if rms < 2.0:
            return np.zeros(samples.shape, dtype=np.int16)

        signal_rms = math.sqrt(max(0.0, (rms * rms) - (self.noise_rms * self.noise_rms)))
        snr_ratio = rms / max(self.noise_rms, 1.0)
        desired_gain = self.target_rms / max(signal_rms, 45.0)
        if snr_ratio < 1.08:
            desired_gain = min(desired_gain, 2.0)
        elif snr_ratio < 1.22:
            desired_gain = min(desired_gain, 4.0)
        desired_gain = max(1.0, min(self.max_gain, desired_gain))

        # Attack quickly when speech is faint and release slowly so words split
        # across blocks do not pump in volume.
        rate = 0.34 if desired_gain > self.gain else 0.08
        self.gain += (desired_gain - self.gain) * rate
        amplified = centered * self.gain
        # A soft limiter protects Vosk from hard-clipped laptop microphone peaks.
        limited = np.tanh(amplified / 30_000.0) * 30_000.0
        return np.clip(limited, -32768, 32767).astype(np.int16)


class RotateAudioDevice(RuntimeError):
    pass


class PauseForVoiceSession(RuntimeError):
    """Close the wake capture while Live Action owns the microphone."""

    pass


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
    # The packaged daemon is also named MORICE.exe, so process-name checks
    # produce a false positive. The UI publishes an exact PID lease instead.
    if app_session_active():
        return True
    if FROZEN or os.name != "nt":
        return False

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { $_.CommandLine -match 'morice\\.pyside_app' } | "
                    "Select-Object -First 1 -ExpandProperty ProcessId"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=6,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        return False
    return bool(result.stdout.strip())


def write_wake_signal(source: str) -> None:
    write_wake_request(source)


def background_process_options() -> dict:
    """Popen options for a cold wake that must not steal a game's focus."""

    options = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "creationflags": subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    }
    if os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        # SW_SHOWMINNOACTIVE: start minimized without activating the window.
        startup_info.wShowWindow = 7
        options["startupinfo"] = startup_info
    return options


def wait_for_voice_session_release(
    *,
    probe=voice_session_active,
    sleeper=time.sleep,
    poll_seconds: float = 0.25,
) -> bool:
    """Wait without an open capture stream while Live Action uses the mic."""

    if not probe():
        return False
    log("Live Action owns the microphone; wake capture paused")
    while probe():
        sleeper(max(0.02, float(poll_seconds)))
    log("Live Action ended; wake capture resumed")
    return True


def wake_morice(source: str) -> None:
    write_wake_signal(source)
    if morice_is_running():
        log(f"wake signal sent by {source}")
        return

    env = os.environ.copy()
    env["MORICE_START_AWAKE"] = "1"
    env["MORICE_WAKE_SOURCE"] = source
    env["MORICE_BACKGROUND_WAKE"] = "1"
    launchers = []
    if EXE_PATH.exists():
        launchers.append(([str(EXE_PATH)], EXE_PATH.parent, "exe"))
    cmd_path = ROOT / "morice.cmd"
    if cmd_path.exists():
        launchers.append((["cmd", "/c", str(cmd_path)], ROOT, "cmd"))
    launchers.append(([sys.executable, "-m", "morice.pyside_app"], ROOT, "python"))

    for args, cwd, label in launchers:
        try:
            process = subprocess.Popen(
                args,
                cwd=str(cwd),
                env=env,
                **background_process_options(),
            )
            # A missing DLL or bad executable can exit immediately even though
            # Popen succeeded. Fall through to the next launcher in that case.
            try:
                exit_code = process.wait(timeout=0.9)
            except subprocess.TimeoutExpired:
                exit_code = None
            if exit_code not in (None, 0):
                log(f"launch failed with {label}: process exited {exit_code}")
                continue
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


def configured_audio_device():
    value = os.getenv("MORICE_AUDIO_DEVICE", "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def normalize_sensitivity(value: str) -> str:
    clean = norm(value)
    aliases = {
        "low": "conservative",
        "normal": "balanced",
        "medium": "balanced",
        "poor mic": "high",
        "quiet": "high",
        "weak": "high",
    }
    clean = aliases.get(clean, clean)
    return clean if clean in SENSITIVITY_PROFILES else "high"


def configured_sensitivity() -> str:
    return normalize_sensitivity(os.getenv("MORICE_WAKE_SENSITIVITY", "high"))


def input_device_candidates(preferred=None) -> list[dict]:
    """Return usable inputs in a practical order, with a forced device first."""
    devices = sd.query_devices()
    default_input = None
    try:
        default_input = int(sd.default.device[0])
    except Exception:  # noqa: BLE001
        pass

    candidates = []
    for index, info in enumerate(devices):
        if int(info.get("max_input_channels", 0)) <= 0:
            continue
        name = str(info.get("name", ""))
        clean_name = norm(name)
        if any(token in clean_name for token in ("speaker", "output", "loopback", "stereo mix")):
            continue
        score = 0
        if index == default_input:
            score += 1000
        if "microphone" in clean_name or "mic" in clean_name:
            score += 400
        if "array" in clean_name:
            score += 160
        if "wasapi" in clean_name:
            score += 35
        candidates.append(
            {
                "index": index,
                "name": name,
                "default_samplerate": float(info.get("default_samplerate") or SAMPLE_RATE),
                "score": score,
            }
        )

    if isinstance(preferred, int):
        candidates.sort(key=lambda item: (item["index"] != preferred, -item["score"], item["index"]))
    elif isinstance(preferred, str) and preferred.strip():
        requested = norm(preferred)
        candidates.sort(
            key=lambda item: (
                requested not in norm(item["name"]),
                -item["score"],
                item["index"],
            )
        )
    else:
        candidates.sort(key=lambda item: (-item["score"], item["index"]))
    return candidates


def stream_rates_for(device: dict) -> list[int]:
    rates = [SAMPLE_RATE, int(round(device.get("default_samplerate", SAMPLE_RATE))), 48_000, 44_100]
    unique_rates = []
    for rate in rates:
        if rate >= 8_000 and rate not in unique_rates:
            unique_rates.append(rate)
    return unique_rates


def audio_stream_options(preferred=None) -> list[dict]:
    """Build resilient device/rate attempts while preserving the preferred mic."""
    try:
        devices = input_device_candidates(preferred)
    except Exception as exc:  # noqa: BLE001
        log(f"could not enumerate microphones; using the system default: {exc}")
        devices = []
    if not devices:
        return [
            {
                "index": preferred,
                "name": str(preferred or "system default"),
                "rate": SAMPLE_RATE,
            }
        ]

    options: list[dict] = []
    for device in devices:
        for rate in stream_rates_for(device):
            options.append(
                {
                    "index": device["index"],
                    "name": device["name"],
                    "rate": rate,
                }
            )
    return options


def resample_pcm16(samples: np.ndarray, source_rate: int, target_rate: int = SAMPLE_RATE) -> np.ndarray:
    if source_rate == target_rate or samples.size == 0:
        return samples.astype(np.int16, copy=False)
    target_size = max(1, int(round(samples.size * target_rate / source_rate)))
    source_positions = np.linspace(0.0, 1.0, num=samples.size, endpoint=False)
    target_positions = np.linspace(0.0, 1.0, num=target_size, endpoint=False)
    resampled = np.interp(target_positions, source_positions, samples.astype(np.float32))
    return np.clip(resampled, -32768, 32767).astype(np.int16)


def detect_clap(
    samples: np.ndarray,
    ambient_peak: float,
    ambient_rms: float,
    sensitivity: str = "high",
) -> tuple[bool, float, float]:
    if samples.size == 0:
        return False, 0.0, 0.0
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
    sharpness = peak / max(rms, 1.0)
    diff_peak = float(np.max(np.abs(np.diff(samples.astype(np.int32))))) if samples.size > 1 else 0.0
    profile = SENSITIVITY_PROFILES[normalize_sensitivity(sensitivity)]
    scale = float(profile["clap_scale"])
    # The two-clap requirement gives us room to accept compressed, low-level
    # transients from inexpensive laptop microphones without waking on speech.
    peak_threshold = max(145.0 * scale, ambient_peak * 1.58 * scale)
    rms_threshold = max(12.0 * scale, ambient_rms * 1.20 * scale)
    attack_threshold = max(82.0 * scale, ambient_peak * 0.24 * scale)
    loud_transient = (
        peak >= peak_threshold
        and diff_peak >= attack_threshold
        and (rms >= rms_threshold or sharpness >= 1.52)
    )
    sharp_snap = (
        peak >= max(220.0 * scale, ambient_peak * 1.30 * scale)
        and diff_peak >= attack_threshold
        and sharpness >= 1.42
    )
    return loud_transient or sharp_snap, peak, rms


def self_test() -> int:
    checks = [
        phrase_matches("wake up son", "wake up son"),
        phrase_matches("hey maurice", "hey morice"),
        phrase_matches("morice wake up", "morice wake up"),
        not phrase_matches("weather today", "wake up son"),
    ]
    quiet = np.zeros(BLOCK_SIZE, dtype=np.int16)
    clap = quiet.copy()
    clap[40] = 9000
    clap[41] = -7600
    quiet_detected, _, _ = detect_clap(quiet, 1200.0, 80.0)
    clap_detected, _, _ = detect_clap(clap, 1200.0, 80.0)
    weak_clap = quiet.copy()
    weak_clap[40] = 520
    weak_clap[41] = -430
    weak_clap_detected, _, _ = detect_clap(weak_clap, 90.0, 12.0)

    phase = np.linspace(0.0, math.tau * 8, BLOCK_SIZE, endpoint=False)
    weak_voice = (np.sin(phase) * 55.0).astype(np.int16)
    frontend = AdaptiveAudioFrontend("high")
    conditioned = frontend.condition_for_speech(weak_voice)
    raw_rms = frontend.metrics(weak_voice).rms
    conditioned_rms = frontend.metrics(conditioned).rms

    transcript = RollingTranscript()
    transcript.add("wake", 1.0)
    combined = transcript.add("wake up son", 1.2)
    checks.extend(
        [
            not quiet_detected,
            clap_detected,
            weak_clap_detected,
            conditioned_rms > raw_rms * 4.0,
            phrase_matches(combined, "wake up son"),
        ]
    )
    if all(checks):
        print("wake listener self-test passed")
        return 0
    print("wake listener self-test failed")
    return 1


def list_devices() -> int:
    print(sd.query_devices())
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if "--list-devices" in sys.argv:
        return list_devices()
    enabled = os.getenv("MORICE_ENABLE_ALWAYS_ON_WAKE", "1").strip().casefold()
    if enabled in {"0", "false", "no", "off", "disabled"}:
        log("background wake is disabled by MORICE_ENABLE_ALWAYS_ON_WAKE")
        return 0
    if not acquire_listener_instance():
        log("another wake listener is already active")
        return 0

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
    last_wake = 0.0
    clap_times: list[float] = []
    last_settings_refresh = 0.0
    last_heard_log = 0.0
    audio_device = configured_audio_device()
    sensitivity = configured_sensitivity()
    if audio_device is not None:
        log(f"using configured audio device: {audio_device!r}")
    log(f"wake sensitivity={sensitivity!r}")
    stream_options = audio_stream_options(audio_device)
    stream_index = 0

    while True:
        wait_for_voice_session_release()
        option = stream_options[stream_index % len(stream_options)]
        source_rate = int(option["rate"])
        source_block_size = max(320, int(round(source_rate * BLOCK_DURATION_SECONDS)))
        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=96)
        frontend = AdaptiveAudioFrontend(sensitivity)
        transcript = RollingTranscript()
        last_input_activity = time.monotonic()

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
                samplerate=source_rate,
                blocksize=source_block_size,
                dtype="int16",
                channels=1,
                device=option["index"],
                callback=callback,
            ):
                log(
                    "listening for two claps or magic words; "
                    f"device={option['name']!r}, rate={source_rate}, "
                    f"adaptive_gain<=x{frontend.max_gain:g}"
                )
                while True:
                    try:
                        data = audio_queue.get(timeout=2.5)
                    except queue.Empty as exc:
                        raise RotateAudioDevice("microphone stopped delivering audio") from exc
                    now = time.monotonic()

                    if voice_session_active():
                        raise PauseForVoiceSession()

                    if now - last_settings_refresh >= SETTINGS_REFRESH_SECONDS:
                        last_settings_refresh = now
                        latest_wake_phrase = configured_wake_phrase()
                        if latest_wake_phrase != wake_phrase:
                            wake_phrase = latest_wake_phrase
                            recognizer = make_recognizer(vosk_model, wake_phrase)
                            transcript.reset()
                            log(f"wake phrase updated to {wake_phrase!r}")

                    source_samples = np.frombuffer(data, dtype=np.int16)
                    samples = resample_pcm16(source_samples, source_rate)
                    if samples.size:
                        metrics = frontend.metrics(samples)
                        if metrics.peak >= 6.0 or metrics.rms >= 1.5:
                            last_input_activity = now
                        elif (
                            len({item["index"] for item in stream_options}) > 1
                            and now - last_input_activity >= DEVICE_SILENCE_ROTATE_SECONDS
                        ):
                            raise RotateAudioDevice("microphone input stayed digitally silent")

                        clap_candidate, _, _ = detect_clap(
                            samples,
                            frontend.noise_peak,
                            frontend.noise_rms,
                            sensitivity,
                        )
                        frontend.observe_noise(metrics, transient=clap_candidate)
                        is_clap = (
                            clap_candidate and now - last_clap >= CLAP_DEBOUNCE
                        )
                        if is_clap:
                            last_clap = now
                            clap_times = [stamp for stamp in clap_times if now - stamp <= DOUBLE_CLAP_WINDOW]
                            clap_times.append(now)
                            log(f"clap heard ({min(len(clap_times), 2)}/2)")
                            if len(clap_times) >= 2:
                                if now - last_wake >= WAKE_DEDUP_SECONDS:
                                    last_wake = now
                                    wake_morice("double clap")
                                else:
                                    log("duplicate double clap ignored")
                                clap_times = []
                                transcript.reset()
                                if recognizer is not None and hasattr(recognizer, "Reset"):
                                    recognizer.Reset()

                    if recognizer is not None:
                        conditioned_data = frontend.condition_for_speech(samples).tobytes()
                        accepted = recognizer.AcceptWaveform(conditioned_data)
                        if accepted:
                            heard = json.loads(recognizer.Result()).get("text", "")
                        else:
                            heard = json.loads(recognizer.PartialResult()).get("partial", "")
                        heard_norm = norm(heard)
                        combined_heard = transcript.add(heard, now, final=accepted)
                        if heard_norm and now - last_heard_log >= HEARD_LOG_GAP:
                            last_heard_log = now
                            log(
                                f"heard: {heard_norm!r}; gain=x{frontend.gain:.1f}, "
                                f"noise_rms={frontend.noise_rms:.0f}"
                            )
                        if any(
                            phrase_matches(combined_heard, phrase)
                            for phrase in magic_phrases(wake_phrase)
                        ):
                            if now - last_wake >= WAKE_DEDUP_SECONDS:
                                last_wake = now
                                wake_morice(f"magic words: {wake_phrase}")
                            else:
                                log("duplicate magic words ignored")
                            clap_times = []
                            transcript.reset()
                            if recognizer is not None and hasattr(recognizer, "Reset"):
                                recognizer.Reset()
        except PauseForVoiceSession:
            # Do not rotate away from the user's selected microphone. The
            # outer lease check waits with no capture stream until Voice exits.
            continue
        except RotateAudioDevice as exc:
            stream_index = (stream_index + 1) % len(stream_options)
            log(f"switching microphone input: {exc}")
            time.sleep(0.2)
        except Exception as exc:  # noqa: BLE001
            stream_index = (stream_index + 1) % len(stream_options)
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
