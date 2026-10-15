"""Live data-only Appearance Lab. One debounce timer for preference writes."""
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFormLayout, QComboBox, QSlider, QCheckBox, QPushButton, QColorDialog, QFileDialog, QMessageBox, QScrollArea

from .themes import PRESETS, AppearanceProfile, AppearanceStore
from ..media_lab.storage import atomic_json
from .theme_scenes import SCENES
from .file_access import require_selected_file


class AppearanceView(QWidget):
    def __init__(self, theme, policy, parent=None, *, runtime=None):
        super().__init__(parent)
        self.theme = theme; self.policy = policy; self.fields = {}; self.runtime = runtime; self.field_rows = {}
        self.save_timer = QTimer(self); self.save_timer.setSingleShot(True); self.save_timer.setInterval(250)
        self.save_timer.timeout.connect(lambda: theme.store.save(theme.profile))
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 20, 24, 20)
        title = QLabel('Appearance'); title.setProperty('role', 'title'); layout.addWidget(title)
        description = QLabel('Every theme has its own shapes, materials and seamless motion. Changes preview immediately.'); description.setProperty('role', 'secondary'); description.setWordWrap(True); layout.addWidget(description)
        self.scene_description=QLabel();self.scene_description.setWordWrap(True);layout.addWidget(self.scene_description)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget(); content = QVBoxLayout(host); form = QFormLayout(); form.setVerticalSpacing(14); form.setRowWrapPolicy(QFormLayout.WrapLongRows); content.addLayout(form)
        self.advanced_toggle = QPushButton('Advanced appearance'); self.advanced_toggle.setProperty('morice_icon', 'settings'); self.advanced_toggle.setCheckable(True); content.addWidget(self.advanced_toggle)
        self.advanced = QWidget(); advanced_form = QFormLayout(self.advanced); advanced_form.setVerticalSpacing(14); advanced_form.setRowWrapPolicy(QFormLayout.WrapLongRows); content.addWidget(self.advanced); self.advanced.hide()
        self.advanced_toggle.toggled.connect(self.advanced.setVisible); content.addStretch(1); scroll.setWidget(host); layout.addWidget(scroll, 1)
        basic = {'preset', 'density', 'font_scale', 'cursor_glow', 'cursor_light', 'reduced_motion', 'high_contrast'}
        def add_field(key, label, field):
            target = form if key in basic else advanced_form
            self.fields[key] = field; field.setAccessibleName(label); field.setMinimumWidth(0)
            target.addRow(label, field); self.field_rows[key] = (field, target.labelForField(field), key not in basic)
        for key, label, values in (('preset', 'Theme', list(PRESETS)), ('quality', 'Effect quality', ['LOW', 'BALANCED', 'HIGH', 'ULTRA']),
            ('density', 'UI density', ['compact', 'comfortable', 'spacious']), ('cursor_glow', 'Cursor glow', ['OFF', 'MINIMAL', 'NORMAL', 'HIGH']), ('particles', 'Particles', ['OFF', 'LOW', 'NORMAL']),
            ('field_palette', 'Energy field palette', ['STATE', 'CYAN', 'VIOLET', 'THEME'])):
            field = QComboBox(); field.addItems(values); field.setCurrentText(getattr(theme.profile, key)); field.setAccessibleName(label)
            field.currentTextChanged.connect(lambda value, name=key: self.update(name, value)); add_field(key, label, field)
        for key, label in (('primary_accent', 'Primary accent'), ('secondary_accent', 'Secondary accent'), ('background_tone', 'Background tone'), ('surface_tone', 'Surface tone')):
            field = QPushButton(getattr(theme.profile, key) or 'Use preset'); field.setProperty('morice_icon', 'appearance'); field.clicked.connect(lambda checked=False, name=key: self.choose_color(name)); add_field(key, label, field)
        for key, label, minimum, maximum, factor in (
            ('glow', 'Glow intensity', 0, 100, .01), ('glass', 'Glass intensity', 0, 100, .01), ('blur', 'Blur amount', 0, 100, .01),
            ('border_brightness', 'Border brightness', 0, 100, .01), ('radius', 'Corner radius', 0, 32, 1),
            ('font_scale', 'Font scale', 80, 180, .01), ('motion_strength', 'Animation strength', 0, 100, .01), ('motion_speed', 'Animation speed', 50, 200, .01)):
            field = QSlider(Qt.Horizontal); field.setRange(minimum, maximum); field.setValue(round(getattr(theme.profile, key) / factor)); field.setAccessibleName(label)
            if key == 'blur': field.setToolTip('Procedural raster softness; no desktop pixels are captured.')
            if key == 'glass': field.setToolTip('Glass theme: translucent panels, refracted field and soft reflective edges.')
            field.valueChanged.connect(lambda value, name=key, scale=factor: self.update(name, value if scale == 1 else value * scale)); add_field(key, label, field)
        for key, label in (('field_intensity', 'Energy field intensity'), ('field_motion', 'Energy field motion'), ('core_brightness', 'Core brightness'), ('orbital_complexity', 'Orbital complexity')):
            field = QSlider(Qt.Horizontal); field.setRange(1 if key == 'orbital_complexity' else 0, 6 if key == 'orbital_complexity' else 100)
            factor = 1 if key == 'orbital_complexity' else .01; field.setValue(round(getattr(theme.profile, key) / factor))
            field.valueChanged.connect(lambda value, name=key, scale=factor: self.update(name, value if scale == 1 else value * scale)); add_field(key, label, field)
        for key, label in (('cursor_light', 'Cursor-reactive light'), ('cursor_trail', 'Cursor trail'), ('magnetic_controls', 'Magnetic controls'),
            ('background_effects', 'Background environment'), ('reduced_motion', 'Reduced Motion'), ('high_contrast', 'High contrast')):
            field = QCheckBox(); field.setChecked(getattr(theme.profile, key)); field.toggled.connect(lambda value, name=key: self.update(name, value)); add_field(key, label, field)
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        row = QHBoxLayout()
        for label, action in (('Import theme', self.import_theme), ('Export theme', self.export_theme), ('Reset appearance', self.reset)):
            button = QPushButton(label); button.clicked.connect(action); row.addWidget(button)
        layout.addLayout(row); policy.changed.connect(self.refresh_status); theme.changed.connect(self.sync); self.refresh_status()

    def filter(self, query):
        query = query.strip().casefold(); show_advanced = False
        for key, (field, label, advanced) in self.field_rows.items():
            visible = not query or query in key.replace('_', ' ') or query in field.accessibleName().casefold() or query in field.toolTip().casefold()
            field.setVisible(visible); label.setVisible(visible); show_advanced |= bool(query) and visible and advanced
        if show_advanced: self.advanced_toggle.setChecked(True)

    def update(self, name, value):
        try:
            self.theme.update(persist=False, **{name: value}); self.save_timer.start()
        except (ValueError, TypeError) as exc: self.status.setText(str(exc))

    def sync(self, *_):
        profile = self.theme.profile
        for key, field in self.fields.items():
            field.blockSignals(True); value = getattr(profile, key)
            if isinstance(field, QComboBox): field.setCurrentText(value)
            elif isinstance(field, QCheckBox): field.setChecked(value)
            elif isinstance(field, QSlider): field.setValue(value if key in {'radius', 'orbital_complexity'} else round(value * 100))
            else: field.setText(value or 'Use preset')
            field.blockSignals(False)
        self.refresh_status()

    def refresh_status(self, *_):
        budget = self.policy.budget
        name,description=SCENES[self.theme.profile.preset];self.scene_description.setText(name+' · '+description)
        self.status.setText(f'Selected {budget.selected} · Active {budget.effective}' + (' · ' + budget.reason if budget.reason else '') + (' · Reduced Motion' if self.theme.profile.reduced_motion else ''))

    def choose_color(self, name):
        selected = QColorDialog.getColor(QColor(getattr(self.theme.profile, name) or self.theme.tokens['accent_primary']), self, 'Choose appearance color')
        if selected.isValid(): self.update(name, selected.name())

    def import_theme(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import data-only theme', '', 'Theme data (*.json)')
        if not path: return
        try:
            if self.runtime: require_selected_file(self.runtime, 'file_read')
            self.theme.apply_profile(AppearanceStore.import_file(path))
        except (ValueError, TypeError, OSError) as exc: QMessageBox.warning(self, 'Theme could not be imported', str(exc))

    def export_theme(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export data-only theme', 'morice-theme.json', 'Theme data (*.json)')
        if not path: return
        try:
            if self.runtime: require_selected_file(self.runtime, 'file_write')
            if Path(path).exists(): raise FileExistsError('Choose a new filename; theme export preserves existing files.')
            atomic_json(path, self.theme.profile.to_dict())
            self.status.setText('Theme data exported.')
        except OSError as exc: QMessageBox.warning(self, 'Theme export failed', str(exc))

    def reset(self):
        self.theme.apply_profile(AppearanceProfile())

    def hideEvent(self, event):
        if self.save_timer.isActive(): self.save_timer.stop(); self.theme.store.save(self.theme.profile)
        super().hideEvent(event)
