"""Exact wheel source/data parity and owned native UI from an extracted wheel.

This proves the production window factory can run from the exact wheel with
installed dependencies. Clean dependency installation is a separate gate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
web_fingerprint=hashlib.sha256()
for path in sorted((ROOT/'morice/assets/web').rglob('*')):
    if path.is_file():web_fingerprint.update(str(path.relative_to(ROOT)).encode());web_fingerprint.update(path.read_bytes())
parser = argparse.ArgumentParser(); parser.add_argument('--wheel', required=True); parser.add_argument('--output', default='build/phase10-wheel-current-evidence.json'); args = parser.parse_args()
wheel = Path(args.wheel).resolve(); modules = []; assets = []; fingerprint = hashlib.sha256()
with zipfile.ZipFile(wheel) as archive:
    assert archive.testzip() is None
    from packaging.requirements import Requirement
    metadata = archive.read(next(name for name in archive.namelist() if name.endswith('.dist-info/METADATA'))).decode()
    from email.parser import Parser
    description=Parser().parsestr(metadata).get_payload()
    assert description.replace('\r\n','\n').strip()==(ROOT/'README.md').read_text(encoding='utf-8').replace('\r\n','\n').strip(),'Wheel README differs from the final repository README.'
    requirements = [Requirement(line.removeprefix('Requires-Dist: ')) for line in metadata.splitlines() if line.startswith('Requires-Dist: ')]
    assert any(requirement.name == 'psutil' and (requirement.marker is None or requirement.marker.evaluate({'platform_system':'Windows','extra':''}))
               for requirement in requirements), 'Windows process ownership requires psutil in base wheel metadata.'
    for source in sorted((ROOT/'morice').rglob('*.py')):
        name = source.relative_to(ROOT).as_posix(); content = source.read_bytes(); assert archive.read(name) == content, name
        modules.append(name); fingerprint.update(str(source.relative_to(ROOT)).encode()); fingerprint.update(content)
    for source in [*(ROOT/'morice/assets/spatial').iterdir(), *(ROOT/'morice/assets/web').rglob('*'), ROOT/'morice/assets/morice-logo-rgb.png', ROOT/'morice/assets/morice_logo.ico']:
        if source.is_file():
            name = source.relative_to(ROOT).as_posix(); assert archive.read(name) == source.read_bytes(), name; assets.append(name)
    for name in archive.namelist():
        assert not name.endswith(('.gguf', '.safetensors', '.env', '.log')), name
        assert not name.endswith('.sqlite3') or name == 'morice/assets/spatial/cities.sqlite3', name
        assert 'MORICE_DATA' not in name and not name.endswith(('settings.json', 'action-journal.json')), name
    with tempfile.TemporaryDirectory(prefix='morice-wheel-native-') as temporary:
        base = Path(temporary); package = base/'package'; package.mkdir(); archive.extractall(package)
        smoke = r'''
import json, os, sqlite3, subprocess, sys, time
from pathlib import Path
from unittest.mock import patch
package=Path(sys.argv[1]); profile=Path(sys.argv[2]); sys.path.insert(0,str(package))
os.environ.update(QT_QPA_PLATFORM='windows', MORICE_PRELOAD='0', MORICE_DISABLE_SESSION='1', MORICE_DISABLE_RECOVERY='1', MORICE_START_AWAKE='1', MORICE_NODE_NETWORK='0', MORICE_REDUCE_MOTION='1', MORICE_LOCAL_DATA_DIR=str(profile/'data'))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from morice import settings
import morice.runtime_services as services
from morice.runtime_services import RuntimeServices
from morice.pyside_app import create_application_window
from morice.ui_next.icons import MARKS
from morice.process_ownership import spawn_owned_process,reap_owned_job
import morice
assert Path(morice.__file__).is_relative_to(package)
managed=spawn_owned_process([str(Path(os.environ['SystemRoot'])/'System32/cmd.exe'),'/d','/c','exit','0'],
    stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
try:
 managed.communicate(timeout=5);assert managed.returncode==0
finally: managed_reaped=reap_owned_job(managed)
assert managed_reaped is True
database=package/'morice/assets/spatial/cities.sqlite3'
with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db: assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
app=QApplication([])
with patch('morice.settings._settings_dir',return_value=str(profile/'settings')):
 settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false','pet_enabled':'false'})
 runtime=RuntimeServices(profile/'runtime',project_root=package); services._RUNTIME_SERVICES=runtime
 window=create_application_window(runtime,runtime.start()); window.show(); app.processEvents(); routes=[]
 try:
  for name in window.navigation.buttons:
   window.navigate(name); assert window.active_route==name, window.status_line.text()
   assert window.navigation.isVisible()!=window.action_deck.isVisible(),name
   assert window.action_deck.isVisible()==(name=='home'),name
   deadline=time.monotonic()+10
   while window.ui_bridge.diagnostics()['pending_deliveries'] and time.monotonic()<deadline: app.processEvents(); QTest.qWait(10)
   assert not window.ui_bridge.diagnostics()['pending_deliveries'], name
   routes.append(name)
  context=runtime.spatial.set_pair('Chennai','New York'); assert context['origin']['identifier']=='geonames:1264527' and context['destination']['identifier']=='geonames:5128581'
  assert context['result']['metres']>10000000 and context['result']['provenance']=='COMPUTED'
  window.navigate('home'); assert window.grab().save(str(profile/'wheel-home.png'))
  assert not any(name in sys.modules for name in ('torch','diffusers','transformers'))
 finally: window.close(); app.processEvents(); runtime.shutdown()
 assert runtime.shutdown_report['clean']
 print(json.dumps({'package':str(morice.__file__),'production_window_class':type(window).__name__,'routes':routes,'authored_icons':len(MARKS),'spatial_actual_metres':context['result']['metres'],'qt_platform':app.platformName(),'owned_windows_job_reaped':managed_reaped,'shutdown':runtime.shutdown_report}))
'''
        environment = {key: value for key, value in os.environ.items() if key not in ('PYTHONPATH', 'PYTHONHOME')}
        environment.update(APPDATA=str(base/'roaming'), LOCALAPPDATA=str(base/'local'),
                           MORICE_RUNTIME_DIR=str(base/'runtime'), MORICE_LOCAL_DATA_DIR=str(base/'data'))
        result = subprocess.run([sys.executable, '-I', '-c', smoke, str(package), str(base/'profile')], cwd=base, env=environment, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout+'\n'+result.stderr
        evidence = {'status': 'PRODUCTION_FACTORY_WHEEL_PASSED', 'production_window_factory': 'morice.pyside_app.create_application_window', 'wheel': str(wheel), 'bytes': wheel.stat().st_size,
            'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'source_sha256': fingerprint.hexdigest(), 'web_assets_sha256':web_fingerprint.hexdigest(), 'source_equal_modules': len(modules), 'asset_equal_files': assets,
            'native_extracted_wheel': json.loads(result.stdout.splitlines()[-1]), 'scope': 'Extracted exact wheel, outside repository cwd, isolated profile, installed dependency runtime; not a clean dependency install or final frozen release.'}
        output = ROOT/args.output; output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(evidence, indent=2), encoding='utf-8'); print(json.dumps(evidence), flush=True)
