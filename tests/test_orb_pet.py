"""Orb's real local presentation transport, voice routing and pause continuity."""
import math,uuid,json,time
from unittest.mock import Mock,patch
import pytest
from PySide6.QtCore import QRectF,QPoint
from PySide6.QtGui import QImage,QPainter
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QWidget
from test_fast_memory_ui import app,window,pump
from morice.ui_next.globe_state import OrbRotation
from morice.ui_next.themes import ThemeEngine
from morice.ui_next.motion import EffectPolicy,EffectClock
from morice.ui_next.core_state import CoreSnapshot,CoreState
from morice.ui_next.core_view import draw_core
from morice.ui_next.energy_field import EnergyField
from morice.orb_pet import OrbPresentation
from morice.desktop_pet import _PetHostServer,PetProcessController,PetManager

def test_random_rotation_visits_all_directions_without_jumps_and_pauses():
    rotation=OrbRotation(7);directions=set()
    for _ in range(8000):
        before=(rotation.yaw,rotation.pitch);rotation.advance(.02);directions.add(rotation.direction)
        assert all(abs(math.remainder(a-b,math.tau))<.005 for a,b in zip((rotation.yaw,rotation.pitch),before))
    assert directions=={'left','right','up','down'}
    for _ in range(200):rotation.advance(.02,interactive=True)
    assert max(map(abs,rotation.velocity))<.001
    before=(rotation.yaw,rotation.pitch);rotation.advance(1,reduced=True);assert before==(rotation.yaw,rotation.pitch)

@pytest.mark.parametrize('preset',['ICE','MORICE','GLASS'])
def test_focus_pause_preserves_background_pixels_and_resumes_at_same_phase(app,tmp_path,preset):
    theme=ThemeEngine(tmp_path/preset);theme.update(preset=preset,quality='HIGH',persist=False)
    policy=EffectPolicy(theme);clock=EffectClock(policy);owner=QWidget();owner.resize(640,480)
    field=EnergyField(owner,theme,policy,clock);field._phase=5.7;field._raster_phase=5.7
    def render():
        image=QImage(640,480,QImage.Format_ARGB32_Premultiplied);image.fill(0);painter=QPainter(image)
        try:field.render(painter,QPoint())
        finally:painter.end()
        return image
    try:
        before=render();policy.set_load('UNFOCUSED',source='focus');assert policy.budget.effective=='HIGH'
        assert render()==before and not field.tick(.05)
        assert field._phase==5.7
        policy.set_load('NORMAL',source='focus');assert render()==before
    finally:field.close();clock.close();owner.deleteLater();app.processEvents()

def test_paused_orbital_core_retains_pose_without_changing_reduced_motion(app,tmp_path):
    theme=ThemeEngine(tmp_path)
    def render(moving,preserve=False):
        image=QImage(300,300,QImage.Format_ARGB32_Premultiplied);image.fill(0);p=QPainter(image)
        draw_core(p,QRectF(0,0,300,300),CoreSnapshot(),theme.tokens,3.7,moving=moving,preserve_pose=preserve);p.end();return image
    assert render(True)==render(False,True) and render(False)!=render(False,True)

def test_orb_visual_protocol_survives_fragmented_messages_and_rejects_invalid_levels(app):
    name='morice-owned-orb-'+uuid.uuid4().hex;server=_PetHostServer(server_name=name);assert server.listen()
    model=OrbPresentation();server.presentation_received.connect(model.present);client=QLocalSocket()
    try:
        client.connectToServer(name);assert client.waitForConnected(1000);app.processEvents()
        client.write(b'{"presentation":{"state":"SPEA');client.flush();app.processEvents()
        assert model.snapshot.state==CoreState.IDLE
        client.write(b'KING","level":0.75}}\n');client.flush()
        pump(app,lambda:model.snapshot.audio_level==.75)
        client.write(b'{"presentation":{"state":"SPEAKING","level":NaN}}\n');client.flush();app.processEvents()
        assert model.snapshot.audio_level==.75
        model.received=time.monotonic()-3;model.sample();assert model.snapshot.state==CoreState.IDLE
    finally:client.abort();server.close();app.processEvents()

def test_production_sender_uses_nonblocking_socket_and_real_snapshot(app):
    name='morice-owned-orb-'+uuid.uuid4().hex;server=_PetHostServer(server_name=name);assert server.listen()
    model=OrbPresentation();server.presentation_received.connect(model.present)
    sender=PetProcessController(settings={'pet_enabled':'true','active_pet':'orb'},server_name=name)
    sender.presentation_source=lambda:CoreSnapshot(state=CoreState.SPEAKING,audio_level=.62)
    try:
        sender._configure_presentation();pump(app,lambda:model.snapshot.audio_level==.62)
        sender.configure({'pet_enabled':'false'});assert not sender._visual_timer.isActive()
    finally:sender.shutdown();server.close();app.processEvents()

def test_orb_voice_opt_in_reuses_existing_listener_and_stops_only_owned_process(app,tmp_path,monkeypatch):
    manager=PetManager(settings={'pet_enabled':'true','active_pet':'orb','orb_voice_wake':'false'})
    process=Mock(pid=12345);process.poll.return_value=None
    spawn=Mock(return_value=process);monkeypatch.setattr('morice.desktop_pet.subprocess.Popen',spawn)
    monkeypatch.setattr('morice.desktop_pet.default_pet_host_command',lambda:['python','owned-launcher','--morice-pet'])
    manager._sync_orb_wake();assert not spawn.called
    manager.settings['orb_voice_wake']='true';manager._sync_orb_wake();manager._sync_orb_wake()
    assert spawn.call_count==1 and spawn.call_args.args[0][-1]=='--morice-wake-listener'
    assert spawn.call_args.kwargs['env']['MORICE_ENABLE_ALWAYS_ON_WAKE']=='1'
    import psutil
    with patch('psutil.Process',side_effect=psutil.NoSuchProcess(12345)):
        manager.settings['orb_voice_wake']='false';manager._sync_orb_wake()
    assert process.terminate.call_count==1 and manager._wake_process is None

def test_morice_orb_wake_keeps_main_window_hidden_and_starts_one_capture(window,app,monkeypatch):
    listening=Mock();monkeypatch.setattr(window,'_begin_voice_listening',listening)
    window.settings.update(pet_enabled='true',active_pet='orb',orb_voice_wake='true')
    window.hide();before=window.active_route
    window._wake_from_external('magic words: morice');app.processEvents()
    pump(app,lambda:bool(listening.call_count))
    assert window.chat_mode=='voice' and window.active_route==before and listening.call_count==1
    assert not window.isVisible() and not window.wake_controller.overlay.isVisible()

def test_voice_can_select_every_workspace_without_changing_voice_surface(window,app,monkeypatch):
    from morice.ui_next.navigation import ROUTES
    monkeypatch.setattr(window,'_begin_voice_listening',Mock())
    window._set_chat_mode('voice');app.processEvents();assert window.active_route=='voice'
    for route in ROUTES:
        result=window.nlui_port._execute('ui.navigate',{'route':route.key},window._chat_id)
        assert window.chat_mode=='voice' and window.active_route=='voice',route.key
        assert route.key in window.routes and result['route']==route.key
        if route.key!='voice':assert window.nlui_port.context().route==route.key

def test_orb_launch_never_shows_or_minimizes_the_main_window(app):
    from morice.pyside_app import _show_window_for_launch
    view=QWidget();before=app.quitOnLastWindowClosed()
    try:
        assert _show_window_for_launch(view,{'MORICE_ORB_VOICE_SESSION':'1'})
        assert not view.isVisible() and not view.isMinimized()
    finally:view.deleteLater();app.setQuitOnLastWindowClosed(before);app.processEvents()

def test_orb_voice_toggle_respects_existing_microphone_denial(window,app,monkeypatch):
    from morice.unified_intelligence import PermissionState
    window.runtime.kernel.permissions.controller.set_state('microphone_access',PermissionState.DENIED)
    configure=Mock();monkeypatch.setattr(window.pet_manager,'configure',configure)
    window.orb_pet_settings.wake.setChecked(True)
    assert not window.orb_pet_settings.wake.isChecked() and window.settings.get('orb_voice_wake')=='false'
    assert not configure.called and 'blocked' in window.orb_pet_settings.status.text()
