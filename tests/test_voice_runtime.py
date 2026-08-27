from __future__ import annotations

import threading
import time
import unittest
from dataclasses import replace
from typing import Iterable, Iterator

from morice.config import TTSConfig
from morice.voice_runtime import (
    BoundedSpeechStream,
    ElevenLabsProvider,
    NOT_CONFIGURED_MESSAGE,
    NaturalSpeechChunker,
    SoundDevicePcmSink,
    VoiceErrorCode,
    VoiceRuntime,
    VoiceState,
    classify_voice_failure,
)


def configured(**changes: object) -> TTSConfig:
    return replace(TTSConfig(api_key="unit-test-credential"), **changes)


class FakeSink:
    def __init__(self, *, write_error: BaseException | None = None) -> None:
        self.started = threading.Event()
        self.aborted = threading.Event()
        self.closed = threading.Event()
        self.start_args: dict[str, object] | None = None
        self.writes: list[bytes] = []
        self.write_error = write_error

    def start(
        self,
        *,
        sample_rate: int,
        channels: int = 1,
        dtype: str = "int16",
    ) -> None:
        self.start_args = {
            "sample_rate": sample_rate,
            "channels": channels,
            "dtype": dtype,
        }
        self.started.set()

    def write(self, pcm: bytes) -> None:
        if self.write_error is not None:
            raise self.write_error
        if self.aborted.is_set():
            raise AssertionError("bytes reached an aborted sink")
        self.writes.append(bytes(pcm))

    def abort(self) -> None:
        self.aborted.set()

    def close(self) -> None:
        self.closed.set()


class FakeSinkFactory:
    def __init__(self, *, write_error: BaseException | None = None) -> None:
        self.write_error = write_error
        self.sinks: list[FakeSink] = []

    def __call__(self, config: TTSConfig) -> FakeSink:  # noqa: ARG002
        sink = FakeSink(write_error=self.write_error)
        self.sinks.append(sink)
        return sink


class StaticProvider:
    def __init__(self, audio: tuple[bytes, ...] = (b"\x00\x01",)) -> None:
        self.audio = audio
        self.calls = 0
        self.text: list[str] = []

    def stream_audio(
        self,
        chunks: Iterable[str],
        config: TTSConfig,  # noqa: ARG002
        cancel: threading.Event,
    ) -> Iterator[bytes]:
        self.calls += 1
        self.text.extend(chunks)
        for value in self.audio:
            if cancel.is_set():
                return
            yield value


class GateProvider:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def stream_audio(
        self,
        chunks: Iterable[str],
        config: TTSConfig,  # noqa: ARG002
        cancel: threading.Event,
    ) -> Iterator[bytes]:
        self.entered.set()
        self.release.wait(2.0)
        if cancel.is_set():
            return
        list(chunks)
        yield b"\x01\x02"


class EarlyAudioProvider:
    def __init__(self, source_eof: threading.Event) -> None:
        self.source_eof = source_eof
        self.eof_at_first_audio: bool | None = None
        self.text: list[str] = []

    def stream_audio(
        self,
        chunks: Iterable[str],
        config: TTSConfig,  # noqa: ARG002
        cancel: threading.Event,  # noqa: ARG002
    ) -> Iterator[bytes]:
        iterator = iter(chunks)
        self.text.append(next(iterator))
        self.eof_at_first_audio = self.source_eof.is_set()
        yield b"\x00\x01"
        self.text.extend(iterator)
        yield b"\x02\x03"


class LateBytesProvider:
    def __init__(self) -> None:
        self.after_first = threading.Event()
        self.release_late = threading.Event()

    def stream_audio(
        self,
        chunks: Iterable[str],
        config: TTSConfig,  # noqa: ARG002
        cancel: threading.Event,  # deliberately ignored to emulate a late SDK frame
    ) -> Iterator[bytes]:
        list(chunks)
        yield b"first"
        self.after_first.set()
        self.release_late.wait(2.0)
        yield b"late"


class StatusFailure(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__()
        self.status_code = status_code


class FailingProvider:
    def __init__(self, error: BaseException, *, consume_one: bool = False) -> None:
        self.error = error
        self.consume_one = consume_one
        self.calls = 0
        self.text: list[str] = []

    def stream_audio(
        self,
        chunks: Iterable[str],
        config: TTSConfig,  # noqa: ARG002
        cancel: threading.Event,  # noqa: ARG002
    ) -> Iterator[bytes]:
        self.calls += 1
        iterator = iter(chunks)
        if self.consume_one:
            self.text.append(next(iterator))
        if False:
            yield b""
        raise self.error


class VoiceRuntimeTests(unittest.TestCase):
    def make_runtime(self, *args: object, **kwargs: object) -> VoiceRuntime:
        runtime = VoiceRuntime(*args, **kwargs)
        self.addCleanup(runtime.shutdown)
        return runtime

    def test_natural_chunker_preserves_abbreviations_decimals_and_bounds(self) -> None:
        chunker = NaturalSpeechChunker(
            minimum_chars=10,
            clause_chars=14,
            comma_chars=20,
            maximum_chars=32,
        )
        chunks = list(
            chunker.feed("Dr. Vega measured 3.14 volts. Next clause, with detail.")
        )
        chunks.extend(chunker.flush())

        self.assertEqual(
            chunks,
            ["Dr. Vega measured 3.14 volts.", "Next clause, with detail."],
        )
        self.assertTrue(all(len(chunk) <= 32 for chunk in chunks))

        hard = NaturalSpeechChunker(minimum_chars=5, maximum_chars=12)
        bounded = [*hard.feed("abcdefghijklmnopqrstuv"), *hard.flush()]
        self.assertEqual("".join(bounded), "abcdefghijklmnopqrstuv")
        self.assertTrue(all(len(chunk) <= 12 for chunk in bounded))

    def test_short_complete_phrase_starts_without_waiting_for_more_text(self) -> None:
        chunker = NaturalSpeechChunker()

        self.assertEqual(("Yeah.",), chunker.feed("Yeah."))

    def test_bounded_speech_stream_coalesces_without_dropping_or_reordering(self) -> None:
        stream = BoundedSpeechStream(max_chunks=2)
        self.assertTrue(stream.put("first"))
        self.assertTrue(stream.put("second"))
        self.assertTrue(stream.put("third"))
        self.assertTrue(stream.put("fourth"))
        stream.close()

        self.assertEqual(list(stream), ["first", "second third fourth"])
        self.assertEqual(stream.peak_depth, 2)
        self.assertEqual(stream.coalesced_chunks, 2)

    def test_prechunked_speech_starts_before_stream_closes(self) -> None:
        source_eof = threading.Event()
        provider = EarlyAudioProvider(source_eof)
        sinks = FakeSinkFactory()
        runtime = self.make_runtime(
            configured(),
            provider_factory=lambda config: provider,
            sink_factory=sinks,
        )
        stream = BoundedSpeechStream(max_chunks=2)
        stream.put("A complete semantic clause is ready")
        events = []

        handle = runtime.speak_chunks(
            stream,
            on_event=lambda event, metadata: events.append((event, metadata)),
        )
        deadline = time.monotonic() + 1.0
        while not sinks.sinks and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertTrue(sinks.sinks)
        self.assertTrue(sinks.sinks[0].started.wait(0.5))
        self.assertFalse(source_eof.is_set())

        stream.put("The ordered continuation follows")
        source_eof.set()
        stream.close()
        result = handle.wait(2.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.success)
        self.assertTrue(result.metrics.streamed_before_text_complete)
        self.assertEqual(
            [event for event, _metadata in events],
            ["provider_started", "first_audio_generated", "playback_started"],
        )
        self.assertTrue(
            all("atMonotonic" in metadata for _event, metadata in events)
        )

    def test_playback_start_metric_excludes_blocking_audio_write(self) -> None:
        class SlowWriteSink(FakeSink):
            def write(self, pcm: bytes) -> None:
                time.sleep(0.08)
                super().write(pcm)

        sinks: list[SlowWriteSink] = []

        def make_sink(config: TTSConfig) -> SlowWriteSink:  # noqa: ARG001
            sink = SlowWriteSink()
            sinks.append(sink)
            return sink

        runtime = self.make_runtime(
            configured(),
            provider_factory=lambda config: StaticProvider(),
            sink_factory=make_sink,
        )
        result = runtime.speak("Ready now.").wait(2.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.success)
        self.assertLess(result.metrics.playback_startup_ms or 1_000.0, 40.0)
        self.assertIsNotNone(result.metrics.provider_to_first_audio_ms)

    def test_missing_key_is_exact_nonfatal_and_never_builds_provider(self) -> None:
        provider_built = threading.Event()

        def forbidden_factory(config: TTSConfig) -> StaticProvider:  # noqa: ARG001
            provider_built.set()
            raise AssertionError("provider must not be built without a key")

        runtime = self.make_runtime(
            TTSConfig(api_key=""),
            provider_factory=forbidden_factory,
            sink_factory=FakeSinkFactory(),
        )

        initial = runtime.status()
        self.assertEqual(initial.state, VoiceState.NOT_CONFIGURED)
        self.assertEqual(initial.last_error_code, VoiceErrorCode.NOT_CONFIGURED)
        self.assertEqual(initial.message, NOT_CONFIGURED_MESSAGE)

        handle = runtime.speak("This should remain a harmless no-op.")
        result = handle.wait(0.2)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.success)
        self.assertFalse(result.cancelled)
        self.assertEqual(result.error_code, VoiceErrorCode.NOT_CONFIGURED)
        self.assertEqual(result.message, "ElevenLabs TTS is not configured.")
        self.assertFalse(provider_built.is_set())
        self.assertTrue(runtime.worker_alive)

    def test_speak_returns_without_waiting_for_network_or_audio(self) -> None:
        provider = GateProvider()
        sinks = FakeSinkFactory()
        runtime = self.make_runtime(
            configured(),
            provider_factory=lambda config: provider,
            sink_factory=sinks,
        )

        started = time.perf_counter()
        handle = runtime.speak("A sufficiently long sentence for queued synthesis.")
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.1)
        self.assertTrue(provider.entered.wait(1.0))
        self.assertFalse(handle.done)
        provider.release.set()
        result = handle.wait(2.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.success)
        self.assertEqual(sinks.sinks[0].writes, [b"\x01\x02"])

    def test_first_audio_arrives_before_stream_token_eof(self) -> None:
        source_eof = threading.Event()
        provider = EarlyAudioProvider(source_eof)
        sinks = FakeSinkFactory()
        runtime = self.make_runtime(
            configured(),
            provider_factory=lambda config: provider,
            sink_factory=sinks,
        )

        def tokens() -> Iterator[str]:
            yield "The first complete sentence is ready for speech now. "
            yield "The second sentence follows after playback begins."
            source_eof.set()

        result = runtime.speak_stream(tokens()).wait(2.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.success)
        self.assertFalse(provider.eof_at_first_audio)
        self.assertTrue(source_eof.is_set())
        self.assertTrue(result.metrics.streamed_before_text_complete)
        self.assertIsNotNone(result.metrics.request_to_first_audio_ms)
        self.assertIsNotNone(result.metrics.playback_startup_ms)
        self.assertGreaterEqual(result.metrics.total_generation_ms or -1, 0)
        self.assertEqual(result.metrics.audio_chunks, 2)
        self.assertEqual(result.metrics.audio_bytes, 4)

    def test_interrupt_aborts_sink_drains_queue_and_fences_late_bytes(self) -> None:
        provider = LateBytesProvider()
        sinks = FakeSinkFactory()
        runtime = self.make_runtime(
            configured(),
            provider_factory=lambda config: provider,
            sink_factory=sinks,
            queue_size=3,
        )
        active = runtime.speak("The active utterance must be interruptible immediately.")
        self.assertTrue(provider.after_first.wait(1.0))
        queued = runtime.speak("This queued utterance must be drained on barge in.")

        self.assertTrue(runtime.interrupt("wake-word"))
        self.assertTrue(sinks.sinks[0].aborted.wait(0.2))
        active_result = active.wait(0.3)
        self.assertIsNotNone(active_result)
        assert active_result is not None
        self.assertTrue(active_result.cancelled)
        self.assertLess(
            active_result.metrics.interruption_latency_ms or 1_000.0,
            300.0,
        )
        queued_result = queued.wait(0.5)
        self.assertIsNotNone(queued_result)
        assert queued_result is not None
        self.assertTrue(queued_result.cancelled)
        self.assertEqual(queued_result.error_code, VoiceErrorCode.CANCELLED)

        provider.release_late.set()
        active_result = active.wait(2.0)
        self.assertTrue(active_result.cancelled)
        self.assertEqual(active_result.error_code, VoiceErrorCode.CANCELLED)
        self.assertIsNotNone(active_result.metrics.interruption_latency_ms)
        self.assertEqual(sinks.sinks[0].writes, [b"first"])

    def test_bounded_queue_rejects_overflow_without_blocking(self) -> None:
        provider = GateProvider()
        runtime = self.make_runtime(
            configured(),
            provider_factory=lambda config: provider,
            sink_factory=FakeSinkFactory(),
            queue_size=1,
        )
        first = runtime.speak("The first request occupies the worker thread.")
        self.assertTrue(provider.entered.wait(1.0))
        second = runtime.speak("The second request occupies the bounded queue.")

        started = time.perf_counter()
        overflow = runtime.speak("The third request cannot fit in that queue.")
        elapsed = time.perf_counter() - started

        result = overflow.wait(0.2)
        self.assertLess(elapsed, 0.1)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.error_code, VoiceErrorCode.QUEUE_FULL)
        provider.release.set()
        self.assertTrue(first.wait(2.0).success)  # type: ignore[union-attr]
        self.assertTrue(second.wait(2.0).success)  # type: ignore[union-attr]

    def test_provider_error_and_logs_never_render_exception_or_key(self) -> None:
        toxic_text = "TOP-SECRET-PROVIDER-BODY"

        class ToxicAuthError(Exception):
            status_code = 401

            def __str__(self) -> str:
                return toxic_text

            def __repr__(self) -> str:
                return toxic_text

        logs: list[tuple[str, object]] = []
        runtime = self.make_runtime(
            configured(api_key="TOP-SECRET-API-KEY"),
            provider_factory=lambda config: FailingProvider(ToxicAuthError()),
            sink_factory=FakeSinkFactory(),
            safe_logger=lambda event, payload: logs.append((event, dict(payload))),
        )

        result = runtime.speak("Authentication failure redaction test.").wait(2.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.error_code, VoiceErrorCode.AUTH)
        self.assertEqual(result.message, "ElevenLabs authentication failed.")
        public_rendering = repr((runtime, runtime.config, runtime.status(), result, logs))
        self.assertNotIn(toxic_text, public_rendering)
        self.assertNotIn("TOP-SECRET-API-KEY", public_rendering)
        self.assertEqual(logs[0][0], "voice.failure")
        self.assertEqual(logs[0][1]["errorCode"], "auth")  # type: ignore[index]

    def test_injected_fallback_replays_consumed_text(self) -> None:
        primary = FailingProvider(StatusFailure(503), consume_one=True)
        fallback = StaticProvider(audio=(b"fallback",))
        sinks = FakeSinkFactory()
        runtime = self.make_runtime(
            configured(automatic_fallback=True),
            provider_factory=lambda config: primary,
            fallback_provider=fallback,
            sink_factory=sinks,
        )

        result = runtime.speak(
            "Fallback should receive all text even after primary consumption."
        ).wait(2.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.success)
        self.assertTrue(result.used_fallback)
        self.assertEqual(result.provider, "fallback")
        self.assertEqual(result.error_code, VoiceErrorCode.SERVICE)
        self.assertEqual(primary.text, fallback.text)
        self.assertEqual(sinks.sinks[0].writes, [b"fallback"])

    def test_fallback_is_optional_and_respects_configuration(self) -> None:
        primary = FailingProvider(StatusFailure(503))
        fallback = StaticProvider()
        runtime = self.make_runtime(
            configured(automatic_fallback=False),
            provider_factory=lambda config: primary,
            fallback_provider=fallback,
            sink_factory=FakeSinkFactory(),
        )

        result = runtime.speak("No fallback should be attempted.").wait(2.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, VoiceErrorCode.SERVICE)
        self.assertEqual(fallback.calls, 0)

    def test_provider_failure_after_audio_does_not_repeat_with_fallback(self) -> None:
        class PartialProvider:
            def stream_audio(
                self,
                chunks: Iterable[str],
                config: TTSConfig,  # noqa: ARG002
                cancel: threading.Event,  # noqa: ARG002
            ) -> Iterator[bytes]:
                list(chunks)
                yield b"partial"
                raise StatusFailure(503)

        fallback = StaticProvider(audio=(b"duplicate",))
        sinks = FakeSinkFactory()
        runtime = self.make_runtime(
            configured(automatic_fallback=True),
            provider_factory=lambda config: PartialProvider(),
            fallback_provider=fallback,
            sink_factory=sinks,
        )

        result = runtime.speak("Do not repeat partially spoken output.").wait(2.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, VoiceErrorCode.SERVICE)
        self.assertEqual(fallback.calls, 0)
        self.assertEqual(sinks.sinks[0].writes, [b"partial"])

    def test_playback_error_is_sanitized_and_never_falls_back(self) -> None:
        fallback = StaticProvider()
        runtime = self.make_runtime(
            configured(),
            provider_factory=lambda config: StaticProvider(),
            fallback_provider=fallback,
            sink_factory=FakeSinkFactory(
                write_error=RuntimeError("SECRET-AUDIO-DEVICE-NAME")
            ),
        )

        result = runtime.speak("Playback error classification test.").wait(2.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.error_code, VoiceErrorCode.PLAYBACK)
        self.assertEqual(result.message, "Audio playback failed.")
        self.assertNotIn("SECRET-AUDIO-DEVICE-NAME", repr(result))
        self.assertEqual(fallback.calls, 0)

    def test_shutdown_is_idempotent_and_future_requests_finish_safely(self) -> None:
        runtime = VoiceRuntime(
            configured(),
            provider_factory=lambda config: StaticProvider(),
            sink_factory=FakeSinkFactory(),
        )
        runtime.shutdown()
        runtime.shutdown()

        self.assertFalse(runtime.worker_alive)
        self.assertEqual(runtime.status().state, VoiceState.STOPPED)
        result = runtime.speak("This is after shutdown.").wait(0.2)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.error_code, VoiceErrorCode.SHUTDOWN)

    def test_failure_classifier_uses_types_and_status_not_exception_text(self) -> None:
        self.assertEqual(classify_voice_failure(StatusFailure(401)), VoiceErrorCode.AUTH)
        self.assertEqual(
            classify_voice_failure(StatusFailure(404)),
            VoiceErrorCode.VOICE_UNAVAILABLE,
        )
        self.assertEqual(
            classify_voice_failure(StatusFailure(429)),
            VoiceErrorCode.QUOTA_OR_RATE_LIMIT,
        )
        self.assertEqual(
            classify_voice_failure(StatusFailure(503)), VoiceErrorCode.SERVICE
        )
        self.assertEqual(classify_voice_failure(TimeoutError()), VoiceErrorCode.TIMEOUT)
        self.assertEqual(classify_voice_failure(ConnectionError()), VoiceErrorCode.NETWORK)
        self.assertEqual(classify_voice_failure(ImportError()), VoiceErrorCode.DEPENDENCY)


class ElevenLabsAdapterTests(unittest.TestCase):
    def test_cancel_active_closes_the_provider_transport(self) -> None:
        class ClosableAudio:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        provider = ElevenLabsProvider(
            "unit-test-credential",
            client_factory=lambda **kwargs: object(),
        )
        audio = ClosableAudio()
        with provider._active_audio_lock:
            provider._active_audio = audio

        provider.cancel_active()

        self.assertTrue(audio.closed)

    def test_convert_realtime_uses_streaming_pcm_without_network(self) -> None:
        class FakeTextToSpeech:
            def __init__(self) -> None:
                self.arguments: dict[str, object] | None = None

            def convert_realtime(self, **arguments: object) -> Iterator[bytes]:
                self.arguments = arguments
                text = arguments["text"]
                assert isinstance(text, Iterable)
                self.received_text = list(text)
                return iter((b"one", b"two"))

        tts = FakeTextToSpeech()
        factory_calls: list[dict[str, object]] = []

        class FakeClient:
            text_to_speech = tts

        def client_factory(**arguments: object) -> FakeClient:
            factory_calls.append(arguments)
            return FakeClient()

        provider = ElevenLabsProvider("unit-test-credential", client_factory=client_factory)
        config = configured(streaming=True, output_format="pcm_24000")
        audio = list(
            provider.stream_audio(
                ("First sentence.", "Second sentence."),
                config,
                threading.Event(),
            )
        )

        self.assertEqual(audio, [b"one", b"two"])
        self.assertEqual(tts.received_text, ["First sentence.", "Second sentence."])
        assert tts.arguments is not None
        self.assertEqual(tts.arguments["voice_id"], config.voice_id)
        self.assertEqual(tts.arguments["model_id"], config.model_id)
        self.assertEqual(tts.arguments["output_format"], "pcm_24000")
        self.assertEqual(tts.arguments["request_options"], {"max_retries": 0})
        self.assertEqual(factory_calls[0]["timeout"], 20.0)
        self.assertNotIn("unit-test-credential", repr(provider))

    def test_http_stream_mode_joins_text_and_disables_provider_logging(self) -> None:
        class FakeTextToSpeech:
            def __init__(self) -> None:
                self.arguments: dict[str, object] | None = None

            def stream(self, **arguments: object) -> Iterator[bytes]:
                self.arguments = arguments
                return iter((b"http",))

        tts = FakeTextToSpeech()

        class FakeClient:
            text_to_speech = tts

        provider = ElevenLabsProvider(
            "unit-test-credential",
            client_factory=lambda **kwargs: FakeClient(),
        )
        audio = list(
            provider.stream_audio(
                ("one", "two"),
                configured(streaming=False),
                threading.Event(),
            )
        )

        self.assertEqual(audio, [b"http"])
        assert tts.arguments is not None
        self.assertEqual(tts.arguments["text"], "one two")
        self.assertFalse(tts.arguments["enable_logging"])


class SoundDeviceSinkTests(unittest.TestCase):
    def test_raw_pcm_sink_starts_writes_closes_and_aborts_idempotently(self) -> None:
        class FakeRawStream:
            def __init__(self, **arguments: object) -> None:
                self.arguments = arguments
                self.started = 0
                self.writes: list[bytes] = []
                self.stopped = 0
                self.aborted = 0
                self.closed = 0

            def start(self) -> None:
                self.started += 1

            def write(self, value: bytes) -> None:
                self.writes.append(value)

            def stop(self, **kwargs: object) -> None:
                self.stopped += 1

            def abort(self, **kwargs: object) -> None:
                self.aborted += 1

            def close(self, **kwargs: object) -> None:
                self.closed += 1

        class FakeSoundDevice:
            def __init__(self) -> None:
                self.streams: list[FakeRawStream] = []

            def RawOutputStream(self, **arguments: object) -> FakeRawStream:
                stream = FakeRawStream(**arguments)
                self.streams.append(stream)
                return stream

        module = FakeSoundDevice()
        sink = SoundDevicePcmSink(7, sounddevice_module=module)
        sink.start(sample_rate=24_000)
        sink.start(sample_rate=24_000)
        sink.write(b"pcm")
        sink.close()
        sink.close()

        self.assertEqual(len(module.streams), 1)
        stream = module.streams[0]
        self.assertEqual(stream.arguments["samplerate"], 24_000)
        self.assertEqual(stream.arguments["device"], 7)
        self.assertEqual(stream.arguments["dtype"], "int16")
        self.assertEqual(stream.arguments["latency"], "low")
        self.assertEqual(stream.started, 1)
        self.assertEqual(stream.writes, [b"pcm"])
        self.assertEqual(stream.stopped, 1)
        self.assertEqual(stream.closed, 1)

        aborting = SoundDevicePcmSink(sounddevice_module=module)
        aborting.start(sample_rate=24_000)
        aborting.abort()
        aborting.abort()
        self.assertEqual(module.streams[1].aborted, 1)
        self.assertEqual(module.streams[1].closed, 1)


if __name__ == "__main__":
    unittest.main()
