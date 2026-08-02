from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)


class FirstRunWizard(QWizard):
    def __init__(self, service: Any, report: dict[str, Any], parent=None):
        super().__init__(parent)
        self.service = service
        self.report = report
        self.setWindowTitle("Set up MORICE")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(680, 500)
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
        self.addPage(self._welcome_page())
        self.addPage(self._hardware_page())
        self.addPage(self._components_page())
        self.addPage(self._permissions_page())
        self.addPage(self._workspace_page())
        self.accepted.connect(self._complete)

    def _welcome_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Welcome to MORICE")
        page.setSubTitle(
            "Configure local AI, optional components, permissions, and your first workspace."
        )
        layout = QVBoxLayout(page)
        label = QLabel(
            "MORICE remains useful offline. Local models, projects, memory, "
            "renderers, plugins, and desktop actions stay under your control."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def _hardware_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Hardware and model")
        gpu = dict(self.report.get("gpu", {}))
        layout = QVBoxLayout(page)
        hardware = QLabel(
            f"GPU: {gpu.get('name') or 'Not detected'}\n"
            f"VRAM: {gpu.get('vramMb', 0) / 1024:.1f} GB\n"
            f"System memory: {self.report.get('memoryMb', 0) / 1024:.1f} GB\n"
            f"Free storage: {self.report.get('diskFreeBytes', 0) / (1024 ** 3):.1f} GB"
        )
        hardware.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(hardware)
        layout.addWidget(QLabel("Recommended local model class"))
        self.model_choice = QComboBox()
        for recommendation in self.report.get("recommendedModels", ()):
            label = (
                f"{recommendation.get('modelClass', 'Local model')} - "
                f"{recommendation.get('detail', '')}"
            )
            self.model_choice.addItem(label, recommendation.get("modelClass", ""))
            if recommendation.get("fit"):
                self.model_choice.setCurrentIndex(self.model_choice.count() - 1)
        layout.addWidget(self.model_choice)
        note = QLabel(
            "This is a hardware recommendation, not a benchmark guarantee. "
            "You can change the model later from the MORICE panel."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _components_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Optional components")
        layout = QVBoxLayout(page)
        self.component_checks: list[QCheckBox] = []
        for component in self.report.get("optionalComponents", ()):
            check = QCheckBox(str(component))
            check.setChecked(component != "Plugin SDK developer tools")
            layout.addWidget(check)
            self.component_checks.append(check)
        layout.addStretch(1)
        return page

    def _permissions_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Permission model")
        layout = QVBoxLayout(page)
        for permission in self.report.get("permissions", ()):
            label = QLabel(f"- {permission}")
            label.setWordWrap(True)
            layout.addWidget(label)
        self.permission_acknowledgement = QCheckBox(
            "I understand that destructive actions require explicit approval."
        )
        self.permission_acknowledgement.setChecked(True)
        layout.addWidget(self.permission_acknowledgement)
        layout.addStretch(1)
        return page

    def _workspace_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("Create your first workspace")
        page.setSubTitle("MORICE will not use its application folder as a project.")
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        self.workspace = QLineEdit(
            str(Path.home() / "MORICE Projects")
        )
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse_workspace)
        row.addWidget(self.workspace, stretch=1)
        row.addWidget(browse)
        layout.addLayout(row)
        detail = QLabel(
            "The folder is created when setup finishes. Project Mode still "
            "previews exact file changes before applying them."
        )
        detail.setWordWrap(True)
        layout.addWidget(detail)
        layout.addStretch(1)
        return page

    def _browse_workspace(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Choose MORICE workspace",
            self.workspace.text() or os.path.expanduser("~"),
        )
        if path:
            self.workspace.setText(path)

    def _complete(self) -> None:
        selected_components = [
            check.text() for check in self.component_checks if check.isChecked()
        ]
        self.service.complete(
            self.workspace.text().strip() or str(Path.home() / "MORICE Projects"),
            {
                "modelClass": self.model_choice.currentData(),
                "components": selected_components,
                "permissionAcknowledged": self.permission_acknowledgement.isChecked(),
            },
        )
