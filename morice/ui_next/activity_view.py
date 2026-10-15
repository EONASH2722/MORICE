"""Public task/event presentation; the Kernel owns execution and verification."""
from collections import OrderedDict, deque
from datetime import datetime

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTableView, QListWidget, QPushButton


PUBLIC_STATES = {'task_queued': 'Queued', 'task_started': 'Working', 'task_progress': 'Working',
    'task_waiting': 'Waiting for resources', 'task_resumed': 'Working', 'task_verifying': 'Verifying',
    'task_completed': 'Completed', 'task_failed': 'Failed', 'user_cancelled': 'Cancelled',
    'media_queued': 'Queued', 'media_started': 'Generating', 'media_completed': 'Completed',
    'media_failed': 'Failed', 'media_cancelled': 'Cancelled', 'media_oom': 'Memory pressure'}


class PublicTaskModel(QAbstractTableModel):
    columns = ('Task', 'Service', 'State', 'Public progress', 'Updated')

    def __init__(self, parent=None):
        super().__init__(parent); self.rows = OrderedDict(); self.maximum = 128

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal: return self.columns[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows): return None
        row = tuple(self.rows.values())[index.row()]
        if role == Qt.DisplayRole: return row['display'][index.column()]
        if role == Qt.ToolTipRole: return row['task_id'] + '\n' + row['progress']
        if role == Qt.UserRole: return row['task_id']
        return None

    def consume(self, event, *, notify=True):
        kind = event['type']; identifier = event['task_id']
        if kind not in PUBLIC_STATES or not identifier: return
        prior = self.rows.get(identifier)
        if prior and prior['timestamp'] > event['timestamp']: return
        payload = event['payload']; done = payload.get('completed', payload.get('step')); total = payload.get('planned', payload.get('total_steps'))
        progress = f'{done} / {total}' if done is not None and total is not None else payload.get('stage') or payload.get('reason') or ''
        updated = datetime.fromtimestamp(event['timestamp']).strftime('%H:%M:%S')
        row = {'task_id': identifier, 'timestamp': event['timestamp'], 'state': PUBLIC_STATES[kind], 'progress': progress,
            'display': (identifier[:12], event['source'], PUBLIC_STATES[kind], progress, updated)}
        if identifier not in self.rows:
            if len(self.rows) >= self.maximum:
                if notify: self.beginRemoveRows(QModelIndex(), 0, 0)
                self.rows.popitem(last=False)
                if notify: self.endRemoveRows()
            index = len(self.rows)
            if notify: self.beginInsertRows(QModelIndex(), index, index)
            self.rows[identifier] = row
            if notify: self.endInsertRows()
        else:
            self.rows[identifier] = row
            if notify:
                index = tuple(self.rows).index(identifier)
                self.dataChanged.emit(self.index(index, 0), self.index(index, len(self.columns)-1))


class ActivityWorkspace(QWidget):
    def __init__(self, window, bridge):
        super().__init__(); self.owner = window; self.runtime = window.runtime
        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 20)
        title = QLabel('Activity'); title.setProperty('role', 'title'); root.addWidget(title)
        note = QLabel('Actual tasks, resource waits and verification stages. Private reasoning stays private.'); note.setWordWrap(True); note.setProperty('role', 'secondary'); root.addWidget(note)
        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        runtime = QWidget(); layout = QVBoxLayout(runtime); self.model = PublicTaskModel(self)
        self.table = QTableView(); self.table.setModel(self.model); self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection); self.table.horizontalHeader().setStretchLastSection(True); layout.addWidget(self.table, 1)
        self.events = QListWidget(); self.events.setMaximumHeight(200); layout.addWidget(self.events)
        self.tabs.addTab(runtime, 'Runtime'); self.tabs.addTab(window.assistant_hub.activity_group_page, 'Workspace / logs')
        queue = QWidget(); queue_layout = QVBoxLayout(queue); queue_layout.addWidget(window.queue_list)
        row = QHBoxLayout()
        for field in (window.queue_up_btn, window.queue_down_btn, window.queue_remove_btn, window.queue_clear_btn): row.addWidget(field)
        queue_layout.addLayout(row); self.tabs.addTab(queue, 'Prompt queue')
        buttons = QHBoxLayout()
        for label, callback in (('Cancel selected task', self.cancel_selected), ('Cancel response', window._cancel_current_work), ('Diagnostics', window._open_diagnostics)):
            button = QPushButton(label); button.clicked.connect(callback); buttons.addWidget(button)
        root.addLayout(buttons); self.status = QLabel('No task progress received yet.'); root.addWidget(self.status)
        self._public_events = deque(maxlen=200)
        bridge.event_arrived.connect(self.runtime_event)

    def runtime_event(self, event):
        self.model.consume(event, notify=self.isVisible())
        if event['type'] in PUBLIC_STATES:
            text = f"{datetime.fromtimestamp(event['timestamp']).strftime('%H:%M:%S')} · {event['source']} · {PUBLIC_STATES[event['type']]} · {event['task_id'][:12]}"
            self._public_events.appendleft(text)
            if self.isVisible():
                self.events.insertItem(0, text)
                while self.events.count() > 200: self.events.takeItem(self.events.count()-1)
                self.status.setText(f'{self.model.rowCount()} recent tasks · {self.events.count()} public events')

    def showEvent(self, event):
        self.model.beginResetModel(); self.model.endResetModel()
        self.events.clear(); self.events.addItems(list(self._public_events))
        self.status.setText(f'{self.model.rowCount()} recent tasks · {self.events.count()} public events')
        super().showEvent(event)

    def cancel_selected(self):
        index = self.table.currentIndex()
        if not index.isValid(): self.status.setText('Select a task first.'); return
        identifier = self.model.data(index, Qt.UserRole); row = self.model.rows.get(identifier)
        if row is None or row['state'] in {'Completed', 'Failed', 'Cancelled'}: self.status.setText('This task is already terminal.'); return
        requested = self.runtime.kernel.cancel(identifier)
        self.status.setText('Cancellation requested from the existing scheduler.' if requested else 'No cancellable scheduler task currently owns this identifier.')
