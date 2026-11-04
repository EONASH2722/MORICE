"""Geometry/privacy/lifecycle regressions; hardware acceptance is reported separately."""
from dataclasses import replace
import io
import math
from unittest.mock import patch

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from morice.background_helper import HelperPreferences
from morice.helper_selection import enclosed_selection
from morice.live_vision import VisionResult
from test_renovation_workspaces_wake import app,window


def circle(cx=200,cy=200,rx=100,ry=70,n=100):
    return [(cx+rx*math.cos(i*math.tau/(n-1)),cy+ry*math.sin(i*math.tau/(n-1))) for i in range(n)]


def test_geometry_closes_small_gap_and_clamps_crop():
    points=circle();points=points[:-3]
    geometry=enclosed_selection(points,(0,0,800,600))
    assert geometry.points[0]==geometry.points[-1]
    assert geometry.bounds==(97,127,304,274)
    assert geometry.area>21000


@pytest.mark.parametrize('points',[[(10,10)],[(i,10) for i in range(90)],circle(rx=4,ry=4),circle()[:65]])
def test_click_tiny_line_and_open_arc_rejected(points):
    with pytest.raises(ValueError):enclosed_selection(points,(0,0,800,600))


def test_negative_monitor_physical_coordinates():
    geometry=enclosed_selection(circle(-900,600,200,150),(-1920,0,0,1080))
    assert geometry.bounds==(-1103,447,-696,754)


def test_cross_monitor_selection_is_rejected():
    with pytest.raises(ValueError,match='one monitor'):enclosed_selection(circle(20,100,90,60),(0,0,800,600))


@pytest.mark.parametrize('changes',[{'enabled':'true'},{'popup_seconds':0},{'popup_seconds':121},{'excluded_apps':[]},{'auto_explain':1}])
def test_preference_bounds(changes):
    with pytest.raises(ValueError):HelperPreferences(**changes)


@pytest.fixture
def helper(window,app):
    h=window.background_helper;old=h.preferences
    h.preferences=replace(old,enabled=True,wake_enabled=False,circle_enabled=False,animation=False,auto_hide=False,screen_capture=True)
    h.apply()
    yield h
    h.cancel();h.preferences=old;h.apply();app.processEvents()


def test_close_hides_without_disposing_runtime_or_wake_timer(helper,window,app):
    with patch.object(helper,'should_hide_on_close',return_value=True):window.close()
    assert not window.isVisible() and window.runtime.started and not window._is_closing
    assert window.wake_signal_timer.isActive() and not window.ui_bridge._closed
    helper.open_main();app.processEvents();assert window.isVisible()


def test_wake_uses_same_top_popup_and_preserves_hidden_main(helper,window,app):
    window.hide()
    with patch.object(window,'_begin_voice_listening',return_value=None):
        assert helper.activate_voice();app.processEvents()
        popup=helper.popup
        assert window.wake_controller.overlay is popup and popup.isVisible()
        assert popup.y()==popup._screen.geometry().top()
        assert not window.isVisible()
        assert helper.activate_voice() and window.wake_controller.overlay is popup
        helper.stream('Actual pipeline delta');assert popup.answer.toPlainText()=='Actual pipeline delta'
        helper.cancel();app.processEvents();assert not popup.isVisible() and not window.wake_controller.active


def test_cold_speech_refinement_keeps_shared_helper_open_and_cancellable(helper,window):
    from types import SimpleNamespace
    from morice.ui_next.wake import WakeState
    with patch.object(window,'_begin_voice_listening',return_value=None):
        assert helper.activate_voice()
    controller=window.wake_controller
    with patch.object(window.runtime.speech_input,'status',return_value=SimpleNamespace(state=SimpleNamespace(value='transcribing'))), \
         patch.object(window.runtime.speech_input,'completion_timeout_seconds',return_value=140.) as budget:
        controller._speech_progress()
    budget.assert_called_once_with(include_capture=False)
    assert helper.session and controller.active and controller.overlay is helper.popup
    assert controller.state==WakeState.UNDERSTANDING and controller.timeout.interval()==140_000
    controller.cancel()
    assert not controller.active and not controller.timeout.isActive() and not helper.session


def test_capture_is_once_masked_memory_only_and_keeps_context(helper,window,app):
    helper._geometry=enclosed_selection(circle(),(0,0,800,600))
    grab_image=Image.new('RGB',(207,147),(210,245,230))
    with patch('PIL.ImageGrab.grab',return_value=grab_image) as grab,patch('morice.background_helper.foreground_identity',return_value=('test.exe',False)):
        helper._capture();app.processEvents()
        assert grab.call_count==1 and grab.call_args.kwargs['bbox']==(97,127,304,274)
        frame=helper.selection
        assert frame is not None and frame.width==207 and helper.popup.preview.isVisible()
        decoded=Image.open(io.BytesIO(frame.jpeg));assert max(decoded.getpixel((0,0)))<40
        assert decoded.getpixel((100,70))[1]>200
        assert helper.selection is frame
        helper.cancel();assert helper.selection is None and helper.mask is None


def test_permission_denial_never_captures(helper):
    helper.preferences=replace(helper.preferences,screen_capture=False)
    with patch('PIL.ImageGrab.grab') as grab:helper._capture();assert not grab.called


def test_no_camera_or_new_capture_for_followup(helper,window):
    helper._geometry=enclosed_selection(circle(),(0,0,800,600))
    with patch('PIL.ImageGrab.grab',return_value=Image.new('RGB',(207,147),'white')),patch('morice.background_helper.foreground_identity',return_value=('test.exe',False)):
        helper._capture()
    frame=helper.selection
    observed=[]
    with patch.object(window.ui_bridge,'submit',side_effect=lambda name,operation,callback:observed.append((operation,callback))),patch.object(window.live_camera,'snapshot_jpeg') as camera:
        assert helper.prepare_vision('Explain this.')[0]
        assert helper.prepare_vision('Now solve it for x.')[0]
        assert helper.selection is frame and len(observed)==2 and not camera.called
    with patch.object(helper.runtime.live_vision.provider,'analyze',return_value=VisionResult.failure('test',frame,'test','test')) as analyze:
        observed[0][0]();observed[1][0]()
        assert all(call.args[0] is frame for call in analyze.call_args_list)


def test_dismissal_discards_late_vision_completion(helper,window):
    helper._geometry=enclosed_selection(circle(),(0,0,800,600))
    with patch('PIL.ImageGrab.grab',return_value=Image.new('RGB',(207,147),'white')),patch('morice.background_helper.foreground_identity',return_value=('test.exe',False)):helper._capture()
    with patch.object(window.ui_bridge,'submit') as submit:
        helper.prepare_vision('Explain this.');callback=submit.call_args.args[2]
    helper.cancel()
    with patch.object(window,'_on_live_vision_ready') as done:
        callback({'ok':False,'error':'late failure'});assert not done.called


def test_reduced_motion_disables_slide_and_idle_does_not_capture(helper,app):
    helper.preferences=replace(helper.preferences,reduced_motion=True)
    helper.apply();helper._begin_session();app.processEvents()
    assert not helper.popup.animate
    with patch('PIL.ImageGrab.grab') as grab:helper._tick();assert not grab.called


def test_secondary_window_reuses_resident_helper_and_does_not_close_it(helper,window,app):
    from morice.ui_next.shell import RenovatedWindow
    child=RenovatedWindow(window.runtime)
    try:
        assert child.background_helper is helper and helper.owner is window
        child._motion_enabled=False;child.close();app.processEvents()
        assert not helper._closed and window.runtime.started
    finally:child.deleteLater();app.processEvents()


def test_settings_category_exact_name_and_searchable(window):
    workspace=window.routes['settings']
    assert 'Background Helper' in workspace.categories
    workspace.filter('middle-mouse')
    item=next(workspace.list.item(i) for i in range(workspace.list.count()) if workspace.list.item(i).text()=='Background Helper')
    assert not item.isHidden();workspace.filter('')


@pytest.mark.parametrize('heard,confidence,expected',[
    ('morice',.65,'morice'),('hey maurice',.9,'hey maurice'),('morice',.3,''),
    ('more rice',.99,''),('hey boys',.99,''),('morice please open settings',.99,''),('',.99,'')])
def test_helper_wake_requires_exact_scored_final_phrase(heard,confidence,expected):
    from morice_wake_listener import helper_wake_match
    payload={'text':heard,'result':[{'word':word,'conf':confidence} for word in heard.split()]}
    assert helper_wake_match(payload)==expected


def test_reference_controls_have_pause_play_and_no_close_or_arrows(helper,app):
    from PySide6.QtWidgets import QPushButton
    helper._begin_session();app.processEvents()
    buttons=[button for button in helper.popup.findChildren(QPushButton) if button.isVisible()]
    assert helper.popup.pause in buttons and helper.popup.pause.accessibleName()=='Pause helper'
    assert all(button.text() not in {'×','↗','↑','Close','Stop','Copy'} for button in buttons)
    helper.pause_interaction(True)
    assert helper.popup.isVisible() and helper.popup.pause.text()=='' and not helper.popup.pause.icon().isNull()
    assert helper.popup.state_label.text()=='Paused' and not helper.idle.isActive()


def test_pause_retains_selected_frame_and_play_reuses_popup(helper,window,app):
    helper._geometry=enclosed_selection(circle(),(0,0,800,600))
    with patch('PIL.ImageGrab.grab',return_value=Image.new('RGB',(207,147),'white')),patch('morice.background_helper.foreground_identity',return_value=('test.exe',False)):helper._capture()
    frame=helper.selection
    helper.pause_interaction(True)
    assert helper.selection is frame and helper.popup.isVisible() and not window.wake_controller.active
    with patch.object(window,'_begin_voice_listening',return_value=None):helper.pause_interaction(False);app.processEvents()
    assert window.wake_controller.overlay is helper.popup and helper.selection is frame
    assert not helper._paused and helper.popup.pause.text()=='' and helper.popup.pause.accessibleName()=='Pause helper'


def test_glass_material_and_invalid_material(helper):
    helper.update(popup_material='dark');assert helper.popup.material=='dark'
    helper.update(popup_material='glass');assert helper.popup.material=='glass'
    assert helper.popup.testAttribute(Qt.WA_TranslucentBackground)
    assert helper.popup.orb.canvas.parentWidget() is None
    with pytest.raises(ValueError):HelperPreferences(popup_material='invalid')


def test_glass_paints_alpha_and_real_curved_corners(helper,app):
    helper._begin_session();app.processEvents()
    image=helper.popup.grab().toImage()
    assert 0<image.pixelColor(image.width()//2,15).alpha()<220
    assert image.pixelColor(0,image.height()-1).alpha()==0
    assert helper.popup.pause.text()=='' and not helper.popup.pause.icon().isNull()


def test_worker_missing_decoder_is_structured_error_not_windowed_exception(capsys):
    import builtins
    from morice.speech_worker import main
    actual=builtins.__import__
    def missing(name,*args,**kwargs):
        if name=='faster_whisper':raise ModuleNotFoundError('missing test decoder')
        return actual(name,*args,**kwargs)
    with patch('builtins.__import__',side_effect=missing):assert main('unused-test-model')==1
    assert 'decoder-dependency-unavailable' in capsys.readouterr().out
