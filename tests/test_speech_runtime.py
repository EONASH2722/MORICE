from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from morice.speech_runtime import (
    SpeechInputConfig,
    SpeechInputState,
    SpeechToTextRuntime,
    _SoundDeviceInput,
    find_vosk_model,
)


class FakeRecognizer:
    def __init__(self) -> None:
        self.calls = 0

    def accept(self, _pcm: bytes):
        self.calls += 1
        if self.calls == 1:
            return False, "", "hello"
        return True, "hello morice", ""

    def finish(self) -> str:
        return ""


class FakeAudio:
    def __init__(self, chunks=(b"one", b"two"), gate: threading.Event | None = None):
        self.chunks = list(chunks)
        self.gate = gate
        self.started = False
        self.aborted = False

    def start(self):
        self.started = True

    def read(self, _timeout):
        if self.gate is not None:
            self.gate.wait(1)
        if self.chunks:
            return self.chunks.pop(0)
        time.sleep(0.01)
        return None

    def stop(self):
        return None

    def abort(self):
        self.aborted = True
        if self.gate is not None:
            self.gate.set()


class SpeechRuntimeTests(unittest.TestCase):
    def configured(self, model: str) -> SpeechInputConfig:
        return SpeechInputConfig(model_path=model, max_listen_seconds=2)

    def test_default_audio_block_bounds_interactive_stt_latency(self):
        config = SpeechInputConfig()
        self.assertEqual(config.block_size, 2_000)
        self.assertEqual(config.block_size / config.sample_rate, 0.125)

    def test_model_discovery_prefers_small_interactive_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_root = root / "voice_models"
            for name in ("vosk-model-large", "vosk-model-small-en-us"):
                (model_root / name / "conf").mkdir(parents=True)
            with (
                patch.dict(os.environ, {"MORICE_VOSK_MODEL": ""}),
                patch("morice.speech_runtime.application_root", return_value=root),
            ):
                selected = find_vosk_model()
        self.assertTrue(selected.endswith("vosk-model-small-en-us"))

    def test_frozen_model_discovery_uses_pyinstaller_internal_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            internal = Path(directory) / "_internal"
            model = internal / "voice_models" / "vosk-model-small-frozen"
            (model / "conf").mkdir(parents=True)
            frozen_module = internal / "morice" / "speech_runtime.py"
            with (
                patch.dict(os.environ, {"MORICE_VOSK_MODEL": ""}),
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", str(internal), create=True),
                patch("morice.speech_runtime.__file__", str(frozen_module)),
            ):
                selected = find_vosk_model()

        self.assertEqual(selected, str(model.resolve()))

    def test_listen_is_nonblocking_and_returns_final_transcript(self):
        partials = []
        completed = []
        runtime = SpeechToTextRuntime(
            self.configured("D:/fake-model"),
            recognizer_factory=lambda _path, _rate: FakeRecognizer(),
            audio_factory=lambda _config: FakeAudio(),
        )
        runtime._model_path = "D:/fake-model"
        started = time.perf_counter()
        handle = runtime.listen_once(
            on_partial=partials.append,
            on_complete=completed.append,
        )
        self.assertLess(time.perf_counter() - started, 0.1)
        result = handle.wait(2)
        self.assertEqual(result.text, "hello morice")
        self.assertEqual(partials, ["hello"])
        self.assertEqual(completed, [result])
        self.assertEqual(runtime.status().state, SpeechInputState.IDLE)
        runtime.shutdown()

    def test_cancel_aborts_microphone_and_finishes_safely(self):
        gate = threading.Event()
        audio = FakeAudio(gate=gate)
        runtime = SpeechToTextRuntime(
            self.configured("D:/fake-model"),
            recognizer_factory=lambda _path, _rate: FakeRecognizer(),
            audio_factory=lambda _config: audio,
        )
        runtime._model_path = "D:/fake-model"
        handle = runtime.listen_once()
        deadline = time.monotonic() + 1
        while not audio.started and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertTrue(runtime.cancel())
        result = handle.wait(2)
        self.assertTrue(audio.aborted)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.error_code, "cancelled")
        runtime.shutdown()

    def test_missing_model_fails_without_opening_microphone(self):
        calls = []
        runtime = SpeechToTextRuntime(
            SpeechInputConfig(model_path="D:/missing"),
            audio_factory=lambda config: calls.append(config),
        )
        runtime._model_path = ""
        handle = runtime.listen_once()
        result = handle.wait(0.2)
        self.assertEqual(result.error_code, "model-unavailable")
        self.assertEqual(calls, [])
        runtime.shutdown()

    def test_incompatible_selected_device_falls_back_to_default(self):
        opened = []

        class FakeStream:
            def __init__(self, device):
                self.device = device

            def start(self):
                return None

            def stop(self, **_kwargs):
                return None

            def close(self, **_kwargs):
                return None

        class FakeSoundDevice:
            @staticmethod
            def RawInputStream(**kwargs):
                device = kwargs.get("device")
                opened.append(device)
                if device == 15:
                    raise RuntimeError("Sample format not supported")
                return FakeStream(device)

        audio = _SoundDeviceInput(
            SpeechInputConfig(input_device=15),
            sounddevice_module=FakeSoundDevice(),
        )
        audio.start()
        audio.stop()

        self.assertEqual(opened, [15, None])


if __name__ == "__main__":
    unittest.main()
