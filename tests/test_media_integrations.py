"""Actual shared Builder, Research, Ambient and paired TLS Mesh contracts."""
from dataclasses import replace
from pathlib import Path
import time

import pytest
from test_media_lab import media,request,run,wait_until,FixtureProvider,hardware
from test_project_build_runtime import builder,calculator
from test_device_mesh import mesh_nodes,pair
from test_ambient_cross_phase import attach

from morice.media_lab.runtime import MediaLab
from morice.media_lab.contracts import ImageModelDescriptor
from morice.research.runtime import ResearchRuntime
from morice.kernel import ExecutionContext,ResourceClaim
from morice.unified_intelligence import PermissionState
from morice.ambient import Trigger


def attach_fixture(media,kernel,agents,tmp_path):
    lab=MediaLab(kernel,agents,tmp_path,providers={'test':FixtureProvider()},hardware_probe=hardware)
    model=media.models.get('fixture');lab.models.register(model);lab.inspect_model('fixture')
    return lab


def test_project_builder_generates_and_attaches_real_decoded_fixture_asset(media,builder,tmp_path):
    build,approve=builder;lab=attach_fixture(media,build.kernel,build.agents,tmp_path/'builder-media')
    try:
        session=calculator(build,tmp_path/'project')
        identifier,future=build.request_media_asset(session,request(),lab)
        assert future.result(timeout=12).success
        build.kernel.permissions.controller.set_state('file_write',PermissionState.GRANTED)
        result=build.attach_media_asset(session,identifier,'assets/hero.png',lab)
        assert result.success and (Path(session.project_root)/'assets/hero.png').is_file()
        manifest=session.constraints['media_assets'][0]
        assert manifest['generation_id']==identifier and manifest['sha256']==lab.artifact(identifier)['sha256'] and manifest['license']=='UNKNOWN'
    finally:lab.close()


def test_research_art_is_generated_visual_and_never_measured(media,tmp_path):
    research=ResearchRuntime(tmp_path/'knowledge.db',tmp_path/'research',kernel=media.kernel,agents=media.agents)
    try:
        project=research.create('Illustrate an observatory concept, without claiming scientific evidence.')
        identifier,future=research.request_media_visual(project,request(),media);assert future.result(timeout=12).success
        record=research.attach_generated_visual(project,identifier,media)
        snapshot=research.store.snapshot(project)
        item=next(r for r in snapshot['records'] if r['id']==record)
        assert item['provenance']=='GENERATED_VISUAL' and item['payload']['scientific_evidence'] is False
        with pytest.raises(ValueError,match='scientific evidence'):research.store.add(project,'measurement','Fake evidence',item['payload'],'MEASURED')
    finally:research.close()


def test_media_completion_triggers_single_existing_ambient_notification(media,tmp_path):
    ambient=attach(media.kernel,media.agents,tmp_path/'ambient')
    try:
        ambient.create(Trigger('Media finishes','media.completed',enabled=True,cooldown_seconds=0),user_confirmed=True)
        identifier,result=run(media);assert result.success
        until=time.monotonic()+5
        while time.monotonic()<until:
            ambient.tick()
            if ambient.notifications.history():break
            time.sleep(.01)
        assert len(ambient.notifications.history())==1
        for _ in range(5):ambient.tick()
        assert len(ambient.notifications.history())==1
    finally:ambient.close()


def test_full_protocol_synthetic_media_capability_and_pin(media,mesh_nodes,tmp_path):
    client,node,_=mesh_nodes;observed={}
    dispatch_errors=[];original_dispatch=node.transport.dispatcher
    def observe_dispatch(*args):
        try:return original_dispatch(*args)
        except Exception as exc:
            dispatch_errors.append(type(exc).__name__+': '+str(exc));raise
    node.transport.dispatcher=observe_dispatch
    def generate(args,ctx):
        # Protocol fixture only; no claim of a physical remote GPU/model.
        observed.update(generation_id=args['generation_id'],status='SUCCEEDED',validation_scope='SYNTHETIC_FULL_PROTOCOL_ONLY')
        return dict(observed)
    node.node.register('media.image.generate',generate,lambda args,ctx:dict(observed),resources=(ResourceClaim('CPU'),),read_only=False)
    target=pair(client,node,grants=('device.status','file.receive','media.image.generate'))
    lab=attach_fixture(media,client.kernel,client.agents,tmp_path/'mesh-media')
    try:
        identifier,future=lab.submit(replace(request(),node_id=target))
        result=future.result(timeout=15)
        assert result.success, str(result.to_dict())+str(dispatch_errors)
        assert result.output['validation_scope']=='SYNTHETIC_FULL_PROTOCOL_ONLY'
        assert lab.result(identifier)['node_id']==target and lab.result(identifier)['status']=='SUCCEEDED'
        assert not lab.providers['test'].processes.snapshot()
        with pytest.raises(ValueError,match='hash-transferred'):lab.artifact(identifier)
    finally:lab.close()


def test_shared_agent_worker_can_execute_media_without_second_runtime(media):
    from morice.kernel import TaskGraph,TaskNode
    graph=TaskGraph((TaskNode('media.image.generate',{'request':request().to_dict()},timeout=20),))
    result=media.agents.run(graph)
    assert result.success
    assert graph.tasks[0].result.artifacts and graph.tasks[0].result.verification.status.value=='verified'
    assert media.agents.workers.peak==1 and not media.kernel.resources.snapshot()
