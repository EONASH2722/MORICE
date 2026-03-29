import os
import sys
import threading
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QTimer, Signal, QEvent
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QFrame,
    QGraphicsOpacityEffect,
    QFileDialog,
)

from .core import (
    MORICE_NAME,
    compute_math,
    enforce_father,
    shorten_reply,
    summon_response,
    is_acknowledgement,
    wants_help,
    help_text,
    father_identity_response,
    wants_first_message,
    wants_memory_list,
    wants_memory_search,
    extract_memory_terms,
    wants_precision_on,
    wants_precision_off,
    wants_math_steps_on,
    wants_math_steps_off,
    wants_steps_detail,
    extract_web_query,
    needs_web,
    wants_notes_search,
    extract_notes_term,
    wants_notes_summary,
    summarize_notes_hits,
    wants_unity_movement,
    wants_unity_2d,
    wants_unity_3d,
    unity_2d_movement_script,
    unity_3d_movement_script,
    wants_html_cube_movement,
    html_cube_movement_script,
    wake_up_response,
    riddle_response,
)
from .knowledge import KB_DIR, load_knowledge, retrieve_context, should_use_context, should_preload, search_notes
from .llm_client import chat
from .web_search import search_web
from .vision import describe_image


def _enable_acrylic(hwnd: int):
    accent = ctypes.Structure

    class ACCENTPOLICY(ctypes.Structure):
        _fields_ = [
            ("AccentState", ctypes.c_int),
            ("AccentFlags", ctypes.c_int),
            ("GradientColor", ctypes.c_int),
            ("AnimationId", ctypes.c_int),
        ]

    class WINCOMPATTRDATA(ctypes.Structure):
        _fields_ = [
            ("Attribute", ctypes.c_int),
            ("Data", ctypes.c_void_p),
            ("SizeOfData", ctypes.c_size_t),
        ]

    # ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
    accent_policy = ACCENTPOLICY(4, 0, 0xCC101010, 0)
    data = WINCOMPATTRDATA(19, ctypes.byref(accent_policy), ctypes.sizeof(accent_policy))
    user32 = ctypes.windll.user32
    set_window_comp_attr = user32.SetWindowCompositionAttribute
    set_window_comp_attr.argtypes = [wintypes.HWND, ctypes.POINTER(WINCOMPATTRDATA)]
    set_window_comp_attr.restype = ctypes.c_int
    set_window_comp_attr(hwnd, ctypes.byref(data))


def _icon_path() -> str:
    return os.path.join(os.path.dirname(__file__), "assets", "morice_logo.ico")


class ChatBubble(QFrame):
    def __init__(self, author: str, message: str, is_user: bool = False):
        super().__init__()
        self.setObjectName("ChatBubble")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        author_label = QLabel(author)
        author_label.setObjectName("AuthorLabel")
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setObjectName("MessageLabel")

        layout.addWidget(author_label)
        layout.addWidget(message_label)

        self.setProperty("user", "true" if is_user else "false")


class TitleBar(QFrame):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._parent = parent
        self._drag_active = False
        self._drag_pos = QPoint()

        self.setObjectName("TitleBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        title = QLabel(f"{MORICE_NAME}")
        title.setObjectName("TitleLabel")

        layout.addWidget(title)
        layout.addStretch(1)

        self.min_btn = QPushButton("_")
        self.min_btn.setObjectName("TitleButton")
        self.min_btn.clicked.connect(self._parent.showMinimized)

        self.max_btn = QPushButton("[]")
        self.max_btn.setObjectName("TitleButton")
        self.max_btn.clicked.connect(self._toggle_maximize)

        self.close_btn = QPushButton("X")
        self.close_btn.setObjectName("TitleClose")
        self.close_btn.clicked.connect(self._parent.close)

        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def _toggle_maximize(self):
        if self._parent.isMaximized():
            self._parent.showNormal()
        else:
            self._parent.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_active = True
            self._drag_pos = event.globalPosition().toPoint() - self._parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_active and event.buttons() & Qt.LeftButton:
            self._parent.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_active = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()
            event.accept()


class MoriceWindow(QWidget):
    message_ready = Signal(str, str, bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{MORICE_NAME} Glass Chat")
        self.resize(980, 640)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        icon_path = _icon_path()
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.history = []
        self.awake = False
        self.last_notes_hits = []
        self.last_notes_term = ""
        self.pending_image_path = ""
        self.precision_mode = True
        self.math_steps_mode = False
        self.user_scrolled = False
        self.first_user_message = ""
        self.user_messages: list[str] = []

        self.message_ready.connect(self.append_message)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)

        chat_container = QFrame()
        chat_container.setObjectName("ChatContainer")
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setFocusPolicy(Qt.StrongFocus)
        self.scroll.viewport().installEventFilter(self)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        chat_layout.addWidget(self.scroll)

        self.chat_list = QWidget()
        self.chat_list_layout = QVBoxLayout(self.chat_list)
        self.chat_list_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_list_layout.setSpacing(10)
        self.chat_list_layout.setAlignment(Qt.AlignTop)
        self.chat_list.setFocusPolicy(Qt.NoFocus)
        self.chat_list.installEventFilter(self)
        self.scroll.setWidget(self.chat_list)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_change)

        root.addWidget(chat_container, stretch=1)

        input_frame = QFrame()
        input_frame.setObjectName("InputFrame")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)
        input_layout.setSpacing(10)

        self.input = QLineEdit()
        self.input.setPlaceholderText("All Father: type here...")
        self.input.setObjectName("InputBox")
        self.input.returnPressed.connect(self.on_send)

        precision_btn = QPushButton("Precision: ON")
        precision_btn.setObjectName("PrecisionButton")
        precision_btn.clicked.connect(self.on_toggle_precision)
        self.precision_btn = precision_btn
        self.precision_btn.setProperty("active", "true")

        attach_btn = QPushButton("Attach")
        attach_btn.setObjectName("AttachButton")
        attach_btn.clicked.connect(self.on_attach)

        send_btn = QPushButton("Send")
        send_btn.setObjectName("SendButton")
        send_btn.clicked.connect(self.on_send)

        input_layout.addWidget(self.input, stretch=1)
        input_layout.addWidget(precision_btn)
        input_layout.addWidget(attach_btn)
        input_layout.addWidget(send_btn)
        root.addWidget(input_frame)

        self._anims = []

        self.setStyleSheet(
            """
            QWidget {
                color: #e9e9e9;
                font-family: "Segoe UI";
            }
            #TitleBar {
                background: rgba(12,12,12,0.8);
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,0.08);
            }
            #TitleLabel {
                font-size: 16px;
                font-weight: 700;
            }
            #TitleButton {
                background: rgba(40,40,40,0.7);
                border-radius: 8px;
                padding: 4px 10px;
                border: 1px solid rgba(255,255,255,0.1);
            }
            #TitleButton:hover {
                background: rgba(60,60,60,0.85);
            }
            #TitleClose {
                background: rgba(180,50,50,0.85);
                border-radius: 8px;
                padding: 4px 10px;
                border: 1px solid rgba(255,255,255,0.1);
            }
            #TitleClose:hover {
                background: rgba(210,70,70,0.95);
            }
            #ChatContainer {
                background: rgba(0,0,0,0.92);
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,0.08);
            }
            #InputFrame {
                background: rgba(20,20,20,0.7);
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,0.08);
            }
            #InputBox {
                background: rgba(0,0,0,0.65);
                border-radius: 10px;
                padding: 10px 12px;
                border: 1px solid rgba(255,255,255,0.08);
            }
            #SendButton {
                background: rgba(60,120,255,0.9);
                color: #fff;
                border-radius: 10px;
                padding: 10px 18px;
                border: none;
            }
            #SendButton:hover {
                background: rgba(80,140,255,0.95);
            }
            #AttachButton {
                background: rgba(40,40,40,0.7);
                border-radius: 10px;
                padding: 10px 16px;
                border: 1px solid rgba(255,255,255,0.1);
            }
            #AttachButton:hover {
                background: rgba(60,60,60,0.85);
            }
            #PrecisionButton {
                background: rgba(30,70,120,0.65);
                border-radius: 10px;
                padding: 10px 16px;
                border: 1px solid rgba(120,180,255,0.25);
            }
            #PrecisionButton[active="true"] {
                background: rgba(60,140,255,0.85);
                border: 1px solid rgba(120,200,255,0.6);
            }
            #PrecisionButton:hover {
                background: rgba(60,120,200,0.8);
            }
            #ChatBubble[user="true"] {
                background: rgba(40,40,40,0.65);
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,0.08);
            }
            #ChatBubble[user="false"] {
                background: rgba(25,25,25,0.8);
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,0.08);
            }
            #AuthorLabel {
                font-size: 12px;
                color: rgba(255,255,255,0.6);
            }
            #MessageLabel {
                font-size: 13px;
            }
            """
        )

        if should_preload():
            try:
                chunk_count = load_knowledge()
            except MemoryError:
                chunk_count = 0
            if chunk_count:
                self.append_message(MORICE_NAME, f"Loaded {chunk_count} knowledge chunks from {KB_DIR}.")
            else:
                self.append_message(MORICE_NAME, f"No knowledge files loaded from {KB_DIR}.")
        else:
            self.append_message(MORICE_NAME, "Knowledge is on-demand. Use @notes to include your files.")

        QTimer.singleShot(200, self._post_init)

    def _post_init(self):
        hwnd = int(self.winId())
        try:
            _enable_acrylic(hwnd)
        except Exception:
            pass

    def append_message(self, author: str, message: str, is_user: bool = False):
        bubble = ChatBubble(author, message, is_user=is_user)
        bubble.installEventFilter(self)
        opacity = QGraphicsOpacityEffect(bubble)
        bubble.setGraphicsEffect(opacity)
        opacity.setOpacity(0.0)

        self.chat_list_layout.insertWidget(self.chat_list_layout.count(), bubble)

        anim = QPropertyAnimation(opacity, b"opacity")
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: self._anims.remove(anim) if anim in self._anims else None)
        self._anims.append(anim)
        anim.start()

        QTimer.singleShot(0, self._maybe_autoscroll)

    def _on_scroll_change(self, value: int):
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() <= 0:
            self.user_scrolled = False
            return
        self.user_scrolled = value < (bar.maximum() - 40)

    def _maybe_autoscroll(self):
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() <= 0:
            return
        if not self.user_scrolled:
            bar.setValue(bar.maximum())

    def eventFilter(self, source, event):
        if event.type() == QEvent.Wheel and source in {self.chat_list, self.scroll.viewport()}:
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.value() - event.angleDelta().y())
            return True
        if event.type() == QEvent.Wheel and isinstance(source, ChatBubble):
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.value() - event.angleDelta().y())
            return True
        return super().eventFilter(source, event)

    def on_send(self):
        user_input = self.input.text().strip()
        if not user_input:
            return
        self.input.clear()
        self.append_message("All Father", user_input, is_user=True)
        self.user_messages.append(user_input)
        if not self.first_user_message:
            self.first_user_message = user_input

        image_path = self.pending_image_path
        if image_path:
            self.pending_image_path = ""
            self.append_message("All Father", f"Attached image: {os.path.basename(image_path)}", is_user=True)

        wake_message = wake_up_response(user_input)
        if wake_message:
            self.append_message(MORICE_NAME, wake_message)
            self.awake = True
            return

        if not self.awake:
            self.append_message(MORICE_NAME, "I am asleep. Say 'wake up son'.")
            return

        summon_message = summon_response(user_input)
        if summon_message:
            self.append_message(MORICE_NAME, summon_message)
            return

        riddle_reply = riddle_response(user_input)
        if riddle_reply:
            self.append_message(MORICE_NAME, enforce_father(riddle_reply))
            return

        father_reply = father_identity_response(user_input)
        if father_reply:
            self.append_message(MORICE_NAME, enforce_father(father_reply))
            return

        if wants_first_message(user_input) and self.first_user_message:
            self.append_message(MORICE_NAME, enforce_father(self.first_user_message))
            return

        if wants_memory_list(user_input):
            recent = self.user_messages[-5:]
            if recent:
                self.append_message(MORICE_NAME, enforce_father(" | ".join(recent)))
            else:
                self.append_message(MORICE_NAME, enforce_father("No messages yet."))
            return

        if wants_memory_search(user_input):
            terms = extract_memory_terms(user_input)
            matches = []
            for msg in reversed(self.user_messages):
                if all(term in msg.lower() for term in terms):
                    matches.append(msg)
                if len(matches) >= 3:
                    break
            if matches:
                self.append_message(MORICE_NAME, enforce_father(" | ".join(matches)))
            else:
                self.append_message(MORICE_NAME, enforce_father("I do not see that in your messages."))
            return

        if is_acknowledgement(user_input):
            self.append_message(MORICE_NAME, enforce_father("Understood."))
            return

        if wants_help(user_input):
            self.append_message(MORICE_NAME, enforce_father(help_text()))
            return

        if wants_precision_on(user_input):
            self._set_precision_state(True)
            self.append_message(MORICE_NAME, enforce_father("Precision mode enabled."))
            return

        if wants_precision_off(user_input):
            self._set_precision_state(False)
            self.append_message(MORICE_NAME, enforce_father("Precision mode disabled."))
            return

        if wants_math_steps_on(user_input):
            self.math_steps_mode = True
            self.append_message(MORICE_NAME, enforce_father("Math steps mode enabled."))
            return

        if wants_math_steps_off(user_input):
            self.math_steps_mode = False
            self.append_message(MORICE_NAME, enforce_father("Math steps mode disabled."))
            return

        if wants_unity_movement(user_input):
            if wants_unity_3d(user_input):
                script = unity_3d_movement_script()
            else:
                script = unity_2d_movement_script()
            self.append_message(MORICE_NAME, f"Father, here is the script.\n{script}")
            return

        if wants_html_cube_movement(user_input):
            self.append_message(MORICE_NAME, f"Father, here is the script.\n{html_cube_movement_script()}")
            return

        if not self.math_steps_mode and not wants_steps_detail(user_input):
            math_result = compute_math(user_input)
            if math_result is not None:
                self.append_message(MORICE_NAME, enforce_father(shorten_reply(math_result)))
                return

        if wants_notes_search(user_input):
            term = extract_notes_term(user_input)
            if term:
                hits = search_notes(term, max_hits=5)
                self.last_notes_hits = hits
                self.last_notes_term = term
                if hits:
                    self.append_message(MORICE_NAME, enforce_father(f"Found {len(hits)} match(es) for {term}."))
                    for hit in hits:
                        self.append_message(MORICE_NAME, f"{hit['source']}: {hit['text']}")
                else:
                    self.append_message(MORICE_NAME, enforce_father(f"No matches for {term} in notes."))
                return

        if wants_notes_summary(user_input) and self.last_notes_hits:
            summary = summarize_notes_hits(self.last_notes_hits)
            self.append_message(MORICE_NAME, enforce_father(summary))
            return

        def worker():
            context = retrieve_context(user_input) if should_use_context(user_input) else ""
            web_context = ""
            if os.getenv("MORICE_WEB", "1") == "1":
                web_query = extract_web_query(user_input) or (user_input if needs_web(user_input) else None)
                if web_query:
                    web_context = search_web(web_query)

            extra_system = ""
            if image_path:
                image_context = describe_image(image_path)
                lowered = image_context.lower()
                if any(key in lowered for key in {"not available", "not found", "could not open"}):
                    self.message_ready.emit(MORICE_NAME, enforce_father(image_context), False)
                    return
                extra_system = (
                    "Image context (best effort, may be incomplete):\n"
                    f"{image_context}"
                )
                if "no readable text detected" in lowered:
                    extra_system += "\nDo not invent text. Ask the user to paste the question."
            if context:
                extra_system = (
                    (extra_system + "\n\n" if extra_system else "")
                    + "Use the following local notes when relevant. "
                    "If they don't apply, ignore them.\n\n"
                    f"{context}"
                )
            if self.first_user_message:
                extra_system = (extra_system + "\n\n" if extra_system else "") + (
                    f"Conversation memory: The user's first message was: {self.first_user_message}"
                )
            if web_context:
                extra_system = (extra_system + "\n\n" if extra_system else "") + (
                    "Web results (may be incomplete):\n" + web_context
                )

            reply = chat(
                self.history,
                user_input,
                extra_system=extra_system,
                precision_mode=self.precision_mode,
                math_steps_mode=self.math_steps_mode or wants_steps_detail(user_input),
            )
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": reply})
            self.message_ready.emit(MORICE_NAME, enforce_father(shorten_reply(reply)), False)

        threading.Thread(target=worker, daemon=True).start()

    def on_attach(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select an image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if file_path:
            self.pending_image_path = file_path
            self.append_message(MORICE_NAME, enforce_father("Image attached. Ask your question."))

    def on_toggle_precision(self):
        self._set_precision_state(not self.precision_mode)
        is_on = self.precision_mode
        self.append_message(MORICE_NAME, enforce_father("Precision mode enabled." if is_on else "Precision mode disabled."))

    def _set_precision_state(self, is_on: bool):
        self.precision_mode = is_on
        self.precision_btn.setText("Precision: ON" if is_on else "Precision: OFF")
        self.precision_btn.setProperty("active", "true" if is_on else "false")
        self.precision_btn.style().unpolish(self.precision_btn)
        self.precision_btn.style().polish(self.precision_btn)


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName("MORICE")
    icon_path = _icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MoriceWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
