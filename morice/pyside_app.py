import os
import sys
import threading
import ctypes
import html
import math
import re
from ctypes import wintypes

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QRect, QTimer, Signal, QEvent
from PySide6.QtGui import QFont, QFontDatabase, QColor, QIcon, QCursor, QPainter, QPen
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
    QGraphicsDropShadowEffect,
    QFileDialog,
    QListWidget,
    QSizePolicy,
    QTextEdit,
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
    wants_web_capability,
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
    emotional_checkin_response,
    current_datetime_response,
)
from .knowledge import KB_DIR, load_knowledge, retrieve_context, should_use_context, should_preload, search_notes
from .llm_client import chat
from .settings import (
    DEFAULT_SETTINGS,
    load_settings,
    normalize_chat_mode,
    normalize_user_title,
    normalize_wake_phrase,
    normalize_response_style,
    save_settings,
    wake_signal_path,
)
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


_UI_FONTS_LOADED = False


def _load_ui_fonts():
    global _UI_FONTS_LOADED
    if _UI_FONTS_LOADED:
        return
    app = QApplication.instance()
    if app is None:
        return

    font_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    font_paths = [
        os.path.join(font_dir, "segoeui.ttf"),
        os.path.join(font_dir, "segoeuib.ttf"),
        os.path.join(font_dir, "segoeuii.ttf"),
    ]
    loaded_family = ""
    for font_path in font_paths:
        if not os.path.exists(font_path):
            continue
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families and not loaded_family:
            loaded_family = families[0]

    if loaded_family:
        app.setFont(QFont(loaded_family, 10))
    _UI_FONTS_LOADED = True


def _inline_markdown_to_rich_text(text: str) -> str:
    safe = html.escape(text, quote=False)
    safe = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", safe)
    safe = re.sub(r"\*\*([^*\n][\s\S]*?[^*\n])\*\*", r"<b>\1</b>", safe)
    safe = re.sub(r"__([^_\n][\s\S]*?[^_\n])__", r"<b>\1</b>", safe)
    return safe


def _message_to_rich_text(message: str) -> str:
    text = (message or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    parts: list[str] = []
    in_code = False
    code_lines: list[str] = []
    list_open = False

    def close_list():
        nonlocal list_open
        if list_open:
            parts.append("</ul>")
            list_open = False

    def flush_code():
        if not code_lines:
            return
        code = html.escape("\n".join(code_lines), quote=False)
        parts.append(f"<pre><code>{code}</code></pre>")
        code_lines.clear()

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                close_list()
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            close_list()
            parts.append("<br>")
            continue

        heading_match = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if heading_match:
            close_list()
            parts.append(f"<p><b>{_inline_markdown_to_rich_text(heading_match.group(1))}</b></p>")
            continue

        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet_match:
            if not list_open:
                parts.append("<ul>")
                list_open = True
            parts.append(f"<li>{_inline_markdown_to_rich_text(bullet_match.group(1))}</li>")
            continue

        numbered_match = re.match(r"^(\d+)[.)]\s+(.+)$", stripped)
        if numbered_match:
            close_list()
            number, body = numbered_match.groups()
            parts.append(f"<p>{number}. {_inline_markdown_to_rich_text(body)}</p>")
            continue

        close_list()
        parts.append(f"<p>{_inline_markdown_to_rich_text(stripped)}</p>")

    close_list()
    if in_code:
        flush_code()
    return "".join(parts)



class ComposerStageFrame(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("ComposerStage")
        self._wave_phase = 0.0
        self._wave_timer = QTimer(self)
        self._wave_timer.timeout.connect(self._advance_wave)
        self._wave_timer.start(45)

    def _advance_wave(self):
        self._wave_phase = (self._wave_phase + 0.16) % (math.pi * 2)
        self.update()

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        width = max(1, rect.width())
        height = max(1, rect.height())

        painter.fillRect(rect, QColor(7, 7, 12, 232))
        painter.setPen(Qt.NoPen)

        start_y = int(height * 0.34)
        end_y = int(height * 0.86)
        if end_y <= start_y:
            return

        for y in range(start_y, end_y, 11):
            vertical_fade = (y - start_y) / max(1, end_y - start_y)
            for x in range(-24, width + 24, 13):
                wave_y = (
                    height * 0.66
                    + math.sin((x * 0.014) + self._wave_phase) * height * 0.060
                    + math.sin((x * 0.031) - (self._wave_phase * 0.7)) * height * 0.026
                )
                envelope = 1.0 - (abs(y - wave_y) / max(1.0, height * 0.245))
                if envelope <= 0:
                    continue
                shimmer = 0.66 + 0.34 * math.sin((x * 0.045) + (y * 0.018) + self._wave_phase)
                strength = max(0.0, min(1.0, envelope * vertical_fade * shimmer))
                alpha = int(22 + 150 * strength)
                if alpha < 28:
                    continue
                blend = 0.5 + 0.5 * math.sin((x * 0.011) + self._wave_phase * 0.55)
                red = int(126 + 92 * blend)
                green = int(74 + 46 * (1.0 - blend))
                blue = int(218 + 30 * strength)
                size = 2 + int(5 * strength)
                painter.setBrush(QColor(red, green, blue, alpha))
                painter.drawEllipse(x, y, size, size)


class ChatBubble(QFrame):
    def __init__(self, author: str, message: str, is_user: bool = False):
        super().__init__()
        self.setObjectName("ChatBubble")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        author_label = QLabel(author)
        author_label.setObjectName("AuthorLabel")
        author_label.setTextFormat(Qt.PlainText)
        author_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        author_label.setFocusPolicy(Qt.StrongFocus)
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setObjectName("MessageLabel")
        message_label.setText(_message_to_rich_text(message))
        message_label.setTextFormat(Qt.RichText)
        message_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        message_label.setFocusPolicy(Qt.StrongFocus)

        layout.addWidget(author_label)
        layout.addWidget(message_label)

        self.setProperty("user", "true" if is_user else "false")


class ThinkingBubble(QFrame):
    def __init__(self, detail: str):
        super().__init__()
        self.setObjectName("ThinkingBubble")
        self._visible = True
        self._lines: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.dot = QLabel()
        self.dot.setObjectName("ThinkingDot")
        self.dot.setFixedSize(10, 10)

        self.toggle = QPushButton("Hide processing")
        self.toggle.setObjectName("ThinkingButton")
        self.toggle.clicked.connect(self.toggle_detail)

        self.detail_label = QLabel()
        self.detail_label.setObjectName("ThinkingDetail")
        self.detail_label.setTextFormat(Qt.PlainText)
        self.detail_label.setWordWrap(True)
        self.detail_label.setVisible(True)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.detail_label.setFocusPolicy(Qt.StrongFocus)

        header.addWidget(self.dot)
        header.addWidget(self.toggle, stretch=1)

        layout.addLayout(header)
        layout.addWidget(self.detail_label)
        self.set_detail(detail)

    def toggle_detail(self):
        self._visible = not self._visible
        self.detail_label.setVisible(self._visible)
        self.toggle.setText("Hide processing" if self._visible else "Show processing")

    def set_detail(self, detail: str):
        detail = (detail or "").strip()
        if not detail:
            return
        if self._lines and self._lines[-1] == detail:
            return
        self._lines.append(detail)
        self.detail_label.setText("\n".join(f"{index + 1}. {line}" for index, line in enumerate(self._lines)))

    def finish(self):
        self.set_detail("Done. Reply is shown below.")
        self.toggle.setText("Processing done")
        self.dot.setProperty("done", "true")
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)


class RgbMenuButton(QPushButton):
    def __init__(self):
        super().__init__("")
        self.setObjectName("RgbMenuButton")
        self.setFixedSize(42, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Open mode panel")
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(60)

    def _advance(self):
        self._phase = (self._phase + 0.10) % (math.pi * 2)
        self.update()

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(18, 15, 27, 218))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 9, 9)

        line_width = 18
        left = (rect.width() - line_width) // 2
        ys = (10, 16, 22)
        for index, y in enumerate(ys):
            red = int(135 + 90 * (0.5 + 0.5 * math.sin(self._phase + index * 2.1)))
            green = int(135 + 90 * (0.5 + 0.5 * math.sin(self._phase + index * 2.1 + 2.0)))
            blue = int(135 + 90 * (0.5 + 0.5 * math.sin(self._phase + index * 2.1 + 4.0)))
            pen = QPen(QColor(red, green, blue, 238), 3)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(left, y, left + line_width, y)


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

        self.mode_btn = RgbMenuButton()
        self.mode_btn.clicked.connect(self._parent.toggle_mode_panel)

        self.sidebar_btn = QPushButton("Panel")
        self.sidebar_btn.setObjectName("SidebarButton")
        self.sidebar_btn.clicked.connect(self._parent.toggle_sidebar)

        logo = QLabel()
        logo.setObjectName("TitleLogo")
        icon = QIcon(_icon_path())
        logo_pixmap = icon.pixmap(22, 22)
        if not logo_pixmap.isNull():
            logo.setPixmap(logo_pixmap)

        title = QLabel(f"{MORICE_NAME}")
        title.setObjectName("TitleLabel")

        layout.addWidget(self.mode_btn)
        layout.addWidget(self.sidebar_btn)
        layout.addWidget(logo)
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
    thinking_update = Signal(str)

    def __init__(self):
        super().__init__()
        _load_ui_fonts()
        self.setWindowTitle(f"{MORICE_NAME} Glass Chat")
        self.resize(980, 640)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        icon_path = _icon_path()
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.history = []
        self.awake = os.getenv("MORICE_START_AWAKE", "").strip() == "1"
        self.last_notes_hits = []
        self.last_notes_term = ""
        self.pending_image_path = ""
        self.precision_mode = True
        self.math_steps_mode = False
        self.follow_latest = True
        self._auto_scrolling = False
        self._last_scroll_max = 0
        self.first_user_message = ""
        self.user_messages: list[str] = []
        self.is_busy = False
        self.thinking_bubble: ThinkingBubble | None = None
        self._thinking_token = 0
        self.composer_centered = True
        self._input_hovered = False
        self.input_glow: QGraphicsDropShadowEffect | None = None
        self._composer_anim: QPropertyAnimation | None = None
        self._dock_placeholder: QWidget | None = None
        self.message_queue: list[str] = []
        self.settings = load_settings()
        self.response_style = self.settings.get("response_style", "").strip()
        self.wake_phrase = normalize_wake_phrase(self.settings.get("wake_phrase", ""))
        self.user_title = normalize_user_title(self.settings.get("user_title", ""))
        self.chat_mode = normalize_chat_mode(self.settings.get("chat_mode", ""))

        self.wake_signal_path = wake_signal_path()
        self.message_ready.connect(self._on_message_ready)
        self.thinking_update.connect(self._on_thinking_update)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        root.addLayout(body, stretch=1)

        self.mode_panel = QFrame()
        self.mode_panel.setObjectName("ModePanel")
        self.mode_panel.setFixedWidth(230)
        mode_layout = QVBoxLayout(self.mode_panel)
        mode_layout.setContentsMargins(14, 16, 14, 16)
        mode_layout.setSpacing(10)

        mode_title = QLabel("Mode")
        mode_title.setObjectName("ModeTitle")

        mode_hint = QLabel("Choose how MORICE should handle the next work.")
        mode_hint.setObjectName("ModeHint")
        mode_hint.setWordWrap(True)

        self.normal_mode_btn = QPushButton("Normal chat")
        self.normal_mode_btn.setObjectName("ModeOption")
        self.normal_mode_btn.clicked.connect(lambda: self._set_chat_mode("normal"))

        self.project_mode_btn = QPushButton("Project")
        self.project_mode_btn.setObjectName("ModeOption")
        self.project_mode_btn.clicked.connect(lambda: self._set_chat_mode("project"))

        self.mode_status = QLabel("")
        self.mode_status.setObjectName("ModeStatus")
        self.mode_status.setWordWrap(True)

        mode_layout.addWidget(mode_title)
        mode_layout.addWidget(mode_hint)
        mode_layout.addSpacing(6)
        mode_layout.addWidget(self.normal_mode_btn)
        mode_layout.addWidget(self.project_mode_btn)
        mode_layout.addWidget(self.mode_status)
        mode_layout.addStretch(1)

        body.addWidget(self.mode_panel)
        self.mode_panel.setVisible(False)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        self.content_layout = content_layout
        body.addLayout(content_layout, stretch=1)

        chat_container = QFrame()
        chat_container.setObjectName("ChatContainer")
        self.chat_container = chat_container
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setFocusPolicy(Qt.StrongFocus)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
        self.scroll.viewport().installEventFilter(self)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chat_layout.addWidget(self.scroll)

        self.chat_list = QWidget()
        self.chat_list.setObjectName("ChatList")
        self.chat_list.setAutoFillBackground(False)
        self.chat_list.setAttribute(Qt.WA_TranslucentBackground, True)
        self.chat_list_layout = QVBoxLayout(self.chat_list)
        self.chat_list_layout.setContentsMargins(12, 16, 12, 24)
        self.chat_list_layout.setSpacing(10)
        self.chat_list_layout.setAlignment(Qt.AlignTop)
        self.chat_list.setFocusPolicy(Qt.NoFocus)
        self.chat_list.installEventFilter(self)
        self.scroll.setWidget(self.chat_list)
        scroll_bar = self.scroll.verticalScrollBar()
        self._last_scroll_max = scroll_bar.maximum()
        scroll_bar.valueChanged.connect(self._on_scroll_change)
        scroll_bar.rangeChanged.connect(self._on_scroll_range_change)
        self._bottom_spacer = QWidget()
        self._bottom_spacer.setFixedHeight(8)
        self.chat_list_layout.addWidget(self._bottom_spacer)

        content_layout.addWidget(chat_container, stretch=1)
        chat_container.setVisible(False)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("SidebarPanel")
        self.sidebar.setFixedWidth(340)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(12)

        sidebar_title = QLabel("Morice panel")
        sidebar_title.setObjectName("SidebarTitle")

        current_label = QLabel("Current personalization")
        current_label.setObjectName("SidebarSectionLabel")

        self.current_style_value = QLabel()
        self.current_style_value.setObjectName("CurrentStyleValue")
        self.current_style_value.setWordWrap(True)
        self.current_style_value.setTextFormat(Qt.PlainText)
        self.current_style_value.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.current_style_value.setFocusPolicy(Qt.StrongFocus)

        style_label = QLabel("Personalise response")
        style_label.setObjectName("StyleLabel")

        self.style_input = QTextEdit()
        self.style_input.setObjectName("StyleInput")
        self.style_input.setPlaceholderText("Example: mid-length, funny, direct, teacher-like, Hinglish...")
        self.style_input.setPlainText(self.response_style)
        self.style_input.setFixedHeight(92)

        title_label = QLabel("What MORICE calls you")
        title_label.setObjectName("StyleLabel")

        self.title_input = QLineEdit()
        self.title_input.setObjectName("TitleInput")
        self.title_input.setPlaceholderText("Example: Boss, Captain, Janmesh...")
        self.title_input.setText(self.user_title)

        wake_label = QLabel("Wake line")
        wake_label.setObjectName("StyleLabel")

        self.wake_input = QLineEdit()
        self.wake_input.setObjectName("WakeInput")
        self.wake_input.setPlaceholderText("Example: wake up son")
        self.wake_input.setText(self.wake_phrase)

        save_style_btn = QPushButton("Save personalization")
        save_style_btn.setObjectName("StyleSaveButton")
        save_style_btn.clicked.connect(self.on_save_response_style)
        self.save_style_btn = save_style_btn

        clear_style_btn = QPushButton("Clear")
        clear_style_btn.setObjectName("StyleClearButton")
        clear_style_btn.clicked.connect(self.on_clear_response_style)
        self.clear_style_btn = clear_style_btn

        style_buttons = QHBoxLayout()
        style_buttons.setContentsMargins(0, 0, 0, 0)
        style_buttons.setSpacing(8)
        style_buttons.addWidget(save_style_btn, stretch=1)
        style_buttons.addWidget(clear_style_btn)

        self.style_status = QLabel("")
        self.style_status.setObjectName("StyleStatus")
        self.style_status.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.style_status.setFocusPolicy(Qt.StrongFocus)

        queue_label = QLabel("Message queue")
        queue_label.setObjectName("StyleLabel")

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("QueueList")
        self.queue_list.setFixedHeight(118)

        queue_up_btn = QPushButton("Up")
        queue_up_btn.setObjectName("QueueButton")
        queue_up_btn.clicked.connect(self.on_queue_up)
        self.queue_up_btn = queue_up_btn

        queue_down_btn = QPushButton("Down")
        queue_down_btn.setObjectName("QueueButton")
        queue_down_btn.clicked.connect(self.on_queue_down)
        self.queue_down_btn = queue_down_btn

        queue_remove_btn = QPushButton("Remove")
        queue_remove_btn.setObjectName("QueueButton")
        queue_remove_btn.clicked.connect(self.on_queue_remove)
        self.queue_remove_btn = queue_remove_btn

        queue_clear_btn = QPushButton("Clear queue")
        queue_clear_btn.setObjectName("QueueButton")
        queue_clear_btn.clicked.connect(self.on_queue_clear)
        self.queue_clear_btn = queue_clear_btn

        queue_buttons = QHBoxLayout()
        queue_buttons.setContentsMargins(0, 0, 0, 0)
        queue_buttons.setSpacing(8)
        queue_buttons.addWidget(queue_up_btn)
        queue_buttons.addWidget(queue_down_btn)
        queue_buttons.addWidget(queue_remove_btn)
        queue_buttons.addWidget(queue_clear_btn)

        sidebar_layout.addWidget(sidebar_title)
        sidebar_layout.addWidget(current_label)
        sidebar_layout.addWidget(self.current_style_value)
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(style_label)
        sidebar_layout.addWidget(self.style_input)
        sidebar_layout.addWidget(title_label)
        sidebar_layout.addWidget(self.title_input)
        sidebar_layout.addWidget(wake_label)
        sidebar_layout.addWidget(self.wake_input)
        sidebar_layout.addLayout(style_buttons)
        sidebar_layout.addWidget(self.style_status)
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(queue_label)
        sidebar_layout.addWidget(self.queue_list)
        sidebar_layout.addLayout(queue_buttons)
        sidebar_layout.addStretch(1)

        body.addWidget(self.sidebar)
        self.sidebar.setVisible(False)

        input_frame = QFrame()
        input_frame.setObjectName("InputFrame")
        self.input_frame = input_frame
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)
        input_layout.setSpacing(10)

        self.input = QLineEdit()
        self.input.setPlaceholderText(f"{self.user_title}: type here...")
        self.input.setObjectName("InputBox")
        self.input.returnPressed.connect(self.on_send)

        precision_btn = QPushButton("Precision: ON")
        precision_btn.setObjectName("PrecisionButton")
        precision_btn.clicked.connect(self.on_toggle_precision)
        self.precision_btn = precision_btn
        self.precision_btn.setProperty("active", "true")

        personalization_btn = QPushButton()
        personalization_btn.setObjectName("PersonalizationStatus")
        personalization_btn.clicked.connect(self.toggle_sidebar)
        self.personalization_btn = personalization_btn

        send_btn = QPushButton("Send")
        send_btn.setObjectName("SendButton")
        send_btn.clicked.connect(self.on_send)
        self.send_btn = send_btn

        input_layout.addWidget(self.input, stretch=1)
        input_layout.addWidget(precision_btn)
        input_layout.addWidget(personalization_btn)
        input_layout.addWidget(send_btn)

        self.composer_stage = ComposerStageFrame()
        stage_layout = QVBoxLayout(self.composer_stage)
        stage_layout.setContentsMargins(18, 20, 18, 42)
        stage_layout.setSpacing(16)

        self.hero_label = QLabel(f"{MORICE_NAME}, what shall we do, {self.user_title}?")
        self.hero_label.setObjectName("HeroPrompt")
        self.hero_label.setAlignment(Qt.AlignCenter)
        self.hero_label.setWordWrap(True)

        self.center_input_host = QWidget()
        self.center_input_host.setObjectName("CenterInputHost")
        self.center_input_host.setMaximumWidth(820)
        self.center_input_layout = QVBoxLayout(self.center_input_host)
        self.center_input_layout.setContentsMargins(0, 0, 0, 0)
        self.center_input_layout.setSpacing(0)

        stage_layout.addStretch(3)
        stage_layout.addWidget(self.hero_label)
        stage_layout.addWidget(self.center_input_host, alignment=Qt.AlignHCenter)
        self.center_panel_host = QWidget()
        self.center_panel_host.setObjectName("CenterPanelHost")
        center_panel_layout = QHBoxLayout(self.center_panel_host)
        center_panel_layout.setContentsMargins(0, 0, 0, 0)
        center_panel_layout.setSpacing(0)
        self.center_panel_layout = center_panel_layout
        self.title_bar.layout().removeWidget(self.title_bar.sidebar_btn)
        self.center_panel_layout.addWidget(self.title_bar.sidebar_btn, alignment=Qt.AlignHCenter)
        self.title_bar.sidebar_btn.setProperty("centered", "true")
        stage_layout.addWidget(self.center_panel_host, alignment=Qt.AlignHCenter)
        stage_layout.addStretch(5)

        self.bottom_input_host = QWidget()
        self.bottom_input_host.setObjectName("BottomInputHost")
        self.bottom_input_layout = QVBoxLayout(self.bottom_input_host)
        self.bottom_input_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_input_layout.setSpacing(0)
        self.bottom_input_host.setVisible(False)

        self.center_input_layout.addWidget(input_frame)
        content_layout.addWidget(self.composer_stage, stretch=1)
        content_layout.addWidget(self.bottom_input_host)
        self._configure_input_bar(centered=True)

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
            #TitleBar[personalized="true"] {
                background: rgba(18,10,28,0.86);
                border: 1px solid rgba(178,130,255,0.24);
            }
            #TitleLabel {
                font-size: 16px;
                font-weight: 700;
            }
            #TitleLogo {
                min-width: 22px;
                min-height: 22px;
            }
            #RgbMenuButton {
                border-radius: 9px;
                border: 1px solid rgba(160,120,255,0.32);
                background: transparent;
            }
            #RgbMenuButton:hover {
                border: 1px solid rgba(225,210,255,0.72);
                background: rgba(80,48,142,0.18);
            }
            #SidebarButton {
                background: rgba(50,80,70,0.78);
                border-radius: 8px;
                padding: 5px 12px;
                border: 1px solid rgba(125,210,160,0.32);
                font-weight: 700;
            }
            #SidebarButton[personalized="true"] {
                background: rgba(78,48,128,0.86);
                border: 1px solid rgba(202,170,255,0.5);
            }
            #SidebarButton[centered="true"] {
                background: rgba(96,58,172,0.84);
                border-radius: 14px;
                padding: 9px 24px;
                border: 1px solid rgba(222,196,255,0.5);
                font-weight: 800;
            }
            #SidebarButton:hover {
                background: rgba(62,105,88,0.9);
            }
            #SidebarButton[personalized="true"]:hover {
                background: rgba(96,60,155,0.94);
            }
            #SidebarButton[centered="true"]:hover {
                background: rgba(126,78,222,0.96);
                border: 1px solid rgba(240,224,255,0.78);
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
            #ChatContainer[personalized="true"] {
                background: rgba(12,8,20,0.93);
                border: 1px solid rgba(178,130,255,0.18);
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget,
            #ChatList {
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.028);
                width: 10px;
                margin: 8px 2px 8px 0;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: rgba(125,210,160,0.52);
                min-height: 56px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(150,235,185,0.76);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                background: transparent;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
            #InputFrame {
                background: rgba(18,15,24,0.88);
                border-radius: 16px;
                border: 1px solid rgba(178,130,255,0.38);
            }
            #InputFrame[centered="true"] {
                background: rgba(22,18,30,0.92);
                border-radius: 24px;
                border: 1px solid rgba(198,150,255,0.68);
            }
            #InputFrame[hovered="true"] {
                border: 1px solid rgba(232,205,255,0.94);
            }
            #InputFrame[personalized="true"] {
                background: rgba(23,15,36,0.9);
                border: 1px solid rgba(196,145,255,0.58);
            }
            #InputFrame[centered="true"][personalized="true"] {
                background: rgba(24,18,34,0.94);
                border: 1px solid rgba(206,165,255,0.72);
            }
            #InputFrame[hovered="true"],
            #InputFrame[personalized="true"][hovered="true"],
            #InputFrame[centered="true"][hovered="true"] {
                border: 1px solid rgba(238,216,255,0.98);
            }
            #ComposerStage {
                background: transparent;
                border: none;
            }
            #CenterInputHost {
                background: transparent;
            }
            #CenterPanelHost {
                background: transparent;
            }
            #BottomInputHost {
                background: transparent;
            }
            #HeroPrompt {
                color: rgba(245,239,255,0.92);
                font-size: 30px;
                font-weight: 500;
            }
            #SidebarPanel {
                background: rgba(12,14,16,0.94);
                border-radius: 14px;
                border: 1px solid rgba(125,210,160,0.18);
            }
            #SidebarPanel[personalized="true"] {
                background: rgba(15,10,26,0.96);
                border: 1px solid rgba(178,130,255,0.28);
            }
            #ModePanel {
                background: rgba(10,12,15,0.95);
                border-radius: 14px;
                border: 1px solid rgba(178,130,255,0.26);
            }
            #ModeTitle {
                color: #ffffff;
                font-size: 18px;
                font-weight: 800;
            }
            #ModeHint {
                color: rgba(226,220,238,0.62);
                font-size: 12px;
            }
            #ModeOption {
                text-align: left;
                background: rgba(20,18,28,0.82);
                color: rgba(246,242,255,0.92);
                border-radius: 10px;
                padding: 11px 12px;
                border: 1px solid rgba(180,135,255,0.22);
                font-weight: 800;
            }
            #ModeOption:hover {
                background: rgba(64,40,112,0.86);
                border: 1px solid rgba(205,172,255,0.44);
            }
            #ModeOption[active="true"] {
                background: rgba(118,72,220,0.92);
                border: 1px solid rgba(225,205,255,0.68);
            }
            #ModeStatus {
                color: rgba(165,225,195,0.78);
                font-size: 12px;
                padding-top: 4px;
            }
            #SidebarTitle {
                color: #ffffff;
                font-size: 18px;
                font-weight: 800;
            }
            #SidebarSectionLabel {
                color: rgba(165,225,195,0.86);
                font-size: 12px;
                font-weight: 800;
            }
            #CurrentStyleValue {
                background: rgba(0,0,0,0.32);
                border-radius: 10px;
                padding: 10px 11px;
                border: 1px solid rgba(255,255,255,0.08);
                color: rgba(245,245,245,0.9);
            }
            #CurrentStyleValue[empty="true"] {
                color: rgba(255,255,255,0.42);
            }
            #StyleLabel {
                color: rgba(255,255,255,0.72);
                font-size: 12px;
                font-weight: 700;
            }
            #InputBox {
                background: rgba(0,0,0,0.28);
                border-radius: 12px;
                padding: 10px 12px;
                border: 1px solid rgba(255,255,255,0.05);
            }
            #InputFrame[centered="true"] #InputBox {
                background: transparent;
                border: none;
                padding: 11px 12px;
                font-size: 14px;
            }
            #StyleInput {
                background: rgba(0,0,0,0.52);
                border-radius: 10px;
                padding: 9px 11px;
                border: 1px solid rgba(255,255,255,0.08);
                selection-background-color: rgba(178,96,255,0.45);
            }
            #WakeInput {
                background: rgba(0,0,0,0.52);
                border-radius: 10px;
                padding: 9px 11px;
                border: 1px solid rgba(255,255,255,0.08);
                selection-background-color: rgba(178,96,255,0.45);
            }
            #TitleInput {
                background: rgba(0,0,0,0.52);
                border-radius: 10px;
                padding: 9px 11px;
                border: 1px solid rgba(255,255,255,0.08);
                selection-background-color: rgba(178,96,255,0.45);
            }
            #StyleStatus {
                color: rgba(165,225,195,0.82);
                font-size: 12px;
                min-height: 18px;
            }
            #QueueList {
                background: rgba(0,0,0,0.42);
                border-radius: 10px;
                padding: 6px;
                border: 1px solid rgba(178,130,255,0.18);
                color: rgba(245,239,255,0.9);
                selection-background-color: rgba(118,72,220,0.62);
            }
            #QueueButton {
                background: rgba(58,42,100,0.72);
                color: rgba(246,239,255,0.94);
                border-radius: 9px;
                padding: 7px 9px;
                border: 1px solid rgba(180,135,255,0.26);
            }
            #QueueButton:hover {
                background: rgba(92,58,154,0.9);
            }
            #InputBox {
                selection-background-color: rgba(178,96,255,0.45);
            }
            #StyleInput:focus,
            #TitleInput:focus,
            #WakeInput:focus,
            #InputBox:focus {
                border: 1px solid rgba(208,165,255,0.6);
            }
            #SendButton {
                background: rgba(120,74,220,0.9);
                color: #fff;
                border-radius: 12px;
                padding: 10px 18px;
                border: none;
            }
            #SendButton:hover {
                background: rgba(148,94,255,0.98);
            }
            #SendButton[personalized="true"] {
                background: rgba(126,76,220,0.94);
                border: 1px solid rgba(202,170,255,0.36);
            }
            #SendButton[personalized="true"]:hover {
                background: rgba(158,102,255,1);
            }
            #SendButton:disabled,
            #PersonalizationStatus:disabled,
            #PrecisionButton:disabled,
            #StyleSaveButton:disabled,
            #StyleClearButton:disabled,
            #QueueButton:disabled,
            #InputBox:disabled,
            #StyleInput:disabled,
            #TitleInput:disabled,
            #WakeInput:disabled {
                color: rgba(255,255,255,0.38);
                background: rgba(45,45,45,0.55);
                border: 1px solid rgba(255,255,255,0.05);
            }
            #PersonalizationStatus {
                background: rgba(70,44,118,0.78);
                color: rgba(246,239,255,0.94);
                border-radius: 12px;
                padding: 10px 16px;
                border: 1px solid rgba(190,145,255,0.32);
                font-weight: 800;
            }
            #PersonalizationStatus:hover {
                background: rgba(92,58,154,0.9);
            }
            #PersonalizationStatus[personalized="true"] {
                background: rgba(88,54,150,0.92);
                color: #f2eaff;
                border: 1px solid rgba(202,170,255,0.5);
            }
            #PersonalizationStatus[personalized="true"]:hover {
                background: rgba(106,68,178,0.96);
            }
            #StyleSaveButton {
                background: rgba(60,130,95,0.82);
                color: #f2fff7;
                border-radius: 10px;
                padding: 8px 14px;
                border: 1px solid rgba(130,230,170,0.26);
            }
            #StyleSaveButton:hover {
                background: rgba(74,155,112,0.9);
            }
            #StyleSaveButton[personalized="true"] {
                background: rgba(98,58,160,0.9);
                border: 1px solid rgba(202,170,255,0.34);
            }
            #StyleClearButton {
                background: rgba(70,70,78,0.72);
                color: #f0f0f0;
                border-radius: 10px;
                padding: 8px 12px;
                border: 1px solid rgba(255,255,255,0.1);
            }
            #StyleClearButton:hover {
                background: rgba(88,88,96,0.82);
            }
            #PrecisionButton {
                background: rgba(58,42,100,0.72);
                border-radius: 12px;
                padding: 10px 16px;
                border: 1px solid rgba(180,135,255,0.28);
            }
            #PrecisionButton[active="true"] {
                background: rgba(118,72,220,0.9);
                border: 1px solid rgba(215,180,255,0.62);
            }
            #PrecisionButton[personalized="true"] {
                background: rgba(72,46,126,0.78);
                border: 1px solid rgba(178,130,255,0.34);
            }
            #PrecisionButton[active="true"][personalized="true"] {
                background: rgba(102,64,190,0.9);
                border: 1px solid rgba(202,170,255,0.55);
            }
            #PrecisionButton:hover {
                background: rgba(92,58,154,0.9);
            }
            #ChatBubble[user="true"] {
                background: rgba(42,74,108,0.72);
                border-radius: 12px;
                border: 1px solid rgba(120,180,255,0.18);
            }
            #ChatBubble[user="false"] {
                background: rgba(25,28,33,0.86);
                border-radius: 12px;
                border: 1px solid rgba(125,210,160,0.12);
            }
            #AuthorLabel {
                font-size: 12px;
                color: rgba(165,225,195,0.78);
                selection-background-color: rgba(125,210,160,0.45);
            }
            #MessageLabel {
                font-size: 13px;
                selection-background-color: rgba(125,210,160,0.45);
            }
            #ThinkingBubble {
                background: rgba(28,26,38,0.88);
                border-radius: 12px;
                border: 1px solid rgba(190,160,255,0.25);
            }
            #ThinkingDot {
                background: rgba(160,125,255,0.95);
                border-radius: 5px;
                border: 1px solid rgba(220,205,255,0.55);
            }
            #ThinkingDot[done="true"] {
                background: rgba(125,210,160,0.95);
                border: 1px solid rgba(190,255,215,0.55);
            }
            #ThinkingButton {
                background: rgba(92,64,160,0.74);
                color: #e9e9e9;
                border-radius: 10px;
                padding: 8px 12px;
                border: 1px solid rgba(120,180,255,0.3);
                text-align: left;
            }
            #ThinkingButton:hover {
                background: rgba(112,82,190,0.86);
            }
            #ThinkingDetail {
                color: rgba(255,255,255,0.68);
                font-size: 12px;
                selection-background-color: rgba(125,210,160,0.45);
            }
            """
        )
        self._update_style_badge()
        self._refresh_queue_list()
        self._refresh_mode_panel()

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
        if self.awake:
            self.append_message(MORICE_NAME, f"{MORICE_NAME} is awake, {self.user_title}.")
        else:
            self.append_message(
                MORICE_NAME,
                f"{MORICE_NAME} is asleep, {self.user_title}. Type '{self.wake_phrase}' to wake me.",
            )

        QTimer.singleShot(200, self._post_init)
        self.wake_signal_timer = QTimer(self)
        self.wake_signal_timer.timeout.connect(self._check_external_wake_signal)
        self.wake_signal_timer.start(1000)

    def _post_init(self):
        hwnd = int(self.winId())
        try:
            _enable_acrylic(hwnd)
        except Exception:
            pass

    def _check_external_wake_signal(self):
        if not os.path.exists(self.wake_signal_path):
            return
        try:
            os.remove(self.wake_signal_path)
        except Exception:
            pass
        self._wake_from_external()

    def _wake_from_external(self):
        if self.awake:
            self.append_message(MORICE_NAME, self._address("I heard the wake signal. I am already awake."))
            return
        self.awake = True
        self.append_message(MORICE_NAME, f"{MORICE_NAME} is awake, {self.user_title}.")

    def _address(self, reply: str) -> str:
        return enforce_father(reply, self.user_title)

    def _input_placeholder(self) -> str:
        return f"{self.user_title}: type here..."

    def _refresh_name_dependent_text(self):
        if hasattr(self, "hero_label"):
            self.hero_label.setText(f"{MORICE_NAME}, what shall we do, {self.user_title}?")
        if hasattr(self, "input") and not self.is_busy:
            self.input.setPlaceholderText(self._input_placeholder())

    def toggle_mode_panel(self):
        is_visible = not self.mode_panel.isVisible()
        self.mode_panel.setVisible(is_visible)
        self.title_bar.mode_btn.setToolTip("Close mode panel" if is_visible else "Open mode panel")

    def toggle_sidebar(self):
        is_visible = not self.sidebar.isVisible()
        self.sidebar.setVisible(is_visible)
        self.title_bar.sidebar_btn.setText("Close" if is_visible else "Panel")
        if is_visible:
            self.style_input.setFocus()

    def _set_chat_mode(self, mode: str):
        clean_mode = normalize_chat_mode(mode)
        if clean_mode == self.chat_mode:
            self._refresh_mode_panel()
            return
        self.chat_mode = clean_mode
        self.settings["chat_mode"] = self.chat_mode
        save_settings(self.settings)
        self._refresh_mode_panel()
        mode_name = "Project" if self.chat_mode == "project" else "Normal chat"
        if self.chat_container.isVisible():
            self.append_message(MORICE_NAME, self._address(f"{mode_name} mode enabled."))
        else:
            self.mode_status.setText(f"{mode_name} mode is ready for the next message.")

    def _refresh_mode_panel(self):
        if not hasattr(self, "normal_mode_btn"):
            return
        is_project = self.chat_mode == "project"
        for button, active in (
            (self.normal_mode_btn, not is_project),
            (self.project_mode_btn, is_project),
        ):
            button.setProperty("active", "true" if active else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        self.mode_status.setText(
            "Project mode keeps answers organized around files, steps, decisions, and next actions."
            if is_project
            else "Normal chat is for everyday questions, quick replies, and casual work."
        )

    def append_message(self, author: str, message: str, is_user: bool = False, force_scroll: bool | None = None):
        should_follow = self.follow_latest or self._is_at_bottom()
        if force_scroll is None:
            force_scroll = is_user or should_follow
        if force_scroll:
            self.follow_latest = True

        bubble = ChatBubble(author, message, is_user=is_user)
        bubble.installEventFilter(self)
        opacity = QGraphicsOpacityEffect(bubble)
        bubble.setGraphicsEffect(opacity)
        opacity.setOpacity(0.0)

        insert_index = max(0, self.chat_list_layout.count() - 1)
        self.chat_list_layout.insertWidget(insert_index, bubble)

        anim = QPropertyAnimation(opacity, b"opacity")
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: self._anims.remove(anim) if anim in self._anims else None)
        self._anims.append(anim)
        anim.start()

        self._schedule_latest_scroll(force=force_scroll)

    def _set_busy(self, is_busy: bool):
        self.is_busy = is_busy
        self.input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.personalization_btn.setEnabled(not is_busy)
        self.precision_btn.setEnabled(not is_busy)
        self.style_input.setEnabled(not is_busy)
        self.title_input.setEnabled(not is_busy)
        self.wake_input.setEnabled(not is_busy)
        self.save_style_btn.setEnabled(not is_busy)
        self.clear_style_btn.setEnabled(not is_busy)
        self._refresh_send_button_state()
        if not is_busy:
            self.input.setFocus()

    def _refresh_send_button_state(self):
        queued_count = len(self.message_queue)
        if self.is_busy:
            self.send_btn.setText(f"Queued {queued_count}" if queued_count else "Steer")
            if queued_count:
                self.input.setPlaceholderText("Queued. Add another steer message or reorder in Panel.")
            else:
                self.input.setPlaceholderText("Steer next message while MORICE replies...")
        else:
            self.send_btn.setText("Send")
            self.input.setPlaceholderText(self._input_placeholder())
        self._refresh_queue_controls()

    def _refresh_queue_list(self, preferred_row: int | None = None):
        if not hasattr(self, "queue_list"):
            return
        current_row = self.queue_list.currentRow() if preferred_row is None else preferred_row
        self.queue_list.clear()
        for index, message in enumerate(self.message_queue, start=1):
            preview = message.replace("\n", " ").strip()
            if len(preview) > 70:
                preview = preview[:67] + "..."
            self.queue_list.addItem(f"{index}. {preview}")
        if self.message_queue:
            self.queue_list.setCurrentRow(max(0, min(current_row, len(self.message_queue) - 1)))
        self._refresh_queue_controls()

    def _refresh_queue_controls(self):
        if not hasattr(self, "queue_list"):
            return
        row = self.queue_list.currentRow()
        has_items = bool(self.message_queue)
        self.queue_up_btn.setEnabled(has_items and row > 0)
        self.queue_down_btn.setEnabled(has_items and 0 <= row < len(self.message_queue) - 1)
        self.queue_remove_btn.setEnabled(has_items and row >= 0)
        self.queue_clear_btn.setEnabled(has_items)

    def _queue_steer_message(self):
        steer_message = self.input.text().strip()
        if not steer_message:
            return
        self.message_queue.append(steer_message)
        self.input.clear()
        self._refresh_queue_list(preferred_row=len(self.message_queue) - 1)
        self._refresh_send_button_state()

    def _send_queued_message_if_ready(self):
        if self.is_busy or not self.message_queue:
            return
        next_message = self.message_queue.pop(0)
        self._refresh_queue_list(preferred_row=0)
        self._refresh_send_button_state()
        self.input.setText(next_message)
        QTimer.singleShot(80, self.on_send)

    def on_queue_up(self):
        row = self.queue_list.currentRow()
        if row <= 0:
            return
        self.message_queue[row - 1], self.message_queue[row] = self.message_queue[row], self.message_queue[row - 1]
        self._refresh_queue_list(preferred_row=row - 1)
        self._refresh_send_button_state()

    def on_queue_down(self):
        row = self.queue_list.currentRow()
        if row < 0 or row >= len(self.message_queue) - 1:
            return
        self.message_queue[row + 1], self.message_queue[row] = self.message_queue[row], self.message_queue[row + 1]
        self._refresh_queue_list(preferred_row=row + 1)
        self._refresh_send_button_state()

    def on_queue_remove(self):
        row = self.queue_list.currentRow()
        if row < 0 or row >= len(self.message_queue):
            return
        self.message_queue.pop(row)
        self._refresh_queue_list(preferred_row=min(row, len(self.message_queue) - 1))
        self._refresh_send_button_state()

    def on_queue_clear(self):
        if not self.message_queue:
            return
        self.message_queue.clear()
        self._refresh_queue_list(preferred_row=0)
        self._refresh_send_button_state()

    def _show_thinking(self, detail: str):
        self._remove_thinking()
        self._thinking_token += 1
        token = self._thinking_token
        self.thinking_bubble = ThinkingBubble(detail)
        insert_index = max(0, self.chat_list_layout.count() - 1)
        self.chat_list_layout.insertWidget(insert_index, self.thinking_bubble)
        self._schedule_latest_scroll(force=True)
        QTimer.singleShot(
            12000,
            lambda: self._thinking_delayed_update(
                token,
                "Hermes is still generating. Local CPU replies can take a bit.",
            ),
        )
        QTimer.singleShot(
            35000,
            lambda: self._thinking_delayed_update(
                token,
                "Still working locally. If the engine fails, I will show the error here.",
            ),
        )

    def _thinking_delayed_update(self, token: int, detail: str):
        if token == self._thinking_token and self.thinking_bubble:
            self.thinking_update.emit(detail)

    def _remove_thinking(self):
        if not self.thinking_bubble:
            return
        self.chat_list_layout.removeWidget(self.thinking_bubble)
        self.thinking_bubble.deleteLater()
        self.thinking_bubble = None

    def _finish_thinking(self):
        self._remove_thinking()

    def _on_message_ready(self, author: str, message: str, is_user: bool = False):
        self._remove_thinking()
        self.append_message(author, message, is_user=is_user, force_scroll=True)
        self._set_busy(False)
        QTimer.singleShot(120, self._send_queued_message_if_ready)

    def _on_thinking_update(self, detail: str):
        if self.thinking_bubble:
            self.thinking_bubble.set_detail(detail)

    def _update_style_badge(self):
        if not hasattr(self, "current_style_value"):
            return
        has_personalization = self._has_personalization()
        current_lines = []
        if self._has_custom_user_title():
            current_lines.append(f"Calls you: {self.user_title}")
        if self.response_style:
            current_lines.append(self.response_style)
        if self._has_custom_wake_phrase():
            current_lines.append(f"Wake line: {self.wake_phrase}")
        if current_lines:
            self.current_style_value.setText("\n".join(current_lines))
        else:
            self.current_style_value.setText("None")
        self.current_style_value.setProperty("empty", "false" if has_personalization else "true")
        self.personalization_btn.setText("Personalised" if has_personalization else "None")
        self.personalization_btn.setProperty("personalized", "true" if has_personalization else "false")
        self._apply_personalization_theme(has_personalization)

    def _has_custom_wake_phrase(self) -> bool:
        return normalize_wake_phrase(self.wake_phrase).lower() != DEFAULT_SETTINGS["wake_phrase"].lower()

    def _has_custom_user_title(self) -> bool:
        return normalize_user_title(self.user_title).lower() != DEFAULT_SETTINGS["user_title"].lower()

    def _has_personalization(self) -> bool:
        return bool(self.response_style.strip()) or self._has_custom_wake_phrase() or self._has_custom_user_title()

    def _apply_personalization_theme(self, has_personalization: bool):
        state = "true" if has_personalization else "false"
        widgets = [
            self.current_style_value,
            self.personalization_btn,
            self.title_bar,
            self.title_bar.sidebar_btn,
            self.chat_container,
            self.input_frame,
            self.sidebar,
            self.mode_panel,
            self.precision_btn,
            self.save_style_btn,
            self.send_btn,
        ]
        for widget in widgets:
            widget.setProperty("personalized", state)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        if hasattr(self, "input_frame"):
            self._configure_input_bar(centered=self.composer_centered)

    def _composer_widgets(self):
        return (
            self.input_frame,
            self.input,
            self.precision_btn,
            self.personalization_btn,
            self.send_btn,
        )

    def _configure_input_bar(self, centered: bool):
        if not hasattr(self, "input_frame"):
            return

        self.composer_centered = centered
        is_active = self.input.hasFocus()
        self.input_frame.setProperty("centered", "true" if centered else "false")
        self.input_frame.setProperty("hovered", "true" if is_active else "false")
        self.input_frame.setMaximumWidth(820 if centered else 16777215)

        if self.input_glow is None:
            self.input_glow = QGraphicsDropShadowEffect(self.input_frame)
            self.input_glow.setOffset(0, 0)
            self.input_frame.setGraphicsEffect(self.input_glow)

        if centered:
            blur_radius = 124
            alpha = 238
        else:
            blur_radius = 66 if is_active else 46
            alpha = 190 if is_active else 126
        self.input_glow.setBlurRadius(blur_radius)
        self.input_glow.setColor(QColor(178, 96, 255, alpha))

        for widget in self._composer_widgets():
            widget.style().unpolish(widget)
            widget.style().polish(widget)

        if not getattr(self, "_composer_filters_installed", False):
            for widget in self._composer_widgets():
                widget.installEventFilter(self)
            self._composer_filters_installed = True

    def _refresh_input_hover_from_cursor(self):
        if not hasattr(self, "input_frame"):
            return
        local_pos = self.input_frame.mapFromGlobal(QCursor.pos())
        self._input_hovered = self.input_frame.rect().contains(local_pos)
        self._configure_input_bar(centered=self.composer_centered)

    def _return_panel_button_to_titlebar(self):
        button = self.title_bar.sidebar_btn
        if self.center_panel_layout.indexOf(button) != -1:
            self.center_panel_layout.removeWidget(button)
        if self.title_bar.layout().indexOf(button) == -1:
            self.title_bar.layout().insertWidget(0, button)
        button.setProperty("centered", "false")
        button.style().unpolish(button)
        button.style().polish(button)

    def _dock_composer(self):
        if not self.composer_centered:
            return

        if not self.isVisible() or self.input_frame.width() <= 0 or self.input_frame.height() <= 0:
            self._dock_composer_immediate()
            return

        self._dock_composer_animated()

    def _dock_composer_immediate(self):
        self._return_panel_button_to_titlebar()
        self.center_input_layout.removeWidget(self.input_frame)
        self.bottom_input_layout.addWidget(self.input_frame)
        self.composer_stage.setVisible(False)
        self.bottom_input_host.setVisible(True)
        self.chat_container.setVisible(True)
        self._input_hovered = False
        self._configure_input_bar(centered=False)
        self.follow_latest = True
        self._schedule_latest_scroll(force=True)

    def _dock_composer_animated(self):
        start_rect = QRect(self.input_frame.mapTo(self, QPoint(0, 0)), self.input_frame.size())
        self._return_panel_button_to_titlebar()
        self.center_input_layout.removeWidget(self.input_frame)

        placeholder = QWidget()
        placeholder.setObjectName("ComposerDockPlaceholder")
        placeholder.setFixedHeight(max(1, start_rect.height()))
        placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._dock_placeholder = placeholder

        self.composer_stage.setVisible(False)
        self.chat_container.setVisible(True)
        self.bottom_input_host.setVisible(True)
        self.bottom_input_layout.addWidget(placeholder)
        QApplication.processEvents()

        target_rect = QRect(placeholder.mapTo(self, QPoint(0, 0)), placeholder.size())
        if target_rect.width() <= 0 or target_rect.height() <= 0:
            self._finish_composer_dock(placeholder)
            return

        self.input_frame.setParent(self)
        self.input_frame.setGeometry(start_rect)
        self.input_frame.show()
        self.input_frame.raise_()
        self._input_hovered = False
        self._configure_input_bar(centered=False)

        fall_anim = QPropertyAnimation(self.input_frame, b"geometry", self)
        fall_anim.setDuration(820)
        fall_anim.setEasingCurve(QEasingCurve.InOutCubic)
        fall_anim.setStartValue(start_rect)

        distance_y = target_rect.y() - start_rect.y()
        early_y = start_rect.y() + int(distance_y * 0.28)
        early_width = start_rect.width() + int((target_rect.width() - start_rect.width()) * 0.25)
        early_x = start_rect.x() + int((target_rect.x() - start_rect.x()) * 0.2)
        fall_anim.setKeyValueAt(
            0.38,
            QRect(early_x, early_y, early_width, target_rect.height()),
        )
        fall_anim.setKeyValueAt(
            0.68,
            QRect(target_rect.x() - 16, target_rect.y() + 22, target_rect.width(), target_rect.height()),
        )
        fall_anim.setKeyValueAt(
            0.82,
            QRect(target_rect.x() + 12, target_rect.y() - 10, target_rect.width(), target_rect.height()),
        )
        fall_anim.setKeyValueAt(
            0.92,
            QRect(target_rect.x() - 5, target_rect.y() + 4, target_rect.width(), target_rect.height()),
        )
        fall_anim.setEndValue(target_rect)
        fall_anim.finished.connect(lambda: self._finish_composer_dock(placeholder))
        self._composer_anim = fall_anim
        self._anims.append(fall_anim)
        fall_anim.start()

    def _finish_composer_dock(self, placeholder: QWidget | None):
        if placeholder is not None:
            self.bottom_input_layout.removeWidget(placeholder)
            placeholder.deleteLater()
        self._dock_placeholder = None
        if self.bottom_input_layout.indexOf(self.input_frame) == -1:
            self.bottom_input_layout.addWidget(self.input_frame)
        self.input_frame.show()
        self._configure_input_bar(centered=False)
        if self._composer_anim in self._anims:
            self._anims.remove(self._composer_anim)
        self._composer_anim = None
        self.follow_latest = True
        self._schedule_latest_scroll(force=True)

    def on_save_response_style(self):
        raw_style = self.style_input.toPlainText().strip()
        clean_style = normalize_response_style(raw_style)
        self.response_style = clean_style
        self.user_title = normalize_user_title(self.title_input.text())
        self.wake_phrase = normalize_wake_phrase(self.wake_input.text())
        self.style_input.setPlainText(self.response_style)
        self.title_input.setText(self.user_title)
        self.wake_input.setText(self.wake_phrase)
        self.settings["response_style"] = self.response_style
        self.settings["user_title"] = self.user_title
        self.settings["wake_phrase"] = self.wake_phrase
        save_settings(self.settings)
        self._refresh_name_dependent_text()
        self._update_style_badge()
        self.style_status.setText("Saved. Morice will use this on the next reply.")

    def on_clear_response_style(self):
        self.response_style = ""
        self.user_title = DEFAULT_SETTINGS["user_title"]
        self.wake_phrase = DEFAULT_SETTINGS["wake_phrase"]
        self.style_input.clear()
        self.title_input.setText(self.user_title)
        self.wake_input.setText(self.wake_phrase)
        self.settings["response_style"] = ""
        self.settings["user_title"] = self.user_title
        self.settings["wake_phrase"] = self.wake_phrase
        save_settings(self.settings)
        self._refresh_name_dependent_text()
        self._update_style_badge()
        self.style_status.setText("Cleared. Personalization is None.")

    def _on_scroll_change(self, value: int):
        if self._auto_scrolling:
            return

        bar = self.scroll.verticalScrollBar()
        maximum = bar.maximum()
        if maximum <= 0:
            self.follow_latest = True
            return

        old_max = max(0, self._last_scroll_max)
        if maximum != old_max and value >= old_max - 48:
            self.follow_latest = True
            return

        self.follow_latest = value >= maximum - 48

    def _on_scroll_range_change(self, _minimum: int, maximum: int):
        bar = self.scroll.verticalScrollBar()
        old_max = self._last_scroll_max
        was_following = self.follow_latest or bar.value() >= old_max - 48
        self._last_scroll_max = maximum
        if was_following:
            self.follow_latest = True
            self._schedule_latest_scroll(force=True)

    def _schedule_latest_scroll(self, force: bool = False):
        if force:
            self.follow_latest = True
        if not self.follow_latest:
            return

        for delay in (0, 16, 50, 120):
            QTimer.singleShot(delay, self._scroll_to_latest)

    def _scroll_to_latest(self):
        if not self.follow_latest:
            return

        bar = self.scroll.verticalScrollBar()
        if bar.maximum() <= 0:
            return
        self._auto_scrolling = True
        try:
            bar.setValue(bar.maximum())
        finally:
            self._auto_scrolling = False
        self.follow_latest = True

    def _is_at_bottom(self, margin: int = 48) -> bool:
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() <= 0:
            return True
        return bar.value() >= (bar.maximum() - margin)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Wheel:
            return False
        if hasattr(self, "input_frame") and source in self._composer_widgets():
            if event.type() in (QEvent.Enter, QEvent.FocusIn):
                self._input_hovered = True
                self._configure_input_bar(centered=self.composer_centered)
            elif event.type() in (QEvent.Leave, QEvent.FocusOut):
                QTimer.singleShot(0, self._refresh_input_hover_from_cursor)
        return super().eventFilter(source, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_latest_scroll()

    def on_send(self):
        if self.is_busy:
            self._queue_steer_message()
            return
        user_input = self.input.text().strip()
        if not user_input:
            return
        self.follow_latest = True
        self.input.clear()
        self._dock_composer()
        self.append_message(self.user_title, user_input, is_user=True, force_scroll=True)
        self.user_messages.append(user_input)
        if not self.first_user_message:
            self.first_user_message = user_input

        image_path = self.pending_image_path
        if image_path:
            self.pending_image_path = ""
            self.append_message(self.user_title, f"Attached image: {os.path.basename(image_path)}", is_user=True)

        wake_message = wake_up_response(user_input, self.wake_phrase, self.user_title)
        if wake_message:
            self.append_message(MORICE_NAME, wake_message)
            self.awake = True
            return

        if not self.awake:
            self.append_message(MORICE_NAME, f"I am asleep, {self.user_title}. Say '{self.wake_phrase}'.")
            return

        summon_message = summon_response(user_input, self.user_title)
        if summon_message:
            self.append_message(MORICE_NAME, summon_message)
            return

        riddle_reply = riddle_response(user_input)
        if riddle_reply:
            self.append_message(MORICE_NAME, self._address(riddle_reply))
            return

        emotional_reply = emotional_checkin_response(user_input, self.user_title)
        if emotional_reply:
            self.append_message(MORICE_NAME, self._address(emotional_reply))
            return

        father_reply = father_identity_response(user_input, self.user_title)
        if father_reply:
            self.append_message(MORICE_NAME, self._address(father_reply))
            return

        datetime_reply = current_datetime_response(user_input)
        if datetime_reply:
            self.append_message(MORICE_NAME, self._address(datetime_reply))
            return

        if wants_first_message(user_input) and self.first_user_message:
            self.append_message(MORICE_NAME, self._address(self.first_user_message))
            return

        if wants_memory_list(user_input):
            recent = self.user_messages[-5:]
            if recent:
                self.append_message(MORICE_NAME, self._address(" | ".join(recent)))
            else:
                self.append_message(MORICE_NAME, self._address("No messages yet."))
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
                self.append_message(MORICE_NAME, self._address(" | ".join(matches)))
            else:
                self.append_message(MORICE_NAME, self._address("I do not see that in your messages."))
            return

        if is_acknowledgement(user_input):
            self.append_message(MORICE_NAME, self._address("Understood."))
            return

        if wants_help(user_input):
            self.append_message(MORICE_NAME, self._address(help_text()))
            return

        if wants_precision_on(user_input):
            self._set_precision_state(True)
            self.append_message(MORICE_NAME, self._address("Precision mode enabled."))
            return

        if wants_precision_off(user_input):
            self._set_precision_state(False)
            self.append_message(MORICE_NAME, self._address("Precision mode disabled."))
            return

        if wants_math_steps_on(user_input):
            self.math_steps_mode = True
            self.append_message(MORICE_NAME, self._address("Math steps mode enabled."))
            return

        if wants_math_steps_off(user_input):
            self.math_steps_mode = False
            self.append_message(MORICE_NAME, self._address("Math steps mode disabled."))
            return

        if wants_unity_movement(user_input):
            if wants_unity_3d(user_input):
                script = unity_3d_movement_script()
            else:
                script = unity_2d_movement_script()
            self.append_message(MORICE_NAME, f"{self.user_title}, here is the script.\n{script}")
            return

        if wants_html_cube_movement(user_input):
            self.append_message(MORICE_NAME, f"{self.user_title}, here is the script.\n{html_cube_movement_script()}")
            return

        if not self.math_steps_mode and not wants_steps_detail(user_input):
            math_result = compute_math(user_input)
            if math_result is not None:
                self.append_message(MORICE_NAME, self._address(shorten_reply(math_result)))
                return

        if wants_notes_search(user_input):
            term = extract_notes_term(user_input)
            if term:
                hits = search_notes(term, max_hits=5)
                self.last_notes_hits = hits
                self.last_notes_term = term
                if hits:
                    self.append_message(MORICE_NAME, self._address(f"Found {len(hits)} match(es) for {term}."))
                    for hit in hits:
                        self.append_message(MORICE_NAME, f"{hit['source']}: {hit['text']}")
                else:
                    self.append_message(MORICE_NAME, self._address(f"No matches for {term} in notes."))
                return

        if wants_notes_summary(user_input) and self.last_notes_hits:
            summary = summarize_notes_hits(self.last_notes_hits)
            self.append_message(MORICE_NAME, self._address(summary))
            return

        if wants_web_capability(user_input) and not extract_web_query(user_input):
            self.append_message(
                MORICE_NAME,
                self._address("Offline mode is active. Start the message with @web <query> when you want web search."),
            )
            return

        web_query_for_status = extract_web_query(user_input)
        self._set_busy(True)
        self._show_thinking(
            "Received your message and started the reply pipeline."
        )
        self.thinking_update.emit(
            "Using @web, collecting search results, then asking the Hermes engine."
            if web_query_for_status
            else "Full offline mode: asking the local Hermes engine only."
        )

        def worker():
            try:
                self.thinking_update.emit("Checking saved response style and local context.")
                context = retrieve_context(user_input) if should_use_context(user_input) else ""
                web_context = ""
                web_query = extract_web_query(user_input)
                if os.getenv("MORICE_WEB", "1") == "1" and web_query:
                    self.thinking_update.emit("Searching the web because the message used @web.")
                    web_context = search_web(web_query)
                    if not web_context:
                        web_context = "Web lookup returned no results."

                extra_system = (
                    f"Saved name preference from the user: address the user as '{self.user_title}'. "
                    "Do not call the user 'All Father' unless that is the saved name preference."
                )
                if self.chat_mode == "project":
                    extra_system += (
                        "\n\nProject mode is on. Keep replies execution-focused: identify the goal, "
                        "organize work into clear steps, call out files or decisions when relevant, "
                        "and end with the next concrete action."
                    )
                response_style = self.response_style.strip()
                if response_style:
                    extra_system += (
                        "\n\n"
                        "Saved response style from the user. Follow it directly for this reply:\n"
                        f"{response_style}"
                    )
                if image_path:
                    self.thinking_update.emit("Reading attached image context.")
                    image_context = describe_image(image_path)
                    lowered = image_context.lower()
                    if any(key in lowered for key in {"not available", "not found", "could not open"}):
                        self.message_ready.emit(MORICE_NAME, self._address(image_context), False)
                        return
                    extra_system = (
                        (extra_system + "\n\n" if extra_system else "")
                        + "Image context (best effort, may be incomplete):\n"
                        f"{image_context}"
                    )
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

                self.thinking_update.emit("Asking Hermes to compose the final answer.")
                reply = chat(
                    self.history,
                    user_input,
                    extra_system=extra_system,
                    timeout=180,
                    precision_mode=self.precision_mode,
                    math_steps_mode=self.math_steps_mode or wants_steps_detail(user_input),
                )
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": reply})
                self.message_ready.emit(MORICE_NAME, self._address(shorten_reply(reply)), False)
            except Exception as exc:  # noqa: BLE001
                self.message_ready.emit(MORICE_NAME, self._address(f"I hit an app error: {exc}"), False)

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
            self.append_message(MORICE_NAME, self._address("Image attached. Ask your question."))

    def on_toggle_precision(self):
        self._set_precision_state(not self.precision_mode)
        is_on = self.precision_mode
        self.append_message(MORICE_NAME, self._address("Precision mode enabled." if is_on else "Precision mode disabled."))

    def _set_precision_state(self, is_on: bool):
        self.precision_mode = is_on
        self.precision_btn.setText("Precision: ON" if is_on else "Precision: OFF")
        self.precision_btn.setProperty("active", "true" if is_on else "false")
        self.precision_btn.style().unpolish(self.precision_btn)
        self.precision_btn.style().polish(self.precision_btn)


def run_app():
    app = QApplication(sys.argv)
    _load_ui_fonts()
    app.setApplicationName("MORICE")
    icon_path = _icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MoriceWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
