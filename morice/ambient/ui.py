"""Compact user controls; accounts and monitoring are off until explicitly enabled."""
from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QTabWidget,QWidget,QLabel,
    QPushButton,QLineEdit,QListWidget,QMessageBox,QFileDialog,QInputDialog)

from ..kernel import ExecutionContext,TaskNode,VerificationPolicy


class AmbientDialog(QDialog):
    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.runtime,self.service = runtime,runtime.ambient
        self.setWindowTitle("MORICE • Ambient & Security")
        self.resize(840,580)
        self._jobs = []
        self._flows = {}
        self._flow_jobs = set()
        layout = QVBoxLayout(self)
        self.status = QLabel()
        layout.addWidget(self.status)
        tabs = QTabWidget(); layout.addWidget(tabs)
        watches = QWidget(); w = QVBoxLayout(watches); tabs.addTab(watches,"Watches")
        self.watch_request = QLineEdit(); self.watch_request.setPlaceholderText("Notify when a build completes / experiment fails / battery below 15%")
        w.addWidget(self.watch_request)
        row=QHBoxLayout(); w.addLayout(row)
        self._button(row,"Create watch",self._create)
        self._button(row,"Enable / pause",self._toggle_watch)
        self._button(row,"Delete",self._delete_watch)
        self._button(row,"Review pending action",self._confirm)
        self._button(row,"Start monitoring",lambda:self._guard(lambda:self.service.start(user_confirmed=True)))
        self._button(row,"Stop",self.service.stop)
        self.watch_list=QListWidget(); w.addWidget(self.watch_list)
        self.events=QListWidget(); w.addWidget(self.events)
        providers=QWidget(); p=QVBoxLayout(providers); tabs.addTab(providers,"Connectors")
        p.addWidget(QLabel("GitHub issues • Official OAuth device authorization • External writes need separate exact approval"))
        self.repository=QLineEdit(); self.repository.setPlaceholderText("owner/repository")
        self.client=QLineEdit(); self.client.setPlaceholderText("Registered GitHub OAuth app client id (device flow enabled)")
        p.addWidget(self.repository);p.addWidget(self.client)
        row=QHBoxLayout();p.addLayout(row)
        self._button(row,"Add GitHub",self._add_provider)
        self._button(row,"Authorize read access",self._authorize)
        self._button(row,"Enable polling",self._poll)
        self._button(row,"Disconnect",self._disconnect)
        self.connector_list=QListWidget();p.addWidget(self.connector_list)
        p.addWidget(QLabel("Webhook ingestion uses the signed adapter API. Public receiver hosting is configured separately.\nDisconnect removes local credentials and watches. Revoke the OAuth app in GitHub settings to revoke server access."))
        security=QWidget();s=QVBoxLayout(security);tabs.addTab(security,"Security")
        self.security_status=QLabel();s.addWidget(self.security_status)
        self.scope=QLineEdit();self.scope.setPlaceholderText("Optional directory for scoped file metadata monitoring")
        s.addWidget(self.scope)
        row=QHBoxLayout();s.addLayout(row)
        self._button(row,"Enable selected sources",self._enable_security)
        self._button(row,"Scan now",lambda:self._guard(lambda:self._work(lambda:self.runtime.kernel.dispatch("security.scan",{}))))
        self._button(row,"Disable",self.service.security.disable)
        self._button(row,"Stop selected process",self._terminate)
        self._button(row,"Quarantine file",self._quarantine)
        self.findings=QListWidget();s.addWidget(self.findings)
        row=QHBoxLayout();s.addLayout(row)
        self._button(row,"Mark false positive",self._ignore)
        self._button(row,"Restore selected quarantine",self._restore)
        self.quarantines=QListWidget();s.addWidget(self.quarantines)
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self._refresh);self.timer.start()
        self._refresh()

    def _button(self, layout, label, callback):
        button=QPushButton(label);button.clicked.connect(lambda:self._guard(callback));layout.addWidget(button)

    def _guard(self, callback):
        try:
            callback()
        except Exception as exc:
            QMessageBox.warning(self,"MORICE",str(exc)[:300])

    def _work(self, callback, completed=None):
        future=self.runtime.workers.submit("ambient-user-action",callback,priority="interactive")
        self._jobs.append((future,completed))

    def _selected(self, widget, values):
        index=widget.currentRow()
        if not 0 <= index < len(values):
            raise ValueError("Select an item first.")
        return values[index]

    def _create(self):
        watch=self.service.from_request(self.watch_request.text())
        self.service.create(watch)
        self.watch_request.clear()

    def _toggle_watch(self):
        watch=self._selected(self.watch_list,self._watch_values)
        if not watch["enabled"]:
            self.service.update(watch["trigger_id"],enabled=True,user_confirmed=True)
        else:
            self.service.update(watch["trigger_id"],paused=not watch["paused"])

    def _delete_watch(self):
        self.service.delete(self._selected(self.watch_list,self._watch_values)["trigger_id"])

    def _confirm(self):
        import json
        receipt=self._selected(self.events,self._receipt_values)
        task=self.service.preview_confirmation(receipt["key"])
        if QMessageBox.question(self,"Confirm exact watch action",task.capability_requirement+"\n"+json.dumps(task.inputs,indent=2))!=QMessageBox.Yes:
            return
        token=self.runtime.kernel.permissions.controller.issue_one_use(task.task_id,task.capability_requirement,task.inputs)
        self._work(lambda:self.service.confirm(receipt["key"],token))

    def _add_provider(self):
        from ..connectors import GitHubProvider
        cid="github-"+uuid.uuid4().hex[:8]
        self.service.connectors.register(GitHubProvider(cid,self.runtime.platform_services.vault,
            repository=self.repository.text().strip(),client_id=self.client.text().strip()))

    def _authorize(self):
        selected=self._selected(self.connector_list,self._connector_values)
        provider=self.service.connectors.providers[selected["connector_id"]]
        def ready(challenge):
            self.service.start(user_confirmed=True)
            QMessageBox.information(self,"GitHub authorization",f"Open {challenge['verification_uri']}\nEnter code: {challenge['user_code']}\nOnly the read scope is enabled locally after authorization.")
        self._work(lambda:self.service.connectors.begin_authorization(provider.descriptor.connector_id,user_confirmed=True),ready)

    def _poll(self):
        cid=self._selected(self.connector_list,self._connector_values)["connector_id"]
        self.service.configure_poll(cid,user_confirmed=True)
        self.service.start(user_confirmed=True)

    def _disconnect(self):
        cid=self._selected(self.connector_list,self._connector_values)["connector_id"]
        self._flows.pop(cid,None)
        self.service.connectors.disable(cid)

    def _enable_security(self):
        directory=self.scope.text().strip()
        self.service.security.enable(sources=("processes","files") if directory else ("processes",),
            directories=(directory,) if directory else (),user_confirmed=True)
        self.service.security.monitor_every(user_confirmed=True)
        self.service.start(user_confirmed=True)

    def _exact(self, capability, arguments, description):
        if QMessageBox.question(self,"Confirm selected action",description) != QMessageBox.Yes:
            return
        self.service.security.authorize_containment(user_confirmed=True)
        task=TaskNode(capability,arguments,verification_policy=VerificationPolicy(required=True))
        token=self.runtime.kernel.permissions.controller.issue_one_use(task.task_id,capability,arguments)
        def ready(result):
            QMessageBox.information(self,"MORICE action", "Action verified." if result.success else "Action did not verify. Review the action receipt.")
        self._work(lambda:self.runtime.kernel.run_task(task,ExecutionContext(approval_token=token)),ready)

    def _terminate(self):
        pid,okay=QInputDialog.getInt(self,"Select local process","PID",5,5,2147483647)
        if not okay:return
        identity=self.service.security.select_process(pid)
        self._exact("security.process.terminate",identity,f"Stop PID {pid}?\n{identity['executable']}\nStart identity: {identity['start_time']}")

    def _quarantine(self):
        path,_=QFileDialog.getOpenFileName(self,"Select an authorized file")
        if not path:return
        from ..security.collectors import file_hash
        digest=file_hash(path)
        self._exact("security.file.quarantine",{"path":path,"sha256":digest,"reason":"User-selected containment"},
            f"Quarantine this file from the selected monitoring scope?\n{path}\nSHA-256: {digest}")

    def _restore(self):
        record=self._selected(self.quarantines,self._quarantine_values)
        self._exact("security.file.restore",{"quarantine_id":record["id"]},
            f"Restore to {record['original_path']}?\nSHA-256: {record['sha256']}\nExisting files will not be overwritten.")

    def _ignore(self):
        finding=self._selected(self.findings,self._finding_values)
        reason,okay=QInputDialog.getText(self,"False positive","Reason for suppressing this exact finding")
        if okay:self.service.security.ignore(finding["finding_id"],reason,user_confirmed=True)

    def _refresh(self):
        for future,callback in tuple(self._jobs):
            if future.done():
                self._jobs.remove((future,callback))
                try:
                    value=future.result()
                    if callback:callback(value)
                except Exception as exc:
                    QMessageBox.warning(self,"MORICE",f"Operation failed: {type(exc).__name__}")
        snap=self.service.snapshot()
        self.status.setText(f"Ambient: {snap['health']} • queued {snap['queue_depth']} • running {snap['inflight']} • model calls {snap['metrics']['model_calls']}")
        self._watch_values=snap["watches"]; self._connector_values=snap["connectors"]
        self._finding_values=snap["security"]["findings"];self._quarantine_values=snap["security"]["quarantine"]
        for widget,values,formatter in ((self.watch_list,self._watch_values,lambda w:f"{'Paused' if w['paused'] else 'Enabled' if w['enabled'] else 'Disabled'} • {w['name']}"),
            (self.connector_list,self._connector_values,lambda p:f"{p['name']} • {p['state']}"),
            (self.findings,self._finding_values,lambda f:f"{f['severity']} • {f['status']} • {f['summary']}"),
            (self.quarantines,self._quarantine_values,lambda q:f"{q['state']} • {Path(q['original_path']).name}")):
            index=widget.currentRow();widget.clear();widget.addItems([formatter(v) for v in values]);widget.setCurrentRow(index)
        self.security_status.setText(snap["security"]["status"])
        self._receipt_values=snap["receipts"][:40]
        index=self.events.currentRow();self.events.clear();self.events.addItems([f"{r['state']} • watch {r['watch'][:8]} • task {r['task'][:8]}" for r in self._receipt_values]);self.events.setCurrentRow(index)

    def closeEvent(self,event):
        self.timer.stop()
        super().closeEvent(event)
