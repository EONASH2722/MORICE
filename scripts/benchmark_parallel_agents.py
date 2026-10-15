"""Repeatable local Phase 2 evidence: real routes plus a controlled I/O fixture."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from morice.agent_runtime import AgentCoordinator, AgentRole
from morice.agent_tools import BuiltinTools
from morice.desktop_environment import DesktopIntegrationLayer
from morice.kernel import CapabilityDescriptor, CapabilityKernel, ExecutionContext, ExecutionResult, TaskGraph, TaskNode, TaskStatus
from morice.kernel.adapters import register_echo, register_native_adapters, register_tool_adapters
from morice.runtime_services import _process_memory_mb, _nvidia_gpu_metrics
from morice.unified_intelligence import PermissionState


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="build/phase2-benchmark.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="morice-phase2-") as directory:
        root = Path(directory)
        kernel = CapabilityKernel()
        register_echo(kernel)
        kernel.permissions.controller.set_state("file_read", PermissionState.GRANTED)
        register_native_adapters(kernel, DesktopIntegrationLayer(root / "desktop"))
        tools = BuiltinTools(root / "tools"); register_tool_adapters(kernel, tools)
        agents = AgentCoordinator(kernel)
        agents.roles.register(AgentRole("fixture", "Fixture", "Controlled wait workload", ("benchmark.io",), result_schema={}))
        def controlled(inputs, context):
            context.cancellation_token.wait(.15)
            context.cancellation_token.raise_if_cancelled()
            return ExecutionResult(TaskStatus.SUCCEEDED, True, inputs["value"])
        kernel.registry.register(CapabilityDescriptor("benchmark.io", "Controlled cancellable I/O", supports_cancellation=True), controlled)
        def io_graph():
            return TaskGraph(tuple(TaskNode("benchmark.io", {"value": n}, constraints={"role": "fixture"}) for n in range(3)))
        stop = threading.Event(); measurements = []
        cpu_started = time.process_time(); wall_started = time.perf_counter()
        def sample():
            while not stop.is_set():
                measurements.append(_process_memory_mb())
                stop.wait(.02)
        sampler = threading.Thread(target=sample, daemon=True); sampler.start()
        def measure(factory):
            times, peaks = {}, {}
            successes = []
            for mode in ("sequential", "parallel"):
                samples = []
                for _ in range(3):
                    graph, context = factory()
                    started = time.perf_counter()
                    result = agents.run(graph, context, sequential=mode == "sequential")
                    samples.append((time.perf_counter()-started)*1000)
                    successes.append(result.success)
                    peaks[mode] = result.metrics["active_peak"]
                times[mode+"_ms"] = statistics.median(samples)
            return {**times, "speedup": times["sequential_ms"]/times["parallel_ms"], "peak_workers": peaks, "all_verified_success": all(successes)}
        controlled_result = measure(lambda: (io_graph(), ExecutionContext()))
        documents = []
        for n in range(3):
            path = root / f"source{n}.txt"; path.write_text((f"Evidence source {n}.\n" * 300), encoding="utf-8"); documents.append(str(path))
        documents_result = measure(lambda: (agents.planner.documents(documents), ExecutionContext()))
        counter = 0
        def coding():
            nonlocal counter
            counter += 1
            candidates = []
            for n in range(2):
                candidate_root = root / f"run{counter}-candidate{n}"; candidate_root.mkdir()
                content = "def square(x):\n    return x * x\n" if n == 0 else "def square(x):\n    return pow(x, 2)\n"
                candidates.append({"name": str(n), "root": str(candidate_root),
                    "changes": [{"path": "answer.py", "content": content, "expected_exists": False}],
                    "command": [sys.executable, "-c", "from answer import square; import time; time.sleep(.15); assert square(3)==9; assert square(-2)==4; print('2 assertions passed')"]})
            graph = agents.planner.coding(candidates)
            approvals = {t.task_id: tools.permissions.grant(t.capability_requirement, t.inputs) for t in graph.tasks
                if t.capability_requirement in {"filesystem.apply_patch", "terminal.run"}}
            return graph, ExecutionContext(metadata={"task_approvals": approvals})
        coding_result = measure(coding)
        # Same direct PC route fixture used by Phase 1; no UI/OS launch timing.
        from morice.pc_control import ControlAction, ControlProviderRegistry, ControlResult, DesktopContext, FastActionRouter, PermissionBroker, PermissionCategory, PolicyMode
        from morice.kernel.adapters import register_pc_adapters
        class CalculatorFixture:
            adapter_id = "calculator-fixture"
            def supports(self, action): return action.tool_id == "application.open"
            def availability(self, action): return True, ""
            def execute(self, action, context): return ControlResult(action.action_id, action.tool_id, True, True, "Opened Calculator.")
        pc = ControlProviderRegistry(PermissionBroker(root/"pc-permissions.json", defaults={PermissionCategory.APPLICATION_CONTROL: PolicyMode.ALLOW}), context=DesktopContext())
        pc.register(CalculatorFixture()); register_pc_adapters(kernel, pc)
        router = FastActionRouter(DesktopContext())
        fast = []
        for _ in range(250):
            started = time.perf_counter()
            action = router.route("Open Calculator").action
            assert pc.execute(action).success
            fast.append((time.perf_counter()-started)*1000)
        stop.set(); sampler.join(1)
        elapsed = time.perf_counter()-wall_started
        gpu, vram = _nvidia_gpu_metrics()
        data = {"controlled_io": controlled_result, "coding": coding_result, "documents": documents_result,
            "direct_calculator_fixture_median_ms": statistics.median(fast),
            "cpu_process_seconds": time.process_time()-cpu_started, "wall_seconds": elapsed,
            "average_process_cpu_one_core_percent": (time.process_time()-cpu_started)/elapsed*100,
            "peak_process_ram_mb": max(measurements, default=0), "gpu_utilization_end_percent": gpu,
            "gpu_vram_used_end_mb": vram,
            "notes": ["Controlled I/O explicitly waits 150 ms per independent task.",
                "Coding uses actual approved patches and Python subprocess tests with a 150 ms wait in each test fixture.",
                "Document workflow uses real desktop previews, comparison and independent readback; speedup is not assumed.",
                "CPU/RAM cover this benchmark process; GPU/VRAM are end samples from existing profiler, not peak inference measurements.",
                "No local model is loaded; no claim about parallel LLM speedup."]}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(json.dumps(data, indent=2))
        agents.shutdown(); kernel.shutdown()


if __name__ == "__main__":
    main()
