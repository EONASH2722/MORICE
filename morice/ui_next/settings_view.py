"""Searchable settings over existing preference and permission authorities."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QStackedWidget, QScrollArea, QFormLayout, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox)

from .appearance_view import AppearanceView
from .profiles_view import ProfilesView


class SettingsWorkspace(QWidget):
    def __init__(self, window):
        super().__init__(); self.owner = window; self.categories = {}; self.rows = {}
        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 20)
        heading = QLabel('Settings'); heading.setProperty('role', 'title'); root.addWidget(heading)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search settings: voice, motion, model, wake…'); self.search.setAccessibleName('Search settings'); root.addWidget(self.search)
        body = QHBoxLayout(); self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideRight)
        self.stack = QStackedWidget(); body.addWidget(self.list); body.addWidget(self.stack, 1); root.addLayout(body, 1)
        self.add_category('Appearance', AppearanceView(window.theme_engine, window.effect_policy, runtime=window.runtime))
        self.add_category('Profiles', ProfilesView(window))
        self.add_form('Personalization', (
            ('Current response style', 'current_style_value'), ('Response instructions', 'style_input'),
            ('Preferred name', 'name_input'), ('Form of address', 'title_input'), ('Preview', 'title_preview'),
            ('Wake phrase', 'wake_input'), ('Emoji amount', 'emoji_select'), ('Maturity', 'maturity_select'),
            ('Precision mode', 'precision_btn'), ('Save', 'save_style_btn'), ('Clear', 'clear_style_btn'), ('Status', 'style_status')))
        self.add_form('Models', (('Ollama model', 'model_name_input'), ('Local GGUF', 'model_path_input'),
            ('Select model', 'change_model_btn'), ('Clear local file', 'clear_model_btn'), ('Hardware', 'gpu_status_input'), ('Detect GPU', 'detect_gpu_btn')))
        provider = QComboBox(); provider.addItem('ElevenLabs', 'elevenlabs'); provider.addItem('Windows local speech', 'local')
        provider.setCurrentIndex(max(0, provider.findData(window.settings.get('tts_provider', 'elevenlabs')))); window.tts_provider_select = provider
        self.add_form('Voice', (('Reply speech enabled', 'tts_enabled_check'), ('Provider', provider),
            ('Streaming', 'tts_streaming_check'), ('Automatic fallback', 'tts_fallback_check'),
            ('Voice ID', 'tts_voice_id_input'), ('Model ID', 'tts_model_id_input'), ('Speech speed', 'tts_speed_slider'),
            ('Output device', 'tts_output_device_select'), ('Speech input', 'stt_enabled_check'),
            ('Automatically send transcript', 'stt_auto_send_check'), ('Microphone input device', 'stt_input_device_select'),
            ('ElevenLabs API key', 'elevenlabs_api_key_input'), ('Secure key storage', 'save_api_key_btn'),
            ('Provider status', 'elevenlabs_api_status'), ('Save voice settings', 'save_voice_btn')))
        self.wake_fields = {}; wake_view = self.wake_form(); self.add_category('Wake', wake_view)
        self.add_form('Desktop pet', (('Enabled', 'pet_enabled_check'), ('Active pet', 'active_pet_select'),
            ('Size', 'pet_size_select'), ('Animation speed', 'pet_animation_speed_select'),
            ('Click action', 'pet_click_action_select'), ('Event frequency', 'pet_event_frequency_select'),
            ('Hide during fullscreen', 'pet_fullscreen_check'), ('Interaction', 'pet_interaction_check'),
            ('Remove selected pet', 'remove_pet_btn')))
        self.add_form('Workspace', (('Default music provider', 'music_provider_select'), ('Workspace preset', 'workspace_preset_select'),
            ('Font family', 'font_select'), ('Import font file', 'add_font_btn')))
        # The selected family belongs to the central schema; the established
        # selector still owns installed/custom-font handling and preferences.
        self.list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.search.textChanged.connect(self.filter); self.list.setCurrentRow(0)
        self._category_layout_timer = QTimer(self)
        self._category_layout_timer.setSingleShot(True)
        self._category_layout_timer.timeout.connect(self._fit_categories)
        window.theme_engine.changed.connect(lambda *_: self._category_layout_timer.start(0))
        self._category_layout_timer.start(0)

    def _fit_categories(self):
        width = max((self.list.fontMetrics().horizontalAdvance(self.list.item(i).text())
                     for i in range(self.list.count())), default=0) + 44
        self.list.setFixedWidth(min(max(170, width), max(150, int(self.width() * .35))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_category_layout_timer'): self._category_layout_timer.start(0)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange) and hasattr(self, '_category_layout_timer'):
            self._category_layout_timer.start(0)

    def add_category(self, name, view):
        self.categories[name] = view; self.list.addItem(name); self.list.item(self.list.count()-1).setToolTip(name); self.stack.addWidget(view)

    def add_form(self, name, fields):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget(); form = QFormLayout(host); form.setContentsMargins(16, 16, 16, 16); form.setSpacing(14)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows); self.rows[name] = []
        for label, reference in fields:
            field = getattr(self.owner, reference, None) if isinstance(reference, str) else reference
            if field is None:
                raise AttributeError('Settings parity binding missing: ' + str(reference))
            field.setParent(host); field.setMinimumWidth(0); field.setMaximumWidth(16777215)
            field.setAccessibleName(label); field.show(); form.addRow(label, field)
            self.rows[name].append((label, field, form.labelForField(field)))
        scroll.setWidget(host); self.add_category(name, scroll)

    def wake_form(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); host = QWidget(); form = QFormLayout(host)
        preferences = self.owner.wake_controller.preferences
        for name, label in (('enabled', 'Wake interaction enabled'), ('orb_enabled', 'Show wake overlay'),
            ('idle_visible', 'Keep an idle orb visible'), ('transcript', 'Show compact transcript'), ('activation_sound', 'Activation sound (off by default)')):
            field = QCheckBox(); field.setChecked(getattr(preferences, name)); field.setAccessibleName(label)
            field.toggled.connect(lambda value, key=name: self.owner.wake_controller.update_preferences(**{key: value}))
            form.addRow(label, field); self.wake_fields[name] = field
        for name, label, values in (('position', 'Overlay position', ('bottom_center', 'bottom_left', 'bottom_right')),
            ('fullscreen', 'Fullscreen overlay policy', ('audio_only', 'small_overlay', 'normal_overlay', 'disabled_overlay'))):
            field = QComboBox(); field.addItems(values); field.setCurrentText(getattr(preferences, name)); field.setAccessibleName(label)
            field.currentTextChanged.connect(lambda value, key=name: self.owner.wake_controller.update_preferences(**{key: value}))
            form.addRow(label, field); self.wake_fields[name] = field
        for name, label in (('size', 'Orb size'), ('command_timeout', 'Command timeout (seconds)'), ('processing_timeout', 'Work timeout (seconds)'), ('idle_timeout', 'Idle timeout (seconds)')):
            field = QSpinBox() if name == 'size' else QDoubleSpinBox(); field.setRange(48, 160) if name == 'size' else field.setRange(1, 60)
            field.setValue(getattr(preferences, name)); field.setAccessibleName(label)
            field.valueChanged.connect(lambda value, key=name: self.owner.wake_controller.update_preferences(**{key: value}))
            form.addRow(label, field); self.wake_fields[name] = field
        note = QLabel('Wake capture and replies use the existing listener, speech input and VoiceRuntime. Camera capture still requires an explicit action.'); note.setWordWrap(True); form.addRow(note)
        scroll.setWidget(host); return scroll

    def filter(self, text):
        query = text.strip().casefold()
        for index in range(self.list.count()):
            name = self.list.item(index).text(); matches_category = query in name.casefold()
            visible = not query or matches_category
            for label, field, caption in self.rows.get(name, []):
                match = not query or matches_category or query in label.casefold() or query in field.toolTip().casefold()
                field.setVisible(match); caption.setVisible(match); visible |= match
            if name == 'Appearance':
                visible |= any(query in key.replace('_', ' ') or query in field.accessibleName().casefold() for key, field in self.categories[name].fields.items())
                self.categories[name].filter('' if matches_category else query)
            if name == 'Wake': visible |= any(query in key.replace('_', ' ') for key in self.wake_fields)
            self.list.item(index).setHidden(not visible)
        if self.list.currentItem() is None or self.list.currentItem().isHidden():
            for index in range(self.list.count()):
                if not self.list.item(index).isHidden(): self.list.setCurrentRow(index); break
