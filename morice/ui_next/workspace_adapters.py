"""Reviewed presentation adapters for established workspace action contracts.

These adapters reuse existing controls/callbacks while replacing their layouts,
window chrome and worker delivery. Domain services and permission dialogs remain
the existing authorities. Production migration is gated separately by parity.
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QScrollArea, QSplitter, QLineEdit,
    QPlainTextEdit, QFormLayout, QTableWidgetItem)

from ..research.ui import ResearchDialog
from ..device_mesh.ui import DevicesDialog
from ..ambient.ui import AmbientDialog
from ..research.history_ui import ChatHistoryDialog
from ..plugin_ui import PluginCenter
from .research_graph import EvidenceGraph


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
        self.bridge = bridge; self._bridge_preparing = False; self._ready = False; self._creating_project = False
        self._meta_reading = False; self._meta_again = False; self._result_reading = False; self._result_key = None; self._meta_rows = {}; self._pending_select_id = None
        super().__init__(services.research, parent=parent)
        self.setWindowFlags(Qt.Widget); self.timer.stop(); self.pool.shutdown(wait=False, cancel_futures=True)
        controls = list(self.findChildren(QPushButton)); self.retained_controls = QWidget(self); self.retained_controls.hide()
        root = self.layout(); retire_layout(root, self.retained_controls)
        root.setContentsMargins(24, 20, 24, 20)
        heading = QLabel('Research'); heading.setProperty('role', 'title'); root.addWidget(heading)
        root.addWidget(QLabel('Evidence, reproducible experiments and computational results.'))
        project_row = QHBoxLayout(); project_row.addWidget(self.projects, 1)
        self.objective = QLineEdit(); self.objective.setPlaceholderText('New research objective'); project_row.addWidget(self.objective, 1)
        self.create_button = QPushButton('Create project'); self.create_button.clicked.connect(self.create_project); project_row.addWidget(self.create_button); root.addLayout(project_row)
        root.addWidget(self.status); self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        _, experiment = self.add_page('Experiments'); experiment.addWidget(self.filter); experiment.addWidget(self.experiments, 1); experiment.addWidget(self.progress)
        button_rows(experiment, controls[:4], 4)
        _, results = self.add_page('Results'); results.addWidget(self.run_filter); results.addWidget(self.runs, 1)
        self.results_note = QLabel('Completed run data remains in the existing experiment store.'); self.results_note.setWordWrap(True); results.addWidget(self.results_note)
        self.run_filter.setPlaceholderText('Filter stored runs by index, parameters, status or outputs')
        _, evidence = self.add_page('Evidence'); evidence.addWidget(self.evidence); self.evidence_summary = QPlainTextEdit(); self.evidence_summary.setReadOnly(True); evidence.addWidget(self.evidence_summary, 1)
        _, simulation = self.add_page('Simulation'); simulation.addWidget(self.plot, 1)
        playback = QHBoxLayout()
        for widget in (self.play, next(button for button in controls if button.text() == 'Step'), self.speed, self.trails): playback.addWidget(widget)
        simulation.addLayout(playback); simulation.addWidget(self.scrub); simulation.addWidget(self.frame_status)
        _, specification = self.add_page('Specification'); self.specification.setMaximumHeight(16777215); specification.addWidget(self.specification, 1)
        self.prepare_button = next(button for button in controls if button.text().startswith('Prepare reviewed')); specification.addWidget(self.prepare_button)
        self.graph = EvidenceGraph(theme) if theme is not None else None
        if self.graph is not None:
            _, graph_layout = self.add_page('Evidence graph'); graph_layout.addWidget(self.graph,1)
            graph_note = QLabel('Stored relationships only. No links or scientific support are inferred. View shows up to 200 records.'); graph_note.setWordWrap(True); graph_layout.addWidget(graph_note)
        root.addWidget(self.detail); self.detail.setMaximumHeight(160)
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
        if not envelope['ok']: self.detail.setPlainText(envelope['error']); return
        self.project_id = envelope['value']; self.projects.addItem(objective, self.project_id)
        self.projects.setCurrentIndex(self.projects.findData(self.project_id))
        if self.objective.text().strip() == objective: self.objective.clear()
        self.refresh()

    def _tab_changed(self, index):
        if index != 3: self.play_timer.stop()
        if index == 2: self.inspect_evidence(); self.evidence_summary.setPlainText(self.detail.toPlainText())

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
            if not envelope['ok']: self.detail.setPlainText(envelope['error']); return
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
            snapshot = value['snapshot']
            if snapshot:
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
        if not identifier or self._result_reading: return
        text = self.run_filter.text().casefold(); metadata = self._meta_rows.get(identifier, {})
        key = (identifier, metadata.get('updated'), metadata.get('completed_runs'), metadata.get('status'), text)
        if self._result_key == key: return
        self._result_reading = True
        def read():
            return self.manager.get(identifier,True,run_limit=500,run_filter=text)
        def apply(envelope):
            self._result_reading = False
            if not envelope['ok']: self.detail.setPlainText(envelope['error']); return
            if identifier != self.selected_id():
                if self.isVisible(): self.select()
                return
            row = envelope['value']; self._result_key = key
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
        except ValueError as exc: self.detail.setPlainText(str(exc)); return
        self._bridge_preparing = True; self.prepare_button.setEnabled(False)
        def completed(envelope):
            self._bridge_preparing = False; self.prepare_button.setEnabled(True)
            if not envelope['ok']: self.detail.setPlainText(envelope['error']); return
            row = envelope['value']; self.project_id = row['project_id']
            self._pending_select_id = row['id']
            if self.projects.findData(self.project_id) < 0: self.projects.addItem(self.runtime.project(self.project_id).objective[:100], self.project_id)
            self.projects.setCurrentIndex(self.projects.findData(self.project_id)); self.refresh()
            for index in range(self.experiments.rowCount()):
                if self.experiments.item(index, 0).data(Qt.UserRole) == row['id']: self.experiments.selectRow(index); break
            self.tabs.setCurrentIndex(0)
        project_id = self.project_id or None
        self.bridge.submit('research-prepare', lambda: self.manager.prepare(spec, project_id=project_id), completed)

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
    """Existing Builder forms, review controls and terminal in the new route."""
    def __init__(self, window):
        super().__init__(); self.owner = window
        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 20)
        heading = QLabel('Projects'); heading.setProperty('role', 'title'); root.addWidget(heading)
        note = QLabel('Plan, build, test and review using the established Builder runtime.'); note.setProperty('role', 'secondary'); root.addWidget(note)
        setup = QHBoxLayout()
        for field in (window.project_folder_input, window.project_add_btn, window.project_mode_btn): setup.addWidget(field)
        root.addLayout(setup)
        access = QHBoxLayout()
        for field in (window.folder_access_btn, window.full_access_btn, window.project_lookup_btn): access.addWidget(field)
        window.project_lookup_btn.setAccessibleName('Project lookup scope'); window.project_lookup_btn.setProperty('morice_icon','search'); window.project_lookup_btn.show()
        access.addStretch(1); root.addLayout(access)
        root.addWidget(window.mode_status); root.addWidget(window.changes_summary)
        window.changes_content.setParent(self); root.addWidget(window.changes_content, 1); window.changes_content.show()
        window.changes_content.setMinimumWidth(0); window.project_workspace_stack.setMinimumWidth(0)


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
        self.owner.navigate('activity' if name == 'Activity' else 'tools')
        tools = ('System', 'Notes', 'Browser', 'Media', 'Desktop')
        if name in tools:
            self.tabs.setCurrentIndex(1); self.owner.assistant_hub.tools_subtabs.setCurrentIndex(tools.index(name))
        elif name != 'Activity': self.tabs.setCurrentIndex({'Files': 0, 'Tools': 1, 'Platform': 2, 'Dashboard': 3}.get(name, 0))
