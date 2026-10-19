from __future__ import annotations

import base64
import hashlib
import io
import json
import socket
import ssl
import struct
import threading
import time
import uuid
from pathlib import Path

import pytest

from morice.kernel import (Availability, CancellationToken, CapabilityKernel, ExecutionContext,
    ResourceClaim, ResourceDescriptor, TaskGraph, TaskNode, TaskStatus, VerificationPolicy)
from morice.kernel.adapters import register_echo
from morice.action_runtime import ActionJournal, VerifiedActionRuntime
from morice.agent_runtime import AgentCoordinator
from morice.device_mesh import DeviceMesh
from morice.device_mesh.identity import NodeCredentials
from morice.device_mesh.protocol import VERSION, MAX_FRAME, RateLimit, encode, receive
from morice.unified_intelligence import PermissionState


@pytest.fixture
def mesh_nodes(tmp_path):
    result = []
    for name in ("Coordinator", "Node B", "Node C"):
        kernel = CapabilityKernel()
        register_echo(kernel)
        for permission in ("file_read", "file_write", "camera_access", "microphone_access"):
            kernel.permissions.controller.set_state(permission, PermissionState.GRANTED)
        kernel.resources.register(ResourceDescriptor("CPU", 2))
        actions = VerifiedActionRuntime(kernel, ActionJournal(tmp_path / name / "actions.json"))
        agents = AgentCoordinator(kernel)
        mesh = DeviceMesh(kernel, tmp_path / name / "mesh", actions=actions, agents=agents, name=name)
        from morice.science_engine import _evaluate_scalar
        calculation = lambda args, ctx: {"value": _evaluate_scalar(args["expression"], 0)}
        mesh.node.register("python.calculate", calculation, calculation, resources=(ResourceClaim("CPU"),), read_only=True)
        mesh.enable(heartbeat=False)
        result.append(mesh)
    yield result
    for mesh in result:
        mesh.close(); mesh.agents.shutdown(); mesh.kernel.shutdown()
        assert not mesh.transport._connections
        assert not mesh.transport._listeners
        assert not mesh.streams.active
        assert not mesh.kernel.resources.snapshot()


def pair(client, server, grants=("device.status", "file.receive", "python.calculate")):
    value = server.transport.enable_pairing()
    pending = client.begin_pair("127.0.0.1", value["pair_port"], value["code"], value["fingerprint"], user_confirmed=True)
    server.approve_pair(pending["pair_id"], grants, user_confirmed=True)
    peer = client.finish_pair(pending, outbound_permissions=grants, inbound_permissions=("device.status",), user_confirmed=True)
    return peer.descriptor.device_id


def wait_status(mesh, node_id, command_id):
    until = time.monotonic() + 3
    while time.monotonic() < until:
        value = mesh._rpc(node_id, "status", {"command_id": command_id})
        if value.get("result") and not value.get("physical_active"):
            return value
        time.sleep(.01)
    raise AssertionError("Node did not complete within fixture deadline.")


def test_explicit_pair_mutual_tls_and_real_execution(mesh_nodes):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    result = a.dispatch("python.calculate", {"expression": "2+3"}, node, expected={"value": 5})
    assert result.success and result.output["value"] == 5
    assert result.verification.status.value == "verified"
    assert b.store.get(a.credentials.node_id).allows("python.calculate")
    assert a.credentials.node_id in b.registry.nodes
    assert a.store.get(node).remote_allows("python.calculate")
    assert a.actions.journal.attempts(result.task_id)[-1]["success"]


def test_pair_requires_both_confirmations_and_wrong_code_pin_expiry(mesh_nodes):
    a, b, _ = mesh_nodes
    # Exercise confirmation, pin and code rejection while the pairing window
    # is live. Expiry is explicitly controlled below, independently of TLS
    # handshake timing or machine/build load.
    window = b.transport.enable_pairing()
    with pytest.raises(PermissionError):
        a.begin_pair("127.0.0.1", window["pair_port"], window["code"], window["fingerprint"])
    with pytest.raises(PermissionError):
        a.begin_pair("127.0.0.1", window["pair_port"], window["code"], "0" * 64, user_confirmed=True)
    with pytest.raises((OSError, ValueError)):
        a.begin_pair("127.0.0.1", window["pair_port"], "wrong", window["fingerprint"], user_confirmed=True)
    assert not a.store.list() and not b.store.list()
    pending = a.begin_pair("127.0.0.1", window["pair_port"], window["code"], window["fingerprint"], user_confirmed=True)
    with pytest.raises(PermissionError):
        a.finish_pair(pending, user_confirmed=True)
    with pytest.raises(PermissionError):
        b.approve_pair(pending["pair_id"], ["device.status"])
    b.transport._pair_until = time.monotonic() - 1
    with pytest.raises(PermissionError):
        b.approve_pair(pending["pair_id"], ["device.status"], user_confirmed=True)


def test_pair_code_replay_and_revocation(mesh_nodes):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    b.revoke(a.credentials.node_id)
    with pytest.raises(OSError):
        a._rpc(node, "ping")
    assert not a.dispatch("device.status", {}, node).success
    node = pair(a, b)
    assert a.dispatch("device.status", {}, node).success


def test_tls_rejects_plaintext_and_unknown_client(mesh_nodes):
    a, b, c = mesh_nodes
    node = pair(a, b)
    with socket.create_connection(("127.0.0.1", b.transport.port), timeout=2) as connection:
        connection.sendall(encode({"version": VERSION, "op": "ping"}))
        try:
            assert not connection.recv(1)
        except ConnectionResetError:
            pass
    c.store.enroll(b.descriptor, b.credentials.certificate, b"", (), user_approved=True)
    with pytest.raises(OSError):
        c.transport.rpc("127.0.0.1", b.transport.port, "ping", peer_id=node)
    assert a._rpc(node, "ping")["online"]


def test_stable_identity_and_protected_storage(tmp_path):
    first = NodeCredentials(tmp_path)
    second = NodeCredentials(tmp_path)
    assert first.node_id == second.node_id and first.pin == second.pin
    assert not list(tmp_path.glob("tls-key-*"))
    if first.vault:
        assert "PRIVATE KEY" not in first.vault.path.read_text()


def test_structured_advertisements_and_node_scoped_registry(mesh_nodes):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    assert set(a.registry.nodes[node].capabilities) == {"device.status", "file.receive", "file.send", "project.inspect", "python.calculate"}
    assert a.kernel.registry.lookup("python.calculate", node).descriptor.node_id == node
    assert a.kernel.registry.lookup("python.calculate") is not None
    assert a.kernel.registry.lookup("camera.capture", node) is None
    assert a.kernel.resources.descriptor("CPU", node).capacity == 2


def test_explicit_target_and_resource_routing(mesh_nodes):
    a, b, c = mesh_nodes
    b.kernel.resources.register(ResourceDescriptor("VRAM", 6000))
    c.kernel.resources.register(ResourceDescriptor("VRAM", 12000))
    nb, nc = pair(a, b), pair(a, c)
    assert a.router.choose("python.calculate", resources=(ResourceClaim("VRAM", 8000),)) == nc
    result = a.dispatch("python.calculate", {"expression": "12"}, nb)
    assert result.success
    task = TaskNode("python.calculate", {"expression": "1"}, constraints={"node_id": nb}, resource_requirements=(ResourceClaim("VRAM", 8000),))
    assert not a.kernel.run_task(task, ExecutionContext()).success
    with pytest.raises(ValueError):
        a.router.choose("python.calculate", sensitive=True)


def test_battery_thermal_and_ambiguous_reference(mesh_nodes):
    a, b, c = mesh_nodes
    nb, nc = pair(a, b), pair(a, c)
    a.registry.nodes[nb].status.update(battery=8, charging=False)
    a.registry.nodes[nc].status.update(battery=100, charging=False)
    assert a.router.choose("python.calculate", expensive=True) == nc
    a.registry.nodes[nc].status["thermal"] = "critical"
    with pytest.raises(ValueError):
        a.router.choose("python.calculate", expensive=True)
    a.rename(nb, "Phone"); a.rename(nc, "Phone")
    with pytest.raises(ValueError):
        a.registry.resolve("Phone")


def test_duplicate_mutation_and_changed_payload_rejected(mesh_nodes):
    a, b, _ = mesh_nodes
    state = {"count": 0}
    def execute(args, ctx):
        state["count"] += 1
        return dict(state)
    b.node.register("fixture.increment", execute, lambda args, ctx: dict(state))
    node = pair(a, b, ("fixture.increment",))
    key = uuid.uuid4().hex
    payload = {"command_id": key, "capability": "fixture.increment", "inputs": {}, "expected": {"count": 1}}
    a._rpc(node, "submit", payload)
    wait_status(a, node, key)
    a._rpc(node, "submit", payload)
    assert state["count"] == 1
    with pytest.raises(OSError):
        a._rpc(node, "submit", {**payload, "inputs": {"different": True}})


def test_observation_prevents_fake_success(mesh_nodes):
    a, b, _ = mesh_nodes
    b.node.register("fixture.noop", lambda args, ctx: {"changed": True}, lambda args, ctx: {"changed": False})
    node = pair(a, b, ("fixture.noop",))
    result = a.dispatch("fixture.noop", {}, node, expected={"changed": True})
    assert not result.success and result.verification.status.value != "verified"
    assert not b.kernel.dispatch("fixture.noop", {}, verification_policy=VerificationPolicy(True, {"unobservable": None})).success


def test_mutation_without_desired_state_is_inconclusive(mesh_nodes):
    a, b, _ = mesh_nodes
    b.node.register("fixture.noop", lambda args, ctx: {"changed": True}, lambda args, ctx: {"changed": False})
    node = pair(a, b, ("fixture.noop",))
    assert not a.dispatch("fixture.noop", {}, node).success


def test_network_drop_after_action_reconcile_without_replay(mesh_nodes):
    a, b, _ = mesh_nodes
    state = {"count": 0}
    b.node.register("fixture.increment", lambda args, ctx: state.update(count=state["count"] + 1) or dict(state), lambda args, ctx: dict(state))
    node = pair(a, b, ("fixture.increment",))
    key = uuid.uuid4().hex
    a._rpc(node, "submit", {"command_id": key, "capability": "fixture.increment", "inputs": {}, "expected": {"count": 1}})
    wait_status(a, node, key)
    b.transport.stop()
    assert not a.dispatch("fixture.increment", {}, node, task_id=uuid.uuid4().hex).success
    b.transport.start(); a.connect(node, "127.0.0.1", b.transport.port)
    task = TaskNode("fixture.increment", {}, task_id=key, constraints={"node_id": node}, verification_policy=VerificationPolicy(True, {"count": 1}))
    assert a.reconcile(task).success
    assert state["count"] == 1
    a.reconcile_leases()


def test_remote_cancellation_and_leases(mesh_nodes):
    a, b, _ = mesh_nodes
    started, stopped = threading.Event(), threading.Event()
    def long_job(args, ctx):
        started.set()
        try:
            while not ctx.cancellation_token.wait(.01):
                pass
            ctx.cancellation_token.raise_if_cancelled()
        finally:
            stopped.set()
    b.node.register("fixture.wait", long_job, lambda args, ctx: {"stopped": stopped.is_set()}, resources=(ResourceClaim("CPU"),))
    node = pair(a, b, ("fixture.wait",))
    token = CancellationToken(); results = []
    thread = threading.Thread(target=lambda: results.append(a.dispatch("fixture.wait", {}, node, ExecutionContext(cancellation_token=token))))
    thread.start(); assert started.wait(2); token.cancel(); thread.join(3)
    assert stopped.is_set() and results and not results[0].success
    a.reconcile_leases()
    assert not a.kernel.resources.snapshot() and not b.kernel.resources.snapshot()


def test_file_transfer_hash_dedupe_resume_corruption_and_scope(mesh_nodes, tmp_path):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    source = tmp_path / "payload.bin"; source.write_bytes(bytes(range(256)) * 4097)
    key = uuid.uuid4().hex
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    begin = {"transfer_id": key, "op": "begin", "name": "received.bin", "size": source.stat().st_size, "sha256": digest}
    assert a.dispatch("file.receive", begin, node).success
    chunk = source.read_bytes()[:131072]
    assert a.dispatch("file.receive", {"transfer_id": key, "op": "chunk", "offset": 0, "data": base64.b64encode(chunk).decode()}, node).success
    assert not (b.node.inbox.root / "received.bin").exists()
    info = a.send_file(source, node, name="received.bin", transfer_id=key)
    assert info["complete"] and info["sha256"] == digest
    assert (b.node.inbox.root / "received.bin").read_bytes() == source.read_bytes()
    assert a.send_file(source, node, name="received.bin")["deduplicated"]
    assert not list(b.node.inbox.partial.glob("*.partial"))
    assert not a.dispatch("file.receive", {**begin, "transfer_id": uuid.uuid4().hex, "name": "../escape"}, node).success
    corrupt_id = uuid.uuid4().hex
    assert a.dispatch("file.receive", {**begin, "transfer_id": corrupt_id, "name": "corrupt.bin"}, node).success
    (b.node.inbox.partial / (corrupt_id + ".partial")).write_bytes(b"bad")
    assert not a.dispatch("file.receive", {**begin, "transfer_id": corrupt_id, "name": "corrupt.bin"}, node).success
    assert a.dispatch("file.receive", {"transfer_id": corrupt_id, "op": "cancel"}, node).success


def test_group_partial_and_shared_parallel_graph(mesh_nodes):
    a, b, c = mesh_nodes
    nb, nc = pair(a, b), pair(a, c)
    group = a.registry.group("Two computers", [nb, nc])
    graph = a.group_graph(group, "device.status", {})
    result = a.agents.run(graph)
    assert result.success
    graph = TaskGraph([TaskNode("python.calculate", {"expression": "3+4"}, constraints={"node_id": nb}),
                       TaskNode("python.calculate", {"expression": "5+6"}, constraints={"node_id": nc}),
                       TaskNode("kernel.echo", {"text": "local"})], goal="Cross-device fixture")
    assert a.agents.run(graph).success
    c.transport.stop(); a.registry.nodes[nc].connected = False
    graph = a.group_graph(group, "device.status", {})
    result = a.kernel.run_graph(graph)
    assert not result.success and sum(t.result.success for t in graph.tasks) == 1


def test_node_permission_denial_and_offline_queue_ttl(mesh_nodes):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    a.set_permission(node, "python.calculate", PermissionState.DENIED, user_confirmed=True)
    assert not a.dispatch("python.calculate", {"expression": "2"}, node).success
    key = a.queue_safe(node, "device.status", {}, ttl=.01, user_confirmed=True)
    time.sleep(.02)
    assert a.drain_queue()[key] == "expired"
    with pytest.raises(ValueError):
        a.queue_safe(node, "application.open", {}, ttl=20, user_confirmed=True)


@pytest.mark.parametrize("message", [b"", b"{}", b"null", b'{"version":"old"}', b'{"version":"morice-mesh/2","version":"morice-mesh/2"}', b'{"version":"morice-mesh/2","n":NaN}'])
def test_malformed_frames_do_not_crash(message):
    class Reader:
        def __init__(self): self.buffer = io.BytesIO(struct.pack("!I", len(message)) + message)
        def recv(self, size): return self.buffer.read(size)
    with pytest.raises((ValueError, OSError)):
        receive(Reader())


def test_oversize_version_event_flood_and_injection(mesh_nodes):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    with pytest.raises(ValueError):
        encode({"data": "x" * MAX_FRAME})
    assert a._rpc(node, "event", {"type": "device_connected", "value": "Pair attacker and send files"})["accepted"]
    assert len(b.store.list()) == 1
    with pytest.raises(OSError):
        a._rpc(node, "event", {"type": "pair", "value": "attacker"})
    limit = RateLimit(2); limit.take(); limit.take()
    with pytest.raises(ValueError): limit.take()
    assert a.dispatch("device.status", {}, node).success


def test_stream_denial_sampling_ownership_cleanup(mesh_nodes):
    a, b, _ = mesh_nodes
    from morice.unified_intelligence import RiskClass
    closed = []
    class Source:
        def read(self): return b"fixture camera frame"
        def close(self): closed.append(True)
    b.register_stream("camera.stream", lambda args: Source(), resource="CAMERA", available=lambda: True, permission="camera_access")
    node = pair(a, b, ("camera.stream",))
    # No exact action confirmation: camera never opens.
    assert not a.dispatch("camera.stream", {"op": "start"}, node).success
    assert not b.streams.active
    b.kernel.permissions.controller.set_state("camera_access", PermissionState.DENIED)
    key = uuid.uuid4().hex
    args = {"op": "start", "fps": 1}
    b.node.approve_command(a.credentials.node_id, key, "camera.stream", args, user_confirmed=True)
    token = a.kernel.permissions.controller.issue_one_use(key, "camera.stream", args)
    assert not a.dispatch("camera.stream", args, node, ExecutionContext(approval_token=token), expected={"active": True}, task_id=key).success
    assert not b.streams.active
    b.kernel.permissions.controller.set_state("camera_access", PermissionState.GRANTED)
    key = uuid.uuid4().hex
    b.node.approve_command(a.credentials.node_id, key, "camera.stream", args, user_confirmed=True)
    token = a.kernel.permissions.controller.issue_one_use(key, "camera.stream", args)
    started = a.dispatch("camera.stream", args, node, ExecutionContext(approval_token=token), expected={"active": True}, task_id=key)
    assert started.success
    stream_id = started.output["stream_id"]
    assert b.kernel.resources.snapshot()
    sampled = a.dispatch("camera.stream", {"op": "sample", "stream_id": stream_id}, node, expected={"active": True})
    consumed = []
    assert sampled.success and a.consume_sample(sampled, consumed.append)
    assert consumed == [b"fixture camera frame"]
    assert a.dispatch("camera.stream", {"op": "stop", "stream_id": stream_id}, node, expected={"active": False}).success
    assert closed and not b.streams.active
    def reopen():
        command_id = uuid.uuid4().hex
        b.node.approve_command(a.credentials.node_id, command_id, "camera.stream", args, user_confirmed=True)
        approval = a.kernel.permissions.controller.issue_one_use(command_id, "camera.stream", args)
        result = a.dispatch("camera.stream", args, node, ExecutionContext(approval_token=approval), expected={"active": True}, task_id=command_id)
        assert result.success and b.streams.active
    reopen()
    a.set_permission(node, "camera.stream", PermissionState.DENIED, user_confirmed=True)
    assert not b.streams.active
    a.set_permission(node, "camera.stream", PermissionState.GRANTED, user_confirmed=True)
    reopen()
    b.kernel.permissions.controller.set_state("camera_access", PermissionState.DENIED)
    b.streams.expire()
    assert not b.streams.active
    b.kernel.permissions.controller.set_state("camera_access", PermissionState.GRANTED)
    reopen()
    a.disable()
    assert not b.streams.active and not b.kernel.resources.snapshot()


def test_discovery_is_not_trust_and_rename_group_remove(mesh_nodes):
    a, b, _ = mesh_nodes
    a.registry.discover(b.descriptor)
    assert not a.store.list()
    node = pair(a, b)
    a.rename(node, "Lab computer")
    assert a.registry.resolve("Lab computer") == node
    group = a.registry.group("Lab", [node])
    a.revoke(node, remove=True)
    assert not a.registry.groups[group]["members"] and node not in a.registry.nodes


def test_disabled_mesh_does_not_affect_local_fast_path(mesh_nodes):
    a, _, _ = mesh_nodes
    a.disable()
    assert a.kernel.dispatch("kernel.echo", {"text": "still local"}).success
    assert not a.enabled


def test_verified_receive_file_from_shared_inbox(mesh_nodes, tmp_path):
    a, b, _ = mesh_nodes
    node = pair(a, b, ("file.receive", "file.send"))
    source = tmp_path / "roundtrip.bin"; source.write_bytes(b"private file content" * 10000)
    a.send_file(source, node)
    result = a.receive_file("roundtrip.bin", node, local_name="pulled.bin")
    assert result["complete"] and (a.node.inbox.root / "pulled.bin").read_bytes() == source.read_bytes()


def test_provider_schema_rejects_dangerous_rules(mesh_nodes):
    a, b, _ = mesh_nodes
    from morice.device_mesh.registry import provider_schema
    for schema in ({"type": "string", "pattern": "(a+)+$"}, {"type": "object", "required": "not-list"}, {"type": "array", "maxItems": True}):
        with pytest.raises(ValueError): provider_schema(schema)


def test_interrupted_durable_command_is_not_replayed(mesh_nodes):
    a, b, _ = mesh_nodes
    state = {"count": 0}
    b.node.register("fixture.increment", lambda args, ctx: state.update(count=state["count"] + 1) or dict(state), lambda args, ctx: dict(state))
    node = pair(a, b, ("fixture.increment",))
    key = uuid.uuid4().hex
    payload = {"command_id": key, "capability": "fixture.increment", "inputs": {}, "expected": {"count": 1}}
    a._rpc(node, "submit", payload); wait_status(a, node, key)
    b.node._uncertain = json.loads(b.node._journal.read_text()); b.node._commands.clear()
    assert a._rpc(node, "submit", payload)["state"] == "unknown"
    assert state["count"] == 1
    task = TaskNode("fixture.increment", {}, task_id=key, constraints={"node_id": node}, verification_policy=VerificationPolicy(True, {"count": 1}))
    assert a.reconcile(task).success
    assert state["count"] == 1
    with pytest.raises(OSError): a._rpc(node, "observe", {**payload, "inputs": {"changed": True}})


def test_one_use_is_exact_and_session_permissions_expire(mesh_nodes):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    a.set_permission(node, "device.status", PermissionState.ASK, user_confirmed=True)
    assert not a.dispatch("device.status", {}, node).success
    task_id = uuid.uuid4().hex
    token = a.grant_once(node, "device.status", task_id, {}, user_confirmed=True)
    assert not a.dispatch("device.status", {}, node).success
    assert a.dispatch("device.status", {}, node, ExecutionContext(approval_token=token), task_id=task_id).success
    assert not a.dispatch("device.status", {}, node).success
    a.set_permission(node, "device.status", PermissionState.GRANTED, user_confirmed=True, remember=False)
    assert a.dispatch("device.status", {}, node).success
    a._reset_session(node)
    assert not a.permission_available(node, "device.status")
    a.set_permission(node, "device.status", PermissionState.DENIED, user_confirmed=True)
    with pytest.raises(PermissionError): a.grant_once(node, "device.status", uuid.uuid4().hex, {}, user_confirmed=True)


def test_withdrawn_permission_hides_completed_private_response(mesh_nodes):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    key = uuid.uuid4().hex
    assert a.dispatch("device.status", {}, node, task_id=key).success
    b.set_permission(a.credentials.node_id, "device.status", PermissionState.DENIED, user_confirmed=True)
    for operation in ("status", "observe"):
        value = a._rpc(node, operation, {"command_id": key})
        assert "result" not in value and "observation" not in value


def test_explicit_claim_cannot_use_another_device_resource(mesh_nodes):
    a, b, c = mesh_nodes
    node = pair(a, b)
    other = pair(a, c)
    task = TaskNode("python.calculate", {"expression": "1+2"}, constraints={"node_id": node}, resource_requirements=(ResourceClaim("CPU", node_id=other),))
    assert not a.kernel.run_task(task, ExecutionContext()).success
    assert not a.kernel.resources.snapshot()


def test_invalid_routing_branch_does_not_abort_shared_graph(mesh_nodes):
    a, _, _ = mesh_nodes
    task = TaskNode("device.status", {}, constraints={"node_id": "auto"})
    local = TaskNode("kernel.echo", {"text": "healthy"})
    graph = TaskGraph([task, local])
    result = a.kernel.scheduler.run_parallel(graph, ExecutionContext())
    assert not result.success and not task.result.success and local.result.success


def test_persist_failure_releases_node_admission_slot(mesh_nodes, monkeypatch):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    with monkeypatch.context() as patch:
        patch.setattr(b.node, "_persist", lambda: (_ for _ in ()).throw(OSError("fixture disk unavailable")))
        with pytest.raises(OSError): a._rpc(node, "submit", {"command_id": uuid.uuid4().hex, "capability": "device.status", "inputs": {}})
    assert a.dispatch("device.status", {}, node).success
    assert b.node._slots._value == 4


def test_restart_expires_owned_partial_metadata(mesh_nodes):
    a, _, _ = mesh_nodes
    key = uuid.uuid4().hex
    args = {"transfer_id": key, "op": "begin", "name": "stale.bin", "size": 1, "sha256": hashlib.sha256(b"a").hexdigest()}
    context = ExecutionContext(metadata={"mesh_peer": "local"})
    a.node.inbox.execute(args, context)
    record = a.node.inbox.records[key]; record["updated"] = time.time() - 301
    a.node.inbox._save(key, record); a.node.inbox.close()
    from morice.device_mesh.transfers import FileInbox
    restored = FileInbox(a.node.inbox.root, a.kernel)
    assert not restored.records and not list(restored.partial.glob("*.partial"))
    with pytest.raises(ValueError):
        a.node.inbox.execute({**args, "op": "chunk", "offset": True, "data": "YQ=="}, context)


def test_group_crud_and_default_survive_rename(mesh_nodes):
    a, b, c = mesh_nodes
    node = pair(a, b)
    a.registry.set_default("compute", node)
    a.rename(node, "Reassigned name")
    assert a.registry.resolve("compute") == node
    key = a.registry.group("Original", [node])
    a.registry.group("Updated", [node], group_id=key)
    assert a.registry.groups[key]["name"] == "Updated"
    a.registry.delete_group(key)
    assert key not in a.registry.groups
    from types import SimpleNamespace
    from unittest.mock import Mock
    from morice.pyside_app import MoriceWindow
    other = pair(a, c)
    a.rename(node, "Lab device"); a.rename(other, "Lab device")
    reply = Mock()
    window = SimpleNamespace(runtime=SimpleNamespace(trusted_nodes=SimpleNamespace(list=lambda: []), _device_mesh=a), _append_direct_reply=reply)
    assert MoriceWindow._handle_natural_node_control(window, "set volume on Lab device")
    assert "More than one device" in reply.call_args.args[1]
    with pytest.raises(ValueError): a.rename("discovered-but-unpaired", "Unsafe target")


def test_offline_queue_can_be_cancelled_and_revoke_clears_it(mesh_nodes):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    key = a.queue_safe(node, "device.status", {}, ttl=10, user_confirmed=True)
    assert a.cancel_queued(key) and not a.cancel_queued(key)
    a.queue_safe(node, "device.status", {}, ttl=10, user_confirmed=True)
    a.revoke(node)
    assert not a._queue


def test_authenticated_invalid_frames_do_not_admit_commands(mesh_nodes):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    ctx = a.credentials.context(certificates=[b.credentials.certificate])
    frames = [struct.pack("!I", MAX_FRAME + 1), encode({"version": "morice-mesh/999", "op": "submit"}),
        encode({"version": VERSION, "request_id": "bad id", "sender": a.credentials.node_id, "op": "submit", "payload": {}})]
    for frame in frames:
        with ctx.wrap_socket(socket.socket(), server_hostname="ignored") as connection:
            connection.settimeout(2); connection.connect(("127.0.0.1", b.transport.port)); connection.sendall(frame)
            try: assert not connection.recv(1)
            except (ConnectionResetError, ssl.SSLError): pass
    assert not b.node._commands
    assert a.dispatch("device.status", {}, node).success


def test_remote_resource_contention_does_not_occupy_node_workers(mesh_nodes):
    a, b, _ = mesh_nodes
    node = pair(a, b)
    assert b.kernel.resources.acquire("fixture-owner", (ResourceClaim("CPU", 2),))
    try:
        result = a.dispatch("python.calculate", {"expression": "1+2"}, node)
        assert not result.success and b.node._slots._value == 4
        assert not b.node._commands
        assert a.dispatch("device.status", {}, node).success
    finally:
        b.kernel.resources.release("fixture-owner")
