"""Compare existing kernel routes with observed actions; local disk/process work only."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from morice.kernel import ExecutionContext, TaskNode
from morice.runtime_services import RuntimeServices, _process_memory_mb, _nvidia_gpu_metrics


def measure(call, count):
    samples = []
    for number in range(count):
        started = time.perf_counter(); call(number); samples.append((time.perf_counter()-started)*1000)
    return {"median_ms": statistics.median(samples), "p95_ms": sorted(samples)[int(.95*(len(samples)-1))], "samples": count}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", default="build/phase3-benchmark.json"); args = parser.parse_args()
    cpu_start = time.process_time(); wall_start = time.perf_counter()
    results = {}
    with tempfile.TemporaryDirectory(prefix="morice-actions-benchmark-") as directory:
        root = Path(directory); service = RuntimeServices(root / "runtime", project_root=root)
        runtime = service.kernel.actions
        try:
            for enabled in (False, True):
                service.kernel.actions = runtime if enabled else None
                label = "observed" if enabled else "existing_kernel"
                def echo(number):
                    assert service.kernel.dispatch("kernel.echo", {"value": number}).success
                def write(number):
                    inputs = {"root": str(root), "changes": [{"path": "actual.txt", "content": f"sample {label} {number}\n"}]}
                    approval = service.agent.tools.permissions.grant("filesystem.apply_patch", inputs)
                    assert service.kernel.run_task(TaskNode("filesystem.apply_patch", inputs), ExecutionContext(approval_token=approval)).success
                def process(number):
                    inputs = {"cwd": str(root), "command": [sys.executable, "-c", "assert 2+3==5"], "timeout": 2}
                    approval = service.agent.tools.permissions.grant("terminal.run", inputs)
                    assert service.kernel.run_task(TaskNode("terminal.run", inputs), ExecutionContext(approval_token=approval)).success
                results[label] = {"echo": measure(echo, 250), "patch": measure(write, 15), "process": measure(process, 5)}
            results["memory_mb"] = _process_memory_mb()
            results["gpu_host_sample"] = _nvidia_gpu_metrics()
            results["agents_dispatched"] = service.agents.workers.peak
            results["leases_after"] = len(service.kernel.resources.snapshot())
            results["journal_attempts"] = len(runtime.journal.attempts())
        finally:
            service.kernel.actions = runtime; service.shutdown()
    results["wall_seconds"] = time.perf_counter()-wall_start
    results["cpu_seconds"] = time.process_time()-cpu_start
    results["cpu_one_core_percent"] = results["cpu_seconds"]/results["wall_seconds"]*100
    target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
