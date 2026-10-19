"""Adaptive route state; no domain work or backend initialization on selection."""
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel, QScrollArea, QWidget, QSizePolicy
from .surfaces import MaterialSurface


@dataclass(frozen=True)
class Route:
    key: str
    label: str
    icon: str


ROUTES = tuple(Route(key, 'Core' if key == 'home' else key.title(), 'core' if key == 'home' else key) for key in ('home', 'chats', 'projects', 'research', 'spatial', 'devices',
    'media', 'automations', 'connectors', 'security', 'history', 'activity', 'tools', 'voice', 'artifacts', 'plugins', 'settings'))
PRIMARY = ('home', 'chats', 'projects', 'research', 'voice', 'media')
ADVANCED = ('spatial', 'devices', 'activity', 'tools', 'artifacts', 'automations', 'connectors', 'security', 'plugins')


class NavigationRail(MaterialSurface):
    selected = Signal(str)
    toggle_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('NavigationRail'); self.expanded = True; self.buttons = {}; self.more_expanded = False
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        layout = QVBoxLayout(self); layout.setContentsMargins(10, 14, 10, 14); layout.setSpacing(6)
        self.toggle = QPushButton(''); self.toggle.setProperty('morice_icon', 'menu'); self.toggle.setToolTip('Collapse navigation'); self.toggle.setAccessibleName('Toggle navigation'); self.toggle.clicked.connect(self.toggle_requested)
        layout.addWidget(self.toggle)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget(); routes_layout = QVBoxLayout(host); routes_layout.setContentsMargins(0, 0, 0, 0); routes_layout.setSpacing(6)
        self.scroll.setWidget(host); layout.addWidget(self.scroll, 1)
        for route in ROUTES:
            button = QPushButton(route.label); button.setProperty('morice_icon', route.icon); button.setProperty('role', 'navigation'); button.setCheckable(True); button.setToolTip(route.label); button.setAccessibleName(route.label)
            button.clicked.connect(lambda checked=False, key=route.key: self.selected.emit(key)); self.buttons[route.key] = button
        for key in PRIMARY: routes_layout.addWidget(self.buttons[key])
        self.more = QPushButton('More'); self.more.setProperty('morice_icon', 'more'); self.more.setCheckable(True)
        self.more.setAccessibleName('More workspaces'); self.more.setToolTip('Spatial, Devices, Activity, Tools, Artifacts, Automations, Connectors, Security and Plugins')
        self.more.clicked.connect(self.set_more_expanded); routes_layout.addWidget(self.more)
        self.advanced = QWidget(); extra = QVBoxLayout(self.advanced); extra.setContentsMargins(0, 0, 0, 0); extra.setSpacing(6)
        for key in ADVANCED: extra.addWidget(self.buttons[key])
        routes_layout.addWidget(self.advanced); self.advanced.hide()
        routes_layout.addStretch(1)
        for key in ('history', 'settings'): layout.addWidget(self.buttons[key])
        self.state = QLabel('Local workspace'); self.state.setProperty('role', 'secondary'); self.state.setWordWrap(True); layout.addWidget(self.state)
        self.set_expanded(True)

    def set_expanded(self, expanded):
        self.expanded = bool(expanded)
        for route in ROUTES: self.buttons[route.key].setText(route.label if expanded else '')
        self.setProperty('collapsed', not expanded)
        for button in (*self.buttons.values(), self.toggle, self.more):
            button.setProperty('compact', not expanded); button.setMinimumWidth(0)
            button.style().unpolish(button); button.style().polish(button); button.updateGeometry()
        self.more.setText('More' if expanded else '')
        self.state.setVisible(expanded); self.toggle.setToolTip('Collapse navigation' if expanded else 'Expand navigation')
        self.setMinimumWidth(0); self.setMaximumWidth(220 if expanded else 72)

    def sizeHint(self): return QSize(220 if self.expanded else 72, super().sizeHint().height())

    def set_active(self, key):
        if key in ADVANCED: self.set_more_expanded(True)
        for route, button in self.buttons.items(): button.setChecked(route == key)
        if key in PRIMARY or key in ADVANCED: self.scroll.ensureWidgetVisible(self.buttons[key], 0, 12)

    def set_more_expanded(self, expanded):
        self.more_expanded = bool(expanded); self.more.setChecked(self.more_expanded); self.advanced.setVisible(self.more_expanded)
        self.more.setAccessibleDescription('Expanded' if self.more_expanded else 'Collapsed; activate to show more workspaces')

    def enable_route(self, key, enabled, reason=''):
        button = self.buttons[key]; button.setEnabled(enabled); button.setToolTip(reason if not enabled else next(route.label for route in ROUTES if route.key == key))
