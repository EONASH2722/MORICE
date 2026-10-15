"""Repeatable, isolated Phase 8 measurements; no provider accounts or model loads.

Run before and after changes with --output. All process metrics describe this
owned Python process; GPU samples are explicitly host wide. No user profile is
opened. Model/mesh/research evidence is recorded by the complementary demos.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if os.getenv("MORICE_PHASE8_SOURCE_TREE"):
    sys.path.insert(0, os.environ["MORICE_PHASE8_SOURCE_TREE"])


def distribution(values):
    ordered = sorted(values)
    return {"count": len(values), "p50_ms": statistics.median(values),
            "p95_ms": ordered[min(len(ordered)-1, int(len(ordered)*.95))],
            "max_ms": max(values), "samples_ms": values}


def snapshot():
    import psutil
    process = psutil.Process()
    cpu = process.cpu_times()
    return {"rss_bytes": process.memory_info().rss, "threads": process.num_threads(),
            "handles": process.num_handles() if os.name == "nt" else process.num_fds(),
            "open_files": len(process.open_files()),
            "sockets": len(process.net_connections()),
            "children": len(process.children(recursive=True)),
            "cpu_seconds": cpu.user + cpu.system}


def child():
    start = time.perf_counter()
    os.environ.update(QT_QPA_PLATFORM="offscreen", MORICE_PRELOAD="0",
        MORICE_DISABLE_SESSION="1", MORICE_DISABLE_RECOVERY="1",
        MORICE_REDUCE_MOTION="1", MORICE_NODE_NETWORK="0")
    stages = {}
    from unittest.mock import patch
    stamp = time.perf_counter()
    from PySide6.QtWidgets import QApplication
    stages["qt_import_ms"] = (time.perf_counter()-stamp)*1000
    stamp = time.perf_counter()
    from morice import settings
    from morice.runtime_services import RuntimeServices
    stages["runtime_import_ms"] = (time.perf_counter()-stamp)*1000
    stamp = time.perf_counter()
    if os.getenv('MORICE_BENCH_UI') == 'renovated':
        from morice.ui_next.shell import RenovatedWindow as MoriceWindow
    else:
        from morice.pyside_app import MoriceWindow
    stages["ui_import_ms"] = (time.perf_counter()-stamp)*1000
    with tempfile.TemporaryDirectory(prefix="morice-phase8-benchmark-") as directory:
        root = Path(directory)
        os.environ['MORICE_LOCAL_DATA_DIR'] = str(root/'data')
        with patch("morice.settings._settings_dir", return_value=str(root/"settings")):
            settings.save_settings({**settings.DEFAULT_SETTINGS, "tts_enabled":"false",
                "stt_enabled":"false", "desktop_pet_enabled":"false"})
            stamp = time.perf_counter(); app = QApplication([])
            stages["qapplication_ms"] = (time.perf_counter()-stamp)*1000
            stamp = time.perf_counter(); runtime = RuntimeServices(root/"runtime", project_root=ROOT)
            # Match run_app's single application runtime, including the prior
            # packaged baseline. Never let optional telemetry open a user profile.
            import morice.runtime_services as runtime_module
            runtime_module._RUNTIME_SERVICES = runtime
            stages["constructor_ms"] = (time.perf_counter()-stamp)*1000
            stamp = time.perf_counter(); recovery = runtime.start()
            stages["health_start_ms"] = (time.perf_counter()-stamp)*1000
            startup_profiler = None
            if os.getenv('MORICE_STARTUP_PROFILE_PATH'):
                import cProfile
                startup_profiler = cProfile.Profile(); startup_profiler.enable()
            stamp = time.perf_counter(); window = MoriceWindow(runtime, recovery)
            window.show(); app.processEvents()
            stages["window_ms"] = (time.perf_counter()-stamp)*1000
            stamp = time.perf_counter(); window._run_startup_health_check()
            stages["actual_health_check_ms"] = (time.perf_counter()-stamp)*1000
            stages["ready_total_ms"] = (time.perf_counter()-start)*1000
            if startup_profiler is not None:
                startup_profiler.disable(); startup_profiler.dump_stats(os.environ['MORICE_STARTUP_PROFILE_PATH'])
            lazy = {"research":runtime._research_runtime is None,
                    "mesh":runtime._device_mesh is None,
                    "ambient":runtime._ambient_service is None,
                    "builder":runtime.autonomous_builder._project_runtime is None,
                    "agents":runtime.agents._drivers is None,
                    "media":runtime._media_lab is None,
                    "heavy_media_imports_absent":not any(name in sys.modules for name in ('torch','diffusers','transformers'))}
            assert all(lazy.values()), lazy
            settle_until = time.perf_counter()+6
            while time.perf_counter()<settle_until:
                app.processEvents(); time.sleep(.01)
            before = snapshot(); idle_start = time.perf_counter(); idle_cpu_start=time.process_time()
            if os.getenv("MORICE_PHASE8_PROFILE"):
                import cProfile
                profiler = cProfile.Profile(); profiler.enable()
            until = idle_start+3
            ui_ticks = 0
            while time.perf_counter() < until:
                app.processEvents(); ui_ticks += 1; time.sleep(.01)
            idle_wall = time.perf_counter()-idle_start
            cpu_seconds = time.process_time()-idle_cpu_start
            if os.getenv("MORICE_PHASE8_PROFILE"):
                profiler.disable(); profiler.dump_stats(ROOT/"build/phase8-idle.prof")
            after = snapshot()
            direct = []
            for _ in range(300):
                stamp = time.perf_counter()
                result = runtime.kernel.dispatch("python.calculate", {"expression":"2+3"})
                assert result.success
                direct.append((time.perf_counter()-stamp)*1000)
            from morice.kernel.events import KernelEvent, EventType
            event_samples = []; received = [0]
            subscription = runtime.kernel.events.subscribe(lambda event: received.__setitem__(0,received[0]+1), EventType.TASK_PROGRESS)
            for i in range(10000):
                stamp = time.perf_counter()
                runtime.kernel.events.publish(KernelEvent(EventType.TASK_PROGRESS, payload={"index":i}))
                event_samples.append((time.perf_counter()-stamp)*1000)
            runtime.kernel.events.unsubscribe(subscription)
            assert received[0] == 10000
            active = snapshot()
            window.close(); app.processEvents(); stamp = time.perf_counter(); runtime.shutdown()
            shutdown_ms = (time.perf_counter()-stamp)*1000
            final = snapshot()
            print(json.dumps({"stages":stages, "lazy":lazy, "idle_before":before,
                "idle_after":after, "idle_wall_seconds":idle_wall, "startup_settle_seconds":6,
                "idle_cpu_one_core_percent":100*cpu_seconds/idle_wall, "ui_ticks":ui_ticks,
                "direct_calculation":distribution(direct), "event_publish":distribution(event_samples),
                "event_received":received[0], "active":active, "shutdown_ms":shutdown_ms,
                "after_shutdown":final, "leases_after":len(runtime.kernel.resources.snapshot()),
                "critical_failures":len(runtime.health_report.critical_failures)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--output", default="build/phase8-benchmark.json")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument('--ui',choices=('legacy','renovated'),default='legacy')
    parser.add_argument('--startup-profile')
    args = parser.parse_args()
    os.environ['MORICE_BENCH_UI'] = args.ui
    if args.startup_profile: os.environ['MORICE_STARTUP_PROFILE_PATH'] = str(Path(args.startup_profile).resolve())
    if args.child:
        child(); return
    runs = []
    for _ in range(args.runs):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", '--ui', args.ui],
            cwd=ROOT, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError(result.stderr[-3000:])
        runs.append(json.loads(result.stdout.splitlines()[-1]))
    fingerprint = hashlib.sha256()
    source_root = Path(os.getenv("MORICE_PHASE8_SOURCE_TREE", str(ROOT)))
    for path in sorted((source_root/"morice").rglob("*.py")):
        fingerprint.update(str(path.relative_to(source_root)).encode()); fingerprint.update(path.read_bytes())
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        gpu = None
    document = {"version":1, "ui":args.ui, "source_sha256":fingerprint.hexdigest(), "python":sys.version,
        "gpu_host_wide":gpu, "source_tree":os.getenv("MORICE_PHASE8_SOURCE_TREE",str(ROOT)), "runs":runs, "startup":distribution([r["stages"]["ready_total_ms"] for r in runs]),
        "limits":"Idle is 3 seconds after 6 seconds settling; CPU excludes observer snapshots and is one-core process CPU; GPU is host-wide. No models loaded."}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document,indent=2), encoding="utf-8")
    print(json.dumps({"output":str(output), "startup":{k:v for k,v in document["startup"].items() if k!="samples_ms"},
        "direct_p50_ms":[r["direct_calculation"]["p50_ms"] for r in runs],
        "idle_cpu_percent":[r["idle_cpu_one_core_percent"] for r in runs]}))


if __name__ == "__main__":
    main()
