"""Compact Devices panel; network requests run outside the Qt UI thread."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog,
    QLabel, QListWidget, QMessageBox, QPushButton, QTextEdit, QVBoxLayout)


class DevicesDialog(QDialog):
    finished_work = Signal(str)

    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MORICE Devices")
        self.resize(660, 560)
        self.mesh = runtime.device_mesh
        self._pool = ThreadPoolExecutor(1, thread_name_prefix="morice-devices-ui")
        self._busy = False
        self._pending = None
        layout = QVBoxLayout(self)
        self.enabled_box = QCheckBox("Device Mesh enabled")
        self.enabled_box.setChecked(self.mesh.enabled)
        self.enabled_box.toggled.connect(self._enable)
        layout.addWidget(self.enabled_box)
        self.nodes = QListWidget()
        self.nodes.currentRowChanged.connect(self.refresh_details)
        layout.addWidget(self.nodes)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details)
        self.status = QLabel("Only explicitly paired devices can execute commands.")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        for label, callback in (("Pair this node", self.pair_here), ("Pair by address", self.pair_remote),
                                ("Confirm pairing", self.confirm_pair), ("Refresh", self.refresh)):
            button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        layout.addLayout(row)
        actions = QHBoxLayout()
        self.action_buttons = {}
        for label, callback in (("Ping", self.ping), ("Send file", self.send_file), ("Rename", self.rename),
                                ("Revoke", self.revoke), ("Create group", self.group)):
            button = QPushButton(label); button.clicked.connect(callback); actions.addWidget(button)
            self.action_buttons[label] = button
        layout.addLayout(actions)
        policies = QHBoxLayout()
        for label, callback in (("Permissions", self.permissions), ("Default device", self.default_device),
                                ("Edit group", self.edit_group), ("Delete group", self.delete_group)):
            button = QPushButton(label); button.clicked.connect(callback); policies.addWidget(button)
        layout.addLayout(policies)
        self.finished_work.connect(self._done)
        self._timer = QTimer(self); self._timer.timeout.connect(self.refresh_details); self._timer.start(2000)
        self.refresh()

    def _run(self, callback):
        if self._busy:
            self.status.setText("A device operation is still running."); return
        self._busy = True
        def run():
            try:
                result = callback()
                text = "Operation finished." if result is None else str(result)
            except Exception as error:
                text = str(error)
            self.finished_work.emit(text[:1600])
        self._pool.submit(run)

    def _done(self, text):
        self._busy = False; self.status.setText(text); self.refresh()

    def _enable(self, enabled):
        def change():
            (self.mesh.enable if enabled else self.mesh.disable)()
            from ..settings import load_settings, save_settings
            settings = load_settings(); settings["device_mesh_enabled"] = "true" if enabled else "false"; save_settings(settings)
        self._run(change)

    def refresh(self):
        selected = self.nodes.currentRow()
        self.rows = self.mesh.registry.snapshot()
        self.nodes.blockSignals(True); self.nodes.clear()
        for row in self.rows:
            self.nodes.addItem(f"{row['name']} · {row['platform']} · {row['connection']} · {row['trust']}")
        self.nodes.blockSignals(False)
        if self.rows:
            self.nodes.setCurrentRow(min(max(0, selected), len(self.rows) - 1))
        self.refresh_details()

    def selected(self):
        index = self.nodes.currentRow()
        if not 0 <= index < len(self.rows):
            raise ValueError("Select a paired device first.")
        return self.rows[index]["node_id"]

    def refresh_details(self, *args):
        self.action_buttons["Send file"].setVisible(False)
        for label in ("Rename", "Revoke", "Ping"):
            self.action_buttons[label].setEnabled(False)
        try:
            node = self.selected()
            row = next(r for r in self.mesh.registry.snapshot() if r["node_id"] == node)
            row["permissions"] = {k.split("|", 1)[1]: v for k, v in self.mesh.registry.permissions.items() if k.startswith(node + "|")}
            row["session_permissions"] = {cap: self.mesh.kernel.permissions.controller.state(f"node:{node}:{cap}").value for cap in row["capabilities"]}
            row["streams"] = self.mesh.streams.snapshot()
            row["groups"] = self.mesh.registry.groups
            for label in ("Rename", "Revoke", "Ping"):
                self.action_buttons[label].setEnabled(row["trust"] == "trusted")
            self.action_buttons["Send file"].setVisible(row["trust"] == "trusted" and "file.receive" in row["capabilities"] and row["capabilities"]["file.receive"] in {"available", "degraded"})
            self.details.setPlainText(json.dumps(row, indent=2))
        except (ValueError, StopIteration):
            self.details.setPlainText("No devices paired. Device Mesh works without remote devices.")

    def pair_here(self):
        def begin():
            self.mesh.enable()
            value = self.mesh.transport.enable_pairing()
            return f"Pairing expires in 120 seconds. Pair port: {value['pair_port']}\nCode: {value['code']}\nCertificate fingerprint: {value['fingerprint']}\nConfirm the requesting device here before granting status/files."
        self._run(begin)

    def pair_remote(self):
        text, okay = QInputDialog.getText(self, "Pair owned device", "Enter host:pair-port, six-digit code, full certificate fingerprint (separated by spaces):")
        if not okay:
            return
        def pair():
            endpoint, code, pin = text.strip().split()
            host, port = endpoint.rsplit(":", 1)
            self._pending = self.mesh.begin_pair(host, int(port), code, pin, user_confirmed=True)
            return "Confirm this device on the other node, then click Confirm pairing here to allow status and Inbox files."
        self._run(pair)

    def confirm_pair(self):
        selected = None
        if not self._pending:
            pending = [v for v in self.mesh.transport.pairing_status()["pending"] if v["state"] == "pairing"]
            if len(pending) != 1:
                self.status.setText("Exactly one requesting device must be pending."); return
            selected = pending[0]
            question = f"Allow {selected['name']}\nIdentity: {selected['node_id']}\nto read device status and receive files in this node's Inbox?"
            confirmation = QMessageBox(self)
            confirmation.setWindowTitle("Confirm requesting device")
            confirmation.setTextFormat(Qt.PlainText)
            confirmation.setText(question)
            confirmation.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            confirmation.setDefaultButton(QMessageBox.No)
            if confirmation.exec() != QMessageBox.Yes:
                return
        def confirm():
            if self._pending:
                self.mesh.finish_pair(self._pending, outbound_permissions=("device.status", "file.receive"), user_confirmed=True)
                self._pending = None
                return "Paired; status and Inbox file transfer are permitted."
            self.mesh.approve_pair(selected["request_id"], ("device.status", "file.receive"), user_confirmed=True)
            return "Confirmed " + selected["name"] + "; the peer can now complete pairing."
        self._run(confirm)

    def ping(self):
        try:
            node = self.selected()
            self._run(lambda: self.mesh.connect(node).reason)
        except ValueError as error:
            self.status.setText(str(error))

    def send_file(self):
        try:
            node = self.selected()
            state = self.mesh.registry.nodes[node]
            if "file.receive" not in state.capabilities:
                raise ValueError("This device does not support receiving files.")
            source, _ = QFileDialog.getOpenFileName(self, "Send selected file to device Inbox")
            if source:
                self._run(lambda: self.mesh.send_file(source, node))
        except ValueError as error:
            self.status.setText(str(error))

    def rename(self):
        text, okay = QInputDialog.getText(self, "Rename device", "Friendly device name:")
        if okay:
            try:
                self.mesh.rename(self.selected(), text); self.refresh()
            except ValueError as error:
                self.status.setText(str(error))

    def revoke(self):
        try:
            node = self.selected()
            self._run(lambda: self.mesh.revoke(node, remove=True))
        except ValueError as error:
            self.status.setText(str(error))

    def group(self):
        text, okay = QInputDialog.getText(self, "Device group", "Group name (includes currently trusted listed devices):")
        if okay:
            try:
                self.mesh.registry.group(text, [v["node_id"] for v in self.rows if v["trust"] == "trusted"])
                self.status.setText("Group created. Group results retain each device's verification outcome.")
            except ValueError as error:
                self.status.setText(str(error))

    def permissions(self):
        try:
            node = self.selected()
            peer = self.mesh.store.get(node)
            if peer is None or peer.revoked:
                raise ValueError("Select a paired device before changing permissions.")
            caps = sorted(set(self.mesh.registry.nodes[node].capabilities) | set(peer.allowed_capabilities))
            cap, okay = QInputDialog.getItem(self, "Device permission", "Capability:", caps, editable=False)
            if not okay: return
            choices = ["Allow this session", "Remember allow", "Ask", "Deny", "Allow one status request"]
            choice, okay = QInputDialog.getItem(self, "Device permission", f"{node}\n{cap}", choices, editable=False)
            if not okay: return
            from ..unified_intelligence import PermissionState
            if choice == choices[4]:
                if cap != "device.status": raise ValueError("One-use UI action is currently limited to status; other exact actions use the capability API.")
                import uuid
                from ..kernel import ExecutionContext
                task_id = uuid.uuid4().hex
                token = self.mesh.grant_once(node, cap, task_id, {}, user_confirmed=True)
                self._run(lambda: self.mesh.dispatch(cap, {}, node, ExecutionContext(approval_token=token), task_id=task_id).to_dict())
                return
            state = PermissionState.GRANTED if choice in choices[:2] else PermissionState.ASK if choice == choices[2] else PermissionState.DENIED
            self.mesh.set_permission(node, cap, state, user_confirmed=True, remember=choice != choices[0]); self.refresh_details()
        except (ValueError, PermissionError) as error:
            self.status.setText(str(error))

    def default_device(self):
        reference, okay = QInputDialog.getItem(self, "Default device", "Reference:", ["phone", "tablet", "compute"], editable=False)
        if okay:
            try: self.mesh.registry.set_default(reference, self.selected()); self.refresh_details()
            except ValueError as error: self.status.setText(str(error))

    def edit_group(self):
        groups = self.mesh.registry.groups
        key, okay = QInputDialog.getItem(self, "Edit group", "Group ID:", list(groups), editable=False)
        if not okay: return
        text, okay = QInputDialog.getText(self, "Edit group", "Name, followed by comma-separated paired node IDs:", text=groups[key]["name"] + "," + ",".join(groups[key]["members"]))
        if okay:
            try:
                name, *members = (part.strip() for part in text.split(","))
                self.mesh.registry.group(name, members, group_id=key); self.refresh_details()
            except ValueError as error: self.status.setText(str(error))

    def delete_group(self):
        key, okay = QInputDialog.getItem(self, "Delete group", "Group ID:", list(self.mesh.registry.groups), editable=False)
        if okay: self.mesh.registry.delete_group(key); self.refresh_details()

    def closeEvent(self, event):
        if self._busy:
            self.status.setText("Wait for the active device operation to finish before closing.")
            event.ignore(); return
        self._timer.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)
