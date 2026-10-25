"""Restored/model-proposed response data cannot create executable UI behavior."""
import pytest

from morice.rich_response import Component,ResponsePlan,SourceRef


def test_versioned_plan_roundtrip_preserves_only_data_and_real_references():
    source=SourceRef('experiment','actual-id','actual-revision','chat')
    plan=ResponsePlan('chat',(Component('chart',source,'Actual run outputs',{'x':'frequency','ys':['power'],'table':True}),))
    assert ResponsePlan.from_dict(plan.to_dict())==plan


@pytest.mark.parametrize('kind,config',[
    ('metrics',{'values':[9999]}),('metrics',{'fields':[{'value':9999}]}),
    ('chart',{'x':'x','ys':['y'],'script':'alert(1)'}),
    ('chart',{'x':'x','ys':['y'],'style':'html'}),
    ('calculator',{'minimum':float('nan')}),('calculator',{'step':0}),
    ('calculator',{'minimum':10,'maximum':1}),('table',{'page_size':10**12}),
    ('table',{'sort':{'field':'x','command':'run'}}),('preview',{'artifact':'real','path':'C:/secret'}),
    ('diagram',{'nodes':[{'id':'n','label':'Plain','on_click':'code'}]}),
    ('diagram',{'nodes':[{'id':'n','label':'Plain'}],'edges':[{'from':'n','to':'missing'}]}),
    ('status',{'fields':['state'],'approval_token':'forged'}),('assembly',{'explode':100}),
    ('progress',{'refresh_seconds':.001}),('media',{'indices':[True]}),
    ('assembly',{'camera':{'yaw':0,'pitch':0,'zoom':-1}}),('assembly',{'camera':{'yaw':0,'pitch':0,'zoom':1,'script':'run'}}),
])
def test_untrusted_configs_are_rejected_before_any_widget_exists(kind,config):
    with pytest.raises(ValueError):Component(kind,SourceRef('experiment','id'),config=config)


def test_missing_sources_unknown_versions_and_duplicate_identity_fail_closed():
    with pytest.raises(ValueError):Component('validation')
    with pytest.raises(ValueError):SourceRef.from_dict({'kind':'experiment','id':'e','path':'C:/secret'})
    component=Component('table',SourceRef('experiment','e'))
    with pytest.raises(ValueError):ResponsePlan('chat',(component,),schema=2)
    with pytest.raises(ValueError):ResponsePlan('chat',(component,component))
    with pytest.raises(ValueError):ResponsePlan.from_dict({'schema':1,'conversation_id':'c','components':[],'execute':'code'})
