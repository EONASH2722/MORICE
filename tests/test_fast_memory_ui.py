"""Exercise model/memory controls and anchored scrolling through the actual Qt shell."""
from __future__ import annotations

import os
from pathlib import Path
import time
from unittest.mock import Mock,patch

import pytest
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from morice import settings
from morice.runtime_services import RuntimeServices
from morice.ui_next.shell import RenovatedWindow
from morice.pyside_app import ChatBubble
from morice.premium_experience import MAX_VISIBLE_CHAT_WIDGETS


@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path,app):
    with patch.dict(os.environ,APPDATA=str(tmp_path/'roaming'),LOCALAPPDATA=str(tmp_path/'local'),
        MORICE_LOCAL_DATA_DIR=str(tmp_path/'data'),MORICE_DISABLE_SESSION='1',
        MORICE_DISABLE_RECOVERY='1',MORICE_PRELOAD='0',MORICE_NODE_NETWORK='0',MORICE_REDUCE_MOTION='1',MORICE_START_AWAKE='1',MORICE_WEB='0'), \
        patch('morice.settings._settings_dir',return_value=str(tmp_path/'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false','pet_enabled':'false'})
        runtime=RuntimeServices(tmp_path/'runtime',project_root=Path(__file__).resolve().parents[1])
        with patch('morice.runtime_services._RUNTIME_SERVICES',runtime):
            view=RenovatedWindow(runtime,runtime.start());view.show();view.navigate('chats');app.processEvents()
            try:yield view
            finally:
                view.wake_controller.cancel();view.close();app.processEvents();runtime.shutdown();view.deleteLater()
                QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()


def pump(app,predicate,timeout=10):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        QTest.qWait(10)
    assert predicate()


def test_scrolling_earlier_keeps_anchor_and_retains_newer_messages(window,app):
    window.follow_latest=True
    for index in range(140):window.append_message('MORICE',f'Visible fixture message {index}',force_scroll=False)
    app.processEvents();QTest.qWait(100);app.processEvents()
    assert len(window._message_rows)==MAX_VISIBLE_CHAT_WIDGETS
    assert window._archived_messages
    window.follow_latest=False
    anchor=window._message_rows[0]
    anchor_text=anchor.findChild(ChatBubble).message
    window._load_earlier_messages()
    pump(app,lambda:not window._loading_history)
    assert any(r is anchor for r in window._message_rows)
    assert len(window._message_rows)==MAX_VISIBLE_CHAT_WIDGETS
    assert window._newer_messages
    assert window._message_rows[0].findChild(ChatBubble).message!=anchor_text
    window.append_message('MORICE','New output while reading earlier',force_scroll=False)
    assert any(r is anchor for r in window._message_rows)
    window._load_history_page(earlier=False)
    pump(app,lambda:not window._loading_history)
    assert len(window._message_rows)<=MAX_VISIBLE_CHAT_WIDGETS


def test_model_controls_and_real_chat_route_use_selected_fast_provider(window,app,tmp_path,monkeypatch):
    fast=tmp_path/'fast.gguf';fast.write_bytes(b'GGUF')
    thinking=tmp_path/'thinking.gguf';thinking.write_bytes(b'GGUF')
    window.model_path=str(thinking);window.settings.update(model_path=str(thinking),generative_model_path=str(fast),automatic_model_selection='true')
    controls=window.routes['settings'].fast_model_settings
    controls.refresh();assert str(fast)==controls.path.text()
    calls=[]
    def stream(history,text,**kwargs):
        calls.append(kwargs);yield 'A streamed answer.'
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    window.input.setText('Explain a simple everyday idea in one sentence.');window.on_send()
    pump(app,lambda:bool(calls) and not window.is_busy)
    assert calls[0]['gguf_path']==str(fast) and not calls[0]['enable_reasoning']
    assert window.model_path==str(thinking)
    assert [m['role'] for m in window.history]==['user','assistant']
    calls.clear();window.input.setText('What is 4 + 7?');window.on_send();app.processEvents()
    assert not calls and '11' in window.history[-1]['content']


def test_chat_thinking_level_reaches_provider_and_is_not_a_settings_control(window,app,tmp_path,monkeypatch):
    model=tmp_path/'owned-thinking.gguf';model.write_bytes(b'GGUF')
    window.settings.update(model_path=str(model),automatic_model_selection='true')
    window.model_path=str(model);calls=[]
    def stream(history,text,**kwargs):calls.append(kwargs);yield 'An owned streamed reply.'
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    assert window.thinking_level.parentWidget() is window.composer
    assert window.thinking_level.count()==4
    window.thinking_level.setCurrentIndex(window.thinking_level.findData('extra_high'))
    window.input.setText('Explain a simple everyday idea in one sentence.');window.on_send()
    pump(app,lambda:bool(calls) and not window.is_busy)
    assert calls[0]['gguf_path']==str(model) and calls[0]['enable_reasoning']
    assert calls[0]['thinking_level']=='extra_high' and calls[0]['max_tokens']>=8192
    window.thinking_level.setCurrentIndex(0)


def test_memory_controls_approve_correct_forget_and_chat_navigation(window,app):
    panel=window.routes['settings'].memory_settings
    panel.flags['personal_memory_enabled'].setChecked(True)
    panel.content.setText('For coding tasks give detailed implementation steps.');panel.save(False)
    assert panel.records.count()==1
    panel.records.setCurrentRow(0);panel.content.setText('For coding tasks prefer concise steps.');panel.save(True)
    assert 'concise' in window.runtime.desktop.memory.preferences_for('implement an app')[0].content
    window.runtime.chat_history.save(window._chat_id,[{'role':'user','content':'Use the name Project Orion.'},
        *[{'role':'assistant','content':f'Later update {n}'} for n in range(200)]],merge=True)
    source=window.runtime.chat_history.search_messages(window._chat_id,'Orion')[0]
    window._jump_to_message(source['message_id']);app.processEvents()
    assert any(r.property('messageId')==source['message_id'] for r in window._message_rows)
    assert any('Project Orion' in r.findChild(ChatBubble).message for r in window._message_rows)
    assert window.active_route=='chats'
    panel.records.setCurrentRow(0);panel.forget();assert not window.runtime.desktop.memory.preferences_for('implement an app')


def test_long_chat_context_retrieval_reaches_model_without_duplicate_user_turn(window,app,monkeypatch):
    window._session_enabled=True
    messages=[{'role':'user','content':'Use the name Project Orion.'},
        *[{'role':'assistant','content':f'Routine update {n}'} for n in range(1000)]]
    window._get_chat_history().save(window._chat_id,messages,merge=True)
    window.history=window._get_chat_history().open(window._chat_id,recent=100)['messages']
    window.first_user_message='Use the name Project Orion.'
    calls=[]
    def stream(history,text,**kwargs):
        calls.append((history,text,kwargs));yield 'The original name was Project Orion.'
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    query='What name did I choose at the beginning?';window.input.setText(query);window.on_send()
    pump(app,lambda:bool(calls) and not window.is_busy)
    assert 'Project Orion' in calls[0][2]['extra_system']
    assert not any(m['content']==query for m in calls[0][0])
    assert len(window._get_chat_history().search_messages(window._chat_id,'name',role='user'))==2
    assert window._last_memory_sources[0]['sequence']==1


def test_streaming_does_not_scroll_away_from_older_messages(window,app):
    window.follow_latest=True
    for index in range(120):window.append_message('MORICE',f'Older row {index}',force_scroll=False)
    app.processEvents();QTest.qWait(100);app.processEvents()
    window.follow_latest=False
    anchor=window._message_rows[0]
    window._on_assistant_stream_delta('reading-test','First streaming phrase. ')
    assert not window.follow_latest and window._stream_deferred
    assert any(row is anchor for row in window._message_rows)
    window._on_assistant_stream_delta('reading-test','Second streaming phrase.')
    window._on_assistant_stream_finished('reading-test','First streaming phrase. Second streaming phrase.')
    app.processEvents()
    assert not window.follow_latest
    assert any(row is anchor for row in window._message_rows)
    assert any('Second streaming phrase' in record[1] for record in window._newer_messages)


def test_disabled_chat_memory_blocks_natural_recall_shortcuts(window,app,monkeypatch):
    window.settings['chat_memory_enabled']='false'
    window.first_user_message='An earlier private fixture.'
    lookup=Mock(side_effect=AssertionError('Disabled memory must not search history'))
    monkeypatch.setattr(window._get_chat_history(),'search_messages',lookup)
    window.input.setText('What was my first message?');window.on_send();app.processEvents()
    assert 'Current-chat memory is off' in window.history[-1]['content']
    lookup.assert_not_called()


def test_streamed_reply_is_not_loaded_again_when_scrolling_down(window,app,monkeypatch):
    window._session_enabled=True
    window._render_chat_messages([])
    window.user_title='Sir'
    reply='A single reply with a second paragraph.\n\nThis must remain in the same message.'
    stream=Mock(side_effect=lambda *args,**kwargs:iter([reply]))
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    window.input.setText('Explain a simple everyday idea in one sentence.');window.on_send()
    pump(app,lambda:len(window.history)==2 and not window.is_busy)
    stream.assert_called_once()
    assert window.history[-1]['content']==reply
    assert len(window.history)==2
    assert len(window._message_rows)==2,[row.findChild(ChatBubble).message for row in window._message_rows]
    window._load_history_page(earlier=False)
    pump(app,lambda:not window._loading_history)
    assert len(window._message_rows)==2
    assert all(row.property('messageId') for row in window._message_rows)
    assert len({row.property('messageId') for row in window._message_rows})==2
    # Identical text in a later turn is still a separate message with its own ID.
    window.input.setText('Explain a simple everyday idea in one sentence.');window.on_send()
    pump(app,lambda:len(window.history)==4 and not window.is_busy)
    assert stream.call_count==2
    window._load_history_page(earlier=False)
    pump(app,lambda:not window._loading_history)
    assert len(window._message_rows)==4
    assert len({row.property('messageId') for row in window._message_rows})==4
    assert len(window._get_chat_history().open(window._chat_id)['messages'])==4
    # An identical older turn outside the visible window cannot supply the ID
    # for a new question/answer pair, either.
    window._render_chat_messages(window.history[-2:])
    window.input.setText('Explain a simple everyday idea in one sentence.');window.on_send()
    pump(app,lambda:len(window.history)==6 and not window.is_busy)
    assert stream.call_count==3
    window._load_history_page(earlier=False)
    pump(app,lambda:not window._loading_history)
    assert [row.property('messageId') for row in window._message_rows]==[m['message_id'] for m in window.history[-4:]]
    assert len(window._get_chat_history().open(window._chat_id)['messages'])==6


def test_returning_to_latest_does_not_append_the_saved_reply_twice(window,app):
    window._session_enabled=True
    window.history=[{'role':'assistant','content':f'Earlier answer {n}'} for n in range(130)]
    window._persist_chat_history()
    window._render_chat_messages(window.history[-100:])
    window._load_earlier_messages()
    pump(app,lambda:not window._loading_history)
    assert window._newer_messages
    window.user_title='Sir'
    reply=window._address('The latest answer appears once.')
    window._remember_conversation_turn('A new question.',reply)
    window.append_message('MORICE',reply,force_scroll=True)
    window._persist_chat_history()
    assert sum(row.findChild(ChatBubble).message==reply for row in window._message_rows)==1
    assert len({row.property('messageId') for row in window._message_rows})==len(window._message_rows)


def test_informal_date_question_uses_the_clock_once(window,app,monkeypatch):
    window._session_enabled=True
    window._render_chat_messages([])
    stream=Mock(side_effect=AssertionError('Clock commands must not invoke a model'))
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    window.input.setText('whats the date today');window.on_send()
    pump(app,lambda:len(window.history)==2)
    assert 'Today is ' in window.history[-1]['content']
    window._load_history_page(earlier=False)
    pump(app,lambda:not window._loading_history)
    assert len(window._message_rows)==2
    stream.assert_not_called()


def test_long_engineering_analysis_reaches_thinking_model_intact(window,app,tmp_path,monkeypatch):
    prompt=('Independent engineering audit and optimization challenge\n\n'
        'Audit a vibration harvester using a coupled mechanical and electromagnetic model. '
        'Compare assumptions, experimental research and numerical simulation. '
        'Do not generate code or a PDF. Give calculations, numerical results and recommendations.\n\n'
        + '\n'.join(f'{i}. Evaluate spring suspension, mechanical damping, coil losses and efficiency under case {i}.' for i in range(90)))
    model=tmp_path/'thinking.gguf';model.write_bytes(b'GGUF')
    window.settings.update(model_path=str(model),model_name='')
    calls=[]
    def stream(history,text,**kwargs):
        calls.append((history,text,kwargs));yield 'An analytical answer with assumptions and calculations.'
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    window.input.setText(prompt);window.on_send()
    pump(app,lambda:bool(calls) and not window.is_busy)
    assert calls[0][1]==prompt
    assert calls[0][2]['gguf_path']==str(model) and calls[0][2]['enable_reasoning']
    assert calls[0][2]['context_tokens']>=16384
    assert calls[0][2]['max_tokens']>=6144
    assert [m['role'] for m in window.history]==['user','assistant']
    assert not window._research_project_id and not window.visualization_cards
    assert 'analytical answer' in window.history[-1]['content']


def test_completed_processing_does_not_accept_delayed_generation_updates(window,app):
    window._show_thinking('Checking the request.')
    token=window._thinking_token
    bubble=window.thinking_bubble
    window._on_message_ready('MORICE','Completed analysis.',False)
    completed=bubble.detail_label.text()
    window._thinking_delayed_update(token,'Qwen is still generating.')
    window._on_thinking_update('Qwen is still generating.')
    app.processEvents()
    assert bubble.detail_label.text()==completed
    assert '[active]' not in completed


def test_tabletop_engineering_prompt_reaches_model_without_device_or_prompt_data_panel(window,app,tmp_path,monkeypatch):
    from morice.ui_next.rich_response import RichResponseHost
    prompt=('# PROJECT ARC-0.3 — Advanced engineering innovation challenge\n\n'
        'Act as an independent engineering research team. Review a battery-powered standalone tabletop generator. '
        'Compare six architectures using numerical reasoning, not a final product. '
        'Discuss physics, spring suspension and numerical simulation; no final 3D-printed rotor.\n\n'
        '| Parameter | Value |\n| --- | --- |\n| Motor speed | 600 rpm |\n| Battery input | 2.5 W |\n'
        '| Effective flux | 0.22 T, assumed |\n\n'
        'Do not generate final CAD, purchasing lists or assembly manuals. '
        'Explain assumptions and provide a written comparison table. All input figures are unverified estimates.')
    model=tmp_path/'thinking.gguf';model.write_bytes(b'GGUF')
    window.settings.update(model_path=str(model),model_name='',automatic_model_selection='false')
    calls=[]
    def stream(history,text,**kwargs):
        calls.append(text)
        yield 'The comparison needs explicit loss assumptions.\n\n| Concept | Evidence |\n| --- | --- |\n| Axial flux | Assumed geometry |'
    remote=Mock(side_effect=AssertionError('Engineering analysis must not call a paired device.'))
    monkeypatch.setattr(window.runtime,'send_node_task',remote)
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    window.input.setText(prompt);window.on_send()
    pump(app,lambda:bool(calls) and not window.is_busy)
    assert calls==[prompt], [m['content'] for m in window.history if m['role']=='assistant']
    remote.assert_not_called()
    assert [m['role'] for m in window.history]==['user','assistant']
    assert 'comparison needs' in window.history[-1]['content']
    assert not window.findChildren(RichResponseHost)


def test_queued_activity_after_close_does_not_refresh_retired_workspace(window,app,monkeypatch):
    from PySide6.QtCore import QTimer
    assert not window.assistant_hub.isVisible()
    rebuild=Mock(side_effect=AssertionError('The hidden legacy item models must not be rebuilt by chat activity.'))
    monkeypatch.setattr(window.assistant_hub,'set_desktop_state',rebuild)
    window._record_activity('Owned current activity','Stored through the live owner.')
    assert window.workspace_state.activity[-1].title=='Owned current activity'
    delivered=[]
    def late():
        window._record_activity('Owned stale activity','Queued before closing.')
        delivered.append(True)
    QTimer.singleShot(0,late);window.close();pump(app,lambda:bool(delivered))
    assert window._is_closing
    assert not any(row.title=='Owned stale activity' for row in window.workspace_state.activity)
    rebuild.assert_not_called()


def test_research_uses_installed_default_model_without_custom_selection(window,app,tmp_path,monkeypatch):
    from morice.research.providers import ResearchProvider
    model=tmp_path/'installed-default.gguf';model.write_bytes(b'GGUF')
    window.model_name=window.model_path=''
    window.settings.update(model_name='',model_path='')
    calls=[]
    monkeypatch.setattr('morice.llm_client._resolve_gguf_path',lambda *args:str(model))
    def provider(name,path):
        calls.append((name,path))
        return ResearchProvider('test-default',frozenset({'synthesis'}),lambda *args:'A substantive interpretation of the supplied assumptions.')
    monkeypatch.setattr('morice.research.providers.selected_local_provider',provider)
    window.input.setText('Research energy harvesting assumptions.');window.on_send()
    pump(app,lambda:bool(calls) and not window.is_busy)
    assert calls[0][1]==str(model)
    assert [m['role'] for m in window.history]==['user','assistant']
    assert 'substantive interpretation' in window.history[-1]['content']
    assert window.thinking_bubble.property('completed')=='true'


def test_engineering_calculation_and_interpretation_share_one_reply(window,app,monkeypatch):
    from test_harvester_calculations import TABLE
    window._session_enabled=True
    window._render_chat_messages([])
    calls=[]
    def stream(history,text,**kwargs):
        calls.append((text,kwargs));yield 'Review measured damping before selecting hardware.'
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    window.input.setText(TABLE);window.on_send()
    pump(app,lambda:bool(calls) and not window.is_busy,timeout=20)
    assert calls[0][0]==TABLE.strip()
    assert 'Verified conditional calculation' in calls[0][1]['extra_system']
    assert 'Mechanical input (mW)' in calls[0][1]['extra_system']
    assert [m['role'] for m in window.history]==['user','assistant']
    reply=window.history[-1]['content']
    assert 'Calculated baseline' in reply and 'Review measured damping' in reply
    window._load_history_page(earlier=False)
    pump(app,lambda:not window._loading_history)
    assert len(window._message_rows)==2,[(r.property('messageId'),r.findChild(ChatBubble).message[:120]) for r in window._message_rows]


def test_desktop_automation_toggle_and_disabled_chat_guidance(window,app,monkeypatch):
    from morice.pc_control import PermissionCategory,PolicyMode
    from morice.unified_intelligence import PermissionState
    controls=window.routes['settings'].control_settings
    assert not controls.desktop.isChecked() and not window.runtime.desktop_automation_enabled
    stream=Mock(side_effect=AssertionError('Disabled PC requests must not be handed to a model'))
    execute=Mock(side_effect=AssertionError('Disabled PC control must not execute'))
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    monkeypatch.setattr(window.runtime.pc_control,'execute',execute)
    window.input.setText('Open Notepad');window.on_send()
    pump(app,lambda:len(window.history)==2 and not window.is_busy)
    assert 'turn on Desktop automation in Settings' in window.history[-1]['content']
    execute.assert_not_called();stream.assert_not_called()
    controls.desktop.setChecked(True);app.processEvents()
    assert window.runtime.pc_permissions.policy(PermissionCategory.DESKTOP_AUTOMATION)==PolicyMode.ALLOW
    assert window.runtime.unified_permissions.state('desktop_automation')==PermissionState.GRANTED
    controls.desktop.setChecked(False);app.processEvents()
    assert not window.runtime.desktop_automation_enabled
    assert window.settings['desktop_automation_enabled']=='false'


def test_natural_first_party_navigation_and_theme_use_actual_state(window,app,monkeypatch):
    window._session_enabled=True;window._render_chat_messages([])
    model=Mock(side_effect=AssertionError('UI commands must not initialize a model'))
    pc=Mock(side_effect=AssertionError('MORICE navigation must not automate external apps'))
    monkeypatch.setattr('morice.pyside_app.stream_chat',model)
    monkeypatch.setattr(window.runtime.pc_control,'execute',pc)
    window.input.setText('Open Settings.');window.on_send();app.processEvents()
    assert window.active_route=='settings' and window.composer.isVisible()
    assert [m['role'] for m in window.history]==['user','assistant']
    window.input.setText('Change the primary color to purple.');window.on_send();app.processEvents()
    assert window.theme_engine.profile.primary_accent=='#a855f7'
    assert window.theme_engine.store.load().primary_accent=='#a855f7'
    window.input.setText('Go back to Chat.');window.on_send();app.processEvents()
    assert window.active_route=='chats'
    assert len(window.history)==6
    assert len(window._message_rows)==6
    assert len({r.property('messageId') for r in window._message_rows})==6
    assert not window.runtime.desktop_automation_enabled
    model.assert_not_called();pc.assert_not_called()
    purple=window.theme_engine.profile.to_dict()
    window.input.setText('Make Core smaller');window.on_send();app.processEvents()
    assert window.theme_engine.profile.core_scale==pytest.approx(purple['core_scale']-.1)
    window.input.setText('Undo that appearance change');window.on_send();app.processEvents()
    assert window.theme_engine.profile.to_dict()==purple
    window.input.setText('Use compact responses');window.on_send();app.processEvents()
    assert window.settings['response_presentation']=='compact'
    window.input.setText('Turn off precision mode');window.on_send();app.processEvents()
    assert not window.precision_mode


def test_natural_research_selection_is_async_and_keeps_one_row_per_turn(window,app,monkeypatch):
    window._session_enabled=True;window._render_chat_messages([])
    store=window.runtime.research.store
    store.create('Energy alpha');store.create('Energy beta')
    monkeypatch.setattr('morice.pyside_app.stream_chat',Mock(side_effect=AssertionError('Saved research uses no model')))
    window.input.setText('Open my energy research');window.on_send()
    pump(app,lambda:not window.is_busy)
    assert 'Which research notebook' in window.history[-1]['content']
    pending=window.runtime.nlui._pending[window._chat_id]
    chosen=pending['choices'][1]['id']
    assert pending['question_turn_key']==window.nlui_port.context().last_turn_key
    window.input.setText('the second');window.on_send()
    pump(app,lambda:not window.is_busy)
    assert window.active_route=='research'
    assert window.routes['research'].project_id==chosen
    assert window._research_project_id==chosen
    assert [m['role'] for m in window.history]==['user','assistant','user','assistant']
    assert len(window._message_rows)==4
    assert window.runtime.chat_history.get_ui_state(window._chat_id,'nlui_pending') is None
