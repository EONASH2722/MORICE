"""Compact history dialog; transcripts are loaded only when Open is chosen."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)


class ChatHistoryDialog(QDialog):
    def __init__(self, history, open_chat, parent=None):
        super().__init__(parent)
        self.history, self.open_chat = history, open_chat
        self.setWindowTitle("Chat history")
        self.resize(650, 570)
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search chat names…")
        layout.addWidget(self.query)
        self.chats = QListWidget()
        layout.addWidget(self.chats)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name this chat")
        layout.addWidget(self.name)
        self.retention = QComboBox()
        for label, value in (("Never delete", "never"), ("Delete after 10 days inactivity", "10_days"),
                             ("Delete after 30 days inactivity", "month"), ("Delete when this chat session ends", "session")):
            self.retention.addItem(label, value)
        layout.addWidget(self.retention)
        self.protected = QCheckBox("Protect: never automatically delete this chat")
        layout.addWidget(self.protected)
        note = QLabel("Retention deletes only the chat. Research projects and evidence remain stored. Opening a chat resets inactivity.")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        for label, callback in (("Open", self.open_selected), ("Save name/settings", self.save), ("Archive", self.archive), ("Delete", self.delete)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.query.textChanged.connect(self.refresh)
        self.chats.currentItemChanged.connect(self.select)
        self.chats.itemDoubleClicked.connect(lambda _: self.open_selected())
        self.refresh()

    def refresh(self):
        self.chats.clear()
        for chat in self.history.search(self.query.text()):
            item = QListWidgetItem(f"{chat['name']} {'[Archived]' if chat['archived'] else ''}\n{chat['preview'][:130]}")
            item.setData(Qt.UserRole, chat)
            self.chats.addItem(item)

    def selected(self):
        item = self.chats.currentItem()
        return item.data(Qt.UserRole) if item else None

    def select(self, *_args):
        chat = self.selected()
        if chat:
            self.name.setText(chat["name"])
            self.retention.setCurrentIndex(max(0, self.retention.findData(chat["retention"])))
            self.protected.setChecked(bool(chat["protected"]))

    def open_selected(self):
        chat = self.selected()
        if chat:
            try:
                self.open_chat(chat["id"])
            except Exception as exc:
                QMessageBox.warning(self, "Could not restore chat", str(exc))
                return
            self.accept()

    def save(self):
        chat = self.selected()
        if chat:
            try:
                self.history.configure(chat["id"], self.name.text(), self.retention.currentData(), self.protected.isChecked())
            except ValueError as exc:
                QMessageBox.warning(self, "Chat settings", str(exc))
                return
            self.refresh()

    def archive(self):
        chat = self.selected()
        if chat:
            self.history.archive(chat["id"])
            self.refresh()

    def delete(self):
        chat = self.selected()
        if chat and QMessageBox.question(self, "Delete chat?", "Permanently delete this chat? Research projects and evidence will remain.") == QMessageBox.Yes:
            self.history.delete(chat["id"])
            parent = self.parent()
            if getattr(parent, "_chat_id", None) == chat["id"]:
                # Do not resurrect an explicitly deleted active transcript on autosave.
                parent._history_deleted_id = chat["id"]
            self.refresh()
