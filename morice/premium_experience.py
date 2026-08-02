from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .settings import (
    normalize_animation_speed,
    normalize_boolean_setting,
    normalize_settings_profile,
    normalize_transparency,
    normalize_ui_scale,
    normalize_workspace_preset,
)
from .ui_system import normalize_accent, normalize_theme


PROFILE_VERSION = 1
MAX_PROFILES = 24
MAX_VISIBLE_CHAT_WIDGETS = 100


@dataclass(frozen=True)
class ExperienceProfile:
    name: str = "Default"
    theme: str = "dark"
    accent: str = "#62d6b0"
    animation_speed: str = "normal"
    reduced_motion: bool = False
    high_contrast: bool = False
    large_text: bool = False
    ui_scale: float = 1.0
    transparency: int = 92
    workspace_preset: str = "balanced"

    @classmethod
    def from_value(
        cls,
        value: Mapping[str, Any] | None,
        *,
        default_name: str = "Default",
    ) -> "ExperienceProfile":
        data = dict(value or {})
        return cls(
            name=normalize_settings_profile(data.get("name", default_name)),
            theme=normalize_theme(str(data.get("theme", "dark"))),
            accent=normalize_accent(str(data.get("accent", "#62d6b0"))),
            animation_speed=normalize_animation_speed(
                str(data.get("animation_speed", "normal"))
            ),
            reduced_motion=normalize_boolean_setting(
                str(data.get("reduced_motion", "false"))
            ),
            high_contrast=normalize_boolean_setting(
                str(data.get("high_contrast", "false"))
            ),
            large_text=normalize_boolean_setting(
                str(data.get("large_text", "false"))
            ),
            ui_scale=normalize_ui_scale(str(data.get("ui_scale", "1.0"))),
            transparency=normalize_transparency(
                str(data.get("transparency", "92"))
            ),
            workspace_preset=normalize_workspace_preset(
                str(data.get("workspace_preset", "balanced"))
            ),
        )


@dataclass(frozen=True)
class WorkspaceLayoutPreset:
    name: str
    mode_panel: bool
    science_panel: bool
    project_panel: bool
    personalization_panel: bool
    tools_panel: bool
    splitter_sizes: tuple[int, int, int, int, int, int]


WORKSPACE_PRESETS: dict[str, WorkspaceLayoutPreset] = {
    "balanced": WorkspaceLayoutPreset(
        "balanced", False, False, False, False, False, (0, 900, 0, 0, 0, 0)
    ),
    "focus": WorkspaceLayoutPreset(
        "focus", False, False, False, False, False, (0, 1000, 0, 0, 0, 0)
    ),
    "science": WorkspaceLayoutPreset(
        "science", False, True, False, False, False, (0, 700, 520, 0, 0, 0)
    ),
    "project": WorkspaceLayoutPreset(
        "project", True, False, True, False, False, (292, 700, 0, 460, 0, 0)
    ),
    "research": WorkspaceLayoutPreset(
        "research", False, True, False, False, True, (0, 620, 480, 0, 0, 420)
    ),
}


def workspace_layout(name: str) -> WorkspaceLayoutPreset:
    return WORKSPACE_PRESETS[normalize_workspace_preset(name)]


def visible_chat_slice(total: int, maximum: int = MAX_VISIBLE_CHAT_WIDGETS) -> tuple[int, int]:
    safe_total = max(0, int(total))
    safe_maximum = max(20, min(500, int(maximum)))
    return max(0, safe_total - safe_maximum), safe_total


class ExperienceProfileStore:
    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self.path = self.directory / "experience-profiles.json"
        self._profiles: dict[str, ExperienceProfile] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            data = {}
        values = data.get("profiles", []) if isinstance(data, dict) else []
        for value in values[:MAX_PROFILES]:
            if not isinstance(value, dict):
                continue
            profile = ExperienceProfile.from_value(value)
            self._profiles[profile.name.casefold()] = profile

    def list(self) -> tuple[ExperienceProfile, ...]:
        return tuple(
            sorted(self._profiles.values(), key=lambda item: item.name.casefold())
        )

    def get(self, name: str) -> ExperienceProfile | None:
        return self._profiles.get(normalize_settings_profile(name).casefold())

    def save(self, profile: ExperienceProfile | Mapping[str, Any]) -> ExperienceProfile:
        clean = (
            profile
            if isinstance(profile, ExperienceProfile)
            else ExperienceProfile.from_value(profile)
        )
        key = clean.name.casefold()
        if key not in self._profiles and len(self._profiles) >= MAX_PROFILES:
            raise ValueError(f"At most {MAX_PROFILES} experience profiles are allowed.")
        self._profiles[key] = clean
        self._persist()
        return clean

    def delete(self, name: str) -> bool:
        key = normalize_settings_profile(name).casefold()
        if key == "default":
            return False
        changed = self._profiles.pop(key, None) is not None
        if changed:
            self._persist()
        return changed

    def export(self, path: str | os.PathLike[str]) -> Path:
        target = Path(path).expanduser().resolve()
        self._atomic_write(
            target,
            {
                "version": PROFILE_VERSION,
                "profiles": [asdict(profile) for profile in self.list()],
            },
        )
        return target

    def import_file(self, path: str | os.PathLike[str]) -> int:
        source = Path(path).expanduser().resolve()
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("The selected profile file is not valid JSON.") from exc
        values = data.get("profiles", []) if isinstance(data, dict) else []
        if not isinstance(values, list):
            raise ValueError("The selected profile file has no profile list.")
        imported = 0
        for value in values[:MAX_PROFILES]:
            if not isinstance(value, dict):
                continue
            try:
                self.save(ExperienceProfile.from_value(value))
                imported += 1
            except ValueError:
                break
        return imported

    def _persist(self) -> None:
        self._atomic_write(
            self.path,
            {
                "version": PROFILE_VERSION,
                "profiles": [asdict(profile) for profile in self.list()],
            },
        )

    @staticmethod
    def _atomic_write(path: Path, value: Any) -> None:
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
                json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.remove(temporary)
                except OSError:
                    pass


__all__ = [
    "ExperienceProfile",
    "ExperienceProfileStore",
    "MAX_VISIBLE_CHAT_WIDGETS",
    "WORKSPACE_PRESETS",
    "WorkspaceLayoutPreset",
    "visible_chat_slice",
    "workspace_layout",
]
