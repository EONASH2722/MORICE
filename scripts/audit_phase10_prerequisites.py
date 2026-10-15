"""Audit the live Phase 1–9 contracts and capture the pre-renovation UI."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(QT_QPA_PLATFORM='offscreen', MORICE_PRELOAD='0', MORICE_DISABLE_SESSION='1', MORICE_DISABLE_RECOVERY='1', MORICE_START_AWAKE='1', MORICE_NODE_NETWORK='0', MORICE_REDUCE_MOTION='1')
required = {
    'Kernel': 'morice/kernel/execution.py', 'Registry': 'morice/kernel/registry.py',
    'ResourceManager': 'morice/kernel/resources.py', 'TaskGraph': 'morice/kernel/tasks.py',
    'EventBus': 'morice/kernel/events.py', 'permissions': 'morice/kernel/permissions.py',
    'AgentCoordinator': 'morice/agent_runtime/coordinator.py', 'WorkerManager': 'morice/agent_runtime/workers.py',
    'SharedTaskState': 'morice/agent_runtime/state.py', 'VerifiedActions': 'morice/action_runtime/runtime.py',
    'ActionJournal': 'morice/action_runtime/journal.py', 'Builder': 'morice/project_build/runtime.py',
    'Mesh': 'morice/device_mesh/runtime.py', 'Research': 'morice/research/runtime.py',
    'Ambient': 'morice/ambient/service.py', 'Security': 'morice/security/service.py',
    'Connectors': 'morice/connectors/registry.py', 'Media': 'morice/media_lab/runtime.py',
    'STT': 'morice/speech_runtime.py', 'TTS': 'morice/voice_runtime.py',
    'Wake': 'morice/wake_runtime.py', 'Listener': 'morice_wake_listener.py',
    'Model routing': 'morice/llm_client.py', 'Browser': 'morice/action_runtime/qt_browser.py',
    'Vision': 'morice/live_vision.py', 'History': 'morice/research/history.py',
    'Pet': 'morice/desktop_pet.py', 'Settings': 'morice/settings.py',
    'Files': 'morice/ui_workspace.py', 'Visualization': 'morice/visualization.py',
}
inventory = {}
for label, relative in required.items():
    path = ROOT / relative
    assert path.is_file(), relative
    data = path.read_bytes()
    tree = ast.parse(data.decode('utf-8-sig'))
    inventory[label] = {'path': relative, 'sha256': hashlib.sha256(data).hexdigest(),
        'classes': [n.name for n in tree.body if isinstance(n, ast.ClassDef)]}

from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from morice import settings
import morice.runtime_services as module
from morice.runtime_services import RuntimeServices
from morice.pyside_app import MoriceWindow

output = ROOT / 'build/phase10-baseline'
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='morice-phase10-baseline-') as directory:
    root = Path(directory)
    os.environ['MORICE_LOCAL_DATA_DIR'] = str(root / 'data')
    with patch('morice.settings._settings_dir', return_value=str(root / 'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS, 'tts_enabled': 'false', 'stt_enabled': 'false', 'desktop_pet_enabled': 'false'})
        app = QApplication.instance() or QApplication([])
        runtime = RuntimeServices(root / 'runtime', project_root=ROOT)
        module._RUNTIME_SERVICES = runtime
        window = MoriceWindow(runtime, runtime.start())
        window.resize(1366, 768); window.show(); app.processEvents()
        health = window._run_startup_health_check()
        assert not health.critical_failures
        assert runtime.agents.kernel is runtime.actions.kernel is runtime.kernel
        assert runtime.kernel.dispatch('python.calculate', {'expression': '2+3'}).success
        screenshot = output / 'old-home.png'
        assert window.grab().save(str(screenshot))
        objects = [{'class': w.metaObject().className(), 'name': w.objectName(),
            'text': w.text()[:120] if isinstance(w, QPushButton) else '',
            'visible': w.isVisible()} for w in window.findChildren(QWidget)]
        ui_tree = ast.parse((ROOT / 'morice/pyside_app.py').read_text(encoding='utf-8-sig'))
        old_class = next(n for n in ui_tree.body if isinstance(n, ast.ClassDef) and n.name == 'MoriceWindow')
        methods = [n.name for n in old_class.body if isinstance(n, ast.FunctionDef)]
        result = {'schema': 1, 'scope': 'Live source/real isolated old Qt window; no provider/model loads',
            'inventory': inventory, 'old_ui_lines': len((ROOT / 'morice/pyside_app.py').read_text().splitlines()),
            'controller_methods': methods, 'widget_count': len(objects), 'widgets': objects,
            'health_checks': len(health.checks), 'critical_failures': 0, 'roles': len(runtime.agents.roles.all()),
            'shared_authorities': True, 'screenshot': str(screenshot)}
        window.close(); app.processEvents(); runtime.shutdown()
        result['shutdown'] = runtime.shutdown_report
        assert result['shutdown']['clean'] and not runtime.kernel.resources.snapshot()
        (ROOT / 'build/phase10-prerequisites.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps({key: result[key] for key in ('old_ui_lines', 'widget_count', 'health_checks', 'roles', 'screenshot', 'shutdown')}))
