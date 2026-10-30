"""Native panels, actual receipts, and transient secret entry in existing Security."""
from __future__ import annotations
import base64,json,time
from pathlib import Path
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,
    QFileDialog,QComboBox,QSpinBox,QTabWidget,QPlainTextEdit,QProgressBar,QTreeWidget,QTreeWidgetItem,QInputDialog,QMessageBox)
from PySide6.QtWidgets import QScrollArea,QHeaderView
from ..ui_next.responsive import FlowLayout
from ..ui_next.file_access import require_selected_file
from ..kernel import TaskNode
from .contracts import Limits

class SecurityLabPanel(QWidget):
    def __init__(self,runtime,bridge,parent=None):
        super().__init__(parent);self.runtime=runtime;self.bridge=bridge;self.current=None;self._candidate_values=[];self._hint_files=[];self._key=None;self._vault_alias='';self._render_revision=None
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame)
        body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(8,8,8,8);scroll.setWidget(body);outer.addWidget(scroll)
        title=QLabel('Security Lab · UNLEASHED');title.setProperty('role','title');layout.addWidget(title)
        subtitle=QLabel('Actual local file analysis, authorized recovery, device diagnostics and reproducible security tests.');subtitle.setWordWrap(True);layout.addWidget(subtitle)
        self.tabs=QTabWidget();layout.addWidget(self.tabs)
        files=QWidget();f=QVBoxLayout(files);self.tabs.addTab(files,'File forensics & recovery')
        row=QHBoxLayout();self.path=QLineEdit();self.path.setPlaceholderText('Choose your encrypted archive, document or unknown local file');row.addWidget(self.path,1)
        self._button(row,'Choose file',self.choose_file);f.addLayout(row)
        form=QFormLayout();self.password=QLineEdit();self.password.setEchoMode(QLineEdit.Password);self.password.setPlaceholderText('A supplied password; never sent to the model or stored in history')
        form.addRow('Password',self.password);f.addLayout(form)
        self.advanced_sources=QWidget();advanced_layout=QVBoxLayout(self.advanced_sources);advanced_layout.setContentsMargins(0,0,0,0);advanced_form=QFormLayout()
        self.convention=QLineEdit();self.convention.setEchoMode(QLineEdit.Password);self.convention.setPlaceholderText('Optional explicit template, e.g. prefix{value}suffix')
        self.convention_values=QLineEdit();self.convention_values.setEchoMode(QLineEdit.Password);self.convention_values.setPlaceholderText('Explicit substitution values, separated by commas')
        advanced_form.addRow('Your convention',self.convention);advanced_form.addRow('Your values',self.convention_values);advanced_layout.addLayout(advanced_form)
        row=FlowLayout();self._button(row,'Candidate list…',self.choose_candidates);self._button(row,'Owner hints…',self.choose_hints)
        self._button(row,'Recovery key…',self.choose_key);self._button(row,'Saved key…',self.choose_saved_key);self._button(row,'Remember key…',self.remember_key);advanced_layout.addLayout(row)
        self.sources=QLabel('No candidate list, hint documents or direct key supplied.');self.sources.setWordWrap(True);f.addWidget(self.sources)
        row=QHBoxLayout();self.candidate_limit=QSpinBox();self.candidate_limit.setRange(1,100000);self.candidate_limit.setValue(1000)
        self.time_limit=QSpinBox();self.time_limit.setRange(1,1200);self.time_limit.setValue(60)
        row.addWidget(QLabel('Candidate limit'));row.addWidget(self.candidate_limit);row.addWidget(QLabel('Time limit (seconds)'));row.addWidget(self.time_limit);row.addStretch();f.addLayout(row)
        row=FlowLayout()
        for label,action in (('Analyze','inspect'),('Decode','decode'),('Estimate recovery','estimate'),('Recover','recover')):
            self._button(row,label,lambda _=False,a=action:self.start(a))
        self._button(row,'Cancel',self.cancel);f.addLayout(row)
        self.source_toggle=QPushButton('Recovery sources, saved keys & puzzle ciphers…');self.source_toggle.setCheckable(True);self.source_toggle.toggled.connect(self.advanced_sources.setVisible)
        f.addWidget(self.source_toggle);f.addWidget(self.advanced_sources);self.advanced_sources.hide()
        row=QHBoxLayout();self.cipher_method=QComboBox();self.cipher_method.addItems(['ROT13','ATBASH','CAESAR','VIGENERE']);row.addWidget(self.cipher_method)
        self._button(row,'Decode explicit toy cipher',lambda:self.start('cipher'));advanced_layout.addLayout(row);f.addStretch(1)
        devices=QWidget();d=QVBoxLayout(devices);self.tabs.addTab(devices,'Device diagnostics')
        d.addWidget(QLabel('Uses an owned loopback ADB server. Android’s normal pairing and debugging authorization apply.'))
        row=QHBoxLayout();self._button(row,'Discover Android',lambda:self.start('devices'));self._button(row,'Bluetooth metadata',lambda:self.start('bluetooth'));d.addLayout(row)
        form=QFormLayout();self.device=QComboBox();self.package=QLineEdit();self.package.setPlaceholderText('Optional Android package, e.g. com.example.myapp')
        self.endpoint=QLineEdit();self.endpoint.setPlaceholderText('Device IP:port shown by Android Wireless debugging')
        self.pair_code=QLineEdit();self.pair_code.setEchoMode(QLineEdit.Password);self.pair_code.setMaxLength(6)
        for label,widget in (('Selected device',self.device),('Application',self.package),('Wireless endpoint',self.endpoint),('Pairing code',self.pair_code)):form.addRow(label,widget)
        d.addLayout(form);row=QHBoxLayout()
        self._button(row,'Pair',lambda:self.start('devices',command='pair'));self._button(row,'Connect',lambda:self.start('devices',command='connect'))
        self._button(row,'Read diagnostics',lambda:self.start('devices',command='diagnose'));d.addLayout(row)
        d.addWidget(QLabel('Bluetooth reports observed Windows device metadata. BLE GATT/system control is unavailable in this adapter.'))
        audits=QWidget();a=QVBoxLayout(audits);self.tabs.addTab(audits,'Code audit & challenges')
        row=QHBoxLayout();self.project=QLineEdit();self.project.setPlaceholderText('Select the local project to inspect');row.addWidget(self.project,1);self._button(row,'Choose project',self.choose_project);a.addLayout(row)
        row=QHBoxLayout();self._button(row,'Audit selected code',lambda:self.start('audit'));self._button(row,'Run owned messaging challenge',lambda:self.start('challenge'));a.addLayout(row)
        note=QLabel('Static matches remain POSSIBLE until reproduced. The messaging challenge uses isolated fixture accounts, verifies recipient readback, repairs the planted authorization defect and reruns the same check. It does not claim to be your live VOX backend.');note.setWordWrap(True);a.addWidget(note)
        self._button(a,'Prepare selected finding in Builder',self.prepare_repair)
        self.vox_note=QLabel('Live VOX: no repository/endpoints/test accounts configured. Select its actual local source for an audit; no message is sent to a guessed handle.');self.vox_note.setWordWrap(True);a.addWidget(self.vox_note)
        web=QWidget();w=QVBoxLayout(web);self.tabs.addTab(web,'Web/API & VOX')
        self.origin=QLineEdit();self.origin.setPlaceholderText('One authorized origin, e.g. http://127.0.0.1:8080');w.addWidget(self.origin)
        self._button(w,'Read endpoint security headers',lambda:self.start('endpoint'))
        self.vox_manifest=QLineEdit();self.vox_manifest.setPlaceholderText('Owner-provided JSON mapping for the actual VOX API and source repository');w.addWidget(self.vox_manifest)
        self._button(w,'Choose actual VOX mapping…',self.choose_vox_manifest)
        self.sender_token=QLineEdit();self.sender_token.setEchoMode(QLineEdit.Password);self.recipient_token=QLineEdit();self.recipient_token.setEchoMode(QLineEdit.Password)
        form=QFormLayout();form.addRow('Authorized sender token',self.sender_token);form.addRow('Authorized recipient token',self.recipient_token);w.addLayout(form)
        self.vox_scope=QLabel('No live target selected. Supply the real mapping and both test identities; endpoints are never guessed.');self.vox_scope.setWordWrap(True);self.vox_scope.setTextFormat(Qt.PlainText);w.addWidget(self.vox_scope)
        self._button(w,'Verify mapped VOX delivery',lambda:self.start('vox'))
        results=QWidget();self.results_tab=results;r=QVBoxLayout(results);self.tabs.addTab(results,'Results & evidence')
        self.history=QComboBox();self.history.setAccessibleName('Saved Security Lab receipts');self.history.currentIndexChanged.connect(self.select_receipt);r.addWidget(self.history)
        self.summary=QLabel('Choose an operation to create an actual result.');self.summary.setWordWrap(True);r.addWidget(self.summary)
        self.table=QTreeWidget();self.table.setHeaderLabels(['Observed field / test','Value / outcome']);r.addWidget(self.table)
        self.table.setColumnWidth(0,240);self.table.header().setSectionResizeMode(1,QHeaderView.Stretch)
        self.evidence=QPlainTextEdit();self.evidence.setReadOnly(True);self.evidence.setMaximumHeight(180);r.addWidget(self.evidence)
        row=QHBoxLayout();self._button(row,'Export recovered files…',lambda:self.export(False));self._button(row,'Export report…',lambda:self.export(True));r.addLayout(row)
        self._button(r,'Clear selected local cache…',self.clear_receipt)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);layout.addWidget(self.progress)
        self.status=QLabel('Ready. Original files are opened read-only; recovered output goes to a separate local job directory.');self.status.setWordWrap(True);self.status.setTextFormat(Qt.PlainText);self.summary.setTextFormat(Qt.PlainText);layout.addWidget(self.status)
        self.timer=QTimer(self);self.timer.setInterval(200);self.timer.timeout.connect(self.refresh)
    @property
    def lab(self):return self.runtime.security_lab
    def _button(self,layout,label,callback):
        button=QPushButton(label);button.clicked.connect(callback);layout.addWidget(button);return button
    def _guard(self,operation):
        try:return operation()
        except Exception as exc:self.status.setText(str(exc)[:500]);return None
    def choose_file(self):
        def selected():
            require_selected_file(self.runtime,'file_read');value,_=QFileDialog.getOpenFileName(self,'Analyze an owned local file')
            if value:self.path.setText(self.lab.select(value))
        self._guard(selected)
    def choose_project(self):
        value=QFileDialog.getExistingDirectory(self,'Choose the project you want to audit')
        if value:self.project.setText(value)
    def choose_candidates(self):
        def selected():
            require_selected_file(self.runtime,'file_read');value,_=QFileDialog.getOpenFileName(self,'Owner-supplied UTF-8 password candidates')
            if value:
                path=Path(value)
                if path.stat().st_size>1024**2:raise ValueError('Candidate list exceeds 1 MiB.')
                self._candidate_values=path.read_text(encoding='utf-8-sig').splitlines()
                if len(self._candidate_values)>100000:raise ValueError('Too many candidates.')
                self.sources.setText(str(len(self._candidate_values))+' explicit candidate lines loaded privately.')
        self._guard(selected)
    def choose_hints(self):
        values,_=QFileDialog.getOpenFileNames(self,'Select owner-provided hint documents')
        if values:self._hint_files=values[:8];self.sources.setText(str(len(self._hint_files))+' explicitly selected hint documents.')
    def choose_key(self):
        def selected():
            require_selected_file(self.runtime,'file_read');value,_=QFileDialog.getOpenFileName(self,'Select your recovery-key file')
            if value:
                path=Path(value)
                if path.stat().st_size>4096:raise ValueError('Key file is too large.')
                raw=path.read_bytes()
                if len(raw)!=32:
                    text=raw.decode('ascii').strip()
                    try:raw=bytes.fromhex(text)
                    except ValueError:raw=base64.b64decode(text,validate=True)
                if len(raw)!=32:raise ValueError('Use a raw, hex or base64-encoded 32-byte key.')
                self._key=raw;self.sources.setText('A 32-byte owner-supplied key is loaded privately.')
        self._guard(selected)
    def choose_saved_key(self):
        aliases=[name for name in self.runtime.platform_services.vault.keys() if name.startswith('security_lab.recovery.')]
        if not aliases:self.status.setText('No explicitly saved lab recovery key exists. Import a key file first.');return
        alias,ok=QInputDialog.getItem(self,'Authorized recovery key','Key alias',aliases,0,False)
        if ok:self._vault_alias=alias;self.sources.setText('An explicitly saved recovery-key alias is selected.')
    def remember_key(self):
        if self._key is None:self.status.setText('Import your 32-byte recovery key first.');return
        alias,ok=QInputDialog.getText(self,'Save authorized recovery key','A name for this key (stored through MORICE’s DPAPI vault)')
        if ok:self._guard(lambda:self.lab.remember_key(alias,self._key))
    def choose_vox_manifest(self):
        def selected():
            value,_=QFileDialog.getOpenFileName(self,'Select your actual VOX API mapping',filter='JSON (*.json)')
            if not value:return
            path=Path(value)
            if path.stat().st_size>65536:raise ValueError('Mapping exceeds its size limit.')
            config=json.loads(path.read_text(encoding='utf-8'));self.vox_manifest.setText(value)
            self.vox_scope.setText('Selected origin: '+str(config.get('origin',''))+'\nSender: '+str(config.get('sender_id',''))+'\nRecipient: '+str(config.get('recipient_id',''))+'\nThe button explicitly requests one authenticated challenge delivery and recipient readback.')
        self._guard(selected)
    def _conversation(self):return getattr(self.window(),'_chat_id','')
    def _prepare(self,action,conversation='',command='discover'):
        if action=='cancel':
            running=[row for row in self.lab.jobs.values() if row['action']=='recover' and row['state'] in {'QUEUED','RUNNING','VERIFYING'} and (not conversation or row.get('conversation')==conversation)]
            return {'job_id':running[0]['id']} if len(running)==1 else {'question':'No unique active recovery job is available; select the intended running job in Results.'}
        if action in {'status','export'}:
            identifier=self.current or self.lab.latest
            if not identifier:return {'question':'Run or select an actual Security Lab result first.'}
            if action=='export':return self._export_selection(identifier,False)
            return {'job_id':identifier}
        path=self.project.text().strip() if action=='audit' else self.vox_manifest.text().strip() if action=='vox' else self.path.text().strip()
        if action in {'inspect','decode','cipher','estimate','recover'}:
            if not path:return {'question':'Choose the local file in Security → Security Lab first.'}
            self.lab.select(path)
        if action=='audit' and not path:return {'question':'Choose the local source project in Security Lab first.'}
        from .service import HEAVY
        if action in HEAVY and any(row['state'] in {'QUEUED','RUNNING','VERIFYING'} for row in self.lab.jobs.values()):
            return {'question':'A lab operation is already running. Use Results for its progress, or cancel it before starting another bounded worker.'}
        password=self.password.text();secret_ref='';options={}
        if action in {'estimate','recover'}:
            conventions=[{'template':self.convention.text(),'values':self.convention_values.text().split(',')}] if self.convention.text() else []
            secret_ref=self.lab.supply([*self._candidate_values,*([password] if password else [])],key=self._key,hint_files=self._hint_files,vault_alias=self._vault_alias,conventions=conventions)
        if action=='endpoint':options={'origin':self.origin.text().strip()}
        if action=='cipher':
            options={'cipher_method':self.cipher_method.currentText()};secret_ref=self.lab.supply([password])
        if action=='vox':
            if not path:return {'question':'Select your real VOX API mapping and authorized test identities first.'}
            secret_ref=self.lab.supply(credential_material={'sender_token':self.sender_token.text(),'recipient_token':self.recipient_token.text()})
        if action=='devices':
            options={'command':command,'endpoint':self.endpoint.text().strip(),'serial':self.device.currentData() or '', 'package':self.package.text().strip()}
            if command=='pair':secret_ref=self.lab.supply([self.pair_code.text()]);self.pair_code.clear()
        identifier=self.lab.prepare(action,path=path,secret_ref=secret_ref,limits=Limits(seconds=self.time_limit.value(),candidates=self.candidate_limit.value()),conversation=conversation,options=options)
        self.current=identifier;approval=''
        if action=='devices':approval=self._approve(identifier,action)
        return {'job_id':identifier,'approval_token':approval}
    def _approve(self,identifier,action):
        # The button/file-dialog selection is the user's exact request. A DENIED
        # state still blocks this token at the shared Kernel permission boundary.
        return self.lab.approve(identifier,action)
    def start(self,action,command='discover'):
        def run():
            value=self._prepare(action,self._conversation(),command)
            if value.get('question'):self.status.setText(value['question']);return
            identifier=value['job_id'];self.status.setText('Queued actual '+action+' operation…');self.progress.setRange(0,0)
            def done(envelope):
                if not envelope['ok']:self.status.setText(envelope['error'])
                else:
                    result=envelope['value']
                    if not result.success:self.status.setText('; '.join(e.message for e in result.errors));self.progress.setRange(0,100);return
                    self.tabs.setCurrentWidget(self.results_tab);self._render_revision=None;self.refresh()
            self.bridge.submit('Security Lab '+action,lambda:self.lab.run(action,identifier,approval_token=value.get('approval_token','')),done)
            if action=='recover':self.password.clear();self.convention.clear();self.convention_values.clear();self._candidate_values=[];self._key=None
            if action=='vox':self.sender_token.clear();self.recipient_token.clear()
        self._guard(run)
    def prepare_nlui(self,action,conversation):return self._prepare(action,conversation)
    def cancel(self):
        if self.lab.cancel(self.current):self.status.setText('Cancellation requested; the owned worker and partial output will be cleaned up.')
        else:self.status.setText('No active recovery operation is running.')
    def _export_selection(self,identifier,report):
        permission='file_write';require_selected_file(self.runtime,permission)
        parent=QFileDialog.getExistingDirectory(self,'Choose a destination parent; a new export is created')
        if not parent:return {'question':'Export cancelled; no destination was written.'}
        suffix=('.json' if report else '');name=('morice-report-' if report else 'morice-recovered-')+identifier[:10]+suffix
        self.lab.jobs[identifier].setdefault('options',{})['export_destination']=str(Path(parent)/name)
        return {'job_id':identifier,'approval_token':self._approve(identifier,'report' if report else 'export')}
    def export(self,report):
        def run():
            identifier=self.current or self.lab.latest
            if not identifier:raise ValueError('No actual result is selected.')
            value=self._export_selection(identifier,report)
            if value.get('question'):self.status.setText(value['question']);return
            action='report' if report else 'export'
            self.bridge.submit('Security Lab export',lambda:self.lab.run(action,identifier,approval_token=value['approval_token']),
                lambda envelope:self.status.setText(envelope['value'].output.get('message','Export failed.') if envelope['ok'] and envelope['value'].success else 'Export did not complete; no success is claimed.'))
        self._guard(run)
    def prepare_repair(self):
        def run():
            job=self.lab.snapshot(self.current);findings=job.get('result',{}).get('findings',[])
            if not findings:raise ValueError('Select an actual code audit with source-referenced findings first.')
            item=self.table.currentItem();finding=item.data(0,Qt.UserRole) if item is not None else None
            if not isinstance(finding,dict) or not finding.get('file'):raise ValueError('Select a source-referenced finding row in Results first.')
            from .contracts import sha256
            root=Path(job['path']).resolve();source=(root/finding['file']).resolve()
            if not source.is_relative_to(root) or sha256(source)!=finding['source_sha256']:raise ValueError('Source changed since the audit. Rerun the audit before preparing a repair.')
            window=self.window();window.navigate('projects')
            request='Review and fix the security candidate at '+finding.get('file','')+':'+str(finding.get('line',''))+' in '+self.project.text()+'. '+finding.get('evidence','')+' Verify the source hash, add a regression test, and use the existing Builder review/apply/test workflow.'
            window.input.setText(request);window.status_line.setText('Security evidence supplied to existing Builder. Select the matching project and send to prepare a reviewed repair.')
        self._guard(run)
    def select_receipt(self,index):
        value=self.history.itemData(index)
        if value:self.current=value;self._render_revision=None;self.refresh()
    def clear_receipt(self):
        def run():
            identifier=self.current or self.lab.latest
            if not identifier:raise ValueError('Select a completed local receipt first.')
            require_selected_file(self.runtime,'file_write')
            if QMessageBox.question(self,'Clear this cached job?','Remove this receipt and its unexported output? Original inputs and exported files are retained.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
            token=self.lab.approve(identifier,'clear')
            def done(envelope):
                if envelope['ok'] and envelope['value'].success:
                    self.current=self.lab.latest;self._render_revision=None;self.status.setText(envelope['value'].output['message'])
                    if self.current:self.refresh()
                    else:
                        self.history.blockSignals(True);self.history.clear();self.history.blockSignals(False);self.table.clear();self.evidence.clear();self.summary.setText('No cached Security Lab result selected.')
                else:self.status.setText('Cache was not cleared; cancel and finish running work before removal.')
            self.bridge.submit('Clear selected lab cache',lambda:self.lab.run('clear',identifier,approval_token=token),done)
        self._guard(run)
    def refresh(self):
        if self.runtime._security_lab is None:return
        identifier=self.current or self.lab.latest
        if not identifier:return
        try:job=self.lab.snapshot(identifier)
        except (ValueError,PermissionError):return
        progress=job.get('progress',{});total=progress.get('total_candidates',progress.get('planned',0));tested=progress.get('tested',progress.get('completed',0))
        if job['state'] in {'RUNNING','VERIFYING'}:
            if total:self.progress.setRange(0,int(total));self.progress.setValue(int(tested))
            else:self.progress.setRange(0,0)
            self.status.setText('Actual '+job['action']+' work: '+str(tested)+' / '+str(total)+' candidates/steps; '+str(progress.get('remaining_candidates','?'))+' remaining.')
        else:self.progress.setRange(0,100);self.progress.setValue(100);self.status.setText(self.lab.describe(job))
        revision=(job['id'],job['state'],job['status'],json.dumps(progress,sort_keys=True))
        if revision==self._render_revision:return
        self._render_revision=revision;self.summary.setText(self.lab.describe(job));self.table.clear()
        records=sorted(self.lab.jobs.values(),key=lambda row:row['created'],reverse=True)
        if [self.history.itemData(i) for i in range(self.history.count())]!=[row['id'] for row in records]:
            self.history.blockSignals(True);self.history.clear()
            for row in records:self.history.addItem(row['action']+' · '+row['status']+' · '+row['id'][:8],row['id'])
            self.history.setCurrentIndex(self.history.findData(identifier));self.history.blockSignals(False)
        for index,row in enumerate(records):self.history.setItemText(index,row['action']+' · '+row['status']+' · '+row['id'][:8])
        value=job.get('result',{})
        for key,item in value.items():
            if key in {'artifacts','attempts','findings','tests','devices'}:
                for row in item[:200]:
                    label=Path(row['path']).name if key=='artifacts' and row.get('path') else next((row[name] for name in ('name','test','file','candidate_index','serial') if name in row),key)
                    description=(str(row.get('bytes',0))+' bytes · SHA-256 '+str(row.get('sha256',''))) if key=='artifacts' else json.dumps(row,ensure_ascii=False)[:1000]
                    item=QTreeWidgetItem(self.table,[str(label),description])
                    if row.get('path'):item.setToolTip(1,row['path'])
                    if key=='findings':item.setData(0,Qt.UserRole,row)
            elif isinstance(item,dict):
                parent=QTreeWidgetItem(self.table,[key,'Observed source metadata'])
                for name,observed in item.items():QTreeWidgetItem(parent,[str(name),json.dumps(observed,ensure_ascii=False)[:1000]])
                parent.setExpanded(True)
            elif not isinstance(item,(dict,list)):QTreeWidgetItem(self.table,[key,str(item)[:1000]])
        self.evidence.setPlainText(json.dumps(value,indent=2,ensure_ascii=False)[:24000])
        if job['action']=='devices' and value.get('devices'):
            selected=self.device.currentData();self.device.clear()
            for row in value['devices']:self.device.addItem(row['serial']+' · '+row['state'],row['serial'])
            index=self.device.findData(selected)
            if index>=0:self.device.setCurrentIndex(index)
    def showEvent(self,event):self.timer.start();self.refresh();super().showEvent(event)
    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)
    def closeEvent(self,event):self.timer.stop();self.password.clear();self._candidate_values=[];self._key=None;super().closeEvent(event)
