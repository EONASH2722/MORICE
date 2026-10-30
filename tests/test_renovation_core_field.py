"""State authority/concurrency and bounded rendering, not synthetic work proofs."""
from dataclasses import replace
import os
import math
from types import SimpleNamespace
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from morice.kernel import CapabilityKernel, CapabilityDescriptor, ExecutionResult, TaskStatus, KernelEvent, EventType, ResourceClaim, ResourceDescriptor, TaskGraph, TaskNode, ErrorCode
from morice.agent_runtime import AgentCoordinator, AgentRole, RuntimeLimits
from morice.ui_next.bridge import UiBridge
from morice.ui_next.core_state import CorePresentation, CoreState
from morice.ui_next.energy_field import EnergyField, FIELD_BUDGETS
from morice.ui_next.themes import ThemeEngine, AppearanceProfile
from morice.ui_next.motion import EffectPolicy, EffectClock
from morice.premium_experience import ExperienceProfile, ExperienceProfileStore
from morice.workspace_state import WorkspaceState


@pytest.fixture(scope='session')
def app(): return QApplication.instance() or QApplication([])


def pump(app, predicate):
    deadline = time.monotonic()+5
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate(): return
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def presentation(app):
    kernel=CapabilityKernel()
    voice_status=SimpleNamespace(state=SimpleNamespace(value='idle'),active=False,queued=0)
    speech_status=SimpleNamespace(listening=False)
    runtime=SimpleNamespace(kernel=kernel,voice=SimpleNamespace(status=lambda:voice_status,audio_level=lambda:0),speech_input=SimpleNamespace(status=lambda:speech_status,audio_level=lambda:0))
    owner=SimpleNamespace(runtime=runtime,is_busy=False,chat_mode='normal',awake=True,wake_controller=SimpleNamespace(active=False))
    bridge=UiBridge(runtime);model=CorePresentation(owner,bridge)
    yield model,owner,bridge,voice_status,speech_status
    model.close();bridge.close();kernel.shutdown();app.processEvents()


def test_real_kernel_work_has_live_requirement_and_releases_lease(presentation,app):
    model,owner,bridge,_,_=presentation;kernel=owner.runtime.kernel;gate=threading.Event();result=[]
    entered=threading.Event();kernel.resources.register(ResourceDescriptor('GPU'))
    def work(inputs,ctx):
        entered.set()
        assert gate.wait(4)
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{'answer':5})
    kernel.registry.register(CapabilityDescriptor('research.core_fixture','Owned state fixture',supported_resources=(ResourceClaim('GPU',exclusive=True),)),work)
    thread=threading.Thread(target=lambda:result.append(kernel.dispatch('research.core_fixture',{})))
    thread.start()
    try:
        pump(app,lambda:model.snapshot.state==CoreState.RESEARCH_RUNNING and entered.is_set())
        assert model.snapshot.nodes==('research.core_fixture',) and kernel.resources.snapshot()
    finally:gate.set();thread.join(5)
    pump(app,lambda:model.snapshot.state==CoreState.SUCCESS)
    assert result[0].success and not kernel.resources.snapshot() and not model.tasks


def test_phase2_coordinator_owns_real_agent_nodes(presentation,app):
    model,owner,_,_,_=presentation;kernel=owner.runtime.kernel;gate=threading.Event();result=[]
    coordinator=AgentCoordinator(kernel,limits=RuntimeLimits(max_workers=2))
    coordinator.roles.register(AgentRole('core_fixture','Core fixture','Owned concurrency fixture',('test.core',),result_schema={}))
    def work(inputs,ctx):
        assert gate.wait(4)
        return ExecutionResult(TaskStatus.SUCCEEDED,True,inputs)
    kernel.registry.register(CapabilityDescriptor('test.core','Core fixture'),work)
    graph=TaskGraph(tuple(TaskNode('test.core',{'value':i},constraints={'role':'core_fixture'}) for i in range(2)))
    thread=threading.Thread(target=lambda:result.append(coordinator.run(graph)));thread.start()
    try:
        pump(app,lambda:model.snapshot.state==CoreState.MULTI_AGENT)
        assert len(model.agents)==2 and model.snapshot.nodes==('core_fixture',)
    finally:gate.set();thread.join(5);coordinator.shutdown()
    pump(app,lambda:not model.agents and not model.tasks)
    assert result[0].success and result[0].metrics['active_peak']==2


def test_failed_workflow_cannot_become_success_from_its_last_successful_branch(presentation,app):
    model,owner,bridge,_,_=presentation;k=owner.runtime.kernel
    a=AgentCoordinator(k,limits=RuntimeLimits(max_workers=2));a.roles.register(AgentRole('truth_fixture','Truth fixture','Controlled mixed result',('test.truth',),result_schema={}))
    def work(args,ctx):
        if args['value']==0:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Owned failure fixture')
        ctx.cancellation_token.wait(.08);return ExecutionResult(TaskStatus.SUCCEEDED,True,args)
    k.registry.register(CapabilityDescriptor('test.truth','Owned mixed result'),work)
    graph=TaskGraph(tuple(TaskNode('test.truth',{'value':i},constraints={'role':'truth_fixture'}) for i in (0,1)))
    try:
        result=a.run(graph);app.processEvents()
        assert not result.success and model.snapshot.state==CoreState.ERROR
        assert not model.workflows and not model.tasks and not model.agents
    finally:a.shutdown()


def test_distinct_security_findings_and_workflows_are_not_coalesced_together(presentation,app):
    model,owner,bridge,_,_=presentation;k=owner.runtime.kernel
    for identifier,severity in (('high-owned','high'),('low-owned','low')):
        k.events.publish(KernelEvent(EventType.SECURITY_FINDING,source='security',payload={'finding_id':identifier,'severity':severity}))
    app.processEvents();assert model.snapshot.state==CoreState.SECURITY_ALERT
    k.events.publish(KernelEvent(EventType.WORKFLOW_CHANGED,source='agents',payload={'workflow_id':'owned-cancel','state':'completed','status':'cancelled'}));app.processEvents()
    assert model.snapshot.state==CoreState.SECURITY_ALERT


def test_real_voice_status_is_required_for_audio_and_arming(presentation):
    model,owner,_,voice,speech=presentation
    owner.runtime.speech_input.audio_level=lambda:75
    model.sample();assert model.snapshot.audio_level==0 and model.snapshot.state==CoreState.IDLE
    speech.listening=True;owner.chat_mode='voice';owner.awake=False
    model.sample();assert model.snapshot.state==CoreState.ARMED and model.snapshot.audio_level==0
    owner.awake=True;model.sample();assert model.snapshot.state==CoreState.LISTENING and model.snapshot.audio_level==.75
    speech.listening=False;voice.active=True;voice.state.value='loading'
    model.sample();assert model.snapshot.state==CoreState.WORKING and model.snapshot.audio_level==0
    voice.state.value='playing';owner.runtime.voice.audio_level=lambda:float('nan')
    model.sample();assert model.snapshot.state==CoreState.SPEAKING and model.snapshot.audio_level==0
    owner.runtime.voice.audio_level=lambda:28
    model.sample();assert model.snapshot.audio_level==.28


def test_waiting_security_priority_and_bounded_public_state(presentation,app):
    model,owner,bridge,_,_=presentation;k=owner.runtime.kernel
    for i in range(160):k.events.publish(KernelEvent(EventType.TASK_STARTED,task_id=str(i),payload={'capability_requirement':'research.fixture','private_chain_of_thought':'never retained'}))
    app.processEvents();assert len(model.tasks)==128 and model.dropped_nodes==32
    k.events.publish(KernelEvent(EventType.TASK_WAITING,task_id='159'));app.processEvents()
    assert model.snapshot.state==CoreState.WAITING_FOR_USER
    k.events.publish(KernelEvent(EventType.SECURITY_FINDING,source='security',payload={'severity':'low'}));app.processEvents()
    assert model.snapshot.state!=CoreState.SECURITY_ALERT
    k.events.publish(KernelEvent(EventType.SECURITY_FINDING,source='security',payload={'severity':'high'}));app.processEvents()
    k.events.publish(KernelEvent(EventType.TASK_COMPLETED,task_id='159'));app.processEvents()
    assert model.snapshot.state==CoreState.SECURITY_ALERT
    assert 'never retained' not in repr(model.tasks) and bridge.diagnostics()['pending_events']==0


def test_media_queue_is_waiting_not_fake_generation(presentation,app):
    model,owner,_,_,_=presentation;k=owner.runtime.kernel
    k.events.publish(KernelEvent(EventType.MEDIA_QUEUED,task_id='owned'));app.processEvents()
    assert model.snapshot.state==CoreState.WAITING_FOR_USER
    k.events.publish(KernelEvent(EventType.MEDIA_STARTED,task_id='owned'));app.processEvents()
    assert model.snapshot.state==CoreState.MEDIA_GENERATING
    k.events.publish(KernelEvent(EventType.MEDIA_CANCELLED,task_id='owned'));app.processEvents()
    assert not model.media and model.snapshot.state==CoreState.IDLE


def test_load_sources_do_not_clear_each_others_pressure(tmp_path,app):
    theme=ThemeEngine(tmp_path);theme.update(quality='ULTRA',persist=False);policy=EffectPolicy(theme)
    policy.set_load('VRAM_PRESSURE',source='metrics');policy.set_load('MEDIA_GENERATING',source='media')
    policy.set_load('NORMAL',source='media')
    assert policy.budget.effective=='LOW' and policy.budget.selected=='ULTRA'
    policy.set_load('NORMAL',source='metrics');assert policy.budget.effective=='ULTRA'
    policy.set_load('UNFOCUSED',source='focus')
    assert policy.budget.effective=='ULTRA' and not policy.budget.decorative_motion


def test_core_motion_changes_orbits_but_reduced_motion_keeps_identical_pixels(tmp_path,app):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage,QPainter
    from morice.ui_next.core_view import draw_core
    from morice.ui_next.core_state import CoreSnapshot
    theme=ThemeEngine(tmp_path)
    def render(phase,moving=True,strength=.65):
        image=QImage(360,360,QImage.Format_ARGB32_Premultiplied);image.fill(0)
        painter=QPainter(image);painter.setRenderHint(QPainter.Antialiasing)
        draw_core(painter,QRectF(0,0,360,360),CoreSnapshot(),theme.tokens,phase,moving=moving,motion_strength=strength)
        painter.end();return image
    assert render(0)!=render(4)
    assert render(0,moving=False)==render(4,moving=False)
    assert render(0,strength=0)==render(4,strength=0)
    assert render(0)==render(24)


def test_every_scene_has_distinct_geometry_and_a_smooth_closed_cycle():
    from morice.ui_next.theme_scenes import SCENES,scene_points,particle_position
    signatures=[];epsilon=1e-5
    for preset in SCENES:
        start=scene_points(preset,2,8,0)
        end=scene_points(preset,2,8,math.tau)
        assert all(math.dist(a,b)<1e-12 for a,b in zip(start,end)),preset
        before=scene_points(preset,2,8,math.tau-epsilon)
        after=scene_points(preset,2,8,epsilon)
        for point,left,right in zip(start,before,after):
            # Both position and velocity must agree at the restart boundary.
            assert math.dist(tuple((p-l)/epsilon for p,l in zip(point,left)),tuple((r-p)/epsilon for p,r in zip(point,right)))<.001,preset
        middle=scene_points(preset,2,8,math.pi/2)
        assert any(math.dist(a,b)>.01 for a,b in zip(start,middle)),preset
        signatures.append(tuple((round(x,5),round(y,5)) for x,y in start))
    assert len(set(signatures))==len(SCENES)
    seed=(.4,.6,.005,.7)
    assert math.dist(particle_position(seed,0),particle_position(seed,math.tau))<1e-12


def test_low_quality_keeps_cheap_ambient_motion_and_explicit_reduced_motion_stops(tmp_path,app):
    theme=ThemeEngine(tmp_path);theme.update(quality='LOW',persist=False)
    policy=EffectPolicy(theme);clock=EffectClock(policy);owner=QWidget();owner.show();owner.activateWindow();app.processEvents()
    field=EnergyField(owner,theme,policy,clock)
    try:
        first=field._phase
        for _ in range(12):field.tick(.05)
        assert field._phase>first and field._moving()
        theme.update(reduced_motion=True,persist=False);phase=field._phase
        for _ in range(12):assert field.tick(.05) is False
        assert field._phase==phase
        theme.update(reduced_motion=False,persist=False);owner.hide()
        assert field.tick(.05) is False
    finally:field.close();clock.close();owner.close();owner.deleteLater();app.processEvents()


def test_field_raster_is_bounded_cached_and_reduced_motion_static(tmp_path,app):
    theme=ThemeEngine(tmp_path);policy=EffectPolicy(theme);clock=EffectClock(policy)
    owner=QWidget();owner.resize(1600,900);owner.show();owner.activateWindow();app.processEvents()
    field=EnergyField(owner,theme,policy,clock)
    try:
        for quality in FIELD_BUDGETS:
            theme.update(quality=quality,persist=False);first=field.material();count=field.render_count
            assert (first.width(),first.height())==FIELD_BUDGETS[quality][:2]
            assert field.material().cacheKey()==first.cacheKey() and field.render_count==count
        theme.update(reduced_motion=True,persist=False);phase=field._phase;field.material();count=field.render_count
        field.pointer_changed({'point':QPointF(450,260),'pressed':True})
        for _ in range(60):assert field.tick(.033) is False
        assert field._phase==phase and field._pulse==0 and field.render_count==count
        theme.update(high_contrast=True,persist=False);assert field.material() is None
    finally:field.close();clock.close();owner.close();owner.deleteLater();app.processEvents()


def test_native_contours_render_without_a_scaled_raster_and_close_the_cycle(tmp_path,app):
    from PySide6.QtGui import QImage,QPainter
    theme=ThemeEngine(tmp_path);policy=EffectPolicy(theme);clock=EffectClock(policy)
    owner=QWidget();owner.resize(1280,720);field=EnergyField(owner,theme,policy,clock)
    def render(phase):
        field._phase=phase
        image=QImage(1280,720,QImage.Format_ARGB32_Premultiplied);image.fill(0)
        painter=QPainter(image);field.draw_contours(painter);painter.end();return image
    try:
        from morice.ui_next.theme_scenes import SCENES
        motions=[]
        def matrix(pose):return tuple(float(value) for value in (pose.m11(),pose.m12(),pose.m21(),pose.m22(),pose.dx(),pose.dy()))
        for preset in SCENES:
            theme.update(preset=preset,persist=False);pose=field._pose(.6,2)
            motions.append(tuple(round(value,6) for value in (pose.m11(),pose.m12(),pose.m21(),pose.m22(),pose.dx(),pose.dy())))
            start=matrix(field._pose(0.,2));end=matrix(field._pose(math.tau,2));epsilon=1e-6
            before=matrix(field._pose(math.tau-epsilon,2));after=matrix(field._pose(epsilon,2))
            assert max(abs(a-b) for a,b in zip(start,end))<1e-7,preset
            assert max(abs((a-b)/epsilon-(c-a)/epsilon) for a,b,c in zip(start,before,after))<.02,preset
        assert len(set(motions))==len(SCENES),'Themes share the same motion profile.'
        for preset in ('MORICE','GLASS','ARCTIC','NEON'):
            theme.update(preset=preset,persist=False)
            first=render(0)
            cache=field._path_cache
            assert any(bytes(first.constBits())),preset
            assert first==render(24) and first!=render(3),preset
            assert field._path_cache is cache,'Animation rebuilt the native geometry.'
        # Foreground vector phase advances every frame even though the diffuse
        # light raster intentionally updates less often under LOW quality.
        theme.update(quality='LOW',persist=False);owner.show();owner.activateWindow();app.processEvents()
        before=field._phase;field.tick(.02)
        assert field._phase!=before
    finally:field.close();clock.close();owner.close();owner.deleteLater();app.processEvents()


@pytest.mark.parametrize('field,value',[('field_intensity',float('nan')),('field_motion',2),('core_brightness',-1),('orbital_complexity',7),('field_palette','url(secret)')])
def test_new_appearance_fields_remain_strict_data(field,value):
    with pytest.raises(ValueError):replace(AppearanceProfile(),**{field:value})


def test_existing_profile_store_roundtrips_complete_new_appearance(tmp_path):
    profile=AppearanceProfile(preset='ARCTIC',field_palette='VIOLET',orbital_complexity=5,font_scale=1.8,reduced_motion=True)
    store=ExperienceProfileStore(tmp_path/'source')
    store.save(ExperienceProfile.from_value({'name':'Field workspace','appearance':profile.to_dict(),'workspace_preset':'research'}))
    exported=store.export(tmp_path/'profiles.json');loaded=ExperienceProfileStore(tmp_path/'target')
    assert loaded.import_file(exported)==1
    assert loaded.get('Field workspace').appearance==profile.to_dict()
    assert loaded.get('Field workspace').workspace_preset=='research'
    with pytest.raises(ValueError):ExperienceProfile.from_value({'appearance':{'font_family':'bad"; image:url(secret)'}})


def test_route_session_fields_roundtrip_without_losing_legacy_data():
    original=WorkspaceState(notes='Retained note',workspace_preset='science',presentation_route='spatial',presentation_navigation_expanded=True)
    restored=WorkspaceState.from_dict(original.to_dict())
    assert restored.notes=='Retained note' and restored.workspace_preset=='science'
    assert restored.presentation_route=='spatial' and restored.presentation_navigation_expanded
    assert WorkspaceState.from_dict({'presentation_route':'../../secret','presentation_navigation_expanded':'false'}).presentation_route=='home'
    assert not WorkspaceState.from_dict({'presentation_navigation_expanded':'false'}).presentation_navigation_expanded
