from __future__ import annotations

import json
import os
import queue
import array
import math
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol


class SpeechInputState(str, Enum):
    DISABLED = "disabled"
    IDLE = "idle"
    LOADING = "loading"
    LISTENING = "listening"
    STOPPED = "stopped"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True)
class SpeechInputConfig:
    enabled: bool = True
    model_path: str = ""
    input_device: int | str | None = None
    sample_rate: int = 16_000
    # 125 ms frames reduce partial/final transcript quantization versus the
    # previous 250 ms blocks while remaining large enough for stable Vosk CPU.
    block_size: int = 2_000
    max_listen_seconds: float = 30.0
    auto_send: bool = True


@dataclass(frozen=True)
class TranscriptResult:
    request_id: str
    text: str
    duration_ms: float
    cancelled: bool = False
    error_code: str = ""
    message: str = ""
    started_monotonic: float = 0.0
    speech_detected_ms: float | None = None
    first_partial_ms: float | None = None
    speech_end_ms: float | None = None
    speech_end_to_final_ms: float | None = None


@dataclass(frozen=True)
class SpeechInputStatus:
    state: SpeechInputState
    listening: bool
    model_configured: bool
    input_device: int | str | None
    last_error_code: str = ""
    message: str = ""


class Recognizer(Protocol):
    def accept(self, pcm: bytes) -> tuple[bool, str, str]: ...

    def finish(self) -> str: ...


class AudioInput(Protocol):
    def start(self) -> None: ...

    def read(self, timeout: float) -> bytes | None: ...

    def stop(self) -> None: ...

    def abort(self) -> None: ...


class ListenHandle:
    def __init__(self, request_id: str, cancel_callback: Callable[[], None]) -> None:
        self.request_id = request_id
        self._cancel_callback = cancel_callback
        self._done = threading.Event()
        self._result: TranscriptResult | None = None
        self._lock = threading.Lock()

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def result(self) -> TranscriptResult | None:
        with self._lock:
            return self._result

    def cancel(self) -> None:
        if not self.done:
            self._cancel_callback()

    def wait(self, timeout: float | None = None) -> TranscriptResult | None:
        if not self._done.wait(timeout):
            return None
        return self.result

    def _finish(self, value: TranscriptResult) -> None:
        with self._lock:
            if self._result is not None:
                return
            self._result = value
            self._done.set()


class _VoskRecognizer:
    def __init__(self, model: Any, sample_rate: int) -> None:
        from vosk import KaldiRecognizer

        self._recognizer = KaldiRecognizer(model, int(sample_rate))

    @staticmethod
    def _value(payload: str, key: str) -> str:
        try:
            value = json.loads(payload)
        except (TypeError, ValueError):
            return ""
        return " ".join(str(value.get(key, "")).split())

    def accept(self, pcm: bytes) -> tuple[bool, str, str]:
        accepted = bool(self._recognizer.AcceptWaveform(pcm))
        if accepted:
            text = self._value(self._recognizer.Result(), "text")
            return True, text, ""
        partial = self._value(self._recognizer.PartialResult(), "partial")
        return False, "", partial

    def finish(self) -> str:
        return self._value(self._recognizer.FinalResult(), "text")


class _SoundDeviceInput:
    def __init__(self, config: SpeechInputConfig, *, sounddevice_module=None) -> None:
        self._config = config
        self._sounddevice = sounddevice_module
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=48)
        self._stream: Any = None
        self._active_device: int | str | None = config.input_device

    def _callback(self, data, frames, timing, status) -> None:  # noqa: ARG002
        value = bytes(data)
        try:
            self._queue.put_nowait(value)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(value)
            except (queue.Empty, queue.Full):
                pass

    def start(self) -> None:
        sounddevice = self._sounddevice
        if sounddevice is None:
            import sounddevice as sounddevice_module

            sounddevice = sounddevice_module
            self._sounddevice = sounddevice

        requested = self._config.input_device
        candidates = (requested, None) if requested is not None else (None,)
        last_error: Exception | None = None
        for device in candidates:
            try:
                stream = sounddevice.RawInputStream(
                    samplerate=int(self._config.sample_rate),
                    blocksize=int(self._config.block_size),
                    dtype="int16",
                    channels=1,
                    device=device,
                    callback=self._callback,
                )
                stream.start()
            except Exception as error:  # PortAudio exposes backend-specific subclasses.
                last_error = error
                try:
                    stream.close(ignore_errors=True)  # type: ignore[possibly-undefined]
                except BaseException:
                    pass
                continue
            self._stream = stream
            self._active_device = device
            return
        if last_error is not None:
            raise last_error
        raise RuntimeError("No microphone input device is available.")

    def read(self, timeout: float) -> bytes | None:
        try:
            return self._queue.get(timeout=max(0.01, float(timeout)))
        except queue.Empty:
            return None

    def stop(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop(ignore_errors=True)
        except TypeError:
            stream.stop()
        finally:
            try:
                stream.close(ignore_errors=True)
            except TypeError:
                stream.close()

    def abort(self) -> None:
        stream = self._stream
        if stream is None:
            return
        try:
            stream.abort(ignore_errors=True)
        except TypeError:
            try:
                stream.abort()
            except BaseException:
                pass
        except BaseException:
            pass


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def find_vosk_model(explicit: str = "") -> str:
    override = str(explicit or os.getenv("MORICE_VOSK_MODEL", "")).strip()
    if override and (Path(override) / "conf").is_dir():
        return str(Path(override).resolve())
    frozen_root = Path(
        getattr(sys, "_MEIPASS", application_root())
    ).resolve()
    roots = (
        application_root() / "voice_models",
        frozen_root / "voice_models",
        Path(__file__).resolve().parent / "voice_models",
    )
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates.extend(
            folder
            for folder in root.glob("vosk-model*")
            if folder.is_dir() and (folder / "conf").is_dir()
        )
    if not candidates:
        return ""
    # The small model is intentionally preferred for interactive latency and
    # memory use. A larger model remains selectable through MORICE_VOSK_MODEL.
    return str(
        sorted(
            set(candidates),
            key=lambda path: (
                0 if "small" in path.name.casefold() else 1,
                path.name.casefold(),
            ),
        )[0]
    )


class SpeechToTextRuntime:
    """One-shot, push-to-talk Vosk runtime for real MORICE conversations."""

    def __init__(
        self,
        config: SpeechInputConfig | None = None,
        *,
        recognizer_factory: Callable[[str, int], Recognizer] | None = None,
        audio_factory: Callable[[SpeechInputConfig], AudioInput] | None = None,
        model_loader: Callable[[str], Any] | None = None,
        safe_logger: Callable[[str, dict[str, Any]], Any] | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._config = config or SpeechInputConfig()
        self._recognizer_factory = recognizer_factory
        self._audio_factory = audio_factory or _SoundDeviceInput
        self._model_loader = model_loader
        self._safe_logger = safe_logger
        self._clock = clock
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._shutdown = False
        self._audio: AudioInput | None = None
        self._active: ListenHandle | None = None
        self._thread: threading.Thread | None = None
        self._model: Any = None
        self._model_path = find_vosk_model(self._config.model_path)
        self._state = (
            SpeechInputState.DISABLED
            if not self._config.enabled
            else SpeechInputState.IDLE
            if self._model_path
            else SpeechInputState.UNAVAILABLE
        )
        self._last_error = "" if self._model_path else "model-unavailable"
        self._message = (
            ""
            if self._model_path
            else "Vosk speech recognition model is unavailable."
        )
        self._last_partial = ""
        self._last_final = ""
        self._last_duration_ms = 0.0
        self._input_level_percent = 0.0
        self._vad_state = "idle"
        self._last_microphone_test: dict[str, Any] = {}

    @property
    def config(self) -> SpeechInputConfig:
        return self._config

    def status(self) -> SpeechInputStatus:
        with self._lock:
            return SpeechInputStatus(
                state=self._state,
                listening=self._active is not None and not self._active.done,
                model_configured=bool(self._model_path),
                input_device=self._config.input_device,
                last_error_code=self._last_error,
                message=self._message,
            )

    @staticmethod
    def _pcm_level(pcm: bytes) -> float:
        if not pcm:
            return 0.0
        samples = array.array("h")
        bounded = min(len(pcm), 64_000)
        bounded -= bounded % 2
        samples.frombytes(pcm[:bounded])
        if not samples:
            return 0.0
        mean_square = sum(float(value) * float(value) for value in samples) / len(samples)
        rms = math.sqrt(mean_square)
        return max(0.0, min(100.0, 100.0 * rms / 12_000.0))

    def diagnostics(self) -> dict[str, Any]:
        status = self.status()
        devices: list[dict[str, Any]] = []
        default_input: int | None = None
        device_error = ""
        try:
            import sounddevice

            raw_default = sounddevice.default.device
            default_input = int(raw_default[0]) if raw_default else None
            for index, raw in enumerate(sounddevice.query_devices()):
                channels = int(raw.get("max_input_channels", 0) or 0)
                if channels <= 0:
                    continue
                devices.append(
                    {
                        "index": index,
                        "name": str(raw.get("name", "")),
                        "inputChannels": channels,
                        "defaultSampleRate": float(
                            raw.get("default_samplerate", 0.0) or 0.0
                        ),
                        "default": index == default_input,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            device_error = str(exc)
        with self._lock:
            return {
                "state": status.state.value,
                "listening": status.listening,
                "modelConfigured": status.model_configured,
                "configuredDevice": status.input_device,
                "defaultInputDevice": default_input,
                "deviceAvailable": bool(devices),
                "devices": devices,
                "sampleRate": int(self._config.sample_rate),
                "inputLevelPercent": round(self._input_level_percent, 1),
                "vadState": self._vad_state,
                "partialTranscript": self._last_partial,
                "finalTranscript": self._last_final,
                "confidence": None,
                "confidenceReason": "Vosk's compact streaming result does not expose a calibrated confidence score.",
                "recognitionLatencyMs": round(self._last_duration_ms, 1),
                "lastErrorCode": self._last_error,
                "message": self._message,
                "deviceError": device_error,
                "lastMicrophoneTest": dict(self._last_microphone_test),
            }

    def test_microphone(
        self,
        *,
        duration_seconds: float = 0.8,
        playback: bool = False,
    ) -> dict[str, Any]:
        """Capture a short temporary level sample; no audio is retained."""

        if self.status().listening:
            raise RuntimeError("Stop the active voice capture before testing the microphone.")
        started = self._clock()
        try:
            import sounddevice

            duration = max(0.25, min(3.0, float(duration_seconds)))
            frames = max(1, int(self._config.sample_rate * duration))
            with sounddevice.RawInputStream(
                samplerate=int(self._config.sample_rate),
                blocksize=0,
                dtype="int16",
                channels=1,
                device=self._config.input_device,
            ) as stream:
                pcm, overflowed = stream.read(frames)
            data = bytes(pcm)
            level = self._pcm_level(data)
            if playback and data:
                sounddevice.play(
                    array.array("h", data),
                    samplerate=int(self._config.sample_rate),
                    blocking=True,
                )
            result = {
                "success": True,
                "durationMs": round((self._clock() - started) * 1_000.0, 1),
                "sampleRate": int(self._config.sample_rate),
                "levelPercent": round(level, 1),
                "vadState": "speech" if level >= 1.0 else "quiet",
                "overflowed": bool(overflowed),
                "playedBack": bool(playback),
                "retained": False,
                "message": "Microphone sample received; temporary audio was discarded.",
            }
        except Exception as exc:  # noqa: BLE001
            result = {
                "success": False,
                "durationMs": round((self._clock() - started) * 1_000.0, 1),
                "sampleRate": int(self._config.sample_rate),
                "levelPercent": 0.0,
                "vadState": "unavailable",
                "playedBack": False,
                "retained": False,
                "message": f"Microphone test failed: {exc}",
            }
        with self._lock:
            self._last_microphone_test = dict(result)
            self._input_level_percent = float(result.get("levelPercent", 0.0))
            self._vad_state = str(result.get("vadState", "unavailable"))
        return result

    def configure(self, config: SpeechInputConfig) -> SpeechInputStatus:
        self.cancel("configuration-changed")
        model_path = find_vosk_model(config.model_path)
        with self._lock:
            changed_model = model_path != self._model_path
            self._config = config
            self._model_path = model_path
            if changed_model:
                self._model = None
            self._last_error = "" if model_path else "model-unavailable"
            self._message = (
                ""
                if model_path
                else "Vosk speech recognition model is unavailable."
            )
            self._state = (
                SpeechInputState.DISABLED
                if not config.enabled
                else SpeechInputState.IDLE
                if model_path
                else SpeechInputState.UNAVAILABLE
            )
            return self.status()

    def prewarm(self) -> bool:
        """Load the configured Vosk model before the first spoken request."""

        with self._lock:
            if self._shutdown or not self._config.enabled or not self._model_path:
                return False
            if self._active is not None and not self._active.done:
                return True
            previous_state = self._state
            self._state = SpeechInputState.LOADING
            self._message = "Loading speech recognition."
        try:
            self._recognizer()
        except (ImportError, OSError, RuntimeError, ValueError):
            with self._lock:
                self._state = SpeechInputState.ERROR
                self._last_error = "dependency"
                self._message = "Speech recognition dependencies are unavailable."
            return False
        with self._lock:
            if not self._shutdown:
                self._state = (
                    previous_state
                    if previous_state not in {SpeechInputState.LOADING, SpeechInputState.ERROR}
                    else SpeechInputState.IDLE
                )
                self._last_error = ""
                self._message = ""
        return True

    def listen_once(
        self,
        *,
        on_partial: Callable[[str], Any] | None = None,
        on_complete: Callable[[TranscriptResult], Any] | None = None,
        request_id: str | None = None,
    ) -> ListenHandle:
        self.cancel("replaced")
        clean_id = str(request_id or uuid.uuid4().hex)[:128]
        handle = ListenHandle(clean_id, lambda: self.cancel("user"))
        with self._lock:
            if self._shutdown:
                handle._finish(self._result(handle, "", True, "shutdown", 0.0))
                return handle
            if not self._config.enabled:
                handle._finish(self._result(handle, "", False, "disabled", 0.0))
                return handle
            if not self._model_path:
                handle._finish(
                    self._result(handle, "", False, "model-unavailable", 0.0)
                )
                return handle
            self._cancel = threading.Event()
            self._active = handle
            self._state = SpeechInputState.LOADING
            self._last_error = ""
            self._message = "Loading speech recognition."
            thread = threading.Thread(
                target=self._listen,
                args=(handle, self._cancel, on_partial, on_complete),
                name="morice-stt",
                daemon=True,
            )
            self._thread = thread
            thread.start()
        return handle

    def cancel(self, reason: str = "user") -> bool:  # noqa: ARG002
        with self._lock:
            active = self._active
            audio = self._audio
            if active is None or active.done:
                return False
            self._cancel.set()
        if audio is not None:
            audio.abort()
        return True

    def shutdown(self, timeout: float = 2.0) -> None:
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
        self.cancel("shutdown")
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(max(0.0, float(timeout)))
        with self._lock:
            self._state = SpeechInputState.STOPPED
            self._message = "Speech input stopped."

    def _recognizer(self) -> Recognizer:
        if self._recognizer_factory is not None:
            return self._recognizer_factory(
                self._model_path,
                int(self._config.sample_rate),
            )
        if self._model is None:
            if self._model_loader is not None:
                self._model = self._model_loader(self._model_path)
            else:
                from vosk import Model, SetLogLevel

                SetLogLevel(-1)
                self._model = Model(self._model_path)
        return _VoskRecognizer(self._model, int(self._config.sample_rate))

    def _listen(
        self,
        handle: ListenHandle,
        cancel: threading.Event,
        on_partial: Callable[[str], Any] | None,
        on_complete: Callable[[TranscriptResult], Any] | None,
    ) -> None:
        started = self._clock()
        speech_detected_at: float | None = None
        first_partial_at: float | None = None
        speech_end_at: float | None = None
        audio: AudioInput | None = None
        final_parts: list[str] = []
        error_code = ""
        phase = "recognizer"
        try:
            recognizer = self._recognizer()
            if cancel.is_set():
                return
            phase = "audio"
            audio = self._audio_factory(self._config)
            with self._lock:
                self._audio = audio
                self._state = SpeechInputState.LISTENING
                self._message = "Listening..."
            audio.start()
            phase = "recognition"
            deadline = started + max(2.0, float(self._config.max_listen_seconds))
            last_partial = ""
            while not cancel.is_set() and self._clock() < deadline:
                data = audio.read(0.25)
                if not data:
                    continue
                level = self._pcm_level(data)
                if speech_detected_at is None and level >= 1.0:
                    speech_detected_at = self._clock()
                with self._lock:
                    self._input_level_percent = level
                    self._vad_state = "speech" if level >= 1.0 else "quiet"
                accepted, final_text, partial = recognizer.accept(data)
                if partial and partial != last_partial:
                    if first_partial_at is None:
                        first_partial_at = self._clock()
                    last_partial = partial
                    with self._lock:
                        self._last_partial = partial
                    self._callback(on_partial, partial)
                if final_text:
                    final_parts.append(final_text)
                if accepted and final_parts:
                    speech_end_at = self._clock()
                    break
            if not cancel.is_set():
                remainder = recognizer.finish()
                if remainder and remainder not in final_parts:
                    final_parts.append(remainder)
        except (ImportError, OSError, RuntimeError, ValueError):
            if not self._model_path:
                error_code = "model-unavailable"
            else:
                error_code = "audio" if phase == "audio" else "dependency"
        except BaseException:
            error_code = "unknown"
        finally:
            if audio is not None:
                try:
                    audio.stop()
                except BaseException:
                    if not error_code:
                        error_code = "audio"
            duration = max(0.0, (self._clock() - started) * 1000.0)
            finalized_at = started + duration / 1000.0
            text = " ".join(" ".join(final_parts).split())
            cancelled = cancel.is_set()
            if not text and not error_code and not cancelled:
                error_code = "no-speech"
            result = self._result(
                handle,
                text,
                cancelled,
                "cancelled" if cancelled else error_code,
                duration,
                started_monotonic=started,
                speech_detected_ms=(
                    max(0.0, (speech_detected_at - started) * 1000.0)
                    if speech_detected_at is not None
                    else None
                ),
                first_partial_ms=(
                    max(0.0, (first_partial_at - started) * 1000.0)
                    if first_partial_at is not None
                    else None
                ),
                speech_end_ms=(
                    max(0.0, (speech_end_at - started) * 1000.0)
                    if speech_end_at is not None
                    else None
                ),
                speech_end_to_final_ms=(
                    max(0.0, (finalized_at - speech_end_at) * 1000.0)
                    if speech_end_at is not None
                    else None
                ),
            )
            handle._finish(result)
            with self._lock:
                self._audio = None
                if self._active is handle:
                    self._active = None
                if not self._shutdown:
                    self._state = (
                        SpeechInputState.IDLE
                        if not result.error_code or result.error_code in {"no-speech", "cancelled"}
                        else SpeechInputState.ERROR
                    )
                    self._last_error = result.error_code
                    self._message = result.message
                    self._last_final = result.text
                    self._last_duration_ms = result.duration_ms
                    self._vad_state = "idle"
            self._log(result)
            self._callback(on_complete, result)

    @staticmethod
    def _callback(callback: Callable[[Any], Any] | None, value: Any) -> None:
        if callback is None:
            return
        try:
            callback(value)
        except BaseException:
            pass

    @staticmethod
    def _result(
        handle: ListenHandle,
        text: str,
        cancelled: bool,
        error_code: str,
        duration_ms: float,
        *,
        started_monotonic: float = 0.0,
        speech_detected_ms: float | None = None,
        first_partial_ms: float | None = None,
        speech_end_ms: float | None = None,
        speech_end_to_final_ms: float | None = None,
    ) -> TranscriptResult:
        messages = {
            "": "Speech recognized.",
            "cancelled": "Listening stopped.",
            "shutdown": "Speech input is stopped.",
            "disabled": "Speech input is disabled.",
            "model-unavailable": "Vosk speech recognition model is unavailable.",
            "dependency": "Speech recognition dependencies are unavailable.",
            "audio": "The microphone stream failed.",
            "no-speech": "No speech was recognized.",
            "unknown": "Speech recognition failed safely.",
        }
        return TranscriptResult(
            request_id=handle.request_id,
            text=text,
            duration_ms=duration_ms,
            cancelled=cancelled,
            error_code=error_code,
            message=messages.get(error_code, messages["unknown"]),
            started_monotonic=max(0.0, float(started_monotonic)),
            speech_detected_ms=speech_detected_ms,
            first_partial_ms=first_partial_ms,
            speech_end_ms=speech_end_ms,
            speech_end_to_final_ms=speech_end_to_final_ms,
        )

    def _log(self, result: TranscriptResult) -> None:
        if self._safe_logger is None:
            return
        try:
            self._safe_logger(
                "speech-input.complete",
                {
                    "requestId": result.request_id,
                    "characters": len(result.text),
                    "durationMs": round(result.duration_ms, 2),
                    "speechEndToFinalMs": (
                        round(result.speech_end_to_final_ms, 2)
                        if result.speech_end_to_final_ms is not None
                        else None
                    ),
                    "cancelled": result.cancelled,
                    "errorCode": result.error_code,
                },
            )
        except BaseException:
            pass


__all__ = [
    "ListenHandle",
    "SpeechInputConfig",
    "SpeechInputState",
    "SpeechInputStatus",
    "SpeechToTextRuntime",
    "TranscriptResult",
    "application_root",
    "find_vosk_model",
]
