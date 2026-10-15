"""Atomic, node-scoped resource leases, independent of renderer caches."""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar

from .contracts import ResourceClaim
_CURRENT_EXECUTION = ContextVar("morice_resource_execution", default=None)


@dataclass(frozen=True)
class ResourceDescriptor:
    resource: str
    capacity: float = 1.0
    node_id: str = "local"
    available: bool = True


@dataclass
class ResourceReservation:
    """Internal scheduler admission token; actual execution keeps lease ownership."""
    owner: str
    task_id: str
    capability_id: str
    claims: tuple[ResourceClaim, ...]
    started: bool = False


class ResourceManager:
    def __init__(self):
        self._resources: dict[tuple[str, str], ResourceDescriptor] = {}
        self._leases: dict[str, tuple[ResourceClaim, ...]] = {}
        self._retained: dict[str, str] = {}
        self._lock = threading.RLock()
        self.register(ResourceDescriptor("FOREGROUND_UI"))

    def register(self, resource: ResourceDescriptor) -> None:
        if not math.isfinite(resource.capacity) or resource.capacity <= 0:
            raise ValueError("Resource capacity must be finite and positive.")
        with self._lock:
            self._resources[(resource.node_id, resource.resource)] = resource

    def acquire(self, owner: str, claims: tuple[ResourceClaim, ...]) -> bool:
        with self._lock:
            if owner in self._leases:
                raise ValueError("Resource owner already holds a lease.")
            keys = {(c.node_id, c.resource) for c in claims}
            for key in keys:
                descriptor = self._resources.get(key)
                if descriptor is None or not descriptor.available:
                    return False
                requested = [c for c in claims if (c.node_id, c.resource) == key]
                held = [c for lease in self._leases.values() for c in lease if (c.node_id, c.resource) == key]
                if (any(c.exclusive for c in requested) and held) or any(c.exclusive for c in held):
                    return False
                if sum(c.amount for c in requested + held) > descriptor.capacity:
                    return False
            self._leases[owner] = claims
            return True

    def release(self, owner: str) -> None:
        with self._lock:
            if owner in self._retained:
                return
            self._leases.pop(owner, None)

    def retain(self, owner: str, reason: str) -> None:
        """Keep an existing lease until its physical cleanup is reconciled."""
        with self._lock:
            if owner not in self._leases:
                raise ValueError("Only an existing physical lease can be retained.")
            self._retained[owner] = str(reason)[:1000]

    def confirm_cleanup(self, owner: str) -> None:
        """Called by the owning adapter only after independent cleanup evidence."""
        with self._lock:
            self._retained.pop(owner, None)
            self._leases.pop(owner, None)

    def retained(self) -> dict[str, str]:
        with self._lock:
            return dict(self._retained)

    def owns(self, owner: str, claims: tuple[ResourceClaim, ...]) -> bool:
        with self._lock:
            return self._leases.get(owner) == claims

    def snapshot(self) -> dict[str, tuple[ResourceClaim, ...]]:
        with self._lock:
            return dict(self._leases)

    def descriptor(self, resource: str, node_id: str = "local") -> ResourceDescriptor | None:
        with self._lock:
            return self._resources.get((node_id, resource))

    @contextmanager
    def execution_scope(self, owner):
        with self._lock:
            if owner not in self._leases:
                raise ValueError("Execution scope requires an actual existing lease.")
        token = _CURRENT_EXECUTION.set((self, owner))
        try:
            yield
        finally:
            _CURRENT_EXECUTION.reset(token)

    def current_holds(self, resource, node_id="local"):
        scope = _CURRENT_EXECUTION.get()
        with self._lock:
            return bool(scope and scope[0] is self and any(c.resource == resource and c.node_id == node_id for c in self._leases.get(scope[1], ())))
