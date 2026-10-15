"""Actual TLS RPC to a second Windows/Linux node process; no mock transport."""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from morice.device_mesh.node import create_node


def process_info(pid):
    if os.name == "nt":
        command = f"$p=Get-Process -Id {int(pid)}; @{{cpu=$p.CPU; rss=$p.WorkingSet64; children=@(Get-CimInstance Win32_Process -Filter 'ParentProcessId = {int(pid)}' | Select-Object -ExpandProperty ProcessId)}} | ConvertTo-Json -Compress"
        return json.loads(subprocess.check_output(["powershell", "-NoProfile", "-Command", command], text=True,
                          creationflags=subprocess.CREATE_NO_WINDOW))
    fields = Path(f"/proc/{pid}/stat").read_text().split()
    return {"cpu": (int(fields[13]) + int(fields[14])) / os.sysconf("SC_CLK_TCK"),
            "rss": int(fields[23]) * os.sysconf("SC_PAGE_SIZE"), "children": []}


def start_node(root, ready, *, pairing):
    command = [sys.executable, "-m", "morice.device_mesh.node", "--state", str(root), "--port", "0", "--pair-port", "0", "--ready-file", str(ready)]
    if pairing:
        command.append("--pairing-window")
    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    until = time.monotonic() + 15
    while time.monotonic() < until:
        if ready.exists():
            value = json.loads(ready.read_text()); process.stdout.readline(); return process, value
        if process.poll() is not None:
            raise RuntimeError(process.stderr.read())
        time.sleep(.03)
    process.terminate(); process.wait(3)
    raise TimeoutError("Node startup deadline.")


def stop_node(process):
    if process.poll() is None:
        try:
            process.stdin.write(json.dumps({"op": "stop"}) + "\n"); process.stdin.flush(); process.wait(5)
        except (OSError, subprocess.TimeoutExpired):
            process.terminate(); process.wait(3)
    process.stdin.close(); process.stdout.close(); process.stderr.close()


def main():
    results = {"transport": "TLS 1.3 mutual certificate authentication", "hardware": "two real local OS processes", "rpc_samples": []}
    with tempfile.TemporaryDirectory(prefix="morice-mesh-benchmark-") as temporary:
        root = Path(temporary); ready = root / "ready.json"
        coordinator = create_node(root / "coordinator")
        coordinator.enable(heartbeat=False)
        process, node = start_node(root / "node", ready, pairing=True)
        try:
            started = time.perf_counter()
            pending = coordinator.begin_pair("127.0.0.1", node["pair_port"], node["code"], node["fingerprint"], user_confirmed=True)
            grants = ["device.status", "python.calculate", "file.receive", "file.send", "project.inspect"]
            process.stdin.write(json.dumps({"op": "approve", "pair_id": pending["pair_id"], "capabilities": grants}) + "\n"); process.stdin.flush()
            assert json.loads(process.stdout.readline())["approved"]
            peer = coordinator.finish_pair(pending, outbound_permissions=grants, inbound_permissions=["device.status"], user_confirmed=True)
            node_id = peer.descriptor.device_id
            results["pairing_ms"] = (time.perf_counter() - started) * 1000
            status = coordinator.dispatch("device.status", {}, node_id)
            reported_pid = status.output.get("process_id") if isinstance(status.output, dict) else None
            family = {process.pid, *process_info(process.pid)["children"]}
            assert status.success and reported_pid in family and reported_pid != os.getpid(), (status.to_dict(), process.pid, family)
            results["remote_process_id"] = reported_pid
            results["remote_process_verified"] = True
            for _ in range(20):
                started = time.perf_counter(); assert coordinator._rpc(node_id, "ping")["online"]
                results["rpc_samples"].append((time.perf_counter() - started) * 1000)
            results["rpc_median_ms"] = statistics.median(results["rpc_samples"])
            started = time.perf_counter(); coordinator.connect(node_id)
            results["capability_discovery_ms"] = (time.perf_counter() - started) * 1000
            commands = []
            for _ in range(5):
                started = time.perf_counter(); value = coordinator.dispatch("python.calculate", {"expression": "19*23"}, node_id)
                assert value.success and value.output["value"] == 437
                commands.append((time.perf_counter() - started) * 1000)
            results["small_command_median_ms"] = statistics.median(commands)
            results["transfers"] = []
            for size in (1024 * 1024, 8 * 1024 * 1024):
                source = root / (str(size) + ".bin")
                with source.open("wb") as stream:
                    for _ in range(size // 65536): stream.write(bytes(range(256)) * 256)
                import uuid
                transfer_id = uuid.uuid4().hex
                started = time.perf_counter(); interruptions = 0
                while True:
                    try:
                        transfer = coordinator.send_file(source, node_id, transfer_id=transfer_id)
                        break
                    except RuntimeError:
                        interruptions += 1
                        if interruptions > 2:
                            raise
                        coordinator.connect(node_id)
                        coordinator.reconcile_leases()
                        # Explicit resume reads/validates the same transfer's
                        # physical ranges before sending further bytes.
                elapsed = time.perf_counter() - started
                assert transfer["complete"]
                results["transfers"].append({"bytes": size, "seconds": elapsed, "mib_per_second": size / 1024**2 / elapsed, "verified": True, "explicit_resumes": interruptions})
            pulled = coordinator.receive_file("1048576.bin", node_id)
            assert pulled["complete"]
            before_cpu = process_info(reported_pid); before_wall = time.perf_counter(); time.sleep(2)
            after_cpu = process_info(reported_pid); elapsed = time.perf_counter() - before_wall
            results["idle_child_cpu_percent_one_core"] = (after_cpu["cpu"] - before_cpu["cpu"]) / elapsed * 100
            results["idle_child_rss_mib"] = after_cpu["rss"] / 1024**2
            stop_node(process)
            started = time.perf_counter(); process, restored = start_node(root / "node", ready, pairing=False)
            assert restored["node_id"] == node_id
            coordinator.connect(node_id, "127.0.0.1", restored["port"])
            assert coordinator.dispatch("device.status", {}, node_id).success
            results["process_restart_reconnect_ms"] = (time.perf_counter() - started) * 1000
            results["repaired"] = False
            results["coordinator_leases_after"] = len(coordinator.kernel.resources.snapshot())
            results["transport_metrics"] = dict(coordinator.transport.metrics)
        finally:
            stop_node(process); coordinator.close(); coordinator.kernel.shutdown()
        results["sockets_after"] = len(coordinator.transport._connections)
        results["node_process_exit"] = process.returncode
    output = ROOT / "build" / "phase5-benchmark.json"
    output.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
