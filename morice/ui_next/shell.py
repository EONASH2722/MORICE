"""Production shell over established window callbacks and runtime authorities.

Hidden compatibility controls retain existing controller bindings. Final
acceptance and source cleanup are tracked separately in the parity matrix.
"""
from __future__ import annotations

from pathlib import Path
import re

from PySide6.QtCore import Qt, Signal, Slot, QObject, QTimer, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QKeySequence, QShortcut, QPalette, QColor, QFont
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QToolButton, QScrollArea, QMenu, QSizePolicy

from ..pyside_app import MoriceWindow as ExistingPresenter, RichContentView
from .bridge import UiBridge
from .effects import CursorLighting, ActionCard
from .motion import EffectClock, EffectPolicy, MotionDirector
from .navigation import NavigationRail
from .spatial_view import SpatialView
from .themes import ThemeEngine, stylesheet, AppearanceProfile
from .surfaces import MaterialSurface
from .theme_scenes import SCENES
from .wake import WakeController
from .settings_view import SettingsWorkspace
from .workspace_adapters import (ResearchWorkspace, DevicesWorkspace, AmbientWorkspace,
    HistoryWorkspace, PluginsWorkspace, ProjectsWorkspace, ToolsWorkspace, page)
from .media_view import MediaWorkspace
from .materials import MaterialBackdrop
from ..spatial.service import SpatialService
from .activity_view import ActivityWorkspace
from .responsive import FlowLayout
from ..ui_workspace import CommandItem, DEFAULT_COMMANDS
from .themes import PRESETS
from .renderer_clock import RendererClockRegistry
from ..unified_intelligence import PermissionState
from .icons import UiIconBinder
from ..ui_system import normalize_theme
from .file_access import require_selected_file
from .core_state import CorePresentation
from .core_view import CoreView
from .action_deck import ActionDeck


class BrandMark(QWidget):
    """Render the unchanged 1024-pixel original at the target's actual DPI."""
    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedSize(32, 32)
        self.source = Path(__file__).resolve().parents[1] / 'assets/morice-logo-rgb.png'
        self.pixmap = QPixmap(str(self.source)); self.setAccessibleName('MORICE original logo')

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self.pixmap); painter.end()


class RouteStack(QStackedWidget):
    """Route pages scroll internally; hidden pages never resize the window."""
    def hasHeightForWidth(self):return False
    def heightForWidth(self,width):return -1
    def minimumSizeHint(self):return QSize(0,0)


class RenovatedWindow(ExistingPresenter):
    voice_output_event = Signal(str, object)
    def __init__(self, runtime_services=None, recovery_info=None):
        self._renovated_ready = False
        super().__init__(runtime_services, recovery_info)
        self.theme_engine = ThemeEngine(self.runtime.directory / 'renovation', {**self.settings, 'theme': self.current_theme, 'reduced_motion': str(self.reduced_motion).lower()}, self)
        self.effect_policy = EffectPolicy(self.theme_engine, self)
        self.motion_director = MotionDirector(self.theme_engine, self)
        self.effect_clock = EffectClock(self.effect_policy, self)
        self.ui_bridge = UiBridge(self.runtime, self)
        self.core_presentation = CorePresentation(self, self.ui_bridge, self)
        self.routes = {}; self.active_route = 'home'; self.route_factories = {}
        # Keep established backend callbacks and their controls during staged
        # migration. Only the renovated root becomes visible; no second window.
        self.compatibility_host = QWidget(self); self.compatibility_host.hide()
        root = self.layout()
        while root.count():
            item = root.takeAt(0)
            if item.widget(): item.widget().setParent(self.compatibility_host)
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget(): child.widget().setParent(self.compatibility_host)
        self.presentation_root = QWidget(self); self.presentation_root.setObjectName('RenovatedContent')
        root.setContentsMargins(0, 0, 0, 0); root.addWidget(self.presentation_root)
        root = QVBoxLayout(self.presentation_root)
        self.setStyleSheet('')
        self.setObjectName('RenovatedShell'); self.setMinimumSize(720, 500)
        available = self.screen().availableGeometry() if self.screen() else None
        if not self._session_enabled or len(self.workspace_state.geometry) != 4:
            self.resize(min(1366, available.width()-24) if available else 1366, min(840, available.height()-24) if available else 840)
        self.setAttribute(Qt.WA_TranslucentBackground, False); self.setAttribute(Qt.WA_StyledBackground, True); self.setAutoFillBackground(True)
        self.setFont(QFont('Segoe UI', 10))
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / 'assets/morice-logo-rgb.png')))
        root.setContentsMargins(14, 12, 14, 12); root.setSpacing(12)
        self.header = QFrame(); header = QHBoxLayout(self.header); header.setContentsMargins(6, 0, 6, 0)
        header.addWidget(BrandMark()); brand = QLabel('MORICE'); brand.setProperty('role', 'title'); header.addWidget(brand)
        self.core_button = QPushButton(''); self.core_button.setProperty('morice_icon', 'core'); self.core_button.setFixedWidth(40)
        self.core_button.setAccessibleName('Return to Core'); self.core_button.setToolTip('Return to Core · Ctrl 1'); self.core_button.clicked.connect(lambda: self.navigate('home')); header.addWidget(self.core_button)
        self.workspace_menu = QPushButton(''); self.workspace_menu.setProperty('morice_icon', 'menu'); self.workspace_menu.setFixedWidth(40)
        self.workspace_menu.setAccessibleName('Show workspaces'); self.workspace_menu.setToolTip('Show workspaces'); self.workspace_menu.clicked.connect(self.toggle_sidebar); header.addWidget(self.workspace_menu)
        self.breadcrumb = QLabel('Personal workspace'); self.breadcrumb.setProperty('role', 'secondary'); header.addWidget(self.breadcrumb); header.addStretch(1)
        palette = QPushButton('Search  ·  Ctrl K'); palette.setProperty('morice_icon', 'search'); palette.clicked.connect(self.open_command_palette); header.addWidget(palette)
        self.theme_button = QPushButton('Theme'); self.theme_button.setProperty('morice_icon','appearance'); self.theme_button.setAccessibleName('Choose theme'); self.theme_button.setToolTip('Choose a theme and its animation'); self.theme_button.clicked.connect(self._open_theme_menu); header.addWidget(self.theme_button)
        for name, label, action in (('minimize', 'Minimize', self.showMinimized), ('maximize', 'Maximize or restore', self._toggle_renovated_maximize), ('close', 'Close', self.close)):
            button = QPushButton(''); button.setProperty('morice_icon', name); button.setFixedWidth(40); button.clicked.connect(action); button.setAccessibleName(label); button.setToolTip(label); header.addWidget(button)
        root.addWidget(self.header)
        body = QHBoxLayout(); self.navigation = NavigationRail(); self.navigation.set_expanded(False); self.navigation.selected.connect(self.navigate); self.navigation.toggle_requested.connect(self.toggle_sidebar); body.addWidget(self.navigation)
        central = QVBoxLayout(); central.setSpacing(16); self.route_stack = RouteStack(); central.addWidget(self.route_stack, 1)
        # Hidden routes must not impose their minimum height on Core/Chat.
        # The composer and dock reserve space before the active route expands.
        self.route_stack.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Ignored)
        self.composer = self._new_composer(); central.addWidget(self.composer, 0, Qt.AlignHCenter)
        self.input.document().documentLayout().documentSizeChanged.connect(self._fit_renovated_composer)
        self.action_deck = ActionDeck(); self.action_deck.selected.connect(self.navigate); central.addWidget(self.action_deck, 0, Qt.AlignHCenter)
        body.addLayout(central, 1); root.addLayout(body, 1)
        self.status_line = QLabel('Ready · Private local workspace'); self.status_line.setProperty('role', 'secondary'); root.addWidget(self.status_line)
        self.core_presentation.changed.connect(self._core_changed)
        self._add_route('home', self._home_view())
        chat = QWidget(); chat_layout = QVBoxLayout(chat); chat_layout.setContentsMargins(16, 8, 16, 8); chat_layout.addWidget(self.scroll)
        self.scroll.show(); self._add_route('chats', chat)
        self._add_route('spatial', SpatialView(self.runtime, self.ui_bridge, self.theme_engine, self.effect_policy, self.effect_clock))
        self.wake_controller = WakeController(self, self.theme_engine, self.effect_policy, self.effect_clock)
        self.wake_controller.changed.connect(self.core_presentation.wake_changed)
        self._add_route('settings', SettingsWorkspace(self))
        self._add_route('projects', ProjectsWorkspace(self))
        self._add_route('tools', ToolsWorkspace(self)); self._add_route('activity', ActivityWorkspace(self, self.ui_bridge))
        self._add_route('voice', self._voice_view()); self._add_route('artifacts', self._artifacts_view())
        self.route_factories.update(research=lambda: ResearchWorkspace(self.runtime, self.ui_bridge, self, theme=self.theme_engine),
            devices=lambda: DevicesWorkspace(self.runtime, self.ui_bridge, self), media=lambda: MediaWorkspace(self.runtime, self.ui_bridge, self.effect_policy),
            history=lambda: HistoryWorkspace(self), plugins=lambda: PluginsWorkspace(self, self.ui_bridge))
        for key in ('automations', 'connectors', 'security'): self.route_factories[key] = self._ambient_view
        self._renovated_ready = True
        self.plugin_center.open_center = lambda: self.navigate('plugins')
        # This retired presentation never becomes visible in the renovated root.
        # Its polling timer is cosmetic; all domain/service owners remain intact.
        for item in self.compatibility_host.findChildren(QWidget):
            if type(item).__name__ == 'LiquidGalaxyFrame' and hasattr(item, '_timer'): item._timer.stop()
        self.voice_output_event.connect(self.wake_controller.voice_event, Qt.QueuedConnection)
        self.composer_centered = False
        self._cancel_composer_animation(finish=False)
        self.theme_engine.changed.connect(self._apply_renovated_theme)
        self.icon_binder = UiIconBinder(self, self.theme_engine)
        self._apply_renovated_theme()
        restored_route = self.workspace_state.presentation_route if self._session_enabled else 'home'
        if restored_route not in self.routes and restored_route not in self.route_factories: restored_route = 'home'
        self.navigation.set_expanded(self._session_enabled and self.workspace_state.presentation_navigation_expanded)
        self.navigate(restored_route)
        self.ui_bridge.event_arrived.connect(self._runtime_event)
        self.theme_engine.changed.connect(lambda *_: self.effect_clock.configure())
        self.cursor_lighting = CursorLighting(self, self.theme_engine, self.effect_policy, self.effect_clock)
        self.material_backdrop = MaterialBackdrop(self, self.theme_engine, self.effect_policy, self.effect_clock, self.core_presentation)
        self.cursor_lighting.pointer_changed.connect(self.material_backdrop.pointer_changed)
        self.renderer_clocks = RendererClockRegistry(self, self.effect_policy, self.effect_clock); self.renderer_clocks.register(self)
        self.cursor_lighting.set_targets()
        self._header_drag = None; self.header.installEventFilter(self)
        QTimer.singleShot(0, self._fit_renovated_composer)
        self._workspace_shortcuts = []
        for key, route in (('Ctrl+1', 'home'), ('Ctrl+2', 'chats'), ('Ctrl+3', 'spatial')):
            shortcut = QShortcut(QKeySequence(key), self); shortcut.activated.connect(lambda name=route: self.navigate(name)); self._workspace_shortcuts.append(shortcut)

    def _new_composer(self):
        frame = MaterialSurface(); frame.setObjectName('ComposerSurface'); frame.setMinimumWidth(0); frame.setMaximumWidth(860)
        layout = QVBoxLayout(frame); layout.setContentsMargins(14, 10, 14, 10); layout.setSpacing(6)
        row = QHBoxLayout(); self.input.setParent(frame); self.input.set_height_bounds(48, 132); self.input.show(); row.addWidget(self.input, 1)
        self.input.setPlaceholderText('Ask MORICE…')
        self.send_btn.setParent(frame); self.send_btn.setProperty('role', 'primary'); self.send_btn.show(); row.addWidget(self.send_btn); layout.addLayout(row)
        controls = QHBoxLayout()
        for widget, label in ((self.attach_btn, 'Attach'), (self.voice_btn, 'Voice')):
            widget.setParent(frame); widget.setText(''); widget.setToolTip(label); widget.setAccessibleName(label); widget.setProperty('morice_icon', label.casefold()); widget.setMinimumWidth(0); widget.setFixedWidth(40); widget.setFixedHeight(self.theme_engine.tokens.control_height); widget.show(); controls.addWidget(widget)
        hint = QLabel('Your workspace'); hint.setProperty('role', 'secondary'); controls.addWidget(hint, 1)
        self.composer_options = QPushButton('Context'); self.composer_options.setProperty('morice_icon', 'context'); self.composer_options.setCheckable(True); controls.addWidget(self.composer_options)
        layout.addLayout(controls)
        self.composer_details = QWidget(frame); details = FlowLayout()
        self.composer_details.setLayout(details)
        for widget, label in ((self.project_selector_btn, 'Project context'), (self.model_selector_btn, 'Model')):
            widget.setParent(self.composer_details); widget.setText(label); widget.setProperty('morice_icon', 'context' if label == 'Project context' else 'model'); widget.setMinimumWidth(0); widget.setMaximumWidth(240); widget.setFixedHeight(self.theme_engine.tokens.control_height); widget.show(); details.addWidget(widget)
        self.quick_actions_btn.setParent(self.composer_details); self.quick_actions_btn.setText('Quick actions'); self.quick_actions_btn.setProperty('morice_icon','more'); self.quick_actions_btn.setMinimumWidth(0); self.quick_actions_btn.show(); details.addWidget(self.quick_actions_btn)
        layout.addWidget(self.composer_details); self.composer_details.hide(); self.composer_options.toggled.connect(self.composer_details.setVisible)
        self.composer_options.toggled.connect(self._fit_renovated_composer)
        self.input_frame.hide(); self.input_frame = frame; self.input_glow = None
        return frame

    def _open_theme_menu(self):
        menu=QMenu(self)
        motion=menu.addAction('Animate the workspace');motion.setCheckable(True);motion.setChecked(not self.theme_engine.profile.reduced_motion)
        motion.triggered.connect(lambda checked:self.theme_engine.update(reduced_motion=not checked))
        menu.addSeparator()
        for preset,(name,description) in SCENES.items():
            action=menu.addAction(preset.title()+' · '+name);action.setCheckable(True);action.setChecked(self.theme_engine.profile.preset==preset);action.setToolTip(description)
            action.triggered.connect(lambda checked=False,value=preset:self.theme_engine.update(preset=value))
        menu.addSeparator();menu.addAction('Appearance settings',lambda:self.navigate('settings'))
        menu.setAttribute(Qt.WA_DeleteOnClose);menu.popup(self.theme_button.mapToGlobal(self.theme_button.rect().bottomLeft()))

    def _home_view(self):
        return CoreView(self.core_presentation, self.theme_engine, self.effect_policy, self.effect_clock)

    def _add_route(self, key, widget):
        self.routes[key] = widget
        if self.route_stack.indexOf(widget) < 0: self.route_stack.addWidget(widget)

    def navigate(self, key):
        if key not in self.routes and key in self.route_factories:
            try: self._add_route(key, self.route_factories[key]())
            except Exception as exc:
                self.status_line.setText('This workspace could not open: ' + str(exc)[:300]); return
        if key not in self.routes: return
        self.active_route = key; self.route_stack.setCurrentWidget(self.routes[key]); self.navigation.set_active(key)
        self.navigation.setVisible(key != 'home'); self.action_deck.set_active(key); self.core_button.setVisible(key != 'home')
        self.action_deck.setVisible(not self.navigation.isVisible())
        self.breadcrumb.setText(key.title() if key != 'home' else 'Core')
        self.composer.setVisible(key in {'home', 'chats', 'projects', 'voice'})
        self._size_renovated_composer()
        if key == 'spatial': self.routes[key].set_context(self.runtime.spatial.snapshot())
        if key == 'projects': self.project_lookup_btn.show()
        if key in {'automations', 'connectors', 'security'}: self.routes[key].select_route(key)
        self.effect_clock.request()
        if hasattr(self, 'cursor_lighting'): self.cursor_lighting.set_targets()

    def _ambient_view(self):
        if not hasattr(self, '_renovated_ambient'): self._renovated_ambient = AmbientWorkspace(self.runtime, self.ui_bridge, self)
        return self._renovated_ambient

    def _voice_view(self):
        view, layout = page('Voice', 'Live conversation and explicitly enabled camera context.')
        row = QHBoxLayout()
        for button in (self.voice_mode_btn, self.normal_mode_btn): row.addWidget(button)
        layout.addLayout(row); self.live_action_workspace.setParent(view); layout.addWidget(self.live_action_workspace, 1)
        return view

    def _artifacts_view(self):
        view, layout = page('Artifacts', 'Interactive graphs, physics, chemistry, diagrams and scientific documents.')
        self.workspace_panel.setParent(view); self.workspace_panel.setMinimumWidth(0); self.workspace_panel.setMaximumWidth(16777215)
        layout.addWidget(self.workspace_panel, 1); self.workspace_panel.show(); return view

    def _cancel_current_work(self):
        self.runtime.voice.interrupt('user stop')
        if self.is_busy: self.input.setText('stop'); ExistingPresenter.on_send(self)

    def append_message(self, *args, **kwargs):
        result = super().append_message(*args, **kwargs)
        if hasattr(self, 'renderer_clocks'): self.renderer_clocks.register(self)
        if getattr(self,'_renovated_ready',False):self._refresh_rich_appearance()
        return result

    def _refresh_rich_appearance(self):
        for view in self.findChildren(RichContentView):view.apply_design_tokens(self.theme_engine.tokens)

    def _set_assistant_hub_visible(self, visible):
        if not getattr(self, '_renovated_ready', False): return super()._set_assistant_hub_visible(visible)
        self.navigate('tools' if visible else 'chats')
        if visible: self._refresh_workspace_hub()

    def toggle_mode_panel(self):
        if not getattr(self, '_renovated_ready', False): return super().toggle_mode_panel()
        self.navigate('projects' if self.chat_mode in {'project','voice'} else 'settings')
        if self.active_route == 'settings': self._select_settings_category('Models')

    def _select_settings_category(self, category):
        view = self.routes['settings']; self.navigate('settings')
        for index in range(view.list.count()):
            if view.list.item(index).text() == category: view.list.setCurrentRow(index); break

    def _open_composer_actions(self):
        if not getattr(self, '_renovated_ready', False): return super()._open_composer_actions()
        menu = QMenu(self)
        for label, callback in (('Attach a file',self.on_attach),('Voice',self._toggle_voice_input),('Choose model',self._choose_model_source),('Project mode',self._toggle_composer_project_mode)):
            menu.addAction(label,callback)
        menu.addSeparator();precision=menu.addAction(self.precision_btn.text(),self.on_toggle_precision);precision.setCheckable(True);precision.setChecked(self.precision_mode)
        menu.addAction('Personalization settings',lambda:self._select_settings_category('Personalization'))
        menu.addAction('Search all commands',self.open_command_palette)
        menu.exec(self.quick_actions_btn.mapToGlobal(self.quick_actions_btn.rect().bottomLeft()))

    def _refresh_mode_panel(self):
        if not getattr(self, '_renovated_ready', False): return super()._refresh_mode_panel()
        # Existing data/control synchronization remains intact. Cosmetic motion
        # on the retired compatibility panels has no presentation purpose.
        moving=self._motion_enabled;self._motion_enabled=False
        try:super()._refresh_mode_panel()
        finally:self._motion_enabled=moving
        self.project_lookup_btn.setVisible(self.active_route=='projects')

    def _open_research_lab(self):
        if not getattr(self, '_renovated_ready', False): return super()._open_research_lab()
        self.navigate('research')

    def _open_ambient(self):
        if not getattr(self, '_renovated_ready', False): return super()._open_ambient()
        self.navigate('automations')

    def _enable_node_pairing(self):
        if not getattr(self, '_renovated_ready', False): return super()._enable_node_pairing()
        self.navigate('devices')

    def _open_chat_history(self):
        if not getattr(self, '_renovated_ready', False): return super()._open_chat_history()
        if self.is_busy: self.status_line.setText('Finish or cancel the response before reopening history.'); return
        self.navigate('history')

    def _open_workspace(self, kind):
        if not getattr(self, '_renovated_ready', False): return super()._open_workspace(kind)
        self._set_workspace_view(kind); self.navigate('artifacts')

    def _close_workspace(self):
        if not getattr(self, '_renovated_ready', False): return super()._close_workspace()
        self.navigate('chats')

    def _renovation_commands(self):
        routes = tuple(CommandItem('renovation:route:'+key, 'Open '+button.accessibleName(), 'Workspace', key)
            for key, button in self.navigation.buttons.items())
        themes = tuple(CommandItem('renovation:theme:'+key, key+' theme', 'Appearance', 'theme color appearance '+key) for key in PRESETS)
        return routes + themes

    def _refresh_plugin_commands(self):
        super()._refresh_plugin_commands()
        if getattr(self, '_renovated_ready', False): self._refresh_renovation_commands()

    def _refresh_renovation_commands(self):
        contributions = tuple(CommandItem(item['key'], item['title'], item['hint'], item['keywords']) for item in self.runtime.plugins.command_contributions())
        panels = tuple(CommandItem(f"plugin-ui:{item['pluginId']}:{item['id']}", item['title'], item['kind'], 'plugin workspace')
            for item in self.runtime.plugins.contribution_catalog().get('ui', ()))
        self.command_palette.set_commands((*DEFAULT_COMMANDS, *self._renovation_commands(), *contributions, *panels))

    def open_command_palette(self):
        if getattr(self, '_renovated_ready', False): self._refresh_renovation_commands()
        super().open_command_palette()

    def _on_workspace_command(self, command, argument=None):
        if getattr(self, '_renovated_ready', False) and str(command).startswith('renovation:'):
            kind, value = str(command).split(':', 2)[1:]
            if kind == 'route': self.navigate(value)
            elif kind == 'theme': self.theme_engine.update(preset=value)
            return
        return super()._on_workspace_command(command, argument)

    def _show_notification(self, *args, **kwargs):
        super()._show_notification(*args, **kwargs)
        if getattr(self, '_renovated_ready', False) and hasattr(self, 'notification_toast'):
            self.notification_toast.setProperty('role', 'surface')
            self.notification_toast.move(max(12, self.width()-self.notification_toast.width()-24), self.header.geometry().bottom()+12)

    def _apply_renovated_theme(self, *_):
        style = stylesheet(self.theme_engine.tokens)
        if self.presentation_root.styleSheet() != style:self.presentation_root.setStyleSheet(style)
        for name in ('command_palette', 'notification_toast', 'diagnostics_dialog'):
            widget = getattr(self, name, None)
            if widget is not None and widget.styleSheet() != style: widget.setStyleSheet(style)
        palette = self.palette(); palette.setColor(QPalette.Window, QColor(self.theme_engine.tokens['background'])); self.setPalette(palette)
        self.reduced_motion = self.theme_engine.profile.reduced_motion
        self._refresh_rich_appearance()
        self._motion_enabled = not self.reduced_motion and self.theme_engine.profile.motion_strength > 0
        self.animation_engine.configure(enabled=self._motion_enabled)
        if hasattr(self, 'micro_interactions'): self.micro_interactions.set_enabled(False)
        if hasattr(self, 'composer'):
            self.input.set_height_bounds(max(48, self.theme_engine.tokens.body_size*2+18), max(132, self.theme_engine.tokens.body_size*5+24))
            for field in (self.attach_btn, self.voice_btn, self.project_selector_btn, self.model_selector_btn, self.quick_actions_btn):
                field.setFixedHeight(self.theme_engine.tokens.control_height)
        if self.width() < 1020 * min(1.4, self.theme_engine.profile.font_scale) and self.navigation.expanded:
            self.navigation.set_expanded(False)
        QTimer.singleShot(0, self._fit_renovated_composer)

    def _apply_theme(self):
        if not getattr(self, '_renovated_ready', False): return super()._apply_theme()
        self._apply_renovated_theme()

    def _set_theme(self, theme, notify=True):
        if not getattr(self, '_renovated_ready', False): return super()._set_theme(theme, notify=notify)
        requested = normalize_theme(theme)
        self.theme_engine.update(preset={'light': 'ICE', 'midnight': 'MIDNIGHT', 'glass':'GLASS', 'custom': 'CUSTOM'}.get(requested, 'MORICE'))
        return super()._set_theme(requested, notify=notify)

    def _apply_experience_preferences(self, data):
        if not getattr(self, '_renovated_ready', False): return super()._apply_experience_preferences(data)
        from ..premium_experience import ExperienceProfile
        profile = ExperienceProfile.from_value(data)
        if profile.appearance is not None:
            appearance = AppearanceProfile.from_dict(profile.appearance)
        else:
            # Legacy profiles migrate through the same central token engine.
            appearance = AppearanceProfile(preset={'light':'ICE','midnight':'MIDNIGHT','glass':'GLASS','custom':'CUSTOM'}.get(profile.theme,'MORICE'),
                primary_accent=profile.accent, reduced_motion=profile.reduced_motion, high_contrast=profile.high_contrast,
                font_scale=profile.ui_scale, motion_speed={'slow':.7,'fast':1.4}.get(profile.animation_speed,1.0))
        self.theme_engine.apply_profile(appearance)
        return super()._apply_experience_preferences(data)

    def _apply_workspace_preset(self, preset, notify=True):
        if not getattr(self, '_renovated_ready', False): return super()._apply_workspace_preset(preset, notify=notify)
        from ..settings import normalize_workspace_preset
        self.workspace_preset = normalize_workspace_preset(preset)
        if self.workspace_preset == 'project': self._set_chat_mode('project')
        self.navigate({'science':'artifacts','project':'projects','research':'research'}.get(self.workspace_preset,'home'))
        self._save_workspace_session()
        if notify: self._show_notification('Workspace preset applied.', 'success')

    def _on_font_selection_changed(self, index):
        super()._on_font_selection_changed(index)
        if getattr(self, '_renovated_ready', False): self.theme_engine.update(font_family=self.font_family)

    def _choose_custom_font(self):
        if getattr(self, '_renovated_ready', False):
            try: require_selected_file(self.runtime, 'file_read')
            except PermissionError as exc: self.style_status.setText(str(exc)); return
        super()._choose_custom_font()
        if getattr(self, '_renovated_ready', False): self.theme_engine.update(font_family=self.font_family)

    def _configure_input_bar(self, centered):
        if not getattr(self, '_renovated_ready', False): return super()._configure_input_bar(centered)
        self.composer_centered = False

    def _update_composer_responsive_state(self):
        if not getattr(self, '_renovated_ready', False): return super()._update_composer_responsive_state()

    def _dock_composer_immediate(self):
        if not getattr(self, '_renovated_ready', False): return super()._dock_composer_immediate()
        self.composer_centered = False; self.navigate('chats')

    def _dock_composer(self):
        if not getattr(self, '_renovated_ready', False): return super()._dock_composer()
        if self.active_route != 'projects': self.navigate('chats')

    def toggle_sidebar(self):
        if not getattr(self, '_renovated_ready', False): return super().toggle_sidebar()
        if not self.navigation.isVisible(): self.navigation.show(); self.action_deck.hide(); self.navigation.set_expanded(True); self._size_renovated_composer(); self.effect_clock.request(); return
        if self.active_route == 'home': self.navigation.hide(); self.action_deck.show(); self._size_renovated_composer(); return
        start = self.navigation.width(); expanded = not self.navigation.expanded; self.navigation.set_expanded(expanded); self.navigation.setMaximumWidth(start)
        self._size_renovated_composer()
        self.motion_director.animate(self.navigation, b'maximumWidth', 220 if expanded else 72, token='panel')

    def _toggle_renovated_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _restore_maximized_workspace(self):
        if not getattr(self, '_renovated_ready', False): return super()._restore_maximized_workspace()
        self._custom_maximized = False; self.showMaximized()

    def _save_workspace_session(self):
        if not getattr(self, '_renovated_ready', False): return super()._save_workspace_session()
        if not self._session_enabled: return
        self.workspace_state.presentation_route = self.active_route
        self.workspace_state.presentation_navigation_expanded = self.navigation.expanded
        previous = self._custom_maximized
        try:
            if self.isMaximized():
                self._normal_geometry = self.normalGeometry(); self._custom_maximized = True
            return super()._save_workspace_session()
        finally: self._custom_maximized = previous

    def _open_new_window(self):
        if not getattr(self, '_renovated_ready', False): return super()._open_new_window()
        window = RenovatedWindow(self.runtime); window.setAttribute(Qt.WA_DeleteOnClose, True)
        self._child_windows.append(window); window.destroyed.connect(self._renovated_child_destroyed)
        window.show(); self._record_activity('New MORICE window opened', category='workspace')

    @Slot(QObject)
    def _renovated_child_destroyed(self, obj):
        from shiboken6 import isValid, getCppPointer
        pointer = getCppPointer(obj)[0]
        self._child_windows[:] = [window for window in self._child_windows if isValid(window) and getCppPointer(window)[0] != pointer]

    def on_send(self):
        if not getattr(self, '_renovated_ready', False): return super().on_send()
        text = self.input.text().strip()
        if SpatialService.is_context_command(text):
            self.input.clear()
            wake_epoch = self.wake_controller.epoch if self.wake_controller.active else None
            cancellation = self.wake_controller.interaction_token if wake_epoch is not None else None
            def done(envelope):
                if wake_epoch is not None and wake_epoch != self.wake_controller.epoch: return
                if envelope['ok'] and envelope['value']:
                    self._append_direct_reply(text, envelope['value']['message'])
                    self.navigate('spatial'); self.routes['spatial'].completed(envelope)
                    if self.isMinimized() or not self.isVisible(): self.showNormal(); self.raise_(); self.activateWindow()
                elif envelope['ok']:
                    self.input.setText(text); self.navigate('chats'); super(RenovatedWindow, self).on_send()
                else:
                    self.status_line.setText(envelope.get('error', 'Spatial request failed.'))
                    self.wake_controller.result(envelope.get('error', 'Spatial request failed.'))
            def execute():
                if cancellation is not None: cancellation.raise_if_cancelled()
                return self.runtime.spatial.handle_text(text)
            self.ui_bridge.submit('spatial-chat-command', execute, done)
            return
        if self.active_route not in {'projects', 'voice'}: self.navigate('chats')
        super().on_send()

    def _wake_from_external(self, source=''):
        if not getattr(self, '_renovated_ready', False): return super()._wake_from_external(source)
        from ..wake_runtime import parse_wake_request
        from ..desktop_pet import foreground_is_fullscreen
        request = parse_wake_request(source)
        self.wake_controller.activate(request.source, fullscreen=self.isFullScreen() or foreground_is_fullscreen(ignored_hwnds={int(self.wake_controller.overlay.winId())}))

    def _begin_voice_listening(self):
        if getattr(self, '_renovated_ready', False):
            permission = self.runtime.kernel.permissions.controller.state('microphone_access')
            if permission not in {PermissionState.ASK, PermissionState.GRANTED}:
                message = 'Microphone input is unavailable under the existing permission policy: ' + permission.value
                if self.wake_controller.active:
                    from .wake import WakeState
                    self.wake_controller.set_state(WakeState.ERROR, message, 2)
                else: self._show_notification(message, 'error')
                return None
        handle = super()._begin_voice_listening()
        if handle is not None and getattr(self, '_renovated_ready', False) and self.wake_controller.active:
            self.wake_controller.stt_request_id = handle.request_id
        return handle

    def _on_speech_partial(self, text):
        if getattr(self, '_renovated_ready', False) and self.wake_controller.active:
            if not (self._barge_in_monitoring and self._is_likely_voice_echo(text)):
                if self._barge_in_monitoring:
                    from .wake import WakeState
                    self.wake_controller.set_state(WakeState.LISTENING, 'Listening…', self.wake_controller.preferences.command_timeout)
                self.wake_controller.partial(text)
        super()._on_speech_partial(text)

    def _on_speech_transcript(self, payload):
        if getattr(self, '_renovated_ready', False) and self.wake_controller.active:
            if getattr(payload, 'request_id', '') != self.wake_controller.stt_request_id: return
            text = getattr(payload, 'text', '')
            if (self._barge_in_monitoring or self._barge_in_interrupted) and text:
                if self._is_likely_voice_echo(text): return
                self.runtime.voice.interrupt('wake-barge-in'); self.runtime.realtime.cancel_active('wake-barge-in'); self.runtime.live_vision.cancel('wake-barge-in')
                self._barge_in_monitoring = self._barge_in_interrupted = False
            if self.wake_controller.transcript(payload): return
        super()._on_speech_transcript(payload)

    def _on_speech_playback_finished(self, result):
        if getattr(self, '_renovated_ready', False) and self.wake_controller.playback_finished(result): return
        super()._on_speech_playback_finished(result)

    def _voice_trace_callback(self, request):
        trace = ExistingPresenter._voice_trace_callback(request)
        def event(name, metadata):
            if trace: trace(name, metadata)
            if not self._is_closing:
                try: self.voice_output_event.emit(name, metadata)
                except RuntimeError: pass
        return event

    def _speak_assistant_text(self, text, *, request_id=None):
        if getattr(self, '_renovated_ready', False) and not self.runtime.voice.config.enabled: return None
        handle = super()._speak_assistant_text(text, request_id=request_id)
        if getattr(self, '_renovated_ready', False) and self.wake_controller.active and handle is not None:
            self.wake_controller.tts_request_id = handle.request_id
        return handle

    def _append_direct_reply(self, user_input, reply, *, address=True):
        result = super()._append_direct_reply(user_input, reply, address=address)
        if getattr(self, '_renovated_ready', False) and self.wake_controller.active:
            self.wake_controller.result(reply)
        return result

    def _finish_response_delivery(self, author, message, is_user, **kwargs):
        result = super()._finish_response_delivery(author, message, is_user, **kwargs)
        if getattr(self, '_renovated_ready', False) and self.wake_controller.active and not is_user:
            self.wake_controller.result(message)
        return result

    def _runtime_event(self, event):
        kind = event['type']
        if kind in {'media_started'}: self.effect_policy.set_load('MEDIA_GENERATING', source='media-events')
        elif kind in {'media_completed', 'media_failed', 'media_cancelled'}:
            busy = any(claim.resource == 'GPU' for lease in self.runtime.kernel.resources.snapshot().values() for claim in lease)
            self.effect_policy.set_load('MEDIA_GENERATING' if 'media_started' in self.core_presentation.media.values() else 'NORMAL', source='media-events')
            self.effect_policy.set_load('GPU_BUSY' if busy else 'NORMAL', source='leases')

    def _core_changed(self, snapshot):
        self.status_line.setText(snapshot.title + ' · ' + snapshot.detail)

    def _refresh_top_bar_status(self, sample=None):
        super()._refresh_top_bar_status(sample)
        if not getattr(self, '_renovated_ready', False): return
        busy = any(claim.resource == 'GPU' for lease in self.runtime.kernel.resources.snapshot().values() for claim in lease)
        self.effect_policy.set_load('GPU_BUSY' if busy else 'NORMAL', source='leases')
        if sample is not None:
            used = getattr(sample, 'vram_used_mb', None); total = getattr(sample, 'vram_total_mb', None); gpu = getattr(sample, 'gpu_percent', None)
            pressure = used is not None and total and used / total >= .9
            self.effect_policy.set_load('VRAM_PRESSURE' if pressure else 'GPU_BUSY' if gpu is not None and gpu >= 85 else 'NORMAL', source='metrics')
            import psutil
            try: battery = psutil.sensors_battery()
            except (OSError, psutil.Error): battery = None
            self.effect_policy.set_load('POWER_SAVING' if battery is not None and not battery.power_plugged else 'NORMAL', source='power')
        self.core_presentation.sample()

    def changeEvent(self, event):
        super().changeEvent(event)
        if getattr(self, '_renovated_ready', False):
            from PySide6.QtCore import QEvent
            if event.type() in (QEvent.ActivationChange, QEvent.WindowStateChange):
                if self.isActiveWindow() and not self._is_closing:
                    self.runtime.pc_browser.activate_window_bridge(self)
                self.effect_policy.set_load('NORMAL' if self.isActiveWindow() and not self.isMinimized() else 'UNFOCUSED', source='focus'); self.effect_clock.request()

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, '_renovated_ready', False) and hasattr(self, 'cursor_lighting'):
            self.cursor_lighting.set_targets(); self.core_presentation.sample(); self.effect_clock.request()

    def eventFilter(self, source, event):
        if getattr(self, '_renovated_ready', False) and source is self:
            from PySide6.QtCore import QEvent
            if event.type() in (QEvent.WindowActivate, QEvent.WindowDeactivate):
                self.effect_policy.set_load('NORMAL' if event.type() == QEvent.WindowActivate else 'UNFOCUSED', source='focus'); self.effect_clock.request()
        if getattr(self, '_renovated_ready', False) and source is self.header:
            from PySide6.QtCore import QEvent
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                handle = self.windowHandle()
                if handle: handle.startSystemMove()
            elif event.type() == QEvent.MouseButtonDblClick:
                self._toggle_renovated_maximize(); return True
        return super().eventFilter(source, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, '_renovated_ready', False): self._size_renovated_composer()
        if getattr(self, '_renovated_ready', False) and self.width() < 1020 and self.navigation.expanded:
            self.navigation.set_expanded(False)
        if hasattr(self, 'material_backdrop'): self.material_backdrop.resize(self.size()); self.material_backdrop.lower()
        if hasattr(self, 'cursor_lighting'): self.cursor_lighting.resize(self.size()); self.cursor_lighting.raise_()
        if getattr(self, '_renovated_ready', False) and hasattr(self, 'notification_toast'):
            self.notification_toast.move(max(12, self.width()-self.notification_toast.width()-24), self.header.geometry().bottom()+12)

    def _size_renovated_composer(self):
        rail = (220 if self.navigation.expanded else 72) if self.navigation.isVisible() else 0
        available = self.width() - rail - 72
        self.composer.setFixedWidth(min(780, max(300, available)))
        self._fit_renovated_composer()

    @Slot()
    def _fit_renovated_composer(self, *_):
        from shiboken6 import isValid
        if not isValid(self): return
        if not hasattr(self, 'composer') or getattr(self, '_fitting_composer', False): return
        self._fitting_composer = True
        try:
            layout = self.composer.layout(); layout.invalidate(); layout.activate()
            height = layout.minimumSize().height()
            if self.composer.height() != height: self.composer.setFixedHeight(height)
        finally: self._fitting_composer = False

    def paintEvent(self, event):
        if getattr(self, '_renovated_ready', False):
            painter = QPainter(self); painter.fillRect(event.rect(), QColor(self.theme_engine.tokens['background'])); painter.end()
        else: super().paintEvent(event)

    def open_premium_settings(self):
        if not getattr(self, '_renovated_ready', False): return super().open_premium_settings()
        self.navigate('settings')

    def closeEvent(self, event):
        if getattr(self, '_renovated_ready', False):
            self.wake_controller.close()
            self.core_presentation.close(); self.action_deck.dispose()
            for view in set(self.routes.values()):
                if hasattr(view, 'dispose'): view.dispose()
            self.cursor_lighting.close()
            self.material_backdrop.close()
            self.renderer_clocks.close()
            self.icon_binder.close()
            self.ui_bridge.close(); self.effect_clock.close(); self.motion_director.stop_all()
        return super().closeEvent(event)
