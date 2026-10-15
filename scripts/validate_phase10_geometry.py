"""Owned native Qt DPI/window geometry, independent of desktop automation."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
parser = argparse.ArgumentParser(); parser.add_argument('--child', action='store_true'); parser.add_argument('--probe',action='store_true')
parser.add_argument('--factor',type=float,default=1); parser.add_argument('--size',default='1366x768'); parser.add_argument('--font',type=float,default=1)
parser.add_argument('--output'); args = parser.parse_args()
os.environ.update(QT_QPA_PLATFORM='windows', QT_SCALE_FACTOR=str(args.factor), MORICE_PRELOAD='0', MORICE_DISABLE_SESSION='1',
    MORICE_DISABLE_RECOVERY='1', MORICE_START_AWAKE='1', MORICE_NODE_NETWORK='0', MORICE_REDUCE_MOTION='1')

if not args.child and not args.probe:
    probe = subprocess.run([sys.executable,__file__,'--probe'],cwd=ROOT,capture_output=True,text=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert probe.returncode == 0, probe.stderr
    initial = json.loads(probe.stdout.strip().splitlines()[-1]); base = initial['device_pixel_ratio']
    directory = ROOT/'build/phase10-geometry'; directory.mkdir(parents=True,exist_ok=True); rows = []
    matrix = [(scale,'1366x768',1.) for scale in (1,1.25,1.5,1.75,2)] + [(1.25,size,1.) for size in ('896x650','1920x1080','2560x1440','3840x2160','2560x1080')] + [(1.25,'1366x768',font) for font in (.8,1.3,1.8)]
    for index,(scale,size,font) in enumerate(matrix):
        output = directory/f'case-{index}'; output.mkdir(exist_ok=True)
        result = subprocess.run([sys.executable,__file__,'--child','--factor',str(scale/base),'--size',size,'--font',str(font),'--output',str(output)],
            cwd=ROOT,capture_output=True,text=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (output/'stdout.log').write_text(result.stdout,encoding='utf-8'); (output/'stderr.log').write_text(result.stderr,encoding='utf-8')
        row = {'requested_scale':scale,'logical_window':size,'font_scale':font,'exit_code':result.returncode,'evidence':str(output/'evidence.json')}
        rows.append(row); print(json.dumps(row),flush=True)
    (directory/'matrix.json').write_text(json.dumps({'scope':'Owned native Qt backing/widget captures at isolated process scale factors and logical window sizes. OS display settings and physical monitors were not changed.', 'probe':initial,'rows':rows},indent=2))
    sys.exit(1 if any(row['exit_code'] for row in rows) else 0)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtTest import QTest
app = QApplication([])
if args.probe:
    screen = app.primaryScreen(); print(json.dumps({'device_pixel_ratio':screen.devicePixelRatio(), 'available_geometry':screen.availableGeometry().getRect(), 'platform':app.platformName()})); sys.exit(0)

from morice import settings
from morice.runtime_services import RuntimeServices
from morice.pyside_app import create_application_window

output = Path(args.output); output.mkdir(parents=True, exist_ok=True); width,height = map(int,args.size.split('x')); rows = []; issues = []
with tempfile.TemporaryDirectory(prefix='morice-dpi-validation-') as directory:
    root = Path(directory); os.environ.update(APPDATA=str(root/'roaming'), LOCALAPPDATA=str(root/'local'), MORICE_LOCAL_DATA_DIR=str(root/'data'))
    with patch('morice.settings._settings_dir',return_value=str(root/'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false','pet_enabled':'false'})
        runtime = RuntimeServices(root/'runtime',project_root=ROOT)
        with patch('morice.runtime_services._RUNTIME_SERVICES',runtime):
            window = create_application_window(runtime,runtime.start()); window.resize(width,height); window.show(); app.processEvents()
            window.theme_engine.update(font_scale=args.font)
            try:
                for route in ('home','chats','spatial','settings','projects','media','voice','artifacts'):
                    window.navigate(route); assert window.active_route == route, window.status_line.text()
                    deadline = time.monotonic()+5
                    while time.monotonic()<deadline and window.ui_bridge.diagnostics()['pending_deliveries']:
                        app.processEvents(); QTest.qWait(10)
                    app.processEvents(); target = output/(route+'.png'); assert window.grab().save(str(target))
                    row = {'route':route,'actual_window':[window.width(),window.height()], 'content':[window.route_stack.width(),window.route_stack.height()],
                        'dpr':window.devicePixelRatioF(),'screenshot':str(target)}
                    rows.append(row)
                    if window.width()>width or window.height()>height: issues.append({'route':route,'reason':'Window minimum constraints exceed requested logical size.','actual':row['actual_window']})
                    if route in {'home','chats','projects'}:
                        visible_rectangles=[]
                        for name in ('input','attach_btn','voice_btn','project_selector_btn','model_selector_btn','send_btn'):
                            field = getattr(window,name)
                            if name in {'input','send_btn'} and not field.isVisible(): issues.append({'route':route,'control':name,'reason':'Required composer control is hidden.'})
                            if not field.isVisible(): continue
                            if field.width()<20 or field.height()<20: issues.append({'route':route,'control':name,'reason':'Visible control collapsed.'})
                            bounds=QRect(field.mapTo(window,field.rect().topLeft()),field.size());visible_rectangles.append((name,bounds))
                            if not window.rect().contains(bounds): issues.append({'route':route,'control':name,'reason':'Composer hit area extends outside the window.','bounds':bounds.getRect()})
                            if name!='input':
                                text=field.text();needed=field.fontMetrics().horizontalAdvance(text)+(field.iconSize().width()+(6 if text else 0) if not field.icon().isNull() else 0)+(12 if field.property('icon_only') else 24)
                                if needed>field.width(): issues.append({'route':route,'control':name,'reason':'Composer label/icon does not fit its hit area.','needed':needed,'width':field.width()})
                        for index,(name,bounds) in enumerate(visible_rectangles):
                            for other,rectangle in visible_rectangles[index+1:]:
                                if bounds.intersects(rectangle): issues.append({'route':route,'control':name,'other':other,'reason':'Composer hit areas overlap.'})
                    if window.navigation.expanded:
                        for name,button in window.navigation.buttons.items():
                            if button.isVisible() and button.fontMetrics().horizontalAdvance(button.text())+button.iconSize().width()+30>button.width():
                                issues.append({'route':route,'control':'navigation:'+name,'reason':'Navigation label/icon is clipped.'})
                    else:
                        for name,button in window.navigation.buttons.items():
                            if button.isVisible() and (not button.accessibleName() or button.icon().isNull()): issues.append({'route':route,'control':'navigation:'+name,'reason':'Collapsed route lacks an accessible name or authored icon.'})
                evidence = {'scope':'Owned native Qt DPI/window geometry, not physical monitor removal or external application interaction.',
                    'requested_window':[width,height], 'font_scale':args.font,'actual_dpr':window.devicePixelRatioF(),'rows':rows,'issues':issues}
                window.close(); app.processEvents(); runtime.shutdown(); evidence['shutdown'] = runtime.shutdown_report
                (output/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
                assert evidence['shutdown']['clean']; print(json.dumps({'issues':issues,'shutdown':evidence['shutdown']}),flush=True)
                if issues: sys.exit(2)
            finally: window.close(); app.processEvents(); runtime.shutdown()
