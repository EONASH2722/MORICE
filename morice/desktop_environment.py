from __future__ import annotations

import csv
import ctypes
import difflib
import hashlib
import json
import math
import mimetypes
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from collections import Counter, deque
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from xml.etree import ElementTree

from .desktop_assistant import (
    DesktopAction,
    SystemSnapshot,
    collect_system_snapshot,
    execute_desktop_action,
)


DESKTOP_STATE_VERSION = 1
MAX_SCAN_FILES = 60_000
MAX_MEMORY_RECORDS = 2_000
MAX_CLIPBOARD_ITEMS = 100
MAX_NOTIFICATION_ITEMS = 500
IGNORED_DIRECTORIES = {
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
TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".log",
    ".lua",
    ".md",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
PROJECT_MARKERS = {
    ".git",
    "CMakeLists.txt",
    "Cargo.toml",
    "Gemfile",
    "go.mod",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass


def _read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def _clean_text(value: Any, limit: int = 4_000) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _json_mapping(
    value: Mapping[str, Any] | None,
    *,
    label: str,
    max_bytes: int = 65_536,
) -> dict[str, Any]:
    candidate = dict(value or {})
    try:
        encoded = json.dumps(
            candidate,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain JSON-compatible values.") from exc
    if len(encoded) > max_bytes:
        raise ValueError(f"{label} exceeds the {max_bytes}-byte limit.")
    return json.loads(encoded.decode("utf-8"))


def _fingerprint(action: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        {"action": action, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_path(value: str | os.PathLike[str]) -> Path:
    return Path(value).expanduser().resolve()


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in re.findall(r"[a-z0-9+#.-]{2,}", value.casefold())
        if token not in {"find", "show", "open", "locate", "file", "files", "my", "the"}
    )


@dataclass(frozen=True)
class PermissionGrant:
    token: str
    action: str
    fingerprint: str
    expires_at: float
    description: str


class DesktopPermissionManager:
    """Issues exact, short-lived, one-use grants for sensitive desktop actions."""

    def __init__(self, *, ttl_seconds: float = 300.0):
        self.ttl_seconds = max(10.0, min(float(ttl_seconds), 3_600.0))
        self._grants: dict[str, PermissionGrant] = {}
        self._lock = threading.RLock()

    def request(
        self,
        action: str,
        payload: Mapping[str, Any],
        *,
        description: str,
    ) -> PermissionGrant:
        clean_action = _clean_text(action, 120)
        if not clean_action:
            raise ValueError("Permission action cannot be empty.")
        token = uuid.uuid4().hex
        grant = PermissionGrant(
            token,
            clean_action,
            _fingerprint(clean_action, payload),
            time.time() + self.ttl_seconds,
            _clean_text(description, 500),
        )
        with self._lock:
            self._prune()
            self._grants[token] = grant
        return grant

    def consume(self, token: str, action: str, payload: Mapping[str, Any]) -> bool:
        with self._lock:
            self._prune()
            grant = self._grants.pop(str(token or ""), None)
        if grant is None or grant.expires_at < time.time():
            return False
        return grant.action == action and grant.fingerprint == _fingerprint(action, payload)

    def pending(self) -> tuple[PermissionGrant, ...]:
        with self._lock:
            self._prune()
            return tuple(self._grants.values())

    def revoke_all(self) -> None:
        with self._lock:
            self._grants.clear()

    def _prune(self) -> None:
        now = time.time()
        self._grants = {
            token: grant
            for token, grant in self._grants.items()
            if grant.expires_at >= now
        }


@dataclass(frozen=True)
class ProcessInfo:
    image_name: str
    pid: int
    session_name: str = ""
    memory_kb: int = 0


@dataclass(frozen=True)
class ApplicationCandidate:
    name: str
    target: str
    source: str


class ApplicationManager:
    def __init__(self, directory: Path, permissions: DesktopPermissionManager):
        self.directory = directory
        self.permissions = permissions
        self.state_path = directory / "applications.json"
        self._lock = threading.RLock()
        data = _read_json(self.state_path, {})
        self.pinned = [
            _clean_text(item, 2_048)
            for item in data.get("pinned", [])
            if _clean_text(item, 2_048)
        ][:50]
        self.recent = [
            _clean_text(item, 2_048)
            for item in data.get("recent", [])
            if _clean_text(item, 2_048)
        ][:50]

    @staticmethod
    def list_processes() -> list[ProcessInfo]:
        if os.name != "nt":
            return []
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            return []
        processes: list[ProcessInfo] = []
        for row in csv.reader(completed.stdout.splitlines()):
            if len(row) < 5:
                continue
            try:
                pid = int(row[1])
            except ValueError:
                continue
            memory = int(re.sub(r"\D", "", row[4]) or 0)
            processes.append(ProcessInfo(row[0], pid, row[2], memory))
        return processes

    @staticmethod
    def _shortcut_roots() -> tuple[Path, ...]:
        values = (
            os.getenv("APPDATA", ""),
            os.getenv("PROGRAMDATA", ""),
        )
        suffixes = (
            Path("Microsoft/Windows/Start Menu/Programs"),
            Path("Microsoft/Windows/Start Menu/Programs"),
        )
        return tuple(
            Path(value) / suffix
            for value, suffix in zip(values, suffixes)
            if value
        )

    def discover(self, query: str = "", *, limit: int = 80) -> list[ApplicationCandidate]:
        needle = _clean_text(query, 200).casefold()
        candidates: dict[str, ApplicationCandidate] = {}
        for root in self._shortcut_roots():
            if not root.is_dir():
                continue
            try:
                iterator = root.rglob("*.lnk")
                for path in iterator:
                    name = path.stem
                    if needle and needle not in name.casefold():
                        continue
                    candidates[str(path).casefold()] = ApplicationCandidate(
                        name, str(path), "start-menu"
                    )
                    if len(candidates) >= limit:
                        break
            except OSError:
                continue
        direct = shutil.which(query) if query else None
        if direct:
            candidates[direct.casefold()] = ApplicationCandidate(
                Path(direct).stem, direct, "path"
            )
        return sorted(candidates.values(), key=lambda item: item.name.casefold())[:limit]

    def resolve(self, target: str) -> ApplicationCandidate | None:
        clean = _clean_text(target, 2_048)
        if not clean:
            return None
        direct = Path(clean).expanduser()
        if direct.exists() and direct.is_file():
            return ApplicationCandidate(direct.stem, str(direct.resolve()), "direct")
        executable = shutil.which(clean)
        if executable:
            return ApplicationCandidate(Path(executable).stem, executable, "path")
        matches = self.discover(clean, limit=20)
        exact = next(
            (item for item in matches if item.name.casefold() == clean.casefold()),
            None,
        )
        return exact or (matches[0] if matches else None)

    def alternatives(self, target: str, *, limit: int = 5) -> list[ApplicationCandidate]:
        all_candidates = self.discover(limit=300)
        names = {item.name: item for item in all_candidates}
        matches = difflib.get_close_matches(target, names, n=limit, cutoff=0.35)
        return [names[name] for name in matches]

    def request_launch(self, target: str) -> PermissionGrant:
        candidate = self.resolve(target)
        payload = {"target": candidate.target if candidate else target}
        return self.permissions.request(
            "application.launch",
            payload,
            description=f"Launch {candidate.name if candidate else target}",
        )

    def launch(self, target: str, permission_token: str) -> ApplicationCandidate:
        candidate = self.resolve(target)
        if candidate is None:
            alternatives = ", ".join(item.name for item in self.alternatives(target))
            suffix = f" Alternatives: {alternatives}." if alternatives else ""
            raise FileNotFoundError(f"Application not found: {target}.{suffix}")
        payload = {"target": candidate.target}
        if not self.permissions.consume(
            permission_token, "application.launch", payload
        ):
            raise PermissionError("Launching this application requires exact approval.")
        if candidate.target.casefold().endswith(".lnk"):
            if os.name != "nt":
                raise RuntimeError("Windows shortcuts are supported on Windows only.")
            os.startfile(candidate.target)
        else:
            subprocess.Popen(
                [candidate.target],
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        self._record_recent(candidate.target)
        return candidate

    def request_close(self, image_name: str, *, pid: int | None = None) -> PermissionGrant:
        payload = {"imageName": Path(image_name).name, "pid": int(pid or 0)}
        return self.permissions.request(
            "application.close",
            payload,
            description=f"Close {payload['imageName']}; unsaved work may be lost",
        )

    def close(self, image_name: str, permission_token: str, *, pid: int | None = None) -> None:
        clean = Path(_clean_text(image_name, 260)).name
        payload = {"imageName": clean, "pid": int(pid or 0)}
        if not self.permissions.consume(permission_token, "application.close", payload):
            raise PermissionError("Closing this application requires exact approval.")
        if os.name != "nt":
            raise RuntimeError("Application control is currently available on Windows only.")
        command = ["taskkill", "/PID", str(pid)] if pid else ["taskkill", "/IM", clean]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            raise RuntimeError(
                (completed.stderr or completed.stdout or "Application close failed.").strip()
            )

    def request_restart(
        self,
        target: str,
        *,
        image_name: str = "",
        pid: int | None = None,
    ) -> PermissionGrant:
        candidate = self.resolve(target)
        payload = {
            "target": candidate.target if candidate else target,
            "imageName": Path(image_name).name,
            "pid": int(pid or 0),
        }
        return self.permissions.request(
            "application.restart",
            payload,
            description=(
                f"Close and restart {candidate.name if candidate else target}; "
                "unsaved work may be lost"
            ),
        )

    def restart(
        self,
        target: str,
        permission_token: str,
        *,
        image_name: str = "",
        pid: int | None = None,
    ) -> ApplicationCandidate:
        candidate = self.resolve(target)
        if candidate is None:
            raise FileNotFoundError(f"Application not found: {target}.")
        payload = {
            "target": candidate.target,
            "imageName": Path(image_name).name,
            "pid": int(pid or 0),
        }
        if not self.permissions.consume(
            permission_token, "application.restart", payload
        ):
            raise PermissionError("Restarting this application requires exact approval.")
        if os.name != "nt":
            raise RuntimeError("Application restart is currently available on Windows only.")
        if pid or image_name:
            command = (
                ["taskkill", "/PID", str(pid)]
                if pid
                else ["taskkill", "/IM", Path(image_name).name]
            )
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    (completed.stderr or completed.stdout or "Application close failed.").strip()
                )
        if candidate.target.casefold().endswith(".lnk"):
            os.startfile(candidate.target)
        else:
            subprocess.Popen(
                [candidate.target],
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        self._record_recent(candidate.target)
        return candidate

    def pin(self, target: str, pinned: bool = True) -> None:
        clean = _clean_text(target, 2_048)
        with self._lock:
            self.pinned = [item for item in self.pinned if item.casefold() != clean.casefold()]
            if pinned and clean:
                self.pinned.insert(0, clean)
            self.pinned = self.pinned[:50]
            self._save()

    def _record_recent(self, target: str) -> None:
        with self._lock:
            self.recent = [
                target,
                *[item for item in self.recent if item.casefold() != target.casefold()],
            ][:50]
            self._save()

    def _save(self) -> None:
        _atomic_json_write(
            self.state_path,
            {"version": DESKTOP_STATE_VERSION, "pinned": self.pinned, "recent": self.recent},
        )


@dataclass(frozen=True)
class WindowInfo:
    handle: int
    title: str
    pid: int
    rect: tuple[int, int, int, int]
    visible: bool
    minimized: bool
    maximized: bool


class WindowManager:
    SW_HIDE = 0
    SW_SHOWNORMAL = 1
    SW_SHOWMINIMIZED = 2
    SW_SHOWMAXIMIZED = 3
    SW_RESTORE = 9

    def __init__(self, permissions: DesktopPermissionManager):
        self.permissions = permissions

    @staticmethod
    def list_windows() -> list[WindowInfo]:
        if os.name != "nt":
            return []
        user32 = ctypes.windll.user32
        windows: list[WindowInfo] = []
        enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if not title:
                return True
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            windows.append(
                WindowInfo(
                    int(hwnd),
                    title,
                    int(pid.value),
                    (rect.left, rect.top, rect.right, rect.bottom),
                    True,
                    bool(user32.IsIconic(hwnd)),
                    bool(user32.IsZoomed(hwnd)),
                )
            )
            return True

        user32.EnumWindows(enum_proc_type(callback), 0)
        return windows

    def request(self, handle: int, action: str, **parameters: Any) -> PermissionGrant:
        payload = {"handle": int(handle), "action": action, **parameters}
        return self.permissions.request(
            "window.control",
            payload,
            description=f"{action.title()} desktop window {handle}",
        )

    def control(
        self,
        handle: int,
        action: str,
        permission_token: str,
        **parameters: Any,
    ) -> None:
        payload = {"handle": int(handle), "action": action, **parameters}
        if not self.permissions.consume(permission_token, "window.control", payload):
            raise PermissionError("Window control requires exact approval.")
        if os.name != "nt":
            raise RuntimeError("Window control is currently available on Windows only.")
        user32 = ctypes.windll.user32
        hwnd = ctypes.c_void_p(int(handle))
        if not user32.IsWindow(hwnd):
            raise ValueError("The selected window no longer exists.")
        show_codes = {
            "minimize": self.SW_SHOWMINIMIZED,
            "maximize": self.SW_SHOWMAXIMIZED,
            "restore": self.SW_RESTORE,
        }
        if action in show_codes:
            user32.ShowWindow(hwnd, show_codes[action])
        elif action == "focus":
            user32.ShowWindow(hwnd, self.SW_RESTORE)
            if not user32.SetForegroundWindow(hwnd):
                raise RuntimeError("Windows refused to focus the selected window.")
        elif action in {"move", "resize", "move-resize"}:
            current = next(
                (item for item in self.list_windows() if item.handle == int(handle)),
                None,
            )
            if current is None:
                raise ValueError("The selected window no longer exists.")
            left, top, right, bottom = current.rect
            x = int(parameters.get("x", left))
            y = int(parameters.get("y", top))
            width = max(200, int(parameters.get("width", right - left)))
            height = max(120, int(parameters.get("height", bottom - top)))
            if not user32.MoveWindow(hwnd, x, y, width, height, True):
                raise RuntimeError("Windows refused to move or resize the window.")
        else:
            raise ValueError(f"Unsupported window action: {action}")

    def apply_layout(
        self,
        handles: Sequence[int],
        layout: str,
        permission_token: str,
        *,
        bounds: tuple[int, int, int, int] | None = None,
    ) -> None:
        clean_handles = [int(handle) for handle in handles[:12]]
        payload = {"handles": clean_handles, "layout": layout, "bounds": bounds}
        if not self.permissions.consume(permission_token, "window.layout", payload):
            raise PermissionError("Workspace layout requires exact approval.")
        if not clean_handles:
            return
        if os.name != "nt":
            raise RuntimeError("Window layouts are currently available on Windows only.")
        if bounds is None:
            width = ctypes.windll.user32.GetSystemMetrics(0)
            height = ctypes.windll.user32.GetSystemMetrics(1)
            bounds = (0, 0, width, height)
        x, y, width, height = bounds
        if layout not in {"columns", "rows", "grid"}:
            raise ValueError("Layout must be columns, rows, or grid.")
        count = len(clean_handles)
        columns = count if layout == "columns" else 1
        rows = count if layout == "rows" else 1
        if layout == "grid":
            columns = max(1, math.ceil(math.sqrt(count)))
            rows = math.ceil(count / columns)
        cell_width = max(200, width // columns)
        cell_height = max(120, height // rows)
        for index, handle in enumerate(clean_handles):
            column = index % columns
            row = index // columns
            if not ctypes.windll.user32.MoveWindow(
                ctypes.c_void_p(handle),
                x + column * cell_width,
                y + row * cell_height,
                cell_width,
                cell_height,
                True,
            ):
                raise RuntimeError(f"Unable to place window {handle}.")


@dataclass(frozen=True)
class FileMetadata:
    path: str
    name: str
    extension: str
    size: int
    created_at: str
    modified_at: str
    mime_type: str
    is_directory: bool


@dataclass(frozen=True)
class FileSearchResult:
    path: str
    score: float
    reasons: tuple[str, ...]
    metadata: FileMetadata


@dataclass(frozen=True)
class PreviewDescriptor:
    path: str
    kind: str
    metadata: FileMetadata
    text: str = ""
    entries: tuple[str, ...] = ()
    dimensions: tuple[int, int] | None = None
    renderer: str = ""
    available: bool = True
    reason: str = ""


def _timestamp_text(value: float) -> str:
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return ""


class FileManager:
    def __init__(self, directory: Path):
        self.directory = directory
        self.state_path = directory / "files.json"
        self._lock = threading.RLock()
        data = _read_json(self.state_path, {})
        self.tags = {
            _clean_text(path, 2_048): [
                _clean_text(tag, 80)
                for tag in tags
                if _clean_text(tag, 80)
            ][:30]
            for path, tags in data.get("tags", {}).items()
            if isinstance(tags, list)
        }
        self.bookmarks = [
            _clean_text(path, 2_048)
            for path in data.get("bookmarks", [])
            if _clean_text(path, 2_048)
        ][:200]
        self.pinned_folders = [
            _clean_text(path, 2_048)
            for path in data.get("pinnedFolders", [])
            if _clean_text(path, 2_048)
        ][:100]
        self.access_counts = Counter(
            {
                _clean_text(path, 2_048): max(0, int(count))
                for path, count in data.get("accessCounts", {}).items()
            }
        )

    @staticmethod
    def metadata(path: str | os.PathLike[str]) -> FileMetadata:
        target = _safe_path(path)
        stat = target.stat()
        mime, _encoding = mimetypes.guess_type(str(target))
        return FileMetadata(
            str(target),
            target.name,
            target.suffix.casefold(),
            0 if target.is_dir() else int(stat.st_size),
            _timestamp_text(stat.st_ctime),
            _timestamp_text(stat.st_mtime),
            mime or "application/octet-stream",
            target.is_dir(),
        )

    @staticmethod
    def _walk(roots: Iterable[str | os.PathLike[str]], *, max_files: int) -> Iterable[Path]:
        scanned = 0
        for value in roots:
            root = Path(value).expanduser()
            if not root.is_dir():
                continue
            for current, directories, files in os.walk(root, followlinks=False):
                directories[:] = [
                    name
                    for name in directories
                    if name.casefold() not in IGNORED_DIRECTORIES
                    and not name.startswith(".")
                    and not (Path(current) / name).is_symlink()
                ]
                for name in files:
                    path = Path(current) / name
                    if path.is_symlink():
                        continue
                    yield path
                    scanned += 1
                    if scanned >= max_files:
                        return

    def search(
        self,
        query: str,
        roots: Iterable[str | os.PathLike[str]],
        *,
        limit: int = 100,
        max_files: int = MAX_SCAN_FILES,
    ) -> list[FileSearchResult]:
        clean = _clean_text(query, 1_000)
        tokens = _tokenize(clean)
        if not tokens:
            return []
        lowered = clean.casefold()
        wants_latest = any(word in lowered for word in ("latest", "newest", "recent"))
        wants_yesterday = "yesterday" in lowered
        wants_large = "large" in lowered or "big" in lowered
        wants_project = "project" in lowered
        categories = {
            "python": {".py"},
            "pdf": {".pdf"},
            "video": {".mp4", ".mkv", ".mov", ".avi", ".webm"},
            "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"},
            "screenshot": {".png", ".jpg", ".jpeg"},
            "document": {".pdf", ".docx", ".md", ".txt", ".pptx", ".xlsx"},
        }
        requested_extensions: set[str] = set()
        for category, extensions in categories.items():
            if category in lowered:
                requested_extensions.update(extensions)
        yesterday = (datetime.now() - timedelta(days=1)).date()
        results: list[FileSearchResult] = []
        for path in self._walk(roots, max_files=max(1, min(max_files, MAX_SCAN_FILES))):
            try:
                metadata = self.metadata(path)
            except OSError:
                continue
            score = 0.0
            reasons: list[str] = []
            haystack = f"{path.name} {path.parent}".casefold()
            matched = sum(1 for token in tokens if token in haystack)
            if matched:
                score += matched * 12.0
                reasons.append(f"{matched} search term(s) matched")
            if requested_extensions:
                if metadata.extension not in requested_extensions:
                    continue
                score += 16.0
                reasons.append("requested file type")
            if wants_yesterday:
                modified = datetime.fromtimestamp(path.stat().st_mtime).date()
                if modified != yesterday:
                    continue
                score += 24.0
                reasons.append("modified yesterday")
            if wants_large:
                if metadata.size < 100 * 1024 * 1024:
                    continue
                score += min(30.0, metadata.size / (100 * 1024 * 1024))
                reasons.append("large file")
            if wants_project:
                parent_names = {item.name for item in path.parents[:3]}
                marker_hit = any((parent / marker).exists() for parent in path.parents[:3] for marker in PROJECT_MARKERS)
                if not marker_hit and not any("project" in name.casefold() for name in parent_names):
                    continue
                score += 20.0
                reasons.append("inside a project")
            if wants_latest:
                age_days = max(
                    0.0, (time.time() - path.stat().st_mtime) / 86_400.0
                )
                score += max(0.0, 20.0 - min(20.0, age_days))
                reasons.append("recently modified")
            score += min(10.0, self.access_counts.get(str(path.resolve()), 0) * 0.5)
            if score <= 0:
                continue
            results.append(FileSearchResult(str(path.resolve()), score, tuple(reasons), metadata))
        results.sort(
            key=lambda item: (
                item.score,
                item.metadata.modified_at,
            ),
            reverse=True,
        )
        return results[: max(1, min(int(limit), 500))]

    def recent_files(
        self,
        roots: Iterable[str | os.PathLike[str]],
        *,
        limit: int = 100,
    ) -> list[FileMetadata]:
        items: list[tuple[float, FileMetadata]] = []
        for path in self._walk(roots, max_files=MAX_SCAN_FILES):
            try:
                stat = path.stat()
                items.append((stat.st_mtime, self.metadata(path)))
            except OSError:
                continue
        items.sort(key=lambda item: item[0], reverse=True)
        return [metadata for _modified, metadata in items[:limit]]

    def large_files(
        self,
        roots: Iterable[str | os.PathLike[str]],
        *,
        minimum_bytes: int = 100 * 1024 * 1024,
        limit: int = 100,
    ) -> list[FileMetadata]:
        items: list[FileMetadata] = []
        for path in self._walk(roots, max_files=MAX_SCAN_FILES):
            try:
                metadata = self.metadata(path)
            except OSError:
                continue
            if metadata.size >= max(0, int(minimum_bytes)):
                items.append(metadata)
        items.sort(key=lambda item: item.size, reverse=True)
        return items[:limit]

    def duplicates(
        self,
        roots: Iterable[str | os.PathLike[str]],
        *,
        minimum_bytes: int = 1,
        max_files: int = MAX_SCAN_FILES,
    ) -> list[tuple[str, ...]]:
        by_size: dict[int, list[Path]] = {}
        for path in self._walk(roots, max_files=max_files):
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size >= minimum_bytes:
                by_size.setdefault(size, []).append(path)
        groups: list[tuple[str, ...]] = []
        for paths in by_size.values():
            if len(paths) < 2:
                continue
            by_hash: dict[str, list[str]] = {}
            for path in paths:
                digest = hashlib.sha256()
                try:
                    with path.open("rb") as handle:
                        while chunk := handle.read(1024 * 1024):
                            digest.update(chunk)
                except OSError:
                    continue
                by_hash.setdefault(digest.hexdigest(), []).append(str(path.resolve()))
            groups.extend(
                tuple(values) for values in by_hash.values() if len(values) > 1
            )
        groups.sort(key=lambda values: len(values), reverse=True)
        return groups

    @staticmethod
    def detect_projects(
        roots: Iterable[str | os.PathLike[str]],
        *,
        max_depth: int = 5,
        limit: int = 100,
    ) -> list[str]:
        projects: list[str] = []
        for value in roots:
            root = Path(value).expanduser()
            if not root.is_dir():
                continue
            for current, directories, files in os.walk(root, followlinks=False):
                path = Path(current)
                try:
                    depth = len(path.relative_to(root).parts)
                except ValueError:
                    continue
                directories[:] = [
                    name
                    for name in directories
                    if name.casefold() not in IGNORED_DIRECTORIES
                    and not name.startswith(".")
                ]
                entries = set(files) | set(directories)
                if entries.intersection(PROJECT_MARKERS):
                    projects.append(str(path.resolve()))
                    directories[:] = []
                    if len(projects) >= limit:
                        return projects
                elif depth >= max_depth:
                    directories[:] = []
        return projects

    def preview(self, path: str | os.PathLike[str]) -> PreviewDescriptor:
        target = _safe_path(path)
        metadata = self.metadata(target)
        if metadata.is_directory:
            entries = tuple(item.name for item in list(target.iterdir())[:500])
            return PreviewDescriptor(str(target), "directory", metadata, entries=entries)
        extension = metadata.extension
        if extension in TEXT_EXTENSIONS or extension in {".csv", ".json"}:
            if metadata.size > 8 * 1024 * 1024:
                return PreviewDescriptor(
                    str(target),
                    "text",
                    metadata,
                    available=False,
                    reason="Text preview is limited to 8 MB.",
                )
            text = target.read_text(encoding="utf-8", errors="replace")
            kind = "json" if extension == ".json" else "csv" if extension == ".csv" else "text"
            return PreviewDescriptor(str(target), kind, metadata, text=text[:500_000], renderer="text")
        if extension in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
            try:
                from PIL import Image

                with Image.open(target) as image:
                    dimensions = tuple(image.size)
            except (ImportError, OSError):
                dimensions = None
            return PreviewDescriptor(
                str(target), "image", metadata, dimensions=dimensions, renderer="image"
            )
        if extension == ".pdf":
            return PreviewDescriptor(str(target), "pdf", metadata, renderer="QtPdf")
        if extension in {".mp3", ".wav", ".flac", ".m4a", ".ogg"}:
            return PreviewDescriptor(str(target), "audio", metadata, renderer="QtMultimedia")
        if extension in {".mp4", ".mkv", ".mov", ".avi", ".webm"}:
            return PreviewDescriptor(str(target), "video", metadata, renderer="QtMultimedia")
        if extension in {".zip", ".docx", ".xlsx", ".pptx"}:
            return self._preview_zip_document(target, metadata)
        return PreviewDescriptor(
            str(target),
            "binary",
            metadata,
            available=False,
            reason="No safe in-app preview renderer is registered for this file type.",
        )

    def _preview_zip_document(
        self, target: Path, metadata: FileMetadata
    ) -> PreviewDescriptor:
        try:
            with zipfile.ZipFile(target) as archive:
                infos = archive.infolist()[:2_000]
                names = [info.filename for info in infos]
                info_by_name = {info.filename: info for info in infos}
                text_parts: list[str] = []
                extracted_bytes = 0
                prefixes = {
                    ".docx": ("word/document.xml",),
                    ".pptx": ("ppt/slides/",),
                    ".xlsx": ("xl/sharedStrings.xml",),
                }.get(target.suffix.casefold(), ())
                for name in names:
                    if not prefixes or not any(
                        name == prefix or name.startswith(prefix) for prefix in prefixes
                    ):
                        continue
                    if not name.endswith(".xml"):
                        continue
                    info = info_by_name[name]
                    if info.file_size > 8 * 1024 * 1024:
                        continue
                    if (
                        info.compress_size > 0
                        and info.file_size / info.compress_size > 1_000
                    ):
                        continue
                    if extracted_bytes + info.file_size > 16 * 1024 * 1024:
                        break
                    raw = archive.read(name)
                    extracted_bytes += len(raw)
                    try:
                        root = ElementTree.fromstring(raw)
                    except ElementTree.ParseError:
                        continue
                    text_parts.extend(
                        node.text.strip()
                        for node in root.iter()
                        if node.text and node.text.strip()
                    )
                    if sum(len(part) for part in text_parts) >= 500_000:
                        break
                kind = target.suffix.casefold().lstrip(".") or "archive"
                return PreviewDescriptor(
                    str(target),
                    kind,
                    metadata,
                    text="\n".join(text_parts)[:500_000],
                    entries=tuple(names),
                    renderer="archive-document",
                )
        except (OSError, zipfile.BadZipFile) as exc:
            return PreviewDescriptor(
                str(target),
                "archive",
                metadata,
                available=False,
                reason=f"Archive preview failed: {exc}",
            )

    def record_access(self, path: str | os.PathLike[str]) -> None:
        target = str(_safe_path(path))
        with self._lock:
            self.access_counts[target] += 1
            self._save()

    def set_tags(self, path: str, tags: Iterable[str]) -> None:
        target = str(_safe_path(path))
        with self._lock:
            self.tags[target] = list(
                dict.fromkeys(_clean_text(tag, 80) for tag in tags if _clean_text(tag, 80))
            )[:30]
            self._save()

    def bookmark(self, path: str, enabled: bool = True) -> None:
        target = str(_safe_path(path))
        with self._lock:
            self.bookmarks = [item for item in self.bookmarks if item != target]
            if enabled:
                self.bookmarks.insert(0, target)
            self.bookmarks = self.bookmarks[:200]
            self._save()

    def pin_folder(self, path: str, enabled: bool = True) -> None:
        target = _safe_path(path)
        if enabled and not target.is_dir():
            raise NotADirectoryError(str(target))
        clean = str(target)
        with self._lock:
            self.pinned_folders = [item for item in self.pinned_folders if item != clean]
            if enabled:
                self.pinned_folders.insert(0, clean)
            self.pinned_folders = self.pinned_folders[:100]
            self._save()

    def smart_collections(
        self, roots: Iterable[str | os.PathLike[str]]
    ) -> dict[str, list[Any]]:
        return {
            "recent": self.recent_files(roots, limit=30),
            "large": self.large_files(roots, limit=30),
            "projects": self.detect_projects(roots, limit=30),
            "bookmarks": list(self.bookmarks),
            "pinnedFolders": list(self.pinned_folders),
        }

    def _save(self) -> None:
        _atomic_json_write(
            self.state_path,
            {
                "version": DESKTOP_STATE_VERSION,
                "tags": self.tags,
                "bookmarks": self.bookmarks,
                "pinnedFolders": self.pinned_folders,
                "accessCounts": dict(self.access_counts.most_common(2_000)),
            },
        )


@dataclass(frozen=True)
class DocumentCitation:
    path: str
    line: int
    excerpt: str


@dataclass(frozen=True)
class DocumentAnalysis:
    path: str
    kind: str
    summary: str
    entities: tuple[str, ...]
    formulas: tuple[str, ...]
    tables: tuple[tuple[tuple[str, ...], ...], ...]
    citations: tuple[DocumentCitation, ...]
    text_available: bool
    limitations: tuple[str, ...] = ()


class DocumentManager:
    """Deterministic local document extraction with source-linked results."""

    def __init__(self, files: FileManager):
        self.files = files

    def analyze(
        self,
        path: str | os.PathLike[str],
        *,
        query: str = "",
        summary_sentences: int = 5,
    ) -> DocumentAnalysis:
        preview = self.files.preview(path)
        text = preview.text
        limitations: list[str] = []
        if not text:
            if preview.kind == "pdf":
                limitations.append(
                    "PDF pages can be displayed, but text extraction is unavailable "
                    "without an installed PDF text backend."
                )
            elif preview.kind in {"audio", "video", "image"}:
                limitations.append(
                    f"{preview.kind.title()} metadata is available; transcription or "
                    "OCR is not installed."
                )
            elif not preview.available:
                limitations.append(preview.reason)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        tokens = set(_tokenize(query))
        ranked_lines = sorted(
            enumerate(lines, start=1),
            key=lambda item: (
                len(tokens.intersection(_tokenize(item[1]))),
                -item[0],
            ),
            reverse=True,
        )
        selected = (
            ranked_lines[: max(1, min(summary_sentences, 20))]
            if tokens
            else list(enumerate(lines[: max(1, min(summary_sentences, 20))], start=1))
        )
        selected.sort(key=lambda item: item[0])
        summary = " ".join(line for _number, line in selected)[:8_000]
        entity_pattern = re.compile(
            r"\b(?:[A-Z][A-Za-z0-9.-]+(?:[ \t]+[A-Z][A-Za-z0-9.-]+){0,4})\b"
        )
        entities = tuple(
            dict.fromkeys(
                match.group(0)
                for match in entity_pattern.finditer(text[:500_000])
                if len(match.group(0)) >= 3
            )
        )[:200]
        formula_pattern = re.compile(
            r"(?:^|[\s,;])([A-Za-z][A-Za-z0-9_]*(?:\([^)]*\))?\s*=\s*[^\n,;]{1,180})"
        )
        formulas = tuple(
            dict.fromkeys(
                match.group(1).strip()
                for match in formula_pattern.finditer(text[:500_000])
            )
        )[:100]
        tables: list[tuple[tuple[str, ...], ...]] = []
        if preview.kind == "csv" and text:
            rows = tuple(
                tuple(cell for cell in row[:100])
                for row in list(csv.reader(text.splitlines()))[:500]
            )
            if rows:
                tables.append(rows)
        citations = tuple(
            DocumentCitation(preview.path, number, line[:500])
            for number, line in selected
        )
        return DocumentAnalysis(
            preview.path,
            preview.kind,
            summary,
            entities,
            formulas,
            tuple(tables),
            citations,
            bool(text),
            tuple(item for item in limitations if item),
        )

    def search(
        self,
        paths: Iterable[str | os.PathLike[str]],
        query: str,
        *,
        limit: int = 30,
    ) -> list[DocumentCitation]:
        tokens = set(_tokenize(query))
        if not tokens:
            return []
        scored: list[tuple[int, DocumentCitation]] = []
        for path in list(paths)[:100]:
            try:
                preview = self.files.preview(path)
            except (OSError, ValueError):
                continue
            for number, line in enumerate(preview.text.splitlines(), start=1):
                clean = line.strip()
                if not clean:
                    continue
                score = len(tokens.intersection(_tokenize(clean)))
                if score:
                    scored.append(
                        (score, DocumentCitation(preview.path, number, clean[:500]))
                    )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [citation for _score, citation in scored[: max(1, min(limit, 200))]]


@dataclass(frozen=True)
class MultimodalAttachment:
    attachment_id: str
    path: str
    kind: str
    size: int
    available: bool
    reason: str = ""


class MultimodalContextManager:
    """Tracks multiple local attachments without loading unbounded blobs into RAM."""

    def __init__(self, files: FileManager, documents: DocumentManager):
        self.files = files
        self.documents = documents
        self._attachments: dict[str, MultimodalAttachment] = {}
        self._lock = threading.RLock()

    def attach(
        self,
        paths: Iterable[str | os.PathLike[str]],
        *,
        max_items: int = 32,
        max_total_bytes: int = 512 * 1024 * 1024,
    ) -> list[MultimodalAttachment]:
        added: list[MultimodalAttachment] = []
        total = sum(item.size for item in self._attachments.values())
        for value in paths:
            if len(self._attachments) >= max(1, min(max_items, 100)):
                break
            try:
                preview = self.files.preview(value)
            except (OSError, ValueError) as exc:
                path = str(Path(value).expanduser())
                item = MultimodalAttachment(
                    uuid.uuid4().hex, path, "unknown", 0, False, str(exc)
                )
                added.append(item)
                continue
            if total + preview.metadata.size > max_total_bytes:
                item = MultimodalAttachment(
                    uuid.uuid4().hex,
                    preview.path,
                    preview.kind,
                    preview.metadata.size,
                    False,
                    "Attachment set exceeds the configured size limit.",
                )
                added.append(item)
                continue
            item = MultimodalAttachment(
                uuid.uuid4().hex,
                preview.path,
                preview.kind,
                preview.metadata.size,
                preview.available,
                preview.reason,
            )
            with self._lock:
                self._attachments[item.attachment_id] = item
            total += item.size
            added.append(item)
        return added

    def list(self) -> list[MultimodalAttachment]:
        with self._lock:
            return list(self._attachments.values())

    def remove(self, attachment_id: str) -> bool:
        with self._lock:
            return self._attachments.pop(attachment_id, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._attachments.clear()

    def cross_reference(self, query: str) -> list[DocumentCitation]:
        with self._lock:
            paths = [
                item.path
                for item in self._attachments.values()
                if item.available
            ]
        return self.documents.search(paths, query)


@dataclass(frozen=True)
class ClipboardItem:
    item_id: str
    kind: str
    text: str
    created_at: str
    pinned: bool = False


class ClipboardManager:
    def __init__(self, permissions: DesktopPermissionManager):
        self.permissions = permissions
        self.enabled = False
        self._items: deque[ClipboardItem] = deque(maxlen=MAX_CLIPBOARD_ITEMS)
        self._lock = threading.RLock()

    def request_monitoring(self) -> PermissionGrant:
        return self.permissions.request(
            "clipboard.monitor",
            {"enabled": True},
            description="Allow MORICE to observe clipboard changes for this session",
        )

    def enable(self, permission_token: str) -> None:
        if not self.permissions.consume(
            permission_token, "clipboard.monitor", {"enabled": True}
        ):
            raise PermissionError("Clipboard monitoring requires explicit approval.")
        self.enabled = True

    def disable(self, *, clear: bool = False) -> None:
        self.enabled = False
        if clear:
            with self._lock:
                self._items.clear()

    @staticmethod
    def classify(text: str) -> str:
        clean = text.strip()
        if re.match(r"^https?://\S+$", clean, flags=re.IGNORECASE):
            return "url"
        if "\t" in clean and "\n" in clean:
            return "table"
        if re.search(r"(^|\n)\s*(def |class |function |const |let |import |#include)", clean):
            return "code"
        if "\n" in clean and "," in clean:
            return "table"
        return "text"

    def observe(self, text: str) -> ClipboardItem | None:
        clean = _clean_text(text, 50_000)
        if not self.enabled or not clean:
            return None
        with self._lock:
            for existing in self._items:
                if existing.text == clean:
                    return existing
            item = ClipboardItem(uuid.uuid4().hex, self.classify(clean), clean, _utc_now())
            self._items.appendleft(item)
            return item

    def history(self, query: str = "") -> list[ClipboardItem]:
        needle = query.casefold().strip()
        with self._lock:
            return [
                item
                for item in self._items
                if not needle or needle in item.text.casefold() or needle in item.kind
            ]

    def pin(self, item_id: str, pinned: bool = True) -> bool:
        with self._lock:
            values = list(self._items)
            changed = False
            for index, item in enumerate(values):
                if item.item_id == item_id:
                    values[index] = ClipboardItem(
                        item.item_id, item.kind, item.text, item.created_at, pinned
                    )
                    changed = True
                    break
            if changed:
                values.sort(key=lambda item: (item.pinned, item.created_at), reverse=True)
                self._items = deque(values, maxlen=MAX_CLIPBOARD_ITEMS)
            return changed


@dataclass(frozen=True)
class DesktopNotification:
    notification_id: str
    title: str
    message: str
    severity: str
    category: str
    created_at: str
    dismissed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class NotificationManager:
    def __init__(self, directory: Path):
        self.path = directory / "notifications.json"
        self._lock = threading.RLock()
        self._listeners: list[Callable[[DesktopNotification], None]] = []
        values = _read_json(self.path, [])
        self._items: list[DesktopNotification] = []
        for value in values[-MAX_NOTIFICATION_ITEMS:]:
            if not isinstance(value, dict):
                continue
            try:
                self._items.append(
                    DesktopNotification(
                        _clean_text(value.get("notification_id"), 64) or uuid.uuid4().hex,
                        _clean_text(value.get("title"), 160),
                        _clean_text(value.get("message"), 4_000),
                        value.get("severity")
                        if value.get("severity") in {"info", "success", "warning", "error"}
                        else "info",
                        _clean_text(value.get("category"), 80) or "general",
                        _clean_text(value.get("created_at"), 64) or _utc_now(),
                        bool(value.get("dismissed", False)),
                        dict(value.get("metadata", {}))
                        if isinstance(value.get("metadata"), dict)
                        else {},
                    )
                )
            except (TypeError, ValueError):
                continue

    def publish(
        self,
        title: str,
        message: str,
        *,
        severity: str = "info",
        category: str = "general",
        metadata: Mapping[str, Any] | None = None,
    ) -> DesktopNotification:
        level = severity if severity in {"info", "success", "warning", "error"} else "info"
        try:
            safe_metadata = _json_mapping(
                metadata,
                label="Notification metadata",
                max_bytes=32_768,
            )
        except ValueError:
            safe_metadata = {}
        item = DesktopNotification(
            uuid.uuid4().hex,
            _clean_text(title, 160) or "MORICE",
            _clean_text(message, 4_000),
            level,
            _clean_text(category, 80) or "general",
            _utc_now(),
            metadata=safe_metadata,
        )
        with self._lock:
            self._items.append(item)
            self._items = self._items[-MAX_NOTIFICATION_ITEMS:]
            self._save()
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(item)
            except Exception:
                continue
        return item

    def dismiss(self, notification_id: str) -> bool:
        with self._lock:
            changed = False
            updated: list[DesktopNotification] = []
            for item in self._items:
                if item.notification_id == notification_id and not item.dismissed:
                    item = DesktopNotification(**{**asdict(item), "dismissed": True})
                    changed = True
                updated.append(item)
            self._items = updated
            if changed:
                self._save()
            return changed

    def history(
        self, *, include_dismissed: bool = True, limit: int = 200
    ) -> list[DesktopNotification]:
        with self._lock:
            values = [
                item
                for item in self._items
                if include_dismissed or not item.dismissed
            ]
            return values[-max(1, min(limit, MAX_NOTIFICATION_ITEMS)) :][::-1]

    def subscribe(self, callback: Callable[[DesktopNotification], None]) -> None:
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def _save(self) -> None:
        _atomic_json_write(self.path, [asdict(item) for item in self._items])


class MediaManager:
    SUPPORTED_ACTIONS = {
        "play-pause",
        "next",
        "previous",
        "mute",
        "volume-down",
        "volume-up",
    }

    def __init__(self, permissions: DesktopPermissionManager):
        self.permissions = permissions

    def request(self, action: str) -> PermissionGrant:
        if action not in self.SUPPORTED_ACTIONS:
            raise ValueError(f"Unsupported media action: {action}")
        return self.permissions.request(
            "media.control",
            {"action": action},
            description=f"Send the global media command {action}",
        )

    def control(self, action: str, permission_token: str) -> str:
        if action not in self.SUPPORTED_ACTIONS:
            raise ValueError(f"Unsupported media action: {action}")
        if not self.permissions.consume(
            permission_token, "media.control", {"action": action}
        ):
            raise PermissionError("Media control requires explicit approval.")
        return execute_desktop_action(DesktopAction("media", argument=action))

    @staticmethod
    def status() -> dict[str, Any]:
        return {
            "globalControls": os.name == "nt",
            "currentTrack": None,
            "playbackPosition": None,
            "reason": (
                "Global media transport metadata is not available through the "
                "current standard-library backend."
            ),
        }


@dataclass(frozen=True)
class MonitorSample:
    captured_at: str
    cpu_percent: float | None
    memory_total_gb: float
    memory_available_gb: float
    memory_percent: float | None
    gpu_percent: float | None
    vram_used_mb: float | None
    vram_total_mb: float | None
    storage_total_gb: float
    storage_free_gb: float
    battery_percent: int | None
    battery_charging: bool | None
    process_count: int
    thread_count: int
    temperature_c: float | None = None
    network_bytes_per_second: float | None = None


class SystemMonitor:
    def __init__(self):
        self._last_cpu: tuple[int, int] | None = None
        self._listeners: list[Callable[[MonitorSample], None]] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

    def _cpu_percent(self) -> float | None:
        if os.name != "nt":
            return None
        idle = ctypes.c_ulonglong()
        kernel = ctypes.c_ulonglong()
        user = ctypes.c_ulonglong()
        if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None
        idle_value = idle.value
        total_value = kernel.value + user.value
        current = (idle_value, total_value)
        previous = self._last_cpu
        self._last_cpu = current
        if previous is None:
            return None
        idle_delta = idle_value - previous[0]
        total_delta = total_value - previous[1]
        if total_delta <= 0:
            return None
        return max(0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta)))

    @staticmethod
    def _gpu() -> tuple[float | None, float | None, float | None]:
        executable = shutil.which("nvidia-smi")
        if not executable:
            return None, None, None
        try:
            completed = subprocess.run(
                [
                    executable,
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=4,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            first = completed.stdout.splitlines()[0].split(",")
            if len(first) < 3:
                return None, None, None
            return (
                float(first[0].strip()),
                float(first[1].strip()),
                float(first[2].strip()),
            )
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return None, None, None

    def sample(self) -> MonitorSample:
        snapshot = collect_system_snapshot()
        gpu_percent, vram_used, vram_total = self._gpu()
        used_memory = snapshot.memory_total_gb - snapshot.memory_available_gb
        memory_percent = (
            100.0 * used_memory / snapshot.memory_total_gb
            if snapshot.memory_total_gb > 0
            else None
        )
        return MonitorSample(
            _utc_now(),
            self._cpu_percent(),
            snapshot.memory_total_gb,
            snapshot.memory_available_gb,
            memory_percent,
            gpu_percent,
            vram_used,
            vram_total,
            snapshot.storage_total_gb,
            snapshot.storage_free_gb,
            snapshot.battery_percent,
            snapshot.battery_charging,
            len(ApplicationManager.list_processes()),
            threading.active_count(),
        )

    def subscribe(
        self, callback: Callable[[MonitorSample], None], *, interval_seconds: float = 2.0
    ) -> None:
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()

            def run() -> None:
                while not self._stop.wait(max(0.5, min(interval_seconds, 60.0))):
                    try:
                        sample = self.sample()
                    except Exception:
                        continue
                    with self._lock:
                        listeners = tuple(self._listeners)
                    for listener in listeners:
                        try:
                            listener(sample)
                        except Exception:
                            continue

            self._thread = threading.Thread(
                target=run, name="morice-system-monitor", daemon=True
            )
            self._thread.start()

    def unsubscribe(self, callback: Callable[[MonitorSample], None]) -> None:
        with self._lock:
            self._listeners = [
                listener for listener in self._listeners if listener is not callback
            ]
            should_stop = not self._listeners
        if should_stop:
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self._thread = None


@dataclass(frozen=True)
class ScreenshotResult:
    path: str
    width: int
    height: int
    mode: str
    captured_at: str


class ScreenshotManager:
    def __init__(
        self,
        directory: Path,
        permissions: DesktopPermissionManager,
        windows: WindowManager,
    ):
        self.directory = directory / "screenshots"
        self.permissions = permissions
        self.windows = windows

    def request(
        self,
        mode: str,
        *,
        region: tuple[int, int, int, int] | None = None,
        window_handle: int | None = None,
        delay_seconds: float = 0,
        annotation: str = "",
    ) -> PermissionGrant:
        payload = {
            "mode": mode,
            "region": region,
            "windowHandle": window_handle,
            "delaySeconds": float(delay_seconds),
            "annotation": _clean_text(annotation, 500),
        }
        return self.permissions.request(
            "screenshot.capture",
            payload,
            description=f"Capture a {mode} screenshot",
        )

    def capture(
        self,
        mode: str,
        permission_token: str,
        *,
        region: tuple[int, int, int, int] | None = None,
        window_handle: int | None = None,
        delay_seconds: float = 0,
        annotation: str = "",
    ) -> ScreenshotResult:
        payload = {
            "mode": mode,
            "region": region,
            "windowHandle": window_handle,
            "delaySeconds": float(delay_seconds),
            "annotation": _clean_text(annotation, 500),
        }
        if not self.permissions.consume(
            permission_token, "screenshot.capture", payload
        ):
            raise PermissionError("Screenshot capture requires exact approval.")
        try:
            from PIL import ImageDraw, ImageGrab
        except ImportError as exc:
            raise RuntimeError("Pillow is required for screenshot capture.") from exc
        delay = max(0.0, min(float(delay_seconds), 30.0))
        if delay:
            time.sleep(delay)
        if mode == "clipboard":
            image = ImageGrab.grabclipboard()
            if image is None or not hasattr(image, "save"):
                raise RuntimeError("The clipboard does not contain a capturable image.")
        else:
            bbox = None
            if mode == "region":
                if not region or region[2] <= region[0] or region[3] <= region[1]:
                    raise ValueError("A valid region is required.")
                bbox = region
            elif mode == "window":
                window = next(
                    (
                        item
                        for item in self.windows.list_windows()
                        if item.handle == int(window_handle or 0)
                    ),
                    None,
                )
                if window is None:
                    raise ValueError("The selected window is unavailable.")
                bbox = window.rect
            elif mode != "full":
                raise ValueError("Screenshot mode must be full, window, region, or clipboard.")
            image = ImageGrab.grab(bbox=bbox, all_screens=mode == "full")
        if annotation:
            draw = ImageDraw.Draw(image)
            draw.rectangle((8, 8, image.width - 8, 48), fill=(0, 0, 0, 190))
            draw.text((16, 18), _clean_text(annotation, 500), fill=(255, 255, 255))
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / (
            f"MORICE-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.png"
        )
        image.save(target, "PNG")
        if not target.is_file() or target.stat().st_size <= 0:
            raise RuntimeError("Screenshot validation failed.")
        return ScreenshotResult(
            str(target),
            int(image.width),
            int(image.height),
            mode,
            _utc_now(),
        )


@dataclass
class MemoryRecord:
    memory_id: str
    scope: str
    content: str
    created_at: str
    updated_at: str
    project_id: str = ""
    tags: list[str] = field(default_factory=list)
    pinned: bool = False
    archived: bool = False
    temporary: bool = False


class MemoryManager:
    SCOPES = {
        "conversation",
        "session",
        "project",
        "user",
        "temporary",
        "retrieved",
        "archived",
    }

    def __init__(self, directory: Path):
        self.path = directory / "memory.json"
        self.enabled = True
        self._lock = threading.RLock()
        data = _read_json(self.path, {})
        self.enabled = bool(data.get("enabled", True))
        self._records: list[MemoryRecord] = []
        for value in data.get("records", [])[-MAX_MEMORY_RECORDS:]:
            if not isinstance(value, dict):
                continue
            scope = value.get("scope")
            content = _clean_text(value.get("content"), 64_000)
            if scope not in self.SCOPES or not content:
                continue
            self._records.append(
                MemoryRecord(
                    _clean_text(value.get("memory_id"), 64) or uuid.uuid4().hex,
                    scope,
                    content,
                    _clean_text(value.get("created_at"), 64) or _utc_now(),
                    _clean_text(value.get("updated_at"), 64) or _utc_now(),
                    _clean_text(value.get("project_id"), 2_048),
                    [
                        _clean_text(tag, 80)
                        for tag in value.get("tags", [])
                        if _clean_text(tag, 80)
                    ][:30],
                    bool(value.get("pinned", False)),
                    bool(value.get("archived", False)),
                    bool(value.get("temporary", False)),
                )
            )

    def add(
        self,
        scope: str,
        content: str,
        *,
        project_id: str = "",
        tags: Iterable[str] = (),
        pinned: bool = False,
        temporary: bool = False,
    ) -> MemoryRecord:
        if not self.enabled:
            raise RuntimeError("Memory is disabled.")
        if scope not in self.SCOPES:
            raise ValueError(f"Unsupported memory scope: {scope}")
        clean = _clean_text(content, 64_000)
        if not clean:
            raise ValueError("Memory content cannot be empty.")
        now = _utc_now()
        record = MemoryRecord(
            uuid.uuid4().hex,
            scope,
            clean,
            now,
            now,
            _clean_text(project_id, 2_048),
            list(dict.fromkeys(_clean_text(tag, 80) for tag in tags if _clean_text(tag, 80)))[:30],
            pinned,
            False,
            temporary or scope == "temporary",
        )
        with self._lock:
            self._records.append(record)
            self._enforce_bounds()
            self._save()
        return record

    def retrieve(
        self,
        query: str,
        *,
        project_id: str = "",
        scopes: Iterable[str] = (),
        limit: int = 20,
    ) -> list[MemoryRecord]:
        if not self.enabled:
            return []
        tokens = set(_tokenize(query))
        allowed = set(scopes)
        scored: list[tuple[float, MemoryRecord]] = []
        with self._lock:
            records = tuple(self._records)
        for record in records:
            if record.archived or (allowed and record.scope not in allowed):
                continue
            content_tokens = set(_tokenize(record.content + " " + " ".join(record.tags)))
            overlap = len(tokens.intersection(content_tokens))
            score = overlap * 10.0
            if project_id and record.project_id == project_id:
                score += 15.0
            if record.pinned:
                score += 4.0
            if not tokens:
                score += 1.0
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [record for _score, record in scored[: max(1, min(limit, 100))]]

    def search(self, query: str, *, include_archived: bool = True) -> list[MemoryRecord]:
        needle = query.casefold().strip()
        with self._lock:
            return [
                record
                for record in reversed(self._records)
                if (include_archived or not record.archived)
                and (
                    not needle
                    or needle in record.content.casefold()
                    or any(needle in tag.casefold() for tag in record.tags)
                )
            ]

    def update(
        self,
        memory_id: str,
        *,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> bool:
        with self._lock:
            for record in self._records:
                if record.memory_id != memory_id:
                    continue
                if pinned is not None:
                    record.pinned = bool(pinned)
                if archived is not None:
                    record.archived = bool(archived)
                    if archived:
                        record.scope = "archived"
                record.updated_at = _utc_now()
                self._save()
                return True
        return False

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            original = len(self._records)
            self._records = [
                record for record in self._records if record.memory_id != memory_id
            ]
            changed = len(self._records) != original
            if changed:
                self._save()
            return changed

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self._save()

    def export(self, path: str | os.PathLike[str]) -> Path:
        target = _safe_path(path)
        _atomic_json_write(
            target,
            {
                "version": DESKTOP_STATE_VERSION,
                "exportedAt": _utc_now(),
                "records": [asdict(record) for record in self._records if not record.temporary],
            },
        )
        return target

    def import_file(self, path: str | os.PathLike[str]) -> int:
        data = _read_json(_safe_path(path), {})
        imported = 0
        for value in data.get("records", [])[:MAX_MEMORY_RECORDS]:
            if not isinstance(value, dict):
                continue
            try:
                self.add(
                    str(value.get("scope", "user")),
                    str(value.get("content", "")),
                    project_id=str(value.get("project_id", "")),
                    tags=value.get("tags", ()),
                    pinned=bool(value.get("pinned", False)),
                )
                imported += 1
            except (TypeError, ValueError, RuntimeError):
                continue
        return imported

    def clear_temporary(self) -> None:
        with self._lock:
            self._records = [record for record in self._records if not record.temporary]
            self._save()

    def _enforce_bounds(self) -> None:
        if len(self._records) <= MAX_MEMORY_RECORDS:
            return
        retained = [record for record in self._records if record.pinned]
        unpinned = [record for record in self._records if not record.pinned]
        room = max(0, MAX_MEMORY_RECORDS - len(retained))
        self._records = (retained + unpinned[-room:])[-MAX_MEMORY_RECORDS:]

    def _save(self) -> None:
        with self._lock:
            _atomic_json_write(
                self.path,
                {
                    "version": DESKTOP_STATE_VERSION,
                    "enabled": self.enabled,
                    "records": [
                        asdict(record)
                        for record in self._records
                        if not record.temporary
                    ],
                },
            )


@dataclass
class ProjectWorkspace:
    project_id: str
    name: str
    root: str
    created_at: str
    updated_at: str
    tasks: list[str] = field(default_factory=list)
    open_editors: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    benchmarks: list[dict[str, Any]] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    build_status: str = "unknown"
    git_status: str = ""
    renderer_status: str = "idle"
    terminal_directory: str = ""


class WorkspaceManager:
    def __init__(self, directory: Path):
        self.path = directory / "projects.json"
        self._lock = threading.RLock()
        self._projects: dict[str, ProjectWorkspace] = {}
        data = _read_json(self.path, {})
        for value in data.get("projects", [])[:200]:
            if not isinstance(value, dict):
                continue
            root = _clean_text(value.get("root"), 2_048)
            if not root:
                continue
            workspace = ProjectWorkspace(
                _clean_text(value.get("project_id"), 64) or uuid.uuid4().hex,
                _clean_text(value.get("name"), 160) or Path(root).name,
                root,
                _clean_text(value.get("created_at"), 64) or _utc_now(),
                _clean_text(value.get("updated_at"), 64) or _utc_now(),
                [_clean_text(item, 1_000) for item in value.get("tasks", [])][-200:],
                [_clean_text(item, 2_048) for item in value.get("open_editors", [])][-50:],
                [_clean_text(item, 2_048) for item in value.get("recent_changes", [])][-200:],
                [_clean_text(item, 2_048) for item in value.get("screenshots", [])][-100:],
                [dict(item) for item in value.get("benchmarks", []) if isinstance(item, dict)][-100:],
                [_clean_text(item, 4_000) for item in value.get("logs", [])][-500:],
                _clean_text(value.get("build_status"), 80) or "unknown",
                _clean_text(value.get("git_status"), 20_000),
                _clean_text(value.get("renderer_status"), 80) or "idle",
                _clean_text(value.get("terminal_directory"), 2_048) or root,
            )
            self._projects[workspace.project_id] = workspace

    def register(self, root: str, *, name: str = "") -> ProjectWorkspace:
        target = _safe_path(root)
        if not target.is_dir():
            raise NotADirectoryError(str(target))
        clean_root = str(target)
        with self._lock:
            existing = next(
                (
                    project
                    for project in self._projects.values()
                    if os.path.normcase(project.root) == os.path.normcase(clean_root)
                ),
                None,
            )
            if existing:
                existing.updated_at = _utc_now()
                self._save()
                return existing
            now = _utc_now()
            project = ProjectWorkspace(
                uuid.uuid4().hex,
                _clean_text(name, 160) or target.name,
                clean_root,
                now,
                now,
                terminal_directory=clean_root,
            )
            self._projects[project.project_id] = project
            self.refresh_status(project.project_id)
            self._save()
            return project

    def get(self, project_id: str) -> ProjectWorkspace | None:
        with self._lock:
            return self._projects.get(project_id)

    def list(self) -> list[ProjectWorkspace]:
        with self._lock:
            return sorted(
                self._projects.values(), key=lambda item: item.updated_at, reverse=True
            )

    def update(self, project_id: str, **values: Any) -> ProjectWorkspace:
        allowed = {
            "tasks",
            "open_editors",
            "recent_changes",
            "screenshots",
            "benchmarks",
            "logs",
            "build_status",
            "git_status",
            "renderer_status",
            "terminal_directory",
        }
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                raise KeyError(project_id)
            for key, value in values.items():
                if key in allowed:
                    setattr(project, key, value)
            project.tasks = project.tasks[-200:]
            project.open_editors = project.open_editors[-50:]
            project.recent_changes = project.recent_changes[-200:]
            project.screenshots = project.screenshots[-100:]
            project.benchmarks = project.benchmarks[-100:]
            project.logs = project.logs[-500:]
            project.updated_at = _utc_now()
            self._save()
            return project

    def refresh_status(self, project_id: str) -> ProjectWorkspace:
        project = self.get(project_id)
        if project is None:
            raise KeyError(project_id)
        root = Path(project.root)
        git_status = ""
        if (root / ".git").exists() and shutil.which("git"):
            try:
                completed = subprocess.run(
                    ["git", "status", "--short", "--branch"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=10,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                git_status = completed.stdout[:20_000]
            except (OSError, subprocess.SubprocessError):
                git_status = ""
        project.git_status = git_status
        project.updated_at = _utc_now()
        self._save()
        return project

    def _save(self) -> None:
        _atomic_json_write(
            self.path,
            {
                "version": DESKTOP_STATE_VERSION,
                "projects": [asdict(project) for project in self._projects.values()],
            },
        )


@dataclass
class SessionState:
    session_id: str
    saved_at: str
    chats: list[str] = field(default_factory=list)
    project_ids: list[str] = field(default_factory=list)
    editors: list[str] = field(default_factory=list)
    windows: list[dict[str, Any]] = field(default_factory=list)
    tabs: list[str] = field(default_factory=list)
    renderers: list[str] = field(default_factory=list)
    terminals: list[str] = field(default_factory=list)
    pending_tasks: list[str] = field(default_factory=list)
    memory_context: list[str] = field(default_factory=list)


class SessionManager:
    def __init__(self, directory: Path):
        self.path = directory / "session.json"
        self._lock = threading.RLock()

    def save(self, state: SessionState) -> None:
        safe = SessionState(
            state.session_id or uuid.uuid4().hex,
            _utc_now(),
            [_clean_text(item, 2_000) for item in state.chats][-100:],
            [_clean_text(item, 64) for item in state.project_ids][-100:],
            [_clean_text(item, 2_048) for item in state.editors][-100:],
            [dict(item) for item in state.windows if isinstance(item, dict)][-50:],
            [_clean_text(item, 200) for item in state.tabs][-100:],
            [_clean_text(item, 200) for item in state.renderers][-100:],
            [_clean_text(item, 2_048) for item in state.terminals][-50:],
            [_clean_text(item, 1_000) for item in state.pending_tasks][-200:],
            [_clean_text(item, 64) for item in state.memory_context][-200:],
        )
        with self._lock:
            _atomic_json_write(
                self.path,
                {"version": DESKTOP_STATE_VERSION, "state": asdict(safe)},
            )

    def load(self) -> SessionState | None:
        data = _read_json(self.path, {})
        value = data.get("state")
        if not isinstance(value, dict):
            return None
        try:
            return SessionState(
                _clean_text(value.get("session_id"), 64) or uuid.uuid4().hex,
                _clean_text(value.get("saved_at"), 64) or _utc_now(),
                [_clean_text(item, 2_000) for item in value.get("chats", [])][-100:],
                [_clean_text(item, 64) for item in value.get("project_ids", [])][-100:],
                [_clean_text(item, 2_048) for item in value.get("editors", [])][-100:],
                [dict(item) for item in value.get("windows", []) if isinstance(item, dict)][-50:],
                [_clean_text(item, 200) for item in value.get("tabs", [])][-100:],
                [_clean_text(item, 200) for item in value.get("renderers", [])][-100:],
                [_clean_text(item, 2_048) for item in value.get("terminals", [])][-50:],
                [_clean_text(item, 1_000) for item in value.get("pending_tasks", [])][-200:],
                [_clean_text(item, 64) for item in value.get("memory_context", [])][-200:],
            )
        except (TypeError, ValueError):
            return None

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


@dataclass
class AutomationWorkflow:
    workflow_id: str
    name: str
    event: str
    action: str
    action_arguments: dict[str, Any]
    conditions: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    enabled: bool = False
    delay_seconds: float = 0
    repeat_count: int = 1
    last_run_at: str = ""
    run_count: int = 0


class AutomationEngine:
    """Runs registered actions only; it never evaluates user code or shell text."""

    def __init__(
        self,
        directory: Path,
        permissions: DesktopPermissionManager,
        notifications: NotificationManager,
    ):
        self.path = directory / "automations.json"
        self.permissions = permissions
        self.notifications = notifications
        self._actions: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._lock = threading.RLock()
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self._workflows: dict[str, AutomationWorkflow] = {}
        data = _read_json(self.path, {})
        for value in data.get("workflows", [])[:200]:
            if not isinstance(value, dict):
                continue
            action = _clean_text(value.get("action"), 120)
            event = _clean_text(value.get("event"), 120)
            if not action or not event:
                continue
            workflow = AutomationWorkflow(
                workflow_id=_clean_text(value.get("workflow_id"), 64)
                or uuid.uuid4().hex,
                name=_clean_text(value.get("name"), 160) or action,
                event=event,
                action=action,
                action_arguments=(
                    dict(value.get("action_arguments", {}))
                    if isinstance(value.get("action_arguments"), dict)
                    else {}
                ),
                conditions=(
                    dict(value.get("conditions", {}))
                    if isinstance(value.get("conditions"), dict)
                    else {}
                ),
                variables=(
                    dict(value.get("variables", {}))
                    if isinstance(value.get("variables"), dict)
                    else {}
                ),
                enabled=bool(value.get("enabled", False)),
                delay_seconds=max(
                    0.0, min(float(value.get("delay_seconds", 0)), 86_400.0)
                ),
                repeat_count=max(1, min(int(value.get("repeat_count", 1)), 20)),
                last_run_at=_clean_text(value.get("last_run_at"), 64),
                run_count=max(0, int(value.get("run_count", 0))),
            )
            self._workflows[workflow.workflow_id] = workflow

    def register_action(
        self, action_id: str, callback: Callable[[dict[str, Any]], Any]
    ) -> None:
        clean = _clean_text(action_id, 120)
        if not clean:
            raise ValueError("Action id cannot be empty.")
        self._actions[clean] = callback

    def create(
        self,
        name: str,
        event: str,
        action: str,
        *,
        arguments: Mapping[str, Any] | None = None,
        conditions: Mapping[str, Any] | None = None,
        variables: Mapping[str, Any] | None = None,
        delay_seconds: float = 0,
        repeat_count: int = 1,
    ) -> AutomationWorkflow:
        if action not in self._actions:
            raise ValueError("Automation action is not registered.")
        safe_arguments = _json_mapping(
            arguments,
            label="Automation arguments",
        )
        safe_conditions = _json_mapping(
            conditions,
            label="Automation conditions",
        )
        safe_variables = _json_mapping(
            variables,
            label="Automation variables",
        )
        workflow = AutomationWorkflow(
            workflow_id=uuid.uuid4().hex,
            name=_clean_text(name, 160) or action,
            event=_clean_text(event, 120),
            action=action,
            action_arguments=safe_arguments,
            conditions=safe_conditions,
            variables=safe_variables,
            enabled=False,
            delay_seconds=max(0.0, min(float(delay_seconds), 86_400.0)),
            repeat_count=max(1, min(int(repeat_count), 20)),
        )
        if not workflow.event:
            raise ValueError("Automation event cannot be empty.")
        with self._lock:
            self._workflows[workflow.workflow_id] = workflow
            self._save()
        return workflow

    def request_enable(self, workflow_id: str) -> PermissionGrant:
        workflow = self._workflows.get(workflow_id)
        if workflow is None:
            raise KeyError(workflow_id)
        return self.permissions.request(
            "automation.enable",
            {"workflowId": workflow_id},
            description=f"Enable automation: {workflow.name}",
        )

    def enable(self, workflow_id: str, permission_token: str) -> None:
        if not self.permissions.consume(
            permission_token, "automation.enable", {"workflowId": workflow_id}
        ):
            raise PermissionError("Enabling this automation requires explicit approval.")
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                raise KeyError(workflow_id)
            workflow.enabled = True
            self._save()

    def disable(self, workflow_id: str) -> None:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow:
                workflow.enabled = False
                self._save()

    def trigger(self, event: str, context: Mapping[str, Any] | None = None) -> list[Any]:
        context_values = dict(context or {})
        with self._lock:
            workflows = [
                workflow
                for workflow in self._workflows.values()
                if workflow.enabled
                and workflow.event == event
                and self._conditions_match(workflow.conditions, context_values)
            ]
        results: list[Any] = []
        for workflow in workflows:
            callback = self._actions.get(workflow.action)
            if callback is None:
                self.notifications.publish(
                    "Automation failed",
                    f"{workflow.name}: action is no longer registered.",
                    severity="error",
                    category="automation",
                )
                continue
            if workflow.delay_seconds:
                time.sleep(workflow.delay_seconds)
            for _index in range(workflow.repeat_count):
                variables = {**workflow.variables, **context_values}
                arguments = self._substitute(workflow.action_arguments, variables)
                arguments["context"] = context_values
                try:
                    results.append(callback(arguments))
                except Exception as exc:
                    self.notifications.publish(
                        "Automation failed",
                        f"{workflow.name}: {exc}",
                        severity="error",
                        category="automation",
                    )
                    break
            workflow.last_run_at = _utc_now()
            workflow.run_count += 1
        if workflows:
            self._save()
        return results

    @staticmethod
    def _conditions_match(
        conditions: Mapping[str, Any], context: Mapping[str, Any]
    ) -> bool:
        for key, expected in conditions.items():
            if context.get(key) != expected:
                return False
        return True

    @classmethod
    def _substitute(cls, value: Any, variables: Mapping[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: cls._substitute(item, variables) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._substitute(item, variables) for item in value]
        if not isinstance(value, str):
            return value
        result = value
        for key, replacement in variables.items():
            result = result.replace("${" + str(key) + "}", str(replacement))
        return result

    def run_due(self, now: datetime | None = None) -> list[Any]:
        current = now or datetime.now().astimezone()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        due_events: list[str] = []
        with self._lock:
            workflows = tuple(self._workflows.values())
        for workflow in workflows:
            if not workflow.enabled or not workflow.event.startswith("schedule:"):
                continue
            parts = workflow.event.split(":")
            due = False
            last = None
            if workflow.last_run_at:
                try:
                    last = datetime.fromisoformat(workflow.last_run_at)
                except ValueError:
                    last = None
            if len(parts) == 3 and parts[1] == "interval":
                try:
                    seconds = max(60, min(int(parts[2]), 31_536_000))
                except ValueError:
                    continue
                due = last is None or (current - last.astimezone(current.tzinfo)).total_seconds() >= seconds
            elif len(parts) == 4 and parts[1] == "daily":
                try:
                    hour, minute = int(parts[2]), int(parts[3])
                except ValueError:
                    continue
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    continue
                due = (
                    current.hour == hour
                    and current.minute == minute
                    and (last is None or last.astimezone(current.tzinfo).date() != current.date())
                )
            if due:
                due_events.append(workflow.event)
        results: list[Any] = []
        for event in dict.fromkeys(due_events):
            results.extend(self.trigger(event, {"scheduledAt": current.isoformat()}))
        return results

    def start_scheduler(self, *, poll_seconds: float = 30.0) -> None:
        with self._lock:
            if self._scheduler_thread and self._scheduler_thread.is_alive():
                return
            self._scheduler_stop.clear()

            def run() -> None:
                while not self._scheduler_stop.wait(
                    max(5.0, min(float(poll_seconds), 300.0))
                ):
                    try:
                        self.run_due()
                    except Exception as exc:
                        self.notifications.publish(
                            "Automation scheduler error",
                            str(exc),
                            severity="error",
                            category="automation",
                        )

            self._scheduler_thread = threading.Thread(
                target=run,
                name="morice-automation-scheduler",
                daemon=True,
            )
            self._scheduler_thread.start()

    def stop_scheduler(self) -> None:
        self._scheduler_stop.set()
        thread = self._scheduler_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self._scheduler_thread = None

    @staticmethod
    def templates() -> tuple[dict[str, Any], ...]:
        return (
            {
                "name": "Notify when a build completes",
                "event": "build.completed",
                "action": "notification.publish",
                "arguments": {
                    "title": "Build complete",
                    "message": "${project} finished building.",
                    "severity": "success",
                },
            },
            {
                "name": "Daily work reminder",
                "event": "schedule:daily:09:00",
                "action": "notification.publish",
                "arguments": {
                    "title": "Daily workspace",
                    "message": "Review open tasks and yesterday's changes.",
                },
            },
        )

    def list(self) -> list[AutomationWorkflow]:
        with self._lock:
            return list(self._workflows.values())

    def _save(self) -> None:
        _atomic_json_write(
            self.path,
            {
                "version": DESKTOP_STATE_VERSION,
                "workflows": [asdict(item) for item in self._workflows.values()],
            },
        )


@dataclass(frozen=True)
class VoiceCapabilities:
    wake_word: bool
    speech_to_text: bool
    text_to_speech: bool
    noise_suppression: bool
    offline: bool
    microphone_selection: bool
    output_device_selection: bool
    details: dict[str, str]


class VoiceManager:
    @staticmethod
    def capabilities() -> VoiceCapabilities:
        try:
            import sounddevice  # noqa: F401

            sounddevice_available = True
        except ImportError:
            sounddevice_available = False
        try:
            import vosk  # noqa: F401

            vosk_available = True
        except ImportError:
            vosk_available = False
        wake_listener = Path(__file__).resolve().parent.parent / "morice_wake_listener.py"
        return VoiceCapabilities(
            wake_word=wake_listener.is_file() and sounddevice_available,
            speech_to_text=vosk_available and sounddevice_available,
            text_to_speech=os.name == "nt",
            noise_suppression=sounddevice_available,
            offline=vosk_available,
            microphone_selection=sounddevice_available,
            output_device_selection=sounddevice_available,
            details={
                "wakeListener": str(wake_listener) if wake_listener.is_file() else "unavailable",
                "speechBackend": "Vosk" if vosk_available else "unavailable",
                "audioBackend": "sounddevice" if sounddevice_available else "unavailable",
                "ttsBackend": "Windows SAPI" if os.name == "nt" else "unavailable",
            },
        )

    @staticmethod
    def devices() -> list[dict[str, Any]]:
        try:
            import sounddevice

            return [
                {
                    "index": index,
                    "name": str(value.get("name", "")),
                    "inputs": int(value.get("max_input_channels", 0)),
                    "outputs": int(value.get("max_output_channels", 0)),
                    "sampleRate": float(value.get("default_samplerate", 0)),
                }
                for index, value in enumerate(sounddevice.query_devices())
            ]
        except (ImportError, OSError, ValueError):
            return []


@dataclass(frozen=True)
class SearchEverywhereResult:
    category: str
    label: str
    detail: str
    action: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchEverywhere:
    def __init__(
        self,
        files: FileManager,
        workspaces: WorkspaceManager,
        memory: MemoryManager,
    ):
        self.files = files
        self.workspaces = workspaces
        self.memory = memory
        self._providers: dict[
            str, Callable[[str], Iterable[SearchEverywhereResult]]
        ] = {}

    def register(
        self,
        category: str,
        provider: Callable[[str], Iterable[SearchEverywhereResult]],
    ) -> None:
        self._providers[_clean_text(category, 80)] = provider

    def search(
        self,
        query: str,
        *,
        roots: Iterable[str | os.PathLike[str]] = (),
        limit: int = 80,
    ) -> list[SearchEverywhereResult]:
        clean = _clean_text(query, 1_000)
        if not clean:
            return []
        results: list[SearchEverywhereResult] = []
        for item in self.files.search(clean, roots, limit=30):
            results.append(
                SearchEverywhereResult(
                    "files",
                    item.metadata.name,
                    item.path,
                    "preview-file",
                    item.score,
                    {"path": item.path},
                )
            )
        for project in self.workspaces.list():
            if clean.casefold() in f"{project.name} {project.root}".casefold():
                results.append(
                    SearchEverywhereResult(
                        "projects",
                        project.name,
                        project.root,
                        "open-project",
                        30.0,
                        {"projectId": project.project_id, "root": project.root},
                    )
                )
        for record in self.memory.retrieve(clean, limit=20):
            results.append(
                SearchEverywhereResult(
                    "memory",
                    record.content[:100],
                    record.scope,
                    "inspect-memory",
                    20.0 + (5.0 if record.pinned else 0.0),
                    {"memoryId": record.memory_id},
                )
            )
        for category, provider in tuple(self._providers.items()):
            try:
                for result in provider(clean):
                    if result.category:
                        results.append(result)
                    else:
                        results.append(
                            SearchEverywhereResult(
                                category,
                                result.label,
                                result.detail,
                                result.action,
                                result.score,
                                result.metadata,
                            )
                        )
            except Exception:
                continue
        results.sort(key=lambda item: item.score, reverse=True)
        return results[: max(1, min(limit, 500))]


class DesktopIntegrationLayer:
    """Owns Phase 3 managers while keeping UI adapters optional and replaceable."""

    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.permissions = DesktopPermissionManager()
        self.notifications = NotificationManager(self.directory)
        self.applications = ApplicationManager(self.directory, self.permissions)
        self.windows = WindowManager(self.permissions)
        self.files = FileManager(self.directory)
        self.documents = DocumentManager(self.files)
        self.multimodal = MultimodalContextManager(self.files, self.documents)
        self.clipboard = ClipboardManager(self.permissions)
        self.media = MediaManager(self.permissions)
        self.system_monitor = SystemMonitor()
        self.screenshots = ScreenshotManager(
            self.directory, self.permissions, self.windows
        )
        self.memory = MemoryManager(self.directory)
        self.workspaces = WorkspaceManager(self.directory)
        self.sessions = SessionManager(self.directory)
        self.automations = AutomationEngine(
            self.directory, self.permissions, self.notifications
        )
        self.voice = VoiceManager()
        self.search = SearchEverywhere(self.files, self.workspaces, self.memory)
        self._register_automation_actions()

    def _register_automation_actions(self) -> None:
        self.automations.register_action(
            "notification.publish",
            lambda arguments: self.notifications.publish(
                str(arguments.get("title", "MORICE automation")),
                str(arguments.get("message", "Automation completed.")),
                severity=str(arguments.get("severity", "info")),
                category="automation",
            ),
        )

    def capabilities(self) -> dict[str, Any]:
        voice = self.voice.capabilities()
        try:
            import PIL  # noqa: F401

            screenshot_available = True
        except ImportError:
            screenshot_available = False
        return {
            "platform": platform.system(),
            "applications": os.name == "nt",
            "windows": os.name == "nt",
            "files": True,
            "previews": {
                "text": True,
                "code": True,
                "json": True,
                "xml": True,
                "csv": True,
                "images": True,
                "pdf": True,
                "audio": True,
                "video": True,
                "officeText": True,
                "archives": True,
            },
            "documentIntelligence": True,
            "multimodalAttachments": True,
            "clipboard": True,
            "notifications": True,
            "mediaControls": os.name == "nt",
            "systemMonitor": True,
            "screenshots": screenshot_available,
            "memory": True,
            "workspaces": True,
            "sessions": True,
            "automations": True,
            "voice": asdict(voice),
            "searchEverywhere": True,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "capabilities": self.capabilities(),
            "permissionRequests": len(self.permissions.pending()),
            "notifications": len(self.notifications.history()),
            "clipboard": {
                "enabled": self.clipboard.enabled,
                "items": len(self.clipboard.history()),
            },
            "projects": len(self.workspaces.list()),
            "attachments": len(self.multimodal.list()),
            "automations": {
                "total": len(self.automations.list()),
                "enabled": sum(1 for item in self.automations.list() if item.enabled),
            },
            "memory": {
                "enabled": self.memory.enabled,
                "records": len(self.memory.search("")),
            },
            "recentApplications": list(self.applications.recent[:10]),
            "pinnedApplications": list(self.applications.pinned[:10]),
        }

    def shutdown(self) -> None:
        self.system_monitor.stop()
        self.automations.stop_scheduler()
        self.permissions.revoke_all()
        self.multimodal.clear()
        self.memory.clear_temporary()


DesktopManager = DesktopIntegrationLayer


__all__ = [
    "ApplicationCandidate",
    "ApplicationManager",
    "AutomationEngine",
    "AutomationWorkflow",
    "ClipboardItem",
    "ClipboardManager",
    "DesktopIntegrationLayer",
    "DesktopManager",
    "DesktopNotification",
    "DesktopPermissionManager",
    "DocumentAnalysis",
    "DocumentCitation",
    "DocumentManager",
    "FileManager",
    "FileMetadata",
    "FileSearchResult",
    "MediaManager",
    "MemoryManager",
    "MemoryRecord",
    "MonitorSample",
    "MultimodalAttachment",
    "MultimodalContextManager",
    "NotificationManager",
    "PermissionGrant",
    "PreviewDescriptor",
    "ProcessInfo",
    "ProjectWorkspace",
    "ScreenshotManager",
    "ScreenshotResult",
    "SearchEverywhere",
    "SearchEverywhereResult",
    "SessionManager",
    "SessionState",
    "SystemMonitor",
    "VoiceCapabilities",
    "VoiceManager",
    "WindowInfo",
    "WindowManager",
    "WorkspaceManager",
]
