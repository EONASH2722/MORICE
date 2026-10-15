"""Bounded source/dependency inventory supporting the manual Phase 9 audit."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
fingerprint = hashlib.sha256()
modules = []
for path in sorted((ROOT / 'morice').rglob('*.py')):
    ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    fingerprint.update(str(path.relative_to(ROOT)).encode())
    fingerprint.update(path.read_bytes())
    modules.append(str(path.relative_to(ROOT)))

heavy = []
for path in (ROOT / 'morice/media_lab').glob('*.py'):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    # A top-level import would run in the desktop during ordinary module use.
    for node in tree.body:
        names = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
        heavy.extend((str(path.relative_to(ROOT)), name) for name in names if name.split('.')[0] in {'torch', 'diffusers', 'transformers', 'accelerate'})
assert not heavy, heavy

dependency_checks = []
for label, python in [('desktop', Path(sys.executable)), ('external_media', Path('E:/MORICE_DATA/media-python/Scripts/python.exe'))]:
    completed = subprocess.run([str(python), '-m', 'pip', 'check'], capture_output=True, text=True, timeout=45)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    dependency_checks.append({'environment': label, 'python': str(python), 'exit_code': completed.returncode, 'output': completed.stdout.strip()})

value = {'schema': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'AST parsing, source inventory and dependency consistency; manual security conclusions are in docs/generative-media-lab-audit.md',
    'source_sha256': fingerprint.hexdigest(), 'module_count': len(modules),
    'media_module_count': len(list((ROOT / 'morice/media_lab').glob('*.py'))),
    'heavy_top_level_media_imports': heavy, 'pip_checks': dependency_checks}
output = ROOT / 'build/phase9-final-audit.json'
output.write_text(json.dumps(value, indent=2), encoding='utf-8')
print(json.dumps(value, indent=2))
