from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_fast_memory_ui import app,window,pump
from morice.speech_runtime import SpeechInputState,SpeechInputStatus


def fake_capture(window, monkeypatch):
    from dataclasses import replace
    callbacks = {}
    status = SpeechInputStatus(SpeechInputState.IDLE, False, True, None)
    monkeypatch.setattr(window.runtime.speech_input, 'status', lambda: status)
    voice_status = replace(window.runtime.voice.status(), active=False)
    monkeypatch.setattr(window.runtime.voice, 'status', lambda: voice_status)

    def listen(**options):
        callbacks.update(options)
        return SimpleNamespace(request_id=options.get('request_id', 'owned-first-capture'))

    monkeypatch.setattr(window.runtime.speech_input, 'listen_once', listen)
    window.chat_mode = 'voice'
    window._voice_conversation_active = True
    window._live_microphone_paused = False
    window.is_busy = False
    window.input.setText('Current draft')
    window._begin_voice_listening()
    return callbacks


def test_queued_partial_from_replaced_capture_cannot_change_the_new_draft(window, app, monkeypatch):
    import threading
    callbacks = fake_capture(window, monkeypatch)
    try:
        worker = threading.Thread(target=lambda: callbacks['on_partial']('obsolete transcript'))
        worker.start(); worker.join(1)
        assert not worker.is_alive()
        window._speech_input_request_id = 'owned-replacement-capture'
        window.input.setText('New session draft')
        app.processEvents()
        assert window.input.text() == 'New session draft'
    finally:
        window._voice_conversation_active = False
        window.chat_mode = 'normal'


def test_queued_partial_after_voice_settings_save_cannot_modify_the_draft(window, app, monkeypatch):
    import threading
    callbacks = fake_capture(window, monkeypatch)
    try:
        worker = threading.Thread(target=lambda: callbacks['on_partial']('obsolete transcript'))
        worker.start(); worker.join(1)
        assert not worker.is_alive()
        window._save_voice_settings()
        app.processEvents()
        assert window.input.text() == 'Current draft'
        assert not window._speech_input_request_id
    finally:
        window._voice_conversation_active = False
        window.chat_mode = 'normal'


@pytest.mark.parametrize('resume', [False, True])
def test_queued_final_after_microphone_pause_cannot_submit_a_request(window, app, monkeypatch, resume):
    import threading
    from PySide6.QtTest import QTest
    from morice.speech_runtime import TranscriptResult
    callbacks = fake_capture(window, monkeypatch)
    send = Mock(); monkeypatch.setattr(window, 'on_send', send)
    result = TranscriptResult(window._speech_input_request_id, 'obsolete request', 1.)
    try:
        worker = threading.Thread(target=lambda: callbacks['on_complete'](result))
        worker.start(); worker.join(1)
        assert not worker.is_alive()
        window._on_live_microphone_requested(False)
        if resume:
            monkeypatch.setattr(window, '_begin_voice_listening', Mock())
            window._on_live_microphone_requested(True)
        QTest.qWait(120); app.processEvents()
        assert window.input.text() == 'Current draft'
        assert not send.called
    finally:
        window._live_microphone_paused = False
        window._voice_conversation_active = False
        window.chat_mode = 'normal'


def test_current_capture_delivers_partial_and_submits_final_only_once(window, app, monkeypatch):
    from PySide6.QtTest import QTest
    from morice.speech_runtime import TranscriptResult
    callbacks = fake_capture(window, monkeypatch)
    send = Mock(); monkeypatch.setattr(window, 'on_send', send)
    request_id = window._speech_input_request_id
    try:
        callbacks['on_partial']('live words'); app.processEvents()
        assert window.input.text() == 'Current draft live words'
        result = TranscriptResult(request_id, 'final words', 1.)
        callbacks['on_complete'](result)
        callbacks['on_complete'](result)
        QTest.qWait(120); app.processEvents()
        assert window.input.text() == 'Current draft final words'
        assert send.call_count == 1
        assert not window._speech_input_request_id
    finally:
        window._voice_conversation_active = False
        window.chat_mode = 'normal'


def test_disabled_speech_input_is_not_presented_as_an_active_recording(window, app, monkeypatch):
    status = SpeechInputStatus(SpeechInputState.DISABLED, False, True, None)
    listen, notify = Mock(), Mock()
    monkeypatch.setattr(window.runtime.speech_input, 'status', lambda: status)
    monkeypatch.setattr(window.runtime.speech_input, 'listen_once', listen)
    monkeypatch.setattr(window, '_show_notification', notify)
    window.chat_mode = 'voice'
    window._voice_conversation_active = True
    window._live_microphone_paused = False
    try:
        assert window._begin_voice_listening() is None
        assert not listen.called
        assert any('disabled' in str(call).casefold() for call in notify.call_args_list)
    finally:
        window._voice_conversation_active = False
        window.chat_mode = 'normal'


def test_orb_reports_disabled_speech_instead_of_waiting_as_if_recording(window, app, monkeypatch):
    from morice.ui_next.wake import WakeState
    status = SpeechInputStatus(SpeechInputState.DISABLED, False, True, None)
    monkeypatch.setattr(window.runtime.speech_input, 'status', lambda: status)
    monkeypatch.setattr(window, '_start_background_task', Mock())
    window.settings.update(active_pet='orb', pet_enabled='true', orb_voice_wake='true')
    window.hide()
    try:
        window._wake_from_external('magic words: morice')
        pump(app, lambda: window.wake_controller.state == WakeState.ERROR)
        assert 'disabled' in window.wake_controller.overlay.state_label.text().casefold()
        assert not window.isVisible()
    finally:
        window.wake_controller.cancel()


def test_voice_settings_save_accuracy_engine_model_and_correction(window,app,tmp_path,monkeypatch):
    panel=window.speech_settings;folder=str(tmp_path/'owned-model')
    panel.provider.setCurrentIndex(panel.provider.findData('whisper'));panel.path.setText(folder)
    panel.correct.setChecked(False);panel.language.setCurrentIndex(panel.language.findData('hi'))
    configure=Mock(return_value=SpeechInputStatus(SpeechInputState.IDLE,False,True,None))
    monkeypatch.setattr(window.runtime.speech_input,'configure',configure)
    window._save_voice_settings()
    config=configure.call_args.args[0]
    assert config.provider=='whisper' and config.accuracy_model_path==folder and not config.autocorrect and config.language=='hi'
    from morice.settings import load_settings
    assert load_settings()['stt_accuracy_model_path']==folder


def test_orb_reports_real_transcription_and_extends_processing_timeout(window,app,monkeypatch):
    from morice.ui_next.wake import WakeState
    from morice.ui_next.core_state import CoreState
    import time
    monkeypatch.setattr(window,'_begin_voice_listening',Mock())
    window.settings.update(active_pet='orb',pet_enabled='true',orb_voice_wake='true')
    window.hide();window._wake_from_external('magic words: morice')
    status=SpeechInputStatus(SpeechInputState.TRANSCRIBING,True,True,None)
    monkeypatch.setattr(window.runtime.speech_input,'status',lambda:status)
    window.wake_controller._speech_progress();window.core_presentation.sample()
    assert window.wake_controller.state==WakeState.UNDERSTANDING
    assert window.wake_controller._deadline-time.monotonic()>40
    assert window.core_presentation.snapshot.state==CoreState.UNDERSTANDING
    assert not window.isVisible() and not window.wake_controller.overlay.isVisible()
