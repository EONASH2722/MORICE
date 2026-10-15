"""Node metadata and groups wrap the existing cryptographic trust records."""
from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..kernel import Availability, CapabilityDescriptor, ResourceClaim
from ..unified_intelligence import RiskClass
from .protocol import capability, identifier


def provider_schema(schema, depth=0):
    """An untrusted node cannot supply executable or pathological validation rules."""
    if not isinstance(schema, dict) or depth > 8:
        raise ValueError("Provider schema exceeds nesting limits.")
    permitted = {"type", "properties", "required", "additionalProperties", "items", "maxLength", "maxItems", "minimum", "maximum", "enum", "description", "title"}
    if set(schema) - permitted:
        raise ValueError("Provider schema contains unsupported validation rules.")
    if schema.get("type", "object") not in {"object", "array", "string", "integer", "number", "boolean"}:
        raise ValueError("Provider schema type is unsupported.")
    for name in ("maxLength", "maxItems"):
        if name in schema and (isinstance(schema[name], bool) or not isinstance(schema[name], int) or not 0 <= schema[name] <= 200000):
            raise ValueError("Invalid schema limit.")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or len(properties) > 32:
        raise ValueError("Invalid provider schema properties.")
    for value in properties.values():
        provider_schema(value, depth + 1)
    if "items" in schema:
        provider_schema(schema["items"], depth + 1)
    required = schema.get("required", [])
    if not isinstance(required, list) or len(required) > 32 or any(not isinstance(k, str) for k in required):
        raise ValueError("Invalid required fields.")
    if "enum" in schema and (not isinstance(schema["enum"], list) or len(schema["enum"]) > 64):
        raise ValueError("Invalid schema enumeration.")
    return schema


@dataclass
class NodeState:
    node_id: str
    host: str = ""
    port: int = 0
    connected: bool = False
    last_seen: float = 0
    latency_ms: float | None = None
    capabilities: dict = field(default_factory=dict)
    resources: dict = field(default_factory=dict)
    status: dict = field(default_factory=dict)
    reason: str = "Offline"


class NodeRegistry:
    def __init__(self, store, path):
        self.store, self.path = store, Path(path)
        self._lock = threading.RLock()
        self.nodes = {}
        self.groups = {}
        self.defaults = {}
        self.permissions = {}
        self.enabled = False
        if self.path.exists():
            value = json.loads(self.path.read_text())
            self.groups = value.get("groups", {})
            self.defaults = value.get("defaults", {})
            self.permissions = value.get("permissions", {})
            self.enabled = bool(value.get("enabled", False))
        for peer in store.list():
            meta = peer.descriptor.metadata
            self.nodes[peer.descriptor.device_id] = NodeState(peer.descriptor.device_id, meta.get("host", ""), int(meta.get("port", 0)))

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"groups": self.groups, "defaults": self.defaults, "permissions": self.permissions, "enabled": self.enabled}))
            os.replace(temporary, self.path)

    def update(self, node_id, advertisement, *, host, port, latency_ms):
        identifier(node_id)
        entries = advertisement.get("capabilities")
        capacities = advertisement.get("resource_capacities", {})
        if not isinstance(entries, list) or len(entries) > 64 or not isinstance(capacities, dict) or len(capacities) > 32:
            raise ValueError("Invalid capability advertisement.")
        resources = {}
        for name, amount in capacities.items():
            if not isinstance(name, str) or len(name) > 100 or isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or not 0 < amount <= 1048576:
                raise ValueError("Invalid resource capacity.")
            resources[name] = amount
        capabilities = {}
        for value in entries:
            if not isinstance(value, dict):
                raise ValueError("Malformed descriptor.")
            cap_id = capability(value.get("capability_id"))
            if cap_id in capabilities:
                raise ValueError("Duplicate capability advertisement.")
            timeout = value.get("timeout", 30)
            if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not math.isfinite(timeout) or not .05 <= timeout <= 60:
                raise ValueError("Invalid provider timeout.")
            claims = value.get("supported_resources", [])
            if not isinstance(claims, list) or len(claims) > 16:
                raise ValueError("Invalid provider resource list.")
            for claim in claims:
                if not isinstance(claim, dict) or not isinstance(claim.get("resource"), str) or not 1 <= len(claim["resource"]) <= 64:
                    raise ValueError("Invalid resource claim.")
                amount = claim.get("amount", 1)
                if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or not 0 < amount <= 1048576 or not isinstance(claim.get("exclusive", False), bool):
                    raise ValueError("Invalid resource claim amount/exclusivity.")
            parsed = tuple(ResourceClaim(c["resource"], c.get("amount", 1), c.get("exclusive", False), node_id) for c in claims)
            schema = provider_schema(value.get("input_schema", {"type": "object"}))
            risk = RiskClass(value.get("risk_level", "low"))
            if cap_id.startswith(("terminal.", "camera.", "microphone.", "location.", "application.install", "application.uninstall", "clipboard.")):
                risk = RiskClass.HIGH
            capabilities[cap_id] = CapabilityDescriptor(cap_id, str(value.get("name", cap_id))[:120],
                node_id=node_id, provider="device_mesh", input_schema=schema,
                risk_level=risk, status=Availability(value.get("status", "unavailable")),
                supported_resources=parsed, supports_cancellation=True, supports_verification=True, timeout=timeout)
        status = advertisement.get("status", {})
        if not isinstance(status, dict):
            raise ValueError("Invalid node health.")
        # Store only a small, typed health subset. Arbitrary remote metadata cannot become policy.
        clean = {}
        for name in ("battery", "charging", "cpu_count", "ram_mb", "storage_free_mb", "thermal", "cpu_load", "gpu_load", "platform", "process_id"):
            value = status.get(name)
            if name == "charging" and isinstance(value, bool) or name in {"thermal", "platform"} and isinstance(value, str) and len(value) <= 80 or name not in {"charging", "thermal", "platform"} and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                clean[name] = value
        with self._lock:
            self.nodes[node_id] = NodeState(node_id, host, int(port), True, time.monotonic(), latency_ms,
                                          capabilities, resources, clean, "Connected")
        return self.nodes[node_id]

    def discover(self, descriptor, host="", port=0):
        # Discovery cannot write the trust store.
        if len(self.nodes) >= 64 and descriptor.device_id not in self.nodes:
            raise ValueError("Discovery node limit reached.")
        self.nodes.setdefault(identifier(descriptor.device_id), NodeState(descriptor.device_id, host, port, reason="Discovered; pairing required"))

    def group(self, name, members, *, group_id=None):
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or len(self.groups) >= 32 and group_id not in self.groups:
            raise ValueError("Invalid group.")
        members = list(dict.fromkeys(identifier(v) for v in members))
        if len(members) > 32 or any(self.store.get(v) is None or self.store.get(v).revoked for v in members):
            raise ValueError("Group members must be paired nodes.")
        key = identifier(group_id or uuid.uuid4().hex)
        self.groups[key] = {"name": name, "members": members}
        self.save()
        return key

    def remove(self, node_id):
        self.nodes.pop(node_id, None)
        for group in self.groups.values():
            group["members"] = [v for v in group["members"] if v != node_id]
        self.defaults = {k: v for k, v in self.defaults.items() if v != node_id}
        self.permissions = {k: v for k, v in self.permissions.items() if not k.startswith(node_id + "|")}
        self.save()

    def delete_group(self, group_id):
        self.groups.pop(identifier(group_id), None)
        self.save()

    def set_default(self, reference, node_id):
        if reference not in {"phone", "my phone", "tablet", "my tablet", "compute"}:
            raise ValueError("Unsupported device reference.")
        peer = self.store.get(node_id)
        if peer is None or peer.revoked:
            raise ValueError("Defaults require a paired device.")
        self.defaults[reference] = node_id
        self.save()

    def resolve(self, reference, cap_id=""):
        if reference in self.nodes:
            return reference
        if reference in self.defaults:
            return self.defaults[reference]
        matches = []
        for peer in self.store.list():
            d = peer.descriptor
            if peer.revoked:
                continue
            name = d.device_name.casefold()
            platform = d.platform.casefold()
            if reference.casefold() == name or reference.casefold() in {"my phone", "phone"} and platform == "android" or reference.casefold() in {"tablet", "my tablet"} and d.metadata.get("device_type") == "tablet":
                matches.append(d.device_id)
        if len(matches) != 1:
            raise ValueError("Device reference is ambiguous or unavailable; specify a device.")
        return matches[0]

    def snapshot(self):
        rows = []
        for node_id, state in tuple(self.nodes.items()):
            trusted = self.store.get(node_id)
            rows.append({"node_id": node_id, "name": trusted.descriptor.device_name if trusted else node_id,
                         "platform": trusted.descriptor.platform if trusted else "unknown", "trust": "revoked" if trusted and trusted.revoked else "trusted" if trusted else "discovered",
                         "connection": state.reason, "latency_ms": state.latency_ms, "health": state.status,
                         "resources": state.resources, "capabilities": {k: v.status.value for k, v in state.capabilities.items()}})
        return rows
