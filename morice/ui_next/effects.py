"""Optional bounded dirty-region cursor lighting and stable-hitbox press motion."""
import math
import time
import weakref

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient, QBrush
from PySide6.QtWidgets import QApplication, QAbstractButton, QPushButton, QStyle, QStyleOptionButton, QWidget, QVBoxLayout, QHBoxLayout, QLabel

from .motion import spring_step
from .icons import draw_mark


class MotionButton(QPushButton):
    def __init__(self, text, theme, policy, clock, parent=None):
        super().__init__(text, parent)
        self.theme = theme; self.policy = policy; self.clock = clock
        self._hover = False; self._pressed = False; self._value = 0.; self._velocity = 0.
        self.setMouseTracking(True); self.setCursor(Qt.PointingHandCursor)
        clock.subscribe(self, self.tick)

    def enterEvent(self, event):
        self._hover = True; self.clock.request(); super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False; self.clock.request(); super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True; self.clock.request(); super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False; self.clock.request(); super().mouseReleaseEvent(event)

    def tick(self, delta):
        if not self.policy.budget.decorative_motion:
            if self._value or self._velocity: self._value = self._velocity = 0.; self.update()
            return False
        target = -1 if self._pressed else 1 if self._hover else 0
        self._value, self._velocity = spring_step(self._value, self._velocity, target, delta)
        self.update()
        return self._velocity != 0 or self._value != target

    def paintEvent(self, event):
        option = QStyleOptionButton(); self.initStyleOption(option)
        painter = QPainter(self)
        if self.policy.budget.decorative_motion and self.theme.profile.magnetic_controls:
            painter.translate(min(3, max(-1, self._value * 2)), 0)
        if self.policy.budget.decorative_motion and self._value < 0:
            painter.translate(self.width() / 2, self.height() / 2); painter.scale(.985, .985); painter.translate(-self.width() / 2, -self.height() / 2)
        self.style().drawControl(QStyle.CE_PushButton, option, painter, self); painter.end()

    def hideEvent(self, event):
        self._hover = self._pressed = False; self._value = self._velocity = 0.; super().hideEvent(event)


class ActionCard(MotionButton):
    def __init__(self, title, detail, theme, policy, clock, parent=None, *, icon_name='action'):
        super().__init__('', theme, policy, clock, parent); self.setObjectName('ActionCard')
        self.setProperty('morice_icon_in_content', True)
        self.setAccessibleName(title + '. ' + detail); self.setMinimumWidth(180); self.setMinimumHeight(100)
        layout = QVBoxLayout(self); layout.setContentsMargins(18, 16, 18, 16); layout.setSpacing(8)
        heading = QHBoxLayout(); heading.setSpacing(12)
        self.mark = AuthoredMark(icon_name, theme); heading.addWidget(self.mark)
        self.heading = QLabel(title); self.heading.setProperty('role', 'card-title'); heading.addWidget(self.heading, 1)
        layout.addLayout(heading); self.description = QLabel(detail); self.description.setProperty('role', 'secondary'); layout.addWidget(self.description)
        for label in (self.heading, self.description): label.setWordWrap(True); label.setAttribute(Qt.WA_TransparentForMouseEvents)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(round(280 * self.theme.profile.font_scale**.5), max(100, self.layout().heightForWidth(280)))


class AuthoredMark(QWidget):
    def __init__(self, name, theme, parent=None):
        super().__init__(parent); self.name = name; self.theme = theme; self.setFixedSize(28, 28)
        self.setAttribute(Qt.WA_TransparentForMouseEvents); theme.changed.connect(self.refresh)
    def refresh(self, *_): self.update()
    def paintEvent(self, event):
        painter = QPainter(self); draw_mark(painter, self.name, QRectF(self.rect()).adjusted(2, 2, -2, -2), self.theme.tokens['accent_primary']); painter.end()


def cursor_style(profile, budget):
    """Distinct user glow levels, bounded again by the existing load policy."""
    radius, opacity = {'OFF': (0., 0.), 'MINIMAL': (.58, 32), 'NORMAL': (.8, 56), 'HIGH': (1., 84)}[profile.cursor_glow]
    intensity = profile.glow * budget.glow_factor
    return max(24, round(budget.cursor_radius * radius)), 0 if profile.high_contrast else round(opacity * intensity)


class CursorLighting(QWidget):
    pointer_changed = Signal(object)
    def __init__(self, window, theme, policy, clock):
        super().__init__(window)
        self.owner = window; self.theme = theme; self.policy = policy; self.clock = clock
        self.setAttribute(Qt.WA_TransparentForMouseEvents); self.setAttribute(Qt.WA_NoSystemBackground)
        self.setMouseTracking(True); window.setMouseTracking(True)
        self._point = None; self._target_point = None; self._last_point = None; self._dirty = False; self._targets = []; self._nearby = []; self._trail = []; self._press = None
        self.paint_count = 0; self.last_dirty_pixels = 0; self._last_event = 0.
        clock.subscribe(self, self.tick); QApplication.instance().installEventFilter(self)
        theme.changed.connect(self.clear); policy.changed.connect(self.clear)
        self.resize(window.size()); self.show(); self.raise_()

    def set_targets(self):
        self._targets = [weakref.ref(widget) for widget in self.owner.findChildren(QAbstractButton) if widget.isVisible()][:256]
        for reference in self._targets:
            widget = reference()
            if widget is not None: widget.setMouseTracking(True)

    def clear(self, *_):
        for point in (self._point, self._last_point):
            if point is not None: self.update(self._dirty_region(point))
        for point, _ in self._trail: self.update(self._dirty_region(point))
        self._point = self._target_point = self._last_point = None; self._dirty = False
        self._trail.clear(); self._nearby.clear(); self._press = None
        self.pointer_changed.emit(None)

    def eventFilter(self, source, event):
        if event.type() in (QEvent.MouseMove, QEvent.MouseButtonPress) and isinstance(source, QWidget) and source.window() is self.owner:
            if not self.theme.profile.cursor_light and self.theme.profile.cursor_glow == 'OFF': return False
            if not self.owner.isVisible() or self.owner.isMinimized(): return False
            now = time.perf_counter()
            self._target_point = QPointF(self.owner.mapFromGlobal(event.globalPosition().toPoint())); self._dirty = True
            self.pointer_changed.emit({'point': QPointF(self._target_point), 'pressed': event.type() == QEvent.MouseButtonPress})
            if self._point is None or not self.policy.budget.decorative_motion: self._point = QPointF(self._target_point)
            if self.theme.profile.cursor_trail and self.policy.budget.decorative_motion and now-self._last_event >= 1/self.policy.budget.fps:
                self._trail.append((QPointF(self._target_point), now)); self._trail = self._trail[-8:]; self._last_event = now
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton and self.policy.budget.decorative_motion:
                self._press = (QPointF(self._target_point), now)
            self.clock.request()
        elif source is self.owner and event.type() == QEvent.Leave:
            self.clear()
        elif source is self.owner and event.type() in (QEvent.WindowDeactivate, QEvent.Hide): self.clear()
        elif event.type() == QEvent.KeyPress and isinstance(source, QWidget) and source.window() is self.owner:
            if event.key() in (Qt.Key_Tab, Qt.Key_Backtab): self.clear()
        return False

    def _dirty_region(self, point):
        radius = self.policy.budget.cursor_radius + 6
        return QRect(round(point.x() - radius - 4), round(point.y() - radius - 4), radius * 2 + 8, radius * 2 + 8).intersected(self.rect())

    def tick(self, delta):
        moving = False
        if self._target_point is not None and self._point is not None:
            offset = self._target_point-self._point
            if math.hypot(offset.x(), offset.y()) > .4 and self.policy.budget.decorative_motion:
                self._point += offset*(1-math.exp(-30*delta)); moving = True; self._dirty = True
            elif offset != QPointF(): self._point = QPointF(self._target_point); self._dirty = True
        if self._dirty:
            if self._last_point is not None: self.update(self._dirty_region(self._last_point))
            if self._point is not None:
                area = self._dirty_region(self._point); self.update(area); self.last_dirty_pixels = area.width() * area.height()
            self._last_point = self._point; self._dirty = False
            self._nearby = self._nearest_controls()
        now = time.perf_counter(); before = list(self._trail); self._trail = [(p, at) for p, at in self._trail if now - at < .18]
        for point, _ in before: self.update(QRect(round(point.x()) - 5, round(point.y()) - 5, 11, 11))
        if self._press:
            self.update(self._dirty_region(self._press[0]))
            if now-self._press[1] >= .28 or not self.policy.budget.decorative_motion: self._press = None
        return moving or bool(self._trail) or self._press is not None

    def _nearest_controls(self):
        if self._point is None: return []
        nearby = []
        for reference in self._targets:
            widget = reference()
            if widget is None: continue
            try:
                if not widget.isVisible() or not widget.isEnabled(): continue
                rect = QRectF(widget.mapTo(self.owner, widget.rect().topLeft()).x(), widget.mapTo(self.owner, widget.rect().topLeft()).y(), widget.width(), widget.height())
                distance = math.hypot(max(rect.left()-self._point.x(), 0, self._point.x()-rect.right()), max(rect.top()-self._point.y(), 0, self._point.y()-rect.bottom()))
                if distance < self.policy.budget.cursor_radius*.75: nearby.append((distance, rect))
            except RuntimeError: continue
        return sorted(nearby, key=lambda item: item[0])[:3]

    def paintEvent(self, event):
        if self._point is None or (not self.theme.profile.cursor_light and self.theme.profile.cursor_glow == 'OFF'): return
        self.paint_count += 1
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); painter.setClipRegion(event.region())
        radius, opacity = cursor_style(self.theme.profile, self.policy.budget); intensity = self.theme.profile.glow * self.policy.budget.glow_factor
        if self.theme.profile.cursor_glow != 'OFF':
            light = QColor(self.theme.tokens['accent_primary']); light.setAlpha(opacity)
            glow = QRadialGradient(self._point, radius); glow.setColorAt(0, light); light.setAlpha(round(opacity*.3)); glow.setColorAt(.45, light); light.setAlpha(0); glow.setColorAt(1, light)
            painter.setPen(Qt.NoPen); painter.setBrush(glow); painter.drawEllipse(self._point, radius, radius)
        if self.theme.profile.cursor_light:
            for distance, rect in self._nearby:
                color = QColor(self.theme.tokens['accent_primary']); color.setAlpha(round(190 * intensity * max(0, 1-distance/self.policy.budget.cursor_radius)))
                edge = QRadialGradient(self._point, self.policy.budget.cursor_radius); edge.setColorAt(0, color); color.setAlpha(0); edge.setColorAt(1, color)
                painter.setBrush(Qt.NoBrush); painter.setPen(QPen(QBrush(edge), 1.4)); painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), self.theme.tokens.radius_small, self.theme.tokens.radius_small)
        if self.policy.budget.decorative_motion and self.theme.profile.cursor_trail:
            for point, at in self._trail:
                color = QColor(self.theme.tokens['accent_secondary']); color.setAlpha(round(max(0, 1 - (time.perf_counter() - at) / .18) * 40 * intensity))
                painter.setPen(Qt.NoPen); painter.setBrush(color); painter.drawEllipse(point, 3, 3)
        if self._press is not None and self.policy.budget.decorative_motion:
            point, at = self._press; progress = min(1, (time.perf_counter()-at)/.28)
            color = QColor(self.theme.tokens['accent_primary']); color.setAlpha(round(120*intensity*(1-progress)))
            painter.setBrush(Qt.NoBrush); painter.setPen(QPen(color, 1.4)); painter.drawEllipse(point, 6+18*progress, 6+18*progress)
        painter.end()

    def close(self):
        application = QApplication.instance()
        if application is not None: application.removeEventFilter(self)
        self.hide(); self._targets.clear(); self.clock.unsubscribe_id(id(self)); return super().close()
