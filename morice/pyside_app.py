import os
import sys
import threading
import ctypes
import html
import json
import math
import re
import difflib
import time
import subprocess
from ctypes import wintypes

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
)
from PySide6.QtGui import (
    QFont,
    QFontDatabase,
    QBrush,
    QColor,
    QIcon,
    QCursor,
    QPainter,
    QPen,
    QPainterPath,
    QLinearGradient,
    QRadialGradient,
)
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
    QSizeGrip,
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
)
from .knowledge import KB_DIR, load_knowledge, retrieve_context, should_use_context, should_preload, search_notes
from .llm_client import chat
from .llm_client import reset_model_runtime
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
from .project_builder import build_project_fallback_manifest
from .project_runtime import (
    ProjectValidationError,
    build_launch_plan,
    build_run_script,
    detect_python_requirements,
    launch_project,
    validate_project_file,
)
from .science_engine import GraphArtifact, PhysicsArtifact, ScienceArtifact, build_science_artifact, is_science_request
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
    normalize_user_title,
    normalize_wake_phrase,
    normalize_response_style,
    save_settings,
    wake_signal_path,
)
from .web_search import search_web
from .vision import describe_image

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
        app_id = "EONASH2722.MORICE.Desktop"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


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
                font-family: "Segoe UI";
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

    def __init__(self, parent=None, gpu_profile: GpuProfile | None = None):
        super().__init__(parent)
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
            ("Hermes test", "hermes 3 8b"),
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
                font-family: "Segoe UI";
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
            self.gpu_detected.emit(profile)

        threading.Thread(target=worker, daemon=True).start()

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
            self.search_finished.emit(results, error)

        threading.Thread(target=worker, daemon=True).start()

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
            self.download_progress.emit(percent, message)

        def worker():
            try:
                path = download_model_result(result, default_model_download_dir(), progress)
                error = ""
            except Exception as exc:  # noqa: BLE001
                path = ""
                error = str(exc)
            self.download_finished.emit(path, error)

        threading.Thread(target=worker, daemon=True).start()

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
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()

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
        plot = self.rect().adjusted(46, 26, -18, -38)
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
        plot = rect.adjusted(46, 26, -18, -38)
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

        for series in self.artifact.series:
            marker_color = QColor(series.color)
            for inspection in series.inspection_points[:5]:
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
                label = str(inspection.get("label") or "point")
                value = f"{ix:.3g}, {iy:.3g}"
                text = f"{label}\n{value}"
                metrics = painter.fontMetrics()
                width = max(metrics.horizontalAdvance(label), metrics.horizontalAdvance(value)) + 26
                height = metrics.height() * 2 + 16
                bubble_x = point.x() + 14
                bubble_y = point.y() - height - 10
                if bubble_x + width > plot.right():
                    bubble_x = point.x() - width - 14
                if bubble_y < plot.top():
                    bubble_y = point.y() + 14
                bubble = QRect(bubble_x, bubble_y, width, height)
                pointer = QPainterPath()
                pointer.addRoundedRect(bubble, 14, 14)
                painter.setPen(QPen(QColor(125, 210, 255, 130), 1))
                painter.setBrush(QColor(0, 145, 255, 230))
                painter.drawPath(pointer)
                painter.setPen(QColor(255, 255, 255, 245))
                painter.drawText(bubble.adjusted(8, 4, -8, -4), Qt.AlignCenter, text)

        painter.setPen(QColor(255, 255, 255, 218))
        painter.drawText(rect.adjusted(12, 6, -12, -6), Qt.AlignTop | Qt.AlignLeft, self.artifact.title)
        painter.setPen(QColor(180, 205, 255, 160))
        painter.drawText(
            rect.adjusted(12, 0, -12, -10),
            Qt.AlignBottom | Qt.AlignLeft,
            f"x {x0:.2g}..{x1:.2g} | y {y0:.2g}..{y1:.2g} | wheel zoom, drag pan",
        )


class PhysicsCanvas(QWidget):
    stats_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("PhysicsCanvas")
        self.setMinimumHeight(300)
        self.artifact: PhysicsArtifact | None = None
        self.running = True
        self.speed = 1.0
        self._collisions = 0
        self._frames = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.step)
        self._timer.start(16)

    def set_artifact(self, artifact: PhysicsArtifact | None):
        self.artifact = artifact
        self._collisions = 0
        self._frames = 0
        self.running = True
        self.update()

    def set_running(self, running: bool):
        self.running = running

    def set_speed(self, speed: float):
        self.speed = max(0.05, min(5.0, speed))

    def step_once(self):
        self._advance()
        self.update()

    def step(self):
        if self.running:
            self._advance()
            self.update()

    def _advance(self):
        if not self.artifact:
            return
        width, height = self.artifact.bounds
        dt = 1 / 60 * self.speed
        particles = self.artifact.particles
        frame_collisions = 0
        for particle in particles:
            particle.vy += self.artifact.gravity * dt
            particle.vx *= self.artifact.friction
            particle.vy *= self.artifact.friction
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            if particle.x - particle.radius < 0:
                particle.x = particle.radius
                particle.vx = abs(particle.vx) * 0.82
                frame_collisions += 1
            elif particle.x + particle.radius > width:
                particle.x = width - particle.radius
                particle.vx = -abs(particle.vx) * 0.82
                frame_collisions += 1
            if particle.y - particle.radius < 0:
                particle.y = particle.radius
                particle.vy = abs(particle.vy) * 0.82
                frame_collisions += 1
            elif particle.y + particle.radius > height:
                particle.y = height - particle.radius
                particle.vy = -abs(particle.vy) * 0.82
                frame_collisions += 1

        if len(particles) <= 220:
            for i, first in enumerate(particles):
                for second in particles[i + 1 :]:
                    dx = second.x - first.x
                    dy = second.y - first.y
                    min_dist = first.radius + second.radius
                    dist_sq = dx * dx + dy * dy
                    if 0 < dist_sq < min_dist * min_dist:
                        dist = math.sqrt(dist_sq)
                        nx = dx / dist
                        ny = dy / dist
                        overlap = (min_dist - dist) * 0.5
                        first.x -= nx * overlap
                        first.y -= ny * overlap
                        second.x += nx * overlap
                        second.y += ny * overlap
                        first.vx, second.vx = second.vx * 0.88, first.vx * 0.88
                        first.vy, second.vy = second.vy * 0.88, first.vy * 0.88
                        frame_collisions += 1

        self._collisions += frame_collisions
        self._frames += 1
        if self._frames % 20 == 0:
            stats = (
                f"Particles: {len(particles)} | FPS target: 60 | "
                f"Collisions/sec: {int((self._collisions / max(1, self._frames)) * 60)} | Speed: {self.speed:g}x"
            )
            self.stats_changed.emit(stats)

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
        scale = min((rect.width() - 36) / sim_w, (rect.height() - 58) / sim_h)
        left = rect.left() + (rect.width() - sim_w * scale) / 2
        top = rect.top() + 34
        field = QRect(int(left), int(top), int(sim_w * scale), int(sim_h * scale))
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1))
        painter.setBrush(QColor(255, 255, 255, 10))
        painter.drawRoundedRect(field, 8, 8)
        painter.setClipRect(field)
        for index, particle in enumerate(self.artifact.particles):
            px = left + particle.x * scale
            py = top + particle.y * scale
            radius = max(1.5, particle.radius * scale)
            color = QColor(particle.color)
            if self.artifact.simulation_type.endswith("3d-projected"):
                radius *= 0.65 + (index % 9) * 0.055
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPoint(int(px), int(py)), int(radius), int(radius))
        painter.setClipping(False)
        painter.setPen(QColor(255, 255, 255, 218))
        painter.drawText(rect.adjusted(12, 6, -12, -6), Qt.AlignTop | Qt.AlignLeft, self.artifact.title)


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

        self.workspace_btn = QPushButton("Lab")
        self.workspace_btn.setObjectName("SidebarButton")
        self.workspace_btn.clicked.connect(self._parent.toggle_workspace_panel)

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
        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addStretch(1)

        self.min_btn = QPushButton("−")
        self.min_btn.setToolTip("Minimize")
        self.min_btn.setObjectName("TitleButton")
        self.min_btn.clicked.connect(self._parent.showMinimized)

        self.max_btn = QPushButton("□")
        self.max_btn.setToolTip("Maximize")
        self.max_btn.setObjectName("TitleButton")
        self.max_btn.clicked.connect(self._toggle_maximize)

        self.close_btn = QPushButton("X")
        self.close_btn.setToolTip("Close")
        self.close_btn.setObjectName("TitleClose")
        self.close_btn.clicked.connect(self._parent.close)

        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def _toggle_maximize(self):
        if getattr(self._parent, "_custom_maximized", False):
            self._parent.showNormal()
            normal_geometry = getattr(self._parent, "_normal_geometry", None)
            if normal_geometry is not None:
                self._parent.setGeometry(normal_geometry)
            self._parent._custom_maximized = False
            self.max_btn.setText("□")
            self.max_btn.setToolTip("Maximize")
        else:
            self._parent._normal_geometry = self._parent.geometry()
            screen = QApplication.screenAt(QCursor.pos()) or self._parent.screen() or QApplication.primaryScreen()
            if screen:
                self._parent.showNormal()
                self._parent.setGeometry(screen.availableGeometry().adjusted(6, 6, -6, -6))
            else:
                self._parent.showMaximized()
            self._parent._custom_maximized = True
            self.max_btn.setText("❐")
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
        self._drag_active = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()
            event.accept()


class MoriceWindow(QWidget):
    message_ready = Signal(str, str, bool)
    thinking_update = Signal(str)
    project_changes_ready = Signal(str, str)
    gpu_detected = Signal(object)

    def __init__(self):
        super().__init__()
        _load_ui_fonts()
        self.setWindowTitle(f"{MORICE_NAME} Glass Chat")
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
        self.first_user_message = ""
        self.user_messages: list[str] = []
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
        self.message_queue: list[str] = []
        self.settings = load_settings()
        self.response_style = self.settings.get("response_style", "").strip()
        self.wake_phrase = normalize_wake_phrase(self.settings.get("wake_phrase", ""))
        self.user_title = normalize_user_title(self.settings.get("user_title", ""))
        self.chat_mode = normalize_chat_mode(self.settings.get("chat_mode", ""))
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
        self.active_workspace_kind = "graph"
        self.last_project_request = ""
        self._last_external_wake_notice = 0.0

        self.wake_signal_path = wake_signal_path()
        self.message_ready.connect(self._on_message_ready)
        self.thinking_update.connect(self._on_thinking_update)
        self.project_changes_ready.connect(self._on_project_changes_ready)
        self.gpu_detected.connect(self._on_gpu_detected)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        root.addLayout(body, stretch=1)
        self.window_resize_grip = QSizeGrip(self)
        self.window_resize_grip.setObjectName("WindowResizeGrip")
        self.window_resize_grip.setToolTip("Resize MORICE window")

        self.mode_panel = QFrame()
        self.mode_panel.setObjectName("ModePanel")
        self.mode_panel.setFixedWidth(292)
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
        mode_layout.addSpacing(4)
        mode_layout.addWidget(model_label)
        mode_layout.addWidget(self.model_name_input)
        mode_layout.addWidget(self.model_path_input)
        mode_layout.addLayout(model_button_row)
        mode_layout.addWidget(hardware_label)
        mode_layout.addWidget(self.gpu_status_input)
        mode_layout.addWidget(self.detect_gpu_btn)
        mode_layout.addWidget(self.project_details)
        mode_layout.addWidget(self.mode_status)
        mode_layout.addStretch(1)

        body.addWidget(self.mode_panel)
        self.mode_panel.setVisible(False)

        self.workspace_panel = QFrame()
        self.workspace_panel.setObjectName("ScienceWorkspacePanel")
        self.workspace_panel.setMinimumWidth(350)
        self.workspace_panel.setMaximumWidth(700)
        self.workspace_panel.setFixedWidth(430)
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

        self.graph_canvas = GraphCanvas()
        self.graph_canvas.inspected.connect(lambda text: self.graph_inspector.setText(text or "Move over the graph to inspect points."))
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
        speed_btn = QPushButton("2x")
        speed_btn.setObjectName("WorkspaceControl")
        speed_btn.clicked.connect(lambda: self.physics_canvas.set_speed(2.0 if self.physics_canvas.speed == 1.0 else 1.0))
        physics_controls.addWidget(pause_btn)
        physics_controls.addWidget(resume_btn)
        physics_controls.addWidget(step_btn)
        physics_controls.addWidget(speed_btn)

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
        workspace_layout.addWidget(self.graph_canvas, stretch=1)
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

        # Keep the live graph/simulation workspace beside the conversation instead of hiding it in the chat flow.
        body.addWidget(self.workspace_panel)
        self.workspace_panel.setVisible(False)

        self.changes_panel = QFrame()
        self.changes_panel.setObjectName("ProjectChangesPanel")
        self.changes_panel.setFixedWidth(400)
        self.changes_minimized = False
        self.changes_expanded = False
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
        self.changes_expand_btn = QPushButton("[]")
        self.changes_expand_btn.setObjectName("ChangesIconButton")
        self.changes_expand_btn.setToolTip("Widen project changes")
        self.changes_expand_btn.clicked.connect(self._toggle_changes_width)
        changes_header.addWidget(self.changes_title, stretch=1)
        changes_header.addWidget(self.changes_minimize_btn)
        changes_header.addWidget(self.changes_expand_btn)

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
        changes_content_layout.setSpacing(10)
        self.changes_verify_btn = QPushButton("Verify project")
        self.changes_verify_btn.setObjectName("ProjectActionButton")
        self.changes_verify_btn.setToolTip("Validate the source files in the selected project folder")
        self.changes_verify_btn.clicked.connect(self._verify_project)
        self.changes_run_btn = QPushButton("Run project")
        self.changes_run_btn.setObjectName("ProjectActionButton")
        self.changes_run_btn.setToolTip("Run the project using its verified local entry point")
        self.changes_run_btn.clicked.connect(self._run_project)
        self.changes_action_status = QLabel("No runnable project detected yet.")
        self.changes_action_status.setObjectName("ProjectChangesSummary")
        self.changes_action_status.setWordWrap(True)
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addWidget(self.changes_verify_btn)
        action_row.addWidget(self.changes_run_btn)
        changes_content_layout.addWidget(self.changes_summary)
        changes_content_layout.addWidget(self.changes_view, stretch=1)
        changes_content_layout.addLayout(action_row)
        changes_content_layout.addWidget(self.changes_action_status)
        changes_layout.addLayout(changes_header)
        changes_layout.addWidget(self.changes_content, stretch=1)
        body.addWidget(self.changes_panel)
        self.changes_panel.setVisible(False)

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
        self.input.textChanged.connect(lambda _text: self._refresh_send_button_state())

        precision_btn = QPushButton("Precision: ON")
        precision_btn.setObjectName("PrecisionButton")
        precision_btn.clicked.connect(self.on_toggle_precision)
        self.precision_btn = precision_btn
        self.precision_btn.setProperty("active", "true")

        personalization_btn = QPushButton()
        personalization_btn.setObjectName("PersonalizationStatus")
        personalization_btn.clicked.connect(self.toggle_sidebar)
        self.personalization_btn = personalization_btn

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
            #ScienceActionCard {
                background: rgba(8,12,22,0.84);
                border-radius: 12px;
                border: 1px solid rgba(124,216,255,0.28);
                padding: 10px;
            }
            #ScienceActionButton {
                background: rgba(74,112,205,0.72);
                color: #ffffff;
                border-radius: 10px;
                padding: 11px 14px;
                border: 1px solid rgba(160,220,255,0.42);
                font-weight: 900;
                text-align: left;
            }
            #ScienceActionButton:hover {
                background: rgba(95,132,225,0.9);
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
        self._update_style_badge()
        self._refresh_queue_list()
        self._refresh_mode_panel()
        self._refresh_gpu_profile_ui()
        self._set_workspace_view("graph")
        self._refresh_send_button_state()

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
        now = time.monotonic()
        if self.awake:
            if now - self._last_external_wake_notice >= 4.0:
                detail = f" from {source}" if source else ""
                self.append_message(MORICE_NAME, self._address(f"I heard the wake signal{detail}. I am already awake."))
                self._last_external_wake_notice = now
            return
        self.awake = True
        self.append_message(MORICE_NAME, f"{MORICE_NAME} is awake, {self.user_title}.")
        self._last_external_wake_notice = now

    def _address(self, reply: str) -> str:
        return enforce_father(reply, self.user_title)

    def _input_placeholder(self) -> str:
        return f"{self.user_title}: type here..."

    def _track_animation(self, animation):
        """Keep transient Qt animations alive until their finished signal fires."""
        if not hasattr(self, "_anims"):
            return animation
        self._anims.append(animation)
        animation.finished.connect(lambda: self._anims.remove(animation) if animation in self._anims else None)
        return animation

    def _animate_panel_visibility(self, panel: QWidget, visible: bool):
        """Fade a side panel without leaving layout space behind after it closes."""
        self._panel_target_visibility[panel] = visible
        running = self._panel_anims.pop(panel, None)
        if running is not None:
            running.stop()
            if running in self._anims:
                self._anims.remove(running)

        effect = panel.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(panel)
            panel.setGraphicsEffect(effect)

        if not self._motion_enabled or not self.isVisible():
            panel.setVisible(visible)
            effect.setOpacity(1.0)
            return

        if visible:
            was_visible = panel.isVisible()
            panel.setVisible(True)
            start = effect.opacity() if was_visible else 0.0
            end = 1.0
        else:
            if not panel.isVisible():
                effect.setOpacity(1.0)
                return
            start = effect.opacity()
            end = 0.0

        if abs(start - end) < 0.01:
            panel.setVisible(visible)
            effect.setOpacity(1.0)
            return

        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(180)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.OutCubic if visible else QEasingCurve.InCubic)

        def finish():
            if self._panel_anims.get(panel) is not animation:
                return
            self._panel_anims.pop(panel, None)
            if not visible:
                panel.setVisible(False)
            effect.setOpacity(1.0)

        animation.finished.connect(finish)
        self._panel_anims[panel] = animation
        self._track_animation(animation).start()

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
        if self.workspace_panel.isVisible():
            self._close_workspace()
        else:
            self._open_workspace(self.active_workspace_kind)

    def _set_chat_mode(self, mode: str):
        clean_mode = normalize_chat_mode(mode)
        if clean_mode == self.chat_mode:
            self._refresh_mode_panel()
            return
        self.chat_mode = clean_mode
        self.settings["chat_mode"] = self.chat_mode
        self._save_project_settings()
        self._refresh_mode_panel()
        mode_name = "Project" if self.chat_mode == "project" else "Normal chat"
        if self.chat_container.isVisible():
            self.append_message(MORICE_NAME, self._address(f"{mode_name} mode enabled."))
        elif self.chat_mode == "normal":
            self.mode_status.setText(f"{mode_name} mode is ready for the next message.")

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
        self.settings["chat_mode"] = self.chat_mode
        self.settings["project_folder"] = self.project_folder
        self.settings["project_access"] = self.project_access
        self.settings["project_lookup_mode"] = self.project_lookup_mode
        self.settings["model_path"] = self.model_path
        self.settings["model_name"] = self.model_name
        self.settings["gpu_name"] = self.gpu_name
        self.settings["gpu_vram_mb"] = self.gpu_vram_mb
        save_settings(self.settings)

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
            self.gpu_detected.emit(profile)

        threading.Thread(target=worker, daemon=True).start()

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
        self._set_project_details_visible(is_project)
        if not is_project:
            self._animate_panel_visibility(self.changes_panel, False)
        self.personalization_btn.setVisible(not is_project)
        self.access_status_btn.setVisible(is_project)
        self.project_lookup_btn.setVisible(is_project)
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
            (self.normal_mode_btn, not is_project),
            (self.project_mode_btn, is_project),
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
            "For a new playable game, default to a complete self-contained HTML/CSS/JavaScript Canvas project that runs by opening index.html. "
            "Only edit a Unity project when the chosen folder already contains a real Unity project and the request specifically asks for it; "
            "never invent Unity scenes, prefabs, metadata, binary art/audio, or a compiled executable. "
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
        if self.chat_mode != "project":
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
        if self.chat_mode != "project" or not self.last_project_request:
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

    def _project_manifest_instruction(self) -> str:
        return (
            "For this project request, do not give copy-paste instructions and do not ask the user to create files. "
            "Return only valid JSON with this shape: "
            '{"summary":"short result","files":[{"path":"relative/path.ext","content":"full file content"}],'
            '"commands":["optional commands"],"notes":["optional notes"]}. '
            "Every file path must be relative to the work folder. Include complete file contents, not snippets. "
            "When editing an existing file, include the full updated file content. "
            "Do not return a commands-only manifest; create or update at least one practical file whenever the request asks to build. "
            "Never create .exe, .dll, .msi, .apk, .zip, or another compiled/binary artifact. MORICE writes runnable source files only. "
            "For a new game or browser app, create a complete self-contained index.html (plus CSS/JS when useful) rather than Unity files, fake assets, or pygame-only code. "
            "Only edit existing Unity source scripts when the folder already contains that Unity project; never create .unity, .prefab, .meta, or binary asset files. "
            "For a browser app, create a complete index.html. For a Python app, create a complete .py entry point and requirements.txt when packages are needed. "
            "Do not wrap the JSON in markdown. Do not include explanations outside the JSON."
        )

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

    def _apply_project_manifest(self, reply) -> dict | None:
        manifest = reply if isinstance(reply, dict) else self._extract_project_manifest(reply)
        if not manifest:
            return None
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
        for relative_path, content, target in staged_files:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            old = ""
            if os.path.exists(target):
                with open(target, "r", encoding="utf-8", errors="replace") as handle:
                    old = handle.read()
            if old == content:
                continue
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
            changed.append(relative_path)
            diff_parts.append(self._diff_html(relative_path, old, content))

        run_script = build_run_script(self.project_folder, requirements)
        if run_script and not os.path.exists(os.path.join(self.project_folder, run_script[0])):
            relative_path, content = run_script
            target = self._project_target_path(relative_path)
            old = ""
            validate_project_file(relative_path, content)
            with open(target, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
            changed.append(relative_path)
            diff_parts.append(self._diff_html(relative_path, old, content))

        summary = str(manifest.get("summary") or "").strip() or f"Updated {len(changed)} file(s)."
        if not changed:
            summary = summary + " No file content changed."
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
        if commands:
            message += "\n\nSuggested run commands:\n" + "\n".join(f"- {command}" for command in commands)
        if notes:
            message += "\n\nNotes:\n" + "\n".join(f"- {note}" for note in notes)
        return {"summary": summary, "message": message, "diff_html": panel_html, "changed": changed}

    def _on_project_changes_ready(self, summary: str, diff_html: str):
        self.changes_summary.setText(summary or "Project files updated.")
        self.changes_view.setHtml(
            diff_html
            or "<span style='color:rgba(255,255,255,0.64)'>No visible file diff for this action.</span>"
        )
        self._animate_panel_visibility(self.changes_panel, self.chat_mode == "project")
        self._refresh_project_actions()

    def _toggle_changes_minimized(self):
        self.changes_minimized = not self.changes_minimized
        self.changes_content.setVisible(not self.changes_minimized)
        self.changes_title.setVisible(not self.changes_minimized)
        self.changes_minimize_btn.setText("+" if self.changes_minimized else "_")
        self.changes_minimize_btn.setToolTip("Restore project changes" if self.changes_minimized else "Minimize project changes")
        self.changes_panel.setFixedWidth(54 if self.changes_minimized else (620 if self.changes_expanded else 400))

    def _toggle_changes_width(self):
        if self.changes_minimized:
            self._toggle_changes_minimized()
        self.changes_expanded = not self.changes_expanded
        self.changes_panel.setFixedWidth(620 if self.changes_expanded else 400)
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
        failures = []
        checked = 0
        for dirpath, dirnames, filenames in os.walk(self.project_folder):
            dirnames[:] = [name for name in dirnames if name not in PROJECT_IGNORED_DIRS]
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                relative_path = os.path.relpath(full_path, self.project_folder).replace("\\", "/")
                if os.path.splitext(relative_path)[1].lower() not in PROJECT_TEXT_EXTENSIONS | {".bat"}:
                    continue
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as handle:
                        validate_project_file(relative_path, handle.read())
                    checked += 1
                except (OSError, ProjectValidationError) as exc:
                    failures.append(f"{relative_path}: {exc}")
        if failures:
            self.changes_action_status.setText("Verification failed: " + failures[0])
        else:
            self.changes_action_status.setText(f"Verified {checked} source file(s).")
        plan = build_launch_plan(self.project_folder)
        if plan:
            self.changes_run_btn.setEnabled(True)
            self.changes_run_btn.setText(plan.label)
            if not failures:
                self.changes_action_status.setText(f"Verified {checked} source file(s). Entry point: {os.path.basename(plan.target)}")
        else:
            self.changes_run_btn.setEnabled(False)

    def _run_project(self):
        plan = build_launch_plan(self.project_folder)
        if not plan:
            self.changes_action_status.setText("No verified project entry point is available to run.")
            return
        try:
            self.changes_action_status.setText(launch_project(plan))
        except (OSError, ProjectValidationError) as exc:
            self.changes_action_status.setText(f"Could not run project: {exc}")

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
        self.graph_canvas.setVisible(clean == "graph")
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

    def _close_workspace(self):
        self._animate_panel_visibility(self.workspace_panel, False)
        if hasattr(self.title_bar, "workspace_btn"):
            self.title_bar.workspace_btn.setText("Lab")

    def _refresh_workspace_artifact_list(self):
        self.workspace_artifact_list.blockSignals(True)
        self.workspace_artifact_list.clear()
        for artifact in self.science_artifacts:
            prefix = "Graph" if artifact.kind == "graph" else "Physics"
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
        self._set_workspace_view(artifact.kind)
        if artifact.graph:
            self.graph_canvas.set_artifact(artifact.graph)
            self.graph_equations.setText(
                "Equations:\n" + "\n".join(f"- {series.label}" for series in artifact.graph.series)
            )
        if artifact.physics:
            self.physics_canvas.set_artifact(artifact.physics)
            self.physics_stats.setText(
                f"Particles: {len(artifact.physics.particles)} | FPS target: 60 | "
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
        self.science_artifacts.append(artifact)
        self._refresh_workspace_artifact_list()
        self._open_workspace(artifact.kind)

    def _insert_chat_widget(self, widget: QWidget, force_scroll: bool = True):
        insert_index = max(0, self.chat_list_layout.count() - 1)
        self.chat_list_layout.insertWidget(insert_index, widget)
        if force_scroll:
            self.follow_latest = True
        self._schedule_latest_scroll(force=force_scroll)

    def append_science_card(self, artifact: ScienceArtifact):
        card = QFrame()
        card.setObjectName("ScienceActionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        if artifact.kind == "graph":
            title = "Graph Generated"
            detail = f"Open Graph Workspace -> {artifact.title}"
            target = "graph"
        else:
            title = "Physics Simulation Generated"
            detail = f"Open Simulation Workspace -> {artifact.title}"
            target = "physics"
        button = QPushButton(f"{title}\n{detail}")
        button.setObjectName("ScienceActionButton")
        button.clicked.connect(lambda _checked=False, kind=target: self._open_workspace(kind))
        layout.addWidget(button)
        self._insert_chat_widget(card)

    def _handle_science_request(self, user_input: str) -> bool:
        if self.chat_mode == "project":
            return False
        if not is_science_request(user_input):
            return False
        artifact = build_science_artifact(user_input)
        if not artifact:
            return False
        self._add_science_artifact(artifact)
        self.append_science_card(artifact)
        return True

    def _science_reply_context(self) -> str:
        if not self.science_artifacts:
            return ""
        artifact = self.science_artifacts[-1]
        if artifact.kind == "graph" and artifact.graph:
            equations = ", ".join(series.label for series in artifact.graph.series)
            return (
                "MORICE has already generated an interactive graph in the Lab workspace for this user prompt. "
                f"Graph title: {artifact.title}. Equations: {equations}. "
                "Give the user the written math/science explanation, key points, and how to inspect the visual. "
                "Do not output placeholder text like [Graph of ...] and do not claim you cannot show the graph."
            )
        if artifact.kind == "physics" and artifact.physics:
            return (
                "MORICE has already generated a live physics simulation in the Lab workspace for this user prompt. "
                f"Simulation title: {artifact.title}. Type: {artifact.physics.simulation_type}. "
                f"Particles: {len(artifact.physics.particles)}. "
                "Give the user the written physics explanation, what the simulation shows, and how to inspect it. "
                "Do not output placeholder text like [Simulation of ...] and do not claim you cannot show the simulation."
            )
        return ""

    def _science_ready_reply(self) -> str:
        artifact = self.science_artifacts[-1] if self.science_artifacts else None
        if artifact and artifact.kind == "graph" and artifact.graph:
            equations = ", ".join(series.label for series in artifact.graph.series)
            return f"I rendered {artifact.title} in the Lab graph workspace. Equations: {equations}. Use the Graphs tab to inspect the curve and hover over points for values."
        if artifact and artifact.kind == "physics" and artifact.physics:
            return f"I started {artifact.title} in the Lab simulation workspace with {len(artifact.physics.particles)} particles. Use Pause, Resume, Step, and 2x to inspect the live motion."
        return "I created the live visual in the Lab workspace."

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

        if self._motion_enabled and self.isVisible():
            anim = QPropertyAnimation(opacity, b"opacity", bubble)
            anim.setDuration(180)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._track_animation(anim).start()
        else:
            opacity.setOpacity(1.0)

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
        self.normal_mode_btn.setEnabled(not is_busy)
        self.project_mode_btn.setEnabled(not is_busy)
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
            self.access_status_btn,
            self.project_lookup_btn,
            self.title_bar,
            self.title_bar.sidebar_btn,
            self.title_bar.workspace_btn,
            self.chat_container,
            self.input_frame,
            self.sidebar,
            self.mode_panel,
            self.workspace_panel,
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

        if wants_model_identity(user_input):
            self.append_message(MORICE_NAME, self._address(self._model_status_line()))
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

        # A simulation prompt can contain a bare number (for example, "80 particles").
        # Keep it out of the quick-math path so the live physics workspace receives it.
        if not self.math_steps_mode and not wants_steps_detail(user_input) and not is_science_request(user_input):
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

        science_visual_ready = self._handle_science_request(user_input)
        if science_visual_ready:
            self.append_message(MORICE_NAME, self._address(self._science_ready_reply()))
            return
        science_visual_context = ""

        retry_project_request = self._is_project_retry_request(user_input)
        project_source_input = self.last_project_request if retry_project_request else user_input
        project_build_request = retry_project_request or self._is_project_build_request(user_input)
        if project_build_request and not retry_project_request:
            self.last_project_request = user_input
        if project_build_request and not self._ensure_project_folder_for_build():
            self.append_message(
                MORICE_NAME,
                self._address("Choose a work folder with the + button, then I can create and edit the project files there."),
            )
            return

        project_online_lookup = project_build_request and self.project_lookup_mode == "online"
        if (
            wants_web_capability(user_input)
            and not extract_web_query(user_input)
            and not project_online_lookup
        ):
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
            "Using @web, collecting search results, then asking the selected Qwen/local engine."
            if web_query_for_status
            else (
                "Online+local Project mode: collecting web context, then building files."
                if project_online_lookup
                else (
                    "Local Project mode: using the selected folder and local model to build files."
                    if project_build_request
                    else (
                        "Normal chat VNext: visual is open in Lab, now writing the explanation."
                        if science_visual_ready
                        else "Full offline mode: asking the bundled Qwen engine only."
                    )
                )
            )
        )

        def worker():
            try:
                self.thinking_update.emit("Checking saved response style and local context.")
                context_input = project_source_input if project_build_request else user_input
                context = retrieve_context(context_input) if should_use_context(context_input) else ""
                web_context = ""
                web_query = extract_web_query(user_input)
                auto_project_web = project_build_request and self.project_lookup_mode == "online"
                if os.getenv("MORICE_WEB", "1") == "1" and (web_query or auto_project_web):
                    search_query = web_query or project_source_input
                    if web_query:
                        self.thinking_update.emit("Searching the web because the message used @web.")
                    else:
                        self.thinking_update.emit("Online+local mode: searching the web for useful project context.")
                    web_context = search_web(search_query)
                    if not web_context:
                        web_context = "Web lookup returned no results."

                extra_system = (
                    f"Saved name preference from the user: address the user as '{self.user_title}'. "
                    "Do not call the user 'All Father' unless that is the saved name preference."
                )
                if self.chat_mode == "project":
                    self.thinking_update.emit("Project builder mode: applying workspace, access, and coding rules.")
                    extra_system += "\n\n" + self._project_builder_system()
                    if project_build_request:
                        self.thinking_update.emit("Reading the work folder so edits can be applied directly.")
                        extra_system += "\n\n" + self._project_snapshot()
                        extra_system += "\n\n" + self._project_manifest_instruction()
                elif science_visual_context:
                    self.thinking_update.emit("Normal chat VNext: using the generated Lab visual as context.")
                    extra_system += "\n\n" + science_visual_context
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

                self.thinking_update.emit(
                    "Asking Qwen for project files."
                    if project_build_request
                    else "Asking Qwen to compose the final answer."
                )
                model_user_input = user_input
                model_history = self.history
                if project_build_request:
                    model_history = []
                    model_user_input = (
                        "Create or update the project files for this request. "
                        "Return only the required JSON manifest with complete file contents.\n\n"
                        f"USER_REQUEST:\n{project_source_input}"
                    )
                reply = chat(
                    model_history,
                    model_user_input,
                    extra_system=extra_system,
                    model=self.model_name or None,
                    timeout=180,
                    precision_mode=self.precision_mode,
                    math_steps_mode=self.math_steps_mode or wants_steps_detail(user_input),
                    gguf_path=self.model_path,
                )
                visible_reply = reply
                if project_build_request:
                    project_result = None
                    apply_error = ""
                    self.thinking_update.emit("Applying generated files to the selected work folder.")
                    try:
                        project_result = self._apply_project_manifest(reply)
                    except Exception as exc:  # noqa: BLE001
                        apply_error = str(exc)

                    if not project_result:
                        self.thinking_update.emit("Converting the model output into a safe file manifest.")
                        repair_prompt = (
                            "Turn this project request into the required JSON file manifest only. "
                            "Include complete file contents and relative paths.\n\n"
                            f"User request:\n{project_source_input}\n\n"
                            f"Previous model output:\n{reply}"
                        )
                        try:
                            repair_reply = chat(
                                [],
                                repair_prompt,
                                extra_system=extra_system + "\n\n" + self._project_manifest_instruction(),
                                model=self.model_name or None,
                                timeout=180,
                                precision_mode=True,
                                math_steps_mode=False,
                                gguf_path=self.model_path,
                            )
                            project_result = self._apply_project_manifest(repair_reply)
                        except Exception as exc:  # noqa: BLE001
                            apply_error = str(exc)

                    if not project_result:
                        self.thinking_update.emit("Using MORICE's local Project fallback builder.")
                        try:
                            fallback_manifest = build_project_fallback_manifest(project_source_input)
                            if fallback_manifest:
                                project_result = self._apply_project_manifest(fallback_manifest)
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
                        self.project_changes_ready.emit(project_result["summary"], project_result["diff_html"])
                    else:
                        detail = f" Error: {apply_error}" if apply_error else ""
                        folder_hint = (
                            "Choose a work folder with the + button, then try a direct build request."
                            if not self.project_folder
                            else "Try a more direct build request, or switch the selected model to a stronger coding GGUF."
                        )
                        visible_reply = f"I could not safely turn that request into project files yet.{detail}\n\n{folder_hint}"
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": visible_reply})
                self.message_ready.emit(MORICE_NAME, self._address(visible_reply), False)
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
    _set_windows_app_id()
    app = QApplication(sys.argv)
    _load_ui_fonts()
    app.setApplicationName("MORICE")
    app.setOrganizationName("EONASH2722")
    icon_path = _icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MoriceWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
