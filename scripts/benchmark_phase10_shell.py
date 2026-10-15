"""Matched, isolated native startup/idle probes; no compositor timing claim."""
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
parser = argparse.ArgumentParser()
parser.add_argument('--child', choices=('legacy', 'renovated'))
parser.add_argument('--samples', type=int, default=3)
parser.add_argument('--output', default='build/phase10-matched-native-benchmark.json')
args = parser.parse_args()

if args.child:
    sys.path.insert(0, str(ROOT))
    started = time.perf_counter()
    import psutil
    from PySide6.QtCore import QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from morice import settings
    from morice.runtime_services import RuntimeServices
    import morice.runtime_services as services
    from morice.pyside_app import MoriceWindow, create_application_window
    imported = time.perf_counter()
    settings.save_settings({**settings.DEFAULT_SETTINGS, 'pet_enabled': 'false',
                           'tts_enabled': 'false', 'stt_enabled': 'false', 'model_path': ''})
    app = QApplication([])
    runtime = RuntimeServices(Path(os.environ['MORICE_RUNTIME_DIR']), project_root=ROOT)
    services._RUNTIME_SERVICES = runtime
    recovery = runtime.start()
    runtime_ready = time.perf_counter()
    window = create_application_window(runtime, recovery) if args.child == 'renovated' else MoriceWindow(runtime, recovery)
    window.resize(1366, 840); window.show(); window.activateWindow(); app.processEvents()
    ready = time.perf_counter()
    process = psutil.Process(); intervals = []; last = [ready]
    timer = QTimer(); timer.setInterval(20)
    def pulse():
        now = time.perf_counter(); intervals.append((now-last[0])*1000); last[0] = now
    timer.timeout.connect(pulse)
    try:
        QTest.qWait(1000)
        timer.start(); last[0] = time.perf_counter()
        cpu = process.cpu_times(); idle_started = time.perf_counter(); QTest.qWait(5000)
        idle_seconds = time.perf_counter()-idle_started; after = process.cpu_times()
        ordered = sorted(intervals)
        record = {
            'kind': args.child, 'window_class': type(window).__name__,
            'import_ms': (imported-started)*1000,
            'runtime_start_ms': (runtime_ready-imported)*1000,
            'window_first_events_ms': (ready-runtime_ready)*1000,
            'first_ready_ms': (ready-started)*1000,
            'idle_seconds': idle_seconds,
            'idle_cpu_one_core_percent': 100*((after.user+after.system)-(cpu.user+cpu.system))/idle_seconds,
            'idle_cpu_machine_percent': 100*((after.user+after.system)-(cpu.user+cpu.system))/idle_seconds/(psutil.cpu_count() or 1),
            'idle_rss_mb': process.memory_info().rss/2**20,
            'widgets': len(app.allWidgets()), 'threads': process.num_threads(),
            'timer_schedule': {'samples': len(ordered), 'median_ms': statistics.median(ordered),
                               'p95_ms': ordered[int((len(ordered)-1)*.95)], 'worst_ms': max(ordered)},
            'scope': 'Native source startup and reduced-motion idle. Retained legacy constructor uses current controllers, not historical release bytes. Timer delivery and paint CPU are not compositor frames.',
        }
        if args.child == 'renovated':
            record['effective_quality'] = window.effect_policy.budget.effective
            record['decorative_motion'] = window.effect_policy.budget.decorative_motion
    finally:
        timer.stop(); window.close(); app.processEvents(); runtime.shutdown()
    record['shutdown'] = runtime.shutdown_report
    assert record['shutdown']['clean']
    print(json.dumps(record), flush=True)
    sys.exit(0)

assert 1 <= args.samples <= 5
digest = hashlib.sha256()
for path in sorted((ROOT/'morice').rglob('*.py')):
    digest.update(str(path.relative_to(ROOT)).encode()); digest.update(path.read_bytes())
rows = []
for sample in range(args.samples):
    # Alternate order to reduce systematic cache/order bias.
    for kind in (('legacy', 'renovated') if sample % 2 == 0 else ('renovated', 'legacy')):
        with tempfile.TemporaryDirectory(prefix='morice-matched-ui-') as directory:
            root = Path(directory)
            environment = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
            environment.update(APPDATA=str(root/'roaming'), LOCALAPPDATA=str(root/'local'),
                MORICE_RUNTIME_DIR=str(root/'runtime'), MORICE_LOCAL_DATA_DIR=str(root/'data'),
                MORICE_PRELOAD='0', MORICE_DISABLE_SESSION='1', MORICE_DISABLE_RECOVERY='1',
                MORICE_DISABLE_FIRST_RUN='1', MORICE_START_AWAKE='1', MORICE_NODE_NETWORK='0',
                MORICE_REDUCE_MOTION='1', QT_QPA_PLATFORM='windows')
            result = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--child', kind],
                cwd=root, env=environment, capture_output=True, text=True, timeout=120,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            assert result.returncode == 0, result.stderr[-3000:]
            row = json.loads(result.stdout.splitlines()[-1]); row['sample'] = sample; rows.append(row)
            print(json.dumps(row), flush=True)
gpu = subprocess.run(['nvidia-smi', '--query-gpu=name,utilization.gpu,memory.used,memory.total',
                      '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=15)
record = {'status': 'MATCHED_NATIVE_SOURCE_PROBE_PASSED', 'source_sha256': digest.hexdigest(), 'rows': rows,
          'device_gpu_snapshot': gpu.stdout.strip() if gpu.returncode == 0 else 'UNAVAILABLE',
          'gpu_scope': 'Whole-device snapshot includes other applications; per-MORICE graphics GPU utilization/VRAM and compositor frame latency are not measured.'}
output = (ROOT/args.output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(record, indent=2), encoding='utf-8')
