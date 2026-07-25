from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PySide6.QtCore import QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
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
    CommandItem("system", "System status", "CPU, memory, storage, battery", "hardware"),
    CommandItem("screenshot", "Capture screenshot", "Save the current display", "screen"),
    CommandItem("theme", "Toggle light or dark theme", "Change appearance", "color"),
    CommandItem("accent", "Choose accent color", "Personalize the workspace", "theme"),
    CommandItem("notes", "Open notes", "Persistent scratch notes", "write"),
    CommandItem("browser", "Open browser", "Browse without leaving MORICE", "web"),
    CommandItem("media", "Open media controls", "Playback and volume", "music"),
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

    def _filter(self, value: str) -> None:
        terms = [part for part in value.lower().split() if part]
        self.results.clear()
        for command in self.commands:
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

    def _open_external(self) -> None:
        if self.current_path:
            self.open_external_requested.emit(self.current_path)


class AssistantHub(QFrame):
    command_requested = Signal(str, object)
    notes_changed = Signal(str)
    visibility_requested = Signal(bool)

    TAB_NAMES = ("Dashboard", "Files", "Activity", "Tools")

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
        self.tools_page = self._group_tabs(
            ("System", self.system_page),
            ("Notes", self.notes_page),
            ("Browser", self.browser_page),
            ("Media", self.media_page),
        )
        self.tools_subtabs = self.tools_page.findChild(QTabWidget, "HubSubTabs")
        for name, page in zip(
            self.TAB_NAMES,
            (
                self.dashboard_page,
                self.files_page,
                self.activity_group_page,
                self.tools_page,
            ),
        ):
            self.tabs.addTab(page, name)

        root.addLayout(header)
        root.addWidget(self.tabs, stretch=1)

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
        layout.addWidget(note)
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
        actions.addWidget(self._button("Screenshot", "screenshot"))
        actions.addWidget(self._button("Downloads", "open-downloads"))
        layout.addWidget(self.system_summary)
        layout.addStretch(1)
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
            self.command_requested.emit("find-files", query)

    def _find_files(self) -> None:
        query = self.file_query.text().strip()
        if query:
            self.command_requested.emit("find-files", query)

    def _preview_result(self, item: QListWidgetItem) -> None:
        path = str(item.data(Qt.UserRole) or item.text())
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

    def set_file_results(self, paths: Iterable[str]) -> None:
        self.file_results.clear()
        for path in paths:
            item = QListWidgetItem(Path(path).name or path)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.file_results.addItem(item)
        if not self.file_results.count():
            self.file_results.addItem("No matching files found.")

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

    def show_tab(self, name: str) -> None:
        if name in {"System", "Notes", "Browser", "Media"}:
            self.tabs.setCurrentIndex(self.TAB_NAMES.index("Tools"))
            if self.tools_subtabs is not None:
                self.tools_subtabs.setCurrentIndex(
                    ("System", "Notes", "Browser", "Media").index(name)
                )
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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(220)
        layout.addWidget(self.label, stretch=1)
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("WorkspaceCloseButton")
        self.close_button.clicked.connect(self.hide)
        layout.addWidget(self.close_button)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, message: str, severity: str = "info", timeout_ms: int = 4200) -> None:
        self.label.setText(message)
        self.setProperty("severity", severity if severity in {"info", "success", "error"} else "info")
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


def install_command_shortcut(parent: QWidget, palette: CommandPalette) -> QShortcut:
    shortcut = QShortcut(QKeySequence("Ctrl+K"), parent)
    shortcut.setContext(Qt.WindowShortcut)
    shortcut.activated.connect(palette.open_palette)
    return shortcut
