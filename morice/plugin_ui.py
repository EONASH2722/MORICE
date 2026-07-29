from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .plugin_cli import create_plugin, pack_plugin
from .plugin_manager import PluginManager
from .plugin_sdk import PluginState


class PermissionReviewDialog(QDialog):
    def __init__(self, manager: PluginManager, plugin_id: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.record = manager.require(plugin_id)
        self.setWindowTitle(f"Review permissions - {self.record.manifest.name}")
        self.setMinimumWidth(520)
        root = QVBoxLayout(self)
        title = QLabel(f"Permissions requested by {self.record.manifest.name}")
        title.setObjectName("PluginDialogTitle")
        detail = QLabel(
            "Review every capability before this plugin starts. Unchecked capabilities "
            "remain blocked inside the isolated plugin process."
        )
        detail.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(detail)
        self.checks: dict[str, QCheckBox] = {}
        existing = manager.permissions.snapshot(plugin_id)
        granted = set(existing.get("granted", ()))
        for permission in self.record.manifest.permissions:
            check = QCheckBox(permission.value)
            check.setChecked(permission.value in granted)
            check.setToolTip(_permission_description(permission.value))
            root.addWidget(check)
            self.checks[permission.value] = check
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @property
    def granted(self) -> tuple[str, ...]:
        return tuple(key for key, check in self.checks.items() if check.isChecked())


class PluginCenter(QDialog):
    operation_finished = Signal(str, bool, str)

    def __init__(self, manager: PluginManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setObjectName("PluginCenter")
        self.setWindowTitle("MORICE Plugin Center")
        self.setMinimumSize(880, 620)
        self.resize(1040, 720)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="plugin-ui")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        heading_row = QHBoxLayout()
        heading = QLabel("Plugin Center")
        heading.setObjectName("PluginCenterTitle")
        self.summary = QLabel()
        self.summary.setObjectName("PluginCenterSummary")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        heading_row.addWidget(heading)
        heading_row.addWidget(self.summary)
        heading_row.addStretch(1)
        heading_row.addWidget(refresh)
        root.addLayout(heading_row)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.installed_tab = self._build_installed_tab()
        self.marketplace_tab = self._build_marketplace_tab()
        self.permissions_tab = self._build_permissions_tab()
        self.diagnostics_tab = self._build_diagnostics_tab()
        self.developer_tab = self._build_developer_tab()
        self.tabs.addTab(self.installed_tab, "Installed")
        self.tabs.addTab(self.marketplace_tab, "Marketplace")
        self.tabs.addTab(self.permissions_tab, "Permissions")
        self.tabs.addTab(self.diagnostics_tab, "Diagnostics")
        self.tabs.addTab(self.developer_tab, "Developer")
        root.addWidget(self.tabs, stretch=1)
        self.status = QLabel("Ready")
        self.status.setObjectName("PluginCenterStatus")
        root.addWidget(self.status)
        self.operation_finished.connect(self._on_operation_finished)
        self.refresh()

    def open_center(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def _build_installed_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        splitter = QSplitter(Qt.Horizontal)
        self.installed_list = QListWidget()
        self.installed_list.currentItemChanged.connect(self._show_installed)
        details = QWidget()
        details_layout = QVBoxLayout(details)
        self.installed_title = QLabel("Select a plugin")
        self.installed_title.setObjectName("PluginDetailTitle")
        self.installed_details = QPlainTextEdit()
        self.installed_details.setReadOnly(True)
        actions = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.pause_button = QPushButton("Pause")
        self.reload_button = QPushButton("Reload")
        self.update_button = QPushButton("Update package")
        self.pin_button = QPushButton("Pin")
        self.rollback_button = QPushButton("Rollback")
        self.remove_button = QPushButton("Remove")
        self.start_button.clicked.connect(self._start_selected)
        self.pause_button.clicked.connect(self._pause_selected)
        self.reload_button.clicked.connect(self._reload_selected)
        self.update_button.clicked.connect(self._update_selected)
        self.pin_button.clicked.connect(self._pin_selected)
        self.rollback_button.clicked.connect(self._rollback_selected)
        self.remove_button.clicked.connect(self._remove_selected)
        for button in (
            self.start_button,
            self.pause_button,
            self.reload_button,
            self.update_button,
            self.pin_button,
            self.rollback_button,
            self.remove_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        details_layout.addWidget(self.installed_title)
        details_layout.addWidget(self.installed_details, stretch=1)
        details_layout.addLayout(actions)
        splitter.addWidget(self.installed_list)
        splitter.addWidget(details)
        splitter.setSizes([300, 650])
        layout.addWidget(splitter)
        install = QPushButton("Install plugin package")
        install.clicked.connect(self._install_package)
        layout.addWidget(install, alignment=Qt.AlignLeft)
        return page

    def _build_marketplace_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        source_row = QHBoxLayout()
        self.marketplace_source = QLineEdit()
        self.marketplace_source.setPlaceholderText(
            "HTTPS catalog URL or local marketplace JSON file"
        )
        load = QPushButton("Load catalog")
        load.clicked.connect(self._load_marketplace)
        source_row.addWidget(self.marketplace_source, stretch=1)
        source_row.addWidget(load)
        layout.addLayout(source_row)
        self.marketplace_search = QLineEdit()
        self.marketplace_search.setPlaceholderText("Search plugins...")
        self.marketplace_search.textChanged.connect(self._filter_marketplace)
        layout.addWidget(self.marketplace_search)
        self.automatic_updates = QCheckBox("Install compatible updates automatically")
        self.automatic_updates.setChecked(self.manager.auto_updates_enabled)
        self.automatic_updates.toggled.connect(self.manager.set_automatic_updates)
        layout.addWidget(self.automatic_updates)
        self.marketplace_list = QListWidget()
        self.marketplace_list.itemDoubleClicked.connect(
            lambda _item: self._install_marketplace_selected()
        )
        layout.addWidget(self.marketplace_list, stretch=1)
        install = QPushButton("Install selected")
        install.clicked.connect(self._install_marketplace_selected)
        layout.addWidget(install, alignment=Qt.AlignLeft)
        return page

    def _build_permissions_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        info = QLabel(
            "Permission decisions are version-specific. An update that changes its "
            "capabilities must be reviewed again."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        self.permission_list = QListWidget()
        layout.addWidget(self.permission_list, stretch=1)
        review = QPushButton("Review selected")
        review.clicked.connect(self._review_selected_permissions)
        layout.addWidget(review, alignment=Qt.AlignLeft)
        return page

    def _build_diagnostics_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.diagnostics_text = QPlainTextEdit()
        self.diagnostics_text.setReadOnly(True)
        layout.addWidget(self.diagnostics_text)
        return page

    def _build_developer_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel(
            "Create a process-isolated sample, validate its manifest, then package it "
            "as a portable MORICE plugin."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.dev_id = QLineEdit("example.hello")
        self.dev_name = QLineEdit("Hello MORICE")
        self.dev_directory = QLineEdit()
        browse = QPushButton("Choose folder")
        browse.clicked.connect(self._choose_dev_directory)
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.dev_directory, stretch=1)
        directory_row.addWidget(browse)
        form.addRow("Plugin id", self.dev_id)
        form.addRow("Name", self.dev_name)
        form.addRow("Folder", directory_row)
        layout.addLayout(form)
        actions = QHBoxLayout()
        generate = QPushButton("Generate sample")
        package = QPushButton("Package ZIP")
        generate.clicked.connect(self._generate_sample)
        package.clicked.connect(self._package_sample)
        actions.addWidget(generate)
        actions.addWidget(package)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.dev_output = QPlainTextEdit()
        self.dev_output.setReadOnly(True)
        layout.addWidget(self.dev_output, stretch=1)
        return page

    def refresh(self) -> None:
        selected_id = self._selected_id(self.installed_list)
        self.installed_list.clear()
        self.permission_list.clear()
        records = tuple(self.manager.records[key] for key in sorted(self.manager.records))
        for record in records:
            item = QListWidgetItem(
                f"{record.manifest.name}\n{record.manifest.version} | {record.state.value}"
            )
            item.setData(Qt.UserRole, record.manifest.plugin_id)
            self.installed_list.addItem(item)
            review = self.manager.permissions.snapshot(record.manifest.plugin_id)
            permission_item = QListWidgetItem(
                f"{record.manifest.name}\n"
                f"Granted: {', '.join(review.get('granted', ())) or 'none'}"
            )
            permission_item.setData(Qt.UserRole, record.manifest.plugin_id)
            self.permission_list.addItem(permission_item)
            if record.manifest.plugin_id == selected_id:
                self.installed_list.setCurrentItem(item)
        if self.installed_list.count() and self.installed_list.currentRow() < 0:
            self.installed_list.setCurrentRow(0)
        diagnostics = self.manager.diagnostics()
        self.summary.setText(
            f"{diagnostics['count']} installed | {diagnostics['running']} running | "
            f"{diagnostics['failed']} failed"
        )
        self.diagnostics_text.setPlainText(
            json.dumps(diagnostics, ensure_ascii=True, indent=2)
        )
        self._filter_marketplace()

    def _show_installed(self, current: QListWidgetItem | None, _previous=None) -> None:
        plugin_id = current.data(Qt.UserRole) if current else ""
        if not plugin_id:
            self.installed_title.setText("Select a plugin")
            self.installed_details.clear()
            return
        record = self.manager.require(plugin_id)
        self.installed_title.setText(record.manifest.name)
        self.installed_details.setPlainText(
            json.dumps(
                record.to_dict(self.manager.permissions.snapshot(plugin_id)),
                ensure_ascii=True,
                indent=2,
            )
        )
        running = record.state == PluginState.RUNNING
        self.start_button.setText("Resume" if record.state == PluginState.PAUSED else "Start")
        self.pin_button.setText("Unpin" if record.pinned_version else "Pin")
        self.start_button.setEnabled(not running)
        self.pause_button.setEnabled(running)

    def _selected_id(self, widget: QListWidget) -> str:
        item = widget.currentItem()
        return str(item.data(Qt.UserRole)) if item else ""

    def _run(self, label: str, callback) -> None:
        self.status.setText(label)
        future = self._executor.submit(callback)

        def completed(done) -> None:
            try:
                result = done.result()
                self.operation_finished.emit(label, True, str(result or "Done"))
            except Exception as exc:
                self.operation_finished.emit(label, False, str(exc))

        future.add_done_callback(completed)

    def _start_selected(self) -> None:
        plugin_id = self._selected_id(self.installed_list)
        if not plugin_id:
            return
        record = self.manager.require(plugin_id)
        if not self.manager.permissions.is_reviewed(record.manifest):
            if not self._review_permissions(plugin_id):
                return
        self._run(f"Starting {record.manifest.name}...", lambda: self.manager.start(plugin_id))

    def _pause_selected(self) -> None:
        plugin_id = self._selected_id(self.installed_list)
        if plugin_id:
            self._run("Pausing plugin...", lambda: self.manager.pause(plugin_id))

    def _reload_selected(self) -> None:
        plugin_id = self._selected_id(self.installed_list)
        if plugin_id:
            self._run("Reloading plugin...", lambda: self.manager.reload(plugin_id))

    def _update_selected(self) -> None:
        plugin_id = self._selected_id(self.installed_list)
        if not plugin_id:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select plugin update package",
            str(Path.home()),
            "MORICE plugins (*.zip);;ZIP archives (*.zip)",
        )
        if path:
            self._run(
                "Validating and applying update...",
                lambda: self.manager.update(plugin_id, path),
            )

    def _pin_selected(self) -> None:
        plugin_id = self._selected_id(self.installed_list)
        if not plugin_id:
            return
        record = self.manager.require(plugin_id)
        version = "" if record.pinned_version else record.manifest.version
        self.manager.pin(plugin_id, version)
        self.refresh()

    def _rollback_selected(self) -> None:
        plugin_id = self._selected_id(self.installed_list)
        if not plugin_id:
            return
        history = self.manager.update_history(plugin_id)
        versions = [item["version"] for item in history]
        if not versions:
            QMessageBox.information(
                self, "No rollback available", "This plugin has no retained update history."
            )
            return
        version, accepted = QInputDialog.getItem(
            self,
            "Roll back plugin",
            "Restore version",
            versions,
            0,
            False,
        )
        if accepted and version:
            self._run(
                f"Rolling back to {version}...",
                lambda: self.manager.rollback(plugin_id, version),
            )

    def _remove_selected(self) -> None:
        plugin_id = self._selected_id(self.installed_list)
        if not plugin_id:
            return
        record = self.manager.require(plugin_id)
        choice = QMessageBox.question(
            self,
            "Remove plugin",
            f"Remove {record.manifest.name}? Plugin settings and permissions will be removed.",
        )
        if choice == QMessageBox.Yes:
            self._run("Removing plugin...", lambda: self.manager.uninstall(plugin_id))

    def _install_package(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Install MORICE plugin",
            str(Path.home()),
            "MORICE plugins (*.zip);;ZIP archives (*.zip)",
        )
        if path:
            self._run("Validating and installing plugin...", lambda: self.manager.install(path))

    def _load_marketplace(self) -> None:
        source = self.marketplace_source.text().strip()
        if not source:
            source, _ = QFileDialog.getOpenFileName(
                self,
                "Open marketplace catalog",
                str(Path.home()),
                "JSON catalogs (*.json)",
            )
        if source:
            self.marketplace_source.setText(source)
            self._run(
                "Loading marketplace catalog...",
                lambda: self.manager.marketplace.refresh(source),
            )

    def _filter_marketplace(self) -> None:
        query = self.marketplace_search.text() if hasattr(self, "marketplace_search") else ""
        self.marketplace_list.clear()
        for entry in self.manager.marketplace.search(query):
            badges = []
            if entry.verified:
                badges.append("verified")
            if entry.featured:
                badges.append("featured")
            item = QListWidgetItem(
                f"{entry.name} {entry.version}\n"
                f"{entry.description}\n"
                f"{entry.rating:.1f}/5 | {entry.downloads:,} downloads"
                + (f" | {', '.join(badges)}" if badges else "")
            )
            item.setData(Qt.UserRole, entry.plugin_id)
            self.marketplace_list.addItem(item)

    def _install_marketplace_selected(self) -> None:
        plugin_id = self._selected_id(self.marketplace_list)
        entry = next(
            (item for item in self.manager.marketplace.entries if item.plugin_id == plugin_id),
            None,
        )
        if entry:
            installed = self.manager.records.get(entry.plugin_id)
            if installed:
                operation = lambda: self.manager.update_from_marketplace(entry)
            else:
                operation = lambda: self.manager.install_marketplace(entry)
            self._run(
                f"{'Updating' if installed else 'Installing'} {entry.name}...",
                operation,
            )

    def _review_selected_permissions(self) -> None:
        plugin_id = self._selected_id(self.permission_list)
        if plugin_id and self._review_permissions(plugin_id):
            self.refresh()

    def _review_permissions(self, plugin_id: str) -> bool:
        dialog = PermissionReviewDialog(self.manager, plugin_id, self)
        if dialog.exec() != QDialog.Accepted:
            return False
        self.manager.review_permissions(plugin_id, dialog.granted)
        return True

    def _choose_dev_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Choose plugin parent folder", str(Path.home())
        )
        if path:
            self.dev_directory.setText(
                str(Path(path) / self.dev_id.text().replace(".", "-"))
            )

    def _generate_sample(self) -> None:
        directory = Path(self.dev_directory.text().strip())
        try:
            create_plugin(directory, self.dev_id.text().strip(), self.dev_name.text().strip())
            self.dev_output.setPlainText(f"Created sample plugin:\n{directory.resolve()}")
        except Exception as exc:
            self.dev_output.setPlainText(f"Generation failed:\n{exc}")

    def _package_sample(self) -> None:
        directory = Path(self.dev_directory.text().strip())
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Package MORICE plugin",
            str(directory.with_suffix(".zip")),
            "ZIP archives (*.zip)",
        )
        if not output:
            return
        try:
            result = pack_plugin(directory, Path(output))
            self.dev_output.setPlainText(f"Plugin package created:\n{result.resolve()}")
        except Exception as exc:
            self.dev_output.setPlainText(f"Packaging failed:\n{exc}")

    def _on_operation_finished(self, label: str, succeeded: bool, detail: str) -> None:
        self.status.setText(("Completed: " if succeeded else "Failed: ") + detail)
        if not succeeded:
            QMessageBox.warning(self, "Plugin operation failed", detail)
        self.refresh()

    def closeEvent(self, event) -> None:
        super().closeEvent(event)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.close()


def _permission_description(permission: str) -> str:
    descriptions = {
        "filesystem.read": "Read files outside the plugin package.",
        "filesystem.write": "Request brokered writes outside plugin storage.",
        "network": "Open internet or local network connections.",
        "process": "Request brokered external process execution.",
        "project.read": "Read active-project data through MORICE.",
        "project.write": "Write active-project data through MORICE.",
        "clipboard": "Read or write clipboard content.",
        "notifications": "Show native MORICE notifications.",
        "microphone": "Access microphone input through MORICE.",
        "voice": "Provide or consume voice features through MORICE.",
        "camera": "Access camera input through MORICE.",
        "desktop.control": "Request desktop interaction through MORICE.",
        "model.access": "Use the active MORICE model.",
        "memory.read": "Read approved MORICE memory entries.",
        "memory.write": "Create approved MORICE memory entries.",
        "automation": "Create or run MORICE automations.",
        "gpu": "Request GPU-backed computation.",
    }
    return descriptions.get(permission, "Plugin capability")


__all__ = ["PermissionReviewDialog", "PluginCenter"]
