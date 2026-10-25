"""Actual ResearchStore selection, Kernel verification, continuation and Qt delivery."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from morice.kernel import CapabilityKernel
from morice.nlui.contracts import ActiveContext
from morice.nlui.runtime import NaturalLanguageController
from morice.research.history import ChatHistory
from morice.research.store import ResearchStore


@pytest.fixture
def research_controller(tmp_path):
    store=ResearchStore(tmp_path/'research.db');kernel=CapabilityKernel()
    history=ChatHistory(tmp_path/'research.db')
    runtime=SimpleNamespace(kernel=kernel,research=SimpleNamespace(store=store),chat_history=history)
    controller=NaturalLanguageController(runtime)
    port=Mock(window_id='w');port.verify.return_value=True
    controller.attach_window(port)
    try:yield controller,store,history,port
    finally:kernel.shutdown()


def test_ambiguous_notebook_asks_then_uses_exact_id_without_replaying_prefix(research_controller):
    controller,store,history,port=research_controller
    first=store.create('Energy study A');second=store.create('Energy study B')
    context=ActiveContext('chat','w')
    resolution=controller.resolve('Open my energy research',context)
    result=controller.execute(resolution,context)
    assert result.status=='awaiting_input' and 'Energy study A' in result.message
    port.execute.assert_not_called()
    context=replace(context,last_turn_key='question')
    controller.commit_pending(context,persist=False)
    assert not controller.resolve('2',replace(context,conversation_id='other')).matched
    assert not controller.resolve('2',replace(context,last_turn_key='unrelated')).matched
    continuation=controller.resolve('the second',context)
    assert continuation.route=='continuation'
    selected=continuation.operations[0].arguments['reference']
    assert selected in {first,second}
    result=controller.execute(continuation,context)
    assert result.status=='completed' and result.executions[0]['verification']['status']=='verified'
    assert port.execute.call_args.args[1]['project_id']==selected
    assert port.execute.call_count==1


def test_restored_pending_requires_resume_then_fresh_choice(research_controller):
    controller,store,history,port=research_controller
    store.create('Energy A');store.create('Energy B')
    history.save('chat',[{'role':'assistant','content':'Question'}])
    context=ActiveContext('chat','w',last_turn_key='q')
    controller.execute(controller.resolve('Open my energy research',context),context)
    controller.commit_pending(context)
    controller._pending.clear();controller.restore_pending('chat')
    assert not controller.resolve('1',context).matched
    resumed=controller.resolve('resume pending request',context)
    assert resumed.question and 'Energy A' in resumed.question
    controller.commit_pending(replace(context,last_turn_key='new-question'))
    assert controller.resolve('1',replace(context,last_turn_key='new-question')).operations
    controller.commit_pending(context)
    assert history.get_ui_state('chat','nlui_pending') is None


def test_no_saved_notebooks_is_an_honest_failure_not_pending(research_controller):
    controller,store,history,port=research_controller
    context=ActiveContext('chat','w')
    result=controller.execute(controller.resolve('Open my latest research project',context),context)
    assert result.status=='failed' and 'No saved' in result.message
    assert not controller._pending


def test_natural_enable_can_only_open_manual_permission_settings(research_controller):
    controller,*_=research_controller
    resolution=controller.resolve('Turn on desktop automation',ActiveContext('chat','w'))
    assert [o.capability_id for o in resolution.operations]==['ui.settings']
    assert 'cannot grant' in resolution.question
