from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from PySide6.QtCore import QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
except ImportError:  # pragma: no cover - optional in minimal PySide installs
    QPdfDocument = None
    QPdfView = None

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:  # pragma: no cover - optional in minimal PySide installs
    QWebEngineView = None

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
except ImportError:  # pragma: no cover - optional in minimal PySide installs
    QAudioOutput = None
    QMediaPlayer = None
    QVideoWidget = None


TEXT_EXTENSIONS = {
    ".bat",
    ".c",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".jsonl",
    ".jsx",
    ".log",
    ".md",
    ".py",
    ".qml",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
MEDIA_EXTENSIONS = {".aac", ".avi", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".wav", ".webm"}


@dataclass(frozen=True)
class CommandItem:
    key: str
    title: str
    hint: str = ""
    keywords: str = ""

    @property
    def searchable_text(self) -> str:
        return f"{self.title} {self.hint} {self.keywords}".lower()


DEFAULT_COMMANDS = (
    CommandItem("new-chat", "New chat", "Start with a clear conversation", "clear reset"),
    CommandItem("workspace", "Toggle workspace hub", "Dashboard, files, tools", "panel dock"),
    CommandItem("project", "Switch to Project mode", "Build and edit a work folder", "code"),
    CommandItem("normal-chat", "Switch to Normal chat", "Conversation and VNext", "chat"),
    CommandItem("open-file", "Open file", "Preview a local file", "browse"),
    CommandItem("find-files", "Find files", "Search common local folders", "search"),
    CommandItem(
        "search-everywhere",
        "Search everywhere",
        "Files, projects, memory, commands, tools, and logs",
        "global universal",
    ),
    CommandItem("system", "System status", "CPU, memory, storage, battery", "hardware"),
    CommandItem(
        "diagnostics",
        "Advanced diagnostics",
        "Health, logs, renderers, workers, and performance",
        "debug profiler crash recovery",
    ),
    CommandItem("screenshot", "Capture screenshot", "Save the current display", "screen"),
    CommandItem("theme", "Toggle light or dark theme", "Change appearance", "color"),
    CommandItem("accent", "Choose accent color", "Personalize the workspace", "theme"),
    CommandItem(
        "settings",
        "Open premium settings",
        "Themes, motion, accessibility, layouts, and profiles",
        "preferences scale contrast",
    ),
    CommandItem("layout-focus", "Focus layout", "Conversation without side panels", "workspace"),
    CommandItem("layout-science", "Science layout", "Chat beside visual workspace", "workspace"),
    CommandItem("layout-project", "Project layout", "Code, files, output, and changes", "workspace"),
    CommandItem("layout-research", "Research layout", "Science and desktop tools", "workspace"),
    CommandItem("notes", "Open notes", "Persistent scratch notes", "write"),
    CommandItem("browser", "Open browser", "Browse without leaving MORICE", "web"),
    CommandItem("media", "Open media controls", "Playback and volume", "music"),
    CommandItem(
        "desktop",
        "Open desktop services",
        "Notifications, memory, permissions, and automations",
        "phase 3 operating environment",
    ),
    CommandItem(
        "plugins",
        "Open Plugin Center",
        "Install, review, update, debug, and build MORICE extensions",
        "extensions marketplace sdk developer",
    ),
    CommandItem(
        "platform",
        "Open autonomous platform",
        "Project dashboard, agents, knowledge, updates, and release readiness",
        "phase 7 project tasks git knowledge release",
    ),
    CommandItem("new-window", "New MORICE window", "Open another workspace", "multi"),
)


class CommandPalette(QDialog):
    action_requested = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        commands: Iterable[CommandItem] = DEFAULT_COMMANDS,
    ):
        super().__init__(parent)
        self.setObjectName("CommandPalette")
        self.setWindowTitle("MORICE command palette")
        self.setModal(True)
        self.setMinimumSize(540, 420)
        self.resize(620, 480)
        self.commands = tuple(commands)
        self._recent: tuple[str, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        title = QLabel("Command palette")
        title.setObjectName("CommandTitle")
        hint = QLabel("Type to find an action. Press Enter to run it.")
        hint.setObjectName("CommandHint")
        self.search = QLineEdit()
        self.search.setObjectName("CommandSearch")
        self.search.setPlaceholderText("Search commands...")
        self.results = QListWidget()
        self.results.setObjectName("CommandResults")
        self.results.itemActivated.connect(self._activate)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._activate_current)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.search)
        layout.addWidget(self.results, stretch=1)
        self._filter("")

    def open_palette(self) -> None:
        self.search.clear()
        self._filter("")
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus(Qt.ShortcutFocusReason)

    def set_recent(self, keys: Iterable[str]) -> None:
        valid = {command.key for command in self.commands}
        self._recent = tuple(
            key for key in (str(value) for value in keys) if key in valid
        )[:12]

    def set_commands(self, commands: Iterable[CommandItem]) -> None:
        self.commands = tuple(commands)
        self.set_recent(self._recent)
        self._filter(self.search.text())

    def _filter(self, value: str) -> None:
        terms = [part for part in value.lower().split() if part]
        self.results.clear()
        recent_rank = {key: index for index, key in enumerate(self._recent)}
        commands = sorted(
            self.commands,
            key=lambda command: (
                recent_rank.get(command.key, len(recent_rank) + 1),
                command.title.casefold(),
            ),
        )
        for command in commands:
            if terms and not all(term in command.searchable_text for term in terms):
                continue
            label = command.title
            if command.hint:
                label += f"\n{command.hint}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, command.key)
            item.setToolTip(command.hint)
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def _activate_current(self) -> None:
        item = self.results.currentItem()
        if item is not None:
            self._activate(item)

    def _activate(self, item: QListWidgetItem) -> None:
        key = str(item.data(Qt.UserRole) or "")
        if not key:
            return
        self.accept()
        self.action_requested.emit(key)


class JsonTree(QTreeWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("WorkspaceJsonTree")
        self.setHeaderLabels(["Key", "Value"])
        self.setAlternatingRowColors(True)

    def set_value(self, value: Any) -> None:
        self.clear()
        self._append(self.invisibleRootItem(), value)
        self.expandToDepth(2)

    def _append(self, parent: QTreeWidgetItem, value: Any, label: str = "root") -> None:
        if isinstance(value, dict):
            item = QTreeWidgetItem([label, f"object ({len(value)})"])
            parent.addChild(item)
            for key, child in value.items():
                self._append(item, child, str(key))
            return
        if isinstance(value, list):
            item = QTreeWidgetItem([label, f"array ({len(value)})"])
            parent.addChild(item)
            for index, child in enumerate(value):
                self._append(item, child, str(index))
            return
        parent.addChild(QTreeWidgetItem([label, json.dumps(value, ensure_ascii=False)]))


class FilePreview(QWidget):
    open_external_requested = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.header = QLabel("Select a file to preview.")
        self.header.setObjectName("WorkspaceMuted")
        self.header.setWordWrap(True)

        self.stack = QStackedWidget()
        self.stack.setObjectName("WorkspacePreview")
        self.placeholder = QLabel("Text, JSON, image, and PDF previews appear here.")
        self.placeholder.setObjectName("WorkspaceMuted")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.text = QPlainTextEdit()
        self.text.setObjectName("WorkspaceTextPreview")
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.json_tree = JsonTree()
        self.spreadsheet = QTableWidget()
        self.spreadsheet.setObjectName("WorkspaceSpreadsheet")
        self.spreadsheet.setEditTriggers(QTableWidget.NoEditTriggers)
        self.spreadsheet.setAlternatingRowColors(True)
        self.image = QLabel()
        self.image.setObjectName("WorkspaceImagePreview")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setScaledContents(False)
        self.pdf_view = QPdfView() if QPdfView is not None else None
        self.pdf_document = QPdfDocument(self) if QPdfDocument is not None else None
        if self.pdf_view is not None and self.pdf_document is not None:
            self.pdf_view.setDocument(self.pdf_document)
            self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

        self.stack.addWidget(self.placeholder)
        self.stack.addWidget(self.text)
        self.stack.addWidget(self.json_tree)
        self.stack.addWidget(self.spreadsheet)
        self.stack.addWidget(self.image)
        if self.pdf_view is not None:
            self.stack.addWidget(self.pdf_view)

        self.open_external = QPushButton("Open in default app")
        self.open_external.setObjectName("WorkspaceAction")
        self.open_external.setEnabled(False)
        self.open_external.clicked.connect(self._open_external)
        self.current_path = ""

        layout.addWidget(self.header)
        layout.addWidget(self.stack, stretch=1)
        layout.addWidget(self.open_external)

    def clear(self, message: str = "Select a file to preview.") -> None:
        self.current_path = ""
        self.header.setText(message)
        self.placeholder.setText(message)
        self.stack.setCurrentWidget(self.placeholder)
        self.open_external.setEnabled(False)

    def show_file(self, path: str) -> tuple[bool, str]:
        target = os.path.abspath(os.path.expanduser(path))
        if not os.path.isfile(target):
            self.clear(f"File not found: {target}")
            return False, "File not found."
        self.current_path = target
        self.open_external.setEnabled(True)
        extension = Path(target).suffix.lower()
        size = os.path.getsize(target)
        self.header.setText(f"{target}\n{size / 1024:.1f} KB")
        try:
            if extension == ".json":
                if size > 8 * 1024 * 1024:
                    raise ValueError("JSON preview is limited to 8 MB.")
                with open(target, "r", encoding="utf-8") as handle:
                    self.json_tree.set_value(json.load(handle))
                self.stack.setCurrentWidget(self.json_tree)
                return True, "JSON preview loaded."
            if extension == ".csv":
                if size > 8 * 1024 * 1024:
                    raise ValueError("Spreadsheet preview is limited to 8 MB.")
                with open(
                    target, "r", encoding="utf-8-sig", errors="replace", newline=""
                ) as handle:
                    rows = list(csv.reader(handle))[:501]
                if not rows:
                    raise ValueError("The CSV file is empty.")
                column_count = min(100, max(len(row) for row in rows))
                headers = rows[0][:column_count]
                data_rows = rows[1:]
                self.spreadsheet.clear()
                self.spreadsheet.setColumnCount(column_count)
                self.spreadsheet.setRowCount(len(data_rows))
                self.spreadsheet.setHorizontalHeaderLabels(
                    headers
                    + [f"Column {index + 1}" for index in range(len(headers), column_count)]
                )
                for row_index, row in enumerate(data_rows):
                    for column_index, value in enumerate(row[:column_count]):
                        self.spreadsheet.setItem(
                            row_index, column_index, QTableWidgetItem(value)
                        )
                self.spreadsheet.resizeColumnsToContents()
                self.stack.setCurrentWidget(self.spreadsheet)
                return True, "Spreadsheet preview loaded."
            if extension in TEXT_EXTENSIONS or extension == "":
                if size > 4 * 1024 * 1024:
                    raise ValueError("Text preview is limited to 4 MB.")
                with open(target, "r", encoding="utf-8", errors="replace") as handle:
                    self.text.setPlainText(handle.read())
                self.stack.setCurrentWidget(self.text)
                return True, "Text preview loaded."
            if extension in IMAGE_EXTENSIONS:
                pixmap = QPixmap(target)
                if pixmap.isNull():
                    raise ValueError("Qt could not decode this image.")
                maximum = self.stack.size()
                if maximum.width() > 80 and maximum.height() > 80:
                    pixmap = pixmap.scaled(
                        maximum.width() - 24,
                        maximum.height() - 24,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                self.image.setPixmap(pixmap)
                self.stack.setCurrentWidget(self.image)
                return True, "Image preview loaded."
            if extension == ".pdf" and self.pdf_document is not None and self.pdf_view is not None:
                self.pdf_document.load(target)
                self.stack.setCurrentWidget(self.pdf_view)
                return True, "PDF preview loaded."
            if extension in MEDIA_EXTENSIONS:
                self.placeholder.setText(
                    "This media file is ready. Use Open in default app or the Media tab controls."
                )
                self.stack.setCurrentWidget(self.placeholder)
                return True, "Media file ready."
            self.placeholder.setText(
                f"No safe inline preview is registered for {extension or 'this file type'}."
            )
            self.stack.setCurrentWidget(self.placeholder)
            return False, "No inline preview is available."
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.placeholder.setText(str(exc))
            self.stack.setCurrentWidget(self.placeholder)
            return False, str(exc)

    def show_descriptor(self, descriptor: Any) -> tuple[bool, str]:
        """Display a validated core preview descriptor without reopening binary data."""
        path = str(getattr(descriptor, "path", "") or "")
        kind = str(getattr(descriptor, "kind", "") or "")
        if kind in {"image", "pdf", "audio", "video", "json", "csv", "text"}:
            return self.show_file(path)
        metadata = getattr(descriptor, "metadata", None)
        size = int(getattr(metadata, "size", 0) or 0)
        self.current_path = path
        self.open_external.setEnabled(bool(path))
        self.header.setText(f"{path}\n{size / 1024:.1f} KB")
        if not bool(getattr(descriptor, "available", False)):
            reason = str(getattr(descriptor, "reason", "") or "Preview unavailable.")
            self.placeholder.setText(reason)
            self.stack.setCurrentWidget(self.placeholder)
            return False, reason
        text = str(getattr(descriptor, "text", "") or "")
        entries = tuple(getattr(descriptor, "entries", ()) or ())
        if text:
            self.text.setPlainText(text)
            self.stack.setCurrentWidget(self.text)
            return True, f"{kind.upper()} content preview loaded."
        if entries:
            self.text.setPlainText("\n".join(str(item) for item in entries))
            self.stack.setCurrentWidget(self.text)
            return True, f"{kind.upper()} archive preview loaded."
        self.placeholder.setText(
            f"{kind.title() or 'File'} metadata loaded. No extractable text was found."
        )
        self.stack.setCurrentWidget(self.placeholder)
        return True, f"{kind.title() or 'File'} metadata loaded."

    def _open_external(self) -> None:
        if self.current_path:
            self.open_external_requested.emit(self.current_path)


class AssistantHub(QFrame):
    command_requested = Signal(str, object)
    notes_changed = Signal(str)
    visibility_requested = Signal(bool)

    TAB_NAMES = ("Dashboard", "Files", "Activity", "Platform", "Tools")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("AssistantHub")
        self.setMinimumWidth(350)
        self.setMaximumWidth(700)
        self.resize(440, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("Workspace")
        title.setObjectName("AssistantHubTitle")
        self.search = QLineEdit()
        self.search.setObjectName("WorkspaceSearch")
        self.search.setPlaceholderText("Search tools, files, and activity...")
        self.search.returnPressed.connect(self._search)
        close_button = QPushButton("Close")
        close_button.setObjectName("WorkspaceCloseButton")
        close_button.clicked.connect(lambda: self.visibility_requested.emit(False))
        header.addWidget(title)
        header.addWidget(self.search, stretch=1)
        header.addWidget(close_button)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("HubTabs")
        self.tabs.setDocumentMode(True)
        self.dashboard_page = self._build_dashboard()
        self.file_explorer_page = self._build_files()
        self.downloads_page = self._build_downloads()
        self.files_page = self._group_tabs(
            ("Explorer", self.file_explorer_page),
            ("Downloads", self.downloads_page),
        )
        self.files_subtabs = self.files_page.findChild(QTabWidget, "HubSubTabs")
        self.tasks_page = self._build_tasks()
        self.activity_page = self._build_activity()
        self.logs_page = self._build_logs()
        self.clipboard_page = self._build_clipboard()
        self.activity_group_page = self._group_tabs(
            ("Timeline", self.activity_page),
            ("Tasks", self.tasks_page),
            ("Logs", self.logs_page),
            ("Clipboard", self.clipboard_page),
        )
        self.activity_subtabs = self.activity_group_page.findChild(
            QTabWidget, "HubSubTabs"
        )
        self.system_page = self._build_system()
        self.notes_page = self._build_notes()
        self.browser_page = self._build_browser()
        self.media_page = self._build_media()
        self.desktop_page = self._build_desktop()
        self.platform_page = self._build_platform()
        self.tools_page = self._group_tabs(
            ("System", self.system_page),
            ("Notes", self.notes_page),
            ("Browser", self.browser_page),
            ("Media", self.media_page),
            ("Desktop", self.desktop_page),
        )
        self.tools_subtabs = self.tools_page.findChild(QTabWidget, "HubSubTabs")
        for name, page in zip(
            self.TAB_NAMES,
            (
                self.dashboard_page,
                self.files_page,
                self.activity_group_page,
                self.platform_page,
                self.tools_page,
            ),
        ):
            self.tabs.addTab(page, name)
        self._plugin_pages: list[QWidget] = []

        root.addLayout(header)
        root.addWidget(self.tabs, stretch=1)

    def set_plugin_panels(
        self,
        contributions: Iterable[dict[str, Any]],
        callback: Callable[[dict[str, Any]], None],
    ) -> None:
        for page in self._plugin_pages:
            index = self.tabs.indexOf(page)
            if index >= 0:
                self.tabs.removeTab(index)
            page.deleteLater()
        self._plugin_pages.clear()
        for contribution in tuple(contributions)[:12]:
            page, layout = self._page()
            title = QLabel(str(contribution.get("title", "Plugin panel")))
            title.setObjectName("AssistantHubTitle")
            detail = QLabel(
                f"Provided by {contribution.get('pluginId', 'plugin')} through the "
                "MORICE declarative UI bridge."
            )
            detail.setWordWrap(True)
            action = QPushButton("Open")
            action.clicked.connect(
                lambda _checked=False, item=dict(contribution): callback(item)
            )
            layout.addWidget(title)
            layout.addWidget(detail)
            layout.addWidget(action, alignment=Qt.AlignLeft)
            layout.addStretch(1)
            self.tabs.addTab(page, str(contribution.get("title", "Plugin"))[:24])
            self._plugin_pages.append(page)

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(8)
        return page, layout

    def _group_tabs(self, *pages: tuple[str, QWidget]) -> QWidget:
        page, layout = self._page()
        tabs = QTabWidget()
        tabs.setObjectName("HubSubTabs")
        tabs.setDocumentMode(True)
        for name, child in pages:
            tabs.addTab(child, name)
        layout.addWidget(tabs, stretch=1)
        return page

    def _button(self, text: str, command: str, argument: object = None) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("WorkspaceAction")
        button.clicked.connect(lambda: self.command_requested.emit(command, argument))
        return button

    def _build_dashboard(self) -> QWidget:
        page, layout = self._page()
        title = QLabel("Today in MORICE")
        title.setObjectName("DashboardTitle")
        self.dashboard_summary = QLabel(
            "Resume a conversation, inspect local files, or open a focused system tool."
        )
        self.dashboard_summary.setObjectName("DashboardDetail")
        self.dashboard_summary.setWordWrap(True)
        quick = QHBoxLayout()
        quick.addWidget(self._button("New chat", "new-chat"))
        quick.addWidget(self._button("Open file", "open-file"))
        quick.addWidget(self._button("System", "system"))
        self.recent_chats = QListWidget()
        self.recent_chats.setObjectName("WorkspaceRecentChats")
        self.recent_chats.itemActivated.connect(
            lambda item: self.command_requested.emit("resume-chat", item.text())
        )
        self.recent_files = QListWidget()
        self.recent_files.setObjectName("WorkspaceRecentFiles")
        self.recent_files.itemActivated.connect(
            lambda item: self.command_requested.emit("preview-file", item.data(Qt.UserRole))
        )
        layout.addWidget(title)
        layout.addWidget(self.dashboard_summary)
        layout.addLayout(quick)
        layout.addWidget(QLabel("Recent chats"))
        layout.addWidget(self.recent_chats, stretch=1)
        layout.addWidget(QLabel("Recent files"))
        layout.addWidget(self.recent_files, stretch=1)
        return page

    def _build_files(self) -> QWidget:
        page, layout = self._page()
        controls = QHBoxLayout()
        self.file_query = QLineEdit()
        self.file_query.setObjectName("WorkspaceSearch")
        self.file_query.setPlaceholderText("Find files by name...")
        self.file_query.returnPressed.connect(self._find_files)
        controls.addWidget(self.file_query, stretch=1)
        controls.addWidget(self._button("Find", "find-files-from-hub"))
        controls.addWidget(self._button("Open", "open-file"))
        self.file_results = QListWidget()
        self.file_results.setObjectName("WorkspaceFileResults")
        self.file_results.itemActivated.connect(self._preview_result)
        self.file_preview = FilePreview()
        self.file_preview.open_external_requested.connect(
            lambda path: self.command_requested.emit("open-path", path)
        )
        layout.addLayout(controls)
        layout.addWidget(self.file_results, stretch=1)
        layout.addWidget(self.file_preview, stretch=3)
        return page

    def _build_activity(self) -> QWidget:
        page, layout = self._page()
        self.activity_list = QListWidget()
        self.activity_list.setObjectName("WorkspaceActivity")
        clear = self._button("Clear activity", "clear-activity")
        layout.addWidget(self.activity_list, stretch=1)
        layout.addWidget(clear)
        return page

    def _build_tasks(self) -> QWidget:
        page, layout = self._page()
        self.task_summary = QLabel("No active tasks.")
        self.task_summary.setObjectName("DashboardDetail")
        self.task_summary.setWordWrap(True)
        self.task_list = QListWidget()
        self.task_list.setObjectName("WorkspaceTasks")
        layout.addWidget(self.task_summary)
        layout.addWidget(self.task_list, stretch=1)
        return page

    def _build_logs(self) -> QWidget:
        page, layout = self._page()
        self.live_logs = QPlainTextEdit()
        self.live_logs.setObjectName("WorkspaceLogViewer")
        self.live_logs.setReadOnly(True)
        self.live_logs.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.live_logs, stretch=1)
        return page

    def _build_clipboard(self) -> QWidget:
        page, layout = self._page()
        note = QLabel(
            "Clipboard history stays in memory for this MORICE session. "
            "Activate an item to copy it again."
        )
        note.setObjectName("DashboardDetail")
        note.setWordWrap(True)
        self.clipboard_list = QListWidget()
        self.clipboard_list.setObjectName("WorkspaceClipboard")
        self.clipboard_list.itemActivated.connect(
            lambda item: self.command_requested.emit(
                "restore-clipboard", item.data(Qt.UserRole)
            )
        )
        controls = QHBoxLayout()
        self.clipboard_status = QLabel("Monitoring is off.")
        self.clipboard_status.setObjectName("DashboardDetail")
        self.clipboard_monitor_button = self._button(
            "Enable for session", "clipboard-monitor"
        )
        controls.addWidget(self.clipboard_status, stretch=1)
        controls.addWidget(self.clipboard_monitor_button)
        layout.addWidget(note)
        layout.addLayout(controls)
        layout.addWidget(self.clipboard_list, stretch=1)
        return page

    def _build_system(self) -> QWidget:
        page, layout = self._page()
        self.system_summary = QLabel("Select Refresh to inspect this PC.")
        self.system_summary.setObjectName("DashboardDetail")
        self.system_summary.setWordWrap(True)
        self.system_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        actions = QHBoxLayout()
        actions.addWidget(self._button("Refresh", "system"))
        actions.addWidget(self._button("Diagnostics", "diagnostics"))
        actions.addWidget(self._button("Screenshot", "screenshot"))
        actions.addWidget(self._button("Downloads", "open-downloads"))
        layout.addWidget(self.system_summary)
        layout.addStretch(1)
        layout.addLayout(actions)
        return page

    def _build_platform(self) -> QWidget:
        page, layout = self._page()
        title = QLabel("Autonomous platform")
        title.setObjectName("DashboardTitle")
        self.platform_summary = QLabel(
            "Unified orchestration, project intelligence, knowledge, Git, "
            "updates, backup, and release state."
        )
        self.platform_summary.setObjectName("DashboardDetail")
        self.platform_summary.setWordWrap(True)
        self.platform_project = QPlainTextEdit()
        self.platform_project.setObjectName("WorkspaceLogViewer")
        self.platform_project.setReadOnly(True)
        self.platform_project.setPlaceholderText(
            "Select a Project Mode work folder to populate its dashboard."
        )
        self.platform_runs = QListWidget()
        self.platform_runs.setObjectName("WorkspaceTasks")
        self.platform_knowledge = QLabel("Knowledge graph is loading.")
        self.platform_knowledge.setObjectName("DashboardDetail")
        self.platform_knowledge.setWordWrap(True)
        self.platform_release = QLabel("Release readiness has not been checked.")
        self.platform_release.setObjectName("DashboardDetail")
        self.platform_release.setWordWrap(True)
        actions = QHBoxLayout()
        actions.addWidget(self._button("Refresh", "platform-refresh"))
        actions.addWidget(self._button("Export", "platform-export"))
        actions.addWidget(self._button("Hardware", "platform-first-run"))
        actions.addWidget(self._button("Release check", "platform-release-check"))
        layout.addWidget(title)
        layout.addWidget(self.platform_summary)
        layout.addWidget(QLabel("Project overview"))
        layout.addWidget(self.platform_project, stretch=2)
        layout.addWidget(QLabel("Recent autonomous runs"))
        layout.addWidget(self.platform_runs, stretch=1)
        layout.addWidget(self.platform_knowledge)
        layout.addWidget(self.platform_release)
        layout.addLayout(actions)
        return page

    def _build_downloads(self) -> QWidget:
        page, layout = self._page()
        controls = QHBoxLayout()
        controls.addWidget(self._button("Refresh", "refresh-downloads"))
        controls.addWidget(self._button("Open folder", "open-downloads"))
        self.downloads = QListWidget()
        self.downloads.setObjectName("WorkspaceDownloads")
        self.downloads.itemActivated.connect(
            lambda item: self.command_requested.emit(
                "preview-file", item.data(Qt.UserRole)
            )
        )
        layout.addLayout(controls)
        layout.addWidget(self.downloads, stretch=1)
        return page

    def _build_notes(self) -> QWidget:
        page, layout = self._page()
        self.notes = QPlainTextEdit()
        self.notes.setObjectName("WorkspaceNotes")
        self.notes.setPlaceholderText("Persistent local notes...")
        self.notes.textChanged.connect(self._schedule_notes)
        self.notes_timer = QTimer(self)
        self.notes_timer.setSingleShot(True)
        self.notes_timer.setInterval(450)
        self.notes_timer.timeout.connect(lambda: self.notes_changed.emit(self.notes.toPlainText()))
        layout.addWidget(self.notes, stretch=1)
        layout.addWidget(QLabel("Saved locally after you stop typing."))
        return page

    def _build_browser(self) -> QWidget:
        page, layout = self._page()
        controls = QHBoxLayout()
        self.browser_address = QLineEdit()
        self.browser_address.setObjectName("WorkspaceSearch")
        self.browser_address.setPlaceholderText("https://example.com")
        self.browser_address.returnPressed.connect(self._navigate)
        controls.addWidget(self.browser_address, stretch=1)
        controls.addWidget(self._button("Go", "browser-go"))
        if QWebEngineView is not None:
            self.browser_view = QWebEngineView()
            self.browser_view.setObjectName("WorkspaceBrowser")
            self.browser_view.urlChanged.connect(
                lambda url: self.browser_address.setText(url.toString())
            )
            layout.addLayout(controls)
            layout.addWidget(self.browser_view, stretch=1)
        else:
            self.browser_view = None
            notice = QLabel(
                "The embedded browser is unavailable in this PySide build. "
                "Addresses can still open in your default browser."
            )
            notice.setWordWrap(True)
            layout.addLayout(controls)
            layout.addWidget(notice)
            layout.addStretch(1)
        return page

    def _build_media(self) -> QWidget:
        page, layout = self._page()
        title = QLabel("Local media")
        title.setObjectName("DashboardTitle")
        local_controls = QHBoxLayout()
        local_controls.addWidget(self._button("Open media", "open-media"))
        self.local_play_button = QPushButton("Play")
        self.local_play_button.setObjectName("WorkspaceAction")
        self.local_play_button.clicked.connect(self._toggle_local_media)
        self.local_play_button.setEnabled(False)
        local_controls.addWidget(self.local_play_button)
        self.local_media_status = QLabel("No local media selected.")
        self.local_media_status.setObjectName("DashboardDetail")
        self.local_media_status.setWordWrap(True)
        if QMediaPlayer is not None and QAudioOutput is not None:
            self.media_player = QMediaPlayer(self)
            self.media_audio = QAudioOutput(self)
            self.media_player.setAudioOutput(self.media_audio)
            self.media_audio.setVolume(0.72)
            self.media_player.mediaStatusChanged.connect(
                lambda _status: self._refresh_local_media_status()
            )
            self.media_player.playbackStateChanged.connect(
                lambda _state: self._refresh_local_media_status()
            )
        else:
            self.media_player = None
            self.media_audio = None
            self.local_media_status.setText(
                "Local Qt multimedia playback is unavailable in this installation."
            )
        if self.media_player is not None and QVideoWidget is not None:
            self.video_widget = QVideoWidget()
            self.video_widget.setObjectName("WorkspaceVideo")
            self.video_widget.setMinimumHeight(180)
            self.media_player.setVideoOutput(self.video_widget)
        else:
            self.video_widget = None

        system_title = QLabel("System media controls")
        system_title.setObjectName("DashboardTitle")
        controls = QHBoxLayout()
        controls.addWidget(self._button("Previous", "media", "previous"))
        controls.addWidget(self._button("Play / Pause", "media", "play-pause"))
        controls.addWidget(self._button("Next", "media", "next"))
        volume = QHBoxLayout()
        volume.addWidget(self._button("Volume down", "media", "volume-down"))
        volume.addWidget(self._button("Mute", "media", "mute"))
        volume.addWidget(self._button("Volume up", "media", "volume-up"))
        layout.addWidget(title)
        layout.addLayout(local_controls)
        layout.addWidget(self.local_media_status)
        if self.video_widget is not None:
            layout.addWidget(self.video_widget, stretch=1)
        layout.addWidget(system_title)
        layout.addLayout(controls)
        layout.addLayout(volume)
        layout.addStretch(1)
        return page

    def _build_desktop(self) -> QWidget:
        page, layout = self._page()
        controls = QHBoxLayout()
        controls.addWidget(self._button("Refresh", "desktop-refresh"))
        self.memory_toggle_button = self._button("Disable memory", "memory-toggle")
        controls.addWidget(self.memory_toggle_button)
        controls.addWidget(self._button("Export memory", "memory-export"))
        controls.addWidget(self._button("Import memory", "memory-import"))
        self.desktop_status = QLabel("Desktop services are loading.")
        self.desktop_status.setObjectName("DashboardDetail")
        self.desktop_status.setWordWrap(True)

        self.notification_list = QListWidget()
        self.notification_list.setObjectName("WorkspaceNotifications")
        self.notification_list.itemActivated.connect(
            lambda item: self.command_requested.emit(
                "notification-dismiss", item.data(Qt.UserRole)
            )
        )
        self.memory_list = QListWidget()
        self.memory_list.setObjectName("WorkspaceMemory")
        self.memory_list.itemActivated.connect(
            lambda item: self.command_requested.emit(
                "inspect-memory", {"memoryId": item.data(Qt.UserRole)}
            )
        )
        memory_actions = QHBoxLayout()
        memory_actions.addWidget(
            self._button("Pin", "memory-pin-selected")
        )
        memory_actions.addWidget(
            self._button("Archive", "memory-archive-selected")
        )
        memory_actions.addWidget(
            self._button("Delete", "memory-delete-selected")
        )
        self.automation_list = QListWidget()
        self.automation_list.setObjectName("WorkspaceAutomations")
        automation_actions = QHBoxLayout()
        automation_actions.addWidget(
            self._button("Enable", "automation-enable-selected")
        )
        automation_actions.addWidget(
            self._button("Disable", "automation-disable-selected")
        )

        layout.addLayout(controls)
        layout.addWidget(self.desktop_status)
        layout.addWidget(QLabel("Notifications (activate to dismiss)"))
        layout.addWidget(self.notification_list, stretch=1)
        layout.addWidget(QLabel("Structured memory"))
        layout.addWidget(self.memory_list, stretch=1)
        layout.addLayout(memory_actions)
        layout.addWidget(QLabel("Automations"))
        layout.addWidget(self.automation_list, stretch=1)
        layout.addLayout(automation_actions)
        return page

    def open_media(self, path: str) -> tuple[bool, str]:
        target = os.path.abspath(os.path.expanduser(path))
        if self.media_player is None:
            return False, "Qt multimedia playback is unavailable."
        if not os.path.isfile(target) or Path(target).suffix.lower() not in MEDIA_EXTENSIONS:
            return False, "Select a supported local audio or video file."
        self.media_player.setSource(QUrl.fromLocalFile(target))
        self.local_media_status.setText(target)
        self.local_play_button.setEnabled(True)
        self.show_tab("Media")
        self.media_player.play()
        return True, f"Playing {Path(target).name}."

    def _toggle_local_media(self) -> None:
        if self.media_player is None:
            return
        if (
            self.media_player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.media_player.pause()
        else:
            self.media_player.play()

    def _refresh_local_media_status(self) -> None:
        if self.media_player is None:
            return
        playing = (
            self.media_player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        )
        self.local_play_button.setText("Pause" if playing else "Play")
        source = self.media_player.source().toLocalFile()
        if source:
            state = "Playing" if playing else "Paused"
            self.local_media_status.setText(f"{state}: {source}")

    def _schedule_notes(self) -> None:
        self.notes_timer.start()

    def _search(self) -> None:
        query = self.search.text().strip()
        if query:
            self.show_tab("Files")
            self.file_query.setText(query)
            self.command_requested.emit("search-everywhere", query)

    def _find_files(self) -> None:
        query = self.file_query.text().strip()
        if query:
            self.command_requested.emit("find-files", query)

    def _preview_result(self, item: QListWidgetItem) -> None:
        value = item.data(Qt.UserRole)
        if isinstance(value, dict):
            self.command_requested.emit(str(value.get("action", "")), value)
            return
        path = str(value or item.text())
        self.command_requested.emit("preview-file", path)

    def _navigate(self) -> None:
        address = self.browser_address.text().strip()
        if address:
            self.command_requested.emit("browser-navigate", address)

    def set_notes(self, text: str) -> None:
        self.notes.blockSignals(True)
        self.notes.setPlainText(text)
        self.notes.blockSignals(False)

    def set_recent(self, chats: Iterable[str], files: Iterable[str]) -> None:
        self.recent_chats.clear()
        for chat in chats:
            self.recent_chats.addItem(str(chat))
        self.recent_files.clear()
        for path in files:
            item = QListWidgetItem(Path(path).name or path)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.recent_files.addItem(item)

    def set_activity(self, entries: Iterable[Any]) -> None:
        self.activity_list.clear()
        log_lines: list[str] = []
        for entry in reversed(tuple(entries)):
            title = str(getattr(entry, "title", "") or "")
            detail = str(getattr(entry, "detail", "") or "")
            timestamp = str(getattr(entry, "timestamp", "") or "")
            label = title
            if detail:
                label += f"\n{detail}"
            if timestamp:
                label += f"\n{timestamp.replace('T', ' ')[:19]}"
            item = QListWidgetItem(label)
            item.setToolTip(detail)
            self.activity_list.addItem(item)
            log_lines.append(
                f"{timestamp.replace('T', ' ')[:19]}  {title}"
                + (f"  |  {detail}" if detail else "")
            )
        self.live_logs.setPlainText("\n".join(reversed(log_lines)))

    def set_tasks(self, tasks: Iterable[str], busy: bool = False) -> None:
        values = [str(task).strip() for task in tasks if str(task).strip()]
        self.task_list.clear()
        for task in values:
            self.task_list.addItem(task)
        active = len(values)
        if busy:
            self.task_summary.setText(
                f"MORICE is processing. {active} queued follow-up(s)."
            )
        elif active:
            self.task_summary.setText(f"{active} queued follow-up(s).")
        else:
            self.task_summary.setText("No active tasks.")

    def set_downloads(self, paths: Iterable[str]) -> None:
        self.downloads.clear()
        for path in paths:
            item = QListWidgetItem(Path(path).name or path)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.downloads.addItem(item)
        if not self.downloads.count():
            self.downloads.addItem("No downloaded files found.")

    def set_clipboard_history(self, values: Iterable[str]) -> None:
        self.clipboard_list.clear()
        for value in values:
            preview = " ".join(str(value).split())
            item = QListWidgetItem(
                preview[:180] + ("..." if len(preview) > 180 else "")
            )
            item.setData(Qt.UserRole, str(value))
            item.setToolTip(str(value)[:1000])
            self.clipboard_list.addItem(item)
        if not self.clipboard_list.count():
            self.clipboard_list.addItem("No text copied during this session.")

    def set_clipboard_status(self, enabled: bool) -> None:
        self.clipboard_status.setText(
            "Monitoring is on for this session." if enabled else "Monitoring is off."
        )
        self.clipboard_monitor_button.setText(
            "Disable" if enabled else "Enable for session"
        )

    def set_file_results(self, paths: Iterable[str]) -> None:
        self.file_results.clear()
        for path in paths:
            item = QListWidgetItem(Path(path).name or path)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.file_results.addItem(item)
        if not self.file_results.count():
            self.file_results.addItem("No matching files found.")

    def set_search_results(self, results: Iterable[Any]) -> None:
        self.file_results.clear()
        for result in results:
            category = str(getattr(result, "category", "") or "result")
            label = str(getattr(result, "label", "") or "Result")
            detail = str(getattr(result, "detail", "") or "")
            action = str(getattr(result, "action", "") or "")
            metadata = dict(getattr(result, "metadata", {}) or {})
            item = QListWidgetItem(f"{label}\n{category.title()} | {detail}")
            item.setData(
                Qt.UserRole,
                {"action": action, "category": category, **metadata},
            )
            item.setToolTip(detail)
            self.file_results.addItem(item)
        if not self.file_results.count():
            self.file_results.addItem("No matching files, projects, memory, or commands found.")

    def preview_file(self, path: str) -> tuple[bool, str]:
        self.show_tab("Files")
        return self.file_preview.show_file(path)

    def set_system_snapshot(self, snapshot: Any, gpu: str = "") -> None:
        battery = "Unavailable"
        if getattr(snapshot, "battery_percent", None) is not None:
            suffix = ", charging" if getattr(snapshot, "battery_charging", False) else ""
            battery = f"{snapshot.battery_percent}%{suffix}"
        summary = (
            f"OS: {snapshot.operating_system}\n"
            f"CPU: {snapshot.cpu} ({snapshot.cpu_threads} threads)\n"
        )
        if gpu:
            summary += f"GPU: {gpu}\n"
        summary += (
            f"Memory: {snapshot.memory_available_gb:.1f} GB available / "
            f"{snapshot.memory_total_gb:.1f} GB total\n"
            f"Storage: {snapshot.storage_free_gb:.1f} GB free / "
            f"{snapshot.storage_total_gb:.1f} GB total\n"
            f"Battery: {battery}\n"
            f"Device: {snapshot.hostname}\n"
            f"Local IP: {snapshot.local_ip}"
        )
        self.system_summary.setText(summary)

    def set_platform_state(self, snapshot: dict[str, Any]) -> None:
        orchestrator = dict(snapshot.get("orchestrator", {}))
        knowledge = dict(snapshot.get("knowledge", {}))
        project = dict(snapshot.get("project", {}))
        release = dict(snapshot.get("release", {}))
        updates = dict(snapshot.get("updates", {}))
        self.platform_summary.setText(
            f"{orchestrator.get('activeRuns', 0)} active run(s) | "
            f"{orchestrator.get('runCount', 0)} retained | "
            f"Update channel: {updates.get('channel', 'stable')}"
        )
        self.platform_runs.clear()
        for run in orchestrator.get("recentRuns", ())[:50]:
            if not isinstance(run, dict):
                continue
            item = QListWidgetItem(
                f"{str(run.get('state', 'unknown')).replace('_', ' ').title()} "
                f"{run.get('progress', 0)}% | {str(run.get('request', ''))[:100]}"
            )
            item.setToolTip(str(run.get("request", "")))
            self.platform_runs.addItem(item)
        if self.platform_runs.count() == 0:
            self.platform_runs.addItem("No autonomous runs in this session.")
        if project:
            overview = dict(project.get("overview", {}))
            architecture = dict(project.get("architecture", {}))
            git = dict(project.get("git", {}))
            self.platform_project.setPlainText(
                "\n".join(
                    (
                        f"Project: {project.get('name', '')}",
                        f"Root: {project.get('root', '')}",
                        f"Files: {overview.get('files', 0)}",
                        f"Languages: {overview.get('languages', {})}",
                        f"Frameworks: {architecture.get('frameworks', ())}",
                        f"Build systems: {architecture.get('buildSystems', ())}",
                        f"Entry points: {architecture.get('entryPoints', ())}",
                        f"Dependencies: {len(project.get('dependencies', ()))}",
                        f"Issues: {len(project.get('issues', ()))}",
                        f"Git branch: {git.get('branch', 'not a repository')}",
                        f"Git dirty: {git.get('dirty', False)}",
                        f"Build: {project.get('build_status', 'unknown')}",
                        f"Renderer: {project.get('renderer_status', 'idle')}",
                    )
                )
            )
        else:
            self.platform_project.clear()
            self.platform_project.setPlaceholderText(
                str(snapshot.get("projectError", ""))
                or "Select a Project Mode work folder to populate its dashboard."
            )
        self.platform_knowledge.setText(
            f"Knowledge: {knowledge.get('nodes', 0)} nodes, "
            f"{knowledge.get('edges', 0)} relationships, "
            f"{knowledge.get('bytes', 0) / 1024:.1f} KB on disk."
        )
        critical = tuple(release.get("criticalFailures", ()))
        self.platform_release.setText(
            (
                "Release ready."
                if release.get("ready")
                else "Release pending: "
                + (
                    ", ".join(str(item) for item in critical)
                    if critical
                    else "automated tests must be recorded"
                )
            )
        )

    def selected_memory_id(self) -> str:
        item = self.memory_list.currentItem()
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def selected_automation_id(self) -> str:
        item = self.automation_list.currentItem()
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def set_desktop_state(
        self,
        snapshot: dict[str, Any],
        notifications: Iterable[Any],
        memories: Iterable[Any],
        automations: Iterable[Any],
    ) -> None:
        clipboard = dict(snapshot.get("clipboard", {}))
        memory = dict(snapshot.get("memory", {}))
        automation = dict(snapshot.get("automations", {}))
        self.desktop_status.setText(
            f"Permissions waiting: {snapshot.get('permissionRequests', 0)} | "
            f"Clipboard: {'on' if clipboard.get('enabled') else 'off'} | "
            f"Projects: {snapshot.get('projects', 0)} | "
            f"Attachments: {snapshot.get('attachments', 0)} | "
            f"Memory records: {memory.get('records', 0)} | "
            f"Automations: {automation.get('enabled', 0)}/{automation.get('total', 0)} enabled"
        )
        self.memory_toggle_button.setText(
            "Disable memory" if memory.get("enabled", True) else "Enable memory"
        )
        self.notification_list.clear()
        for item in notifications:
            label = (
                f"{getattr(item, 'severity', 'info').upper()} | "
                f"{getattr(item, 'title', 'MORICE')}\n"
                f"{getattr(item, 'message', '')}"
            )
            widget_item = QListWidgetItem(label)
            widget_item.setData(Qt.UserRole, getattr(item, "notification_id", ""))
            self.notification_list.addItem(widget_item)
        if not self.notification_list.count():
            self.notification_list.addItem("No notifications.")

        self.memory_list.clear()
        for item in memories:
            content = " ".join(str(getattr(item, "content", "")).split())
            label = (
                f"{getattr(item, 'scope', 'memory').title()} | "
                f"{'Pinned | ' if getattr(item, 'pinned', False) else ''}"
                f"{content[:180]}"
            )
            widget_item = QListWidgetItem(label)
            widget_item.setData(Qt.UserRole, getattr(item, "memory_id", ""))
            self.memory_list.addItem(widget_item)
        if not self.memory_list.count():
            self.memory_list.addItem("No stored memory.")

        self.automation_list.clear()
        for item in automations:
            label = (
                f"{'Enabled' if getattr(item, 'enabled', False) else 'Disabled'} | "
                f"{getattr(item, 'name', 'Automation')}\n"
                f"{getattr(item, 'event', '')} -> {getattr(item, 'action', '')}"
            )
            widget_item = QListWidgetItem(label)
            widget_item.setData(Qt.UserRole, getattr(item, "workflow_id", ""))
            self.automation_list.addItem(widget_item)
        if not self.automation_list.count():
            self.automation_list.addItem("No automations configured.")

    def show_tab(self, name: str) -> None:
        tool_names = ("System", "Notes", "Browser", "Media", "Desktop")
        if name in tool_names:
            self.tabs.setCurrentIndex(self.TAB_NAMES.index("Tools"))
            if self.tools_subtabs is not None:
                self.tools_subtabs.setCurrentIndex(tool_names.index(name))
            return
        try:
            index = self.TAB_NAMES.index(name)
        except ValueError:
            index = 0
        self.tabs.setCurrentIndex(index)

    def navigate_browser(self, address: str) -> None:
        value = address.strip()
        if not value:
            return
        if "://" not in value:
            value = f"https://{value}"
        self.browser_address.setText(value)
        self.show_tab("Browser")
        if self.browser_view is not None:
            self.browser_view.setUrl(QUrl(value))
        else:
            QDesktopServices.openUrl(QUrl(value))


class NotificationToast(QFrame):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("NotificationToast")
        self.setProperty("severity", "info")
        self.setMinimumWidth(320)
        self.setMaximumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        message_row = QHBoxLayout()
        message_row.setSpacing(8)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(220)
        message_row.addWidget(self.label, stretch=1)
        self.action_button = QPushButton()
        self.action_button.setObjectName("WorkspaceAction")
        self.action_button.hide()
        self.action_button.clicked.connect(self._run_action)
        message_row.addWidget(self.action_button)
        self.copy_button = QPushButton("Copy")
        self.copy_button.setObjectName("WorkspaceAction")
        self.copy_button.setToolTip("Copy notification details")
        self.copy_button.setAccessibleName("Copy notification details")
        self.copy_button.clicked.connect(self._copy_details)
        self.copy_button.hide()
        message_row.addWidget(self.copy_button)
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("WorkspaceCloseButton")
        self.close_button.clicked.connect(self.hide)
        message_row.addWidget(self.close_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addLayout(message_row)
        layout.addWidget(self.progress)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self._details = ""
        self._action_callback: Callable[[], None] | None = None
        self.hide()

    def show_message(
        self,
        message: str,
        severity: str = "info",
        timeout_ms: int = 4200,
        *,
        action_text: str = "",
        action_callback: Callable[[], None] | None = None,
        progress: int | None = None,
        details: str = "",
    ) -> None:
        self.label.setText(message)
        clean_severity = (
            severity
            if severity in {"info", "success", "warning", "error"}
            else "info"
        )
        self.setProperty("severity", clean_severity)
        self._details = str(details or message)
        self._action_callback = action_callback
        if action_text and action_callback is not None:
            self.action_button.setText(action_text)
            self.action_button.show()
        else:
            self.action_button.hide()
        self.copy_button.setVisible(clean_severity == "error")
        if progress is None:
            self.progress.hide()
        else:
            self.progress.setValue(max(0, min(100, int(progress))))
            self.progress.show()
        self.style().unpolish(self)
        self.style().polish(self)
        parent = self.parentWidget()
        if parent is not None:
            target_width = max(320, min(420, parent.width() - 56))
            self.setFixedWidth(target_width)
            self.adjustSize()
            margin = 28
            self.move(max(margin, parent.width() - self.width() - margin), margin)
            self.raise_()
        self.show()
        if timeout_ms > 0:
            self.timer.start(timeout_ms)

    def _copy_details(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._details)

    def _run_action(self) -> None:
        callback = self._action_callback
        if callback is not None:
            callback()
        self.hide()


def install_command_shortcut(parent: QWidget, palette: CommandPalette) -> QShortcut:
    shortcut = QShortcut(QKeySequence("Ctrl+K"), parent)
    shortcut.setContext(Qt.WindowShortcut)
    callback = getattr(parent, "open_command_palette", palette.open_palette)
    shortcut.activated.connect(callback)
    return shortcut
