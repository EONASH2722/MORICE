"""Metadata discovery with cached lazy health and isolated optional providers."""
from __future__ import annotations

import logging
import platform
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable

from .contracts import Availability, CapabilityDescriptor, CapabilityHandler, Verifier
from .events import EventBus, EventType, KernelEvent


@dataclass(frozen=True)
class CapabilityHealth:
    status: Availability
    reason: str = ""
    checked_at: float = 0.0


@dataclass(frozen=True)
class CapabilityEntry:
    descriptor: CapabilityDescriptor
    handler: CapabilityHandler
    verifier: Verifier | None = None
    health_check: Callable[[], CapabilityHealth] | None = None
    # Compatibility adapters may delegate to an existing domain authority.
    permission_check: Callable | None = None
    on_completed: Callable | None = None
    # Optional bounded provider-specific estimates; leases still belong to the
    # shared ResourceManager and scheduler. Never execute work in this callback.
    resource_resolver: Callable | None = None


class CapabilityRegistry:
    def __init__(self, events: EventBus | None = None, health_ttl: float = 30.0):
        self._entries: dict[str, CapabilityEntry] = {}
        self._node_entries: dict[tuple[str, str], CapabilityEntry] = {}
        self._health: dict[str, CapabilityHealth] = {}
        self._lock = threading.RLock()
        self.events = events
        self.health_ttl = health_ttl

    def register(self, descriptor: CapabilityDescriptor, handler: CapabilityHandler, *, verifier: Verifier | None = None, health_check: Callable[[], CapabilityHealth] | None = None, permission_check: Callable | None = None, on_completed: Callable | None = None, resource_resolver: Callable | None = None) -> None:
        if descriptor.supports_verification and verifier is None:
            raise ValueError("A capability advertising verification needs a verifier.")
        with self._lock:
            key = descriptor.capability_id if descriptor.node_id == "local" else (descriptor.node_id, descriptor.capability_id)
            entries = self._entries if descriptor.node_id == "local" else self._node_entries
            if key in entries:
                raise ValueError(f"Capability already registered: {descriptor.capability_id}")
            entries[key] = CapabilityEntry(descriptor, handler, verifier, health_check, permission_check, on_completed, resource_resolver)
            self._health[key] = CapabilityHealth(descriptor.status)

    def unregister(self, capability_id: str, node_id: str = "local") -> None:
        with self._lock:
            key = capability_id if node_id == "local" else (node_id, capability_id)
            (self._entries if node_id == "local" else self._node_entries).pop(key, None)
            self._health.pop(key, None)

    def extend(self, capability_id: str, **changes) -> None:
        """Atomically extend a registration while preserving its identity."""
        with self._lock:
            updated = replace(self._entries[capability_id], **changes)
            if updated.descriptor.capability_id != capability_id:
                raise ValueError("Capability identity cannot change.")
            self._entries[capability_id] = updated
            self._health[capability_id] = CapabilityHealth(updated.descriptor.status)

    def lookup(self, capability_id: str, node_id: str = "local") -> CapabilityEntry | None:
        with self._lock:
            return self._entries.get(capability_id) if node_id == "local" else self._node_entries.get((node_id, capability_id))

    def providers(self, capability_id: str) -> tuple[CapabilityEntry, ...]:
        with self._lock:
            return tuple(e for e in (*self._entries.values(), *self._node_entries.values()) if e.descriptor.capability_id == capability_id)

    def set_status(self, capability_id: str, status: Availability, reason: str = "") -> None:
        with self._lock:
            entry = self._entries[capability_id]
            self._entries[capability_id] = replace(entry, descriptor=replace(entry.descriptor, status=status))
            self._health[capability_id] = CapabilityHealth(status, reason, time.monotonic())
        if self.events:
            kind = EventType.CAPABILITY_AVAILABLE if status in {Availability.AVAILABLE, Availability.DEGRADED} else EventType.CAPABILITY_UNAVAILABLE
            self.events.publish(KernelEvent(kind, source=capability_id, payload={"status": status.value, "reason": reason}))

    def health(self, capability_id: str, *, refresh: bool = False, node_id: str = "local") -> CapabilityHealth:
        # Health checks are lightweight by contract; expensive probes belong in
        # a separate background capability, never in discovery or startup.
        with self._lock:
            key = capability_id if node_id == "local" else (node_id, capability_id)
            entry = self.lookup(capability_id, node_id)
            cached = self._health[key]
            if entry.descriptor.status == Availability.DISABLED:
                return cached
            if not refresh and cached.checked_at and time.monotonic() - cached.checked_at < self.health_ttl:
                return cached
            try:
                state = entry.health_check() if entry.health_check else CapabilityHealth(
                    Availability.AVAILABLE if entry.descriptor.status == Availability.REGISTERED else entry.descriptor.status
                )
                if not isinstance(state, CapabilityHealth):
                    raise TypeError("Invalid capability health result.")
            except Exception as exc:
                logging.getLogger(__name__).exception("Capability health failed: %s", capability_id)
                state = CapabilityHealth(Availability.UNAVAILABLE, f"Health check failed: {type(exc).__name__}: {exc}")
            state = replace(state, checked_at=time.monotonic())
            self._health[key] = state
        if self.events and cached.status != state.status:
            kind = EventType.CAPABILITY_AVAILABLE if state.status in {Availability.AVAILABLE, Availability.DEGRADED} else EventType.CAPABILITY_UNAVAILABLE
            self.events.publish(KernelEvent(kind, source=capability_id, payload={"status": state.status.value, "reason": state.reason}))
        return state

    def search(self, query: str = "", *, platform_name: str | None = None, permissions: tuple[str, ...] | None = None, availability: tuple[Availability, ...] | None = None, healthy: bool | None = None, resources: tuple[str, ...] | None = None, category: str | None = None, provider: str | None = None) -> tuple[CapabilityDescriptor, ...]:
        with self._lock:
            entries = (*self._entries.values(), *self._node_entries.values())
            health = dict(self._health)
        found = []
        for entry in entries:
            d = entry.descriptor
            state = health[d.capability_id if d.node_id == "local" else (d.node_id, d.capability_id)].status
            if query.casefold() not in f"{d.capability_id} {d.name} {d.description} {d.category} {d.provider}".casefold():
                continue
            if platform_name and "any" not in d.supported_platforms and platform_name.casefold() not in {p.casefold() for p in d.supported_platforms}:
                continue
            if permissions is not None and not set(d.required_permissions).issubset(permissions):
                continue
            if availability is not None and state not in availability:
                continue
            if healthy is not None and (state in {Availability.AVAILABLE, Availability.DEGRADED}) != healthy:
                continue
            if resources is not None and not {c.resource for c in d.supported_resources}.issubset(resources):
                continue
            if category and d.category != category or provider and d.provider != provider:
                continue
            found.append(replace(d, status=state))
        return tuple(sorted(found, key=lambda d: d.capability_id))
