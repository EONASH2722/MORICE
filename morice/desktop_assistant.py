from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import socket
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


SEARCH_IGNORED_DIRS = {
    "$recycle.bin",
    ".git",
    ".idea",
    ".venv",
    "__pycache__",
    "appdata",
    "build",
    "dist",
    "node_modules",
    "programdata",
    "system volume information",
    "windows",
}


@dataclass(frozen=True)
class DesktopAction:
    kind: str
    target: str = ""
    argument: str = ""
    confirmation_required: bool = False
    description: str = ""


@dataclass(frozen=True)
class SystemSnapshot:
    operating_system: str
    cpu: str
    cpu_threads: int
    memory_total_gb: float
    memory_available_gb: float
    storage_total_gb: float
    storage_free_gb: float
    battery_percent: int | None
    battery_charging: bool | None
    hostname: str
    local_ip: str


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("memory_load", ctypes.c_ulong),
        ("total_physical", ctypes.c_ulonglong),
        ("available_physical", ctypes.c_ulonglong),
        ("total_page_file", ctypes.c_ulonglong),
        ("available_page_file", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("available_virtual", ctypes.c_ulonglong),
        ("available_extended_virtual", ctypes.c_ulonglong),
    ]


class _PowerStatus(ctypes.Structure):
    _fields_ = [
        ("ac_line_status", ctypes.c_byte),
        ("battery_flag", ctypes.c_byte),
        ("battery_life_percent", ctypes.c_byte),
        ("system_status_flag", ctypes.c_byte),
        ("battery_life_time", ctypes.c_ulong),
        ("battery_full_life_time", ctypes.c_ulong),
    ]


def _memory_values() -> tuple[float, float]:
    if os.name != "nt":
        return 0.0, 0.0
    status = _MemoryStatus()
    status.length = ctypes.sizeof(_MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return 0.0, 0.0
    divisor = 1024**3
    return status.total_physical / divisor, status.available_physical / divisor


def _battery_values() -> tuple[int | None, bool | None]:
    if os.name != "nt":
        return None, None
    status = _PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return None, None
    percent = int(status.battery_life_percent)
    if percent > 100:
        percent = None
    charging = None if status.ac_line_status not in {0, 1} else status.ac_line_status == 1
    return percent, charging


def collect_system_snapshot() -> SystemSnapshot:
    memory_total, memory_available = _memory_values()
    storage = shutil.disk_usage(os.path.abspath(os.sep))
    battery_percent, battery_charging = _battery_values()
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except OSError:
        local_ip = "Unavailable"
    processor = platform.processor().strip() or platform.machine() or "Unknown CPU"
    return SystemSnapshot(
        operating_system=f"{platform.system()} {platform.release()}",
        cpu=processor,
        cpu_threads=os.cpu_count() or 1,
        memory_total_gb=memory_total,
        memory_available_gb=memory_available,
        storage_total_gb=storage.total / (1024**3),
        storage_free_gb=storage.free / (1024**3),
        battery_percent=battery_percent,
        battery_charging=battery_charging,
        hostname=hostname,
        local_ip=local_ip,
    )


def search_files(
    query: str,
    roots: Iterable[str],
    *,
    max_results: int = 80,
    max_scanned: int = 40_000,
) -> list[str]:
    needle = " ".join((query or "").strip().lower().split())
    if not needle:
        return []
    results: list[str] = []
    scanned = 0
    for root_value in roots:
        root = os.path.abspath(os.path.expanduser(root_value))
        if not os.path.isdir(root):
            continue
        for current, directories, files in os.walk(root):
            directories[:] = [
                name
                for name in directories
                if name.lower() not in SEARCH_IGNORED_DIRS and not name.startswith(".")
            ]
            for name in files:
                scanned += 1
                if needle in name.lower():
                    results.append(os.path.join(current, name))
                    if len(results) >= max_results:
                        return results
                if scanned >= max_scanned:
                    return results
    return results


def parse_desktop_command(text: str) -> DesktopAction | None:
    command = (text or "").strip()
    if not command.startswith("/"):
        return None
    name, _, argument = command.partition(" ")
    name = name.lower()
    argument = argument.strip().strip('"')
    if name in {"/system", "/status"}:
        return DesktopAction("system", description="Refresh system information")
    if name in {"/diagnostics", "/diag"}:
        return DesktopAction(
            "diagnostics",
            description="Open MORICE runtime diagnostics",
        )
    if name == "/find" and argument:
        return DesktopAction("find", argument=argument, description=f"Find files matching {argument}")
    if name == "/open" and argument:
        return DesktopAction("open", target=argument, description=f"Open {argument}")
    if name == "/folder" and argument:
        return DesktopAction("folder", target=argument, description=f"Open folder {argument}")
    if name in {"/site", "/website"} and argument:
        return DesktopAction("website", target=argument, description=f"Open website {argument}")
    if name == "/launch" and argument:
        return DesktopAction("launch", target=argument, description=f"Launch {argument}")
    if name == "/close-app" and argument:
        return DesktopAction(
            "close-app",
            target=argument,
            confirmation_required=True,
            description=f"Close application {argument}",
        )
    if name == "/screenshot":
        return DesktopAction("screenshot", description="Capture the current display")
    if name in {"/play", "/pause", "/play-pause"}:
        return DesktopAction("media", argument="play-pause", description="Toggle media playback")
    if name == "/next":
        return DesktopAction("media", argument="next", description="Play next track")
    if name == "/previous":
        return DesktopAction("media", argument="previous", description="Play previous track")
    if name in {"/mute", "/volume-up", "/volume-down"}:
        return DesktopAction("media", argument=name[1:], description=name[1:].replace("-", " ").title())
    if name == "/workspace":
        return DesktopAction("workspace", description="Open the workspace hub")
    if name == "/theme":
        return DesktopAction("theme", argument=argument.lower(), description="Change the MORICE theme")
    if name == "/new-window":
        return DesktopAction("new-window", description="Open another MORICE window")
    return DesktopAction("unknown", argument=command, description="Unknown desktop command")


def _safe_website(target: str) -> str:
    value = target.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", value, flags=re.IGNORECASE):
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only valid HTTP or HTTPS websites can be opened.")
    return value


def _send_media_key(code: int) -> None:
    if os.name != "nt":
        raise RuntimeError("Global media controls are currently available on Windows only.")
    key_up = 0x0002
    ctypes.windll.user32.keybd_event(code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(code, 0, key_up, 0)


def execute_desktop_action(action: DesktopAction) -> str:
    if action.confirmation_required:
        raise PermissionError("This action requires explicit confirmation.")
    if action.kind == "website":
        website = _safe_website(action.target)
        webbrowser.open(website)
        return f"Opened {website}."
    if action.kind in {"open", "folder"}:
        target = os.path.abspath(os.path.expanduser(action.target))
        if not os.path.exists(target):
            raise FileNotFoundError(target)
        if action.kind == "folder" and not os.path.isdir(target):
            target = os.path.dirname(target)
        os.startfile(target)
        return f"Opened {target}."
    if action.kind == "launch":
        candidate = os.path.abspath(os.path.expanduser(action.target))
        executable = candidate if os.path.exists(candidate) else shutil.which(action.target)
        if not executable:
            raise FileNotFoundError(f"Application not found: {action.target}")
        subprocess.Popen([executable], close_fds=True)
        return f"Launched {action.target}."
    if action.kind == "media":
        key_codes = {
            "play-pause": 0xB3,
            "next": 0xB0,
            "previous": 0xB1,
            "mute": 0xAD,
            "volume-down": 0xAE,
            "volume-up": 0xAF,
        }
        code = key_codes.get(action.argument)
        if code is None:
            raise ValueError("Unsupported media action.")
        _send_media_key(code)
        return f"Media command sent: {action.argument.replace('-', ' ')}."
    raise ValueError(f"Unsupported desktop action: {action.kind}")


def close_application(process_name: str) -> str:
    clean_name = Path(process_name.strip()).name
    if not clean_name or not re.fullmatch(r"[A-Za-z0-9_. -]{1,120}", clean_name):
        raise ValueError("Enter a valid application process name.")
    if os.name != "nt":
        raise RuntimeError("Application closing is currently available on Windows only.")
    if not clean_name.lower().endswith(".exe"):
        clean_name += ".exe"
    completed = subprocess.run(
        ["taskkill", "/IM", clean_name],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Unable to close application.").strip()
        raise RuntimeError(detail)
    return f"Closed {clean_name}."
