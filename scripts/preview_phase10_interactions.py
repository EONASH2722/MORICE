"""Native owned-window acceptance for the custom icon/glow/appearance revision."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
os.environ.update(QT_QPA_PLATFORM='windows', MORICE_PRELOAD='0', MORICE_DISABLE_SESSION='1', MORICE_DISABLE_RECOVERY='1', MORICE_START_AWAKE='1', MORICE_NODE_NETWORK='0', MORICE_REDUCE_MOTION='1')
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QEvent
from PySide6.QtGui import QColor, QImage, QPainter, QFont, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from morice import settings
from morice.runtime_services import RuntimeServices
from morice.ui_next.shell import RenovatedWindow
from morice.ui_next.effects import ActionCard
from morice.ui_next.icons import MARKS, draw_mark

output = ROOT/'build/phase10-interaction-preview'; output.mkdir(parents=True, exist_ok=True)
app = QApplication([]); evidence = {'scope': 'Owned native Qt actions and widget captures; no external application, physical audio or release validation.', 'status': 'FOCUSED_UI_ACCEPTANCE', 'screenshots': {}}
with tempfile.TemporaryDirectory(prefix='morice-custom-ui-') as directory:
    root = Path(directory); os.environ['MORICE_LOCAL_DATA_DIR'] = str(root/'data')
    with patch('morice.settings._settings_dir', return_value=str(root/'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS, 'tts_enabled': 'false', 'stt_enabled': 'false', 'pet_enabled': 'false'})
        runtime = RuntimeServices(root/'runtime', project_root=ROOT)
        with patch('morice.runtime_services._RUNTIME_SERVICES', runtime):
            window = RenovatedWindow(runtime, runtime.start()); window.show(); window.activateWindow(); app.processEvents()
            def capture(name):
                app.processEvents(); path = output/(name+'.png'); assert window.grab().save(str(path)); evidence['screenshots'][name] = str(path)
            try:
                window.theme_engine.update(reduced_motion=False, cursor_glow='NORMAL', cursor_trail=False, persist=False)
                capture('home')
                cards = window.routes['home'].findChildren(ActionCard); assert len(cards) == 3
                # Native paint, controlled owned-widget event delivery. OS focus
                # and an unrelated application's physical cursor are not proof.
                point = QPoint(40, 30)
                QApplication.sendEvent(cards[0], QMouseEvent(QEvent.MouseMove, QPointF(point), QPointF(cards[0].mapToGlobal(point)), Qt.NoButton, Qt.NoButton, Qt.NoModifier))
                QTest.qWait(160)
                assert window.cursor_lighting._point is not None; capture('cursor-halo')
                settle_started = time.monotonic()
                while window.effect_clock.timer.isActive() and time.monotonic()-settle_started < 1.8: QTest.qWait(20)
                assert not window.effect_clock.timer.isActive(), window.effect_clock.diagnostics()
                evidence['cursor'] = {'paint_count': window.cursor_lighting.paint_count, 'last_dirty_pixels': window.cursor_lighting.last_dirty_pixels, 'clock_stopped_after_settle': True, 'shared_effects_settle_ms': (time.monotonic()-settle_started)*1000, 'input_source': 'Controlled QMouseEvent delivered to owned QWidget; native rendering.'}
                QTest.mouseClick(cards[1], Qt.LeftButton); assert window.active_route == 'projects'
                evidence['home_card_opened_existing_projects'] = True
                window.navigate('home'); QTest.mouseClick(window.navigation.more, Qt.LeftButton); assert window.navigation.more_expanded; capture('more-workspaces')
                window.navigate('settings'); appearance = window.routes['settings'].categories['Appearance']
                window.routes['settings'].list.setCurrentRow(0); capture('appearance-simple')
                QTest.mouseClick(appearance.advanced_toggle, Qt.LeftButton); assert appearance.advanced.isVisible(); capture('appearance-advanced')
                for preset in ('ICE', 'AMETHYST'):
                    window.theme_engine.update(preset=preset, persist=False); window.navigate('home'); capture('home-'+preset.lower())
                window.theme_engine.update(preset='MORICE', reduced_motion=True, persist=False); window.navigate('home'); QTest.qWait(100)
                assert not window.effect_clock.timer.isActive(); evidence['reduced_motion_idle_clock_stopped'] = True
                evidence['actual_dpr'] = window.devicePixelRatioF(); evidence['brand_sha256'] = hashlib.sha256((ROOT/'morice/assets/morice-logo-rgb.png').read_bytes()).hexdigest()
                # Gallery uses the exact authored renderer shipped in the UI.
                names = list(MARKS); columns = 8; image = QImage(1120, ((len(names)+columns-1)//columns)*105, QImage.Format_ARGB32_Premultiplied); image.fill(QColor('#0b101b'))
                painter = QPainter(image); painter.setFont(QFont('Segoe UI', 9))
                for index, name in enumerate(names):
                    x = (index%columns)*140; y = (index//columns)*105
                    draw_mark(painter, name, QRectF(x+50, y+14, 40, 40), '#85d6ed'); painter.setPen(QColor('#cdd9e8')); painter.drawText(QRectF(x+3, y+64, 134, 25), Qt.AlignCenter, name)
                painter.end(); assert image.save(str(output/'authored-icon-gallery.png'))
                evidence['authored_icon_count'] = len(names)
            finally:
                window.close(); app.processEvents(); runtime.shutdown(); evidence['shutdown'] = runtime.shutdown_report
            assert evidence['shutdown']['clean']
            digest = hashlib.sha256()
            for path in sorted((ROOT/'morice').rglob('*.py')): digest.update(str(path.relative_to(ROOT)).encode()); digest.update(path.read_bytes())
            evidence['source_sha256'] = digest.hexdigest()
            (output/'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print(json.dumps(evidence), flush=True)
