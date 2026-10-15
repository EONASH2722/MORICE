"""Deterministic Phase 1 overhead benchmark; no model or real PC actions."""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from morice.kernel import CapabilityKernel, EventBus, EventType, KernelEvent
from morice.kernel.adapters import register_echo, register_pc_adapters
from morice.pc_control import (ControlProviderRegistry, ControlResult, DesktopContext,
    FastActionRouter, PermissionBroker, PermissionCategory, PolicyMode)


def measure(function, count=250):
    samples = []
    for _ in range(count):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    return {"median_ms": statistics.median(samples), "p95_ms": ordered[int(.95 * (len(ordered) - 1))], "samples": count}


def main():
    cold = []
    code = "import time,json; s=time.perf_counter(); import morice.kernel; print(json.dumps((time.perf_counter()-s)*1000))"
    for _ in range(5):
        value = subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, text=True)
        cold.append(json.loads(value))
    kernel = CapabilityKernel()
    register_echo(kernel)
    bus = EventBus()
    subscription = bus.subscribe(lambda event: None)
    with tempfile.TemporaryDirectory() as directory:
        broker = PermissionBroker(Path(directory) / "permissions.json", defaults={PermissionCategory.APPLICATION_CONTROL: PolicyMode.ALLOW})
        registry = ControlProviderRegistry(broker)
        class DeterministicApplication:
            adapter_id = "benchmark.application"
            def supports(self, action): return action.tool_id == "application.open"
            def availability(self, action=None): return True, ""
            def execute(self, action, context):
                return ControlResult(action.action_id, action.tool_id, True, True, "Observed fixture application.")
        registry.register(DeterministicApplication())
        router = FastActionRouter(DesktopContext())
        def command(use_kernel):
            action = router.route("Open Calculator").action
            result = registry.execute(action) if use_kernel else registry._execute_legacy(action)
            assert result.success and result.verified
        direct = measure(lambda: command(False))
        register_pc_adapters(kernel, registry)
        adapted = measure(lambda: command(True))

        # Measure kernel constructor/registration within actual runtime startup,
        # keeping the real desktop/permission/tool objects and worker manager.
        from morice import kernel as kernel_module
        from morice.kernel import adapters
        from morice.runtime_services import RuntimeServices
        contributions = []
        def timed(function):
            def wrapper(*args, **kwargs):
                started = time.perf_counter()
                try:
                    return function(*args, **kwargs)
                finally:
                    contributions.append((time.perf_counter() - started) * 1000)
            return wrapper
        with patch.object(kernel_module, "CapabilityKernel", timed(kernel_module.CapabilityKernel)), \
             patch.object(adapters, "register_echo", timed(adapters.register_echo)), \
             patch.object(adapters, "register_tool_adapters", timed(adapters.register_tool_adapters)), \
             patch.object(adapters, "register_pc_adapters", timed(adapters.register_pc_adapters)), \
             patch.object(adapters, "register_native_adapters", timed(adapters.register_native_adapters)):
            start = time.perf_counter()
            runtime = RuntimeServices(Path(directory) / "runtime", project_root=ROOT)
            runtime_init = (time.perf_counter() - start) * 1000
            runtime.shutdown()
    data = {
        "python": sys.version.split()[0], "platform": sys.platform,
        "kernel_import_fresh_process_median_ms": statistics.median(cold),
        "kernel_constructor_and_registration_ms": sum(contributions),
        "runtime_initialization_ms": runtime_init,
        "echo_dispatch": measure(lambda: kernel.dispatch("kernel.echo", {"value": 1})),
        "event_with_one_subscriber": measure(lambda: bus.publish(KernelEvent(EventType.TASK_PROGRESS)), 1000),
        "calculator_fixture_direct_route_execute": direct,
        "calculator_fixture_kernel_route_execute_verify": adapted,
        "calculator_fixture_added_median_ms": adapted["median_ms"] - direct["median_ms"],
        "notes": "Warm deterministic fixture. Includes routing, permission checks and verification; excludes real OS launch, models and disk logging. Fresh-process import excludes Python process creation. Runtime initialization includes existing services; no model inference or network startup.",
    }
    kernel.shutdown()
    print(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    main()
