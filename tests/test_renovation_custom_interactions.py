"""Owned Qt rendering, bounded cursor lifecycle and progressive disclosure."""
import os
from dataclasses import replace
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt, QSize
from PySide6.QtGui import QIcon, QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QDialog
from PySide6.QtTest import QTest

from morice.ui_next.icons import MARKS, icon, UiIconBinder
from morice.ui_next.effects import CursorLighting, cursor_style, MotionButton
from morice.ui_next.themes import ThemeEngine, stylesheet
from morice.ui_next.motion import EffectClock, EffectPolicy
from morice.ui_next.navigation import NavigationRail, ADVANCED
from morice.ui_next.appearance_view import AppearanceView


@pytest.fixture(scope='session')
def app(): return QApplication.instance() or QApplication([])


def test_owned_dialogs_use_live_central_theme_and_authored_icons(tmp_path, app):
    theme=ThemeEngine(tmp_path);owner=QWidget();binder=UiIconBinder(owner,theme)
    dialog=QDialog(owner);layout=QVBoxLayout(dialog);button=QPushButton('Save');layout.addWidget(button)
    dialog.setStyleSheet('QDialog { background: magenta; }');dialog.show();app.processEvents()
    try:
        assert dialog.styleSheet()==stylesheet(theme.tokens) and not button.icon().isNull()
        theme.update(preset='ARCTIC',persist=False)
        assert dialog.styleSheet()==stylesheet(theme.tokens)
    finally:dialog.close();binder.close();owner.close();owner.deleteLater();app.processEvents()


def test_retained_model_surface_uses_tokens_without_orphan_decorative_timer(tmp_path,app):
    from morice.pyside_app import LiquidGalaxyFrame
    theme=ThemeEngine(tmp_path);owner=QWidget();binder=UiIconBinder(owner,theme)
    dialog=QDialog(owner);layout=QVBoxLayout(dialog);surface=LiquidGalaxyFrame();surface.setMinimumSize(240,140);layout.addWidget(surface)
    dialog.show();app.processEvents()
    try:
        assert not surface._timer.isActive()
        before=surface.grab().toImage();theme.update(preset='ARCTIC',persist=False);app.processEvents()
        assert before!=surface.grab().toImage()
        dialog.hide();QTest.qWait(100);assert not surface._timer.isActive()
    finally:dialog.close();binder.close();owner.close();owner.deleteLater();app.processEvents()


@pytest.mark.parametrize('scale', [1, 1.25, 1.5, 1.75, 2, 2.5, 3])
def test_authored_vectors_render_visible_alpha_at_each_dpi(app, scale):
    for name in MARKS:
        pixmap = icon(name, color='#85d6ed').pixmap(QSize(24, 24), scale, QIcon.Normal, QIcon.Off)
        assert pixmap.devicePixelRatioF() == scale
        assert abs(pixmap.width()-24*scale) < 1
        image = pixmap.toImage()
        pixels = [image.pixelColor(x, y).alpha() for x in range(image.width()) for y in range(image.height())]
        assert any(value > 100 for value in pixels), name
        assert sum(value > 0 for value in pixels) < len(pixels)*.65, name


def test_authored_icon_native_paint_keeps_modes_without_python_callbacks(app,monkeypatch):
    from types import SimpleNamespace
    import morice.ui_next.icons as icons
    tokens={'text_primary':'#2ea4e8','text_muted':'#a57249','accent_text':'#e84189'}
    glyph=icons.icon('core',SimpleNamespace(tokens=tokens),primary=True)
    def unexpected_callback(*_):raise AssertionError('Native icon painting reentered the vector callback')
    monkeypatch.setattr(icons,'draw_mark',unexpected_callback)
    for mode,state,color in ((QIcon.Normal,QIcon.Off,'#e84189'),(QIcon.Disabled,QIcon.On,'#a57249'),(QIcon.Normal,QIcon.On,'#2ea4e8')):
        image=glyph.pixmap(QSize(19,19),2.5,mode,state).toImage()
        pixel=max((image.pixelColor(x,y) for x in range(image.width()) for y in range(image.height())),key=lambda p:p.alpha())
        assert pixel.alpha()>200 and pixel.name()==color
    duplicate=icons.icon('core',SimpleNamespace(tokens=tokens),primary=True)
    glyph.setIsMask(True)
    assert not duplicate.isMask() and not icons.icon('core',SimpleNamespace(tokens=tokens),primary=True).isMask()


def test_authored_icon_cache_is_bounded_across_color_changes(app):
    from morice.ui_next.icons import _native_icon
    for index in range(135):icon('core',color=f'#{0x102030+index:06x}')
    assert _native_icon.cache_info().currsize<=128


@pytest.mark.skipif(os.name!='nt',reason='Real Windows native Qt subprocess acceptance')
def test_authored_icons_survive_worker_gc_native_subprocess(tmp_path):
    import json,subprocess,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1];output=tmp_path/'icons.json'
    result=subprocess.run([sys.executable,'-X','faulthandler',str(root/'scripts/validate_icon_gc_stress.py'),
        '--with-style','--seconds','3','--output',str(output)],cwd=tmp_path,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    report=json.loads(output.read_text())
    assert report['status']=='ICON_WORKER_GC_STRESS_PASSED' and report['authored_style']
    assert report['worker_collections']>0 and report['frames']>1 and report['icons']==len(MARKS)


def test_glow_levels_differ_and_memory_pressure_reduces_them(tmp_path, app):
    theme = ThemeEngine(tmp_path); theme.update(quality='ULTRA'); policy = EffectPolicy(theme)
    levels = [cursor_style(replace(theme.profile, cursor_glow=name), policy.budget) for name in ('MINIMAL', 'NORMAL', 'HIGH')]
    assert levels[0][0] < levels[1][0] < levels[2][0]
    assert levels[0][1] < levels[1][1] < levels[2][1]
    policy.set_load('VRAM_PRESSURE')
    constrained = cursor_style(replace(theme.profile, cursor_glow='HIGH'), policy.budget)
    assert constrained[0] < levels[0][0] and constrained[1] < levels[0][1]
    assert policy.budget.selected == 'ULTRA'


def test_cursor_settles_without_idle_timer_and_reduced_motion_skips_pulse(tmp_path, app):
    theme = ThemeEngine(tmp_path); theme.update(cursor_trail=True, cursor_glow='NORMAL', persist=False)
    policy = EffectPolicy(theme); clock = EffectClock(policy); owner = QWidget(); owner.resize(700, 400)
    button = QPushButton('Action', owner); button.setGeometry(200, 160, 140, 50)
    owner.show(); owner.activateWindow(); app.processEvents()
    light = CursorLighting(owner, theme, policy, clock); light.set_targets()
    try:
        QTest.mouseMove(button, QPoint(30, 20)); QTest.qWait(70)
        assert light._point is not None and len(light._nearby) <= 3
        assert light.last_dirty_pixels < owner.width()*owner.height()*.4
        QTest.qWait(500); assert not clock.timer.isActive() and not light._trail
        theme.update(reduced_motion=True, persist=False)
        QTest.mousePress(button, Qt.LeftButton, pos=QPoint(70, 20)); QTest.qWait(70)
        assert light._press is None and not light._trail
        assert light._point == light._target_point
        QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(70, 20)); QTest.qWait(70)
        assert not clock.timer.isActive()
        QApplication.sendEvent(button, QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier))
        assert light._point is None
    finally: light.close(); clock.close(); owner.close(); owner.deleteLater(); app.processEvents()


def test_more_group_remains_reachable_with_keyboard_and_authored_icons(tmp_path, app):
    theme = ThemeEngine(tmp_path); owner = QWidget(); layout = QVBoxLayout(owner); rail = NavigationRail(); layout.addWidget(rail)
    binder = UiIconBinder(owner, theme); owner.resize(300, 800); owner.show(); app.processEvents()
    try:
        assert all(not rail.buttons[key].isVisible() for key in ADVANCED)
        rail.more.setFocus(); QTest.keyClick(rail.more, Qt.Key_Space); app.processEvents()
        assert all(rail.buttons[key].isVisible() for key in ADVANCED)
        rail.set_more_expanded(False); rail.set_active('security'); assert rail.buttons['security'].isVisible()
        selected = []; rail.selected.connect(selected.append); rail.buttons['security'].setFocus(); QTest.keyClick(rail.buttons['security'], Qt.Key_Space)
        assert selected == ['security']
        rail.set_expanded(False)
        assert all(button.text() == '' and button.accessibleName() and not button.icon().isNull() for button in rail.buttons.values())
    finally: binder.close(); owner.close(); owner.deleteLater(); app.processEvents()


def test_appearance_search_reaches_hidden_advanced_controls(tmp_path, app):
    theme = ThemeEngine(tmp_path); policy = EffectPolicy(theme); view = AppearanceView(theme, policy); view.show(); app.processEvents()
    try:
        assert not view.advanced.isVisible() and view.fields['cursor_glow'].isVisible()
        view.filter('animation speed'); app.processEvents()
        assert view.advanced.isVisible() and view.fields['motion_speed'].isVisible()
        assert not view.fields['font_scale'].isVisible()
        view.fields['motion_speed'].setValue(135)
        assert theme.profile.motion_speed == 1.35
        view.filter(''); view.advanced_toggle.setChecked(False); assert view.fields['font_scale'].isVisible()
    finally: view.close(); view.deleteLater(); app.processEvents()


def test_reduced_motion_immediately_clears_an_in_progress_button_spring(tmp_path, app):
    theme = ThemeEngine(tmp_path); policy = EffectPolicy(theme); clock = EffectClock(policy)
    button = MotionButton('Controlled action', theme, policy, clock); button.show(); app.processEvents()
    try:
        button._hover = True; button.tick(.02); assert button._value != 0
        theme.update(reduced_motion=True, persist=False); button.tick(.02)
        assert button._value == button._velocity == 0 and not button.tick(.02)
    finally: clock.close(); button.close(); button.deleteLater(); app.processEvents()


def test_collapsed_large_text_routes_fit_inside_scroll_viewport(tmp_path, app):
    theme = ThemeEngine(tmp_path); theme.update(font_scale=1.8, persist=False)
    owner = QWidget(); layout = QVBoxLayout(owner); rail = NavigationRail(); layout.addWidget(rail)
    owner.setStyleSheet(stylesheet(theme.tokens)); binder = UiIconBinder(owner, theme)
    rail.set_expanded(False); owner.resize(100, 600); owner.show(); app.processEvents()
    try:
        rail.set_active('home'); app.processEvents()
        button = rail.buttons['home']; point = button.mapTo(rail.scroll.viewport(), QPoint())
        assert point.x() >= 0 and point.x()+button.width() <= rail.scroll.viewport().width()
    finally: binder.close(); owner.close(); owner.deleteLater(); app.processEvents()
