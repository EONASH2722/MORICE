"""Natural-language resolution is data-only and dispatches through the Kernel."""
from unittest.mock import Mock

import pytest

from morice.kernel import CapabilityKernel
from morice.nlui.contracts import ActiveContext
from morice.nlui.runtime import NaturalLanguageController


@pytest.fixture
def controller():
    kernel=CapabilityKernel();runtime=Mock(kernel=kernel)
    adapter=NaturalLanguageController(runtime)
    try:yield adapter
    finally:kernel.shutdown()


@pytest.mark.parametrize('text,capability,args',[
    ('Open Settings.','ui.navigate',{'route':'settings'}),
    ('Please take me to the lab.','ui.navigate',{'route':'research'}),
    ("Let's go to my experiments.",'ui.navigate',{'route':'research'}),
    ('Show Research Lab.','ui.navigate',{'route':'research'}),
    ('Go back to Chat.','ui.navigate',{'route':'chats'}),
    ('Open Appearance Lab.','ui.settings',{'category':'Appearance'}),
    ('Show memory settings.','ui.settings',{'category':'Memory'}),
    ('Open automation settings.','ui.navigate',{'route':'automations'}),
    ('Open desktop automation settings.','ui.settings',{'category':'Permissions & control'}),
    ('Maximize MORICE.','ui.window',{'action':'maximize'}),
    ('Resize MORICE to 1100 by 700.','ui.window',{'action':'resize','width':1100,'height':700}),
])
def test_direct_navigation_paraphrases(controller,text,capability,args):
    resolved=controller.resolve(text,ActiveContext('chat','window'))
    assert resolved.route=='direct'
    assert len(resolved.operations)==1
    assert resolved.operations[0].capability_id==capability
    assert resolved.operations[0].arguments==args


@pytest.mark.parametrize('text',[
    'Make the UI purple.','Switch to purple.','Use purple as the accent.',
    'Change the primary color to purple.','Can you change the interface to purple?',
])
def test_color_paraphrases_have_one_typed_target(controller,text):
    resolved=controller.resolve(text,ActiveContext('chat','window'))
    assert resolved.operations[0].arguments['changes']=={'primary_accent':'#a855f7'}


def test_compound_ui_plan_has_dependency_order_and_no_model(controller):
    plan=controller.resolve('Open Settings, then change accent to violet; go back to Chat.',ActiveContext('chat','window'))
    assert plan.route=='task_graph'
    assert [o.capability_id for o in plan.operations]==['ui.navigate','ui.appearance','ui.navigate']


def test_compound_project_request_keeps_original_goal_case_and_does_not_swallow_actions(controller):
    plan=controller.resolve('Open my latest project, then Build a Python addition calculator in this project; Open Settings.',ActiveContext('chat','window'))
    assert [o.capability_id for o in plan.operations]==['nlui.project.open','nlui.project.propose','ui.navigate']
    assert plan.operations[1].arguments['request']=='Build a Python addition calculator in this project'


def test_ordinary_answer_and_external_apps_stay_out_of_ui_navigation(controller):
    for text in ('What is the capital of France?','Explain research methods.','Open Notepad.'):
        assert not controller.resolve(text,ActiveContext('chat','window')).matched
    assert controller.catalog() and all(row['verification_contract'] for row in controller.catalog())
