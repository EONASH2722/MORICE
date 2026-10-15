"""Local-first Windows/Linux node entry point. No arbitrary terminal or capture by default."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

from ..kernel import CapabilityKernel, ResourceDescriptor
from ..kernel.adapters import register_calculation
from ..action_runtime import ActionJournal, VerifiedActionRuntime
from ..unified_intelligence import PermissionState
from .runtime import DeviceMesh


def create_node(directory, *, name="MORICE Compute Node", host="127.0.0.1", port=0, pair_port=0):
    kernel = CapabilityKernel()
    kernel.resources.register(ResourceDescriptor("CPU", min(2, os.cpu_count() or 1)))
    kernel.permissions.controller.set_state("file_read", PermissionState.GRANTED)
    kernel.permissions.controller.set_state("file_write", PermissionState.GRANTED)
    register_calculation(kernel)
    actions = VerifiedActionRuntime(kernel, ActionJournal(Path(directory) / "action-journal.json"))
    mesh = DeviceMesh(kernel, directory, actions=actions, name=name, host=host, port=port, pair_port=pair_port, exposed=("python.calculate",))
    from ..science_engine import _evaluate_scalar
    mesh.node._observers["python.calculate"] = lambda args, ctx: {"value": _evaluate_scalar(args["expression"], float(args.get("x", 0)))}
    return mesh


def main():
    parser = argparse.ArgumentParser(description="Run an explicitly paired MORICE capability node.")
    parser.add_argument("--state", default=str(Path.home() / ".local" / "state" / "morice-mesh"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=47671)
    parser.add_argument("--pair-port", type=int, default=47672)
    parser.add_argument("--name", default="MORICE Compute Node")
    parser.add_argument("--pairing-window", action="store_true", help="Explicitly open a two-minute pairing window.")
    parser.add_argument("--ready-file", help="Private local harness/UI handoff; may contain a live pairing code.")
    args = parser.parse_args()
    mesh = create_node(args.state, name=args.name, host=args.host, port=args.port, pair_port=args.pair_port)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    mesh.enable()
    ready = {"node_id": mesh.credentials.node_id, "port": mesh.transport.port, "pair_port": mesh.transport.pair_port, "fingerprint": mesh.credentials.pin}
    if args.pairing_window:
        ready.update(mesh.transport.enable_pairing())
    if args.ready_file:
        path = Path(args.ready_file); path.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), "w") as stream:
            json.dump(ready, stream)
    print(json.dumps({k: v for k, v in ready.items() if k != "code"}), flush=True)
    def admin():
        for line in sys.stdin:
            try:
                request = json.loads(line)
                op = request.get("op")
                if op == "approve":
                    mesh.approve_pair(request["pair_id"], request["capabilities"], user_confirmed=True)
                    response = {"approved": True}
                elif op == "pair":
                    response = mesh.transport.enable_pairing()
                elif op == "status":
                    response = mesh.snapshot()
                elif op == "stop":
                    stop.set(); break
                else:
                    raise ValueError("Unknown local administrative operation.")
                print(json.dumps(response), flush=True)
            except (KeyError, ValueError, PermissionError) as error:
                print(json.dumps({"error": str(error)}), flush=True)
    threading.Thread(target=admin, daemon=True, name="morice-node-local-admin").start()
    try:
        while not stop.wait(.5):
            mesh.node.expire()
    finally:
        mesh.close(); mesh.kernel.shutdown()
        if args.ready_file:
            Path(args.ready_file).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
