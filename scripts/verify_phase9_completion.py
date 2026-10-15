"""Fail closed on missing/stale Phase 9 evidence, preserving validation limits."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from morice.media_lab.artifacts import verify_image


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8-sig'))


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


report_path = ROOT / 'docs/generative-media-lab-report.md'
report = report_path.read_text(encoding='utf-8')
numbers = [int(item) for item in re.findall(r'^(\d+)\. \*\*', report, re.M)]
assert numbers == list(range(1, 79)), numbers
assert 'final clean Windows package validation pending' not in report
assert all(word in report for word in ('RAM', 'INTERRUPTED', 'VIDEO PROVIDER UNAVAILABLE', 'controlled', 'unvalidated'))
assert (ROOT / 'docs/generative-media-lab-audit.md').is_file()

log = (ROOT / 'build/phase9-post-audit-full-tests.log').read_text(encoding='utf-8-sig')
match = re.search(r'(\d+) passed, (\d+) subtests passed in ([\d.]+)s', log)
assert match and 'FAILED ' not in log and 'ERROR ' not in log, log[-2000:]
assert (int(match[1]), int(match[2])) == (923, 62)
targeted = (ROOT / 'build/phase9-final-audit-tests.log').read_text(encoding='utf-8-sig')
assert '48 passed in 35.73s' in targeted

audit = read('build/phase9-final-audit.json')
package = read('build/phase9-package.json')
startup = read('build/phase9-release-startup.json')
smoke = read('build/phase9-isolated-startup-smoke.json')
baseline = read('build/phase9-startup-idle-quiet.json')
fingerprint = hashlib.sha256()
for path in sorted((ROOT / 'morice').rglob('*.py')):
    fingerprint.update(str(path.relative_to(ROOT)).encode())
    fingerprint.update(path.read_bytes())
source_sha = fingerprint.hexdigest()
assert source_sha == audit['source_sha256'] == baseline['source_sha256']
assert audit['module_count'] == package['source_equal_modules'] == 182
assert audit['media_module_count'] == 16 and not audit['heavy_top_level_media_imports']
assert all(row['exit_code'] == 0 for row in audit['pip_checks'])
assert digest(package['wheel']) == package['sha256'] and package['sha256'] in report
assert package['zip_integrity'] and package['isolated_import']['calculation_verified']
assert package['isolated_import']['roles'] == 9 and package['isolated_import']['leases'] == 0
assert package['frozen']['source_equal_modules'] == 180
assert set(package['frozen']['omitted_cli_modules']) == {'morice.cli', 'morice.__main__'}
assert package['frozen']['external_media_worker_equal'] and not package['frozen']['model_weights_embedded']
assert digest(startup['executable']) == package['frozen']['exe_sha256'] == startup['executable_sha256']
assert startup['executable_sha256'] in report
assert startup['exit_code'] == 0 and startup['system_path_only'] and startup['python_environment_removed']
assert not Path(startup['cwd']).is_relative_to(ROOT)
assert smoke['frozen'] and smoke['window_created'] and smoke['roles'] == 9
assert len(smoke['health']) == 27 and smoke['critical_failures'] == smoke['leases_after'] == 0
assert smoke['shutdown']['clean'] and smoke['shutdown']['pending_workers'] == 0
assert any(row['name'] == 'Generative Media Lab' and row['status'] == 'disabled' for row in smoke['health'])
assert len(baseline['runs']) == 3
assert all(all(row['lazy'].values()) and row['leases_after'] == row['critical_failures'] == 0 for row in baseline['runs'])

receipt = read('build/phase9-model-download-receipt.json')
assert receipt['status'] == 'APPROVED_DOWNLOADED_VERIFIED'
assert receipt['repository'] == 'stabilityai/sd-turbo'
assert receipt['revision'] == 'b261bac6fd2cf515557d5d0707481eafa0485ec2'
assert len(receipt['files']) == 14 and sum(row['bytes'] for row in receipt['files']) == 2581668541
model_root = Path(receipt['destination']).resolve()
assert not model_root.is_relative_to(ROOT)
for row in receipt['files']:
    path = (model_root / row['path']).resolve()
    assert path.is_relative_to(model_root) and path.stat().st_size == row['bytes']
    assert digest(path) == row['sha256'], row['path']

real = read('build/phase9-real-image-process-tree.json')
suite = read('build/phase9-real-ui-suite.json')
benchmark = read('build/phase9-real-benchmark.json')
soak = read('build/phase9-safety-soak.json')
assert real['shutdown']['clean'] and real['shutdown']['leases_remaining'] == 0
assert benchmark['shutdown']['clean'] and benchmark['shutdown']['leases_remaining'] == 0
rows = benchmark['benchmark']['rows']
successful = [row for row in rows if row['status'] == 'SUCCEEDED']
assert len(rows) == 9 and len(successful) == 5 and benchmark['benchmark']['ooms'] == 0
assert {(row['settings']['width'], row['mode']) for row in successful} == {(512, 'direct'), (512, 'low_vram'), (640, 'direct'), (640, 'low_vram'), (768, 'low_vram')}
assert len(suite['cases']) == 4 and all(case['success'] for case in suite['cases'])
assert {case['history']['request']['intent'] for case in suite['cases']} == {'TEXT_TO_IMAGE', 'IMAGE_TO_IMAGE', 'INPAINT'}
assert real['cases'][0]['result']['metrics']['peak_ram_mb'] > 2000

data_root = model_root.parents[2]
history_path = data_root / 'media/metadata/history.sqlite3'
artifacts = []
with sqlite3.connect('file:' + history_path.as_posix() + '?mode=ro', uri=True) as db:
    assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    ids = [case['generation_id'] for case in real['cases'] + suite['cases']] + [row['generation_id'] for row in successful]
    for identifier in ids:
        state, payload = db.execute('SELECT state,payload FROM media_jobs WHERE id=?', (identifier,)).fetchone()
        value = json.loads(payload)
        assert state == value['status'] == 'SUCCEEDED' and value['verification'] == 'verified'
        for artifact in value['artifacts']:
            path = Path(artifact['path']).resolve()
            assert path.is_relative_to(data_root / 'media/outputs')
            observed = verify_image(path, artifact['width'], artifact['height'])
            assert observed['sha256'] == artifact['sha256']
            artifacts.append({key: artifact[key] for key in ('generation_id', 'path', 'sha256', 'width', 'height', 'format')})
    interrupted_id = 'ec3dde629ba44571adf2169b712a71d8'
    state, payload = db.execute('SELECT state,payload FROM media_jobs WHERE id=?', (interrupted_id,)).fetchone()
    assert state == 'INTERRUPTED' and not json.loads(payload)['artifacts']
registry = json.loads((data_root / 'media/metadata/models.json').read_text())
model = next(row for row in registry['models'] if row['model_id'] == 'sd-turbo-fp16')
assert (model['estimated_vram_mb'], model['estimated_ram_mb'], model['minimum_vram_mb']) == (4096, 3584, 2304)
assert len(artifacts) == 11

assert soak['success'] and len(soak['cases']) == 16 and not soak['cases'][0]['success']
assert any('ACTUAL bounded CUDA OutOfMemoryError' in error['detail'] for error in soak['cases'][0]['result']['errors'])
assert all(case['success'] for case in soak['cases'][1:])
assert not soak['owned_workers_after'] and soak['leases_after'] == 0
assert soak['shutdown']['clean'] and soak['shutdown']['pending_workers'] == 0
assert soak['ui_ticks'] > 100
for case in soak['cases'][1:]:
    for artifact in case['result']['artifacts']:
        assert verify_image(artifact['path'], artifact['width'], artifact['height'])['sha256'] == artifact['sha256']

constraints = [
    'User chose to document remaining RAM headroom; safety margins are unchanged.',
    'Real offload, actual GGUF/media contention, actual-model cancellation, diffusion-model OOM/recovery, successful outpaint Kernel commit and fresh MAX replay remain RAM-limited/unvalidated.',
    'Original native real-model suite exited unexpectedly after four verified jobs; cause unresolved. Its outpaint record is INTERRUPTED with no artifacts.',
    'Older interrupted outpaint temp folder remains quarantined because automatic approval review rejected removal with blocked by policy and no specific reason.',
    'No approved video/SVD/motion weights, live model-backed ComfyUI, ffmpeg/ffprobe or physical remote-GPU validation.',
    'LoRA/control/quantization/neural-upscale/background-removal providers unavailable; SDXL/SVD are reviewed code paths without actual local model tests.',
    'Soak is actual bounded CUDA OOM plus fifteen controlled Pillow recoveries, not long-term diffusion stability.',
    'Local Windows packaging only; unsigned/unpublished, no installer upgrade or other-OS/physical-device validation.',
]
value = {'schema': 1, 'phase': 9,
    'status': 'complete_for_validated_local_image_scope_with_documented_constraints',
    'phase10_ready_for_validated_api_scope': True, 'phase10_started': False,
    'created_utc': datetime.now(timezone.utc).isoformat(), 'source_sha256': source_sha,
    'report': str(report_path), 'report_items': len(numbers),
    'audit': str(ROOT / 'docs/generative-media-lab-audit.md'),
    'regression': {'passed': int(match[1]), 'subtests_passed': int(match[2]), 'seconds': float(match[3]), 'log': 'build/phase9-post-audit-full-tests.log', 'targeted_passed': 48},
    'package': package, 'outside_checkout_startup': startup,
    'download': {'receipt': 'build/phase9-model-download-receipt.json', 'files_rehashed': 14, 'bytes': 2581668541, 'revision': receipt['revision']},
    'actual_model': {'model_id': 'sd-turbo-fp16', 'model_hash': model['sha256'], 'artifact_files_redecoded_rehashed': artifacts,
        'benchmark_configurations': 9, 'benchmark_successes': 5, 'benchmark_admission_refusals': 4, 'benchmark_ooms': 0,
        'peak_allocated_vram_mb': max(row['peak_vram_mb'] for row in successful),
        'peak_owned_tree_rss_mb': max(row['peak_ram_mb'] for row in successful),
        'representative_total_ms': real['cases'][0]['wall_ms'],
        'source_receipts': ['build/phase9-real-image-process-tree.json', 'build/phase9-real-benchmark.json', 'build/phase9-real-ui-suite.json']},
    'safety_soak': {'receipt': 'build/phase9-safety-soak.json', 'actual_cuda_allocator_oom': True,
        'diffusion_model_loaded_for_oom': False, 'controlled_recovery_images': 15,
        'ui_ticks': soak['ui_ticks'], 'combined_event_and_action_p95_ms': soak['fast_action_p95_ms'],
        'rss_growth_bytes': soak['rss_after'] - soak['rss_before'], 'owned_workers_after': 0, 'leases_after': 0, 'clean_shutdown': True},
    'startup_idle_receipt': 'build/phase9-startup-idle-quiet.json',
    'video_status': 'VIDEO PROVIDER UNAVAILABLE', 'remaining_constraints': constraints}
(ROOT / 'build/phase9-completion.json').write_text(json.dumps(value, indent=2), encoding='utf-8')
print(json.dumps({'status': value['status'], 'phase10_ready_for_validated_api_scope': True, 'report_items': len(numbers),
    'tests': int(match[1]), 'subtests': int(match[2]), 'verified_actual_model_artifacts': len(artifacts),
    'source_sha256': source_sha, 'output': 'build/phase9-completion.json'}, indent=2))
