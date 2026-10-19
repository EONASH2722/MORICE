"""Actual native actions must produce files/runs through existing authorities."""
import json
import subprocess
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtTest import QTest
from test_renovation_workspaces_wake import app, window, pump


def project_folder(window, directory):
    window.navigate('projects')
    window.project_folder = str(directory)
    window.project_folder_input.setText(str(directory))
    window.routes['projects'].action.setCurrentIndex(0)
    window._set_project_access('folder')


def test_project_navigation_send_review_save_creates_actual_files(window, app, tmp_path):
    destination = tmp_path/'addition'
    window._set_chat_mode('normal'); project_folder(window, destination)
    assert window.chat_mode == 'project'
    with patch.object(window, '_run_research_request', side_effect=AssertionError('Build entered Research')):
        window.input.setText('Build a simple Python addition calculator'); window.send_btn.click()
        pump(app, lambda: not window.is_busy and bool(window.pending_project_patch), timeout=20)
    assert window.active_route == 'projects'
    assert window.changes_apply_btn.isVisible() and window.changes_apply_btn.isEnabled()
    original_size = window.size(); window.resize(720, 500); QTest.qWait(150)
    assert window.changes_apply_btn.height() >= 32 and not window.changes_apply_btn.visibleRegion().isEmpty()
    assert window.changes_apply_btn.mapTo(window, window.changes_apply_btn.rect().bottomRight()).y() < window.height()
    window.resize(original_size)
    assert not (destination/'main.py').exists(), 'Folder review was bypassed'
    assert window._pending_build_session is not None
    window.changes_apply_btn.click()
    pump(app, lambda: not window.pending_project_patch and not window._project_build_id and (destination/'main.py').is_file(), timeout=45)
    assert (destination/'tests/test_main.py').is_file()
    result = subprocess.run([sys.executable, str(destination/'main.py'), '2', '3'], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout.strip() == '5'
    assert not window.pending_project_patch
    assert not (destination/'requirements.txt').exists(), 'A local import became a pip dependency'
    assert window.runtime.autonomous_builder.project_runtime.kernel is window.runtime.kernel
    assert 'Build a simple Python addition calculator' in window.routes['projects'].updates.toPlainText()
    window.navigate('chats'); assert window.chat_mode == 'normal'


@pytest.mark.parametrize('selection', ['explicit', 'bundled'])
def test_simulator_app_uses_selected_coder_and_writes_sources(window, app, tmp_path, selection):
    destination = tmp_path/'thermal-app'; project_folder(window, destination)
    goal = 'Create a Python thermal expansion simulator app. Save main.py and tests/test_main.py.'
    manifest = {'files': [
        {'path': 'main.py', 'content': 'def expansion(length, alpha, change):\n    return length * alpha * change\n\nif __name__ == "__main__":\n    print(expansion(1, 0.000012, 50))\n'},
        {'path': 'tests/test_main.py', 'content': 'import unittest\nfrom main import expansion\n\nclass Tests(unittest.TestCase):\n    def test_expansion(self):\n        self.assertAlmostEqual(expansion(1, 0.000012, 50), 0.0006)\n'}]}
    old_model = window.model_name, window.model_path; submitted = []
    def generate(history, prompt, **kwargs):
        submitted.append(prompt); yield json.dumps(manifest)
    try:
        window.model_name, window.model_path = ('controlled-coder' if selection == 'explicit' else ''), ''
        default_path = str(tmp_path/'controlled-bundled.gguf')
        with patch('morice.pyside_app.stream_chat', side_effect=generate), \
             patch('morice.llm_client._resolve_gguf_path', return_value='' if selection == 'explicit' else default_path), \
             patch.object(window, '_run_research_request', side_effect=AssertionError('Simulator app entered Research')):
            window.input.setText(goal); window.send_btn.click()
            pump(app, lambda: not window.is_busy and bool(window.pending_project_patch), timeout=25)
            assert submitted and goal in submitted[0]
            assert window.active_route == 'projects'
            window.changes_apply_btn.click()
            pump(app, lambda: not window.pending_project_patch and not window._project_build_id and (destination/'main.py').is_file(), timeout=45)
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], cwd=destination,
            capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        window.model_name, window.model_path = old_model
        window.navigate('home')


def test_project_ask_shows_response_in_project_without_writing(window, app, tmp_path):
    destination = tmp_path/'question'; project_folder(window, destination)
    view = window.routes['projects']; view.action.setCurrentIndex(1)
    old_model = window.model_name, window.model_path
    reply = 'This project answer stays visible in Updates.'
    try:
        window.model_name, window.model_path = 'controlled-coder', ''
        with patch('morice.pyside_app.stream_chat', return_value=iter([reply])):
            window.input.setText('Explain how to organize a Python app'); window.send_btn.click()
            pump(app, lambda: not window.is_busy and reply in view.updates.toPlainText(), timeout=15)
        assert window.active_route == 'projects' and not destination.exists()
        assert not window.pending_project_patch
    finally:
        window.model_name, window.model_path = old_model
        view.action.setCurrentIndex(0); window.navigate('home')


def test_experiment_form_runs_and_keeps_actual_results_in_research(window, app):
    window.navigate('research'); view = window.routes['research']; editor = view.editor
    editor.entry_mode.setCurrentIndex(1)
    editor.model.setCurrentIndex(editor.model.findData('ideal_mixture_density'))
    editor.title.setText('Compare ideal component densities')
    for name, value in {'density_a': '1000', 'density_b': '2000', 'fraction_a': '0.5'}.items(): editor.inputs[name].setText(value)
    editor.kind.setCurrentIndex(1); editor.axis.setCurrentIndex(editor.axis.findData('fraction_a'))
    editor.low.setText('0'); editor.high.setText('1'); editor.points.setValue(5)
    editor.prepare_button.click()
    pump(app, lambda: not view._bridge_preparing and bool(view.selected_id()) and view.run_button.isEnabled(), timeout=15)
    identifier = view.selected_id(); prepared = view.manager.get(identifier)
    assert prepared['status'] == 'PREPARED' and prepared['estimate']['planned_runs'] == 5
    assert 'Ready to run' in view.feedback.text()
    original_size = window.size(); window.resize(720, 500); QTest.qWait(150)
    assert view.run_button.height() >= 32 and not view.run_button.visibleRegion().isEmpty()
    assert view.review.height() >= 96 and view.experiment_scroll.verticalScrollBar().maximum() > 0
    window.resize(original_size)
    view.run_button.click()
    pump(app, lambda: view.manager.get(identifier)['status'] == 'COMPLETED', timeout=20)
    view.refresh(); pump(app, lambda: not view._meta_reading and not view._result_reading and view.runs.rowCount() == 5)
    stored = view.manager.get(identifier, True)
    assert stored['runs'][0]['outputs']['density'] == 2000
    assert stored['runs'][-1]['outputs']['density'] == 1000
    assert window.active_route == 'research'
    assert view.manager.runtime.kernel is window.runtime.kernel
    assert view.progress.value() == 5
    assert not view.detail.isVisible(), 'Raw JSON should not occupy the default workflow'
    window.navigate('home')


def test_experiment_description_missing_inputs_keeps_draft_and_explains(window, app):
    window.navigate('research'); view = window.routes['research']; editor = view.editor
    editor.entry_mode.setCurrentIndex(0)
    draft = 'Simulate an oscillator without supplying physical inputs'
    editor.prompt.setPlainText(draft)
    count = len(view.manager.list())
    editor.prepare_button.click()
    pump(app, lambda: not view._bridge_preparing)
    assert 'Missing physical inputs' in view.feedback.text()
    assert editor.prompt.toPlainText() == draft and editor.prepare_button.isEnabled()
    assert len(view.manager.list()) == count
    window.navigate('home')


def test_described_experiment_runs_actual_sweep_without_chat_fallback(window, app):
    window.navigate('research'); view = window.routes['research']; editor = view.editor
    editor.entry_mode.setCurrentIndex(0)
    editor.prompt.setPlainText('Simulate an oscillator; mass=1 kg; stiffness=100 N/m; damping=0.5 N*s/m; '
        'force=1 N; frequency=1 Hz; sweep frequency from 0 to 5 Hz; 5 points')
    previous = set(row['id'] for row in view.manager.list())
    with patch('morice.pyside_app.stream_chat', side_effect=AssertionError('Experiment fell back to chat')):
        editor.prepare_button.click()
        pump(app, lambda: not view._bridge_preparing and view.selected_id() not in previous and view.run_button.isEnabled())
        identifier = view.selected_id(); view.run_button.click()
        pump(app, lambda: view.manager.get(identifier)['status'] == 'COMPLETED', timeout=20)
    assert view.manager.get(identifier)['completed_runs'] == 5 and window.active_route == 'research'
    window.navigate('home')


@pytest.mark.parametrize('route', ['projects', 'research'])
def test_primary_workflows_fit_compact_window_and_keep_keyboard_targets(window, app, route):
    previous_size = window.size()
    try:
        window.resize(720, 500); window.navigate(route); QTest.qWait(150)
        page = window.routes[route]
        assert page.width() <= window.width() and page.height() < window.height()
        if route == 'projects':
            assert window.send_btn.isVisible() and window.input.isVisible()
            assert window.send_btn.mapTo(window, window.send_btn.rect().bottomRight()).y() < window.height()
        else:
            page.tabs.setCurrentIndex(0)
            assert page.editor.prepare_button.isVisible() and page.editor.prepare_button.height() >= 32
            assert page.editor.prepare_button.mapTo(window, page.editor.prepare_button.rect().bottomRight()).y() < window.height()
    finally: window.resize(previous_size); window.navigate('home')


def test_project_build_no_code_instruction_stays_explanation(window):
    window.navigate('projects')
    assert not window._is_project_build_request('Do not generate code. Explain the simulator design.')
    assert window._is_project_build_request('The navigation needs a darker theme')
    window.navigate('chats')
    assert not window._is_project_build_request('Build a website')


def test_python_dependencies_exclude_local_modules_and_relative_imports(tmp_path):
    from morice.project_runtime import detect_python_requirements
    (tmp_path/'helpers.py').write_text('VALUE = 2\n')
    files = {'main.py': 'import requests\nimport helpers\nimport logging\nimport sqlite3\nfrom widgets import Panel\n',
        'widgets/__init__.py': 'from .panel import Panel\n',
        'widgets/panel.py': 'import math\n',
        'tests/test_main.py': 'from main import run\n'}
    assert detect_python_requirements(files, tmp_path) == ['requests']


def test_web_build_preview_keeps_projects_and_existing_browser_bridge(window, app, tmp_path):
    window.navigate('projects')
    bridge = window.runtime.pc_browser.bridge; browser = window.assistant_hub.browser_view
    window._prepare_build_browser(str(tmp_path))
    app.processEvents()
    assert window.active_route == 'projects'
    assert window.project_workspace_stack.currentWidget() is window.routes['projects'].preview
    assert window.assistant_hub.browser_view is browser and window.runtime.pc_browser.bridge is bridge
    assert browser.isVisible()
    window.assistant_hub.show_tab('Browser'); app.processEvents()
    assert window.active_route == 'tools' and browser.isVisible()
    assert window.assistant_hub.tools_subtabs.indexOf(window.assistant_hub.browser_page) >= 0
    window.navigate('home')


def test_workflow_controls_only_reference_existing_authored_icons(window):
    from morice.ui_next.icons import MARKS
    from PySide6.QtWidgets import QWidget
    for widget in window.findChildren(QWidget):
        name = widget.property('morice_icon')
        assert not name or name in MARKS, (widget.objectName(), name)


def test_leaving_a_project_during_reply_does_not_turn_chat_into_a_build(window, app, tmp_path):
    import threading
    release = threading.Event(); project_folder(window, tmp_path/'held-question')
    view = window.routes['projects']; view.action.setCurrentIndex(1)
    old_model = window.model_name, window.model_path
    def generate(*args, **kwargs):
        assert release.wait(5); yield 'The original project question is complete.'
    try:
        window.model_name, window.model_path = 'controlled-coder', ''
        with patch('morice.pyside_app.stream_chat', side_effect=generate):
            window.input.setText('Explain the project structure'); window.send_btn.click()
            assert window.is_busy
            window.navigate('chats'); window.input.setText('2+3'); window.on_send()
            assert window.input.text() == '2+3', 'Cross-workspace input was consumed while another request owned the response'
            release.set(); pump(app, lambda: not window.is_busy)
        window.send_btn.click(); pump(app, lambda: not window.is_busy and window.chat_mode == 'normal')
        assert not (tmp_path/'held-question').exists()
        assert 'The original project question is complete.' in view.updates.toPlainText()
        assert '5' in window.history[-1]['content']
    finally:
        release.set(); window.model_name, window.model_path = old_model
        view.action.setCurrentIndex(0); window.navigate('home')
