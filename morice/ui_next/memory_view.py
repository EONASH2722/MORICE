"""Model profile and memory controls using the existing runtime authorities."""
from __future__ import annotations

import threading
from dataclasses import asdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
    QCheckBox,QPushButton,QListWidget,QListWidgetItem,QComboBox,QFileDialog,QMessageBox,QDialog,QGridLayout)

from ..model_router import ModelRouter
from ..settings import save_settings


class FastModelSettings(QWidget):
    def __init__(self,owner):
        super().__init__(); self.owner=owner
        form=QFormLayout(self); form.setContentsMargins(0,0,0,0)
        self.automatic=QCheckBox('Select fast replies and thinking automatically')
        self.automatic.setChecked(owner.settings.get('automatic_model_selection','true')=='true')
        self.path=QLineEdit(); self.path.setReadOnly(True)
        self.name=QLineEdit(owner.settings.get('generative_model_name','')); self.name.setPlaceholderText('Optional installed Ollama model')
        self.status=QLabel(); self.status.setWordWrap(True)
        row=QHBoxLayout()
        browse=QPushButton('Change fast reply model…'); browse.clicked.connect(self.choose); row.addWidget(browse)
        reset=QPushButton('Use Qwen default'); reset.clicked.connect(self.reset); row.addWidget(reset)
        form.addRow(self.automatic); form.addRow('Fast reply GGUF',self.path); form.addRow('Fast reply Ollama model',self.name)
        form.addRow(row); form.addRow(self.status)
        self.automatic.toggled.connect(self.save); self.name.editingFinished.connect(self.save_name)
        self.refresh()

    def persist(self):
        if self.owner._session_enabled: save_settings(self.owner.settings)
        self.refresh()

    def save(self,*_):
        self.owner.settings['automatic_model_selection']=str(self.automatic.isChecked()).lower(); self.persist()

    def save_name(self):
        from ..settings import normalize_model_name
        name=normalize_model_name(self.name.text()); self.name.setText(name)
        self.owner.settings['generative_model_name']=name
        if name: self.owner.settings['generative_model_path']=''
        self.persist()

    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose fast reply GGUF','','GGUF models (*.gguf)')
        if not path: return
        result=self.owner._validate_model_file(path)
        if not result.ok or not result.direct_chat:
            self.status.setText(result.message); return
        self.owner.settings.update(generative_model_path=path,generative_model_name='')
        self.name.clear(); self.persist()

    def reset(self):
        self.owner.settings.update(generative_model_path='',generative_model_name=''); self.name.clear(); self.persist()

    def refresh(self):
        profiles=ModelRouter.reply_models(self.owner.settings)
        self.path.setText(profiles['generative']['path'] or profiles['generative_configured'])
        self.path.setToolTip(self.path.text())
        status=('Fast Ollama model is configured; availability is checked when a reply starts. ' if profiles['generative']['name'] and not profiles['generative']['path']
            else 'Fast reply model file is installed. ' if profiles['generative_available']
            else 'Fast reply model is unavailable; replies use the thinking profile. ')
        self.status.setText(status+
            'Changes apply to the next request. Active generation finishes before a model swap. The thinking profile below is preserved.')


class MemorySettings(QWidget):
    rebuilt=Signal(str)

    def __init__(self,owner):
        super().__init__(); self.owner=owner; self.memory=owner.runtime.desktop.memory
        self.cancel=threading.Event(); self.destroyed.connect(lambda *_: self.cancel.set())
        layout=QVBoxLayout(self)
        note=QLabel('Search retained messages in the current chat. Personal Memory is optional and saves approved preferences across chats. Preferences stay local and use Windows account protection. Exports are readable JSON.'); note.setWordWrap(True); layout.addWidget(note)
        self.flags={}
        for key,label in (('chat_memory_enabled','Search current-chat history'),('personal_memory_enabled','Enable Personal Memory'),
                          ('memory_allow_explicit','Allow explicit “remember” requests'),('memory_allow_suggestions','Allow preference suggestions for review'),
                          ('project_memory_enabled','Use approved project preferences')):
            field=QCheckBox(label); field.setChecked(owner.settings.get(key,'false')=='true'); field.setAccessibleName(label)
            field.toggled.connect(lambda value,k=key:self.toggle(k,value)); self.flags[key]=field; layout.addWidget(field)
        self.query=QLineEdit(); self.query.setPlaceholderText('Search saved preferences'); self.query.textChanged.connect(self.refresh); layout.addWidget(self.query)
        self.records=QListWidget(); self.records.currentItemChanged.connect(self.select); layout.addWidget(self.records,1)
        self.content=QLineEdit(); self.content.setPlaceholderText('Preference to save or correct'); layout.addWidget(self.content)
        form=QFormLayout(); self.category=QComboBox(); self.category.addItems(['response_style','explanation_preference','technical_preference','project_context','stable_choice','recurring_workflow','user_explicit_memory'])
        self.scope=QComboBox(); self.scope.addItem('Personal: future chats','user'); self.scope.addItem('Current project','project'); self.scope.addItem('Current chat only','conversation')
        form.addRow('Category',self.category); form.addRow('Scope',self.scope); layout.addLayout(form)
        buttons=QHBoxLayout()
        for label,callback in (('Save new',lambda:self.save(False)),('Correct / approve selected',lambda:self.save(True)),('Forget selected',self.forget)):
            button=QPushButton(label); button.clicked.connect(callback); buttons.addWidget(button)
        layout.addLayout(buttons)
        buttons=QGridLayout()
        for index,(label,callback) in enumerate((('Export preferences',self.export),('Clear all preferences',self.clear),('Search this chat',self.search_chat),('Rebuild history index',self.rebuild),('Storage status',self.diagnostics),('Cancel index rebuild',self.cancel_rebuild))):
            button=QPushButton(label); button.clicked.connect(callback); buttons.addWidget(button,index//2,index%2)
        layout.addLayout(buttons)
        self.status=QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        self._rebuilding=False
        self.rebuilt.connect(self.rebuild_finished); self.refresh()

    def toggle(self,key,value):
        try:
            if key=='personal_memory_enabled': self.memory.set_personal_enabled(value)
            self.owner.settings[key]=str(value).lower()
            if self.owner._session_enabled: save_settings(self.owner.settings)
            self.status.setText('Memory setting saved.')
        except Exception as exc:
            field=self.flags[key]; field.blockSignals(True); field.setChecked(not value); field.blockSignals(False)
            self.status.setText(str(exc))

    def selected(self):
        item=self.records.currentItem(); return item.data(Qt.UserRole) if item else None

    def refresh(self,*_):
        self.records.clear()
        for record in self.memory.list_preferences(self.query.text()):
            state='superseded' if record.superseded else record.consent_state
            item=QListWidgetItem(f'{record.content}\n{record.scope} · {record.category} · {state} · {record.updated_at[:10]}'); item.setData(Qt.UserRole,asdict(record)); self.records.addItem(item)
        self.status.setText(f'{len(self.memory.list_preferences())} saved preference records. Personal Memory is '+('on.' if self.memory.personal_enabled else 'off.')+' Chat history and personal preferences have separate deletion controls.')

    def select(self,*_):
        record=self.selected()
        if record:
            self.content.setText(record['content']); self.category.setCurrentText(record['category']); self.scope.setCurrentIndex(max(0,self.scope.findData(record['scope'])))

    def save(self,edit):
        record=self.selected() if edit else None
        if edit and record is None: return
        try:
            self.memory.save_preference(self.content.text(),category=self.category.currentText(),scope=self.scope.currentData(),
                project_id=self.owner._research_project_id or self.owner.project_folder,chat_id=self.owner._chat_id,
                memory_id=record['memory_id'] if record else '')
            self.refresh(); self.status.setText('Approved preference saved.')
        except Exception as exc: self.status.setText(str(exc))

    def forget(self):
        record=self.selected()
        if record:
            self.memory.delete(record['memory_id']); self.content.clear(); self.refresh()

    def clear(self):
        if QMessageBox.question(self,'Clear all personal preferences?','Permanently remove saved preferences and pending suggestions? Chat history will remain.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            self.memory.clear_preferences(); self.refresh()

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Export approved preferences','morice-preferences.json','JSON (*.json)')
        if path:
            try: self.memory.export_preferences(path); self.status.setText('Approved preferences exported as readable JSON.')
            except Exception as exc: self.status.setText(str(exc))

    def search_chat(self): self.owner._open_chat_search()

    def diagnostics(self):
        info=self.owner._get_chat_history().diagnostics(self.owner._chat_id)
        records=self.memory.list_preferences();personal=sum(r.scope=='user' for r in records);projects=sum(r.scope=='project' for r in records)
        self.status.setText(f"{info['indexed_messages']} indexed messages in this chat; {personal} personal and {projects} project preference records. Database: {info['database_bytes']:,} bytes. Last retrieval: {info['retrieval_ms']:.2f} ms. Embedding backend: unavailable; indexed text search remains enabled.")

    def rebuild(self):
        if self._rebuilding:return
        self._rebuilding=True
        self.cancel.clear(); self.status.setText('Rebuilding retained chat indexes…')
        def work():
            try: result=f'Index rebuild completed for {self.owner._get_chat_history().rebuild_index(cancel_event=self.cancel)} chats.'
            except Exception as exc: result=str(exc)
            try: self.rebuilt.emit(result)
            except RuntimeError: pass
        self.owner._start_background_task('chat-index-rebuild',work)

    def rebuild_finished(self,text):
        self._rebuilding=False;self.status.setText(text)

    def cancel_rebuild(self):
        if self._rebuilding:
            self.cancel.set();self.status.setText('Cancelling index rebuild; the previous index will be preserved.')


class ChatSearchDialog(QDialog):
    def __init__(self,owner):
        super().__init__(owner); self.owner=owner; self.setWindowTitle('Search this chat'); self.resize(760,560)
        layout=QVBoxLayout(self); self.query=QLineEdit(); self.query.setPlaceholderText('Search all retained messages in this chat'); layout.addWidget(self.query)
        row=QHBoxLayout(); self.mode=QComboBox()
        for label,value in [('Search','auto'),('First messages','first_message'),('Latest messages','latest_message'),('Decision timeline','timeline')]: self.mode.addItem(label,value)
        row.addWidget(self.mode); search=QPushButton('Search'); search.clicked.connect(self.search); row.addWidget(search); layout.addLayout(row)
        self.results=QListWidget(); layout.addWidget(self.results,1); self.status=QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        row=QHBoxLayout(); jump=QPushButton('Jump to original message'); jump.clicked.connect(self.jump); row.addWidget(jump)
        latest=QPushButton('Show latest chat'); latest.clicked.connect(self.latest); row.addWidget(latest); layout.addLayout(row)
        self.query.returnPressed.connect(self.search); self.results.itemDoubleClicked.connect(lambda *_:self.jump())
        self.search()

    def search(self):
        self.results.clear()
        try:
            rows=self.owner._get_chat_history().search_messages(self.owner._chat_id,self.query.text(),mode=self.mode.currentData(),limit=60)
            for record in rows:
                item=QListWidgetItem(f"Message {record['sequence']} · {record['role']}\n{record['content'][:500]}"); item.setData(Qt.UserRole,record); self.results.addItem(item)
            self.status.setText(f'{len(rows)} results in this chat. Search uses indexed text and a small query-expansion dictionary; no embedding model is installed.')
        except Exception as exc: self.status.setText(str(exc))

    def jump(self):
        item=self.results.currentItem()
        if item:
            self.owner._jump_to_message(item.data(Qt.UserRole)['message_id']); self.accept()

    def latest(self):
        self.owner._render_chat_messages(self.owner.history[-160:]); self.accept()
