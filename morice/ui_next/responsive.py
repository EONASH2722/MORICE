"""Bounded flow layout for native controls and wrapped action cards."""
from PySide6.QtCore import Qt, QRect, QPoint, QSize
from PySide6.QtWidgets import QLayout, QLayoutItem


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing=8):
        super().__init__(parent); self._items = []; self.setContentsMargins(0, 0, 0, 0); self.setSpacing(spacing)

    def addItem(self, item):
        if len(self._items) >= 64: raise ValueError('Flow layout has a bounded 64-control limit.')
        self._items.append(item)

    def count(self): return len(self._items)
    def itemAt(self, index): return self._items[index] if 0 <= index < self.count() else None
    def takeAt(self, index): return self._items.pop(index) if 0 <= index < self.count() else None
    def expandingDirections(self): return Qt.Horizontal
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self._arrange(QRect(0, 0, max(1, width), 0), True)

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            if item.widget() is not None and item.widget().isHidden(): continue
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left()+margins.right(), margins.top()+margins.bottom())

    def sizeHint(self): return QSize(max(300, self.minimumSize().width()), self.heightForWidth(700))

    def setGeometry(self, rect):
        super().setGeometry(rect); self._arrange(rect, False)

    def _arrange(self, rect, measure):
        margins = self.contentsMargins(); area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = area.x(); y = area.y(); line_height = 0; gap = max(0, self.spacing())
        for item in self._items:
            if item.widget() is not None and item.widget().isHidden(): continue
            width = min(max(1, area.width()), max(item.minimumSize().width(), item.sizeHint().width()))
            height = max(item.minimumSize().height(), item.heightForWidth(width) if item.hasHeightForWidth() else item.sizeHint().height())
            if x != area.x() and x+width > area.x()+area.width(): x = area.x(); y += line_height+gap; line_height = 0
            if not measure: item.setGeometry(QRect(QPoint(x, y), QSize(width, height)))
            x += width+gap; line_height = max(line_height, height)
        return y+line_height-rect.y()+margins.bottom()

