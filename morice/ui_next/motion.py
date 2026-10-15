"""One visible-only effect clock and interruptible token-driven Qt animations."""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
import weakref

from PySide6.QtCore import QObject, QTimer, Signal, Slot, QPropertyAnimation, QEasingCurve
from shiboken6 import isValid


MOTION_MS = {'instant': 0, 'fast': 100, 'normal': 180, 'panel': 240, 'dialog': 220, 'route': 260, 'core': 300, 'globe': 340, 'workspace': 180, 'wake': 160, 'spring_soft': 220, 'spring_medium': 180, 'spring_strong': 140}


@dataclass(frozen=True)
class EffectBudget:
    selected: str
    effective: str
    fps: int
    cursor_radius: int
    particle_count: int
    glow_factor: float
    atmosphere: bool
    decorative_motion: bool
    reason: str = ''


class EffectPolicy(QObject):
    changed = Signal(object)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme; self.load_state = 'NORMAL'; self._loads = {}; self.budget = self._calculate()
        theme.changed.connect(self.refresh)

    def _calculate(self):
        profile = self.theme.profile; selected = profile.quality; effective = selected; reason = ''
        if self.load_state in {'VRAM_PRESSURE', 'POWER_SAVING'}:
            effective = 'LOW'; reason = 'Low-cost animation while memory or power is constrained.'
        elif self.load_state == 'UNFOCUSED':
            effective = 'LOW'; reason = 'Static effects while this window is unfocused.'
        elif self.load_state in {'GPU_BUSY', 'MEDIA_GENERATING'} and selected in {'HIGH', 'ULTRA'}:
            effective = 'BALANCED'; reason = 'Effects reduced during model work.'
        presets = {'LOW': (20, 72, 0, .15, False), 'BALANCED': (30, 130, 20, .45, True),
            'HIGH': (45, 180, 36, .7, True), 'ULTRA': (60, 220, 48, 1, True)}
        fps, radius, particles, glow, atmosphere = presets[effective]
        decorative = not profile.reduced_motion and profile.motion_strength > 0
        if not decorative: particles = 0
        if profile.particles == 'OFF': particles = 0
        elif profile.particles == 'LOW': particles //= 2
        return EffectBudget(selected, effective, fps, radius, particles, glow, atmosphere, decorative, reason)

    def refresh(self, *_):
        updated = self._calculate()
        if updated != self.budget:
            self.budget = updated; self.changed.emit(updated)

    def set_load(self, state, *, source='legacy'):
        if state not in {'NORMAL', 'GPU_BUSY', 'VRAM_PRESSURE', 'MEDIA_GENERATING', 'POWER_SAVING', 'UNFOCUSED'}:
            raise ValueError('Unknown runtime presentation load state.')
        if state == 'NORMAL': self._loads.pop(source, None)
        else: self._loads[source] = state
        priority = {'UNFOCUSED': 1, 'GPU_BUSY': 2, 'MEDIA_GENERATING': 3, 'POWER_SAVING': 4, 'VRAM_PRESSURE': 5}
        self.load_state = max(self._loads.values(), key=priority.get, default='NORMAL'); self.refresh()


class MotionDirector(QObject):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme; self._animations = {}; self._callbacks = {}; theme.changed.connect(self._configure)

    def duration(self, token):
        if token not in MOTION_MS: raise ValueError('Use a declared motion token.')
        profile = self.theme.profile
        return 0 if profile.reduced_motion or profile.motion_strength == 0 else round(MOTION_MS[token] / profile.motion_speed)

    def animate(self, target, property_name, end, *, token='normal', finished=None):
        self._purge()
        key = (id(target), bytes(property_name))
        if key in self._animations:
            old = self._animations.pop(key); old.stop(); old.deleteLater()
            self._callbacks.pop(key, None)
        duration = self.duration(token)
        if duration == 0 or not target.isVisible():
            target.setProperty(property_name.decode(), end)
            if finished: finished()
            return None
        if len(self._animations) >= 64:
            target.setProperty(property_name.decode(), end)
            if finished: finished()
            return None
        animation = QPropertyAnimation(target, property_name, self)
        animation.setStartValue(target.property(property_name.decode())); animation.setEndValue(end)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.OutCubic if not token.startswith('spring') else QEasingCurve.OutBack)
        self._animations[key] = animation
        self._callbacks[key] = finished
        # QObject slots have native receiver lifetime tracking. A Python closure
        # on destroyed/finished can otherwise outlive its Qt receiver at teardown.
        animation.finished.connect(self._finished)
        target.destroyed.connect(animation.stop)
        animation.start()
        return animation

    @Slot()
    def _finished(self):
        animation = self.sender()
        key = next((key for key, value in self._animations.items() if value is animation), None)
        if key is not None:
            self._animations.pop(key, None)
            callback = self._callbacks.pop(key, None)
            if callback: callback()
        if animation is not None and isValid(animation): animation.deleteLater()

    def _purge(self):
        for key, animation in tuple(self._animations.items()):
            if not isValid(animation) or animation.targetObject() is None:
                self._animations.pop(key, None); self._callbacks.pop(key, None)
                if isValid(animation): animation.deleteLater()

    def _discard(self, key):
        animation = self._animations.pop(key, None)
        self._callbacks.pop(key, None)
        if animation and isValid(animation):
            animation.stop(); animation.deleteLater()

    def _configure(self, *_):
        if self.theme.profile.reduced_motion or self.theme.profile.motion_strength == 0:
            self.stop_all(finish=True)

    def stop_all(self, *, finish=False):
        animations = list(self._animations.values())
        for animation in animations:
            try:
                if finish: animation.setCurrentTime(animation.duration())
                animation.stop(); animation.deleteLater()
            except RuntimeError: pass
        self._animations.clear(); self._callbacks.clear()

    def diagnostics(self):
        self._purge()
        return {'active_animations': len(self._animations), 'maximum_animations': 64}


class EffectClock(QObject):
    """Weak visible subscribers; all scene/cursor/voice effects share this clock."""
    def __init__(self, policy, parent=None):
        super().__init__(parent)
        self.policy = policy; self._subscribers = {}; self._last = 0.; self.frame_samples = []; self._closed = False
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.setInterval(max(16, round(1000 / policy.budget.fps)))
        self.policy.changed.connect(self.configure)

    def subscribe(self, widget, callback):
        if len(self._subscribers) >= 256: raise ValueError('Visible-effect subscriber limit reached.')
        identifier = id(widget)
        self._subscribers[identifier] = (weakref.ref(widget), weakref.WeakMethod(callback))
        widget.destroyed.connect(self._widget_destroyed)

    @Slot(QObject)
    def _widget_destroyed(self, _object):
        for identifier, (reference, _) in tuple(self._subscribers.items()):
            value = reference()
            if value is None or value is _object or not isValid(value): self._subscribers.pop(identifier, None)
        if not self._subscribers and isValid(self.timer): self.timer.stop()

    def unsubscribe_id(self, identifier):
        self._subscribers.pop(identifier, None)
        if not self._subscribers and isValid(self.timer): self.timer.stop()

    def request(self):
        if self._closed or not self._subscribers: return
        if not self.timer.isActive(): self._last = time.perf_counter(); self.timer.start()

    def configure(self, *_):
        if self._closed: return
        self.timer.setInterval(max(16, round(1000 / self.policy.budget.fps)))
        self.request()

    def _tick(self):
        if self._closed or not self._subscribers:
            self.timer.stop(); return
        start = time.perf_counter(); delta = min(.05, max(.001, start - self._last)); self._last = start
        active = False
        for identifier, (reference, method) in tuple(self._subscribers.items()):
            widget, callback = reference(), method()
            if widget is None or callback is None:
                self._subscribers.pop(identifier, None); continue
            try:
                if widget.isVisible() and not widget.window().isMinimized(): active = bool(callback(delta)) or active
            except RuntimeError: self._subscribers.pop(identifier, None)
        self.frame_samples.append((time.perf_counter() - start) * 1000)
        self.frame_samples = self.frame_samples[-600:]
        if not active: self.timer.stop()

    def close(self):
        self._closed = True; self.timer.stop(); self._subscribers.clear()

    def diagnostics(self):
        ordered = sorted(self.frame_samples)
        return {'timer_active': self.timer.isActive(), 'closed': self._closed, 'subscribers': len(self._subscribers), 'samples': len(ordered),
            'callback_p50_ms': ordered[len(ordered) // 2] if ordered else 0,
            'callback_p95_ms': ordered[int((len(ordered) - 1) * .95)] if ordered else 0,
            'scope': 'Effect callback CPU time, not complete paint/presentation frame latency.'}


def spring_step(value, velocity, target, delta, *, stiffness=240, damping=30):
    velocity += ((target - value) * stiffness - velocity * damping) * delta
    value += velocity * delta
    if not math.isfinite(value) or not math.isfinite(velocity): return target, 0
    if abs(value - target) < .001 and abs(velocity) < .01: return target, 0
    return value, velocity
