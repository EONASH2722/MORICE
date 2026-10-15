"""Capture only MORICE-owned native UI in an isolated demonstration profile."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix='morice-current-ui-') as temporary:
    profile = Path(temporary)
    os.environ.update(APPDATA=str(profile/'roaming'), LOCALAPPDATA=str(profile/'local'),
        MORICE_LOCAL_DATA_DIR=str(profile/'data'), MORICE_PRELOAD='0', MORICE_DISABLE_SESSION='1',
        MORICE_DISABLE_RECOVERY='1', MORICE_DISABLE_FIRST_RUN='1', MORICE_NODE_NETWORK='0',
        QT_QPA_PLATFORM='windows')
    os.environ.pop('MORICE_REDUCE_MOTION', None)
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from morice import settings
    from morice.runtime_services import RuntimeServices
    from morice.pyside_app import create_application_window
    from morice.version import VERSION

    app = QApplication([])
    def settle(seconds=.15):
        deadline = time.monotonic()+seconds
        while time.monotonic()<deadline: app.processEvents(); QTest.qWait(10)

    with patch('morice.settings._settings_dir', return_value=str(profile/'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS, 'tts_enabled':'false', 'stt_enabled':'false',
            'pet_enabled':'false', 'model_path':'', 'user_title':'', 'reduced_motion':'false'})
        runtime = RuntimeServices(profile/'runtime', project_root=ROOT)
        with patch('morice.runtime_services._RUNTIME_SERVICES', runtime):
            window = create_application_window(runtime, runtime.start()); window.resize(1366,840)
            files=[]; routes=[]
            def save(name, *, kind='native_owned_qt_window', fixture=None):
                settle()
                if window.composer.isVisible():
                    for control in (window.input,window.send_btn):
                        assert window.rect().contains(QRect(control.mapTo(window,QPoint()),control.size())),name
                assert window.navigation.isVisible()!=window.action_deck.isVisible()
                destination=output/name; assert window.grab().save(str(destination))
                files.append({'name':name,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
                    'bytes':destination.stat().st_size,'route':window.active_route,'preset':window.theme_engine.profile.preset,
                    'capture_kind':kind,'fixture':fixture})
                print(json.dumps({'capture':name,'route':window.active_route}),flush=True)
            try:
                window.show();window.activateWindow();settle(.5)
                window.theme_engine.update(preset='MORICE',reduced_motion=False,persist=False)
                for route in window.navigation.buttons:
                    window.navigate(route); deadline=time.monotonic()+20
                    while window.ui_bridge.diagnostics()['pending_deliveries'] and time.monotonic()<deadline:
                        app.processEvents();QTest.qWait(10)
                    assert window.active_route==route,window.status_line.text()
                    assert not window.ui_bridge.diagnostics()['pending_deliveries'],route
                    routes.append(route)
                    if route=='spatial':
                        runtime.spatial.set_pair('Chennai','New York')
                        window.routes[route].set_context(runtime.spatial.snapshot())
                    save('morice-'+route+'.png')
                window.navigate('home')
                for preset in ('GLASS','AMETHYST','ARCTIC'):
                    window.theme_engine.update(preset=preset,persist=False);save('morice-theme-'+preset.casefold()+'.png')
                window.theme_engine.update(preset='MORICE',persist=False)
                window._select_settings_category('Models');save('reviewer-project.png')
                window._select_settings_category('Personalization')
                window.title_input.setText('Sir');window.title_input.editingFinished.emit()
                save('reviewer-personalization.png',fixture='Owned demonstration form of address: Sir')
                window._set_chat_mode('normal');window.navigate('chats')
                for prompt,kind,name in (('Plot y=x^2-6*x+8','graph','reviewer-graph.png'),
                    ('Simulate 80 particles with gravity and elastic collisions.','physics','reviewer-simulation.png')):
                    assert window._handle_science_request(prompt)
                    deadline=time.monotonic()+30
                    while window.visualization_futures and time.monotonic()<deadline:app.processEvents();QTest.qWait(10)
                    assert not window.visualization_futures
                    index=len(window.science_artifacts)-1;assert index>=0
                    window._on_workspace_artifact_selected(index);window._open_workspace(kind)
                    settle(.3)
                    if kind=='physics':window.physics_canvas.set_running(False)
                    save(name,fixture='Actual deterministic computation: '+prompt)
                    window.navigate('chats')
                window.navigate('home');save('reviewer-home.png')
            finally:
                window.close();app.processEvents();runtime.shutdown()
            assert runtime.shutdown_report['clean']
            source=hashlib.sha256()
            for path in sorted((ROOT/'morice').rglob('*.py')):source.update(str(path.relative_to(ROOT)).encode());source.update(path.read_bytes())
            evidence={'version':VERSION,'source_sha256':source.hexdigest(),'platform':app.platformName(),
                'device_pixel_ratio':window.devicePixelRatioF(),'routes':routes,'files':files,'shutdown':runtime.shutdown_report,
                'scope':'Native owned application only, isolated demonstration data. Camera/microphone/providers remain off; graph, physics and geographic fixtures are actual computations. Stills do not certify frame pacing.'}
            (output/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
