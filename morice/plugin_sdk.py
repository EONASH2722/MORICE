from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


PLUGIN_API_VERSION = "1.0"
MAX_MANIFEST_BYTES = 512 * 1024
PLUGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
CONTRIBUTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,80}$")
VERSION_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


class PluginValidationError(ValueError):
    pass


class PluginState(str, Enum):
    INSTALLED = "installed"
    VALIDATED = "validated"
    LOADED = "loaded"
    RUNNING = "running"
    PAUSED = "paused"
    DISABLED = "disabled"
    UPDATING = "updating"
    UNINSTALLED = "uninstalled"
    FAILED = "failed"
    RECOVERY = "recovery"


ALLOWED_TRANSITIONS: dict[PluginState, frozenset[PluginState]] = {
    PluginState.INSTALLED: frozenset(
        {PluginState.VALIDATED, PluginState.DISABLED, PluginState.UNINSTALLED, PluginState.FAILED}
    ),
    PluginState.VALIDATED: frozenset(
        {PluginState.LOADED, PluginState.DISABLED, PluginState.UPDATING, PluginState.FAILED}
    ),
    PluginState.LOADED: frozenset(
        {PluginState.RUNNING, PluginState.DISABLED, PluginState.FAILED}
    ),
    PluginState.RUNNING: frozenset(
        {
            PluginState.PAUSED,
            PluginState.DISABLED,
            PluginState.UPDATING,
            PluginState.FAILED,
        }
    ),
    PluginState.PAUSED: frozenset(
        {PluginState.RUNNING, PluginState.DISABLED, PluginState.UPDATING, PluginState.FAILED}
    ),
    PluginState.DISABLED: frozenset(
        {PluginState.VALIDATED, PluginState.UPDATING, PluginState.UNINSTALLED}
    ),
    PluginState.UPDATING: frozenset(
        {PluginState.VALIDATED, PluginState.RUNNING, PluginState.DISABLED, PluginState.FAILED}
    ),
    PluginState.UNINSTALLED: frozenset(),
    PluginState.FAILED: frozenset(
        {PluginState.RECOVERY, PluginState.DISABLED, PluginState.UPDATING}
    ),
    PluginState.RECOVERY: frozenset(
        {PluginState.VALIDATED, PluginState.RUNNING, PluginState.DISABLED, PluginState.FAILED}
    ),
}


class PluginCategory(str, Enum):
    AI_MODEL = "ai-model"
    RENDERER = "renderer"
    TOOL = "tool"
    VISUALIZATION = "visualization"
    DESKTOP = "desktop"
    PROJECT = "project"
    VOICE = "voice"
    THEME = "theme"
    LANGUAGE = "language"
    AUTOMATION = "automation"
    MEMORY = "memory"
    DATA_SOURCE = "data-source"
    CLOUD = "cloud"
    DEVELOPER = "developer"
    PRODUCTIVITY = "productivity"
    WIDGET = "widget"
    INTEGRATION = "integration"


class PluginPermission(str, Enum):
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    NETWORK = "network"
    PROCESS = "process"
    PROJECT_READ = "project.read"
    PROJECT_WRITE = "project.write"
    CLIPBOARD = "clipboard"
    NOTIFICATIONS = "notifications"
    MICROPHONE = "microphone"
    VOICE = "voice"
    CAMERA = "camera"
    DESKTOP_CONTROL = "desktop.control"
    MODEL_ACCESS = "model.access"
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    AUTOMATION = "automation"
    GPU = "gpu"


class PluginEventType(str, Enum):
    APPLICATION_STARTED = "application.started"
    APPLICATION_STOPPING = "application.stopping"
    CHAT_STARTED = "chat.started"
    CHAT_FINISHED = "chat.finished"
    PROJECT_LOADED = "project.loaded"
    PROJECT_CLOSED = "project.closed"
    FILE_OPENED = "file.opened"
    FILE_SAVED = "file.saved"
    VISUALIZATION_STARTED = "visualization.started"
    VISUALIZATION_FINISHED = "visualization.finished"
    VISUALIZATION_CREATED = "visualization.created"
    RENDERER_STARTED = "renderer.started"
    RENDERER_FINISHED = "renderer.finished"
    MODEL_LOADED = "model.loaded"
    MODEL_CHANGED = "model.changed"
    MODEL_SWITCHED = "model.switched"
    VOICE_ACTIVATED = "voice.activated"
    SCREENSHOT_CAPTURED = "screenshot.captured"
    MEMORY_UPDATED = "memory.updated"
    NOTIFICATION_CREATED = "notification.created"
    AUTOMATION_TRIGGERED = "automation.triggered"
    THEME_CHANGED = "theme.changed"
    WORKSPACE_CHANGED = "workspace.changed"
    PLUGIN_INSTALLED = "plugin.installed"
    PLUGIN_REMOVED = "plugin.removed"
    PLUGIN_LOADED = "plugin.loaded"
    PLUGIN_UNLOADED = "plugin.unloaded"
    PLUGIN_FAILED = "plugin.failed"


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: str = field(default="", compare=False)

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        cleaned = str(value or "").strip()
        match = VERSION_PATTERN.fullmatch(cleaned)
        if not match:
            raise PluginValidationError(f"Invalid semantic version: {value!r}")
        return cls(
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
            match.group("pre") or "",
        )

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base


def version_satisfies(version: str, constraint: str) -> bool:
    current = SemVer.parse(version)
    text = str(constraint or "*").strip()
    if text in {"", "*", "latest"}:
        return True
    for clause in (part.strip() for part in text.split(",") if part.strip()):
        if clause.startswith("^"):
            floor = SemVer.parse(clause[1:])
            ceiling = SemVer(floor.major + 1, 0, 0)
            if not (floor <= current < ceiling):
                return False
            continue
        if clause.startswith("~"):
            floor = SemVer.parse(clause[1:])
            ceiling = SemVer(floor.major, floor.minor + 1, 0)
            if not (floor <= current < ceiling):
                return False
            continue
        wildcard = re.fullmatch(r"(\d+)(?:\.(\d+))?\.[xX*]", clause)
        if wildcard:
            if current.major != int(wildcard.group(1)):
                return False
            if wildcard.group(2) is not None and current.minor != int(wildcard.group(2)):
                return False
            continue
        operator_match = re.fullmatch(r"(>=|<=|>|<|==|=)?\s*(.+)", clause)
        if not operator_match:
            return False
        operator = operator_match.group(1) or "=="
        expected = SemVer.parse(operator_match.group(2))
        comparisons = {
            ">=": current >= expected,
            "<=": current <= expected,
            ">": current > expected,
            "<": current < expected,
            "==": current == expected,
            "=": current == expected,
        }
        if not comparisons[operator]:
            return False
    return True


@dataclass(frozen=True)
class PluginDependency:
    plugin_id: str
    version: str = "*"
    optional: bool = False


@dataclass(frozen=True)
class PluginCommand:
    command_id: str
    title: str
    description: str = ""
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginTool:
    tool_id: str
    title: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permissions: tuple[str, ...] = ()
    timeout_seconds: float = 30.0
    risk: str = "read_only"


@dataclass(frozen=True)
class PluginRenderer:
    renderer_id: str
    title: str
    keywords: tuple[str, ...] = ()
    interactive: bool = True
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class PluginTheme:
    theme_id: str
    title: str
    stylesheet: str


@dataclass(frozen=True)
class PluginWorkspace:
    workspace_id: str
    title: str
    location: str = "sidebar"
    icon: str = ""


@dataclass(frozen=True)
class PluginModel:
    model_id: str
    title: str
    provider: str = ""
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginUIContribution:
    component_id: str
    title: str
    kind: str
    location: str = ""
    icon: str = ""
    command_id: str = ""


@dataclass(frozen=True)
class PluginContributionSet:
    commands: tuple[PluginCommand, ...] = ()
    tools: tuple[PluginTool, ...] = ()
    renderers: tuple[PluginRenderer, ...] = ()
    themes: tuple[PluginTheme, ...] = ()
    workspaces: tuple[PluginWorkspace, ...] = ()
    models: tuple[PluginModel, ...] = ()
    ui: tuple[PluginUIContribution, ...] = ()
    settings: tuple[dict[str, Any], ...] = ()
    memory: tuple[dict[str, Any], ...] = ()
    automations: tuple[dict[str, Any], ...] = ()
    voice: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    description: str
    author: str
    entry_point: str
    api_version: str = PLUGIN_API_VERSION
    homepage: str = ""
    license: str = ""
    categories: tuple[PluginCategory, ...] = ()
    permissions: tuple[PluginPermission, ...] = ()
    dependencies: tuple[PluginDependency, ...] = ()
    platforms: tuple[str, ...] = ("any",)
    min_morice_version: str = "0.0.0"
    max_morice_version: str = ""
    lazy: bool = False
    verified: bool = False
    contributions: PluginContributionSet = field(default_factory=PluginContributionSet)
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_path(cls, path: str | Path) -> "PluginManifest":
        source = Path(path)
        if not source.is_file():
            raise PluginValidationError(f"Plugin manifest was not found: {source}")
        if source.stat().st_size > MAX_MANIFEST_BYTES:
            raise PluginValidationError("Plugin manifest is larger than 512 KB.")
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PluginValidationError(f"Plugin manifest is not valid JSON: {exc}") from exc
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PluginManifest":
        if not isinstance(payload, Mapping):
            raise PluginValidationError("Plugin manifest must be a JSON object.")
        plugin_id = _required_string(payload, "id", 100)
        if not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            raise PluginValidationError(
                "Plugin id must use lowercase letters, digits, dots, or hyphens."
            )
        name = _required_string(payload, "name", 120)
        version = _required_string(payload, "version", 40)
        SemVer.parse(version)
        api_version = str(payload.get("apiVersion", PLUGIN_API_VERSION)).strip()
        if not version_satisfies(PLUGIN_API_VERSION + ".0", api_version + ".0"):
            raise PluginValidationError(
                f"Plugin API {api_version!r} is incompatible with {PLUGIN_API_VERSION}."
            )
        entry_point = str(payload.get("entryPoint", "plugin.py")).strip()
        entry_path = Path(entry_point)
        if (
            not entry_point
            or entry_path.is_absolute()
            or ".." in entry_path.parts
            or entry_path.suffix.lower() != ".py"
        ):
            raise PluginValidationError("entryPoint must be a relative Python file.")

        categories = tuple(
            _enum_values(PluginCategory, payload.get("categories", ()), "category")
        )
        permissions = tuple(
            _enum_values(PluginPermission, payload.get("permissions", ()), "permission")
        )
        dependencies = _parse_dependencies(payload.get("dependencies", ()))
        platforms = _strings(payload.get("platforms", ("any",)), "platform", 32)
        if not platforms:
            platforms = ("any",)
        contributions = _parse_contributions(payload.get("contributions", {}))
        declared_permissions = {permission.value for permission in permissions}
        for tool in contributions.tools:
            undeclared = set(tool.permissions) - declared_permissions
            if undeclared:
                raise PluginValidationError(
                    f"Tool {tool.tool_id!r} requests permissions not declared by the "
                    f"plugin: {', '.join(sorted(undeclared))}"
                )
        min_version = str(payload.get("minMoriceVersion", "0.0.0")).strip()
        max_version = str(payload.get("maxMoriceVersion", "")).strip()
        SemVer.parse(min_version)
        if max_version:
            SemVer.parse(max_version)
        return cls(
            plugin_id=plugin_id,
            name=name,
            version=version,
            description=str(payload.get("description", "")).strip()[:2000],
            author=str(payload.get("author", "")).strip()[:200],
            entry_point=entry_point,
            api_version=api_version,
            homepage=str(payload.get("homepage", "")).strip()[:500],
            license=str(payload.get("license", "")).strip()[:100],
            categories=categories,
            permissions=permissions,
            dependencies=dependencies,
            platforms=platforms,
            min_morice_version=min_version,
            max_morice_version=max_version,
            lazy=bool(payload.get("lazy", False)),
            verified=bool(payload.get("verified", False)),
            contributions=contributions,
            raw=dict(payload),
        )

    def supports_platform(self, system: str | None = None) -> bool:
        current = (system or platform.system()).casefold()
        supported = {item.casefold() for item in self.platforms}
        aliases = {
            "windows": {"windows", "win32"},
            "darwin": {"darwin", "macos", "mac"},
            "linux": {"linux"},
        }
        return "any" in supported or bool(supported & aliases.get(current, {current}))

    def supports_morice(self, version: str) -> bool:
        current = SemVer.parse(version.split("-", 1)[0])
        minimum = SemVer.parse(self.min_morice_version)
        maximum = SemVer.parse(self.max_morice_version) if self.max_morice_version else None
        return current >= minimum and (maximum is None or current <= maximum)


@dataclass(frozen=True)
class PluginEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "morice"
    timestamp: float = 0.0


@dataclass(frozen=True)
class LifecycleTransition:
    previous: PluginState
    current: PluginState
    reason: str
    timestamp: float


def _required_string(payload: Mapping[str, Any], key: str, limit: int) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise PluginValidationError(f"Plugin manifest field {key!r} is required.")
    if len(value) > limit:
        raise PluginValidationError(f"Plugin manifest field {key!r} is too long.")
    return value


def _strings(value: Any, label: str, limit: int = 100) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, (list, tuple)):
        raise PluginValidationError(f"Plugin {label}s must be a list.")
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text or len(text) > limit:
            raise PluginValidationError(f"Invalid plugin {label}: {item!r}")
        if text not in result:
            result.append(text)
    return tuple(result)


def _enum_values(enum_type, value: Any, label: str) -> Iterable[Any]:
    for item in _strings(value, label):
        try:
            yield enum_type(item)
        except ValueError as exc:
            raise PluginValidationError(f"Unknown plugin {label}: {item}") from exc


def _parse_dependencies(value: Any) -> tuple[PluginDependency, ...]:
    if isinstance(value, Mapping):
        value = [{"id": key, "version": constraint} for key, constraint in value.items()]
    if value in (None, ""):
        return ()
    if not isinstance(value, (list, tuple)):
        raise PluginValidationError("Plugin dependencies must be a list or object.")
    result: list[PluginDependency] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise PluginValidationError("Each plugin dependency must be an object.")
        plugin_id = str(item.get("id", "")).strip()
        if not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            raise PluginValidationError(f"Invalid dependency id: {plugin_id!r}")
        if plugin_id in seen:
            raise PluginValidationError(f"Duplicate dependency: {plugin_id}")
        constraint = str(item.get("version", "*")).strip() or "*"
        if constraint not in {"*", "latest"}:
            probe = constraint.lstrip("^~<>= ").replace("x", "0").replace("X", "0").replace("*", "0")
            SemVer.parse(probe.split(",", 1)[0].strip())
        result.append(PluginDependency(plugin_id, constraint, bool(item.get("optional", False))))
        seen.add(plugin_id)
    return tuple(result)


def _contribution_id(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not CONTRIBUTION_ID_PATTERN.fullmatch(text):
        raise PluginValidationError(f"Invalid {label} id: {text!r}")
    return text


def _records(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, (list, tuple)):
        raise PluginValidationError(f"Plugin {label} contributions must be a list.")
    if len(value) > 200:
        raise PluginValidationError(f"Plugin has too many {label} contributions.")
    if not all(isinstance(item, Mapping) for item in value):
        raise PluginValidationError(f"Every {label} contribution must be an object.")
    return tuple(value)


def _parse_contributions(value: Any) -> PluginContributionSet:
    if value in (None, ""):
        return PluginContributionSet()
    if not isinstance(value, Mapping):
        raise PluginValidationError("Plugin contributions must be an object.")
    commands = tuple(
        PluginCommand(
            _contribution_id(item.get("id"), "command"),
            _required_string(item, "title", 120),
            str(item.get("description", "")).strip()[:500],
            _strings(item.get("keywords", ()), "keyword", 80),
        )
        for item in _records(value.get("commands"), "command")
    )
    tools = tuple(
        PluginTool(
            _contribution_id(item.get("id"), "tool"),
            _required_string(item, "title", 120),
            _required_string(item, "description", 1000),
            dict(item.get("inputSchema") or {"type": "object"}),
            dict(item.get("outputSchema") or {}),
            _strings(item.get("permissions", ()), "tool permission", 100),
            max(0.1, min(300.0, float(item.get("timeoutSeconds", 30.0)))),
            str(item.get("risk", "read_only")),
        )
        for item in _records(value.get("tools"), "tool")
    )
    renderers = tuple(
        PluginRenderer(
            _contribution_id(item.get("id"), "renderer"),
            _required_string(item, "title", 120),
            _strings(item.get("keywords", ()), "renderer keyword", 120),
            bool(item.get("interactive", True)),
            max(0.1, min(300.0, float(item.get("timeoutSeconds", 30.0)))),
        )
        for item in _records(value.get("renderers"), "renderer")
    )
    themes = tuple(
        PluginTheme(
            _contribution_id(item.get("id"), "theme"),
            _required_string(item, "title", 120),
            str(item.get("stylesheet", "")).strip(),
        )
        for item in _records(value.get("themes"), "theme")
    )
    workspaces = tuple(
        PluginWorkspace(
            _contribution_id(item.get("id"), "workspace"),
            _required_string(item, "title", 120),
            str(item.get("location", "sidebar")).strip(),
            str(item.get("icon", "")).strip(),
        )
        for item in _records(value.get("workspaces"), "workspace")
    )
    models = tuple(
        PluginModel(
            _contribution_id(item.get("id"), "model"),
            _required_string(item, "title", 120),
            str(item.get("provider", "")).strip(),
            _strings(item.get("capabilities", ()), "model capability", 100),
        )
        for item in _records(value.get("models"), "model")
    )
    ui_records: list[Mapping[str, Any]] = list(_records(value.get("ui"), "UI"))
    ui_aliases = {
        "toolbarButtons": "toolbar-button",
        "sidebarPanels": "sidebar-panel",
        "contextMenus": "context-menu",
        "workspacePanels": "workspace-panel",
        "floatingWindows": "floating-window",
    }
    for key, kind in ui_aliases.items():
        ui_records.extend({**item, "kind": kind} for item in _records(value.get(key), key))
    ui = tuple(
        PluginUIContribution(
            _contribution_id(item.get("id"), "UI component"),
            _required_string(item, "title", 120),
            str(item.get("kind", "workspace-panel")).strip()[:80],
            str(item.get("location", "")).strip()[:120],
            str(item.get("icon", "")).strip()[:500],
            str(item.get("commandId", "")).strip()[:100],
        )
        for item in ui_records
    )
    supported_ui_kinds = {
        "command-palette",
        "context-menu",
        "floating-window",
        "settings-page",
        "sidebar-panel",
        "status-indicator",
        "toolbar-button",
        "workspace-panel",
    }
    unsupported_ui_kinds = sorted(
        {item.kind for item in ui if item.kind not in supported_ui_kinds}
    )
    if unsupported_ui_kinds:
        raise PluginValidationError(
            "Unsupported plugin UI contribution kind: "
            + ", ".join(unsupported_ui_kinds)
        )
    contribution_groups = {
        "command": tuple(item.command_id for item in commands),
        "tool": tuple(item.tool_id for item in tools),
        "renderer": tuple(item.renderer_id for item in renderers),
        "theme": tuple(item.theme_id for item in themes),
        "workspace": tuple(item.workspace_id for item in workspaces),
        "model": tuple(item.model_id for item in models),
        "UI component": tuple(item.component_id for item in ui),
    }
    for label, identifiers in contribution_groups.items():
        duplicates = sorted(
            identifier for identifier in set(identifiers) if identifiers.count(identifier) > 1
        )
        if duplicates:
            raise PluginValidationError(
                f"Duplicate plugin {label} id: {', '.join(duplicates)}"
            )
    passthrough = {}
    for key in ("settings", "memory", "automations", "voice"):
        records = tuple(dict(item) for item in _records(value.get(key), key))
        identifiers = tuple(
            _contribution_id(item.get("id"), key.rstrip("s")) for item in records
        )
        duplicates = sorted(
            identifier
            for identifier in set(identifiers)
            if identifiers.count(identifier) > 1
        )
        if duplicates:
            raise PluginValidationError(
                f"Duplicate plugin {key.rstrip('s')} id: {', '.join(duplicates)}"
            )
        passthrough[key] = records
    return PluginContributionSet(
        commands=commands,
        tools=tools,
        renderers=renderers,
        themes=themes,
        workspaces=workspaces,
        models=models,
        ui=ui,
        **passthrough,
    )


def validate_transition(previous: PluginState, current: PluginState) -> None:
    if current == previous:
        return
    if current not in ALLOWED_TRANSITIONS[previous]:
        raise PluginValidationError(
            f"Invalid plugin lifecycle transition: {previous.value} -> {current.value}"
        )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "LifecycleTransition",
    "PLUGIN_API_VERSION",
    "PluginCategory",
    "PluginCommand",
    "PluginContributionSet",
    "PluginDependency",
    "PluginEvent",
    "PluginEventType",
    "PluginManifest",
    "PluginModel",
    "PluginPermission",
    "PluginRenderer",
    "PluginState",
    "PluginTheme",
    "PluginTool",
    "PluginUIContribution",
    "PluginValidationError",
    "PluginWorkspace",
    "SemVer",
    "validate_transition",
    "version_satisfies",
]
