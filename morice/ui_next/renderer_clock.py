"""Move retained visualization presentation timers onto the shared clock."""
from __future__ import annotations
import weakref

from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QWidget
from shiboken6 import isValid


class RendererClockAdapter(QObject):
    def __init__(self, widget, policy, clock, parent):
        super().__init__(parent); self.widget = weakref.ref(widget); self.policy = policy; self.clock = clock
        self.kind = type(widget).__name__; self.quantum = widget._timer.interval()/1000
        self.accumulator = 0.; widget._timer.stop(); widget.installEventFilter(self); clock.subscribe(widget, self.tick)

    def needs_tick(self, widget):
        if self.kind == 'PhysicsCanvas': return bool(widget.artifact and widget.running)
        if not self.policy.budget.decorative_motion: return False
        if self.kind == 'DataStructureCanvas': return bool(widget.highlighted)
        return bool(widget.artifact and widget.running and (self.kind != 'SceneCanvas' or widget.view_mode == '3d'))

    def eventFilter(self, source, event):
        if event.type() in {QEvent.Show, QEvent.Paint} and self.needs_tick(source): self.clock.request()
        return False

    def tick(self, delta):
        widget = self.widget()
        if widget is None or not isValid(widget) or not self.needs_tick(widget): return False
        self.accumulator = min(self.accumulator + delta, self.quantum * 4)
        while self.accumulator >= self.quantum:
            widget.step() if self.kind == 'PhysicsCanvas' else widget._tick()
            self.accumulator -= self.quantum
        return True


class RendererClockRegistry(QObject):
    def __init__(self, owner, policy, clock):
        super().__init__(owner); self.owner = owner; self.policy = policy; self.clock = clock; self.adapters = {}

    def register(self, root):
        for widget in [root, *root.findChildren(QWidget)]:
            if type(widget).__name__ in {'PhysicsCanvas', 'SceneCanvas', 'BiologyCanvas', 'DataStructureCanvas'} and id(widget) not in self.adapters:
                self.adapters[id(widget)] = RendererClockAdapter(widget, self.policy, self.clock, self)
        for identifier, adapter in tuple(self.adapters.items()):
            widget = adapter.widget()
            if widget is None or not isValid(widget):
                adapter.deleteLater(); self.adapters.pop(identifier, None)

    def close(self):
        for identifier, adapter in tuple(self.adapters.items()):
            widget = adapter.widget()
            if widget is not None and isValid(widget): widget.removeEventFilter(adapter)
            self.clock.unsubscribe_id(identifier); adapter.deleteLater()
        self.adapters.clear()

