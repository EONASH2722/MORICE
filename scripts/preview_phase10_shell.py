"""Owned isolated Qt preview of the staged Renovation shell; not acceptance."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
os.environ.update(QT_QPA_PLATFORM='windows' if '--native' in sys.argv else 'offscreen', MORICE_PRELOAD='0', MORICE_DISABLE_SESSION='1', MORICE_DISABLE_RECOVERY='1', MORICE_START_AWAKE='1', MORICE_NODE_NETWORK='0', MORICE_REDUCE_MOTION='1')

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from morice import settings
import morice.runtime_services as module
from morice.runtime_services import RuntimeServices
from morice.pyside_app import create_application_window

output = Path(sys.argv[sys.argv.index('--output')+1]) if '--output' in sys.argv else ROOT / ('build/phase10-all-workspaces-preview' if '--all' in sys.argv else 'build/phase10-native-preview' if '--native' in sys.argv else 'build/phase10-staged-preview'); output.mkdir(parents=True, exist_ok=True)
app = QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory(prefix='morice-renovation-preview-') as directory:
    root = Path(directory); os.environ.update(APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local'),MORICE_LOCAL_DATA_DIR=str(root/'data'))
    with patch('morice.settings._settings_dir', return_value=str(root / 'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS, 'tts_enabled': 'false', 'stt_enabled': 'false', 'pet_enabled': 'false'})
        runtime = RuntimeServices(root / 'runtime', project_root=ROOT); module._RUNTIME_SERVICES = runtime
        window = create_application_window(runtime, runtime.start()); window.resize(1366, 840); window.show(); app.processEvents()
        from PySide6.QtGui import QFontInfo
        evidence = {'status': 'DEVELOPMENT_PREVIEW_UNPUBLISHED', 'production_window_factory':True, 'migrated_routes': list(window.routes), 'screenshots': {}, 'qt_platform': app.platformName(), 'font_resolved': QFontInfo(window.font()).family()}
        for route in (tuple(window.navigation.buttons) if '--all' in sys.argv else ('home', 'chats', 'settings', 'spatial')):
            window.navigate(route)
            assert window.active_route == route, window.status_line.text()
            if route == 'spatial':
                runtime.spatial.set_pair('Chennai', 'New York'); window.routes[route].set_context(runtime.spatial.snapshot())
            for _ in range(40):
                app.processEvents()
                if window.ui_bridge.diagnostics()['pending_deliveries'] == 0: break
                QTest.qWait(25)
            app.processEvents(); target = output / (route + '.png'); assert window.grab().save(str(target))
            evidence['screenshots'][route] = str(target)
        evidence['spatial_actual_result'] = runtime.spatial.snapshot()['result']
        evidence['migrated_routes'] = list(window.routes)
        evidence['bridge'] = window.ui_bridge.diagnostics(); evidence['effects'] = window.effect_clock.diagnostics()
        window.close(); app.processEvents(); runtime.shutdown(); evidence['shutdown'] = runtime.shutdown_report
        assert evidence['shutdown']['clean']
        (output / 'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        print(json.dumps({key: evidence[key] for key in ('status', 'migrated_routes', 'screenshots', 'shutdown')}))
