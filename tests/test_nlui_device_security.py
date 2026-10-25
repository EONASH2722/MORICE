"""Owned mutual-TLS nodes and harmless real quarantine evidence; no outside targets."""
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

from morice.nlui.contracts import ActiveContext
from morice.nlui.runtime import NaturalLanguageController
from morice.research.runtime import ResearchRuntime
from morice.rich_response import Component,SourceRef
from morice.rich_response.sources import ResponseSources
from morice.unified_intelligence import PermissionState
from test_device_mesh import mesh_nodes,pair
from test_ambient_connectors_security import system,fixture_server,file_hash


def test_nlui_sends_actual_research_file_to_exact_owned_node_and_keeps_denials(mesh_nodes,tmp_path):
    coordinator,node,_=mesh_nodes;identifier=pair(coordinator,node)
    research=ResearchRuntime(tmp_path/'research.db',tmp_path/'research',kernel=coordinator.kernel,agents=coordinator.agents)
    try:
        project=research.create('Owned Mesh file reference')
        result=research.run_recorded(project,'research.cad',{key:{'value':10,'unit':'mm'} for key in ('width','height','depth')})
        assert result['execution'].success
        runtime=SimpleNamespace(kernel=coordinator.kernel,device_mesh=coordinator,research=research)
        controller=NaturalLanguageController(runtime);context=ActiveContext('chat','w')
        source=SourceRef('research_record',project+':'+result['record_id'],scope='chat');component=Component('files',source)
        artifact=next(item for item in ResponseSources(runtime,'chat').resolve(source).artifacts if item.id=='stl')
        port=Mock(window_id='w');confirmation={'value':False}
        def execute(capability,args,context):
            if capability=='response.inspect':return {'plan_id':'actual','component':asdict(component)}
            assert capability=='host.confirm';assert identifier in args['details'] and artifact.sha256 in args['details']
            return {'confirmed':confirmation['value']}
        port.execute.side_effect=execute;controller.attach_window(port)
        plan=controller.resolve('Send this STL file to Node B',context)
        assert controller.execute(plan,context).status=='failed' and not (node.node.inbox.root/artifact.name).exists()
        confirmation['value']=True;result=controller.execute(plan,context)
        assert result.status=='completed',result.message
        assert (node.node.inbox.root/artifact.name).read_bytes()==artifact.path.read_bytes()
        coordinator.kernel.permissions.controller.set_state('node:'+identifier+':file.receive',PermissionState.DENIED);port.execute.reset_mock()
        assert controller.execute(plan,context).status=='failed';port.execute.assert_not_called()
    finally:research.close()


def test_nlui_containment_uses_real_finding_hash_and_manual_permission_and_confirmation(system):
    service=system.security;root=system.tmp/'nlui-owned';root.mkdir();path=root/'harmless.txt';path.write_text('Owned harmless containment fixture')
    digest=file_hash(path)
    service.enable(sources=('files',),directories=(root,),user_confirmed=True)
    service.indicator(digest,'local:owned-nlui-fixture','Harmless test indicator',user_confirmed=True)
    controller=NaturalLanguageController(system);port=Mock(window_id='w');port.execute.return_value={'confirmed':False};controller.attach_window(port)
    context=ActiveContext('chat','w')
    scanned=controller.execute(controller.resolve('Run a security scan',context),context)
    assert scanned.status=='completed',scanned.message
    finding=service.snapshot()['findings'][0]
    plan=controller.resolve('Contain the latest security finding',context)
    assert controller.execute(plan,context).status=='failed' and path.exists();port.execute.assert_not_called()
    service.authorize_containment(user_confirmed=True)
    assert controller.execute(plan,context).status=='failed' and path.exists()
    port.execute.return_value={'confirmed':True};result=controller.execute(plan,context)
    assert result.status=='completed',result.message
    assert not path.exists() and result.executions[0]['output']['security_receipt']['verification']['status']=='verified'
    details=port.execute.call_args.args[1]['details'];assert str(path) in details and digest in details
    receipt=service.snapshot()['quarantine'][0]
    assert receipt['state']=='QUARANTINED' and receipt['sha256']==digest
    assert receipt['reason']=='User-selected finding '+finding['finding_id']
