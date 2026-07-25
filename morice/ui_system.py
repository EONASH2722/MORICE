from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
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
}


def normalize_theme(value: str) -> str:
    return "light" if str(value or "").strip().lower() == "light" else "dark"


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
    theme: str, accent: str, font_family: str = "Segoe UI"
) -> str:
    tokens = THEMES[normalize_theme(theme)]
    accent = normalize_accent(accent)
    font_family = _safe_font_family(font_family)
    accent_soft = _rgba(accent, 44 if tokens.name == "dark" else 28)
    accent_border = _rgba(accent, 112 if tokens.name == "dark" else 82)
    hover = _rgba(accent, 66 if tokens.name == "dark" else 38)
    panel = _rgba(tokens.surface, 244 if tokens.name == "dark" else 250)
    canvas = _rgba(tokens.canvas, 238 if tokens.name == "dark" else 242)
    return f"""
        QWidget {{
            color: {tokens.text};
            font-family: "{font_family}", "Segoe UI Emoji", "Segoe UI", sans-serif;
            selection-background-color: {accent_border};
        }}
        #TitleBar, #TitleBar[personalized="true"] {{
            background: {panel};
            border: 1px solid {tokens.border};
            border-radius: 8px;
        }}
        #TitleLabel, #HeroPrompt {{
            color: {tokens.text};
        }}
        #CommandPalette {{
            background: {tokens.surface};
            border: 1px solid {accent_border};
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
            border-color: {tokens.border};
        }}
        #ModePanel, #SidebarPanel, #ScienceWorkspacePanel,
        #ProjectChangesPanel, #AssistantHub, #SidebarPanel[personalized="true"] {{
            background: {panel};
            border: 1px solid {tokens.border};
            border-radius: 8px;
        }}
        #ChatBubble[user="true"] {{
            background: {tokens.user_bubble};
            border: 1px solid {_rgba(accent, 50)};
            border-radius: 8px;
        }}
        #ChatBubble[user="false"] {{
            background: {tokens.assistant_bubble};
            border: 1px solid {tokens.border};
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
            border: 1px solid {tokens.border};
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
            color: {"#07100d" if tokens.name == "dark" else "#ffffff"};
            border-color: {accent};
        }}
        #SidebarButton, #WorkspaceAction, #CommandAction, #ProjectActionButton,
        #WorkspaceControl, #WorkspaceTab, #HubTab, #WorkspaceCloseButton,
        #TitleButton, #SidebarButton[personalized="true"] {{
            background: {tokens.surface_alt};
            color: {tokens.text};
            border: 1px solid {tokens.border};
            border-radius: 7px;
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
        #PrecisionButton, #PrecisionButton[personalized="true"],
        #PrecisionButton[active="true"], #PrecisionButton[active="true"][personalized="true"],
        #PersonalizationStatus, #PersonalizationStatus[personalized="true"] {{
            color: {tokens.text};
            border-color: {accent_border};
        }}
        #WorkspaceMuted, #CommandHint, #DashboardDetail, #ModeHint,
        #ThinkingDetail, #InlineVisualizationInspector {{
            color: {tokens.muted};
        }}
        #WorkspaceCard, #DashboardCard, #NotificationToast {{
            background: {tokens.surface_alt};
            border: 1px solid {tokens.border};
            border-radius: 8px;
        }}
        #NotificationToast[severity="success"] {{
            border-color: {tokens.success};
        }}
        #NotificationToast[severity="error"] {{
            border-color: {tokens.danger};
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
            border: 1px solid {tokens.border};
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
            color: {tokens.muted};
            border: 1px solid {tokens.border};
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
        }}
        QToolTip {{
            background: {tokens.surface};
            color: {tokens.text};
            border: 1px solid {accent_border};
            padding: 6px;
        }}
    """


class AnimationEngine(QObject):
    def __init__(self, parent: QObject | None = None, enabled: bool = True):
        super().__init__(parent)
        self.enabled = bool(enabled)
        self._animations: list[QObject] = []

    def _duration(self, requested: int) -> int:
        if not self.enabled:
            return 0
        return max(120, min(350, int(requested)))

    def _track(self, animation):
        self._animations.append(animation)
        animation.finished.connect(
            lambda: self._animations.remove(animation)
            if animation in self._animations
            else None
        )
        return animation

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
