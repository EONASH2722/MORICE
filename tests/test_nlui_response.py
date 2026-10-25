"""Actual model units and typed current-chat display controls, without UI code from text."""
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from morice.nlui.contracts import ActiveContext
from morice.nlui.runtime import NaturalLanguageController
from morice.rich_response import Component,SourceRef
from test_rich_response_sources import sources


@pytest.mark.parametrize('text,action,extra',[
    ('Show this as a table','show_table',{}),('Filter this table to completed','filter',{'text':'completed'}),
    ('Sort the table by run descending','sort',{'text':'run','descending':True}),('Use a bar chart','style',{'text':'bar'}),
    ('Explode this assembly','explode',{'value':1}),('Hide part part:0','hide_part',{'text':'part:0'}),
    ('Turn off wireframe','wireframe',{'enabled':False}),('Set force to 2 kN','parameter',{'value':2,'unit':'kN'})])
def test_display_intents_resolve_to_typed_arguments(sources,text,action,extra):
    _,research=sources;controller=NaturalLanguageController(SimpleNamespace(kernel=research.kernel))
    context=ActiveContext('chat','owned-window',selected=({'kind':'response','id':'actual'},))
    resolution=controller.resolve(text,context)
    assert resolution.operations[0].capability_id=='nlui.response.control'
    args=resolution.operations[0].arguments
    assert args['action']==action and all(args[key]==value for key,value in extra.items())


def test_display_calculator_converts_actual_units_and_never_changes_saved_model(sources):
    _,research=sources;project=research.create('Owned control calculation')
    result=research.run_recorded(project,'research.calculate',{'expression':'force*distance',
        'inputs':{'force':{'value':3,'unit':'N'},'distance':{'value':2,'unit':'m'}},'output_unit':'J'})
    component=Component('calculator',SourceRef('research_record',project+':'+result['record_id'],scope='chat'))
    class Port:
        window_id='owned-window'
        def execute(self,capability,args,context):
            if capability=='response.inspect':return {'plan_id':'actual','component':asdict(component)}
            assert capability=='response.apply';self.updated=args['updated'];return self.updated
        def verify(self,*args):return True
    port=Port();controller=NaturalLanguageController(SimpleNamespace(kernel=research.kernel,research=research));controller.attach_window(port)
    context=ActiveContext('chat',port.window_id,selected=({'kind':'response','id':'actual'},))
    executed=controller.execute(controller.resolve('Set force to 2 kN',context),context)
    assert executed.status=='completed',executed.message
    assert port.updated['config']['values']=={'force':2000}
    record=next(r for r in research.store.snapshot(project)['records'] if r['id']==result['record_id'])
    assert record['payload']['inputs']['inputs']['force']['value']==3


def test_saved_cad_request_reads_actual_record_and_gets_reachable_mesh_and_file_views(sources):
    from morice.rich_response.planner import ResponsePlanner
    _,research=sources;project=research.create('Actual saved CAD')
    recorded=research.run_recorded(project,'research.cad',{key:{'value':15,'unit':'mm'} for key in ('width','height','depth')})
    assert recorded['execution'].success
    controller=NaturalLanguageController(SimpleNamespace(kernel=research.kernel,research=research))
    context=ActiveContext('chat','w',research_project_id=project)
    result=controller.execute(controller.resolve('Show my latest CAD model',context),context)
    assert result.status=='completed',result.message
    plan=ResponsePlanner().from_nlui(result,context)
    assert {c.kind for c in plan.components}=={'mesh','files','validation'}
    assert all(c.source.id==project+':'+recorded['record_id'] for c in plan.components)
    research.store.invalidate(project,recorded['record_id'],'Owned source change')
    result=controller.execute(controller.resolve('Show my latest CAD model',context),context)
    assert result.status=='failed' and 'stale' in result.message


def test_geographic_followups_do_not_borrow_another_conversations_markers(sources):
    from unittest.mock import Mock
    from dataclasses import replace
    from morice.spatial.service import SpatialService
    _,research=sources;spatial=SpatialService(research.kernel)
    controller=NaturalLanguageController(SimpleNamespace(kernel=research.kernel,spatial=spatial))
    port=Mock(window_id='w');controller.attach_window(port)
    context=ActiveContext('chat-a','w')
    first=controller.execute(controller.resolve('Show Chennai and Tokyo',context),context)
    assert first.status=='completed',first.message
    context=replace(context,selected=tuple(first.executions[0]['output']['source_refs']))
    assert controller.execute(controller.resolve('In miles',context),context).status=='completed'
    other=ActiveContext('chat-b','w')
    denied=controller.execute(controller.resolve('How far apart',other),other)
    assert denied.status=='failed' and 'in this chat first' in denied.message
