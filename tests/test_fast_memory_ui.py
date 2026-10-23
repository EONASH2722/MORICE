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
    with patch.dict(os.environ,MORICE_LOCAL_DATA_DIR=str(tmp_path/'data'),MORICE_DISABLE_SESSION='1',
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
