"""Pure metadata routing: no discovery or blocking waits in agent workers."""
from __future__ import annotations

import time
from dataclasses import replace

from ..kernel import Availability


class NodeRouter:
    def __init__(self, mesh):
        self.mesh = mesh

    def choose(self, cap_id, *, target="", resources=(), allow_fallback=False, sensitive=False, data_node="", expensive=False):
        registry = self.mesh.registry
        if sensitive and not target:
            raise ValueError("Sensitive data needs an explicitly authorized device target.")
        requested = registry.resolve(target, cap_id) if target and target != "auto" else ""
        matches = []
        for node_id, state in tuple(registry.nodes.items()):
            peer = registry.store.get(node_id)
            if peer is None or peer.revoked or not state.connected or time.monotonic() - state.last_seen > 30:
                continue
            descriptor = state.capabilities.get(cap_id)
            if not descriptor or descriptor.status not in {Availability.AVAILABLE, Availability.DEGRADED}:
                continue
            if not peer.remote_allows(cap_id) or not self.mesh.permission_available(node_id, cap_id):
                continue
            if any(state.resources.get(c.resource, 0) < c.amount for c in (*resources, *descriptor.supported_resources)):
                continue
            if expensive and (state.status.get("battery", 100) < 15 and not state.status.get("charging") or state.status.get("thermal") in {"severe", "critical"}):
                continue
            if requested and node_id != requested and not allow_fallback:
                continue
            score = (0 if node_id == requested else 1, 0 if node_id == data_node else 1,
                     state.status.get("cpu_load", 0), state.latency_ms or 1000)
            matches.append((score, node_id))
        if not matches:
            raise ValueError("No connected, permitted device satisfies this capability and resource request.")
        return min(matches)[1]

    def prepare(self, task, context=None):
        target = task.constraints.get("node_id", "local")
        if target == "local":
            return
        if not self.mesh.enabled:
            raise ValueError("Device Mesh is disabled.")
        if target != "auto" and not task.constraints.get("allow_node_fallback", False):
            node_id = self.mesh.registry.resolve(target, task.capability_requirement)
            peer = self.mesh.store.get(node_id)
            if peer is None or peer.revoked:
                raise ValueError("The explicitly targeted device is untrusted/revoked.")
            task.constraints["node_id"] = node_id
            task.resource_requirements = tuple(replace(c, node_id=node_id) if c.node_id == "local" else c for c in task.resource_requirements)
            if any(c.node_id != node_id for c in task.resource_requirements):
                raise ValueError("Remote task resource claims refer to another device.")
            return  # Kernel reports offline, denied or missing capability per branch.
        node_id = self.choose(task.capability_requirement, target=target,
            resources=task.resource_requirements, allow_fallback=bool(task.constraints.get("allow_node_fallback", False)),
            sensitive=bool(task.constraints.get("sensitive_data", False)), data_node=task.constraints.get("data_node", ""),
            expensive=bool(task.constraints.get("expensive", False)))
        task.constraints["node_id"] = node_id  # Selection is pinned for the entire attempt/checkpoint.
        task.resource_requirements = tuple(replace(c, node_id=node_id) if c.node_id == "local" else c for c in task.resource_requirements)
        if any(c.node_id != node_id for c in task.resource_requirements):
            raise ValueError("Remote task resource claims refer to another device.")
