import os
import sys
import threading
import ctypes
import copy
import html
import json
import math
import re
import shlex
import difflib
import time
import subprocess
import tempfile
import queue
from dataclasses import replace
from ctypes import wintypes
from datetime import datetime

from PySide6.QtCore import (
    Qt,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QEasingCurve,
    QPoint,
    QRect,
    QSize,
    QTimer,
    Signal,
    QEvent,
    QUrl,
)
from PySide6.QtGui import (
    QFont,
    QFontDatabase,
    QBrush,
    QColor,
    QDesktopServices,
    QIcon,
    QCursor,
    QPainter,
    QPixmap,
    QPen,
    QPainterPath,
    QPolygon,
    QLinearGradient,
    QRadialGradient,
    QPdfWriter,
    QKeySequence,
    QShortcut,
    QTextCursor,
)
from PySide6.QtSvg import QSvgGenerator
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:  # pragma: no cover - optional on minimal PySide installs
    QWebEngineView = None
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
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
    QListWidgetItem,
    QProgressBar,
    QComboBox,
    QCheckBox,
    QSlider,
    QSizeGrip,
    QSizePolicy,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QStackedWidget,
    QSplitter,
    QMessageBox,
    QColorDialog,
    QStyle,
)

from . import __version__
from .core import (
    MORICE_NAME,
    compute_math,
    enforce_father,
    shorten_reply,
    summon_response,
    is_acknowledgement,
    wants_help,
    wants_model_identity,
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
    harmful_request_response,
    ensure_visible_response,
)
from .knowledge import KB_DIR, load_knowledge, retrieve_context, should_use_context, should_preload, search_notes
from .llm_client import chat, prewarm_local_model, prime_local_chat_prefix, stream_chat
from .llm_client import reset_model_runtime
from .realtime_intelligence import LatencyStage, ModelTier
from .model_catalog import (
    GpuProfile,
    default_model_download_dir,
    detect_gpu_profile,
    download_model_result,
    format_size,
    gpu_profile_from_values,
    gpu_profile_summary,
    local_model_result,
    model_run_plan,
    model_worth,
    model_compatibility,
    search_huggingface_gguf,
    verify_ai_model_file,
)
from .project_builder import (
    analyze_project_request,
    build_project_fallback_manifest,
    project_request_contract,
    validate_project_manifest_intent,
)
from .project_runtime import (
    ProjectValidationError,
    build_launch_plan,
    build_run_script,
    detect_python_requirements,
    launch_project,
    validate_project_file,
)
from .agent_types import ToolCall
from .science_engine import GraphArtifact, GraphSurface, PhysicsArtifact, ScienceArtifact, is_science_request
from .domain_engine import DiagramArtifact, MoleculeArtifact, atom_color
from .educational_engine import BiologyArtifact, DataStructureArtifact
from .universal_engine import ChartArtifact, DocumentArtifact, SceneArtifact, ScenePrimitive
from .visualization import VisualizationManager, VisualizationResult
from .capabilities import (
    apply_emoji_presentation,
    capability_answer,
    detect_capability_topic,
    emoji_preference_instruction,
    maturity_preference_instruction,
)
from .conversation import (
    conversation_reference_instruction,
    previous_user_message,
    saved_settings_instruction,
    select_recent_history,
    wants_previous_user_message,
)
from .desktop_assistant import (
    DesktopAction,
    close_application,
    collect_system_snapshot,
    execute_desktop_action,
    parse_desktop_command,
    search_files,
)
from .desktop_environment import SearchEverywhereResult, SessionState
from .ui_system import (
    THEMES,
    AnimationEngine,
    MicroInteractionFilter,
    SmoothScrollController,
    normalize_accent,
    normalize_theme,
    premium_theme_stylesheet,
)
from .ui_workspace import (
    AssistantHub,
    CommandItem,
    CommandPalette,
    DEFAULT_COMMANDS,
    FilePreview,
    NotificationToast,
    install_command_shortcut,
)
from .diagnostics_ui import DiagnosticsDialog
from .plugin_ui import PluginCenter
from .premium_experience import (
    ExperienceProfile,
    ExperienceProfileStore,
    MAX_VISIBLE_CHAT_WIDGETS,
    workspace_layout,
)
from .premium_ui import PremiumSettingsDialog
from .platform_ui import FirstRunWizard
from .runtime_services import RecoveryInfo, RuntimeServices, get_runtime_services
from .config import load_tts_config
from .live_action_ui import LiveActionWorkspace
from .live_camera import LiveCameraController
from .live_vision import VisionResult, visual_follow_up, visual_intent
from .speech_runtime import SpeechInputConfig, TranscriptResult
from .voice_runtime import BoundedSpeechStream
from .wake_runtime import (
    parse_wake_request,
    set_app_session_active,
    set_voice_session_active,
)
from .workspace_state import (
    WorkspaceState,
    load_workspace_state,
    save_workspace_state,
)
from .settings import (
    DEFAULT_SETTINGS,
    load_settings,
    normalize_chat_mode,
    normalize_model_name,
    normalize_model_path,
    normalize_project_access,
    normalize_project_folder,
    normalize_project_lookup_mode,
    normalize_gpu_name,
    normalize_gpu_vram_mb,
    normalize_emoji_level,
    normalize_maturity_level,
    normalize_font_family,
    normalize_custom_font_path,
    normalize_animation_speed,
    normalize_boolean_setting,
    normalize_settings_profile,
    normalize_music_provider,
    normalize_transparency,
    normalize_ui_scale,
    normalize_workspace_preset,
    normalize_user_title,
    normalize_wake_phrase,
    normalize_response_style,
    normalize_tts_model_id,
    normalize_tts_output_device,
    normalize_tts_output_format,
    normalize_tts_provider,
    normalize_tts_speed,
    normalize_tts_voice_id,
    normalize_stt_input_device,
    normalize_stt_max_listen_seconds,
    save_settings,
    wake_signal_path,
)
from .web_search import infer_web_need, internet_available, search_web
from .vision import describe_image


def _tokenize_for_ui_search(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9+#.-]{2,}", value.casefold()))


def _start_background_task(name: str, target):
    runtime = get_runtime_services()
    if runtime.started:
        interactive = {
            "chat-reply",
            "conversation-turn",
            "voice-trace",
            "pc-control",
            "desktop-action",
            "close-application",
            "system-snapshot",
            "file-search",
            "project-command",
        }
        return runtime.workers.submit(
            name,
            target,
            priority="interactive" if name in interactive else "background",
        )
    try:
        thread = threading.Thread(
            target=target,
            daemon=True,
            name=f"morice-{name}",
        )
    except TypeError:
        # Some test and embedding hosts provide a minimal Thread-compatible
        # adapter without Python's optional naming argument.
        thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


PROJECT_TEXT_EXTENSIONS = {
    ".bat",
    ".c",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".go",
    ".gradle",
    ".h",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

PROJECT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}


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
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        exe_dir = os.path.dirname(sys.executable)
        if meipass:
            candidates.append(os.path.join(meipass, "morice", "assets", "morice_logo.ico"))
        candidates.append(os.path.join(exe_dir, "morice", "assets", "morice_logo.ico"))
        candidates.append(os.path.join(exe_dir, "_internal", "morice", "assets", "morice_logo.ico"))
    candidates.append(os.path.join(os.path.dirname(__file__), "assets", "morice_logo.ico"))
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return candidates[-1]


def _set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        app_id = "EONASH2722.MORICE"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


_UI_FONTS_LOADED = False
_ACTIVE_UI_FONT_FAMILY = "Segoe UI"
_ACTIVE_UI_THEME = "dark"


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
        os.path.join(font_dir, "seguiemj.ttf"),
        os.path.join(font_dir, "seguisym.ttf"),
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


def register_ui_font_file(path: str) -> str:
    font_path = normalize_custom_font_path(path)
    if not font_path or not os.path.isfile(font_path):
        return ""
    font_id = QFontDatabase.addApplicationFont(font_path)
    if font_id < 0:
        return ""
    families = QFontDatabase.applicationFontFamilies(font_id)
    return normalize_font_family(families[0]) if families else ""


def _theme_outline_icon(theme: str) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(QColor(255, 255, 255, 245), 1.7, Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    if normalize_theme(theme) == "light":
        painter.drawEllipse(QPoint(12, 12), 4, 4)
        for index in range(8):
            angle = index * math.tau / 8
            painter.drawLine(
                QPoint(int(12 + math.cos(angle) * 7), int(12 + math.sin(angle) * 7)),
                QPoint(int(12 + math.cos(angle) * 10), int(12 + math.sin(angle) * 10)),
            )
    else:
        path = QPainterPath()
        path.moveTo(15.5, 3.5)
        path.cubicTo(10.0, 5.0, 7.2, 9.0, 8.2, 13.2)
        path.cubicTo(9.2, 17.4, 13.2, 19.7, 18.2, 18.2)
        path.cubicTo(16.0, 20.4, 12.7, 21.2, 9.6, 19.9)
        path.cubicTo(4.2, 17.7, 1.8, 11.5, 4.1, 6.6)
        path.cubicTo(6.1, 2.5, 11.0, 1.1, 15.5, 3.5)
        painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


def available_ui_font_families(selected_family: str = "") -> list[str]:
    installed = {
        normalize_font_family(family)
        for family in QFontDatabase.families()
        if normalize_font_family(family)
    }
    preferred = (
        "Segoe UI",
        "Inter",
        "Arial",
        "Calibri",
        "Verdana",
        "Georgia",
        "Tahoma",
        "Times New Roman",
        "Cascadia Code",
    )
    families = [family for family in preferred if family in installed]
    selected = normalize_font_family(selected_family)
    if selected in installed and selected not in families:
        families.append(selected)
    if not families:
        families.append(QApplication.font().family() or DEFAULT_SETTINGS["font_family"])
    return families


class ModelSourceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.choice = ""
        self.setWindowTitle("Change MORICE model")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Choose model source")
        title.setObjectName("ModelDialogTitle")

        file_btn = QPushButton("Files from PC")
        file_btn.setObjectName("ModelChoiceButton")
        file_btn.clicked.connect(lambda: self._choose("files"))

        web_btn = QPushButton("Trusted web browser")
        web_btn.setObjectName("ModelChoiceButton")
        web_btn.clicked.connect(lambda: self._choose("web"))

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("ModelCancelButton")
        cancel_btn.clicked.connect(self.reject)

        layout.addWidget(title)
        layout.addWidget(file_btn)
        layout.addWidget(web_btn)
        layout.addWidget(cancel_btn)
        self.setStyleSheet(
            """
            QDialog {
                background: #111018;
                color: #f4f0ff;
            }
            #ModelDialogTitle {
                font-size: 18px;
                font-weight: 800;
            }
            #ModelChoiceButton {
                background: rgba(92,58,154,0.9);
                color: #fff;
                border-radius: 10px;
                padding: 11px 14px;
                border: 1px solid rgba(205,170,255,0.45);
                font-weight: 800;
            }
            #ModelChoiceButton:hover {
                background: rgba(118,72,220,0.96);
            }
            #ModelCancelButton {
                background: rgba(62,62,72,0.8);
                color: rgba(255,255,255,0.86);
                border-radius: 10px;
                padding: 9px 12px;
                border: 1px solid rgba(255,255,255,0.12);
            }
            """
        )

    def _choose(self, choice: str):
        self.choice = choice
        self.accept()


class LiquidGalaxyFrame(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("ModelGalaxySurface")
        self.setMouseTracking(True)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(40)

    def watch(self, root: QWidget):
        # Keep the model browser surface lightweight. The visual is a slow wave,
        # not a cursor-tracking effect, so it does not need filters on every child.
        root.setMouseTracking(True)

    def _advance(self):
        if not self.isVisible() or self.window().isMinimized():
            return
        self._phase = (self._phase + 0.045) % (math.pi * 2)
        self.update()

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        width = max(1, rect.width())
        height = max(1, rect.height())

        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0.0, QColor(5, 7, 18, 255))
        base.setColorAt(0.42, QColor(18, 12, 35, 255))
        base.setColorAt(0.72, QColor(5, 25, 35, 255))
        base.setColorAt(1.0, QColor(4, 7, 13, 255))
        painter.fillRect(rect, QBrush(base))

        painter.setPen(Qt.NoPen)
        for i in range(72):
            x = int((i * 97 + math.sin(self._phase + i) * 16) % (width + 28)) - 14
            y = int((i * i * 31 + math.cos(self._phase * 0.7 + i * 0.4) * 10) % (height + 24)) - 12
            pulse = 0.55 + 0.45 * math.sin(self._phase * 1.8 + i * 0.73)
            alpha = int(28 + 95 * pulse)
            size = 1 + (i % 3)
            painter.setBrush(QColor(160, 210, 255, alpha))
            painter.drawEllipse(x, y, size, size)

        wave = QPainterPath()
        wave.moveTo(0, height)
        wave_top = height * 0.74
        step = max(8, width // 42)
        for x in range(-step, width + step * 2, step):
            y = wave_top
            y += math.sin((x * 0.018) + self._phase * 2.4) * 16
            y += math.sin((x * 0.045) - self._phase * 1.8) * 7
            wave.lineTo(x, y)
        wave.lineTo(width, height)
        wave.closeSubpath()

        liquid = QLinearGradient(0, int(wave_top), width, height)
        liquid.setColorAt(0.0, QColor(68, 38, 140, 92))
        liquid.setColorAt(0.48, QColor(104, 64, 210, 120))
        liquid.setColorAt(1.0, QColor(36, 178, 196, 84))
        painter.fillPath(wave, QBrush(liquid))


class ModelWebBrowserDialog(QDialog):
    search_finished = Signal(object, str)
    download_progress = Signal(int, str)
    download_finished = Signal(str, str)
    gpu_detected = Signal(object)

    def _emit_background(self, signal_name: str, *arguments) -> bool:
        if getattr(self, "_is_closing", False):
            return False
        try:
            getattr(self, signal_name).emit(*arguments)
        except RuntimeError:
            return False
        return True

    def __init__(self, parent=None, gpu_profile: GpuProfile | None = None):
        super().__init__(parent)
        self._is_closing = False
        self.selected_path = ""
        self.gpu_profile = gpu_profile or gpu_profile_from_values()
        self._busy = False
        self._auto_search_started = False
        self._gpu_detection_busy = False
        self.setWindowTitle("MORICE trusted model browser")
        self.setModal(True)
        self.resize(1040, 760)
        self.setMinimumSize(920, 660)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.galaxy_surface = LiquidGalaxyFrame()
        root_layout.addWidget(self.galaxy_surface)

        layout = QVBoxLayout(self.galaxy_surface)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Trusted model browser")
        title.setObjectName("ModelDialogTitle")

        source = QLabel(
            "Trusted lanes only: Hugging Face GGUF files, verified download URLs, and official/source links."
        )
        source.setObjectName("ModelDialogSource")
        source.setWordWrap(True)

        self.gpu_chip = QLabel(gpu_profile_summary(self.gpu_profile))
        self.gpu_chip.setObjectName("ModelGpuChip")
        self.gpu_chip.setWordWrap(True)

        self.browser_map = QLabel(
            "Search or use a lane below. MORICE shows what the model is best for, whether it is worth using, "
            "and whether your detected GPU/VRAM can run it smoothly before install."
        )
        self.browser_map.setObjectName("ModelBrowserMap")
        self.browser_map.setWordWrap(True)

        gpu_row = QHBoxLayout()
        gpu_row.setContentsMargins(0, 0, 0, 0)
        gpu_row.setSpacing(8)

        self.dialog_detect_gpu_btn = QPushButton("Detect GPU")
        self.dialog_detect_gpu_btn.setObjectName("ModelSecondaryButton")
        self.dialog_detect_gpu_btn.clicked.connect(lambda _checked=False: self._detect_gpu_profile(auto=False))

        gpu_row.addWidget(self.gpu_chip, stretch=1)
        gpu_row.addWidget(self.dialog_detect_gpu_btn)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("ModelSearchInput")
        self.search_input.setPlaceholderText("Search model, e.g. qwen2.5 coder 7b")
        self.search_input.returnPressed.connect(self._start_search)

        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("ModelPrimaryButton")
        self.search_btn.clicked.connect(self._start_search)

        search_row.addWidget(self.search_input, stretch=1)
        search_row.addWidget(self.search_btn)

        quick_row = QHBoxLayout()
        quick_row.setContentsMargins(0, 0, 0, 0)
        quick_row.setSpacing(8)
        self.quick_buttons = []
        for label, query in (
            ("Best fit", ""),
            ("Qwen coder", "qwen2.5 coder 7b"),
            ("Mistral", "mistral 7b instruct"),
            ("Gemma", "gemma 3 4b"),
            ("Phi mini", "phi 4 mini"),
        ):
            button = QPushButton(label)
            button.setObjectName("ModelLaneButton")
            button.clicked.connect(lambda _checked=False, value=query: self._quick_search(value))
            quick_row.addWidget(button)
            self.quick_buttons.append(button)

        self.results = QListWidget()
        self.results.setObjectName("ModelResultList")
        self.results.setSpacing(8)
        self.results.setWordWrap(True)
        self.results.setMinimumHeight(260)
        self.results.itemSelectionChanged.connect(self._refresh_install_state)

        self.status = QLabel("Search trusted model sources and choose a GGUF model file.")
        self.status.setObjectName("ModelStatus")
        self.status.setWordWrap(True)

        self.compatibility_card = QFrame()
        self.compatibility_card.setObjectName("CompatibilityCard")
        compatibility_layout = QHBoxLayout(self.compatibility_card)
        compatibility_layout.setContentsMargins(10, 10, 10, 10)
        compatibility_layout.setSpacing(10)

        self.compatibility_dot = QFrame()
        self.compatibility_dot.setObjectName("CompatibilityDot")
        self.compatibility_dot.setFixedSize(16, 16)

        compatibility_text = QVBoxLayout()
        compatibility_text.setContentsMargins(0, 0, 0, 0)
        compatibility_text.setSpacing(3)

        self.compatibility_title = QLabel("Compatibility: choose a model")
        self.compatibility_title.setObjectName("CompatibilityTitle")

        self.compatibility_detail = QLabel(
            "Red means very low, yellow medium, green good, and dark green excellent."
        )
        self.compatibility_detail.setObjectName("CompatibilityDetail")
        self.compatibility_detail.setWordWrap(True)

        compatibility_text.addWidget(self.compatibility_title)
        compatibility_text.addWidget(self.compatibility_detail)
        compatibility_layout.addWidget(self.compatibility_dot, alignment=Qt.AlignTop)
        compatibility_layout.addLayout(compatibility_text, stretch=1)

        self.worth_card = QFrame()
        self.worth_card.setObjectName("WorthCard")
        worth_layout = QHBoxLayout(self.worth_card)
        worth_layout.setContentsMargins(10, 10, 10, 10)
        worth_layout.setSpacing(10)

        self.worth_dot = QFrame()
        self.worth_dot.setObjectName("WorthDot")
        self.worth_dot.setFixedSize(16, 16)

        worth_text = QVBoxLayout()
        worth_text.setContentsMargins(0, 0, 0, 0)
        worth_text.setSpacing(3)

        self.worth_title = QLabel("Worth: choose a model")
        self.worth_title.setObjectName("WorthTitle")

        self.worth_detail = QLabel("Worth blends source trust, popularity, file quality, search match, and GPU fit.")
        self.worth_detail.setObjectName("WorthDetail")
        self.worth_detail.setWordWrap(True)

        worth_text.addWidget(self.worth_title)
        worth_text.addWidget(self.worth_detail)
        worth_layout.addWidget(self.worth_dot, alignment=Qt.AlignTop)
        worth_layout.addLayout(worth_text, stretch=1)

        self.run_plan_card = QFrame()
        self.run_plan_card.setObjectName("RunPlanCard")
        run_plan_layout = QHBoxLayout(self.run_plan_card)
        run_plan_layout.setContentsMargins(10, 10, 10, 10)
        run_plan_layout.setSpacing(10)

        self.run_plan_dot = QFrame()
        self.run_plan_dot.setObjectName("RunPlanDot")
        self.run_plan_dot.setFixedSize(16, 16)

        run_plan_text = QVBoxLayout()
        run_plan_text.setContentsMargins(0, 0, 0, 0)
        run_plan_text.setSpacing(3)

        self.run_plan_title = QLabel("Run plan: choose a model")
        self.run_plan_title.setObjectName("RunPlanTitle")

        self.run_plan_detail = QLabel("MORICE will explain context and GPU-offload expectations here.")
        self.run_plan_detail.setObjectName("RunPlanDetail")
        self.run_plan_detail.setWordWrap(True)

        run_plan_text.addWidget(self.run_plan_title)
        run_plan_text.addWidget(self.run_plan_detail)
        run_plan_layout.addWidget(self.run_plan_dot, alignment=Qt.AlignTop)
        run_plan_layout.addLayout(run_plan_text, stretch=1)

        self.model_detail_card = QFrame()
        self.model_detail_card.setObjectName("ModelDetailCard")
        model_detail_layout = QVBoxLayout(self.model_detail_card)
        model_detail_layout.setContentsMargins(10, 10, 10, 10)
        model_detail_layout.setSpacing(5)

        self.speciality_title = QLabel("Model speciality")
        self.speciality_title.setObjectName("SpecialityTitle")

        self.speciality_detail = QLabel("Choose a result to see what that AI model is best at.")
        self.speciality_detail.setObjectName("SpecialityDetail")
        self.speciality_detail.setWordWrap(True)

        self.source_detail = QLabel("Trusted source details will appear here.")
        self.source_detail.setObjectName("SourceDetail")
        self.source_detail.setWordWrap(True)
        self.source_detail.setTextFormat(Qt.RichText)
        self.source_detail.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.source_detail.setOpenExternalLinks(True)

        model_detail_layout.addWidget(self.speciality_title)
        model_detail_layout.addWidget(self.speciality_detail)
        model_detail_layout.addWidget(self.source_detail)

        self.progress = QProgressBar()
        self.progress.setObjectName("ModelProgress")
        self.progress.setVisible(False)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        self.install_btn = QPushButton("Install and use")
        self.install_btn.setObjectName("ModelPrimaryButton")
        self.install_btn.clicked.connect(self._start_install)
        self.install_btn.setEnabled(False)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("ModelCancelButton")
        close_btn.clicked.connect(self.reject)

        button_row.addWidget(self.install_btn)
        button_row.addWidget(close_btn)

        layout.addWidget(title)
        layout.addWidget(source)
        layout.addWidget(self.browser_map)
        layout.addLayout(gpu_row)
        layout.addLayout(search_row)
        layout.addLayout(quick_row)
        layout.addWidget(self.results, stretch=1)
        layout.addWidget(self.compatibility_card)
        layout.addWidget(self.worth_card)
        layout.addWidget(self.run_plan_card)
        layout.addWidget(self.model_detail_card)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addLayout(button_row)

        self.search_finished.connect(self._on_search_finished)
        self.download_progress.connect(self._on_download_progress)
        self.download_finished.connect(self._on_download_finished)
        self.gpu_detected.connect(self._on_gpu_detected)
        self.setStyleSheet(
            """
            QDialog {
                background: #050711;
                color: #f6f1ff;
            }
            #ModelGalaxySurface {
                border-radius: 16px;
                border: 1px solid rgba(150,190,255,0.22);
            }
            #ModelDialogTitle {
                font-size: 20px;
                font-weight: 900;
            }
            #ModelDialogSource {
                color: rgba(178,230,210,0.82);
                font-weight: 700;
            }
            #ModelBrowserMap {
                background: rgba(5,12,20,0.58);
                color: rgba(225,238,245,0.84);
                border-radius: 12px;
                padding: 9px 11px;
                border: 1px solid rgba(95,215,235,0.16);
                font-size: 12px;
            }
            #ModelGpuChip {
                background: rgba(28,48,42,0.72);
                color: rgba(225,255,238,0.92);
                border-radius: 9px;
                padding: 8px 10px;
                border: 1px solid rgba(125,210,160,0.24);
                font-size: 12px;
                font-weight: 800;
            }
            #ModelSearchInput {
                background: rgba(5,8,18,0.72);
                border-radius: 14px;
                padding: 10px 12px;
                border: 1px solid rgba(145,190,255,0.28);
                selection-background-color: rgba(178,96,255,0.45);
            }
            #ModelSearchInput:focus {
                border: 1px solid rgba(120,230,255,0.68);
                background: rgba(8,12,26,0.9);
            }
            #ModelResultList {
                background: rgba(1,3,10,0.52);
                border-radius: 14px;
                padding: 8px;
                border: 1px solid rgba(128,170,255,0.2);
                color: rgba(245,239,255,0.94);
                selection-background-color: rgba(58,120,190,0.82);
            }
            #ModelResultList::item {
                background: rgba(12,16,31,0.74);
                border: 1px solid rgba(135,190,255,0.12);
                border-radius: 12px;
                padding: 10px;
                margin: 3px;
            }
            #ModelResultList::item:hover {
                background: rgba(25,34,60,0.88);
                border: 1px solid rgba(120,230,255,0.34);
            }
            #ModelResultList::item:selected {
                background: rgba(52,72,126,0.95);
                border: 1px solid rgba(175,230,255,0.62);
            }
            #ModelStatus {
                color: rgba(224,216,240,0.82);
                min-height: 20px;
            }
            #CompatibilityCard {
                background: rgba(4,8,18,0.62);
                border-radius: 12px;
                border: 1px solid rgba(178,130,255,0.18);
            }
            #WorthCard {
                background: rgba(4,8,18,0.62);
                border-radius: 12px;
                border: 1px solid rgba(125,210,160,0.18);
            }
            #RunPlanCard {
                background: rgba(4,8,18,0.62);
                border-radius: 12px;
                border: 1px solid rgba(95,215,235,0.18);
            }
            #CompatibilityDot {
                border-radius: 8px;
                background: #aeb4bf;
                border: 1px solid rgba(255,255,255,0.22);
            }
            #WorthDot {
                border-radius: 8px;
                background: #aeb4bf;
                border: 1px solid rgba(255,255,255,0.22);
            }
            #RunPlanDot {
                border-radius: 8px;
                background: #aeb4bf;
                border: 1px solid rgba(255,255,255,0.22);
            }
            #CompatibilityTitle {
                color: #ffffff;
                font-size: 13px;
                font-weight: 900;
            }
            #WorthTitle {
                color: #ffffff;
                font-size: 13px;
                font-weight: 900;
            }
            #RunPlanTitle {
                color: #ffffff;
                font-size: 13px;
                font-weight: 900;
            }
            #CompatibilityDetail {
                color: rgba(224,216,240,0.78);
                font-size: 12px;
            }
            #WorthDetail {
                color: rgba(224,238,224,0.8);
                font-size: 12px;
            }
            #RunPlanDetail {
                color: rgba(224,238,245,0.82);
                font-size: 12px;
            }
            #ModelDetailCard {
                background: rgba(4,10,18,0.64);
                border-radius: 12px;
                border: 1px solid rgba(95,215,235,0.16);
            }
            #SpecialityTitle {
                color: #ffffff;
                font-size: 13px;
                font-weight: 900;
            }
            #SpecialityDetail,
            #SourceDetail {
                color: rgba(224,238,245,0.82);
                font-size: 12px;
            }
            #SourceDetail a {
                color: rgba(135,230,255,0.96);
            }
            #ModelPrimaryButton {
                background: rgba(58,82,154,0.86);
                color: #fff;
                border-radius: 14px;
                padding: 10px 14px;
                border: 1px solid rgba(150,215,255,0.42);
                font-weight: 800;
            }
            #ModelPrimaryButton:hover {
                background: rgba(88,78,220,0.96);
            }
            #ModelSecondaryButton,
            #ModelLaneButton {
                background: rgba(22,28,42,0.86);
                color: rgba(245,250,255,0.92);
                border-radius: 12px;
                padding: 9px 12px;
                border: 1px solid rgba(150,215,255,0.24);
                font-weight: 800;
            }
            #ModelSecondaryButton:hover,
            #ModelLaneButton:hover {
                background: rgba(45,68,96,0.94);
                border: 1px solid rgba(150,230,255,0.48);
            }
            #ModelPrimaryButton:disabled {
                background: rgba(50,50,56,0.68);
                color: rgba(255,255,255,0.42);
                border: 1px solid rgba(255,255,255,0.08);
            }
            #ModelCancelButton {
                background: rgba(22,28,42,0.86);
                color: rgba(255,255,255,0.86);
                border-radius: 14px;
                padding: 10px 14px;
                border: 1px solid rgba(170,210,255,0.14);
            }
            #ModelProgress {
                border-radius: 8px;
                background: rgba(255,255,255,0.08);
                color: #fff;
                text-align: center;
            }
            #ModelProgress::chunk {
                border-radius: 8px;
                background: rgba(138,84,235,0.95);
            }
            """
        )
        self.galaxy_surface.watch(self)
        if not self.gpu_profile.detected or self.gpu_profile.vram_mb <= 0:
            QTimer.singleShot(140, lambda: self._detect_gpu_profile(auto=True))
        else:
            QTimer.singleShot(140, self._start_recommended_search)

    def _recommended_query(self) -> str:
        vram = self.gpu_profile.vram_mb if self.gpu_profile else 0
        if not vram:
            return "qwen2.5 3b gguf"
        if vram and vram < 5_500:
            return "qwen2.5 3b gguf"
        return "qwen2.5 coder 7b gguf"

    def _start_recommended_search(self):
        if self._auto_search_started or self.results.count() > 0:
            return
        self._auto_search_started = True
        self._quick_search("")

    def _quick_search(self, query: str):
        self.search_input.setText(query or self._recommended_query())
        self._start_search()

    def _detect_gpu_profile(self, auto: bool = False):
        if self._gpu_detection_busy:
            return
        self._gpu_detection_busy = True
        self.dialog_detect_gpu_btn.setEnabled(False)
        self.gpu_chip.setText("Detecting GPU and VRAM...")
        if not auto:
            self.status.setText("Detecting GPU/VRAM so model fit is not a guess.")

        def worker():
            profile = detect_gpu_profile()
            self._emit_background("gpu_detected", profile)

        _start_background_task("model-gpu-detection", worker)

    def _on_gpu_detected(self, profile: GpuProfile):
        self._gpu_detection_busy = False
        self.gpu_profile = profile
        self.dialog_detect_gpu_btn.setEnabled(not self._busy)
        self.gpu_chip.setText(gpu_profile_summary(profile))
        self.gpu_chip.setToolTip(profile.message)
        if profile.detected:
            self.status.setText(f"GPU detected: {gpu_profile_summary(profile)}")
        else:
            self.status.setText(profile.message)
        for index in range(self.results.count()):
            item = self.results.item(index)
            result = item.data(Qt.UserRole)
            if isinstance(result, dict):
                compatibility = model_compatibility(result, self.gpu_profile)
                item.setForeground(QBrush(QColor(compatibility.color)))
        self._refresh_compatibility()
        self._start_recommended_search()

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.search_btn.setEnabled(not busy)
        self.search_input.setEnabled(not busy)
        self.results.setEnabled(not busy)
        self.dialog_detect_gpu_btn.setEnabled((not busy) and not self._gpu_detection_busy)
        for button in self.quick_buttons:
            button.setEnabled(not busy)
        self._refresh_install_state()

    def _refresh_install_state(self):
        self.install_btn.setEnabled((not self._busy) and bool(self.results.selectedItems()))
        self._refresh_compatibility()

    def _refresh_compatibility(self):
        selected = self.results.selectedItems()
        if not selected:
            self.compatibility_title.setText("Compatibility: choose a model")
            self.compatibility_detail.setText(
                "Red means very low, yellow medium, green good, and dark green excellent."
            )
            self.speciality_title.setText("Model speciality")
            self.speciality_detail.setText("Choose a result to see what that AI model is best at.")
            self.source_detail.setText("Trusted source details will appear here.")
            self.compatibility_dot.setStyleSheet("background: #aeb4bf; border-radius: 8px;")
            self.worth_title.setText("Worth: choose a model")
            self.worth_detail.setText("Worth blends source trust, popularity, file quality, search match, and GPU fit.")
            self.worth_dot.setStyleSheet("background: #aeb4bf; border-radius: 8px;")
            self.run_plan_title.setText("Run plan: choose a model")
            self.run_plan_detail.setText("MORICE will explain context and GPU-offload expectations here.")
            self.run_plan_dot.setStyleSheet("background: #aeb4bf; border-radius: 8px;")
            self.install_btn.setText("Install and use")
            self.install_btn.setToolTip("")
            return
        result = selected[0].data(Qt.UserRole)
        if not isinstance(result, dict):
            return
        compatibility = model_compatibility(result, self.gpu_profile)
        self.compatibility_title.setText(
            f"Compatibility: {compatibility.label} ({compatibility.score}/100)"
            if compatibility.score
            else f"Compatibility: {compatibility.label}"
        )
        self.compatibility_detail.setText(compatibility.message)
        self.compatibility_dot.setStyleSheet(
            f"background: {compatibility.color}; border-radius: 8px;"
        )
        worth = model_worth(result, compatibility)
        self.worth_title.setText(f"Worth: {worth.label} ({worth.score}/100)")
        self.worth_detail.setText(worth.message)
        self.worth_dot.setStyleSheet(f"background: {worth.color}; border-radius: 8px;")
        run_plan = model_run_plan(result, self.gpu_profile)
        self.run_plan_title.setText(f"Run plan: {run_plan.label}")
        self.run_plan_detail.setText(f"{run_plan.message} {run_plan.context_hint} {run_plan.offload_hint}")
        self.run_plan_dot.setStyleSheet(f"background: {run_plan.color}; border-radius: 8px;")
        self.install_btn.setText("Install anyway" if compatibility.level in {"cpu-assisted", "very-low"} else "Install and use")
        self.speciality_title.setText(f"{result.get('family') or 'Model'} speciality")
        self.speciality_detail.setText(result.get("speciality") or "Best for general local assistant work.")
        repo_url = html.escape(result.get("detail_url") or "")
        official_url = html.escape(result.get("official_url") or repo_url)
        source_label = html.escape(result.get("source_label") or "Hugging Face model repo")
        license_text = html.escape(result.get("license") or "License not listed")
        pipeline = html.escape(result.get("pipeline_tag") or "text-generation")
        self.source_detail.setText(
            f"{source_label} | Task: {pipeline} | License: {license_text}<br>"
            f"<a href=\"{repo_url}\">Hugging Face repo</a> | "
            f"<a href=\"{official_url}\">Official/source page</a>"
        )
        self.install_btn.setToolTip(f"{compatibility.message}\n{run_plan.message}\n{worth.message}")

    def _start_search(self):
        query = " ".join(self.search_input.text().split())
        if not query:
            self.status.setText("Type a model name first.")
            return
        self.results.clear()
        self.progress.setVisible(False)
        self.status.setText("Searching trusted model sources...")
        self._set_busy(True)

        def worker():
            try:
                results = search_huggingface_gguf(query)
                error = ""
            except Exception as exc:  # noqa: BLE001
                results = []
                error = str(exc)
            self._emit_background("search_finished", results, error)

        _start_background_task("model-search", worker)

    def _on_search_finished(self, results: list[dict], error: str):
        self._set_busy(False)
        if error:
            self.status.setText(f"Search failed: {error}")
            return
        if not results:
            self.status.setText("No trusted GGUF model files found for that search.")
            return

        def result_rank(result: dict) -> tuple[int, int, int, int]:
            compatibility = model_compatibility(result, self.gpu_profile)
            worth = model_worth(result, compatibility)
            fit_score = compatibility.score if compatibility.score else 50
            return (
                fit_score,
                worth.score,
                int(result.get("downloads") or 0),
                int(result.get("file_score") or 0),
            )

        ranked_results = sorted(results, key=result_rank, reverse=True)
        for result in ranked_results:
            downloads = int(result.get("downloads") or 0)
            compatibility = model_compatibility(result, self.gpu_profile)
            worth = model_worth(result, compatibility)
            run_plan = model_run_plan(result, self.gpu_profile)
            fit_line = (
                f"GPU fit: {compatibility.label} ({compatibility.score}/100)"
                if compatibility.score
                else f"GPU fit: {compatibility.label}"
            )
            item = QListWidgetItem(
                f"{result.get('title', 'Model')}\n"
                f"{result.get('size_text') or format_size(result.get('size'))} | "
                f"{downloads:,} downloads | {fit_line} | Run: {run_plan.label} | Worth: {worth.score}/100\n"
                f"{result.get('source_label', 'Hugging Face')} | {result.get('speciality', '')}"
            )
            item.setData(Qt.UserRole, result)
            item.setToolTip(result.get("detail_url", ""))
            item.setForeground(QBrush(QColor(compatibility.color)))
            item.setSizeHint(QSize(0, 92))
            self.results.addItem(item)
        self.status.setText(f"Found {len(results)} GGUF model file(s), sorted by detected GPU fit and model worth.")
        if self.results.count() > 0:
            self.results.setCurrentRow(0)

    def _start_install(self):
        selected = self.results.selectedItems()
        if not selected:
            return
        result = selected[0].data(Qt.UserRole)
        if not isinstance(result, dict):
            return
        self._set_busy(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status.setText("Installing selected model...")

        def progress(percent: int, message: str):
            self._emit_background("download_progress", percent, message)

        def worker():
            try:
                path = download_model_result(result, default_model_download_dir(), progress)
                error = ""
            except Exception as exc:  # noqa: BLE001
                path = ""
                error = str(exc)
            self._emit_background("download_finished", path, error)

        _start_background_task("model-download", worker)

    def _on_download_progress(self, percent: int, message: str):
        if percent > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, percent))
        self.status.setText(message)

    def _on_download_finished(self, path: str, error: str):
        self._set_busy(False)
        if error:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.status.setText(f"Install failed: {error}")
            return
        self.selected_path = path
        selected = self.results.selectedItems()
        result = selected[0].data(Qt.UserRole) if selected else {}
        if not isinstance(result, dict):
            result = local_model_result(path)
        compatibility = model_compatibility(result, self.gpu_profile)
        run_plan = model_run_plan(result, self.gpu_profile)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText(
            f"Installed and selected. GPU fit: {compatibility.label}. Run plan: {run_plan.label}."
        )
        QTimer.singleShot(650, self.accept)

    def closeEvent(self, event):
        self._is_closing = True
        super().closeEvent(event)


def _inline_markdown_to_rich_text(text: str) -> str:
    safe = html.escape(text, quote=False)
    safe = re.sub(
        r"([\u2600-\u27bf\U0001f300-\U0001faff]\ufe0f?)",
        r'<span style="font-family: Segoe UI Emoji;">\1</span>',
        safe,
    )
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


def _web_assets_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "web")


def _needs_web_rich_text(message: str) -> bool:
    text = message or ""
    return bool(
        re.search(
            r"(?:```|`[^`\n]+`|\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|"
            r"\\\([\s\S]+?\\\)|(?<!\\)\$[^$\n]+\$|^\s*\|.+\|\s*$)",
            text,
            flags=re.MULTILINE,
        )
    )


class RichContentView(QWebEngineView if QWebEngineView is not None else QWidget):
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.setObjectName("RichContentView")
        self.setFixedHeight(80)
        self.setMaximumHeight(1400)
        if QWebEngineView is None:
            fallback_layout = QVBoxLayout(self)
            fallback = QLabel(message)
            fallback.setWordWrap(True)
            fallback.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
            )
            fallback_layout.addWidget(fallback)
            return
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.loadFinished.connect(lambda _ok: QTimer.singleShot(0, self._measure_content))
        source = json.dumps(message or "", ensure_ascii=False).replace("</", "<\\/")
        tokens = THEMES[normalize_theme(_ACTIVE_UI_THEME)]
        font_family = normalize_font_family(_ACTIVE_UI_FONT_FAMILY)
        font_css = font_family.replace("\\", "\\\\").replace('"', '\\"')
        code_background = "rgba(5, 7, 12, .82)" if tokens.name == "dark" else "rgba(225, 231, 236, .92)"
        quote_color = "#cbd5e5" if tokens.name == "dark" else "#526171"
        table_border = "rgba(255,255,255,.16)" if tokens.name == "dark" else "rgba(22,27,34,.18)"
        document = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <link rel="stylesheet" href="katex.min.css">
  <link rel="stylesheet" href="github-dark.min.css">
  <style>
    :root {{ --ui-font: "{font_css}"; --text: {tokens.text}; --muted: {quote_color};
      --code-bg: {code_background}; --table-border: {table_border}; }}
    html, body {{ margin: 0; padding: 0; background: transparent; color: var(--text);
      font: 15px/1.58 var(--ui-font), "Segoe UI Emoji", "Segoe UI", sans-serif; letter-spacing: 0; }}
    body {{ overflow-x: hidden; overflow-y: auto; }}
    p {{ margin: 0 0 10px; }}
    h1, h2, h3, h4 {{ margin: 12px 0 7px; line-height: 1.25; }}
    h1 {{ font-size: 21px; }} h2 {{ font-size: 19px; }} h3 {{ font-size: 17px; }}
    ul, ol {{ margin: 6px 0 10px 24px; padding: 0; }}
    li {{ margin: 3px 0; }}
    code {{ font-family: "Cascadia Code", Consolas, monospace; font-size: 0.94em; }}
    :not(pre) > code {{ background: rgba(119, 92, 190, .18); border: 1px solid
      rgba(153, 119, 229, .22); padding: 2px 5px; border-radius: 4px; }}
    pre {{ overflow-x: auto; padding: 12px; background: var(--code-bg);
      border: 1px solid rgba(153, 119, 229, .28); border-radius: 6px; }}
    blockquote {{ margin: 8px 0; padding: 2px 12px; color: var(--muted);
      border-left: 3px solid #8c64e8; }}
    table {{ width: 100%; border-collapse: collapse; margin: 9px 0; }}
    th, td {{ border: 1px solid var(--table-border); padding: 7px 9px;
      text-align: left; }}
    th {{ background: rgba(68, 91, 158, .28); }}
    .katex-display {{ overflow-x: auto; overflow-y: hidden; padding: 7px 0; }}
    a {{ color: #74c9ff; }}
  </style>
</head>
<body><main id="content"></main>
<script src="markdown-it.min.js"></script>
<script src="katex.min.js"></script>
<script src="auto-render.min.js"></script>
<script src="highlight.min.js"></script>
<script>
  const source = {source};
  const md = window.markdownit({{html: false, linkify: true, typographer: true}});
  document.getElementById("content").innerHTML = md.render(source);
  renderMathInElement(document.getElementById("content"), {{
    throwOnError: false,
    strict: "warn",
    delimiters: [
      {{left: "$$", right: "$$", display: true}},
      {{left: "\\\\[", right: "\\\\]", display: true}},
      {{left: "\\\\(", right: "\\\\)", display: false}},
      {{left: "$", right: "$", display: false}}
    ]
  }});
  document.querySelectorAll("pre code").forEach((block) => hljs.highlightElement(block));
</script>
</body>
</html>"""
        self.setHtml(document, QUrl.fromLocalFile(_web_assets_path() + os.sep))

    def apply_appearance(self, theme: str, font_family: str):
        if QWebEngineView is None:
            return
        tokens = THEMES[normalize_theme(theme)]
        family = normalize_font_family(font_family)
        code_background = (
            "rgba(5, 7, 12, .82)"
            if tokens.name == "dark"
            else "rgba(225, 231, 236, .92)"
        )
        quote_color = "#cbd5e5" if tokens.name == "dark" else "#526171"
        table_border = (
            "rgba(255,255,255,.16)"
            if tokens.name == "dark"
            else "rgba(22,27,34,.18)"
        )
        values = {
            "--ui-font": family,
            "--text": tokens.text,
            "--muted": quote_color,
            "--code-bg": code_background,
            "--table-border": table_border,
        }
        payload = json.dumps(values, ensure_ascii=False)
        self.page().runJavaScript(
            "const values="
            + payload
            + "; for (const [key,value] of Object.entries(values)) "
            + "document.documentElement.style.setProperty(key,value);"
        )

    def _measure_content(self):
        if QWebEngineView is None:
            return
        self.page().runJavaScript(
            "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)",
            self._resize_to_content,
        )

    def _resize_to_content(self, value):
        try:
            height = max(80, min(1400, int(math.ceil(float(value))) + 6))
        except (TypeError, ValueError):
            return
        self.setFixedHeight(height)



class ComposerStageFrame(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("ComposerStage")
        self.theme_name = "dark"
        self._wave_phase = 0.0
        self._wave_timer = QTimer(self)
        self._wave_timer.timeout.connect(self._advance_wave)
        self._wave_timer.start(45)

    def set_theme(self, theme: str):
        self.theme_name = "light" if theme == "light" else "dark"
        self.update()

    def _advance_wave(self):
        if not self.isVisible() or self.window().isMinimized():
            return
        self._wave_phase = (self._wave_phase + 0.16) % (math.pi * 2)
        self.update()

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        width = max(1, rect.width())
        height = max(1, rect.height())

        painter.fillRect(
            rect,
            QColor(238, 242, 245, 246)
            if self.theme_name == "light"
            else QColor(7, 7, 12, 232),
        )
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
    edit_requested = Signal(str)
    reaction_changed = Signal(str)

    def __init__(self, author: str, message: str, is_user: bool = False):
        super().__init__()
        self.author = str(author or "")
        self.message = str(message or "")
        self.is_user = bool(is_user)
        self._message_label: QLabel | None = None
        self._reaction = ""
        self.setObjectName("ChatBubble")
        self.setMaximumWidth(16777215)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(5)
        author_label = QLabel(self.author)
        author_label.setObjectName("AuthorLabel")
        author_label.setTextFormat(Qt.PlainText)
        author_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        author_label.setFocusPolicy(Qt.StrongFocus)
        timestamp = QLabel(datetime.now().strftime("%H:%M"))
        timestamp.setObjectName("MessageMeta")
        timestamp.setToolTip(datetime.now().strftime("%A, %d %B %Y at %H:%M"))
        timestamp.setAccessibleName("Message timestamp")
        copy_button = self._action_button(
            QApplication.style().standardIcon(QStyle.SP_DialogSaveButton),
            "Copy message",
            self._copy_message,
        )
        header.addWidget(author_label)
        header.addStretch(1)
        header.addWidget(timestamp)
        header.addWidget(copy_button)
        if is_user:
            edit_button = self._action_button(
                QApplication.style().standardIcon(QStyle.SP_FileDialogDetailedView),
                "Edit this message in the composer",
                lambda: self.edit_requested.emit(self.message),
            )
            header.addWidget(edit_button)
        reaction_button = QPushButton("M+")
        reaction_button.setObjectName("MessageAction")
        reaction_button.setFixedSize(26, 26)
        reaction_button.setToolTip("React to this message")
        reaction_button.setAccessibleName("React to message")
        reaction_button.clicked.connect(self._cycle_reaction)
        self.reaction_button = reaction_button
        header.addWidget(reaction_button)
        layout.addLayout(header)
        if QWebEngineView is not None and _needs_web_rich_text(self.message):
            layout.addWidget(RichContentView(self.message, self))
        else:
            message_label = QLabel(self.message)
            message_label.setWordWrap(True)
            message_label.setObjectName("MessageLabel")
            message_label.setText(_message_to_rich_text(self.message))
            message_label.setTextFormat(Qt.RichText)
            message_label.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
            )
            message_label.setFocusPolicy(Qt.StrongFocus)
            self._message_label = message_label
            layout.addWidget(message_label)

        self.setProperty("user", "true" if is_user else "false")
        self.setAccessibleName(f"{self.author} message")

    def set_message(self, message: str) -> None:
        """Update an in-progress response without rebuilding the chat row."""

        self.message = str(message or "")
        if self._message_label is not None:
            self._message_label.setText(_message_to_rich_text(self.message))
            self._message_label.adjustSize()

    @staticmethod
    def _action_button(icon: QIcon, tooltip: str, callback) -> QPushButton:
        button = QPushButton()
        button.setObjectName("MessageAction")
        button.setIcon(icon)
        button.setFixedSize(26, 26)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.clicked.connect(callback)
        return button

    def _copy_message(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.message)

    def _cycle_reaction(self) -> None:
        choices = ("", "M^", "Mv")
        self._reaction = choices[(choices.index(self._reaction) + 1) % len(choices)]
        self.reaction_button.setText(self._reaction or "M+")
        self.reaction_changed.emit(self._reaction)


class AdaptivePromptEdit(QTextEdit):
    returnPressed = Signal()
    historyRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setTabChangesFocus(True)
        self.setMinimumHeight(44)
        self.setMaximumHeight(132)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.textChanged.connect(self._resize_to_document)
        self._resize_to_document()

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, text: str) -> None:
        self.setPlainText(str(text or ""))

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key_Return, Qt.Key_Enter} and not (
            event.modifiers() & Qt.ShiftModifier
        ):
            self.returnPressed.emit()
            event.accept()
            return
        if (
            event.key() in {Qt.Key_Up, Qt.Key_Down}
            and "\n" not in self.toPlainText()
            and not (event.modifiers() & Qt.ShiftModifier)
        ):
            self.historyRequested.emit(-1 if event.key() == Qt.Key_Up else 1)
            event.accept()
            return
        super().keyPressEvent(event)

    def _resize_to_document(self) -> None:
        document_height = int(self.document().size().height()) + 20
        target = max(44, min(132, document_height))
        self.setFixedHeight(target)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if document_height > 132 else Qt.ScrollBarAlwaysOff
        )


class ThinkingBubble(QFrame):
    def __init__(self, detail: str):
        super().__init__()
        self.setObjectName("ThinkingBubble")
        self._visible = True
        self._stages: list[tuple[str, str]] = []

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
        stage = self._stage_for_detail(detail)
        if self._stages and self._stages[-1] == (stage, detail):
            return
        if self._stages and self._stages[-1][0] == stage:
            self._stages[-1] = (stage, detail)
        else:
            self._stages.append((stage, detail))
        self._stages = self._stages[-7:]
        lines: list[str] = []
        for index, (label, text) in enumerate(self._stages):
            state = "[active]" if index == len(self._stages) - 1 else "[done]"
            lines.append(f"{state} {label}")
            lines.append(f"         {text}")
        self.detail_label.setText("\n".join(lines))

    @staticmethod
    def _stage_for_detail(detail: str) -> str:
        lowered = detail.lower()
        if any(word in lowered for word in ("received", "request", "message")):
            return "Understanding request"
        if any(word in lowered for word in ("context", "notes", "reading", "search")):
            return "Gathering context"
        if any(word in lowered for word in ("mode", "rules", "folder", "plan")):
            return "Planning"
        if any(word in lowered for word in ("applying", "files", "execut", "command")):
            return "Executing"
        if any(word in lowered for word in ("render", "visual", "prepare")):
            return "Preparing output"
        if any(word in lowered for word in ("asking", "generating", "compose", "qwen")):
            return "Generating response"
        return "Finalizing"

    def finish(self):
        self._stages.append(("Complete", "The result is ready below."))
        lines: list[str] = []
        for label, text in self._stages[-7:]:
            lines.append(f"[done] {label}")
            lines.append(f"         {text}")
        self.detail_label.setText("\n".join(lines))
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

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(18, 15, 27, 218))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 9, 9)

        line_width = 17
        left = (rect.width() - line_width) // 2
        ys = (10, 16, 22)
        for y in ys:
            pen = QPen(QColor(255, 255, 255, 238), 1.6)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(left, y, left + line_width, y)


class SendButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("SendButton")
        self.setCursor(Qt.PointingHandCursor)
        self._ready = False

    def set_ready(self, ready: bool):
        ready = bool(ready)
        if ready == self._ready:
            return
        self._ready = ready
        self.setProperty("ready", "true" if ready else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class GraphCanvas(QWidget):
    inspected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("GraphCanvas")
        self.setMinimumHeight(300)
        self.setMouseTracking(True)
        self.artifact: GraphArtifact | None = None
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._drag_start = QPoint()
        self._dragging = False
        self._last_mouse = QPoint()

    def set_artifact(self, artifact: GraphArtifact | None):
        self.artifact = artifact
        self.reset_view()

    def reset_view(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def export_png(self, path: str) -> bool:
        return bool(path and self.grab().save(path, "PNG"))

    def export_svg(self, path: str) -> bool:
        if not path:
            return False
        generator = QSvgGenerator()
        generator.setFileName(path)
        generator.setSize(self.size())
        generator.setViewBox(self.rect())
        generator.setTitle(self.artifact.title if self.artifact else "MORICE graph")
        generator.setDescription("Interactive graph exported from MORICE")
        painter = QPainter(generator)
        try:
            self.render(painter, QPoint())
        finally:
            painter.end()
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def export_pdf(self, path: str) -> bool:
        if not path:
            return False
        writer = QPdfWriter(path)
        writer.setTitle(self.artifact.title if self.artifact else "MORICE graph")
        writer.setCreator("MORICE")
        writer.setResolution(144)
        painter = QPainter(writer)
        viewport = painter.viewport()
        target = self.size()
        target.scale(viewport.size(), Qt.KeepAspectRatio)
        painter.setViewport(
            viewport.x() + (viewport.width() - target.width()) // 2,
            viewport.y() + (viewport.height() - target.height()) // 2,
            target.width(),
            target.height(),
        )
        painter.setWindow(self.rect())
        try:
            self.render(painter, QPoint())
        finally:
            painter.end()
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def _ranges(self) -> tuple[float, float, float, float]:
        if not self.artifact:
            return -10.0, 10.0, -10.0, 10.0
        x0, x1 = self.artifact.x_range
        y0, y1 = self.artifact.y_range
        cx = (x0 + x1) / 2 + self.pan_x
        cy = (y0 + y1) / 2 + self.pan_y
        half_x = max(0.001, (x1 - x0) / (2 * self.zoom))
        half_y = max(0.001, (y1 - y0) / (2 * self.zoom))
        return cx - half_x, cx + half_x, cy - half_y, cy + half_y

    def _to_screen(self, x: float, y: float, rect: QRect) -> QPoint:
        x0, x1, y0, y1 = self._ranges()
        px = rect.left() + int(((x - x0) / max(1e-9, x1 - x0)) * rect.width())
        py = rect.bottom() - int(((y - y0) / max(1e-9, y1 - y0)) * rect.height())
        return QPoint(px, py)

    def _to_world(self, point: QPoint, rect: QRect) -> tuple[float, float]:
        x0, x1, y0, y1 = self._ranges()
        x = x0 + ((point.x() - rect.left()) / max(1, rect.width())) * (x1 - x0)
        y = y1 - ((point.y() - rect.top()) / max(1, rect.height())) * (y1 - y0)
        return x, y

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self.zoom = max(0.18, min(18.0, self.zoom * (1.12 if delta > 0 else 0.88)))
            self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = event.position().toPoint()
            self._last_mouse = self._drag_start
            event.accept()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        plot = self.rect().adjusted(58, 30, -18, -56)
        if self._dragging:
            x0, x1, y0, y1 = self._ranges()
            dx = pos.x() - self._last_mouse.x()
            dy = pos.y() - self._last_mouse.y()
            self.pan_x -= dx / max(1, plot.width()) * (x1 - x0)
            self.pan_y += dy / max(1, plot.height()) * (y1 - y0)
            self._last_mouse = pos
            self.update()
        elif self.artifact and plot.contains(pos):
            x, y = self._to_world(pos, plot)
            nearest = ""
            best = 999999.0
            for series in self.artifact.series:
                for sx, sy in zip(series.x[::8], series.y[::8]):
                    if not math.isfinite(sy):
                        continue
                    distance = abs(sx - x) + abs(sy - y)
                    if distance < best:
                        best = distance
                        nearest = f"{series.label}: x={sx:.3g}, y={sy:.3g}"
            self.inspected.emit(nearest or f"x={x:.3g}, y={y:.3g}")
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        plot = rect.adjusted(58, 30, -18, -56)
        painter.fillRect(rect, QColor(5, 7, 12, 235))
        painter.setPen(QPen(QColor(150, 120, 225, 70), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 12, 12)

        if not self.artifact:
            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(rect, Qt.AlignCenter, "No graph generated yet")
            return

        x0, x1, y0, y1 = self._ranges()
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1))
        for i in range(11):
            x = plot.left() + int(plot.width() * i / 10)
            y = plot.top() + int(plot.height() * i / 10)
            painter.drawLine(x, plot.top(), x, plot.bottom())
            painter.drawLine(plot.left(), y, plot.right(), y)
            x_value = x0 + (x1 - x0) * i / 10
            y_value = y1 - (y1 - y0) * i / 10
            painter.setPen(QColor(195, 205, 225, 150))
            painter.drawText(QRect(x - 28, plot.bottom() + 5, 56, 18), Qt.AlignHCenter | Qt.AlignTop, f"{x_value:.3g}")
            painter.drawText(QRect(2, y - 9, 40, 18), Qt.AlignRight | Qt.AlignVCenter, f"{y_value:.3g}")
            painter.setPen(QPen(QColor(255, 255, 255, 42), 1))

        zero = self._to_screen(0.0, 0.0, plot)
        painter.setPen(QPen(QColor(255, 255, 255, 96), 1))
        if plot.left() <= zero.x() <= plot.right():
            painter.drawLine(zero.x(), plot.top(), zero.x(), plot.bottom())
        if plot.top() <= zero.y() <= plot.bottom():
            painter.drawLine(plot.left(), zero.y(), plot.right(), zero.y())

        painter.setClipRect(plot)
        for series in self.artifact.series:
            path = QPainterPath()
            started = False
            for sx, sy in zip(series.x, series.y):
                if not math.isfinite(sy) or sx < x0 or sx > x1 or sy < y0 or sy > y1:
                    started = False
                    continue
                point = self._to_screen(sx, sy, plot)
                if not started:
                    path.moveTo(point)
                    started = True
                else:
                    path.lineTo(point)
            painter.setPen(QPen(QColor(series.color), 2))
            painter.drawPath(path)
        painter.setClipping(False)

        occupied_labels: list[QRect] = []
        labels_drawn = 0
        label_priority = {
            "y-intercept": 0,
            "maximum": 1,
            "minimum": 1,
            "inflection": 2,
            "x-intercept": 3,
        }
        for series in self.artifact.series:
            marker_color = QColor(series.color)
            inspections = sorted(
                series.inspection_points[:14],
                key=lambda point: (
                    label_priority.get(str(point.get("kind")), 9),
                    abs(float(point.get("x", 0.0))),
                ),
            )
            for inspection in inspections:
                try:
                    ix = float(inspection.get("x", 0.0))
                    iy = float(inspection.get("y", 0.0))
                except (TypeError, ValueError):
                    continue
                if ix < x0 or ix > x1 or iy < y0 or iy > y1:
                    continue
                point = self._to_screen(ix, iy, plot)
                if not plot.adjusted(-8, -8, 8, 8).contains(point):
                    continue
                painter.setPen(QPen(QColor(4, 8, 16, 220), 2))
                painter.setBrush(marker_color)
                painter.drawEllipse(point, 5, 5)
                if labels_drawn >= 8:
                    continue
                label = str(inspection.get("label") or "point")
                value = f"{ix:.3g}, {iy:.3g}"
                text = f"{label}\n{value}"
                metrics = painter.fontMetrics()
                width = max(metrics.horizontalAdvance(label), metrics.horizontalAdvance(value)) + 26
                height = metrics.height() * 2 + 16
                candidates = [
                    QRect(point.x() + 14, point.y() - height - 10, width, height),
                    QRect(point.x() + 14, point.y() + 14, width, height),
                    QRect(point.x() - width - 14, point.y() - height - 10, width, height),
                    QRect(point.x() - width - 14, point.y() + 14, width, height),
                    QRect(point.x() - width // 2, point.y() - height - 18, width, height),
                    QRect(point.x() - width // 2, point.y() + 18, width, height),
                    QRect(point.x() + 40, point.y() - height // 2, width, height),
                    QRect(point.x() - width - 40, point.y() - height // 2, width, height),
                    QRect(point.x() - width // 2, point.y() - height * 2 - 20, width, height),
                    QRect(point.x() - width // 2, point.y() + height + 20, width, height),
                ]
                allowed = plot.adjusted(4, 4, -4, -4)
                bubble = None
                positioned_candidates = []
                for candidate in candidates:
                    candidate.moveLeft(max(allowed.left(), min(candidate.left(), allowed.right() - width)))
                    candidate.moveTop(max(allowed.top(), min(candidate.top(), allowed.bottom() - height)))
                    positioned_candidates.append(QRect(candidate))
                    if not any(candidate.adjusted(-5, -5, 5, 5).intersects(other) for other in occupied_labels):
                        bubble = candidate
                        break
                if bubble is None:
                    def overlap_area(candidate: QRect) -> int:
                        return sum(
                            candidate.intersected(other).width() * candidate.intersected(other).height()
                            for other in occupied_labels
                            if candidate.intersects(other)
                        )

                    bubble = min(positioned_candidates, key=overlap_area)
                occupied_labels.append(bubble)
                labels_drawn += 1
                pointer = QPainterPath()
                pointer.addRoundedRect(bubble, 14, 14)
                painter.setPen(QPen(QColor(125, 210, 255, 130), 1))
                painter.setBrush(QColor(0, 145, 255, 230))
                painter.drawPath(pointer)
                painter.setPen(QColor(255, 255, 255, 245))
                painter.drawText(bubble.adjusted(8, 4, -8, -4), Qt.AlignCenter, text)

        painter.setPen(QColor(255, 255, 255, 218))
        painter.drawText(rect.adjusted(12, 6, -12, -6), Qt.AlignTop | Qt.AlignLeft, self.artifact.title)
        painter.setPen(QColor(220, 230, 250, 190))
        painter.drawText(QRect(plot.right() - 20, plot.bottom() - 24, 18, 20), Qt.AlignCenter, "x")
        painter.drawText(QRect(plot.left() + 6, plot.top() + 2, 18, 20), Qt.AlignCenter, "y")
        painter.setPen(QColor(180, 205, 255, 160))
        painter.drawText(
            rect.adjusted(12, 0, -12, -10),
            Qt.AlignBottom | Qt.AlignLeft,
            f"x {x0:.2g}..{x1:.2g} | y {y0:.2g}..{y1:.2g} | wheel zoom, drag pan",
        )


class SurfaceCanvas(QWidget):
    inspected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("GraphCanvas")
        self.setMinimumHeight(340)
        self.setMouseTracking(True)
        self.artifact: GraphArtifact | None = None
        self.view_mode = "3d"
        self.zoom = 1.0
        self.yaw = math.radians(42.0)
        self.pitch = math.radians(31.0)
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._dragging = False
        self._last_mouse = QPoint()
        self._projected_points: list[tuple[QPoint, float, float, float]] = []

    def set_artifact(self, artifact: GraphArtifact | None):
        self.artifact = artifact
        self.reset_view()

    def set_view_mode(self, mode: str):
        self.view_mode = "2d" if str(mode).lower().startswith("2") else "3d"
        self.reset_view()

    def reset_view(self):
        self.zoom = 1.0
        self.yaw = math.radians(42.0)
        self.pitch = math.radians(31.0)
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def export_png(self, path: str) -> bool:
        return bool(path and self.grab().save(path, "PNG"))

    def export_svg(self, path: str) -> bool:
        if not path:
            return False
        generator = QSvgGenerator()
        generator.setFileName(path)
        generator.setSize(self.size())
        generator.setViewBox(self.rect())
        generator.setTitle(self.artifact.title if self.artifact else "MORICE surface")
        generator.setDescription("Validated surface exported from MORICE")
        painter = QPainter(generator)
        try:
            self.render(painter, QPoint())
        finally:
            painter.end()
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def export_pdf(self, path: str) -> bool:
        if not path:
            return False
        writer = QPdfWriter(path)
        writer.setTitle(self.artifact.title if self.artifact else "MORICE surface")
        writer.setCreator("MORICE")
        writer.setResolution(144)
        painter = QPainter(writer)
        try:
            viewport = painter.viewport()
            target = self.size()
            target.scale(viewport.size(), Qt.KeepAspectRatio)
            painter.setViewport(
                viewport.x() + (viewport.width() - target.width()) // 2,
                viewport.y() + (viewport.height() - target.height()) // 2,
                target.width(),
                target.height(),
            )
            painter.setWindow(self.rect())
            self.render(painter, QPoint())
        finally:
            painter.end()
        return os.path.isfile(path) and os.path.getsize(path) > 0

    @staticmethod
    def _surface_color(value: float, low: float, high: float, alpha: int = 225) -> QColor:
        amount = max(0.0, min(1.0, (value - low) / max(1e-9, high - low)))
        stops = (
            (0.0, QColor("#2356d8")),
            (0.34, QColor("#2bc4c8")),
            (0.67, QColor("#f0d35d")),
            (1.0, QColor("#e55364")),
        )
        for index in range(len(stops) - 1):
            start_at, start_color = stops[index]
            end_at, end_color = stops[index + 1]
            if amount <= end_at:
                local = (amount - start_at) / max(1e-9, end_at - start_at)
                color = QColor(
                    int(start_color.red() + (end_color.red() - start_color.red()) * local),
                    int(start_color.green() + (end_color.green() - start_color.green()) * local),
                    int(start_color.blue() + (end_color.blue() - start_color.blue()) * local),
                    alpha,
                )
                return color
        color = QColor(stops[-1][1])
        color.setAlpha(alpha)
        return color

    def _project_3d(
        self,
        x: float,
        y: float,
        z: float,
        surface: GraphSurface,
        plot: QRect,
    ) -> tuple[QPoint, float]:
        x_mid = (surface.x[0] + surface.x[-1]) * 0.5
        y_mid = (surface.y[0] + surface.y[-1]) * 0.5
        z_mid = (surface.z_range[0] + surface.z_range[1]) * 0.5
        xn = (x - x_mid) / max(1e-9, (surface.x[-1] - surface.x[0]) * 0.5)
        yn = (y - y_mid) / max(1e-9, (surface.y[-1] - surface.y[0]) * 0.5)
        zn = (z - z_mid) / max(1e-9, (surface.z_range[1] - surface.z_range[0]) * 0.5)
        # Keep mathematically exact samples in the artifact; only constrain the
        # camera projection so singularities cannot fling the mesh off-screen.
        zn = max(-1.35, min(1.35, zn))
        cos_yaw = math.cos(self.yaw)
        sin_yaw = math.sin(self.yaw)
        x_rotated = xn * cos_yaw - yn * sin_yaw
        y_rotated = xn * sin_yaw + yn * cos_yaw
        vertical = zn * math.cos(self.pitch) - y_rotated * math.sin(self.pitch)
        depth = zn * math.sin(self.pitch) + y_rotated * math.cos(self.pitch)
        scale = min(plot.width(), plot.height()) * 0.32 * self.zoom
        point = QPoint(
            int(plot.center().x() + self.pan_x + x_rotated * scale),
            int(plot.center().y() + self.pan_y - vertical * scale),
        )
        return point, depth

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self.zoom = max(0.35, min(4.0, self.zoom * (1.1 if delta > 0 else 0.9)))
            self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_mouse = event.position().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        if self._dragging:
            delta = position - self._last_mouse
            self._last_mouse = position
            if self.view_mode == "3d":
                self.yaw += delta.x() * 0.009
                self.pitch = max(-1.25, min(1.25, self.pitch + delta.y() * 0.009))
            else:
                self.pan_x += delta.x()
                self.pan_y += delta.y()
            self.update()
        elif self._projected_points:
            nearest = min(
                self._projected_points,
                key=lambda item: (item[0].x() - position.x()) ** 2 + (item[0].y() - position.y()) ** 2,
            )
            distance = math.hypot(nearest[0].x() - position.x(), nearest[0].y() - position.y())
            if distance <= 34:
                self.inspected.emit(f"x={nearest[1]:.4g}, y={nearest[2]:.4g}, z={nearest[3]:.4g}")
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        plot = rect.adjusted(54, 34, -28, -50)
        painter.fillRect(rect, QColor(5, 7, 12, 240))
        painter.setPen(QPen(QColor(150, 120, 225, 70), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        if not self.artifact or not self.artifact.surface:
            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(rect, Qt.AlignCenter, "No validated surface data")
            return
        surface = self.artifact.surface
        low, high = surface.z_range
        self._projected_points = []

        if self.view_mode == "2d":
            rows = len(surface.y)
            columns = len(surface.x)
            cell_width = plot.width() / max(1, columns - 1)
            cell_height = plot.height() / max(1, rows - 1)
            for row in range(rows - 1):
                for column in range(columns - 1):
                    value = surface.z[row][column]
                    if not math.isfinite(value):
                        continue
                    left = plot.left() + self.pan_x + column * cell_width * self.zoom
                    top = plot.bottom() + self.pan_y - (row + 1) * cell_height * self.zoom
                    cell = QRect(
                        int(left),
                        int(top),
                        max(1, int(cell_width * self.zoom) + 1),
                        max(1, int(cell_height * self.zoom) + 1),
                    )
                    painter.fillRect(cell, self._surface_color(value, low, high))
                    if row % 2 == 0 and column % 2 == 0:
                        self._projected_points.append(
                            (
                                cell.center(),
                                surface.x[column],
                                surface.y[row],
                                value,
                            )
                        )
            painter.setPen(QPen(QColor(255, 255, 255, 48), 1))
            for index in range(0, 11):
                x = plot.left() + int(plot.width() * index / 10)
                y = plot.top() + int(plot.height() * index / 10)
                painter.drawLine(x, plot.top(), x, plot.bottom())
                painter.drawLine(plot.left(), y, plot.right(), y)
            painter.setPen(QColor(225, 235, 250, 205))
            painter.drawText(plot.adjusted(5, 5, -5, -5), Qt.AlignBottom | Qt.AlignRight, "2D height map")
        else:
            faces: list[tuple[float, QPolygon, float]] = []
            step = 2 if len(surface.x) > 30 else 1
            for row in range(0, len(surface.y) - step, step):
                for column in range(0, len(surface.x) - step, step):
                    coordinates = (
                        (column, row),
                        (column + step, row),
                        (column + step, row + step),
                        (column, row + step),
                    )
                    points: list[QPoint] = []
                    depths: list[float] = []
                    values: list[float] = []
                    valid = True
                    for column_index, row_index in coordinates:
                        value = surface.z[row_index][column_index]
                        if not math.isfinite(value):
                            valid = False
                            break
                        point, depth = self._project_3d(
                            surface.x[column_index],
                            surface.y[row_index],
                            value,
                            surface,
                            plot,
                        )
                        points.append(point)
                        depths.append(depth)
                        values.append(value)
                    if valid:
                        faces.append((sum(depths) / len(depths), QPolygon(points), sum(values) / len(values)))
                        self._projected_points.append(
                            (
                                points[0],
                                surface.x[column],
                                surface.y[row],
                                values[0],
                            )
                        )
            for _depth, polygon, value in sorted(faces, key=lambda item: item[0], reverse=True):
                painter.setBrush(self._surface_color(value, low, high, 205))
                painter.setPen(QPen(QColor(5, 10, 18, 86), 1))
                painter.drawPolygon(polygon)
            painter.setPen(QColor(225, 235, 250, 205))
            painter.drawText(plot.adjusted(5, 5, -5, -5), Qt.AlignBottom | Qt.AlignRight, "Drag rotate | wheel zoom")

        legend = QRect(plot.right() - 20, plot.top() + 10, 12, max(70, plot.height() // 3))
        for offset in range(legend.height()):
            value = high - (high - low) * offset / max(1, legend.height() - 1)
            painter.setPen(self._surface_color(value, low, high))
            painter.drawLine(legend.left(), legend.top() + offset, legend.right(), legend.top() + offset)
        painter.setPen(QColor(230, 238, 250, 205))
        painter.drawText(QRect(legend.left() - 44, legend.top() - 18, 56, 18), Qt.AlignRight, f"{high:.3g}")
        painter.drawText(QRect(legend.left() - 44, legend.bottom(), 56, 18), Qt.AlignRight, f"{low:.3g}")
        painter.setPen(QColor(255, 255, 255, 225))
        painter.drawText(rect.adjusted(12, 7, -12, -7), Qt.AlignTop | Qt.AlignLeft, self.artifact.title)


class MoleculeCanvas(QWidget):
    inspected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("MoleculeCanvas")
        self.setMinimumHeight(340)
        self.setMouseTracking(True)
        self.artifact: MoleculeArtifact | None = None
        self.view_mode = "3d"
        self.yaw = math.radians(36.0)
        self.pitch = math.radians(24.0)
        self.zoom = 1.0
        self._dragging = False
        self._last_mouse = QPoint()
        self._hit_regions: list[tuple[QPoint, int, float]] = []

    def set_artifact(self, artifact: MoleculeArtifact | None):
        self.artifact = artifact
        self.reset_view()

    def set_view_mode(self, mode: str):
        self.view_mode = "2d" if str(mode).lower().startswith("2") else "3d"
        self.reset_view()

    def reset_view(self):
        self.yaw = math.radians(36.0)
        self.pitch = math.radians(24.0)
        self.zoom = 1.0
        self.update()

    def export_png(self, path: str) -> bool:
        return bool(path and self.grab().save(path, "PNG"))

    def export_svg(self, path: str) -> bool:
        if not path:
            return False
        generator = QSvgGenerator()
        generator.setFileName(path)
        generator.setSize(self.size())
        generator.setViewBox(self.rect())
        generator.setTitle(self.artifact.title if self.artifact else "MORICE molecule")
        generator.setDescription("Validated molecular structure exported from MORICE")
        painter = QPainter(generator)
        try:
            self.render(painter, QPoint())
        finally:
            painter.end()
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def export_pdf(self, path: str) -> bool:
        if not path:
            return False
        writer = QPdfWriter(path)
        writer.setTitle(self.artifact.title if self.artifact else "MORICE molecule")
        writer.setCreator("MORICE")
        writer.setResolution(144)
        painter = QPainter(writer)
        try:
            viewport = painter.viewport()
            target = self.size()
            target.scale(viewport.size(), Qt.KeepAspectRatio)
            painter.setViewport(
                viewport.x() + (viewport.width() - target.width()) // 2,
                viewport.y() + (viewport.height() - target.height()) // 2,
                target.width(),
                target.height(),
            )
            painter.setWindow(self.rect())
            self.render(painter, QPoint())
        finally:
            painter.end()
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def _project_3d(self, x: float, y: float, z: float, plot: QRect) -> tuple[QPoint, float]:
        cos_yaw = math.cos(self.yaw)
        sin_yaw = math.sin(self.yaw)
        x_rotated = x * cos_yaw - y * sin_yaw
        y_rotated = x * sin_yaw + y * cos_yaw
        vertical = z * math.cos(self.pitch) - y_rotated * math.sin(self.pitch)
        depth = z * math.sin(self.pitch) + y_rotated * math.cos(self.pitch)
        scale = min(plot.width(), plot.height()) * 0.29 * self.zoom
        return (
            QPoint(
                int(plot.center().x() + x_rotated * scale),
                int(plot.center().y() - vertical * scale),
            ),
            depth,
        )

    def _layout_2d(self, plot: QRect) -> dict[int, QPoint]:
        if not self.artifact:
            return {}
        outer = [atom for atom in self.artifact.atoms if atom.atom_id != self.artifact.central_atom]
        radius = min(plot.width(), plot.height()) * 0.31 * self.zoom
        positions = {self.artifact.central_atom: plot.center()}
        count = max(1, len(outer))
        start = -math.pi / 2
        for index, atom in enumerate(outer):
            angle = start + math.tau * index / count
            positions[atom.atom_id] = QPoint(
                int(plot.center().x() + math.cos(angle) * radius),
                int(plot.center().y() + math.sin(angle) * radius),
            )
        return positions

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self.zoom = max(0.45, min(2.8, self.zoom * (1.1 if delta > 0 else 0.9)))
            self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_mouse = event.position().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        if self._dragging and self.view_mode == "3d":
            delta = position - self._last_mouse
            self._last_mouse = position
            self.yaw += delta.x() * 0.009
            self.pitch = max(-1.25, min(1.25, self.pitch + delta.y() * 0.009))
            self.update()
        elif self.artifact and self._hit_regions:
            point, atom_id, radius = min(
                self._hit_regions,
                key=lambda item: math.hypot(item[0].x() - position.x(), item[0].y() - position.y()),
            )
            if math.hypot(point.x() - position.x(), point.y() - position.y()) <= radius + 10:
                atom = next(atom for atom in self.artifact.atoms if atom.atom_id == atom_id)
                charge = (
                    f", formal charge {atom.formal_charge:+d}"
                    if atom.formal_charge
                    else ""
                )
                self.inspected.emit(
                    f"Atom {atom.atom_id}: {atom.element} at "
                    f"({atom.x:.3g}, {atom.y:.3g}, {atom.z:.3g}){charge}"
                )
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()

    @staticmethod
    def _bond_offsets(start: QPoint, end: QPoint, order: int) -> list[tuple[QPoint, QPoint]]:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = max(1.0, math.hypot(dx, dy))
        nx = -dy / length
        ny = dx / length
        if order <= 1:
            offsets = [0.0]
        elif order == 2:
            offsets = [-3.5, 3.5]
        else:
            offsets = [-5.5, 0.0, 5.5]
        return [
            (
                QPoint(int(start.x() + nx * offset), int(start.y() + ny * offset)),
                QPoint(int(end.x() + nx * offset), int(end.y() + ny * offset)),
            )
            for offset in offsets
        ]

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        plot = rect.adjusted(30, 42, -30, -70)
        painter.fillRect(rect, QColor(5, 7, 12, 240))
        painter.setPen(QPen(QColor(150, 120, 225, 70), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        if not self.artifact:
            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(rect, Qt.AlignCenter, "No validated molecule data")
            return

        projected: dict[int, tuple[QPoint, float]] = {}
        if self.view_mode == "3d":
            for atom in self.artifact.atoms:
                projected[atom.atom_id] = self._project_3d(atom.x, atom.y, atom.z, plot)
        else:
            projected = {
                atom_id: (point, 0.0)
                for atom_id, point in self._layout_2d(plot).items()
            }

        painter.setPen(QPen(QColor(205, 218, 238, 190), 4, Qt.SolidLine, Qt.RoundCap))
        for bond in self.artifact.bonds:
            start = projected[bond.first][0]
            end = projected[bond.second][0]
            for line_start, line_end in self._bond_offsets(start, end, bond.order):
                painter.drawLine(line_start, line_end)

        self._hit_regions = []
        atom_depths = sorted(
            self.artifact.atoms,
            key=lambda atom: projected[atom.atom_id][1],
            reverse=True,
        )
        for atom in atom_depths:
            point, depth = projected[atom.atom_id]
            central = atom.atom_id == self.artifact.central_atom
            radius = int((24 if central else 20) * self.zoom)
            if self.view_mode == "3d":
                radius = int(radius * max(0.74, min(1.2, 1.0 - depth * 0.09)))
            radius = max(13, radius)
            color = QColor(atom_color(atom.element))
            painter.setBrush(color)
            painter.setPen(QPen(color.lighter(145), 2))
            painter.drawEllipse(point, radius, radius)
            painter.setPen(QColor(4, 7, 12, 245) if color.lightness() > 145 else QColor(255, 255, 255, 245))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(max(8, min(13, radius // 2)))
            painter.setFont(font)
            painter.drawText(
                QRect(point.x() - radius, point.y() - radius, radius * 2, radius * 2),
                Qt.AlignCenter,
                atom.element,
            )
            self._hit_regions.append((point, atom.atom_id, float(radius)))

        if self.view_mode == "2d" and self.artifact.central_lone_pairs:
            center = projected[self.artifact.central_atom][0]
            painter.setBrush(QColor(116, 219, 255, 235))
            painter.setPen(Qt.NoPen)
            for pair in range(self.artifact.central_lone_pairs):
                angle = math.pi + (pair - (self.artifact.central_lone_pairs - 1) / 2) * 0.62
                base_x = center.x() + math.cos(angle) * 45
                base_y = center.y() + math.sin(angle) * 45
                tangent_x = -math.sin(angle) * 5
                tangent_y = math.cos(angle) * 5
                painter.drawEllipse(QPoint(int(base_x + tangent_x), int(base_y + tangent_y)), 3, 3)
                painter.drawEllipse(QPoint(int(base_x - tangent_x), int(base_y - tangent_y)), 3, 3)

        painter.setPen(QColor(255, 255, 255, 228))
        title_font = painter.font()
        title_font.setBold(True)
        title_font.setPointSize(11)
        painter.setFont(title_font)
        painter.drawText(rect.adjusted(14, 8, -14, -8), Qt.AlignTop | Qt.AlignLeft, self.artifact.title)
        painter.setPen(QColor(190, 205, 230, 195))
        angle_text = ", ".join(
            f"{value:g} deg" for value in self.artifact.reference_angles
        )
        mode = "3D geometry" if self.view_mode == "3d" else "2D structure schematic"
        footer = (
            f"{mode} | molecular geometry: {self.artifact.geometry} | "
            f"electron geometry: {self.artifact.electron_geometry} | "
            f"reference angles: {angle_text}"
        )
        painter.drawText(rect.adjusted(14, 0, -14, -10), Qt.AlignBottom | Qt.AlignLeft, footer)


class DiagramCanvas(QWidget):
    inspected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("DiagramCanvas")
        self.setMinimumHeight(320)
        self.setMouseTracking(True)
        self.artifact: DiagramArtifact | None = None
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._dragging = False
        self._last_mouse = QPoint()
        self._node_rects: dict[str, QRect] = {}

    def set_artifact(self, artifact: DiagramArtifact | None):
        self.artifact = artifact
        self.reset_view()

    def reset_view(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

    def export_png(self, path: str) -> bool:
        return bool(path and self.grab().save(path, "PNG"))

    def export_svg(self, path: str) -> bool:
        if not path:
            return False
        generator = QSvgGenerator()
        generator.setFileName(path)
        generator.setSize(self.size())
        generator.setViewBox(self.rect())
        generator.setTitle(self.artifact.title if self.artifact else "MORICE diagram")
        generator.setDescription("Validated structured diagram exported from MORICE")
        painter = QPainter(generator)
        try:
            self.render(painter, QPoint())
        finally:
            painter.end()
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def export_pdf(self, path: str) -> bool:
        if not path:
            return False
        writer = QPdfWriter(path)
        writer.setTitle(self.artifact.title if self.artifact else "MORICE diagram")
        writer.setCreator("MORICE")
        writer.setResolution(144)
        painter = QPainter(writer)
        try:
            viewport = painter.viewport()
            target = self.size()
            target.scale(viewport.size(), Qt.KeepAspectRatio)
            painter.setViewport(
                viewport.x() + (viewport.width() - target.width()) // 2,
                viewport.y() + (viewport.height() - target.height()) // 2,
                target.width(),
                target.height(),
            )
            painter.setWindow(self.rect())
            self.render(painter, QPoint())
        finally:
            painter.end()
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self.zoom = max(0.55, min(2.4, self.zoom * (1.1 if delta > 0 else 0.9)))
            self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_mouse = event.position().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        if self._dragging:
            delta = position - self._last_mouse
            self._last_mouse = position
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self.update()
        else:
            for node_id, node_rect in self._node_rects.items():
                if node_rect.contains(position) and self.artifact:
                    node = next(item for item in self.artifact.nodes if item.node_id == node_id)
                    outgoing = sum(1 for edge in self.artifact.edges if edge.source == node_id)
                    incoming = sum(1 for edge in self.artifact.edges if edge.target == node_id)
                    self.inspected.emit(f"{node.label} | incoming {incoming} | outgoing {outgoing}")
                    break
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()

    def _layout_nodes(self, plot: QRect) -> dict[str, QRect]:
        if not self.artifact:
            return {}
        count = len(self.artifact.nodes)
        vertical = self.artifact.instruction.get("parameters", {}).get("layout") == "vertical"
        node_width = int(min(190, max(104, (plot.width() / max(1, count)) * 0.72)) * self.zoom)
        node_height = int(58 * self.zoom)
        positions: dict[str, QRect] = {}
        if vertical:
            gap = max(12, int((plot.height() - count * node_height) / max(1, count - 1)))
            total_height = count * node_height + max(0, count - 1) * gap
            top = plot.center().y() - total_height // 2 + int(self.pan_y)
            for index, node in enumerate(self.artifact.nodes):
                positions[node.node_id] = QRect(
                    int(plot.center().x() - node_width / 2 + self.pan_x),
                    top + index * (node_height + gap),
                    node_width,
                    node_height,
                )
        else:
            columns = min(4, max(1, count))
            rows = math.ceil(count / columns)
            gap_x = max(20, int((plot.width() - columns * node_width) / max(1, columns - 1)))
            gap_y = max(26, int((plot.height() - rows * node_height) / max(1, rows - 1)))
            total_width = columns * node_width + max(0, columns - 1) * gap_x
            total_height = rows * node_height + max(0, rows - 1) * gap_y
            left = plot.center().x() - total_width // 2 + int(self.pan_x)
            top = plot.center().y() - total_height // 2 + int(self.pan_y)
            for index, node in enumerate(self.artifact.nodes):
                row = index // columns
                column = index % columns
                positions[node.node_id] = QRect(
                    left + column * (node_width + gap_x),
                    top + row * (node_height + gap_y),
                    node_width,
                    node_height,
                )
        return positions

    @staticmethod
    def _edge_points(source: QRect, target: QRect) -> tuple[QPoint, QPoint]:
        dx = target.center().x() - source.center().x()
        dy = target.center().y() - source.center().y()
        if abs(dx) >= abs(dy):
            start = QPoint(source.right() if dx >= 0 else source.left(), source.center().y())
            end = QPoint(target.left() if dx >= 0 else target.right(), target.center().y())
        else:
            start = QPoint(source.center().x(), source.bottom() if dy >= 0 else source.top())
            end = QPoint(target.center().x(), target.top() if dy >= 0 else target.bottom())
        return start, end

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        plot = rect.adjusted(34, 46, -34, -48)
        painter.fillRect(rect, QColor(5, 7, 12, 240))
        painter.setPen(QPen(QColor(150, 120, 225, 70), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        if not self.artifact:
            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(rect, Qt.AlignCenter, "No validated diagram data")
            return
        self._node_rects = self._layout_nodes(plot)

        painter.setPen(QPen(QColor(119, 202, 255, 205), 2))
        for edge in self.artifact.edges:
            source_rect = self._node_rects.get(edge.source)
            target_rect = self._node_rects.get(edge.target)
            if not source_rect or not target_rect:
                continue
            start, end = self._edge_points(source_rect, target_rect)
            painter.drawLine(start, end)
            angle = math.atan2(end.y() - start.y(), end.x() - start.x())
            arrow = QPolygon(
                [
                    end,
                    QPoint(
                        int(end.x() - 11 * math.cos(angle - 0.48)),
                        int(end.y() - 11 * math.sin(angle - 0.48)),
                    ),
                    QPoint(
                        int(end.x() - 11 * math.cos(angle + 0.48)),
                        int(end.y() - 11 * math.sin(angle + 0.48)),
                    ),
                ]
            )
            painter.setBrush(QColor(119, 202, 255, 220))
            painter.drawPolygon(arrow)
            if edge.label:
                midpoint = QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2)
                label_rect = QRect(midpoint.x() - 55, midpoint.y() - 18, 110, 24)
                painter.fillRect(label_rect, QColor(5, 7, 12, 220))
                painter.setPen(QColor(200, 220, 246, 210))
                painter.drawText(label_rect, Qt.AlignCenter, edge.label)
                painter.setPen(QPen(QColor(119, 202, 255, 205), 2))

        colors = ("#3d5ca8", "#2a7894", "#447a69", "#7551a8")
        for index, node in enumerate(self.artifact.nodes):
            node_rect = self._node_rects[node.node_id]
            painter.setBrush(QColor(colors[index % len(colors)]))
            painter.setPen(QPen(QColor(154, 211, 255, 150), 1))
            painter.drawRoundedRect(node_rect, 7, 7)
            painter.setPen(QColor(255, 255, 255, 240))
            painter.drawText(node_rect.adjusted(10, 7, -10, -7), Qt.AlignCenter | Qt.TextWordWrap, node.label)

        painter.setPen(QColor(255, 255, 255, 228))
        title_font = painter.font()
        title_font.setBold(True)
        title_font.setPointSize(11)
        painter.setFont(title_font)
        painter.drawText(rect.adjusted(14, 8, -14, -8), Qt.AlignTop | Qt.AlignLeft, self.artifact.title)
        painter.setPen(QColor(190, 205, 230, 190))
        painter.drawText(
            rect.adjusted(14, 0, -14, -9),
            Qt.AlignBottom | Qt.AlignLeft,
            "wheel zoom | drag pan | hover nodes for connection counts",
        )


class ChartCanvas(QWidget):
    inspected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("ChartCanvas")
        self.setMinimumHeight(340)
        self.setMouseTracking(True)
        self.artifact: ChartArtifact | None = None
        self._regions: list[tuple[QRect, str]] = []

    def set_artifact(self, artifact: ChartArtifact | None):
        self.artifact = artifact
        self.update()

    def reset_view(self):
        self.update()

    def export_png(self, path: str) -> bool:
        return bool(path and self.grab().save(path, "PNG"))

    def export_svg(self, path: str) -> bool:
        if not path:
            return False
        generator = QSvgGenerator()
        generator.setFileName(path)
        generator.setSize(self.size())
        generator.setViewBox(self.rect())
        generator.setTitle(self.artifact.title if self.artifact else "MORICE chart")
        generator.setDescription("Validated chart exported from MORICE")
        painter = QPainter(generator)
        try:
            self.render(painter, QPoint())
        finally:
            painter.end()
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def export_pdf(self, path: str) -> bool:
        if not path:
            return False
        writer = QPdfWriter(path)
        writer.setTitle(self.artifact.title if self.artifact else "MORICE chart")
        writer.setCreator("MORICE")
        writer.setResolution(144)
        painter = QPainter(writer)
        try:
            viewport = painter.viewport()
            target = self.size()
            target.scale(viewport.size(), Qt.KeepAspectRatio)
            painter.setViewport(
                viewport.x() + (viewport.width() - target.width()) // 2,
                viewport.y() + (viewport.height() - target.height()) // 2,
                target.width(),
                target.height(),
            )
            painter.setWindow(self.rect())
            self.render(painter, QPoint())
        finally:
            painter.end()
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        for region, detail in self._regions:
            if region.contains(position):
                self.inspected.emit(detail)
                break
        event.accept()

    @staticmethod
    def _palette(index: int) -> QColor:
        colors = ("#52b7ff", "#62d6ad", "#a985ff", "#f2c45c", "#ef7080", "#48c3cf")
        return QColor(colors[index % len(colors)])

    def _draw_pie(self, painter: QPainter, plot: QRect):
        values = [max(0.0, point.y) for point in self.artifact.points]
        total = sum(values)
        if total <= 0:
            painter.setPen(QColor(255, 255, 255, 180))
            painter.drawText(plot, Qt.AlignCenter, "Pie charts require positive values")
            return
        diameter = min(plot.width() * 0.58, plot.height() * 0.88)
        pie_rect = QRect(
            int(plot.left() + plot.width() * 0.04),
            int(plot.center().y() - diameter / 2),
            int(diameter),
            int(diameter),
        )
        start = 90 * 16
        self._regions = []
        for index, (point, value) in enumerate(zip(self.artifact.points, values)):
            span = int(round(value / total * 360 * 16))
            painter.setBrush(self._palette(index))
            painter.setPen(QPen(QColor(5, 8, 14, 220), 2))
            painter.drawPie(pie_rect, start, -span)
            start -= span
        legend_x = int(plot.left() + plot.width() * 0.68)
        for index, (point, value) in enumerate(zip(self.artifact.points, values)):
            row = QRect(legend_x, plot.top() + 10 + index * 29, plot.right() - legend_x, 24)
            painter.fillRect(QRect(row.left(), row.top() + 5, 14, 14), self._palette(index))
            painter.setPen(QColor(235, 241, 250, 225))
            percent = value / total * 100
            painter.drawText(row.adjusted(22, 0, 0, 0), Qt.AlignVCenter, f"{point.label}: {value:g} ({percent:.1f}%)")
            self._regions.append((row, f"{point.label} = {value:g} | {percent:.2f}%"))

    def _draw_cartesian(self, painter: QPainter, plot: QRect):
        points = self.artifact.points
        values = [point.y for point in points]
        min_y = min(0.0, min(values))
        max_y = max(0.0, max(values))
        if abs(max_y - min_y) < 1e-12:
            max_y = min_y + 1.0
        painter.setPen(QPen(QColor(255, 255, 255, 35), 1))
        for index in range(6):
            y = plot.top() + index * plot.height() / 5
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            value = max_y - index * (max_y - min_y) / 5
            painter.setPen(QColor(190, 205, 230, 170))
            painter.drawText(plot.left() - 64, int(y) - 10, 58, 20, Qt.AlignRight | Qt.AlignVCenter, f"{value:g}")
            painter.setPen(QPen(QColor(255, 255, 255, 35), 1))
        zero_y = int(plot.bottom() - (0.0 - min_y) / (max_y - min_y) * plot.height())
        painter.setPen(QPen(QColor(230, 238, 250, 110), 2))
        painter.drawLine(plot.left(), zero_y, plot.right(), zero_y)
        self._regions = []

        if self.artifact.chart_type in {"bar", "histogram"}:
            slot = plot.width() / max(1, len(points))
            width = max(8, int(slot * 0.68))
            for index, point in enumerate(points):
                value_y = int(plot.bottom() - (point.y - min_y) / (max_y - min_y) * plot.height())
                top = min(zero_y, value_y)
                height = max(2, abs(value_y - zero_y))
                bar = QRect(int(plot.left() + index * slot + (slot - width) / 2), top, width, height)
                painter.setBrush(self._palette(index))
                painter.setPen(QPen(QColor(180, 225, 255, 150), 1))
                painter.drawRoundedRect(bar, 4, 4)
                label_rect = QRect(int(plot.left() + index * slot), plot.bottom() + 7, int(slot), 36)
                painter.setPen(QColor(220, 230, 244, 205))
                painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, point.label[:18])
                self._regions.append((bar.adjusted(-4, -4, 4, 4), f"{point.label} = {point.y:g}"))
            return

        x_values = [point.x for point in points]
        min_x, max_x = min(x_values), max(x_values)
        if abs(max_x - min_x) < 1e-12:
            max_x = min_x + 1.0

        def projected(point):
            x = plot.left() + (point.x - min_x) / (max_x - min_x) * plot.width()
            y = plot.bottom() - (point.y - min_y) / (max_y - min_y) * plot.height()
            return QPoint(int(x), int(y))

        projected_points = [projected(point) for point in points]
        if self.artifact.chart_type == "line":
            path = QPainterPath()
            path.moveTo(projected_points[0])
            for point in projected_points[1:]:
                path.lineTo(point)
            painter.setPen(QPen(QColor("#52b7ff"), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        for index, (point, screen_point) in enumerate(zip(points, projected_points)):
            painter.setBrush(self._palette(index))
            painter.setPen(QPen(QColor(5, 8, 14, 220), 2))
            painter.drawEllipse(screen_point, 6, 6)
            region = QRect(screen_point.x() - 10, screen_point.y() - 10, 20, 20)
            self._regions.append((region, f"{point.label}: x={point.x:g}, y={point.y:g}"))

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        plot = rect.adjusted(82, 48, -30, -58)
        painter.fillRect(rect, QColor(5, 8, 14, 244))
        painter.setPen(QPen(QColor(80, 190, 225, 80), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        if not self.artifact:
            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(rect, Qt.AlignCenter, "No validated chart data")
            return
        if self.artifact.chart_type == "pie":
            self._draw_pie(painter, plot.adjusted(-45, 0, 0, 20))
        else:
            self._draw_cartesian(painter, plot)
        painter.setPen(QColor(255, 255, 255, 235))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(rect.adjusted(14, 8, -14, -8), Qt.AlignTop | Qt.AlignLeft, self.artifact.title)
        painter.setPen(QColor(190, 205, 230, 180))
        painter.drawText(
            rect.adjusted(14, 0, -14, -9),
            Qt.AlignBottom | Qt.AlignLeft,
            f"{self.artifact.chart_type} | hover marks for exact values",
        )


class SceneCanvas(QWidget):
    inspected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("SceneCanvas")
        self.setMinimumHeight(380)
        self.setMouseTracking(True)
        self.artifact: SceneArtifact | None = None
        self.view_mode = "3d"
        self.running = True
        self.yaw = math.radians(28)
        self.pitch = math.radians(18)
        self.zoom = 1.0
        self._dragging = False
        self._last_mouse = QPoint()
        self._hit_regions: list[tuple[QRect, str]] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(32)

    def set_artifact(self, artifact: SceneArtifact | None):
        self.artifact = artifact
        self.reset_view()

    def set_view_mode(self, mode: str):
        self.view_mode = "2d" if str(mode).lower().startswith("2") else "3d"
        self.update()

    def set_running(self, running: bool):
        self.running = bool(running)

    def reset_view(self):
        self.yaw = math.radians(28)
        self.pitch = math.radians(18)
        self.zoom = 1.0
        self.update()

    def export_png(self, path: str) -> bool:
        return bool(path and self.grab().save(path, "PNG"))

    def _tick(self):
        if self.running and self.isVisible() and self.view_mode == "3d":
            self.yaw = (self.yaw + 0.006) % math.tau
            self.update()

    def wheelEvent(self, event):
        if event.angleDelta().y():
            self.zoom = max(0.45, min(2.8, self.zoom * (1.1 if event.angleDelta().y() > 0 else 0.9)))
            self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_mouse = event.position().toPoint()
        event.accept()

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        if self._dragging and self.view_mode == "3d":
            delta = position - self._last_mouse
            self._last_mouse = position
            self.yaw += delta.x() * 0.009
            self.pitch = max(-1.2, min(1.2, self.pitch + delta.y() * 0.009))
            self.update()
        else:
            for region, label in self._hit_regions:
                if region.contains(position):
                    self.inspected.emit(label)
                    break
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()

    def _rotate(self, point: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = point
        if self.view_mode == "2d":
            return x, y, z
        cos_yaw, sin_yaw = math.cos(self.yaw), math.sin(self.yaw)
        x_rotated = x * cos_yaw - z * sin_yaw
        z_rotated = x * sin_yaw + z * cos_yaw
        cos_pitch, sin_pitch = math.cos(self.pitch), math.sin(self.pitch)
        y_rotated = y * cos_pitch - z_rotated * sin_pitch
        depth = y * sin_pitch + z_rotated * cos_pitch
        return x_rotated, y_rotated, depth

    def _project(self, point: tuple[float, float, float], plot: QRect) -> tuple[QPoint, float]:
        x, y, depth = self._rotate(point)
        scale = min(plot.width(), plot.height()) * 0.19 * self.zoom
        return QPoint(
            int(plot.center().x() + x * scale),
            int(plot.center().y() - y * scale),
        ), depth

    @staticmethod
    def _corners(primitive: ScenePrimitive) -> list[tuple[float, float, float]]:
        cx, cy, cz = primitive.center
        sx, sy, sz = (value / 2.0 for value in primitive.size)
        return [
            (cx + dx * sx, cy + dy * sy, cz + dz * sz)
            for dx, dy, dz in (
                (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
            )
        ]

    def _draw_primitive(self, painter: QPainter, primitive: ScenePrimitive, plot: QRect) -> tuple[QRect, float]:
        center, depth = self._project(primitive.center, plot)
        color = QColor(primitive.color)
        color.setAlpha(175)
        outline = QColor(primitive.color)
        outline.setAlpha(235)
        scale = min(plot.width(), plot.height()) * 0.19 * self.zoom
        if primitive.shape == "box":
            projected = [self._project(point, plot)[0] for point in self._corners(primitive)]
            painter.setBrush(color)
            painter.setPen(QPen(outline, 1.7))
            face = QPolygon([projected[index] for index in (4, 5, 6, 7)])
            painter.drawPolygon(face)
            for first, second in (
                (0, 1), (1, 2), (2, 3), (3, 0),
                (4, 5), (5, 6), (6, 7), (7, 4),
                (0, 4), (1, 5), (2, 6), (3, 7),
            ):
                painter.drawLine(projected[first], projected[second])
            xs = [point.x() for point in projected]
            ys = [point.y() for point in projected]
            region = QRect(min(xs), min(ys), max(8, max(xs) - min(xs)), max(8, max(ys) - min(ys)))
        else:
            width = max(10, int(primitive.size[0] * scale))
            height = max(10, int(primitive.size[1] * scale))
            if primitive.shape == "cylinder":
                height = max(height, int(primitive.size[2] * scale * 0.55))
            region = QRect(center.x() - width // 2, center.y() - height // 2, width, height)
            painter.setBrush(color)
            painter.setPen(QPen(outline, 1.8))
            painter.drawEllipse(region)
            if primitive.shape == "cylinder":
                painter.drawLine(region.left(), region.center().y(), region.right(), region.center().y())
        return region, depth

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        plot = rect.adjusted(36, 48, -36, -62)
        painter.fillRect(rect, QColor(5, 8, 14, 244))
        painter.setPen(QPen(QColor(130, 165, 255, 75), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        if not self.artifact:
            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(rect, Qt.AlignCenter, "No validated scene data")
            return

        centers = [self._project(item.center, plot) for item in self.artifact.primitives]
        painter.setPen(QPen(QColor(119, 202, 255, 170), 2))
        for connection in self.artifact.connections:
            painter.drawLine(centers[connection.first][0], centers[connection.second][0])

        ordered = sorted(
            enumerate(self.artifact.primitives),
            key=lambda item: self._rotate(item[1].center)[2],
        )
        self._hit_regions = []
        for index, primitive in ordered:
            region, _depth = self._draw_primitive(painter, primitive, plot)
            painter.setPen(QColor(245, 248, 255, 235))
            label_rect = QRect(region.left() - 35, region.bottom() + 3, region.width() + 70, 22)
            painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop, primitive.label)
            self._hit_regions.append(
                (
                    region.adjusted(-5, -5, 5, 24),
                    f"{primitive.label} | shape {primitive.shape} | schematic size "
                    f"{primitive.size[0]:g} x {primitive.size[1]:g} x {primitive.size[2]:g}",
                )
            )

        painter.setPen(QColor(255, 255, 255, 235))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(rect.adjusted(14, 8, -14, -8), Qt.AlignTop | Qt.AlignLeft, self.artifact.title)
        painter.setPen(QColor(190, 205, 230, 185))
        mode = "3D rotatable schematic" if self.view_mode == "3d" else "2D orthographic schematic"
        painter.drawText(
            rect.adjusted(14, 0, -14, -9),
            Qt.AlignBottom | Qt.AlignLeft,
            f"{mode} | wheel zoom | drag rotate | hover labeled components",
        )


class BiologyCanvas(QWidget):
    inspected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("BiologyCanvas")
        self.setMinimumHeight(360)
        self.setMouseTracking(True)
        self.artifact: BiologyArtifact | None = None
        self.view_mode = "3d"
        self.running = True
        self.yaw = math.radians(28)
        self.pitch = math.radians(18)
        self.zoom = 1.0
        self.phase = 0.0
        self._dragging = False
        self._last_mouse = QPoint()
        self._hit_regions: list[tuple[QPoint, str]] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_artifact(self, artifact: BiologyArtifact | None):
        self.artifact = artifact
        self.reset_view()

    def set_view_mode(self, mode: str):
        self.view_mode = "2d" if str(mode).lower().startswith("2") else "3d"
        self.update()

    def set_running(self, running: bool):
        self.running = bool(running)

    def reset_view(self):
        self.yaw = math.radians(28)
        self.pitch = math.radians(18)
        self.zoom = 1.0
        self.phase = 0.0
        self.update()

    def export_png(self, path: str) -> bool:
        return bool(path and self.grab().save(path, "PNG"))

    def _tick(self):
        if self.running and self.artifact and self.artifact.model_type == "dna":
            self.phase = (self.phase + 0.012) % math.tau
            self.update()

    def _project(self, point: tuple[float, float, float], plot: QRect) -> tuple[QPoint, float]:
        x, y, z = point
        yaw = self.yaw + (self.phase if self.artifact and self.artifact.model_type == "dna" else 0.0)
        if self.view_mode == "2d":
            if self.artifact and self.artifact.model_type == "dna":
                scale_x = plot.width() * 0.28 * self.zoom
                scale_y = plot.height() * 0.105 * self.zoom
                return QPoint(
                    int(plot.center().x() + z * scale_x),
                    int(plot.center().y() - x * scale_y),
                ), y
            return QPoint(
                int(plot.center().x() + x * plot.width() * 0.20 * self.zoom),
                int(plot.center().y() - y * plot.height() * 0.22 * self.zoom),
            ), z
        cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
        x_rotated = x * cos_yaw - y * sin_yaw
        y_rotated = x * sin_yaw + y * cos_yaw
        vertical = z * math.cos(self.pitch) - y_rotated * math.sin(self.pitch)
        depth = z * math.sin(self.pitch) + y_rotated * math.cos(self.pitch)
        scale = min(plot.width(), plot.height()) * 0.25 * self.zoom
        return QPoint(
            int(plot.center().x() + x_rotated * scale),
            int(plot.center().y() - vertical * scale),
        ), depth

    def wheelEvent(self, event):
        if event.angleDelta().y():
            self.zoom = max(0.5, min(2.8, self.zoom * (1.1 if event.angleDelta().y() > 0 else 0.9)))
            self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_mouse = event.position().toPoint()
        event.accept()

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        if self._dragging and self.view_mode == "3d":
            delta = position - self._last_mouse
            self._last_mouse = position
            self.yaw += delta.x() * 0.009
            self.pitch = max(-1.2, min(1.2, self.pitch + delta.y() * 0.009))
            self.update()
        elif self._hit_regions:
            point, label = min(
                self._hit_regions,
                key=lambda item: math.hypot(item[0].x() - position.x(), item[0].y() - position.y()),
            )
            if math.hypot(point.x() - position.x(), point.y() - position.y()) < 18:
                self.inspected.emit(label)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        event.accept()

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        plot = rect.adjusted(30, 44, -30, -56)
        painter.fillRect(rect, QColor(5, 9, 14, 244))
        painter.setPen(QPen(QColor(91, 214, 178, 95), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        if not self.artifact:
            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(rect, Qt.AlignCenter, "No validated biology model")
            return

        projected = [self._project(point, plot) for point in self.artifact.points]
        connection_colors = {
            "backbone": QColor(72, 185, 255, 220),
            "base pair": QColor(242, 115, 172, 215),
            "signal": QColor(255, 204, 92, 220),
            "input": QColor(91, 214, 178, 220),
            "output": QColor(190, 130, 255, 220),
            "contains": QColor(125, 190, 235, 170),
        }
        for first, second, connection_type in self.artifact.connections:
            if first >= len(projected) or second >= len(projected):
                continue
            painter.setPen(QPen(connection_colors.get(connection_type, QColor(175, 205, 235, 190)), 3))
            painter.drawLine(projected[first][0], projected[second][0])

        self._hit_regions = []
        for index in sorted(range(len(projected)), key=lambda item: projected[item][1], reverse=True):
            point, depth = projected[index]
            if self.artifact.model_type == "dna":
                color = QColor(72, 185, 255) if index % 2 == 0 else QColor(242, 115, 172)
                label = ("Sugar-phosphate backbone A" if index % 2 == 0 else "Sugar-phosphate backbone B")
                radius = 6
            else:
                color = (QColor("#5bd6b2"), QColor("#67b7ff"), QColor("#f0a6ca"))[index % 3]
                label = self.artifact.labels[min(index, len(self.artifact.labels) - 1)]
                radius = 13 if index else 18
            if self.view_mode == "3d":
                radius = max(5, int(radius * max(0.75, min(1.2, 1.0 - depth * 0.06))))
            painter.setBrush(color)
            painter.setPen(QPen(color.lighter(145), 2))
            painter.drawEllipse(point, radius, radius)
            if self.artifact.model_type != "dna":
                painter.setPen(QColor(236, 245, 252, 225))
                painter.drawText(QRect(point.x() + 15, point.y() - 11, 145, 24), Qt.AlignLeft | Qt.AlignVCenter, label)
            self._hit_regions.append((point, label))

        painter.setPen(QColor(255, 255, 255, 235))
        title_font = painter.font()
        title_font.setBold(True)
        title_font.setPointSize(11)
        painter.setFont(title_font)
        painter.drawText(rect.adjusted(14, 8, -14, -8), Qt.AlignTop | Qt.AlignLeft, self.artifact.title)
        painter.setPen(QColor(190, 210, 228, 195))
        mode = "2D schematic" if self.view_mode == "2d" else "3D perspective"
        painter.drawText(
            rect.adjusted(14, 0, -14, -10),
            Qt.AlignBottom | Qt.AlignLeft,
            f"{mode} | wheel zoom | drag rotate | hover to inspect",
        )


class DataStructureCanvas(QWidget):
    inspected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("DataStructureCanvas")
        self.setMinimumHeight(350)
        self.structure = "Binary Search Tree"
        self.values: list[int] = []
        self.highlighted: set[int] = set()
        self.status = "Choose an operation."
        self._pulse = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(28)

    def set_state(self, structure: str, values: list[int], highlighted=None, status: str = ""):
        self.structure = structure
        self.values = list(values)
        self.highlighted = set(highlighted or [])
        self.status = status or "Choose an operation."
        self._pulse = 0.0
        self.update()

    def _tick(self):
        if self.highlighted:
            self._pulse = (self._pulse + 0.12) % math.tau
            self.update()

    @staticmethod
    def _bst(values: list[int]):
        root = None
        for value in values:
            if root is None:
                root = [value, None, None]
                continue
            node = root
            while True:
                branch = 1 if value < node[0] else 2
                if value == node[0]:
                    break
                if node[branch] is None:
                    node[branch] = [value, None, None]
                    break
                node = node[branch]
        return root

    @staticmethod
    def _balanced_tree(values: list[int]):
        items = sorted(set(values))

        def build(subset):
            if not subset:
                return None
            middle = len(subset) // 2
            return [
                subset[middle],
                build(subset[:middle]),
                build(subset[middle + 1:]),
            ]

        return build(items)

    def _tree_positions(self, tree, plot: QRect):
        positions: dict[int, QPoint] = {}

        def walk(node, low: float, high: float, depth: int):
            if not node:
                return
            x = plot.left() + int((low + high) * 0.5 * plot.width())
            y = plot.top() + 35 + depth * max(58, plot.height() // 5)
            positions[node[0]] = QPoint(x, y)
            walk(node[1], low, (low + high) * 0.5, depth + 1)
            walk(node[2], (low + high) * 0.5, high, depth + 1)

        walk(tree, 0.0, 1.0, 0)
        return positions

    def _draw_node(self, painter: QPainter, point: QPoint, value: int, radius: int = 22):
        active = value in self.highlighted
        if active:
            radius += int(3 + 2 * math.sin(self._pulse))
        color = QColor("#38d9a9") if active else QColor("#315d91")
        painter.setBrush(color)
        painter.setPen(QPen(color.lighter(150), 2))
        painter.drawEllipse(point, radius, radius)
        painter.setPen(QColor(255, 255, 255, 245))
        painter.drawText(QRect(point.x() - radius, point.y() - radius, radius * 2, radius * 2), Qt.AlignCenter, str(value))

    def _draw_tree(self, painter: QPainter, plot: QRect, avl: bool):
        tree = self._balanced_tree(self.values) if avl else self._bst(self.values)
        positions = self._tree_positions(tree, plot)

        def edges(node):
            if not node:
                return
            for child in node[1:]:
                if child:
                    painter.drawLine(positions[node[0]], positions[child[0]])
                    edges(child)

        painter.setPen(QPen(QColor(105, 190, 245, 185), 2))
        edges(tree)
        for value, point in positions.items():
            self._draw_node(painter, point, value)

    def _draw_sequence(self, painter: QPainter, plot: QRect, mode: str):
        if mode == "Stack":
            width, height = min(180, plot.width() // 2), 42
            left = plot.center().x() - width // 2
            bottom = plot.bottom() - 25
            for index, value in enumerate(self.values[-7:]):
                box = QRect(left, bottom - (index + 1) * height, width, height - 4)
                self._draw_box(painter, box, value)
            return
        shown = self.values[:9]
        width = max(52, min(96, (plot.width() - 40) // max(1, len(shown))))
        left = plot.center().x() - len(shown) * width // 2
        for index, value in enumerate(shown):
            box = QRect(left + index * width, plot.center().y() - 26, width - 8, 52)
            self._draw_box(painter, box, value)
            if mode in {"Linked List", "Queue"} and index < len(shown) - 1:
                painter.setPen(QPen(QColor(115, 204, 255, 210), 2))
                painter.drawLine(box.right(), box.center().y(), box.right() + 8, box.center().y())

    def _draw_box(self, painter: QPainter, box: QRect, value: int):
        active = value in self.highlighted
        color = QColor("#38d9a9") if active else QColor("#315d91")
        painter.setBrush(color)
        painter.setPen(QPen(color.lighter(150), 2))
        painter.drawRoundedRect(box, 5, 5)
        painter.setPen(QColor(255, 255, 255, 245))
        painter.drawText(box, Qt.AlignCenter, str(value))

    def _draw_hash(self, painter: QPainter, plot: QRect):
        buckets = {index: [] for index in range(8)}
        for value in self.values:
            buckets[value % 8].append(value)
        row_height = max(30, min(42, plot.height() // 9))
        top = plot.top() + 8
        for index, values in buckets.items():
            label = QRect(plot.left() + 30, top + index * row_height, 58, row_height - 5)
            painter.setBrush(QColor("#243c58"))
            painter.setPen(QPen(QColor("#5bd6b2"), 1))
            painter.drawRoundedRect(label, 4, 4)
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawText(label, Qt.AlignCenter, str(index))
            for offset, value in enumerate(values[:6]):
                box = QRect(label.right() + 14 + offset * 64, label.top(), 58, label.height())
                self._draw_box(painter, box, value)

    def _draw_graph(self, painter: QPainter, plot: QRect):
        shown = self.values[:9]
        radius = min(plot.width(), plot.height()) * 0.32
        points = [
            QPoint(
                int(plot.center().x() + math.cos(-math.pi / 2 + math.tau * index / max(1, len(shown))) * radius),
                int(plot.center().y() + math.sin(-math.pi / 2 + math.tau * index / max(1, len(shown))) * radius),
            )
            for index in range(len(shown))
        ]
        painter.setPen(QPen(QColor(105, 190, 245, 175), 2))
        for index in range(len(points)):
            if len(points) > 1:
                painter.drawLine(points[index], points[(index + 1) % len(points)])
            if index + 2 < len(points) and index % 2 == 0:
                painter.drawLine(points[index], points[index + 2])
        for value, point in zip(shown, points):
            self._draw_node(painter, point, value)

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        plot = rect.adjusted(24, 46, -24, -55)
        painter.fillRect(rect, QColor(5, 9, 14, 244))
        painter.setPen(QPen(QColor(91, 214, 178, 95), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        painter.setPen(QColor(255, 255, 255, 235))
        title_font = painter.font()
        title_font.setBold(True)
        title_font.setPointSize(11)
        painter.setFont(title_font)
        painter.drawText(rect.adjusted(14, 8, -14, -8), Qt.AlignTop | Qt.AlignLeft, self.structure)
        if self.structure == "Binary Search Tree":
            self._draw_tree(painter, plot, False)
        elif self.structure == "AVL Tree":
            self._draw_tree(painter, plot, True)
        elif self.structure == "Graph":
            self._draw_graph(painter, plot)
        elif self.structure == "Hash Table":
            self._draw_hash(painter, plot)
        else:
            self._draw_sequence(painter, plot, self.structure)
        painter.setPen(QColor(190, 210, 228, 205))
        painter.drawText(rect.adjusted(14, 0, -14, -10), Qt.AlignBottom | Qt.AlignLeft, self.status)


class PhysicsCanvas(QWidget):
    stats_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("PhysicsCanvas")
        self.setMinimumHeight(300)
        self.artifact: PhysicsArtifact | None = None
        self._initial_artifact: PhysicsArtifact | None = None
        self.running = True
        self.speed = 1.0
        self.render_mode = "2d"
        self.view_yaw = math.radians(38.0)
        self.view_pitch = math.radians(24.0)
        self.view_zoom = 1.0
        self._view_dragging = False
        self._view_last_mouse = QPoint()
        self.show_trails = False
        self._trails: dict[int, list[tuple[float, float, float]]] = {}
        self._replay: list[tuple[list[tuple[float, float, float, float, float, float]], dict]] = []
        self._collisions = 0
        self._frames = 0
        self._stats_started = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.step)
        self._timer.start(16)

    def set_artifact(self, artifact: PhysicsArtifact | None):
        self._initial_artifact = copy.deepcopy(artifact)
        self.artifact = copy.deepcopy(artifact)
        self._collisions = 0
        self._frames = 0
        self._stats_started = time.perf_counter()
        self._trails.clear()
        self._replay.clear()
        self.running = True
        self.show_trails = bool(
            artifact
            and artifact.instruction.get("parameters", {}).get("showTrails", False)
        )
        self.render_mode = "3d" if self._supports_3d_view(artifact) else "2d"
        self.view_yaw = math.radians(38.0)
        self.view_pitch = math.radians(24.0)
        self.view_zoom = 1.0
        self.update()

    def reset_simulation(self):
        self.artifact = copy.deepcopy(self._initial_artifact)
        self._collisions = 0
        self._frames = 0
        self._stats_started = time.perf_counter()
        self._trails.clear()
        self._replay.clear()
        self.running = True
        self.update()

    def set_running(self, running: bool):
        self.running = running

    def set_speed(self, speed: float):
        self.speed = max(0.05, min(5.0, speed))

    def set_render_mode(self, mode: str):
        if not self._supports_3d_view(self.artifact):
            self.render_mode = "2d"
        else:
            self.render_mode = "2d" if str(mode).lower().startswith("2") else "3d"
        self.update()

    @staticmethod
    def _supports_3d_view(artifact: PhysicsArtifact | None) -> bool:
        if not artifact:
            return False
        views = artifact.instruction.get("parameters", {}).get("views", ["2d"])
        return "3d" in views

    def set_gravity(self, gravity: float):
        if self.artifact:
            self.artifact.gravity = float(gravity)
            if self.artifact.simulation_type == "pendulum-2d":
                self.artifact.instruction.setdefault("parameters", {})[
                    "physicalGravity"
                ] = float(gravity)

    def set_show_vectors(self, visible: bool):
        if self.artifact:
            self.artifact.instruction.setdefault("parameters", {})["showVelocityVectors"] = bool(visible)
        self.update()

    def set_show_trails(self, visible: bool):
        self.show_trails = bool(visible)
        if not self.show_trails:
            self._trails.clear()
        self.update()

    def export_png(self, path: str) -> bool:
        return bool(path and self.grab().save(path, "PNG"))

    def export_json(self, path: str) -> bool:
        if not path or not self.artifact:
            return False
        payload = {
            "schema": "morice.physics-state.v1",
            "title": self.artifact.title,
            "simulationType": self.artifact.simulation_type,
            "parameters": copy.deepcopy(
                self.artifact.instruction.get("parameters", {})
            ),
            "gravity": self.artifact.gravity,
            "friction": self.artifact.friction,
            "restitution": self.artifact.restitution,
            "bounds": list(self.artifact.bounds),
            "particles": [
                {
                    "x": particle.x,
                    "y": particle.y,
                    "z": particle.z,
                    "vx": particle.vx,
                    "vy": particle.vy,
                    "vz": particle.vz,
                    "radius": particle.radius,
                    "mass": particle.mass,
                    "color": particle.color,
                }
                for particle in self.artifact.particles
            ],
        }
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except OSError:
            return False
        return os.path.isfile(path) and os.path.getsize(path) > 0

    def wheelEvent(self, event):
        if self._supports_3d_view(self.artifact) and self.render_mode == "3d":
            delta = event.angleDelta().y()
            if delta:
                self.view_zoom = max(0.45, min(2.6, self.view_zoom * (1.1 if delta > 0 else 0.9)))
                self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.LeftButton
            and self._supports_3d_view(self.artifact)
            and self.render_mode == "3d"
        ):
            self._view_dragging = True
            self._view_last_mouse = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._view_dragging:
            position = event.position().toPoint()
            delta = position - self._view_last_mouse
            self._view_last_mouse = position
            self.view_yaw += delta.x() * 0.009
            self.view_pitch = max(-1.2, min(1.2, self.view_pitch + delta.y() * 0.009))
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._view_dragging = False
        event.accept()

    def step_once(self):
        self._advance()
        self.update()

    def step_back(self):
        self.running = False
        if not self._replay or not self.artifact:
            return
        states, parameters = self._replay.pop()
        if len(states) != len(self.artifact.particles):
            return
        for particle, state in zip(self.artifact.particles, states):
            (
                particle.x,
                particle.y,
                particle.z,
                particle.vx,
                particle.vy,
                particle.vz,
            ) = state
        self.artifact.instruction["parameters"] = parameters
        self._frames = max(0, self._frames - 1)
        self.update()

    def step(self):
        if self.running and self.isVisible():
            self._advance()
            self.update()

    def _advance(self):
        if not self.artifact:
            return
        replay_limit = 45 if len(self.artifact.particles) > 300 else 120
        self._replay.append(
            (
                [
                    (
                        particle.x,
                        particle.y,
                        particle.z,
                        particle.vx,
                        particle.vy,
                        particle.vz,
                    )
                    for particle in self.artifact.particles
                ],
                copy.deepcopy(
                    self.artifact.instruction.get("parameters", {})
                ),
            )
        )
        if len(self._replay) > replay_limit:
            del self._replay[: len(self._replay) - replay_limit]
        width, height = self.artifact.bounds
        is_3d = self.artifact.simulation_type in {"particle-3d", "lorenz-3d"}
        depth = float(self.artifact.instruction.get("parameters", {}).get("depth") or height)
        dt = 1 / 60 * self.speed
        particles = self.artifact.particles
        frame_collisions = 0
        parameters = self.artifact.instruction.setdefault("parameters", {})
        if self.artifact.simulation_type == "lorenz-3d" and particles:
            sigma = float(parameters.get("sigma", 10.0))
            rho = float(parameters.get("rho", 28.0))
            beta = float(parameters.get("beta", 8.0 / 3.0))
            state = [float(value) for value in parameters.get("state", [0.1, 0.0, 0.0])]
            integration_step = max(0.0005, min(0.02, float(parameters.get("integrationStep", 0.005))))

            def derivative(current):
                x_value, y_value, z_value = current
                return (
                    sigma * (y_value - x_value),
                    x_value * (rho - z_value) - y_value,
                    x_value * y_value - beta * z_value,
                )

            remaining = dt
            while remaining > 1e-12:
                step_size = min(integration_step, remaining)
                k1 = derivative(state)
                k2 = derivative([state[index] + k1[index] * step_size * 0.5 for index in range(3)])
                k3 = derivative([state[index] + k2[index] * step_size * 0.5 for index in range(3)])
                k4 = derivative([state[index] + k3[index] * step_size for index in range(3)])
                state = [
                    state[index]
                    + step_size * (k1[index] + 2 * k2[index] + 2 * k3[index] + k4[index]) / 6.0
                    for index in range(3)
                ]
                remaining -= step_size
            parameters["state"] = state
            particle = particles[0]
            previous = (particle.x, particle.y, particle.z)
            particle.x = width * 0.5 + state[0] * 7.0
            particle.y = height * 0.5 + (state[2] - 25.0) * 5.2
            particle.z = height * 0.5 + state[1] * 7.0
            particle.vx = (particle.x - previous[0]) / max(1e-9, dt)
            particle.vy = (particle.y - previous[1]) / max(1e-9, dt)
            particle.vz = (particle.z - previous[2]) / max(1e-9, dt)
        elif self.artifact.simulation_type == "double-pendulum-2d" and len(particles) >= 2:
            anchor_x, anchor_y = [float(value) for value in parameters["anchor"]]
            length_1, length_2 = [float(value) for value in parameters["lengths"]]
            angle_1, angle_2 = [float(value) for value in parameters["angles"]]
            velocity_1, velocity_2 = [float(value) for value in parameters["angularVelocities"]]
            mass_1, mass_2 = [float(value) for value in parameters.get("masses", [1.0, 1.0])]
            physical_gravity = float(parameters.get("physicalGravity", 9.81))
            difference = angle_1 - angle_2
            common = 2 * mass_1 + mass_2 - mass_2 * math.cos(2 * difference)
            acceleration_1 = (
                -physical_gravity * (2 * mass_1 + mass_2) * math.sin(angle_1)
                - mass_2 * physical_gravity * math.sin(angle_1 - 2 * angle_2)
                - 2
                * math.sin(difference)
                * mass_2
                * (velocity_2 * velocity_2 * length_2 + velocity_1 * velocity_1 * length_1 * math.cos(difference))
            ) / max(1e-9, length_1 * common)
            acceleration_2 = (
                2
                * math.sin(difference)
                * (
                    velocity_1 * velocity_1 * length_1 * (mass_1 + mass_2)
                    + physical_gravity * (mass_1 + mass_2) * math.cos(angle_1)
                    + velocity_2 * velocity_2 * length_2 * mass_2 * math.cos(difference)
                )
            ) / max(1e-9, length_2 * common)
            velocity_1 += acceleration_1 * dt
            velocity_2 += acceleration_2 * dt
            angle_1 += velocity_1 * dt
            angle_2 += velocity_2 * dt
            parameters["angles"] = [angle_1, angle_2]
            parameters["angularVelocities"] = [velocity_1, velocity_2]
            first, second = particles[:2]
            previous_first = (first.x, first.y)
            previous_second = (second.x, second.y)
            first.x = anchor_x + math.sin(angle_1) * length_1
            first.y = anchor_y + math.cos(angle_1) * length_1
            second.x = first.x + math.sin(angle_2) * length_2
            second.y = first.y + math.cos(angle_2) * length_2
            first.vx = (first.x - previous_first[0]) / max(1e-9, dt)
            first.vy = (first.y - previous_first[1]) / max(1e-9, dt)
            second.vx = (second.x - previous_second[0]) / max(1e-9, dt)
            second.vy = (second.y - previous_second[1]) / max(1e-9, dt)
        elif self.artifact.simulation_type == "pendulum-2d" and particles:
            anchor_x, anchor_y = [float(value) for value in parameters["anchor"]]
            length = float(parameters["length"])
            angle = float(parameters.get("angleRadians", 0.0))
            angular_velocity = float(parameters.get("angularVelocity", 0.0))
            physical_gravity = float(parameters.get("physicalGravity", 9.81))
            # Semi-implicit Euler is symplectic and much more stable for the
            # lossless pendulum than explicit Euler.
            angular_acceleration = -(physical_gravity / max(1e-9, length / 20.0)) * math.sin(angle)
            angular_velocity += angular_acceleration * dt
            angle += angular_velocity * dt
            parameters["angleRadians"] = angle
            parameters["angularVelocity"] = angular_velocity
            particle = particles[0]
            previous_x, previous_y = particle.x, particle.y
            particle.x = anchor_x + math.sin(angle) * length
            particle.y = anchor_y + math.cos(angle) * length
            particle.vx = (particle.x - previous_x) / max(1e-9, dt)
            particle.vy = (particle.y - previous_y) / max(1e-9, dt)
        elif self.artifact.simulation_type == "wave-2d":
            phase = float(parameters.get("phase", 0.0))
            phase += float(parameters["angularFrequency"]) * dt
            parameters["phase"] = phase
            amplitude = float(parameters["amplitude"])
            wavelength = float(parameters["wavelength"])
            center_y = height * 0.5
            for particle in particles:
                previous_y = particle.y
                particle.y = center_y + amplitude * math.sin(
                    math.tau * particle.x / wavelength - phase
                )
                particle.vy = (particle.y - previous_y) / max(1e-9, dt)
        elif self.artifact.simulation_type == "circular-motion-2d" and particles:
            angle = float(parameters.get("angleRadians", 0.0))
            angular_speed = float(parameters["angularSpeed"])
            angle = (angle + angular_speed * dt) % math.tau
            parameters["angleRadians"] = angle
            center_x, center_y = [float(value) for value in parameters["center"]]
            radius = float(parameters["radius"])
            particle = particles[0]
            particle.x = center_x + math.cos(angle) * radius
            particle.y = center_y + math.sin(angle) * radius
            particle.vx = -math.sin(angle) * radius * angular_speed
            particle.vy = math.cos(angle) * radius * angular_speed
        for particle in particles:
            if self.artifact.simulation_type in {
                "pendulum-2d",
                "double-pendulum-2d",
                "lorenz-3d",
                "wave-2d",
                "circular-motion-2d",
            }:
                continue
            if self.artifact.simulation_type == "spring-2d":
                anchor_x, anchor_y = width * 0.5, height * 0.5
                spring_k = 3.8
                damping = 0.18
                particle.vx += (-spring_k * (particle.x - anchor_x) / particle.mass - damping * particle.vx) * dt
                particle.vy += (-spring_k * (particle.y - anchor_y) / particle.mass - damping * particle.vy) * dt
            elif self.artifact.simulation_type == "orbit-2d":
                dx = width * 0.5 - particle.x
                dy = height * 0.5 - particle.y
                distance_sq = max(625.0, dx * dx + dy * dy)
                distance = math.sqrt(distance_sq)
                acceleration = 900_000.0 / distance_sq
                particle.vx += acceleration * dx / distance * dt
                particle.vy += acceleration * dy / distance * dt
            else:
                particle.vy += self.artifact.gravity * dt
            particle.vx *= self.artifact.friction
            particle.vy *= self.artifact.friction
            if is_3d:
                particle.vz *= self.artifact.friction
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            if is_3d:
                particle.z += particle.vz * dt
            if particle.x - particle.radius < 0:
                particle.x = particle.radius
                particle.vx = abs(particle.vx) * self.artifact.restitution
                frame_collisions += 1
            elif particle.x + particle.radius > width:
                particle.x = width - particle.radius
                particle.vx = -abs(particle.vx) * self.artifact.restitution
                frame_collisions += 1
            if particle.y - particle.radius < 0:
                particle.y = particle.radius
                particle.vy = abs(particle.vy) * self.artifact.restitution
                frame_collisions += 1
            elif particle.y + particle.radius > height:
                particle.y = height - particle.radius
                particle.vy = -abs(particle.vy) * self.artifact.restitution
                frame_collisions += 1
            if is_3d and particle.z - particle.radius < 0:
                particle.z = particle.radius
                particle.vz = abs(particle.vz) * self.artifact.restitution
                frame_collisions += 1
            elif is_3d and particle.z + particle.radius > depth:
                particle.z = depth - particle.radius
                particle.vz = -abs(particle.vz) * self.artifact.restitution
                frame_collisions += 1

        if self.artifact.simulation_type not in {
            "projectile-2d",
            "spring-2d",
            "orbit-2d",
            "pendulum-2d",
            "double-pendulum-2d",
            "lorenz-3d",
            "wave-2d",
            "circular-motion-2d",
        }:
            cell_size = max(16.0, max((particle.radius for particle in particles), default=4.0) * 2.2)
            spatial_grid: dict[tuple[int, int, int], list[int]] = {}
            for index, particle in enumerate(particles):
                cell = (
                    int(particle.x // cell_size),
                    int(particle.y // cell_size),
                    int(particle.z // cell_size) if is_3d else 0,
                )
                spatial_grid.setdefault(cell, []).append(index)

            checked_pairs: set[tuple[int, int]] = set()
            for (cell_x, cell_y, cell_z), indices in spatial_grid.items():
                nearby = []
                for offset_x in (-1, 0, 1):
                    for offset_y in (-1, 0, 1):
                        z_offsets = (-1, 0, 1) if is_3d else (0,)
                        for offset_z in z_offsets:
                            nearby.extend(
                                spatial_grid.get(
                                    (cell_x + offset_x, cell_y + offset_y, cell_z + offset_z),
                                    (),
                                )
                            )
                for first_index in indices:
                    first = particles[first_index]
                    for second_index in nearby:
                        if second_index == first_index:
                            continue
                        pair = (min(first_index, second_index), max(first_index, second_index))
                        if pair in checked_pairs:
                            continue
                        checked_pairs.add(pair)
                        second = particles[second_index]
                        dx = second.x - first.x
                        dy = second.y - first.y
                        dz = second.z - first.z if is_3d else 0.0
                        min_dist = first.radius + second.radius
                        dist_sq = dx * dx + dy * dy + dz * dz
                        if dist_sq < min_dist * min_dist:
                            if dist_sq <= 1e-12:
                                dist = min_dist
                                nx, ny, nz = 1.0, 0.0, 0.0
                            else:
                                dist = math.sqrt(dist_sq)
                                nx = dx / dist
                                ny = dy / dist
                                nz = dz / dist if is_3d else 0.0
                            inverse_first = 1.0 / max(1e-6, first.mass)
                            inverse_second = 1.0 / max(1e-6, second.mass)
                            inverse_total = inverse_first + inverse_second
                            overlap = max(0.0, min_dist - dist)
                            correction = overlap / inverse_total
                            first.x -= nx * correction * inverse_first
                            first.y -= ny * correction * inverse_first
                            first.z -= nz * correction * inverse_first
                            second.x += nx * correction * inverse_second
                            second.y += ny * correction * inverse_second
                            second.z += nz * correction * inverse_second

                            relative_normal_velocity = (
                                (second.vx - first.vx) * nx + (second.vy - first.vy) * ny
                                + (second.vz - first.vz) * nz
                            )
                            if relative_normal_velocity < 0:
                                impulse = (
                                    -(1.0 + self.artifact.restitution)
                                    * relative_normal_velocity
                                    / inverse_total
                                )
                                impulse_x = impulse * nx
                                impulse_y = impulse * ny
                                impulse_z = impulse * nz
                                first.vx -= impulse_x * inverse_first
                                first.vy -= impulse_y * inverse_first
                                first.vz -= impulse_z * inverse_first
                                second.vx += impulse_x * inverse_second
                                second.vy += impulse_y * inverse_second
                                second.vz += impulse_z * inverse_second
                            frame_collisions += 1

        self._collisions += frame_collisions
        self._frames += 1
        if self.show_trails:
            trail_limit = min(100, len(particles))
            for index, particle in enumerate(particles[:trail_limit]):
                trail = self._trails.setdefault(index, [])
                trail.append((particle.x, particle.y, particle.z))
                if len(trail) > 42:
                    del trail[:-42]
        if self._frames % 20 == 0:
            elapsed = max(1e-6, time.perf_counter() - self._stats_started)
            measured_fps = self._frames / elapsed
            runtime = get_runtime_services()
            if runtime.started and measured_fps > 0:
                runtime.profiler.set_frame_time(1000.0 / measured_fps)
            kinetic_energy = sum(
                0.5
                * particle.mass
                * (
                    particle.vx * particle.vx
                    + particle.vy * particle.vy
                    + (particle.vz * particle.vz if is_3d else 0.0)
                )
                for particle in particles
            )
            stats = (
                f"Particles: {len(particles)} | FPS: {measured_fps:.0f} | "
                f"Collisions/sec: {int((self._collisions / max(1, self._frames)) * 60)} | "
                f"Energy: {kinetic_energy:.3g} | Speed: {self.speed:g}x"
            )
            self.stats_changed.emit(stats)

    def _project_particle_3d(
        self,
        x: float,
        y: float,
        z: float,
        sim_w: float,
        sim_h: float,
        depth: float,
        field: QRect,
    ) -> tuple[QPoint, float, float]:
        xn = (x - sim_w * 0.5) / max(1e-9, sim_w * 0.5)
        yn = (y - sim_h * 0.5) / max(1e-9, sim_h * 0.5)
        zn = (z - depth * 0.5) / max(1e-9, depth * 0.5)
        cos_yaw = math.cos(self.view_yaw)
        sin_yaw = math.sin(self.view_yaw)
        x_rotated = xn * cos_yaw - zn * sin_yaw
        z_rotated = xn * sin_yaw + zn * cos_yaw
        vertical = yn * math.cos(self.view_pitch) - z_rotated * math.sin(self.view_pitch)
        view_depth = yn * math.sin(self.view_pitch) + z_rotated * math.cos(self.view_pitch)
        scale = min(field.width(), field.height()) * 0.36 * self.view_zoom
        point = QPoint(
            int(field.center().x() + x_rotated * scale),
            int(field.center().y() + vertical * scale),
        )
        return point, view_depth, scale

    def paintEvent(self, event):  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, QColor(5, 7, 12, 235))
        painter.setPen(QPen(QColor(150, 120, 225, 70), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 12, 12)
        if not self.artifact:
            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(rect, Qt.AlignCenter, "No simulation generated yet")
            return
        sim_w, sim_h = self.artifact.bounds
        is_3d = self.artifact.simulation_type in {"particle-3d", "lorenz-3d"}
        supports_3d_view = self._supports_3d_view(self.artifact)
        depth = float(self.artifact.instruction.get("parameters", {}).get("depth") or sim_h)
        if supports_3d_view and self.render_mode == "3d":
            field = rect.adjusted(24, 38, -24, -28)
            painter.setPen(QPen(QColor(160, 205, 245, 70), 1))
            corners: dict[tuple[int, int, int], QPoint] = {}
            for x_side in (0, 1):
                for y_side in (0, 1):
                    for z_side in (0, 1):
                        point, _view_depth, _scale = self._project_particle_3d(
                            sim_w * x_side,
                            sim_h * y_side,
                            depth * z_side,
                            sim_w,
                            sim_h,
                            depth,
                            field,
                        )
                        corners[(x_side, y_side, z_side)] = point
            for corner, point in corners.items():
                for axis in range(3):
                    adjacent = list(corner)
                    adjacent[axis] = 1 - adjacent[axis]
                    adjacent_key = tuple(adjacent)
                    if corner[axis] == 0:
                        painter.drawLine(point, corners[adjacent_key])

            if self.artifact.simulation_type == "double-pendulum-2d" and len(self.artifact.particles) >= 2:
                parameters = self.artifact.instruction.get("parameters", {})
                anchor_values = parameters.get("anchor", [sim_w * 0.5, 55.0])
                anchor = self._project_particle_3d(
                    float(anchor_values[0]),
                    float(anchor_values[1]),
                    depth * 0.5,
                    sim_w,
                    sim_h,
                    depth,
                    field,
                )[0]
                first = self._project_particle_3d(
                    self.artifact.particles[0].x,
                    self.artifact.particles[0].y,
                    self.artifact.particles[0].z,
                    sim_w,
                    sim_h,
                    depth,
                    field,
                )[0]
                second = self._project_particle_3d(
                    self.artifact.particles[1].x,
                    self.artifact.particles[1].y,
                    self.artifact.particles[1].z,
                    sim_w,
                    sim_h,
                    depth,
                    field,
                )[0]
                painter.setPen(QPen(QColor(215, 226, 240, 225), 3))
                painter.drawLine(anchor, first)
                painter.drawLine(first, second)

            if self.show_trails:
                for index, trail in self._trails.items():
                    if len(trail) < 2:
                        continue
                    color = QColor(self.artifact.particles[index].color)
                    color.setAlpha(88)
                    painter.setPen(QPen(color, 1))
                    path = QPainterPath()
                    first = self._project_particle_3d(
                        *trail[0],
                        sim_w,
                        sim_h,
                        depth,
                        field,
                    )[0]
                    path.moveTo(first)
                    for trail_point in trail[1:]:
                        projected = self._project_particle_3d(
                            *trail_point,
                            sim_w,
                            sim_h,
                            depth,
                            field,
                        )[0]
                        path.lineTo(projected)
                    painter.drawPath(path)

            projected_particles = []
            for particle in self.artifact.particles:
                point, view_depth, scale = self._project_particle_3d(
                    particle.x,
                    particle.y,
                    particle.z,
                    sim_w,
                    sim_h,
                    depth,
                    field,
                )
                projected_particles.append((view_depth, point, scale, particle))
            for view_depth, point, scale, particle in sorted(projected_particles, key=lambda item: item[0]):
                perspective = max(0.62, min(1.38, 1.0 + view_depth * 0.16))
                radius = max(2.0, particle.radius * scale / max(sim_w, sim_h) * 5.0 * perspective)
                color = QColor(particle.color)
                color.setAlpha(max(120, min(255, int(215 + view_depth * 24))))
                painter.setBrush(color)
                painter.setPen(QPen(QColor(color).lighter(135), 1))
                painter.drawEllipse(point, int(radius), int(radius))
                if self.artifact.instruction.get("parameters", {}).get("showVelocityVectors"):
                    end = self._project_particle_3d(
                        particle.x + particle.vx * 0.12,
                        particle.y + particle.vy * 0.12,
                        particle.z + particle.vz * 0.12,
                        sim_w,
                        sim_h,
                        depth,
                        field,
                    )[0]
                    painter.drawLine(point, end)
            painter.setPen(QColor(255, 255, 255, 218))
            painter.drawText(
                rect.adjusted(12, 6, -12, -6),
                Qt.AlignTop | Qt.AlignLeft,
                f"{self.artifact.title} | 3D view | drag rotate, wheel zoom",
            )
            return

        scale = min((rect.width() - 36) / sim_w, (rect.height() - 58) / sim_h)
        left = rect.left() + (rect.width() - sim_w * scale) / 2
        top = rect.top() + 34
        field = QRect(int(left), int(top), int(sim_w * scale), int(sim_h * scale))
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1))
        painter.setBrush(QColor(255, 255, 255, 10))
        painter.drawRoundedRect(field, 8, 8)
        painter.setClipRect(field)
        if self.artifact.simulation_type == "spring-2d" and self.artifact.particles:
            anchor = QPoint(int(left + sim_w * 0.5 * scale), int(top + sim_h * 0.5 * scale))
            particle = self.artifact.particles[0]
            end = QPoint(int(left + particle.x * scale), int(top + particle.y * scale))
            painter.setPen(QPen(QColor(170, 130, 255, 210), 2))
            painter.drawLine(anchor, end)
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(anchor, 5, 5)
        elif self.artifact.simulation_type == "double-pendulum-2d" and len(self.artifact.particles) >= 2:
            anchor_values = self.artifact.instruction.get("parameters", {}).get(
                "anchor", [sim_w * 0.5, 55.0]
            )
            anchor = QPoint(
                int(left + float(anchor_values[0]) * scale),
                int(top + float(anchor_values[1]) * scale),
            )
            first = self.artifact.particles[0]
            second = self.artifact.particles[1]
            first_point = QPoint(int(left + first.x * scale), int(top + first.y * scale))
            second_point = QPoint(int(left + second.x * scale), int(top + second.y * scale))
            painter.setPen(QPen(QColor(205, 218, 238, 220), 3))
            painter.drawLine(anchor, first_point)
            painter.drawLine(first_point, second_point)
            painter.setBrush(QColor(255, 255, 255, 235))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(anchor, 5, 5)
        elif self.artifact.simulation_type == "pendulum-2d" and self.artifact.particles:
            anchor_values = self.artifact.instruction.get("parameters", {}).get(
                "anchor", [sim_w * 0.5, 72.0]
            )
            anchor = QPoint(
                int(left + float(anchor_values[0]) * scale),
                int(top + float(anchor_values[1]) * scale),
            )
            particle = self.artifact.particles[0]
            end = QPoint(int(left + particle.x * scale), int(top + particle.y * scale))
            painter.setPen(QPen(QColor(205, 218, 238, 220), 3))
            painter.drawLine(anchor, end)
            painter.setBrush(QColor(255, 255, 255, 235))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(anchor, 5, 5)
        elif self.artifact.simulation_type == "wave-2d" and self.artifact.particles:
            path = QPainterPath()
            first = self.artifact.particles[0]
            path.moveTo(left + first.x * scale, top + first.y * scale)
            for particle in self.artifact.particles[1:]:
                path.lineTo(left + particle.x * scale, top + particle.y * scale)
            painter.setPen(QPen(QColor("#64d8ff"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        elif self.artifact.simulation_type == "circular-motion-2d":
            parameters = self.artifact.instruction.get("parameters", {})
            center_values = parameters.get("center", [sim_w * 0.5, sim_h * 0.5])
            orbit_radius = float(parameters.get("radius", 118.0)) * scale
            center = QPoint(
                int(left + float(center_values[0]) * scale),
                int(top + float(center_values[1]) * scale),
            )
            painter.setPen(QPen(QColor(119, 202, 255, 90), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, int(orbit_radius), int(orbit_radius))
        elif self.artifact.simulation_type == "orbit-2d":
            center = QPoint(int(left + sim_w * 0.5 * scale), int(top + sim_h * 0.5 * scale))
            painter.setBrush(QColor("#ffd166"))
            painter.setPen(QPen(QColor(255, 230, 150, 160), 2))
            painter.drawEllipse(center, 11, 11)
        if self.show_trails:
            for index, trail in self._trails.items():
                if len(trail) < 2:
                    continue
                color = QColor(self.artifact.particles[index].color)
                color.setAlpha(90)
                painter.setPen(QPen(color, 1))
                path = QPainterPath()
                first_x, first_y, _first_z = trail[0]
                path.moveTo(left + first_x * scale, top + first_y * scale)
                for trail_x, trail_y, _trail_z in trail[1:]:
                    path.lineTo(left + trail_x * scale, top + trail_y * scale)
                painter.drawPath(path)
        for index, particle in enumerate(self.artifact.particles):
            px = left + particle.x * scale
            py = top + particle.y * scale
            radius = max(1.5, particle.radius * scale)
            color = QColor(particle.color)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPoint(int(px), int(py)), int(radius), int(radius))
            if self.artifact.instruction.get("parameters", {}).get("showVelocityVectors"):
                painter.setPen(QPen(QColor(color).lighter(135), 1))
                painter.drawLine(
                    QPoint(int(px), int(py)),
                    QPoint(int(px + particle.vx * scale * 0.12), int(py + particle.vy * scale * 0.12)),
                )
        painter.setClipping(False)
        painter.setPen(QColor(255, 255, 255, 218))
        mode_label = " | 2D projection" if supports_3d_view else ""
        painter.drawText(
            rect.adjusted(12, 6, -12, -6),
            Qt.AlignTop | Qt.AlignLeft,
            self.artifact.title + mode_label,
        )


class VisualizationGenerationCard(QFrame):
    def __init__(self, renderer_label: str):
        super().__init__()
        self.setObjectName("VisualizationGenerationCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.title = QLabel("Generating interactive visualization")
        self.title.setObjectName("VisualizationGenerationTitle")
        self.stage = QLabel("Queued")
        self.stage.setObjectName("VisualizationGenerationStage")
        self.detail = QLabel(f"Waiting for {renderer_label}.")
        self.detail.setObjectName("VisualizationGenerationDetail")
        self.detail.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setObjectName("VisualizationGenerationProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)

        layout.addWidget(self.title)
        layout.addWidget(self.stage)
        layout.addWidget(self.detail)
        layout.addWidget(self.progress)

    def set_stage(self, stage: str, detail: str, percent: int):
        self.stage.setText(stage or "Working")
        self.detail.setText(detail or "")
        self.progress.setValue(max(0, min(100, int(percent))))

    def set_error(self, message: str):
        self.setProperty("error", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        self.title.setText("Visualization unavailable")
        self.stage.setText("Nothing was rendered")
        self.detail.setText(message)
        self.progress.setValue(100)


class InlineGraphWorkspace(QFrame):
    def __init__(self, artifact: GraphArtifact, parent=None):
        super().__init__(parent)
        self.artifact = artifact
        self.setObjectName("InlineVisualization")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel(artifact.title)
        title.setObjectName("InlineVisualizationTitle")
        kind = QLabel("Interactive surface" if artifact.surface else "Interactive graph")
        kind.setObjectName("InlineVisualizationKind")
        header.addWidget(title, stretch=1)
        header.addWidget(kind)

        controls = QHBoxLayout()
        controls.setSpacing(7)
        reset_button = QPushButton("Reset view")
        reset_button.setObjectName("InlineVisualizationControl")
        reset_button.clicked.connect(self._reset)
        large_button = QPushButton("Open large")
        large_button.setObjectName("InlineVisualizationControl")
        large_button.clicked.connect(self._open_large)
        png_button = QPushButton("PNG")
        png_button.setObjectName("InlineVisualizationControl")
        png_button.clicked.connect(lambda: self._export("png"))
        svg_button = QPushButton("SVG")
        svg_button.setObjectName("InlineVisualizationControl")
        svg_button.clicked.connect(lambda: self._export("svg"))
        pdf_button = QPushButton("PDF")
        pdf_button.setObjectName("InlineVisualizationControl")
        pdf_button.clicked.connect(lambda: self._export("pdf"))
        controls.addWidget(reset_button)
        controls.addWidget(large_button)
        self.dimension_select: QComboBox | None = None
        if artifact.surface:
            dimension_label = QLabel("View")
            dimension_label.setObjectName("InlineVisualizationParameter")
            self.dimension_select = QComboBox()
            self.dimension_select.setObjectName("InlineVisualizationSelect")
            self.dimension_select.addItem("2D", "2d")
            self.dimension_select.addItem("3D", "3d")
            self.dimension_select.setCurrentText("3D")
            controls.addWidget(dimension_label)
            controls.addWidget(self.dimension_select)
        controls.addStretch(1)
        controls.addWidget(png_button)
        controls.addWidget(svg_button)
        controls.addWidget(pdf_button)

        self.canvas = SurfaceCanvas() if artifact.surface else GraphCanvas()
        self.canvas.setMinimumHeight(350)
        self.canvas.set_artifact(artifact)
        if self.dimension_select:
            self.dimension_select.currentIndexChanged.connect(
                lambda index: self.canvas.set_view_mode(str(self.dimension_select.itemData(index)))
            )
        self.inspector = QLabel("Move over the curve for exact coordinates. Use the wheel to zoom and drag to pan.")
        if artifact.surface:
            self.inspector.setText(
                "Switch between the 2D height map and 3D mesh. Hover for the same validated x, y, z samples."
            )
        self.inspector.setObjectName("InlineVisualizationInspector")
        self.inspector.setWordWrap(True)
        self.canvas.inspected.connect(self.inspector.setText)
        equations = QLabel(
            artifact.surface.label
            if artifact.surface
            else "   ".join(series.label for series in artifact.series)
        )
        equations.setObjectName("InlineVisualizationEquation")
        equations.setWordWrap(True)

        layout.addLayout(header)
        layout.addLayout(controls)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(equations)
        layout.addWidget(self.inspector)

    def _reset(self):
        self.canvas.reset_view()
        self.inspector.setText("View reset. Move over the curve for exact coordinates.")

    def _open_large(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.artifact.title)
        dialog.resize(1100, 760)
        layout = QVBoxLayout(dialog)
        canvas = SurfaceCanvas() if self.artifact.surface else GraphCanvas()
        canvas.set_artifact(self.artifact)
        if self.artifact.surface and self.dimension_select:
            canvas.set_view_mode(str(self.dimension_select.currentData()))
        layout.addWidget(canvas)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.show()
        dialog.raise_()

    def _export(self, export_format: str):
        filters = {
            "png": ("PNG image (*.png)", ".png"),
            "svg": ("SVG vector image (*.svg)", ".svg"),
            "pdf": ("PDF document (*.pdf)", ".pdf"),
        }
        selected_filter, extension = filters[export_format]
        path, _ = QFileDialog.getSaveFileName(self, f"Export {self.artifact.title}", "", selected_filter)
        if not path:
            return
        if not path.lower().endswith(extension):
            path += extension
        exporters = {
            "png": self.canvas.export_png,
            "svg": self.canvas.export_svg,
            "pdf": self.canvas.export_pdf,
        }
        succeeded = exporters[export_format](path)
        self.inspector.setText(f"Exported to {path}" if succeeded else f"Could not export {path}")


class InlinePhysicsWorkspace(QFrame):
    def __init__(self, artifact: PhysicsArtifact, parent=None):
        super().__init__(parent)
        self.artifact = artifact
        self.setObjectName("InlineVisualization")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel(artifact.title)
        title.setObjectName("InlineVisualizationTitle")
        kind = QLabel("Live physics")
        kind.setObjectName("InlineVisualizationKind")
        header.addWidget(title, stretch=1)
        header.addWidget(kind)

        controls = QHBoxLayout()
        controls.setSpacing(7)
        pause_button = QPushButton("Pause")
        pause_button.setObjectName("InlineVisualizationControl")
        pause_button.clicked.connect(lambda: self.canvas.set_running(False))
        resume_button = QPushButton("Resume")
        resume_button.setObjectName("InlineVisualizationControl")
        resume_button.clicked.connect(lambda: self.canvas.set_running(True))
        step_button = QPushButton("Step")
        step_button.setObjectName("InlineVisualizationControl")
        step_button.clicked.connect(self.canvas_step)
        back_button = QPushButton("Step back")
        back_button.setObjectName("InlineVisualizationControl")
        back_button.clicked.connect(self.canvas_back)
        reset_button = QPushButton("Reset")
        reset_button.setObjectName("InlineVisualizationControl")
        reset_button.clicked.connect(self._reset)
        large_button = QPushButton("Open large")
        large_button.setObjectName("InlineVisualizationControl")
        large_button.clicked.connect(self._open_large)
        screenshot_button = QPushButton("PNG")
        screenshot_button.setObjectName("InlineVisualizationControl")
        screenshot_button.clicked.connect(self._export_png)
        json_button = QPushButton("JSON")
        json_button.setObjectName("InlineVisualizationControl")
        json_button.clicked.connect(self._export_json)
        controls.addWidget(pause_button)
        controls.addWidget(resume_button)
        controls.addWidget(step_button)
        controls.addWidget(back_button)
        controls.addWidget(reset_button)
        controls.addWidget(large_button)
        controls.addStretch(1)
        controls.addWidget(json_button)
        controls.addWidget(screenshot_button)

        parameter_row = QHBoxLayout()
        parameter_row.setSpacing(10)
        speed_label = QLabel("Speed")
        speed_label.setObjectName("InlineVisualizationParameter")
        self.speed_select = QComboBox()
        self.speed_select.setObjectName("InlineVisualizationSelect")
        for label, value in (("0.25x", 0.25), ("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("5x", 5.0)):
            self.speed_select.addItem(label, value)
        self.speed_select.setCurrentText("1x")
        self.speed_select.currentIndexChanged.connect(
            lambda index: self.canvas.set_speed(float(self.speed_select.itemData(index)))
        )
        self.dimension_select: QComboBox | None = None
        if "3d" in artifact.instruction.get("parameters", {}).get("views", ["2d"]):
            dimension_label = QLabel("View")
            dimension_label.setObjectName("InlineVisualizationParameter")
            self.dimension_select = QComboBox()
            self.dimension_select.setObjectName("InlineVisualizationSelect")
            self.dimension_select.addItem("2D", "2d")
            self.dimension_select.addItem("3D", "3d")
            self.dimension_select.setCurrentText("3D")
            parameter_row.addWidget(dimension_label)
            parameter_row.addWidget(self.dimension_select)
        vectors = QCheckBox("Velocity vectors")
        vectors.setObjectName("InlineVisualizationCheck")
        vectors.setChecked(
            bool(artifact.instruction.get("parameters", {}).get("showVelocityVectors"))
        )
        vectors.toggled.connect(self.canvas_vectors)
        trails = QCheckBox("Trails")
        trails.setObjectName("InlineVisualizationCheck")
        trails.setChecked(bool(artifact.instruction.get("parameters", {}).get("showTrails")))
        trails.toggled.connect(self.canvas_trails)
        parameter_row.addWidget(speed_label)
        parameter_row.addWidget(self.speed_select)
        parameter_row.addWidget(vectors)
        parameter_row.addWidget(trails)
        parameter_row.addStretch(1)

        gravity_row = QHBoxLayout()
        gravity_label = QLabel(f"Gravity {artifact.gravity:g} canvas units/s²")
        gravity_label.setObjectName("InlineVisualizationParameter")
        self.gravity_label = gravity_label
        gravity_slider = QSlider(Qt.Horizontal)
        gravity_slider.setObjectName("InlineVisualizationSlider")
        gravity_slider.setRange(-200, 500)
        gravity_slider.setValue(int(artifact.gravity))
        gravity_slider.valueChanged.connect(self._set_gravity)
        gravity_row.addWidget(gravity_label)
        gravity_row.addWidget(gravity_slider, stretch=1)

        self.canvas = PhysicsCanvas()
        self.canvas.setMinimumHeight(350)
        self.canvas.set_artifact(artifact)
        self.canvas.set_show_trails(trails.isChecked())
        if self.dimension_select:
            self.dimension_select.currentIndexChanged.connect(
                lambda index: self.canvas.set_render_mode(str(self.dimension_select.itemData(index)))
            )
            self.canvas.set_render_mode(str(self.dimension_select.currentData()))
        self.stats = QLabel("Preparing live statistics...")
        self.stats.setObjectName("InlineVisualizationInspector")
        self.stats.setWordWrap(True)
        self.canvas.stats_changed.connect(self.stats.setText)

        layout.addLayout(header)
        layout.addLayout(controls)
        layout.addLayout(parameter_row)
        layout.addLayout(gravity_row)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self.stats)

    def canvas_step(self):
        self.canvas.set_running(False)
        self.canvas.step_once()

    def canvas_back(self):
        self.canvas.step_back()
        self.stats.setText("Moved back one recorded simulation step.")

    def canvas_vectors(self, visible: bool):
        self.canvas.set_show_vectors(visible)

    def canvas_trails(self, visible: bool):
        self.canvas.set_show_trails(visible)

    def _set_gravity(self, value: int):
        self.gravity_label.setText(f"Gravity {value} canvas units/s²")
        self.canvas.set_gravity(float(value))

    def _reset(self):
        self.canvas.reset_simulation()
        self.speed_select.setCurrentText("1x")
        if self.dimension_select:
            self.dimension_select.setCurrentText("3D")
        self.stats.setText("Simulation reset to its validated initial state.")

    def _open_large(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.artifact.title)
        dialog.setWindowIcon(QIcon(_icon_path()))
        dialog.resize(1120, 780)
        layout = QVBoxLayout(dialog)
        canvas = PhysicsCanvas()
        canvas.set_artifact(self.artifact)
        if self.dimension_select:
            canvas.set_render_mode(str(self.dimension_select.currentData()))
        canvas.set_speed(float(self.speed_select.currentData()))
        layout.addWidget(canvas)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.show()
        dialog.raise_()

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, f"Export {self.artifact.title}", "", "PNG image (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        succeeded = self.canvas.export_png(path)
        self.stats.setText(f"Exported to {path}" if succeeded else f"Could not export {path}")

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {self.artifact.title} state",
            "",
            "JSON simulation state (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        succeeded = self.canvas.export_json(path)
        self.stats.setText(f"Exported to {path}" if succeeded else f"Could not export {path}")


class InlineMoleculeWorkspace(QFrame):
    def __init__(self, artifact: MoleculeArtifact, parent=None):
        super().__init__(parent)
        self.artifact = artifact
        self.setObjectName("InlineVisualization")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(570)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel(artifact.title)
        title.setObjectName("InlineVisualizationTitle")
        kind = QLabel("Validated molecular model")
        kind.setObjectName("InlineVisualizationKind")
        header.addWidget(title, stretch=1)
        header.addWidget(kind)

        controls = QHBoxLayout()
        controls.setSpacing(7)
        reset_button = QPushButton("Reset view")
        reset_button.setObjectName("InlineVisualizationControl")
        reset_button.clicked.connect(self._reset)
        large_button = QPushButton("Open large")
        large_button.setObjectName("InlineVisualizationControl")
        large_button.clicked.connect(self._open_large)
        controls.addWidget(reset_button)
        controls.addWidget(large_button)
        controls.addWidget(QLabel("View"))
        self.dimension_select = QComboBox()
        self.dimension_select.setObjectName("InlineVisualizationSelect")
        self.dimension_select.addItem("2D", "2d")
        self.dimension_select.addItem("3D", "3d")
        self.dimension_select.setCurrentText("3D")
        controls.addWidget(self.dimension_select)
        controls.addStretch(1)
        for label, export_format in (("PNG", "png"), ("SVG", "svg"), ("PDF", "pdf")):
            button = QPushButton(label)
            button.setObjectName("InlineVisualizationControl")
            button.clicked.connect(
                lambda _checked=False, selected=export_format: self._export(selected)
            )
            controls.addWidget(button)

        self.canvas = MoleculeCanvas()
        self.canvas.set_artifact(artifact)
        self.dimension_select.currentIndexChanged.connect(
            lambda index: self.canvas.set_view_mode(
                str(self.dimension_select.itemData(index))
            )
        )
        self.canvas.set_view_mode("3d")
        self.inspector = QLabel(
            "Drag the 3D model to rotate, or switch to the 2D structure schematic. "
            "Hover an atom for its validated coordinates."
        )
        self.inspector.setObjectName("InlineVisualizationInspector")
        self.inspector.setWordWrap(True)
        self.canvas.inspected.connect(self.inspector.setText)
        angles = ", ".join(f"{value:g} deg" for value in artifact.reference_angles)
        details = QLabel(
            f"Formula: {artifact.formula} | molecular geometry: {artifact.geometry} | "
            f"electron geometry: {artifact.electron_geometry} | central lone pairs: "
            f"{artifact.central_lone_pairs} | reference angles: {angles} | "
            f"coordinate model: {artifact.coordinate_model}"
        )
        details.setObjectName("InlineVisualizationEquation")
        details.setWordWrap(True)
        notes = QLabel("\n".join(artifact.notes))
        notes.setObjectName("InlineVisualizationInspector")
        notes.setWordWrap(True)
        notes.setVisible(bool(artifact.notes))

        layout.addLayout(header)
        layout.addLayout(controls)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(details)
        layout.addWidget(self.inspector)
        layout.addWidget(notes)

    def _reset(self):
        self.canvas.reset_view()
        self.inspector.setText("View reset. Hover an atom for validated coordinates.")

    def _open_large(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.artifact.title)
        dialog.setWindowIcon(QIcon(_icon_path()))
        dialog.resize(1100, 760)
        layout = QVBoxLayout(dialog)
        canvas = MoleculeCanvas()
        canvas.set_artifact(self.artifact)
        canvas.set_view_mode(str(self.dimension_select.currentData()))
        layout.addWidget(canvas)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.show()
        dialog.raise_()

    def _export(self, export_format: str):
        selected_filter, extension = {
            "png": ("PNG image (*.png)", ".png"),
            "svg": ("SVG vector image (*.svg)", ".svg"),
            "pdf": ("PDF document (*.pdf)", ".pdf"),
        }[export_format]
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {self.artifact.title}",
            "",
            selected_filter,
        )
        if not path:
            return
        if not path.lower().endswith(extension):
            path += extension
        succeeded = {
            "png": self.canvas.export_png,
            "svg": self.canvas.export_svg,
            "pdf": self.canvas.export_pdf,
        }[export_format](path)
        self.inspector.setText(f"Exported to {path}" if succeeded else f"Could not export {path}")


class InlineDiagramWorkspace(QFrame):
    def __init__(self, artifact: DiagramArtifact, parent=None):
        super().__init__(parent)
        self.artifact = artifact
        self.setObjectName("InlineVisualization")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel(artifact.title)
        title.setObjectName("InlineVisualizationTitle")
        kind = QLabel("Validated structured diagram")
        kind.setObjectName("InlineVisualizationKind")
        header.addWidget(title, stretch=1)
        header.addWidget(kind)

        controls = QHBoxLayout()
        reset_button = QPushButton("Reset view")
        reset_button.setObjectName("InlineVisualizationControl")
        reset_button.clicked.connect(self._reset)
        large_button = QPushButton("Open large")
        large_button.setObjectName("InlineVisualizationControl")
        large_button.clicked.connect(self._open_large)
        controls.addWidget(reset_button)
        controls.addWidget(large_button)
        controls.addStretch(1)
        for label, export_format in (("PNG", "png"), ("SVG", "svg"), ("PDF", "pdf")):
            button = QPushButton(label)
            button.setObjectName("InlineVisualizationControl")
            button.clicked.connect(
                lambda _checked=False, selected=export_format: self._export(selected)
            )
            controls.addWidget(button)

        self.canvas = DiagramCanvas()
        self.canvas.set_artifact(artifact)
        self.inspector = QLabel(
            "Hover a node for validated connection counts. Use the wheel to zoom and drag to pan."
        )
        self.inspector.setObjectName("InlineVisualizationInspector")
        self.inspector.setWordWrap(True)
        self.canvas.inspected.connect(self.inspector.setText)

        layout.addLayout(header)
        layout.addLayout(controls)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self.inspector)

    def _reset(self):
        self.canvas.reset_view()
        self.inspector.setText("View reset. Hover a node for connection counts.")

    def _open_large(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.artifact.title)
        dialog.setWindowIcon(QIcon(_icon_path()))
        dialog.resize(1100, 760)
        layout = QVBoxLayout(dialog)
        canvas = DiagramCanvas()
        canvas.set_artifact(self.artifact)
        layout.addWidget(canvas)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.show()
        dialog.raise_()

    def _export(self, export_format: str):
        selected_filter, extension = {
            "png": ("PNG image (*.png)", ".png"),
            "svg": ("SVG vector image (*.svg)", ".svg"),
            "pdf": ("PDF document (*.pdf)", ".pdf"),
        }[export_format]
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {self.artifact.title}",
            "",
            selected_filter,
        )
        if not path:
            return
        if not path.lower().endswith(extension):
            path += extension
        succeeded = {
            "png": self.canvas.export_png,
            "svg": self.canvas.export_svg,
            "pdf": self.canvas.export_pdf,
        }[export_format](path)
        self.inspector.setText(f"Exported to {path}" if succeeded else f"Could not export {path}")


class InlineChartWorkspace(QFrame):
    def __init__(self, artifact: ChartArtifact, parent=None):
        super().__init__(parent)
        self.artifact = artifact
        self.setObjectName("InlineVisualization")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel(artifact.title)
        title.setObjectName("InlineVisualizationTitle")
        kind = QLabel("Validated numeric chart")
        kind.setObjectName("InlineVisualizationKind")
        header.addWidget(title, stretch=1)
        header.addWidget(kind)

        controls = QHBoxLayout()
        reset = QPushButton("Reset view")
        reset.setObjectName("InlineVisualizationControl")
        large = QPushButton("Open large")
        large.setObjectName("InlineVisualizationControl")
        reset.clicked.connect(self._reset)
        large.clicked.connect(self._open_large)
        controls.addWidget(reset)
        controls.addWidget(large)
        controls.addStretch(1)
        for label, export_format in (("PNG", "png"), ("SVG", "svg"), ("PDF", "pdf")):
            button = QPushButton(label)
            button.setObjectName("InlineVisualizationControl")
            button.clicked.connect(
                lambda _checked=False, selected=export_format: self._export(selected)
            )
            controls.addWidget(button)

        self.canvas = ChartCanvas()
        self.canvas.set_artifact(artifact)
        self.inspector = QLabel("Hover a mark for the exact value.")
        self.inspector.setObjectName("InlineVisualizationInspector")
        self.inspector.setWordWrap(True)
        self.canvas.inspected.connect(self.inspector.setText)
        details = QLabel(" | ".join(artifact.notes))
        details.setObjectName("InlineVisualizationEquation")
        details.setWordWrap(True)

        layout.addLayout(header)
        layout.addLayout(controls)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(details)
        layout.addWidget(self.inspector)

    def _reset(self):
        self.canvas.reset_view()
        self.inspector.setText("View reset. Hover a mark for the exact value.")

    def _open_large(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.artifact.title)
        dialog.setWindowIcon(QIcon(_icon_path()))
        dialog.resize(1120, 760)
        layout = QVBoxLayout(dialog)
        canvas = ChartCanvas()
        canvas.set_artifact(self.artifact)
        layout.addWidget(canvas)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.show()
        dialog.raise_()

    def _export(self, export_format: str):
        selected_filter, extension = {
            "png": ("PNG image (*.png)", ".png"),
            "svg": ("SVG vector image (*.svg)", ".svg"),
            "pdf": ("PDF document (*.pdf)", ".pdf"),
        }[export_format]
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {self.artifact.title}", "", selected_filter
        )
        if not path:
            return
        if not path.lower().endswith(extension):
            path += extension
        succeeded = {
            "png": self.canvas.export_png,
            "svg": self.canvas.export_svg,
            "pdf": self.canvas.export_pdf,
        }[export_format](path)
        self.inspector.setText(f"Exported to {path}" if succeeded else f"Could not export {path}")


class InlineSceneWorkspace(QFrame):
    def __init__(self, artifact: SceneArtifact, parent=None):
        super().__init__(parent)
        self.artifact = artifact
        self.setObjectName("InlineVisualization")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel(artifact.title)
        title.setObjectName("InlineVisualizationTitle")
        kind = QLabel("Validated component schematic")
        kind.setObjectName("InlineVisualizationKind")
        header.addWidget(title, stretch=1)
        header.addWidget(kind)

        controls = QHBoxLayout()
        self.dimension_select = QComboBox()
        self.dimension_select.setObjectName("InlineVisualizationSelect")
        self.dimension_select.addItem("2D", "2d")
        self.dimension_select.addItem("3D", "3d")
        self.dimension_select.setCurrentText("3D")
        pause = QPushButton("Pause")
        resume = QPushButton("Resume")
        reset = QPushButton("Reset view")
        large = QPushButton("Open large")
        export = QPushButton("PNG")
        for button in (pause, resume, reset, large, export):
            button.setObjectName("InlineVisualizationControl")
        controls.addWidget(QLabel("View"))
        controls.addWidget(self.dimension_select)
        controls.addWidget(pause)
        controls.addWidget(resume)
        controls.addWidget(reset)
        controls.addWidget(large)
        controls.addStretch(1)
        controls.addWidget(export)

        self.canvas = SceneCanvas()
        self.canvas.set_artifact(artifact)
        self.canvas.set_view_mode("3d")
        self.inspector = QLabel("Hover a component to inspect it. Drag to rotate the 3D schematic.")
        self.inspector.setObjectName("InlineVisualizationInspector")
        self.inspector.setWordWrap(True)
        self.canvas.inspected.connect(self.inspector.setText)
        details = QLabel(" | ".join(artifact.notes))
        details.setObjectName("InlineVisualizationEquation")
        details.setWordWrap(True)

        self.dimension_select.currentIndexChanged.connect(
            lambda index: self.canvas.set_view_mode(str(self.dimension_select.itemData(index)))
        )
        pause.clicked.connect(lambda: self.canvas.set_running(False))
        resume.clicked.connect(lambda: self.canvas.set_running(True))
        reset.clicked.connect(self.canvas.reset_view)
        large.clicked.connect(self._open_large)
        export.clicked.connect(self._export_png)

        layout.addLayout(header)
        layout.addLayout(controls)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(details)
        layout.addWidget(self.inspector)

    def _open_large(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.artifact.title)
        dialog.setWindowIcon(QIcon(_icon_path()))
        dialog.resize(1120, 780)
        layout = QVBoxLayout(dialog)
        canvas = SceneCanvas()
        canvas.set_artifact(self.artifact)
        canvas.set_view_mode(self.dimension_select.currentData())
        layout.addWidget(canvas)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.show()
        dialog.raise_()

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {self.artifact.title}", "", "PNG image (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        succeeded = self.canvas.export_png(path)
        self.inspector.setText(f"Exported to {path}" if succeeded else f"Could not export {path}")


class InlineDocumentWorkspace(QFrame):
    def __init__(self, artifact: DocumentArtifact, parent=None):
        super().__init__(parent)
        self.artifact = artifact
        self.setObjectName("InlineVisualization")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel(artifact.title)
        title.setObjectName("InlineVisualizationTitle")
        kind = QLabel(f"Validated local {artifact.extension.lstrip('.').upper()} preview")
        kind.setObjectName("InlineVisualizationKind")
        header.addWidget(title, stretch=1)
        header.addWidget(kind)

        self.preview = FilePreview()
        loaded, message = self.preview.show_file(artifact.path)
        self.status = QLabel(message)
        self.status.setObjectName("InlineVisualizationInspector")
        self.status.setWordWrap(True)
        if not loaded:
            self.status.setText(f"Preview failed after validation: {message}")

        layout.addLayout(header)
        layout.addWidget(self.preview, stretch=1)
        layout.addWidget(self.status)


class InlineBiologyWorkspace(QFrame):
    def __init__(self, artifact: BiologyArtifact, parent=None):
        super().__init__(parent)
        self.artifact = artifact
        self.setObjectName("InlineVisualization")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(550)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel(artifact.title)
        title.setObjectName("InlineVisualizationTitle")
        kind = QLabel("Validated biology model")
        kind.setObjectName("InlineVisualizationKind")
        header.addWidget(title, stretch=1)
        header.addWidget(kind)

        controls = QHBoxLayout()
        self.dimension_select = QComboBox()
        self.dimension_select.setObjectName("InlineVisualizationSelect")
        self.dimension_select.addItem("2D", "2d")
        self.dimension_select.addItem("3D", "3d")
        self.dimension_select.setCurrentText("3D")
        pause = QPushButton("Pause")
        pause.setObjectName("InlineVisualizationControl")
        resume = QPushButton("Resume")
        resume.setObjectName("InlineVisualizationControl")
        reset = QPushButton("Reset view")
        reset.setObjectName("InlineVisualizationControl")
        export = QPushButton("PNG")
        export.setObjectName("InlineVisualizationControl")
        controls.addWidget(QLabel("View"))
        controls.addWidget(self.dimension_select)
        controls.addWidget(pause)
        controls.addWidget(resume)
        controls.addWidget(reset)
        controls.addStretch(1)
        controls.addWidget(export)

        self.canvas = BiologyCanvas()
        self.canvas.set_artifact(artifact)
        self.canvas.set_view_mode("3d")
        self.inspector = QLabel("Hover the model to inspect validated components.")
        self.inspector.setObjectName("InlineVisualizationInspector")
        self.inspector.setWordWrap(True)
        self.canvas.inspected.connect(self.inspector.setText)
        details = QLabel(" | ".join(artifact.notes))
        details.setObjectName("InlineVisualizationEquation")
        details.setWordWrap(True)
        details.setVisible(bool(artifact.notes))

        self.dimension_select.currentIndexChanged.connect(
            lambda index: self.canvas.set_view_mode(str(self.dimension_select.itemData(index)))
        )
        pause.clicked.connect(lambda: self.canvas.set_running(False))
        resume.clicked.connect(lambda: self.canvas.set_running(True))
        reset.clicked.connect(self.canvas.reset_view)
        export.clicked.connect(self._export_png)

        layout.addLayout(header)
        layout.addLayout(controls)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(details)
        layout.addWidget(self.inspector)

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {self.artifact.title}", "", "PNG image (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        succeeded = self.canvas.export_png(path)
        self.inspector.setText(f"Exported to {path}" if succeeded else f"Could not export {path}")


class InlineDataStructureWorkspace(QFrame):
    COMPLEXITY = {
        "Binary Search Tree": {
            "insert": "average O(log n), worst O(n)",
            "delete": "average O(log n), worst O(n)",
            "search": "average O(log n), worst O(n)",
        },
        "AVL Tree": {"insert": "O(log n)", "delete": "O(log n)", "search": "O(log n)"},
        "Graph": {"insert": "O(1)", "delete": "O(V + E)", "search": "O(V + E)"},
        "Linked List": {"insert": "O(1)", "delete": "O(n)", "search": "O(n)"},
        "Queue": {"insert": "O(1)", "delete": "O(1)", "search": "O(n)"},
        "Stack": {"insert": "O(1)", "delete": "O(1)", "search": "O(n)"},
        "Hash Table": {
            "insert": "average O(1), worst O(n)",
            "delete": "average O(1), worst O(n)",
            "search": "average O(1), worst O(n)",
        },
    }

    def __init__(self, artifact: DataStructureArtifact, parent=None):
        super().__init__(parent)
        self.artifact = artifact
        self.values_by_structure = {
            structure: list(artifact.initial_values) for structure in artifact.structures
        }
        self.setObjectName("InlineVisualization")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(590)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel(artifact.title)
        title.setObjectName("InlineVisualizationTitle")
        kind = QLabel("Interactive algorithm lab")
        kind.setObjectName("InlineVisualizationKind")
        header.addWidget(title, stretch=1)
        header.addWidget(kind)

        controls = QHBoxLayout()
        self.structure_select = QComboBox()
        self.structure_select.setObjectName("InlineVisualizationSelect")
        self.structure_select.addItems(artifact.structures)
        self.value_input = QLineEdit("25")
        self.value_input.setObjectName("InlineVisualizationInput")
        self.value_input.setPlaceholderText("Integer value")
        self.value_input.setMaximumWidth(130)
        controls.addWidget(self.structure_select)
        controls.addWidget(self.value_input)
        for operation in ("Insert", "Delete", "Search"):
            button = QPushButton(operation)
            button.setObjectName("InlineVisualizationControl")
            button.clicked.connect(
                lambda _checked=False, selected=operation.lower(): self._operate(selected)
            )
            controls.addWidget(button)
        reset = QPushButton("Reset")
        reset.setObjectName("InlineVisualizationControl")
        reset.clicked.connect(self._reset)
        controls.addWidget(reset)
        controls.addStretch(1)

        self.canvas = DataStructureCanvas()
        self.complexity = QLabel()
        self.complexity.setObjectName("InlineVisualizationInspector")
        self.complexity.setWordWrap(True)
        self.structure_select.currentTextChanged.connect(self._structure_changed)

        layout.addLayout(header)
        layout.addLayout(controls)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self.complexity)
        self._structure_changed(self.structure_select.currentText())

    def _current_values(self) -> list[int]:
        return self.values_by_structure.setdefault(
            self.structure_select.currentText(), list(self.artifact.initial_values)
        )

    def _structure_changed(self, structure: str):
        values = self.values_by_structure.setdefault(structure, list(self.artifact.initial_values))
        self.canvas.set_state(structure, values, status="Ready for insert, delete, or search.")
        complexity = self.COMPLEXITY.get(structure, {})
        self.complexity.setText(
            "Complexity: "
            + " | ".join(f"{operation.title()} {value}" for operation, value in complexity.items())
        )

    def _operate(self, operation: str):
        try:
            value = int(self.value_input.text().strip())
        except ValueError:
            self.complexity.setText("Enter a valid integer before running an operation.")
            return
        structure = self.structure_select.currentText()
        values = self._current_values()
        highlighted: set[int] = set()
        if operation == "insert":
            if value not in values:
                values.append(value)
                status = f"Inserted {value}."
            else:
                status = f"{value} already exists; duplicate insertion was skipped."
            highlighted.add(value)
        elif operation == "delete":
            if structure == "Queue" and values:
                removed = values.pop(0)
                status = f"Dequeued {removed} from the front."
            elif structure == "Stack" and values:
                removed = values.pop()
                status = f"Popped {removed} from the top."
            elif value in values:
                values.remove(value)
                status = f"Deleted {value}."
            else:
                status = f"{value} was not found; nothing was deleted."
        else:
            if structure in {"Binary Search Tree", "AVL Tree"}:
                tree = (
                    DataStructureCanvas._balanced_tree(values)
                    if structure == "AVL Tree"
                    else DataStructureCanvas._bst(values)
                )
                node = tree
                while node:
                    highlighted.add(node[0])
                    if value == node[0]:
                        break
                    node = node[1] if value < node[0] else node[2]
            elif value in values:
                highlighted.add(value)
            status = f"Found {value}." if value in values else f"{value} was not found."
        complexity = self.COMPLEXITY[structure][operation]
        self.canvas.set_state(
            structure,
            values,
            highlighted,
            f"{status} {operation.title()} complexity: {complexity}.",
        )
        self.complexity.setText(
            f"{operation.title()} result: {status} Complexity: {complexity}. "
            "Highlighted nodes show the visited or changed state."
        )

    def _reset(self):
        structure = self.structure_select.currentText()
        self.values_by_structure[structure] = list(self.artifact.initial_values)
        self._structure_changed(structure)


class TitleBar(QFrame):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._parent = parent
        self._drag_active = False
        self._drag_pos = QPoint()

        self.setObjectName("TitleBar")
        layout = QHBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.mode_btn = RgbMenuButton()
        self.mode_btn.clicked.connect(self._parent.toggle_mode_panel)

        self.sidebar_btn = QPushButton("Panel")
        self.sidebar_btn.setObjectName("SidebarButton")
        self.sidebar_btn.clicked.connect(self._parent.toggle_sidebar)

        self.workspace_btn = QPushButton("Lab")
        self.workspace_btn.setObjectName("SidebarButton")
        self.workspace_btn.clicked.connect(self._parent.toggle_workspace_panel)

        self.hub_btn = QPushButton("Tools")
        self.hub_btn.setObjectName("SidebarButton")
        self.hub_btn.setToolTip("Open workspace tools")
        self.hub_btn.clicked.connect(self._parent.toggle_assistant_hub)

        self.command_btn = QPushButton()
        self.command_btn.setObjectName("TitleButton")
        self.command_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_FileDialogContentsView)
        )
        self.command_btn.setToolTip("Command palette (Ctrl+K)")
        self.command_btn.setFixedWidth(34)
        self.command_btn.clicked.connect(self._parent.open_command_palette)

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
        layout.addWidget(self.workspace_btn)
        layout.addWidget(self.hub_btn)
        layout.addWidget(logo)
        layout.addWidget(title)
        self.workspace_status = QLabel("Chat")
        self.workspace_status.setObjectName("TopStatus")
        self.workspace_status.setToolTip("Active workspace")
        self.workspace_status.setAccessibleName("Active workspace")
        self.model_status = QLabel("Local model")
        self.model_status.setObjectName("TopStatus")
        self.model_status.setToolTip("Active AI model")
        self.model_status.setAccessibleName("Active AI model")
        self.hardware_status = QLabel("GPU -- | RAM -- | VRAM --")
        self.hardware_status.setObjectName("TopStatus")
        self.hardware_status.setToolTip("Live hardware usage")
        self.hardware_status.setAccessibleName("Live GPU RAM and VRAM usage")
        self.task_status = QLabel("Idle")
        self.task_status.setObjectName("TopStatus")
        self.task_status.setToolTip("Background task status")
        self.task_status.setAccessibleName("Background task status")
        self._status_labels = (
            self.workspace_status,
            self.model_status,
            self.hardware_status,
            self.task_status,
        )
        for status in self._status_labels:
            layout.addWidget(status)
        layout.addStretch(1)
        self._plugin_buttons: list[QPushButton] = []

        self.settings_btn = QPushButton()
        self.settings_btn.setObjectName("TitleButton")
        self.settings_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_FileDialogDetailedView)
        )
        self.settings_btn.setToolTip("Quick settings")
        self.settings_btn.setAccessibleName("Open settings")
        self.settings_btn.setFixedWidth(34)
        self.settings_btn.clicked.connect(self._parent.open_premium_settings)
        layout.addWidget(self.settings_btn)

        self.command_btn.setAccessibleName("Open command palette")
        layout.addWidget(self.command_btn)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("TitleButton")
        self.theme_btn.setFixedWidth(34)
        self.theme_btn.clicked.connect(self._parent.toggle_theme)
        self.set_theme_icon(getattr(self._parent, "current_theme", "dark"))
        layout.addWidget(self.theme_btn)

        self.min_btn = QPushButton()
        self.min_btn.setToolTip("Minimize")
        self.min_btn.setObjectName("TitleButton")
        self.min_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_TitleBarMinButton)
        )
        self.min_btn.setAccessibleName("Minimize")
        self.min_btn.setFixedWidth(34)
        self.min_btn.clicked.connect(self._parent.animate_minimize)

        self.max_btn = QPushButton()
        self.max_btn.setToolTip("Maximize")
        self.max_btn.setObjectName("TitleButton")
        self.max_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_TitleBarMaxButton)
        )
        self.max_btn.setAccessibleName("Maximize")
        self.max_btn.setFixedWidth(34)
        self.max_btn.clicked.connect(self._toggle_maximize)

        self.close_btn = QPushButton()
        self.close_btn.setToolTip("Close")
        self.close_btn.setObjectName("TitleClose")
        self.close_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_TitleBarCloseButton)
        )
        self.close_btn.setAccessibleName("Close")
        self.close_btn.setFixedWidth(34)
        self.close_btn.clicked.connect(self._parent.close)

        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def set_plugin_buttons(self, contributions: list[dict], callback):
        for button in self._plugin_buttons:
            self._layout.removeWidget(button)
            button.deleteLater()
        self._plugin_buttons.clear()
        insert_at = self._layout.indexOf(self.settings_btn)
        for contribution in contributions[:8]:
            button = QPushButton(str(contribution.get("title", "Plugin"))[:18])
            button.setObjectName("SidebarButton")
            button.setToolTip(
                f"Plugin: {contribution.get('pluginId', '')}"
            )
            button.clicked.connect(
                lambda _checked=False, item=dict(contribution): callback(item)
            )
            self._layout.insertWidget(insert_at, button)
            insert_at += 1
            self._plugin_buttons.append(button)

    def set_theme_icon(self, theme: str):
        normalized = normalize_theme(theme)
        self.theme_btn.setIcon(_theme_outline_icon(normalized))
        self.theme_btn.setIconSize(QSize(22, 22))
        self.theme_btn.setAccessibleName(
            "Light theme active" if normalized == "light" else "Dark theme active"
        )
        self.theme_btn.setToolTip(
            "Switch to dark theme" if normalized == "light" else "Switch to light theme"
        )

    def set_runtime_status(
        self,
        *,
        workspace: str,
        model: str,
        gpu: str,
        ram: str,
        vram: str,
        tasks: int,
    ) -> None:
        self.workspace_status.setText(workspace or "Chat")
        self.model_status.setText(model or "Local model")
        self.hardware_status.setText(
            f"GPU {gpu or '--'} | RAM {ram or '--'} | VRAM {vram or '--'}"
        )
        self.task_status.setText(f"{tasks} task{'s' if tasks != 1 else ''}" if tasks else "Idle")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.width()
        self.hardware_status.setVisible(width >= 1080)
        self.model_status.setVisible(width >= 820)
        self.workspace_status.setVisible(width >= 680)
        self.task_status.setVisible(width >= 920)

    def _toggle_maximize(self):
        if self._parent.isMaximized() or getattr(self._parent, "_custom_maximized", False):
            self._parent.showNormal()
            normal_geometry = getattr(self._parent, "_normal_geometry", None)
            if normal_geometry is not None:
                self._parent.animation_engine.geometry(
                    self._parent, normal_geometry, duration=220
                )
            self._parent._custom_maximized = False
            self.max_btn.setIcon(
                QApplication.style().standardIcon(QStyle.SP_TitleBarMaxButton)
            )
            self.max_btn.setToolTip("Maximize")
        else:
            self._parent._normal_geometry = self._parent.geometry()
            screen = self._parent.screen()
            if screen is None:
                screen = QApplication.primaryScreen()
            self._parent.showNormal()
            if screen is not None:
                # Frameless translucent windows can extend below the taskbar
                # when native maximize margins are guessed by Windows. Using
                # the available geometry keeps every bottom control visible.
                self._parent.animation_engine.geometry(
                    self._parent, screen.availableGeometry(), duration=220
                )
            else:
                self._parent.showMaximized()
            self._parent._custom_maximized = True
            self.max_btn.setIcon(
                QApplication.style().standardIcon(QStyle.SP_TitleBarNormalButton)
            )
            self.max_btn.setToolTip("Restore")

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
        was_dragging = self._drag_active
        self._drag_active = False
        if was_dragging and event.button() == Qt.LeftButton:
            self._snap_to_edge(event.globalPosition().toPoint())
        event.accept()

    def _snap_to_edge(self, position: QPoint):
        screen = QApplication.screenAt(position) or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        threshold = 18
        if abs(position.y() - available.top()) <= threshold:
            if not getattr(self._parent, "_custom_maximized", False):
                self._toggle_maximize()
            return
        left_edge = abs(position.x() - available.left()) <= threshold
        right_edge = abs(position.x() - available.right()) <= threshold
        if not left_edge and not right_edge:
            return
        if available.width() // 2 < self._parent.minimumWidth():
            if not getattr(self._parent, "_custom_maximized", False):
                self._toggle_maximize()
            return
        self._parent.showNormal()
        self._parent._custom_maximized = False
        self._parent._normal_geometry = self._parent.geometry()
        half = QRect(
            available.left()
            if left_edge
            else available.left() + available.width() // 2,
            available.top(),
            available.width() // 2,
            available.height(),
        )
        self._parent.animation_engine.geometry(self._parent, half, duration=220)
        self.max_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_TitleBarMaxButton)
        )
        self.max_btn.setToolTip("Maximize")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()
            event.accept()


class MoriceWindow(QWidget):
    message_ready = Signal(str, str, bool)
    assistant_stream_delta = Signal(str, str)
    assistant_stream_finished = Signal(str, str)
    response_cancelled = Signal(str)
    thinking_update = Signal(str)
    project_changes_ready = Signal(str, str)
    project_output_ready = Signal(str)
    project_patch_result = Signal(object)
    project_command_state = Signal(bool)
    gpu_detected = Signal(object)
    visualization_progress = Signal(str, str, str, int)
    visualization_finished = Signal(object)
    system_snapshot_ready = Signal(object)
    file_search_ready = Signal(object)
    desktop_action_ready = Signal(str, bool)
    premium_metrics_ready = Signal(object)
    plugin_catalog_changed = Signal()
    plugin_notification_received = Signal(str, str)
    speech_partial_ready = Signal(str)
    speech_transcript_ready = Signal(object)
    speech_playback_finished = Signal(object)
    pc_control_ready = Signal(str, object)
    live_vision_ready = Signal(str, object)

    def _emit_background(self, signal_name: str, *arguments) -> bool:
        if getattr(self, "_is_closing", False):
            return False
        try:
            getattr(self, signal_name).emit(*arguments)
        except RuntimeError:
            return False
        return True

    def __init__(
        self,
        runtime_services: RuntimeServices | None = None,
        recovery_info: RecoveryInfo | None = None,
    ):
        super().__init__()
        self._is_closing = False
        self.runtime = runtime_services or get_runtime_services()
        self.recovery_info = recovery_info or RecoveryInfo(False)
        self._owns_runtime_lifecycle = recovery_info is not None
        _load_ui_fonts()
        application = QApplication.instance()
        if application is not None:
            application.setApplicationName("MORICE")
            application.setApplicationDisplayName("MORICE")
            application.setOrganizationName("EONASH2722")
        stored_base_size = (
            application.property("moriceBaseFontPointSize")
            if application is not None
            else None
        )
        if stored_base_size is None:
            stored_base_size = (
                application.font().pointSize()
                if application is not None and application.font().pointSize() > 0
                else 10
            )
            if application is not None:
                application.setProperty("moriceBaseFontPointSize", stored_base_size)
        self._base_font_point_size = max(8, int(stored_base_size))
        self.setWindowTitle(MORICE_NAME)
        self.setMinimumSize(860, 580)
        self.resize(1240, 760)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        icon_path = _icon_path()
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self._normal_geometry = None
        self._custom_maximized = False

        self._session_enabled = (
            os.getenv("MORICE_DISABLE_SESSION", "").strip().lower()
            not in {"1", "true", "yes"}
        )
        self.workspace_state = (
            load_workspace_state() if self._session_enabled else WorkspaceState()
        )
        self.current_theme = normalize_theme(self.workspace_state.theme)
        self.accent_color = normalize_accent(self.workspace_state.accent)
        # Every process launch starts a new conversation. Appearance, notes,
        # geometry, and workspace preferences remain persistent.
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
        self._user_scroll_guard_until = 0.0
        self.user_messages: list[str] = []
        self.first_user_message = ""
        self.is_busy = False
        self.thinking_bubble: ThinkingBubble | None = None
        self._thinking_token = 0
        self.composer_centered = True
        self._input_hovered = False
        self.input_glow: QGraphicsDropShadowEffect | None = None
        self._input_glow_animation: QParallelAnimationGroup | None = None
        self._input_glow_target: tuple[int, int] | None = None
        self._composer_anim: QPropertyAnimation | None = None
        self._dock_placeholder: QWidget | None = None
        self._panel_anims: dict[QWidget, QPropertyAnimation] = {}
        self._panel_target_visibility: dict[QWidget, bool] = {}
        self._motion_enabled = os.getenv("MORICE_REDUCE_MOTION", "").strip().lower() not in {"1", "true", "yes"}
        self.animation_engine = AnimationEngine(self, enabled=self._motion_enabled)
        self._child_windows: list[MoriceWindow] = []
        self._closing_after_animation = False
        self._open_animation_played = False
        self.message_queue: list[str] = []
        self.clipboard_history: list[str] = []
        self.settings = load_settings()
        self.animation_speed = normalize_animation_speed(
            self.settings.get("animation_speed", "")
        )
        self.reduced_motion = normalize_boolean_setting(
            self.settings.get("reduced_motion", "")
        ) or not self._motion_enabled
        self.high_contrast = normalize_boolean_setting(
            self.settings.get("high_contrast", "")
        )
        self.large_text = normalize_boolean_setting(
            self.settings.get("large_text", "")
        )
        self.ui_scale = normalize_ui_scale(self.settings.get("ui_scale", ""))
        self.transparency = normalize_transparency(
            self.settings.get("transparency", "")
        )
        self.workspace_preset = normalize_workspace_preset(
            (
                self.workspace_state.workspace_preset
                if self.workspace_state.splitter_sizes
                else self.settings.get("workspace_preset", "")
            )
        )
        self.settings_profile = normalize_settings_profile(
            self.settings.get("settings_profile", "")
        )
        self.default_music_provider = normalize_music_provider(
            self.settings.get("default_music_provider", "")
        )
        self._motion_enabled = not self.reduced_motion
        self.animation_engine.configure(
            enabled=self._motion_enabled,
            speed=self.animation_speed,
        )
        self.experience_profiles = ExperienceProfileStore(
            self.runtime.directory / "experience"
        )
        self.response_style = self.settings.get("response_style", "").strip()
        self.wake_phrase = normalize_wake_phrase(self.settings.get("wake_phrase", ""))
        self.user_title = normalize_user_title(self.settings.get("user_title", ""))
        self.emoji_level = normalize_emoji_level(
            self.settings.get("emoji_level", "")
        )
        self.maturity_level = normalize_maturity_level(
            self.settings.get("maturity_level", "")
        )
        self.font_family = normalize_font_family(
            self.settings.get("font_family", "")
        )
        self.custom_font_path = normalize_custom_font_path(
            self.settings.get("custom_font_path", "")
        )
        registered_custom_family = register_ui_font_file(self.custom_font_path)
        installed_fonts = {
            family.casefold(): family for family in QFontDatabase.families()
        }
        if self.font_family.casefold() not in installed_fonts:
            self.font_family = (
                registered_custom_family
                or installed_fonts.get("segoe ui")
                or QApplication.font().family()
                or DEFAULT_SETTINGS["font_family"]
            )
        application = QApplication.instance()
        if application is not None:
            scale = self.ui_scale * (1.12 if self.large_text else 1.0)
            application.setFont(
                QFont(
                    self.font_family,
                    max(8, round(self._base_font_point_size * scale)),
                )
            )
        loaded_chat_mode = normalize_chat_mode(self.settings.get("chat_mode", ""))
        # Voice is an explicit, session-only mode. Never reopen a microphone
        # merely because the previous process closed while Voice mode was active.
        self.chat_mode = "normal" if loaded_chat_mode == "voice" else loaded_chat_mode
        self._voice_return_mode = self.chat_mode
        self.project_folder = normalize_project_folder(self.settings.get("project_folder", ""))
        self.project_access = normalize_project_access(self.settings.get("project_access", ""))
        self.project_lookup_mode = normalize_project_lookup_mode(self.settings.get("project_lookup_mode", ""))
        self.model_path = normalize_model_path(self.settings.get("model_path", ""))
        self.model_name = normalize_model_name(self.settings.get("model_name", ""))
        # Hermes was the old bundled default. It remains selectable for tests, but
        # saved default selections now migrate to Qwen automatically.
        legacy_model_path = os.path.basename(self.model_path).lower()
        legacy_model_name = self.model_name.lower()
        migrated_legacy_model = False
        if self.model_path and not os.path.isfile(self.model_path):
            relocated_candidates = (
                os.path.join(
                    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
                    os.path.basename(self.model_path),
                ),
                os.path.join(
                    os.path.dirname(sys.executable),
                    os.path.basename(self.model_path),
                ),
            )
            relocated = next(
                (
                    normalize_model_path(path)
                    for path in relocated_candidates
                    if os.path.isfile(path)
                ),
                "",
            )
            if relocated:
                self.model_path = relocated
                migrated_legacy_model = True
        if "hermes-3-llama" in legacy_model_path:
            self.model_path = ""
            migrated_legacy_model = True
        if legacy_model_name in {"morice", "hermes", "hermes-3"} or "hermes-3-llama" in legacy_model_name:
            self.model_name = ""
            migrated_legacy_model = True
        self.gpu_name = normalize_gpu_name(self.settings.get("gpu_name", ""))
        self.gpu_vram_mb = normalize_gpu_vram_mb(self.settings.get("gpu_vram_mb", ""))
        self.gpu_profile = gpu_profile_from_values(self.gpu_name, self.gpu_vram_mb, "settings")
        if migrated_legacy_model:
            self._save_project_settings()
        self.science_artifacts: list[ScienceArtifact] = []
        self.visualization_manager = VisualizationManager()
        self.runtime.plugins.bind(
            tool_registry=self.runtime.agent.tools.registry,
            renderer_registry=self.visualization_manager.registry,
        )
        self.visualization_cards: dict[str, VisualizationGenerationCard] = {}
        self.visualization_futures: dict[str, object] = {}
        self.active_workspace_kind = "graph"
        self.last_project_request = ""
        self._active_agent_request_id = ""
        self._active_platform_run_id = ""
        self.pending_project_patch: dict | None = None
        self.last_project_undo_id = ""
        self._active_project_command_id = ""
        self._last_external_wake_notice = 0.0
        self._speech_base_text = ""
        self._streamed_voice_reply_pending = False
        self._stream_request_id = ""
        self._stream_text = ""
        self._stream_bubble: ChatBubble | None = None
        self._pending_transcript: TranscriptResult | None = None
        self._voice_conversation_active = False
        self._live_microphone_paused = False
        self._barge_in_monitoring = False
        self._barge_in_interrupted = False
        self._last_spoken_text = ""
        self._pending_live_vision_result: tuple[
            str, VisionResult, int, int
        ] | None = None
        self._live_vision_started_ns: int | None = None
        self._last_awareness_publish = 0.0

        self.wake_signal_path = wake_signal_path()
        self.message_ready.connect(self._on_message_ready)
        self.assistant_stream_delta.connect(self._on_assistant_stream_delta)
        self.assistant_stream_finished.connect(self._on_assistant_stream_finished)
        self.response_cancelled.connect(self._on_response_cancelled)
        self.thinking_update.connect(self._on_thinking_update)
        self.project_changes_ready.connect(self._on_project_changes_ready)
        self.project_output_ready.connect(self._append_project_output)
        self.project_patch_result.connect(self._on_project_patch_result)
        self.project_command_state.connect(
            lambda running: self.project_command_stop_btn.setEnabled(running)
        )
        self.gpu_detected.connect(self._on_gpu_detected)
        self.visualization_progress.connect(self._on_visualization_progress)
        self.visualization_finished.connect(self._on_visualization_finished)
        self.system_snapshot_ready.connect(self._on_system_snapshot_ready)
        self.file_search_ready.connect(self._on_file_search_ready)
        self.desktop_action_ready.connect(self._on_desktop_action_ready)
        self.premium_metrics_ready.connect(self._on_premium_metrics)
        self.speech_partial_ready.connect(self._on_speech_partial)
        self.speech_transcript_ready.connect(self._on_speech_transcript)
        self.speech_playback_finished.connect(
            self._on_speech_playback_finished
        )
        self.pc_control_ready.connect(self._on_pc_control_ready)
        self.live_vision_ready.connect(self._on_live_vision_ready)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, stretch=1)
        self.workspace_splitter = QSplitter(Qt.Horizontal)
        self.workspace_splitter.setObjectName("WorkspaceSplitter")
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(6)
        body.addWidget(self.workspace_splitter)
        self.window_resize_grip = QSizeGrip(self)
        self.window_resize_grip.setObjectName("WindowResizeGrip")
        self.window_resize_grip.setToolTip("Resize MORICE window")

        self.mode_panel = QFrame()
        self.mode_panel.setObjectName("ModePanel")
        self.mode_panel.setMinimumWidth(250)
        self.mode_panel.setMaximumWidth(420)
        self.mode_panel.resize(292, 620)
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

        self.voice_mode_btn = QPushButton("Live Action")
        self.voice_mode_btn.setObjectName("ModeOption")
        self.voice_mode_btn.setToolTip(
            "Camera-centered voice conversation with all Chat, Lab, Tools, and Project features"
        )
        self.voice_mode_btn.clicked.connect(lambda: self._set_chat_mode("voice"))

        model_label = QLabel("AI model")
        model_label.setObjectName("ModeSectionLabel")

        self.model_name_input = QLineEdit()
        self.model_name_input.setObjectName("ProjectFolderInput")
        self.model_name_input.setPlaceholderText("Ollama model, e.g. qwen2.5-coder:7b")
        self.model_name_input.setText(self.model_name)
        self.model_name_input.setToolTip("Optional Ollama model name. Clear the GGUF file to use this route.")
        self.model_name_input.editingFinished.connect(self._save_model_name)

        self.model_path_input = QLineEdit()
        self.model_path_input.setObjectName("ProjectFolderInput")
        self.model_path_input.setReadOnly(True)
        self.model_path_input.setPlaceholderText("Bundled Qwen2.5 Coder 7B GGUF")
        self.model_path_input.setText(self._model_display_text())

        self.change_model_btn = QPushButton("Change model")
        self.change_model_btn.setObjectName("ProjectModelButton")
        self.change_model_btn.clicked.connect(self._choose_model_source)

        self.clear_model_btn = QPushButton("Clear file")
        self.clear_model_btn.setObjectName("ProjectModelButton")
        self.clear_model_btn.clicked.connect(self._clear_model_file)

        model_button_row = QHBoxLayout()
        model_button_row.setContentsMargins(0, 0, 0, 0)
        model_button_row.setSpacing(8)
        model_button_row.addWidget(self.change_model_btn)
        model_button_row.addWidget(self.clear_model_btn)

        hardware_label = QLabel("GPU setting")
        hardware_label.setObjectName("ModeSectionLabel")

        self.gpu_status_input = QLineEdit()
        self.gpu_status_input.setObjectName("ProjectFolderInput")
        self.gpu_status_input.setReadOnly(True)
        self.gpu_status_input.setPlaceholderText("Detect GPU for model fit")
        self.gpu_status_input.setText(gpu_profile_summary(self.gpu_profile))
        self.gpu_status_input.setToolTip(self.gpu_profile.message)

        self.detect_gpu_btn = QPushButton("Detect GPU")
        self.detect_gpu_btn.setObjectName("ProjectModelButton")
        self.detect_gpu_btn.clicked.connect(lambda _checked=False: self._detect_gpu_profile(auto=False))

        music_provider_label = QLabel("Default music provider")
        music_provider_label.setObjectName("ModeSectionLabel")

        self.music_provider_select = QComboBox()
        self.music_provider_select.setObjectName("ProjectFolderInput")
        self.music_provider_select.setEditable(True)
        for provider in ("Amazon Music", "Spotify", "YouTube Music"):
            self.music_provider_select.addItem(provider)
        if self.music_provider_select.findText(self.default_music_provider) < 0:
            self.music_provider_select.addItem(self.default_music_provider)
        self.music_provider_select.setCurrentText(self.default_music_provider)
        self.music_provider_select.setToolTip(
            "Generic commands such as 'play music' use this installed application."
        )
        self.music_provider_select.activated.connect(
            lambda _index: self._save_default_music_provider(
                self.music_provider_select.currentText()
            )
        )
        if self.music_provider_select.lineEdit() is not None:
            self.music_provider_select.lineEdit().editingFinished.connect(
                lambda: self._save_default_music_provider(
                    self.music_provider_select.currentText()
                )
            )

        self.project_details = QFrame()
        self.project_details.setObjectName("ProjectDetails")
        self.project_details_opacity = QGraphicsOpacityEffect(self.project_details)
        self.project_details_opacity.setOpacity(0.0)
        self.project_details.setGraphicsEffect(self.project_details_opacity)
        project_details_layout = QVBoxLayout(self.project_details)
        project_details_layout.setContentsMargins(10, 10, 10, 10)
        project_details_layout.setSpacing(9)

        project_header = QHBoxLayout()
        project_header.setContentsMargins(0, 0, 0, 0)
        project_header.setSpacing(8)

        folder_label = QLabel("Project setup")
        folder_label.setObjectName("ModeSectionLabel")

        self.project_add_btn = QPushButton("+")
        self.project_add_btn.setObjectName("ProjectAddButton")
        self.project_add_btn.setFixedSize(32, 32)
        self.project_add_btn.setToolTip("Choose or create a work folder")
        self.project_add_btn.clicked.connect(self._choose_project_folder)

        project_header.addWidget(folder_label, stretch=1)
        project_header.addWidget(self.project_add_btn)

        self.project_folder_input = QLineEdit()
        self.project_folder_input.setObjectName("ProjectFolderInput")
        self.project_folder_input.setReadOnly(True)
        self.project_folder_input.setPlaceholderText("Choose a folder for builds")
        self.project_folder_input.setText(self.project_folder)

        access_label = QLabel("Access")
        access_label.setObjectName("ModeSectionLabel")

        self.folder_access_btn = QPushButton("Limited to folder")
        self.folder_access_btn.setObjectName("AccessOption")
        self.folder_access_btn.clicked.connect(lambda: self._set_project_access("folder"))

        self.full_access_btn = QPushButton("Full access")
        self.full_access_btn.setObjectName("AccessOption")
        self.full_access_btn.clicked.connect(lambda: self._set_project_access("full"))

        project_details_layout.addLayout(project_header)
        project_details_layout.addWidget(self.project_folder_input)
        project_details_layout.addWidget(access_label)
        project_details_layout.addWidget(self.folder_access_btn)
        project_details_layout.addWidget(self.full_access_btn)

        self.mode_status = QLabel("")
        self.mode_status.setObjectName("ModeStatus")
        self.mode_status.setWordWrap(True)

        mode_layout.addWidget(mode_title)
        mode_layout.addWidget(mode_hint)
        mode_layout.addSpacing(6)
        mode_layout.addWidget(self.normal_mode_btn)
        mode_layout.addWidget(self.project_mode_btn)
        mode_layout.addWidget(self.voice_mode_btn)
        mode_layout.addSpacing(4)
        mode_layout.addWidget(model_label)
        mode_layout.addWidget(self.model_name_input)
        mode_layout.addWidget(self.model_path_input)
        mode_layout.addLayout(model_button_row)
        mode_layout.addWidget(hardware_label)
        mode_layout.addWidget(self.gpu_status_input)
        mode_layout.addWidget(self.detect_gpu_btn)
        mode_layout.addWidget(music_provider_label)
        mode_layout.addWidget(self.music_provider_select)
        mode_layout.addWidget(self.project_details)
        mode_layout.addWidget(self.mode_status)
        mode_layout.addStretch(1)

        self.workspace_splitter.addWidget(self.mode_panel)
        self.mode_panel.setVisible(False)

        self.workspace_panel = QFrame()
        self.workspace_panel.setObjectName("ScienceWorkspacePanel")
        self.workspace_panel.setMinimumWidth(350)
        self.workspace_panel.setMaximumWidth(700)
        self.workspace_panel.resize(430, 620)
        workspace_layout = QVBoxLayout(self.workspace_panel)
        workspace_layout.setContentsMargins(14, 14, 14, 14)
        workspace_layout.setSpacing(10)

        workspace_header = QHBoxLayout()
        workspace_header.setContentsMargins(0, 0, 0, 0)
        workspace_title = QLabel("Science workspace")
        workspace_title.setObjectName("ScienceWorkspaceTitle")
        workspace_close = QPushButton("Close")
        workspace_close.setObjectName("WorkspaceCloseButton")
        workspace_close.clicked.connect(self._close_workspace)
        workspace_header.addWidget(workspace_title, stretch=1)
        workspace_header.addWidget(workspace_close)

        workspace_tabs = QHBoxLayout()
        workspace_tabs.setContentsMargins(0, 0, 0, 0)
        workspace_tabs.setSpacing(8)
        self.graph_workspace_btn = QPushButton("Graphs")
        self.graph_workspace_btn.setObjectName("WorkspaceTab")
        self.graph_workspace_btn.clicked.connect(lambda: self._set_workspace_view("graph"))
        self.physics_workspace_btn = QPushButton("Simulations")
        self.physics_workspace_btn.setObjectName("WorkspaceTab")
        self.physics_workspace_btn.clicked.connect(lambda: self._set_workspace_view("physics"))
        self.notebook_workspace_btn = QPushButton("Notebook")
        self.notebook_workspace_btn.setObjectName("WorkspaceTab")
        self.notebook_workspace_btn.clicked.connect(lambda: self._set_workspace_view("notebook"))
        workspace_tabs.addWidget(self.graph_workspace_btn)
        workspace_tabs.addWidget(self.physics_workspace_btn)
        workspace_tabs.addWidget(self.notebook_workspace_btn)

        self.workspace_artifact_list = QListWidget()
        self.workspace_artifact_list.setObjectName("WorkspaceArtifactList")
        self.workspace_artifact_list.currentRowChanged.connect(self._on_workspace_artifact_selected)

        self.graph_canvas_host = QWidget()
        self.graph_canvas_layout = QVBoxLayout(self.graph_canvas_host)
        self.graph_canvas_layout.setContentsMargins(0, 0, 0, 0)
        self.graph_canvas_layout.setSpacing(0)
        self.graph_canvas = GraphCanvas()
        self.graph_canvas.inspected.connect(lambda text: self.graph_inspector.setText(text or "Move over the graph to inspect points."))
        self.graph_canvas_layout.addWidget(self.graph_canvas)
        self.graph_dimension_select = QComboBox()
        self.graph_dimension_select.setObjectName("InlineVisualizationSelect")
        self.graph_dimension_select.addItem("2D", "2d")
        self.graph_dimension_select.addItem("3D", "3d")
        self.graph_dimension_select.setCurrentText("3D")
        self.graph_dimension_select.setVisible(False)
        self.graph_dimension_select.currentIndexChanged.connect(
            lambda index: self.graph_canvas.set_view_mode(
                str(self.graph_dimension_select.itemData(index))
            )
            if isinstance(self.graph_canvas, SurfaceCanvas)
            else None
        )
        self.graph_inspector = QLabel("Move over the graph to inspect points.")
        self.graph_inspector.setObjectName("WorkspaceInspector")
        self.graph_equations = QLabel("No equations yet.")
        self.graph_equations.setObjectName("WorkspaceInspector")
        self.graph_equations.setWordWrap(True)

        self.physics_canvas = PhysicsCanvas()
        self.physics_canvas.stats_changed.connect(lambda text: self.physics_stats.setText(text))
        self.physics_stats = QLabel("No simulation yet.")
        self.physics_stats.setObjectName("WorkspaceInspector")
        self.physics_stats.setWordWrap(True)

        self.physics_controls_frame = QFrame()
        self.physics_controls_frame.setObjectName("WorkspaceControlsFrame")
        physics_controls = QHBoxLayout(self.physics_controls_frame)
        physics_controls.setContentsMargins(0, 0, 0, 0)
        physics_controls.setSpacing(8)
        pause_btn = QPushButton("Pause")
        pause_btn.setObjectName("WorkspaceControl")
        pause_btn.clicked.connect(lambda: self.physics_canvas.set_running(False))
        resume_btn = QPushButton("Resume")
        resume_btn.setObjectName("WorkspaceControl")
        resume_btn.clicked.connect(lambda: self.physics_canvas.set_running(True))
        step_btn = QPushButton("Step")
        step_btn.setObjectName("WorkspaceControl")
        step_btn.clicked.connect(self.physics_canvas.step_once)
        back_btn = QPushButton("Back")
        back_btn.setObjectName("WorkspaceControl")
        back_btn.clicked.connect(self.physics_canvas.step_back)
        speed_btn = QPushButton("2x")
        speed_btn.setObjectName("WorkspaceControl")
        speed_btn.clicked.connect(lambda: self.physics_canvas.set_speed(2.0 if self.physics_canvas.speed == 1.0 else 1.0))
        self.physics_dimension_select = QComboBox()
        self.physics_dimension_select.setObjectName("InlineVisualizationSelect")
        self.physics_dimension_select.addItem("2D", "2d")
        self.physics_dimension_select.addItem("3D", "3d")
        self.physics_dimension_select.setCurrentText("3D")
        self.physics_dimension_select.setVisible(False)
        self.physics_dimension_select.currentIndexChanged.connect(
            lambda index: self.physics_canvas.set_render_mode(
                str(self.physics_dimension_select.itemData(index))
            )
        )
        physics_controls.addWidget(pause_btn)
        physics_controls.addWidget(resume_btn)
        physics_controls.addWidget(step_btn)
        physics_controls.addWidget(back_btn)
        physics_controls.addWidget(speed_btn)
        physics_controls.addWidget(self.physics_dimension_select)

        self.notebook_view = QTextEdit()
        self.notebook_view.setObjectName("WorkspaceNotebook")
        self.notebook_view.setReadOnly(True)
        self.notebook_view.setPlainText(
            "Scientific notebook mode stores the chat prompt, deterministic instruction JSON, generated graphs, "
            "simulation state, files, and notes per project. This VNext panel is the first desktop slice."
        )

        workspace_layout.addLayout(workspace_header)
        workspace_layout.addLayout(workspace_tabs)
        workspace_layout.addWidget(self.workspace_artifact_list)
        workspace_layout.addWidget(self.graph_canvas_host, stretch=1)
        workspace_layout.addWidget(self.graph_dimension_select)
        workspace_layout.addWidget(self.graph_equations)
        workspace_layout.addWidget(self.graph_inspector)
        workspace_layout.addWidget(self.physics_canvas, stretch=1)
        workspace_layout.addWidget(self.physics_stats)
        workspace_layout.addWidget(self.physics_controls_frame)
        workspace_layout.addWidget(self.notebook_view, stretch=1)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        self.content_layout = content_layout
        self.content_host = QWidget()
        self.content_host.setObjectName("ContentHost")
        self.content_host.setLayout(content_layout)
        self.workspace_splitter.addWidget(self.content_host)

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
        self._message_rows: list[QFrame] = []
        self._archived_messages: list[tuple[str, str, bool]] = []
        self.chat_archive_notice = QFrame()
        self.chat_archive_notice.setObjectName("ChatArchiveNotice")
        archive_layout = QHBoxLayout(self.chat_archive_notice)
        archive_layout.setContentsMargins(8, 5, 8, 5)
        self.chat_archive_label = QLabel()
        self.chat_archive_label.setObjectName("MessageMeta")
        self.chat_archive_load_btn = QPushButton("Load earlier")
        self.chat_archive_load_btn.setObjectName("MessageAction")
        self.chat_archive_load_btn.clicked.connect(self._load_earlier_messages)
        archive_layout.addWidget(self.chat_archive_label, stretch=1)
        archive_layout.addWidget(self.chat_archive_load_btn)
        self.chat_archive_notice.setVisible(False)
        self.chat_list_layout.addWidget(self.chat_archive_notice)
        self._bottom_spacer = QWidget()
        self._bottom_spacer.setFixedHeight(8)
        self.chat_list_layout.addWidget(self._bottom_spacer)

        content_layout.addWidget(chat_container, stretch=1)
        chat_container.setVisible(False)

        self.live_action_workspace = LiveActionWorkspace()
        self.live_action_workspace.setVisible(False)
        self.live_action_workspace.cameraRequested.connect(
            self._on_live_camera_requested
        )
        self.live_action_workspace.cameraConfigurationChanged.connect(
            self._on_live_camera_configuration_changed
        )
        self.live_action_workspace.awarenessRequested.connect(
            self._on_live_awareness_requested
        )
        self.live_action_workspace.microphoneRequested.connect(
            self._on_live_microphone_requested
        )
        self.live_action_workspace.textSubmitted.connect(
            self._submit_live_action_text
        )
        self.live_action_workspace.analyzeRequested.connect(
            lambda: self._submit_live_action_text("Analyze the current camera view.")
        )
        self.live_action_workspace.exitRequested.connect(
            lambda: self._set_chat_mode(self._voice_return_mode)
        )
        content_layout.addWidget(self.live_action_workspace, stretch=1)

        self.live_camera = LiveCameraController(self)
        self.live_camera.devicesChanged.connect(
            self.live_action_workspace.set_devices
        )
        self.live_camera.frameReady.connect(self._on_live_camera_frame)
        self.live_camera.stateChanged.connect(
            self.live_action_workspace.set_camera_state
        )
        self.live_camera.diagnosticsChanged.connect(
            self.runtime.update_live_camera_diagnostics
        )
        self.live_action_workspace.set_devices(self.live_camera.options())
        try:
            saved_camera_fps = float(self.settings.get("camera_fps", "30"))
        except (TypeError, ValueError):
            saved_camera_fps = 30.0
        self.live_action_workspace.apply_preferences(
            device_id=str(self.settings.get("camera_device_id", "")),
            resolution=str(self.settings.get("camera_resolution", "1280x720")),
            fps=saved_camera_fps,
            mirror=normalize_boolean_setting(
                self.settings.get("camera_mirror", "true"), default=True
            ),
            continuous_awareness=normalize_boolean_setting(
                self.settings.get("continuous_visual_awareness", "false")
            ),
        )
        self.runtime.update_live_camera_diagnostics(self.live_camera.diagnostics())

        # Keep the live graph/simulation workspace beside the conversation instead of hiding it in the chat flow.
        self.workspace_splitter.addWidget(self.workspace_panel)
        self.workspace_panel.setVisible(False)

        self.changes_panel = QFrame()
        self.changes_panel.setObjectName("ProjectChangesPanel")
        self.changes_panel.setMinimumWidth(390)
        self.changes_panel.setMaximumWidth(680)
        self.changes_panel.resize(390, 620)
        self.changes_minimized = False
        self.changes_expanded = False
        self.changes_panel_dismissed = False
        self.changes_available = False
        changes_layout = QVBoxLayout(self.changes_panel)
        changes_layout.setContentsMargins(14, 14, 14, 14)
        changes_layout.setSpacing(10)

        changes_header = QHBoxLayout()
        changes_header.setContentsMargins(0, 0, 0, 0)
        changes_header.setSpacing(6)
        self.changes_title = QLabel("Project changes")
        self.changes_title.setObjectName("ProjectChangesTitle")
        self.changes_minimize_btn = QPushButton("_")
        self.changes_minimize_btn.setObjectName("ChangesIconButton")
        self.changes_minimize_btn.setToolTip("Minimize project changes")
        self.changes_minimize_btn.clicked.connect(self._toggle_changes_minimized)
        # Keep code review readable. The former minimized strip could become a
        # nearly empty sliver at the right edge and hide the actual diff.
        self.changes_minimize_btn.setVisible(False)
        self.changes_expand_btn = QPushButton("[]")
        self.changes_expand_btn.setObjectName("ChangesIconButton")
        self.changes_expand_btn.setFixedSize(30, 30)
        self.changes_expand_btn.setToolTip("Widen project changes")
        self.changes_expand_btn.clicked.connect(self._toggle_changes_width)
        self.changes_close_btn = QPushButton()
        self.changes_close_btn.setObjectName("ChangesIconButton")
        self.changes_close_btn.setFixedSize(30, 30)
        self.changes_close_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_TitleBarCloseButton)
        )
        self.changes_close_btn.setToolTip("Close project changes")
        self.changes_close_btn.clicked.connect(self._close_changes_panel)
        changes_header.addWidget(self.changes_title, stretch=1)
        changes_header.addWidget(self.changes_minimize_btn)
        changes_header.addWidget(self.changes_expand_btn)
        changes_header.addWidget(self.changes_close_btn)

        self.changes_summary = QLabel("Build something in Project mode to see file changes here.")
        self.changes_summary.setObjectName("ProjectChangesSummary")
        self.changes_summary.setWordWrap(True)

        self.changes_view = QTextEdit()
        self.changes_view.setObjectName("ProjectChangesView")
        self.changes_view.setReadOnly(True)
        self.changes_view.setAcceptRichText(True)

        self.changes_content = QWidget()
        changes_content_layout = QVBoxLayout(self.changes_content)
        changes_content_layout.setContentsMargins(0, 0, 0, 0)
        changes_content_layout.setSpacing(8)

        project_tabs = QHBoxLayout()
        project_tabs.setContentsMargins(0, 0, 0, 0)
        project_tabs.setSpacing(6)
        self.project_files_tab = QPushButton("Files")
        self.project_changes_tab = QPushButton("Changes")
        self.project_output_tab = QPushButton("Output")
        for index, button in enumerate(
            (self.project_files_tab, self.project_changes_tab, self.project_output_tab)
        ):
            button.setObjectName("WorkspaceTab")
            button.clicked.connect(
                lambda _checked=False, selected=index: self._set_project_workspace_tab(
                    selected
                )
            )
            project_tabs.addWidget(button)
        changes_content_layout.addLayout(project_tabs)

        self.project_workspace_stack = QStackedWidget()
        self.project_workspace_stack.setObjectName("ProjectWorkspaceStack")
        changes_content_layout.addWidget(self.project_workspace_stack, stretch=1)

        self.project_files_page = QWidget()
        project_files_layout = QVBoxLayout(self.project_files_page)
        project_files_layout.setContentsMargins(0, 0, 0, 0)
        project_files_layout.setSpacing(8)
        files_header = QHBoxLayout()
        files_label = QLabel("Project tree")
        files_label.setObjectName("ProjectChangesSummary")
        files_refresh = QPushButton("Refresh")
        files_refresh.setObjectName("ProjectActionButton")
        files_refresh.clicked.connect(self._refresh_project_tree)
        files_header.addWidget(files_label, stretch=1)
        files_header.addWidget(files_refresh)
        self.project_file_tree = QTreeWidget()
        self.project_file_tree.setObjectName("ProjectFileTree")
        self.project_file_tree.setHeaderHidden(True)
        self.project_file_tree.itemSelectionChanged.connect(
            self._preview_selected_project_file
        )
        self.project_file_preview = QTextEdit()
        self.project_file_preview.setObjectName("ProjectChangesView")
        self.project_file_preview.setReadOnly(True)
        self.project_file_preview.setPlaceholderText(
            "Select a text file to preview it."
        )
        project_files_layout.addLayout(files_header)
        project_files_layout.addWidget(self.project_file_tree, stretch=1)
        project_files_layout.addWidget(self.project_file_preview, stretch=2)
        self.project_workspace_stack.addWidget(self.project_files_page)

        self.project_changes_page = QWidget()
        changes_page_layout = QVBoxLayout(self.project_changes_page)
        changes_page_layout.setContentsMargins(0, 0, 0, 0)
        changes_page_layout.setSpacing(10)
        self.changes_verify_btn = QPushButton("Verify project")
        self.changes_verify_btn.setObjectName("ProjectActionButton")
        self.changes_verify_btn.setToolTip("Validate the source files in the selected project folder")
        self.changes_verify_btn.clicked.connect(self._verify_project)
        self.changes_run_btn = QPushButton("Run project")
        self.changes_run_btn.setObjectName("ProjectActionButton")
        self.changes_run_btn.setToolTip("Run the project using its verified local entry point")
        self.changes_run_btn.clicked.connect(self._run_project)
        self.changes_apply_btn = QPushButton("Apply patch")
        self.changes_apply_btn.setObjectName("ProjectActionButton")
        self.changes_apply_btn.setToolTip(
            "Apply the reviewed file patch to the selected work folder"
        )
        self.changes_apply_btn.clicked.connect(self._apply_pending_project_patch)
        self.changes_apply_btn.setEnabled(False)
        self.changes_reject_btn = QPushButton("Reject")
        self.changes_reject_btn.setObjectName("ProjectActionButton")
        self.changes_reject_btn.setToolTip("Discard the pending file patch")
        self.changes_reject_btn.clicked.connect(self._reject_pending_project_patch)
        self.changes_reject_btn.setEnabled(False)
        self.changes_undo_btn = QPushButton("Undo")
        self.changes_undo_btn.setObjectName("ProjectActionButton")
        self.changes_undo_btn.setToolTip("Restore files changed by the last MORICE patch")
        self.changes_undo_btn.clicked.connect(self._undo_last_project_patch)
        self.changes_undo_btn.setEnabled(False)
        self.changes_action_status = QLabel("No runnable project detected yet.")
        self.changes_action_status.setObjectName("ProjectChangesSummary")
        self.changes_action_status.setWordWrap(True)
        run_action_row = QHBoxLayout()
        run_action_row.setContentsMargins(0, 0, 0, 0)
        run_action_row.setSpacing(8)
        run_action_row.addWidget(self.changes_verify_btn)
        run_action_row.addWidget(self.changes_run_btn)
        patch_action_row = QHBoxLayout()
        patch_action_row.setContentsMargins(0, 0, 0, 0)
        patch_action_row.setSpacing(8)
        patch_action_row.addWidget(self.changes_apply_btn)
        patch_action_row.addWidget(self.changes_reject_btn)
        patch_action_row.addWidget(self.changes_undo_btn)
        changes_page_layout.addWidget(self.changes_summary)
        changes_page_layout.addWidget(self.changes_view, stretch=1)
        changes_page_layout.addLayout(run_action_row)
        changes_page_layout.addLayout(patch_action_row)
        changes_page_layout.addWidget(self.changes_action_status)
        self.project_workspace_stack.addWidget(self.project_changes_page)

        self.project_output_page = QWidget()
        output_layout = QVBoxLayout(self.project_output_page)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        output_header = QHBoxLayout()
        output_label = QLabel("Terminal and build output")
        output_label.setObjectName("ProjectChangesSummary")
        git_status_button = QPushButton("Git status")
        git_status_button.setObjectName("ProjectActionButton")
        git_status_button.clicked.connect(self._show_project_git_status)
        clear_output_button = QPushButton("Clear")
        clear_output_button.setObjectName("ProjectActionButton")
        clear_output_button.clicked.connect(lambda: self.project_output_view.clear())
        output_header.addWidget(output_label, stretch=1)
        output_header.addWidget(git_status_button)
        output_header.addWidget(clear_output_button)
        self.project_output_view = QTextEdit()
        self.project_output_view.setObjectName("ProjectChangesView")
        self.project_output_view.setReadOnly(True)
        self.project_output_view.setAcceptRichText(False)
        self.project_output_view.setPlaceholderText(
            "Verification, tests, run logs, Git status, and terminal output appear here."
        )
        command_row = QHBoxLayout()
        self.project_command_input = QLineEdit()
        self.project_command_input.setObjectName("ProjectFolderInput")
        self.project_command_input.setPlaceholderText(
            "Run in project folder, e.g. python -m unittest"
        )
        self.project_command_input.returnPressed.connect(self._run_project_command)
        command_button = QPushButton("Run")
        command_button.setObjectName("ProjectActionButton")
        command_button.clicked.connect(self._run_project_command)
        self.project_command_stop_btn = QPushButton("Stop")
        self.project_command_stop_btn.setObjectName("ProjectActionButton")
        self.project_command_stop_btn.setEnabled(False)
        self.project_command_stop_btn.clicked.connect(
            self._cancel_project_command
        )
        command_row.addWidget(self.project_command_input, stretch=1)
        command_row.addWidget(command_button)
        command_row.addWidget(self.project_command_stop_btn)
        output_layout.addLayout(output_header)
        output_layout.addWidget(self.project_output_view, stretch=1)
        output_layout.addLayout(command_row)
        self.project_workspace_stack.addWidget(self.project_output_page)

        changes_layout.addLayout(changes_header)
        changes_layout.addWidget(self.changes_content, stretch=1)
        self._set_project_workspace_tab(1)
        self.workspace_splitter.addWidget(self.changes_panel)
        self.changes_panel.setVisible(False)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("SidebarPanel")
        self.sidebar.setMinimumWidth(290)
        self.sidebar.setMaximumWidth(480)
        self.sidebar.resize(340, 620)
        sidebar_shell_layout = QVBoxLayout(self.sidebar)
        sidebar_shell_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setObjectName("SidebarScroll")
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar_content = QFrame()
        self.sidebar_content.setObjectName("SidebarContent")
        sidebar_layout = QVBoxLayout(self.sidebar_content)
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

        appearance_label = QLabel("Appearance")
        appearance_label.setObjectName("SidebarSectionLabel")

        theme_label = QLabel("Theme")
        theme_label.setObjectName("StyleLabel")
        self.theme_select = QComboBox()
        self.theme_select.setObjectName("AppearanceSelect")
        for label, key in (
            ("Dark", "dark"),
            ("Light", "light"),
            ("Midnight", "midnight"),
            ("Glass", "glass"),
            ("Custom", "custom"),
        ):
            self.theme_select.addItem(label, key)
        self.theme_select.setCurrentIndex(
            max(0, self.theme_select.findData(self.current_theme))
        )
        self.theme_select.currentIndexChanged.connect(self._on_theme_selection_changed)

        emoji_label = QLabel("Emoji amount")
        emoji_label.setObjectName("StyleLabel")
        self.emoji_select = QComboBox()
        self.emoji_select.setObjectName("AppearanceSelect")
        self.emoji_select.addItem("None", "none")
        self.emoji_select.addItem("Medium", "medium")
        self.emoji_select.addItem("Expressive", "expressive")
        emoji_index = self.emoji_select.findData(self.emoji_level)
        self.emoji_select.setCurrentIndex(max(0, emoji_index))
        self.emoji_select.currentIndexChanged.connect(self._on_emoji_selection_changed)

        maturity_label = QLabel("Maturity")
        maturity_label.setObjectName("StyleLabel")
        self.maturity_select = QComboBox()
        self.maturity_select.setObjectName("AppearanceSelect")
        self.maturity_select.addItem("None", "none")
        self.maturity_select.addItem("Medium", "medium")
        self.maturity_select.addItem("Full", "full")
        maturity_index = self.maturity_select.findData(self.maturity_level)
        self.maturity_select.setCurrentIndex(max(0, maturity_index))
        self.maturity_select.currentIndexChanged.connect(
            self._on_maturity_selection_changed
        )

        font_label = QLabel("App font")
        font_label.setObjectName("StyleLabel")
        self.font_select = QComboBox()
        self.font_select.setObjectName("AppearanceSelect")
        for family in available_ui_font_families(self.font_family):
            self.font_select.addItem(family, family)
        selected_font_index = self.font_select.findData(self.font_family)
        self.font_select.setCurrentIndex(max(0, selected_font_index))
        self.font_select.currentIndexChanged.connect(self._on_font_selection_changed)

        add_font_btn = QPushButton("Add your own")
        add_font_btn.setObjectName("QueueButton")
        add_font_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_DialogOpenButton)
        )
        add_font_btn.setToolTip("Load a local TTF, OTF, or TTC font")
        add_font_btn.clicked.connect(self._choose_custom_font)
        self.add_font_btn = add_font_btn

        motion_label = QLabel("Motion")
        motion_label.setObjectName("StyleLabel")
        self.animation_speed_select = QComboBox()
        self.animation_speed_select.setObjectName("AppearanceSelect")
        for label, key in (("Slow", "slow"), ("Normal", "normal"), ("Fast", "fast")):
            self.animation_speed_select.addItem(label, key)
        self.animation_speed_select.setCurrentIndex(
            max(0, self.animation_speed_select.findData(self.animation_speed))
        )
        self.animation_speed_select.currentIndexChanged.connect(
            self._on_experience_control_changed
        )

        self.reduced_motion_check = QCheckBox("Reduced motion")
        self.reduced_motion_check.setChecked(self.reduced_motion)
        self.reduced_motion_check.setAccessibleName("Reduce interface motion")
        self.reduced_motion_check.toggled.connect(self._on_experience_control_changed)

        self.high_contrast_check = QCheckBox("High contrast")
        self.high_contrast_check.setChecked(self.high_contrast)
        self.high_contrast_check.setAccessibleName("Use high contrast interface")
        self.high_contrast_check.toggled.connect(self._on_experience_control_changed)

        self.large_text_check = QCheckBox("Large text")
        self.large_text_check.setChecked(self.large_text)
        self.large_text_check.setAccessibleName("Use large interface text")
        self.large_text_check.toggled.connect(self._on_experience_control_changed)

        scale_label = QLabel("Interface scale")
        scale_label.setObjectName("StyleLabel")
        self.ui_scale_slider = QSlider(Qt.Horizontal)
        self.ui_scale_slider.setRange(80, 160)
        self.ui_scale_slider.setSingleStep(5)
        self.ui_scale_slider.setValue(round(self.ui_scale * 100))
        self.ui_scale_slider.setAccessibleName("Interface scale")
        self.ui_scale_slider.sliderReleased.connect(self._on_experience_control_changed)

        opacity_label = QLabel("Glass opacity")
        opacity_label.setObjectName("StyleLabel")
        self.transparency_slider = QSlider(Qt.Horizontal)
        self.transparency_slider.setRange(70, 100)
        self.transparency_slider.setValue(self.transparency)
        self.transparency_slider.setAccessibleName("Glass opacity")
        self.transparency_slider.sliderReleased.connect(
            self._on_experience_control_changed
        )

        layout_label = QLabel("Workspace layout")
        layout_label.setObjectName("StyleLabel")
        self.workspace_preset_select = QComboBox()
        self.workspace_preset_select.setObjectName("AppearanceSelect")
        for label, key in (
            ("Balanced", "balanced"),
            ("Focus", "focus"),
            ("Science", "science"),
            ("Project", "project"),
            ("Research", "research"),
        ):
            self.workspace_preset_select.addItem(label, key)
        self.workspace_preset_select.setCurrentIndex(
            max(0, self.workspace_preset_select.findData(self.workspace_preset))
        )
        self.workspace_preset_select.currentIndexChanged.connect(
            self._on_workspace_preset_selected
        )

        self.advanced_settings_btn = QPushButton("Advanced settings")
        self.advanced_settings_btn.setObjectName("QueueButton")
        self.advanced_settings_btn.setToolTip(
            "Search settings, preview themes, and manage profiles"
        )
        self.advanced_settings_btn.clicked.connect(self.open_premium_settings)

        voice_label = QLabel("Live Action voice configuration")
        voice_label.setObjectName("SidebarSectionLabel")
        self.tts_enabled_check = QCheckBox("Speak MORICE replies in Live Action")
        self.tts_enabled_check.setChecked(
            normalize_boolean_setting(
                self.settings.get("tts_enabled", "true"), default=True
            )
        )
        self.tts_streaming_check = QCheckBox("Stream speech while replying")
        self.tts_streaming_check.setChecked(
            normalize_boolean_setting(
                self.settings.get("tts_streaming", "true"), default=True
            )
        )
        self.tts_fallback_check = QCheckBox("Fall back to text safely")
        self.tts_fallback_check.setChecked(
            normalize_boolean_setting(
                self.settings.get("tts_automatic_fallback", "true"),
                default=True,
            )
        )
        self.stt_enabled_check = QCheckBox("Enable microphone in Live Action")
        self.stt_enabled_check.setChecked(
            normalize_boolean_setting(
                self.settings.get("stt_enabled", "true"), default=True
            )
        )
        self.stt_auto_send_check = QCheckBox("Send recognized speech automatically")
        self.stt_auto_send_check.setChecked(
            normalize_boolean_setting(
                self.settings.get("stt_auto_send", "true"), default=True
            )
        )

        tts_voice_label = QLabel("ElevenLabs voice ID")
        tts_voice_label.setObjectName("StyleLabel")
        self.tts_voice_id_input = QLineEdit()
        self.tts_voice_id_input.setObjectName("TitleInput")
        self.tts_voice_id_input.setText(
            normalize_tts_voice_id(self.settings.get("tts_voice_id", ""))
        )

        tts_model_label = QLabel("ElevenLabs model")
        tts_model_label.setObjectName("StyleLabel")
        self.tts_model_id_input = QLineEdit()
        self.tts_model_id_input.setObjectName("TitleInput")
        self.tts_model_id_input.setText(
            normalize_tts_model_id(self.settings.get("tts_model_id", ""))
        )

        tts_speed_label = QLabel("Speech speed")
        tts_speed_label.setObjectName("StyleLabel")
        self.tts_speed_slider = QSlider(Qt.Horizontal)
        self.tts_speed_slider.setRange(70, 120)
        self.tts_speed_slider.setValue(
            round(normalize_tts_speed(self.settings.get("tts_speech_speed", "1")) * 100)
        )
        self.tts_speed_slider.setAccessibleName("ElevenLabs speech speed")

        devices = self.runtime.desktop.voice.devices()
        tts_output_label = QLabel("Reply audio output")
        tts_output_label.setObjectName("StyleLabel")
        stt_input_label = QLabel("Conversation microphone")
        stt_input_label.setObjectName("StyleLabel")
        self.tts_output_device_select = QComboBox()
        self.tts_output_device_select.setObjectName("AppearanceSelect")
        self.tts_output_device_select.addItem("Default output device", "")
        self.stt_input_device_select = QComboBox()
        self.stt_input_device_select.setObjectName("AppearanceSelect")
        self.stt_input_device_select.addItem("Default microphone", "")
        for device in devices:
            index = str(device.get("index", ""))
            name = str(device.get("name", "Device"))
            if int(device.get("outputs", 0) or 0) > 0:
                self.tts_output_device_select.addItem(name, index)
            if int(device.get("inputs", 0) or 0) > 0:
                self.stt_input_device_select.addItem(name, index)
        self.tts_output_device_select.setCurrentIndex(
            max(
                0,
                self.tts_output_device_select.findData(
                    normalize_tts_output_device(
                        self.settings.get("tts_output_device", "")
                    )
                ),
            )
        )
        self.stt_input_device_select.setCurrentIndex(
            max(
                0,
                self.stt_input_device_select.findData(
                    normalize_stt_input_device(
                        self.settings.get("stt_input_device", "")
                    )
                ),
            )
        )

        api_key_label = QLabel("ElevenLabs API key (stored with Windows DPAPI)")
        api_key_label.setObjectName("StyleLabel")
        self.elevenlabs_api_key_input = QLineEdit()
        self.elevenlabs_api_key_input.setObjectName("TitleInput")
        self.elevenlabs_api_key_input.setEchoMode(QLineEdit.Password)
        self.elevenlabs_api_key_input.setPlaceholderText("Paste a new rotated key locally")
        self.elevenlabs_api_status = QLabel()
        self.elevenlabs_api_status.setObjectName("StyleStatus")
        self.elevenlabs_api_status.setText(
            "ElevenLabs API: Configured"
            if self.runtime.voice.status().api_configured
            else "ElevenLabs API: Not configured"
        )
        save_api_key_btn = QPushButton("Store API key securely")
        save_api_key_btn.setObjectName("QueueButton")
        save_api_key_btn.clicked.connect(self._store_elevenlabs_key)
        self.save_api_key_btn = save_api_key_btn
        save_voice_btn = QPushButton("Save voice settings")
        save_voice_btn.setObjectName("StyleSaveButton")
        save_voice_btn.clicked.connect(self._save_voice_settings)
        self.save_voice_btn = save_voice_btn

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
        sidebar_layout.addWidget(appearance_label)
        sidebar_layout.addWidget(theme_label)
        sidebar_layout.addWidget(self.theme_select)
        sidebar_layout.addWidget(emoji_label)
        sidebar_layout.addWidget(self.emoji_select)
        sidebar_layout.addWidget(maturity_label)
        sidebar_layout.addWidget(self.maturity_select)
        sidebar_layout.addWidget(font_label)
        sidebar_layout.addWidget(self.font_select)
        sidebar_layout.addWidget(self.add_font_btn)
        sidebar_layout.addWidget(motion_label)
        sidebar_layout.addWidget(self.animation_speed_select)
        sidebar_layout.addWidget(self.reduced_motion_check)
        sidebar_layout.addWidget(self.high_contrast_check)
        sidebar_layout.addWidget(self.large_text_check)
        sidebar_layout.addWidget(scale_label)
        sidebar_layout.addWidget(self.ui_scale_slider)
        sidebar_layout.addWidget(opacity_label)
        sidebar_layout.addWidget(self.transparency_slider)
        sidebar_layout.addWidget(layout_label)
        sidebar_layout.addWidget(self.workspace_preset_select)
        sidebar_layout.addWidget(self.advanced_settings_btn)
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(voice_label)
        sidebar_layout.addWidget(self.tts_enabled_check)
        sidebar_layout.addWidget(self.tts_streaming_check)
        sidebar_layout.addWidget(self.tts_fallback_check)
        sidebar_layout.addWidget(self.stt_enabled_check)
        sidebar_layout.addWidget(self.stt_auto_send_check)
        sidebar_layout.addWidget(tts_voice_label)
        sidebar_layout.addWidget(self.tts_voice_id_input)
        sidebar_layout.addWidget(tts_model_label)
        sidebar_layout.addWidget(self.tts_model_id_input)
        sidebar_layout.addWidget(tts_speed_label)
        sidebar_layout.addWidget(self.tts_speed_slider)
        sidebar_layout.addWidget(tts_output_label)
        sidebar_layout.addWidget(self.tts_output_device_select)
        sidebar_layout.addWidget(stt_input_label)
        sidebar_layout.addWidget(self.stt_input_device_select)
        sidebar_layout.addWidget(api_key_label)
        sidebar_layout.addWidget(self.elevenlabs_api_key_input)
        sidebar_layout.addWidget(self.save_api_key_btn)
        sidebar_layout.addWidget(self.elevenlabs_api_status)
        sidebar_layout.addWidget(self.save_voice_btn)
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(queue_label)
        sidebar_layout.addWidget(self.queue_list)
        sidebar_layout.addLayout(queue_buttons)
        sidebar_layout.addStretch(1)
        self.sidebar_scroll.setWidget(self.sidebar_content)
        sidebar_shell_layout.addWidget(self.sidebar_scroll)

        self.workspace_splitter.addWidget(self.sidebar)
        self.sidebar.setVisible(False)

        self.assistant_hub = AssistantHub(self)
        self.assistant_hub.command_requested.connect(self._on_workspace_command)
        self.assistant_hub.notes_changed.connect(self._on_workspace_notes_changed)
        self.assistant_hub.visibility_requested.connect(self._set_assistant_hub_visible)
        self.workspace_splitter.addWidget(self.assistant_hub)
        self.assistant_hub.setVisible(False)
        self.assistant_hub.set_clipboard_status(
            self.runtime.desktop.clipboard.enabled
        )
        clipboard = QApplication.clipboard()
        clipboard.dataChanged.connect(self._capture_clipboard_entry)
        self._register_desktop_search_providers()
        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setStretchFactor(2, 0)
        self.workspace_splitter.setStretchFactor(3, 0)
        self.workspace_splitter.setStretchFactor(4, 0)
        self.workspace_splitter.setStretchFactor(5, 0)

        input_frame = QFrame()
        input_frame.setObjectName("InputFrame")
        self.input_frame = input_frame
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)
        input_layout.setSpacing(10)

        self._prompt_history_index = -1
        self.input = AdaptivePromptEdit()
        self.input.setPlaceholderText(f"{self.user_title}: type here...")
        self.input.setObjectName("InputBox")
        self.input.returnPressed.connect(self.on_send)
        self.input.historyRequested.connect(self._navigate_prompt_history)
        self.input.textChanged.connect(self._refresh_send_button_state)

        self.attach_btn = QPushButton()
        self.attach_btn.setObjectName("ComposerToolButton")
        self.attach_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_DialogOpenButton)
        )
        self.attach_btn.setToolTip("Attach an image (Ctrl+O)")
        self.attach_btn.setAccessibleName("Attach image")
        self.attach_btn.clicked.connect(self.on_attach)

        self.voice_btn = QPushButton()
        self.voice_btn.setObjectName("ComposerToolButton")
        self.voice_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_MediaVolume)
        )
        self.voice_btn.setToolTip("Enter Live Action")
        self.voice_btn.setAccessibleName("Enter or exit Live Action")
        self.voice_btn.clicked.connect(self._toggle_voice_input)

        self.model_selector_btn = QPushButton()
        self.model_selector_btn.setObjectName("ComposerToolButton")
        self.model_selector_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
        )
        self.model_selector_btn.setToolTip("Choose AI model")
        self.model_selector_btn.setAccessibleName("Choose AI model")
        self.model_selector_btn.clicked.connect(self._choose_model_source)

        self.project_selector_btn = QPushButton()
        self.project_selector_btn.setObjectName("ComposerToolButton")
        self.project_selector_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_DirIcon)
        )
        self.project_selector_btn.setToolTip("Switch between chat and Project mode")
        self.project_selector_btn.setAccessibleName("Choose workspace mode")
        self.project_selector_btn.clicked.connect(self._toggle_composer_project_mode)

        self.quick_actions_btn = QPushButton()
        self.quick_actions_btn.setObjectName("ComposerToolButton")
        self.quick_actions_btn.setIcon(
            QApplication.style().standardIcon(QStyle.SP_FileDialogContentsView)
        )
        self.quick_actions_btn.setToolTip("Quick actions (Ctrl+K)")
        self.quick_actions_btn.setAccessibleName("Open quick actions")
        self.quick_actions_btn.clicked.connect(self.open_command_palette)

        for tool_button in (
            self.attach_btn,
            self.voice_btn,
            self.model_selector_btn,
            self.project_selector_btn,
            self.quick_actions_btn,
        ):
            tool_button.setFixedSize(38, 38)

        precision_btn = QPushButton("Precision: ON")
        precision_btn.setObjectName("PrecisionButton")
        precision_btn.clicked.connect(self.on_toggle_precision)
        self.precision_btn = precision_btn
        self.precision_btn.setProperty("active", "true")
        self.precision_btn.setMinimumWidth(106)

        personalization_btn = QPushButton()
        personalization_btn.setObjectName("PersonalizationStatus")
        personalization_btn.clicked.connect(self.toggle_sidebar)
        self.personalization_btn = personalization_btn
        self.personalization_btn.setMinimumWidth(112)

        access_status_btn = QPushButton()
        access_status_btn.setObjectName("ProjectAccessStatus")
        access_status_btn.clicked.connect(self.toggle_mode_panel)
        access_status_btn.setVisible(False)
        self.access_status_btn = access_status_btn

        project_lookup_btn = QPushButton()
        project_lookup_btn.setObjectName("ProjectLookupStatus")
        project_lookup_btn.clicked.connect(self._toggle_project_lookup_mode)
        project_lookup_btn.setVisible(False)
        self.project_lookup_btn = project_lookup_btn

        send_btn = SendButton("Send")
        send_btn.clicked.connect(self.on_send)
        self.send_btn = send_btn
        self.send_btn.setMinimumWidth(82)

        input_layout.addWidget(self.attach_btn)
        input_layout.addWidget(self.voice_btn)
        input_layout.addWidget(self.model_selector_btn)
        input_layout.addWidget(self.project_selector_btn)
        input_layout.addWidget(self.quick_actions_btn)
        input_layout.addWidget(self.input, stretch=1)
        input_layout.addWidget(precision_btn)
        input_layout.addWidget(personalization_btn)
        input_layout.addWidget(access_status_btn)
        input_layout.addWidget(project_lookup_btn)
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
            #ModeSectionLabel {
                color: rgba(255,255,255,0.72);
                font-size: 12px;
                font-weight: 800;
            }
            #ProjectDetails {
                background: rgba(255,255,255,0.025);
                border-radius: 12px;
                border: 1px solid rgba(178,130,255,0.12);
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
            #ProjectFolderInput {
                background: rgba(0,0,0,0.44);
                border-radius: 10px;
                padding: 9px 10px;
                border: 1px solid rgba(255,255,255,0.08);
                color: rgba(246,242,255,0.86);
                selection-background-color: rgba(178,96,255,0.45);
            }
            #ProjectAddButton,
            #ProjectModelButton {
                background: rgba(54,78,92,0.82);
                color: rgba(244,252,255,0.94);
                border: 1px solid rgba(120,205,235,0.24);
                font-weight: 800;
            }
            #ProjectAddButton {
                border-radius: 16px;
                font-size: 18px;
                font-weight: 900;
            }
            #ProjectModelButton {
                border-radius: 10px;
                padding: 9px 12px;
            }
            #ProjectAddButton:hover,
            #ProjectModelButton:hover {
                background: rgba(70,100,118,0.94);
                border: 1px solid rgba(150,230,255,0.42);
            }
            #AccessOption {
                text-align: left;
                background: rgba(20,18,28,0.78);
                color: rgba(246,242,255,0.88);
                border-radius: 10px;
                padding: 9px 12px;
                border: 1px solid rgba(180,135,255,0.18);
                font-weight: 800;
            }
            #AccessOption:hover {
                background: rgba(54,42,92,0.9);
                border: 1px solid rgba(205,172,255,0.34);
            }
            #AccessOption[active="true"] {
                background: rgba(55,112,92,0.9);
                border: 1px solid rgba(155,235,185,0.45);
            }
            #ModeStatus {
                color: rgba(165,225,195,0.78);
                font-size: 12px;
                padding-top: 4px;
            }
            #ProjectChangesPanel {
                background: rgba(8,10,14,0.96);
                border-radius: 14px;
                border: 1px solid rgba(178,130,255,0.22);
            }
            #ProjectChangesTitle {
                color: #ffffff;
                font-size: 17px;
                font-weight: 900;
            }
            #ChangesIconButton {
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                padding: 0;
                background: rgba(52,40,76,0.9);
                color: rgba(246,242,255,0.92);
                border-radius: 6px;
                border: 1px solid rgba(184,144,255,0.28);
                font-weight: 900;
            }
            #ChangesIconButton:hover {
                background: rgba(112,70,184,0.94);
                border: 1px solid rgba(220,192,255,0.55);
            }
            #ProjectActionButton {
                background: rgba(46,72,94,0.9);
                color: rgba(240,250,255,0.94);
                border-radius: 8px;
                border: 1px solid rgba(126,210,245,0.28);
                padding: 8px 10px;
                font-weight: 800;
            }
            #ProjectActionButton:hover {
                background: rgba(66,106,138,0.96);
                border: 1px solid rgba(160,232,255,0.5);
            }
            #ProjectActionButton:disabled {
                background: rgba(42,44,50,0.62);
                color: rgba(230,230,230,0.42);
                border-color: rgba(255,255,255,0.07);
            }
            #ProjectChangesSummary {
                color: rgba(165,225,195,0.82);
                font-size: 12px;
            }
            #ProjectChangesView {
                background: rgba(0,0,0,0.42);
                border-radius: 10px;
                padding: 10px;
                border: 1px solid rgba(178,130,255,0.16);
                font-family: "Cascadia Mono", "Consolas";
                font-size: 11px;
                color: rgba(238,238,238,0.92);
                selection-background-color: rgba(118,72,220,0.62);
            }
            #ProjectFileTree {
                background: rgba(0,0,0,0.42);
                color: rgba(238,244,252,0.94);
                border-radius: 8px;
                border: 1px solid rgba(126,210,245,0.16);
                padding: 6px;
                selection-background-color: rgba(74,112,205,0.72);
                alternate-background-color: rgba(255,255,255,0.025);
            }
            #ProjectFileTree::item {
                min-height: 24px;
            }
            #ProjectWorkspaceStack {
                background: transparent;
                border: none;
            }
            #ScienceWorkspacePanel {
                background: rgba(5,8,14,0.97);
                border-radius: 14px;
                border: 1px solid rgba(120,180,255,0.24);
            }
            #ScienceWorkspaceTitle {
                color: #ffffff;
                font-size: 17px;
                font-weight: 900;
            }
            #WorkspaceCloseButton,
            #WorkspaceControl,
            #WorkspaceTab {
                background: rgba(22,24,34,0.86);
                color: rgba(246,250,255,0.9);
                border-radius: 8px;
                padding: 8px 10px;
                border: 1px solid rgba(160,200,255,0.18);
                font-weight: 800;
            }
            #WorkspaceTab[active="true"] {
                background: rgba(74,112,205,0.72);
                border: 1px solid rgba(124,216,255,0.45);
            }
            #WorkspaceCloseButton:hover,
            #WorkspaceControl:hover,
            #WorkspaceTab:hover {
                background: rgba(62,74,112,0.92);
                border: 1px solid rgba(168,220,255,0.42);
            }
            #WorkspaceArtifactList {
                min-height: 92px;
                max-height: 132px;
                background: rgba(0,0,0,0.34);
                color: rgba(245,248,255,0.9);
                border-radius: 10px;
                border: 1px solid rgba(160,200,255,0.14);
                padding: 4px;
            }
            #WorkspaceArtifactList::item {
                padding: 7px 8px;
                border-radius: 6px;
            }
            #WorkspaceArtifactList::item:selected {
                background: rgba(96,78,210,0.72);
            }
            #WorkspaceInspector {
                color: rgba(188,226,255,0.86);
                font-size: 12px;
            }
            #WorkspaceNotebook {
                background: rgba(0,0,0,0.34);
                color: rgba(240,244,255,0.9);
                border-radius: 10px;
                border: 1px solid rgba(160,200,255,0.14);
                padding: 10px;
            }
            #VisualizationGenerationCard,
            #InlineVisualization {
                background: rgba(7,11,18,0.96);
                border-radius: 8px;
                border: 1px solid rgba(100,190,240,0.34);
            }
            #VisualizationGenerationCard[error="true"] {
                background: rgba(30,12,16,0.96);
                border-color: rgba(235,95,110,0.58);
            }
            #VisualizationGenerationTitle,
            #InlineVisualizationTitle {
                color: rgba(248,251,255,0.98);
                font-size: 15px;
                font-weight: 900;
            }
            #VisualizationGenerationStage,
            #InlineVisualizationKind {
                color: rgba(112,205,255,0.9);
                font-size: 12px;
                font-weight: 800;
            }
            #VisualizationGenerationDetail,
            #InlineVisualizationInspector {
                color: rgba(212,224,240,0.76);
                font-size: 12px;
            }
            #VisualizationGenerationProgress {
                min-height: 5px;
                max-height: 5px;
                border: none;
                border-radius: 2px;
                background: rgba(255,255,255,0.08);
            }
            #VisualizationGenerationProgress::chunk {
                border-radius: 2px;
                background: rgba(76,190,245,0.9);
            }
            #InlineVisualizationControl {
                background: rgba(25,35,50,0.92);
                color: rgba(240,247,255,0.94);
                border-radius: 6px;
                border: 1px solid rgba(120,190,235,0.24);
                padding: 7px 10px;
                font-weight: 800;
            }
            #InlineVisualizationControl:hover {
                background: rgba(48,80,108,0.96);
                border-color: rgba(132,216,255,0.52);
            }
            #InlineVisualizationEquation {
                background: rgba(255,255,255,0.035);
                color: rgba(235,242,255,0.94);
                border-radius: 6px;
                padding: 8px 10px;
                font-family: "Cambria Math", "Segoe UI";
                font-size: 14px;
            }
            #InlineVisualizationParameter,
            #InlineVisualizationCheck {
                color: rgba(220,231,246,0.86);
                font-size: 12px;
            }
            #InlineVisualizationSelect {
                min-width: 80px;
                background: rgba(21,29,42,0.98);
                color: rgba(240,247,255,0.94);
                border-radius: 6px;
                border: 1px solid rgba(120,190,235,0.25);
                padding: 5px 8px;
            }
            #InlineVisualizationSelect QAbstractItemView {
                background: #111923;
                color: #eef6ff;
                selection-background-color: #315f82;
            }
            #InlineVisualizationSlider::groove:horizontal {
                height: 5px;
                border-radius: 2px;
                background: rgba(255,255,255,0.1);
            }
            #InlineVisualizationSlider::handle:horizontal {
                width: 15px;
                margin: -5px 0;
                border-radius: 7px;
                background: rgba(105,205,250,0.96);
                border: 1px solid rgba(220,248,255,0.82);
            }
            #GraphCanvas,
            #PhysicsCanvas {
                border-radius: 6px;
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
                background: rgba(72,72,80,0.78);
                color: #fff;
                border-radius: 12px;
                padding: 10px 18px;
                border: 1px solid rgba(255,255,255,0.10);
                min-width: 82px;
                font-weight: 700;
            }
            #SendButton[ready="true"] {
                background: rgba(104,72,194,0.92);
                border: 1px solid rgba(215,190,255,0.58);
            }
            #SendButton[ready="true"]:hover {
                background: rgba(122,84,220,0.96);
            }
            #SendButton[personalized="true"] {
                border: 1px solid rgba(202,170,255,0.36);
            }
            #ProjectAccessStatus {
                background: rgba(55,112,92,0.78);
                color: rgba(246,255,250,0.94);
                border-radius: 12px;
                padding: 10px 14px;
                border: 1px solid rgba(155,235,185,0.34);
                font-weight: 800;
            }
            #ProjectAccessStatus:hover {
                background: rgba(70,138,112,0.92);
                border: 1px solid rgba(185,255,212,0.52);
            }
            #ProjectLookupStatus {
                background: rgba(54,78,122,0.78);
                color: rgba(244,250,255,0.94);
                border-radius: 12px;
                padding: 10px 14px;
                border: 1px solid rgba(130,190,255,0.34);
                font-weight: 800;
            }
            #ProjectLookupStatus:hover {
                background: rgba(68,96,150,0.92);
                border: 1px solid rgba(170,215,255,0.52);
            }
            #SendButton:disabled,
            #PersonalizationStatus:disabled,
            #ProjectAccessStatus:disabled,
            #ProjectLookupStatus:disabled,
            #PrecisionButton:disabled,
            #StyleSaveButton:disabled,
            #StyleClearButton:disabled,
            #ProjectAddButton:disabled,
            #ProjectModelButton:disabled,
            #AccessOption:disabled,
            #QueueButton:disabled,
            #InputBox:disabled,
            #StyleInput:disabled,
            #TitleInput:disabled,
            #WakeInput:disabled,
            #ProjectFolderInput:disabled {
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
        self._base_stylesheet = self.styleSheet()
        self.command_palette = CommandPalette(self)
        self.command_palette.action_requested.connect(self._execute_palette_command)
        self.command_shortcut = install_command_shortcut(self, self.command_palette)
        self.attach_shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        self.attach_shortcut.setContext(Qt.WindowShortcut)
        self.attach_shortcut.activated.connect(self.on_attach)
        self.settings_shortcut = QShortcut(QKeySequence("Ctrl+,"), self)
        self.settings_shortcut.setContext(Qt.WindowShortcut)
        self.settings_shortcut.activated.connect(self.open_premium_settings)
        self.notification_toast = NotificationToast(self)
        self.plugin_center = PluginCenter(self.runtime.plugins, self)
        self.plugin_catalog_changed.connect(self._refresh_plugin_commands)
        self.plugin_notification_received.connect(self._show_plugin_notification)
        self.runtime.plugins.bind(
            notification_callback=lambda title, message: self._emit_background(
                "plugin_notification_received", title, message
            ),
            command_callback=lambda: self._emit_background(
                "plugin_catalog_changed"
            ),
        )
        self._refresh_plugin_commands()
        self.diagnostics_dialog = DiagnosticsDialog(
            self.runtime,
            self._diagnostics_context,
            self,
        )
        self.recovery_timer = QTimer(self)
        self.recovery_timer.setInterval(10_000)
        self.recovery_timer.timeout.connect(self._save_recovery_snapshot)
        if self._owns_runtime_lifecycle:
            self.recovery_timer.start()
        self.micro_interactions = MicroInteractionFilter(
            self, enabled=not self.reduced_motion
        )
        for button in self.findChildren(QPushButton):
            button.installEventFilter(self.micro_interactions)
            button.setCursor(Qt.PointingHandCursor)
            if not button.accessibleName():
                button.setAccessibleName(
                    button.toolTip() or button.text().replace("&", "")
                )
        self.smooth_scroll_controllers = [
            SmoothScrollController(
                area,
                enabled=not self.reduced_motion,
                duration=150,
            )
            for area in self.findChildren(QScrollArea)
        ]
        self._apply_theme()
        self._update_style_badge()
        self._refresh_queue_list()
        self._refresh_mode_panel()
        self._refresh_gpu_profile_ui()
        self._set_workspace_view("graph")
        self._refresh_send_button_state()
        self.assistant_hub.set_notes(self.workspace_state.notes)
        self._refresh_workspace_hub()
        self.assistant_hub.tabs.setCurrentIndex(
            min(
                self.assistant_hub.tabs.count() - 1,
                self.workspace_state.active_workspace_tab,
            )
        )
        self.mode_panel.setVisible(self.workspace_state.mode_panel_visible)
        self.sidebar.setVisible(self.workspace_state.sidebar_visible)
        self.assistant_hub.setVisible(self.workspace_state.assistant_hub_visible)
        self.title_bar.hub_btn.setText(
            "Close Tools" if self.assistant_hub.isVisible() else "Tools"
        )
        self._monitor_callback = lambda sample: self._emit_background(
            "premium_metrics_ready", sample
        )
        self.runtime.desktop.system_monitor.subscribe(
            self._monitor_callback,
            interval_seconds=3.0,
        )
        self._refresh_top_bar_status()
        if len(self.workspace_state.geometry) == 4:
            x, y, width, height = self.workspace_state.geometry
            target = QRect(x, y, max(860, width), max(580, height))
            screen = QApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                target.setWidth(min(target.width(), available.width()))
                target.setHeight(min(target.height(), available.height()))
                if not target.intersects(available):
                    target.moveTopLeft(
                        available.topLeft() + QPoint(32, 32)
                    )
                target.moveLeft(
                    max(
                        available.left(),
                        min(target.left(), available.right() - target.width() + 1),
                    )
                )
                target.moveTop(
                    max(
                        available.top(),
                        min(target.top(), available.bottom() - target.height() + 1),
                    )
                )
            self.setGeometry(target)

        if len(self.workspace_state.splitter_sizes) == self.workspace_splitter.count():
            QTimer.singleShot(
                0,
                lambda sizes=list(self.workspace_state.splitter_sizes): self.workspace_splitter.setSizes(
                    sizes
                ),
            )
        elif self.workspace_preset != "balanced":
            QTimer.singleShot(
                0,
                lambda preset=self.workspace_preset: self._apply_workspace_preset(
                    preset,
                    notify=False,
                ),
            )

        restored_history = bool(self.history)
        if restored_history:
            for entry in self.history:
                role = entry.get("role", "")
                content = entry.get("content", "")
                if role == "user":
                    self.append_message(self.user_title, content, is_user=True, force_scroll=False)
                elif role == "assistant":
                    self.append_message(MORICE_NAME, self._address(content), force_scroll=False)
            self._dock_composer_immediate()
        else:
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
                    self.append_message(MORICE_NAME, "Relevant local notes are selected automatically when available.")
            if self.awake:
                self.append_message(MORICE_NAME, f"{MORICE_NAME} is awake, {self.user_title}.")
            else:
                self.append_message(
                    MORICE_NAME,
                    f"{MORICE_NAME} is asleep, {self.user_title}. Type '{self.wake_phrase}' to wake me.",
                )

        QTimer.singleShot(200, self._post_init)
        if self.workspace_state.fullscreen:
            QTimer.singleShot(240, self.showFullScreen)
        elif self.workspace_state.maximized:
            QTimer.singleShot(240, self.title_bar._toggle_maximize)
        if not self.gpu_profile.detected or self.gpu_profile.vram_mb <= 0:
            QTimer.singleShot(650, lambda: self._detect_gpu_profile(auto=True))
        self.wake_signal_timer = QTimer(self)
        self.wake_signal_timer.timeout.connect(self._check_external_wake_signal)
        self.wake_signal_timer.start(1000)

    def _post_init(self):
        hwnd = int(self.winId())
        try:
            _enable_acrylic(hwnd)
        except Exception:
            pass
        model_path = self.model_path or os.getenv("MORICE_GGUF_PATH", "")
        headless = os.getenv("QT_QPA_PLATFORM", "").strip().casefold() in {
            "offscreen",
            "minimal",
        }
        prewarm_disabled = os.getenv(
            "MORICE_DISABLE_MODEL_PREWARM", "0"
        ).strip().casefold() in {"1", "true", "yes"}
        if (
            not headless
            and not prewarm_disabled
            and model_path
            and os.path.isfile(model_path)
        ):
            stable_system = saved_settings_instruction(
                self.user_title,
                self.response_style,
                emoji_preference_instruction(self.emoji_level),
                maturity_preference_instruction(self.maturity_level),
            )

            def prewarm() -> None:
                started = time.perf_counter()
                try:
                    endpoint = prewarm_local_model(model_path)
                except (OSError, RuntimeError, ValueError) as exc:
                    self.runtime.logs.log(
                        "WARNING",
                        "Selected local model could not be prewarmed.",
                        category="model",
                        metadata={"errorType": type(exc).__name__},
                    )
                    return
                prime_started = time.perf_counter()
                try:
                    prime_result = prime_local_chat_prefix(
                        model_path,
                        extra_system=stable_system,
                    )
                except (OSError, RuntimeError, ValueError) as exc:
                    prime_result = {
                        "ready": False,
                        "errorType": type(exc).__name__,
                    }
                self.runtime.logs.log(
                    "INFO",
                    "Selected local model prewarmed.",
                    category="model",
                    metadata={
                        "durationMs": (
                            time.perf_counter() - started
                        )
                        * 1000,
                        "endpoint": endpoint,
                        "prefixPrimeMs": (
                            time.perf_counter() - prime_started
                        )
                        * 1000,
                        "prefixPrime": prime_result,
                    },
                )

            _start_background_task("model-prewarm", prewarm)
        _start_background_task("stt-prewarm", self.runtime.speech_input.prewarm)
        if self.runtime.voice.config.enabled:
            # Keep the first ElevenLabs/Pydantic import on Qt's main thread.
            # Frozen Python 3.14 builds can fault inside python314.dll when the
            # SDK is imported for the first time from ThreadPoolExecutor while
            # Qt and Vosk are also finishing their startup imports.  Provider
            # prewarm creates a reusable HTTP client but performs no request,
            # so the main-thread cost is small and avoids that native race.
            started = time.perf_counter()
            warmed = self.runtime.voice.prewarm()
            self.runtime.logs.log(
                "INFO",
                "Voice provider prewarm completed.",
                category="voice",
                metadata={
                    "warmed": warmed,
                    "durationMs": (time.perf_counter() - started) * 1000,
                    "provider": self.runtime.voice.config.provider,
                },
            )

        def refresh_application_index() -> None:
            try:
                self.runtime.desktop.applications.refresh_discovery(force=True)
            except (OSError, RuntimeError, ValueError):
                return

        if self._session_enabled and os.getenv("QT_QPA_PLATFORM", "").strip().lower() not in {
            "offscreen",
            "minimal",
        }:
            _start_background_task("application-index", refresh_application_index)
        if self.recovery_info.available:
            QTimer.singleShot(350, self._offer_crash_recovery)
        if (
            os.getenv("MORICE_DISABLE_FIRST_RUN", "0") != "1"
            and os.getenv("MORICE_DISABLE_SESSION", "0") != "1"
            and os.getenv("QT_QPA_PLATFORM", "").strip().lower()
            not in {"offscreen", "minimal"}
            and not self.runtime.platform_services.first_run.path.exists()
        ):
            QTimer.singleShot(700, self._offer_first_run)

    def _offer_first_run(self):
        if self.runtime.platform_services.first_run.path.exists():
            return
        report = self.runtime.platform_services.first_run.inspect(self.gpu_profile)
        wizard = FirstRunWizard(
            self.runtime.platform_services.first_run,
            report,
            self,
        )
        wizard.exec()
        self._refresh_workspace_hub()

    def _diagnostics_context(self) -> dict:
        gpu = {
            "name": self.gpu_profile.name,
            "vramMb": self.gpu_profile.vram_mb,
            "detected": self.gpu_profile.detected,
            "source": self.gpu_profile.source,
        }
        model_path = self.model_path or os.getenv("MORICE_GGUF_PATH", "")
        model = {
            "name": self.model_name or os.getenv("MORICE_MODEL", "") or "Not selected",
            "path": model_path,
            "exists": bool(model_path and os.path.isfile(model_path)),
        }
        return {
            "renderer_capabilities": self.visualization_manager.capabilities(),
            "model": model,
            "gpu": gpu,
            "tools": tuple(command.title for command in self.command_palette.commands),
            "task_queue": (
                len(self.message_queue)
                + self.visualization_manager.scheduler.queued_jobs
                + (1 if self.is_busy else 0)
            ),
            "renderer_cache_bytes": self.visualization_manager.resources.used_bytes,
            "project_root": (
                self.project_folder
                if self._project_capable_mode()
                and os.path.isdir(self.project_folder)
                else ""
            ),
        }

    def _run_startup_health_check(self):
        context = self._diagnostics_context()
        return self.runtime.run_health_check(
            renderer_capabilities=context["renderer_capabilities"],
            model_path=self.model_path or os.getenv("MORICE_GGUF_PATH", ""),
            model_name=self.model_name or os.getenv("MORICE_MODEL", ""),
            tools=context["tools"],
            gpu=context["gpu"],
        )

    def _prepare_agent_request(
        self,
        request: str,
        *,
        include_project: bool = False,
    ) -> str:
        renderer_tools = tuple(
            capability.renderer_id
            for capability in self.visualization_manager.capabilities()
            if capability.available
        )
        selected_model = (
            self.model_name
            or (os.path.basename(self.model_path) if self.model_path else "")
        )
        available_models = tuple(
            item
            for item in (
                selected_model,
                os.getenv("MORICE_MODEL", "").strip(),
                "Bundled Qwen2.5 Coder 7B",
            )
            if item
        )
        persistent_context = saved_settings_instruction(
            self.user_title,
            self.response_style,
            emoji_preference_instruction(self.emoji_level),
            maturity_preference_instruction(self.maturity_level),
        )
        try:
            context, platform_run = self.runtime.platform_services.orchestrator.prepare(
                request,
                history=self.history,
                project_root=(
                    self.project_folder
                    if include_project
                    and self._project_capable_mode()
                    and os.path.isdir(self.project_folder)
                    else ""
                ),
                selected_model=selected_model,
                available_models=available_models,
                capabilities=(
                    *renderer_tools,
                    *(definition.tool_id for definition in self.runtime.agent.tools.registry.definitions()),
                ),
                persistent_context=persistent_context,
            )
        except Exception as exc:  # noqa: BLE001
            self.runtime.logs.log(
                "ERROR",
                f"Agent request preparation failed: {exc}",
                category="agent",
            )
            return ""
        self._active_agent_request_id = context.request_id
        self._active_platform_run_id = platform_run.run_id
        return context.request_id

    def _complete_agent_ui(
        self,
        *,
        response_present: bool = True,
        successful: bool | None = None,
    ):
        request_id = self._active_agent_request_id
        if request_id:
            self.runtime.agent.mark_ui_complete(
                request_id,
                response_present=response_present,
            )
        run_id = self._active_platform_run_id
        if run_id:
            try:
                self.runtime.platform_services.orchestrator.finish(
                    run_id,
                    success=response_present if successful is None else successful,
                    summary=(
                        f"Request finished in {self.chat_mode} mode."
                        if response_present
                        else f"Request failed in {self.chat_mode} mode."
                    ),
                )
            except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
                self.runtime.logs.log(
                    "ERROR",
                    f"Platform run completion failed: {exc}",
                    category="platform",
                )
        self._active_agent_request_id = ""
        self._active_platform_run_id = ""

    def _agent_project_prompt_context(self, request_id: str) -> str:
        context = self.runtime.agent.request_context(request_id)
        if context is None or not context.project.root:
            return self._project_snapshot()
        summary = context.project.summary
        lines = [
            "Indexed project context (verified from the selected work folder):",
            f"Root: {context.project.root}",
            f"Languages: {summary.get('languages', {})}",
            f"Frameworks: {summary.get('frameworks', ())}",
            f"Dependencies: {summary.get('dependencies', ())}",
            f"Build systems: {summary.get('build_systems', ())}",
            f"Entry points: {summary.get('entry_points', ())}",
            f"Git: {summary.get('git', {})}",
        ]
        relevant = context.project.relevant_files
        if relevant and any("content" in item for item in relevant):
            lines.append("\nRelevant source files:")
            for item in relevant:
                content = str(item.get("content", ""))
                if not content:
                    continue
                lines.append(
                    f"\n--- {item.get('path', 'unknown')} ---\n{content}"
                )
            return "\n".join(lines)
        return self._project_snapshot()

    def _open_diagnostics(self):
        self.runtime.logs.log(
            "INFO",
            "Diagnostics window opened.",
            category="ui",
        )
        self.diagnostics_dialog.show()
        self.diagnostics_dialog.raise_()
        self.diagnostics_dialog.activateWindow()

    def _save_recovery_snapshot(self):
        if not self._owns_runtime_lifecycle:
            return
        self.runtime.save_recovery_snapshot(
            {
                "history": list(self.history),
                "messageQueue": list(self.message_queue),
                "draft": self.input.text() if hasattr(self, "input") else "",
                "chatMode": self.chat_mode,
                "projectFolder": self.project_folder,
                "projectAccess": self.project_access,
                "projectLookupMode": self.project_lookup_mode,
            }
        )

    def _offer_crash_recovery(self):
        if not self.recovery_info.available:
            return
        if os.getenv("MORICE_DISABLE_RECOVERY", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }:
            return
        crash_message = str(self.recovery_info.crash.get("message", "")).strip()
        detail = self.recovery_info.reason
        if crash_message:
            detail += f"\n\nLast error: {crash_message[:400]}"
        detail += "\n\nRestore the crash-only conversation snapshot?"
        choice = QMessageBox.question(
            self,
            "Recover previous MORICE session",
            detail,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if choice == QMessageBox.Yes:
            self._restore_crash_recovery(self.recovery_info.payload)
        else:
            self.runtime.logs.log(
                "INFO",
                "Crash recovery snapshot was declined.",
                category="recovery",
            )
        self.recovery_info = RecoveryInfo(False)

    def _restore_crash_recovery(self, payload: dict):
        history = payload.get("history", [])
        if not isinstance(history, list):
            history = []
        self._start_new_chat()
        restored: list[dict[str, str]] = []
        for entry in history[-160:]:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role", "")).strip().lower()
            content = str(entry.get("content", "")).replace("\x00", "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            restored.append({"role": role, "content": content[:120_000]})
            if role == "user":
                self.append_message(
                    self.user_title,
                    content,
                    is_user=True,
                    force_scroll=False,
                )
            else:
                self.append_message(
                    MORICE_NAME,
                    self._address(content),
                    force_scroll=False,
                )
        self.history = restored
        queue = payload.get("messageQueue", [])
        self.message_queue = [
            str(item)[:20_000]
            for item in queue
            if str(item).strip()
        ][:80]
        draft = str(payload.get("draft", "")).replace("\x00", "")[:20_000]
        self.input.setText(draft)
        recovered_folder = normalize_project_folder(
            str(payload.get("projectFolder", ""))
        )
        if recovered_folder and os.path.isdir(recovered_folder):
            self.project_folder = recovered_folder
            self.project_access = normalize_project_access(
                str(payload.get("projectAccess", self.project_access))
            )
            self.project_lookup_mode = normalize_project_lookup_mode(
                str(payload.get("projectLookupMode", self.project_lookup_mode))
            )
        self._refresh_queue_list()
        self._refresh_mode_panel()
        self._dock_composer_immediate()
        self._scroll_to_latest()
        self.runtime.logs.log(
            "INFO",
            f"Recovered {len(restored)} conversation entries after an unclean shutdown.",
            category="recovery",
        )
        self._show_notification(
            f"Recovered {len(restored)} conversation entries from the crash snapshot.",
            "success",
            7000,
        )

    def _check_external_wake_signal(self):
        if not os.path.exists(self.wake_signal_path):
            return
        source = ""
        try:
            with open(self.wake_signal_path, "r", encoding="utf-8", errors="replace") as handle:
                source = handle.read().strip()
        except Exception:
            source = ""
        try:
            os.remove(self.wake_signal_path)
        except Exception:
            pass
        self._wake_from_external(source)

    def _wake_from_external(self, source: str = ""):
        request = parse_wake_request(source)
        if request.enter_live_action and self.chat_mode != "voice":
            # A wake trigger is an explicit request to enter Live Action. This
            # changes only MORICE's internal workspace; it never raises or
            # activates the top-level window, so a game keeps keyboard focus.
            self._set_chat_mode("voice")
            self.awake = True
            return
        if self.chat_mode != "voice":
            return
        self.runtime.voice.interrupt("wake-phrase")
        self.runtime.realtime.cancel_active("wake-phrase")
        now = time.monotonic()
        if self.awake:
            if now - self._last_external_wake_notice >= 4.0:
                detail = f" from {request.source}" if request.source else ""
                self.append_message(MORICE_NAME, self._address(f"I heard the wake signal{detail}. I am already awake."))
                self._last_external_wake_notice = now
            if not self.runtime.speech_input.status().listening:
                QTimer.singleShot(180, self._begin_voice_listening)
            return
        self.awake = True
        self.append_message(MORICE_NAME, f"{MORICE_NAME} is awake, {self.user_title}.")
        self._last_external_wake_notice = now
        QTimer.singleShot(180, self._begin_voice_listening)

    def _address(self, reply: str) -> str:
        addressed = enforce_father(reply, self.user_title)
        return apply_emoji_presentation(addressed, self.emoji_level)

    def _input_placeholder(self) -> str:
        if self.chat_mode == "voice":
            return f"{self.user_title}: speak naturally or type here..."
        return f"{self.user_title}: type here..."

    def _experience_profile(self) -> ExperienceProfile:
        return ExperienceProfile.from_value(
            {
                "name": self.settings_profile,
                "theme": self.current_theme,
                "accent": self.accent_color,
                "animation_speed": self.animation_speed,
                "reduced_motion": self.reduced_motion,
                "high_contrast": self.high_contrast,
                "large_text": self.large_text,
                "ui_scale": self.ui_scale,
                "transparency": self.transparency,
                "workspace_preset": self.workspace_preset,
            }
        )

    def open_premium_settings(self) -> None:
        dialog = PremiumSettingsDialog(
            self.experience_profiles,
            self._experience_profile(),
            self,
        )
        dialog.setStyleSheet(
            premium_theme_stylesheet(
                self.current_theme,
                self.accent_color,
                self.font_family,
                high_contrast=self.high_contrast,
                transparency=self.transparency,
            )
        )
        dialog.preferences_applied.connect(self._apply_experience_preferences)
        self.premium_settings_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _apply_experience_preferences(self, values: object) -> None:
        data = dict(values) if isinstance(values, dict) else {}
        profile = ExperienceProfile.from_value(data)
        self.settings_profile = profile.name
        self.current_theme = profile.theme
        self.accent_color = profile.accent
        self.animation_speed = profile.animation_speed
        self.reduced_motion = profile.reduced_motion
        self.high_contrast = profile.high_contrast
        self.large_text = profile.large_text
        self.ui_scale = profile.ui_scale
        self.transparency = profile.transparency
        self.workspace_preset = profile.workspace_preset
        self._motion_enabled = not self.reduced_motion
        self.animation_engine.configure(
            enabled=self._motion_enabled,
            speed=self.animation_speed,
        )
        if hasattr(self, "micro_interactions"):
            self.micro_interactions.set_enabled(self._motion_enabled)
        for controller in getattr(self, "smooth_scroll_controllers", ()):
            controller.set_enabled(self._motion_enabled)
        self._sync_experience_controls()
        self._apply_theme()
        self._apply_workspace_preset(self.workspace_preset, notify=False)
        self._save_appearance_settings()
        self._save_workspace_session()
        self._show_notification(
            f"{profile.name} experience profile applied.",
            "success",
        )

    def _sync_experience_controls(self) -> None:
        controls = (
            getattr(self, "animation_speed_select", None),
            getattr(self, "workspace_preset_select", None),
            getattr(self, "reduced_motion_check", None),
            getattr(self, "high_contrast_check", None),
            getattr(self, "large_text_check", None),
            getattr(self, "ui_scale_slider", None),
            getattr(self, "transparency_slider", None),
        )
        for control in controls:
            if control is not None:
                control.blockSignals(True)
        if hasattr(self, "animation_speed_select"):
            self.animation_speed_select.setCurrentIndex(
                max(0, self.animation_speed_select.findData(self.animation_speed))
            )
            self.workspace_preset_select.setCurrentIndex(
                max(0, self.workspace_preset_select.findData(self.workspace_preset))
            )
            self.reduced_motion_check.setChecked(self.reduced_motion)
            self.high_contrast_check.setChecked(self.high_contrast)
            self.large_text_check.setChecked(self.large_text)
            self.ui_scale_slider.setValue(round(self.ui_scale * 100))
            self.transparency_slider.setValue(self.transparency)
        for control in controls:
            if control is not None:
                control.blockSignals(False)

    def _on_experience_control_changed(self, *_args) -> None:
        values = {
            "name": self.settings_profile,
            "theme": self.current_theme,
            "accent": self.accent_color,
            "animation_speed": self.animation_speed_select.currentData(),
            "reduced_motion": self.reduced_motion_check.isChecked(),
            "high_contrast": self.high_contrast_check.isChecked(),
            "large_text": self.large_text_check.isChecked(),
            "ui_scale": self.ui_scale_slider.value() / 100,
            "transparency": self.transparency_slider.value(),
            "workspace_preset": self.workspace_preset,
        }
        self._apply_experience_preferences(values)

    def _on_workspace_preset_selected(self, _index: int) -> None:
        requested = normalize_workspace_preset(
            self.workspace_preset_select.currentData()
        )
        self._apply_workspace_preset(requested)

    def _apply_workspace_preset(self, name: str, *, notify: bool = True) -> None:
        preset = workspace_layout(name)
        self.workspace_preset = preset.name
        if preset.project_panel and not self._project_capable_mode():
            self._set_chat_mode("project")
        self._animate_panel_visibility(self.mode_panel, preset.mode_panel)
        self._animate_panel_visibility(self.workspace_panel, preset.science_panel)
        show_changes = preset.project_panel and self.changes_available
        if show_changes:
            self.changes_panel_dismissed = False
        self._animate_panel_visibility(self.changes_panel, show_changes)
        self._animate_panel_visibility(
            self.sidebar,
            preset.personalization_panel,
        )
        self._set_assistant_hub_visible(preset.tools_panel)
        self.workspace_splitter.setSizes(list(preset.splitter_sizes))
        self._sync_experience_controls()
        self._save_appearance_settings()
        self._save_workspace_session()
        self._refresh_top_bar_status()
        self.runtime.plugins.publish_event(
            "workspace.changed",
            {"preset": preset.name, "chatMode": self.chat_mode},
        )
        if notify:
            self._show_notification(
                f"{preset.name.title()} workspace layout applied.",
                "success",
            )

    def _refresh_top_bar_status(self, sample: object | None = None) -> None:
        if not hasattr(self, "title_bar"):
            return
        gpu = "--"
        ram = "--"
        vram = "--"
        if sample is not None:
            gpu_value = getattr(sample, "gpu_percent", None)
            ram_value = getattr(sample, "memory_percent", None)
            vram_used = getattr(sample, "vram_used_mb", None)
            vram_total = getattr(sample, "vram_total_mb", None)
            gpu = f"{gpu_value:.0f}%" if gpu_value is not None else "--"
            ram = f"{ram_value:.0f}%" if ram_value is not None else "--"
            if vram_used is not None and vram_total:
                vram = f"{vram_used / 1024:.1f}/{vram_total / 1024:.1f}G"
        model = (
            self.model_name
            or (os.path.basename(self.model_path) if self.model_path else "")
            or "Qwen local"
        )
        if len(model) > 24:
            model = model[:21] + "..."
        tasks = (
            self.runtime.workers.pending_count
            + len(self.message_queue)
            + (1 if self.is_busy else 0)
        )
        workspace = {
            "normal": "Chat",
            "project": "Project",
            "voice": "Live Action",
        }.get(self.chat_mode, "Chat")
        if self.workspace_panel.isVisible():
            workspace = "Live · Lab" if self.chat_mode == "voice" else "Science"
        elif self.assistant_hub.isVisible():
            workspace = "Live · Tools" if self.chat_mode == "voice" else "Tools"
        self.title_bar.set_runtime_status(
            workspace=workspace,
            model=model,
            gpu=gpu,
            ram=ram,
            vram=vram,
            tasks=tasks,
        )

    def _on_premium_metrics(self, sample: object) -> None:
        self._refresh_top_bar_status(sample)

    def _show_voice_status(self) -> None:
        if self.chat_mode != "voice":
            self._show_notification(
                "Live Action is off. Camera, microphone input, and spoken replies are stopped.",
                "info",
                5000,
            )
            return
        wake_state = "awake" if self.awake else "listening for the wake line"
        speech = self.runtime.speech_input.status()
        voice = self.runtime.voice.status()
        self._show_notification(
            (
                f"Wake service is {wake_state}. Microphone: {speech.state.value}. "
                f"Reply voice: {voice.state.value}. Wake line: \"{self.wake_phrase}\"."
            ),
            "info",
            6500,
        )

    def _toggle_voice_input(self) -> None:
        if self.chat_mode == "voice":
            self._set_chat_mode(self._voice_return_mode)
        else:
            self._set_chat_mode("voice")

    def _begin_voice_listening(self) -> None:
        if (
            self.chat_mode != "voice"
            or not self._voice_conversation_active
            or self._live_microphone_paused
            or self._is_closing
        ):
            return
        barge_in = bool(self.is_busy or self.runtime.voice.status().active)
        status = self.runtime.speech_input.status()
        if status.listening:
            return
        if not status.model_configured:
            self._show_notification(status.message, "error", 6500)
            return
        self._barge_in_monitoring = barge_in
        if not barge_in:
            self.runtime.voice.interrupt("user-speaking")
            self.runtime.realtime.cancel_active("user-speaking")
            self.runtime.live_vision.cancel("user-speaking")
        self._speech_base_text = self.input.text().strip()
        self.voice_btn.setProperty("active", "true")
        self.voice_btn.style().unpolish(self.voice_btn)
        self.voice_btn.style().polish(self.voice_btn)
        self.voice_btn.setToolTip("Live Action listening — click to exit")
        self._show_notification("Listening… speak naturally.", "info", 3500)
        if hasattr(self, "live_action_workspace"):
            self.live_action_workspace.set_microphone_state(
                True, "Listening… speak naturally."
            )
        self.runtime.speech_input.listen_once(
            on_partial=lambda text: self._emit_background(
                "speech_partial_ready", text
            ),
            on_complete=lambda result: self._emit_background(
                "speech_transcript_ready", result
            ),
        )

    def _on_speech_partial(self, text: str) -> None:
        if self.chat_mode != "voice" or not self._voice_conversation_active:
            return
        partial = " ".join(str(text or "").split())
        if not partial:
            return
        if self._barge_in_monitoring:
            if self._is_likely_voice_echo(partial):
                return
            self._barge_in_monitoring = False
            self._barge_in_interrupted = True
            self.runtime.voice.interrupt("barge-in")
            self.runtime.realtime.cancel_active("barge-in")
            self.runtime.live_vision.cancel("barge-in")
            self._remove_thinking()
        combined = " ".join(
            part for part in (self._speech_base_text, partial) if part
        )
        self.input.setText(combined)
        if hasattr(self, "live_action_workspace"):
            self.live_action_workspace.set_transcript(combined, partial=True)
        cursor = self.input.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.input.setTextCursor(cursor)

    def _on_speech_transcript(self, payload: object) -> None:
        result = payload if isinstance(payload, TranscriptResult) else None
        barge_in = self._barge_in_monitoring or self._barge_in_interrupted
        self.voice_btn.setProperty(
            "active", "true" if self.chat_mode == "voice" else "false"
        )
        self.voice_btn.style().unpolish(self.voice_btn)
        self.voice_btn.style().polish(self.voice_btn)
        self.voice_btn.setToolTip(
            "Exit Live Action" if self.chat_mode == "voice" else "Enter Live Action"
        )
        if self.chat_mode != "voice" or not self._voice_conversation_active:
            return
        if result is None or not result.text:
            self._barge_in_monitoring = False
            self._barge_in_interrupted = False
            message = result.message if result is not None else "Speech input returned no result."
            if result is None or not result.cancelled:
                self._show_notification(message, "error", 5000)
            if result is not None and result.error_code == "no-speech":
                QTimer.singleShot(450, self._begin_voice_listening)
            if hasattr(self, "live_action_workspace"):
                self.live_action_workspace.set_microphone_state(
                    not self._live_microphone_paused,
                    message,
                )
            return
        if barge_in and self._is_likely_voice_echo(result.text):
            self._barge_in_monitoring = False
            self._barge_in_interrupted = False
            self._speech_base_text = ""
            QTimer.singleShot(180, self._resume_voice_conversation)
            return
        if barge_in and not self._barge_in_interrupted:
            self.runtime.voice.interrupt("barge-in")
            self.runtime.realtime.cancel_active("barge-in")
            self.runtime.live_vision.cancel("barge-in")
        self._barge_in_monitoring = False
        self._barge_in_interrupted = False
        combined = " ".join(
            part for part in (self._speech_base_text, result.text) if part
        )
        self.input.setText(combined)
        if hasattr(self, "live_action_workspace"):
            self.live_action_workspace.set_transcript(combined, partial=False)
        self._pending_transcript = result
        self._speech_base_text = ""
        if self.runtime.speech_input.config.auto_send:
            if barge_in:
                self._remove_thinking()
                self._set_busy(False)
            QTimer.singleShot(80, self.on_send)
        else:
            self._show_notification("Speech transcribed. Review it, then press Send.", "success")

    def _runtime_tts_config(self):
        config = load_tts_config(self.settings)
        if not config.api_configured:
            key = self.runtime.platform_services.vault.get(
                "elevenlabs.api-key", ""
            )
            if key:
                config = replace(config, api_key=key)
        return config

    def _save_voice_settings(self) -> None:
        self.settings["tts_enabled"] = str(
            self.tts_enabled_check.isChecked()
        ).lower()
        self.settings["tts_provider"] = "elevenlabs"
        self.settings["tts_voice_id"] = normalize_tts_voice_id(
            self.tts_voice_id_input.text()
        )
        self.settings["tts_model_id"] = normalize_tts_model_id(
            self.tts_model_id_input.text()
        )
        self.settings["tts_streaming"] = str(
            self.tts_streaming_check.isChecked()
        ).lower()
        self.settings["tts_speech_speed"] = str(
            normalize_tts_speed(self.tts_speed_slider.value() / 100.0)
        )
        self.settings["tts_automatic_fallback"] = str(
            self.tts_fallback_check.isChecked()
        ).lower()
        self.settings["tts_output_device"] = normalize_tts_output_device(
            self.tts_output_device_select.currentData() or ""
        )
        self.settings["tts_output_format"] = normalize_tts_output_format(
            self.settings.get("tts_output_format", "pcm_24000")
        )
        self.settings["stt_enabled"] = str(
            self.stt_enabled_check.isChecked()
        ).lower()
        self.settings["stt_auto_send"] = str(
            self.stt_auto_send_check.isChecked()
        ).lower()
        self.settings["stt_input_device"] = normalize_stt_input_device(
            self.stt_input_device_select.currentData() or ""
        )
        self.settings["stt_max_listen_seconds"] = str(
            normalize_stt_max_listen_seconds(
                self.settings.get("stt_max_listen_seconds", "30")
            )
        )
        save_settings(self.settings)
        voice_status = self.runtime.voice.configure(self._runtime_tts_config())
        raw_device = self.settings["stt_input_device"]
        try:
            input_device: int | str | None = int(raw_device) if raw_device else None
        except ValueError:
            input_device = raw_device or None
        speech_status = self.runtime.speech_input.configure(
            SpeechInputConfig(
                enabled=self.stt_enabled_check.isChecked(),
                input_device=input_device,
                max_listen_seconds=float(
                    self.settings["stt_max_listen_seconds"]
                ),
                auto_send=self.stt_auto_send_check.isChecked(),
            )
        )
        self.elevenlabs_api_status.setText(
            "ElevenLabs API: Configured"
            if voice_status.api_configured
            else "ElevenLabs API: Not configured"
        )
        self._show_notification(
            f"Voice settings saved. Microphone: {speech_status.state.value}.",
            "success",
            5000,
        )

    def _store_elevenlabs_key(self) -> None:
        key = self.elevenlabs_api_key_input.text().strip()
        self.elevenlabs_api_key_input.clear()
        if len(key) < 12 or any(character.isspace() for character in key):
            self._show_notification(
                "Enter a valid new ElevenLabs API key. It is never stored in settings.",
                "error",
                6000,
            )
            return
        try:
            self.runtime.platform_services.vault.set("elevenlabs.api-key", key)
            config = replace(load_tts_config(self.settings), api_key=key)
            self.runtime.voice.configure(config)
        except (OSError, RuntimeError, ValueError):
            self.elevenlabs_api_status.setText("ElevenLabs API: Not configured")
            self._show_notification(
                "Windows secure storage could not save the API key.",
                "error",
                6500,
            )
            return
        finally:
            key = ""
        self.elevenlabs_api_status.setText("ElevenLabs API: Configured")
        self._show_notification(
            "ElevenLabs API key stored with Windows DPAPI.",
            "success",
            5500,
        )

    @staticmethod
    def _voice_trace_callback(realtime_request):
        if realtime_request is None:
            return None

        def on_event(event: str, metadata) -> None:
            details = dict(metadata or {})
            at_ns = int(
                float(details.pop("atMonotonic", time.perf_counter()))
                * 1_000_000_000
            )
            realtime_request.trace.mark_event(
                f"tts_{event}",
                at_ns=at_ns,
                metadata=details,
            )
            if event == "first_audio_generated":
                realtime_request.trace.mark(
                    LatencyStage.FIRST_AUDIO_GENERATED,
                    at_ns=at_ns,
                )
                realtime_request.trace.mark_event(
                    "first_audio_generated",
                    at_ns=at_ns,
                    metadata=details,
                )
            elif event == "playback_started":
                realtime_request.trace.mark(
                    LatencyStage.FIRST_AUDIO_AUDIBLE,
                    at_ns=at_ns,
                )
                realtime_request.trace.mark_event(
                    "first_audio_audible",
                    at_ns=at_ns,
                    metadata=details,
                )

        return on_event

    def _speak_assistant_text(
        self,
        text: str,
        *,
        request_id: str | None = None,
    ):
        if self.chat_mode != "voice" or self._is_closing:
            return None
        spoken = str(text or "").strip()
        if spoken:
            self._last_spoken_text = spoken
            active_request = self.runtime.realtime.active_request
            traced_request = (
                active_request
                if active_request is not None
                and (not request_id or active_request.request_id == request_id)
                else None
            )
            submitted_ns = time.perf_counter_ns()
            if traced_request is not None:
                traced_request.trace.mark(LatencyStage.TTS_CHUNK_RECEIVED, at_ns=submitted_ns)
                traced_request.trace.mark_event("tts_submitted", at_ns=submitted_ns)
            handle = self.runtime.voice.speak(
                spoken,
                request_id=request_id,
                on_event=self._voice_trace_callback(traced_request),
            )

            def wait_for_playback() -> None:
                result = handle.wait()
                if traced_request is not None and result is not None:
                    metrics = result.metrics
                    traced_request.trace.annotate(
                        ttsMetrics={
                            "queueWaitMs": metrics.queue_wait_ms,
                            "providerToFirstAudioMs": metrics.provider_to_first_audio_ms,
                            "playbackStartupMs": metrics.playback_startup_ms,
                            "streamedBeforeTextComplete": (
                                metrics.streamed_before_text_complete
                            ),
                        }
                    )
                    if metrics.request_to_first_audio_ms is not None:
                        first_audio_ns = submitted_ns + int(
                            metrics.request_to_first_audio_ms * 1_000_000
                        )
                        traced_request.trace.mark(
                            LatencyStage.FIRST_AUDIO_GENERATED,
                            at_ns=first_audio_ns,
                        )
                        traced_request.trace.mark_event(
                            "first_audio_generated",
                            at_ns=first_audio_ns,
                        )
                        audible_ns = first_audio_ns + int(
                            (metrics.playback_startup_ms or 0.0) * 1_000_000
                        )
                        traced_request.trace.mark(
                            LatencyStage.FIRST_AUDIO_AUDIBLE,
                            at_ns=audible_ns,
                        )
                        traced_request.trace.mark_event(
                            "first_audio_audible",
                            at_ns=audible_ns,
                        )
                    self.runtime.realtime.finish_speech(traced_request.epoch)
                self._emit_background("speech_playback_finished", result)

            _start_background_task(
                "conversation-turn",
                wait_for_playback,
            )
            QTimer.singleShot(220, self._begin_voice_listening)
            return handle
        return None

    def _on_speech_playback_finished(self, _result: object) -> None:
        if (
            self.chat_mode != "voice"
            or not self._voice_conversation_active
            or self._is_closing
        ):
            return
        QTimer.singleShot(180, self._resume_voice_conversation)

    def _resume_voice_conversation(self) -> None:
        if (
            self.chat_mode != "voice"
            or not self._voice_conversation_active
            or self._is_closing
        ):
            return
        if self.is_busy or self.runtime.voice.status().active:
            QTimer.singleShot(180, self._resume_voice_conversation)
            return
        if not self.runtime.speech_input.status().listening:
            self._begin_voice_listening()

    def _is_likely_voice_echo(self, text: str) -> bool:
        heard = " ".join(str(text or "").casefold().split())
        spoken = " ".join(
            str(self._stream_text or self._last_spoken_text or "").casefold().split()
        )
        if not heard or not spoken:
            return False
        if len(heard) >= 8 and heard in spoken:
            return True
        return difflib.SequenceMatcher(None, heard, spoken).ratio() >= 0.72

    def _toggle_composer_project_mode(self) -> None:
        if self.chat_mode == "voice":
            self._set_chat_mode(self._voice_return_mode)
        else:
            self._set_chat_mode("normal" if self.chat_mode == "project" else "project")

    def _navigate_prompt_history(self, direction: int) -> None:
        if not self.user_messages:
            return
        if self._prompt_history_index < 0:
            self._prompt_history_index = len(self.user_messages)
        self._prompt_history_index = max(
            0,
            min(
                len(self.user_messages),
                self._prompt_history_index + int(direction),
            ),
        )
        if self._prompt_history_index >= len(self.user_messages):
            self.input.clear()
        else:
            self.input.setText(self.user_messages[self._prompt_history_index])
            cursor = self.input.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.input.setTextCursor(cursor)

    def _apply_theme(self):
        global _ACTIVE_UI_FONT_FAMILY, _ACTIVE_UI_THEME
        _ACTIVE_UI_FONT_FAMILY = self.font_family
        _ACTIVE_UI_THEME = self.current_theme
        application = QApplication.instance()
        if application is not None:
            scale = self.ui_scale * (1.12 if self.large_text else 1.0)
            application.setFont(
                QFont(
                    self.font_family,
                    max(8, round(self._base_font_point_size * scale)),
                )
            )
        base = getattr(self, "_base_stylesheet", self.styleSheet())
        self.setStyleSheet(
            base
            + "\n"
            + premium_theme_stylesheet(
                self.current_theme,
                self.accent_color,
                self.font_family,
                high_contrast=self.high_contrast,
                transparency=self.transparency,
            )
        )
        if hasattr(self, "command_palette"):
            self.command_palette.setStyleSheet(
                premium_theme_stylesheet(
                    self.current_theme,
                    self.accent_color,
                    self.font_family,
                    high_contrast=self.high_contrast,
                    transparency=self.transparency,
                )
            )
        if hasattr(self, "diagnostics_dialog"):
            self.diagnostics_dialog.setStyleSheet(
                premium_theme_stylesheet(
                    self.current_theme,
                    self.accent_color,
                    self.font_family,
                    high_contrast=self.high_contrast,
                    transparency=self.transparency,
                )
            )
        if hasattr(self, "premium_settings_dialog"):
            self.premium_settings_dialog.setStyleSheet(
                premium_theme_stylesheet(
                    self.current_theme,
                    self.accent_color,
                    self.font_family,
                    high_contrast=self.high_contrast,
                    transparency=self.transparency,
                )
            )
        if hasattr(self, "composer_stage"):
            self.composer_stage.set_theme(self.current_theme)
        if hasattr(self, "theme_select"):
            self.theme_select.blockSignals(True)
            self.theme_select.setCurrentIndex(
                max(0, self.theme_select.findData(self.current_theme))
            )
            self.theme_select.blockSignals(False)
        if hasattr(self, "title_bar"):
            self.title_bar.set_theme_icon(self.current_theme)
        for rich_view in self.findChildren(RichContentView):
            rich_view.apply_appearance(self.current_theme, self.font_family)

    def toggle_theme(self):
        requested = "light" if self.current_theme != "light" else "dark"
        self._set_theme(requested)

    def _set_theme(self, theme: str, notify: bool = True):
        requested = normalize_theme(theme)
        if requested == self.current_theme:
            self._apply_theme()
            return
        self.current_theme = requested
        self._apply_theme()
        self._record_activity(
            "Theme changed", self.current_theme.title(), category="appearance"
        )
        if notify:
            self._show_notification(
                f"{self.current_theme.title()} theme enabled.", "success"
            )
        self._save_workspace_session()

    def _on_theme_selection_changed(self, _index: int):
        requested = self.theme_select.currentData()
        if requested:
            self._set_theme(str(requested))

    def _save_appearance_settings(self):
        self.settings["emoji_level"] = self.emoji_level
        self.settings["maturity_level"] = self.maturity_level
        self.settings["font_family"] = self.font_family
        self.settings["custom_font_path"] = self.custom_font_path
        self.settings["animation_speed"] = self.animation_speed
        self.settings["reduced_motion"] = str(self.reduced_motion).lower()
        self.settings["high_contrast"] = str(self.high_contrast).lower()
        self.settings["large_text"] = str(self.large_text).lower()
        self.settings["ui_scale"] = str(self.ui_scale)
        self.settings["transparency"] = str(self.transparency)
        self.settings["workspace_preset"] = self.workspace_preset
        self.settings["settings_profile"] = self.settings_profile
        save_settings(self.settings)

    def _on_emoji_selection_changed(self, _index: int):
        self.emoji_level = normalize_emoji_level(self.emoji_select.currentData())
        self._save_appearance_settings()
        self.style_status.setText(
            f"Emoji amount saved: {self.emoji_level.title()}."
        )
        self._record_activity(
            "Emoji preference changed",
            self.emoji_level.title(),
            category="appearance",
        )

    def _on_maturity_selection_changed(self, _index: int):
        self.maturity_level = normalize_maturity_level(
            self.maturity_select.currentData()
        )
        self._save_appearance_settings()
        self.style_status.setText(
            f"Maturity level saved: {self.maturity_level.title()}."
        )
        self._record_activity(
            "Maturity preference changed",
            self.maturity_level.title(),
            category="appearance",
        )

    def _on_font_selection_changed(self, _index: int):
        family = normalize_font_family(self.font_select.currentData())
        if not family:
            return
        self.font_family = family
        self._save_appearance_settings()
        self._apply_theme()
        self.style_status.setText(f"App font changed to {self.font_family}.")
        self._record_activity(
            "Font changed", self.font_family, category="appearance"
        )

    def _choose_custom_font(self):
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Add a MORICE font",
            os.path.dirname(self.custom_font_path)
            if self.custom_font_path
            else os.path.expanduser("~"),
            "Font files (*.ttf *.otf *.ttc)",
        )
        if not path:
            return
        family = register_ui_font_file(path)
        if not family:
            self.style_status.setText(
                "That file is not a valid TTF, OTF, or TTC font."
            )
            self._show_notification("MORICE could not load that font file.", "error")
            return
        self.custom_font_path = normalize_custom_font_path(path)
        self.font_family = family
        index = self.font_select.findData(family)
        if index < 0:
            self.font_select.addItem(family, family)
            index = self.font_select.findData(family)
        self.font_select.blockSignals(True)
        self.font_select.setCurrentIndex(index)
        self.font_select.blockSignals(False)
        self._save_appearance_settings()
        self._apply_theme()
        self.style_status.setText(f"Custom font loaded: {family}.")
        self._show_notification(f"{family} is now active.", "success")
        self._record_activity(
            "Custom font loaded",
            os.path.basename(self.custom_font_path),
            category="appearance",
        )

    def _choose_accent_color(self):
        selected = QColorDialog.getColor(
            QColor(self.accent_color),
            self,
            "Choose MORICE accent color",
        )
        if not selected.isValid():
            return
        self.accent_color = normalize_accent(selected.name())
        self._apply_theme()
        self._record_activity(
            "Accent changed", self.accent_color, category="appearance"
        )
        self._save_workspace_session()

    def open_command_palette(self):
        if hasattr(self.command_palette, "set_recent"):
            self.command_palette.set_recent(self.workspace_state.recent_commands)
        self.command_palette.open_palette()

    def animate_minimize(self):
        if not self._motion_enabled:
            self.showMinimized()
            return

        def minimize():
            self.showMinimized()
            self.setWindowOpacity(1.0)

        self.animation_engine.window_opacity(
            self, 0.0, duration=130, finished=minimize
        )

    def toggle_assistant_hub(self):
        target = not self._panel_target_visibility.get(
            self.assistant_hub, self.assistant_hub.isVisible()
        )
        self._set_assistant_hub_visible(target)

    def _set_assistant_hub_visible(self, visible: bool):
        self._animate_panel_visibility(self.assistant_hub, visible)
        self.title_bar.hub_btn.setText("Close Tools" if visible else "Tools")
        if visible:
            self._refresh_workspace_hub()
        self._refresh_top_bar_status()

    def _refresh_workspace_hub(self):
        if not hasattr(self, "assistant_hub"):
            return
        self.assistant_hub.set_recent(
            self.workspace_state.recent_chats,
            self.workspace_state.recent_files,
        )
        self.assistant_hub.set_activity(self.workspace_state.activity)
        self.assistant_hub.set_tasks(self.message_queue, self.is_busy)
        self.assistant_hub.set_clipboard_history(self.clipboard_history)
        self._refresh_desktop_hub_state()
        self._refresh_downloads()
        workspace = None
        if self.project_folder and os.path.isdir(self.project_folder):
            workspace = next(
                (
                    item
                    for item in self.runtime.desktop.workspaces.list()
                    if os.path.normcase(item.root)
                    == os.path.normcase(os.path.abspath(self.project_folder))
                ),
                None,
            )
        renderer_values = tuple(
            {
                "id": capability.renderer_id,
                "label": capability.label,
                "available": capability.available,
                "interactive": capability.interactive,
                "backend": capability.backend,
                "reason": capability.reason,
            }
            for capability in self.visualization_manager.capabilities()
        )
        platform_state = self.runtime.platform_services.snapshot(
            project_root=(
                self.project_folder
                if self._project_capable_mode()
                and os.path.isdir(self.project_folder)
                else ""
            ),
            workspace=workspace,
            health=self.runtime.health_report,
            plugins=self.runtime.plugins.diagnostics(),
            renderers=renderer_values,
        )
        self.assistant_hub.set_platform_state(platform_state)

    def _refresh_desktop_hub_state(self):
        if not hasattr(self, "assistant_hub"):
            return
        desktop = self.runtime.desktop
        self.assistant_hub.set_desktop_state(
            desktop.snapshot(),
            desktop.notifications.history(limit=100),
            desktop.memory.search("")[:200],
            desktop.automations.list(),
        )

    def _capture_clipboard_entry(self):
        if not self.runtime.desktop.clipboard.enabled:
            return
        clipboard = QApplication.clipboard()
        text = clipboard.text().replace("\x00", "").strip()[:20_000]
        if not text:
            return
        self.runtime.desktop.clipboard.observe(text)
        self.clipboard_history = [
            item.text for item in self.runtime.desktop.clipboard.history()
        ]
        if hasattr(self, "assistant_hub"):
            self.assistant_hub.set_clipboard_history(self.clipboard_history)

    def _refresh_downloads(self):
        if not hasattr(self, "assistant_hub"):
            return
        directory = os.path.join(os.path.expanduser("~"), "Downloads")
        files: list[tuple[float, str]] = []
        try:
            for entry in os.scandir(directory):
                if entry.is_file():
                    try:
                        modified = entry.stat().st_mtime
                    except OSError:
                        modified = 0.0
                    files.append((modified, entry.path))
        except OSError:
            files = []
        files.sort(reverse=True)
        self.assistant_hub.set_downloads(path for _modified, path in files[:80])

    def _record_activity(
        self, title: str, detail: str = "", category: str = "general"
    ):
        self.workspace_state.add_activity(title, detail, category)
        self.runtime.logs.log(
            "INFO",
            title,
            category=category,
            metadata={"detail": detail} if detail else None,
        )
        self._refresh_workspace_hub()

    def _show_notification(
        self,
        message: str,
        severity: str = "info",
        timeout_ms: int = 4200,
        *,
        action_text: str = "",
        action_callback=None,
        progress: int | None = None,
        details: str = "",
    ):
        if not getattr(self, "_handling_plugin_notification", False):
            self.runtime.plugins.publish_event(
                "notification.created",
                {"message": message[:2_000], "severity": severity},
            )
        try:
            self.runtime.desktop.notifications.publish(
                "MORICE",
                message,
                severity=severity,
                category="desktop-ui",
            )
        except (OSError, ValueError, TypeError):
            pass
        if hasattr(self, "assistant_hub"):
            self._refresh_desktop_hub_state()
        if hasattr(self, "notification_toast"):
            self.notification_toast.show_message(
                message,
                severity,
                timeout_ms,
                action_text=action_text,
                action_callback=action_callback,
                progress=progress,
                details=details,
            )

    def _show_plugin_notification(self, message: str, severity: str = "info"):
        self._handling_plugin_notification = True
        try:
            self._show_notification(message, severity)
        finally:
            self._handling_plugin_notification = False

    def _on_workspace_notes_changed(self, notes: str):
        self.workspace_state.notes = notes[:200_000]
        self._save_workspace_session()

    def _save_workspace_session(self):
        if not self._session_enabled:
            return
        geometry = self._normal_geometry if self._custom_maximized else self.geometry()
        self.workspace_state.theme = self.current_theme
        self.workspace_state.accent = self.accent_color
        self.workspace_state.geometry = [
            geometry.x(),
            geometry.y(),
            geometry.width(),
            geometry.height(),
        ]
        self.workspace_state.maximized = bool(
            self.isMaximized() or self._custom_maximized
        )
        self.workspace_state.fullscreen = bool(self.isFullScreen())
        self.workspace_state.splitter_sizes = self.workspace_splitter.sizes()
        self.workspace_state.workspace_preset = self.workspace_preset
        self.workspace_state.active_workspace_tab = (
            self.assistant_hub.tabs.currentIndex()
            if hasattr(self, "assistant_hub")
            else 0
        )
        self.workspace_state.mode_panel_visible = bool(
            hasattr(self, "mode_panel") and self.mode_panel.isVisible()
        )
        self.workspace_state.sidebar_visible = bool(
            hasattr(self, "sidebar") and self.sidebar.isVisible()
        )
        self.workspace_state.assistant_hub_visible = bool(
            hasattr(self, "assistant_hub") and self.assistant_hub.isVisible()
        )
        self.workspace_state.history = []
        self.workspace_state.user_messages = []
        self.workspace_state.notes = (
            self.assistant_hub.notes.toPlainText()[:200_000]
            if hasattr(self, "assistant_hub")
            else self.workspace_state.notes
        )
        try:
            save_workspace_state(self.workspace_state)
            self.runtime.desktop.sessions.save(
                SessionState(
                    session_id=str(os.getpid()),
                    saved_at="",
                    project_ids=(
                        [
                            self.runtime.desktop.workspaces.register(
                                self.project_folder
                            ).project_id
                        ]
                        if self.project_folder
                        and os.path.isdir(self.project_folder)
                        and not self._is_inside_app_folder(self.project_folder)
                        else []
                    ),
                    editors=(
                        [self.current_project_preview_path]
                        if getattr(self, "current_project_preview_path", "")
                        else []
                    ),
                    tabs=[
                        self.assistant_hub.TAB_NAMES[
                            self.assistant_hub.tabs.currentIndex()
                        ]
                    ]
                    if hasattr(self, "assistant_hub")
                    else [],
                    renderers=[
                        str(getattr(self.runtime.profiler, "current_renderer", "") or "")
                    ],
                    pending_tasks=list(self.message_queue),
                )
            )
        except OSError as exc:
            self.runtime.logs.log(
                "ERROR",
                f"Workspace state save failed: {exc}",
                category="storage",
            )
            self._show_notification(f"Session could not be saved: {exc}", "error")

    def _execute_palette_command(self, command: str):
        self.workspace_state.add_recent_command(command)
        self._on_workspace_command(command, None)
        self._save_workspace_session()

    def _refresh_plugin_commands(self):
        if not hasattr(self, "command_palette"):
            return
        dynamic_commands = tuple(
            CommandItem(
                item["key"],
                item["title"],
                item["hint"],
                item["keywords"],
            )
            for item in self.runtime.plugins.command_contributions()
        )
        catalog = self.runtime.plugins.contribution_catalog()
        ui_contributions = tuple(catalog.get("ui", ()))
        dynamic_ui = tuple(
            CommandItem(
                f"plugin-ui:{item['pluginId']}:{item['id']}",
                item["title"],
                f"{item['kind']} from {item['pluginId']}",
                f"plugin extension {item['kind']}",
            )
            for item in ui_contributions
        )
        self.command_palette.set_commands(
            (*DEFAULT_COMMANDS, *dynamic_commands, *dynamic_ui)
        )
        toolbar = [
            item for item in ui_contributions if item.get("kind") == "toolbar-button"
        ]
        if hasattr(self, "title_bar"):
            self.title_bar.set_plugin_buttons(toolbar, self._run_plugin_ui_contribution)
        panels = [
            item
            for item in ui_contributions
            if item.get("kind") in {"sidebar-panel", "workspace-panel"}
        ]
        panels.extend(
            {
                **item,
                "kind": "workspace-panel",
                "commandId": "",
            }
            for item in catalog.get("workspaces", ())
        )
        if hasattr(self, "assistant_hub"):
            self.assistant_hub.set_plugin_panels(
                panels,
                self._run_plugin_ui_contribution,
            )

    def _run_plugin_ui_contribution(self, contribution: dict):
        plugin_id = str(contribution.get("pluginId", ""))
        command_id = str(contribution.get("commandId", ""))
        if command_id:
            try:
                result = self.runtime.plugins.invoke_command(
                    plugin_id, command_id, {}
                )
                self._show_notification(str(result or "Plugin action completed.")[:500], "success")
            except Exception as exc:
                self._show_notification(f"Plugin action failed: {exc}", "error")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(str(contribution.get("title", "Plugin surface")))
        dialog.setMinimumSize(520, 320)
        layout = QVBoxLayout(dialog)
        title = QLabel(str(contribution.get("title", "Plugin surface")))
        title.setObjectName("PluginDetailTitle")
        detail = QLabel(
            f"{contribution.get('kind', 'surface')} provided by {plugin_id}. "
            "The surface is hosted by MORICE so plugin code cannot modify the core UI."
        )
        detail.setWordWrap(True)
        open_center = QPushButton("Open Plugin Center")
        open_center.clicked.connect(self.plugin_center.open_center)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addStretch(1)
        layout.addWidget(open_center, alignment=Qt.AlignLeft)
        dialog.show()
        self._plugin_surface_dialogs = getattr(self, "_plugin_surface_dialogs", [])
        self._plugin_surface_dialogs.append(dialog)

    def _on_workspace_command(self, command: str, argument: object = None):
        if command == "plugins":
            self.plugin_center.open_center()
            return
        if command.startswith("plugin:"):
            _prefix, plugin_id, command_id = command.split(":", 2)
            try:
                result = self.runtime.plugins.invoke_command(
                    plugin_id,
                    command_id,
                    argument if isinstance(argument, dict) else {},
                )
                detail = (
                    json.dumps(result, ensure_ascii=False)
                    if isinstance(result, (dict, list))
                    else str(result or "Plugin command completed.")
                )
                self._show_notification(detail[:500], "success")
            except Exception as exc:
                self._show_notification(f"Plugin command failed: {exc}", "error")
            return
        if command.startswith("plugin-ui:"):
            _prefix, plugin_id, component_id = command.split(":", 2)
            contribution = next(
                (
                    item
                    for item in self.runtime.plugins.contribution_catalog().get("ui", ())
                    if item.get("pluginId") == plugin_id
                    and item.get("id") == component_id
                ),
                None,
            )
            if contribution:
                self._run_plugin_ui_contribution(contribution)
            return
        if command == "settings":
            self.open_premium_settings()
            return
        if command.startswith("layout-"):
            self._apply_workspace_preset(command.removeprefix("layout-"))
            return
        if command == "workspace":
            self.toggle_assistant_hub()
            return
        if command == "new-chat":
            self._start_new_chat()
            return
        if command == "project":
            self._set_chat_mode("project")
            return
        if command == "normal-chat":
            self._set_chat_mode("normal")
            return
        if command == "voice-mode":
            self._set_chat_mode("voice")
            return
        if command == "open-file":
            self._choose_workspace_file()
            return
        if command == "open-media":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open local media",
                os.path.expanduser("~"),
                "Media (*.mp3 *.wav *.flac *.m4a *.mp4 *.webm *.mkv *.mov *.avi);;All files (*.*)",
            )
            if path:
                succeeded, detail = self.assistant_hub.open_media(path)
                if succeeded:
                    self.workspace_state.add_recent_file(path)
                    self._record_activity("Media opened", path, "media")
                self._show_notification(
                    detail, "success" if succeeded else "error"
                )
            return
        if command == "find-files-from-hub":
            query = self.assistant_hub.file_query.text().strip()
            if query:
                self._start_file_search(query)
            return
        if command == "find-files":
            query = str(argument or "").strip()
            if query:
                self._start_file_search(query)
            else:
                self._set_assistant_hub_visible(True)
                self.assistant_hub.show_tab("Files")
                self.assistant_hub.file_query.setFocus()
            return
        if command == "search-everywhere":
            query = str(argument or "").strip()
            if query:
                self._start_search_everywhere(query)
            else:
                self._set_assistant_hub_visible(True)
                self.assistant_hub.search.setFocus()
            return
        if command == "clipboard-monitor":
            if self.runtime.desktop.clipboard.enabled:
                self.runtime.desktop.clipboard.disable(clear=False)
                self.assistant_hub.set_clipboard_status(False)
                self._show_notification(
                    "Clipboard monitoring is off. Session history remains until MORICE closes."
                )
                return
            choice = QMessageBox.question(
                self,
                "Enable clipboard monitoring",
                "Allow MORICE to observe text copied during this session? "
                "Clipboard history stays in memory and is not persisted.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if choice == QMessageBox.Yes:
                grant = self.runtime.desktop.clipboard.request_monitoring()
                self.runtime.desktop.clipboard.enable(grant.token)
                self.assistant_hub.set_clipboard_status(True)
                self._capture_clipboard_entry()
                self._show_notification(
                    "Clipboard monitoring is enabled for this session.", "success"
                )
            return
        if command == "desktop-refresh":
            self._refresh_desktop_hub_state()
            self.assistant_hub.show_tab("Desktop")
            return
        if command == "notification-dismiss":
            notification_id = str(argument or "")
            if notification_id and self.runtime.desktop.notifications.dismiss(
                notification_id
            ):
                self._refresh_desktop_hub_state()
            return
        if command == "memory-toggle":
            memory = self.runtime.desktop.memory
            memory.set_enabled(not memory.enabled)
            self._refresh_desktop_hub_state()
            self._show_notification(
                f"Structured memory is now {'enabled' if memory.enabled else 'disabled'}."
            )
            return
        if command == "memory-export":
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export MORICE memory",
                os.path.join(os.path.expanduser("~"), "morice-memory.json"),
                "JSON (*.json)",
            )
            if path:
                try:
                    target = self.runtime.desktop.memory.export(path)
                    self._show_notification(
                        f"Memory exported to {target}.", "success", 7000
                    )
                except OSError as exc:
                    self._show_notification(f"Memory export failed: {exc}", "error")
            return
        if command == "memory-import":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Import MORICE memory",
                os.path.expanduser("~"),
                "JSON (*.json)",
            )
            if path:
                try:
                    count = self.runtime.desktop.memory.import_file(path)
                    self._refresh_desktop_hub_state()
                    self._show_notification(
                        f"Imported {count} memory record(s).", "success"
                    )
                except (OSError, RuntimeError, ValueError) as exc:
                    self._show_notification(f"Memory import failed: {exc}", "error")
            return
        if command in {
            "memory-pin-selected",
            "memory-archive-selected",
            "memory-delete-selected",
        }:
            memory_id = self.assistant_hub.selected_memory_id()
            if not memory_id:
                self._show_notification("Select a memory record first.", "warning")
                return
            if command == "memory-pin-selected":
                self.runtime.desktop.memory.update(memory_id, pinned=True)
            elif command == "memory-archive-selected":
                self.runtime.desktop.memory.update(memory_id, archived=True)
            else:
                choice = QMessageBox.question(
                    self,
                    "Delete memory",
                    "Permanently delete the selected memory record?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if choice == QMessageBox.Yes:
                    self.runtime.desktop.memory.delete(memory_id)
            self._refresh_desktop_hub_state()
            return
        if command in {
            "automation-enable-selected",
            "automation-disable-selected",
        }:
            workflow_id = self.assistant_hub.selected_automation_id()
            if not workflow_id:
                self._show_notification("Select an automation first.", "warning")
                return
            try:
                if command == "automation-enable-selected":
                    grant = self.runtime.desktop.automations.request_enable(
                        workflow_id
                    )
                    self.runtime.desktop.automations.enable(
                        workflow_id, grant.token
                    )
                else:
                    self.runtime.desktop.automations.disable(workflow_id)
                self._refresh_desktop_hub_state()
            except (KeyError, PermissionError, ValueError) as exc:
                self._show_notification(f"Automation update failed: {exc}", "error")
            return
        if command == "diagnostics":
            self._open_diagnostics()
            return
        if command in {"platform", "platform-refresh"}:
            self._set_assistant_hub_visible(True)
            self._refresh_workspace_hub()
            self.assistant_hub.show_tab("Platform")
            return
        if command == "platform-export":
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export MORICE platform bundle",
                os.path.join(
                    os.path.expanduser("~"),
                    f"morice-platform-{time.strftime('%Y%m%d')}.zip",
                ),
                "MORICE bundle (*.zip)",
            )
            if path:
                try:
                    target = self.runtime.platform_services.exports.export_bundle(
                        path,
                        {
                            "platform": self.runtime.directory / "platform",
                            "desktop": self.runtime.directory / "desktop",
                            "logs": self.runtime.directory / "logs",
                            **(
                                {"project": self.project_folder}
                                if self.project_folder
                                and os.path.isdir(self.project_folder)
                                else {}
                            ),
                        },
                        metadata={
                            "projectRoot": self.project_folder,
                            "applicationVersion": __version__,
                        },
                    )
                    self._show_notification(
                        f"Platform bundle exported to {target}.",
                        "success",
                        7000,
                    )
                except (OSError, RuntimeError, ValueError) as exc:
                    self._show_notification(
                        f"Platform export failed: {exc}",
                        "error",
                    )
            return
        if command == "platform-first-run":
            report = self.runtime.platform_services.first_run.inspect(
                self.gpu_profile
            )
            gpu = dict(report.get("gpu", {}))
            fit = next(
                (
                    item.get("modelClass", "")
                    for item in report.get("recommendedModels", ())
                    if item.get("fit")
                ),
                "CPU-friendly model",
            )
            QMessageBox.information(
                self,
                "MORICE hardware profile",
                (
                    f"GPU: {gpu.get('name') or 'Not detected'}\n"
                    f"VRAM: {gpu.get('vramMb', 0) / 1024:.1f} GB\n"
                    f"System memory: {report.get('memoryMb', 0) / 1024:.1f} GB\n"
                    f"Recommended local class: {fit}\n\n"
                    "You can change the model at any time from the MORICE panel."
                ),
            )
            return
        if command == "platform-release-check":
            renderers = tuple(
                {
                    "id": item.renderer_id,
                    "available": item.available,
                    "reason": item.reason,
                }
                for item in self.visualization_manager.capabilities()
            )
            report = self.runtime.platform_services.release.check(
                health=self.runtime.health_report,
                plugins=self.runtime.plugins.diagnostics(),
                renderers=renderers,
            )
            failures = tuple(report.get("criticalFailures", ()))
            self._refresh_workspace_hub()
            self.assistant_hub.show_tab("Platform")
            self._show_notification(
                (
                    "Release readiness checks passed."
                    if report.get("ready")
                    else "Release is not ready yet: "
                    + (
                        ", ".join(str(item) for item in failures)
                        if failures
                        else "record a passing automated test run"
                    )
                ),
                "success" if report.get("ready") else "warning",
                7000,
            )
            return
        if command == "system":
            self._refresh_system_snapshot()
            return
        if command == "screenshot":
            self._capture_desktop_screenshot()
            return
        if command == "theme":
            self.toggle_theme()
            return
        if command == "accent":
            self._choose_accent_color()
            return
        if command in {"notes", "browser", "media", "desktop"}:
            self._set_assistant_hub_visible(True)
            self.assistant_hub.show_tab(command.title())
            return
        if command == "new-window":
            self._open_new_window()
            return
        if command == "clear-activity":
            self.workspace_state.activity.clear()
            self._refresh_workspace_hub()
            self._save_workspace_session()
            return
        if command == "resume-chat":
            self.input.setText(str(argument or ""))
            self.input.setFocus()
            return
        if command == "preview-file":
            if isinstance(argument, dict):
                self._preview_workspace_file(str(argument.get("path", "")))
            else:
                self._preview_workspace_file(str(argument or ""))
            return
        if command == "open-project" and isinstance(argument, dict):
            root = normalize_project_folder(str(argument.get("root", "")))
            if root and os.path.isdir(root) and not self._is_inside_app_folder(root):
                self.project_folder = root
                self.project_folder_input.setText(root)
                self.project_folder_input.setToolTip(root)
                self._set_chat_mode("project")
                self._save_project_settings()
                self._refresh_project_tree()
                self._show_notification(
                    f"Project workspace opened: {Path(root).name}", "success"
                )
            return
        if command == "inspect-memory" and isinstance(argument, dict):
            memory_id = str(argument.get("memoryId", ""))
            record = next(
                (
                    item
                    for item in self.runtime.desktop.memory.search("")
                    if item.memory_id == memory_id
                ),
                None,
            )
            if record is not None:
                self.append_message(
                    MORICE_NAME,
                    self._address(
                        f"Memory ({record.scope}):\n\n{record.content}"
                    ),
                )
            return
        if command == "open-path":
            path = str(argument or "")
            if path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            return
        if command == "open-downloads":
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
            QDesktopServices.openUrl(QUrl.fromLocalFile(downloads))
            return
        if command == "refresh-downloads":
            self._refresh_downloads()
            self.assistant_hub.show_tab("Files")
            if self.assistant_hub.files_subtabs is not None:
                self.assistant_hub.files_subtabs.setCurrentIndex(1)
            return
        if command == "restore-clipboard":
            text = str(argument or "")
            if text:
                QApplication.clipboard().setText(text)
                self._show_notification("Copied back to the clipboard.", "success")
            return
        if command in {"browser-go", "browser-navigate"}:
            address = (
                self.assistant_hub.browser_address.text().strip()
                if command == "browser-go"
                else str(argument or "").strip()
            )
            self.assistant_hub.navigate_browser(address)
            self._record_activity("Website opened", address, "browser")
            return
        if command == "media":
            self._execute_desktop_action_async(
                DesktopAction("media", argument=str(argument or "play-pause"))
            )

    def _start_new_chat(self):
        if self.is_busy:
            self._show_notification(
                "Wait for the current response before clearing this chat.", "error"
            )
            return
        for index in reversed(range(self.chat_list_layout.count())):
            item = self.chat_list_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None and widget not in {
                self._bottom_spacer,
                self.chat_archive_notice,
            }:
                self.chat_list_layout.removeWidget(widget)
                widget.deleteLater()
        self._message_rows.clear()
        self._archived_messages.clear()
        self._refresh_archive_notice()
        self.history.clear()
        self.user_messages.clear()
        self.first_user_message = ""
        self.science_artifacts.clear()
        self._refresh_workspace_artifact_list()
        self.append_message(
            MORICE_NAME,
            f"New chat ready, {self.user_title}.",
            force_scroll=True,
        )
        self._record_activity("New chat", category="chat")
        self.runtime.plugins.publish_event("chat.started", {"newChat": True})
        self._save_workspace_session()

    def _choose_workspace_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open a file in MORICE",
            os.path.expanduser("~"),
            "All files (*.*)",
        )
        if path:
            self._preview_workspace_file(path)

    def _preview_workspace_file(self, path: str):
        if not path:
            return
        self._set_assistant_hub_visible(True)
        try:
            descriptor = self.runtime.desktop.files.preview(path)
            self.assistant_hub.show_tab("Files")
            succeeded, detail = self.assistant_hub.file_preview.show_descriptor(
                descriptor
            )
        except (OSError, ValueError, TypeError) as exc:
            succeeded, detail = False, str(exc)
        if os.path.isfile(path):
            self.workspace_state.add_recent_file(path)
            try:
                self.runtime.desktop.files.record_access(path)
            except OSError:
                pass
            self._record_activity(
                "File previewed", os.path.abspath(path), category="files"
            )
            self._save_workspace_session()
        self._show_notification(detail, "success" if succeeded else "error")

    def _file_search_roots(self) -> list[str]:
        home = os.path.expanduser("~")
        roots = [
            os.path.join(home, "Desktop"),
            os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"),
        ]
        if self.project_folder:
            roots.insert(0, self.project_folder)
        return [root for root in roots if os.path.isdir(root)]

    def _start_file_search(self, query: str):
        self._set_assistant_hub_visible(True)
        self.assistant_hub.show_tab("Files")
        self.assistant_hub.file_results.clear()
        self.assistant_hub.file_results.addItem("Searching...")
        roots = self._file_search_roots()

        def worker():
            try:
                result = [
                    item.path
                    for item in self.runtime.desktop.files.search(
                        query,
                        roots,
                        limit=80,
                    )
                ]
            except Exception:  # noqa: BLE001
                result = []
            self._emit_background(
                "file_search_ready", {"query": query, "paths": result}
            )

        _start_background_task("file-search", worker)

    def _on_file_search_ready(self, result: object):
        data = result if isinstance(result, dict) else {}
        query = str(data.get("query", ""))
        if data.get("scope") == "everywhere":
            values = list(data.get("results", []))
            self.assistant_hub.set_search_results(values)
            self._record_activity(
                "Search everywhere",
                f"{query}: {len(values)} result(s)",
                category="search",
            )
            self._show_notification(
                f"Found {len(values)} result(s) across MORICE."
            )
            return
        paths = list(data.get("paths", []))
        self.assistant_hub.set_file_results(paths)
        self._record_activity(
            "File search",
            f"{query}: {len(paths)} result(s)",
            category="files",
        )
        self._show_notification(f"Found {len(paths)} file(s) for {query}.")

    def _register_desktop_search_providers(self):
        def commands(query: str):
            terms = _tokenize_for_ui_search(query)
            for command in self.command_palette.commands:
                if terms and not all(
                    term in command.searchable_text for term in terms
                ):
                    continue
                yield SearchEverywhereResult(
                    "commands",
                    command.title,
                    command.hint,
                    command.key,
                    25.0,
                )

        def logs(query: str):
            for record in self.runtime.logs.search(query)[-20:]:
                yield SearchEverywhereResult(
                    "logs",
                    record.message[:140],
                    f"{record.level} | {record.category} | {record.timestamp}",
                    "diagnostics",
                    12.0,
                )

        def tools(query: str):
            needle = query.casefold()
            for tool in self.runtime.agent.tools.registry.definitions():
                label = str(tool.display_name or tool.tool_id)
                detail = str(tool.description)
                if needle not in f"{label} {detail}".casefold():
                    continue
                yield SearchEverywhereResult(
                    "tools", label, detail, "diagnostics", 15.0
                )

        self.runtime.desktop.search.register("commands", commands)
        self.runtime.desktop.search.register("logs", logs)
        self.runtime.desktop.search.register("tools", tools)

    def _start_search_everywhere(self, query: str):
        self._set_assistant_hub_visible(True)
        self.assistant_hub.show_tab("Files")
        self.assistant_hub.file_results.clear()
        self.assistant_hub.file_results.addItem("Searching MORICE and local files...")
        roots = self._file_search_roots()

        def worker():
            try:
                results = self.runtime.desktop.search.search(
                    query, roots=roots, limit=80
                )
            except Exception:  # noqa: BLE001
                results = []
            self._emit_background(
                "file_search_ready",
                {"scope": "everywhere", "query": query, "results": results}
            )

        _start_background_task("search-everywhere", worker)

    def _refresh_system_snapshot(self):
        self._set_assistant_hub_visible(True)
        self.assistant_hub.show_tab("System")
        self.assistant_hub.system_summary.setText("Reading system information...")

        def worker():
            try:
                snapshot = collect_system_snapshot()
            except Exception as exc:  # noqa: BLE001
                snapshot = exc
            self._emit_background("system_snapshot_ready", snapshot)

        _start_background_task("system-snapshot", worker)

    def _on_system_snapshot_ready(self, snapshot: object):
        if isinstance(snapshot, Exception):
            self.assistant_hub.system_summary.setText(str(snapshot))
            self._show_notification(
                f"System status failed: {snapshot}", "error"
            )
            return
        gpu = ""
        if getattr(self, "gpu_profile", None) is not None:
            gpu = (
                f"{self.gpu_profile.name} "
                f"({self.gpu_profile.vram_mb / 1024:.1f} GB VRAM)"
                if self.gpu_profile.detected and self.gpu_profile.vram_mb > 0
                else self.gpu_profile.name
            )
        self.assistant_hub.set_system_snapshot(snapshot, gpu)
        self._record_activity("System status refreshed", category="system")

    def _capture_desktop_screenshot(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            self._show_notification("No display is available to capture.", "error")
            return
        target_dir = os.path.join(
            os.path.expanduser("~"), "Pictures", "MORICE Screenshots"
        )
        os.makedirs(target_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = os.path.join(target_dir, f"MORICE-{stamp}.png")
        pixmap = screen.grabWindow(0)
        if pixmap.isNull() or not pixmap.save(target, "PNG"):
            self._show_notification("The screenshot could not be saved.", "error")
            return
        self.workspace_state.add_recent_file(target)
        if self._project_capable_mode() and self.project_folder:
            try:
                project = self.runtime.desktop.workspaces.register(
                    self.project_folder
                )
                self.runtime.desktop.workspaces.update(
                    project.project_id,
                    screenshots=[*project.screenshots, target],
                )
            except (OSError, ValueError):
                pass
        self._record_activity("Screenshot captured", target, "system")
        self.runtime.plugins.publish_event(
            "screenshot.captured",
            {"path": target, "projectFolder": self.project_folder},
        )
        self._refresh_workspace_hub()
        self._save_workspace_session()
        self._show_notification(f"Screenshot saved to {target}", "success", 7000)

    def _open_new_window(self):
        window = MoriceWindow(self.runtime)
        window.setAttribute(Qt.WA_DeleteOnClose, True)
        window.destroyed.connect(
            lambda: self._child_windows.remove(window)
            if window in self._child_windows
            else None
        )
        self._child_windows.append(window)
        window.show()
        self._record_activity("New MORICE window opened", category="workspace")

    def _execute_desktop_action_async(self, action: DesktopAction):
        def worker():
            try:
                message = execute_desktop_action(action)
                self._emit_background("desktop_action_ready", message, True)
            except Exception as exc:  # noqa: BLE001
                self._emit_background("desktop_action_ready", str(exc), False)

        _start_background_task("desktop-action", worker)

    def _on_desktop_action_ready(self, message: str, succeeded: bool):
        self.append_message(MORICE_NAME, self._address(message), force_scroll=True)
        self._record_activity(
            "Desktop action completed" if succeeded else "Desktop action failed",
            message,
            category="desktop",
        )
        self._show_notification(message, "success" if succeeded else "error")

    def _handle_desktop_command(self, user_input: str) -> bool:
        action = parse_desktop_command(user_input)
        if action is None:
            return False
        if action.kind == "unknown":
            self.animation_engine.shake(self.input_frame)
            self.append_message(
                MORICE_NAME,
                self._address(
                    "Unknown command. Try /system, /find, /open, /site, "
                    "/diagnostics, /screenshot, /workspace, /theme, /new-window, "
                    "or a media command."
                ),
            )
            return True
        if action.kind == "system":
            self._refresh_system_snapshot()
            self.append_message(
                MORICE_NAME,
                self._address("System status is opening in Tools."),
            )
            return True
        if action.kind == "diagnostics":
            self._open_diagnostics()
            self.append_message(
                MORICE_NAME,
                self._address(
                    "Diagnostics is open with health checks, structured logs, "
                    "worker state, renderers, and live performance."
                ),
            )
            return True
        if action.kind == "find":
            self._start_file_search(action.argument)
            self.append_message(
                MORICE_NAME,
                self._address(f"Searching local folders for {action.argument}."),
            )
            return True
        if action.kind == "workspace":
            self.toggle_assistant_hub()
            return True
        if action.kind == "theme":
            requested = normalize_theme(action.argument) if action.argument else ""
            if requested and requested != self.current_theme:
                self.current_theme = requested
                self._apply_theme()
                self._save_workspace_session()
            elif not action.argument:
                self.toggle_theme()
            self.append_message(
                MORICE_NAME,
                self._address(f"{self.current_theme.title()} theme is active."),
            )
            return True
        if action.kind == "new-window":
            self._open_new_window()
            return True
        if action.kind == "screenshot":
            self._capture_desktop_screenshot()
            return True
        if action.kind == "close-app":
            choice = QMessageBox.question(
                self,
                "Confirm application close",
                f"Close {action.target}? Unsaved work in that application may be lost.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if choice != QMessageBox.Yes:
                self.append_message(MORICE_NAME, self._address("Close cancelled."))
                return True

            def close_worker():
                try:
                    message = close_application(action.target)
                    self._emit_background("desktop_action_ready", message, True)
                except Exception as exc:  # noqa: BLE001
                    self._emit_background("desktop_action_ready", str(exc), False)

            _start_background_task("close-application", close_worker)
            return True
        self._execute_desktop_action_async(action)
        return True

    def _handle_natural_pc_control(self, user_input: str) -> bool:
        decision = self.runtime.pc_router.route(user_input)
        action = decision.action
        realtime_request = self.runtime.realtime.active_request
        if realtime_request is not None and realtime_request.text == user_input.strip():
            realtime_request.trace.mark_event(
                "fast_route_completed",
                metadata={
                    "routeType": decision.route_type,
                    "modelInvocations": decision.model_invocations,
                    "toolId": action.tool_id if action is not None else "",
                    "durationMs": decision.duration_ms,
                },
            )
        route_metadata = {
            "route": decision.route_type,
            "tool": action.tool_id if action is not None else "",
            "durationMs": decision.duration_ms,
            "modelInvocations": decision.model_invocations,
            "escalateToModel": decision.escalate_to_model,
            "reason": decision.reason,
        }
        _start_background_task(
            "routing-log",
            lambda: self.runtime.logs.log(
                "INFO",
                "PC route selected.",
                category="routing",
                metadata=route_metadata,
            ),
        )
        if action is None:
            if not decision.escalate_to_model and decision.clarification:
                self._append_direct_reply(user_input, decision.clarification)
                return True
            return False
        authorization = self.runtime.pc_permissions.authorize(action)
        confirmation_token = ""
        if not authorization.allowed and authorization.confirmation_required:
            choice = QMessageBox.question(
                self,
                "Confirm PC action",
                (
                    f"MORICE wants to perform: {action.tool_id}\n"
                    f"Target: {action.target or 'current context'}\n\n"
                    "Approve this exact action once?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if choice != QMessageBox.Yes:
                self._append_direct_reply(
                    user_input,
                    "PC action cancelled. Nothing was changed.",
                )
                return True
            grant = self.runtime.pc_permissions.request_confirmation(
                action,
                description=f"Approve {action.tool_id} for {action.target}",
            )
            confirmation_token = grant.token
        elif not authorization.allowed:
            self._append_direct_reply(user_input, authorization.reason)
            return True

        self._set_busy(True)
        work_state = (
            "Opening and verifying."
            if action.tool_id == "application.open"
            else "Checking system state."
            if action.tool_id == "system.status"
            else "Running and verifying."
        )
        self._show_thinking(work_state)

        def worker():
            started_ns = time.perf_counter_ns()
            if realtime_request is not None:
                realtime_request.trace.mark_event(
                    "tool_execution_started",
                    at_ns=started_ns,
                    metadata={"toolId": action.tool_id},
                )
            result = self.runtime.pc_control.execute(
                action,
                confirmation_token=confirmation_token,
            )
            if realtime_request is not None:
                realtime_request.trace.mark_event(
                    "tool_execution_finished",
                    metadata={
                        "toolId": action.tool_id,
                        "success": result.success,
                        "verified": result.verified,
                        "timingsMs": dict(result.timings_ms),
                    },
                )
            self._emit_background("pc_control_ready", user_input, result)

        _start_background_task("pc-control", worker)
        return True

    def _on_pc_control_ready(self, user_input: str, result: object) -> None:
        message = str(getattr(result, "message", "PC action returned no result."))
        output = dict(getattr(result, "output", {}) or {})
        tool_id = str(getattr(result, "tool_id", ""))
        succeeded = bool(getattr(result, "success", False))
        verified = bool(getattr(result, "verified", False))
        compact_ack = False
        if succeeded and verified:
            short_ack = {
                "application.open": "Opened.",
                "application.close": "Closed.",
                "application.focus": "Focused.",
                "application.minimize": "Minimized.",
                "application.maximize": "Maximized.",
                "media.pause": "Paused.",
                "media.resume": "Playing.",
                "media.next": "Skipped.",
                "media.previous": "Previous track.",
                "media.restart": "Restarted.",
                "media.set_volume": "Done.",
                "media.adjust_volume": "Done.",
            }.get(tool_id)
            if short_ack:
                message = short_ack
                compact_ack = True
            elif tool_id == "system.status":
                available = output.get("memoryAvailableGb")
                gpu = output.get("gpu_percent", output.get("gpuPercent"))
                if available is not None:
                    message = f"{float(available):.1f} GB RAM free."
                    compact_ack = True
                elif gpu is not None:
                    message = f"GPU usage is {float(gpu):.0f}%."
                    compact_ack = True
            elif tool_id == "screenshot.capture":
                path = str(output.get("path", "") or "")
                message = f"Captured: {path}" if path else "Captured."
                compact_ack = True
        if output.get("results") and not compact_ack:
            rows = []
            for item in list(output["results"])[:8]:
                if not isinstance(item, dict):
                    continue
                label = str(
                    item.get("title") or item.get("name") or item.get("path") or "Result"
                )
                target = str(item.get("url") or item.get("path") or "")
                rows.append(f"- {label}" + (f": {target}" if target else ""))
            if rows:
                message += "\n\n" + "\n".join(rows)
        elif output and (not compact_ack or tool_id == "system.status"):
            useful = []
            for key, value in list(output.items())[:8]:
                if isinstance(value, (str, int, float, bool)):
                    useful.append(f"- {key}: {value}")
            if useful:
                message += "\n\n" + "\n".join(useful)
        self._append_direct_reply(user_input, message)
        # PC actions are asynchronous, so their completion must close the
        # processing state explicitly.  Without this cleanup the verified
        # tool result was visible while the stale bubble later claimed that
        # Qwen was still generating, even though the fast route invoked no
        # model at all.
        self._remove_thinking()
        self._set_busy(False)
        QTimer.singleShot(120, self._send_queued_message_if_ready)
        self._record_activity(
            "PC action completed" if succeeded else "PC action failed",
            message[:240],
            category="desktop",
        )

    def _track_animation(self, animation):
        """Keep transient Qt animations alive until their finished signal fires."""
        if not hasattr(self, "_anims"):
            return animation
        self._anims.append(animation)
        animation.finished.connect(lambda: self._anims.remove(animation) if animation in self._anims else None)
        return animation

    def _animate_panel_visibility(self, panel: QWidget, visible: bool):
        """Route panel transitions through the shared animation engine."""
        self._panel_target_visibility[panel] = visible
        self.animation_engine.fade(panel, visible, duration=180)
        if visible and panel is getattr(self, "changes_panel", None):
            QTimer.singleShot(0, self._ensure_changes_panel_allocation)

    def _animate_input_glow(self, blur_radius: int, alpha: int):
        if self.input_glow is None:
            return
        target = (blur_radius, alpha)
        if target == self._input_glow_target:
            return
        self._input_glow_target = target

        if self._input_glow_animation is not None:
            self._input_glow_animation.stop()
            if self._input_glow_animation in self._anims:
                self._anims.remove(self._input_glow_animation)
            self._input_glow_animation = None

        target_color = QColor(178, 96, 255, alpha)
        if not self._motion_enabled or not self.isVisible() or not hasattr(self, "_anims"):
            self.input_glow.setBlurRadius(blur_radius)
            self.input_glow.setColor(target_color)
            return

        group = QParallelAnimationGroup(self)
        blur = QPropertyAnimation(self.input_glow, b"blurRadius", group)
        blur.setDuration(180)
        blur.setStartValue(self.input_glow.blurRadius())
        blur.setEndValue(blur_radius)
        blur.setEasingCurve(QEasingCurve.OutCubic)

        color = QPropertyAnimation(self.input_glow, b"color", group)
        color.setDuration(180)
        color.setStartValue(self.input_glow.color())
        color.setEndValue(target_color)
        color.setEasingCurve(QEasingCurve.OutCubic)

        group.addAnimation(blur)
        group.addAnimation(color)
        group.finished.connect(
            lambda: setattr(self, "_input_glow_animation", None)
            if self._input_glow_animation is group
            else None
        )
        self._input_glow_animation = group
        self._track_animation(group).start()

    def _refresh_name_dependent_text(self):
        if hasattr(self, "hero_label"):
            self.hero_label.setText(f"{MORICE_NAME}, what shall we do, {self.user_title}?")
        if hasattr(self, "input") and not self.is_busy:
            self.input.setPlaceholderText(self._input_placeholder())

    def toggle_mode_panel(self):
        is_visible = not self._panel_target_visibility.get(self.mode_panel, self.mode_panel.isVisible())
        self._animate_panel_visibility(self.mode_panel, is_visible)
        self.title_bar.mode_btn.setToolTip("Close mode panel" if is_visible else "Open mode panel")

    def toggle_sidebar(self):
        is_visible = not self._panel_target_visibility.get(self.sidebar, self.sidebar.isVisible())
        self._animate_panel_visibility(self.sidebar, is_visible)
        self.title_bar.sidebar_btn.setText("Close" if is_visible else "Panel")

    def toggle_workspace_panel(self):
        is_open = self._panel_target_visibility.get(
            self.workspace_panel,
            self.workspace_panel.isVisible(),
        )
        if is_open:
            self._close_workspace()
        else:
            self._open_workspace(self.active_workspace_kind)

    def _set_chat_mode(self, mode: str):
        clean_mode = normalize_chat_mode(mode)
        if clean_mode == self.chat_mode:
            self._refresh_mode_panel()
            if clean_mode == "voice" and not self._voice_conversation_active:
                self._activate_voice_mode_io()
            return
        previous_mode = self.chat_mode
        if previous_mode == "voice":
            self._stop_voice_mode_io("voice-mode-exited")
        if clean_mode == "voice":
            if previous_mode in {"normal", "project"}:
                self._voice_return_mode = previous_mode
            self.chat_mode = "voice"
            # Persist the non-listening return mode, never an active microphone.
            self.settings["chat_mode"] = self._voice_return_mode
        else:
            self.chat_mode = clean_mode
            self._voice_return_mode = clean_mode
            self.settings["chat_mode"] = self.chat_mode
        self._save_project_settings()
        self._refresh_live_action_surface()
        self._refresh_mode_panel()
        mode_name = {
            "normal": "Normal chat",
            "project": "Project",
            "voice": "Live Action",
        }[self.chat_mode]
        if self.chat_container.isVisible():
            detail = (
                "Live Action enabled. Speak naturally or type; camera vision, Chat, Lab, Tools, graphs, PC control, and Project builds remain available."
                if self.chat_mode == "voice"
                else f"{mode_name} mode enabled."
            )
            self.append_message(MORICE_NAME, self._address(detail))
        elif self.chat_mode == "normal":
            self.mode_status.setText(f"{mode_name} mode is ready for the next message.")
        if self.chat_mode == "voice":
            self._activate_voice_mode_io()
        self._refresh_top_bar_status()

    def _activate_voice_mode_io(self) -> None:
        if self.chat_mode != "voice" or self._is_closing:
            return
        # Choosing the explicit Voice workspace is itself an activation gesture;
        # it must not require a second spoken wake phrase before normal chat works.
        self.awake = True
        self.runtime.voice.configure(self._runtime_tts_config())
        self._voice_conversation_active = True
        set_voice_session_active(True)
        self._live_microphone_paused = False
        self.voice_btn.setProperty("active", "true")
        self.voice_btn.setToolTip("Exit Live Action")
        self.voice_btn.style().unpolish(self.voice_btn)
        self.voice_btn.style().polish(self.voice_btn)
        if hasattr(self, "live_action_workspace"):
            self.live_action_workspace.set_microphone_state(
                True, "Listening for your voice…"
            )
            self.live_action_workspace.show_response(
                "Live Action is ready. The camera stays off until you press Turn camera on.",
                state="MORICE",
            )
        QTimer.singleShot(180, self._begin_voice_listening)

    def _stop_voice_mode_io(self, reason: str = "voice-mode-exited") -> None:
        self._voice_conversation_active = False
        set_voice_session_active(False)
        if hasattr(self, "input") and self.runtime.speech_input.status().listening:
            self.input.setText(self._speech_base_text)
        self._speech_base_text = ""
        self._barge_in_monitoring = False
        self._barge_in_interrupted = False
        self.runtime.speech_input.cancel(reason)
        self.runtime.voice.interrupt(reason)
        self.runtime.live_vision.cancel(reason)
        self.runtime.live_vision.frames.clear()
        self.runtime.live_vision.memory.clear()
        if hasattr(self, "live_camera"):
            self.live_camera.stop("Camera is off outside Live Action.")
        if hasattr(self, "live_action_workspace"):
            self.live_action_workspace.set_microphone_state(
                False, "Live Action is off."
            )
        self.voice_btn.setProperty("active", "false")
        self.voice_btn.setToolTip("Enter Live Action")
        self.voice_btn.style().unpolish(self.voice_btn)
        self.voice_btn.style().polish(self.voice_btn)

    def _refresh_live_action_surface(self) -> None:
        if not hasattr(self, "live_action_workspace"):
            return
        is_live = self.chat_mode == "voice"
        self.live_action_workspace.setVisible(is_live)
        self.chat_container.setVisible(not is_live and not self.composer_centered)
        if hasattr(self, "composer_stage"):
            self.composer_stage.setVisible(not is_live and self.composer_centered)
        if hasattr(self, "bottom_input_host"):
            self.bottom_input_host.setVisible(not is_live and not self.composer_centered)
        if is_live:
            self.live_action_workspace.raise_()

    def _submit_live_action_text(self, text: str) -> None:
        clean = str(text or "").strip()
        if not clean:
            return
        self.input.setText(clean)
        self.on_send()

    def _on_live_camera_requested(self, enabled: bool) -> None:
        if self.chat_mode != "voice":
            return
        if not enabled:
            self.live_camera.stop("Camera is off. No frames are being captured.")
            self.runtime.live_vision.cancel("camera-off")
            self.runtime.live_vision.frames.clear()
            return
        device_id, resolution, fps, mirror = (
            self.live_action_workspace.selected_configuration()
        )
        self._save_live_camera_preferences(device_id, resolution, fps, mirror)
        self.live_camera.start(
            device_id=device_id,
            resolution=resolution,
            fps=fps,
            mirror=mirror,
        )

    def _on_live_camera_frame(self, image: object) -> None:
        # A final queued frame can arrive after QCamera.stop().  The camera
        # controller clears its in-memory image during teardown, and the UI
        # must also refuse that stale delivery so Camera Off is visibly and
        # semantically immediate.
        if self.chat_mode != "voice" or not self.live_camera.desired_active:
            return
        self.live_action_workspace.preview.set_frame(image)
        if (
            not self.live_action_workspace.awareness_check.isChecked()
        ):
            return
        now = time.monotonic()
        if now - self._last_awareness_publish < 0.75:
            return
        self._last_awareness_publish = now
        snapshot = self.live_camera.snapshot_jpeg(quality=78)
        if snapshot is None:
            return
        jpeg, metadata = snapshot
        try:
            self.runtime.live_vision.publish_frame(jpeg, **metadata)
        except (RuntimeError, ValueError):
            return

    def _on_live_awareness_requested(self, enabled: bool) -> None:
        self.settings["continuous_visual_awareness"] = str(bool(enabled)).lower()
        self._save_project_settings()
        self._last_awareness_publish = 0.0
        if not enabled:
            self.runtime.live_vision.frames.clear()
        self.live_action_workspace.show_response(
            (
                "Lightweight scene awareness is on. It tracks scene changes in memory without continuously running the visual model."
                if enabled
                else "Scene awareness is off. Vision runs only when you ask."
            ),
            state="VISION",
        )

    def _on_live_camera_configuration_changed(
        self,
        device_id: str,
        resolution: str,
        fps: float,
        mirror: bool,
    ) -> None:
        self._save_live_camera_preferences(device_id, resolution, fps, mirror)
        if self.live_camera.desired_active:
            self.live_camera.start(
                device_id=device_id,
                resolution=resolution,
                fps=fps,
                mirror=mirror,
            )
        else:
            self.live_camera.update_mirror(mirror)

    def _save_live_camera_preferences(
        self,
        device_id: str,
        resolution: str,
        fps: float,
        mirror: bool,
    ) -> None:
        self.settings["camera_device_id"] = str(device_id or "")
        self.settings["camera_resolution"] = str(resolution or "1280x720")
        self.settings["camera_fps"] = str(int(round(float(fps))))
        self.settings["camera_mirror"] = str(bool(mirror)).lower()
        self._save_project_settings()

    def _on_live_microphone_requested(self, enabled: bool) -> None:
        if self.chat_mode != "voice":
            return
        self._live_microphone_paused = not bool(enabled)
        if enabled:
            self._voice_conversation_active = True
            self.live_action_workspace.set_microphone_state(
                True, "Listening… speak naturally."
            )
            QTimer.singleShot(0, self._begin_voice_listening)
        else:
            self.runtime.speech_input.cancel("microphone-paused")
            self.live_action_workspace.set_microphone_state(
                False, "Microphone paused. Typed requests still work."
            )

    def _prepare_live_vision_request(
        self, user_input: str
    ) -> tuple[bool, VisionResult | None, tuple[int, int] | None]:
        pending = self._pending_live_vision_result
        if pending is not None and pending[0] == user_input:
            self._pending_live_vision_result = None
            return False, pending[1], (pending[2], pending[3])
        should_capture = visual_intent(user_input)
        if not should_capture:
            recalled = self.runtime.live_vision.memory.recall()
            cross_modal = bool(
                re.search(
                    r"\b(?:search|look up|copy)\s+(?:it|this|that|the text)\b",
                    user_input.casefold(),
                )
            )
            if cross_modal and recalled is not None and visual_follow_up(user_input):
                return False, recalled, None
            return False, None, None
        self._live_vision_started_ns = time.perf_counter_ns()
        snapshot = self.live_camera.snapshot_jpeg()
        if snapshot is None:
            return False, VisionResult.failure(
                "live-action-no-frame",
                None,
                "camera-off",
                "I cannot inspect the view because there is no fresh camera frame. Turn the camera on and keep the item visible.",
            ), None
        jpeg, metadata = snapshot
        try:
            self.runtime.live_vision.publish_frame(jpeg, **metadata)
        except (RuntimeError, ValueError) as exc:
            return False, VisionResult.failure(
                "live-action-publish-failed",
                None,
                "camera-frame-failed",
                f"I could not use the current camera frame: {exc}",
            ), None
        self.live_action_workspace.show_response(
            "Inspecting the latest real camera frame…",
            streaming=True,
            state="VISION",
        )
        self.live_action_workspace.set_regions(())
        self.runtime.live_vision.analyze_latest(
            user_input,
            on_complete=lambda result, prompt=user_input: self._emit_background(
                "live_vision_ready", prompt, result
            ),
        )
        return True, None, None

    def _on_live_vision_ready(self, prompt: str, payload: object) -> None:
        if self.chat_mode != "voice" or not isinstance(payload, VisionResult):
            return
        completed_ns = time.perf_counter_ns()
        started_ns = self._live_vision_started_ns or completed_ns
        self._pending_live_vision_result = (
            str(prompt),
            payload,
            started_ns,
            completed_ns,
        )
        self._live_vision_started_ns = None
        self.input.setText(str(prompt))
        if payload.success:
            self.live_action_workspace.set_regions(payload.regions)
            self.live_action_workspace.show_response(
                "Visual processing finished. Composing the response…",
                streaming=True,
                state="VISION",
            )
        else:
            self.live_action_workspace.set_regions(())
            self.live_action_workspace.show_response(payload.message, state="VISION")
        QTimer.singleShot(0, self.on_send)

    def _project_capable_mode(self) -> bool:
        return self.chat_mode in {"project", "voice"}

    def _choose_project_folder(self):
        start_dir = (
            self.project_folder
            if self.project_folder and os.path.isdir(self.project_folder)
            else os.path.expanduser("~")
        )
        folder = QFileDialog.getExistingDirectory(self, "Choose or create a work folder outside MORICE", start_dir)
        if not folder:
            return
        clean_folder = normalize_project_folder(folder)
        if self._is_inside_app_folder(clean_folder):
            self.mode_status.setText("Pick a work folder outside the MORICE app folder.")
            return
        self.project_folder = clean_folder
        self.project_folder_input.setText(self.project_folder)
        self.project_folder_input.setToolTip(self.project_folder)
        self._save_project_settings()
        self._refresh_mode_panel()
        self._refresh_project_tree()
        self.runtime.plugins.publish_event(
            "project.loaded",
            {"path": self.project_folder, "access": self.project_access},
        )
        self.mode_status.setText("Work folder saved. Project mode can use this as the build root.")

    def _ensure_project_folder_for_build(self) -> bool:
        typed_folder = ""
        if hasattr(self, "project_folder_input"):
            typed_folder = normalize_project_folder(self.project_folder_input.text())
        if typed_folder and not self._is_inside_app_folder(typed_folder):
            self.project_folder = typed_folder

        if not self.project_folder:
            base = os.path.join(os.path.expanduser("~"), "MORICE Projects")
            self.project_folder = normalize_project_folder(os.path.join(base, "Quick Build"))

        if self._is_inside_app_folder(self.project_folder):
            self.mode_status.setText("Pick a work folder outside the MORICE app folder.")
            return False

        try:
            os.makedirs(self.project_folder, exist_ok=True)
        except OSError as exc:
            self.mode_status.setText(f"Could not prepare work folder: {exc}")
            return False

        if hasattr(self, "project_folder_input"):
            self.project_folder_input.setText(self.project_folder)
            self.project_folder_input.setToolTip(self.project_folder)
        self._save_project_settings()
        self._refresh_mode_panel()
        return True

    def _set_project_access(self, access: str):
        clean_access = normalize_project_access(access)
        if clean_access == self.project_access:
            self._refresh_mode_panel()
            return
        self.project_access = clean_access
        self._save_project_settings()
        self._refresh_mode_panel()
        label = "Full access" if self.project_access == "full" else "Folder-limited access"
        self.mode_status.setText(f"{label} saved for project mode.")

    def _toggle_project_lookup_mode(self):
        self.project_lookup_mode = "local" if self.project_lookup_mode == "online" else "online"
        self._save_project_settings()
        self._refresh_mode_panel()
        label = "Online+local" if self.project_lookup_mode == "online" else "Local mode"
        self.mode_status.setText(f"{label} saved for Project mode.")

    def _save_project_settings(self):
        self.settings["emoji_level"] = self.emoji_level
        self.settings["maturity_level"] = self.maturity_level
        self.settings["font_family"] = self.font_family
        self.settings["custom_font_path"] = self.custom_font_path
        self.settings["chat_mode"] = (
            self._voice_return_mode
            if self.chat_mode == "voice"
            else self.chat_mode
        )
        self.settings["project_folder"] = self.project_folder
        self.settings["project_access"] = self.project_access
        self.settings["project_lookup_mode"] = self.project_lookup_mode
        self.settings["model_path"] = self.model_path
        self.settings["model_name"] = self.model_name
        self.settings["gpu_name"] = self.gpu_name
        self.settings["gpu_vram_mb"] = self.gpu_vram_mb
        self.settings["default_music_provider"] = self.default_music_provider
        if not self._session_enabled:
            return
        save_settings(self.settings)

    def _save_default_music_provider(self, provider: str) -> None:
        clean = normalize_music_provider(provider)
        if clean == self.default_music_provider:
            return
        self.default_music_provider = clean
        self.runtime.set_default_music_provider(clean)
        self._save_project_settings()
        if hasattr(self, "mode_status"):
            self.mode_status.setText(
                f"{clean} is now the default music provider."
            )

    def _refresh_gpu_profile_ui(self):
        if not hasattr(self, "gpu_status_input"):
            return
        self.gpu_status_input.setText(gpu_profile_summary(self.gpu_profile))
        self.gpu_status_input.setToolTip(self.gpu_profile.message)

    def _detect_gpu_profile(self, auto: bool = False):
        if getattr(self, "_gpu_detection_busy", False):
            return
        self._gpu_detection_busy = True
        self.detect_gpu_btn.setEnabled(False)
        self.gpu_status_input.setText("Detecting GPU and VRAM...")
        if not auto:
            self.mode_status.setText("Detecting GPU and VRAM for model compatibility.")

        def worker():
            profile = detect_gpu_profile()
            self._emit_background("gpu_detected", profile)

        _start_background_task("gpu-detection", worker)

    def _on_gpu_detected(self, profile: GpuProfile):
        self._gpu_detection_busy = False
        self.detect_gpu_btn.setEnabled(not self.is_busy)
        self.gpu_profile = profile
        self.gpu_name = normalize_gpu_name(profile.name)
        self.gpu_vram_mb = normalize_gpu_vram_mb(str(profile.vram_mb))
        self._save_project_settings()
        self._refresh_gpu_profile_ui()
        if self.model_path:
            self.model_path_input.setToolTip(f"{self.model_path}\n{self._model_fit_message(self.model_path)}")
        if profile.detected:
            self.mode_status.setText(f"GPU profile saved: {gpu_profile_summary(profile)}")
        else:
            self.mode_status.setText(profile.message)

    def _save_model_name(self):
        clean_name = normalize_model_name(self.model_name_input.text())
        if self.model_name_input.text() != clean_name:
            self.model_name_input.setText(clean_name)
        replaced_file = bool(clean_name and self.model_path)
        if clean_name == self.model_name and not replaced_file:
            return
        old_name = self.model_name
        self.model_name = clean_name
        if replaced_file:
            self.model_path = ""
            self.model_path_input.setText(self._model_display_text())
            self.model_path_input.setToolTip("Using the selected Ollama model")
        self._save_project_settings()
        self._refresh_mode_panel()
        if old_name != self.model_name or replaced_file:
            reset_model_runtime()
            self.runtime.plugins.publish_event(
                "model.changed",
                {"name": self.model_name, "path": self.model_path},
            )
            self.runtime.plugins.publish_event(
                "model.switched",
                {"name": self.model_name, "path": self.model_path},
            )
        if self.model_name:
            replacement = " It replaced the selected GGUF file." if replaced_file else ""
            self.mode_status.setText(f"Ollama model saved: {self.model_name}. MORICE will use it next.{replacement}")
        else:
            self.mode_status.setText("Ollama model name cleared. MORICE will use the selected or bundled GGUF.")

    def _model_display_text(self) -> str:
        if not self.model_path:
            return "Bundled Qwen2.5 Coder 7B GGUF"
        return os.path.basename(self.model_path) or self.model_path

    def _model_status_line(self) -> str:
        if self.model_path:
            return f"Model file: {self._model_display_text()}."
        if self.model_name:
            return f"Ollama model: {self.model_name}."
        return "Model: bundled Qwen2.5 Coder 7B GGUF."

    def _model_fit_message(self, path: str) -> str:
        result = local_model_result(path)
        compatibility = model_compatibility(result, self.gpu_profile)
        run_plan = model_run_plan(result, self.gpu_profile)
        return (
            f"{compatibility.message} Run plan: {run_plan.label}. "
            f"{run_plan.context_hint} {run_plan.offload_hint}"
        )

    def _apply_model_file(self, path: str, source: str) -> bool:
        clean_path = normalize_model_path(path)
        verification = self._validate_model_file(clean_path)
        if not verification.ok:
            self.mode_status.setText(verification.message)
            return False
        if not verification.direct_chat:
            self.mode_status.setText(
                verification.message + " Pick a GGUF file or use Web to install a GGUF model."
            )
            return False

        changed = clean_path != self.model_path
        replaced_name = self.model_name
        self.model_path = clean_path
        if replaced_name:
            self.model_name = ""
            self.model_name_input.clear()
        self.model_path_input.setText(self._model_display_text())
        fit_message = self._model_fit_message(clean_path)
        self.model_path_input.setToolTip(f"{self.model_path}\n{fit_message}")
        self._save_project_settings()
        self._refresh_mode_panel()
        if changed or replaced_name:
            reset_model_runtime()
        replacement = " It replaced the selected Ollama model." if replaced_name else ""
        self.mode_status.setText(
            f"{source}: {verification.message} MORICE will use it on the next reply.{replacement} {fit_message}"
        )
        return True

    def _validate_model_file(self, path: str):
        return verify_ai_model_file(path)

    def _choose_model_source(self):
        dialog = ModelSourceDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.choice == "files":
            self._choose_model_file()
        elif dialog.choice == "web":
            self._open_model_web_browser()

    def _choose_model_file(self):
        start_dir = (
            os.path.dirname(self.model_path)
            if self.model_path and os.path.exists(self.model_path)
            else os.path.expanduser("~")
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an AI model file",
            start_dir,
            "All files (*)",
        )
        if not file_path:
            return
        self._apply_model_file(file_path, "Local model selected")

    def _open_model_web_browser(self):
        dialog = ModelWebBrowserDialog(self, self.gpu_profile)
        result = dialog.exec()
        if dialog.gpu_profile and dialog.gpu_profile.detected:
            self._on_gpu_detected(dialog.gpu_profile)
        if result != QDialog.Accepted or not dialog.selected_path:
            return
        self._apply_model_file(dialog.selected_path, "Web model installed and selected")

    def _clear_model_file(self):
        if not self.model_path:
            self.mode_status.setText(self._model_status_line())
            return
        self.model_path = ""
        self.model_path_input.setText(self._model_display_text())
        self.model_path_input.setToolTip("Using bundled Qwen2.5 Coder 7B GGUF unless an Ollama model name is set")
        self._save_project_settings()
        self._refresh_mode_panel()
        reset_model_runtime()
        if self.model_name:
            self.mode_status.setText(f"GGUF file cleared. MORICE will use Ollama model {self.model_name}.")
        else:
            self.mode_status.setText("GGUF file cleared. MORICE will use the bundled Qwen2.5 Coder 7B GGUF.")

    def _app_folder(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.abspath(os.path.dirname(sys.executable))
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def _is_inside_app_folder(self, path: str) -> bool:
        if not path:
            return False
        try:
            app_folder = os.path.normcase(self._app_folder())
            candidate = os.path.normcase(os.path.abspath(path))
            return os.path.commonpath([candidate, app_folder]) == app_folder
        except ValueError:
            return False

    def _project_folder_label(self) -> str:
        if not self.project_folder:
            return "No folder"
        name = os.path.basename(os.path.normpath(self.project_folder))
        return name or self.project_folder

    def _set_project_details_visible(self, visible: bool):
        if not hasattr(self, "project_details_opacity"):
            self.project_details.setVisible(visible)
            return
        if not hasattr(self, "_anims"):
            self.project_details_opacity.setOpacity(1.0 if visible else 0.0)
            self.project_details.setVisible(visible)
            return
        if visible:
            self.project_details.setVisible(True)
        start = self.project_details_opacity.opacity()
        end = 1.0 if visible else 0.0
        if abs(start - end) < 0.01:
            self.project_details.setVisible(visible)
            return
        anim = QPropertyAnimation(self.project_details_opacity, b"opacity")
        anim.setDuration(220)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        if not visible:
            anim.finished.connect(lambda: self.project_details.setVisible(False))
        anim.finished.connect(lambda: self._anims.remove(anim) if anim in self._anims else None)
        self._anims.append(anim)
        anim.start()

    def _refresh_mode_panel(self):
        if not hasattr(self, "normal_mode_btn"):
            return
        is_project = self.chat_mode == "project"
        is_voice = self.chat_mode == "voice"
        project_capable = is_project or is_voice
        self._set_project_details_visible(project_capable)
        if project_capable and self.changes_available and not self.changes_panel_dismissed:
            self._animate_panel_visibility(self.changes_panel, True)
            self._refresh_project_tree()
        else:
            self._animate_panel_visibility(self.changes_panel, False)
        self.personalization_btn.setVisible(not is_project)
        self.access_status_btn.setVisible(project_capable)
        self.project_lookup_btn.setVisible(project_capable)
        self.access_status_btn.setText("Full access" if self.project_access == "full" else "Folder only")
        self.access_status_btn.setToolTip("Open Project access settings")
        self.project_lookup_btn.setText("Online+local" if self.project_lookup_mode == "online" else "Local mode")
        self.project_lookup_btn.setToolTip("Toggle Project mode web lookup. Online+local is recommended.")
        self.model_name_input.setText(self.model_name)
        self.model_path_input.setText(self._model_display_text())
        if self.model_path:
            self.model_path_input.setToolTip(f"{self.model_path}\n{self._model_fit_message(self.model_path)}")
        else:
            self.model_path_input.setToolTip("Using bundled Qwen2.5 Coder 7B GGUF unless an Ollama name is set")
        self._refresh_gpu_profile_ui()
        for button, active in (
            (self.normal_mode_btn, self.chat_mode == "normal"),
            (self.project_mode_btn, is_project),
            (self.voice_mode_btn, is_voice),
        ):
            button.setProperty("active", "true" if active else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        self.project_folder_input.setText(self.project_folder)
        self.project_folder_input.setToolTip(self.project_folder or "No work folder selected")
        for button, active in (
            (self.folder_access_btn, self.project_access == "folder"),
            (self.full_access_btn, self.project_access == "full"),
        ):
            button.setProperty("active", "true" if active else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        QTimer.singleShot(0, self._update_composer_responsive_state)
        if is_voice:
            voice_status = self.runtime.voice.status()
            speech_status = self.runtime.speech_input.status()
            api_line = (
                "ElevenLabs reply audio is configured."
                if voice_status.api_configured
                else "ElevenLabs is not configured; microphone conversation remains available but replies stay text-only."
            )
            self.mode_status.setText(
                "Live Action is camera-centered and uses the complete MORICE voice/chat pipeline.\n"
                "Vision, graphs, Lab renderers, Tools, PC control, attachments, and Project builds remain available.\n"
                "The camera stays off until you explicitly turn it on, and frames are not saved.\n"
                f"Microphone: {speech_status.state.value}. {api_line}\n"
                f"Project folder: {self.project_folder or 'Quick Build will be prepared when needed.'}\n"
                + self._model_status_line()
            )
            self._refresh_send_button_state()
            return
        if not is_project:
            self.mode_status.setText(
                "Normal chat is for everyday questions, quick replies, and casual work.\n"
                + self._model_status_line()
            )
            self._refresh_send_button_state()
            return
        folder_line = self.project_folder if self.project_folder else "Choose a work folder before real builds."
        access_line = (
            "Full access: MORICE treats requested project actions as pre-approved."
            if self.project_access == "full"
            else "Limited: MORICE keeps project work inside the chosen folder."
        )
        lookup_line = (
            "Online+local: web lookup is available for current docs and examples."
            if self.project_lookup_mode == "online"
            else "Local mode: MORICE will use only the selected folder and local model."
        )
        self.mode_status.setText(
            f"Project builder ready.\n{folder_line}\n{access_line}\n{lookup_line}\n{self._model_status_line()}"
        )
        self._refresh_send_button_state()

    def _project_builder_system(self) -> str:
        folder = (
            self.project_folder
            or "No work folder selected yet. Ask the user to click the + project button before creating files."
        )
        if self.project_access == "full":
            access = (
                "Full access is selected. The user has pre-approved normal project work, including file creation, "
                "edits, installs, builds, and run commands needed for the requested project. Act responsibly and "
                "privately: do not create malware, persistence, credential theft, data exfiltration, destructive "
                "scripts, or system-breaking changes. Avoid blunders by explaining risky assumptions and choosing "
                "safe defaults."
            )
        else:
            access = (
                "Folder-limited access is selected. Treat the work folder as the project root. Keep all generated "
                "paths, commands, and file changes inside it. If the task needs anything outside that folder, ask "
                "permission for that specific job only, then return the plan back to the folder."
            )
        lookup = (
            "Online+local mode is selected. Use the local project snapshot first, then use provided web context for "
            "current APIs, package commands, and examples. If web context is missing or weak, say so briefly and use "
            "stable local knowledge."
            if self.project_lookup_mode == "online"
            else "Local/offline mode is selected. Use the selected model, conversation, and project snapshot only. "
            "Do not pretend to have current documentation; choose conservative, dependency-light code when unsure."
        )
        return (
            "Project builder mode is on. Behave like a senior coding agent for apps, games, websites, scripts, APIs, "
            "desktop apps, and mobile app planning in any language or framework the user asks for. "
            "Silently correct obvious typos, short forms, and missing words from context, for example treating 'shrt "
            "frm' as 'short form' and 'sory' as 'sorry' when the conversation makes that clear. "
            "When the user asks to build something, produce complete, practical source files that can run locally. "
            "Do not pretend a text file is a compiled app and never propose or emit fake .exe, .dll, .apk, .msi, or archive files. "
            "Treat an explicitly requested language, engine, framework, platform, and game/app identity as non-negotiable acceptance criteria. "
            "Never replace the requested product with a generic landing page, unrelated mini-games, or a page that merely uses the prompt as its heading. "
            "For a new playable game with no language or engine specified, default to a complete self-contained HTML/CSS/JavaScript project that runs by opening index.html. "
            "For a new Unity request, create valid C# source and text configuration that can be imported into Unity; "
            "only edit scenes, prefabs, and metadata when those files already exist. Never invent binary art/audio or a compiled executable. "
            "Prefer dependency-light HTML/CSS/JavaScript for browser games and apps. For Python, include a requirements.txt "
            "only for real third-party imports and make the source run with a normal Python installation. "
            "Use clean architecture, readable names, validation, useful error handling, responsive UI guidance, and "
            "testing notes where appropriate. If information is missing, choose strong defaults and mention the "
            "assumption briefly instead of stopping.\n\n"
            f"Work folder: {folder}\n"
            f"Access policy: {access}\n"
            f"Lookup policy: {lookup}"
        )

    def _is_project_build_request(self, text: str) -> bool:
        if not self._project_capable_mode():
            return False
        lowered = " ".join((text or "").lower().split())
        if not lowered:
            return False
        explanation_only = (
            lowered.startswith("chat:")
            or lowered.startswith("ask:")
            or lowered.startswith("explain:")
            or lowered.startswith("question:")
        )
        if explanation_only:
            return False
        action_words = {
            "add",
            "build",
            "change",
            "code",
            "complete",
            "create",
            "debug",
            "edit",
            "enhance",
            "fix",
            "finish",
            "generate",
            "improve",
            "implement",
            "make",
            "patch",
            "polish",
            "refactor",
            "repair",
            "scaffold",
            "tighten",
            "update",
            "write",
        }
        direct_build_words = {"build", "code", "create", "generate", "make", "scaffold", "write"}
        project_words = {
            "api",
            "app",
            "bug",
            "bugs",
            "component",
            "file",
            "game",
            "page",
            "project",
            "screen",
            "script",
            "site",
            "tool",
            "ui",
            "website",
        }
        file_like_target = bool(
            re.search(
                r"\b[\w.-]+\.(?:bat|c|cpp|cs|css|go|html|java|js|json|jsx|kt|md|php|py|rb|rs|sh|swift|ts|tsx|txt|xml|ya?ml)\b",
                lowered,
            )
        )
        question_words = {
            "how",
            "what",
            "when",
            "where",
            "which",
            "who",
            "why",
            "explain",
            "tell me",
        }
        has_action = any(key in lowered for key in action_words)
        has_project_target = any(key in lowered for key in project_words)
        has_direct_build = any(key in lowered for key in direct_build_words)
        if has_action and (has_project_target or file_like_target):
            return True
        if (
            has_direct_build
            and file_like_target
            and len(lowered.split()) >= 2
            and not any(lowered.startswith(word) for word in question_words)
        ):
            return True
        if has_action and any(marker in lowered for marker in {"this folder", "the project", "my project", "these files"}):
            return True
        if has_action and any(marker in lowered for marker in {"bug", "glitch", "issue", "loose end", "error"}):
            return True
        if has_project_target and not any(lowered.startswith(word) for word in question_words):
            return any(key in lowered for key in {"new", "simple", "small", "full", "complete", "working"})
        return False

    def _is_project_retry_request(self, text: str) -> bool:
        if not self._project_capable_mode() or not self.last_project_request:
            return False
        lowered = " ".join((text or "").lower().split())
        retry_phrases = {
            "again",
            "do it",
            "do it now",
            "done now try",
            "now try",
            "retry",
            "try again",
            "try it",
            "try it now",
            "try now",
        }
        return lowered in retry_phrases or (
            any(phrase in lowered for phrase in {"try again", "retry", "now try"})
            and len(lowered.split()) <= 5
        )

    def _project_has_files(self) -> bool:
        if not self.project_folder or not os.path.isdir(self.project_folder):
            return False
        try:
            with os.scandir(self.project_folder) as entries:
                return any(entries)
        except OSError:
            return False

    def _project_snapshot(self) -> str:
        if not self.project_folder or not os.path.isdir(self.project_folder):
            return "Existing project snapshot: no files yet."

        root = os.path.abspath(self.project_folder)
        tree_lines: list[str] = []
        content_blocks: list[str] = []
        total_chars = 0
        max_files = 120
        max_chars = 70_000
        scanned = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                name for name in dirnames if name not in PROJECT_IGNORED_DIRS and not name.startswith(".cache")
            )
            rel_dir = os.path.relpath(dirpath, root)
            depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
            if depth > 4:
                dirnames[:] = []
                continue
            for filename in sorted(filenames):
                if scanned >= max_files:
                    break
                full_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(full_path, root).replace("\\", "/")
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    continue
                if size > 1_000_000:
                    tree_lines.append(f"- {rel_path} ({size} bytes, skipped: large)")
                    scanned += 1
                    continue
                tree_lines.append(f"- {rel_path} ({size} bytes)")
                scanned += 1

                ext = os.path.splitext(filename)[1].lower()
                if ext not in PROJECT_TEXT_EXTENSIONS or total_chars >= max_chars:
                    continue
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as handle:
                        content = handle.read()
                except OSError:
                    continue
                remaining = max_chars - total_chars
                if len(content) > remaining:
                    content = content[:remaining] + "\n...truncated..."
                total_chars += len(content)
                content_blocks.append(f"\n--- {rel_path} ---\n{content}")
            if scanned >= max_files:
                break

        if not tree_lines:
            return "Existing project snapshot: no files yet."
        snapshot = "Existing project files:\n" + "\n".join(tree_lines)
        if content_blocks:
            snapshot += "\n\nReadable file contents:" + "".join(content_blocks)
        return snapshot

    def _project_manifest_instruction(self, request: str = "") -> str:
        instruction = (
            "For this project request, do not give copy-paste instructions and do not ask the user to create files. "
            "Return only valid JSON with this shape: "
            '{"summary":"short result","files":[{"path":"relative/path.ext","content":"full file content"}],'
            '"commands":["optional commands"],"notes":["optional notes"]}. '
            "Every file path must be relative to the work folder. Include complete file contents, not snippets. "
            "When editing an existing file, include the full updated file content. "
            "Do not return a commands-only manifest; create or update at least one practical file whenever the request asks to build. "
            "Never create .exe, .dll, .msi, .apk, .zip, or another compiled/binary artifact. MORICE writes runnable source files only. "
            "Honor every explicitly requested language, engine, framework, and platform. Do not silently switch languages. "
            "For a new game with no requested language or engine, create a complete self-contained index.html (plus CSS/JS when useful) rather than Unity files, fake assets, or pygame-only code. "
            "For Unity, create or edit complete C# source files and safe text configuration; never fabricate .unity, .prefab, .meta, or binary asset files. "
            "For a browser app, create a complete index.html. For a Python app, create a complete .py entry point and requirements.txt when packages are needed. "
            "Implement the requested behavior itself. A title, description, mockup, TODO, or unrelated substitute does not satisfy the request. "
            "On follow-up requests, preserve unrelated existing features and edit the current project instead of rebuilding it as a new prompt-title page. "
            "Do not wrap the JSON in markdown. Do not include explanations outside the JSON."
        )
        if request:
            instruction += "\n\n" + project_request_contract(request, self._project_has_files())
        return instruction

    def _manifest_from_markdown_files(self, text: str) -> dict | None:
        default_names = {
            "css": "styles.css",
            "html": "index.html",
            "javascript": "app.js",
            "js": "app.js",
            "jsx": "src/App.jsx",
            "py": "main.py",
            "python": "main.py",
            "ts": "src/app.ts",
            "tsx": "src/App.tsx",
        }
        files = []
        used_paths: set[str] = set()

        def unique_path(path: str) -> str:
            cleaned = path.replace("\\", "/").strip().strip("`'\"")
            base, ext = os.path.splitext(cleaned)
            candidate = cleaned
            counter = 2
            while candidate.lower() in used_paths:
                candidate = f"{base}-{counter}{ext}"
                counter += 1
            used_paths.add(candidate.lower())
            return candidate

        def infer_path(before: str, language: str, index: int) -> str | None:
            for line in reversed(before.splitlines()[-5:]):
                line = line.strip().rstrip(":")
                matches = re.findall(
                    r"([A-Za-z0-9_.-]+(?:[/\\][A-Za-z0-9_.-]+)*\.[A-Za-z0-9]{1,8})",
                    line,
                )
                for match in reversed(matches):
                    ext = os.path.splitext(match)[1].lower()
                    if ext in PROJECT_TEXT_EXTENSIONS:
                        return unique_path(match)
            language = (language or "").lower().strip()
            if language in {"json", "text", "txt", ""}:
                return None
            if language in default_names:
                return unique_path(default_names[language])
            return unique_path(f"generated-{index}.{language}")

        for index, match in enumerate(
            re.finditer(r"```([A-Za-z0-9_+.-]*)[ \t]*\n(.*?)```", text, flags=re.DOTALL),
            start=1,
        ):
            language = match.group(1).strip().lower()
            content = match.group(2).rstrip()
            if not content:
                continue
            relative_path = infer_path(text[: match.start()], language, index)
            if not relative_path:
                continue
            files.append({"path": relative_path, "content": content + "\n"})

        if not files:
            return None
        return {
            "summary": f"Created {len(files)} file(s) from the model's code blocks.",
            "files": files,
            "commands": [],
            "notes": ["MORICE converted markdown code blocks into editable project files."],
        }

    def _extract_project_manifest(self, reply: str) -> dict | None:
        text = (reply or "").strip()
        if not text:
            return None
        fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        candidates = []
        if fence_match:
            candidates.append(fence_match.group(1))
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidates.append(text[start : end + 1])
        candidates.append(text)
        for candidate in candidates:
            try:
                manifest = json.loads(candidate)
            except Exception:
                decoder = json.JSONDecoder()
                for match in re.finditer(r"\{", candidate):
                    try:
                        manifest, _end = decoder.raw_decode(candidate[match.start() :])
                    except Exception:
                        continue
                    if isinstance(manifest, dict) and isinstance(manifest.get("files"), list):
                        return manifest
                continue
            if isinstance(manifest, dict) and isinstance(manifest.get("files"), list):
                return manifest
        return self._manifest_from_markdown_files(text)

    def _project_target_path(self, relative_path: str) -> str:
        rel = (relative_path or "").replace("\\", "/").strip().lstrip("/")
        parts = [part for part in rel.split("/") if part and part != "."]
        if not parts or rel.endswith("/"):
            raise ValueError("Invalid project file path.")
        if any(part == ".." or ":" in part for part in parts):
            raise ValueError(f"Blocked unsafe project path: {relative_path}")
        if any(part.lower() in PROJECT_IGNORED_DIRS for part in parts):
            raise ValueError(f"Blocked generated file inside ignored project folder: {relative_path}")
        root = os.path.abspath(self.project_folder)
        target = os.path.abspath(os.path.join(root, *parts))
        if os.path.commonpath([root, target]) != root:
            raise ValueError(f"Blocked unsafe path outside project folder: {relative_path}")
        return target

    def _diff_html(self, path: str, old: str, new: str) -> str:
        lines = difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
        rendered = [f"<div style='color:#f4f4f4;font-weight:800;margin:8px 0'>{html.escape(path)}</div>"]
        for line in lines:
            escaped = html.escape(line)
            if line.startswith("+") and not line.startswith("+++"):
                color = "#8ff0a4"
            elif line.startswith("-") and not line.startswith("---"):
                color = "#ff8b8b"
            elif line.startswith("@@"):
                color = "#9cc8ff"
            else:
                color = "rgba(235,235,235,0.72)"
            rendered.append(f"<div style='white-space:pre;color:{color}'>{escaped}</div>")
        return "".join(rendered)

    def _apply_project_manifest(
        self,
        reply,
        request: str = "",
        *,
        preview_only: bool = False,
    ) -> dict | None:
        manifest = reply if isinstance(reply, dict) else self._extract_project_manifest(reply)
        if not manifest:
            return None
        if request:
            validate_project_manifest_intent(manifest, request)
        files = manifest.get("files") or []
        if not self.project_folder:
            raise ValueError("No work folder selected.")
        os.makedirs(self.project_folder, exist_ok=True)

        staged_files: list[tuple[str, str, str]] = []
        file_contents: dict[str, str] = {}
        for item in files[:80]:
            if not isinstance(item, dict):
                continue
            relative_path = str(item.get("path") or "").strip()
            content = item.get("content")
            if not relative_path or not isinstance(content, str):
                continue
            if len(content) > 2_000_000:
                raise ValueError(f"Refused very large generated file: {relative_path}")
            target = self._project_target_path(relative_path)
            validate_project_file(relative_path, content)
            staged_files.append((relative_path, content, target))
            file_contents[relative_path] = content

        if not staged_files:
            raise ProjectValidationError("The project response did not contain any valid source files.")

        requirements = detect_python_requirements(file_contents)
        has_requirements = any(os.path.basename(path).lower() == "requirements.txt" for path in file_contents)
        if requirements and not has_requirements:
            requirements_content = "\n".join(requirements) + "\n"
            target = self._project_target_path("requirements.txt")
            validate_project_file("requirements.txt", requirements_content)
            staged_files.append(("requirements.txt", requirements_content, target))

        changed = []
        diff_parts = []
        pending_writes: list[tuple[str, str, str]] = []
        for relative_path, content, target in staged_files:
            old = ""
            if os.path.exists(target):
                with open(target, "r", encoding="utf-8", errors="replace") as handle:
                    old = handle.read()
            if old == content:
                continue
            pending_writes.append((content, target, relative_path))
            changed.append(relative_path)
            diff_parts.append(self._diff_html(relative_path, old, content))

        run_script = build_run_script(self.project_folder, requirements)
        if run_script and not os.path.exists(os.path.join(self.project_folder, run_script[0])):
            relative_path, content = run_script
            target = self._project_target_path(relative_path)
            old = ""
            validate_project_file(relative_path, content)
            pending_writes.append((content, target, relative_path))
            changed.append(relative_path)
            diff_parts.append(self._diff_html(relative_path, old, content))

        patch_arguments = {
            "root": self.project_folder,
            "changes": [
                {"path": relative_path, "content": content}
                for content, _target, relative_path in pending_writes
            ],
        }
        patch_result = None
        if pending_writes and preview_only:
            preview_result = self.runtime.agent.tools.executor.execute(
                ToolCall(
                    "filesystem.preview_patch",
                    patch_arguments,
                    call_id=f"project-preview-{time.time_ns()}",
                )
            )
            if not preview_result.success:
                raise ProjectValidationError(
                    "; ".join(preview_result.errors)
                    or "MORICE could not validate the project patch preview."
                )
            preview_files = (
                preview_result.output.get("files", ())
                if isinstance(preview_result.output, dict)
                else ()
            )
            baselines = {
                str(item.get("path", "")): item
                for item in preview_files
                if isinstance(item, dict)
            }
            for change in patch_arguments["changes"]:
                baseline = baselines.get(str(change["path"]))
                if baseline is None:
                    raise ProjectValidationError(
                        f"MORICE could not establish a safe patch baseline for {change['path']}."
                    )
                change["expected_exists"] = bool(baseline.get("exists", False))
                change["expected_sha256"] = str(
                    baseline.get("beforeSha256", "")
                )
            self.pending_project_patch = patch_arguments
        elif pending_writes:
            permission_token = self.runtime.agent.permission_token(
                "filesystem.apply_patch",
                patch_arguments,
            )
            patch_result = self.runtime.agent.tools.executor.execute(
                ToolCall(
                    "filesystem.apply_patch",
                    patch_arguments,
                    call_id=f"project-apply-{time.time_ns()}",
                    permission_token=permission_token,
                )
            )
            if not patch_result.success or not patch_result.verified:
                raise ProjectValidationError(
                    "; ".join(patch_result.errors)
                    or "MORICE could not verify the applied project patch."
                )
            self.last_project_undo_id = str(
                patch_result.metadata.get("undoId", "")
            )
            self.pending_project_patch = None

        summary = str(manifest.get("summary") or "").strip() or f"Updated {len(changed)} file(s)."
        if not changed:
            summary = summary + " No file content changed."
        elif preview_only:
            summary = f"Patch ready for review: {summary}"
        panel_html = "<div style='font-family:Consolas,monospace;font-size:11px'>" + "".join(diff_parts) + "</div>"
        commands = [
            str(command).strip()
            for command in (manifest.get("commands") or [])[:6]
            if str(command).strip()
        ]
        notes = [
            str(note).strip()
            for note in (manifest.get("notes") or [])[:4]
            if str(note).strip()
        ]
        launch_plan = build_launch_plan(self.project_folder)
        if launch_plan and launch_plan.kind == "batch":
            # Keep users off raw Python entry points when dependencies are needed.
            # run.bat installs requirements first and then starts the real entry point.
            commands = ["run.bat"] + [
                command
                for command in commands
                if not re.match(r"^(?:py(?:thon)?|pyinstaller)\b", command.strip(), flags=re.IGNORECASE)
            ]
            notes.insert(0, "Use run.bat to install required packages before launching the Python project.")
        elif launch_plan and launch_plan.kind == "browser":
            commands = ["Open index.html in a browser"] + commands
        message = (
            f"{summary}\n\n"
            f"Work folder: {self.project_folder}\n"
            f"Changed files: {', '.join(changed) if changed else 'none'}"
        )
        if preview_only and changed:
            message += (
                "\n\nReview the green and red diff in Project changes, then choose "
                "Apply patch or Reject."
            )
        if commands:
            message += "\n\nSuggested run commands:\n" + "\n".join(f"- {command}" for command in commands)
        if notes:
            message += "\n\nNotes:\n" + "\n".join(f"- {note}" for note in notes)
        return {
            "summary": summary,
            "message": message,
            "diff_html": panel_html,
            "changed": changed,
            "validated": True,
            "pending": bool(preview_only and changed),
            "verified": bool(
                not changed
                or (patch_result is not None and patch_result.verified)
                or preview_only
            ),
        }

    def _project_patch_requires_review(self) -> bool:
        """Folder-limited mode stages a diff; Full access writes requested files.

        The mode panel promises that ordinary project work is pre-approved when
        Full access is selected.  Keeping every build as a preview broke that
        promise and made a successful response point at an empty work folder.
        """

        return self.project_access != "full"

    @staticmethod
    def _project_output_worth_repairing(reply: str) -> bool:
        text = str(reply or "").strip()
        if len(text) < 24:
            return False
        lowered = text.lower()
        if text.startswith("(MORICE)") and any(
            marker in lowered
            for marker in (
                "error",
                "timed out",
                "too long",
                "not set",
                "not found",
                "could not",
            )
        ):
            return False
        return True

    def _on_project_changes_ready(self, summary: str, diff_html: str):
        self._set_changes_minimized(False)
        self.changes_available = True
        self.changes_panel_dismissed = False
        self.changes_summary.setText(summary or "Project files updated.")
        self.changes_view.setHtml(
            diff_html
            or "<span style='color:rgba(255,255,255,0.64)'>No visible file diff for this action.</span>"
        )
        if self._project_capable_mode():
            self._animate_panel_visibility(self.changes_panel, True)
        else:
            self._animate_panel_visibility(self.changes_panel, False)
        self._set_project_workspace_tab(1)
        has_pending_patch = bool(
            self.pending_project_patch
            and self.pending_project_patch.get("changes")
        )
        self.changes_apply_btn.setEnabled(has_pending_patch)
        self.changes_reject_btn.setEnabled(has_pending_patch)
        self.changes_undo_btn.setEnabled(bool(self.last_project_undo_id))
        self._refresh_project_tree()
        try:
            self.runtime.desktop.workspaces.register(self.project_folder)
        except OSError:
            pass
        self._refresh_project_actions()
        self._record_activity(
            "Project files updated",
            summary or self.project_folder,
            category="project",
        )
        self._save_workspace_session()

    def _apply_pending_project_patch(self):
        arguments = copy.deepcopy(self.pending_project_patch or {})
        if not arguments.get("changes"):
            self.changes_action_status.setText("There is no pending patch to apply.")
            return
        pending_root = os.path.normcase(
            os.path.realpath(str(arguments.get("root", "")))
        )
        current_root = os.path.normcase(os.path.realpath(self.project_folder))
        if not pending_root or pending_root != current_root:
            self.pending_project_patch = None
            self.changes_apply_btn.setEnabled(False)
            self.changes_reject_btn.setEnabled(False)
            self.changes_action_status.setText(
                "The work folder changed. Generate a fresh patch for the selected folder."
            )
            return
        permission_token = self.runtime.agent.permission_token(
            "filesystem.apply_patch",
            arguments,
        )
        self.changes_apply_btn.setEnabled(False)
        self.changes_reject_btn.setEnabled(False)
        self.changes_action_status.setText("Applying and verifying the approved patch...")

        def worker():
            result = self.runtime.agent.tools.executor.execute(
                ToolCall(
                    "filesystem.apply_patch",
                    arguments,
                    call_id=f"project-approved-{time.time_ns()}",
                    permission_token=permission_token,
                )
            )
            self._emit_background(
                "project_patch_result",
                {"operation": "apply", "result": result, "arguments": arguments}
            )

        _start_background_task("project-apply-patch", worker)

    def _reject_pending_project_patch(self):
        self.pending_project_patch = None
        self.changes_apply_btn.setEnabled(False)
        self.changes_reject_btn.setEnabled(False)
        self.changes_summary.setText("Pending patch rejected. No files were changed.")
        self.changes_action_status.setText("Patch rejected.")
        self._append_project_output("Pending MORICE patch rejected by the user.")

    def _undo_last_project_patch(self):
        undo_id = self.last_project_undo_id
        if not undo_id:
            self.changes_action_status.setText("There is no MORICE patch to undo.")
            return
        arguments = {"undo_id": undo_id}
        permission_token = self.runtime.agent.permission_token(
            "action.undo",
            arguments,
        )
        self.changes_undo_btn.setEnabled(False)
        self.changes_action_status.setText("Restoring the previous file state...")

        def worker():
            result = self.runtime.agent.tools.executor.execute(
                ToolCall(
                    "action.undo",
                    arguments,
                    call_id=f"project-undo-{time.time_ns()}",
                    permission_token=permission_token,
                )
            )
            self._emit_background(
                "project_patch_result",
                {"operation": "undo", "result": result, "arguments": arguments}
            )

        _start_background_task("project-undo-patch", worker)

    def _on_project_patch_result(self, payload: object):
        value = payload if isinstance(payload, dict) else {}
        operation = str(value.get("operation", ""))
        result = value.get("result")
        if result is None:
            self.changes_action_status.setText("Project action returned no result.")
            return
        if operation == "verify":
            output = result.output if isinstance(result.output, dict) else {}
            checked = int(output.get("checked", 0))
            failures = list(output.get("failures", ()))
            launch = output.get("launch")
            if failures:
                self.changes_action_status.setText(
                    "Verification failed: " + str(failures[0])
                )
                self._append_project_output(
                    "Project verification failed:\n"
                    + "\n".join(str(item) for item in failures[:30])
                )
            else:
                entry = (
                    os.path.basename(str(launch.get("target", "")))
                    if isinstance(launch, dict)
                    else ""
                )
                detail = (
                    f" Entry point: {entry}."
                    if entry
                    else " No runnable entry point was detected."
                )
                self.changes_action_status.setText(
                    f"Verified {checked} source file(s).{detail}"
                )
                self._append_project_output(
                    f"Project verification passed: {checked} source file(s) checked."
                    + detail
                )
            self.changes_verify_btn.setEnabled(True)
            if isinstance(launch, dict):
                self.changes_run_btn.setEnabled(True)
                self.changes_run_btn.setText(
                    str(launch.get("label", "Run project"))
                )
            else:
                self.changes_run_btn.setEnabled(False)
                self.changes_run_btn.setText("Run project")
            return
        verify_after_apply = False
        if result.success and result.verified:
            if operation == "apply":
                self.pending_project_patch = None
                self.last_project_undo_id = str(
                    result.metadata.get("undoId", "")
                )
                changed = [
                    *result.generated_files,
                    *result.modified_files,
                ]
                self.changes_summary.setText(
                    f"Applied and verified {len(changed)} file change(s)."
                )
                self.changes_action_status.setText(
                    "Patch applied. Verification passed."
                )
                self._append_project_output(
                    "Approved patch applied and verified.\n"
                    + "\n".join(changed)
                )
                verify_after_apply = True
            else:
                self.last_project_undo_id = ""
                restored = result.output.get("restored", []) if isinstance(result.output, dict) else []
                self.changes_summary.setText(
                    f"Undo completed for {len(restored)} file(s)."
                )
                self.changes_action_status.setText("Previous file state restored.")
                self._append_project_output(
                    "Undo completed and verified.\n" + "\n".join(restored)
                )
        else:
            errors = "; ".join(result.errors) or "Unknown project action failure."
            self.changes_action_status.setText(errors)
            self._append_project_output(
                f"Project {operation or 'patch'} failed:\n{errors}"
            )
        self.changes_apply_btn.setEnabled(bool(self.pending_project_patch))
        self.changes_reject_btn.setEnabled(bool(self.pending_project_patch))
        self.changes_undo_btn.setEnabled(bool(self.last_project_undo_id))
        self._refresh_project_tree()
        if verify_after_apply:
            QTimer.singleShot(0, self._verify_project)
        else:
            self._refresh_project_actions()

    def _set_project_workspace_tab(self, index: int):
        if not hasattr(self, "project_workspace_stack"):
            return
        clean_index = max(0, min(2, int(index)))
        self.project_workspace_stack.setCurrentIndex(clean_index)
        for button_index, button in enumerate(
            (
                self.project_files_tab,
                self.project_changes_tab,
                self.project_output_tab,
            )
        ):
            button.setProperty(
                "active", "true" if button_index == clean_index else "false"
            )
            button.style().unpolish(button)
            button.style().polish(button)
        self.changes_title.setText(
            ("Project files", "Project changes", "Project output")[clean_index]
        )
        if clean_index == 0:
            self._refresh_project_tree()

    def _refresh_project_tree(self):
        if not hasattr(self, "project_file_tree"):
            return
        self.project_file_tree.clear()
        folder = self.project_folder
        if not folder or not os.path.isdir(folder):
            placeholder = QTreeWidgetItem(["Choose a valid work folder."])
            placeholder.setDisabled(True)
            self.project_file_tree.addTopLevelItem(placeholder)
            return
        root_item = QTreeWidgetItem([os.path.basename(folder) or folder])
        root_item.setData(0, Qt.UserRole, folder)
        self.project_file_tree.addTopLevelItem(root_item)
        item_by_path = {os.path.normcase(os.path.abspath(folder)): root_item}
        entries = 0
        for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
            dirnames[:] = sorted(
                name
                for name in dirnames
                if name not in PROJECT_IGNORED_DIRS
                and not os.path.islink(os.path.join(dirpath, name))
            )
            parent_path = os.path.normcase(os.path.abspath(dirpath))
            parent_item = item_by_path.get(parent_path, root_item)
            for dirname in dirnames:
                if entries >= 800:
                    break
                full_path = os.path.abspath(os.path.join(dirpath, dirname))
                item = QTreeWidgetItem([dirname])
                item.setData(0, Qt.UserRole, full_path)
                parent_item.addChild(item)
                item_by_path[os.path.normcase(full_path)] = item
                entries += 1
            for filename in sorted(filenames):
                if entries >= 800:
                    break
                full_path = os.path.abspath(os.path.join(dirpath, filename))
                item = QTreeWidgetItem([filename])
                item.setData(0, Qt.UserRole, full_path)
                parent_item.addChild(item)
                entries += 1
            if entries >= 800:
                truncated = QTreeWidgetItem(["... tree limited to 800 entries"])
                truncated.setDisabled(True)
                root_item.addChild(truncated)
                break
        root_item.setExpanded(True)

    def _preview_selected_project_file(self):
        selected = self.project_file_tree.selectedItems()
        if not selected:
            return
        path = str(selected[0].data(0, Qt.UserRole) or "")
        if not path or not os.path.isfile(path):
            self.project_file_preview.clear()
            return
        try:
            root = os.path.realpath(self.project_folder)
            resolved = os.path.realpath(path)
            if os.path.commonpath([root, resolved]) != root:
                self.project_file_preview.setPlainText(
                    "This file is outside the selected project root."
                )
                return
            if os.path.getsize(resolved) > 512 * 1024:
                self.project_file_preview.setPlainText(
                    "Preview unavailable: this file is larger than 512 KiB."
                )
                return
            with open(resolved, "r", encoding="utf-8", errors="strict") as handle:
                content = handle.read()
        except (OSError, UnicodeError, ValueError) as exc:
            self.project_file_preview.setPlainText(
                f"Preview unavailable for this file: {exc}"
            )
            return
        relative = os.path.relpath(resolved, root).replace("\\", "/")
        self.project_file_preview.setPlainText(f"{relative}\n\n{content}")

    def _append_project_output(self, text: str):
        if not hasattr(self, "project_output_view"):
            return
        clean = (text or "").rstrip()
        if not clean:
            return
        current = self.project_output_view.toPlainText()
        combined = f"{current}\n\n{clean}".strip()
        if len(combined) > 240_000:
            combined = "[Older output trimmed]\n\n" + combined[-220_000:]
        self.project_output_view.setPlainText(combined)
        cursor = self.project_output_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.project_output_view.setTextCursor(cursor)

    def _run_project_command(self):
        command = self.project_command_input.text().strip()
        if not command:
            return
        if not self.project_folder or not os.path.isdir(self.project_folder):
            self._append_project_output(
                "Command not started: choose a valid project folder first."
            )
            return
        if re.search(r"[&|<>;\r\n]", command):
            self._append_project_output(
                "Command not started: shell chaining and redirection are disabled. "
                "Run one direct command at a time."
            )
            return
        executable_match = re.match(r'^\s*"?([^"\s]+)', command)
        executable = (
            os.path.basename(executable_match.group(1)).lower()
            if executable_match
            else ""
        )
        allowed = {
            "cargo",
            "cmake",
            "dotnet",
            "git",
            "go",
            "gradle",
            "gradlew",
            "gradlew.bat",
            "java",
            "javac",
            "node",
            "npm",
            "npm.cmd",
            "npx",
            "npx.cmd",
            "pnpm",
            "pnpm.cmd",
            "py",
            "pytest",
            "python",
            "python.exe",
            "uv",
        }
        if executable not in allowed:
            self._append_project_output(
                f"Command not started: '{executable or command}' is not in MORICE's "
                "project-terminal allowlist."
            )
            return
        self.project_command_input.clear()
        self._set_project_workspace_tab(2)
        self._append_project_output(f"> {command}")
        try:
            command_parts = shlex.split(command, posix=False)
        except ValueError as exc:
            self._append_project_output(f"Command not started: {exc}")
            return
        command_parts = [
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part
            for part in command_parts
        ]
        arguments = {
            "cwd": self.project_folder,
            "command": command_parts,
            "timeout": 300,
        }
        permission_token = self.runtime.agent.permission_token(
            "terminal.run",
            arguments,
        )
        command_call_id = f"project-command-{time.time_ns()}"
        self._active_project_command_id = command_call_id
        self._emit_background("project_command_state", True)

        def worker():
            result = self.runtime.agent.tools.executor.execute(
                ToolCall(
                    "terminal.run",
                    arguments,
                    call_id=command_call_id,
                    permission_token=permission_token,
                )
            )
            output = result.output if isinstance(result.output, dict) else {}
            combined = (str(output.get("stdout", "")) + str(output.get("stderr", ""))).rstrip()
            if result.errors:
                combined += ("\n" if combined else "") + "\n".join(result.errors)
            self._emit_background(
                "project_output_ready",
                (combined or "(no output)")
                + f"\n[exit code {output.get('exitCode', 'unknown')}]"
            )
            self._active_project_command_id = ""
            self._emit_background("project_command_state", False)

        _start_background_task("project-command", worker)

    def _cancel_project_command(self):
        call_id = self._active_project_command_id
        if not call_id:
            self._emit_background("project_command_state", False)
            return
        if self.runtime.agent.cancel(call_id):
            self._append_project_output(
                "Cancellation requested for the active command."
            )
        else:
            self._append_project_output(
                "The command already finished or could not be cancelled."
            )

    def _show_project_git_status(self):
        if not self.project_folder or not os.path.isdir(self.project_folder):
            self._append_project_output(
                "Git status unavailable: choose a valid project folder first."
            )
            return
        self._set_project_workspace_tab(2)
        self._append_project_output("> git status --short --branch")

        def worker():
            result = self.runtime.agent.tools.executor.execute(
                ToolCall(
                    "git.status",
                    {"root": self.project_folder},
                    call_id=f"git-status-{time.time_ns()}",
                )
            )
            output = result.output if isinstance(result.output, dict) else {}
            combined = (str(output.get("stdout", "")) + str(output.get("stderr", ""))).rstrip()
            if result.errors:
                combined += ("\n" if combined else "") + "\n".join(result.errors)
            self._emit_background(
                "project_output_ready",
                (combined or "Clean working tree.")
                + f"\n[exit code {output.get('exitCode', 'unknown')}]"
            )

        _start_background_task("project-git-status", worker)

    def _toggle_changes_minimized(self):
        self._set_changes_minimized(not self.changes_minimized)

    def _close_changes_panel(self):
        self.changes_panel_dismissed = True
        self._animate_panel_visibility(self.changes_panel, False)

    def _ensure_changes_panel_allocation(self):
        """Give the review pane enough splitter space for its header and controls."""
        panel_index = self.workspace_splitter.indexOf(self.changes_panel)
        chat_index = self.workspace_splitter.indexOf(self.chat_container)
        sizes = self.workspace_splitter.sizes()
        if panel_index < 0 or panel_index >= len(sizes):
            return
        target_width = 620 if self.changes_expanded else 390
        current_width = sizes[panel_index]
        sizes[panel_index] = target_width
        if 0 <= chat_index < len(sizes) and current_width < target_width:
            sizes[chat_index] = max(360, sizes[chat_index] - (target_width - current_width))
        self.workspace_splitter.setSizes(sizes)
        self.changes_panel.resize(target_width, self.changes_panel.height())

    def _set_changes_minimized(self, minimized: bool):
        self.changes_minimized = False
        self.changes_content.setVisible(True)
        self.changes_title.setVisible(True)
        self.changes_minimize_btn.setVisible(False)
        self.changes_expand_btn.setVisible(True)
        self.changes_panel.resize(620 if self.changes_expanded else 390, self.changes_panel.height())

    def _toggle_changes_width(self):
        if self.changes_minimized:
            self._set_changes_minimized(False)
        self.changes_expanded = not self.changes_expanded
        target_width = 620 if self.changes_expanded else 390
        self._ensure_changes_panel_allocation()
        self.changes_expand_btn.setText("<>" if self.changes_expanded else "[]")
        self.changes_expand_btn.setToolTip("Use normal width" if self.changes_expanded else "Widen project changes")

    def _refresh_project_actions(self):
        plan = build_launch_plan(self.project_folder)
        if plan:
            self.changes_run_btn.setEnabled(True)
            self.changes_run_btn.setText(plan.label)
            self.changes_action_status.setText(f"Verified entry point available: {os.path.basename(plan.target)}")
        else:
            self.changes_run_btn.setEnabled(False)
            self.changes_run_btn.setText("Run project")
            self.changes_action_status.setText("No runnable entry point detected. Create index.html, main.py, or run.bat.")
        self.changes_verify_btn.setEnabled(bool(self.project_folder and os.path.isdir(self.project_folder)))

    def _verify_project(self):
        if not self.project_folder or not os.path.isdir(self.project_folder):
            self.changes_action_status.setText("Choose a project folder before verification.")
            return
        self.changes_verify_btn.setEnabled(False)
        self.changes_action_status.setText("Verifying project source files...")
        arguments = {"root": self.project_folder}

        def worker():
            result = self.runtime.agent.tools.executor.execute(
                ToolCall(
                    "project.verify",
                    arguments,
                    call_id=f"project-verify-{time.time_ns()}",
                )
            )
            self._emit_background(
                "project_patch_result",
                {"operation": "verify", "result": result, "arguments": arguments}
            )

        _start_background_task("project-verify", worker)

    def _run_project(self):
        plan = build_launch_plan(self.project_folder)
        if not plan:
            self.changes_action_status.setText("No verified project entry point is available to run.")
            return
        try:
            message = launch_project(plan)
            self.changes_action_status.setText(message)
            self._append_project_output(message)
        except (OSError, ProjectValidationError) as exc:
            self.changes_action_status.setText(f"Could not run project: {exc}")
            self._append_project_output(f"Could not run project: {exc}")

    def _set_workspace_view(self, kind: str):
        clean = kind if kind in {"graph", "physics", "notebook"} else "graph"
        self.active_workspace_kind = clean
        for button, active in (
            (self.graph_workspace_btn, clean == "graph"),
            (self.physics_workspace_btn, clean == "physics"),
            (self.notebook_workspace_btn, clean == "notebook"),
        ):
            button.setProperty("active", "true" if active else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        self.graph_canvas_host.setVisible(clean == "graph")
        self.graph_dimension_select.setVisible(
            clean == "graph" and isinstance(self.graph_canvas, SurfaceCanvas)
        )
        self.graph_equations.setVisible(clean == "graph")
        self.graph_inspector.setVisible(clean == "graph")
        self.physics_canvas.setVisible(clean == "physics")
        self.physics_stats.setVisible(clean == "physics")
        self.physics_controls_frame.setVisible(clean == "physics")
        self.notebook_view.setVisible(clean == "notebook")

    def _open_workspace(self, kind: str):
        self._animate_panel_visibility(self.workspace_panel, True)
        self._set_workspace_view(kind)
        if hasattr(self.title_bar, "workspace_btn"):
            self.title_bar.workspace_btn.setText("Close Lab")
        self._refresh_top_bar_status()

    def _close_workspace(self):
        self._animate_panel_visibility(self.workspace_panel, False)
        if hasattr(self.title_bar, "workspace_btn"):
            self.title_bar.workspace_btn.setText("Lab")
        self._refresh_top_bar_status()

    def _refresh_workspace_artifact_list(self):
        self.workspace_artifact_list.blockSignals(True)
        self.workspace_artifact_list.clear()
        for artifact in self.science_artifacts:
            prefix = {
                "graph": "Graph",
                "physics": "Physics",
                "chemistry": "Molecule",
                "diagram": "Diagram",
                "biology": "Biology",
                "data-structures": "Data structures",
                "chart": "Chart",
                "scene": "3D schematic",
                "document": "Document",
            }.get(artifact.kind, "Artifact")
            item = QListWidgetItem(f"{prefix}: {artifact.title}")
            item.setData(Qt.UserRole, artifact.kind)
            self.workspace_artifact_list.addItem(item)
        self.workspace_artifact_list.blockSignals(False)
        if self.science_artifacts:
            self.workspace_artifact_list.setCurrentRow(len(self.science_artifacts) - 1)

    def _on_workspace_artifact_selected(self, row: int):
        if row < 0 or row >= len(self.science_artifacts):
            return
        artifact = self.science_artifacts[row]
        self._set_workspace_view(
            artifact.kind if artifact.kind in {"graph", "physics"} else "notebook"
        )
        if artifact.graph:
            wants_surface_canvas = artifact.graph.surface is not None
            has_surface_canvas = isinstance(self.graph_canvas, SurfaceCanvas)
            if wants_surface_canvas != has_surface_canvas:
                self.graph_canvas_layout.removeWidget(self.graph_canvas)
                self.graph_canvas.deleteLater()
                self.graph_canvas = SurfaceCanvas() if wants_surface_canvas else GraphCanvas()
                self.graph_canvas.inspected.connect(
                    lambda text: self.graph_inspector.setText(text or "Move over the graph to inspect points.")
                )
                self.graph_canvas_layout.addWidget(self.graph_canvas)
            self.graph_canvas.set_artifact(artifact.graph)
            self.graph_dimension_select.setVisible(wants_surface_canvas)
            if wants_surface_canvas:
                self.graph_dimension_select.setCurrentText("3D")
                self.graph_canvas.set_view_mode("3d")
            self.graph_equations.setText(
                "Equations:\n"
                + (
                    f"- {artifact.graph.surface.label}"
                    if artifact.graph.surface
                    else "\n".join(f"- {series.label}" for series in artifact.graph.series)
                )
            )
        if artifact.physics:
            self.physics_canvas.set_artifact(artifact.physics)
            is_3d = "3d" in artifact.physics.instruction.get(
                "parameters", {}
            ).get("views", ["2d"])
            self.physics_dimension_select.setVisible(is_3d)
            if is_3d:
                self.physics_dimension_select.setCurrentText("3D")
                self.physics_canvas.set_render_mode("3d")
            self.physics_stats.setText(
                f"Particles: {len(artifact.physics.particles)} | FPS: measuring | "
                f"Collisions/sec: 0 | Speed: {self.physics_canvas.speed:g}x"
            )
        self.notebook_view.setPlainText(
            "Artifact\n"
            f"Title: {artifact.title}\n"
            f"Kind: {artifact.kind}\n\n"
            "Deterministic instruction JSON\n"
            + json.dumps(artifact.instruction, indent=2)
        )

    def _add_science_artifact(self, artifact: ScienceArtifact):
        self.science_artifacts.append(copy.deepcopy(artifact))
        self._refresh_workspace_artifact_list()

    def _insert_chat_widget(self, widget: QWidget, force_scroll: bool = True):
        insert_index = max(0, self.chat_list_layout.count() - 1)
        self.chat_list_layout.insertWidget(insert_index, widget)
        if force_scroll:
            self.follow_latest = True
        self._schedule_latest_scroll(force=force_scroll)

    def _replace_chat_widget(self, old_widget: QWidget, new_widget: QWidget):
        index = self.chat_list_layout.indexOf(old_widget)
        if index < 0:
            self._insert_chat_widget(new_widget)
            return
        self.chat_list_layout.removeWidget(old_widget)
        self.chat_list_layout.insertWidget(index, new_widget)
        old_widget.deleteLater()
        self.follow_latest = True
        self._schedule_latest_scroll(force=True)

    def _visualization_renderer_label(self, renderer_id: str) -> str:
        plugin = self.visualization_manager.registry.get(renderer_id)
        return plugin.label if plugin else renderer_id.replace(".", " ")

    def _handle_science_request(self, user_input: str) -> bool:
        if self.chat_mode == "project":
            return False
        decision = self.visualization_manager.decide(user_input)
        if decision is None:
            return False

        request = self.visualization_manager.create_request(user_input, decision)
        renderer_label = self._visualization_renderer_label(decision.renderer_id)
        card = VisualizationGenerationCard(renderer_label)
        self.visualization_cards[request.job_id] = card
        self._insert_chat_widget(card)
        self.history.append({"role": "user", "content": user_input})

        def progress(stage: str, detail: str, percent: int):
            self._emit_background(
                "visualization_progress",
                request.job_id,
                stage,
                detail,
                percent,
            )

        future = self.visualization_manager.submit(request, progress)
        self.visualization_futures[request.job_id] = future
        self.runtime.plugins.publish_event(
            "visualization.started",
            {
                "jobId": request.job_id,
                "rendererId": decision.renderer_id,
                "prompt": user_input[:2_000],
            },
        )
        self.runtime.plugins.publish_event(
            "renderer.started",
            {"jobId": request.job_id, "rendererId": decision.renderer_id},
        )

        def completed(completed_future):
            try:
                result = completed_future.result()
            except Exception as exc:  # noqa: BLE001
                result = VisualizationResult(
                    job_id=request.job_id,
                    status="failed",
                    renderer_id=decision.renderer_id,
                    error=f"Rendering failed: {exc}",
                )
            self._emit_background("visualization_finished", result)

        future.add_done_callback(completed)
        return True

    def _on_visualization_progress(self, job_id: str, stage: str, detail: str, percent: int):
        card = self.visualization_cards.get(job_id)
        if card:
            card.set_stage(stage, detail, percent)

    def _on_visualization_finished(self, result: VisualizationResult):
        card = self.visualization_cards.pop(result.job_id, None)
        self.visualization_futures.pop(result.job_id, None)
        if card is None:
            return
        self.runtime.plugins.publish_event(
            "visualization.finished",
            {
                "jobId": result.job_id,
                "rendererId": result.renderer_id,
                "status": result.status,
                "validated": result.validated,
                "durationMs": result.duration_ms,
                "error": result.error,
            },
        )
        self.runtime.plugins.publish_event(
            "renderer.finished",
            {
                "jobId": result.job_id,
                "rendererId": result.renderer_id,
                "status": result.status,
                "validated": result.validated,
            },
        )
        if not result.ok or result.artifact is None:
            message = result.error or "The renderer did not produce a validated visualization."
            card.set_error(message)
            reply = (
                f"I could not render that visual. {message} "
                "Nothing was displayed, and I will not substitute a fake placeholder."
            )
            self.history.append({"role": "assistant", "content": reply})
            visible_reply = self._address(reply)
            self.append_message(MORICE_NAME, visible_reply)
            self._speak_assistant_text(visible_reply)
            self._record_activity(
                "Visualization failed", message, category="visualization"
            )
            self._complete_agent_ui(response_present=True, successful=False)
            self._save_workspace_session()
            return

        artifact = result.artifact
        self.runtime.plugins.publish_event(
            "visualization.created",
            {
                "jobId": result.job_id,
                "rendererId": result.renderer_id,
                "kind": artifact.kind,
                "title": artifact.title,
            },
        )
        self._add_science_artifact(artifact)
        if artifact.kind == "graph" and artifact.graph:
            workspace = InlineGraphWorkspace(artifact.graph)
        elif artifact.kind == "physics" and artifact.physics:
            workspace = InlinePhysicsWorkspace(artifact.physics)
        elif artifact.kind == "chemistry" and isinstance(artifact.chemistry, MoleculeArtifact):
            workspace = InlineMoleculeWorkspace(artifact.chemistry)
        elif artifact.kind == "diagram" and isinstance(artifact.diagram, DiagramArtifact):
            workspace = InlineDiagramWorkspace(artifact.diagram)
        elif artifact.kind == "biology" and isinstance(artifact.biology, BiologyArtifact):
            workspace = InlineBiologyWorkspace(artifact.biology)
        elif artifact.kind == "data-structures" and isinstance(
            artifact.data_structures, DataStructureArtifact
        ):
            workspace = InlineDataStructureWorkspace(artifact.data_structures)
        elif artifact.kind == "chart" and isinstance(artifact.chart, ChartArtifact):
            workspace = InlineChartWorkspace(artifact.chart)
        elif artifact.kind == "scene" and isinstance(artifact.scene, SceneArtifact):
            workspace = InlineSceneWorkspace(artifact.scene)
        elif artifact.kind == "document" and isinstance(
            artifact.document, DocumentArtifact
        ):
            workspace = InlineDocumentWorkspace(artifact.document)
        else:
            message = "The renderer returned an unsupported artifact type, so nothing was displayed."
            card.set_error(message)
            self.history.append({"role": "assistant", "content": message})
            visible_message = self._address(message)
            self.append_message(MORICE_NAME, visible_message)
            self._speak_assistant_text(visible_message)
            self._record_activity(
                "Visualization rejected", message, category="visualization"
            )
            self._complete_agent_ui(response_present=True, successful=False)
            self._save_workspace_session()
            return

        self._replace_chat_widget(card, workspace)
        reply = self._science_ready_reply(artifact, result)
        self.history.append({"role": "assistant", "content": reply})
        visible_reply = self._address(reply)
        self.append_message(MORICE_NAME, visible_reply)
        self._speak_assistant_text(visible_reply)
        self._record_activity(
            "Visualization rendered",
            f"{artifact.kind}: {artifact.title}",
            category="visualization",
        )
        self._complete_agent_ui(response_present=True)
        self._save_workspace_session()

    def _science_ready_reply(
        self,
        artifact: ScienceArtifact | None = None,
        result: VisualizationResult | None = None,
    ) -> str:
        artifact = artifact or (self.science_artifacts[-1] if self.science_artifacts else None)
        timing = f" It was prepared and validated in {result.duration_ms:.0f} ms." if result else ""
        if artifact and artifact.kind == "graph" and artifact.graph:
            if artifact.graph.surface:
                surface = artifact.graph.surface
                return (
                    f"The validated surface above uses one shared data grid for both views: "
                    f"{surface.label}. Switch between the 2D height map and interactive 3D mesh; "
                    f"hover to inspect x, y, z samples, drag to rotate or pan, and use the wheel to zoom."
                    f"{timing}"
                )
            equations = ", ".join(series.label for series in artifact.graph.series)
            landmark_count = sum(len(series.inspection_points) for series in artifact.graph.series)
            return (
                f"The interactive graph above is live and validated. Equations: {equations}. "
                f"I found {landmark_count} inspectable intercept, extrema, or inflection points. "
                f"Hover for coordinates, drag to pan, use the wheel to zoom, or export PNG, SVG, or PDF.{timing}"
            )
        if artifact and artifact.kind == "physics" and artifact.physics:
            views = (
                " Switch between the 2D projection and 3D perspective; both use the same xyz simulation state."
                if "3d" in artifact.physics.instruction.get(
                    "parameters", {}
                ).get("views", ["2d"])
                else ""
            )
            return (
                f"The live {artifact.physics.simulation_type} simulation above contains "
                f"{len(artifact.physics.particles)} physical bodies. Use Pause, Resume, Step, Reset, "
                f"speed, gravity, vector, and trail controls to inspect the system.{views}{timing}"
            )
        if artifact and artifact.kind == "chemistry" and isinstance(
            artifact.chemistry, MoleculeArtifact
        ):
            molecule = artifact.chemistry
            return (
                f"The validated {molecule.formula} model above is from MORICE's curated VSEPR "
                f"library. Its molecular geometry is {molecule.geometry}, its electron geometry is "
                f"{molecule.electron_geometry}, and the central atom has "
                f"{molecule.central_lone_pairs} lone pair(s). The 2D and 3D controls use the same "
                f"validated atom and bond topology.{timing}"
            )
        if artifact and artifact.kind == "diagram" and isinstance(
            artifact.diagram, DiagramArtifact
        ):
            diagram = artifact.diagram
            return (
                f"The structured {diagram.diagram_type} diagram above contains "
                f"{len(diagram.nodes)} validated nodes and {len(diagram.edges)} directed links. "
                f"Hover nodes to inspect their connections, drag to pan, zoom with the wheel, "
                f"or export it.{timing}"
            )
        if artifact and artifact.kind == "biology" and isinstance(
            artifact.biology, BiologyArtifact
        ):
            biology = artifact.biology
            return (
                f"The interactive {biology.title} model above contains "
                f"{len(biology.points)} validated geometry points. Switch between its 2D "
                f"schematic and 3D perspective, pause or resume animation, zoom, rotate, "
                f"and inspect labeled components.{timing}"
            )
        if artifact and artifact.kind == "data-structures" and isinstance(
            artifact.data_structures, DataStructureArtifact
        ):
            data = artifact.data_structures
            return (
                f"The data-structure lab above includes {', '.join(data.structures)}. "
                "Choose a structure and run real Insert, Delete, or Search operations; "
                f"the changed or visited nodes animate and the operation complexity updates live.{timing}"
            )
        if artifact and artifact.kind == "chart" and isinstance(
            artifact.chart, ChartArtifact
        ):
            chart = artifact.chart
            return (
                f"The interactive {chart.chart_type} chart above contains "
                f"{len(chart.points)} validated numeric points taken directly from your prompt. "
                f"Hover marks for exact values or export PNG, SVG, or PDF.{timing}"
            )
        if artifact and artifact.kind == "scene" and isinstance(
            artifact.scene, SceneArtifact
        ):
            scene = artifact.scene
            return (
                f"The labeled {scene.scene_type} schematic above contains "
                f"{len(scene.primitives)} validated components. Switch between 2D and 3D, "
                f"pause rotation, zoom, drag to inspect the assembly, or export PNG. "
                f"It is an educational component schematic, not a dimensionally certified CAD model.{timing}"
            )
        if artifact and artifact.kind == "document" and isinstance(
            artifact.document, DocumentArtifact
        ):
            document = artifact.document
            return (
                f"The validated local preview above displays {document.title} "
                f"({document.size_bytes / 1024:.1f} KB). The file was read from the exact "
                f"path you supplied and no substitute content was generated.{timing}"
            )
        return "The renderer completed, but no supported interactive artifact was available."

    def _create_message_row(
        self,
        author: str,
        message: str,
        is_user: bool,
        *,
        insert_index: int | None = None,
        animate: bool = True,
        row_list_index: int | None = None,
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("MessageRow")
        row.setProperty("chatMessage", "true")
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        bubble = ChatBubble(author, message, is_user=is_user)
        bubble.edit_requested.connect(self._edit_chat_message)
        bubble.reaction_changed.connect(
            lambda reaction, author=author: self._record_activity(
                "Message reaction changed",
                f"{author}: {reaction or 'cleared'}",
                category="chat",
            )
        )
        bubble.installEventFilter(self)
        bubble.setMaximumWidth(16777215)
        row_layout.addWidget(bubble, stretch=1)
        for button in bubble.findChildren(QPushButton):
            if hasattr(self, "micro_interactions"):
                button.installEventFilter(self.micro_interactions)
            button.setCursor(Qt.PointingHandCursor)

        opacity = QGraphicsOpacityEffect(row)
        row.setGraphicsEffect(opacity)
        opacity.setOpacity(0.0 if animate else 1.0)
        target_index = (
            max(1, int(insert_index))
            if insert_index is not None
            else max(1, self.chat_list_layout.count() - 1)
        )
        self.chat_list_layout.insertWidget(target_index, row)
        if row_list_index is None:
            self._message_rows.append(row)
        else:
            self._message_rows.insert(max(0, row_list_index), row)

        if animate and self._motion_enabled and self.isVisible():
            animation = QPropertyAnimation(opacity, b"opacity", row)
            animation.setDuration(self.animation_engine.duration(180))
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            if not is_user:
                glow_color = QColor(self.accent_color)
                glow_color.setAlpha(72)
                animation.finished.connect(
                    lambda bubble=bubble, color=glow_color: self.animation_engine.shadow(
                        bubble,
                        color=color,
                        blur=16,
                        duration=220,
                    )
                )
            self._track_animation(animation).start()
        else:
            opacity.setOpacity(1.0)
        return row

    def _edit_chat_message(self, message: str) -> None:
        self.input.setText(message)
        self.input.setFocus(Qt.OtherFocusReason)
        cursor = self.input.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.input.setTextCursor(cursor)
        self._show_notification("Message loaded into the composer for editing.")

    def _virtualize_chat_widgets(self) -> None:
        while len(self._message_rows) > MAX_VISIBLE_CHAT_WIDGETS:
            row = self._message_rows.pop(0)
            bubble = row.findChild(ChatBubble)
            if bubble is not None:
                self._archived_messages.append(
                    (bubble.author, bubble.message, bubble.is_user)
                )
            self.chat_list_layout.removeWidget(row)
            row.deleteLater()
        self._refresh_archive_notice()

    def _refresh_archive_notice(self) -> None:
        count = len(self._archived_messages)
        self.chat_archive_notice.setVisible(count > 0)
        self.chat_archive_label.setText(
            f"{count} earlier message{'s' if count != 1 else ''} are virtualized."
            if count
            else ""
        )

    def _load_earlier_messages(self) -> None:
        if not self._archived_messages:
            return
        batch = self._archived_messages[-20:]
        del self._archived_messages[-len(batch) :]
        for offset, (author, message, is_user) in enumerate(batch):
            self._create_message_row(
                author,
                message,
                is_user,
                insert_index=1 + offset,
                animate=self._motion_enabled,
                row_list_index=offset,
            )
        self._refresh_archive_notice()

    def append_message(self, author: str, message: str, is_user: bool = False, force_scroll: bool | None = None):
        if self.chat_mode == "voice" and hasattr(self, "live_action_workspace"):
            if is_user:
                self.live_action_workspace.set_transcript(message, partial=False)
            elif author == MORICE_NAME:
                self.live_action_workspace.show_response(message, state="MORICE")
        should_follow = self.follow_latest or self._is_at_bottom()
        if force_scroll is None:
            force_scroll = is_user or should_follow
        if force_scroll:
            self.follow_latest = True

        self._create_message_row(author, message, is_user)
        self._virtualize_chat_widgets()
        self._schedule_latest_scroll(force=force_scroll)

    def _remember_conversation_turn(self, user_input: str, assistant_reply: str):
        user_text = str(user_input or "").strip()
        reply_text = str(assistant_reply or "").strip()
        if user_text:
            self.history.append({"role": "user", "content": user_text})
        if reply_text:
            self.history.append({"role": "assistant", "content": reply_text})
        self.history = self.history[-160:]

    def _append_direct_reply(
        self,
        user_input: str,
        reply: str,
        *,
        address: bool = True,
    ):
        realtime_request = self.runtime.realtime.active_request
        if realtime_request is not None and realtime_request.text != str(user_input or "").strip():
            realtime_request = None
        visible_reply = self._address(reply) if address else str(reply or "").strip()
        self._remember_conversation_turn(user_input, visible_reply)
        self.append_message(MORICE_NAME, visible_reply)
        if realtime_request is not None:
            realtime_request.trace.mark_event("first_visible_token")
            realtime_request.trace.mark_event("fast_response_visible")
        voice_handle = self._speak_assistant_text(
            visible_reply,
            request_id=(realtime_request.request_id if realtime_request else None),
        )
        if realtime_request is not None:
            self.runtime.realtime.complete_generation(realtime_request.epoch)
            if voice_handle is None:
                self.runtime.realtime.finish_speech(realtime_request.epoch)
        self._complete_agent_ui(response_present=bool(visible_reply))
        self._save_workspace_session()

    def _set_busy(self, is_busy: bool):
        self.is_busy = is_busy
        self.input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.personalization_btn.setEnabled(not is_busy)
        self.precision_btn.setEnabled(not is_busy)
        self.style_input.setEnabled(not is_busy)
        self.title_input.setEnabled(not is_busy)
        self.wake_input.setEnabled(not is_busy)
        self.theme_select.setEnabled(not is_busy)
        self.emoji_select.setEnabled(not is_busy)
        self.maturity_select.setEnabled(not is_busy)
        self.font_select.setEnabled(not is_busy)
        self.add_font_btn.setEnabled(not is_busy)
        self.animation_speed_select.setEnabled(not is_busy)
        self.reduced_motion_check.setEnabled(not is_busy)
        self.high_contrast_check.setEnabled(not is_busy)
        self.large_text_check.setEnabled(not is_busy)
        self.ui_scale_slider.setEnabled(not is_busy)
        self.transparency_slider.setEnabled(not is_busy)
        self.workspace_preset_select.setEnabled(not is_busy)
        self.advanced_settings_btn.setEnabled(not is_busy)
        self.save_style_btn.setEnabled(not is_busy)
        self.clear_style_btn.setEnabled(not is_busy)
        allow_voice_exit = self.chat_mode == "voice"
        self.normal_mode_btn.setEnabled(not is_busy or allow_voice_exit)
        self.project_mode_btn.setEnabled(not is_busy or allow_voice_exit)
        self.voice_mode_btn.setEnabled(not is_busy or allow_voice_exit)
        self.model_name_input.setEnabled(not is_busy)
        self.model_path_input.setEnabled(not is_busy)
        self.change_model_btn.setEnabled(not is_busy)
        self.clear_model_btn.setEnabled(not is_busy)
        self.detect_gpu_btn.setEnabled((not is_busy) and not getattr(self, "_gpu_detection_busy", False))
        self.project_folder_input.setEnabled(not is_busy)
        self.project_add_btn.setEnabled(not is_busy)
        self.folder_access_btn.setEnabled(not is_busy)
        self.full_access_btn.setEnabled(not is_busy)
        self.access_status_btn.setEnabled(not is_busy)
        self.project_lookup_btn.setEnabled(not is_busy)
        self._refresh_send_button_state()
        if hasattr(self, "assistant_hub"):
            self.assistant_hub.set_tasks(self.message_queue, self.is_busy)
        if hasattr(self, "title_bar"):
            self._refresh_top_bar_status()
        self._refresh_top_bar_status()

    def _refresh_send_button_state(self):
        queued_count = len(self.message_queue)
        has_text = bool(self.input.text().strip()) if hasattr(self, "input") else False
        can_click = has_text
        ready_state = has_text and not self.is_busy
        if self.is_busy:
            self.send_btn.setText(f"Queued {queued_count}" if queued_count else "Steer")
            if queued_count:
                self.input.setPlaceholderText("Queued. Add another steer message or reorder in Panel.")
            else:
                self.input.setPlaceholderText("Steer next message while MORICE replies...")
        else:
            self.send_btn.setText("Send")
            self.input.setPlaceholderText(self._input_placeholder())
        self.send_btn.setEnabled(can_click)
        if hasattr(self.send_btn, "set_ready"):
            self.send_btn.set_ready(ready_state)
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
        if hasattr(self, "assistant_hub"):
            self.assistant_hub.set_tasks(self.message_queue, self.is_busy)

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
        if self.chat_mode == "voice" and hasattr(self, "live_action_workspace"):
            self.live_action_workspace.show_response(
                detail, streaming=True, state="WORKING"
            )
        self._thinking_token += 1
        token = self._thinking_token
        self.thinking_bubble = ThinkingBubble(detail)
        insert_index = max(0, self.chat_list_layout.count() - 1)
        self.chat_list_layout.insertWidget(insert_index, self.thinking_bubble)
        if self._motion_enabled and self.isVisible():
            opacity = QGraphicsOpacityEffect(self.thinking_bubble)
            opacity.setOpacity(0.0)
            self.thinking_bubble.setGraphicsEffect(opacity)
            anim = QPropertyAnimation(opacity, b"opacity", self.thinking_bubble)
            anim.setDuration(160)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._track_animation(anim).start()
        self._schedule_latest_scroll(force=True)
        QTimer.singleShot(
            12000,
            lambda: self._thinking_delayed_update(
                token,
                "Qwen is still generating. Local CPU replies can take a bit.",
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
            self._emit_background("thinking_update", detail)

    def _remove_thinking(self):
        if not self.thinking_bubble:
            return
        self.chat_list_layout.removeWidget(self.thinking_bubble)
        self.thinking_bubble.deleteLater()
        self.thinking_bubble = None

    def _remove_thinking_widget(self, bubble: ThinkingBubble):
        if self.thinking_bubble is bubble:
            self._remove_thinking()

    def _finish_thinking(self):
        self._remove_thinking()

    def _on_assistant_stream_delta(self, request_id: str, delta: str) -> None:
        clean_delta = str(delta or "")
        if not clean_delta:
            return
        if request_id != self._stream_request_id:
            self._stream_request_id = request_id
            self._stream_text = ""
            self._stream_bubble = None
        self._stream_text += clean_delta
        visible = self._address(self._stream_text)
        if self.chat_mode == "voice" and hasattr(self, "live_action_workspace"):
            self._remove_thinking()
            self.live_action_workspace.show_response(
                visible, streaming=True, state="MORICE"
            )
            if not self.runtime.speech_input.status().listening:
                QTimer.singleShot(0, self._begin_voice_listening)
            self.runtime.realtime.mark_event(
                request_id,
                "first_visible_token",
                metadata={"surface": "live-action"},
            )
            self.runtime.realtime.mark_event(
                request_id,
                "ui_delta_displayed",
                metadata={"surface": "live-action"},
            )
            return
        if self._stream_bubble is None:
            # The first model token replaces the work-state bubble immediately;
            # this is the actual time-to-first-visible-response milestone.
            self._remove_thinking()
            row = self._create_message_row(MORICE_NAME, visible, False)
            self._stream_bubble = row.findChild(ChatBubble)
            self._virtualize_chat_widgets()
            self.runtime.realtime.mark_event(
                request_id,
                "first_visible_token",
                metadata={"surface": "chat"},
            )
        elif self._stream_bubble is not None:
            self._stream_bubble.set_message(visible)
        self.runtime.realtime.mark_event(
            request_id,
            "ui_delta_displayed",
            metadata={"surface": "chat"},
        )
        self._schedule_latest_scroll(force=True)

    def _on_assistant_stream_finished(
        self,
        request_id: str,
        message: str,
    ) -> None:
        final_message = str(message or "").strip()
        if (
            self.chat_mode == "voice"
            and request_id == self._stream_request_id
            and hasattr(self, "live_action_workspace")
        ):
            self._last_spoken_text = final_message
            self.live_action_workspace.finish_response(final_message)
            self._stream_request_id = ""
            self._stream_text = ""
            self._stream_bubble = None
            active_request = self.runtime.realtime.active_request
            if (
                not self._streamed_voice_reply_pending
                and active_request is not None
                and active_request.request_id == request_id
            ):
                self.runtime.realtime.finish_speech(active_request.epoch)
            self.append_message(MORICE_NAME, final_message, force_scroll=False)
            self._finish_response_delivery(
                MORICE_NAME,
                final_message,
                False,
                already_visible=True,
            )
            return
        if request_id != self._stream_request_id or self._stream_bubble is None:
            active_request = self.runtime.realtime.active_request
            if (
                not self._streamed_voice_reply_pending
                and active_request is not None
                and active_request.request_id == request_id
            ):
                self.runtime.realtime.finish_speech(active_request.epoch)
            self._on_message_ready(MORICE_NAME, final_message, False)
            return
        self._stream_bubble.set_message(final_message)
        self._stream_request_id = ""
        self._stream_text = ""
        self._stream_bubble = None
        active_request = self.runtime.realtime.active_request
        if (
            not self._streamed_voice_reply_pending
            and active_request is not None
            and active_request.request_id == request_id
        ):
            self.runtime.realtime.finish_speech(active_request.epoch)
        self._finish_response_delivery(
            MORICE_NAME,
            final_message,
            False,
            already_visible=True,
        )

    def _on_response_cancelled(self, request_id: str) -> None:
        active_request = self.runtime.realtime.active_request
        superseded = bool(
            active_request is not None
            and active_request.request_id != request_id
            and not active_request.cancellation.cancelled
        )
        if request_id == self._stream_request_id:
            if self._stream_bubble is not None and self._stream_text.strip():
                self._stream_bubble.set_message(
                    self._address(self._stream_text).rstrip() + "\n\n[Stopped]"
                )
            self._stream_request_id = ""
            self._stream_text = ""
            self._stream_bubble = None
        if superseded:
            return
        self._remove_thinking()
        self._complete_agent_ui(response_present=False, successful=False)
        self._set_busy(False)
        QTimer.singleShot(0, self._send_queued_message_if_ready)

    def _on_message_ready(self, author: str, message: str, is_user: bool = False):
        completed_bubble = self.thinking_bubble
        if completed_bubble is not None:
            completed_bubble.finish()
        self.append_message(author, message, is_user=is_user, force_scroll=True)
        self._finish_response_delivery(
            author,
            message,
            is_user,
            completed_bubble=completed_bubble,
        )

    def _finish_response_delivery(
        self,
        author: str,
        message: str,
        is_user: bool,
        *,
        completed_bubble: ThinkingBubble | None = None,
        already_visible: bool = False,
    ) -> None:
        if not is_user and author == MORICE_NAME:
            if self._streamed_voice_reply_pending:
                self._streamed_voice_reply_pending = False
            else:
                self._speak_assistant_text(message)
        if completed_bubble is not None:
            QTimer.singleShot(
                220,
                lambda bubble=completed_bubble: self._remove_thinking_widget(bubble),
            )
        self._record_activity(
            "Response completed",
            " ".join(message.split())[:240],
            category="chat",
        )
        self.runtime.plugins.publish_event(
            "chat.finished",
            {
                "author": author,
                "isUser": is_user,
                "characters": len(message),
            },
        )
        self._complete_agent_ui(response_present=bool(message))
        self._save_workspace_session()
        self._set_busy(False)
        QTimer.singleShot(120, self._send_queued_message_if_ready)

    def _on_thinking_update(self, detail: str):
        if self.thinking_bubble:
            self.thinking_bubble.set_detail(detail)
        if self.chat_mode == "voice" and hasattr(self, "live_action_workspace"):
            self.live_action_workspace.show_response(
                detail, streaming=True, state="WORKING"
            )

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
            self.access_status_btn,
            self.project_lookup_btn,
            self.title_bar,
            self.title_bar.sidebar_btn,
            self.title_bar.workspace_btn,
            self.title_bar.hub_btn,
            self.chat_container,
            self.input_frame,
            self.sidebar,
            self.mode_panel,
            self.workspace_panel,
            self.assistant_hub,
            self.changes_panel,
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
            self.attach_btn,
            self.voice_btn,
            self.model_selector_btn,
            self.project_selector_btn,
            self.quick_actions_btn,
            self.input,
            self.precision_btn,
            self.personalization_btn,
            self.access_status_btn,
            self.project_lookup_btn,
            self.send_btn,
        )

    def _configure_input_bar(self, centered: bool):
        if not hasattr(self, "input_frame"):
            return

        self.composer_centered = centered
        is_interacting = self.input.hasFocus() or self._input_hovered
        centered_state = "true" if centered else "false"
        hovered_state = "true" if is_interacting else "false"
        centered_changed = self.input_frame.property("centered") != centered_state
        hovered_changed = self.input_frame.property("hovered") != hovered_state
        self.input_frame.setProperty("centered", centered_state)
        self.input_frame.setProperty("hovered", hovered_state)
        self.input_frame.setMaximumWidth(820 if centered else 16777215)

        if self.input_glow is None:
            self.input_glow = QGraphicsDropShadowEffect(self.input_frame)
            self.input_glow.setOffset(0, 0)
            self.input_frame.setGraphicsEffect(self.input_glow)

        if centered:
            blur_radius = 104 if is_interacting else 86
            alpha = 228 if is_interacting else 190
        else:
            blur_radius = 60 if is_interacting else 40
            alpha = 184 if is_interacting else 112
        self._animate_input_glow(blur_radius, alpha)

        if centered_changed:
            for widget in self._composer_widgets():
                widget.style().unpolish(widget)
                widget.style().polish(widget)
        elif hovered_changed:
            self.input_frame.style().unpolish(self.input_frame)
            self.input_frame.style().polish(self.input_frame)

        if not getattr(self, "_composer_filters_installed", False):
            for widget in self._composer_widgets():
                widget.installEventFilter(self)
            self._composer_filters_installed = True

        QTimer.singleShot(0, self._update_composer_responsive_state)

    def _update_composer_responsive_state(self):
        """Keep centered composer commands legible in compact windows."""
        if not hasattr(self, "input_frame"):
            return

        available = self.input_frame.width()
        if available <= 0:
            return

        is_project = self.chat_mode == "project"
        is_voice = self.chat_mode == "voice"
        project_capable = is_project or is_voice
        if available >= 760:
            visible_tools = {
                self.attach_btn,
                self.voice_btn,
                self.model_selector_btn,
                self.project_selector_btn,
                self.quick_actions_btn,
            }
        elif available >= 620:
            visible_tools = {self.attach_btn, self.voice_btn}
        elif available >= 480:
            visible_tools = {self.attach_btn}
        else:
            visible_tools = set()

        for tool_button in (
            self.attach_btn,
            self.voice_btn,
            self.model_selector_btn,
            self.project_selector_btn,
            self.quick_actions_btn,
        ):
            tool_button.setVisible(tool_button in visible_tools)

        self.precision_btn.setVisible(available >= 480)
        self.personalization_btn.setVisible(not is_project and available >= 620)
        self.access_status_btn.setVisible(project_capable and available >= 760)
        self.project_lookup_btn.setVisible(project_capable and available >= 920)

        if available >= 620:
            self.input.setMinimumWidth(120)
        elif available >= 480:
            self.input.setMinimumWidth(92)
        else:
            self.input.setMinimumWidth(72)
        self.send_btn.setMinimumWidth(82 if available >= 480 else 64)

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
        if self.chat_mode == "voice":
            return
        if not self.composer_centered:
            return

        if not self.isVisible() or self.input_frame.width() <= 0 or self.input_frame.height() <= 0:
            self._dock_composer_immediate()
            return

        self._dock_composer_animated()

    def _cancel_composer_animation(self, finish: bool = False):
        animation = self._composer_anim
        if animation is None:
            return
        self._composer_anim = None
        animation.stop()
        if animation in self._anims:
            self._anims.remove(animation)
        if finish:
            self._finish_composer_dock(self._dock_placeholder)

    def _dock_composer_immediate(self):
        self._cancel_composer_animation()
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
        self._cancel_composer_animation(finish=True)
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
        fall_anim.setDuration(640)
        fall_anim.setEasingCurve(QEasingCurve.InCubic)
        fall_anim.setStartValue(start_rect)

        distance_y = target_rect.y() - start_rect.y()
        early_y = start_rect.y() + int(distance_y * 0.28)
        early_width = start_rect.width() + int((target_rect.width() - start_rect.width()) * 0.25)
        early_x = start_rect.x() + int((target_rect.x() - start_rect.x()) * 0.2)
        fall_anim.setKeyValueAt(
            0.46,
            QRect(early_x, early_y, early_width, target_rect.height()),
        )
        fall_anim.setKeyValueAt(
            0.74,
            QRect(target_rect.x() - 10, target_rect.y() + 13, target_rect.width(), target_rect.height()),
        )
        fall_anim.setKeyValueAt(
            0.88,
            QRect(target_rect.x() + 6, target_rect.y() - 5, target_rect.width(), target_rect.height()),
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
        if time.monotonic() < self._user_scroll_guard_until:
            self._last_scroll_max = maximum
            return
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
            if hasattr(self, "scroll") and (source is self.scroll.viewport() or source is self.chat_list):
                self._user_scroll_guard_until = time.monotonic() + 0.75
                QTimer.singleShot(0, self._sync_scroll_follow_state)
            return False
        if hasattr(self, "input_frame") and source in self._composer_widgets():
            if event.type() in (QEvent.Enter, QEvent.FocusIn):
                self._input_hovered = True
                self._configure_input_bar(centered=self.composer_centered)
            elif event.type() in (QEvent.Leave, QEvent.FocusOut):
                QTimer.singleShot(0, self._refresh_input_hover_from_cursor)
        return super().eventFilter(source, event)

    def _sync_scroll_follow_state(self):
        self.follow_latest = self._is_at_bottom()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._composer_anim is not None:
            # A layout target can move while the window is being resized. Finish
            # the transition cleanly instead of animating toward stale geometry.
            self._cancel_composer_animation(finish=True)
        if hasattr(self, "window_resize_grip"):
            margin = 4
            self.window_resize_grip.move(
                max(0, self.width() - self.window_resize_grip.width() - margin),
                max(0, self.height() - self.window_resize_grip.height() - margin),
            )
            self.window_resize_grip.raise_()
        if hasattr(self, "notification_toast") and self.notification_toast.isVisible():
            margin = 28
            self.notification_toast.move(
                max(margin, self.width() - self.notification_toast.width() - margin),
                margin,
            )
            self.notification_toast.raise_()
        if hasattr(self, "input_frame"):
            QTimer.singleShot(0, self._update_composer_responsive_state)
        self._schedule_latest_scroll()

    def showEvent(self, event):
        super().showEvent(event)
        if self._open_animation_played or not self._motion_enabled:
            return
        self._open_animation_played = True
        self.setWindowOpacity(0.0)
        QTimer.singleShot(
            0,
            lambda: self.animation_engine.window_opacity(
                self, 1.0, duration=180
            ),
        )

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() != QEvent.WindowStateChange:
            return
        old_state = event.oldState()
        if (
            old_state & Qt.WindowMinimized
            and not self.isMinimized()
            and self._motion_enabled
        ):
            self.setWindowOpacity(0.0)
            self.animation_engine.window_opacity(self, 1.0, duration=150)

    def on_send(self):
        ui_received_ns = time.perf_counter_ns()
        self.runtime.voice.interrupt("new-user-request")
        self.runtime.speech_input.cancel("transcript-submitted")
        self.runtime.live_vision.cancel("new-user-request")
        user_input = self.input.text().strip()
        if self.is_busy:
            if re.fullmatch(
                r"(?:stop|cancel|never mind|nevermind|stop that|cancel that)[.!? ]*",
                user_input.casefold(),
            ):
                active_request = self.runtime.realtime.active_request
                self.runtime.realtime.cancel_active("user stop")
                self.input.clear()
                self.append_message(
                    self.user_title,
                    user_input,
                    is_user=True,
                    force_scroll=True,
                )
                self.append_message(MORICE_NAME, self._address("Stopped."))
                if active_request is not None:
                    active_request.trace.mark_event("user_interrupt")
                    active_request.trace.mark_event("fast_response_visible")
                    self.runtime.realtime.finish_speech(active_request.epoch)
                self._remove_thinking()
                self._set_busy(False)
                return
            self.runtime.realtime.cancel_active("superseded by user")
            self._queue_steer_message()
            return
        if not user_input:
            return
        live_vision_waiting = False
        live_vision_result: VisionResult | None = None
        live_vision_timing: tuple[int, int] | None = None
        if self.chat_mode == "voice":
            live_vision_waiting, live_vision_result, live_vision_timing = (
                self._prepare_live_vision_request(user_input)
            )
            if live_vision_waiting:
                return
        submitted_ns = time.perf_counter_ns()
        self.follow_latest = True
        self.input.clear()
        self._prompt_history_index = -1
        self._dock_composer()
        self.append_message(self.user_title, user_input, is_user=True, force_scroll=True)
        transcript = self._pending_transcript
        self._pending_transcript = None
        initial_marks = {}
        request_started_ns = (
            live_vision_timing[0] if live_vision_timing is not None else ui_received_ns
        )
        request_source = "typed"
        if (
            transcript is not None
            and transcript.text.strip()
            and transcript.started_monotonic > 0
        ):
            request_source = "speech"
            request_started_ns = int(transcript.started_monotonic * 1_000_000_000)
            if transcript.speech_detected_ms is not None:
                initial_marks[LatencyStage.SPEECH_DETECTED] = request_started_ns + int(
                    transcript.speech_detected_ms * 1_000_000
                )
            if transcript.first_partial_ms is not None:
                initial_marks[LatencyStage.STT_FIRST_PARTIAL] = request_started_ns + int(
                    transcript.first_partial_ms * 1_000_000
                )
            initial_marks[LatencyStage.STT_FINAL] = request_started_ns + int(
                transcript.duration_ms * 1_000_000
            )
        realtime_request = self.runtime.realtime.begin_request(
            user_input,
            override_model=self.model_path or self.model_name,
            started_ns=request_started_ns,
            initial_marks=initial_marks,
            metadata={
                "projectMode": self._is_project_build_request(user_input),
                "source": request_source,
                "visionUsed": live_vision_result is not None,
                "modelUsed": False,
            },
            input_event="input_received",
        )
        realtime_request.trace.mark_event(
            "ui_request_received",
            at_ns=(
                live_vision_timing[0]
                if live_vision_timing is not None
                else ui_received_ns
            ),
        )
        realtime_request.trace.mark_event("text_submitted", at_ns=submitted_ns)
        if live_vision_timing is not None:
            realtime_request.trace.mark_event(
                "vision_started",
                at_ns=live_vision_timing[0],
            )
            realtime_request.trace.mark_event(
                "vision_completed",
                at_ns=live_vision_timing[1],
                metadata={
                    "durationMs": max(
                        0.0,
                        (live_vision_timing[1] - live_vision_timing[0])
                        / 1_000_000.0,
                    ),
                },
            )
        if request_source == "speech" and transcript is not None:
            if transcript.speech_end_ms is not None:
                realtime_request.trace.mark_event(
                    "speech_end",
                    at_ns=request_started_ns
                    + int(transcript.speech_end_ms * 1_000_000),
                )
            realtime_request.trace.mark_event(
                "transcript_final",
                at_ns=request_started_ns + int(transcript.duration_ms * 1_000_000),
                metadata={
                    "speechEndToFinalMs": transcript.speech_end_to_final_ms,
                },
            )
        self.user_messages.append(user_input)
        self.workspace_state.add_recent_chat(user_input)
        submission_metadata = {
            "mode": self.chat_mode,
            "characters": len(user_input),
            "projectFolder": self.project_folder if self._project_capable_mode() else "",
        }

        def record_submission() -> None:
            try:
                self.runtime.desktop.memory.add(
                    "temporary",
                    user_input,
                    tags=("chat", "user"),
                    temporary=True,
                )
                self.runtime.plugins.publish_event(
                    "memory.updated",
                    {"scope": "temporary", "source": "chat"},
                )
                self.runtime.plugins.publish_event("chat.started", submission_metadata)
            except (RuntimeError, TypeError, ValueError):
                return

        _start_background_task("chat-bookkeeping", record_submission)
        QTimer.singleShot(
            0,
            lambda text=" ".join(user_input.split())[:240]: self._record_activity(
                "Message sent",
                text,
                category="chat",
            ),
        )
        if not self.first_user_message:
            self.first_user_message = user_input
        image_path = self.pending_image_path
        if image_path:
            self.pending_image_path = ""
            self.append_message(self.user_title, f"Attached image: {os.path.basename(image_path)}", is_user=True)

        if live_vision_result is not None and not live_vision_result.success:
            self._append_direct_reply(
                user_input,
                live_vision_result.message
                or "I could not safely analyze the current camera frame.",
                address=False,
            )
            return

        wake_message = wake_up_response(user_input, self.wake_phrase, self.user_title)
        if wake_message:
            self._append_direct_reply(user_input, wake_message, address=False)
            self.awake = True
            self.runtime.plugins.publish_event(
                "voice.activated",
                {"source": "wake-phrase", "phrase": self.wake_phrase},
            )
            return

        if not self.awake:
            self._append_direct_reply(
                user_input,
                f"I am asleep, {self.user_title}. Say '{self.wake_phrase}'.",
                address=False,
            )
            return

        if self._handle_desktop_command(user_input):
            realtime_request.trace.mark_event("first_visible_token")
            realtime_request.trace.mark_event("fast_response_visible")
            self.runtime.realtime.complete_generation(realtime_request.epoch)
            self.runtime.realtime.finish_speech(realtime_request.epoch)
            self._save_workspace_session()
            return

        if live_vision_result is not None and live_vision_result.success:
            lower_input = user_input.casefold()
            visual_subject = (
                live_vision_result.extracted_text.strip()
                or live_vision_result.summary.strip()
            )
            if re.search(r"\bcopy\s+(?:it|this|that|the text)\b", lower_input):
                QApplication.clipboard().setText(visual_subject)
                self._append_direct_reply(
                    user_input,
                    "Copied the processed visual text to the clipboard."
                    if live_vision_result.extracted_text.strip()
                    else "Copied the processed visual description to the clipboard.",
                    address=False,
                )
                return
            if visual_subject and re.search(
                r"\b(?:search|look up)\s+(?:it|this|that|the text)\b",
                lower_input,
            ):
                if self._handle_natural_pc_control(
                    f"search the web for {visual_subject}"
                ):
                    self._save_workspace_session()
                    return

        if self._handle_natural_pc_control(user_input):
            self._save_workspace_session()
            return

        summon_message = summon_response(user_input, self.user_title)
        if summon_message:
            self._append_direct_reply(user_input, summon_message, address=False)
            return

        riddle_reply = riddle_response(user_input)
        if riddle_reply:
            self._append_direct_reply(user_input, riddle_reply)
            return

        emotional_reply = emotional_checkin_response(user_input, self.user_title)
        if emotional_reply:
            self._append_direct_reply(user_input, emotional_reply)
            return

        father_reply = father_identity_response(user_input, self.user_title)
        if father_reply:
            self._append_direct_reply(user_input, father_reply)
            return

        harmful_reply = harmful_request_response(user_input, self.user_title)
        if harmful_reply:
            self._append_direct_reply(user_input, harmful_reply, address=False)
            return

        datetime_reply = current_datetime_response(user_input)
        if datetime_reply:
            self._append_direct_reply(user_input, datetime_reply)
            return

        if wants_first_message(user_input) and self.first_user_message:
            self._append_direct_reply(user_input, self.first_user_message)
            return

        prior_user_messages = self.user_messages[:-1]
        if wants_previous_user_message(user_input):
            previous_message = previous_user_message(prior_user_messages)
            reply = (
                f'Your previous message was: "{previous_message}"'
                if previous_message
                else "There is no previous user message in this chat yet."
            )
            self._append_direct_reply(user_input, reply)
            return

        if wants_memory_list(user_input):
            recent = prior_user_messages[-5:]
            if recent:
                self._append_direct_reply(user_input, " | ".join(recent))
            else:
                self._append_direct_reply(user_input, "No earlier messages yet.")
            return

        if wants_memory_search(user_input):
            terms = extract_memory_terms(user_input)
            matches = []
            for msg in reversed(prior_user_messages):
                if all(term in msg.lower() for term in terms):
                    matches.append(msg)
                if len(matches) >= 3:
                    break
            if matches:
                self._append_direct_reply(user_input, " | ".join(matches))
            else:
                self._append_direct_reply(user_input, "I do not see that in your earlier messages.")
            return

        if is_acknowledgement(user_input):
            self._append_direct_reply(user_input, "Understood.")
            return

        capability_topic = detect_capability_topic(user_input)
        if capability_topic:
            self._append_direct_reply(
                user_input,
                capability_answer(capability_topic, self.emoji_level),
            )
            return

        if wants_help(user_input):
            self._append_direct_reply(user_input, help_text())
            return

        if wants_model_identity(user_input):
            self._append_direct_reply(user_input, self._model_status_line())
            return

        if wants_precision_on(user_input):
            self._set_precision_state(True)
            self._append_direct_reply(user_input, "Precision mode enabled.")
            return

        if wants_precision_off(user_input):
            self._set_precision_state(False)
            self._append_direct_reply(user_input, "Precision mode disabled.")
            return

        if wants_math_steps_on(user_input):
            self.math_steps_mode = True
            self._append_direct_reply(user_input, "Math steps mode enabled.")
            return

        if wants_math_steps_off(user_input):
            self.math_steps_mode = False
            self._append_direct_reply(user_input, "Math steps mode disabled.")
            return

        if wants_unity_movement(user_input):
            if wants_unity_3d(user_input):
                script = unity_3d_movement_script()
            else:
                script = unity_2d_movement_script()
            self._append_direct_reply(
                user_input,
                f"{self.user_title}, here is the script.\n{script}",
                address=False,
            )
            return

        if wants_html_cube_movement(user_input):
            self._append_direct_reply(
                user_input,
                f"{self.user_title}, here is the script.\n{html_cube_movement_script()}",
                address=False,
            )
            return

        # A simulation prompt can contain a bare number (for example, "80 particles").
        # Keep it out of the quick-math path so the live physics workspace receives it.
        if not self.math_steps_mode and not wants_steps_detail(user_input) and not is_science_request(user_input):
            math_result = compute_math(user_input)
            if math_result is not None:
                self._append_direct_reply(user_input, shorten_reply(math_result))
                return

        if wants_notes_search(user_input):
            term = extract_notes_term(user_input)
            if term:
                hits = search_notes(term, max_hits=5)
                self.last_notes_hits = hits
                self.last_notes_term = term
                if hits:
                    details = "\n".join(
                        f"{hit['source']}: {hit['text']}" for hit in hits
                    )
                    self._append_direct_reply(
                        user_input,
                        f"Found {len(hits)} match(es) for {term}.\n\n{details}",
                    )
                else:
                    self._append_direct_reply(
                        user_input,
                        f"No matches for {term} in notes.",
                    )
                return

        if wants_notes_summary(user_input) and self.last_notes_hits:
            summary = summarize_notes_hits(self.last_notes_hits)
            self._append_direct_reply(user_input, summary)
            return

        if self._handle_science_request(user_input):
            realtime_request.trace.mark_event("first_visible_token")
            self.runtime.realtime.complete_generation(realtime_request.epoch)
            self.runtime.realtime.finish_speech(realtime_request.epoch)
            return

        retry_project_request = self._is_project_retry_request(user_input)
        project_source_input = self.last_project_request if retry_project_request else user_input
        project_build_request = retry_project_request or self._is_project_build_request(user_input)
        if project_build_request and not retry_project_request:
            self.last_project_request = user_input
        if project_build_request and not self._ensure_project_folder_for_build():
            self._append_direct_reply(
                user_input,
                "Choose a work folder with the + button, then I can create and edit the project files there.",
            )
            return

        project_online_lookup = project_build_request and self.project_lookup_mode == "online"
        web_decision_for_status = infer_web_need(user_input)
        self._set_busy(True)
        self._show_thinking(
            "Received your message and started the reply pipeline."
        )
        self._emit_background(
            "thinking_update",
            "Collecting live web context, then asking the selected local engine."
            if web_decision_for_status.required
            else (
                "Online+local Project mode: collecting web context, then building files."
                if project_online_lookup
                else (
                    "Local Project mode: using the selected folder and local model to build files."
                    if project_build_request
                    else "Using the fastest relevant local context path."
                )
            )
        )

        def worker():
            try:
                realtime_request.trace.mark_event("worker_started")
                realtime_request.trace.mark_event("context_started")
                agent_request_id = self._prepare_agent_request(
                    project_source_input if project_build_request else user_input,
                    include_project=project_build_request,
                )
                request_spec = (
                    analyze_project_request(
                        project_source_input,
                        self._project_has_files(),
                    )
                    if project_build_request
                    else None
                )
                if request_spec is not None and request_spec.subject == "flappy bird":
                    fast_manifest = build_project_fallback_manifest(
                        project_source_input,
                        self.project_folder,
                    )
                    if fast_manifest:
                        self._emit_background(
                            "thinking_update",
                            "Building the verified Flappy Bird project locally.",
                        )
                        project_result = self._apply_project_manifest(
                            fast_manifest,
                            project_source_input,
                            preview_only=self._project_patch_requires_review(),
                        )
                        visible_reply = project_result["message"]
                        self.history.append(
                            {"role": "user", "content": user_input}
                        )
                        self.history.append(
                            {"role": "assistant", "content": visible_reply}
                        )
                        self.runtime.realtime.mark(
                            realtime_request.request_id,
                            LatencyStage.CONTEXT_ASSEMBLED,
                        )
                        self.runtime.realtime.mark(
                            realtime_request.request_id,
                            LatencyStage.INFERENCE_BEGAN,
                        )
                        self.runtime.realtime.complete_generation(
                            realtime_request.epoch
                        )
                        self.runtime.realtime.finish_speech(
                            realtime_request.epoch
                        )
                        self._emit_background(
                            "project_changes_ready",
                            project_result["summary"],
                            project_result["diff_html"],
                        )
                        self._emit_background(
                            "message_ready",
                            MORICE_NAME,
                            self._address(visible_reply),
                            False,
                        )
                        return
                self._emit_background(
                    "thinking_update",
                    "Checking saved response style and local context.",
                )
                context_input = project_source_input if project_build_request else user_input
                context = retrieve_context(context_input) if should_use_context(context_input) else ""
                web_context = ""
                web_decision = infer_web_need(user_input)
                auto_project_web = project_build_request and self.project_lookup_mode == "online"
                web_offline = False
                if os.getenv("MORICE_WEB", "1") == "1" and (web_decision.required or auto_project_web):
                    search_query = web_decision.query or project_source_input
                    if internet_available():
                        self._emit_background(
                            "thinking_update",
                            "Searching live sources because the answer needs current or external information.",
                        )
                        web_context = search_web(search_query)
                        if not web_context:
                            web_context = "Web lookup returned no results."
                    else:
                        web_offline = True
                        self._emit_background(
                            "thinking_update",
                            "Internet is unavailable; continuing with local model, notes, and tools.",
                        )

                model_history = select_recent_history(
                    self.history,
                    max_messages=24 if project_build_request else 16,
                    max_chars=24_000 if project_build_request else 12_000,
                )
                extra_system = saved_settings_instruction(
                    self.user_title,
                    self.response_style,
                    emoji_preference_instruction(self.emoji_level),
                    maturity_preference_instruction(self.maturity_level),
                )
                reference_instruction = conversation_reference_instruction(
                    user_input,
                    model_history,
                    self.user_messages[:-1],
                )
                if reference_instruction:
                    extra_system += "\n\n" + reference_instruction
                if live_vision_result is not None:
                    extra_system += "\n\n" + live_vision_result.context_text()
                if self.chat_mode == "project" or (
                    self.chat_mode == "voice" and project_build_request
                ):
                    self._emit_background(
                        "thinking_update",
                        "Project builder mode: applying workspace, access, and coding rules.",
                    )
                    extra_system += "\n\n" + self._project_builder_system()
                    if project_build_request:
                        self._emit_background(
                            "thinking_update",
                            "Reading the work folder so edits can be applied directly.",
                        )
                        extra_system += "\n\n" + self._agent_project_prompt_context(
                            agent_request_id
                        )
                        extra_system += "\n\n" + self._project_manifest_instruction(project_source_input)
                if image_path:
                    self._emit_background(
                        "thinking_update",
                        "Reading attached image context.",
                    )
                    image_context = describe_image(image_path)
                    lowered = image_context.lower()
                    if any(key in lowered for key in {"not available", "not found", "could not open"}):
                        self._emit_background(
                            "message_ready",
                            MORICE_NAME,
                            self._address(image_context),
                            False,
                        )
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
                elif web_offline:
                    extra_system = (extra_system + "\n\n" if extra_system else "") + (
                        "Internet access is currently unavailable. Use local context only and "
                        "state plainly when a live fact cannot be verified."
                    )

                self.runtime.realtime.mark(
                    realtime_request.request_id,
                    LatencyStage.CONTEXT_ASSEMBLED,
                )
                realtime_request.trace.mark_event("context_completed")

                self._emit_background(
                    "thinking_update",
                    "Asking Qwen for project files."
                    if project_build_request
                    else "Asking Qwen to compose the final answer."
                )
                model_user_input = user_input
                if project_build_request:
                    model_history = model_history[-8:]
                    model_user_input = (
                        "Create or update the current project files for the authoritative request below. "
                        "Use the existing project snapshot and recent project conversation to preserve prior work. "
                        "Return only the required JSON manifest with complete file contents.\n\n"
                        f"{project_request_contract(project_source_input, self._project_has_files())}\n\n"
                        f"AUTHORITATIVE_USER_REQUEST:\n{project_source_input}"
                    )
                completion_started = time.perf_counter()
                self.runtime.realtime.mark(
                    realtime_request.request_id,
                    LatencyStage.INFERENCE_BEGAN,
                )
                realtime_request.trace.annotate(modelUsed=True)

                def model_telemetry(event: str, payload: dict) -> None:
                    data = dict(payload or {})
                    at_ns = int(data.pop("atNs", time.perf_counter_ns()))
                    if event == "prompt_assembled":
                        realtime_request.trace.set_counter(
                            "promptCharacters", int(data.get("characters") or 0)
                        )
                        realtime_request.trace.set_counter(
                            "promptEstimatedTokens",
                            int(data.get("estimatedTokens") or 0),
                        )
                        realtime_request.trace.set_counter(
                            "promptMessages", int(data.get("messages") or 0)
                        )
                    elif event == "model_usage":
                        usage = data.get("usage")
                        if isinstance(usage, dict):
                            for source, target in (
                                ("prompt_tokens", "promptTokens"),
                                ("completion_tokens", "completionTokens"),
                                ("total_tokens", "totalTokens"),
                            ):
                                value = usage.get(source)
                                if isinstance(value, (int, float)):
                                    realtime_request.trace.set_counter(
                                        target, int(value)
                                    )
                        realtime_request.trace.annotate(modelTelemetry=data)
                    marked = realtime_request.trace.mark_event(
                        event,
                        at_ns=at_ns,
                        metadata=data,
                    )
                    if event == "model_request_submitted" and marked:
                        realtime_request.trace.increment("modelCallCount")

                voice_stream: BoundedSpeechStream | None = None
                voice_handle = None
                voice_submitted_ns: int | None = None
                voice_status = self.runtime.voice.status()
                stream_voice = bool(
                    self.chat_mode == "voice"
                    and not project_build_request
                    and self.runtime.voice.config.enabled
                    and voice_status.api_configured
                )

                def submit_voice_chunks(chunks) -> None:
                    nonlocal voice_stream, voice_handle, voice_submitted_ns
                    if not stream_voice:
                        return
                    for chunk in chunks:
                        spoken = str(getattr(chunk, "spoken_text", "") or "").strip()
                        if not spoken:
                            continue
                        if voice_stream is None:
                            voice_stream = BoundedSpeechStream(max_chunks=8)
                            voice_submitted_ns = time.perf_counter_ns()
                            realtime_request.trace.mark_event(
                                "first_speakable_chunk",
                                at_ns=voice_submitted_ns,
                                metadata={"characters": len(spoken)},
                            )
                            realtime_request.trace.mark(
                                LatencyStage.TTS_CHUNK_RECEIVED,
                                at_ns=voice_submitted_ns,
                            )
                            realtime_request.trace.mark_event(
                                "tts_submitted",
                                at_ns=voice_submitted_ns,
                            )
                            voice_stream.put(spoken)
                            voice_handle = self.runtime.voice.speak_chunks(
                                voice_stream,
                                request_id=realtime_request.request_id,
                                on_event=self._voice_trace_callback(
                                    realtime_request
                                ),
                            )
                            self._streamed_voice_reply_pending = True
                        else:
                            voice_stream.put(spoken)
                        realtime_request.trace.increment("ttsChunksQueued")

                reply_parts: list[str] = []
                visible_model_text_started = False
                try:
                    with self.runtime.profiler.measure("completion", "model"):
                        for delta in stream_chat(
                            model_history,
                            model_user_input,
                            extra_system=extra_system,
                            model=self.model_name or None,
                            timeout=180,
                            precision_mode=self.precision_mode,
                            math_steps_mode=self.math_steps_mode
                            or wants_steps_detail(user_input),
                            gguf_path=self.model_path,
                            cancel_event=realtime_request.cancellation.event,
                            max_tokens=(
                                4_096
                                if project_build_request
                                else realtime_request.route.max_output_tokens
                            ),
                            enable_reasoning=(
                                project_build_request
                                or realtime_request.route.tier is ModelTier.DEEP
                            ),
                            telemetry=model_telemetry,
                        ):
                            if not self.runtime.realtime.is_current(
                                realtime_request.epoch
                            ):
                                break
                            clean_delta = str(delta or "")
                            if not clean_delta:
                                continue
                            reply_parts.append(clean_delta)
                            speech_chunks = self.runtime.realtime.accept_delta(
                                realtime_request.epoch,
                                clean_delta,
                            )
                            submit_voice_chunks(speech_chunks)
                            if not visible_model_text_started:
                                visible_model_text_started = bool(clean_delta.strip())
                            if not visible_model_text_started:
                                continue
                            if not project_build_request:
                                realtime_request.trace.mark_event(
                                    "ui_delta_queued"
                                )
                                self._emit_background(
                                    "assistant_stream_delta",
                                    realtime_request.request_id,
                                    clean_delta,
                                )

                    if realtime_request.cancellation.cancelled:
                        self.runtime.realtime.finish_speech(realtime_request.epoch)
                        self._emit_background(
                            "response_cancelled",
                            realtime_request.request_id,
                        )
                        return

                    final_speech_chunks = self.runtime.realtime.complete_generation(
                        realtime_request.epoch
                    )
                    submit_voice_chunks(final_speech_chunks)
                finally:
                    if voice_stream is not None:
                        voice_stream.close()
                        realtime_request.trace.set_counter(
                            "ttsQueuePeakDepth", voice_stream.peak_depth
                        )
                        realtime_request.trace.set_counter(
                            "ttsChunksCoalesced", voice_stream.coalesced_chunks
                        )
                if voice_handle is not None:
                    def finish_streamed_speech():
                        result = voice_handle.wait()
                        if (
                            result is not None
                            and voice_submitted_ns is not None
                            and result.metrics.request_to_first_audio_ms is not None
                        ):
                            realtime_request.trace.annotate(
                                ttsMetrics={
                                    "queueWaitMs": result.metrics.queue_wait_ms,
                                    "providerToFirstAudioMs": (
                                        result.metrics.provider_to_first_audio_ms
                                    ),
                                    "playbackStartupMs": (
                                        result.metrics.playback_startup_ms
                                    ),
                                    "streamedBeforeTextComplete": (
                                        result.metrics.streamed_before_text_complete
                                    ),
                                }
                            )
                            first_audio_ns = voice_submitted_ns + int(
                                result.metrics.request_to_first_audio_ms * 1_000_000
                            )
                            realtime_request.trace.mark(
                                LatencyStage.FIRST_AUDIO_GENERATED,
                                at_ns=first_audio_ns,
                            )
                            realtime_request.trace.mark_event(
                                "first_audio_generated",
                                at_ns=first_audio_ns,
                            )
                            audible_ns = first_audio_ns + int(
                                (result.metrics.playback_startup_ms or 0.0)
                                * 1_000_000
                            )
                            realtime_request.trace.mark(
                                LatencyStage.FIRST_AUDIO_AUDIBLE,
                                at_ns=audible_ns,
                            )
                            realtime_request.trace.mark_event(
                                "first_audio_audible",
                                at_ns=audible_ns,
                            )
                        self.runtime.realtime.finish_speech(
                            realtime_request.epoch
                        )
                        self._emit_background(
                            "speech_playback_finished",
                            result,
                        )

                    _start_background_task(
                        "voice-trace",
                        finish_streamed_speech,
                    )

                reply = "".join(reply_parts)
                model_returned_text = bool(str(reply or "").strip())
                reply = ensure_visible_response(reply)
                completion_ms = (time.perf_counter() - completion_started) * 1000
                estimated_tps = self.runtime.profiler.record_model_completion(
                    len(reply),
                    completion_ms,
                )
                self.runtime.logs.log(
                    "INFO",
                    "Model completion finished.",
                    category="model",
                    metadata={
                        "projectMode": project_build_request,
                        "replyCharacters": len(reply),
                        "emptyCompletion": not model_returned_text,
                        "durationMs": completion_ms,
                        "estimatedTokensPerSecond": estimated_tps,
                    },
                )
                if agent_request_id:
                    self.runtime.agent.record_model_result(
                        agent_request_id,
                        success=model_returned_text,
                        latency_ms=completion_ms,
                        prompt_tokens=max(1, len(model_user_input) // 4),
                        generated_tokens=max(1, len(reply) // 4),
                        gpu_layers=int(os.getenv("MORICE_GPU_LAYERS", "0") or 0),
                        error="" if model_returned_text else "The selected model returned an empty completion.",
                    )
                visible_reply = reply
                if project_build_request:
                    project_result = None
                    apply_error = ""
                    self._emit_background(
                        "thinking_update",
                        "Applying generated files to the selected work folder.",
                    )
                    try:
                        project_result = self._apply_project_manifest(
                            reply,
                            project_source_input,
                            preview_only=self._project_patch_requires_review(),
                        )
                    except Exception as exc:  # noqa: BLE001
                        apply_error = str(exc)

                    if not project_result and self._project_output_worth_repairing(reply):
                        self._emit_background(
                            "thinking_update",
                            "Converting the model output into a safe file manifest.",
                        )
                        repair_prompt = (
                            "Turn this project request into the required JSON file manifest only. "
                            "Include complete file contents and relative paths.\n\n"
                            f"User request:\n{project_source_input}\n\n"
                            f"Previous model output:\n{reply}"
                        )
                        try:
                            repair_reply = "".join(
                                stream_chat(
                                    [],
                                    repair_prompt,
                                    extra_system=extra_system
                                    + "\n\n"
                                    + self._project_manifest_instruction(
                                        project_source_input
                                    ),
                                    model=self.model_name or None,
                                    timeout=180,
                                    precision_mode=True,
                                    math_steps_mode=False,
                                    gguf_path=self.model_path,
                                    cancel_event=(
                                        realtime_request.cancellation.event
                                    ),
                                )
                            )
                            if realtime_request.cancellation.cancelled:
                                self.runtime.realtime.finish_speech(
                                    realtime_request.epoch
                                )
                                self._emit_background(
                                    "response_cancelled",
                                    realtime_request.request_id,
                                )
                                return
                            project_result = self._apply_project_manifest(
                                repair_reply,
                                project_source_input,
                                preview_only=self._project_patch_requires_review(),
                            )
                        except Exception as exc:  # noqa: BLE001
                            apply_error = str(exc)

                    if not project_result:
                        self._emit_background(
                            "thinking_update",
                            "Using MORICE's local Project fallback builder.",
                        )
                        try:
                            fallback_manifest = build_project_fallback_manifest(
                                project_source_input,
                                self.project_folder,
                            )
                            if fallback_manifest:
                                project_result = self._apply_project_manifest(
                                    fallback_manifest,
                                    project_source_input,
                                    preview_only=self._project_patch_requires_review(),
                                )
                                if project_result:
                                    project_result["summary"] = (
                                        project_result["summary"]
                                        + " Built with MORICE's local fallback builder."
                                    )
                                    project_result["message"] += (
                                        "\n\nNotes:\n- MORICE used its local fallback builder because the model did not return safe project JSON."
                                    )
                        except Exception as exc:  # noqa: BLE001
                            apply_error = str(exc)

                    if project_result:
                        visible_reply = project_result["message"]
                        self._emit_background(
                            "project_changes_ready",
                            project_result["summary"],
                            project_result["diff_html"],
                        )
                    else:
                        detail = f" Error: {apply_error}" if apply_error else ""
                        folder_hint = (
                            "Choose a work folder with the + button, then try a direct build request."
                            if not self.project_folder
                            else "Try a more direct build request, or switch the selected model to a stronger coding GGUF."
                        )
                        visible_reply = f"I could not safely turn that request into project files yet.{detail}\n\n{folder_hint}"
                else:
                    visible_reply = self.visualization_manager.sanitize_model_reply(visible_reply)
                    visible_reply = ensure_visible_response(visible_reply)
                if project_build_request:
                    self.runtime.realtime.finish_speech(
                        realtime_request.epoch
                    )
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": visible_reply})
                try:
                    self.runtime.platform_services.orchestrator.remember_interaction(
                        user_input,
                        visible_reply,
                        project_root=(
                            self.project_folder
                            if self._project_capable_mode()
                            and os.path.isdir(self.project_folder)
                            else ""
                        ),
                        metadata={
                            "mode": self.chat_mode,
                            "requestId": agent_request_id,
                            "runId": self._active_platform_run_id,
                        },
                    )
                except (OSError, RuntimeError, TypeError, ValueError):
                    pass
                if project_build_request:
                    self._emit_background(
                        "message_ready",
                        MORICE_NAME,
                        self._address(visible_reply),
                        False,
                    )
                else:
                    self._emit_background(
                        "assistant_stream_finished",
                        realtime_request.request_id,
                        self._address(visible_reply),
                    )
            except Exception as exc:  # noqa: BLE001
                if realtime_request is not None:
                    realtime_request.cancellation.cancel("pipeline-error")
                    self.runtime.realtime.finish_speech(
                        realtime_request.epoch
                    )
                if self._active_agent_request_id:
                    self.runtime.agent.record_model_result(
                        self._active_agent_request_id,
                        success=False,
                        latency_ms=0,
                        error=str(exc),
                        gpu_layers=int(os.getenv("MORICE_GPU_LAYERS", "0") or 0),
                    )
                self.runtime.logs.log(
                    "ERROR",
                    f"Chat reply failed: {exc}",
                    category="model",
                )
                self._complete_agent_ui(response_present=False, successful=False)
                self._emit_background(
                    "assistant_stream_finished",
                    realtime_request.request_id,
                    self._address(f"I hit an app error: {exc}"),
                )

        _start_background_task("chat-reply", worker)

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

    def closeEvent(self, event):
        self._is_closing = True
        set_voice_session_active(False)
        self._save_workspace_session()
        self._save_recovery_snapshot()
        if (
            self._motion_enabled
            and self.isVisible()
            and not self._closing_after_animation
        ):
            self._closing_after_animation = True
            event.ignore()
            self.setEnabled(False)
            self.animation_engine.fade(
                self,
                False,
                duration=160,
                finished=self.close,
            )
            return
        self.recovery_timer.stop()
        if self.project_folder:
            self.runtime.plugins.publish_event(
                "project.closed",
                {"path": self.project_folder},
            )
        if hasattr(self, "_monitor_callback"):
            self.runtime.desktop.system_monitor.unsubscribe(self._monitor_callback)
        if hasattr(self, "premium_settings_dialog"):
            self.premium_settings_dialog.close()
        self.plugin_center.shutdown()
        self.diagnostics_dialog.close()
        self.visualization_manager.shutdown()
        if hasattr(self, "live_camera"):
            self.live_camera.shutdown()
        self.animation_engine.stop_all()
        super().closeEvent(event)
        if self._owns_runtime_lifecycle:
            application = QApplication.instance()
            if application is not None:
                QTimer.singleShot(0, application.quit)


def _show_window_for_launch(window: QWidget, environ: dict[str, str] | None = None) -> bool:
    """Show an ordinary launch normally and a wake launch without activation."""

    environment = os.environ if environ is None else environ
    background_wake = str(environment.get("MORICE_BACKGROUND_WAKE", "")).strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if background_wake:
        window.setAttribute(Qt.WA_ShowWithoutActivating, True)
        window.showMinimized()
    else:
        window.show()
    return background_wake


def run_app():
    _set_windows_app_id()
    # Publish the UI identity before model/runtime prewarm. The background
    # listener can otherwise observe a long cold start as "no app" and launch
    # duplicate hidden copies while a game or media audio is still playing.
    set_app_session_active(True)
    runtime = get_runtime_services()
    recovery_info = runtime.start()
    app = QApplication(sys.argv)
    _load_ui_fonts()
    app.setApplicationName("MORICE")
    app.setApplicationDisplayName("MORICE")
    app.setOrganizationName("EONASH2722")
    icon_path = _icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MoriceWindow(runtime, recovery_info)
    health_report = window._run_startup_health_check()
    if health_report.critical_failures:
        failure_text = "\n".join(
            f"- {check.name}: {check.detail}"
            for check in health_report.critical_failures
        )
        QMessageBox.critical(
            window,
            "MORICE startup health check failed",
            "MORICE cannot start safely because required components failed:\n\n"
            + failure_text,
        )
        set_app_session_active(False)
        runtime.shutdown(clean=True)
        return 2
    _show_window_for_launch(window)
    try:
        return app.exec()
    finally:
        set_app_session_active(False)
        reset_model_runtime()
        runtime.shutdown(clean=True)


if __name__ == "__main__":
    raise SystemExit(run_app())
