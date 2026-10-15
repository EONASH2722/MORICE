"""Native, isolated maximize/restore and composer regression evidence."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import faulthandler
import hashlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
faulthandler.enable();faulthandler.dump_traceback_later(45,repeat=True)
sys.path.insert(0, str(ROOT))
os.environ.update(QT_QPA_PLATFORM='windows', MORICE_PRELOAD='0',
    MORICE_DISABLE_RECOVERY='1', MORICE_DISABLE_FIRST_RUN='1', MORICE_START_AWAKE='1', MORICE_NODE_NETWORK='0')
os.environ.pop('MORICE_DISABLE_SESSION', None)
os.environ.pop('MORICE_REDUCE_MOTION', None)
from PySide6.QtCore import QPoint, QRect, Qt, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtTest import QTest
from morice import settings
from morice.runtime_services import RuntimeServices
from morice.pyside_app import create_application_window
from morice.ui_next.appearance_profile import PRESETS

output = ROOT / 'build/theme-composer-native'
output.mkdir(parents=True, exist_ok=True)
app = QApplication([])
rows = []
theme_rows=[]
def settle(duration=.4):
    until = time.monotonic() + duration
    while time.monotonic() < until:
        app.processEvents(); QTest.qWait(10)

with tempfile.TemporaryDirectory(prefix='morice-theme-composer-') as directory:
    root = Path(directory)
    os.environ.update(APPDATA=str(root/'roaming'), LOCALAPPDATA=str(root/'local'), MORICE_LOCAL_DATA_DIR=str(root/'data'))
    with patch('morice.settings._settings_dir', return_value=str(root/'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS, 'tts_enabled':'false', 'stt_enabled':'false', 'pet_enabled':'false'})
        runtime = RuntimeServices(root/'runtime', project_root=ROOT)
        with patch('morice.runtime_services._RUNTIME_SERVICES', runtime):
            window = create_application_window(runtime, runtime.start())
            try:
                window.theme_engine.update(reduced_motion=True,persist=False)
                window.show(); window.activateWindow(); settle()
                for mode in ('normal', 'native-maximized', 'native-restored', 'maximized', 'restored'):
                    if mode == 'native-maximized':QWidget.showMaximized(window)
                    elif mode == 'native-restored':QWidget.showNormal(window)
                    elif mode == 'maximized': window.showMaximized()
                    elif mode == 'restored': window.showNormal()
                    settle()
                    controls = {}
                    for name in ('presentation_root', 'route_stack', 'composer', 'input', 'send_btn', 'action_deck', 'status_line'):
                        widget = getattr(window, name)
                        bounds = QRect(widget.mapTo(window, QPoint()), widget.size())
                        controls[name] = {'visible':widget.isVisible(), 'bounds':bounds.getRect(), 'inside':window.rect().contains(bounds), 'minimum_hint':widget.minimumSizeHint().toTuple()}
                        controls[name]['inside_screen']=window.screen().availableGeometry().contains(QRect(widget.mapToGlobal(QPoint()),widget.size()))
                    row = {'mode':mode, 'window':window.size().toTuple(), 'dpr':window.devicePixelRatioF(), 'controls':controls,
                        'minimum':window.minimumSize().toTuple(),'maximum':window.maximumSize().toTuple(),'position':window.pos().toTuple(),
                        'screen':window.screen().availableGeometry().getRect(),'native_minimum':window.windowHandle().minimumSize().toTuple(),
                        'layout_min':window.layout().minimumSize().toTuple(), 'root_min':window.presentation_root.minimumSizeHint().toTuple()}
                    rows.append(row); print(json.dumps(row),flush=True); window.grab().save(str(output/f'{mode}.png'))
                for preset in (PRESETS if '--gallery' in sys.argv else ('GLASS',)):
                    window.theme_engine.update(preset=preset, reduced_motion=False, persist=False)
                    window.activateWindow();settle(.2)
                    field=window.material_backdrop;phase=field._phase
                    field.paint_samples.clear();field.raster_samples.clear()
                    first=hashlib.sha256(bytes(field.material().toImage().constBits())).hexdigest()
                    settle(.6)
                    second=hashlib.sha256(bytes(field.material().toImage().constBits())).hexdigest()
                    window.grab().save(str(output/f'theme-{preset.lower()}.png'))
                    def timings(values):
                        ordered=sorted(values)
                        return {'samples':len(ordered),'p50_ms':ordered[len(ordered)//2] if ordered else None,'p95_ms':ordered[int((len(ordered)-1)*.95)] if ordered else None,'scope':'Owned widget paint/raster CPU, not compositor frame presentation.'}
                    theme_rows.append({'preset':preset,'phase_advanced':field._phase!=phase,'raster_pixels_changed':first!=second,'field':field.diagnostics(),'field_paint_cpu':timings(field.paint_samples),'diffuse_raster_cpu':timings(field.raster_samples)})
                window.navigate('home'); window.input.setFocus()
                window.input.clear();QTest.keyClicks(window.input,'2+3');QTest.mouseClick(window.send_btn,Qt.LeftButton);settle(.5)
                sent_ok=any(row['role']=='user' and row['content']=='2+3' for row in window.history) and any(row['role']=='assistant' and '5' in row['content'] for row in window.history)
                window.navigate('home');window.input.clear()
                QTest.keyClicks(window.input, 'Visible composer regression')
                typing_ok = window.input.toPlainText() == 'Visible composer regression'
                evidence = {'scope':'Owned native Qt window with normal session handling; no user profile or external desktop capture.', 'rows':rows, 'typing_ok':typing_ok,
                    'field':window.material_backdrop.diagnostics(), 'effect_clock':window.effect_clock.diagnostics()}
                evidence['themes']=theme_rows
                evidence['send_button_actual_calculation']=sent_ok
            finally:
                window.close(); settle(.1); runtime.shutdown()
                window.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); app.processEvents()
            evidence['shutdown'] = runtime.shutdown_report
            (output/'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print(json.dumps(evidence), flush=True)
            assert all(row['controls'][name]['visible'] and row['controls'][name]['inside'] and row['controls'][name]['inside_screen'] for row in rows for name in ('input','send_btn','composer')), 'Composer is not visible inside the screen and native window.'
            assert typing_ok and runtime.shutdown_report['clean']
            assert sent_ok,'The visible Send button did not complete the deterministic calculation.'
            assert all(row['phase_advanced'] and row['raster_pixels_changed'] for row in theme_rows),'A native theme did not visibly animate.'
