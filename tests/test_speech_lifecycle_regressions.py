"""Capture ownership and late warmup completion must not affect a newer session."""
import threading
from unittest.mock import patch

import pytest

from morice.speech_runtime import SpeechInputConfig, SpeechInputState, SpeechToTextRuntime


class BlockingAudio:
    def __init__(self, *, stop_gate=None):
        self.started = threading.Event()
        self.aborted = threading.Event()
        self.stopping = threading.Event()
        self.stop_gate = stop_gate

    def start(self):
        self.started.set()

    def read(self, timeout):
        self.aborted.wait(timeout)
        return None

    def abort(self):
        self.aborted.set()

    def stop(self):
        self.stopping.set()
        if self.stop_gate is not None:
            assert self.stop_gate.wait(3), 'Owned fixture cleanup was not released.'


class EmptyRecognizer:
    def accept(self, pcm):
        return False, '', ''

    def finish(self):
        return ''


def test_old_listen_handle_cannot_cancel_a_replacement_capture():
    stop_gate = threading.Event()
    first, second = BlockingAudio(stop_gate=stop_gate), BlockingAudio()
    audios = iter((first, second))
    runtime = SpeechToTextRuntime(
        SpeechInputConfig(provider='vosk'),
        recognizer_factory=lambda *_: EmptyRecognizer(),
        audio_factory=lambda _: next(audios),
    )
    runtime._model_path = 'owned-fixture'
    try:
        old = runtime.listen_once()
        assert first.started.wait(1)
        current = runtime.listen_once()
        assert first.stopping.wait(1) and second.started.wait(1)
        assert not old.done
        old.cancel()
        assert not second.aborted.is_set(), 'An obsolete handle cancelled the new microphone capture.'
        assert runtime.status().listening
        current.cancel()
        assert current.wait(1).cancelled
    finally:
        stop_gate.set()
        first.abort()
        second.abort()
        runtime.shutdown()


@pytest.mark.parametrize('change', ['disable', 'shutdown', 'new-capture'])
def test_late_failed_prewarm_preserves_the_current_runtime_state(change):
    loading, release = threading.Event(), threading.Event()
    audio = BlockingAudio()

    def recognizer(*_):
        loading.set()
        assert release.wait(3), 'Owned model-load fixture was not released.'
        raise RuntimeError('Owned fixture model load failed.')

    runtime = SpeechToTextRuntime(
        SpeechInputConfig(provider='vosk'),
        recognizer_factory=recognizer,
        audio_factory=lambda _: audio,
    )
    runtime._model_path = 'owned-fixture'
    worker = threading.Thread(target=runtime.prewarm)
    try:
        worker.start()
        assert loading.wait(1)
        if change == 'disable':
            with patch('morice.speech_runtime.find_vosk_model', return_value='owned-fixture'):
                runtime.configure(SpeechInputConfig(enabled=False, provider='vosk'))
        elif change == 'shutdown':
            runtime.shutdown()
        else:
            runtime._recognizer_factory = lambda *_: EmptyRecognizer()
            runtime.listen_once()
            assert audio.started.wait(1)
        expected = runtime.status()
        release.set()
        worker.join(1)
        assert not worker.is_alive()
        assert runtime.status() == expected, 'An old warmup error overwrote the current voice state.'
        assert runtime.status().state != SpeechInputState.ERROR
    finally:
        release.set()
        audio.abort()
        worker.join(1)
        runtime.shutdown()
