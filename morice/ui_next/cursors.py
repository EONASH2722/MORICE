"""Outlined native cursors, independent of decorative cursor lighting."""
from PySide6.QtCore import QObject, QEvent, QPointF, Qt
from PySide6.QtGui import QCursor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


def outlined_cursor(shape, ratio=1.):
    ratio = max(1., min(4., float(ratio)))
    pixmap = QPixmap(round(32 * ratio), round(32 * ratio))
    pixmap.setDevicePixelRatio(ratio); pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    if shape == Qt.IBeamCursor:
        path.moveTo(16, 5); path.lineTo(16, 27)
        path.moveTo(11, 5); path.lineTo(21, 5)
        path.moveTo(11, 27); path.lineTo(21, 27)
        painter.setPen(QPen(Qt.black, 4., Qt.SolidLine, Qt.RoundCap)); painter.drawPath(path)
        painter.setPen(QPen(Qt.white, 1.8, Qt.SolidLine, Qt.RoundCap)); painter.drawPath(path)
        hotspot = (16, 16)
    else:
        if shape == Qt.PointingHandCursor:
            path.moveTo(10, 16); path.lineTo(10, 5)
            path.cubicTo(10, 1, 15, 1, 15, 5); path.lineTo(15, 12)
            path.cubicTo(16, 9, 20, 10, 20, 13)
            path.cubicTo(22, 11, 25, 13, 25, 16)
            path.cubicTo(28, 15, 29, 18, 27, 23)
            path.lineTo(24, 29); path.lineTo(13, 29); path.lineTo(5, 19)
            path.cubicTo(2, 15, 6, 13, 10, 18); path.closeSubpath()
            hotspot = (12, 3)
        else:
            path.moveTo(4, 3); path.lineTo(4, 26); path.lineTo(10, 20)
            path.lineTo(15, 30); path.lineTo(20, 27); path.lineTo(15, 18)
            path.lineTo(24, 18); path.closeSubpath(); hotspot = (4, 3)
        painter.setPen(QPen(Qt.black, 2., Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.white); painter.drawPath(path)
    painter.end()
    return QCursor(pixmap, *hotspot)


class VisibleCursors(QObject):
    """Keep pointer roles visible without a global override or hiding the OS cursor."""
    SHAPES = (Qt.ArrowCursor, Qt.PointingHandCursor, Qt.IBeamCursor)

    def __init__(self, owner):
        super().__init__(owner); self.owner = owner; self._cache = {}
        for widget in (owner, *owner.findChildren(QWidget)): self.apply(widget)
        QApplication.instance().installEventFilter(self)

    def apply(self, widget):
        shape = QWidget.cursor(widget).shape()
        if shape not in self.SHAPES: return
        key = (shape, widget.devicePixelRatioF())
        if key not in self._cache: self._cache[key] = outlined_cursor(*key)
        QWidget.setCursor(widget, self._cache[key])

    def eventFilter(self, source, event):
        if event.type() in (QEvent.Enter, QEvent.CursorChange) and isinstance(source, QWidget):
            if source is self.owner or self.owner.isAncestorOf(source): self.apply(source)
        return False

    def close(self):
        application = QApplication.instance()
        if application is not None: application.removeEventFilter(self)
