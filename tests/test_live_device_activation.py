"""Explicit device gestures start Voice; restoring a page does not capture media."""
from unittest.mock import Mock
import pytest
from PySide6.QtTest import QTest
from test_fast_memory_ui import app,window,pump
from morice.speech_runtime import TranscriptResult


@pytest.mark.parametrize('entry',['navigation','deck','palette','nlui'])
def test_explicit_voice_selection_activates_device_controls(window,app,monkeypatch,entry):
    listen=Mock();monkeypatch.setattr(window,'_begin_voice_listening',listen)
    start=Mock(return_value=True);monkeypatch.setattr(window.live_camera,'start',start)
    window._set_chat_mode('normal')
    if entry=='navigation':window.navigation.buttons['voice'].click()
    elif entry=='deck':window.action_deck.selected.emit('voice')
    elif entry=='palette':window._on_workspace_command('renovation:route:voice')
    else:window.nlui_port._execute('ui.navigate',{'route':'voice'},window._chat_id)
    app.processEvents()
    assert window.active_route=='voice' and window.chat_mode=='voice' and window._voice_conversation_active
    window.live_action_workspace.camera_button.click()
    assert start.called
    pump(app,lambda:listen.called)


def test_restoring_voice_page_keeps_devices_off_until_a_user_gesture(window,app,monkeypatch):
    listen=Mock();monkeypatch.setattr(window,'_begin_voice_listening',listen)
    start=Mock();monkeypatch.setattr(window.live_camera,'start',start)
    window._set_chat_mode('normal');window.navigate('voice')
    QTest.qWait(230);app.processEvents()
    assert window.chat_mode=='normal' and not window._voice_conversation_active
    assert not listen.called and not start.called


@pytest.mark.parametrize('device',['microphone','camera'])
def test_device_gesture_activates_a_passively_restored_voice_page(window,app,monkeypatch,device):
    listen=Mock();monkeypatch.setattr(window,'_begin_voice_listening',listen)
    start=Mock(return_value=True);monkeypatch.setattr(window.live_camera,'start',start)
    window._set_chat_mode('normal');window.navigate('voice')
    view=window.live_action_workspace
    if device=='camera':view.camera_button.click()
    else:view.mic_button.click()
    assert window.chat_mode=='voice'
    pump(app,lambda:listen.called)
    assert start.called==(device=='camera')


@pytest.mark.parametrize('state',['starting','unavailable','error'])
def test_pending_camera_and_failures_remain_visible_and_cancellable(window,app,state):
    view=window.live_action_workspace;requested=[]
    view.cameraRequested.connect(requested.append)
    try:
        view.set_camera_state(state,'Owned camera status fixture')
        assert not view.stage.isHidden()
        assert 'CAMERA OFF' not in view.privacy_label.text()
        assert view.preview.text()=='Owned camera status fixture'
        view.camera_button.click()
        assert requested==[False]
    finally:view.cameraRequested.disconnect(requested.append)


def test_failed_microphone_is_not_presented_as_recording(window,app,monkeypatch):
    monkeypatch.setattr(window,'_begin_voice_listening',Mock())
    window._set_chat_mode('voice');window._speech_input_request_id='owned-device-failure'
    window._on_speech_transcript(TranscriptResult('owned-device-failure','',1.,error_code='audio',message='Microphone stream failed.'))
    assert not window.live_action_workspace._microphone_active
    assert window.live_action_workspace.mic_button.text()=='Resume microphone'
    assert 'failed' in window.live_action_workspace.transcript_label.text().lower()
