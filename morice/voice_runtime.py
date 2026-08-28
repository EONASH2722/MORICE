from __future__ import annotations

import queue
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol, runtime_checkable

from .config import TTSConfig


NOT_CONFIGURED_MESSAGE = "ElevenLabs TTS is not configured."


class VoiceState(str, Enum):
    DISABLED = "disabled"
    NOT_CONFIGURED = "not-configured"
    IDLE = "idle"
    SYNTHESIZING = "synthesizing"
    PLAYING = "playing"
    DEGRADED = "degraded"
    STOPPED = "stopped"


class VoiceErrorCode(str, Enum):
    NONE = "none"
    DISABLED = "disabled"
    NOT_CONFIGURED = "not-configured"
    QUEUE_FULL = "queue-full"
    AUTH = "auth"
    VOICE_UNAVAILABLE = "voice-unavailable"
    QUOTA_OR_RATE_LIMIT = "quota-or-rate-limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    SERVICE = "service"
    PLAYBACK = "playback"
    DEPENDENCY = "dependency"
    CANCELLED = "cancelled"
    SHUTDOWN = "shutdown"
    UNKNOWN = "unknown"


_SAFE_MESSAGES: Mapping[VoiceErrorCode, str] = {
    VoiceErrorCode.NONE: "Voice output completed.",
    VoiceErrorCode.DISABLED: "Voice output is disabled.",
    VoiceErrorCode.NOT_CONFIGURED: NOT_CONFIGURED_MESSAGE,
    VoiceErrorCode.QUEUE_FULL: "The voice output queue is full.",
    VoiceErrorCode.AUTH: "ElevenLabs authentication failed.",
    VoiceErrorCode.VOICE_UNAVAILABLE: "The configured voice is unavailable.",
    VoiceErrorCode.QUOTA_OR_RATE_LIMIT: "ElevenLabs voice service is temporarily unavailable.",
    VoiceErrorCode.TIMEOUT: "The voice request timed out.",
    VoiceErrorCode.NETWORK: "The voice service could not be reached.",
    VoiceErrorCode.SERVICE: "The voice service failed.",
    VoiceErrorCode.PLAYBACK: "Audio playback failed.",
    VoiceErrorCode.DEPENDENCY: "Voice output dependencies are unavailable.",
    VoiceErrorCode.CANCELLED: "Voice output was interrupted.",
    VoiceErrorCode.SHUTDOWN: "Voice output is stopped.",
    VoiceErrorCode.UNKNOWN: "Voice output failed safely.",
}


@dataclass(frozen=True)
class VoiceMetrics:
    request_id: str
    queue_wait_ms: float | None = None
    request_to_first_audio_ms: float | None = None
    provider_to_first_audio_ms: float | None = None
    playback_startup_ms: float | None = None
    total_generation_ms: float | None = None
    interruption_latency_ms: float | None = None
    audio_bytes: int = 0
    audio_chunks: int = 0
    streamed_before_text_complete: bool = False


@dataclass(frozen=True)
class VoiceResult:
    request_id: str
    success: bool
    cancelled: bool
    provider: str
    error_code: VoiceErrorCode
    message: str
    metrics: VoiceMetrics
    used_fallback: bool = False


@dataclass(frozen=True)
class VoiceStatus:
    state: VoiceState
    provider: str
    api_configured: bool
    queued: int
    active: bool
    last_error_code: VoiceErrorCode = VoiceErrorCode.NONE
    last_metrics: VoiceMetrics | None = None
    message: str = ""


class SpeechHandle:
    """A secret-free handle for one queued or active speech request."""

    def __init__(
        self,
        request_id: str,
        cancel_callback: Callable[["SpeechHandle"], None],
    ) -> None:
        self.request_id = request_id
        self._cancel_callback = cancel_callback
        self._cancel_event = threading.Event()
        self._done = threading.Event()
        self._lock = threading.RLock()
        self._result: VoiceResult | None = None
        self._interruption_latency_ms: float | None = None

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def cancelled(self) -> bool:
        result = self.result
        return bool(result and result.cancelled)

    @property
    def result(self) -> VoiceResult | None:
        with self._lock:
            return self._result

    def cancel(self) -> None:
        if self._done.is_set():
            return
        self._cancel_event.set()
        self._cancel_callback(self)

    def wait(self, timeout: float | None = None) -> VoiceResult | None:
        if not self._done.wait(timeout):
            return None
        return self.result

    def _finish(self, result: VoiceResult) -> None:
        with self._lock:
            if self._result is not None:
                return
            if self._interruption_latency_ms is not None:
                result = replace(
                    result,
                    metrics=replace(
                        result.metrics,
                        interruption_latency_ms=self._interruption_latency_ms,
                    ),
                )
            self._result = result
            self._done.set()

    def _set_interruption_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._interruption_latency_ms = max(0.0, float(latency_ms))
            if self._result is None:
                return
            metrics = replace(
                self._result.metrics,
                interruption_latency_ms=self._interruption_latency_ms,
            )
            self._result = replace(self._result, metrics=metrics)

    def __repr__(self) -> str:
        return f"SpeechHandle(request_id={self.request_id!r}, done={self.done})"


@runtime_checkable
class AudioSink(Protocol):
    def start(
        self,
        *,
        sample_rate: int,
        channels: int = 1,
        dtype: str = "int16",
    ) -> None: ...

    def write(self, pcm: bytes) -> None: ...

    def abort(self) -> None: ...

    def close(self) -> None: ...


@runtime_checkable
class TTSProvider(Protocol):
    def stream_audio(
        self,
        chunks: Iterable[str],
        config: TTSConfig,
        cancel: threading.Event,
    ) -> Iterator[bytes]: ...


class NaturalSpeechChunker:
    """Turn arbitrary token fragments into bounded sentence or clause chunks."""

    _ABBREVIATIONS = {
        "dr",
        "e.g",
        "etc",
        "fig",
        "i.e",
        "jr",
        "mr",
        "mrs",
        "ms",
        "no",
        "prof",
        "sr",
        "st",
        "vs",
    }

    def __init__(
        self,
        *,
        minimum_chars: int = 24,
        clause_chars: int = 48,
        comma_chars: int = 96,
        maximum_chars: int = 220,
        sentence_minimum_chars: int = 4,
    ) -> None:
        minimum = max(1, int(minimum_chars))
        maximum = max(minimum, int(maximum_chars))
        self.minimum_chars = minimum
        self.clause_chars = max(minimum, min(maximum, int(clause_chars)))
        self.comma_chars = max(self.clause_chars, min(maximum, int(comma_chars)))
        self.maximum_chars = maximum
        self.sentence_minimum_chars = max(
            1, min(self.minimum_chars, int(sentence_minimum_chars))
        )
        self._buffer = ""

    @property
    def pending(self) -> str:
        return self._buffer

    def feed(self, delta: str) -> tuple[str, ...]:
        text = str(delta or "").replace("\x00", " ")
        if not text:
            return ()
        self._buffer += text
        return tuple(self._extract(force=False))

    def flush(self) -> tuple[str, ...]:
        return tuple(self._extract(force=True))

    def _extract(self, *, force: bool) -> list[str]:
        output: list[str] = []
        while self._buffer:
            self._buffer = self._buffer.lstrip()
            if not self._buffer:
                break
            boundary = self._find_boundary()
            if boundary is None and len(self._buffer) > self.maximum_chars:
                boundary = self._hard_boundary()
            if boundary is None:
                if not force:
                    break
                boundary = min(len(self._buffer), self.maximum_chars)
                if boundary < len(self._buffer):
                    whitespace = self._buffer.rfind(" ", 0, boundary + 1)
                    if whitespace >= self.minimum_chars:
                        boundary = whitespace + 1
            chunk = " ".join(self._buffer[:boundary].split()).strip()
            self._buffer = self._buffer[boundary:]
            if chunk:
                output.append(chunk)
            if not force and boundary <= 0:
                break
        return output

    def _find_boundary(self) -> int | None:
        text = self._buffer
        for index, character in enumerate(text):
            end = index + 1
            if character in ".?!":
                if end < self.sentence_minimum_chars or not self._sentence_boundary(index):
                    continue
                while end < len(text) and text[end] in "\"'”’)]}":
                    end += 1
                if end == len(text) or text[end].isspace():
                    return end
            elif character == "\n" and end >= self.minimum_chars:
                return end
            elif character in ";:—" and end >= self.clause_chars:
                return end
            elif character == "," and end >= self.comma_chars:
                return end
        return None

    def _sentence_boundary(self, index: int) -> bool:
        text = self._buffer
        character = text[index]
        if character != ".":
            return True
        previous = text[index - 1] if index else ""
        following = text[index + 1] if index + 1 < len(text) else ""
        if previous.isdigit() and following.isdigit():
            return False
        prefix = text[:index]
        match = re.search(r"([A-Za-z](?:[A-Za-z.]*)?)$", prefix)
        word = match.group(1).casefold().rstrip(".") if match else ""
        if word in self._ABBREVIATIONS:
            return False
        if len(word) == 1 and word.isalpha():
            return False
        return True

    def _hard_boundary(self) -> int:
        boundary = self.maximum_chars
        whitespace = max(
            self._buffer.rfind(" ", 0, boundary + 1),
            self._buffer.rfind("\n", 0, boundary + 1),
        )
        if whitespace >= self.minimum_chars:
            return whitespace + 1
        return boundary


class BoundedSpeechStream:
    """Thread-safe ordered speech chunks with bounded queue depth.

    When the producer outruns ElevenLabs, new text is coalesced into the newest
    queued chunk. This bounds memory without dropping or reordering words.
    Closing the stream wakes a blocked consumer immediately for barge-in.
    """

    def __init__(self, max_chunks: int = 8) -> None:
        self.max_chunks = max(1, int(max_chunks))
        self._chunks: deque[str] = deque()
        self._condition = threading.Condition()
        self._closed = False
        self._coalesced = 0
        self._peak_depth = 0

    @property
    def coalesced_chunks(self) -> int:
        with self._condition:
            return self._coalesced

    @property
    def peak_depth(self) -> int:
        with self._condition:
            return self._peak_depth

    def put(self, text: str) -> bool:
        clean = str(text or "").strip()
        if not clean:
            return False
        with self._condition:
            if self._closed:
                return False
            if len(self._chunks) >= self.max_chunks:
                previous = self._chunks.pop()
                self._chunks.append(f"{previous.rstrip()} {clean.lstrip()}")
                self._coalesced += 1
                self._condition.notify()
                return True
            self._chunks.append(clean)
            self._peak_depth = max(self._peak_depth, len(self._chunks))
            self._condition.notify()
            return True

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def __iter__(self) -> "BoundedSpeechStream":
        return self

    def __next__(self) -> str:
        with self._condition:
            while not self._chunks and not self._closed:
                self._condition.wait()
            if self._chunks:
                return self._chunks.popleft()
            raise StopIteration


class SoundDevicePcmSink:
    """Low-latency raw PCM output using MORICE's existing sounddevice dependency."""

    def __init__(self, output_device: int | None = None, *, sounddevice_module=None) -> None:
        self.output_device = output_device
        self._sounddevice = sounddevice_module
        self._stream = None
        self._lock = threading.RLock()

    def start(
        self,
        *,
        sample_rate: int,
        channels: int = 1,
        dtype: str = "int16",
    ) -> None:
        with self._lock:
            if self._stream is not None:
                return
            module = self._sounddevice
            if module is None:
                import sounddevice as module  # type: ignore

            stream = module.RawOutputStream(
                samplerate=int(sample_rate),
                channels=int(channels),
                dtype=dtype,
                device=self.output_device,
                latency="low",
            )
            stream.start()
            self._sounddevice = module
            self._stream = stream

    def write(self, pcm: bytes) -> None:
        with self._lock:
            stream = self._stream
        if stream is None:
            raise RuntimeError("Audio output was not started.")
        stream.write(bytes(pcm))

    def abort(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
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
        try:
            stream.close(ignore_errors=True)
        except TypeError:
            try:
                stream.close()
            except BaseException:
                pass
        except BaseException:
            pass

    def close(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is None:
            return
        try:
            stream.stop(ignore_errors=True)
        except TypeError:
            try:
                stream.stop()
            except BaseException:
                pass
        except BaseException:
            pass
        try:
            stream.close(ignore_errors=True)
        except TypeError:
            try:
                stream.close()
            except BaseException:
                pass
        except BaseException:
            pass


class ElevenLabsProvider:
    """ElevenLabs adapter that never logs credentials or provider exception text."""

    def __init__(self, api_key: str, *, client_factory=None) -> None:
        self._api_key = str(api_key or "")
        self._client_factory = client_factory
        self._client = None
        self._voice_settings_type = None
        self._client_lock = threading.Lock()
        self._active_audio = None
        self._active_audio_lock = threading.Lock()

    def prewarm(self, config: TTSConfig) -> None:
        """Create the reusable HTTP client without making a TTS request."""

        self._client_and_settings(config)

    def _client_and_settings(self, config: TTSConfig):
        with self._client_lock:
            if self._client is not None:
                return self._client, self._voice_settings_type
            client_factory = self._client_factory
            voice_settings_type = None
            if client_factory is None:
                from elevenlabs import VoiceSettings
                from elevenlabs.client import ElevenLabs

                client_factory = ElevenLabs
                voice_settings_type = VoiceSettings
            else:
                try:
                    from elevenlabs import VoiceSettings
                except ImportError:
                    voice_settings_type = None
                else:
                    voice_settings_type = VoiceSettings
            self._client = client_factory(
                api_key=self._api_key,
                timeout=float(config.request_timeout_seconds),
            )
            self._voice_settings_type = voice_settings_type
            return self._client, self._voice_settings_type

    def stream_audio(
        self,
        chunks: Iterable[str],
        config: TTSConfig,
        cancel: threading.Event,
    ) -> Iterator[bytes]:
        client, voice_settings_type = self._client_and_settings(config)
        settings = (
            voice_settings_type(
                speed=float(config.speech_speed),
                stability=float(config.stability),
                style=float(config.style),
            )
            if voice_settings_type is not None
            else {
                "speed": float(config.speech_speed),
                "stability": float(config.stability),
                "style": float(config.style),
            }
        )
        if config.streaming:
            audio = client.text_to_speech.convert_realtime(
                voice_id=config.voice_id,
                text=self._cancel_aware(chunks, cancel),
                model_id=config.model_id,
                output_format=config.output_format,
                voice_settings=settings,
                request_options={"max_retries": 0},
            )
        else:
            text = " ".join(self._cancel_aware(chunks, cancel)).strip()
            if cancel.is_set() or not text:
                return
            audio = client.text_to_speech.stream(
                voice_id=config.voice_id,
                text=text,
                model_id=config.model_id,
                output_format=config.output_format,
                voice_settings=settings,
                enable_logging=False,
                request_options={
                    "timeout_in_seconds": max(1, round(config.request_timeout_seconds)),
                    "max_retries": 0,
                },
            )
        with self._active_audio_lock:
            self._active_audio = audio
        try:
            for value in audio:
                if cancel.is_set():
                    break
                if value:
                    yield bytes(value)
        finally:
            with self._active_audio_lock:
                if self._active_audio is audio:
                    self._active_audio = None
            close = getattr(audio, "close", None)
            if callable(close):
                try:
                    close()
                except BaseException:
                    pass

    def cancel_active(self) -> None:
        """Close the active SDK response so barge-in is not network-bound."""

        with self._active_audio_lock:
            audio = self._active_audio
        close = getattr(audio, "close", None)
        if callable(close):
            try:
                close()
            except BaseException:
                pass

    @staticmethod
    def _cancel_aware(chunks: Iterable[str], cancel: threading.Event) -> Iterator[str]:
        for chunk in chunks:
            if cancel.is_set():
                return
            text = str(chunk or "").strip()
            if text:
                yield text

    def __repr__(self) -> str:
        return "ElevenLabsProvider(api_key=[REDACTED])"


class _CancelledSpeech(Exception):
    pass


class _NoAudio(Exception):
    pass


class _ProviderFailure(Exception):
    """Internal failure envelope that never renders the provider exception."""

    def __init__(self, error: BaseException, *, audio_started: bool) -> None:
        super().__init__()
        self.error = error
        self.audio_started = bool(audio_started)


@dataclass
class _SpeechRequest:
    handle: SpeechHandle
    source: Iterable[str]
    generation: int
    submitted_at: float
    streaming_input: bool
    prechunked: bool
    event_callback: Callable[[str, Mapping[str, Any]], Any] | None
    delivery: Mapping[str, float]


class _TextTracker:
    def __init__(self, complete: bool) -> None:
        self.complete = complete


class _ReplayableChunks:
    def __init__(self, source: Iterator[str]) -> None:
        self._source = source
        self._cache: list[str] = []
        self._exhausted = False

    def primary(self) -> Iterator[str]:
        yield from self._continue(cache_start=0)

    def replay(self) -> Iterator[str]:
        for chunk in self._cache:
            yield chunk
        if not self._exhausted:
            yield from self._continue(cache_start=len(self._cache))

    def _continue(self, *, cache_start: int) -> Iterator[str]:  # noqa: ARG002
        while not self._exhausted:
            try:
                chunk = next(self._source)
            except StopIteration:
                self._exhausted = True
                return
            self._cache.append(chunk)
            yield chunk


class VoiceRuntime:
    """Bounded, nonblocking, interruptible speech synthesis and playback runtime."""

    def __init__(
        self,
        config: TTSConfig,
        *,
        provider_factory: Callable[[TTSConfig], TTSProvider] | None = None,
        sink_factory: Callable[[TTSConfig], AudioSink] | None = None,
        fallback_provider: TTSProvider | None = None,
        safe_logger: Callable[[str, Mapping[str, Any]], Any] | None = None,
        clock: Callable[[], float] = time.perf_counter,
        queue_size: int = 8,
    ) -> None:
        self._config = config
        self._provider_factory = provider_factory or self._default_provider
        self._sink_factory = sink_factory or (
            lambda value: SoundDevicePcmSink(value.output_device)
        )
        self._fallback_provider = fallback_provider
        self._safe_logger = safe_logger
        self._clock = clock
        self._queue: queue.Queue[_SpeechRequest | object] = queue.Queue(
            maxsize=max(1, int(queue_size))
        )
        self._sentinel = object()
        self._shutdown = threading.Event()
        self._lock = threading.RLock()
        self._generation = 0
        self._active_request: _SpeechRequest | None = None
        self._active_sink: AudioSink | None = None
        self._cached_provider: TTSProvider | None = None
        self._cached_provider_config: TTSConfig | None = None
        self._state = self._initial_state(config)
        self._last_error = (
            VoiceErrorCode.NOT_CONFIGURED
            if self._state == VoiceState.NOT_CONFIGURED
            else VoiceErrorCode.DISABLED
            if self._state == VoiceState.DISABLED
            else VoiceErrorCode.NONE
        )
        self._last_metrics: VoiceMetrics | None = None
        self._message = (
            _SAFE_MESSAGES[self._last_error]
            if self._last_error != VoiceErrorCode.NONE
            else ""
        )
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="morice-voice",
            daemon=True,
        )
        self._worker.start()

    def __repr__(self) -> str:
        status = self.status()
        return (
            "VoiceRuntime("
            f"state={status.state.value!r}, provider={status.provider!r}, "
            f"api_configured={status.api_configured}, queued={status.queued})"
        )

    @property
    def worker_alive(self) -> bool:
        return self._worker.is_alive()

    @property
    def config(self) -> TTSConfig:
        with self._lock:
            return self._config

    def speak(
        self,
        text: str,
        *,
        request_id: str | None = None,
        on_event: Callable[[str, Mapping[str, Any]], Any] | None = None,
        delivery: Mapping[str, float] | None = None,
    ) -> SpeechHandle:
        return self._submit(
            (str(text or ""),), False, False, request_id, on_event, delivery
        )

    def speak_stream(
        self,
        tokens: Iterable[str],
        *,
        request_id: str | None = None,
        on_event: Callable[[str, Mapping[str, Any]], Any] | None = None,
        delivery: Mapping[str, float] | None = None,
    ) -> SpeechHandle:
        return self._submit(tokens, True, False, request_id, on_event, delivery)

    def speak_chunks(
        self,
        chunks: Iterable[str],
        *,
        request_id: str | None = None,
        on_event: Callable[[str, Mapping[str, Any]], Any] | None = None,
        delivery: Mapping[str, float] | None = None,
    ) -> SpeechHandle:
        """Speak already-normalized semantic chunks without buffering them again."""

        return self._submit(chunks, True, True, request_id, on_event, delivery)

    def interrupt(self, reason: str = "barge-in") -> bool:  # noqa: ARG002
        started = self._clock()
        with self._lock:
            active = self._active_request
            sink = self._active_sink
            self._generation += 1
            if active is not None:
                active.handle._cancel_event.set()
                self._close_stream_source(active)
        drained: list[_SpeechRequest] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                if item is self._sentinel:
                    if self._shutdown.is_set():
                        try:
                            self._queue.put_nowait(self._sentinel)
                        except queue.Full:
                            pass
                    continue
                request = item
                if isinstance(request, _SpeechRequest):
                    request.handle._cancel_event.set()
                    self._close_stream_source(request)
                    drained.append(request)
            finally:
                self._queue.task_done()
        if sink is not None:
            try:
                sink.abort()
            except BaseException:
                pass
        with self._lock:
            provider = self._cached_provider
        cancel_provider = getattr(provider, "cancel_active", None)
        if callable(cancel_provider):
            cancel_thread = threading.Thread(target=cancel_provider)
            try:
                cancel_thread.name = "morice-voice-cancel"
                cancel_thread.daemon = True
            except (RuntimeError, TypeError):
                pass
            cancel_thread.start()
        latency_ms = max(0.0, (self._clock() - started) * 1000.0)
        if active is not None:
            active.handle._set_interruption_latency(latency_ms)
            active.handle._finish(
                self._result(
                    active,
                    success=False,
                    cancelled=True,
                    error=VoiceErrorCode.CANCELLED,
                    metrics=VoiceMetrics(
                        request_id=active.handle.request_id,
                        total_generation_ms=max(
                            0.0,
                            (self._clock() - active.submitted_at) * 1000.0,
                        ),
                        interruption_latency_ms=latency_ms,
                    ),
                )
            )
        for request in drained:
            metrics = VoiceMetrics(
                request_id=request.handle.request_id,
                interruption_latency_ms=latency_ms,
            )
            request.handle._finish(
                self._result(
                    request,
                    success=False,
                    cancelled=True,
                    error=VoiceErrorCode.CANCELLED,
                    metrics=metrics,
                )
            )
        interrupted = active is not None or bool(drained)
        if interrupted and not self._shutdown.is_set():
            self._set_status(
                VoiceState.IDLE,
                VoiceErrorCode.CANCELLED,
                None,
                _SAFE_MESSAGES[VoiceErrorCode.CANCELLED],
            )
        return interrupted

    def configure(self, config: TTSConfig) -> VoiceStatus:
        self.interrupt("configuration-changed")
        with self._lock:
            self._config = config
            if config != self._cached_provider_config:
                self._cached_provider = None
                self._cached_provider_config = None
            self._state = self._initial_state(config)
            self._last_error = VoiceErrorCode.NONE
            self._message = ""
        return self.status()

    def prewarm(self) -> bool:
        """Prepare the provider client before the first spoken response."""

        with self._lock:
            config = self._config
            if self._shutdown.is_set() or not config.enabled:
                return False
            if config.provider == "elevenlabs" and not config.api_configured:
                return False
        try:
            provider = self._provider(config)
            prewarm = getattr(provider, "prewarm", None)
            if callable(prewarm):
                prewarm(config)
        except (ImportError, OSError, RuntimeError, ValueError):
            return False
        return True

    def status(self) -> VoiceStatus:
        with self._lock:
            return VoiceStatus(
                state=self._state,
                provider=self._config.provider,
                api_configured=self._config.api_configured,
                queued=(0 if self._shutdown.is_set() else self._queue.qsize()),
                active=self._active_request is not None,
                last_error_code=self._last_error,
                last_metrics=self._last_metrics,
                message=self._message,
            )

    def shutdown(self, timeout: float = 2.0) -> None:
        with self._lock:
            if self._shutdown.is_set():
                return
            self._shutdown.set()
        self.interrupt("shutdown")
        try:
            self._queue.put_nowait(self._sentinel)
        except queue.Full:
            pass
        if threading.current_thread() is not self._worker:
            self._worker.join(max(0.0, float(timeout)))
        self._set_status(
            VoiceState.STOPPED,
            VoiceErrorCode.SHUTDOWN,
            self._last_metrics,
            _SAFE_MESSAGES[VoiceErrorCode.SHUTDOWN],
        )

    def _submit(
        self,
        source: Iterable[str],
        streaming_input: bool,
        prechunked: bool,
        request_id: str | None,
        event_callback: Callable[[str, Mapping[str, Any]], Any] | None,
        delivery: Mapping[str, float] | None,
    ) -> SpeechHandle:
        clean_request_id = self._request_id(request_id)
        handle = SpeechHandle(clean_request_id, self._cancel_handle)
        now = self._clock()
        with self._lock:
            config = self._config
            generation = self._generation
            stopped = self._shutdown.is_set()
        if stopped:
            self._finish_immediately(handle, VoiceErrorCode.SHUTDOWN, now)
            return handle
        if not config.enabled:
            self._finish_immediately(handle, VoiceErrorCode.DISABLED, now)
            return handle
        if config.provider == "elevenlabs" and not config.api_configured:
            self._finish_immediately(handle, VoiceErrorCode.NOT_CONFIGURED, now)
            self._set_status(
                VoiceState.NOT_CONFIGURED,
                VoiceErrorCode.NOT_CONFIGURED,
                handle.result.metrics if handle.result else None,
                NOT_CONFIGURED_MESSAGE,
            )
            return handle
        request = _SpeechRequest(
            handle=handle,
            source=source,
            generation=generation,
            submitted_at=now,
            streaming_input=streaming_input,
            prechunked=prechunked,
            event_callback=event_callback,
            delivery={
                str(key): float(value)
                for key, value in dict(delivery or {}).items()
                if str(key) in {"speed", "stability", "style"}
                and isinstance(value, (int, float))
            },
        )
        try:
            self._queue.put_nowait(request)
        except queue.Full:
            self._finish_immediately(handle, VoiceErrorCode.QUEUE_FULL, now)
        return handle

    def _worker_loop(self) -> None:
        while True:
            try:
                item = self._queue.get()
            except BaseException:
                if self._shutdown.is_set():
                    return
                continue
            try:
                if item is self._sentinel:
                    return
                request = item
                if not isinstance(request, _SpeechRequest):
                    continue
                if self._request_cancelled(request):
                    self._finish_cancelled(request)
                    continue
                try:
                    self._process(request)
                except BaseException as error:
                    if self._request_cancelled(request):
                        self._finish_cancelled(request)
                        continue
                    code = classify_voice_failure(error)
                    metrics = VoiceMetrics(
                        request_id=request.handle.request_id,
                        total_generation_ms=max(
                            0.0,
                            (self._clock() - request.submitted_at) * 1000.0,
                        ),
                    )
                    result = self._result(
                        request,
                        success=False,
                        cancelled=False,
                        error=code,
                        metrics=metrics,
                    )
                    request.handle._finish(result)
                    self._set_status(
                        VoiceState.DEGRADED,
                        code,
                        metrics,
                        result.message,
                    )
                    self._log("voice.failure", request, code, False)
            finally:
                self._queue.task_done()

    def _process(self, request: _SpeechRequest) -> None:
        with self._lock:
            if self._request_cancelled(request):
                self._finish_cancelled(request)
                return
            self._active_request = request
            base_config = self._config
            config = replace(
                base_config,
                speech_speed=max(
                    0.7,
                    min(1.2, request.delivery.get("speed", base_config.speech_speed)),
                ),
                stability=max(
                    0.0,
                    min(1.0, request.delivery.get("stability", base_config.stability)),
                ),
                style=max(
                    0.0,
                    min(1.0, request.delivery.get("style", base_config.style)),
                ),
            )
            self._state = VoiceState.SYNTHESIZING
            self._message = ""

        tracker = _TextTracker(complete=not request.streaming_input)
        text_chunks = self._chunked_text(request, tracker)
        replayable = _ReplayableChunks(iter(text_chunks))
        primary_error = VoiceErrorCode.NONE
        try:
            try:
                provider = self._provider(base_config)
                metrics = self._attempt(
                    request,
                    provider,
                    replayable.primary(),
                    tracker,
                    config,
                )
                result = self._result(
                    request,
                    success=True,
                    cancelled=False,
                    error=VoiceErrorCode.NONE,
                    metrics=metrics,
                )
            except _CancelledSpeech:
                self._finish_cancelled(request)
                return
            except BaseException as error:
                if self._request_cancelled(request):
                    self._finish_cancelled(request)
                    return
                provider_error = (
                    error.error if isinstance(error, _ProviderFailure) else error
                )
                audio_started = bool(
                    isinstance(error, _ProviderFailure) and error.audio_started
                )
                primary_error = classify_voice_failure(provider_error)
                if (
                    self._request_cancelled(request)
                    or not config.automatic_fallback
                    or self._fallback_provider is None
                    or audio_started
                    or primary_error == VoiceErrorCode.PLAYBACK
                ):
                    metrics = VoiceMetrics(
                        request_id=request.handle.request_id,
                        total_generation_ms=max(
                            0.0,
                            (self._clock() - request.submitted_at) * 1000.0,
                        ),
                    )
                    result = self._result(
                        request,
                        success=False,
                        cancelled=False,
                        error=primary_error,
                        metrics=metrics,
                    )
                else:
                    try:
                        metrics = self._attempt(
                            request,
                            self._fallback_provider,
                            replayable.replay(),
                            tracker,
                            config,
                        )
                        result = self._result(
                            request,
                            success=True,
                            cancelled=False,
                            error=primary_error,
                            metrics=metrics,
                            used_fallback=True,
                        )
                    except _CancelledSpeech:
                        self._finish_cancelled(request)
                        return
                    except BaseException as fallback_error:
                        fallback_cause = (
                            fallback_error.error
                            if isinstance(fallback_error, _ProviderFailure)
                            else fallback_error
                        )
                        fallback_code = classify_voice_failure(fallback_cause)
                        metrics = VoiceMetrics(
                            request_id=request.handle.request_id,
                            total_generation_ms=max(
                                0.0,
                                (self._clock() - request.submitted_at) * 1000.0,
                            ),
                        )
                        result = self._result(
                            request,
                            success=False,
                            cancelled=False,
                            error=fallback_code,
                            metrics=metrics,
                            used_fallback=True,
                        )

            request.handle._finish(result)
            state = VoiceState.IDLE if result.success else VoiceState.DEGRADED
            self._set_status(state, result.error_code, result.metrics, result.message)
            self._log(
                "voice.completed" if result.success else "voice.failure",
                request,
                result.error_code,
                result.used_fallback,
            )
        finally:
            with self._lock:
                if self._active_request is request:
                    self._active_request = None
                    self._active_sink = None

    def _attempt(
        self,
        request: _SpeechRequest,
        provider: TTSProvider,
        chunks: Iterable[str],
        tracker: _TextTracker,
        config: TTSConfig,
    ) -> VoiceMetrics:
        sink: AudioSink | None = None
        audio_iterator: Iterator[bytes] | None = None
        first_audio_at: float | None = None
        playback_started_at: float | None = None
        audio_bytes = 0
        audio_chunks = 0
        streamed_before_complete = False
        phase = "provider"
        provider_started_at = self._clock()
        self._emit_request_event(
            request,
            "provider_started",
            at_monotonic=provider_started_at,
            queueWaitMs=max(
                0.0,
                (provider_started_at - request.submitted_at) * 1000.0,
            ),
        )
        try:
            audio_iterator = iter(
                provider.stream_audio(chunks, config, request.handle._cancel_event)
            )
            for audio in audio_iterator:
                if self._request_cancelled(request):
                    raise _CancelledSpeech()
                if not audio:
                    continue
                now = self._clock()
                if first_audio_at is None:
                    first_audio_at = now
                    streamed_before_complete = (
                        request.streaming_input and not tracker.complete
                    )
                    self._emit_request_event(
                        request,
                        "first_audio_generated",
                        at_monotonic=first_audio_at,
                        requestToFirstAudioMs=max(
                            0.0,
                            (first_audio_at - request.submitted_at) * 1000.0,
                        ),
                        providerToFirstAudioMs=max(
                            0.0,
                            (first_audio_at - provider_started_at) * 1000.0,
                        ),
                        streamedBeforeTextComplete=streamed_before_complete,
                    )
                phase = "playback"
                if sink is None:
                    sink = self._sink_factory(config)
                    sink.start(
                        sample_rate=config.sample_rate,
                        channels=1,
                        dtype="int16",
                    )
                    with self._lock:
                        if self._request_cancelled(request):
                            raise _CancelledSpeech()
                        self._active_sink = sink
                    # RawOutputStream.start() makes the first bytes immediately
                    # eligible for playback. sink.write can block for the entire
                    # audio buffer, so timestamp audibility before that write.
                    playback_started_at = self._clock()
                    self._emit_request_event(
                        request,
                        "playback_started",
                        at_monotonic=playback_started_at,
                        playbackStartupMs=max(
                            0.0,
                            (playback_started_at - first_audio_at) * 1000.0,
                        ),
                    )
                sink.write(bytes(audio))
                audio_bytes += len(audio)
                audio_chunks += 1
                with self._lock:
                    if not self._request_cancelled(request):
                        self._state = VoiceState.PLAYING
                phase = "provider"
            generation_finished_at = self._clock()
            if self._request_cancelled(request):
                raise _CancelledSpeech()
            if audio_bytes <= 0:
                raise _NoAudio()
            if sink is not None:
                sink.close()
            return VoiceMetrics(
                request_id=request.handle.request_id,
                queue_wait_ms=max(
                    0.0,
                    (provider_started_at - request.submitted_at) * 1000.0,
                ),
                request_to_first_audio_ms=(
                    max(0.0, (first_audio_at - request.submitted_at) * 1000.0)
                    if first_audio_at is not None
                    else None
                ),
                provider_to_first_audio_ms=(
                    max(0.0, (first_audio_at - provider_started_at) * 1000.0)
                    if first_audio_at is not None
                    else None
                ),
                playback_startup_ms=(
                    max(0.0, (playback_started_at - first_audio_at) * 1000.0)
                    if playback_started_at is not None and first_audio_at is not None
                    else None
                ),
                total_generation_ms=max(
                    0.0,
                    (generation_finished_at - request.submitted_at) * 1000.0,
                ),
                audio_bytes=audio_bytes,
                audio_chunks=audio_chunks,
                streamed_before_text_complete=streamed_before_complete,
            )
        except _CancelledSpeech:
            if sink is not None:
                try:
                    sink.abort()
                except BaseException:
                    pass
            raise
        except BaseException as error:
            if sink is not None:
                try:
                    sink.abort()
                except BaseException:
                    pass
            if phase == "playback":
                raise _PlaybackFailure() from None
            raise _ProviderFailure(
                error,
                audio_started=audio_bytes > 0,
            ) from None
        finally:
            if audio_iterator is not None:
                close = getattr(audio_iterator, "close", None)
                if callable(close):
                    try:
                        close()
                    except BaseException:
                        pass
            with self._lock:
                if self._active_sink is sink:
                    self._active_sink = None

    def _chunked_text(
        self,
        request: _SpeechRequest,
        tracker: _TextTracker,
    ) -> Iterator[str]:
        iterator = iter(request.source)
        if request.prechunked:
            while True:
                if self._request_cancelled(request):
                    return
                try:
                    chunk = next(iterator)
                except StopIteration:
                    tracker.complete = True
                    return
                clean = str(chunk or "").strip()
                if clean:
                    yield clean

        chunker = NaturalSpeechChunker()
        while True:
            if self._request_cancelled(request):
                return
            try:
                delta = next(iterator)
            except StopIteration:
                tracker.complete = True
                break
            for chunk in chunker.feed(str(delta or "")):
                if self._request_cancelled(request):
                    return
                yield chunk
        for chunk in chunker.flush():
            if self._request_cancelled(request):
                return
            yield chunk

    @staticmethod
    def _close_stream_source(request: _SpeechRequest) -> None:
        if isinstance(request.source, BoundedSpeechStream):
            request.source.close()

    @staticmethod
    def _emit_request_event(
        request: _SpeechRequest,
        event: str,
        *,
        at_monotonic: float,
        **metadata: Any,
    ) -> None:
        callback = request.event_callback
        if callback is None:
            return
        try:
            callback(
                str(event),
                {
                    "atMonotonic": float(at_monotonic),
                    **metadata,
                },
            )
        except Exception:
            pass

    def _cancel_handle(self, handle: SpeechHandle) -> None:
        with self._lock:
            active = self._active_request
        if active is not None and active.handle is handle:
            self.interrupt("handle-cancel")

    def _provider(self, config: TTSConfig) -> TTSProvider:
        with self._lock:
            if self._cached_provider is not None and self._cached_provider_config == config:
                return self._cached_provider
        provider = self._provider_factory(config)
        with self._lock:
            if self._cached_provider is None or self._cached_provider_config != config:
                self._cached_provider = provider
                self._cached_provider_config = config
            return self._cached_provider

    def _request_cancelled(self, request: _SpeechRequest) -> bool:
        with self._lock:
            return (
                self._shutdown.is_set()
                or request.handle._cancel_event.is_set()
                or request.generation != self._generation
            )

    def _finish_cancelled(self, request: _SpeechRequest) -> None:
        existing = request.handle.result
        latency = (
            existing.metrics.interruption_latency_ms
            if existing is not None
            else None
        )
        metrics = VoiceMetrics(
            request_id=request.handle.request_id,
            total_generation_ms=max(
                0.0,
                (self._clock() - request.submitted_at) * 1000.0,
            ),
            interruption_latency_ms=latency,
        )
        request.handle._finish(
            self._result(
                request,
                success=False,
                cancelled=True,
                error=VoiceErrorCode.CANCELLED,
                metrics=metrics,
            )
        )

    def _finish_immediately(
        self,
        handle: SpeechHandle,
        error: VoiceErrorCode,
        submitted_at: float,
    ) -> None:
        metrics = VoiceMetrics(
            request_id=handle.request_id,
            total_generation_ms=max(0.0, (self._clock() - submitted_at) * 1000.0),
        )
        request = _SpeechRequest(
            handle,
            (),
            self._generation,
            submitted_at,
            False,
            False,
            None,
            {},
        )
        handle._finish(
            self._result(
                request,
                success=False,
                cancelled=error == VoiceErrorCode.CANCELLED,
                error=error,
                metrics=metrics,
            )
        )

    def _result(
        self,
        request: _SpeechRequest,
        *,
        success: bool,
        cancelled: bool,
        error: VoiceErrorCode,
        metrics: VoiceMetrics,
        used_fallback: bool = False,
    ) -> VoiceResult:
        message = (
            "Voice output completed with the configured fallback."
            if success and used_fallback
            else _SAFE_MESSAGES[error]
        )
        return VoiceResult(
            request_id=request.handle.request_id,
            success=success,
            cancelled=cancelled,
            provider=("fallback" if used_fallback else self._config.provider),
            error_code=error,
            message=message,
            metrics=metrics,
            used_fallback=used_fallback,
        )

    def _set_status(
        self,
        state: VoiceState,
        error: VoiceErrorCode,
        metrics: VoiceMetrics | None,
        message: str,
    ) -> None:
        with self._lock:
            self._state = state
            self._last_error = error
            if metrics is not None:
                self._last_metrics = metrics
            self._message = message

    def _log(
        self,
        event: str,
        request: _SpeechRequest,
        error: VoiceErrorCode,
        used_fallback: bool,
    ) -> None:
        if self._safe_logger is None:
            return
        payload = {
            "requestId": request.handle.request_id,
            "provider": self._config.provider,
            "errorCode": error.value,
            "usedFallback": bool(used_fallback),
        }
        try:
            self._safe_logger(event, payload)
        except BaseException:
            pass

    @staticmethod
    def _default_provider(config: TTSConfig) -> TTSProvider:
        if config.provider != "elevenlabs":
            raise ImportError("No local speech provider is configured.")
        return ElevenLabsProvider(config.api_key)

    @staticmethod
    def _initial_state(config: TTSConfig) -> VoiceState:
        if not config.enabled:
            return VoiceState.DISABLED
        if config.provider == "elevenlabs" and not config.api_configured:
            return VoiceState.NOT_CONFIGURED
        return VoiceState.IDLE

    @staticmethod
    def _request_id(value: str | None) -> str:
        text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip("-.")
        return text[:64] or uuid.uuid4().hex


class _PlaybackFailure(Exception):
    pass


def classify_voice_failure(error: BaseException) -> VoiceErrorCode:
    """Map provider/audio failures without rendering their potentially secret text."""

    if isinstance(error, _CancelledSpeech):
        return VoiceErrorCode.CANCELLED
    if isinstance(error, _PlaybackFailure):
        return VoiceErrorCode.PLAYBACK
    if isinstance(error, ImportError):
        return VoiceErrorCode.DEPENDENCY
    if isinstance(error, (TimeoutError, queue.Empty)):
        return VoiceErrorCode.TIMEOUT
    status_code = getattr(error, "status_code", None)
    try:
        status = int(status_code) if status_code is not None else 0
    except (TypeError, ValueError):
        status = 0
    if status in {401, 403}:
        return VoiceErrorCode.AUTH
    if status == 404:
        return VoiceErrorCode.VOICE_UNAVAILABLE
    if status == 429:
        return VoiceErrorCode.QUOTA_OR_RATE_LIMIT
    if status in {408, 504}:
        return VoiceErrorCode.TIMEOUT
    if status >= 500:
        return VoiceErrorCode.SERVICE
    if isinstance(error, _NoAudio):
        return VoiceErrorCode.SERVICE
    type_name = type(error).__name__.casefold()
    if "timeout" in type_name:
        return VoiceErrorCode.TIMEOUT
    if any(token in type_name for token in ("connect", "network", "socket", "dns")):
        return VoiceErrorCode.NETWORK
    if isinstance(error, (ConnectionError, OSError)):
        return VoiceErrorCode.NETWORK
    return VoiceErrorCode.UNKNOWN


__all__ = [
    "AudioSink",
    "BoundedSpeechStream",
    "ElevenLabsProvider",
    "NOT_CONFIGURED_MESSAGE",
    "NaturalSpeechChunker",
    "SoundDevicePcmSink",
    "SpeechHandle",
    "TTSProvider",
    "VoiceErrorCode",
    "VoiceMetrics",
    "VoiceResult",
    "VoiceRuntime",
    "VoiceState",
    "VoiceStatus",
    "classify_voice_failure",
]
