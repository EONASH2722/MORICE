"""Real TLS, bounded runtime; synthetic source/cooperative adapter clearly labelled."""
import json
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from morice.device_mesh.node import create_node
from morice.agent_runtime import AgentCoordinator
from morice.kernel import CancellationToken, ExecutionContext, TaskGraph, TaskNode, ResourceClaim
from morice.unified_intelligence import PermissionState

with tempfile.TemporaryDirectory(prefix="morice-mesh-limits-") as temporary:
    nodes = [create_node(Path(temporary) / str(index)) for index in range(3)]
    a, b, c = nodes
    agents = AgentCoordinator(a.kernel)
    result = {"transport": "real mutual TLS on localhost", "source": "explicit synthetic sample adapter; no hardware capture"}
    state = {"cancelled": False}
    def cooperative(args, context):
        context.cancellation_token.wait(5); state["cancelled"] = context.cancellation_token.cancelled
        return dict(state)
    b.node.register("fixture.wait", cooperative, lambda args, context: dict(state), resources=(ResourceClaim("CPU"),))
    class Source:
        def read(self): return b"synthetic fixture sample" * 100
        def close(self): pass
    b.kernel.permissions.controller.set_state("camera_access", PermissionState.GRANTED)
    b.register_stream("camera.stream", lambda args: Source(), resource="CAMERA", available=lambda: True, permission="camera_access")
    try:
        for node in nodes: node.enable(heartbeat=False)
        peers = []
        for remote in (b, c):
            window = remote.transport.enable_pairing()
            pending = a.begin_pair("127.0.0.1", window["pair_port"], window["code"], window["fingerprint"], user_confirmed=True)
            grants = ["device.status", "python.calculate"] + (["fixture.wait", "camera.stream"] if remote is b else [])
            remote.approve_pair(pending["pair_id"], grants, user_confirmed=True)
            peers.append(a.finish_pair(pending, outbound_permissions=grants, user_confirmed=True).descriptor.device_id)
        graph = TaskGraph([TaskNode("python.calculate", {"expression": f"{i}+1"}, constraints={"node_id": peers[i % 2]}) for i in range(12)])
        started = time.perf_counter(); output = agents.run(graph)
        result["parallel_12_commands_ms"] = (time.perf_counter() - started) * 1000
        assert output.success
        token = CancellationToken(); key = uuid.uuid4().hex; completed = []
        worker = threading.Thread(target=lambda: completed.append(a.dispatch("fixture.wait", {}, peers[0], ExecutionContext(cancellation_token=token), expected={"cancelled": True}, task_id=key)))
        worker.start(); until = time.monotonic() + 3
        while key not in b.node._commands and time.monotonic() < until: time.sleep(.01)
        started = time.perf_counter(); token.cancel(); worker.join(3)
        result["cooperative_cancel_ms"] = (time.perf_counter() - started) * 1000
        assert completed and not completed[0].success and state["cancelled"]
        args = {"op": "start", "fps": 5}; key = uuid.uuid4().hex
        b.node.approve_command(a.credentials.node_id, key, "camera.stream", args, user_confirmed=True)
        approval = a.kernel.permissions.controller.issue_one_use(key, "camera.stream", args)
        opened = a.dispatch("camera.stream", args, peers[0], ExecutionContext(approval_token=approval), task_id=key, expected={"active": True})
        assert opened.success
        started = time.perf_counter()
        sampled = a.dispatch("camera.stream", {"op": "sample", "stream_id": opened.output["stream_id"]}, peers[0], expected={"active": True})
        result["synthetic_sample_ms"] = (time.perf_counter() - started) * 1000
        assert sampled.success and sampled.output["sample_ready"]
        assert a.dispatch("camera.stream", {"op": "stop", "stream_id": opened.output["stream_id"]}, peers[0], expected={"active": False}).success
        before_rpc = sum(node.transport.metrics["rpc_count"] for node in nodes)
        before_cpu = time.process_time(); started = time.perf_counter()
        for node in nodes: node.enable(heartbeat=True)
        time.sleep(6)
        result["heartbeat_6_seconds_process_cpu_ms"] = (time.process_time() - before_cpu) * 1000
        result["heartbeat_rpc_count"] = sum(node.transport.metrics["rpc_count"] for node in nodes) - before_rpc
    finally:
        for node in nodes: node.close()
        agents.shutdown()
        for node in nodes: node.kernel.shutdown()
    result["leases_after"] = sum(len(node.kernel.resources.snapshot()) for node in nodes)
    result["sockets_after"] = sum(len(node.transport._connections) for node in nodes)
    result["streams_after"] = sum(len(node.streams.active) for node in nodes)
    assert result["leases_after"] == result["sockets_after"] == result["streams_after"] == 0
    Path("build/phase5-limits-benchmark.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
