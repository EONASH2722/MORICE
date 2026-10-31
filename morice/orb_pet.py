"""Transparent desktop presentation of MORICE's production holographic globe."""
from __future__ import annotations
import math,time,json
from pathlib import Path
from PySide6.QtCore import QObject,Signal,Qt
from PySide6.QtWidgets import QVBoxLayout,QMenu,QWidget,QPushButton,QCheckBox,QLabel
from .desktop_pet import PetOverlayWindow,_virtual_available_geometry
from .wake_runtime import app_session_path
from .ui_next.core_state import CoreSnapshot,CoreState,LABELS
from .ui_next.themes import ThemeEngine
from .ui_next.motion import EffectPolicy,EffectClock
from .ui_next.globe_state import GlobeBoot
from .ui_next.globe_renderer import HolographicGlobe
from .ui_next.globe_colors import choose_globe_color
from .media_lab.storage import atomic_json

def appearance_directory():return app_session_path().parent/'orb-pet'

class OrbPresentation(QObject):
    changed=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.snapshot=CoreSnapshot();self.received=0.
    def present(self,value):
        try:
            state=CoreState(value['state']);level=float(value.get('level',0.))
            if not math.isfinite(level):return False
        except (KeyError,ValueError,TypeError):return False
        self.received=time.monotonic();self.snapshot=CoreSnapshot(state=state,title=LABELS[state][0],detail=LABELS[state][1],audio_level=max(0.,min(1.,level)))
        self.changed.emit(self.snapshot);return True
    def sample(self):
        if self.snapshot.state!=CoreState.IDLE and time.monotonic()-self.received>2.:
            self.snapshot=CoreSnapshot();self.changed.emit(self.snapshot)

class OrbPetWindow(PetOverlayWindow):
    _SIZE_PIXELS={'small':160,'medium':230,'large':320}
    def __init__(self,definition,**options):
        super().__init__(definition,**options)
        self.theme=ThemeEngine(appearance_directory());self.policy=EffectPolicy(self.theme);self.clock=EffectClock(self.policy,self)
        self.model=OrbPresentation(self)
        self.canvas=HolographicGlobe(self.model,self.theme,self.policy,self.clock,self,
            boot=GlobeBoot(ready=True,skipped=True),transparent_pet=True)
        self.canvas.setAttribute(Qt.WA_TransparentForMouseEvents);self.canvas.setFocusPolicy(Qt.NoFocus)
        self.canvas._center=self.canvas._center_target=(.5,.5)
        self.canvas.setToolTip('Drag to move Orb · Move the pointer to interact · Right-click for colors')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.addWidget(self.canvas)
        self.setWindowTitle('MORICE Orb');self.setAccessibleName('Orb desktop pet')
        from .ui_next.cursors import VisibleCursors
        self.visible_cursors=VisibleCursors(self)
        self.set_animation_speed(options.get('animation_speed','normal'))

    def configure_size(self,size):
        super().configure_size(size)
        self.clearMask() # Per-pixel DWM alpha preserves the glow and wallpaper gaps.

    def start(self):
        saved=appearance_directory()/'position.json'
        try:
            if saved.stat().st_size<1024:
                value=json.loads(saved.read_text());self.move(int(value['x']),int(value['y']))
        except (OSError,ValueError,KeyError,TypeError,OverflowError):pass
        if self.pos().isNull():
            area=_virtual_available_geometry();self.move(area.right()-self.width()-60,area.center().y()-self.height()//2)
        self._clamp_to_visible_desktop();self._suspended=False;self.show();self.clock.request()

    def reload_style(self):
        speed=self.theme.profile.motion_speed
        self.theme.apply_profile(self.theme.store.load(),persist=False);self.theme.update(motion_speed=speed,persist=False);self.clock.request()

    def set_animation_speed(self,speed):
        super().set_animation_speed(speed)
        if hasattr(self,'theme'):self.theme.update(motion_speed={'slow':.6,'normal':1.,'fast':1.6}.get(str(speed),1.),persist=False)

    def set_suspended(self,suspended):
        if bool(suspended)==self._suspended:return
        self._suspended=bool(suspended)
        if suspended:self.hide()
        else:self.show();self.clock.request()

    def mouseMoveEvent(self,event):
        if self.interaction_enabled:
            self.canvas.dynamics.move(*self.canvas._coords(event.position()))
            self.clock.request();self.canvas.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self,event):
        if self.interaction_enabled:self.canvas.dynamics.move(*self.canvas._coords(event.position()))
        super().mousePressEvent(event)

    def leaveEvent(self,event):
        self.canvas.dynamics.pointer=(4.,4.);self.clock.request();super().leaveEvent(event)

    def mouseReleaseEvent(self,event):
        was_drag=self._drag_started
        super().mouseReleaseEvent(event)
        if was_drag:atomic_json(appearance_directory()/'position.json',{'x':self.x(),'y':self.y()})

    def trigger_click_feedback(self):
        if not self.interaction_enabled:return
        self.canvas.dynamics.click(*self.canvas.dynamics.pointer);self.clock.request();self.canvas.update()

    def contextMenuEvent(self,event):
        menu=QMenu(self)
        for label,key in (('Orb color…','globe_color'),('Glow color…','globe_glow_color')):
            menu.addAction(label,lambda k=key:choose_globe_color(self.theme,k,self))
        menu.addSeparator();menu.addAction('Open MORICE',lambda:self.activated.emit('open_morice'))
        menu.setAttribute(Qt.WA_DeleteOnClose);menu.popup(event.globalPos())

    def present(self,value):self.model.present(value)
    def paintEvent(self,event):pass # Child GL canvas owns every visible pixel.
    def shutdown(self):
        self.visible_cursors.close();self.canvas.dispose();self.clock.close();super().shutdown()

class OrbSettings(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.theme=ThemeEngine(appearance_directory());box=QVBoxLayout(self);box.setContentsMargins(0,0,0,0)
        for label,key in (('Orb color…','globe_color'),('Orb glow color…','globe_glow_color')):
            button=QPushButton(label);button.clicked.connect(lambda checked=False,k=key:self.choose(k));box.addWidget(button)
        self.wake=QCheckBox('Say “MORICE” to start voice\nAllow background microphone')
        self.wake.setChecked(owner.settings.get('orb_voice_wake','false')=='true');self.wake.toggled.connect(self.toggle);box.addWidget(self.wake)
        self.status=QLabel('Orb uses the home globe, transparent gaps and speech-reactive animation. Voice wake is optional and uses the existing microphone permission and local wake listener.')
        self.status.setWordWrap(True);box.addWidget(self.status)
    def choose(self,key):
        self.theme.apply_profile(self.theme.store.load(),persist=False)
        choose_globe_color(self.theme,key,self)
        from .desktop_pet import _send_pet_host_command
        _send_pet_host_command('reload')
    def toggle(self,enabled):
        from .unified_intelligence import PermissionState
        permission=self.owner.runtime.kernel.permissions.controller.state('microphone_access')
        if enabled and permission not in {PermissionState.ASK,PermissionState.GRANTED}:
            self.wake.blockSignals(True);self.wake.setChecked(False);self.wake.blockSignals(False)
            self.status.setText('Microphone access is blocked. Enable it in Permissions before allowing Orb voice wake.');return
        if enabled and permission==PermissionState.ASK:
            self.owner.runtime.kernel.permissions.controller.set_state('microphone_access',PermissionState.GRANTED)
        self.owner.settings['orb_voice_wake']=str(enabled).lower();self.owner._on_pet_settings_changed()
        self.status.setText('Orb voice wake is enabled while Orb is the selected, enabled pet.' if enabled else 'Orb background microphone is off.')
