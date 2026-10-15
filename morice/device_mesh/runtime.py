"""One mesh facade attaches node providers to Phases 1, 2, 3 and 4."""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import uuid
from collections import deque
from dataclasses import replace
from pathlib import Path

from ..action_runtime.contracts import ActionBinding, ActionMethod, Observation
from ..kernel import (Availability, ErrorCode, ExecutionContext, ExecutionResult, ResourceDescriptor,
                      TaskGraph, TaskNode, TaskStatus, VerificationPolicy, VerificationResult, VerificationStatus)
from ..kernel.registry import CapabilityHealth
from ..node_protocol import LanDiscovery, NodeDescriptor
from ..unified_intelligence import PermissionState
from .identity import NodeCredentials, ProtectedTrustStore
from .node_runtime import MeshNodeRuntime
from .protocol import VERSION, CHUNK_BYTES, identifier
from .registry import NodeRegistry, NodeState
from .routing import NodeRouter
from .transfers import file_hash
from .transport import MeshTransport


class DeviceMesh:
    def __init__(self, kernel, directory, *, actions=None, agents=None, identity=None, name="MORICE Node", host="127.0.0.1", port=0, pair_port=0, exposed=()):
        self.kernel, self.actions, self.agents = kernel, actions, agents
        self.directory = Path(directory)
        self.credentials = NodeCredentials(self.directory / "identity", identity)
        self.store = ProtectedTrustStore(self.directory, self.credentials)
        self.registry = NodeRegistry(self.store, self.directory / "mesh-settings.json")
        import platform
        self.descriptor = NodeDescriptor(self.credentials.node_id, name, platform.system().casefold(), (), protocol_version=VERSION)
        self.node = MeshNodeRuntime(kernel, self.directory / "node", exposed=exposed)
        self.transport = MeshTransport(self.credentials, self.store, self.descriptor, self.node.dispatch, host=host, port=port, pair_port=pair_port)
        self.router = NodeRouter(self)
        self._stop = threading.Event()
        self._heartbeat = None
        self._registered = {}
        self._commands = {}
        self._remote_leases = {}
        self._session_permissions = set()
        self._once = {}
        self._lock = threading.RLock()
        self.audit = deque(maxlen=500)
        self._queue = {}
        from .streams import StreamManager
        self.streams = StreamManager(kernel)
        self.node.streams = self.streams
        self._discovery = None
        kernel.mesh = self
        for key, state in self.registry.permissions.items():
            node_id, cap_id = key.split("|", 1)
            kernel.permissions.controller.set_state(f"node:{node_id}:{cap_id}", state)

    @property
    def enabled(self):
        return self.transport.running

    def enable(self, *, heartbeat=True):
        self.transport.start()
        if self.transport.host != "127.0.0.1" and self._discovery is None:
            self.descriptor = replace(self.descriptor, capabilities=tuple(sorted(self.node.exposed)))
            self.transport.descriptor = self.descriptor
            self._discovery = LanDiscovery(self.descriptor, node_port=self.transport.port)
            self._discovery.start_responder()
        self.node._closed = False
        self.registry.enabled = True
        self.registry.save()
        self._stop.clear()
        if heartbeat and self._heartbeat is None:
            self._heartbeat = threading.Thread(target=self._heartbeat_loop, daemon=True, name="morice-mesh-heartbeat")
            self._heartbeat.start()

    def disable(self):
        self._stop.set()
        if self._discovery:
            self._discovery.stop()
            self._discovery = None
        cleanup_until = time.monotonic() + 2
        for node_id in {value["node_id"] for value in self._commands.values() if value.get("stream_start")}:
            self._stop_remote_sources(node_id, deadline=cleanup_until)
        for command_id, value in reversed(tuple(self._commands.items())):
            remaining = cleanup_until - time.monotonic()
            if remaining <= .01:
                break
            if value["state"] in {"sent", "executing", "unknown"} and self.enabled:
                try:
                    self._rpc(value["node_id"], "cancel", {"command_id": command_id}, timeout=min(.2, remaining))
                except (OSError, ValueError, KeyError):
                    pass
        if self.streams:
            try:
                self.streams.close()
            except Exception:
                self.audit.append({"state": "capture_cleanup_unconfirmed", "timestamp": time.time()})
        for peer in self.store.list():
            try:
                self.node.disconnect(peer.descriptor.device_id)
            except Exception:
                self.audit.append({"node_id": peer.descriptor.device_id, "state": "cleanup_unconfirmed"})
        self.transport.stop()
        if self._heartbeat:
            self._heartbeat.join(3)
            self._heartbeat = None
        for state in self.registry.nodes.values():
            state.connected, state.reason = False, "Offline"
            for resource, amount in state.resources.items():
                self.kernel.resources.register(ResourceDescriptor(resource, amount, state.node_id, available=False))
        for owner in tuple(self._remote_leases):
            self.kernel.resources.release(owner)
        self._remote_leases.clear()
        for node_id, cap_id in tuple(self._session_permissions):
            remembered = self.registry.permissions.get(node_id + "|" + cap_id, PermissionState.ASK.value)
            self.kernel.permissions.controller.set_state(f"node:{node_id}:{cap_id}", remembered)
        self._session_permissions.clear()
        self._once.clear()
        self._queue.clear()
        self.registry.enabled = False
        self.registry.save()

    def close(self):
        self.disable()
        self.node.close()

    def begin_pair(self, host, pair_port, code, fingerprint, *, user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Explicit pairing action and fingerprint confirmation required.")
        self.enable(heartbeat=False)
        value = self.transport.rpc(host, pair_port, "pair", {"code": code, "certificate": self.credentials.certificate,
            "descriptor": replace(self.descriptor, metadata={"port": self.transport.port}).to_dict()}, pairing_pin=fingerprint)
        return {**value, "host": host, "pair_port": pair_port, "fingerprint": fingerprint}

    def approve_pair(self, pair_id, capabilities, *, user_confirmed=False):
        if not set(capabilities).issubset(self.node.exposed):
            raise ValueError("Only implemented, exposed capabilities can be granted.")
        self.transport.approve_pair(pair_id, capabilities, user_confirmed=user_confirmed)
        peer = self.transport._pending[pair_id]["descriptor"].device_id
        descriptor = self.store.get(peer).descriptor
        self.registry.nodes[peer] = NodeState(peer, descriptor.metadata.get("host", ""), descriptor.metadata.get("port", 0))
        for cap_id in capabilities:
            self.set_permission(peer, cap_id, PermissionState.GRANTED, user_confirmed=True)

    def finish_pair(self, pending, *, outbound_permissions=(), inbound_permissions=(), user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Local device/grant confirmation required.")
        value = self.transport.rpc(pending["host"], pending["pair_port"], "pair_status", {"pair_id": pending["pair_id"]}, pairing_pin=pending["fingerprint"])
        if value.get("state") != "trusted":
            raise PermissionError("The other device has not confirmed pairing.")
        descriptor = NodeDescriptor.from_dict(value["descriptor"])
        from .identity import certificate_id, certificate_pin
        if certificate_id(value["certificate"]) != descriptor.device_id or certificate_pin(value["certificate"]) != pending["fingerprint"]:
            raise ValueError("Pairing identity mismatch.")
        if not set(inbound_permissions).issubset(self.node.exposed):
            raise ValueError("Unsupported local grants.")
        descriptor = replace(descriptor, metadata={"host": pending["host"], "port": value["port"]})
        peer = self.store.enroll(descriptor, value["certificate"], b"", inbound_permissions,
                                 user_approved=True, remote_capabilities=value["grants"])
        self.transport._refresh_context()
        for cap_id in outbound_permissions:
            if cap_id not in value["grants"]:
                raise ValueError("Remote device did not grant this capability.")
            self.set_permission(descriptor.device_id, cap_id, PermissionState.GRANTED, user_confirmed=True)
        for cap_id in inbound_permissions:
            self.set_permission(descriptor.device_id, cap_id, PermissionState.GRANTED, user_confirmed=True)
        self.connect(descriptor.device_id, pending["host"], value["port"])
        return peer

    def set_permission(self, node_id, cap_id, state, *, user_confirmed=False, remember=True):
        if not user_confirmed:
            raise PermissionError("Permission changes require explicit user action.")
        state = PermissionState(state)
        self.kernel.permissions.controller.set_state(f"node:{node_id}:{cap_id}", state)
        if state != PermissionState.GRANTED and cap_id.endswith(".stream"):
            self._stop_remote_sources(node_id, cap_id)
            try:
                self.streams.stop_owned(node_id, cap_id)
            except Exception:
                self.audit.append({"node_id": node_id, "capability": cap_id, "state": "source_cleanup_unconfirmed"})
        if remember:
            self.registry.permissions[node_id + "|" + cap_id] = state.value
            self.registry.save()
        else:
            self._session_permissions.add((node_id, cap_id))

    def grant_once(self, node_id, cap_id, task_id, inputs, *, user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Exact device action confirmation is required.")
        state = self.kernel.permissions.controller.state(f"node:{node_id}:{cap_id}")
        if state in {PermissionState.DENIED, PermissionState.UNSUPPORTED, PermissionState.OS_REQUIRED}:
            raise PermissionError("A denied/OS permission cannot be overridden by a one-use token.")
        self.set_permission(node_id, cap_id, PermissionState.GRANTED, user_confirmed=True, remember=False)
        self._once[(node_id, cap_id)] = (task_id, state)
        return self.kernel.permissions.controller.issue_one_use(task_id, cap_id, inputs)

    def permission_available(self, node_id, cap_id):
        return self.kernel.permissions.controller.state(f"node:{node_id}:{cap_id}") == PermissionState.GRANTED

    def connect(self, node_id, host=None, port=None):
        peer = self.store.get(node_id)
        if peer is None or peer.revoked:
            raise PermissionError("Device must be explicitly paired.")
        state = self.registry.nodes.get(node_id)
        host = host or (state.host if state else peer.descriptor.metadata.get("host"))
        port = port or (state.port if state else peer.descriptor.metadata.get("port"))
        if not host or not port:
            raise ValueError("Provide the current device address.")
        start = time.perf_counter()
        advertisement = self.transport.rpc(host, port, "hello", peer_id=node_id)
        state = self.registry.update(node_id, advertisement, host=host, port=port, latency_ms=(time.perf_counter() - start) * 1000)
        peer.descriptor = replace(peer.descriptor, metadata={**peer.descriptor.metadata, "host": host, "port": int(port)})
        grants = advertisement.get("granted_capabilities", list(peer.remote_capabilities))
        if not isinstance(grants, list) or len(grants) > 64 or any(v not in state.capabilities for v in grants):
            raise ValueError("Invalid remote grant advertisement.")
        peer.remote_capabilities = tuple(grants)
        self.store._save()
        self._register(state)
        from ..kernel import EventType,KernelEvent
        self.kernel.events.publish(KernelEvent(EventType.DEVICE_CHANGED,source="device_mesh",payload={"node_id":node_id,"type":"device_connected"}))
        return state

    def _register(self, state):
        node_id = state.node_id
        for cap_id in self._registered.get(node_id, ()):
            self.kernel.registry.unregister(cap_id, node_id)
        for resource, amount in state.resources.items():
            self.kernel.resources.register(ResourceDescriptor(resource, amount, node_id))
        self._registered[node_id] = tuple(state.capabilities)
        for cap_id, descriptor in state.capabilities.items():
            descriptor = replace(descriptor, required_permissions=(f"node:{node_id}:{cap_id}",))
            def handler(args, ctx, node_id=node_id, cap_id=cap_id):
                return self._execute(node_id, cap_id, args, ctx)
            def health(node_id=node_id, cap_id=cap_id):
                state = self.registry.nodes.get(node_id)
                available = self.enabled and state and state.connected and time.monotonic() - state.last_seen < 30
                return CapabilityHealth(state.capabilities[cap_id].status if available else Availability.UNAVAILABLE, "Device is offline" if not available else "")
            def verifier(result, expected, ctx):
                return result.verification or VerificationResult(VerificationStatus.INCONCLUSIVE)
            def permission_check(args, ctx, descriptor=descriptor):
                from ..unified_intelligence import PermissionDecision, RiskClass
                once = self._once.get((descriptor.node_id, descriptor.capability_id))
                if once and once[0] != ctx.task_id:
                    return PermissionDecision(False, reason="One-use device permission belongs to another action.")
                risk = RiskClass.HIGH if once else descriptor.risk_level
                if descriptor.capability_id in {"camera.stream", "microphone.stream", "screen.stream"} and args.get("op") != "start" and not once:
                    risk = RiskClass.LOW
                return self.kernel.permissions.controller.authorize(task_id=ctx.task_id,
                    capability_id=descriptor.capability_id, arguments=args,
                    permissions=descriptor.required_permissions, risk=risk, approval_token=ctx.approval_token)
            def completed(result, ctx, node_id=node_id, cap_id=cap_id):
                once = self._once.get((node_id, cap_id))
                if once and once[0] == ctx.task_id:
                    self._once.pop((node_id, cap_id), None)
                    self.kernel.permissions.controller.set_state(f"node:{node_id}:{cap_id}", once[1])
                    self._session_permissions.discard((node_id, cap_id))
            self.kernel.registry.register(descriptor, handler, verifier=verifier, health_check=health,
                                          permission_check=permission_check, on_completed=completed)
            if self.actions:
                def observe(spec, ctx, result=None, before=None, node_id=node_id):
                    command_id = ctx.task_id or spec.task_id
                    try:
                        value = self._rpc(node_id, "observe", {"command_id": command_id, "capability": spec.capability_id,
                            "inputs": ctx.metadata.get("task_inputs", {}), "expected": spec.expected_outcome})
                    except (OSError, ValueError):
                        return Observation(spec.action_id, "remote", {}, errors=("Remote observation unavailable.",))
                    state = value.get("observation")
                    if not isinstance(state, dict):
                        return Observation(spec.action_id, "remote", {}, errors=("No fresh independent remote observation.",))
                    return Observation(spec.action_id, "remote:" + node_id, {**state, "verified_remote": value.get("verification") == "verified"},
                                       evidence=("Authenticated remote observation for " + command_id,))
                def verify(spec, obs, before):
                    if not obs.state.get("verified_remote"):
                        return VerificationResult(VerificationStatus.INCONCLUSIVE, message="Remote kernel did not verify this action.")
                    return VerificationResult(VerificationStatus.VERIFIED, obs.evidence)
                self.actions.register(cap_id, ActionBinding(ActionMethod.APPLICATION_API,
                    lambda args, expected: {"verified_remote": True}, observe, verify), node_id=node_id)

    def _rpc(self, node_id, operation, payload=None, timeout=2):
        state = self.registry.nodes[node_id]
        value = self.transport.rpc(state.host, state.port, operation, payload, peer_id=node_id, timeout=timeout)
        state.last_seen, state.connected, state.reason = time.monotonic(), True, "Connected"
        return value

    def _execute(self, node_id, cap_id, args, ctx):
        command_id = identifier(ctx.task_id)
        peer = self.store.get(node_id)
        if peer is None or peer.revoked or not peer.remote_allows(cap_id):
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED, "Remote capability is not authorized.")
        ttl = max(.05, min(60, (ctx.deadline or time.monotonic() + 30) - time.monotonic()))
        payload = {"command_id": command_id, "capability": cap_id, "inputs": args, "ttl": ttl}
        expected = ctx.metadata.get("expected_outcome")
        if expected is not None:
            payload["expected"] = expected
        with self._lock:
            if len(self._commands) >= 900:
                for old_id, old in list(self._commands.items()):
                    if old["state"] in {"verified", "failed", "cancelled"} and old["capability"] in {"file.receive", "file.send", "device.status", "python.calculate", "project.inspect"}:
                        self._commands.pop(old_id)
                        if len(self._commands) < 900:
                            break
            if len(self._commands) >= 1000 and command_id not in self._commands:
                return ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE, "Mesh command admission limit reached.")
            self._commands[command_id] = {"node_id": node_id, "capability": cap_id, "state": "sent",
                                          "stream_start": cap_id.endswith(".stream") and args.get("op") == "start"}
        try:
            value = self._rpc(node_id, "submit", payload)
        except (OSError, ValueError):
            self._commands[command_id]["state"] = "unknown"
            self._retain(ctx, node_id, command_id, ttl)
            return ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, "Connection lost; action status requires reconciliation before any retry.")
        while value.get("state") in {"acknowledged", "queued", "executing", "observing"}:
            if ctx.cancellation_token.cancelled or time.monotonic() >= ctx.deadline:
                try:
                    self._rpc(node_id, "cancel", {"command_id": command_id}, timeout=.5)
                    until = time.monotonic() + .7
                    while time.monotonic() < until:
                        state = self._rpc(node_id, "status", {"command_id": command_id}, timeout=.2)
                        if not state.get("physical_active", True):
                            break
                        time.sleep(.02)
                    else:
                        self._retain(ctx, node_id, command_id, ttl)
                except OSError:
                    self._retain(ctx, node_id, command_id, ttl)
                return ExecutionResult.failure(ErrorCode.CANCELLED if ctx.cancellation_token.cancelled else ErrorCode.TIMEOUT, "Remote cancellation requested; status must confirm physical cleanup.")
            ctx.cancellation_token.wait(.03)
            try:
                value = self._rpc(node_id, "status", {"command_id": command_id}, timeout=min(2, max(.01, ctx.deadline - time.monotonic())))
            except (OSError, ValueError):
                self._commands[command_id]["state"] = "unknown"
                self._retain(ctx, node_id, command_id, ttl)
                return ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, "Remote action outcome is unknown; no mutation was replayed.")
        self._commands[command_id]["state"] = value.get("state", "unknown")
        raw = value.get("result")
        if not isinstance(raw, dict):
            return ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, value.get("error", "Remote action has no completed execution evidence."))
        result = ExecutionResult.from_dict(raw)
        if result.task_id != command_id or result.capability_id != cap_id:
            raise ValueError("Remote execution identity mismatch.")
        if not result.verification or result.verification.status != VerificationStatus.VERIFIED:
            result.success, result.status = False, TaskStatus.FAILED
        result.retryable = False  # Disconnect never causes a mutating replay.
        if value.get("physical_active", False):
            self._retain(ctx, node_id, command_id, ttl)
        self.audit.append({"node_id": node_id, "request_id": command_id, "capability": cap_id,
                           "state": value["state"], "timestamp": time.time()})
        return result

    def prepare_task(self, task, context=None):
        self.router.prepare(task, context)

    def _retain(self, context, node_id, command_id, ttl):
        owner = context.metadata.get("execution_id")
        if owner:
            self._remote_leases[owner] = (node_id, command_id, time.monotonic() + ttl + 5)

    def lease_retained(self, owner):
        return owner in self._remote_leases

    def reconcile_leases(self):
        for owner, (node_id, command_id, expiry) in list(self._remote_leases.items()):
            stopped = False
            try:
                value = self._rpc(node_id, "status", {"command_id": command_id}, timeout=.5)
                stopped = value.get("physical_active") is False
            except (OSError, ValueError, KeyError):
                pass
            if stopped or time.monotonic() >= expiry:
                if not stopped:
                    state = self.registry.nodes[node_id]
                    state.connected, state.reason = False, "Offline; execution cleanup unconfirmed"
                    for resource, amount in state.resources.items():
                        self.kernel.resources.register(ResourceDescriptor(resource, amount, node_id, available=False))
                self.kernel.resources.release(owner)
                self._remote_leases.pop(owner, None)

    def dispatch(self, cap_id, inputs, node_id, context=None, *, expected=None, task_id=None):
        task = TaskNode(cap_id, inputs, task_id=task_id or uuid.uuid4().hex, constraints={"node_id": node_id},
                        verification_policy=VerificationPolicy(True, expected))
        context = context or ExecutionContext()
        return self.kernel.run_task(task, replace(context, metadata={**context.metadata, "mesh_expected": expected}))

    def reconcile(self, task, context=None):
        if not self.actions:
            return ExecutionResult.failure(ErrorCode.DEPENDENCY_MISSING, "Phase 3 observer is required.")
        return self.actions.reconcile(task, context or ExecutionContext())

    def group_graph(self, group_id, cap_id, inputs, *, expected=None):
        group = self.registry.groups[group_id]
        return TaskGraph([TaskNode(cap_id, dict(inputs), constraints={"node_id": member},
                         verification_policy=VerificationPolicy(True, expected)) for member in group["members"]],
                         goal="Apply " + cap_id + " to " + group["name"])

    def send_file(self, source, node_id, *, name=None, transfer_id=None, context=None, progress=None):
        source = Path(source).resolve()
        if not source.is_file() or source.stat().st_size > self.node.inbox.max_bytes:
            raise ValueError("Source file is unavailable or exceeds the transfer limit.")
        context = context or ExecutionContext()
        from ..unified_intelligence import RiskClass
        decision = self.kernel.permissions.controller.authorize(task_id=context.task_id or "mesh-file-source",
            capability_id="file.send", arguments={"path": str(source)}, permissions=("file_read",), risk=RiskClass.LOW)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        transfer_id = transfer_id or uuid.uuid4().hex
        digest, size = file_hash(source), source.stat().st_size
        def run(arguments):
            if context.cancellation_token and context.cancellation_token.cancelled:
                raise InterruptedError("File transfer cancelled.")
            result = self.dispatch("file.receive", {"transfer_id": transfer_id, **arguments}, node_id, context)
            if not result.success:
                raise RuntimeError("Verified transfer operation failed: " + "; ".join(e.message for e in result.errors))
            return result.output
        info = run({"op": "begin", "name": name or source.name, "size": size, "sha256": digest})
        offset = info.get("offset", 0)
        if info.get("complete"):
            return info
        try:
            with source.open("rb") as stream:
                stream.seek(offset)
                while chunk := stream.read(CHUNK_BYTES):
                    run({"op": "chunk", "offset": offset, "data": base64.b64encode(chunk).decode()})
                    offset += len(chunk)
                    if progress:
                        progress(offset, size)
            info = run({"op": "finish"})
            if not info.get("complete") or info.get("sha256") != digest or info.get("size") != size:
                raise ValueError("Remote final file integrity proof differs from source.")
            return info
        except InterruptedError:
            try:
                self.dispatch("file.receive", {"transfer_id": transfer_id, "op": "cancel"}, node_id)
            finally:
                raise

    def receive_file(self, name, node_id, *, local_name=None, transfer_id=None, context=None):
        """Pull only from the remote shared Inbox into this node's shared Inbox."""
        context = context or ExecutionContext()
        transfer_id = transfer_id or uuid.uuid4().hex
        info = self.dispatch("file.send", {"op": "stat", "name": name}, node_id, context)
        if not info.success:
            raise PermissionError("Remote shared file could not be read/verified.")
        metadata = info.output
        def local(arguments):
            result = self.kernel.dispatch("file.receive", {"transfer_id": transfer_id, **arguments}, context)
            if not result.success:
                raise ValueError("Local Inbox transfer failed verification.")
            return result.output
        state = local({"op": "begin", "name": local_name or Path(name).name, "size": metadata["size"], "sha256": metadata["sha256"]})
        if state.get("complete"):
            return state
        offset = state["offset"]
        while offset < metadata["size"]:
            result = self.dispatch("file.send", {"op": "read", "name": name, "offset": offset}, node_id, context)
            if not result.success:
                raise ValueError("Remote file range could not be verified; partial retained for explicit resume.")
            data = base64.b64decode(result.output["data"], validate=True)
            if not data or hashlib.sha256(data).hexdigest() != result.output["sha256"]:
                raise ValueError("Remote chunk integrity failed.")
            local({"op": "chunk", "offset": offset, "data": result.output["data"]})
            offset += len(data)
        state = local({"op": "finish"})
        if not state.get("complete") or state["sha256"] != metadata["sha256"]:
            raise ValueError("Pulled file final hash failed.")
        return state

    def queue_safe(self, node_id, cap_id, inputs, *, ttl, user_confirmed=False):
        if not user_confirmed or cap_id not in {"device.status"} or isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not 0 < ttl <= 60 or len(self._queue) >= 32:
            raise ValueError("Only explicitly queued, bounded, read-only status requests are supported.")
        key = uuid.uuid4().hex
        self._queue[key] = (time.monotonic() + ttl, node_id, cap_id, dict(inputs))
        return key

    def cancel_queued(self, request_id):
        return self._queue.pop(identifier(request_id), None) is not None

    def drain_queue(self):
        result = {}
        for key, (expiry, node_id, cap_id, inputs) in list(self._queue.items()):
            if time.monotonic() >= expiry:
                self._queue.pop(key); result[key] = "expired"
            elif self.registry.nodes.get(node_id) and self.registry.nodes[node_id].connected:
                self._queue.pop(key); result[key] = self.dispatch(cap_id, inputs, node_id).to_dict()
        return result

    def _heartbeat_loop(self):
        while not self._stop.wait(5):
            for node_id, state in tuple(self.registry.nodes.items()):
                if self._stop.is_set():
                    break
                peer = self.store.get(node_id)
                if peer is None or peer.revoked or not state.host or not state.port:
                    continue
                try:
                    if not state.connected:
                        self.connect(node_id)
                    else:
                        start = time.perf_counter()
                        self._rpc(node_id, "ping")
                        state.latency_ms = (state.latency_ms or 0) * .8 + (time.perf_counter() - start) * 200
                except (OSError, ValueError, KeyError):
                    was_connected = state.connected
                    state.connected, state.reason = False, "Offline"
                    self._reset_session(node_id)
                    if was_connected:
                        from ..kernel import EventType,KernelEvent
                        self.kernel.events.publish(KernelEvent(EventType.DEVICE_CHANGED,source="device_mesh",payload={"node_id":node_id,"type":"device_disconnected"}))
            self.node.expire()
            self.reconcile_leases()

    def _reset_session(self, node_id):
        for peer, cap_id in tuple(self._session_permissions):
            if peer == node_id:
                remembered = self.registry.permissions.get(peer + "|" + cap_id, PermissionState.ASK.value)
                self.kernel.permissions.controller.set_state(f"node:{peer}:{cap_id}", remembered)
                self._session_permissions.discard((peer, cap_id))
                self._once.pop((peer, cap_id), None)

    def _stop_remote_sources(self, node_id, cap_id=None, *, deadline=None):
        if not self.enabled:
            return
        deadline = deadline or time.monotonic() + 2
        stopped = set()
        for command_id, command in reversed(tuple(self._commands.items())):
            cap = command["capability"]
            remaining = deadline - time.monotonic()
            if remaining <= .01:
                break
            if command["node_id"] == node_id and command.get("stream_start") and cap not in stopped and (cap_id is None or cap_id == cap):
                stopped.add(cap)
                try:
                    self._rpc(node_id, "cancel", {"command_id": command_id}, timeout=min(.5, remaining))
                except (OSError, ValueError, KeyError):
                    self.audit.append({"node_id": node_id, "capability": cap, "state": "source_cleanup_unconfirmed"})
                if cap_id is not None:
                    break

    def revoke(self, node_id, *, remove=False):
        self._stop_remote_sources(node_id)
        self.transport.revoke(node_id)
        self.node.disconnect(node_id)
        self._reset_session(node_id)
        for key, queued in tuple(self._queue.items()):
            if queued[1] == node_id:
                self._queue.pop(key, None)
        if self.streams:
            self.streams.disconnect(node_id)
        state = self.registry.nodes.get(node_id)
        if state:
            state.connected, state.reason = False, "Revoked"
        from ..kernel import EventType,KernelEvent
        self.kernel.events.publish(KernelEvent(EventType.DEVICE_CHANGED,source="device_mesh",payload={"node_id":node_id,"type":"device_revoked"}))
        if remove:
            self.registry.remove(node_id)

    def rename(self, node_id, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ValueError("Invalid device name.")
        peer = self.store.get(node_id)
        if peer is None or peer.revoked:
            raise ValueError("Select a paired device before renaming it.")
        peer.descriptor = replace(peer.descriptor, device_name=name.strip())
        self.store._save()

    def register_stream(self, cap_id, factory, *, resource, available, permission):
        self.streams.register_source(cap_id, factory, resource=resource, available=available, permission=permission)
        from ..unified_intelligence import RiskClass
        self.node.register(cap_id, lambda args, ctx: self.streams.operate(cap_id, args, ctx),
            lambda args, ctx: self.streams.observe(cap_id, args, ctx), permissions=(permission,), risk=RiskClass.HIGH)
        from ..kernel.registry import CapabilityHealth
        entry = self.kernel.registry.lookup(cap_id)
        def permission_check(args, ctx):
            from ..unified_intelligence import RiskClass
            return self.kernel.permissions.controller.authorize(task_id=ctx.task_id, capability_id=cap_id,
                arguments=args, permissions=(permission, *ctx.permissions),
                risk=RiskClass.HIGH if args.get("op") == "start" else RiskClass.LOW, approval_token=ctx.approval_token)
        self.kernel.registry.extend(cap_id, permission_check=permission_check,
            health_check=lambda: CapabilityHealth(Availability.AVAILABLE if available() else Availability.UNAVAILABLE))

    def consume_sample(self, result, consumer):
        """A selected live-vision/voice adapter consumes bytes; no recording or new model."""
        if not result.success or not isinstance(result.output, dict) or not result.output.get("sample_ready"):
            return False
        data = base64.b64decode(result.output["data"], validate=True)
        if len(data) > 128 * 1024 or hashlib.sha256(data).hexdigest() != result.output.get("sha256"):
            raise ValueError("Stream sample integrity failed.")
        consumer(data)
        return True

    def discover(self, timeout=1):
        # Existing bounded LAN discovery advertises metadata only; no trust mutations.
        for value in LanDiscovery.discover(timeout=min(2, timeout)):
            descriptor = NodeDescriptor.from_dict(value.get("descriptor", value))
            self.registry.discover(descriptor, value.get("host", ""), value.get("port", 0))
        return self.registry.snapshot()

    def snapshot(self):
        return {"enabled": self.enabled, "protocol": VERSION, "nodes": self.registry.snapshot(),
                "groups": self.registry.groups, "active_commands": sum(c["state"] in {"sent", "executing", "unknown"} for c in self._commands.values()),
                "streams": self.streams.snapshot() if self.streams else []}
