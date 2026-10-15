import json
from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtTest import QTest

from morice.ui_next.themes import AppearanceProfile, AppearanceStore, PRESETS, ThemeEngine, contrast, tokens
from morice.ui_next.motion import EffectClock, EffectPolicy, MotionDirector, spring_step


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('preset', PRESETS)
def test_preset_text_and_button_contrast(preset):
    value = tokens(AppearanceProfile(preset=preset))
    assert contrast(value['text_primary'], value['surface']) >= 4.5
    assert contrast(value['text_secondary'], value['surface']) >= 4.5
    assert contrast(value['accent_text'], value['accent_primary']) >= 4.5


@pytest.mark.parametrize('changes', [{'qss': 'url(secret)'}, {'primary_accent': 'red; image:url(file)'},
    {'font_scale': 100}, {'motion_speed': -1}, {'glow': float('nan')}, {'particles': '100000'}, {'cursor_light': 'true'}])
def test_theme_rejects_executable_and_unbounded_data(changes):
    with pytest.raises((ValueError, TypeError)): AppearanceProfile.from_dict({'schema': 1, **changes})


def test_corrupt_appearance_falls_back_preserves_bytes_and_legacy_preferences(tmp_path):
    store = AppearanceStore(tmp_path); store.path.write_text('{bad')
    assert store.load().preset == 'MORICE' and store.error
    assert store.path.read_text() == '{bad'
    other = AppearanceStore(tmp_path / 'other')
    assert other.load({'theme': 'light', 'ui_scale': '1.2', 'reduced_motion': 'true'}).preset == 'ICE'
    profile = AppearanceProfile(preset='AMETHYST', primary_accent='#010101')
    other.save(profile)
    assert AppearanceStore.import_file(other.path) == profile
    assert contrast(tokens(profile)['accent_text'], '#010101') > 4.5


def test_runtime_load_reduces_and_restores_selected_quality(tmp_path, app):
    engine = ThemeEngine(tmp_path); engine.update(quality='ULTRA', particles='NORMAL')
    policy = EffectPolicy(engine)
    assert policy.budget.effective == 'ULTRA'
    policy.set_load('MEDIA_GENERATING'); assert policy.budget.effective == 'BALANCED' and policy.budget.selected == 'ULTRA'
    policy.set_load('VRAM_PRESSURE'); assert policy.budget.effective == 'LOW' and policy.budget.particle_count == 0
    policy.set_load('NORMAL'); assert policy.budget.effective == 'ULTRA'
    engine.update(reduced_motion=True)
    assert not policy.budget.decorative_motion and policy.budget.particle_count == 0


def test_interrupted_animation_and_reduced_motion_final_state(tmp_path, app):
    theme = ThemeEngine(tmp_path); director = MotionDirector(theme)
    widget = QWidget(); widget.show(); app.processEvents()
    director.animate(widget, b'pos', QPoint(100, 100), token='panel')
    QTest.qWait(50)
    director.animate(widget, b'pos', QPoint(0, 0), token='panel')
    theme.update(reduced_motion=True); app.processEvents()
    assert widget.pos() == QPoint(0, 0) and director.diagnostics()['active_animations'] == 0
    widget.close(); widget.deleteLater(); app.processEvents()


def test_closed_clock_ignores_late_policy_updates_and_requests(tmp_path, app):
    theme = ThemeEngine(tmp_path); clock = EffectClock(EffectPolicy(theme))
    class Scene(QWidget):
        def tick(self, _): return True
    scene = Scene(); scene.show(); clock.subscribe(scene, scene.tick); clock.request()
    assert clock.timer.isActive()
    clock.close(); theme.update(quality='ULTRA'); clock.request(); clock.configure()
    app.processEvents()
    assert not clock.timer.isActive() and clock.diagnostics()['closed']
    assert clock.diagnostics()['subscribers'] == 0
    scene.close(); scene.deleteLater(); app.processEvents()


def test_hidden_effects_and_empty_clock_stop(tmp_path, app):
    theme = ThemeEngine(tmp_path); clock = EffectClock(EffectPolicy(theme))
    class Scene(QWidget):
        def __init__(self): super().__init__(); self.count = 0
        def tick(self, _): self.count += 1; return False
    widget = Scene(); clock.subscribe(widget, widget.tick); clock.request(); QTest.qWait(80)
    assert widget.count == 0 and not clock.timer.isActive()
    widget.show(); clock.request(); QTest.qWait(80)
    assert widget.count == 1 and not clock.timer.isActive()
    widget.hide(); clock.unsubscribe_id(id(widget)); assert clock.diagnostics()['subscribers'] == 0
    widget.close(); clock.close()


def test_spring_settles_without_unbounded_motion():
    value = velocity = 0.
    for _ in range(400): value, velocity = spring_step(value, velocity, 1., 1 / 60)
    assert value == 1 and velocity == 0
