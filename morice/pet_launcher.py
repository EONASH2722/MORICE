"""Deterministic MORICE activation and single-instance coordination.

Desktop companions use this module directly.  No model, agent, network, or
voice service participates in opening the application.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QLockFile, QRect, QTimer, Qt, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QWidget

from .wake_runtime import app_session_active, app_session_path


INSTANCE_SERVER_NAME = "EONASH2722.MORICE.UI.v1"
INSTANCE_LOCK_FILENAME = "morice-ui-instance.lock"
OPEN_MORICE = "open_morice"
OPEN_CHAT = "open_chat"
DO_NOTHING = "nothing"
VALID_OPEN_ACTIONS = frozenset({OPEN_MORICE, OPEN_CHAT})


def normalize_open_action(value: object) -> str:
    text = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "open": OPEN_MORICE,
        "morice": OPEN_MORICE,
        "open_morice": OPEN_MORICE,
        "chat": OPEN_CHAT,
        "open_morice_chat": OPEN_CHAT,
        "open_chat": OPEN_CHAT,
        "none": DO_NOTHING,
        "off": DO_NOTHING,
        "do_nothing": DO_NOTHING,
        "nothing": DO_NOTHING,
    }
    return aliases.get(text, OPEN_MORICE)


def _instance_lock_path() -> str:
    return str(app_session_path().with_name(INSTANCE_LOCK_FILENAME))


def _send_instance_command(
    action: str,
    *,
    server_name: str = INSTANCE_SERVER_NAME,
    timeout_ms: int = 180,
) -> bool:
    """Send an activation command to an already-running MORICE UI."""

    clean_action = normalize_open_action(action)
    if clean_action not in VALID_OPEN_ACTIONS:
        return False
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if not socket.waitForConnected(max(1, int(timeout_ms))):
        socket.abort()
        return False
    socket.write((clean_action + "\n").encode("ascii"))
    socket.flush()
    delivered = socket.waitForBytesWritten(max(1, int(timeout_ms)))
    socket.disconnectFromServer()
    return bool(delivered)


def request_existing_instance(
    action: str = OPEN_MORICE,
    *,
    attempts: int = 1,
    timeout_ms: int = 180,
) -> bool:
    """Ask the primary UI process to show itself, with a bounded startup retry."""

    for attempt in range(max(1, int(attempts))):
        if _send_instance_command(action, timeout_ms=timeout_ms):
            return True
        if attempt + 1 < attempts:
            time.sleep(0.04)
    return False


class SingleInstanceController(QObject):
    """Own a per-user lock and receive activation requests from later launches."""

    activation_requested = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        Path(_instance_lock_path()).parent.mkdir(parents=True, exist_ok=True)
        self._lock = QLockFile(_instance_lock_path())
        # PID-aware stale lock detection is safer than an arbitrary timeout.
        self._lock.setStaleLockTime(0)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept_connections)
        self._clients: set[QLocalSocket] = set()
        self._pending_actions: list[str] = []
        self._primary = False

    @property
    def is_primary(self) -> bool:
        return self._primary

    def acquire_or_notify(self, action: str = OPEN_MORICE) -> bool:
        """Return True only for the process allowed to construct the main UI."""

        if not self._lock.tryLock(0):
            # The primary may still be constructing QApplication/server.  The
            # lock alone is sufficient to prevent a duplicate heavy runtime.
            request_existing_instance(action, attempts=12, timeout_ms=90)
            return False

        QLocalServer.removeServer(INSTANCE_SERVER_NAME)
        if not self._server.listen(INSTANCE_SERVER_NAME):
            self._lock.unlock()
            request_existing_instance(action, attempts=4, timeout_ms=100)
            return False
        self._primary = True
        return True

    def close(self) -> None:
        if self._server.isListening():
            self._server.close()
            QLocalServer.removeServer(INSTANCE_SERVER_NAME)
        for client in tuple(self._clients):
            client.abort()
        self._clients.clear()
        if self._primary:
            self._lock.unlock()
            self._primary = False

    def take_pending_actions(self) -> list[str]:
        actions = list(self._pending_actions)
        self._pending_actions.clear()
        return actions

    def _accept_connections(self) -> None:
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is None:
                continue
            self._clients.add(client)
            client.readyRead.connect(lambda client=client: self._read_client(client))
            client.disconnected.connect(lambda client=client: self._drop_client(client))
            if client.bytesAvailable():
                self._read_client(client)

    def _read_client(self, client: QLocalSocket) -> None:
        payload = bytes(client.readAll()).decode("utf-8", errors="ignore")
        for line in payload.splitlines():
            action = normalize_open_action(line)
            if action in VALID_OPEN_ACTIONS:
                self._pending_actions.append(action)
                self.activation_requested.emit(action)
                break
        client.disconnectFromServer()

    def _drop_client(self, client: QLocalSocket) -> None:
        self._clients.discard(client)
        client.deleteLater()


def repaired_window_geometry(
    window_rect: tuple[int, int, int, int],
    available_rects: list[tuple[int, int, int, int]],
    *,
    margin: int = 32,
) -> tuple[int, int, int, int]:
    """Keep a saved window location, relocating only when its monitor vanished."""

    x, y, width, height = (int(value) for value in window_rect)
    width = max(1, width)
    height = max(1, height)
    if not available_rects:
        return x, y, width, height

    for sx, sy, sw, sh in available_rects:
        intersection_width = max(0, min(x + width, sx + sw) - max(x, sx))
        intersection_height = max(0, min(y + height, sy + sh) - max(y, sy))
        if intersection_width >= min(64, width) and intersection_height >= min(64, height):
            return x, y, width, height

    sx, sy, sw, sh = available_rects[0]
    width = min(width, max(1, sw))
    height = min(height, max(1, sh))
    x = max(sx, min(sx + sw - width, sx + margin))
    y = max(sy, min(sy + sh - height, sy + margin))
    return x, y, width, height


def _repair_qt_window_geometry(window: QWidget) -> None:
    screens = QApplication.screens()
    if not screens:
        return
    geometry = window.frameGeometry()
    available = [screen.availableGeometry() for screen in screens]
    repaired = repaired_window_geometry(
        (geometry.x(), geometry.y(), geometry.width(), geometry.height()),
        [(item.x(), item.y(), item.width(), item.height()) for item in available],
    )
    if repaired != (geometry.x(), geometry.y(), geometry.width(), geometry.height()):
        window.setGeometry(QRect(*repaired))


def _native_restore_window(hwnd: int) -> bool:
    if os.name != "nt" or hwnd <= 0:
        return False
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.SetActiveWindow.argtypes = [ctypes.c_void_p]
        user32.AttachThreadInput.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_bool]
        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)  # SW_RESTORE
        user32.BringWindowToTop(ctypes.c_void_p(hwnd))

        foreground = int(user32.GetForegroundWindow() or 0)
        current_thread = int(kernel32.GetCurrentThreadId())
        foreground_thread = (
            int(user32.GetWindowThreadProcessId(ctypes.c_void_p(foreground), None))
            if foreground
            else 0
        )
        attached = False
        if foreground_thread and foreground_thread != current_thread:
            attached = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))
        try:
            user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
            user32.SetActiveWindow(ctypes.c_void_p(hwnd))
        finally:
            if attached:
                user32.AttachThreadInput(current_thread, foreground_thread, False)
        return True
    except (AttributeError, OSError, ValueError):
        return False


def restore_morice_window(window: QWidget, action: str = OPEN_MORICE) -> None:
    """Restore, raise, and focus the existing main window in-place."""

    clean_action = normalize_open_action(action)
    if clean_action == DO_NOTHING:
        return
    window.setAttribute(Qt.WA_ShowWithoutActivating, False)
    _repair_qt_window_geometry(window)
    if window.isMinimized():
        window.showNormal()
    elif not window.isVisible():
        window.show()
    else:
        window.show()
    window.raise_()
    window.activateWindow()
    _native_restore_window(int(window.winId()))

    if clean_action == OPEN_CHAT:
        input_widget = getattr(window, "input", None)
        if input_widget is not None:
            input_widget.setFocus()

    # Qt sometimes receives the activation before Windows finishes restoring
    # a minimized window.  One queued repeat makes the direct user action feel
    # immediate without leaving the window topmost.
    QTimer.singleShot(0, lambda: (window.raise_(), window.activateWindow()))


def _read_session_pid() -> int:
    try:
        payload = json.loads(app_session_path().read_text(encoding="utf-8"))
        return int(payload.get("pid") or 0) if isinstance(payload, dict) else 0
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return 0


def focus_existing_process_window(pid: int = 0) -> bool:
    """Compatibility fallback for an older MORICE process without local IPC."""

    if os.name != "nt":
        return False
    target_pid = int(pid or _read_session_pid())
    if target_pid <= 0:
        return False
    try:
        user32 = ctypes.windll.user32
        user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        found: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def visitor(hwnd, _lparam):
            process_id = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if process_id.value != target_pid:
                return True
            length = int(user32.GetWindowTextLengthW(hwnd))
            title = ctypes.create_unicode_buffer(max(1, length + 1))
            user32.GetWindowTextW(hwnd, title, len(title))
            if "MORICE" in title.value.upper():
                found.append(int(hwnd))
                return False
            return True

        user32.EnumWindows(callback_type(visitor), 0)
        return bool(found and _native_restore_window(found[0]))
    except (AttributeError, OSError, ValueError):
        return False


def default_launch_command() -> list[str]:
    explicit = os.getenv("MORICE_APP_EXECUTABLE", "").strip().strip('"')
    if explicit:
        return [explicit]
    if getattr(sys, "frozen", False):
        return [sys.executable]
    root = Path(__file__).resolve().parent.parent
    launcher = root / "morice_app_launcher.py"
    if launcher.is_file():
        return [sys.executable, str(launcher)]
    return [sys.executable, "-m", "morice"]


class MoriceLauncher(QObject):
    """Fast, debounced launcher used by an out-of-process pet host."""

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        request: Callable[[str], bool] | None = None,
        session_probe: Callable[[], bool] | None = None,
        launch: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self._request = request or request_existing_instance
        self._session_probe = session_probe or app_session_active
        self._launch = launch or self._spawn
        self._launch_pending = False
        self._pending_action = OPEN_MORICE
        self._poll_deadline = 0.0

    @property
    def launch_pending(self) -> bool:
        return self._launch_pending

    def open(self, action: str = OPEN_MORICE) -> str:
        clean_action = normalize_open_action(action)
        if clean_action == DO_NOTHING:
            return DO_NOTHING
        self._pending_action = clean_action
        if self._request(clean_action):
            self._launch_pending = False
            return "focused"
        if self._session_probe():
            focus_existing_process_window()
            return "focused"
        if self._launch_pending:
            return "pending"

        self._launch_pending = True
        self._poll_deadline = time.monotonic() + 15.0
        try:
            self._launch()
        except (OSError, RuntimeError, ValueError):
            self._launch_pending = False
            return "failed"
        QTimer.singleShot(80, self._poll_for_window)
        return "launched"

    def _spawn(self) -> subprocess.Popen:
        command = default_launch_command()
        return subprocess.Popen(
            command,
            cwd=str(Path(command[0]).resolve().parent) if getattr(sys, "frozen", False) else None,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )

    def _poll_for_window(self) -> None:
        if not self._launch_pending:
            return
        if self._request(self._pending_action):
            self._launch_pending = False
            return
        if time.monotonic() >= self._poll_deadline:
            self._launch_pending = False
            focus_existing_process_window()
            return
        QTimer.singleShot(120, self._poll_for_window)


__all__ = [
    "DO_NOTHING",
    "INSTANCE_SERVER_NAME",
    "MoriceLauncher",
    "OPEN_CHAT",
    "OPEN_MORICE",
    "SingleInstanceController",
    "default_launch_command",
    "focus_existing_process_window",
    "normalize_open_action",
    "repaired_window_geometry",
    "request_existing_instance",
    "restore_morice_window",
]
