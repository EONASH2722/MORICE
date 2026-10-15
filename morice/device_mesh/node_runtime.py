"""Remote admission delegates execution/permissions/verification to the node's kernel."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from ..kernel import (CancellationToken, CapabilityDescriptor, ErrorCode, ExecutionContext,
                      ExecutionResult, ResourceClaim, ResourceDescriptor, TaskNode, TaskStatus,
                      VerificationPolicy, VerificationResult, VerificationStatus)
from ..unified_intelligence import PermissionState, RiskClass
from .protocol import capability, identifier
from .transfers import FileInbox
from ..kernel.resources import ResourceReservation


@dataclass
class Command:
    command_id: str
    peer_id: str
    digest: str
    task: TaskNode
    token: CancellationToken = field(default_factory=CancellationToken)
    state: str = "queued"
    result: ExecutionResult | None = None
    observation: dict = field(default_factory=dict)
    started: float = field(default_factory=time.monotonic)
    reservation: ResourceReservation | None = None


class MeshNodeRuntime:
    def __init__(self, kernel, directory, *, exposed=(), max_jobs=4):
        self.kernel, self.directory = kernel, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.exposed = set(exposed)
        self._observers = {}
        self._read_only = {"python.calculate"}
        self._commands = {}
        self._lock = threading.RLock()
        self._slots = threading.BoundedSemaphore(max_jobs)
        self._pool = None
        self._closed = False
        self.events = deque(maxlen=100)
        self.audit = deque(maxlen=500)
        self._approvals = {}
        self._peer_seen = {}
        self.streams = None
        self._journal = self.directory / "commands.json"
        self._uncertain = {}
        if self._journal.exists():
            self._uncertain = json.loads(self._journal.read_text())
        self.inbox = FileInbox(self.directory / "Inbox", kernel)
        self._install()

    def _install(self):
        def status(args, ctx):
            value = {"platform": platform.system().casefold(), "cpu_count": os.cpu_count(), "process_id": os.getpid(), "online": True}
            try:
                import psutil
                value.update(ram_mb=round(psutil.virtual_memory().total / 1024**2), storage_free_mb=round(psutil.disk_usage(str(self.directory)).free / 1024**2))
                battery = psutil.sensors_battery()
                if battery:
                    value.update(battery=battery.percent, charging=battery.power_plugged)
            except (ImportError, OSError, AttributeError):
                pass
            return value
        if self.kernel.registry.lookup("device.status") is None:
            self.register("device.status", status, status, resources=(), read_only=True)
        self.register("file.receive", self.inbox.execute, self.inbox.observe,
                      resources=(ResourceClaim("DISK"),), read_only=False)
        self.register("file.send", self.inbox.read, self.inbox.observe_read,
                      resources=(ResourceClaim("DISK"),), read_only=True)
        self.kernel.resources.register(ResourceDescriptor("DISK"))
        self.exposed.update({"device.status", "file.receive", "file.send"})
        from .projects import inspect_source_archive
        self.register("project.inspect", lambda args, ctx: inspect_source_archive(self.inbox, args, ctx),
                      lambda args, ctx: inspect_source_archive(self.inbox, args, ctx), read_only=True)

    def register(self, cap_id, execute, observe, *, schema=None, permissions=(), resources=(), risk=RiskClass.LOW, read_only=False):
        self._observers[cap_id] = observe
        if read_only:
            self._read_only.add(cap_id)
        if self.kernel.registry.lookup(cap_id) is None:
            def handler(args, ctx):
                value = execute(args, ctx)
                return value if isinstance(value, ExecutionResult) else ExecutionResult(TaskStatus.SUCCEEDED, True, value, verification_required=True)
            def verify(result, expected, ctx):
                actual = observe(ctx.metadata["task_inputs"], ctx)
                if not isinstance(actual, dict):
                    return VerificationResult(VerificationStatus.INCONCLUSIVE, message="Structured independent observation unavailable.")
                if expected is not None and (not isinstance(expected, dict) or any(k not in actual or actual[k] != v for k, v in expected.items())):
                    return VerificationResult(VerificationStatus.FAILED, message="Observed remote state differs from desired state.")
                if not read_only and cap_id != "file.receive" and not expected:
                    return VerificationResult(VerificationStatus.INCONCLUSIVE, message="Mutating remote capability needs a desired-state contract.")
                if cap_id == "file.receive":
                    args = ctx.metadata["task_inputs"]
                    if args["op"] == "finish" and not actual.get("complete"):
                        return VerificationResult(VerificationStatus.FAILED, message="Received file not complete.")
                    if args["op"] == "chunk" and actual.get("offset") != args["offset"] + len(__import__("base64").b64decode(args["data"])):
                        return VerificationResult(VerificationStatus.FAILED, message="Chunk range not observed.")
                return VerificationResult(VerificationStatus.VERIFIED, ("Independent node observation matched the contract.",))
            self.kernel.registry.register(CapabilityDescriptor(cap_id, cap_id, input_schema=schema or {"type": "object"},
                required_permissions=permissions, supported_resources=resources, supports_verification=True,
                supports_cancellation=True, risk_level=risk, timeout=60), handler, verifier=verify)
        self.exposed.add(cap_id)

    def _replay_safe(self, command):
        cap = command.task.capability_requirement
        return cap in self._read_only or cap in {"file.receive", "file.send"} or cap.endswith(".stream") and command.task.inputs.get("op") in {"sample", "stop"}

    def _persist(self):
        # Only identities/digests/lifecycle metadata. Never logs, file chunks or private observation data.
        value = {**self._uncertain, **{key: {"peer": c.peer_id, "digest": c.digest, "state": c.state, "capability": c.task.capability_requirement}
                 for key, c in self._commands.items() if not self._replay_safe(c)}}
        if len(value) > 1000:
            raise ValueError("Command journal is full; explicit reconciliation is required.")
        temporary = self._journal.with_suffix(".tmp")
        temporary.write_text(json.dumps(value), encoding="utf-8")
        os.replace(temporary, self._journal)

    def advertise(self):
        result = []
        for cap_id in sorted(self.exposed):
            entry = self.kernel.registry.lookup(cap_id)
            if entry:
                descriptor = entry.descriptor.to_dict()
                descriptor["status"] = self.kernel.registry.health(cap_id).status.value
                result.append(descriptor)
        return result

    def approve_command(self, peer, command_id, cap_id, inputs, *, user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Exact local confirmation required.")
        if len(self._approvals) >= 128:
            raise ValueError("Pending confirmation limit reached.")
        self._approvals[(peer, command_id)] = self.kernel.permissions.controller.issue_one_use(command_id, cap_id, inputs)

    def dispatch(self, operation, payload, trusted):
        peer = trusted.descriptor.device_id
        self._peer_seen[peer] = time.monotonic()
        if self._closed or trusted.revoked:
            raise PermissionError("Node is disabled/revoked.")
        if operation == "hello":
            return {"capabilities": self.advertise(), "status": self._observers["device.status"]({}, ExecutionContext()),
                    "granted_capabilities": list(trusted.allowed_capabilities),
                    "resource_capacities": {name: d.capacity for name in ("CPU", "IO", "RAM", "GPU", "VRAM", "DISK", "CAMERA", "MICROPHONE", "SCREEN", "NETWORK", "FOREGROUND_UI") if (d := self.kernel.resources.descriptor(name))}}
        if operation == "ping":
            return {"online": True}
        if operation == "event":
            if payload.get("type") not in {"battery_low", "device_connected", "file_received", "task_completed"} or set(payload) - {"type", "value"}:
                raise ValueError("Unsupported remote event.")
            event = {"node_id": peer, "type": payload["type"], "received_at": time.time()}
            if payload["type"] == "battery_low":
                percent = payload.get("value")
                if isinstance(percent,bool) or not isinstance(percent,(int,float)) or not 0 <= percent <= 100:
                    raise ValueError("Battery events require a percentage in 0..100.")
                event["battery_percent"] = percent
            self.events.append(event)
            from ..kernel import KernelEvent, EventType
            self.kernel.events.publish(KernelEvent(EventType.TASK_PROGRESS, source="device_mesh", payload=event))
            self.kernel.events.publish(KernelEvent(EventType.DEVICE_CHANGED, source="device_mesh", payload=event))
            return {"accepted": True}
        command_id = identifier(payload.get("command_id"))
        with self._lock:
            command = self._commands.get(command_id)
            previous = self._uncertain.get(command_id)
            if command and command.peer_id != peer or previous and previous["peer"] != peer:
                raise PermissionError("Command belongs to a different node.")
            if operation == "submit":
                cap_id = capability(payload.get("capability"))
                inputs = payload.get("inputs", {})
                if not isinstance(inputs, dict) or cap_id not in self.exposed or not trusted.allows(cap_id):
                    return {"state": "failed", "error": "Capability is not permitted on this node."}
                digest = hashlib.sha256(json.dumps({"capability": cap_id, "inputs": inputs, "expected": payload.get("expected")}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                if command:
                    if command.digest != digest:
                        raise ValueError("Idempotency ID reused with different action.")
                    return self._status(command)
                if previous:
                    if previous["digest"] != digest:
                        raise ValueError("Idempotency conflict.")
                    return {"state": "unknown", "error": "Interrupted action requires observation; it was not replayed."}
                ttl = payload.get("ttl", 30)
                if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not .05 <= ttl <= 60:
                    raise ValueError("Invalid remote deadline.")
                if len(self._commands) >= 200:
                    for old_id, old in list(self._commands.items()):
                        if old.result is not None and self._replay_safe(old):
                            self._commands.pop(old_id)
                            if len(self._commands) < 200:
                                break
                if len(self._commands) >= 256:
                    raise ValueError("Command limit reached; reconnect does not erase replay history.")
                if not self._slots.acquire(blocking=False):
                    return {"state": "failed", "error": "Remote execution slots are busy."}
                task = TaskNode(cap_id, inputs, task_id=command_id, timeout=ttl,
                                verification_policy=VerificationPolicy(True, payload.get("expected")))
                command = Command(command_id, peer, digest, task)
                entry = self.kernel.registry.lookup(cap_id)
                if entry is not None:
                    owner = "mesh-admit:" + command_id
                    claims = entry.descriptor.supported_resources
                    if not self.kernel.resources.acquire(owner, claims):
                        self._slots.release()
                        return {"state": "failed", "error": "Node resources are busy; no execution worker was occupied."}
                    command.reservation = ResourceReservation(owner, command_id, cap_id, claims)
                self._commands[command_id] = command
                try:
                    self._persist()  # Persist intent before any mutation.
                    if self._pool is None:
                        self._pool = ThreadPoolExecutor(4, thread_name_prefix="morice-mesh-driver")
                    self._pool.submit(self._run, command)
                except Exception:
                    self._commands.pop(command_id, None)
                    if command.reservation:
                        self.kernel.resources.release(command.reservation.owner)
                    self._slots.release()
                    raise
                return {"state": "acknowledged", "command_id": command_id}
            if previous and command is None:
                if operation == "observe":
                    cap_id = capability(payload.get("capability"))
                    inputs, expected = payload.get("inputs"), payload.get("expected")
                    if not isinstance(inputs, dict) or not trusted.allows(cap_id) or self.kernel.permissions.controller.state(f"node:{peer}:{cap_id}") != PermissionState.GRANTED:
                        raise PermissionError("Interrupted observation is not permitted.")
                    digest = hashlib.sha256(json.dumps({"capability": cap_id, "inputs": inputs, "expected": expected}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                    if previous["digest"] != digest or previous["capability"] != cap_id:
                        raise ValueError("Interrupted observation does not match the original intent.")
                    observer = self._observers.get(cap_id)
                    if observer is not None:
                        actual = observer(inputs, ExecutionContext(metadata={"mesh_peer": peer, "task_inputs": inputs}))
                        matches = isinstance(actual, dict) and isinstance(expected, dict) and bool(expected) and all(k in actual and actual[k] == v for k, v in expected.items())
                        return {"state": "observed", "command_id": command_id, "capability": cap_id,
                                "observation": actual, "verification": "verified" if matches else "inconclusive"}
                return {"state": "unknown", "error": "Prior action has no fresh observation; no automatic replay."}
            if command is None:
                return {"state": "unknown"}
            if operation == "cancel":
                command.token.cancel("Remote cancellation requested.")
                self.kernel.cancel(command_id)
                if self.streams and command.task.capability_requirement.endswith(".stream"):
                    self.streams.stop_owned(peer, command.task.capability_requirement)
                return {"state": "cancelling" if command.result is None else command.state}
            if operation in {"status", "observe"}:
                group = f"node:{peer}:{command.task.capability_requirement}"
                if not trusted.allows(command.task.capability_requirement) or self.kernel.permissions.controller.state(group) != PermissionState.GRANTED:
                    return {"state": command.state, "physical_active": self._status(command)["physical_active"], "error": "Capability permission was withdrawn."}
                return self._status(command) if operation == "status" else self._observe(command)
        raise ValueError("Unsupported RPC operation.")

    def _run(self, command):
        try:
            with self._lock:
                command.state = "executing"
                self._persist()
            context = ExecutionContext(cancellation_token=command.token,
                permissions=(f"node:{command.peer_id}:{command.task.capability_requirement}",),
                approval_token=self._approvals.pop((command.peer_id, command.command_id), ""),
                deadline=command.started + command.task.timeout,
                metadata={"mesh_peer": command.peer_id, "remote_command": command.command_id,
                          "_resource_reservation": command.reservation})
            result = self.kernel.run_task(command.task, context)
            with self._lock:
                command.result = result
                command.state = "verified" if result.success and result.verification and result.verification.status == VerificationStatus.VERIFIED else "cancelled" if result.status == TaskStatus.CANCELLED else "failed"
                self._persist()
                self.audit.append({"node_id": command.peer_id, "command_id": command.command_id,
                    "capability": command.task.capability_requirement, "state": command.state, "timestamp": time.time()})
        except Exception:
            with self._lock:
                command.state = "unknown"
                command.result = ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, "Node execution failed; explicit observation is required before retry.")
                command.result.task_id = command.command_id
                command.result.capability_id = command.task.capability_requirement
                self.audit.append({"node_id": command.peer_id, "command_id": command.command_id, "state": "unknown"})
        finally:
            if command.reservation and not command.reservation.started:
                self.kernel.resources.release(command.reservation.owner)
            self._slots.release()

    def _status(self, command):
        return {"state": command.state, "command_id": command.command_id,
                "physical_active": command.result is None or command.result.execution_id in self.kernel.resources.snapshot(),
                "result": command.result.to_dict() if command.result else None}

    def _observe(self, command):
        if command.result is None:
            return {"state": command.state, "observation": None}
        observer = self._observers.get(command.task.capability_requirement)
        if observer is None:
            return {"state": command.state, "observation": None, "verification": command.result.verification.status.value if command.result.verification else "inconclusive"}
        context = ExecutionContext(metadata={"mesh_peer": command.peer_id, "task_inputs": command.task.inputs})
        observed = observer(command.task.inputs, context)
        if not isinstance(observed, dict):
            raise ValueError("Invalid node observation.")
        return {"state": command.state, "observation": observed,
                "verification": command.result.verification.status.value if command.result.verification else "inconclusive",
                "command_id": command.command_id, "capability": command.task.capability_requirement}

    def disconnect(self, peer):
        with self._lock:
            for command in self._commands.values():
                if command.peer_id == peer and command.result is None:
                    command.token.cancel("Peer disconnected or revoked.")
            self.inbox.disconnect(peer)
            if self.streams:
                self.streams.disconnect(peer)

    def expire(self):
        self.inbox.expire()
        if self.streams:
            self.streams.expire()
        for peer, last in list(self._peer_seen.items()):
            if time.monotonic() - last > 30:
                self.disconnect(peer)
                self._peer_seen.pop(peer, None)

    def close(self):
        self._closed = True
        for command in self._commands.values():
            command.token.cancel("Node is stopping.")
        if self._pool:
            self._pool.shutdown(wait=True, cancel_futures=False)
        self.inbox.close()
