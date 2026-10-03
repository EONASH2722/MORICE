import os
import time
from unittest.mock import Mock, patch
import pytest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['MORICE_DISABLE_SESSION']='1'
os.environ['MORICE_PRELOAD']='0'
from PySide6.QtWidgets import QApplication
from morice.pyside_app import MoriceWindow, InlineGraphWorkspace
from morice.visualization import VisualizationResult
from morice import settings, llm_client


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv('MORICE_PRELOAD','0')
    app=QApplication.instance() or QApplication([])
    with patch('morice.settings._settings_dir',return_value=str(tmp_path)):
        widget=MoriceWindow()
        widget.awake=True
        widget.show()
        app.processEvents()
        yield widget,app
        widget.close()
        app.processEvents()


def test_live_identity_affects_normal_errors_and_voice_text(window):
    widget,app=window
    assert widget.user_title=='' and widget.preferred_name==''
    assert widget._address('Hello.')=='Hello.'
    assert widget.personalization_btn.text()=='Personalization: Off'
    widget.title_input.setText('  Boss\n ')
    widget.on_save_response_style()
    assert widget._address('Hello.').startswith('Boss,')
    assert 'Boss' in llm_client._friendly_local_timeout_reply()
    assert 'Custom' in widget.personalization_btn.text()
    assert 'Boss' in widget.hero_label.text()
    widget.title_input.clear()
    widget.name_input.setText('李 Mira')
    widget.on_save_response_style()
    assert widget._address('Hello.').startswith('李 Mira,')
    messages=llm_client._conversation_messages([], 'Hello')
    assert any('李 Mira' in message['content'] for message in messages if message['role']=='system')
    widget.on_clear_response_style()
    assert widget._address('Hello.')=='Hello.'
    assert 'Boss' not in widget.input.placeholderText()
    assert settings.load_settings()['preferred_name']==''
    assert widget.personalization_btn.text()=='Personalization: Off'


def test_precision_is_saved_and_accessible(window):
    widget,app=window
    widget.on_toggle_precision()
    assert not widget.precision_mode and not widget.precision_btn.isChecked()
    assert settings.load_settings()['precision_mode']=='false'
    assert 'verification pass' in widget.precision_btn.toolTip()
    assert widget.precision_btn.accessibleName()=='Precision'


@pytest.mark.parametrize('width',[360,480,620,760,1000,1200])
def test_controls_always_have_overflow_access(window,width):
    widget,app=window
    widget.input_frame.setFixedWidth(width)
    widget._update_composer_responsive_state()
    assert not widget.quick_actions_btn.isHidden()
    controls=(widget.attach_btn,widget.voice_btn,widget.model_selector_btn,widget.project_selector_btn,widget.quick_actions_btn)
    assert all(button.toolTip() and button.accessibleName() for button in controls)
    assert widget.attach_btn.icon().cacheKey()!=widget.project_selector_btn.icon().cacheKey()
    if width>=1100: assert [button.text() for button in controls]==['Files','Voice','Model','Project','Tools']


def test_failed_render_does_not_display_graph_or_claim_success(window):
    widget,app=window
    card=Mock()
    widget.visualization_cards['forced-failure']=card
    with patch.object(widget,'append_message') as append, patch.object(widget,'_speak_assistant_text'), patch.object(widget,'_complete_agent_ui'):
        widget._on_visualization_finished(VisualizationResult('forced-failure','failed','math.graph',error='Controlled graph render failure'))
    card.set_error.assert_called_once()
    assert 'could not render' in append.call_args.args[1]
    assert not widget.chat_list.findChildren(InlineGraphWorkspace)


def test_graph_reply_explains_computed_properties(window):
    widget,app=window
    from morice.science_engine import build_graph_artifact
    artifact=build_graph_artifact('plot y=x^2-6*x+8')
    reply=widget._science_ready_reply(artifact)
    assert 'Real roots: 2, 4' in reply and 'Vertex (3, -1)' in reply
    assert reply.index('Real roots')<reply.index('Render validation')
