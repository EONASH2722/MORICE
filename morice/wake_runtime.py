from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .settings import wake_signal_path


WAKE_SIGNAL_VERSION = 1
VOICE_SESSION_FILENAME = "voice-session.json"
APP_SESSION_FILENAME = "app-session.json"


def _clean_text(value: object, limit: int = 160) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    return text[:limit]


def _trigger_from_source(source: str) -> str:
    lowered = source.casefold()
    if "clap" in lowered:
        return "clap"
    if "magic" in lowered or "phrase" in lowered or "word" in lowered:
        return "phrase"
    return "external"


@dataclass(frozen=True)
class WakeRequest:
    """A versioned, backwards-compatible hand-off from the wake daemon."""

    source: str
    trigger: str = "external"
    enter_live_action: bool = True
    preserve_focus: bool = True
    created_at: float = 0.0

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": WAKE_SIGNAL_VERSION,
                "source": _clean_text(self.source),
                "trigger": _clean_text(self.trigger, 24) or "external",
                "enterLiveAction": bool(self.enter_live_action),
                "preserveFocus": bool(self.preserve_focus),
                "createdAt": float(self.created_at or time.time()),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )


def parse_wake_request(payload: object) -> WakeRequest:
    """Parse new JSON signals while accepting the legacy plain-text signal."""

    raw = str(payload or "").strip()
    data: dict[str, object] | None = None
    if raw.startswith("{"):
        try:
            candidate = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            candidate = None
        if isinstance(candidate, dict):
            data = candidate

    if data is None:
        source = _clean_text(raw) or "background listener"
        return WakeRequest(
            source=source,
            trigger=_trigger_from_source(source),
            created_at=time.time(),
        )

    source = _clean_text(data.get("source")) or "background listener"
    trigger = _clean_text(data.get("trigger"), 24).casefold()
    if trigger not in {"phrase", "clap", "external"}:
        trigger = _trigger_from_source(source)
    try:
        created_at = float(data.get("createdAt") or 0.0)
    except (TypeError, ValueError):
        created_at = 0.0
    return WakeRequest(
        source=source,
        trigger=trigger,
        enter_live_action=data.get("enterLiveAction") is not False,
        preserve_focus=data.get("preserveFocus") is not False,
        created_at=created_at or time.time(),
    )


def write_wake_request(source: str, *, path: str | os.PathLike[str] | None = None) -> WakeRequest:
    request = WakeRequest(
        source=_clean_text(source) or "background listener",
        trigger=_trigger_from_source(_clean_text(source)),
        enter_live_action=True,
        preserve_focus=True,
        created_at=time.time(),
    )
    target = Path(path or wake_signal_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_text(request.to_json(), encoding="utf-8")
    os.replace(temporary, target)
    return request


def voice_session_path() -> Path:
    return Path(wake_signal_path()).with_name(VOICE_SESSION_FILENAME)


def app_session_path() -> Path:
    return Path(wake_signal_path()).with_name(APP_SESSION_FILENAME)


def set_voice_session_active(
    active: bool,
    *,
    path: str | os.PathLike[str] | None = None,
    pid: int | None = None,
) -> None:
    """Publish whether Live Action owns the microphone.

    The background listener closes its capture stream while this lease exists,
    preventing device contention and preventing MORICE's own voice from being
    mistaken for another wake phrase.
    """

    target = Path(path) if path is not None else voice_session_path()
    if not active:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "version": WAKE_SIGNAL_VERSION,
                "pid": int(pid or os.getpid()),
                "createdAt": time.time(),
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    os.replace(temporary, target)


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def voice_session_active(
    *,
    path: str | os.PathLike[str] | None = None,
    pid_probe: Callable[[int], bool] | None = None,
) -> bool:
    target = Path(path) if path is not None else voice_session_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        pid = int(data.get("pid") or 0) if isinstance(data, dict) else 0
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
        pid = 0
    alive = (pid_probe or _pid_is_running)(pid) if pid else False
    if alive:
        return True
    try:
        target.unlink()
    except (FileNotFoundError, OSError):
        pass
    return False


def set_app_session_active(
    active: bool,
    *,
    path: str | os.PathLike[str] | None = None,
    pid: int | None = None,
) -> None:
    """Publish the actual UI process identity for the background wake daemon."""

    target = Path(path) if path is not None else app_session_path()
    if not active:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "version": WAKE_SIGNAL_VERSION,
                "pid": int(pid or os.getpid()),
                "createdAt": time.time(),
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    os.replace(temporary, target)


def app_session_active(
    *,
    path: str | os.PathLike[str] | None = None,
    pid_probe: Callable[[int], bool] | None = None,
) -> bool:
    target = Path(path) if path is not None else app_session_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        pid = int(data.get("pid") or 0) if isinstance(data, dict) else 0
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
        pid = 0
    alive = (pid_probe or _pid_is_running)(pid) if pid else False
    if alive:
        return True
    try:
        target.unlink()
    except (FileNotFoundError, OSError):
        pass
    return False
