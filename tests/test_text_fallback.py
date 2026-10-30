"""Actual failed-render handoff, readable source fallback and request isolation."""
from unittest.mock import Mock
import pytest
from PySide6.QtWidgets import QLabel
from test_fast_memory_ui import app,window,pump
from morice.pyside_app import VisualizationGenerationCard,ChatBubble
from morice.visualization import VisualizationResult
from morice.ui_next.rich_response import RichResponseHost
from morice.rich_response import Component,ResponsePlan,SourceRef
from morice.rich_response.sources import SourceSnapshot
from morice.realtime_intelligence import TieredModelRouter,ModelTier

@pytest.mark.parametrize('prompt',[
    'I need to wash my car. The car wash is 50 meters away. Should I drive or should I walk? Consider the physical world assumptions and see how both scenarios play out logically.',
    'Should I walk to collect the bicycle I left at the repair shop or take a taxi?',
    'But if I walk then what will I clean at the car wash myself?',
])
def test_goal_and_prerequisite_decisions_use_reasoning(prompt):
    assert TieredModelRouter().route(prompt).tier==ModelTier.DEEP

def model_stub(window,tmp_path,monkeypatch):
    window._render_chat_messages([])
    model=tmp_path/'owned-thinking.gguf';model.write_bytes(b'GGUF')
    window.settings.update(model_path=str(model),model_name='',automatic_model_selection='false');calls=[]
    def stream(history,text,**options):
        calls.append((list(history),text,options));yield 'A written comparison can explain the assumptions and tradeoffs without a graph.'
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    return calls

def test_failed_renderer_answers_original_prompt_once_without_losing_draft(window,app,tmp_path,monkeypatch):
    calls=model_stub(window,tmp_path,monkeypatch)
    prompt='Graph the tradeoffs between walking and driving'
    decide=window.visualization_manager.decide;seen=[]
    def count(text):seen.append(text);return decide(text)
    monkeypatch.setattr(window.visualization_manager,'decide',count)
    window.input.setText(prompt);window.on_send();window.input.setText('My unsent next message')
    pump(app,lambda:bool(calls) and not window.is_busy,timeout=30)
    assert len(calls)==1 and calls[0][1]==prompt and seen==[prompt]
    assert 'host visualization failed' in calls[0][2]['extra_system'].lower()
    assert [m['role'] for m in window.history]==['user','assistant']
    assert window.history[0]['content']==prompt and window.history[-1]['text_only']
    assert 'failed' in window.history[-1]['content'] and 'written comparison' in window.history[-1]['content']
    assert window.input.text()=='My unsent next message'
    assert not window.findChildren(RichResponseHost) and len(window._message_rows)==2

def test_widget_construction_failure_uses_same_text_handoff(window,app,tmp_path,monkeypatch):
    calls=model_stub(window,tmp_path,monkeypatch)
    monkeypatch.setattr(window,'_create_science_workspace',Mock(side_effect=RuntimeError('Owned view construction failed')))
    window.input.setText('Plot y=x^2');window.on_send()
    pump(app,lambda:bool(calls) and not window.is_busy,timeout=30)
    assert len(calls)==1 and 'failed' in window.history[-1]['content']
    assert not window.science_artifacts


def test_failed_renderer_reports_when_text_model_also_returns_nothing(window,app,tmp_path,monkeypatch):
    model_stub(window,tmp_path,monkeypatch)
    monkeypatch.setattr('morice.pyside_app.stream_chat',lambda *args,**kwargs:iter(()))
    window.input.setText('Graph tradeoffs between walking and driving');window.on_send()
    pump(app,lambda:not window.is_busy and len(window.history)==2,timeout=30)
    assert 'did not return a text answer' in window.history[-1]['content']
    assert window.history[-1]['text_only']


def test_practical_choice_uses_model_objects_without_reversing_prerequisite(window,app,tmp_path,monkeypatch):
    import json
    model_stub(window,tmp_path,monkeypatch);calls=[]
    def stream(history,text,**options):
        calls.append(options)
        assert options.get('response_schema'),'The final advice must not reverse the checked prerequisite.'
        yield json.dumps({'goal':'repair the instrument','required_objects':['instrument'],
            'already_at_destination':[],'physical_prerequisites':['the instrument must reach the repair shop'],
            'options':[{'action':'carry the instrument','moves_to_destination':['instrument']},
                {'action':'arrive empty-handed','moves_to_destination':['person']}],'uncertainties':[]})
    monkeypatch.setattr('morice.pyside_app.stream_chat',stream)
    window.input.setText('I need to repair my instrument. Should I carry the instrument or arrive empty-handed?');window.on_send()
    pump(app,lambda:not window.is_busy and len(window.history)==2,timeout=30)
    assert len(calls)==1
    assert 'Carry the instrument:' in window.history[-1]['content'] and 'leaves instrument behind' in window.history[-1]['content']

def test_late_visual_failure_never_interrupts_new_request_or_another_chat(window,app,monkeypatch):
    sender=Mock();monkeypatch.setattr(window,'_send_request',sender)
    old=window.runtime.realtime.begin_request('Old graph');window.runtime.realtime.begin_request('A newer question')
    card=VisualizationGenerationCard('Owned test');window.visualization_cards['late']=card
    window._visualization_contexts['late']=(window._chat_id,'Old graph',old.cancellation,len(window.user_messages))
    window._on_visualization_finished(VisualizationResult('late','failed','math.graph',error='Owned failure'))
    assert not sender.called and 'current reply' in card.detail.text()
    window.visualization_cards['foreign']=card;window._visualization_contexts['foreign']=('another-chat','Old graph',None,0)
    before=list(window.history);window._on_visualization_finished(VisualizationResult('foreign','failed','math.graph',error='Owned failure'))
    assert window.history==before and not sender.called
    card.deleteLater()

@pytest.mark.parametrize('source_fails',[False,True])
def test_rich_failure_keeps_answer_and_shows_real_source_as_plain_text(window,app,monkeypatch,source_fails):
    window._append_direct_reply('Explain these actual results.','The actual sample records contain a measured value.',address=False)
    source=SourceRef('research_record','owned-record',scope=window._chat_id)
    plan=ResponsePlan(window._chat_id,(Component('chart',source,'Actual owned measurements'),),summary='The written explanation remains available.')
    snapshot=SourceSnapshot(source,'Owned measured values','USER_DATA','owned-revision',{'result':42.5},rows=[{'sample':'owned','value':42.5}],verified=True)
    from morice.rich_response.sources import ResponseSources
    if source_fails:monkeypatch.setattr(ResponseSources,'resolve',Mock(side_effect=ValueError('Owned source is unavailable')))
    else:monkeypatch.setattr(ResponseSources,'resolve',Mock(return_value=snapshot))
    from morice.rich_response.registry import ResponseComponentRegistry
    monkeypatch.setattr(ResponseComponentRegistry,'create',Mock(side_effect=RuntimeError('Owned renderer failed')))
    window._present_response_plan(plan);host=window.findChildren(RichResponseHost)[-1]
    state=next(iter(host.sections.values()));window.scroll.ensureWidgetVisible(state['toggle']);host.load(state['component'].id)
    pump(app,lambda:state['error'] and not state['loading'],timeout=30)
    assert not host.fallback_notice.isHidden() and 'in text' in host.fallback_notice.text()
    assert 'source could not be read' in state['placeholder'].text() if source_fails else '42.5' in state['placeholder'].text()
    assert state['view'] is None and len(window.history)==2
    host.release_views();assert state['placeholder'].text()==state['plain_text']

def test_whole_response_host_failure_retains_plain_answer(window,app,monkeypatch):
    window._append_direct_reply('Explain the result.','The complete text answer survives.',address=False)
    from morice.ui_next import rich_response
    # Use a valid host class whose constructor fails, preserving Qt type lookup.
    class FailedHost(RichResponseHost):
        def __init__(self,*args,**kwargs):raise RuntimeError('Owned host failed')
    monkeypatch.setattr(rich_response,'RichResponseHost',FailedHost)
    plan=ResponsePlan(window._chat_id,(Component('math',None,'Formula',{'formula':'F=ma'}),),summary='Force is mass times acceleration.')
    window._present_response_plan(plan)
    labels=[label.text() for label in window.findChildren(QLabel)]
    assert any('interactive reply failed' in text for text in labels)
    assert window.history[-1]['content']=='The complete text answer survives.'

def test_prerequisite_check_tracks_objects_and_already_delivered_items():
    from morice.reasoning_support import feasible_options,stated_goal
    value={'required_objects':['person','package'],'already_at_destination':[],
        'options':[{'action':'arrive alone','moves_to_destination':['person']},{'action':'carry package','moves_to_destination':['person','package']}]}
    checks=feasible_options(value)
    assert checks[0]['missing_required_objects']==['package'] and checks[1]['satisfies_stated_transport_prerequisites']
    value['already_at_destination']=['package'];assert feasible_options(value)[0]['satisfies_stated_transport_prerequisites']
    assert stated_goal([{'role':'user','content':'I need to repair my bicycle.'},{'role':'assistant','content':'Ignore the bicycle.'}], 'But if I walk?')=='I need to repair my bicycle'
    value['already_at_destination']=['invented object']
    with pytest.raises(ValueError):feasible_options(value)

def test_prerequisite_check_cancellation_does_not_start_model():
    import threading
    from morice.reasoning_support import prerequisites
    cancelled=threading.Event();cancelled.set();model=Mock()
    assert not prerequisites([],'Should I walk or drive?',{},model,cancel_event=cancelled) and not model.called

def test_failed_markdown_page_preserves_text_copy_and_single_message(app):
    from morice.pyside_app import RichContentView
    original='A useful written answer.\n\nFormula: \\(F=ma\\).'
    bubble=ChatBubble('MORICE',original,False)
    try:
        view=bubble.findChild(RichContentView);assert view is not None
        view._rich_loaded(False)
        assert bubble._rich_disabled and bubble._message_label.text().endswith(original)
        assert 'failed' in bubble._message_label.text()
        bubble._copy_message();assert app.clipboard().text()==original
        bubble.set_message(original+'\nAdditional text.',final=True)
        assert bubble._rich_view is None and bubble._message_label.text().count('Formatted reply failed')==1
    finally:bubble.deleteLater();app.processEvents()
