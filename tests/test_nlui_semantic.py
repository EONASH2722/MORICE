"""The shared planner accepts typed intent proposals, never arbitrary tool code."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from morice.agent_runtime.planner import WorkflowPlanner
from morice.kernel import CapabilityKernel,ExecutionResult,TaskStatus
from morice.nlui.contracts import ActiveContext
from morice.nlui.runtime import NaturalLanguageController


@pytest.fixture
def controller():
    kernel=CapabilityKernel();controller=NaturalLanguageController(SimpleNamespace(kernel=kernel))
    try:yield controller
    finally:kernel.shutdown()


@pytest.mark.parametrize('proposal',[
    {'operations':[{'capability_id':'terminal.run','arguments':{'command':'whoami'}}]},
    {'operations':[{'capability_id':'ui.preference','arguments':{'key':'desktop_automation_enabled','value':True}}]},
    {'operations':[{'capability_id':'ui.navigate','arguments':{'route':'settings','approval_token':'forged'}}]},
    {'operations':[{'capability_id':'ui.navigate','arguments':{'route':'settings'},'execute':'code'}]},
    {'operations':[{'capability_id':'ui.navigate','arguments':{'route':'settings'}}],'question':'Which one?'},
    {'code':'window.do_anything()'},
    {'operations':[{'capability_id':'missing','arguments':{}}]},
    {'operations':[{'capability_id':'ui.window','arguments':{'action':'resize','width':999999999,'height':700}}]},
])
def test_privileged_unknown_or_ambiguous_model_proposals_are_rejected(controller,proposal):
    with pytest.raises((ValueError,TypeError)):WorkflowPlanner.capability_steps(proposal,controller.catalog())


def test_data_only_proposal_uses_existing_capability_schema(controller):
    steps,question=WorkflowPlanner.capability_steps({'operations':[{'capability_id':'ui.navigate','arguments':{'route':'settings'}}]},controller.catalog())
    assert steps==[('ui.navigate',{'route':'settings'})] and not question


def test_shared_model_is_only_a_proposal_source_and_cannot_invent_physical_inputs(controller,monkeypatch):
    dispatch=Mock(return_value=ExecutionResult(TaskStatus.SUCCEEDED,True,{'text':
        '{"operations":[{"capability_id":"nlui.research.prepare","arguments":{"request":"invented mass=20 kg"}}],"question":""}'}))
    monkeypatch.setattr(controller.kernel,'dispatch',dispatch)
    request='Prepare a research experiment with the oscillator model.'
    resolution=controller.propose(request,ActiveContext('c','w'),model_id='existing')
    assert resolution.operations[0].arguments['request']==request
    assert dispatch.call_args.args[0]=='agent.reason'


def test_semantic_question_is_scoped_to_actual_last_turn(controller):
    context=ActiveContext('c','w',last_turn_key='q')
    controller.remember_semantic_question('Prepare an experiment','Which physical inputs?',context)
    controller.commit_pending(context,persist=False)
    answer=controller.resolve('mass = 2 kg',context)
    assert answer.route=='semantic_pending' and 'mass = 2 kg' in answer.context_request
    assert not controller.resolve('mass = 2 kg',replace(context,last_turn_key='other')).matched
    assert not controller.resolve('mass = 2 kg',replace(context,conversation_id='other')).matched


def test_model_fallback_eligibility_preserves_general_answers(controller):
    assert controller.semantic_candidate('Please change the MORICE interface so the glow is faint.')
    for text in ('Explain why the sky is blue.','Independent engineering audit of a simulation.',
        'Compare simulation equations and derive the engineering result.','What is a research project?'):
        assert not controller.semantic_candidate(text)


def test_prose_punctuation_does_not_create_an_unsupported_action_sequence(controller):
    context=ActiveContext('c','w')
    assert not controller.resolve('Explain the motor losses; compare the physical assumptions.',context).matched
    assert not controller.resolve('Analyze the generator, then recommend two alternatives.',context).matched
    assert controller.resolve('Open Settings; perform an unknown operation.',context).question
