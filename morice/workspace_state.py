from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


SESSION_VERSION = 1
MAX_HISTORY_ITEMS = 160
MAX_ACTIVITY_ITEMS = 120
MAX_RECENT_ITEMS = 24


def _state_dir() -> str:
    base = os.getenv("APPDATA", "").strip()
    if base:
        return os.path.join(base, "MORICE")
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".morice"))


def workspace_state_path() -> str:
    return os.path.join(_state_dir(), "workspace-state.json")


def _clean_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


def _clean_string_list(values: Any, limit: int, item_limit: int = 1000) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        text = _clean_text(value, item_limit)
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _clean_messages(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in values[-MAX_HISTORY_ITEMS:]:
        if not isinstance(item, dict):
            continue
        role = _clean_text(item.get("role"), 16).lower()
        content = _clean_text(item.get("content"), 120_000)
        if role in {"user", "assistant"} and content:
            cleaned.append({"role": role, "content": content})
    return cleaned


@dataclass
class ActivityEntry:
    title: str
    detail: str = ""
    category: str = "general"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @classmethod
    def from_value(cls, value: Any) -> "ActivityEntry | None":
        if not isinstance(value, dict):
            return None
        title = _clean_text(value.get("title"), 180)
        if not title:
            return None
        return cls(
            title=title,
            detail=_clean_text(value.get("detail"), 1200),
            category=_clean_text(value.get("category"), 40) or "general",
            timestamp=_clean_text(value.get("timestamp"), 48)
            or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )


@dataclass
class WorkspaceState:
    version: int = SESSION_VERSION
    theme: str = "dark"
    accent: str = "#62d6b0"
    geometry: list[int] = field(default_factory=list)
    maximized: bool = False
    active_workspace_tab: int = 0
    mode_panel_visible: bool = False
    sidebar_visible: bool = False
    assistant_hub_visible: bool = False
    history: list[dict[str, str]] = field(default_factory=list)
    user_messages: list[str] = field(default_factory=list)
    recent_files: list[str] = field(default_factory=list)
    recent_chats: list[str] = field(default_factory=list)
    notes: str = ""
    activity: list[ActivityEntry] = field(default_factory=list)

    def add_activity(self, title: str, detail: str = "", category: str = "general") -> None:
        entry = ActivityEntry(
            _clean_text(title, 180),
            _clean_text(detail, 1200),
            _clean_text(category, 40) or "general",
        )
        if not entry.title:
            return
        self.activity.append(entry)
        self.activity = self.activity[-MAX_ACTIVITY_ITEMS:]

    def add_recent_file(self, path: str) -> None:
        clean_path = os.path.abspath(os.path.expanduser(_clean_text(path, 1000)))
        self.recent_files = [
            clean_path,
            *[item for item in self.recent_files if os.path.normcase(item) != os.path.normcase(clean_path)],
        ][:MAX_RECENT_ITEMS]

    def add_recent_chat(self, text: str) -> None:
        preview = " ".join(_clean_text(text, 240).split())
        if not preview:
            return
        self.recent_chats = [preview, *[item for item in self.recent_chats if item != preview]][
            :MAX_RECENT_ITEMS
        ]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["version"] = SESSION_VERSION
        return data

    @classmethod
    def from_dict(cls, data: Any) -> "WorkspaceState":
        if not isinstance(data, dict):
            return cls()
        geometry = data.get("geometry")
        clean_geometry: list[int] = []
        if isinstance(geometry, list) and len(geometry) == 4:
            try:
                clean_geometry = [int(value) for value in geometry]
            except (TypeError, ValueError):
                clean_geometry = []
        activity = [
            entry
            for entry in (ActivityEntry.from_value(value) for value in data.get("activity", []))
            if entry is not None
        ][-MAX_ACTIVITY_ITEMS:]
        return cls(
            theme="light" if str(data.get("theme", "")).lower() == "light" else "dark",
            accent=_clean_text(data.get("accent"), 16) or "#62d6b0",
            geometry=clean_geometry,
            maximized=bool(data.get("maximized", False)),
            active_workspace_tab=max(0, min(3, int(data.get("active_workspace_tab", 0) or 0))),
            mode_panel_visible=bool(data.get("mode_panel_visible", False)),
            sidebar_visible=bool(data.get("sidebar_visible", False)),
            assistant_hub_visible=bool(data.get("assistant_hub_visible", False)),
            history=_clean_messages(data.get("history")),
            user_messages=_clean_string_list(
                data.get("user_messages"), MAX_HISTORY_ITEMS, item_limit=120_000
            ),
            recent_files=_clean_string_list(
                data.get("recent_files"), MAX_RECENT_ITEMS, item_limit=1000
            ),
            recent_chats=_clean_string_list(
                data.get("recent_chats"), MAX_RECENT_ITEMS, item_limit=240
            ),
            notes=_clean_text(data.get("notes"), 200_000),
            activity=activity,
        )


def load_workspace_state(path: str | None = None) -> WorkspaceState:
    target = path or workspace_state_path()
    try:
        with open(target, "r", encoding="utf-8") as handle:
            return WorkspaceState.from_dict(json.load(handle))
    except (OSError, ValueError, TypeError):
        return WorkspaceState()


def save_workspace_state(state: WorkspaceState, path: str | None = None) -> None:
    target = path or workspace_state_path()
    directory = os.path.dirname(target)
    os.makedirs(directory, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=directory,
            prefix="workspace-state-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(state.to_dict(), handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary and os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass
