"""Transparent input area over the single shared globe, with no render surface."""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent, QWheelEvent, QContextMenuEvent
from PySide6.QtWidgets import QWidget, QApplication


class GlobeInputSurface(QWidget):
    def __init__(self,view,parent=None):
        super().__init__(parent);self.view=view;self.setMouseTracking(True);self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName('Interact with the background globe')

    def _mouse(self,event):
        target=self.view.canvas
        if not hasattr(target,'dynamics'):return
        position=QPointF(target.mapFromGlobal(event.globalPosition().toPoint()))
        copy=QMouseEvent(event.type(),position,event.globalPosition(),event.button(),event.buttons(),event.modifiers())
        QApplication.sendEvent(target,copy);event.accept()

    mouseMoveEvent=_mouse
    mousePressEvent=_mouse
    mouseReleaseEvent=_mouse
    mouseDoubleClickEvent=_mouse

    def wheelEvent(self,event):
        target=self.view.canvas
        if not hasattr(target,'dynamics'):return
        position=QPointF(target.mapFromGlobal(event.globalPosition().toPoint()))
        copy=QWheelEvent(position,event.globalPosition(),event.pixelDelta(),event.angleDelta(),event.buttons(),event.modifiers(),event.phase(),event.inverted())
        QApplication.sendEvent(target,copy);event.accept()

    def leaveEvent(self,event):
        if hasattr(self.view.canvas,'dynamics'):
            self.view.canvas.dynamics.pointer=(4.,4.);self.view.canvas.clock.request()
        super().leaveEvent(event)

    def contextMenuEvent(self,event):
        QApplication.sendEvent(self.view.canvas,QContextMenuEvent(event.reason(),self.view.canvas.mapFromGlobal(event.globalPos()),event.globalPos()))
