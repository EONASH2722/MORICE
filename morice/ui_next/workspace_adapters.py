"""Reviewed presentation adapters for established workspace action contracts.

These adapters reuse existing controls/callbacks while replacing their layouts,
window chrome and worker delivery. Domain services and permission dialogs remain
the existing authorities. Production migration is gated separately by parity.
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, QItemSelectionModel, QTimer
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QScrollArea, QSplitter, QLineEdit,
    QPlainTextEdit, QFormLayout, QTableWidgetItem, QComboBox, QTextBrowser, QHeaderView, QSizePolicy)

from ..research.ui import ResearchDialog
from ..device_mesh.ui import DevicesDialog
from ..ambient.ui import AmbientDialog
from ..research.history_ui import ChatHistoryDialog
from ..plugin_ui import PluginCenter
from .research_graph import EvidenceGraph
from .responsive import FlowLayout
from .experiment_form import ExperimentForm


def page(title, description=''):
    view = QWidget(); layout = QVBoxLayout(view); layout.setContentsMargins(24, 20, 24, 20)
    heading = QLabel(title); heading.setProperty('role', 'title'); layout.addWidget(heading)
    if description:
        note = QLabel(description); note.setWordWrap(True); note.setProperty('role', 'secondary'); layout.addWidget(note)
    return view, layout


def retire_layout(layout, owner):
    """Keep controller-owned controls alive while installing a reviewed layout."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget(): item.widget().setParent(owner)
        elif item.layout(): retire_layout(item.layout(), owner)


def button_rows(layout, buttons, columns=3):
    for start in range(0, len(buttons), columns):
        row = QHBoxLayout()
        for button in buttons[start:start + columns]: row.addWidget(button)
        layout.addLayout(row)


class ResearchWorkspace(ResearchDialog):
    def __init__(self, services, bridge, parent=None, *, theme=None):
        self.bridge = bridge; self._bridge_preparing = False; self._ready = False; self._creating_project = False; self._controlling = False
        self._meta_reading = False; self._meta_again = False; self._result_reading = False; self._result_key = None; self._meta_rows = {}; self._pending_select_id = None
        super().__init__(services.research, parent=parent)
        self.setWindowFlags(Qt.Widget); self.timer.stop(); self.pool.shutdown(wait=False, cancel_futures=True)
        controls = list(self.findChildren(QPushButton)); self.retained_controls = QWidget(self); self.retained_controls.hide()
        root = self.layout(); retire_layout(root, self.retained_controls)
        root.setContentsMargins(24, 20, 24, 20)
        heading = QLabel('Research'); heading.setProperty('role', 'title')
        heading_row = QHBoxLayout(); heading_row.addWidget(heading, 1); root.addLayout(heading_row)
        root.addWidget(QLabel('Describe a test → review the inputs → run it and view saved results.'))
        self.notebooks_button = QPushButton('Notebooks'); self.notebooks_button.setCheckable(True)
        self.notebooks_button.setAccessibleName('Research notebooks')
        self.notebooks_button.setProperty('morice_icon', 'projects'); heading_row.addWidget(self.notebooks_button)
        self.notebooks = QWidget(); notebooks = QVBoxLayout(self.notebooks); notebooks.setContentsMargins(0, 0, 0, 0)
        project_row = QHBoxLayout(); project_row.addWidget(self.projects, 1)
        self.objective = QLineEdit(); self.objective.setPlaceholderText('New research objective'); project_row.addWidget(self.objective, 1)
        self.create_button = QPushButton('Create notebook'); self.create_button.clicked.connect(self.create_project); project_row.addWidget(self.create_button); notebooks.addLayout(project_row)
        root.addWidget(self.notebooks); self.notebooks.hide(); self.notebooks_button.toggled.connect(self.notebooks.setVisible)
        self.feedback = QLabel('Start with an experiment below. Its inputs and results are saved automatically.')
        self.feedback.setWordWrap(True); root.addWidget(self.feedback)
        notebooks.addWidget(self.status); self.status.hide(); self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        _, new = self.add_page('New experiment')
        self.editor = ExperimentForm(self.manager.registry); self.editor.prepare_requested.connect(self._prepare_request)
        new.addWidget(self.editor)
        self.experiments_page, experiment = self.add_page('Experiments')
        self.experiment_scroll = QScrollArea(); self.experiment_scroll.setWidgetResizable(True)
        self.experiment_scroll.setFrameShape(QScrollArea.NoFrame)
        self.experiment_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        experiment_content = QWidget(); review_layout = QVBoxLayout(experiment_content); review_layout.setContentsMargins(0, 0, 0, 0)
        self.review = QPlainTextEdit('Select a saved experiment to review or run.'); self.review.setReadOnly(True)
        self.review.setAccessibleName('Reviewed experiment inputs and model limits')
        self.review.setMinimumHeight(96); self.review.setMaximumHeight(160); review_layout.addWidget(self.review)
        review_layout.addWidget(self.filter); review_layout.addWidget(self.experiments, 1); review_layout.addWidget(self.progress)
        self.experiments.setMinimumHeight(100)
        self.experiment_scroll.setWidget(experiment_content); experiment.addWidget(self.experiment_scroll, 1)
        self.experiment_controls = controls[:4]
        self.run_button, self.pause_button, self.cancel_button, self.compare_button = self.experiment_controls
        self.run_button.setText('Run experiment'); self.run_button.setProperty('role', 'primary')
        self.compare_button.setText('Compare selected')
        action_row = FlowLayout()
        for button in self.experiment_controls: action_row.addWidget(button); button.setEnabled(False)
        experiment.addLayout(action_row)
        self.experiments.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for index in range(1, 5): self.experiments.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeToContents)
        _, results = self.add_page('Results'); results.addWidget(self.run_filter); results.addWidget(self.runs, 1)
        self.results_note = QLabel('Completed run data remains in the existing experiment store.'); self.results_note.setWordWrap(True); results.addWidget(self.results_note)
        self.run_filter.setPlaceholderText('Filter stored runs by index, parameters, status or outputs')
        _, evidence = self.add_page('Evidence'); evidence.addWidget(self.evidence); self.evidence_summary = QPlainTextEdit(); self.evidence_summary.setReadOnly(True); evidence.addWidget(self.evidence_summary, 1)
        self.simulation_page, simulation = self.add_page('Simulation'); simulation.addWidget(self.plot, 1)
        playback = QHBoxLayout()
        for widget in (self.play, next(button for button in controls if button.text() == 'Step'), self.speed, self.trails): playback.addWidget(widget)
        simulation.addLayout(playback); simulation.addWidget(self.scrub); simulation.addWidget(self.frame_status)
        self.specification_page, specification = self.add_page('Specification'); self.specification.setMaximumHeight(16777215); specification.addWidget(self.specification, 1)
        self.prepare_button = next(button for button in controls if button.text().startswith('Prepare reviewed')); specification.addWidget(self.prepare_button)
        self.graph = EvidenceGraph(theme) if theme is not None else None; self.graph_page = None
        if self.graph is not None:
            self.graph_page, graph_layout = self.add_page('Evidence graph'); graph_layout.addWidget(self.graph,1)
            graph_note = QLabel('Stored relationships only. No links or scientific support are inferred. View shows up to 200 records.'); graph_note.setWordWrap(True); graph_layout.addWidget(graph_note)
        self.advanced_button = QPushButton('Advanced'); self.advanced_button.setCheckable(True)
        self.advanced_button.setAccessibleName('Advanced research details')
        self.advanced_button.setProperty('morice_icon', 'more'); heading_row.addWidget(self.advanced_button)
        root.addWidget(self.detail); self.detail.setMaximumHeight(160); self.detail.hide()
        self.advanced_button.toggled.connect(self._show_advanced); self._show_advanced(False)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.timer.setInterval(1000)
        self._ready = True

    def add_page(self, label):
        view = QWidget(); layout = QVBoxLayout(view); self.tabs.addTab(view, label); return view, layout

    def create_project(self):
        objective = self.objective.text().strip()
        if not objective or self._creating_project: return
        self._creating_project = True; self.create_button.setEnabled(False)
        try:
            self.bridge.submit('research-create-project', lambda: self.runtime.create(objective),
                lambda envelope: self._created(envelope, objective))
        except (ValueError, RuntimeError) as exc:
            self._created({'ok': False, 'error': str(exc)}, objective)

    def _created(self, envelope, objective):
        self._creating_project = False; self.create_button.setEnabled(True)
        if not envelope['ok']: self._error(envelope['error']); return
        self.project_id = envelope['value']; self.projects.addItem(objective, self.project_id)
        self.projects.setCurrentIndex(self.projects.findData(self.project_id))
        if self.objective.text().strip() == objective: self.objective.clear()
        self.refresh()

    def _tab_changed(self, index):
        if self.tabs.widget(index) is not self.simulation_page: self.play_timer.stop()
        if self.tabs.tabText(index) == 'Evidence': self.inspect_evidence(); self.evidence_summary.setPlainText(self.detail.toPlainText())

    def _show_advanced(self, visible):
        self.detail.setVisible(visible)
        for view in (self.specification_page, self.graph_page):
            if view is not None: self.tabs.setTabVisible(self.tabs.indexOf(view), visible)

    def _error(self, message):
        self.detail.setPlainText(str(message)); self.feedback.setText(str(message))

    def refresh(self, *_):
        if not self._ready: return super().refresh()
        if self._meta_reading: self._meta_again = True; return
        self.project_id = self.projects.currentData() or self.project_id
        project_id = self.project_id; text = self.filter.text().casefold(); self._meta_reading = True; self._meta_again = False
        def read():
            rows = self.manager.list(project_id) if project_id else []
            rows = [row for row in rows if text in (row['title']+' '+row['status']).casefold()]
            snapshot = self.runtime.store.snapshot(project_id) if project_id else None
            return {'rows':rows, 'snapshot':snapshot, 'project_id':project_id}
        def apply(envelope):
            self._meta_reading = False
            if not envelope['ok']: self._error(envelope['error']); return
            value = envelope['value']
            if value['project_id'] != self.project_id:
                if self.isVisible(): self.refresh()
                return
            selected = self._pending_select_id or self.selected_id(); selections = {self.experiments.item(i.row(),0).data(Qt.UserRole) for i in self.experiments.selectionModel().selectedRows()}
            rows = value['rows']; self._meta_rows = {row['id']:row for row in rows}
            self.experiments.blockSignals(True); self.experiments.setSortingEnabled(False); self.experiments.setRowCount(len(rows))
            for index, row in enumerate(rows):
                for column, item_value in enumerate((row['title'], row['status'], row['completed_runs'], row['estimate']['planned_runs'], row['error'])):
                    item = QTableWidgetItem(); item.setData(Qt.DisplayRole, item_value); item.setData(Qt.UserRole, row['id']); self.experiments.setItem(index,column,item)
            self.experiments.setSortingEnabled(True)
            for index in range(self.experiments.rowCount()):
                if self.experiments.item(index,0).data(Qt.UserRole) in selections:
                    self.experiments.selectionModel().select(self.experiments.model().index(index,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
                if self.experiments.item(index,0).data(Qt.UserRole) == selected:
                    self.experiments.selectionModel().setCurrentIndex(self.experiments.model().index(index,0),QItemSelectionModel.NoUpdate)
                    if self._pending_select_id: self.experiments.selectRow(index); self._pending_select_id = None
            self.experiments.blockSignals(False)
            if not rows:
                self.runs.setRowCount(0); self.progress.setValue(0); self._result_key = None
                self.review.setPlainText('No experiments in this notebook. Open New experiment to create one.')
                for button in self.experiment_controls: button.setEnabled(False)
            self.compare_button.setEnabled(len(self.experiments.selectionModel().selectedRows()) == 2)
            snapshot = value['snapshot']
            if snapshot:
                self.status.show()
                if self.graph is not None: self.graph.set_snapshot(snapshot)
                records = snapshot['records']
                self.status.setText(f"{snapshot['objective']}\n{sum(row['kind']=='question' for row in records)} questions · {sum(row['kind']=='hypothesis' for row in records)} hypotheses · {sum(row['stale'] for row in records)} stale records")
                ids = tuple((row['id'],row['stale'],row['revision']) for row in records)
                if ids != self.evidence_ids:
                    current = self.evidence.currentData(); self.evidence.blockSignals(True); self.evidence.clear(); self.evidence.addItem('Project timeline','timeline')
                    for row in records: self.evidence.addItem(f"{row['kind']} · {row['provenance']} · {row['title']}" + (' · STALE' if row['stale'] else ''),row['id'])
                    self.evidence.setCurrentIndex(max(0,self.evidence.findData(current))); self.evidence.blockSignals(False); self.evidence_ids = ids
            if not self.inspection_mode: self.select()
            if self._meta_again and self.isVisible(): self.refresh()
        self.bridge.submit('research-read-metadata', read, apply)

    def select(self):
        if not self._ready: return super().select()
        self.inspection_mode = False; identifier = self.selected_id()
        self.compare_button.setEnabled(len(self.experiments.selectionModel().selectedRows()) == 2)
        if not identifier:
            for button in (self.run_button, self.pause_button, self.cancel_button): button.setEnabled(False)
            return
        if self._result_reading: return
        text = self.run_filter.text().casefold(); metadata = self._meta_rows.get(identifier, {})
        key = (identifier, metadata.get('updated'), metadata.get('completed_runs'), metadata.get('status'), text)
        if self._result_key == key: return
        self._result_reading = True
        def read():
            return self.manager.get(identifier,True,run_limit=500,run_filter=text)
        def apply(envelope):
            self._result_reading = False
            if not envelope['ok']: self._error(envelope['error']); return
            if identifier != self.selected_id():
                if self.isVisible(): self.select()
                return
            row = envelope['value']; self._result_key = key
            state = row['status']; running = state in {'QUEUED', 'RUNNING'}
            self.run_button.setEnabled(not running and not self._controlling)
            self.run_button.setText('Resume experiment' if state in {'PAUSED', 'CANCELLED'} else 'Completed' if state.startswith('COMPLETED') else 'Run experiment')
            # Completed experiments are immutable; use a new reviewed plan instead.
            if state.startswith('COMPLETED'): self.run_button.setEnabled(False)
            self.pause_button.setEnabled(running and not self._controlling)
            self.cancel_button.setEnabled(state in {'QUEUED', 'RUNNING', 'PAUSED'} and not self._controlling)
            values = ', '.join(f"{name.replace('_', ' ')} = {quantity['value']} {quantity['unit']}" for name, quantity in row['spec']['parameters'].items())
            self.review.setPlainText(f"{row['title']} · {state.replace('_', ' ').title()}\n"
                f"{row['completed_runs']} / {row['estimate']['planned_runs']} runs saved\n{values}\n{row['estimate']['limitations']}")
            self.progress.setRange(0,row['estimate']['planned_runs']); self.progress.setValue(row['completed_runs'])
            self.detail.setPlainText(json.dumps({'summary':row['summary'],'error':row['error'],'specification':row['spec']},indent=2)[:30000])
            self.runs.setSortingEnabled(False); self.runs.setRowCount(len(row['runs']))
            for index, run in enumerate(row['runs']):
                for column, item_value in enumerate((run['run_index'],json.dumps(run['parameters']),run['status'],json.dumps(run['outputs'])+' '+run['error'])):
                    item = QTableWidgetItem(); item.setData(Qt.DisplayRole,item_value); self.runs.setItem(index,column,item)
            self.runs.setSortingEnabled(True)
            self.results_note.setText(f"Showing {len(row['runs'])} of {row['matching_runs']} matching stored runs. Complete results and provenance remain in the experiment export.")
        self.bridge.submit('research-read-results', read, apply)

    def compare(self):
        identifiers = {self.experiments.item(index.row(),0).data(Qt.UserRole) for index in self.experiments.selectionModel().selectedRows()}
        if len(identifiers) != 2: self.detail.setPlainText('Select exactly two experiments to compare.'); return
        self.inspection_mode = True
        self.bridge.submit('research-compare', lambda: self.manager.compare(*sorted(identifiers)),
            lambda envelope: self.detail.setPlainText(json.dumps(envelope['value'],indent=2)[:30000] if envelope['ok'] else envelope['error']))

    def prepare(self):
        if self._bridge_preparing: return
        try: spec = json.loads(self.specification.toPlainText())
        except ValueError as exc: self._error(str(exc)); return
        self._prepare_request(spec)

    def _prepare_request(self, spec):
        if self._bridge_preparing: return
        self._bridge_preparing = True; self.prepare_button.setEnabled(False); self.editor.prepare_button.setEnabled(False)
        self.projects.setEnabled(False); self.feedback.setText('Checking your inputs and preparing an experiment for review…')
        def completed(envelope):
            self._bridge_preparing = False; self.prepare_button.setEnabled(True); self.editor.prepare_button.setEnabled(True); self.projects.setEnabled(True)
            if not envelope['ok']: self._error(envelope['error']); return
            row = envelope['value']; self.project_id = row['project_id']
            self._pending_select_id = row['id']
            if self.projects.findData(self.project_id) < 0: self.projects.addItem(self.runtime.project(self.project_id).objective[:100], self.project_id)
            self.projects.setCurrentIndex(self.projects.findData(self.project_id)); self.refresh()
            for index in range(self.experiments.rowCount()):
                if self.experiments.item(index, 0).data(Qt.UserRole) == row['id']: self.experiments.selectRow(index); break
            self.tabs.setCurrentWidget(self.experiments_page)
            self.feedback.setText(f"Ready to run: {row['estimate']['planned_runs']} computational runs. Review the inputs below, then select Run experiment.")
        project_id = self.project_id or None
        try: self.bridge.submit('research-prepare', lambda: self.manager.prepare(spec, project_id=project_id), completed)
        except (ValueError, RuntimeError) as exc: completed({'ok': False, 'error': str(exc)})

    def control(self, action):
        identifier = self.selected_id()
        if not identifier or self._controlling: return
        self._controlling = True
        for button in self.experiment_controls: button.setEnabled(False)
        def completed(envelope):
            self._controlling = False; self._result_key = None
            if not envelope['ok']: self._error(envelope['error'])
            else: self.feedback.setText('Experiment updated. Progress and results are saved in this notebook.')
            self.refresh()
        try: self.bridge.submit('research-experiment-control', lambda: action(identifier), completed)
        except (ValueError, RuntimeError) as exc: completed({'ok': False, 'error': str(exc)})

    def tick(self):
        self.refresh()

    def showEvent(self, event):
        self.timer.start(); self.refresh(); super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop(); self.play_timer.stop(); super().hideEvent(event)

    def dispose(self):
        self.timer.stop(); self.play_timer.stop()


class DevicesWorkspace(DevicesDialog):
    def __init__(self, runtime, bridge, parent=None):
        self.bridge = bridge
        super().__init__(runtime, parent); self.setWindowFlags(Qt.Widget)
        self._timer.stop(); self._pool.shutdown(wait=False, cancel_futures=True)
        buttons = list(self.findChildren(QPushButton)); self.retained_controls = QWidget(self); self.retained_controls.hide()
        root = self.layout(); retire_layout(root, self.retained_controls); root.setContentsMargins(24, 20, 24, 20)
        heading = QLabel('Devices'); heading.setProperty('role', 'title'); root.addWidget(heading)
        root.addWidget(self.status); root.addWidget(self.enabled_box)
        split = QSplitter(); split.addWidget(self.nodes); split.addWidget(self.details); split.setStretchFactor(1, 1); root.addWidget(split, 1)
        self.tabs = QTabWidget(); root.addWidget(self.tabs)
        for label, group in (('Pairing', buttons[:4]), ('Actions', buttons[4:9]), ('Groups & permissions', buttons[9:])):
            view = QWidget(); layout = QVBoxLayout(view); button_rows(layout, group); self.tabs.addTab(view, label)

    def _run(self, callback):
        if self._busy: self.status.setText('A device operation is still running.'); return
        self._busy = True
        self.bridge.submit('device-user-action', callback, lambda value: self._done(str(value.get('value') or 'Operation finished.') if value['ok'] else value['error']))

    def showEvent(self, event):
        self.refresh(); self._timer.start(); super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop(); super().hideEvent(event)

    def dispose(self): self._timer.stop()


class AmbientWorkspace(AmbientDialog):
    def __init__(self, runtime, bridge, parent=None):
        self.bridge = bridge
        super().__init__(runtime, parent); self.setWindowFlags(Qt.Widget); self.timer.stop()
        self.layout().setContentsMargins(24, 20, 24, 20); self.tabs = self.findChild(QTabWidget)
        self.heading = QLabel('Automations'); self.heading.setProperty('role', 'title'); self.layout().insertWidget(0, self.heading)
        self.timer.setInterval(1500)

    def select_route(self, key):
        self.heading.setText({'automations': 'Automations', 'connectors': 'Connectors', 'security': 'Security'}[key])
        self.tabs.setCurrentIndex({'automations': 0, 'connectors': 1, 'security': 2}[key])

    def _work(self, callback, completed=None):
        def done(envelope):
            if not envelope['ok']: self.status.setText(envelope['error']); return
            if completed: completed(envelope['value'])
            self._refresh()
        self.bridge.submit('ambient-user-action', callback, done)

    def showEvent(self, event):
        self._refresh(); self.timer.start(); super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop(); super().hideEvent(event)

    def dispose(self): self.timer.stop()


class HistoryWorkspace(ChatHistoryDialog):
    def __init__(self, window):
        self.owner = window
        def reopen(identifier):
            window._restore_history_chat(identifier); window.navigate('chats')
        super().__init__(window._get_chat_history(), reopen, window)
        self.setWindowFlags(Qt.Widget); self.layout().setContentsMargins(24, 20, 24, 20)
        heading = QLabel('History'); heading.setProperty('role', 'title'); self.layout().insertWidget(0, heading)

    def open_selected(self):
        # Embedded navigation must not accept/hide its persistent workspace.
        chat = self.selected()
        if chat:
            try: self.open_chat(chat['id'])
            except Exception as exc: self.owner.status_line.setText(str(exc))

    def delete(self):
        selected = self.selected()
        super().delete()
        if selected and selected['id'] == self.owner._chat_id and not any(chat['id'] == selected['id'] for chat in self.history.search('')):
            self.owner._history_deleted_id = selected['id']

    def showEvent(self, event):
        self.owner._persist_chat_history(); self.refresh(); super().showEvent(event)


class PluginsWorkspace(PluginCenter):
    def __init__(self, window, bridge):
        self.bridge = bridge
        super().__init__(window.runtime.plugins, window); self.setWindowFlags(Qt.Widget)
        self.setMinimumSize(0, 0); self._executor.shutdown(wait=False, cancel_futures=True)
        self.layout().setContentsMargins(24, 20, 24, 20)

    def _run(self, label, callback):
        self.status.setText(label)
        self.bridge.submit('plugin-user-action', callback, lambda envelope: self._on_operation_finished(label, envelope['ok'], str(envelope.get('value') or envelope.get('error') or 'Done')))

    def showEvent(self, event):
        self.refresh(); super().showEvent(event)


class ProjectsWorkspace(QWidget):
    """One visible task, destination and result over the established Builder."""
    def __init__(self, window):
        super().__init__(); self.owner = window
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(); root = QVBoxLayout(content); root.setContentsMargins(16, 8, 16, 8); root.setSpacing(8)
        self.scroll.setWidget(content); outer.addWidget(self.scroll)
        heading = QLabel('Projects'); heading.setProperty('role', 'title'); root.addWidget(heading)
        note = QLabel('Choose a folder → describe your changes → review and save the files.')
        note.setWordWrap(True); note.setProperty('role', 'secondary'); root.addWidget(note)
        setup = QHBoxLayout()
        window.project_folder_input.setMinimumWidth(0)
        window.project_folder_input.setPlaceholderText('Choose where MORICE should save your project')
        window.project_add_btn.setText('Choose folder'); window.project_add_btn.setMinimumWidth(0)
        window.project_add_btn.setMaximumWidth(16777215)
        window.project_add_btn.setFixedHeight(window.theme_engine.tokens.control_height)
        setup.addWidget(window.project_folder_input, 1); setup.addWidget(window.project_add_btn)
        root.addLayout(setup)
        actions = QHBoxLayout()
        self.action = QComboBox(); self.action.addItem('Build or edit files', 'build'); self.action.addItem('Ask about this project', 'ask')
        self.action.setAccessibleName('Project prompt action')
        self.action.currentIndexChanged.connect(lambda: window._refresh_send_button_state())
        actions.addWidget(self.action, 1)
        self.options_button = QPushButton('Build settings'); self.options_button.setCheckable(True)
        self.options_button.setProperty('morice_icon', 'settings'); actions.addWidget(self.options_button)
        self.stop_button = QPushButton('Stop build'); self.stop_button.setProperty('morice_icon', 'stop')
        self.stop_button.clicked.connect(self.stop_build); actions.addWidget(self.stop_button); self.stop_button.hide()
        root.addLayout(actions)
        self.options = QWidget(); options = QVBoxLayout(self.options); options.setContentsMargins(0, 0, 0, 0)
        access = FlowLayout()
        for field in (window.folder_access_btn, window.full_access_btn, window.project_lookup_btn):
            field.setMinimumWidth(0); access.addWidget(field)
        window.project_lookup_btn.setAccessibleName('Project lookup scope'); window.project_lookup_btn.setProperty('morice_icon','search'); window.project_lookup_btn.show()
        options.addLayout(access); options.addWidget(window.mode_status)
        root.addWidget(self.options); self.options.hide(); self.options_button.toggled.connect(self.options.setVisible)
        self.feedback = QLabel('Describe what to build below. MORICE will prepare real files for your review.')
        self.feedback.setWordWrap(True); root.addWidget(self.feedback)
        window.changes_summary.setParent(self); root.addWidget(window.changes_summary); window.changes_summary.show()
        window.changes_content.setParent(self); root.addWidget(window.changes_content, 1); window.changes_content.show()
        window.changes_content.setMinimumWidth(0); window.project_workspace_stack.setMinimumWidth(0)
        # The route may shrink; review controls must retain usable hit areas.
        # Scroll the project surface instead of collapsing its review page.
        window.project_workspace_stack.setMinimumHeight(280)
        self.updates = QTextBrowser(); self.updates.setOpenExternalLinks(False)
        self.updates.document().setMaximumBlockCount(1000)
        self.updates.setAccessibleName('Project conversation and progress'); self.updates.setPlaceholderText('Your project requests and responses appear here. Files and verification stay in this workspace.')
        window.project_workspace_stack.addWidget(self.updates)
        window.project_updates_tab = QPushButton('Updates'); window.project_updates_tab.setProperty('morice_icon', 'chats')
        window.project_updates_tab.clicked.connect(lambda: window._set_project_workspace_tab(3))
        window.changes_content.layout().itemAt(0).layout().addWidget(window.project_updates_tab)
        self.preview = QWidget(); self.preview_layout = QVBoxLayout(self.preview); self.preview_layout.setContentsMargins(0, 0, 0, 0)
        window.project_workspace_stack.addWidget(self.preview)
        window.project_preview_tab = QPushButton('Preview'); window.project_preview_tab.setProperty('morice_icon', 'spatial')
        window.project_preview_tab.clicked.connect(self.show_preview); window.project_preview_tab.hide()
        window.changes_content.layout().itemAt(0).layout().addWidget(window.project_preview_tab)
        window.changes_apply_btn.setText('Save reviewed files'); window.changes_apply_btn.setProperty('role', 'primary')
        window.changes_reject_btn.setText('Discard proposal')
        window.project_changes_tab.setText('Review')
        # A tree and readable preview share the available area instead of two
        # full-width, vertically competing panes.
        files = window.project_files_page.layout()
        files.removeWidget(window.project_file_tree); files.removeWidget(window.project_file_preview)
        self.file_split = QSplitter(Qt.Horizontal)
        self.file_split.addWidget(window.project_file_tree); self.file_split.addWidget(window.project_file_preview)
        self.file_split.setSizes([240, 520]); files.addWidget(self.file_split, 1)
        window.project_file_tree.setMinimumWidth(0); window.project_file_preview.setMinimumWidth(0)
        window._set_project_workspace_tab(0)
        self.refresh_state()

    def record_message(self, author, message):
        from html import escape
        self.updates.append('<b>' + escape(str(author)) + '</b><p style="white-space:pre-wrap">' + escape(str(message)) + '</p>')
        self.updates.verticalScrollBar().setValue(self.updates.verticalScrollBar().maximum())
        QTimer.singleShot(0, self.ensure_primary_visible)

    def ensure_primary_visible(self):
        if not self.isVisible(): return
        window = self.owner
        if window.project_workspace_stack.currentIndex() == 0 and not window.changes_available:
            self.scroll.verticalScrollBar().setValue(0); return
        target = window.changes_apply_btn if window.pending_project_patch and window.project_workspace_stack.currentIndex() == 1 else window.project_workspace_stack.currentWidget()
        if target is not None: self.scroll.ensureWidgetVisible(target, 0, 12)

    def show_preview(self):
        hub = self.owner.assistant_hub
        index = hub.tools_subtabs.indexOf(hub.browser_page)
        if index >= 0: hub.tools_subtabs.removeTab(index)
        self.preview_layout.addWidget(hub.browser_page); hub.browser_page.show()
        self.owner.project_preview_tab.show(); self.owner.navigate('projects')
        self.owner._set_project_workspace_tab(4)

    def release_preview(self):
        hub = self.owner.assistant_hub
        if hub.browser_page.parent() is self.preview:
            self.preview_layout.removeWidget(hub.browser_page)
            hub.tools_subtabs.insertTab(2, hub.browser_page, 'Browser')
            self.owner.project_preview_tab.hide()

    def refresh_state(self):
        window = self.owner
        building = bool(window._project_build_id)
        window.changes_summary.setVisible(bool(window.changes_available) or building)
        self.stop_button.setVisible(building)
        for field in (window.project_folder_input, window.project_add_btn, self.action, self.options):
            field.setEnabled(not window.is_busy and not building)
        pending = bool(window.pending_project_patch)
        window.changes_apply_btn.setVisible(pending); window.changes_reject_btn.setVisible(pending)
        window.changes_verify_btn.setVisible(not pending); window.changes_run_btn.setVisible(not pending)
        window.changes_undo_btn.setVisible(bool(window.last_project_undo_id))
        window.changes_resume_btn.setVisible(bool(window._last_project_build_id) and not window._project_build_id)
        if pending:
            self.feedback.setText('Your files are ready. Open Review, check the changes, then select Save reviewed files.')
            window.changes_action_status.setText('These files have not been saved yet. Save reviewed files to start the checks.')
        elif window._project_build_id: self.feedback.setText('Building and checking your project. Progress is available in Output.')
        elif not window.project_folder: self.feedback.setText('Choose a folder first, or use the default MORICE Projects / Quick Build folder.')
        QTimer.singleShot(0, self.ensure_primary_visible)

    def stop_build(self):
        token = self.owner._project_build_token
        if token is not None:
            token.cancel('User chose Stop build.')
            self.feedback.setText('Stopping the build. Completed file changes and checks remain visible in this project.')

    def resizeEvent(self, event):
        if hasattr(self, 'file_split'): self.file_split.setOrientation(Qt.Vertical if self.width() < 600 else Qt.Horizontal)
        if hasattr(self, 'scroll'): QTimer.singleShot(0, self.ensure_primary_visible)
        super().resizeEvent(event)


class ToolsWorkspace(QWidget):
    """Retain the verified Qt browser bridge and every desktop/tool control."""
    def __init__(self, window):
        super().__init__(); self.owner = window
        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 20)
        heading = QLabel('Tools'); heading.setProperty('role', 'title'); root.addWidget(heading)
        root.addWidget(window.assistant_hub.search)
        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        hub = window.assistant_hub
        for name, field in (('Files', hub.files_page), ('Desktop & media', hub.tools_page), ('Platform', hub.platform_page), ('Overview', hub.dashboard_page)):
            self.tabs.addTab(field, name)
        self._previous_show_tab = hub.show_tab; hub.show_tab = self.show_tab
        self._previous_plugin_panels = hub.set_plugin_panels; hub.set_plugin_panels = self.set_plugin_panels
        self.mount_plugin_pages()

    def mount_plugin_pages(self):
        for field in self.owner.assistant_hub._plugin_pages:
            if self.tabs.indexOf(field) < 0:
                labels = field.findChildren(QLabel)
                self.tabs.addTab(field, labels[0].text()[:24] if labels else 'Plugin workspace')

    def set_plugin_panels(self, contributions, callback):
        self._previous_plugin_panels(contributions, callback); self.mount_plugin_pages()

    def show_tab(self, name):
        if name == 'Browser':
            if getattr(self.owner, '_project_preview_preparing', False):
                self.owner.routes['projects'].show_preview(); return
            self.owner.routes['projects'].release_preview()
        self.owner.navigate('activity' if name == 'Activity' else 'tools')
        tools = ('System', 'Notes', 'Browser', 'Media', 'Desktop')
        if name in tools:
            self.tabs.setCurrentIndex(1)
            subtabs = self.owner.assistant_hub.tools_subtabs
            index = next((i for i in range(subtabs.count()) if subtabs.tabText(i) == name), -1)
            if index >= 0: subtabs.setCurrentIndex(index)
        elif name != 'Activity': self.tabs.setCurrentIndex({'Files': 0, 'Tools': 1, 'Platform': 2, 'Dashboard': 3}.get(name, 0))
