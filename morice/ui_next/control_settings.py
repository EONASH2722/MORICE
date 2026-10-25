"""Explicit desktop consent and first-party conversational presentation options."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QCheckBox,QComboBox,QFormLayout

from ..settings import save_settings


class ControlSettings(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner
        self.setToolTip('Desktop automation permission, PC and third-party apps, natural language, response presentation, compact, detailed, visual, technical.')
        layout=QVBoxLayout(self)
        note=QLabel('Desktop automation lets MORICE inspect and operate third-party app windows and accessible controls for your requests. It is off by default. Turning it on keeps existing file, send, delete and other consequential-action confirmations. Internal MORICE navigation and tools do not require PC control.')
        note.setWordWrap(True);layout.addWidget(note)
        self.desktop=QCheckBox('Desktop automation')
        self.desktop.setObjectName('DesktopAutomationPermission')
        self.desktop.setAccessibleName('Desktop automation')
        self.desktop.setToolTip('Allow requested third-party app control. Turn off to revoke permission immediately.')
        self.desktop.setChecked(owner.runtime.desktop_automation_enabled)
        self.desktop.toggled.connect(self.toggle_desktop);layout.addWidget(self.desktop)
        self.flags={}
        for key,label in (('nlui_enabled','Natural language control'),('nlui_auto_open','Open the workspace relevant to a result'),('nlui_show_plan','Show the plan for complex requests')):
            field=QCheckBox(label);field.setChecked(owner.settings.get(key,'true')=='true')
            field.setAccessibleName(label);field.toggled.connect(lambda v,k=key:self.save_flag(k,v))
            self.flags[key]=field;layout.addWidget(field)
        form=QFormLayout();self.presentation=QComboBox()
        for value in ('auto','compact','detailed','visual','technical'):self.presentation.addItem(value.title(),value)
        self.presentation.setCurrentIndex(max(0,self.presentation.findData(owner.settings.get('response_presentation','auto'))))
        self.presentation.setAccessibleName('Response presentation')
        self.presentation.currentIndexChanged.connect(self.save_presentation)
        form.addRow('Response presentation',self.presentation);layout.addLayout(form)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);layout.addStretch(1)

    def toggle_desktop(self,enabled):
        try:
            self.owner.runtime.set_desktop_automation_enabled(enabled,persist=self.owner._session_enabled)
            self.owner.settings['desktop_automation_enabled']=str(enabled).lower()
            if not enabled:
                token=getattr(self.owner,'_pc_action_token',None)
                if token is not None:token.cancel('Desktop automation disabled in Settings.')
            self.status.setText('Desktop automation is enabled. Existing action confirmations still apply.' if enabled else 'Desktop automation is off. Third-party app control is blocked.')
        except Exception as exc:
            self.owner.settings['desktop_automation_enabled']=str(self.owner.runtime.desktop_automation_enabled).lower()
            self.desktop.blockSignals(True);self.desktop.setChecked(self.owner.runtime.desktop_automation_enabled);self.desktop.blockSignals(False)
            self.status.setText('Desktop permission could not be saved: '+str(exc))

    def save_flag(self,key,value):
        self.owner.settings[key]=str(value).lower()
        if self.owner._session_enabled:save_settings(self.owner.settings)

    def save_presentation(self,*_):
        self.owner.settings['response_presentation']=self.presentation.currentData()
        if self.owner._session_enabled:save_settings(self.owner.settings)
