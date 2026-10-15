"""Named appearance/workspace profiles using the existing ExperienceProfileStore."""
from dataclasses import asdict
from pathlib import Path

from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QFileDialog

from ..premium_experience import ExperienceProfile
from .file_access import require_selected_file


class ProfilesView(QWidget):
    def __init__(self, owner, parent=None):
        super().__init__(parent);self.owner=owner;self.store=owner.experience_profiles
        layout=QVBoxLayout(self);layout.setContentsMargins(16,16,16,16)
        description=QLabel('Save your appearance and workspace together. Existing profiles stay available.');description.setWordWrap(True);description.setProperty('role','secondary');layout.addWidget(description)
        self.select=QComboBox();self.select.setEditable(True);self.select.setAccessibleName('Experience profile name');self.select.setMaxCount(24);layout.addWidget(self.select)
        row=QHBoxLayout()
        for label,mark,action in (('Apply','check',self.apply),('Save current','save',self.save),('Delete','delete',self.delete)):
            button=QPushButton(label);button.setProperty('morice_icon',mark);button.clicked.connect(action);row.addWidget(button)
        layout.addLayout(row);row=QHBoxLayout()
        for label,mark,action in (('Import profiles','import',self.import_profiles),('Export profiles','export',self.export_profiles)):
            button=QPushButton(label);button.setProperty('morice_icon',mark);button.clicked.connect(action);row.addWidget(button)
        layout.addLayout(row);self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);layout.addStretch(1);self.refresh()

    def refresh(self,name=None):
        name=name or self.select.currentText() or 'Default';self.select.clear();self.select.addItems([profile.name for profile in self.store.list()]);self.select.setCurrentText(name)

    def save(self):
        try:
            profile=self.owner.theme_engine.profile
            value=ExperienceProfile.from_value({'name':self.select.currentText(),'theme':self.owner.current_theme,'accent':profile.primary_accent or self.owner.theme_engine.tokens['accent_primary'],
                'animation_speed':self.owner.animation_speed,'reduced_motion':profile.reduced_motion,'high_contrast':profile.high_contrast,'ui_scale':profile.font_scale,
                'transparency':self.owner.transparency,'workspace_preset':self.owner.workspace_preset,'appearance':profile.to_dict()})
            self.store.save(value);self.refresh(value.name);self.status.setText('Profile saved.')
        except (ValueError,TypeError,OSError) as exc:self.status.setText(str(exc))

    def apply(self):
        profile=self.store.get(self.select.currentText())
        if profile is None:self.status.setText('Choose a saved profile, or save the current appearance first.');return
        try:self.owner._apply_experience_preferences(asdict(profile));self.status.setText('Profile applied.')
        except (ValueError,TypeError,OSError) as exc:self.status.setText(str(exc))

    def delete(self):
        changed=self.store.delete(self.select.currentText());self.refresh();self.status.setText('Profile deleted.' if changed else 'The default profile is protected.')

    def import_profiles(self):
        try:
            require_selected_file(self.owner.runtime,'file_read')
            path,_=QFileDialog.getOpenFileName(self,'Import experience profiles','','Profiles (*.json)')
            if path:self.status.setText(f'{self.store.import_file(path)} profiles imported.');self.refresh()
        except (ValueError,TypeError,OSError) as exc:self.status.setText(str(exc))

    def export_profiles(self):
        try:
            require_selected_file(self.owner.runtime,'file_write')
            path,_=QFileDialog.getSaveFileName(self,'Export experience profiles','morice-profiles.json','Profiles (*.json)')
            if not path:return
            if Path(path).exists():raise FileExistsError('Choose a new filename to preserve existing files.')
            self.store.export(path);self.status.setText('Profiles exported.')
        except (ValueError,TypeError,OSError) as exc:self.status.setText(str(exc))
