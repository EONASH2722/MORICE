"""Ordered, bounded delivery with weak bound-method subscriptions."""
from __future__ import annotations

import logging
import threading
import time
import weakref
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .contracts import new_id


class EventType(str, Enum):
    TASK_QUEUED = "task_queued"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_VERIFYING = "task_verifying"
    TASK_WAITING = "task_waiting"
    TASK_RESUMED = "task_resumed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    USER_CANCELLED = "user_cancelled"
    CAPABILITY_AVAILABLE = "capability_available"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    WORKER_CHANGED = "worker_changed"
    WORKFLOW_CHANGED = "workflow_changed"
    AMBIENT_INPUT = "ambient_input"
    CONNECTOR_CHANGED = "connector_changed"
    BUILD_FINISHED = "build_finished"
    RESEARCH_FINISHED = "research_finished"
    DEVICE_CHANGED = "device_changed"
    SECURITY_FINDING = "security_finding"
    MEDIA_QUEUED = "media_queued"
    MEDIA_STARTED = "media_started"
    MEDIA_COMPLETED = "media_completed"
    MEDIA_FAILED = "media_failed"
    MEDIA_CANCELLED = "media_cancelled"
    MEDIA_OOM = "media_oom"


@dataclass(frozen=True)
class KernelEvent:
    event_type: EventType
    source: str = "kernel"
    task_id: str = ""
    project_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"
    event_id: str = field(default_factory=new_id)
    timestamp: float = field(default_factory=time.time)


class EventBus:
    def __init__(self, max_pending: int = 1024):
        if not isinstance(max_pending, int) or not 1 <= max_pending <= 65536:
            raise ValueError("Event queue capacity must be between 1 and 65536.")
        self._subscriptions: dict[str, tuple[EventType | None, Any, bool]] = {}
        self._queue: deque[KernelEvent] = deque()
        self._lock = threading.RLock()
        self._delivering = False
        self.max_pending = max_pending
        self.dropped_events = 0

    def subscribe(self, callback: Callable[[KernelEvent], None], event_type: EventType | None = None) -> str:
        with self._lock:
            for key, (kind, ref, weak) in tuple(self._subscriptions.items()):
                existing = ref() if weak else ref
                if existing is None:
                    self._subscriptions.pop(key, None)
                elif kind == event_type and existing == callback:
                    return key
            weak = getattr(callback, "__self__", None) is not None and hasattr(callback, "__func__")
            key = new_id()
            self._subscriptions[key] = (event_type, weakref.WeakMethod(callback) if weak else callback, weak)
            return key

    def unsubscribe(self, subscription_id: str) -> None:
        with self._lock:
            self._subscriptions.pop(subscription_id, None)

    def publish(self, event: KernelEvent) -> None:
        # One publisher drains in FIFO order. Other/reentrant publishers enqueue
        # and return; callbacks never run under the bus lock. Domain locks in a
        # subscriber therefore cannot invert with a concurrent publisher.
        with self._lock:
            if len(self._queue) >= self.max_pending:
                self.dropped_events += 1
                return
            self._queue.append(event)
            if self._delivering:
                return
            self._delivering = True
        try:
            for _ in range(self.max_pending):
                with self._lock:
                    if not self._queue:
                        self._delivering = False
                        return
                    current = self._queue.popleft()
                    subscriptions = tuple(self._subscriptions.items())
                for key, (kind, ref, weak) in subscriptions:
                    with self._lock:
                        callback = ref() if weak else ref
                        if callback is None:
                            self._subscriptions.pop(key, None)
                        selected = callback is not None and key in self._subscriptions and (kind is None or kind == current.event_type)
                    if selected:
                        try:
                            callback(current)
                        except Exception as exc:
                            logging.getLogger(__name__).error("Kernel event subscriber failed (%s)", type(exc).__name__)
            with self._lock:
                self.dropped_events += len(self._queue)
                self._queue.clear()
                self._delivering = False
        except BaseException:
            with self._lock:
                self.dropped_events += len(self._queue)
                self._queue.clear()
                self._delivering = False
            raise

    def clear(self) -> None:
        with self._lock:
            self._subscriptions.clear()
            self._queue.clear()
