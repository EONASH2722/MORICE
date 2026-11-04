"""Resident helper over the one existing MORICE runtime. Screenshots stay in RAM."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import ctypes
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from PySide6.QtCore import QObject, Qt, QTimer, Signal, QPointF, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QCursor, QIcon
from PySide6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu

from .helper_selection import MiddleMouseHook, enclosed_selection, physical_monitors, foreground_identity
from .media_lab.storage import atomic_json
from .unified_intelligence import PermissionState
from .live_vision import VisionFrame, VisionResult
from .ui_next.helper_popup import TopAssistantPopup


@dataclass(frozen=True)
class HelperPreferences:
    enabled: bool=False
    run_after_close: bool=True
    start_with_windows: bool=False
    wake_enabled: bool=False
    wake_paused: bool=False
    circle_enabled: bool=False
    circle_paused: bool=False
    auto_explain: bool=False
    popup_seconds: int=10
    auto_hide: bool=True
    animation: bool=True
    reduced_motion: bool=False
    pause_fullscreen: bool=True
    screen_capture: bool=False
    excluded_apps: str='blender.exe; acad.exe; fusion360.exe'
    popup_material: str='glass'

    def __post_init__(self):
        for key,value in asdict(self).items():
            if key not in {'popup_seconds','excluded_apps','popup_material'} and type(value) is not bool:
                raise ValueError('Helper switches must be boolean.')
        if type(self.popup_seconds) is not int or not 3<=self.popup_seconds<=120:
            raise ValueError('Popup duration must be between 3 and 120 seconds.')
        if not isinstance(self.excluded_apps,str) or len(self.excluded_apps)>2000:
            raise ValueError('Application exclusion list is too long.')
        if self.popup_material not in {'dark','glass'}:raise ValueError('Unknown popup material.')


class SelectionOverlay(QWidget):
    def __init__(self):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.WindowTransparentForInput)
        self.setWindowTitle('MORICE Freehand Selection');self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating);self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_QuitOnClose,False);self.points=[];self.color='#b68bf5'
        self.physical=(0,0,1,1);self.opacity=1.
        self.fade=QVariantAnimation(self);self.fade.setDuration(130);self.fade.setStartValue(1.);self.fade.setEndValue(0.)
        self.fade.valueChanged.connect(self._opacity);self.fade.finished.connect(self.hide)

    def _opacity(self,value):self.opacity=float(value);self.update()

    def begin(self,screen,physical,color):
        self.fade.stop();self.opacity=1.;self.points=[];self.physical=physical;self.color=color
        self.setGeometry(screen.geometry());self.show()
        # Defense in depth. Capture also waits until this window is hidden.
        if os.name=='nt':
            user=ctypes.windll.user32
            user.SetWindowDisplayAffinity.argtypes=[ctypes.c_void_p,ctypes.c_uint]
            user.SetWindowDisplayAffinity(int(self.winId()),0x11)

    def add(self,x,y):
        l,t,r,b=self.physical
        self.points.append(QPointF((x-l)*self.width()/(r-l),(y-t)*self.height()/(b-t)))
        if len(self.points)>8192:self.points=self.points[::2]
        self.update()

    def paintEvent(self,event):
        if len(self.points)<2:return
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);painter.setOpacity(self.opacity)
        path=QPainterPath(self.points[0])
        for a,b in zip(self.points[1:],self.points[2:]):path.quadTo(a,(a+b)/2)
        path.lineTo(self.points[-1]);color=QColor(self.color)
        for width,alpha in ((9,25),(5,60),(2,245)):
            color.setAlpha(alpha);painter.setPen(QPen(color,width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));painter.drawPath(path)
        painter.end()


class BackgroundHelper(QObject):
    changed=Signal()

    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.runtime=owner.runtime
        self.path=self.runtime.directory/'renovation/background-helper.json'
        self.preference_error=''
        try:
            self.preferences=HelperPreferences(**json.loads(self.path.read_text())) if self.path.exists() and self.path.stat().st_size<12000 else HelperPreferences()
        except (OSError,ValueError,TypeError) as exc:
            self.preferences=HelperPreferences();self.preference_error=str(exc)
        self.popup=TopAssistantPopup();self.overlay=SelectionOverlay();self.hook=MiddleMouseHook(self)
        self.hook.event.connect(self._gesture,Qt.QueuedConnection);self.hook.status.connect(self._status,Qt.QueuedConnection)
        self.session=False;self.selection=None;self.mask=None;self._epoch=0;self._vision_cancel=threading.Event()
        self._legacy_overlay=owner.wake_controller.overlay;self._listener=None;self._closed=False;self._quitting=False
        self._points=[];self._monitor=None;self._capture_pending=False;self._last_tick=time.monotonic();self._listener_retry=0.
        self._owned_nlui_token=None;self._has_request=False
        self._paused=False
        self.response_serial=0
        self.last_vision_success=None
        self.status='Ready';self.benchmarks={};self.captures=0
        self.popup.cancelled.connect(self.cancel);self.popup.reviewed_command.connect(owner.wake_controller.submit_reviewed)
        self.popup.submitted.connect(self.submit);self.popup.microphone.connect(self.listen);self.popup.open_main.connect(self.open_main)
        self.popup.dismissed.connect(self._dismissed)
        self.popup.pause_requested.connect(self.pause_interaction)
        owner.voice_output_event.connect(self.voice_event,Qt.QueuedConnection)
        owner.wake_controller.changed.connect(self.voice_state)
        self.tray=QSystemTrayIcon(owner.windowIcon(),self);self.tray.setToolTip('MORICE · Background Helper')
        menu=QMenu();menu.addAction('Open MORICE',self.open_main)
        self.enabled_action=menu.addAction('Background Helper: Off',lambda:self.update(enabled=not self.preferences.enabled))
        self.wake_action=menu.addAction('Pause Wake Listening',lambda:self.update(wake_paused=not self.preferences.wake_paused))
        self.circle_action=menu.addAction('Pause Circle Selection',lambda:self.update(circle_paused=not self.preferences.circle_paused))
        menu.addAction('Settings',lambda:owner._select_settings_category('Background Helper'))
        menu.addSeparator();menu.addAction('Quit MORICE',self.quit);self.tray.setContextMenu(menu);self._menu=menu
        self.tray.activated.connect(lambda reason:self.open_main() if reason==QSystemTrayIcon.DoubleClick else None)
        self.idle=QTimer(self);self.idle.setSingleShot(True);self.idle.timeout.connect(self.cancel)
        self.capture_timer=QTimer(self);self.capture_timer.setSingleShot(True);self.capture_timer.timeout.connect(self._capture)
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self._tick)
        QApplication.instance().aboutToQuit.connect(self.shutdown)
        self.apply()

    def _status(self,message):self.status=str(message);self.changed.emit()

    def engaged(self,window):return self.session and self.owner is window

    def update(self,**changes):
        previous=self.preferences;self.preferences=replace(previous,**changes)
        if 'wake_enabled' in changes and changes['wake_enabled']:
            permission=self.runtime.kernel.permissions.controller.state('microphone_access')
            if permission==PermissionState.ASK:
                self.runtime.kernel.permissions.controller.set_state('microphone_access',PermissionState.GRANTED)
        try:
            if previous.start_with_windows!=self.preferences.start_with_windows:self._startup()
            atomic_json(self.path,asdict(self.preferences))
        except OSError as exc:
            self.preferences=previous;self._status('Could not save helper settings: '+str(exc));return
        self.apply();self.changed.emit()

    def apply(self):
        if self._closed:return
        p=self.preferences
        self.popup.animate=p.animation and not (p.reduced_motion or self.owner.theme_engine.profile.reduced_motion)
        self.popup.configure_material(p.popup_material)
        self.popup.orb.reload(p.reduced_motion or self.owner.theme_engine.profile.reduced_motion)
        self.enabled_action.setText('Background Helper: '+('On' if p.enabled else 'Off'))
        self.wake_action.setText('Resume Wake Listening' if p.wake_paused else 'Pause Wake Listening')
        self.circle_action.setText('Resume Circle Selection' if p.circle_paused else 'Pause Circle Selection')
        if p.enabled:
            if QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
            QApplication.instance().setQuitOnLastWindowClosed(False)
            self.timer.start();self._tick()
        else:
            self.timer.stop();self.hook.stop();self._stop_listener();self.cancel();self.tray.hide()
            if getattr(self.owner,'_renovated_ready',False) and not self.owner.isVisible():self.open_main()
            QApplication.instance().setQuitOnLastWindowClosed(True)
        # The pet retains its own opt-in setting, but yields wake ownership.
        if hasattr(self.owner,'pet_manager'):
            self.owner.pet_manager.settings['background_helper_enabled']=str(p.enabled).lower()
            self.owner.pet_manager.configure(self.owner.pet_manager.settings)

    def _startup(self):
        if os.name!='nt':raise OSError('Windows startup is available on Windows only.')
        import winreg
        command=[sys.executable,'--morice-background'] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve().parents[1]/'morice_app_launcher.py'),'--morice-background']
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            if self.preferences.start_with_windows:winreg.SetValueEx(key,'MORICE Background Helper',0,winreg.REG_SZ,subprocess.list2cmdline(command))
            else:
                try:winreg.DeleteValue(key,'MORICE Background Helper')
                except FileNotFoundError:pass

    def _tick(self):
        if self._closed:return
        now=time.monotonic()
        if now-self._last_tick>15:
            self.cancel();self.hook.stop();self._stop_listener()
        self._last_tick=now;p=self.preferences
        from .desktop_pet import foreground_is_fullscreen
        fullscreen=p.pause_fullscreen and foreground_is_fullscreen(ignored_hwnds=self._visible_handles())
        if fullscreen:
            if self.session:self.cancel()
            self._cancel_selection()
        name,protected=foreground_identity()
        if os.name=='nt':
            ctypes.windll.user32.GetForegroundWindow.restype=ctypes.c_void_p
            self.hook.foreground_hwnd=ctypes.windll.user32.GetForegroundWindow()
        excluded=name in {s.strip().casefold() for s in p.excluded_apps.replace(',',';').split(';') if s.strip()}
        wanted=p.enabled and p.circle_enabled and not p.circle_paused
        self.hook.allowed=wanted and p.screen_capture and not fullscreen and not excluded and not protected and not self._capture_pending
        if wanted and not self.hook.running:self.hook.start()
        elif not wanted and self.hook.running:self.hook.stop();self._cancel_selection()
        permission=self.runtime.kernel.permissions.controller.state('microphone_access')
        wake=p.enabled and p.wake_enabled and not p.wake_paused and not fullscreen and not self.session and permission==PermissionState.GRANTED
        if wake:
            if (self._listener is None or self._listener.poll() is not None) and now>=self._listener_retry:self._start_listener()
        else:self._stop_listener()
        if self.session and self.selection is not None and not self._screen_allowed():self.cancel()

    def _start_listener(self):
        from .desktop_pet import default_pet_host_command
        self.owner.pet_manager.settings['background_helper_enabled']='true'
        command=default_pet_host_command();command[-1]='--morice-wake-listener'
        env={**os.environ,'MORICE_ENABLE_ALWAYS_ON_WAKE':'1','MORICE_HELPER_PREFS':str(self.path),'MORICE_HELPER_OWNER_PID':str(os.getpid())}
        env.pop('MORICE_ORB_WAKE_SESSION',None)
        try:
            self._listener=subprocess.Popen(command,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
            self._listener_retry=time.monotonic()+10
        except OSError as exc:self._status('Wake listener could not start: '+str(exc));self._listener_retry=time.monotonic()+10

    def _stop_listener(self):
        if self._listener is None:return
        process=self._listener;self._listener=None
        import psutil
        try:
            children=psutil.Process(process.pid).children(recursive=True)
            for child in children:
                if '--morice-wake-listener' in child.cmdline():child.terminate()
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
            _,alive=psutil.wait_procs(children,timeout=1)
            for child in alive:
                if '--morice-wake-listener' in child.cmdline():child.kill()
        except (psutil.NoSuchProcess,psutil.AccessDenied,OSError):pass

    def should_hide_on_close(self):
        return self.preferences.enabled and self.preferences.run_after_close and not self._closed and not self._quitting and self.tray.isVisible() and QSystemTrayIcon.isSystemTrayAvailable()

    def hide_main(self):
        self.owner._save_workspace_session();self.owner.hide()
        self.tray.setToolTip('MORICE · Running in the background')

    def open_main(self):
        from .pet_launcher import restore_morice_window
        restore_morice_window(self.owner)

    def quit(self):
        self._quitting=True;self.shutdown();self.owner._closing_after_animation=True
        self.owner.close();QTimer.singleShot(0,QApplication.instance().quit)

    def _screen_allowed(self):
        return self.preferences.screen_capture and self.runtime.kernel.permissions.controller.state('screen_access') not in {PermissionState.DENIED,PermissionState.OS_REQUIRED,PermissionState.UNSUPPORTED}

    def activate_voice(self,source='MORICE',*,followup=False):
        if not self.preferences.enabled:return False
        if self.preferences.wake_paused and not followup:return False
        from .desktop_pet import foreground_is_fullscreen
        if self.preferences.pause_fullscreen and foreground_is_fullscreen(ignored_hwnds=self._visible_handles()):return False
        if self.owner.wake_controller.active:return True
        self._stop_listener()
        if not followup:self._clear_selection()
        self._begin_session();self.popup.state_label.setText('Listening…')
        self.owner._orb_voice_wake=False
        return self.owner.wake_controller.activate(source,fullscreen=False)

    def _begin_session(self):
        self._stop_listener()
        if not self.session:self._return_mode=self.owner.chat_mode
        self.idle.stop();self._epoch+=1;self._vision_cancel.set();self._vision_cancel=threading.Event()
        self.session=True;self.owner.wake_controller.overlay=self.popup
        self._paused=False;self.popup.set_paused(False)
        self.popup.animate=self.preferences.animation and not (self.preferences.reduced_motion or self.owner.theme_engine.profile.reduced_motion)
        self.popup.orb.reload(self.preferences.reduced_motion)
        if not self.popup.isVisible():self.popup.reset()
        self.popup.place(screen=QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen());self.popup.show()

    def listen(self):
        if self._paused:self.pause_interaction(False);return
        self.idle.stop()
        if self.owner.wake_controller.active:self.owner._begin_voice_listening()
        else:self.activate_voice('helper microphone',followup=True)

    def submit(self,text):
        if not self.session:return
        self._paused=False;self.popup.set_paused(False)
        self._has_request=True
        self.idle.stop();self._vision_cancel.set();self._vision_cancel=threading.Event()
        self.popup.transcript.setText(text);self.popup.state_label.setText('Thinking…');self.popup.orb.state='WORKING'
        self.popup.interaction('PROCESSING')
        self.owner.awake=True
        if self.owner.chat_mode!='voice':
            # Set the existing mode without opening the main window or starting a second mic.
            self.owner.chat_mode='voice';self.owner._voice_conversation_active=False
        self.owner.input.setText(text);self.owner.on_send()
        self._owned_nlui_token=getattr(self.owner,'_nlui_token',None)

    def stream(self,text,request_id=None):
        if self._paused:return
        active=self.runtime.realtime.active_request
        if request_id and (active is None or active.request_id!=request_id):return
        if self.session:
            self.idle.stop();self.popup.state_label.setText('Responding…');self.popup.response(text,streaming=True)

    def result(self,text):
        if not self.session or self._paused:return
        self.response_serial+=1
        self.popup.state_label.setText('MORICE');self.popup.response(text);self.popup.orb.state='SUCCESS'
        # Sources are actual response links, never invented at capture time.
        import re
        links=re.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)',str(text))
        self.popup.sources.setText('\n'.join(label+': '+url for label,url in links[:4]));self.popup.sources.setVisible(bool(links))
        voice=self.runtime.voice.status()
        if not (voice.active or voice.queued):self.arm_idle()

    def voice_state(self,state):
        if self.session:
            self.popup.interaction({'UNDERSTANDING':'PROCESSING','WORKING':'PROCESSING','IDLE':'RESULT_VISIBLE'}.get(state,state))

    def voice_event(self,event,metadata):
        if not self.session:return
        if event=='playback_started':
            self.idle.stop();self.popup.state_label.setText('Speaking…');self.popup.orb.state='SPEAKING'
            self.popup.interaction('SPEAKING')
            self.popup.orb.level_source=self.runtime.voice.audio_level
        elif event in {'playback_finished','playback_completed','request_finished'}:
            self.popup.orb.level_source=None;self.popup.orb.state='SUCCESS';self.arm_idle()

    def arm_idle(self):
        if self.preferences.auto_hide and not self._paused:self.idle.start(self.preferences.popup_seconds*1000)

    def _visible_handles(self):
        return {int(window.winId()) for window in (self.popup,self.overlay) if window.isVisible()}

    def pause_interaction(self,paused):
        if not self.session:return
        self._paused=bool(paused);self.popup.set_paused(paused)
        if not paused:
            self.activate_voice('helper resumed',followup=True);return
        self.idle.stop();self._epoch+=1;self._vision_cancel.set()
        controller=self.owner.wake_controller
        controller.timeout.stop();controller.speech_progress.stop();controller.active=False
        controller.epoch+=1;controller.stt_request_id='';controller.tts_request_id=''
        if controller.interaction_token is not None:controller.interaction_token.cancel('helper-paused')
        self.owner._stop_voice_mode_io('helper-paused')
        self.runtime.voice.interrupt('helper-paused');self.runtime.realtime.cancel_active('helper-paused')
        if self._owned_nlui_token is not None:self._owned_nlui_token.cancel('helper-paused')
        if self._has_request:self.owner._remove_thinking();self.owner._set_busy(False)
        self.popup.orb.level_source=None;self.popup.orb.state='IDLE'
        self.popup.state_label.setText('Paused');self.popup.interaction('PAUSED')

    def end_voice(self):
        if self.session:self.cancel()

    def cancel(self):
        was_session=self.session
        self.idle.stop();self._epoch+=1;self._vision_cancel.set();self._cancel_selection()
        if self.owner.wake_controller.active:
            # Clear session before cancelling to avoid recursive finish handling.
            self.session=False;self.owner.wake_controller.cancel()
        elif self.session:
            self.session=False;self.runtime.voice.interrupt('helper-dismissed');self.runtime.speech_input.cancel('helper-dismissed')
            self.runtime.realtime.cancel_active('helper-dismissed');self.runtime.live_vision.cancel('helper-dismissed')
        self.owner.wake_controller.overlay=self._legacy_overlay
        if was_session:
            if self._owned_nlui_token is not None and self._owned_nlui_token is getattr(self.owner,'_nlui_token',None):
                self._owned_nlui_token.cancel('Helper dismissed.')
            elif self._has_request and self.owner.is_busy:
                self.owner._remove_thinking();self.owner._set_busy(False)
            self.owner._stop_voice_mode_io('helper-dismissed')
            self.owner.chat_mode=getattr(self,'_return_mode','normal')
            self.owner._pending_live_vision_result=None
        self._owned_nlui_token=None;self._has_request=False
        self._paused=False
        self.popup.dismiss();self._clear_selection()

    def _dismissed(self):
        if not self.session:self.popup.reset()

    def _clear_selection(self):
        self.selection=None;self.mask=None
        if not self.popup._closing:self.popup.set_selection(None)

    def _cancel_selection(self):
        self.capture_timer.stop();self.overlay.fade.stop();self.overlay.hide();self._capture_pending=False;self._points=[]

    def _gesture(self,event,x,y):
        if self._closed:return
        if event=='cancel':self._cancel_selection();return
        if event=='down':
            if not self.hook.allowed:return
            self._cancel_selection()
            self._monitor=next(((name,bounds) for name,bounds in physical_monitors() if bounds[0]<=x<bounds[2] and bounds[1]<=y<bounds[3]),None)
            self._points=[(x,y)];return
        if not self._monitor:return
        if event=='start':
            self.cancel();self._points=[(x,y)]
            screen=next((s for s in QApplication.screens() if s.name().casefold()==self._monitor[0].casefold()),None)
            if screen is None:self._status('The selected monitor could not be mapped safely.');return
            from .orb_pet import appearance_directory
            from .ui_next.themes import ThemeEngine
            accent=ThemeEngine(appearance_directory()).profile.globe_color
            self.overlay.begin(screen,self._monitor[1],accent)
            self.overlay.add(x,y)
        elif event=='move' and self.overlay.isVisible():
            self._points.append((x,y));self.overlay.add(x,y)
            if len(self._points)>8192:self._points=self._points[::2]
        elif event=='up' and self.overlay.isVisible():
            self._points.append((x,y))
            try:self._geometry=enclosed_selection(self._points,self._monitor[1])
            except ValueError as exc:self._status(str(exc));self._cancel_selection();return
            self._capture_pending=True;self.hook.allowed=False
            self.overlay.fade.start();self.capture_timer.start(185)

    def _capture(self):
        self.overlay.hide();self._capture_pending=False
        if not self._screen_allowed():self._status('Screen capture permission is off.');return
        _,protected=foreground_identity()
        if protected:self._status('This protected surface cannot be captured.');return
        start=time.perf_counter()
        try:
            from PIL import ImageGrab,Image,ImageDraw,ImageStat
            geometry=self._geometry
            image=ImageGrab.grab(bbox=geometry.bounds,all_screens=True).convert('RGB')
            if max(ImageStat.Stat(image).extrema[0])==0 and image.getbbox() is None:raise ValueError('The selected surface is protected or empty.')
            l,t,r,b=geometry.bounds;mask=Image.new('L',image.size,0)
            ImageDraw.Draw(mask).polygon([(x-l,y-t) for x,y in geometry.points],fill=255)
            # Keep only the enclosed pixels; the rest of the bounded crop is neutral.
            background=Image.new('RGB',image.size,(24,24,28));background.paste(image,(0,0),mask)
            png=io.BytesIO();background.save(png,'PNG');jpeg=io.BytesIO();background.save(jpeg,'JPEG',quality=93)
            self._begin_session();self.mask=mask
            self.selection=VisionFrame(uuid.uuid4().hex,datetime.now(timezone.utc),time.monotonic_ns(),image.width,image.height,jpeg.getvalue(),camera_id='user-selected-screen-region')
            self.popup.set_selection(png.getvalue());self.popup.state_label.setText('Ask about your selection')
            self.popup.transcript.setText('Type a question or choose Mic.');self.captures+=1
            self.benchmarks['last_capture_ms']=round((time.perf_counter()-start)*1000,2)
            if self.preferences.auto_explain:self.submit('Explain this selection.')
        except Exception as exc:self._status('Could not capture the selection: '+str(exc));self._cancel_selection()

    def prepare_vision(self,prompt):
        pending=self.owner._pending_live_vision_result
        if pending is not None and pending[0]==prompt:
            self.owner._pending_live_vision_result=None;return False,pending[1],(pending[2],pending[3])
        frame=self.selection
        if frame is None:return False,None,None
        if not self._screen_allowed():return False,VisionResult.failure('helper-permission',frame,'screen-denied','Screen capture permission was withdrawn.'),None
        permission=self.runtime.kernel.permissions.controller.state('vision')
        if permission in {PermissionState.DENIED,PermissionState.OS_REQUIRED,PermissionState.UNSUPPORTED}:
            return False,VisionResult.failure('helper-vision-denied',frame,'vision-denied','Vision analysis is disabled by your permission settings.'),None
        epoch=self._epoch;cancel=self._vision_cancel;started=time.perf_counter_ns()
        self.popup.state_label.setText('Reading your selection…');self.popup.orb.state='UNDERSTANDING'
        self.popup.sources.setText('Vision: '+self.runtime.live_vision.provider.name);self.popup.sources.show()
        def analyze():
            # Existing local provider, same model owner/GPU arbitration; no cloud image upload.
            return self.runtime.live_vision.provider.analyze(frame,prompt,cancel_event=cancel,request_id=uuid.uuid4().hex)
        def done(envelope):
            if not self.session or epoch!=self._epoch or cancel.is_set():return
            result=envelope.get('value') if envelope.get('ok') else None
            if not isinstance(result,VisionResult):result=VisionResult.failure('helper-vision-error',frame,'vision-error',str(envelope.get('error') or 'Vision could not analyze the captured region.'))
            self.last_vision_success=result.success
            self.owner._live_vision_started_ns=started;self.owner._on_live_vision_ready(prompt,result)
        self.owner.ui_bridge.submit('helper-selected-vision',analyze,done)
        return True,None,None

    def shutdown(self):
        if self._closed:return
        self._closed=True;self.timer.stop();self.capture_timer.stop();self.idle.stop()
        self.cancel();self.hook.stop();self._stop_listener();self.tray.hide();self.overlay.close();self.popup.dispose()

    def diagnostics(self):
        return {'enabled':self.preferences.enabled,'resident':not self.owner.isVisible(),'popup_visible':self.popup.isVisible(),
            'popup_phase':self.popup.phase,'hook_running':self.hook.running,'wake_pid':self._listener.pid if self._listener and self._listener.poll() is None else None,
            'capture_count':self.captures,'capture_pending':self._capture_pending,'selection_in_memory':self.selection is not None,
            'status':self.status,'benchmarks':dict(self.benchmarks)}
