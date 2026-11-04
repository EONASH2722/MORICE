"""User-initiated freehand geometry and native Windows input ownership.

Hook points and crops are physical pixels. Only overlay painting crosses into
Qt's per-monitor logical coordinate system. No screenshots are taken here.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import math
import os
import threading
import time

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class SelectionGeometry:
    points: tuple[tuple[int, int], ...]
    bounds: tuple[int, int, int, int]  # left, top, right, bottom, exclusive
    area: float


def enclosed_selection(points, monitor, *, minimum=18) -> SelectionGeometry:
    """Reject clicks, scribbles and open arcs; close a small final gap only."""
    clean = []
    for point in points:
        x, y = point
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError('Selection contains an invalid coordinate.')
        p = (round(x), round(y))
        if not clean or math.dist(clean[-1], p) >= 2:
            clean.append(p)
    if len(clean) < 10:
        raise ValueError('Hold the middle button and draw a closed loop.')
    xs, ys = zip(*clean)
    width, height = max(xs)-min(xs), max(ys)-min(ys)
    if min(width, height) < minimum:
        raise ValueError('The selection is too small. Draw around the content.')
    diagonal = math.hypot(width, height)
    if math.dist(clean[0], clean[-1]) > max(20, diagonal * .22):
        raise ValueError('The circle is open. Bring the end closer to the start.')
    closed = clean + [clean[0]]
    area = abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(closed, closed[1:]))) / 2
    if area < max(160, width*height*.15):
        raise ValueError('Draw around an area rather than along a line.')
    ml, mt, mr, mb = monitor
    # Cross-monitor strokes are rejected: never silently capture another display.
    if any(not (ml <= x < mr and mt <= y < mb) for x,y in clean):
        raise ValueError('Keep the circle on one monitor, then try again.')
    bounds = (max(ml,min(xs)-3), max(mt,min(ys)-3),
              min(mr,max(xs)+4), min(mb,max(ys)+4))
    return SelectionGeometry(tuple(closed), bounds, area)


def physical_monitors():
    if os.name != 'nt':
        return []
    user = ctypes.windll.user32
    class Info(ctypes.Structure):
        _fields_ = [('size',wintypes.DWORD),('monitor',wintypes.RECT),
                    ('work',wintypes.RECT),('flags',wintypes.DWORD),('device',wintypes.WCHAR*32)]
    result = []
    user.GetMonitorInfoW.argtypes=[wintypes.HMONITOR,ctypes.POINTER(Info)]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HMONITOR,wintypes.HDC,
                                     ctypes.POINTER(wintypes.RECT),wintypes.LPARAM)
    def visit(handle, _dc, _rect, _data):
        info=Info();info.size=ctypes.sizeof(info)
        if user.GetMonitorInfoW(handle,ctypes.byref(info)):
            r=info.monitor;result.append((info.device,(r.left,r.top,r.right,r.bottom)))
        return True
    callback=callback_type(visit);user.EnumDisplayMonitors(None,None,callback,0)
    return result


def foreground_identity():
    """Cheap status sample, outside hook callbacks; protected windows fail closed."""
    if os.name != 'nt':return '', False
    user=ctypes.windll.user32
    user.GetForegroundWindow.restype=wintypes.HWND
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowDisplayAffinity.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    handle=user.GetForegroundWindow();pid=wintypes.DWORD()
    user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
    name=''
    try:
        import psutil
        name=psutil.Process(pid.value).name().casefold()
    except Exception:pass
    affinity=wintypes.DWORD()
    protected=bool(user.GetWindowDisplayAffinity(handle,ctypes.byref(affinity)) and affinity.value)
    return name, protected or name in {'lockapp.exe','credentialuibroker.exe','keepass.exe','keepassxc.exe','1password.exe','bitwarden.exe'}


class MiddleMouseHook(QObject):
    event = Signal(str, int, int)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.allowed=False;self.running=False;self._thread=None;self._tid=0
        self._held=False;self._drawing=False;self._cancelled=False
        self._origin=(0,0);self._started=0.;self._last=(0,0)
        self._stop_event=threading.Event();self.foreground_hwnd=0

    def start(self):
        if self.running:return
        if os.name != 'nt':self.status.emit('Global circle selection is available on Windows only.');return
        self.running=True
        self._stop_event.clear()
        self._thread=threading.Thread(target=self._run,name='morice-middle-mouse',daemon=True)
        self._thread.start()

    def stop(self):
        self.allowed=False
        self._stop_event.set()
        if self._tid:ctypes.windll.user32.PostThreadMessageW(self._tid,0x0012,0,0)
        if self._thread:self._thread.join(timeout=2)
        if self._thread and self._thread.is_alive():
            self.status.emit('Mouse hook is still shutting down.')
        self._held=False;self._drawing=False

    def _run(self):
        user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self._tid=kernel.GetCurrentThreadId()
        user.GetForegroundWindow.restype=wintypes.HWND
        proc_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_int,ctypes.c_size_t,ctypes.c_ssize_t)
        class Mouse(ctypes.Structure):
            _fields_=[('pt',wintypes.POINT),('data',wintypes.DWORD),('flags',wintypes.DWORD),
                      ('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
        user.SetWindowsHookExW.argtypes=[ctypes.c_int,proc_type,wintypes.HINSTANCE,wintypes.DWORD]
        user.SetWindowsHookExW.restype=ctypes.c_void_p
        user.CallNextHookEx.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_size_t,ctypes.c_ssize_t]
        user.CallNextHookEx.restype=ctypes.c_ssize_t
        user.UnhookWindowsHookEx.argtypes=[ctypes.c_void_p]
        def mouse(code, message, address):
            try:
                if code>=0:
                    value=ctypes.cast(address,ctypes.POINTER(Mouse)).contents
                    x,y=value.pt.x,value.pt.y
                    if value.flags & 1:return user.CallNextHookEx(None,code,message,address)
                    if message==0x207 and self.allowed and (not self.foreground_hwnd or user.GetForegroundWindow()==self.foreground_hwnd):
                        self._held=True;self._drawing=False;self._cancelled=False
                        self._origin=self._last=(x,y);self._started=time.monotonic()
                        self.event.emit('down',x,y);return 1
                    if message==0x200 and self._held and not self._cancelled:
                        if not self.allowed:
                            self._cancelled=True;self.event.emit('cancel',x,y)
                        elif not self._drawing and time.monotonic()-self._started>=.12 and math.dist(self._origin,(x,y))>=12:
                            self._drawing=True;self.event.emit('start',*self._origin)
                        if self._drawing and math.dist(self._last,(x,y))>=2:
                            self._last=(x,y);self.event.emit('move',x,y)
                    if message==0x208 and self._held:
                        self._held=False
                        if self._drawing and not self._cancelled:self.event.emit('up',x,y)
                        elif not self._cancelled:
                            # A brief click retains ordinary middle-click behavior.
                            user.mouse_event(0x20,0,0,0,0);user.mouse_event(0x40,0,0,0,0)
                        self._drawing=False;return 1
            except Exception:
                self._cancelled=True;self.event.emit('cancel',0,0)
            return user.CallNextHookEx(None,code,message,address)
        def keyboard(code,message,address):
            if code>=0 and message in (0x100,0x104) and self._held:
                key=ctypes.cast(address,ctypes.POINTER(wintypes.DWORD)).contents.value
                if key==27:
                    self._cancelled=True;self.event.emit('cancel',0,0);return 1
            return user.CallNextHookEx(None,code,message,address)
        callbacks=[proc_type(mouse),proc_type(keyboard)];handles=[]
        try:
            # Force creation of the thread message queue before exposing readiness.
            message=wintypes.MSG();user.PeekMessageW(ctypes.byref(message),None,0,0,0)
            handles=[user.SetWindowsHookExW(14,callbacks[0],None,0),user.SetWindowsHookExW(13,callbacks[1],None,0)]
            if not all(handles):
                raise ctypes.WinError(ctypes.get_last_error())
            self.status.emit('Middle-mouse circle selection is ready.')
            while not self._stop_event.is_set() and user.GetMessageW(ctypes.byref(message),None,0,0)>0:
                user.TranslateMessage(ctypes.byref(message));user.DispatchMessageW(ctypes.byref(message))
        except Exception as exc:self.status.emit('Global input hook unavailable: '+str(exc))
        finally:
            for handle in handles:
                if handle:user.UnhookWindowsHookEx(handle)
            self._tid=0;self.running=False
