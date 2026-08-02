from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .premium_experience import ExperienceProfile, ExperienceProfileStore
from .ui_system import normalize_accent, normalize_theme, premium_theme_stylesheet


class PremiumSettingsDialog(QDialog):
    preferences_applied = Signal(object)

    CATEGORIES = ("Appearance", "Motion", "Accessibility", "Workspace", "Profiles")

    def __init__(
        self,
        store: ExperienceProfileStore,
        current: ExperienceProfile,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.store = store
        self.current = current
        self._accent = normalize_accent(current.accent)
        self.setObjectName("PremiumSettingsDialog")
        self.setWindowTitle("MORICE settings")
        self.setMinimumSize(780, 570)
        self.resize(880, 650)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        heading = QLabel("Settings")
        heading.setObjectName("CommandTitle")
        self.search = QLineEdit()
        self.search.setObjectName("CommandSearch")
        self.search.setPlaceholderText("Search appearance, motion, accessibility...")
        self.search.setAccessibleName("Search settings")
        self.search.textChanged.connect(self._filter_categories)
        header.addWidget(heading)
        header.addWidget(self.search, stretch=1)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.categories = QListWidget()
        self.categories.setObjectName("SettingsCategories")
        self.categories.setFixedWidth(180)
        self.categories.currentRowChanged.connect(self._show_category)
        self.stack = QStackedWidget()
        self.stack.setObjectName("SettingsStack")
        for name in self.CATEGORIES:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            self.categories.addItem(item)
        self.stack.addWidget(self._appearance_page())
        self.stack.addWidget(self._motion_page())
        self.stack.addWidget(self._accessibility_page())
        self.stack.addWidget(self._workspace_page())
        self.stack.addWidget(self._profiles_page())
        self.categories.setCurrentRow(0)
        body.addWidget(self.categories)
        body.addWidget(self.stack, stretch=1)

        self.preview = QFrame()
        self.preview.setObjectName("SettingsPreview")
        preview_layout = QHBoxLayout(self.preview)
        preview_layout.setContentsMargins(14, 12, 14, 12)
        self.preview_text = QLabel("MORICE live preview | Aa | Interactive")
        self.preview_text.setObjectName("MessageLabel")
        self.preview_text.setAccessibleName("Settings live preview")
        self.preview_status = QProgressBar()
        self.preview_status.setRange(0, 100)
        self.preview_status.setValue(68)
        self.preview_status.setTextVisible(False)
        self.preview_status.setFixedWidth(150)
        preview_layout.addWidget(self.preview_text, stretch=1)
        preview_layout.addWidget(self.preview_status)

        actions = QHBoxLayout()
        reset = QPushButton("Reset")
        reset.setObjectName("WorkspaceAction")
        reset.clicked.connect(self._reset)
        apply_button = QPushButton("Apply")
        apply_button.setObjectName("StyleSaveButton")
        apply_button.clicked.connect(self._apply)
        close = QPushButton("Close")
        close.setObjectName("WorkspaceCloseButton")
        close.clicked.connect(self.reject)
        actions.addWidget(reset)
        actions.addStretch(1)
        actions.addWidget(apply_button)
        actions.addWidget(close)

        root.addLayout(header)
        root.addLayout(body, stretch=1)
        root.addWidget(self.preview)
        root.addLayout(actions)
        self._set_values(current)
        self._refresh_profiles()
        self._refresh_preview()

    @staticmethod
    def _page(title: str, description: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("SidebarTitle")
        detail = QLabel(description)
        detail.setObjectName("WorkspaceMuted")
        detail.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(detail)
        return page, layout

    @staticmethod
    def _field(layout: QVBoxLayout, label: str, widget: QWidget) -> None:
        text = QLabel(label)
        text.setObjectName("StyleLabel")
        layout.addWidget(text)
        layout.addWidget(widget)

    def _appearance_page(self) -> QWidget:
        page, layout = self._page(
            "Appearance",
            "Choose a readable theme and accent. Transparency never reduces text opacity.",
        )
        self.theme = QComboBox()
        self.theme.setObjectName("AppearanceSelect")
        for label, key in (
            ("Dark", "dark"),
            ("Light", "light"),
            ("Midnight", "midnight"),
            ("Glass", "glass"),
            ("Custom", "custom"),
        ):
            self.theme.addItem(label, key)
        self.theme.currentIndexChanged.connect(self._refresh_preview)
        self.accent_button = QPushButton("Choose accent")
        self.accent_button.setObjectName("WorkspaceAction")
        self.accent_button.clicked.connect(self._choose_accent)
        self.transparency = QSlider(Qt.Horizontal)
        self.transparency.setRange(70, 100)
        self.transparency.valueChanged.connect(self._refresh_preview)
        self._field(layout, "Theme", self.theme)
        self._field(layout, "Accent colour", self.accent_button)
        self._field(layout, "Glass opacity", self.transparency)
        layout.addStretch(1)
        return page

    def _motion_page(self) -> QWidget:
        page, layout = self._page(
            "Motion",
            "Animations are interruptible and never gate commands or typing.",
        )
        self.animation_speed = QComboBox()
        self.animation_speed.setObjectName("AppearanceSelect")
        for label, key in (("Slow", "slow"), ("Normal", "normal"), ("Fast", "fast")):
            self.animation_speed.addItem(label, key)
        self.reduced_motion = QCheckBox("Reduce non-essential motion")
        self.reduced_motion.setAccessibleName("Reduce motion")
        self._field(layout, "Animation speed", self.animation_speed)
        layout.addWidget(self.reduced_motion)
        layout.addStretch(1)
        return page

    def _accessibility_page(self) -> QWidget:
        page, layout = self._page(
            "Accessibility",
            "Focus rings, labels, contrast and scaling apply immediately.",
        )
        self.high_contrast = QCheckBox("High contrast borders and text")
        self.large_text = QCheckBox("Large text")
        self.ui_scale = QSlider(Qt.Horizontal)
        self.ui_scale.setRange(80, 160)
        self.ui_scale.setSingleStep(5)
        self.ui_scale.valueChanged.connect(self._refresh_preview)
        self._field(layout, "Interface scale", self.ui_scale)
        layout.addWidget(self.high_contrast)
        layout.addWidget(self.large_text)
        layout.addStretch(1)
        return page

    def _workspace_page(self) -> QWidget:
        page, layout = self._page(
            "Workspace",
            "Presets rearrange existing panels without discarding their state.",
        )
        self.workspace_preset = QComboBox()
        self.workspace_preset.setObjectName("AppearanceSelect")
        for label, key in (
            ("Balanced", "balanced"),
            ("Focus", "focus"),
            ("Science", "science"),
            ("Project", "project"),
            ("Research", "research"),
        ):
            self.workspace_preset.addItem(label, key)
        self._field(layout, "Layout preset", self.workspace_preset)
        layout.addStretch(1)
        return page

    def _profiles_page(self) -> QWidget:
        page, layout = self._page(
            "Profiles",
            "Save, restore, import or export appearance and accessibility profiles.",
        )
        self.profile_name = QComboBox()
        self.profile_name.setObjectName("AppearanceSelect")
        self.profile_name.setEditable(True)
        self.profile_name.currentTextChanged.connect(self._profile_selected)
        row = QHBoxLayout()
        save_button = QPushButton("Save profile")
        save_button.setObjectName("WorkspaceAction")
        save_button.clicked.connect(self._save_profile)
        delete_button = QPushButton("Delete")
        delete_button.setObjectName("WorkspaceAction")
        delete_button.clicked.connect(self._delete_profile)
        import_button = QPushButton("Import")
        import_button.setObjectName("WorkspaceAction")
        import_button.clicked.connect(self._import_profiles)
        export_button = QPushButton("Export")
        export_button.setObjectName("WorkspaceAction")
        export_button.clicked.connect(self._export_profiles)
        row.addWidget(save_button)
        row.addWidget(delete_button)
        row.addWidget(import_button)
        row.addWidget(export_button)
        self._field(layout, "Active profile", self.profile_name)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _set_values(self, profile: ExperienceProfile) -> None:
        self.current = profile
        self._accent = profile.accent
        self.theme.setCurrentIndex(max(0, self.theme.findData(profile.theme)))
        self.animation_speed.setCurrentIndex(
            max(0, self.animation_speed.findData(profile.animation_speed))
        )
        self.reduced_motion.setChecked(profile.reduced_motion)
        self.high_contrast.setChecked(profile.high_contrast)
        self.large_text.setChecked(profile.large_text)
        self.ui_scale.setValue(round(profile.ui_scale * 100))
        self.transparency.setValue(profile.transparency)
        self.workspace_preset.setCurrentIndex(
            max(0, self.workspace_preset.findData(profile.workspace_preset))
        )
        self.accent_button.setText(profile.accent.upper())

    def values(self, *, name: str | None = None) -> ExperienceProfile:
        return ExperienceProfile.from_value(
            {
                "name": name or self.current.name,
                "theme": self.theme.currentData(),
                "accent": self._accent,
                "animation_speed": self.animation_speed.currentData(),
                "reduced_motion": self.reduced_motion.isChecked(),
                "high_contrast": self.high_contrast.isChecked(),
                "large_text": self.large_text.isChecked(),
                "ui_scale": self.ui_scale.value() / 100,
                "transparency": self.transparency.value(),
                "workspace_preset": self.workspace_preset.currentData(),
            }
        )

    def _choose_accent(self) -> None:
        color = QColorDialog.getColor(QColor(self._accent), self, "Choose accent")
        if not color.isValid():
            return
        self._accent = normalize_accent(color.name())
        self.accent_button.setText(self._accent.upper())
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if not hasattr(self, "preview"):
            return
        self.preview.setStyleSheet(
            premium_theme_stylesheet(
                normalize_theme(str(self.theme.currentData() or "dark")),
                self._accent,
                high_contrast=(
                    self.high_contrast.isChecked()
                    if hasattr(self, "high_contrast")
                    else False
                ),
                transparency=self.transparency.value(),
            )
        )
        scale = self.ui_scale.value() / 100 if hasattr(self, "ui_scale") else 1.0
        self.preview_text.setStyleSheet(f"font-size: {max(10, round(13 * scale))}px;")

    def _filter_categories(self, text: str) -> None:
        needle = text.strip().casefold()
        first_visible = -1
        for index in range(self.categories.count()):
            item = self.categories.item(index)
            visible = not needle or needle in (
                f"{item.text()} theme accent animation motion contrast "
                "scale layout profile import export"
            ).casefold()
            item.setHidden(not visible)
            if visible and first_visible < 0:
                first_visible = index
        if first_visible >= 0:
            self.categories.setCurrentRow(first_visible)

    def _show_category(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _refresh_profiles(self) -> None:
        current_name = self.current.name
        self.profile_name.blockSignals(True)
        self.profile_name.clear()
        self.profile_name.addItem("Default")
        for profile in self.store.list():
            if profile.name.casefold() != "default":
                self.profile_name.addItem(profile.name)
        self.profile_name.setCurrentText(current_name)
        self.profile_name.blockSignals(False)

    def _profile_selected(self, name: str) -> None:
        profile = self.store.get(name)
        if profile is not None:
            self._set_values(profile)
            self._refresh_preview()

    def _save_profile(self) -> None:
        name = self.profile_name.currentText().strip() or "Default"
        profile = self.store.save(self.values(name=name))
        self.current = profile
        self._refresh_profiles()
        self.profile_name.setCurrentText(profile.name)

    def _delete_profile(self) -> None:
        if self.store.delete(self.profile_name.currentText()):
            self.current = ExperienceProfile()
            self._set_values(self.current)
            self._refresh_profiles()

    def _import_profiles(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import MORICE profiles", str(Path.home()), "JSON files (*.json)"
        )
        if not path:
            return
        try:
            imported = self.store.import_file(path)
        except ValueError as exc:
            QMessageBox.warning(self, "Profile import failed", str(exc))
            return
        self._refresh_profiles()
        QMessageBox.information(self, "Profiles imported", f"Imported {imported} profile(s).")

    def _export_profiles(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export MORICE profiles",
            str(Path.home() / "morice-experience-profiles.json"),
            "JSON files (*.json)",
        )
        if path:
            self.store.export(path)

    def _reset(self) -> None:
        self._set_values(ExperienceProfile())
        self._refresh_preview()

    def _apply(self) -> None:
        profile = self.values(name=self.profile_name.currentText() or "Default")
        self.current = self.store.save(profile)
        self.preferences_applied.emit(asdict(self.current))
        self.accept()


__all__ = ["PremiumSettingsDialog"]
