from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import (
    QEvent,
    QEasingCurve,
    QObject,
    QPoint,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractButton,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QScrollArea,
    QScroller,
    QWidget,
)


@dataclass(frozen=True)
class ThemeTokens:
    name: str
    canvas: str
    surface: str
    surface_alt: str
    text: str
    muted: str
    border: str
    accent: str
    accent_soft: str
    success: str
    danger: str
    user_bubble: str
    assistant_bubble: str


THEMES = {
    "dark": ThemeTokens(
        "dark",
        "#080a0e",
        "#10141a",
        "#151b23",
        "#f3f5f7",
        "#9ca6b2",
        "#2b3541",
        "#62d6b0",
        "#193c35",
        "#69d39e",
        "#f06d7c",
        "#17324a",
        "#12181f",
    ),
    "light": ThemeTokens(
        "light",
        "#eef2f5",
        "#ffffff",
        "#f5f7f9",
        "#161b22",
        "#617080",
        "#cbd4dc",
        "#147d68",
        "#d9f0ea",
        "#147d68",
        "#c43f55",
        "#dceaf6",
        "#f6f8fa",
    ),
    "midnight": ThemeTokens(
        "midnight",
        "#03050a",
        "#090d14",
        "#0f1721",
        "#f5f8fb",
        "#93a4b8",
        "#233143",
        "#55d6c2",
        "#123a38",
        "#65d9a6",
        "#ff6f82",
        "#102d46",
        "#0b121c",
    ),
    "glass": ThemeTokens(
        "glass",
        "#091017",
        "#101923",
        "#17232f",
        "#f4f8fb",
        "#9eacb9",
        "#344554",
        "#62d6b0",
        "#193c35",
        "#69d39e",
        "#f47584",
        "#17354b",
        "#121d27",
    ),
    "custom": ThemeTokens(
        "custom",
        "#0a0d11",
        "#111820",
        "#18222c",
        "#f5f7f9",
        "#a2acb8",
        "#34404d",
        "#62d6b0",
        "#193c35",
        "#69d39e",
        "#f06d7c",
        "#18364d",
        "#131b23",
    ),
}


def normalize_theme(value: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in THEMES else "dark"


def normalize_accent(value: str) -> str:
    color = QColor(str(value or "").strip())
    if not color.isValid():
        return THEMES["dark"].accent
    return color.name(QColor.HexRgb)


def _rgba(hex_color: str, alpha: int) -> str:
    color = QColor(hex_color)
    return f"rgba({color.red()},{color.green()},{color.blue()},{max(0, min(255, alpha))})"


def _safe_font_family(value: str) -> str:
    text = " ".join(str(value or "").strip().split())
    text = "".join(ch for ch in text if ch not in '\r\n\t\x00{};"\'').strip()
    return text[:100] or "Segoe UI"


def premium_theme_stylesheet(
    theme: str,
    accent: str,
    font_family: str = "Segoe UI",
    *,
    high_contrast: bool = False,
    transparency: int = 92,
) -> str:
    tokens = THEMES[normalize_theme(theme)]
    accent = normalize_accent(accent)
    font_family = _safe_font_family(font_family)
    transparency = max(70, min(100, int(transparency)))
    if high_contrast:
        border = "#ffffff" if tokens.name != "light" else "#111111"
        muted = "#e2e8ee" if tokens.name != "light" else "#33404c"
    else:
        border = tokens.border
        muted = tokens.muted
    dark_theme = tokens.name != "light"
    accent_soft = _rgba(accent, 44 if dark_theme else 28)
    accent_border = _rgba(accent, 112 if dark_theme else 82)
    hover = _rgba(accent, 66 if dark_theme else 38)
    surface_alpha = round(255 * transparency / 100)
    canvas_alpha = max(170, surface_alpha - 12)
    panel = _rgba(tokens.surface, surface_alpha)
    canvas = _rgba(tokens.canvas, canvas_alpha)
    return f"""
        QWidget {{
            color: {tokens.text};
            font-family: "{font_family}", "Segoe UI Emoji", "Segoe UI", sans-serif;
            selection-background-color: {accent_border};
        }}
        #TitleBar, #TitleBar[personalized="true"] {{
            background: {panel};
            border: 1px solid {border};
            border-radius: 8px;
        }}
        #TitleLabel, #HeroPrompt {{
            color: {tokens.text};
        }}
        #CommandPalette {{
            background: {panel};
            border: 1px solid {accent_border};
            border-radius: 8px;
        }}
        #WorkspaceSplitter::handle {{
            background: {_rgba(tokens.border, 150)};
            margin: 10px 1px;
            border-radius: 2px;
        }}
        #WorkspaceSplitter::handle:hover {{
            background: {accent_border};
        }}
        #ChatContainer, #ChatContainer[personalized="true"], #ComposerStage {{
            background: {canvas};
            border-color: {border};
        }}
        #ModePanel, #SidebarPanel, #ScienceWorkspacePanel,
        #ProjectChangesPanel, #AssistantHub, #SidebarPanel[personalized="true"] {{
            background: {panel};
            border: 1px solid {border};
            border-radius: 8px;
        }}
        #ChatBubble[user="true"] {{
            background: {tokens.user_bubble};
            border: 1px solid {_rgba(accent, 50)};
            border-radius: 8px;
        }}
        #ChatBubble[user="false"] {{
            background: {tokens.assistant_bubble};
            border: 1px solid {border};
            border-radius: 8px;
        }}
        #InputFrame, #InputFrame[centered="true"],
        #InputFrame[personalized="true"],
        #InputFrame[centered="true"][personalized="true"] {{
            background: {tokens.surface};
            border: 1px solid {accent_border};
            border-radius: 16px;
        }}
        #InputFrame[hovered="true"], #InputFrame[centered="true"][hovered="true"] {{
            border-color: {accent};
        }}
        #InputBox, #WorkspaceSearch, #WorkspaceNotes, #WorkspacePreview,
        #CommandSearch, #ProjectFolderInput, #StyleInput, #TitleInput, #WakeInput,
        #AppearanceSelect {{
            background: {tokens.surface_alt};
            color: {tokens.text};
            border: 1px solid {border};
            border-radius: 7px;
        }}
        #AppearanceSelect {{
            min-height: 32px;
            padding: 2px 8px;
        }}
        #SidebarScroll, #SidebarContent {{
            background: transparent;
            border: none;
        }}
        #InputBox:focus, #WorkspaceSearch:focus, #WorkspaceNotes:focus,
        #CommandSearch:focus, #ProjectFolderInput:focus {{
            border-color: {accent};
        }}
        #SendButton[ready="true"], #ModeOption[active="true"],
        #WorkspaceTab[active="true"], #HubTab[active="true"] {{
            background: {accent};
            color: {"#07100d" if dark_theme else "#ffffff"};
            border-color: {accent};
        }}
        #SidebarButton, #WorkspaceAction, #CommandAction, #ProjectActionButton,
        #WorkspaceControl, #WorkspaceTab, #HubTab, #WorkspaceCloseButton,
        #TitleButton, #SidebarButton[personalized="true"] {{
            background: {tokens.surface_alt};
            color: {tokens.text};
            border: 1px solid {border};
            border-radius: 7px;
            min-height: 20px;
            padding: 6px 10px;
        }}
        QAbstractButton[pressed="true"] {{
            background: {accent_soft};
            border-color: {accent};
        }}
        QAbstractButton:focus, QLineEdit:focus, QTextEdit:focus,
        QListWidget:focus, QTreeWidget:focus {{
            border: 2px solid {accent};
        }}
        #SidebarButton:hover, #WorkspaceAction:hover, #CommandAction:hover,
        #ProjectActionButton:hover, #WorkspaceControl:hover, #WorkspaceTab:hover,
        #HubTab:hover, #WorkspaceCloseButton:hover, #TitleButton:hover {{
            background: {hover};
            border-color: {accent_border};
        }}
        #AssistantHubTitle, #CommandTitle, #DashboardTitle, #ScienceWorkspaceTitle,
        #ProjectChangesTitle, #SidebarTitle, #ModeTitle, #MessageLabel {{
            color: {tokens.text};
        }}
        #CommandTitle, #SidebarTitle {{
            font-size: 18px;
            font-weight: 700;
        }}
        #PrecisionButton, #PrecisionButton[personalized="true"],
        #PrecisionButton[active="true"], #PrecisionButton[active="true"][personalized="true"],
        #PersonalizationStatus, #PersonalizationStatus[personalized="true"] {{
            color: {tokens.text};
            border-color: {accent_border};
        }}
        #WorkspaceMuted, #CommandHint, #DashboardDetail, #ModeHint,
        #ThinkingDetail, #InlineVisualizationInspector {{
            color: {muted};
        }}
        #WorkspaceCard, #DashboardCard, #NotificationToast {{
            background: {tokens.surface_alt};
            border: 1px solid {border};
            border-radius: 8px;
        }}
        #NotificationToast[severity="success"] {{
            border-color: {tokens.success};
        }}
        #NotificationToast[severity="error"] {{
            border-color: {tokens.danger};
        }}
        #NotificationToast[severity="warning"] {{
            border-color: #e6b94c;
        }}
        #MessageMeta, #MessageAction {{
            color: {muted};
        }}
        #MessageAction {{
            background: transparent;
            border: none;
            padding: 3px;
        }}
        #MessageAction:hover {{
            color: {tokens.text};
            background: {accent_soft};
            border-radius: 5px;
        }}
        #MessageRow {{
            background: transparent;
            border: none;
        }}
        #ChatArchiveNotice {{
            color: {muted};
            background: {tokens.surface_alt};
            border: 1px solid {border};
            border-radius: 7px;
            padding: 7px 10px;
        }}
        #ComposerToolButton, #TopStatus {{
            background: transparent;
            color: {muted};
            border: 1px solid transparent;
            border-radius: 6px;
            padding: 5px 7px;
        }}
        #ComposerToolButton:hover, #TopStatus:hover {{
            color: {tokens.text};
            border-color: {border};
            background: {accent_soft};
        }}
        #SettingsPreview, #SettingsStack, #PremiumSettingsDialog {{
            background: {panel};
            color: {tokens.text};
            border: 1px solid {border};
            border-radius: 8px;
        }}
        #ThinkingBubble {{
            background: {tokens.surface_alt};
            border-color: {accent_border};
            border-radius: 8px;
        }}
        #ThinkingDot {{
            background: {accent};
            border-color: {_rgba(accent, 210)};
        }}
        #AuthorLabel, #SidebarSectionLabel, #ModeStatus,
        #ProjectChangesSummary, #WorkspaceInspector {{
            color: {accent};
        }}
        #CurrentStyleValue {{
            background: {tokens.surface_alt};
            color: {tokens.text};
            border: 1px solid {border};
        }}
        #CurrentStyleValue[empty="true"], #StyleStatus {{
            color: {tokens.muted};
        }}
        #QueueList {{
            background: {tokens.surface_alt};
            color: {tokens.text};
            border: 1px solid {tokens.border};
        }}
        #QueueButton, #StyleClearButton {{
            background: {tokens.surface_alt};
            color: {tokens.text};
            border: 1px solid {tokens.border};
        }}
        #QueueButton:hover, #StyleClearButton:hover {{
            background: {hover};
            border-color: {accent_border};
        }}
        #StyleSaveButton {{
            background: {tokens.success};
            color: #ffffff;
            border: 1px solid {_rgba(tokens.success, 180)};
        }}
        QListWidget, QTreeWidget, QTextEdit, QPlainTextEdit, QTabWidget::pane {{
            background: {tokens.surface_alt};
            color: {tokens.text};
            border: 1px solid {tokens.border};
        }}
        QTabBar::tab {{
            background: {tokens.surface};
            color: {muted};
            border: 1px solid {border};
            padding: 7px 10px;
            margin-right: 2px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
        }}
        QTabBar::tab:selected {{
            background: {accent_soft};
            color: {tokens.text};
            border-color: {accent_border};
        }}
        QTabBar::tab:hover {{
            color: {tokens.text};
            border-color: {accent_border};
        }}
        QListWidget::item:selected, QTreeWidget::item:selected {{
            background: {accent_soft};
            color: {tokens.text};
        }}
        QScrollBar::handle:vertical {{
            background: {_rgba(accent, 120)};
            min-height: 28px;
            border-radius: 4px;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 9px;
            margin: 2px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QToolTip {{
            background: {tokens.surface};
            color: {tokens.text};
            border: 1px solid {accent_border};
            padding: 6px;
        }}
    """


class AnimationEngine(QObject):
    SPEED_MULTIPLIERS = {"slow": 1.35, "normal": 1.0, "fast": 0.72}

    def __init__(
        self,
        parent: QObject | None = None,
        enabled: bool = True,
        speed: str = "normal",
    ):
        super().__init__(parent)
        self.enabled = bool(enabled)
        self.speed = speed if speed in self.SPEED_MULTIPLIERS else "normal"
        self._animations: list[QObject] = []
        self._active: dict[tuple[int, bytes], tuple[int, QPropertyAnimation]] = {}

    def configure(self, *, enabled: bool | None = None, speed: str | None = None) -> None:
        if enabled is not None:
            self.enabled = bool(enabled)
            if not self.enabled:
                self.stop_all()
        if speed is not None:
            self.speed = speed if speed in self.SPEED_MULTIPLIERS else "normal"

    def _duration(self, requested: int) -> int:
        if not self.enabled:
            return 0
        scaled = int(requested * self.SPEED_MULTIPLIERS[self.speed])
        return max(70, min(650, scaled))

    def duration(self, requested: int) -> int:
        return self._duration(requested)

    def _track(self, animation):
        self._animations.append(animation)
        animation.finished.connect(
            lambda: self._animations.remove(animation)
            if animation in self._animations
            else None
        )
        return animation

    def animate_property(
        self,
        target: QObject,
        property_name: bytes,
        end_value,
        *,
        start_value=None,
        duration: int = 180,
        easing: QEasingCurve.Type = QEasingCurve.OutCubic,
        priority: int = 0,
        finished: Callable[[], None] | None = None,
    ):
        if not self.enabled:
            target.setProperty(property_name.decode("ascii"), end_value)
            if finished:
                finished()
            return None
        key = (id(target), property_name)
        current = self._active.get(key)
        if current is not None:
            current_priority, current_animation = current
            if current_priority > priority:
                return current_animation
            current_animation.stop()
        animation = QPropertyAnimation(target, property_name, target)
        animation.setDuration(self._duration(duration))
        if start_value is not None:
            animation.setStartValue(start_value)
        animation.setEndValue(end_value)
        animation.setEasingCurve(easing)
        self._active[key] = (int(priority), animation)

        def complete() -> None:
            if self._active.get(key, (None, None))[1] is animation:
                self._active.pop(key, None)
            if finished:
                finished()

        animation.finished.connect(complete)
        self._track(animation).start()
        return animation

    def move(
        self,
        widget: QWidget,
        target: QPoint,
        *,
        duration: int = 180,
        spring: bool = False,
        priority: int = 0,
    ):
        return self.animate_property(
            widget,
            b"pos",
            target,
            start_value=widget.pos(),
            duration=duration,
            easing=QEasingCurve.OutBack if spring else QEasingCurve.OutCubic,
            priority=priority,
        )

    def fade(
        self,
        widget: QWidget,
        visible: bool,
        *,
        duration: int = 180,
        finished: Callable[[], None] | None = None,
    ):
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
        if not self.enabled:
            widget.setVisible(visible)
            effect.setOpacity(1.0)
            if finished:
                finished()
            return None
        was_visible = widget.isVisible()
        start_opacity = effect.opacity() if was_visible else 0.0
        if visible:
            widget.setVisible(True)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(self._duration(duration))
        animation.setStartValue(start_opacity)
        animation.setEndValue(1.0 if visible else 0.0)
        animation.setEasingCurve(QEasingCurve.OutCubic if visible else QEasingCurve.InCubic)

        def complete():
            if not visible:
                widget.setVisible(False)
            effect.setOpacity(1.0)
            if finished:
                finished()

        animation.finished.connect(complete)
        self._track(animation).start()
        return animation

    def geometry(
        self,
        widget: QWidget,
        target: QRect,
        *,
        duration: int = 220,
        finished: Callable[[], None] | None = None,
    ):
        if not self.enabled:
            widget.setGeometry(target)
            if finished:
                finished()
            return None
        animation = QPropertyAnimation(widget, b"geometry", widget)
        animation.setDuration(self._duration(duration))
        animation.setStartValue(widget.geometry())
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        if finished:
            animation.finished.connect(finished)
        self._track(animation).start()
        return animation

    def window_opacity(
        self,
        widget: QWidget,
        target: float,
        *,
        duration: int = 150,
        finished: Callable[[], None] | None = None,
    ):
        clean_target = max(0.0, min(1.0, float(target)))
        if not self.enabled:
            widget.setWindowOpacity(clean_target)
            if finished:
                finished()
            return None
        animation = QPropertyAnimation(widget, b"windowOpacity", widget)
        animation.setDuration(self._duration(duration))
        animation.setStartValue(widget.windowOpacity())
        animation.setEndValue(clean_target)
        animation.setEasingCurve(
            QEasingCurve.OutCubic
            if clean_target > widget.windowOpacity()
            else QEasingCurve.InCubic
        )
        if finished:
            animation.finished.connect(finished)
        self._track(animation).start()
        return animation

    def reveal(self, widget: QWidget, *, offset: int = 12, duration: int = 180):
        if not self.enabled:
            widget.show()
            return None
        origin = widget.geometry()
        shifted = QRect(origin.x(), origin.y() + offset, origin.width(), origin.height())
        opacity = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(opacity)
        opacity.setOpacity(0.0)
        widget.setGeometry(shifted)
        widget.show()
        group = QParallelAnimationGroup(widget)
        fade = QPropertyAnimation(opacity, b"opacity", group)
        fade.setDuration(self._duration(duration))
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        move = QPropertyAnimation(widget, b"geometry", group)
        move.setDuration(self._duration(duration))
        move.setStartValue(shifted)
        move.setEndValue(origin)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        move.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(fade)
        group.addAnimation(move)
        self._track(group).start()
        return group

    def shake(self, widget: QWidget, *, distance: int = 8, duration: int = 240):
        origin = widget.geometry()
        if not self.enabled:
            return None
        animation = QPropertyAnimation(widget, b"geometry", widget)
        animation.setDuration(self._duration(duration))
        animation.setKeyValueAt(0.0, origin)
        animation.setKeyValueAt(0.2, origin.translated(-distance, 0))
        animation.setKeyValueAt(0.4, origin.translated(distance, 0))
        animation.setKeyValueAt(0.6, origin.translated(-distance // 2, 0))
        animation.setKeyValueAt(0.8, origin.translated(distance // 2, 0))
        animation.setKeyValueAt(1.0, origin)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self._track(animation).start()
        return animation

    def shadow(
        self,
        widget: QWidget,
        *,
        color: QColor,
        blur: int,
        duration: int = 180,
    ):
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            effect = QGraphicsDropShadowEffect(widget)
            effect.setOffset(0, 4)
            widget.setGraphicsEffect(effect)
        if not self.enabled:
            effect.setColor(color)
            effect.setBlurRadius(blur)
            return None
        group = QParallelAnimationGroup(widget)
        blur_animation = QPropertyAnimation(effect, b"blurRadius", group)
        blur_animation.setDuration(self._duration(duration))
        blur_animation.setStartValue(effect.blurRadius())
        blur_animation.setEndValue(blur)
        color_animation = QPropertyAnimation(effect, b"color", group)
        color_animation.setDuration(self._duration(duration))
        color_animation.setStartValue(effect.color())
        color_animation.setEndValue(color)
        blur_animation.setEasingCurve(QEasingCurve.OutCubic)
        color_animation.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(blur_animation)
        group.addAnimation(color_animation)
        self._track(group).start()
        return group

    def stop_all(self) -> None:
        for animation in tuple(self._animations):
            try:
                animation.stop()
            except RuntimeError:
                pass
        self._animations.clear()
        self._active.clear()


class MicroInteractionFilter(QObject):
    """Applies consistent hover/press state without taking over widget input."""

    def __init__(self, parent: QObject | None = None, *, enabled: bool = True):
        super().__init__(parent)
        self.enabled = bool(enabled)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self.enabled or not isinstance(watched, QAbstractButton):
            return False
        event_type = event.type()
        if event_type in {QEvent.Enter, QEvent.Leave}:
            watched.setProperty("hovered", "true" if event_type == QEvent.Enter else "false")
        elif event_type == QEvent.MouseButtonPress:
            watched.setProperty("pressed", "true")
        elif event_type == QEvent.MouseButtonRelease:
            watched.setProperty("pressed", "false")
        else:
            return False
        watched.style().unpolish(watched)
        watched.style().polish(watched)
        return False

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)


class SmoothScrollController(QObject):
    """Interruptible wheel animation plus native touch momentum."""

    def __init__(
        self,
        area: QScrollArea,
        *,
        enabled: bool = True,
        duration: int = 150,
    ):
        super().__init__(area)
        self.area = area
        self.enabled = bool(enabled)
        self.duration = max(60, min(400, int(duration)))
        self._animation: QPropertyAnimation | None = None
        area.viewport().installEventFilter(self)
        try:
            QScroller.grabGesture(
                area.viewport(), QScroller.ScrollerGestureType.TouchGesture
            )
        except (AttributeError, RuntimeError):
            pass

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self.enabled or event.type() != QEvent.Wheel:
            return False
        delta = event.pixelDelta().y() or event.angleDelta().y()
        if not delta:
            return False
        bar = self.area.verticalScrollBar()
        scale = 1.0 if event.pixelDelta().y() else 0.8
        target = max(
            bar.minimum(),
            min(bar.maximum(), bar.value() - int(delta * scale)),
        )
        if self._animation is not None:
            self._animation.stop()
        self._animation = QPropertyAnimation(bar, b"value", self)
        self._animation.setDuration(self.duration)
        self._animation.setStartValue(bar.value())
        self._animation.setEndValue(target)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.start()
        event.accept()
        return True

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled and self._animation is not None:
            self._animation.stop()
