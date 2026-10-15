"""Read Win32 state through existing windows; no coordinate or title-only actions."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path

from .contracts import Observation, UserInterventionRequired


def process_image(pid):
    if os.name != "nt":
        return ""
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    process = kernel.OpenProcess(0x1000, False, int(pid))
    if not process:
        return ""
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel.QueryFullProcessImageNameW(ctypes.c_void_p(process), 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel.CloseHandle(ctypes.c_void_p(process))


def process_family(root_pid):
    """Include owned launcher children (notably Windows Python venv redirectors)."""
    family = {int(root_pid)}
    if os.name != "nt":
        return family
    class Entry(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
            ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
            ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong), ("name", ctypes.c_wchar * 260)]
    kernel = ctypes.windll.kernel32
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot in {None, ctypes.c_void_p(-1).value}:
        return family
    parents = {}
    try:
        entry = Entry(); entry.size = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        while more and len(parents) < 32768:
            parents[int(entry.pid)] = int(entry.parent)
            more = kernel.Process32NextW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
    finally:
        kernel.CloseHandle(ctypes.c_void_p(snapshot))
    for unused in range(8):
        children = {pid for pid, parent in parents.items() if parent in family}
        if children <= family:
            break
        family.update(children)
    return family


def window_values(manager):
    from dataclasses import asdict, is_dataclass
    result = []
    for window in manager.list_windows():
        value = asdict(window) if is_dataclass(window) else dict(window)
        value["image"] = value.get("image") or process_image(value.get("pid", 0))
        if os.name == "nt":
            hwnd = ctypes.c_void_p(int(value["handle"]))
            native = ctypes.windll.user32
            value["enabled"] = bool(native.IsWindowEnabled(hwnd))
            value["dpi"] = int(native.GetDpiForWindow(hwnd)) if hasattr(native, "GetDpiForWindow") else 96
            monitor = native.MonitorFromWindow
            monitor.restype = ctypes.c_void_p
            value["monitor_id"] = int(monitor(hwnd, 2) or 0)
            buffer = ctypes.create_unicode_buffer(256)
            native.GetClassNameW(hwnd, buffer, 256)
            value["window_class"] = buffer.value
        else:
            value.setdefault("enabled", True)
        result.append(value)
    return result


def matching_windows(values, target, arguments=None):
    arguments = arguments or {}
    if arguments.get("handle"):
        return [w for w in values if w["handle"] == int(arguments["handle"])]
    if arguments.get("pid"):
        return [w for w in values if w["pid"] == int(arguments["pid"])]
    expected = Path(str(target)).stem.casefold()
    aliases = {"calculator": {"calculatorapp", "calc", "calculator"}, "chrome": {"chrome"},
        "notepad": {"notepad"}, "edge": {"msedge"}, "file explorer": {"explorer"}}
    names = aliases.get(expected, {expected})
    # A title alone can be forged by another process. Require process identity.
    return [w for w in values if Path(w.get("image", "")).stem.casefold() in names and w.get("visible", True)]


def other_windows(values, exception):
    name = str(exception or "MORICE").casefold()
    return [w for w in values if w["pid"] != os.getpid() and name not in w.get("title", "").casefold()
        and "morice" not in w.get("title", "").casefold()]


class DesktopObserver:
    def __init__(self, desktop):
        self.desktop = desktop

    def applications(self, spec, context, result=None, before=None):
        arguments = context.metadata["task_inputs"].get("arguments", {})
        values = window_values(self.desktop.windows)
        matches = matching_windows(values, spec.target, arguments)
        if spec.desired_state.get("verb") == "close_others":
            matches = other_windows(values, arguments.get("except", spec.target or "MORICE"))
        if result and isinstance(result.output, dict) and result.output.get("applicationPid"):
            family = process_family(result.output["applicationPid"])
            matches = [w for w in values if w["pid"] in family]
        candidate = (result.output or {}).get("application", {}) if result else {}
        if not matches and not (result and isinstance(result.output, dict) and result.output.get("applicationPid")) and isinstance(candidate, dict) and candidate.get("target"):
            matches = matching_windows(values, candidate["target"], arguments)
        old_handles = [v["handle"] for v in before.state.get("windows", [])] if before else []
        # Close verification follows the exact original handles, including dialogs.
        if spec.desired_state.get("verb") in {"close", "close_others"} and before:
            matches = [v for v in values if v["handle"] in old_handles or v["pid"] in {w["pid"] for w in before.state.get("windows", [])}]
        state = {"windows": matches, "active_handle": self.desktop.windows.active_window(),
            "waiting_for_user": len(matches) > 1 and spec.desired_state.get("verb") not in {"open", "close_others"}}
        if before and spec.desired_state.get("verb") in {"close", "close_others"} and any(not v.get("enabled", True) for v in matches):
            state["waiting_for_user"] = True  # Modal save/auth dialog; never force termination.
        return Observation(spec.action_id, "win32.windows", state,
            (f"Observed {len(matches)} matching window(s) with process identities.",))

    def file_viewer(self, spec, context, result=None, before=None):
        path = Path(spec.target or ((result.output or {}).get("path", "") if result else "")).resolve()
        output = result.output or {} if result else {}
        viewer_pid = output.get("viewerPid") or output.get("detail", {}).get("viewerPid") if isinstance(output.get("detail", {}), dict) else output.get("viewerPid")
        family = process_family(viewer_pid) if viewer_pid else set()
        matches = [w for w in window_values(self.desktop.windows)
            if path.name.casefold() in w.get("title", "").casefold() and w.get("enabled", True)
            and w["pid"] in family and w.get("visible", True) and not w.get("minimized")
            and w["rect"][2] > w["rect"][0] and w["rect"][3] > w["rect"][1]]
        # Shell-open has no process/document association: existence is insufficient.
        return Observation(spec.action_id, "win32.document", {"path": str(path), "windows": matches,
            "document_association": len(matches) == 1}, ("Viewer PID, document title, and usable window checked.",))


class FocusGuard:
    """Guard a foreground provider's input against focus stolen by the user."""
    def __init__(self, windows, target_handle, *, explicit_focus=False):
        self.windows = windows
        self.target = int(target_handle)
        self.previous = windows.active_window()
        self.explicit_focus = explicit_focus
        self.cursor = None
        if os.name == "nt":
            from ctypes import wintypes
            point = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                self.cursor = (point.x, point.y)

    def assert_target(self):
        if self.windows.active_window() != self.target:
            raise UserInterventionRequired("Focus changed; input was withheld.")

    def restore(self):
        # Do not fight a user who already changed focus.
        if not self.explicit_focus and self.previous and self.windows.active_window() == self.target and self.previous != self.target:
            grant = self.windows.request(self.previous, "focus")
            self.windows.control(self.previous, "focus", grant.token)


def observed_point(window, normalized_x, normalized_y):
    """Physical coordinates derived from a fresh monitor/window rectangle."""
    if not 0 <= normalized_x <= 1 or not 0 <= normalized_y <= 1:
        raise ValueError("Point must lie inside the observed window.")
    left, top, right, bottom = window["rect"]
    if right <= left or bottom <= top or not window.get("monitor_id") or window.get("dpi", 0) <= 0:
        raise ValueError("Fresh monitor bounds and DPI are required.")
    return round(left + (right - left) * normalized_x), round(top + (bottom - top) * normalized_y)
