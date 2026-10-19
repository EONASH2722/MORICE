"""Native Project save/run and Research experiment evidence in an owned profile.

Uses the deterministic addition scaffold and real scientific model. No language
model, public network, existing user project, or real user profile is required.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'build/workspace-flows/evidence.json')
    args = parser.parse_args(); output = args.output.resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='morice-native-workflows-') as directory:
        profile = Path(directory)
        os.environ.update(APPDATA=str(profile/'roaming'), LOCALAPPDATA=str(profile/'local'),
            MORICE_LOCAL_DATA_DIR=str(profile/'data'), MORICE_DISABLE_SESSION='1', MORICE_DISABLE_RECOVERY='1',
            MORICE_DISABLE_FIRST_RUN='1', MORICE_PRELOAD='0', MORICE_NODE_NETWORK='0',
            MORICE_REDUCE_MOTION='1', MORICE_START_AWAKE='1', QT_QPA_PLATFORM='windows')
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from morice import settings
        from morice.runtime_services import RuntimeServices
        from morice.pyside_app import create_application_window
        from morice.version import VERSION
        app = QApplication.instance() or QApplication([])
        def wait(predicate, timeout=30):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                app.processEvents()
                if predicate(): return
                QTest.qWait(15)
            raise AssertionError('Native workflow did not finish in its bounded timeout.')
        record = {'version': VERSION, 'scope': 'Native Qt actions, deterministic scaffold, actual saved files and actual scientific runs. No model inference claim.', 'screenshots': []}
        fingerprint = hashlib.sha256()
        for source in sorted((ROOT/'morice').rglob('*.py')):
            fingerprint.update(str(source.relative_to(ROOT)).encode()); fingerprint.update(source.read_bytes())
        record['source_sha256'] = fingerprint.hexdigest()
        with patch('morice.settings._settings_dir', return_value=str(profile/'settings')):
            settings.save_settings({**settings.DEFAULT_SETTINGS, 'tts_enabled':'false', 'stt_enabled':'false', 'pet_enabled':'false'})
            runtime = RuntimeServices(profile/'runtime', project_root=ROOT)
            with patch('morice.runtime_services._RUNTIME_SERVICES', runtime):
                window = create_application_window(runtime, runtime.start()); window.resize(1366, 840); window.show()
                def capture(name):
                    QTest.qWait(150); app.processEvents()
                    path = output.parent/(name+'.png'); assert window.grab().save(str(path))
                    record['screenshots'].append(str(path))
                try:
                    window.navigate('projects'); capture('01-project-start')
                    destination = profile/'addition'; window.project_folder = str(destination); window.project_folder_input.setText(str(destination))
                    window._set_project_access('folder')
                    window.input.setText('Build a simple Python addition calculator'); window.send_btn.click()
                    wait(lambda: not window.is_busy and bool(window.pending_project_patch))
                    assert window.active_route == 'projects' and not (destination/'main.py').exists()
                    capture('02-project-review')
                    window.resize(720, 500); QTest.qWait(150)
                    assert window.changes_apply_btn.height() >= 32
                    assert not window.changes_apply_btn.visibleRegion().isEmpty()
                    assert window.changes_apply_btn.mapTo(window, window.changes_apply_btn.rect().bottomRight()).y() < window.height()
                    capture('02-project-review-compact'); window.resize(1366, 840)
                    window.changes_apply_btn.click()
                    wait(lambda: not window.pending_project_patch and not window._project_build_id and (destination/'main.py').is_file(), 90)
                    result = subprocess.run([sys.executable, str(destination/'main.py'), '2', '3'], capture_output=True,
                        text=True, timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    assert result.returncode == 0 and result.stdout.strip() == '5'
                    assert (destination/'tests/test_main.py').is_file() and not (destination/'requirements.txt').exists()
                    record['project'] = {'review_preserved': True, 'source_files_written': True, 'output': result.stdout.strip(),
                        'session_status': runtime.autonomous_builder.project_runtime.load(window._last_project_build_id).status,
                        'same_kernel': runtime.autonomous_builder.project_runtime.kernel is runtime.kernel}
                    window._set_project_workspace_tab(0)
                    entries = window.project_file_tree.findItems('main.py', Qt.MatchExactly | Qt.MatchRecursive)
                    assert entries; window.project_file_tree.setCurrentItem(entries[0])
                    assert 'def add' in window.project_file_preview.toPlainText()
                    capture('03-project-files')
                    window.navigate('research'); view = window.routes['research']; editor = view.editor
                    editor.entry_mode.setCurrentIndex(1); editor.model.setCurrentIndex(editor.model.findData('ideal_mixture_density'))
                    editor.title.setText('Compare ideal component densities')
                    for name, value in {'density_a':'1000','density_b':'2000','fraction_a':'0.5'}.items(): editor.inputs[name].setText(value)
                    editor.kind.setCurrentIndex(1); editor.axis.setCurrentIndex(editor.axis.findData('fraction_a'))
                    editor.low.setText('0'); editor.high.setText('1'); editor.points.setValue(5)
                    editor.prepare_button.click()
                    wait(lambda: not view._bridge_preparing and bool(view.selected_id()) and view.run_button.isEnabled())
                    identifier = view.selected_id(); capture('04-experiment-review')
                    window.resize(720, 500); QTest.qWait(150)
                    assert view.run_button.height() >= 32
                    assert not view.run_button.visibleRegion().isEmpty()
                    assert view.run_button.mapTo(window, view.run_button.rect().bottomRight()).y() < window.height()
                    capture('04-experiment-review-compact'); window.resize(1366, 840)
                    view.run_button.click(); wait(lambda: view.manager.get(identifier)['status'] == 'COMPLETED', 30)
                    view.refresh(); wait(lambda: not view._meta_reading and not view._result_reading and view.runs.rowCount() == 5)
                    row = view.manager.get(identifier, True)
                    assert row['runs'][0]['outputs']['density'] == 2000 and row['runs'][-1]['outputs']['density'] == 1000
                    record['experiment'] = {'status':row['status'], 'actual_runs':len(row['runs']),
                        'densities':[run['outputs']['density'] for run in row['runs']], 'same_kernel':view.runtime.kernel is runtime.kernel}
                    view.tabs.setCurrentIndex(next(i for i in range(view.tabs.count()) if view.tabs.tabText(i) == 'Results'))
                    capture('05-experiment-results')
                    for route in ('projects', 'research'):
                        window.resize(720, 500); window.navigate(route)
                        if route == 'research': view.tabs.setCurrentIndex(0)
                        capture('06-compact-'+route)
                    record['completed'] = True
                finally:
                    window.close(); app.processEvents(); runtime.shutdown(); record['shutdown'] = runtime.shutdown_report
                    output.write_text(json.dumps(record, indent=2), encoding='utf-8')
        assert record['shutdown']['clean'] and record['completed']
        print(json.dumps(record), flush=True)


if __name__ == '__main__': main()
