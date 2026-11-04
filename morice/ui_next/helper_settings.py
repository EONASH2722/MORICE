"""Background Helper settings backed by its validated, private preference file."""
from PySide6.QtWidgets import QWidget,QFormLayout,QCheckBox,QSpinBox,QLineEdit,QLabel,QScrollArea,QComboBox


class BackgroundHelperSettings(QScrollArea):
    def __init__(self,owner):
        super().__init__();self.setWidgetResizable(True);self.helper=owner.background_helper
        host=QWidget();form=QFormLayout(host);form.setSpacing(14);self.fields={}
        switches=(('enabled','Enable Background Helper'),('run_after_close','Run after closing main window'),
            ('start_with_windows','Start with Windows (optional)'),('wake_enabled','Enable "MORICE" wake phrase'),
            ('circle_enabled','Enable middle-mouse circle selection'),('auto_explain','Automatically explain selected area'),
            ('auto_hide','Hide popup automatically'),('animation','Popup animation On/Off'),('reduced_motion','Reduced Motion'),
            ('pause_fullscreen','Pause helper in fullscreen games'),('screen_capture','Screen-capture permission'))
        for key,label in switches:
            field=QCheckBox();field.setChecked(getattr(self.helper.preferences,key));field.setAccessibleName(label)
            field.toggled.connect(lambda value,k=key:self.helper.update(**{k:value}));form.addRow(label,field);self.fields[key]=field
        duration=QSpinBox();duration.setRange(3,120);duration.setSuffix(' seconds');duration.setValue(self.helper.preferences.popup_seconds)
        duration.setAccessibleName('Popup display duration');duration.valueChanged.connect(lambda value:self.helper.update(popup_seconds=value))
        form.addRow('Popup display duration',duration);self.fields['popup_seconds']=duration
        material=QComboBox();material.addItem('Black glass','glass');material.addItem('Reference dark','dark')
        material.setCurrentIndex(max(0,material.findData(self.helper.preferences.popup_material)))
        material.setAccessibleName('Popup material');material.currentIndexChanged.connect(lambda index:self.helper.update(popup_material=material.itemData(index)))
        form.addRow('Popup material',material);self.fields['popup_material']=material
        exclusions=QLineEdit(self.helper.preferences.excluded_apps);exclusions.setPlaceholderText('blender.exe; acad.exe; game.exe')
        exclusions.setAccessibleName('Excluded applications');exclusions.editingFinished.connect(lambda:self.helper.update(excluded_apps=exclusions.text()))
        form.addRow('Excluded applications',exclusions);self.fields['excluded_apps']=exclusions
        self.microphone=QLabel();self.microphone.setWordWrap(True);form.addRow('Microphone permission/status',self.microphone)
        self.status=QLabel();self.status.setWordWrap(True);form.addRow('Helper status',self.status)
        note=QLabel('Middle mouse is opt-in. Brief clicks pass through; held gestures reserve the button. Exclude applications that use middle-button dragging. Screen capture runs only after you finish a circle and stays in memory until dismissal. Images use the existing local vision model. Orb and glow colors remain in Desktop pet settings.')
        note.setWordWrap(True);form.addRow(note);self.setWidget(host)
        self.helper.changed.connect(self.refresh);self.refresh()

    def refresh(self):
        for key,field in self.fields.items():
            field.blockSignals(True);value=getattr(self.helper.preferences,key)
            if isinstance(field,QCheckBox):field.setChecked(value)
            elif isinstance(field,QSpinBox):field.setValue(value)
            elif isinstance(field,QComboBox):field.setCurrentIndex(max(0,field.findData(value)))
            elif not field.hasFocus():field.setText(value)
            field.blockSignals(False)
        permission=self.helper.runtime.kernel.permissions.controller.state('microphone_access')
        speech=self.helper.runtime.speech_input.status()
        listener=self.helper._listener
        self.microphone.setText(permission.value+' · '+speech.message+(' · Wake listener running' if listener and listener.poll() is None else ' · Wake listener paused'))
        self.status.setText(self.helper.preference_error or self.helper.status)
