"""Lightweight, data-driven desktop companions for MORICE.

The renderer intentionally uses original procedural pixel placeholders.  A
licensed sprite pack can replace them through pet definition files without
changing click, drag, fullscreen, or launch behavior.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QPoint, QRect, QLockFile, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygon, QRegion
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QWidget

from .pet_launcher import DO_NOTHING, MoriceLauncher, normalize_open_action, restore_morice_window
from .pet_events import RareEventScheduler, normalize_event_frequency
from .settings import load_settings
from .wake_runtime import app_session_path


SUPPORTED_PETS = (
    "ironman_mark42",
    "spiderman",
    "horse",
    "skeleton",
    "dog",
    "cat",
)
PET_HOST_SERVER_NAME = "EONASH2722.MORICE.DesktopPet.v1"


@dataclass(frozen=True)
class PetDefinition:
    pet_id: str
    name: str
    renderer: str
    movement: str = "ground"
    click_feedback: str = "look"
    accent: str = "#72e4ff"
    behavior_states: tuple[str, ...] = ("idle", "patrol", "react")


class AssetLoader:
    """Load pet metadata while keeping the engine independent from art packs."""

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(root) if root is not None else Path(__file__).with_name("assets") / "pets"

    def load(self, pet_id: str) -> PetDefinition:
        clean_id = normalize_pet_id(pet_id)
        path = self.root / clean_id / "definition.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
            data = {}
        defaults = _PET_DEFAULTS[clean_id]
        return PetDefinition(
            pet_id=clean_id,
            name=str(data.get("name") or defaults.name)[:80],
            renderer=str(data.get("renderer") or defaults.renderer)[:80],
            movement=str(data.get("movement") or defaults.movement)[:40],
            click_feedback=str(data.get("click_feedback") or defaults.click_feedback)[:80],
            accent=str(data.get("accent") or defaults.accent)[:24],
            behavior_states=_normalize_behavior_states(
                data.get("behavior_states"), defaults.behavior_states
            ),
        )


_PET_DEFAULTS = {
    "ironman_mark42": PetDefinition(
        "ironman_mark42",
        "Iron Man — Mark 42",
        "armored_flyer",
        "flight",
        "arc_flash",
        "#7defff",
        (
            "idle",
            "hover",
            "slow_flight",
            "fast_flight",
            "bank",
            "barrel_roll",
            "hard_stop",
            "landing",
            "superhero_landing",
            "walk",
            "edge_sit",
            "look",
            "stabilize",
            "takeoff",
            "special",
            "armor_off",
            "enemy_alert",
            "enemy_chase",
            "enemy_attack",
            "enemy_victory",
            "react",
        ),
    ),
    "spiderman": PetDefinition(
        "spiderman",
        "Spider-Man",
        "web_hero",
        "acrobat",
        "eye_focus",
        "#f5f7ff",
        (
            "idle", "perch", "swing", "patrol", "special", "react",
            "enemy_alert", "enemy_chase", "enemy_web", "enemy_victory",
            "symbiote_notice", "symbiote_transform", "symbiote_active",
            "symbiote_struggle", "symbiote_remove",
        ),
    ),
    "horse": PetDefinition(
        "horse", "Horse", "horse", "ground", "head_nod", "#d7a76e",
        ("idle", "patrol", "play", "react", "graze", "rear", "gallop"),
    ),
    "skeleton": PetDefinition(
        "skeleton", "Skeleton", "skeleton", "ground", "rattle", "#e8eef2",
        (
            "idle", "patrol", "special", "react", "skeleton_collapse",
            "skeleton_scatter", "skeleton_reform",
        ),
    ),
    "dog": PetDefinition(
        "dog", "Dog", "dog", "ground", "tail_wag", "#f5bd67",
        (
            "idle", "patrol", "play", "sleep", "react", "fetch_ready",
            "fetch_chase", "fetch_return", "fetch_celebrate",
        ),
    ),
    "cat": PetDefinition(
        "cat", "Cat", "cat", "ground", "ear_twitch", "#c8a7ef",
        (
            "idle", "patrol", "play", "sleep", "react", "cat_bed",
            "cat_deep_sleep", "cat_stretch",
        ),
    ),
}


_VALID_BEHAVIOR_STATES = frozenset(
    {
        "idle",
        "patrol",
        "sleep",
        "play",
        "hover",
        "perch",
        "swing",
        "special",
        "react",
        "dragged",
        "escape",
        "slow_flight",
        "fast_flight",
        "bank",
        "barrel_roll",
        "hard_stop",
        "landing",
        "superhero_landing",
        "walk",
        "edge_sit",
        "look",
        "stabilize",
        "takeoff",
        "armor_off",
        "falling",
        "enemy_alert",
        "enemy_chase",
        "enemy_attack",
        "enemy_web",
        "enemy_victory",
        "symbiote_notice",
        "symbiote_transform",
        "symbiote_active",
        "symbiote_struggle",
        "symbiote_remove",
        "graze",
        "rear",
        "gallop",
        "skeleton_collapse",
        "skeleton_scatter",
        "skeleton_reform",
        "fetch_ready",
        "fetch_chase",
        "fetch_return",
        "fetch_celebrate",
        "cat_bed",
        "cat_deep_sleep",
        "cat_stretch",
    }
)

_EVENT_ONLY_STATES = frozenset(
    state
    for state in _VALID_BEHAVIOR_STATES
    if state.startswith(("enemy_", "symbiote_", "skeleton_", "fetch_", "cat_"))
    or state in {"graze", "rear", "gallop"}
)


def _normalize_behavior_states(
    value: object, fallback: tuple[str, ...]
) -> tuple[str, ...]:
    if not isinstance(value, list):
        return fallback
    states = tuple(
        dict.fromkeys(
            str(item).strip().casefold()
            for item in value
            if str(item).strip().casefold() in _VALID_BEHAVIOR_STATES
        )
    )
    return states or fallback


def normalize_pet_id(value: object) -> str:
    clean = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "ironman": "ironman_mark42",
        "mark42": "ironman_mark42",
        "spider_man": "spiderman",
        "spider": "spiderman",
    }
    clean = aliases.get(clean, clean)
    return clean if clean in SUPPORTED_PETS else "dog"


def normalize_pet_size(value: object) -> str:
    clean = str(value or "").strip().casefold()
    return clean if clean in {"small", "medium", "large"} else "medium"


@dataclass
class PointerGesture:
    """Classify a scale-aware pointer sequence as a click or a drag."""

    start_x: float = 0.0
    start_y: float = 0.0
    started_at: float = 0.0
    drag_threshold: float = 8.0
    click_timeout_seconds: float = 0.5
    dragging: bool = False
    active: bool = False

    def begin(
        self,
        x: float,
        y: float,
        timestamp: float,
        *,
        drag_threshold: float,
        click_timeout_seconds: float,
    ) -> None:
        self.start_x = float(x)
        self.start_y = float(y)
        self.started_at = float(timestamp)
        self.drag_threshold = max(1.0, float(drag_threshold))
        self.click_timeout_seconds = max(0.05, float(click_timeout_seconds))
        self.dragging = False
        self.active = True

    def move(self, x: float, y: float) -> bool:
        if not self.active:
            return False
        distance = math.hypot(float(x) - self.start_x, float(y) - self.start_y)
        if distance >= self.drag_threshold:
            self.dragging = True
        return self.dragging

    def finish(self, x: float, y: float, timestamp: float) -> str:
        if not self.active:
            return "none"
        self.move(x, y)
        duration = max(0.0, float(timestamp) - self.started_at)
        result = (
            "click"
            if not self.dragging and duration <= self.click_timeout_seconds
            else "drag"
        )
        self.active = False
        return result


_STATE_FRAME_COUNTS = {
    "idle": 4,
    "patrol": 6,
    "sleep": 4,
    "play": 6,
    "hover": 4,
    "perch": 3,
    "swing": 8,
    "special": 8,
    "react": 4,
    "dragged": 2,
    "escape": 8,
    "slow_flight": 6,
    "fast_flight": 8,
    "bank": 6,
    "barrel_roll": 10,
    "hard_stop": 6,
    "landing": 8,
    "superhero_landing": 8,
    "walk": 8,
    "edge_sit": 5,
    "look": 6,
    "stabilize": 6,
    "takeoff": 8,
    "armor_off": 20,
    "falling": 8,
    "enemy_alert": 5,
    "enemy_chase": 8,
    "enemy_attack": 10,
    "enemy_web": 10,
    "enemy_victory": 8,
    "symbiote_notice": 6,
    "symbiote_transform": 14,
    "symbiote_active": 12,
    "symbiote_struggle": 12,
    "symbiote_remove": 16,
    "graze": 8,
    "rear": 8,
    "gallop": 10,
    "skeleton_collapse": 10,
    "skeleton_scatter": 10,
    "skeleton_reform": 12,
    "fetch_ready": 6,
    "fetch_chase": 10,
    "fetch_return": 10,
    "fetch_celebrate": 8,
    "cat_bed": 6,
    "cat_deep_sleep": 8,
    "cat_stretch": 10,
}


class AnimationController:
    """Convert behavior state and elapsed time into stable animation frames."""

    _SPEED_FACTORS = {"slow": 0.72, "normal": 1.0, "fast": 1.35}

    def __init__(self, speed: str = "normal") -> None:
        self.state = "idle"
        self.started_at = time.monotonic()
        self.speed = "normal"
        self.set_speed(speed)

    def set_speed(self, speed: object) -> None:
        clean = str(speed or "").strip().casefold()
        self.speed = clean if clean in self._SPEED_FACTORS else "normal"

    @property
    def speed_factor(self) -> float:
        return self._SPEED_FACTORS[self.speed]

    def set_state(self, state: str, now: float | None = None) -> None:
        clean = state if state in _STATE_FRAME_COUNTS else "idle"
        if clean == self.state:
            return
        self.state = clean
        self.started_at = time.monotonic() if now is None else float(now)

    def sample(self, now: float | None = None) -> tuple[int, float]:
        current = time.monotonic() if now is None else float(now)
        elapsed = max(0.0, current - self.started_at)
        factor = self.speed_factor
        frame_count = _STATE_FRAME_COUNTS.get(self.state, 4)
        fps = (5.0 if self.state in {"idle", "sleep", "perch"} else 9.0) * factor
        cycle_position = elapsed * fps
        frame = int(cycle_position) % frame_count
        return frame, (cycle_position % frame_count) / frame_count


class BehaviorController:
    """Small deterministic state machine shared by every pet definition."""

    def __init__(
        self,
        definition: PetDefinition,
        *,
        rng: random.Random | None = None,
        now: float | None = None,
    ) -> None:
        self.definition = definition
        self.rng = rng or random.Random()
        self.state = "idle"
        current = time.monotonic() if now is None else float(now)
        self.state_started_at = current
        self.state_duration = 2.5
        self.state_until = current + self.state_duration
        self._sequence: list[tuple[str, float]] = []
        self.active_event_id = ""

    @property
    def major_event_active(self) -> bool:
        return bool(self.active_event_id)

    def queue_event(
        self,
        event_id: str,
        sequence: tuple[tuple[str, float], ...],
        now: float | None = None,
    ) -> bool:
        if self.major_event_active or self.state in {"dragged", "falling", "escape"}:
            return False
        queue = [(state, duration) for state, duration in sequence if state in _VALID_BEHAVIOR_STATES]
        if not queue:
            return False
        self.active_event_id = str(event_id)
        self._sequence = queue
        state, duration = self._sequence.pop(0)
        self.force(state, duration, now)
        return True

    def cancel_event(self, now: float | None = None) -> None:
        self.active_event_id = ""
        self._sequence.clear()
        if self.state in _EVENT_ONLY_STATES:
            self.force("idle", 0.8, now)

    def update(self, now: float | None = None) -> str:
        current = time.monotonic() if now is None else float(now)
        if self.state in {"dragged", "react", "escape"} and current < self.state_until:
            return self.state
        if current >= self.state_until:
            self._choose_next(current)
        return self.state

    def progress(self, now: float | None = None) -> float:
        current = time.monotonic() if now is None else float(now)
        if self.state_duration <= 0:
            return 1.0
        return max(
            0.0,
            min(1.0, (current - self.state_started_at) / self.state_duration),
        )

    def force(self, state: str, duration: float, now: float | None = None) -> None:
        clean = state if state in _VALID_BEHAVIOR_STATES else "idle"
        current = time.monotonic() if now is None else float(now)
        self.state = clean
        self.state_started_at = current
        self.state_duration = max(0.08, float(duration))
        self.state_until = current + self.state_duration

    def react(self, now: float | None = None) -> None:
        self.force("react", 0.42, now)

    def begin_drag(self, now: float | None = None) -> None:
        self.cancel_event(now)
        self.force("dragged", 60.0, now)

    def end_drag(self, now: float | None = None) -> None:
        if self.definition.movement in {"flight", "acrobat"}:
            self.force("escape", 0.95, now)
        else:
            self.force("falling", 8.0, now)

    def _choose_next(self, now: float) -> None:
        if self._sequence:
            state, duration = self._sequence.pop(0)
            self.force(state, duration, now)
            return
        if self.active_event_id:
            self.active_event_id = ""
        if self.definition.pet_id == "ironman_mark42":
            self._choose_ironman_next(now)
            return
        candidates = [
            state
            for state in self.definition.behavior_states
            if state not in {"react", "dragged", "escape"} | _EVENT_ONLY_STATES
        ] or ["idle"]
        weights = {
            "idle": 3.0,
            "patrol": 4.5,
            "sleep": 0.7,
            "play": 1.1,
            "hover": 3.0,
            "perch": 1.4,
            "swing": 2.5,
            "special": 0.55,
        }
        chosen = self.rng.choices(
            candidates,
            weights=[weights.get(state, 1.0) for state in candidates],
            k=1,
        )[0]
        duration_ranges = {
            "idle": (1.8, 4.5),
            "patrol": (3.2, 7.5),
            "sleep": (5.0, 10.0),
            "play": (1.0, 2.4),
            "hover": (2.5, 5.5),
            "perch": (2.5, 5.5),
            "swing": (2.8, 6.0),
            "special": (1.4, 2.8),
        }
        low, high = duration_ranges.get(chosen, (2.0, 4.0))
        self.force(chosen, self.rng.uniform(low, high), now)

    def _choose_ironman_next(self, now: float) -> None:
        """Run readable Mark 42 action chains instead of unrelated pose swaps."""

        if self._sequence:
            state, duration = self._sequence.pop(0)
            self.force(state, duration, now)
            return

        roll = self.rng.random()
        if roll < 0.33:
            self._sequence = [
                ("takeoff", 0.85),
                ("fast_flight", 2.7),
                ("bank", 1.05),
                ("barrel_roll", 1.0),
                ("hard_stop", 0.9),
                ("stabilize", 1.35),
                ("hover", 2.2),
            ]
        elif roll < 0.60:
            self._sequence = [
                ("landing", 1.0),
                ("superhero_landing", 1.45),
                ("walk", 2.6),
                ("look", 1.4),
                ("takeoff", 0.9),
                ("hover", 2.0),
            ]
        elif roll < 0.82:
            self._sequence = [
                ("slow_flight", 2.6),
                ("bank", 1.1),
                ("edge_sit", 2.4),
                ("look", 1.2),
                ("takeoff", 0.9),
            ]
        else:
            self._sequence = [
                ("stabilize", 1.1),
                ("barrel_roll", 1.05),
                ("fast_flight", 2.2),
                ("hard_stop", 0.75),
                ("hover", 2.0),
            ]

        state, duration = self._sequence.pop(0)
        self.force(state, duration, now)


def _virtual_available_geometry() -> QRect:
    screens = QApplication.screens()
    if not screens:
        return QRect(0, 0, 1280, 720)
    combined = QRect(screens[0].availableGeometry())
    for screen in screens[1:]:
        combined = combined.united(screen.availableGeometry())
    return combined


def _is_true_fullscreen_geometry(
    window_rect: tuple[int, int, int, int],
    monitor_rect: tuple[int, int, int, int],
    *,
    is_maximized: bool,
    tolerance: int = 2,
) -> bool:
    """Distinguish borderless fullscreen from an ordinary maximized window."""

    if is_maximized:
        return False
    left, top, right, bottom = window_rect
    monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_rect
    return (
        left <= monitor_left + tolerance
        and top <= monitor_top + tolerance
        and right >= monitor_right - tolerance
        and bottom >= monitor_bottom - tolerance
    )


def foreground_is_fullscreen(*, ignored_hwnds: set[int] | None = None) -> bool:
    """Return True for borderless fullscreen, excluding normal maximize state."""

    if os.name != "nt":
        return False
    ignored = ignored_hwnds or set()
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetShellWindow.restype = ctypes.c_void_p
        user32.GetDesktopWindow.restype = ctypes.c_void_p
        user32.IsZoomed.argtypes = [ctypes.c_void_p]
        user32.IsZoomed.restype = ctypes.c_bool
        hwnd = int(user32.GetForegroundWindow() or 0)
        if not hwnd or hwnd in ignored or user32.IsIconic(ctypes.c_void_p(hwnd)):
            return False
        shell = int(user32.GetShellWindow() or 0)
        desktop = int(user32.GetDesktopWindow() or 0)
        if hwnd in {shell, desktop}:
            return False

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", ctypes.c_ulong),
            ]

        user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]
        user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        user32.MonitorFromWindow.restype = ctypes.c_void_p
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]

        window_rect = RECT()
        if not user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(window_rect)):
            return False
        monitor = user32.MonitorFromWindow(ctypes.c_void_p(hwnd), 2)
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        return _is_true_fullscreen_geometry(
            (
                window_rect.left,
                window_rect.top,
                window_rect.right,
                window_rect.bottom,
            ),
            (
                info.rcMonitor.left,
                info.rcMonitor.top,
                info.rcMonitor.right,
                info.rcMonitor.bottom,
            ),
            is_maximized=bool(user32.IsZoomed(ctypes.c_void_p(hwnd))),
        )
    except (AttributeError, OSError, ValueError):
        return False


class DesktopPetEffectsWindow(QWidget):
    """Full-desktop, click-through effects canvas for webs and long trails."""

    def __init__(self, definition: PetDefinition) -> None:
        super().__init__(None)
        self.definition = definition
        self._suspended = False
        self._web_start = QPoint()
        self._web_anchor = QPoint()
        self._pet_center = QPoint()
        self._enemy = QPoint()
        self._ball = QPoint()
        self._effect_state = ""
        self._effect_progress = 0.0
        self._flight_direction = 1
        self.setObjectName("MoriceDesktopPetEffects")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.NoDropShadowWindowHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowTransparentForInput
        )

    def sync_from_pet(self, pet: "PetOverlayWindow") -> None:
        if self._suspended:
            self.hide()
            return
        state = pet.behavior.state
        show_web = self.definition.pet_id == "spiderman" and state in {
            "swing", "special", "escape", "enemy_web", "enemy_victory",
        }
        show_combat = self.definition.pet_id in {"ironman_mark42", "spiderman"} and state in {
            "enemy_alert", "enemy_chase", "enemy_attack", "enemy_web", "enemy_victory",
        }
        show_ball = self.definition.pet_id == "dog" and state in {
            "fetch_ready", "fetch_chase", "fetch_return", "fetch_celebrate",
        }
        show_flight = self.definition.pet_id == "ironman_mark42" and state in {
            "fast_flight", "bank", "barrel_roll", "enemy_chase",
        }
        if not (show_web or show_combat or show_ball or show_flight):
            self.hide()
            return
        area = _virtual_available_geometry()
        if self.geometry() != area:
            self.setGeometry(area)
        pet_origin = pet.mapToGlobal(QPoint(0, 0))
        hand_x = pet_origin.x() + (pet.width() * (3 if pet._direction > 0 else 1)) // 4
        hand_y = pet_origin.y() + pet.height() // 3
        self._web_start = QPoint(hand_x - area.left(), hand_y - area.top())
        self._pet_center = QPoint(
            pet_origin.x() + pet.width() // 2 - area.left(),
            pet_origin.y() + pet.height() // 2 - area.top(),
        )
        self._enemy = QPoint(
            round(pet._enemy_x + pet.width() / 2 - area.left()),
            round(pet._enemy_y + pet.height() / 2 - area.top()),
        )
        self._ball = QPoint(
            round(pet._fetch_ball_x - area.left()),
            round(pet._fetch_ball_y - area.top()),
        )
        if state == "swing":
            anchor_x = round(pet._swing_anchor_x)
            anchor_y = round(pet._swing_anchor_y)
        elif state in {"enemy_web", "enemy_victory"}:
            anchor_x = round(pet._enemy_x + pet.width() / 2)
            anchor_y = round(pet._enemy_y + pet.height() / 2)
        else:
            anchor_x = area.right() if pet._direction > 0 else area.left()
            anchor_y = area.top() + max(24, area.height() // 5)
        self._web_anchor = QPoint(anchor_x - area.left(), anchor_y - area.top())
        self._effect_state = state
        self._effect_progress = pet.behavior.progress()
        self._flight_direction = pet._direction
        if not self.isVisible():
            self.show()
        self.update()

    def set_suspended(self, suspended: bool) -> None:
        self._suspended = bool(suspended)
        if self._suspended:
            self.hide()

    def shutdown(self) -> None:
        self.hide()
        self.deleteLater()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        if not self._effect_state:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        state = self._effect_state
        if self.definition.pet_id == "ironman_mark42" and state in {
            "fast_flight", "bank", "barrel_roll", "enemy_chase",
        }:
            trail = 46 + round(24 * abs(math.sin(self._effect_progress * math.pi * 5)))
            direction = 1 if self._flight_direction >= 0 else -1
            for offset, alpha in ((-7, 170), (7, 120)):
                start = QPoint(self._pet_center.x() - direction * 7, self._pet_center.y() + offset)
                end = QPoint(start.x() - direction * trail, start.y() + 6)
                painter.setPen(QPen(QColor(30, 145, 210, alpha), 8, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(start, end)
                painter.setPen(QPen(QColor(190, 250, 255, 220), 2, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(start, end)

        if self.definition.pet_id == "spiderman" and state in {
            "swing", "special", "escape", "enemy_web", "enemy_victory",
        }:
            painter.setPen(QPen(QColor(18, 34, 54, 155), 4, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(self._web_start, self._web_anchor)
            painter.setPen(QPen(QColor(232, 247, 255, 235), 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(self._web_start, self._web_anchor)
            dx = self._web_anchor.x() - self._web_start.x()
            dy = self._web_anchor.y() - self._web_start.y()
            if math.hypot(dx, dy) > 120:
                for ratio in (0.22, 0.46, 0.70):
                    x = round(self._web_start.x() + dx * ratio)
                    y = round(self._web_start.y() + dy * ratio)
                    painter.drawLine(x - 3, y + 3, x + 3, y - 3)

        if state.startswith("enemy_"):
            fade = 1.0 - self._effect_progress if state == "enemy_victory" else 1.0
            painter.save()
            painter.setOpacity(max(0.08, fade))
            ex, ey = self._enemy.x(), self._enemy.y()
            if self.definition.pet_id == "ironman_mark42":
                # Original rogue drone: rounded hull, articulated fins, red sensor.
                painter.setPen(QPen(QColor("#151b27"), 3))
                painter.setBrush(QColor("#566579"))
                painter.drawEllipse(ex - 26, ey - 13, 52, 26)
                painter.setBrush(QColor("#263143"))
                painter.drawPolygon(QPolygon([
                    QPoint(ex - 22, ey - 5), QPoint(ex - 43, ey - 20),
                    QPoint(ex - 35, ey + 4), QPoint(ex - 22, ey + 8),
                ]))
                painter.drawPolygon(QPolygon([
                    QPoint(ex + 22, ey - 5), QPoint(ex + 43, ey - 20),
                    QPoint(ex + 35, ey + 4), QPoint(ex + 22, ey + 8),
                ]))
                painter.setBrush(QColor("#ff425b"))
                painter.drawEllipse(ex - 6, ey - 5, 12, 10)
                if state == "enemy_attack":
                    painter.setOpacity(0.9)
                    painter.setPen(QPen(QColor("#55dcff"), 10, Qt.SolidLine, Qt.RoundCap))
                    painter.drawLine(self._pet_center, self._enemy)
                    painter.setPen(QPen(QColor("#edffff"), 3, Qt.SolidLine, Qt.RoundCap))
                    painter.drawLine(self._pet_center, self._enemy)
                    radius = 12 + round(18 * abs(math.sin(self._effect_progress * math.pi * 5)))
                    painter.drawEllipse(self._enemy, radius, radius)
            else:
                # Masked tech raider: deliberately generic, readable, non-graphic.
                painter.setPen(QPen(QColor("#151321"), 3))
                painter.setBrush(QColor("#5d397d"))
                painter.drawEllipse(ex - 17, ey - 30, 34, 31)
                painter.setBrush(QColor("#29263e"))
                painter.drawRoundedRect(ex - 20, ey - 5, 40, 46, 12, 12)
                painter.setPen(QPen(QColor("#ff8bdd"), 3, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(ex - 9, ey - 18, ex - 2, ey - 15)
                painter.drawLine(ex + 9, ey - 18, ex + 2, ey - 15)
                if state in {"enemy_web", "enemy_victory"}:
                    painter.setPen(QPen(QColor("#edfaff"), 2, Qt.SolidLine, Qt.RoundCap))
                    for offset in range(-28, 29, 9):
                        painter.drawLine(ex - 24, ey + offset, ex + 24, ey - offset)
                    for radius in (16, 24, 32):
                        painter.drawEllipse(QPoint(ex, ey + 4), radius, round(radius * 1.35))
            painter.restore()

        if self.definition.pet_id == "dog" and state.startswith("fetch_"):
            bx, by = self._ball.x(), self._ball.y()
            if state == "fetch_return":
                bx = self._pet_center.x() + (-18 if self._pet_center.x() > self._ball.x() else 18)
                by = self._pet_center.y() + 4
            painter.setPen(QPen(QColor("#5a1720"), 2))
            painter.setBrush(QColor("#ef4c45"))
            painter.drawEllipse(bx - 8, by - 8, 16, 16)
            painter.setPen(QPen(QColor("#ffd7a5"), 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(bx - 4, by - 5, 8, 8, 40 * 16, 95 * 16)
        painter.end()


class PetOverlayWindow(QWidget):
    """A non-focus-stealing transparent pet surface with click/drag handling."""

    activated = Signal(str)
    dragged = Signal(QPoint)

    _SIZE_PIXELS = {"small": 64, "medium": 86, "large": 112}

    def __init__(
        self,
        definition: PetDefinition,
        *,
        click_action: str,
        size: str = "medium",
        animation_speed: str = "normal",
        interaction_enabled: bool = True,
        event_frequency: str = "normal",
        event_scheduler: RareEventScheduler | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.definition = definition
        self.click_action = normalize_open_action(click_action)
        self.interaction_enabled = bool(interaction_enabled)
        self._gesture = PointerGesture()
        self._press_offset = QPoint()
        self._feedback_until = 0.0
        self._hovered = False
        self._suspended = False
        self._direction = -1
        self._phase = 0.0
        self._speed = 20.0 if definition.movement == "ground" else 30.0
        self._last_tick = time.monotonic()
        self._rng = random.Random((os.getpid() << 8) ^ int(time.time()))
        self.behavior = BehaviorController(
            definition, rng=self._rng, now=self._last_tick
        )
        self.animation = AnimationController(animation_speed)
        self._last_behavior_state = self.behavior.state
        self._animation_frame = 0
        self._animation_progress = 0.0
        self._position_x = 0.0
        self._position_y = 0.0
        self._target_x = 0.0
        self._target_y = 0.0
        self._flight_anchor_y = 0.0
        self._swing_anchor_x = 0.0
        self._swing_anchor_y = 0.0
        self._swing_length = 220.0
        self._swing_angle = -0.7
        self._swing_angular_velocity = 1.4
        self._drag_started = False
        self._drag_sample_pos = QPoint()
        self._drag_sample_time = 0.0
        self._drop_velocity_x = 0.0
        self._drop_velocity_y = 0.0
        self._drop_bounces = 0
        self._event_frequency = normalize_event_frequency(event_frequency)
        self._event_scheduler = event_scheduler or RareEventScheduler(
            app_session_path().with_name("pet-events.json"),
            frequency=self._event_frequency,
        )
        self._next_event_poll = 0.0
        self._enemy_x = 0.0
        self._enemy_y = 0.0
        self._fetch_ball_x = 0.0
        self._fetch_ball_y = 0.0
        self._effects = DesktopPetEffectsWindow(definition)

        self.setObjectName("MoriceDesktopPet")
        self.setWindowTitle(f"MORICE Desktop Pet — {definition.name}")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.NoDropShadowWindowHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.configure_size(size)

        self._animation_timer = QTimer(self)
        self._animation_timer.setTimerType(Qt.CoarseTimer)
        self._animation_timer.setInterval(50)
        self._animation_timer.timeout.connect(self._tick)

    def configure_size(self, size: str) -> None:
        pixels = self._SIZE_PIXELS[normalize_pet_size(size)]
        self.setFixedSize(pixels, pixels)
        # Keep transparent corners from intercepting desktop clicks.
        inset = max(5, pixels // 14)
        self.setMask(QRegion(self.rect().adjusted(inset, inset // 2, -inset, 0), QRegion.Ellipse))

    def set_animation_speed(self, speed: object) -> None:
        self.animation.set_speed(speed)

    def configure_event_frequency(self, frequency: object) -> None:
        self._event_frequency = normalize_event_frequency(frequency)
        self._event_scheduler.set_frequency(self._event_frequency)

    def start(self) -> None:
        if self.pos().isNull():
            area = _virtual_available_geometry()
            start_x = area.right() - self.width() - 70
            if self.definition.movement in {"flight", "acrobat"}:
                start_y = area.top() + max(
                    40, (area.height() - self.height()) * 2 // 3
                )
            else:
                start_y = area.bottom() - self.height() + 1
            self.move(start_x, start_y)
        self._position_x = float(self.x())
        self._position_y = float(self.y())
        self._target_x = self._position_x
        self._target_y = self._position_y
        self._flight_anchor_y = self._position_y
        self._suspended = False
        self.show()
        self._effects.sync_from_pet(self)
        self._last_tick = time.monotonic()
        self._animation_timer.start()

    def shutdown(self) -> None:
        self._animation_timer.stop()
        self._effects.shutdown()
        self.hide()
        self.deleteLater()

    def set_suspended(self, suspended: bool) -> None:
        requested = bool(suspended)
        if requested == self._suspended:
            return
        self._suspended = requested
        if requested:
            self.behavior.cancel_event()
            self._animation_timer.stop()
            self._effects.set_suspended(True)
            self.hide()
        else:
            self.show()
            self._effects.set_suspended(False)
            self._last_tick = time.monotonic()
            self._animation_timer.start()

    def trigger_click_feedback(self) -> None:
        self._feedback_until = time.monotonic() + 0.34
        self.behavior.react()
        self.animation.set_state("react")
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.LeftButton:
            event.ignore()
            return
        global_pos = event.globalPosition().toPoint()
        self._press_offset = global_pos - self.frameGeometry().topLeft()
        app = QApplication.instance()
        drag_distance = app.startDragDistance() if app is not None else 10
        drag_time_ms = app.startDragTime() if app is not None else 500
        self._gesture.begin(
            global_pos.x(),
            global_pos.y(),
            time.monotonic(),
            drag_threshold=drag_distance,
            click_timeout_seconds=max(0.18, min(0.75, drag_time_ms / 1000.0)),
        )
        self._drag_started = False
        self._drag_sample_pos = global_pos
        self._drag_sample_time = time.monotonic()
        self._drop_velocity_x = 0.0
        self._drop_velocity_y = 0.0
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._gesture.active:
            event.ignore()
            return
        global_pos = event.globalPosition().toPoint()
        sample_time = time.monotonic()
        sample_elapsed = sample_time - self._drag_sample_time
        if sample_elapsed > 0.005:
            instant_x = (global_pos.x() - self._drag_sample_pos.x()) / sample_elapsed
            instant_y = (global_pos.y() - self._drag_sample_pos.y()) / sample_elapsed
            self._drop_velocity_x = self._drop_velocity_x * 0.45 + instant_x * 0.55
            self._drop_velocity_y = self._drop_velocity_y * 0.45 + instant_y * 0.55
            self._drag_sample_pos = global_pos
            self._drag_sample_time = sample_time
        if self._gesture.move(global_pos.x(), global_pos.y()) and self.interaction_enabled:
            if not self._drag_started:
                self._drag_started = True
                self.behavior.begin_drag()
                self.animation.set_state("dragged")
            target = global_pos - self._press_offset
            self.move(target)
            self._position_x = float(target.x())
            self._position_y = float(target.y())
            self._flight_anchor_y = self._position_y
            self.dragged.emit(target)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.LeftButton or not self._gesture.active:
            event.ignore()
            return
        global_pos = event.globalPosition().toPoint()
        result = self._gesture.finish(global_pos.x(), global_pos.y(), time.monotonic())
        if result == "click":
            # Feedback is painted first; activation is queued but not delayed.
            self.trigger_click_feedback()
            if self.click_action != DO_NOTHING:
                QTimer.singleShot(0, lambda: self.activated.emit(self.click_action))
        elif result == "drag":
            self._clamp_to_visible_desktop()
            if self._drag_started:
                self.behavior.end_drag()
                self.animation.set_state(self.behavior.state)
                self._drop_bounces = 0
                self._drop_velocity_x = max(-720.0, min(720.0, self._drop_velocity_x))
                self._drop_velocity_y = max(-760.0, min(760.0, self._drop_velocity_y))
        self._drag_started = False
        event.accept()

    def _clamp_to_visible_desktop(self) -> None:
        area = _virtual_available_geometry()
        x = max(area.left(), min(self.x(), area.right() - self.width() + 1))
        y = max(area.top(), min(self.y(), area.bottom() - self.height() + 1))
        self.move(x, y)
        self._position_x = float(x)
        self._position_y = float(y)
        self._flight_anchor_y = self._position_y

    def _choose_flight_target(self, state: str, area: QRect) -> None:
        """Choose targets across the entire virtual desktop, not a local band."""

        min_x = float(area.left())
        max_x = float(max(area.left(), area.right() - self.width() + 1))
        min_y = float(area.top() + 12)
        max_y = float(max(area.top() + 12, area.bottom() - self.height() + 1))
        ground_y = max_y

        if state == "enemy_chase":
            self._target_x = max(min_x, min(max_x, self._enemy_x - self.width() * 1.7))
            self._target_y = max(min_y, min(max_y, self._enemy_y))
        elif state == "fast_flight":
            midpoint = (min_x + max_x) / 2.0
            self._target_x = min_x if self._position_x >= midpoint else max_x
            self._target_y = self._rng.uniform(min_y, max_y)
        elif state in {"slow_flight", "bank", "barrel_roll"}:
            # Keep choosing destinations far enough away that motion reads as
            # genuine roaming, including climbs and dives.
            minimum_span = max(180.0, area.width() * 0.38)
            candidates = [min_x, max_x]
            random_x = self._rng.uniform(min_x, max_x)
            if abs(random_x - self._position_x) >= minimum_span:
                candidates.append(random_x)
            self._target_x = self._rng.choice(candidates)
            self._target_y = self._rng.uniform(min_y, max_y)
        elif state == "takeoff":
            self._target_x = max(min_x, min(max_x, self._position_x + self._rng.uniform(-160, 160)))
            self._target_y = self._rng.uniform(min_y, min_y + max(40.0, area.height() * 0.36))
        elif state in {"landing", "superhero_landing", "walk"}:
            self._target_x = self._rng.uniform(min_x, max_x)
            self._target_y = ground_y
        elif state == "edge_sit":
            self._target_x = self._rng.choice((min_x, max_x))
            self._target_y = self._rng.choice((min_y, ground_y))
        elif state == "escape":
            self._target_x = min_x if self._position_x > (min_x + max_x) / 2 else max_x
            self._target_y = self._rng.uniform(min_y, max_y)
        elif state in {
            "hover", "stabilize", "look", "special", "hard_stop",
            "enemy_alert", "enemy_attack", "enemy_victory", "armor_off",
        }:
            self._target_x = self._position_x
            self._target_y = self._position_y

        self._direction = 1 if self._target_x >= self._position_x else -1

    def _poll_special_events(self, now: float) -> None:
        if now < self._next_event_poll:
            return
        self._next_event_poll = now + 1.0
        if (
            self._event_frequency == "off"
            or self._gesture.active
            or self.behavior.major_event_active
            or self.behavior.state not in {"idle", "hover", "perch", "patrol", "sleep"}
        ):
            return
        event = self._event_scheduler.claim_due(self.definition.pet_id)
        if event is not None:
            self.behavior.queue_event(event.event_id, event.sequence, now)

    def _begin_event_state(self, state: str, area: QRect) -> None:
        min_x = float(area.left())
        max_x = float(area.right() - self.width() + 1)
        ground_y = float(area.bottom() - self.height() + 1)
        if state == "enemy_alert":
            opposite = min_x + area.width() * (0.18 if self._position_x > area.center().x() else 0.78)
            self._enemy_x = max(min_x + 30, min(max_x - 30, opposite))
            self._enemy_y = self._rng.uniform(
                float(area.top() + area.height() * 0.18),
                float(area.top() + area.height() * 0.60),
            )
            self._direction = 1 if self._enemy_x >= self._position_x else -1
        elif state == "enemy_chase":
            self._target_x = max(min_x, min(max_x, self._enemy_x - self._direction * self.width() * 1.6))
            self._target_y = self._enemy_y
        elif state in {"enemy_attack", "enemy_web", "enemy_victory"}:
            self._direction = 1 if self._enemy_x >= self._position_x else -1
        elif state == "fetch_ready":
            self._fetch_ball_x = max(
                min_x + 20,
                min(max_x - 20, self._position_x - self._direction * area.width() * 0.48),
            )
            self._fetch_ball_y = ground_y + self.height() * 0.72
        elif state == "fetch_chase":
            self._target_x = max(min_x, min(max_x, self._fetch_ball_x - self.width() * 0.2))
            self._target_y = ground_y
            self._direction = 1 if self._target_x >= self._position_x else -1
        elif state == "fetch_return":
            self._target_x = float(area.center().x() - self.width() // 2)
            self._target_y = ground_y
            self._direction = 1 if self._target_x >= self._position_x else -1
        elif state == "gallop":
            self._target_x = min_x if self._position_x > area.center().x() else max_x
            self._direction = 1 if self._target_x >= self._position_x else -1
        elif state == "symbiote_active":
            self._target_x = min_x if self._position_x > area.center().x() else max_x
            self._target_y = self._rng.uniform(
                float(area.top() + 30), float(area.bottom() - self.height() - 30)
            )
            self._direction = 1 if self._target_x >= self._position_x else -1

    def _advance_toward_target(self, speed: float, elapsed: float) -> bool:
        dx = self._target_x - self._position_x
        dy = self._target_y - self._position_y
        distance = math.hypot(dx, dy)
        if distance <= 1.0:
            self._position_x = self._target_x
            self._position_y = self._target_y
            return True
        step = min(distance, max(0.0, speed * elapsed * self.animation.speed_factor))
        self._position_x += dx / distance * step
        self._position_y += dy / distance * step
        return step >= distance

    def _begin_swing(self, area: QRect) -> None:
        center_x = self._position_x + self.width() / 2.0
        center_y = self._position_y + self.height() / 2.0
        horizontal_reach = max(180.0, min(area.width() * 0.30, 460.0))
        proposed_anchor = center_x + self._direction * horizontal_reach
        self._swing_anchor_x = max(
            float(area.left() + 20),
            min(float(area.right() - 20), proposed_anchor),
        )
        self._swing_anchor_y = float(area.top() + max(18, area.height() // 22))
        dx = center_x - self._swing_anchor_x
        dy = max(80.0, center_y - self._swing_anchor_y)
        self._swing_length = max(170.0, min(math.hypot(dx, dy), area.height() * 0.72))
        self._swing_angle = max(-1.05, min(1.05, math.atan2(dx, dy)))
        if abs(self._swing_angle) < 0.28:
            self._swing_angle = -0.55 * self._direction
        self._swing_angular_velocity = 1.65 * self._direction

    def _advance_swing(self, elapsed: float, area: QRect) -> None:
        # Lightweight pendulum dynamics: the web anchor remains fixed while
        # gravity accelerates the character through a smooth circular arc.
        gravity = 980.0
        acceleration = -(gravity / max(1.0, self._swing_length)) * math.sin(
            self._swing_angle
        )
        self._swing_angular_velocity += acceleration * elapsed
        self._swing_angular_velocity *= 0.997
        self._swing_angle += self._swing_angular_velocity * elapsed
        limit = 1.28
        if abs(self._swing_angle) > limit:
            self._swing_angle = math.copysign(limit, self._swing_angle)
            self._swing_angular_velocity *= -0.82

        center_x = self._swing_anchor_x + self._swing_length * math.sin(self._swing_angle)
        center_y = self._swing_anchor_y + self._swing_length * math.cos(self._swing_angle)
        self._position_x = center_x - self.width() / 2.0
        self._position_y = center_y - self.height() / 2.0
        min_x = float(area.left())
        max_x = float(area.right() - self.width() + 1)
        min_y = float(area.top())
        max_y = float(area.bottom() - self.height() + 1)
        self._position_x = max(min_x, min(max_x, self._position_x))
        self._position_y = max(min_y, min(max_y, self._position_y))
        self._direction = 1 if self._swing_angular_velocity >= 0 else -1

    def _advance_drop(self, elapsed: float, area: QRect) -> None:
        gravity = 1180.0
        self._drop_velocity_y += gravity * elapsed
        self._position_x += self._drop_velocity_x * elapsed
        self._position_y += self._drop_velocity_y * elapsed
        min_x = float(area.left())
        max_x = float(area.right() - self.width() + 1)
        ground_y = float(area.bottom() - self.height() + 1)
        if self._position_x <= min_x or self._position_x >= max_x:
            self._position_x = max(min_x, min(max_x, self._position_x))
            self._drop_velocity_x *= -0.42
        if self._position_y >= ground_y:
            self._position_y = ground_y
            if self._drop_bounces == 0 and self._drop_velocity_y > 180.0:
                self._drop_bounces = 1
                self._drop_velocity_y *= -0.30
                self._drop_velocity_x *= 0.64
            else:
                self._drop_velocity_x = 0.0
                self._drop_velocity_y = 0.0
                self.behavior.force("react", 0.72)
                self.animation.set_state("react")
        self._position_y = max(float(area.top()), self._position_y)

    def _tick(self) -> None:
        if self._suspended:
            return
        now = time.monotonic()
        elapsed = max(0.0, min(0.2, now - self._last_tick))
        self._last_tick = now
        if self._gesture.active:
            # Keep the body, eyes, tail, limbs, and struggle pose alive while
            # the window follows the pointer. Position remains mouse-driven.
            self._phase = (
                self._phase + elapsed * 8.5 * self.animation.speed_factor
            ) % math.tau
            self._animation_frame, self._animation_progress = self.animation.sample(now)
            self._effects.sync_from_pet(self)
            self.update()
            return
        state = self.behavior.update(now)
        area = _virtual_available_geometry()
        self._poll_special_events(now)
        state = self.behavior.state
        if state != self._last_behavior_state:
            self._last_behavior_state = state
            self.animation.set_state(state, now)
            if self._rng.random() < 0.22:
                self._direction *= -1
            if self.definition.movement == "flight":
                self._choose_flight_target(state, area)
            elif self.definition.movement == "acrobat" and state == "swing":
                self._begin_swing(area)
            if self.behavior.major_event_active:
                self._begin_event_state(state, area)
        speed_factor = self.animation.speed_factor
        self._phase = (self._phase + elapsed * 5.2 * speed_factor) % math.tau
        self._animation_frame, self._animation_progress = self.animation.sample(now)

        ground_y = float(area.bottom() - self.height() + 1)
        moving = state in {
            "patrol", "play", "swing", "special", "escape", "walk", "gallop",
            "fetch_chase", "fetch_return", "enemy_chase", "symbiote_active",
        }
        movement_multiplier = {
            "play": 1.35,
            "swing": 2.0,
            "special": 1.25,
            "escape": 2.8,
            "gallop": 4.8,
            "fetch_chase": 4.2,
            "fetch_return": 2.8,
            "enemy_chase": 5.0,
            "symbiote_active": 4.0,
        }.get(state, 1.0)
        if state == "falling":
            self._advance_drop(elapsed, area)
        elif moving and self.definition.movement != "flight" and not (
            self.definition.movement == "acrobat" and state == "swing"
        ):
            self._position_x += (
                self._direction
                * self._speed
                * movement_multiplier
                * elapsed
                * speed_factor
            )

        if state == "falling":
            pass
        elif self.definition.movement == "flight":
            flight_speeds = {
                "slow_flight": 105.0,
                "fast_flight": 620.0,
                "bank": 300.0,
                "barrel_roll": 360.0,
                "takeoff": 280.0,
                "landing": 330.0,
                "superhero_landing": 180.0,
                "walk": 58.0,
                "edge_sit": 340.0,
                "escape": 690.0,
                "enemy_chase": 520.0,
            }
            speed = flight_speeds.get(state, 0.0)
            arrived = self._advance_toward_target(speed, elapsed) if speed else False
            if arrived and state in {"slow_flight", "fast_flight", "bank", "barrel_roll"}:
                self._choose_flight_target(state, area)
            self._flight_anchor_y = self._position_y
        elif self.definition.movement == "acrobat":
            min_y = float(area.top() + 20)
            max_y = float(area.bottom() - self.height() + 1)
            self._flight_anchor_y = max(
                min_y, min(self._flight_anchor_y, max_y)
            )
            if state in {"enemy_chase", "symbiote_active"}:
                self._advance_toward_target(
                    560.0 if state == "enemy_chase" else 410.0, elapsed
                )
                self._flight_anchor_y = self._position_y
                vertical_offset = 0.0
            elif state == "perch":
                target_anchor = min_y + 8
                self._flight_anchor_y += (
                    target_anchor - self._flight_anchor_y
                ) * min(1.0, elapsed * 2.4)
                vertical_offset = 0.0
            elif state == "swing":
                self._advance_swing(elapsed, area)
                vertical_offset = 0.0
            elif state == "escape":
                vertical_offset = -math.sin(
                    self.behavior.progress(now) * math.pi
                ) * min(90.0, area.height() * 0.16)
            else:
                amplitude = 5.0 if state in {"idle", "hover", "react"} else 14.0
                vertical_offset = math.sin(self._phase * 0.68) * amplitude
            if state not in {"swing", "enemy_chase", "symbiote_active"}:
                self._position_y = max(
                    min_y,
                    min(self._flight_anchor_y + vertical_offset, max_y),
                )
        else:
            jump_height = 0.0
            if state in {"play", "special", "rear", "fetch_celebrate"}:
                jump_height = math.sin(
                    self.behavior.progress(now) * math.pi
                ) * min(34.0, self.height() * 0.28)
            self._position_y = ground_y - jump_height

        if (
            self._position_x <= area.left()
            or self._position_x + self.width() >= area.right() + 1
        ):
            self._direction *= -1
            self._position_x = max(
                float(area.left()),
                min(
                    self._position_x,
                    float(area.right() - self.width() + 1),
                ),
            )
        self.move(round(self._position_x), round(self._position_y))
        self._effects.sync_from_pet(self)
        desired_interval = 120 if state == "sleep" else 80 if state in {"idle", "perch"} else 40
        if self._animation_timer.interval() != desired_interval:
            self._animation_timer.setInterval(desired_interval)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        if self._direction > 0:
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        unit = max(1, self.width() // 28)
        feedback = time.monotonic() < self._feedback_until
        state = self.behavior.state
        frame, cycle_progress = self.animation.sample()
        bob_scale = 0.0 if state in {"sleep", "perch", "dragged"} else 0.45
        bob = round(math.sin(self._phase) * unit * bob_scale)
        if self._hovered:
            bob -= max(1, unit // 2)
        painter.translate(0, bob)
        if state == "falling":
            painter.translate(self.width() / 2, self.height() / 2)
            painter.rotate(max(-24.0, min(24.0, self._drop_velocity_x * 0.035)))
            stretch = min(0.12, abs(self._drop_velocity_y) / 4200.0)
            painter.scale(1.0 - stretch * 0.45, 1.0 + stretch)
            painter.translate(-self.width() / 2, -self.height() / 2)
        if state == "swing" and self.definition.movement == "acrobat":
            painter.translate(self.width() / 2, self.height() / 2)
            painter.rotate(-math.degrees(self._swing_angle) * 0.42)
            painter.translate(-self.width() / 2, -self.height() / 2)
        if self.definition.pet_id == "ironman_mark42" and state in {
            "slow_flight", "fast_flight", "bank", "barrel_roll", "hard_stop",
            "takeoff", "enemy_chase",
        }:
            painter.translate(self.width() / 2, self.height() / 2)
            if state == "barrel_roll":
                painter.rotate(self.behavior.progress() * 360.0)
            elif state == "bank":
                painter.rotate(math.sin(self.behavior.progress() * math.pi) * 27.0)
            elif state == "fast_flight":
                painter.rotate(-32.0)
            elif state == "slow_flight":
                painter.rotate(-12.0)
            elif state == "enemy_chase":
                painter.rotate(-26.0)
            elif state == "hard_stop":
                painter.rotate(16.0)
            elif state == "takeoff":
                painter.rotate(-8.0)
            # A slightly reduced rig keeps the pitched body inside the shaped
            # overlay; the tiny pulse gives thrust depth without widening legs.
            depth_scale = 0.91 + (
                math.sin(self.behavior.progress() * math.pi) * 0.035
                if state in {"fast_flight", "bank", "barrel_roll", "enemy_chase"}
                else 0.03
            )
            painter.scale(depth_scale, depth_scale)
            painter.translate(-self.width() / 2, -self.height() / 2)
        if state == "escape" and self.definition.movement == "flight":
            painter.translate(self.width() / 2, self.height() / 2)
            painter.rotate(math.sin(cycle_progress * math.tau) * 22.0)
            painter.translate(-self.width() / 2, -self.height() / 2)
        _draw_contact_shadow(
            painter,
            self.width(),
            self.height(),
            unit,
            airborne=self.definition.movement in {"flight", "acrobat"}
            and state not in {"perch", "dragged"},
        )
        renderer = getattr(_ProceduralPetArt, self.definition.renderer, _ProceduralPetArt.dog)
        renderer(
            painter,
            self.width(),
            self.height(),
            unit,
            self._phase,
            feedback,
            state,
            frame,
            self.behavior.progress(),
        )
        painter.end()

    def effect_window_id(self) -> int:
        return int(self._effects.winId()) if self._effects.isVisible() else 0


def _draw_contact_shadow(
    painter: QPainter,
    width: int,
    height: int,
    unit: int,
    *,
    airborne: bool = False,
) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(0, 0, 0, 42 if airborne else 82))
    inset = width // 3 if airborne else width // 5
    painter.drawEllipse(
        QRect(inset, height - 5 * unit, width - inset * 2, 2 * unit if airborne else 3 * unit)
    )


class _ProceduralPetArt:
    """Original layered character art with shaped, readable silhouettes."""

    @staticmethod
    def _rect(painter: QPainter, color: str | QColor, x: int, y: int, w: int, h: int, u: int) -> None:
        painter.fillRect(QRect(x * u, y * u, w * u, h * u), QColor(color))

    @staticmethod
    def _ellipse(
        painter: QPainter,
        color: str | QColor,
        x: float,
        y: float,
        width: float,
        height: float,
        u: int,
        outline: str | QColor | None = None,
    ) -> None:
        painter.setBrush(QColor(color))
        painter.setPen(QPen(QColor(outline), max(1, u // 2)) if outline else Qt.NoPen)
        painter.drawEllipse(
            QRect(round(x * u), round(y * u), round(width * u), round(height * u))
        )

    @staticmethod
    def _poly(
        painter: QPainter,
        color: str | QColor,
        points: list[tuple[float, float]],
        u: int,
        outline: str | QColor | None = None,
    ) -> None:
        painter.setBrush(QColor(color))
        painter.setPen(QPen(QColor(outline), max(1, u // 2)) if outline else Qt.NoPen)
        painter.drawPolygon(QPolygon([QPoint(round(x * u), round(y * u)) for x, y in points]))

    @staticmethod
    def _stroke(
        painter: QPainter,
        color: str | QColor,
        points: list[tuple[float, float]],
        width: float,
        u: int,
    ) -> None:
        if len(points) < 2:
            return
        path = QPainterPath(QPoint(round(points[0][0] * u), round(points[0][1] * u)))
        for x, y in points[1:]:
            path.lineTo(round(x * u), round(y * u))
        pen = QPen(QColor(color), max(1.0, width * u), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(pen)
        painter.drawPath(path)

    @classmethod
    def dog(
        cls, p: QPainter, w: int, h: int, u: int, phase: float,
        feedback: bool, state: str, frame: int, progress: float,
    ) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        base = h / u - 2.0
        coat, light, dark, outline = "#9b5a2b", "#dda05a", "#5a301d", "#2b1b17"
        if state == "sleep":
            breath = .5 * (1 + math.sin(phase))
            cls._ellipse(p, outline, 4.0, base - 10.0 - breath, 17.0, 8.5 + breath, u)
            cls._ellipse(p, coat, 4.7, base - 10.7 - breath, 15.7, 7.8 + breath, u)
            cls._ellipse(p, light, 16.0, base - 9.8, 7.2, 6.2, u, outline)
            cls._poly(p, dark, [(17, base - 10), (19, base - 13), (20.5, base - 9)], u, outline)
            cls._ellipse(p, "#19181a", 21.2, base - 7.5, 1.8, 1.3, u)
            return
        stride = (
            math.sin(phase * 3.2) * 3.0
            if state in {"fetch_chase", "fetch_return"}
            else math.sin(phase * 2.0) * 2.2 if state in {"patrol", "play"} else 0.0
        )
        struggle = math.sin(phase * 3.0) * 2.0 if state == "dragged" else 0.0
        body_y = base - 11.5
        tail_wag = (
            math.sin(phase * 5.0) * 3.2
            if state in {"fetch_ready", "fetch_celebrate"}
            else struggle
        )
        cls._stroke(p, dark, [(5.0, body_y + 3.0), (2.2, body_y + tail_wag), (1.0, body_y - 1.0 + tail_wag)], 2.3, u)
        cls._ellipse(p, outline, 4.0, body_y, 15.5, 8.2, u)
        cls._ellipse(p, coat, 4.7, body_y + .4, 14.2, 7.2, u)
        cls._ellipse(p, light, 6.0, body_y + 1.1, 6.8, 3.6, u)
        cls._stroke(p, outline, [(8.0, body_y + 6), (7.0 - stride, base - 1)], 3.0, u)
        cls._stroke(p, outline, [(16.0, body_y + 6), (17.0 + stride, base - 1)], 3.0, u)
        cls._stroke(p, dark, [(8.0, body_y + 6), (7.0 - stride, base - 1)], 2.1, u)
        cls._stroke(p, dark, [(16.0, body_y + 6), (17.0 + stride, base - 1)], 2.1, u)
        head_y = body_y - 4.0 + (.8 if feedback else 0) + (1.2 if state == "fetch_ready" else 0)
        cls._ellipse(p, outline, 15.0, head_y, 9.2, 8.8, u)
        cls._ellipse(p, coat, 15.6, head_y + .5, 8.0, 7.7, u)
        cls._ellipse(p, light, 19.0, head_y + 4.0, 6.5, 4.0, u, outline)
        cls._poly(p, dark, [(16.0, head_y + 1), (14.0, head_y - 1), (15.1, head_y + 5.0), (18.0, head_y + 2.0)], u, outline)
        cls._ellipse(p, "#f9e7a8", 19.0, head_y + 2.2, 1.2, 1.2, u, outline)
        cls._ellipse(p, "#17171a", 24.0, head_y + 5.0, 1.7, 1.5, u)

    @classmethod
    def cat(
        cls, p: QPainter, w: int, h: int, u: int, phase: float,
        feedback: bool, state: str, frame: int, progress: float,
    ) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        base = h / u - 2.0
        fur, light, dark, outline = "#806493", "#b69ac6", "#493752", "#251f2b"
        if state in {"sleep", "cat_bed", "cat_deep_sleep"}:
            breath = .4 * (1 + math.sin(phase))
            if state in {"cat_bed", "cat_deep_sleep"}:
                cls._ellipse(p, "#493f58", 2.5, base - 8.2, 22.0, 8.0, u, outline)
                cls._ellipse(p, "#d7c4e5", 3.5, base - 7.5, 20.0, 6.2, u, "#6c5a7a")
            cls._ellipse(p, outline, 4.0, base - 10.0 - breath, 18.0, 8.5 + breath, u)
            cls._ellipse(p, fur, 4.7, base - 10.5 - breath, 16.5, 7.6 + breath, u)
            cls._stroke(p, dark, [(7.0, base - 5), (4.0, base - 8), (8.0, base - 11)], 2.0, u)
            cls._ellipse(p, light, 16.0, base - 10.0, 6.5, 6.2, u, outline)
            return
        stretch = 3.0 * math.sin(progress * math.pi) if state == "cat_stretch" else 0.0
        stride = math.sin(phase * 2.2) * 2.0 if state == "patrol" else 0.0
        tail_wave = math.sin(phase * (2.4 if state in {"play", "dragged"} else 1.15)) * 2.5
        body_y = base - 11.0
        cls._stroke(p, dark, [(6.0, body_y + 3), (2.0, body_y - 1 + tail_wave), (3.0, body_y - 6 + tail_wave)], 2.0, u)
        cls._ellipse(p, outline, 5.0 - stretch, body_y, 14.5 + stretch, 7.8, u)
        cls._ellipse(p, fur, 5.6 - stretch, body_y + .4, 13.3 + stretch, 6.8, u)
        cls._stroke(p, dark, [(8.5, body_y + 6), (7.5 - stride, base - 1)], 2.3, u)
        cls._stroke(p, dark, [(16.0, body_y + 6), (17.0 + stride, base - 1)], 2.3, u)
        head_y = body_y - 4.0 + (1.0 if feedback else 0.0)
        cls._ellipse(p, outline, 15.0, head_y, 8.5, 8.0, u)
        cls._ellipse(p, fur, 15.6, head_y + .5, 7.3, 6.8, u)
        ear_twitch = .8 if (feedback or state == "react") and frame % 2 else 0.0
        cls._poly(p, light, [(16.0, head_y + 1.2 + ear_twitch), (16.8, head_y - 2.0 + ear_twitch), (19.0, head_y + .5)], u, outline)
        cls._poly(p, light, [(20.0, head_y + .4), (22.3, head_y - 1.8), (22.5, head_y + 2.0)], u, outline)
        cls._poly(p, "#8df2c5", [(17.2, head_y + 3), (18.5, head_y + 3.4), (17.2, head_y + 3.8)], u, outline)
        cls._poly(p, "#8df2c5", [(21.3, head_y + 3), (20.0, head_y + 3.4), (21.3, head_y + 3.8)], u, outline)
        cls._ellipse(p, "#e3a1ad", 18.7, head_y + 4.8, 1.3, 1.0, u)

    @classmethod
    def horse(
        cls, p: QPainter, w: int, h: int, u: int, phase: float,
        feedback: bool, state: str, frame: int, progress: float,
    ) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        base = h / u - 2.0
        coat, light, mane, outline = "#a96535", "#d59a5c", "#59311f", "#29201c"
        stride = (
            math.sin(phase * 4.0) * 4.0
            if state == "gallop"
            else math.sin(phase * 2.3) * 2.6 if state in {"patrol", "play"} else 0.0
        )
        struggle = math.sin(phase * 2.7) * 2.0 if state == "dragged" else 0.0
        body_y = base - 14.0
        cls._stroke(p, mane, [(5.0, body_y + 3), (1.8, body_y + struggle), (1.0, body_y + 5 + struggle)], 2.3, u)
        cls._ellipse(p, outline, 3.0, body_y, 17.0, 8.2, u)
        cls._ellipse(p, coat, 3.7, body_y + .5, 15.6, 7.1, u)
        cls._ellipse(p, light, 7.0, body_y + 1.0, 8.0, 3.0, u)
        cls._stroke(p, outline, [(7.0, body_y + 6), (6.0 - stride, base - 1)], 3.0, u)
        cls._stroke(p, outline, [(16.5, body_y + 6), (18.0 + stride, base - 1)], 3.0, u)
        cls._stroke(p, coat, [(7.0, body_y + 6), (6.0 - stride, base - 1)], 2.1, u)
        cls._stroke(p, coat, [(16.5, body_y + 6), (18.0 + stride, base - 1)], 2.1, u)
        grazing = state == "graze"
        neck_mid = (20.0, body_y + 8.0) if grazing else (18.5, body_y - 5.5)
        neck_end = (22.0, body_y + 9.5) if grazing else (21.0, body_y - 8.5)
        cls._stroke(p, outline, [(17.0, body_y + 2), neck_mid, neck_end], 5.0, u)
        cls._stroke(p, coat, [(17.0, body_y + 2), neck_mid, neck_end], 3.8, u)
        head_y = (body_y + 7.0 if grazing else body_y - 10.5) + (1.2 if feedback or state == "react" else 0.0)
        cls._ellipse(p, outline, 18.0, head_y, 7.5, 6.4, u)
        cls._ellipse(p, coat, 18.6, head_y + .4, 6.5, 5.4, u)
        cls._ellipse(p, light, 22.0, head_y + 3.0, 5.0, 3.2, u, outline)
        cls._poly(p, coat, [(19.4, head_y + .5), (19.2, head_y - 2.2), (21.0, head_y + .1)], u, outline)
        cls._poly(p, coat, [(22.1, head_y + .2), (23.0, head_y - 2.0), (23.8, head_y + 1.0)], u, outline)
        cls._stroke(p, mane, [(17.7, body_y - 1), (17.0, body_y - 5), (18.2, body_y - 9)], 1.6, u)
        cls._ellipse(p, "#16191d", 22.0, head_y + 1.8, 1.1, 1.1, u)
        if grazing:
            for blade_x in (20.0, 22.0, 24.0, 26.0):
                cls._stroke(p, "#4b9a52", [(blade_x, base), (blade_x - .7, base - 3.0)], .75, u)
        if state == "rear":
            cls._stroke(p, coat, [(8.0, body_y + 4), (3.0, body_y - 2)], 2.2, u)
            cls._stroke(p, coat, [(11.0, body_y + 5), (7.0, body_y - 3)], 2.2, u)

    @classmethod
    def skeleton(
        cls, p: QPainter, w: int, h: int, u: int, phase: float,
        feedback: bool, state: str, frame: int, progress: float,
    ) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        bone, shade, socket = "#e9e4d3", "#aeb7b7", "#273038"
        base = h / u - 2.0
        rattle = math.sin(phase * 3.2) * (1.5 if feedback or state in {"react", "dragged"} else .35)
        if state in {"special", "skeleton_collapse", "skeleton_scatter", "skeleton_reform"}:
            if state == "skeleton_scatter":
                collapse = 1.0
                spread = 4.0 + math.sin(phase * 1.8) * 1.2
            elif state == "skeleton_reform":
                collapse = 1.0 - progress
                spread = collapse * 5.0
            else:
                collapse = progress if state == "skeleton_collapse" else math.sin(progress * math.pi)
                spread = collapse * 4.0
            cls._ellipse(p, bone, 10 + rattle, 3 + collapse * 15, 8, 7, u, shade)
            cls._ellipse(p, socket, 12 + rattle, 5 + collapse * 15, 1.5, 1.8, u)
            cls._ellipse(p, socket, 15 + rattle, 5 + collapse * 15, 1.5, 1.8, u)
            cls._stroke(p, bone, [(9 - spread, 18 + collapse * 5), (3, 23)], 1.8, u)
            cls._stroke(p, bone, [(19 + spread, 18 + collapse * 5), (25, 24)], 1.8, u)
            cls._stroke(p, bone, [(12 - spread * .4, 19), (7, 27)], 1.8, u)
            cls._stroke(p, bone, [(16 + spread * .4, 20), (21, 27)], 1.8, u)
            cls._stroke(p, bone, [(7, 14 + collapse * 9), (21, 14 + collapse * 9)], 1.6, u)
            return
        stride = math.sin(phase * 2.1) * 2.2 if state == "patrol" else 0.0
        head_y = 2.0 + abs(rattle) * .25
        cls._ellipse(p, shade, 10.4 + rattle, head_y + .6, 8.0, 7.2, u)
        cls._ellipse(p, bone, 9.8 + rattle, head_y, 8.0, 7.2, u, shade)
        cls._ellipse(p, socket, 11.5 + rattle, head_y + 2.2, 1.8, 2.0, u)
        cls._ellipse(p, socket, 15.0 + rattle, head_y + 2.2, 1.8, 2.0, u)
        cls._poly(p, socket, [(13.5 + rattle, head_y + 4.2), (14.5 + rattle, head_y + 4.2), (14.0 + rattle, head_y + 5.3)], u)
        cls._stroke(p, bone, [(14 + rattle, 9), (14, 17)], 2.0, u)
        for rib_y, rib_width in ((10.5, 4.4), (12.3, 5.0), (14.1, 4.2)):
            cls._stroke(p, bone, [(14, rib_y), (14 - rib_width, rib_y + 1.3)], 1.2, u)
            cls._stroke(p, bone, [(14, rib_y), (14 + rib_width, rib_y + 1.3)], 1.2, u)
        arm_wave = 2.4 if state == "dragged" else 0.0
        cls._stroke(p, bone, [(10, 10.5), (6 - arm_wave, 15), (5, 19)], 1.8, u)
        cls._stroke(p, bone, [(18, 10.5), (22 + arm_wave, 15), (23, 19)], 1.8, u)
        cls._stroke(p, bone, [(12.5, 17), (10 - stride, 22), (9 - stride, base)], 2.0, u)
        cls._stroke(p, bone, [(15.5, 17), (18 + stride, 22), (19 + stride, base)], 2.0, u)
        for joint_x, joint_y in ((10, 10.5), (18, 10.5), (6 - arm_wave, 15), (22 + arm_wave, 15), (12.5, 17), (15.5, 17)):
            cls._ellipse(p, bone, joint_x - .8, joint_y - .8, 1.6, 1.6, u, shade)

    @classmethod
    def armored_flyer(
        cls, p: QPainter, w: int, h: int, u: int, phase: float,
        feedback: bool, state: str, frame: int, progress: float,
    ) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        red, red_dark = "#a3262d", "#591c25"
        gold, gold_light = "#d9a93d", "#ffe08a"
        outline, glow = "#301820", "#7defff"
        base = h / u - 2.0
        struggle = math.sin(phase * 2.5) * 1.8 if state == "dragged" else 0.0
        stride = math.sin(phase * 2.1) * 2.1 if state == "walk" else 0.0
        crouch = 4.4 if state == "superhero_landing" else 1.7 if state in {"landing", "edge_sit"} else 0.0
        torso_top = 8.0 + crouch
        streamlined_flight = state in {
            "slow_flight", "fast_flight", "bank", "barrel_roll", "takeoff",
            "escape", "enemy_chase", "enemy_attack", "enemy_victory",
        }

        # Thrusters sit behind the figure. Ambient actions never fire a beam;
        # the palms only stabilize or flash in direct response to the user.
        thrusters = state in {
            "hover", "slow_flight", "fast_flight", "bank", "barrel_roll",
            "hard_stop", "stabilize", "takeoff", "escape", "dragged",
            "enemy_chase", "enemy_attack", "enemy_victory",
        }
        if thrusters:
            flame = 3.0 + (frame % 3) + (2.5 if state in {"fast_flight", "takeoff", "escape"} else 0.0)
            thruster_feet = (13.0, 15.0) if streamlined_flight else (11.4, 16.6)
            for foot_x in thruster_feet:
                cls._poly(p, "#1a789e", [(foot_x - 1.6, base - 1), (foot_x + 1.6, base - 1), (foot_x, base + flame)], u)
                cls._poly(p, "#baf8ff", [(foot_x - .7, base - 1), (foot_x + .7, base - 1), (foot_x, base + flame - 1.1)], u)

        if state == "armor_off":
            separation = math.sin(min(1.0, progress * 1.45) * math.pi / 2)
            if progress > 0.68:
                separation = max(0.0, (1.0 - progress) / 0.32)
            # Casual person beneath the modular armor, with a tiny coffee cup.
            cls._ellipse(p, "#d1a07c", 11.2, 3.0, 5.6, 5.8, u, outline)
            cls._poly(p, "#26394b", [(10.3, 8.0), (17.7, 8.0), (16.8, 17.0), (11.2, 17.0)], u, outline)
            cls._stroke(p, "#24303c", [(12.0, 16.0), (11.3, 24.0)], 2.2, u)
            cls._stroke(p, "#24303c", [(16.0, 16.0), (17.0, 24.0)], 2.2, u)
            cls._stroke(p, "#d1a07c", [(17.1, 10.0), (20.5, 13.2)], 1.8, u)
            cls._ellipse(p, "#e7edf2", 20.0, 12.0, 2.8, 3.0, u, "#6a7077")
            modules = [
                (14, 4, 0, -9, gold), (10, 10, -9, -3, red),
                (18, 10, 9, -3, red), (11, 19, -8, 7, gold),
                (17, 19, 8, 7, gold), (14, 13, 0, 10, red),
            ]
            for x, y, dx, dy, color in modules:
                cls._ellipse(p, color, x - 1 + dx * separation, y - 1 + dy * separation, 2.4, 2.4, u, outline)
            return

        # Pose skeleton: round joints and tapered plates create an actual body
        # silhouette rather than a stack of rectangular tiles.
        left_shoulder = (10.3, torso_top + 1.5)
        right_shoulder = (17.7, torso_top + 1.5)
        left_elbow = (8.1 + struggle, torso_top + 6.0)
        right_elbow = (19.9 - struggle, torso_top + 6.0)
        left_hand = (7.8 + struggle, torso_top + 11.0)
        right_hand = (20.2 - struggle, torso_top + 11.0)
        if state in {"slow_flight", "fast_flight", "bank", "barrel_roll", "escape", "enemy_chase"}:
            # Cruise pose: both arms are swept tightly beside the torso.  This
            # avoids the unrelated one-arm repulsor/salute silhouette.
            left_elbow, right_elbow = (9.5, torso_top + 7.2), (18.5, torso_top + 7.2)
            left_hand, right_hand = (11.0, torso_top + 12.4), (17.0, torso_top + 12.4)
        elif state in {"stabilize", "hard_stop", "enemy_attack"}:
            left_elbow, right_elbow = (6.7, torso_top + 4), (21.3, torso_top + 4)
            left_hand, right_hand = (5.0, torso_top + 8), (23.0, torso_top + 8)
        elif state == "superhero_landing":
            left_elbow, left_hand = (7.0, 18.0), (5.2, 23.5)
            right_elbow, right_hand = (20.2, 15.0), (22.2, 18.5)

        cls._stroke(p, outline, [left_shoulder, left_elbow, left_hand], 3.0, u)
        cls._stroke(p, outline, [right_shoulder, right_elbow, right_hand], 3.0, u)
        cls._stroke(p, red, [left_shoulder, left_elbow, left_hand], 2.05, u)
        cls._stroke(p, red, [right_shoulder, right_elbow, right_hand], 2.05, u)
        # Separate shoulder, bicep, and forearm modules retain the M42
        # modular-armor identity even at the medium 86 px preset.
        for shoulder_x, shoulder_y in (left_shoulder, right_shoulder):
            cls._ellipse(p, gold, shoulder_x - 1.45, shoulder_y - 1.3, 2.9, 2.6, u, outline)
            cls._ellipse(p, gold_light, shoulder_x - .75, shoulder_y - .85, .75, 1.05, u)
        for elbow_x, elbow_y in (left_elbow, right_elbow):
            cls._ellipse(p, red_dark, elbow_x - 1.45, elbow_y - 1.45, 2.9, 2.9, u, outline)
            cls._ellipse(p, gold, elbow_x - .85, elbow_y - .85, 1.7, 1.7, u)
        for x, y in (left_hand, right_hand):
            cls._ellipse(p, red_dark, x - 1.45, y - 1.35, 2.9, 2.7, u, outline)
            cls._ellipse(p, glow if feedback else gold_light, x - .9, y - .85, 1.8, 1.7, u)
            # Three readable articulated fingers around each palm emitter.
            finger_direction = -1.0 if y < torso_top + 8 else 1.0
            finger_motion = (
                .32 * math.sin(phase * 3.4)
                if state in {"dragged", "react", "stabilize"} or feedback
                else 0.0
            )
            finger_pen = QPen(
                QColor(gold), max(1.0, u * .42), Qt.SolidLine, Qt.RoundCap
            )
            p.setPen(finger_pen)
            for index, offset in enumerate((-.65, 0.0, .65)):
                spread = offset * (1.0 + finger_motion * (index - 1))
                p.drawLine(
                    round((x + spread * .45) * u),
                    round((y + finger_direction * .65) * u),
                    round((x + spread) * u),
                    round((y + finger_direction * 1.35) * u),
                )

        hip_y = torso_top + 9.2
        if streamlined_flight:
            # The Mark 42's flight silhouette stays aerodynamic: thighs,
            # knees, boots, and exhaust are centered rather than splayed.
            left_knee, left_foot = (12.8, 19.8), (13.1, 25.0)
            right_knee, right_foot = (15.2, 19.8), (14.9, 25.0)
        elif state == "superhero_landing":
            left_knee, left_foot = (10.0, 20.0), (6.2, 24.5)
            right_knee, right_foot = (18.7, 19.2), (21.7, 24.2)
        elif state == "edge_sit":
            left_knee, left_foot = (10.5, 21.0), (9.7, 25.0)
            right_knee, right_foot = (17.5, 21.0), (18.4, 25.0)
        else:
            left_knee, left_foot = (11.8 - stride, 19.7), (11.5 - stride, 25.0)
            right_knee, right_foot = (16.2 + stride, 19.7), (16.5 + stride, 25.0)
        cls._stroke(p, outline, [(12.0, hip_y), left_knee, left_foot], 3.35, u)
        cls._stroke(p, outline, [(16.0, hip_y), right_knee, right_foot], 3.35, u)
        cls._stroke(p, gold, [(12.0, hip_y), left_knee, left_foot], 2.4, u)
        cls._stroke(p, gold, [(16.0, hip_y), right_knee, right_foot], 2.4, u)
        cls._ellipse(p, red, left_knee[0] - 1.4, left_knee[1] - 1.1, 2.8, 2.2, u, outline)
        cls._ellipse(p, red, right_knee[0] - 1.4, right_knee[1] - 1.1, 2.8, 2.2, u, outline)
        for knee, foot in ((left_knee, left_foot), (right_knee, right_foot)):
            mid_x = (knee[0] + foot[0]) / 2
            mid_y = (knee[1] + foot[1]) / 2
            cls._poly(
                p,
                red,
                [
                    (mid_x - 1.15, mid_y - 1.7),
                    (mid_x + 1.15, mid_y - 1.4),
                    (mid_x + .85, mid_y + 1.8),
                    (mid_x - .75, mid_y + 1.6),
                ],
                u,
                outline,
            )
            cls._ellipse(p, gold_light, foot[0] - 1.2, foot[1] - .7, 2.4, 1.4, u, outline)

        cls._poly(p, red_dark, [(9.1, torso_top), (18.9, torso_top), (17.3, hip_y + 1), (10.7, hip_y + 1)], u, outline)
        cls._poly(p, gold, [(10.0, torso_top + .3), (18.0, torso_top + .3), (16.6, hip_y), (11.4, hip_y)], u)
        cls._poly(p, red, [(10.0, torso_top + .3), (12.0, torso_top + 1.2), (11.4, hip_y), (9.7, hip_y - 1)], u)
        cls._poly(p, red, [(18.0, torso_top + .3), (16.0, torso_top + 1.2), (16.6, hip_y), (18.3, hip_y - 1)], u)
        # Chest and abdominal seams are individual modules, not a flat tunic.
        seam_pen = QPen(QColor("#7d5a25"), max(1.0, u * .35), Qt.SolidLine, Qt.RoundCap)
        p.setPen(seam_pen)
        p.drawLine(round(11.2 * u), round((torso_top + 2.0) * u), round(16.8 * u), round((torso_top + 2.0) * u))
        p.drawLine(round(14.0 * u), round((torso_top + 6.7) * u), round(14.0 * u), round((hip_y - .4) * u))
        p.drawLine(round(11.7 * u), round((torso_top + 7.0) * u), round(16.3 * u), round((torso_top + 7.0) * u))
        cls._ellipse(p, "#eaffff" if feedback or state == "react" else glow, 12.2, torso_top + 3.1, 3.6, 3.6, u, "#ffffff")

        head_y = 2.0 + crouch
        cls._ellipse(p, outline, 10.2, head_y - .35, 7.6, 7.5, u)
        cls._poly(p, gold, [(10.8, head_y + .3), (17.2, head_y + .3), (17.6, head_y + 4.8), (15.6, head_y + 6.6), (12.4, head_y + 6.6), (10.4, head_y + 4.8)], u)
        cls._poly(p, red, [(10.4, head_y + .3), (12.0, head_y), (11.7, head_y + 5.5), (10.4, head_y + 4.8)], u)
        cls._poly(p, red, [(17.6, head_y + .3), (16.0, head_y), (16.3, head_y + 5.5), (17.6, head_y + 4.8)], u)
        helmet_pen = QPen(QColor("#8b672b"), max(1.0, u * .34), Qt.SolidLine, Qt.RoundCap)
        p.setPen(helmet_pen)
        p.drawLine(round(12.0 * u), round((head_y + 5.4) * u), round(14.0 * u), round((head_y + 6.2) * u))
        p.drawLine(round(16.0 * u), round((head_y + 5.4) * u), round(14.0 * u), round((head_y + 6.2) * u))
        p.drawLine(round(14.0 * u), round((head_y + .7) * u), round(14.0 * u), round((head_y + 2.0) * u))
        look = 0.8 * math.sin(phase) if state in {"look", "react", "dragged"} else 0.0
        cls._poly(p, "#edffff", [(11.6 + look, head_y + 2.7), (13.7 + look, head_y + 3.0), (13.2 + look, head_y + 3.8), (11.4 + look, head_y + 3.5)], u)
        cls._poly(p, "#edffff", [(14.3 + look, head_y + 3.0), (16.4 + look, head_y + 2.7), (16.6 + look, head_y + 3.5), (14.8 + look, head_y + 3.8)], u)

    @classmethod
    def web_hero(
        cls, p: QPainter, w: int, h: int, u: int, phase: float,
        feedback: bool, state: str, frame: int, progress: float,
    ) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        symbiote_states = {
            "symbiote_notice", "symbiote_transform", "symbiote_active",
            "symbiote_struggle", "symbiote_remove",
        }
        symbiote = state in symbiote_states
        red, red_dark = (("#171a20", "#050609") if symbiote else ("#c62e3a", "#6e1722"))
        blue, blue_light = (("#262b35", "#3d4553") if symbiote else ("#183f7a", "#2867ae"))
        white, outline = "#f5f8ff", "#111a2a"
        crouch = 3.8 if state == "perch" else 1.8 if state == "falling" else 0.0
        struggle = (
            math.sin(phase * 3.8) * 3.0
            if state == "symbiote_struggle"
            else math.sin(phase * 2.8) * 2.2 if state == "dragged" else 0.0
        )
        stride = (
            math.sin(phase * 3.4) * 3.0
            if state in {"enemy_chase", "symbiote_active"}
            else math.sin(phase * 2.2) * 2.4 if state in {"patrol", "escape"} else 0.0
        )
        torso_top = 8.2 + crouch
        shoulder_l, shoulder_r = (9.8, torso_top + 1.5), (18.2, torso_top + 1.5)
        if state == "swing":
            elbow_l, hand_l = (9.0, 5.0), (12.1, 1.2)
            elbow_r, hand_r = (18.8, 5.3), (15.8, 1.5)
        elif state in {"special", "enemy_web"}:
            elbow_l, hand_l = (6.7, torso_top + 3), (3.5, torso_top + 1)
            elbow_r, hand_r = (21.0, torso_top + 4), (24.2, torso_top + 2)
        else:
            elbow_l, hand_l = (6.8 + struggle, torso_top + 5.8), (5.2 + struggle, torso_top + 10.5)
            elbow_r, hand_r = (21.2 - struggle, torso_top + 5.8), (22.8 - struggle, torso_top + 10.5)
        cls._stroke(p, outline, [shoulder_l, elbow_l, hand_l], 3.2, u)
        cls._stroke(p, outline, [shoulder_r, elbow_r, hand_r], 3.2, u)
        cls._stroke(p, red, [shoulder_l, elbow_l, hand_l], 2.3, u)
        cls._stroke(p, red, [shoulder_r, elbow_r, hand_r], 2.3, u)

        hip_y = torso_top + 9.2
        if state in {"swing", "perch"}:
            left_knee, left_foot = (8.8, 20.0), (5.8, 18.2)
            right_knee, right_foot = (18.8, 20.8), (22.0, 24.3)
        else:
            left_knee, left_foot = (11.2 - stride, 20.2), (9.8 - stride, 25.5)
            right_knee, right_foot = (16.8 + stride, 20.2), (18.2 + stride, 25.5)
        cls._stroke(p, outline, [(12.0, hip_y), left_knee, left_foot], 3.8, u)
        cls._stroke(p, outline, [(16.0, hip_y), right_knee, right_foot], 3.8, u)
        cls._stroke(p, blue, [(12.0, hip_y), left_knee, left_foot], 2.8, u)
        cls._stroke(p, blue, [(16.0, hip_y), right_knee, right_foot], 2.8, u)

        cls._poly(p, outline, [(9.0, torso_top), (19.0, torso_top), (17.2, hip_y + 1), (10.8, hip_y + 1)], u)
        cls._poly(p, blue, [(9.8, torso_top + .4), (18.2, torso_top + .4), (16.6, hip_y), (11.4, hip_y)], u)
        cls._poly(p, red, [(9.8, torso_top + .4), (18.2, torso_top + .4), (17.2, torso_top + 3.2), (10.8, torso_top + 3.2)], u)
        cls._poly(p, blue_light, [(11.0, torso_top + 4), (12.3, torso_top + 4.8), (11.8, hip_y - .5), (10.9, hip_y - 1)], u)

        head_y = 1.6 + crouch
        cls._ellipse(p, outline, 9.5, head_y - .3, 9.0, 7.7, u)
        cls._ellipse(p, red, 10.1, head_y, 7.8, 6.8, u)
        eye_shift = math.sin(phase) * .35 if feedback or state in {"react", "dragged"} else 0.0
        cls._poly(p, white, [(11.0 + eye_shift, head_y + 2.0), (13.3 + eye_shift, head_y + 2.6), (12.8 + eye_shift, head_y + 4.5), (10.7 + eye_shift, head_y + 3.6)], u, outline)
        cls._poly(p, white, [(17.0 + eye_shift, head_y + 2.0), (14.7 + eye_shift, head_y + 2.6), (15.2 + eye_shift, head_y + 4.5), (17.3 + eye_shift, head_y + 3.6)], u, outline)

        # Large, unmistakable eight-legged white spider emblem—not a cross.
        cx, sy = 14.0, torso_top + 4.2
        cls._ellipse(p, white, cx - .8, sy, 1.6, 3.7, u, outline)
        cls._ellipse(p, white, cx - 1.1, sy + 3.0, 2.2, 3.0, u, outline)
        emblem_pen = QPen(QColor(white), max(1.2, u * .62), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(emblem_pen)
        for side in (-1, 1):
            for y_offset, reach in ((.6, 2.7), (1.6, 3.3), (2.8, 3.1), (4.1, 2.5)):
                root_x = (cx + side * .65) * u
                root_y = (sy + y_offset) * u
                mid_x = (cx + side * reach * .62) * u
                end_x = (cx + side * reach) * u
                end_y = (sy + y_offset + (1.1 if y_offset > 2 else -.7)) * u
                p.drawLine(round(root_x), round(root_y), round(mid_x), round(root_y + (.25 * u)))
                p.drawLine(round(mid_x), round(root_y + (.25 * u)), round(end_x), round(end_y))

        if state in {"symbiote_transform", "symbiote_struggle", "symbiote_remove"}:
            # Living-suit tendrils curl out and retract; the motion remains
            # playful and non-graphic at desktop-pet scale.
            reach = (
                math.sin(progress * math.pi) * 6.0
                if state != "symbiote_struggle"
                else 5.0 + math.sin(phase * 3.0) * 1.5
            )
            for side, y_offset in ((-1, 9.5), (1, 11.5), (-1, 15.5), (1, 17.0)):
                start = (14.0 + side * 3.5, y_offset)
                bend = (14.0 + side * (4.5 + reach * .45), y_offset - 2.0)
                end = (14.0 + side * (5.0 + reach), y_offset + math.sin(phase + y_offset) * 2.0)
                cls._stroke(p, "#0a0b0f", [start, bend, end], 1.2, u)

        # Only the short attachment point is in the character window; the long
        # strand is painted by DesktopPetEffectsWindow across the whole screen.
        if state in {"swing", "special", "escape", "enemy_web", "enemy_victory"}:
            p.setPen(QPen(QColor(white), max(1, u // 2), Qt.SolidLine, Qt.RoundCap))
            p.drawLine(round(hand_r[0] * u), round(hand_r[1] * u), round((hand_r[0] + 2.0) * u), round((hand_r[1] - 2.5) * u))


class PetManager(QObject):
    """Own the overlay, fullscreen suspension, settings, and launch action."""

    def __init__(
        self,
        main_window: QWidget | None = None,
        *,
        settings: dict | None = None,
        asset_loader: AssetLoader | None = None,
        launcher: MoriceLauncher | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.settings = dict(settings or load_settings())
        self.asset_loader = asset_loader or AssetLoader()
        self.launcher = launcher or MoriceLauncher(self)
        self.overlay: PetOverlayWindow | None = None
        self._last_activation = 0.0
        self._lock = QLockFile(str(app_session_path().with_name("morice-desktop-pet.lock")))
        self._lock.setStaleLockTime(0)
        self._owns_lock = False
        self._fullscreen_timer = QTimer(self)
        self._fullscreen_timer.setInterval(650)
        self._fullscreen_timer.setTimerType(Qt.CoarseTimer)
        self._fullscreen_timer.timeout.connect(self._update_fullscreen_state)

    def start(self) -> bool:
        if not _setting_bool(self.settings.get("pet_enabled", "false")):
            return False
        if not self._owns_lock:
            Path(self._lock.fileName()).parent.mkdir(parents=True, exist_ok=True)
            self._owns_lock = self._lock.tryLock(0)
        if not self._owns_lock:
            return False
        self._create_overlay()
        if self.overlay is not None:
            self.overlay.start()
        self._fullscreen_timer.start()
        return self.overlay is not None

    def configure(self, settings: dict) -> None:
        self.settings = dict(settings)
        enabled = _setting_bool(self.settings.get("pet_enabled", "false"))
        if not enabled:
            self.remove_pet()
            return
        current_pet = self.overlay.definition.pet_id if self.overlay is not None else ""
        requested_pet = normalize_pet_id(self.settings.get("active_pet", "dog"))
        if self.overlay is None or current_pet != requested_pet:
            if self.overlay is not None:
                self.overlay.shutdown()
                self.overlay = None
            self.start()
        elif self.overlay is not None:
            self.overlay.click_action = normalize_open_action(
                self.settings.get("pet_click_action", "open_morice")
            )
            self.overlay.interaction_enabled = _setting_bool(
                self.settings.get("pet_interaction_enabled", "true"), default=True
            )
            self.overlay.configure_size(self.settings.get("pet_size", "medium"))
            self.overlay.set_animation_speed(
                self.settings.get("pet_animation_speed", "normal")
            )
            self.overlay.configure_event_frequency(
                self.settings.get("pet_event_frequency", "normal")
            )

    def remove_pet(self) -> None:
        self._fullscreen_timer.stop()
        if self.overlay is not None:
            self.overlay.shutdown()
            self.overlay = None
        if self._owns_lock:
            self._lock.unlock()
            self._owns_lock = False

    def shutdown(self) -> None:
        self.remove_pet()

    def _create_overlay(self) -> None:
        definition = self.asset_loader.load(self.settings.get("active_pet", "dog"))
        overlay = PetOverlayWindow(
            definition,
            click_action=self.settings.get("pet_click_action", "open_morice"),
            size=self.settings.get("pet_size", "medium"),
            animation_speed=self.settings.get("pet_animation_speed", "normal"),
            interaction_enabled=_setting_bool(
                self.settings.get("pet_interaction_enabled", "true"), default=True
            ),
            event_frequency=self.settings.get("pet_event_frequency", "normal"),
        )
        overlay.activated.connect(self._activate_morice)
        self.overlay = overlay

    def _activate_morice(self, action: str) -> None:
        now = time.monotonic()
        if now - self._last_activation < 0.25:
            return
        self._last_activation = now
        if self.main_window is not None:
            restore_morice_window(self.main_window, action)
        else:
            self.launcher.open(action)

    def _update_fullscreen_state(self) -> None:
        if self.overlay is None:
            return
        auto_hide = _setting_bool(
            self.settings.get("pet_fullscreen_autohide", "true"), default=True
        )
        ignored = {int(self.overlay.winId())}
        effect_hwnd = self.overlay.effect_window_id()
        if effect_hwnd:
            ignored.add(effect_hwnd)
        hidden = auto_hide and foreground_is_fullscreen(ignored_hwnds=ignored)
        self.overlay.set_suspended(hidden)


def _send_pet_host_command(command: str, *, timeout_ms: int = 160) -> bool:
    clean = str(command or "").strip().casefold()
    if clean not in {"reload", "stop"}:
        return False
    socket = QLocalSocket()
    socket.connectToServer(PET_HOST_SERVER_NAME)
    if not socket.waitForConnected(max(1, int(timeout_ms))):
        socket.abort()
        return False
    socket.write((clean + "\n").encode("ascii"))
    socket.flush()
    delivered = socket.waitForBytesWritten(max(1, int(timeout_ms)))
    socket.disconnectFromServer()
    return bool(delivered)


def default_pet_host_command() -> list[str]:
    explicit = os.getenv("MORICE_PET_EXECUTABLE", "").strip().strip('"')
    if explicit:
        return [explicit, "--morice-pet"]
    if getattr(sys, "frozen", False):
        return [sys.executable, "--morice-pet"]
    root = Path(__file__).resolve().parent.parent
    launcher = root / "morice_app_launcher.py"
    if launcher.is_file():
        return [sys.executable, str(launcher), "--morice-pet"]
    return [sys.executable, "-m", "morice.desktop_pet"]


class PetProcessController(QObject):
    """Control the resident pet process without coupling it to the AI runtime."""

    def __init__(
        self,
        *,
        settings: dict | None = None,
        spawn: Callable[[], object] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = dict(settings or load_settings())
        self._spawn_callback = spawn or self._spawn
        self._launch_pending_until = 0.0

    def start(self) -> bool:
        if not _setting_bool(self.settings.get("pet_enabled", "false")):
            return False
        if _send_pet_host_command("reload"):
            self._launch_pending_until = 0.0
            return True
        now = time.monotonic()
        if now < self._launch_pending_until:
            return True
        try:
            self._spawn_callback()
        except (OSError, RuntimeError, ValueError):
            self._launch_pending_until = 0.0
            return False
        self._launch_pending_until = now + 3.0
        QTimer.singleShot(350, lambda: _send_pet_host_command("reload"))
        return True

    def configure(self, settings: dict) -> None:
        self.settings = dict(settings)
        if not _setting_bool(self.settings.get("pet_enabled", "false")):
            self.remove_pet()
            return
        if not _send_pet_host_command("reload"):
            self.start()

    def remove_pet(self) -> None:
        _send_pet_host_command("stop")
        self._launch_pending_until = 0.0

    def shutdown(self) -> None:
        # The resident companion intentionally survives the main app so it can
        # act as a desktop shortcut.  "Remove Pet" is the explicit stop path.
        return

    def _spawn(self) -> subprocess.Popen:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        return subprocess.Popen(
            default_pet_host_command(),
            creationflags=flags,
            close_fds=True,
        )


class _PetHostServer(QObject):
    stop_requested = Signal()
    reload_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept_connections)
        self.clients: set[QLocalSocket] = set()

    def listen(self) -> bool:
        QLocalServer.removeServer(PET_HOST_SERVER_NAME)
        return self.server.listen(PET_HOST_SERVER_NAME)

    def close(self) -> None:
        self.server.close()
        QLocalServer.removeServer(PET_HOST_SERVER_NAME)
        for client in tuple(self.clients):
            client.abort()
        self.clients.clear()

    def _accept_connections(self) -> None:
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            if client is None:
                continue
            self.clients.add(client)
            client.readyRead.connect(lambda client=client: self._read(client))
            client.disconnected.connect(lambda client=client: self._drop(client))
            if client.bytesAvailable():
                self._read(client)

    def _read(self, client: QLocalSocket) -> None:
        payload = bytes(client.readAll()).decode("utf-8", errors="ignore")
        commands = {line.strip().casefold() for line in payload.splitlines()}
        if "stop" in commands:
            self.stop_requested.emit()
        elif "reload" in commands:
            self.reload_requested.emit()
        client.disconnectFromServer()

    def _drop(self, client: QLocalSocket) -> None:
        self.clients.discard(client)
        client.deleteLater()


def _setting_bool(value: object, *, default: bool = False) -> bool:
    text = str(value or "").strip().casefold()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def run_pet_host() -> int:
    """Run only the companion, allowing it to launch MORICE when clicked."""

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MORICE Desktop Pet")
    settings = load_settings()
    manager = PetManager(settings=settings)
    if not manager.start():
        return 0
    server = _PetHostServer(app)
    if not server.listen():
        manager.shutdown()
        return 0

    def reload_pet() -> None:
        refreshed = load_settings()
        if not _setting_bool(refreshed.get("pet_enabled", "false")):
            app.quit()
            return
        manager.configure(refreshed)

    server.reload_requested.connect(reload_pet)
    server.stop_requested.connect(app.quit)
    app.aboutToQuit.connect(server.close)
    app.aboutToQuit.connect(manager.shutdown)
    return app.exec()


if __name__ == "__main__":  # pragma: no cover - manual companion entry point
    raise SystemExit(run_pet_host())


__all__ = [
    "AssetLoader",
    "PetDefinition",
    "PetManager",
    "PetOverlayWindow",
    "PetProcessController",
    "PointerGesture",
    "SUPPORTED_PETS",
    "foreground_is_fullscreen",
    "default_pet_host_command",
    "normalize_pet_id",
    "normalize_pet_size",
    "run_pet_host",
]
