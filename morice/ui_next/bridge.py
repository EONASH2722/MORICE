"""Bounded queued UI delivery over existing workers and Kernel events."""
from __future__ import annotations

import threading
from collections import OrderedDict

from PySide6.QtCore import QObject, Qt, Signal, Slot

from ..redaction import redact_text


class UiBridge(QObject):
    delivered = Signal(str, object)
    event_arrived = Signal(object)
    completed = Signal(str, object)
    event_pending = Signal()

    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.runtime = runtime; self._closed = False; self._next = 0; self._callbacks = {}; self._lock = threading.RLock()
        self._events = OrderedDict(); self._event_scheduled = False; self.coalesced_events = 0
        self.delivered.connect(self._deliver, Qt.QueuedConnection)
        self.event_pending.connect(self._flush_events, Qt.QueuedConnection)
        self._subscription = runtime.kernel.events.subscribe(self._event)

    def _event(self, event):
        if self._closed: return
        payload = event.payload or {}
        allowed = ('generation_id', 'status', 'stage', 'step', 'total_steps', 'completed', 'planned', 'workers', 'reason', 'node_id', 'capability_id', 'capability_requirement', 'workflow_id', 'role', 'state', 'severity', 'finding_id')
        value = {'type': event.event_type.value, 'source': event.source, 'task_id': event.task_id,
            'project_id': event.project_id, 'timestamp': event.timestamp, 'severity': event.severity, 'payload': {key: redact_text(str(payload[key]))[:500] for key in allowed if key in payload}}
        identifier = value['task_id'] or value['payload'].get('generation_id') or value['payload'].get('workflow_id') or value['payload'].get('finding_id') or ''
        key = (value['source'], identifier, value['type'])
        with self._lock:
            if key in self._events: self.coalesced_events += 1
            self._events[key] = value
            self._events.move_to_end(key)
            while len(self._events) > 256: self._events.popitem(last=False); self.coalesced_events += 1
            schedule = not self._event_scheduled; self._event_scheduled = True
        if schedule:
            try: self.event_pending.emit()
            except RuntimeError: pass

    @Slot()
    def _flush_events(self):
        with self._lock:
            values = tuple(self._events.values()); self._events.clear(); self._event_scheduled = False
        if self._closed: return
        for value in values: self.event_arrived.emit(value)

    def submit(self, title, operation, callback, *, priority='interactive'):
        with self._lock:
            if self._closed: raise RuntimeError('UI delivery is closed.')
            if len(self._callbacks) >= 32: raise ValueError('Too many UI requests; wait for current work.')
            self._next += 1; identifier = str(self._next); self._callbacks[identifier] = callback
        try:
            future = self.runtime.workers.submit(title, operation, priority=priority)
        except Exception:
            self._callbacks.pop(identifier, None); raise
        def done(value):
            try: envelope = {'ok': True, 'value': value.result()}
            except Exception as exc: envelope = {'ok': False, 'error': redact_text(str(exc))[:500]}
            if not self._closed:
                try: self.delivered.emit(identifier, envelope)
                except RuntimeError: pass
        future.add_done_callback(done)
        return future

    @Slot(str, object)
    def _deliver(self, identifier, envelope):
        with self._lock: callback = self._callbacks.pop(identifier, None)
        if callback is not None and not self._closed:
            try: callback(envelope)
            except RuntimeError: pass  # A view can have been destroyed while work finished.
        if not self._closed: self.completed.emit(identifier, envelope)

    def close(self):
        self._closed = True
        self.runtime.kernel.events.unsubscribe(self._subscription)
        with self._lock: self._callbacks.clear(); self._events.clear()

    def diagnostics(self):
        with self._lock: return {'pending_deliveries': len(self._callbacks), 'maximum_pending': 32, 'pending_events': len(self._events), 'maximum_events': 256, 'coalesced_events': self.coalesced_events, 'closed': self._closed}
