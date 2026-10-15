"""Owned Qt behavior and authority/lifetime parity, separate from real PCM demo."""
from __future__ import annotations

from dataclasses import replace
import json
import math
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch, Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QPointF, Qt, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QMessageBox

from morice import settings
from morice.runtime_services import RuntimeServices
from morice.kernel import KernelEvent, EventType
from morice.speech_runtime import TranscriptResult
from morice.unified_intelligence import PermissionState
from morice.ui_next.shell import RenovatedWindow
from morice.ui_next.wake import WakePreferences, WakeState
from morice.ui_next.navigation import ROUTES
from morice.ui_next.themes import AppearanceProfile, tokens, contrast, PRESETS
from morice.ui_next.file_access import require_selected_file


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


def pump(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate(): return
        QTest.qWait(10)
    assert predicate(), 'Qt delivery did not settle.'


@pytest.fixture(scope='module')
def window(tmp_path_factory, app):
    directory = tmp_path_factory.mktemp('renovation-owned-qt'); source = Path(__file__).resolve().parents[1]
    with patch.dict(os.environ, MORICE_LOCAL_DATA_DIR=str(directory / 'data'), MORICE_DISABLE_SESSION='1',
        MORICE_DISABLE_RECOVERY='1', MORICE_PRELOAD='0', MORICE_NODE_NETWORK='0', MORICE_REDUCE_MOTION='1', MORICE_START_AWAKE='1'), \
        patch('morice.settings._settings_dir', return_value=str(directory / 'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS, 'tts_enabled': 'false', 'stt_enabled': 'false', 'pet_enabled': 'false'})
        runtime = RuntimeServices(directory / 'runtime', project_root=source)
        with patch('morice.runtime_services._RUNTIME_SERVICES', runtime):
            view = RenovatedWindow(runtime, runtime.start()); view.show(); app.processEvents()
            try: yield view
            finally:
                view.wake_controller.cancel(); view.close(); app.processEvents(); runtime.shutdown()
                view.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
                assert runtime.shutdown_report['clean'] and runtime.shutdown_report['leases_remaining'] == 0


def test_every_destination_reachable_one_runtime_hidden_pollers_stop(window, app):
    for route in ROUTES:
        window.navigate(route.key)
        try: pump(app, lambda: window.ui_bridge.diagnostics()['pending_deliveries'] == 0)
        except AssertionError:
            import faulthandler
            faulthandler.dump_traceback()
            print({'route': route.key, 'bridge': window.ui_bridge.diagnostics(), 'status': window.status_line.text(),
                'media_refreshing': getattr(window.routes.get('media'), '_refreshing', None), 'media_again': getattr(window.routes.get('media'), '_refresh_again', None)})
            raise
        assert window.active_route == route.key, window.status_line.text()
        assert window.routes[route.key].window() is window
        assert window.navigation.isVisible() != window.action_deck.isVisible(),'Two workspace navigation bars are visible.'
        assert window.action_deck.isVisible() == (route.key=='home')
    assert window.routes['research'].runtime.kernel is window.runtime.kernel
    assert window.routes['media'].lab.kernel is window.runtime.kernel
    assert window.routes['devices'].mesh.kernel is window.runtime.kernel
    assert window.routes['automations'] is window.routes['connectors'] is window.routes['security']
    window.navigate('home'); QTest.qWait(50)
    window.toggle_sidebar();app.processEvents()
    assert window.navigation.isVisible() and not window.action_deck.isVisible()
    window.toggle_sidebar();app.processEvents()
    assert not window.navigation.isVisible() and window.action_deck.isVisible()
    assert not window.routes['research'].timer.isActive()
    assert not window.routes['research'].play_timer.isActive()
    assert not window.routes['devices']._timer.isActive()
    assert not window.routes['media'].timer.isActive()
    assert not window.routes['automations'].timer.isActive()
    assert not window.runtime.device_mesh.enabled
    assert not window.runtime.speech_input.status().listening


def test_bridge_delivers_worker_results_on_gui_thread_and_bounds_event_bursts(window, app):
    delivered = []; gui = threading.get_ident()
    window.ui_bridge.submit('renovation-thread-check', threading.get_ident,
        lambda envelope: delivered.append((threading.get_ident(), envelope)))
    pump(app, lambda: bool(delivered))
    assert delivered[0][0] == gui and delivered[0][1]['value'] != gui
    for index in range(1500):
        window.runtime.kernel.events.publish(KernelEvent(EventType.TASK_PROGRESS, source='controlled-test', task_id=str(index % 400),
            payload={'completed': index, 'private_chain_of_thought': 'NEVER DISPLAY THIS'}))
    state = window.ui_bridge.diagnostics()
    assert state['pending_events'] <= 256 and state['coalesced_events'] > 0
    events = []; window.ui_bridge.event_arrived.connect(events.append)
    pump(app, lambda: window.ui_bridge.diagnostics()['pending_events'] == 0)
    window.ui_bridge.event_arrived.disconnect(events.append)
    assert events and all('private_chain_of_thought' not in row['payload'] for row in events)


def test_settings_search_and_local_provider_binding(window, app):
    window.navigate('settings'); view = window.routes['settings']; view.search.setText('microphone'); app.processEvents()
    assert view.list.currentItem().text() == 'Voice'
    assert window.stt_input_device_select.isVisible()
    assert not window.tts_voice_id_input.isVisible()
    view.search.clear(); view.list.setCurrentRow(3)
    window.tts_provider_select.setCurrentIndex(window.tts_provider_select.findData('local'))
    window._save_voice_settings()
    assert window.settings['tts_provider'] == 'local'
    assert window.runtime.voice.status().provider == 'local'
    assert not window.runtime.speech_input.status().listening


def test_settings_categories_fit_large_text_and_keep_names_at_compact_width(window, app):
    old_size, old_scale = window.size(), window.theme_engine.profile.font_scale
    window.navigate('settings'); view = window.routes['settings']; view.search.clear()
    try:
        window.resize(1366, 840); window.theme_engine.update(font_scale=1.8, persist=False)
        QTest.qWait(100); app.processEvents()
        needed = max(view.list.fontMetrics().horizontalAdvance(view.list.item(i).text())
                     for i in range(view.list.count())) + 24
        assert view.list.width() >= needed
        window.resize(720, 500); QTest.qWait(100); app.processEvents()
        assert view.list.width() <= max(150, int(view.width() * .35))
        assert view.list.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
        assert view.list.textElideMode() == Qt.ElideRight
        assert all(view.list.item(i).toolTip() == view.list.item(i).text() for i in range(view.list.count()))
    finally:
        window.resize(old_size); window.theme_engine.update(font_scale=old_scale, persist=False)
        QTest.qWait(100)


def test_tool_browser_stays_on_existing_verified_bridge(window, app):
    bridge = window.runtime.pc_browser.bridge
    window.assistant_hub.show_tab('Browser'); app.processEvents()
    assert window.active_route == 'tools'
    assert window.assistant_hub.browser_view.isVisible() if window.assistant_hub.browser_view else True
    assert window.runtime.pc_browser.bridge is bridge


def test_renovated_chat_shows_stream_before_completion_and_clears_busy_state(window, app):
    from morice.ui_next.core_state import CoreState
    previous_mode = window.chat_mode
    window._set_chat_mode('normal'); window.navigate('chats')
    request = window.runtime.realtime.begin_request('Owned streaming contract fixture', request_id='renovated-stream-contract')
    try:
        window._set_busy(True); window._show_thinking('Generating.'); window.core_presentation.sample()
        assert window.core_presentation.snapshot.state == CoreState.THINKING
        window._on_assistant_stream_delta(request.request_id, 'First visible ')
        window._on_assistant_stream_delta(request.request_id, 'sentence.')
        app.processEvents()
        assert window._stream_bubble is not None and window._stream_bubble.isVisible()
        assert window.presentation_root.isAncestorOf(window._stream_bubble)
        assert 'First visible sentence.' in window._stream_bubble.message
        assert 'first_visible_token' in request.trace.snapshot()['events']
        window.runtime.realtime.complete_generation(request.epoch)
        window._on_assistant_stream_finished(request.request_id, window._address('First visible sentence.'))
        assert not window.is_busy
    finally:
        window._set_busy(False); window._set_chat_mode(previous_mode)


def test_simple_calculation_from_spatial_bypasses_ui_and_agent_worker_queues(window, app):
    window.navigate('spatial'); window.input.setText('2+3')
    with patch.object(window.ui_bridge, 'submit', wraps=window.ui_bridge.submit) as ui_submit, \
        patch.object(window.runtime.agents, 'submit', side_effect=AssertionError('Direct arithmetic entered agents')):
        window.on_send(); pump(app, lambda: any('5' in row['content'] for row in window.history if row['role'] == 'assistant'))
        assert not ui_submit.called
    assert any('5' in row['content'] for row in window.history if row['role'] == 'assistant')


def test_history_restore_after_reparent_and_explicit_delete_does_not_resurrect(window, app):
    history = window._get_chat_history(); identifier = 'renovation-history-check'
    history.save(identifier, [{'role': 'user', 'content': 'Stored controlled conversation'}, {'role': 'assistant', 'content': 'Existing archive integrity.'}])
    window.navigate('history'); view = window.routes['history']; view.query.setText('Stored controlled'); app.processEvents()
    view.chats.setCurrentRow(0); view.open_selected()
    assert window.active_route == 'chats' and window._chat_id == identifier
    assert window.history[-1]['content'] == 'Existing archive integrity.'
    window.navigate('history'); view.query.clear(); view.refresh()
    for index in range(view.chats.count()):
        if view.chats.item(index).data(Qt.UserRole)['id'] == identifier: view.chats.setCurrentRow(index); break
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes): view.delete()
    assert window._history_deleted_id == identifier
    assert not any(row['id'] == identifier for row in history.search(''))


def test_media_native_event_delivery_form_geometry_and_unavailable_workflow(window, app):
    window.navigate('media'); view = window.routes['media']; app.processEvents()
    pump(app, lambda: not view._refreshing)
    assert view.prompt.width() > 200 and view.viewer.width() >= 220
    # This normal Qt event exercises QWidget::event, preventing a dictionary
    # Kernel handler from accidentally overriding Qt's native event dispatch.
    view.resize(view.width() - 1, view.height()); app.processEvents()
    view.intent.setCurrentIndex(view.intent.findData('IMAGE_TO_VIDEO'))
    assert not view.run.isEnabled() and 'unavailable' in view.run.toolTip()
    window.navigate('home')


def test_spatial_projection_inverse_and_chord_endpoints_visible_after_pair_fit(window, app):
    window.navigate('spatial'); canvas = window.routes['spatial'].canvas
    context = window.runtime.spatial.set_pair('Chennai', 'New York')
    window.runtime.spatial.handle_text('straight line distance')
    canvas.set_context(window.runtime.spatial.snapshot()); app.processEvents()
    for coordinate in (context['origin']['coordinate'], context['destination']['coordinate']):
        point, z = canvas.project(coordinate['latitude'], coordinate['longitude']); assert z > 0
        roundtrip = canvas.unproject(point)
        assert roundtrip['latitude'] == pytest.approx(coordinate['latitude'], abs=1e-7)
        assert roundtrip['longitude'] == pytest.approx(coordinate['longitude'], abs=1e-7)
    assert canvas.context['result']['mode'] == 'CHORD' and len(canvas.context['result']['path']) == 2
    assert canvas.unproject(QPointF(-1000, -1000)) is None


@pytest.mark.parametrize('changes', [{'enabled': 'true'}, {'size': 500}, {'processing_timeout': math.inf}, {'fullscreen': 'always_focus'}])
def test_wake_preference_bounds(changes):
    with pytest.raises((ValueError, TypeError)): WakePreferences(**changes)


@pytest.fixture
def wake(window):
    controller = window.wake_controller; controller.cancel(); old = controller.preferences; old_mode = window.chat_mode
    with patch.object(window, '_set_chat_mode', side_effect=lambda mode: setattr(window, 'chat_mode', mode)), \
        patch.object(window, '_begin_voice_listening', return_value=None):
        controller.preferences = WakePreferences(command_timeout=1, idle_timeout=1)
        yield controller
        controller.cancel(); controller.preferences = old; window.chat_mode = old_mode; window.showNormal()


@pytest.mark.parametrize('policy,shown,size', [('audio_only', False, 80), ('disabled_overlay', False, 80), ('small_overlay', True, 64), ('normal_overlay', True, 80)])
def test_fullscreen_overlay_policy_preserves_minimized_main(wake, window, app, policy, shown, size):
    wake.preferences = replace(wake.preferences, fullscreen=policy); window.showMinimized(); app.processEvents()
    assert wake.activate(fullscreen=True)
    assert window.isMinimized() and wake.overlay.isVisible() == shown
    if shown: assert wake.overlay.orb.width() == size
    assert wake.overlay.testAttribute(Qt.WA_ShowWithoutActivating)


def test_wake_timeout_cancel_and_disabled_activation(wake, app):
    wake.preferences = replace(wake.preferences, enabled=False)
    assert not wake.activate() and not wake.timeout.isActive()
    wake.preferences = replace(wake.preferences, enabled=True); wake.activate()
    token = wake.interaction_token; QTest.qWait(1100); app.processEvents()
    assert not wake.active and wake.state == WakeState.IDLE and not wake.overlay.isVisible()
    assert token.cancelled and not wake.timeout.isActive()


def test_stale_transcript_tts_event_and_duplicate_wake_do_not_corrupt_current_interaction(wake, window):
    window.chat_mode = 'normal'; wake.activate(); wake.activate()
    assert wake._return_mode == 'normal'
    wake.stt_request_id = 'current'
    before = window.input.text()
    assert wake.transcript(TranscriptResult('old', 'show earth', 1))
    assert window.input.text() == before
    wake.tts_request_id = 'current-reply'; wake.voice_event('playback_started', {'requestId': 'old-reply'})
    assert wake.state == WakeState.LISTENING
    wake.voice_event('playback_started', {'requestId': 'current-reply'})
    assert wake.state == WakeState.SPEAKING
    wake.cancel(); assert window.chat_mode == 'normal'


def test_review_before_send_and_cancel_phrase(wake, window):
    wake.activate(); wake.stt_request_id = 'current'
    original = window.runtime.speech_input.config
    window.runtime.speech_input.configure(replace(original, auto_send=False))
    try:
        with patch.object(window, 'on_send') as send:
            assert wake.transcript(TranscriptResult('current', 'show earth', 1))
            assert not send.called and wake.overlay.run.isVisible()
            wake.submit_reviewed(); assert send.call_count == 1
        wake.stt_request_id = 'next'; wake.transcript(TranscriptResult('next', 'cancel', 1))
        assert not wake.active
    finally: window.runtime.speech_input.configure(original)


def test_selected_file_actions_respect_existing_denials(window):
    controller = window.runtime.kernel.permissions.controller
    previous = controller.state('file_read'); controller.set_state('file_read', PermissionState.DENIED)
    try:
        with pytest.raises(PermissionError): require_selected_file(window.runtime, 'file_read')
        window.navigate('media'); view = window.routes['media']; view.load_reference(str(Path(__file__)))
        assert 'denied' in view.status.text().casefold() and view.reference_metadata is None
    finally: controller.set_state('file_read', previous)


@pytest.mark.parametrize('preset', PRESETS)
def test_primary_hover_pressed_and_status_contrast(preset):
    value = tokens(AppearanceProfile(preset=preset))
    for background in ('accent_primary', 'primary_hover', 'primary_pressed'):
        assert contrast(value['accent_text'], value[background]) >= 4.5
    for role in ('success', 'warning', 'error', 'info'):
        assert contrast(value[role], value['surface']) >= 4.5


def test_mixed_custom_surfaces_have_distinct_legible_roles():
    value = tokens(AppearanceProfile(preset='CUSTOM', background_tone='#000000', surface_tone='#ffffff'))
    assert contrast(value['text_background'], value['background']) >= 4.5
    assert contrast(value['text_primary'], value['surface']) >= 4.5
    assert contrast(value['text_primary'], value['surface_elevated']) >= 4.5


def test_palette_exposes_every_route_and_theme_preserving_existing_commands(window):
    window._refresh_renovation_commands()
    keys = {row.key for row in window.command_palette.commands}
    assert {f'renovation:route:{route.key}' for route in ROUTES} <= keys
    assert {f'renovation:theme:{preset}' for preset in PRESETS} <= keys
    window._execute_palette_command('renovation:theme:ICE')
    assert window.theme_engine.profile.preset == 'ICE'
    window._execute_palette_command('renovation:route:spatial'); assert window.active_route == 'spatial'
    window.theme_engine.update(preset='MORICE')


def test_retained_renderer_polling_timers_retired_and_microphone_denial_honored(window):
    assert window.renderer_clocks.adapters
    for adapter in window.renderer_clocks.adapters.values():
        widget = adapter.widget()
        if widget is not None: assert not widget._timer.isActive()
    controller = window.runtime.kernel.permissions.controller; previous = controller.state('microphone_access')
    controller.set_state('microphone_access', PermissionState.DENIED)
    try:
        with patch.object(window.runtime.speech_input, 'listen_once') as listen:
            window._begin_voice_listening(); assert not listen.called
    finally: controller.set_state('microphone_access', previous)


def test_unicode_font_family_is_data_but_stylesheet_syntax_still_rejected():
    assert AppearanceProfile(font_family='微软雅黑').font_family == '微软雅黑'
    with pytest.raises(ValueError): AppearanceProfile(font_family='Arial";image:url(secret)')


def test_reduced_motion_stops_material_particles_and_idle_clock(window, app):
    window.navigate('home'); old = window.theme_engine.profile
    try:
        window.activateWindow(); app.processEvents()
        with patch('psutil.sensors_battery', return_value=SimpleNamespace(power_plugged=True)):
            # This is an effects fixture; an actual unplugged host correctly
            # forces LOW and therefore cannot be assumed to produce particles.
            window.effect_policy.set_load('NORMAL', source='power')
            window.theme_engine.update(background_effects=True, particles='NORMAL', quality='HIGH', reduced_motion=False)
            window.effect_clock.request(); QTest.qWait(90)
            assert 0 < len(window.material_backdrop._points) <= 36
            assert window.material_backdrop.material() is not None
            window.theme_engine.update(reduced_motion=True); QTest.qWait(100)
            assert not window.material_backdrop._points and not window.effect_clock.timer.isActive()
    finally: window.theme_engine.apply_profile(old)


def test_existing_media_export_reports_actual_verified_contract(window, app, tmp_path):
    """Controlled stored PNG fixture; actual Kernel permission/export/readback."""
    import hashlib
    import uuid
    from PIL import Image
    window.navigate('media'); view = window.routes['media']; lab = view.lab
    pump(app, lambda: not view._refreshing)
    identifier = uuid.uuid4().hex; directory = lab.directory/'outputs'/identifier; directory.mkdir(parents=True)
    original = directory/'controlled-fixture.png'; Image.new('RGB', (64, 64), (25, 90, 140)).save(original)
    sha = hashlib.sha256(original.read_bytes()).hexdigest()
    lab.history_store.save(identifier, {'generation_id': identifier, 'status': 'SUCCEEDED', 'node_id': 'local',
        'artifacts': [{'path': str(original), 'sha256': sha}], 'label': 'CONTROLLED stored image fixture, not model generation'})
    view.refresh(); pump(app, lambda: not view._refreshing)
    item = next(view.history.item(index) for index in range(view.history.count()) if view.history.item(index).data(Qt.UserRole) == identifier)
    view.history.setCurrentItem(item)
    target = tmp_path/'exported.png'
    controller = window.runtime.kernel.permissions.controller; previous = controller.state('file_write')
    try:
        controller.set_state('file_write', PermissionState.GRANTED)
        with patch('morice.ui_next.media_view.QFileDialog.getSaveFileName', return_value=(str(target), 'PNG')):
            view.export(); pump(app, lambda: 'Verified export completed.' in view.status.text())
        assert hashlib.sha256(target.read_bytes()).hexdigest() == sha
        controller.set_state('file_write', PermissionState.DENIED); denied = tmp_path/'denied.png'
        with patch('morice.ui_next.media_view.QFileDialog.getSaveFileName', return_value=(str(denied), 'PNG')):
            view.export(); pump(app, lambda: window.ui_bridge.diagnostics()['pending_deliveries'] == 0)
        assert not denied.exists() and view.status.text() != 'Verified export completed.'
    finally: controller.set_state('file_write', previous)


def test_compact_composer_expands_only_for_content(window, app):
    window.navigate('chats'); window.input.clear(); app.processEvents()
    compact = window.input.height(); window.input.setText('\n'.join('A controlled line.' for _ in range(30))); app.processEvents()
    assert window.input.height() > compact and window.input.height() == window.input._max_document_height
    window.input.clear(); app.processEvents(); assert window.input.height() == compact


def test_required_composer_survives_maximize_restore_and_hidden_tall_routes(window, app):
    from PySide6.QtCore import QRect, QPoint
    previous=window.theme_engine.profile;size=window.size()
    try:
        for route in ('settings','artifacts','home','chats','projects','voice'):
            window.navigate(route);app.processEvents()
        for font in (1.,1.8):
            window.theme_engine.update(font_scale=font,persist=False)
            for maximize in (False,True,False):
                window.showMaximized() if maximize else window.showNormal()
                window.navigate('home');app.processEvents();QTest.qWait(30)
                for name in ('input','send_btn','composer'):
                    field=getattr(window,name)
                    assert field.isVisible(),f'Required {name} is hidden.'
                    bounds=QRect(field.mapTo(window,QPoint()),field.size())
                    assert window.rect().contains(bounds),(name,bounds,window.rect())
                window.input.setFocus();window.input.clear();QTest.keyClicks(window.input,'A visible message')
                assert window.input.toPlainText()=='A visible message'
    finally:
        window.input.clear();window.showNormal();window.resize(size);window.theme_engine.apply_profile(previous,persist=False);window.navigate('home');app.processEvents()


def test_legacy_theme_commands_change_the_renovated_tokens(window):
    previous = window.theme_engine.profile; legacy = window.current_theme
    try:
        window._set_theme('light', notify=False); assert window.theme_engine.profile.preset == 'ICE'
        window._set_theme('dark', notify=False); assert window.theme_engine.profile.preset == 'MORICE'
    finally: window.current_theme = legacy; window.theme_engine.apply_profile(previous)


def test_custom_font_denial_prevents_picker_and_parser(window):
    controller = window.runtime.kernel.permissions.controller; previous = controller.state('file_read')
    try:
        controller.set_state('file_read', PermissionState.DENIED)
        with patch('morice.pyside_app.QFileDialog.getOpenFileName') as picker, patch('morice.pyside_app.register_ui_font_file') as parse:
            window._choose_custom_font()
        assert not picker.called and not parse.called and 'denied' in window.style_status.text().casefold()
    finally: controller.set_state('file_read', previous)


def test_normal_deterministic_wake_reply_rearms_with_speech_disabled(window, app):
    wake = window.wake_controller
    try:
        with patch.object(window, '_begin_voice_listening', return_value=None) as listen:
            wake.activate('controlled-owned-wake')
            # Existing voice-mode entry schedules capture after 220 ms. Wait for
            # that real handoff instead of relying on incidental paint cost.
            pump(app, lambda: listen.call_count >= 1)
            wake.set_state(WakeState.WORKING, 'Working', 8)
            window.input.setText('2+3'); window.on_send()
            pump(app, lambda: wake.state == WakeState.LISTENING)
            assert listen.call_count >= 2 and not window.runtime.voice.status().active
    finally: wake.cancel(); window.input.clear()


def test_wake_does_not_rearm_while_reply_is_queued_before_playback(window):
    wake = window.wake_controller
    try:
        with patch.object(window, '_begin_voice_listening', return_value=None): wake.activate('controlled-owned-wake')
        wake.tts_request_id = 'controlled-pending-reply'
        with patch.object(window.runtime.voice, 'status', return_value=SimpleNamespace(active=False, queued=1, state=SimpleNamespace(value='idle'))), \
            patch.object(window, '_begin_voice_listening') as listen:
            wake.result('Controlled pending reply')
            assert wake.state == WakeState.WORKING and not listen.called
    finally: wake.cancel()


def test_named_profiles_keep_new_appearance_and_existing_workspace_authority(window, app):
    old=window.theme_engine.profile;old_preset=window.workspace_preset;old_mode=window.chat_mode
    profiles=window.routes['settings'].categories['Profiles']
    try:
        window.theme_engine.update(preset='ARCTIC',field_palette='VIOLET',core_brightness=.8,orbital_complexity=5)
        profiles.select.setCurrentText('Owned cinematic fixture');profiles.save()
        saved=window.experience_profiles.get('Owned cinematic fixture')
        assert saved is not None and saved.appearance['orbital_complexity']==5
        window.theme_engine.update(preset='SOLAR',core_brightness=.2)
        profiles.apply();app.processEvents()
        assert window.theme_engine.profile.preset=='ARCTIC' and window.theme_engine.profile.core_brightness==.8
        window._apply_workspace_preset('research',notify=False);assert window.active_route=='research'
        profiles.select.setCurrentText('Owned cinematic fixture');profiles.delete();assert window.experience_profiles.get('Owned cinematic fixture') is None
    finally:
        window.theme_engine.apply_profile(old);window.workspace_preset=old_preset;window._set_chat_mode(old_mode);window.navigate('home')


def test_profile_import_denial_prevents_picker(window):
    profiles=window.routes['settings'].categories['Profiles'];controller=window.runtime.kernel.permissions.controller;old=controller.state('file_read')
    controller.set_state('file_read',PermissionState.DENIED)
    try:
        with patch('morice.ui_next.profiles_view.QFileDialog.getOpenFileName') as picker:
            profiles.import_profiles();assert not picker.called and 'denied' in profiles.status.text().casefold()
    finally:controller.set_state('file_read',old)


def test_project_lookup_and_context_quick_actions_are_reachable(window,app):
    previous=window.project_lookup_mode
    try:
        window.navigate('projects');app.processEvents();assert window.project_lookup_btn.isVisible()
        QTest.mouseClick(window.project_lookup_btn,Qt.LeftButton);assert window.project_lookup_mode!=previous
        window._refresh_mode_panel();assert window.project_lookup_btn.isVisible()
        window.navigate('home');window.composer_options.setChecked(True);app.processEvents()
        assert window.quick_actions_btn.isVisible() and window.presentation_root.isAncestorOf(window.quick_actions_btn)
        window._select_settings_category('Personalization')
        assert window.active_route=='settings' and window.routes['settings'].list.currentItem().text()=='Personalization'
    finally:
        if window.project_lookup_mode!=previous:window._toggle_project_lookup_mode()
        window.composer_options.setChecked(False);window.navigate('home')


def test_session_save_preserves_native_normal_geometry_and_new_route(window, app, tmp_path):
    from morice.workspace_state import save_workspace_state,load_workspace_state
    old=window._session_enabled;window._session_enabled=True
    try:
        window.showNormal();window.resize(1100,720);window.navigate('spatial');window.navigation.set_expanded(False);app.processEvents()
        normal=window.geometry();window.showMaximized();app.processEvents()
        target=tmp_path/'owned-session.json'
        with patch('morice.pyside_app.save_workspace_state',side_effect=lambda state:save_workspace_state(state,str(target))):window._save_workspace_session()
        stored=load_workspace_state(str(target))
        assert stored.maximized and stored.geometry[2:]==[normal.width(),normal.height()]
        assert stored.presentation_route=='spatial' and not stored.presentation_navigation_expanded
    finally:window._session_enabled=old;window.showNormal();window.navigate('home')


def test_additional_window_uses_same_kernel_and_new_presentation(window, app):
    from shiboken6 import isValid
    window._open_new_window();child=window._child_windows[-1]
    try:
        assert isinstance(child,RenovatedWindow) and child.runtime is window.runtime
        assert child.runtime.kernel is window.runtime.kernel and child.active_route=='home'
        child.theme_engine.update(reduced_motion=True,persist=False);child.close()
        pump(app,lambda:not isValid(child))
        assert child not in window._child_windows and not window.runtime.kernel._closed
    finally:
        if isValid(child):child.close();app.processEvents()
        window.show();window.activateWindow();app.processEvents()


def test_closing_secondary_window_restores_surviving_verified_browser_bridge(window, app):
    from morice.pyside_app import create_application_window
    parent_bridge=window._action_browser_bridge
    child=create_application_window(window.runtime);child.show();app.processEvents()
    try:
        assert window.runtime.pc_browser.bridge is child._action_browser_bridge
    finally:
        child.close();child.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
    assert window.runtime.pc_browser.bridge is parent_bridge


def test_production_factory_opens_new_shell_over_existing_runtime(window,app):
    from morice.pyside_app import create_application_window
    previous_mode=window.runtime.spatial.context.mode
    child=create_application_window(window.runtime)
    try:
        child.show();app.processEvents()
        assert isinstance(child,RenovatedWindow) and child.runtime.kernel is window.runtime.kernel
        child.navigate('spatial');child.routes['spatial'].command('show Chennai and New York')
        pump(app,lambda:not child.routes['spatial']._busy)
        assert child.runtime.spatial.context.mode==previous_mode
        child.routes['spatial'].command('as the crow flies')
        pump(app,lambda:not child.routes['spatial']._busy)
        assert child.runtime.spatial.snapshot()['result']['metres']>13_000_000
        assert child.presentation_root.isVisible() and not child.compatibility_host.isVisible()
    finally:
        child.close()
        assert not child.wake_signal_timer.isActive()
        assert window.wake_signal_timer.isActive()
        child.deleteLater();app.processEvents()
        assert not window.runtime.kernel._closed
