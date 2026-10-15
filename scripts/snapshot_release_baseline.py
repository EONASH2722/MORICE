"""Read-only repository/environment snapshot; never stage or modify Git state."""
from __future__ import annotations
import datetime
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import psutil
from morice.version import VERSION


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='build/phase11-baseline');args=parser.parse_args()
    output = (ROOT/args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    # Preserve the first successful snapshot. Later comparisons need a new name.
    destination = output/'repository.json'
    if destination.exists(): raise FileExistsError('Initial release baseline already exists; preserve it.')
    status = git('status', '--porcelain=v1', '-uall'); entries = []
    for line in status.splitlines():
        name = line[3:]; path = ROOT/name; record = {'status': line[:2], 'path': name}
        if path.is_file():
            record['bytes'] = path.stat().st_size
            if record['bytes'] <= 32*1024*1024: record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(record)
    fingerprint = hashlib.sha256()
    for path in sorted((ROOT/'morice').rglob('*.py')):
        fingerprint.update(str(path.relative_to(ROOT)).encode()); fingerprint.update(path.read_bytes())
    dependencies = {}
    phase10_file=ROOT/'build/phase10-cinematic-current-status.json'
    phase10_current=json.loads(phase10_file.read_text(encoding='utf-8')) if phase10_file.exists() else {}
    authorization_file=ROOT/'docs/release-audit-issues.json'
    authorization=json.loads(authorization_file.read_text(encoding='utf-8')).get('authorized_update_scope',{}) if authorization_file.exists() else {}
    for name in ('PySide6', 'pytest', 'psutil', 'Pillow', 'geographiclib', 'comtypes', 'vosk', 'numpy', 'torch', 'diffusers', 'PyInstaller', 'cryptography'):
        try: dependencies[name] = metadata.version(name)
        except metadata.PackageNotFoundError: dependencies[name] = None
    try:
        gpu = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,driver_version', '--format=csv,noheader'], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired): gpu = None
    record = {'captured_at_utc': datetime.datetime.now(datetime.UTC).isoformat(), 'repository': str(ROOT), 'data_root': r'E:\MORICE_DATA',
        'branch': git('branch', '--show-current').strip(), 'head': git('rev-parse', 'HEAD').strip(), 'source_sha256': fingerprint.hexdigest(),
        'git_status': entries, 'staged_summary': git('diff', '--cached', '--stat'), 'version': VERSION,
        'version_source': 'morice/version.py (pyproject.toml dynamic version)', 'python': sys.version, 'platform': platform.platform(),
        'cpu': platform.processor(), 'cpu_logical_count': psutil.cpu_count(), 'ram_total_bytes': psutil.virtual_memory().total,
        'ram_available_bytes': psutil.virtual_memory().available, 'dependencies_main_runtime': dependencies, 'gpu_host_wide': gpu,
        'phase10_status': phase10_current.get('status','UNKNOWN'),
        'phase10_evidence':phase10_current,
        'test_baselines': [{'path': 'build/phase10-full-regression-first.log', 'tests': 1004, 'subtests': 62, 'seconds': 438.31, 'scope': 'Historical mid-migration source, before custom UI refinements'},
            {'path': 'build/phase10-custom-ui-validation.log', 'tests': 119, 'scope': 'Focused UI/voice snapshot, before later fixes'}],
        'startup_baselines': ['build/phase10-old-ui-baseline.json', 'build/phase10-new-ui-baseline.json'],
        'packaging_baseline': {'historical':'Phase9 and the preceding 0.8.0 Phase10 artifacts are retained separately.',
            'current_evidence':[name for name in ('build/phase11-theme-wheel-parity.json','build/phase11-theme-frozen-parity.json','build/phase11-theme-frozen-startup.json','build/phase11-clean-wheel-startup.json','build/phase10-dist-update.json') if (ROOT/name).is_file()]},
        'publication_authorized': authorization, 'preservation': 'No Git mutation, deletion, stash or model/data change performed by this snapshot'}
    destination.write_text(json.dumps(record, indent=2), encoding='utf-8'); (output/'git-status.txt').write_text(status, encoding='utf-8')
    print(json.dumps({'output': str(destination), 'head': record['head'], 'branch': record['branch'], 'version': VERSION, 'status_entries': len(entries), 'source_sha256': record['source_sha256'], 'phase10_status': record['phase10_status']}))


if __name__ == '__main__': main()
