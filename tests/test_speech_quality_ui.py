from types import SimpleNamespace
from unittest.mock import Mock
from test_fast_memory_ui import app,window,pump
from morice.speech_runtime import SpeechInputState,SpeechInputStatus


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
