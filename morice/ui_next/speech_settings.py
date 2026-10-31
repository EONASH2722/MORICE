"""Local speech quality, model selection and conservative transcript correction."""
from PySide6.QtWidgets import QWidget,QFormLayout,QHBoxLayout,QComboBox,QLineEdit,QPushButton,QCheckBox,QFileDialog,QLabel
from ..speech_refinement import find_whisper_model


class SpeechSettings(QWidget):
    def __init__(self,owner):
        super().__init__(); self.owner=owner; form=QFormLayout(self); form.setContentsMargins(0,0,0,0)
        self.provider=QComboBox()
        for label,value in (('Automatic: accurate when installed','auto'),('Whisper: accuracy','whisper'),('Vosk: fast','vosk')): self.provider.addItem(label,value)
        self.provider.setCurrentIndex(max(0,self.provider.findData(owner.settings.get('stt_provider','auto')))); form.addRow('Recognition engine',self.provider)
        self.path=QLineEdit(owner.settings.get('stt_accuracy_model_path','')); self.path.setPlaceholderText('Local Whisper model folder')
        browse=QPushButton('Choose folder…'); browse.clicked.connect(self.choose)
        row=QHBoxLayout(); row.addWidget(self.path,1); row.addWidget(browse); form.addRow('Accuracy model',row)
        self.language=QComboBox()
        for label,value in (('English','en'),('Hindi','hi'),('Detect language','auto')): self.language.addItem(label,value)
        self.language.setCurrentIndex(max(0,self.language.findData(owner.settings.get('stt_language','en')))); form.addRow('Spoken language',self.language)
        self.correct=QCheckBox('Automatic transcript correction'); self.correct.setChecked(owner.settings.get('stt_autocorrect','true')=='true'); form.addRow(self.correct)
        note=QLabel('Whisper checks the original audio for the final transcript; Vosk provides quick live text. Correction standardizes MORICE’s name and known workspace commands, preserving numbers, other names, paths and negation. Save voice settings to apply changes.')
        note.setWordWrap(True); form.addRow(note)
        self.status=QLabel();self.status.setWordWrap(True);form.addRow(self.status);self.path.textChanged.connect(self.refresh);self.refresh()
    def choose(self):
        path=QFileDialog.getExistingDirectory(self,'Select a local Whisper model',self.path.text())
        if path:self.path.setText(path)
    def refresh(self,*_):
        self.status.setText('Local accuracy model available.' if find_whisper_model(self.path.text()) else 'Accuracy model unavailable. Vosk remains available for speech input. Model downloads require an explicit user action.')
    def write_settings(self,settings):
        settings.update(stt_provider=self.provider.currentData(),stt_accuracy_model_path=self.path.text().strip(),stt_language=self.language.currentData(),stt_autocorrect=str(self.correct.isChecked()).lower())
