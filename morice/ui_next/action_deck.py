"""Keyboard-accessible contextual dock with authored marks and bounded disclosure."""
from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QApplication, QToolTip
from .surfaces import MaterialSurface


class ActionDeck(MaterialSurface):
    selected = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent);self.setObjectName('ActionDeck');self.buttons={};self.expanded=False
        layout=QHBoxLayout(self);layout.setContentsMargins(8,6,8,6);layout.setSpacing(4)
        for route,label in (('chats','Chat'),('research','Research'),('projects','Build'),('spatial','Earth'),('media','Media'),('devices','Devices'),('activity','Activity')):
            button=QPushButton('');button.setCheckable(True);button.setProperty('morice_icon',route);button.setProperty('role','deck')
            button.setAccessibleName(label);button.setToolTip(label);button.setMinimumWidth(0);button.setFixedWidth(44)
            button.clicked.connect(lambda checked=False,key=route:self.selected.emit(key));button.installEventFilter(self);layout.addWidget(button);self.buttons[route]=button

    def set_active(self,key):
        for name,button in self.buttons.items():button.setChecked(name==key)

    def reveal(self):
        # Stable hit areas also work at large text scales. Context appears in a
        # themed tooltip rather than widening seven buttons during pointer use.
        self.expanded=True

    def collapse(self):
        focus=QApplication.focusWidget()
        if self.underMouse() or focus in self.buttons.values():return
        self.expanded=False
        for button in self.buttons.values():button.setText('');button.setFixedWidth(44)

    def eventFilter(self,source,event):
        if event.type() in (QEvent.Enter,QEvent.FocusIn):
            self.reveal()
            QToolTip.showText(source.mapToGlobal(source.rect().bottomLeft()),source.accessibleName(),source,source.rect(),1800)
        elif event.type() in (QEvent.Leave,QEvent.FocusOut): self.collapse()
        return False

    def hideEvent(self,event):self.expanded=False;super().hideEvent(event)

    def dispose(self):self.expanded=False
