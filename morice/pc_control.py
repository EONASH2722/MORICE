from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlparse


POLICY_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _clean_text(value: Any, limit: int = 4_000) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


class PermissionCategory(str, Enum):
    READ_SYSTEM_STATE = "read_system_state"
    APPLICATION_CONTROL = "application_control"
    WINDOW_CONTROL = "window_control"
    MEDIA_CONTROL = "media_control"
    BROWSER_CONTROL = "browser_control"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    PROJECT_MODIFICATION = "project_modification"
    CLIPBOARD = "clipboard"
    MICROPHONE = "microphone"
    SCREEN_ACCESS = "screen_access"
    NETWORK_ACCESS = "network_access"
    SYSTEM_SETTINGS = "system_settings"


class PolicyMode(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ActionRisk(str, Enum):
    ROUTINE = "routine"
    SENSITIVE = "sensitive"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ControlAction:
    domain: str
    verb: str
    target: str = ""
    arguments: Mapping[str, Any] = field(default_factory=dict)
    permissions: tuple[PermissionCategory, ...] = ()
    risk: ActionRisk = ActionRisk.ROUTINE
    source_text: str = ""
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_utc_now)
    route_duration_ms: float = 0.0

    def __post_init__(self) -> None:
        domain = _clean_text(self.domain, 80).casefold().replace("-", "_")
        verb = _clean_text(self.verb, 80).casefold().replace("-", "_")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,79}", domain):
            raise ValueError(f"Invalid control domain: {self.domain!r}")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,79}", verb):
            raise ValueError(f"Invalid control verb: {self.verb!r}")
        permissions = tuple(dict.fromkeys(PermissionCategory(item) for item in self.permissions))
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "verb", verb)
        object.__setattr__(self, "target", _clean_text(self.target, 2_048))
        object.__setattr__(self, "arguments", _json_safe(dict(self.arguments)))
        object.__setattr__(self, "permissions", permissions)
        object.__setattr__(self, "source_text", _clean_text(self.source_text, 8_000))
        object.__setattr__(self, "route_duration_ms", max(0.0, float(self.route_duration_ms)))

    @property
    def tool_id(self) -> str:
        return f"{self.domain}.{self.verb}"

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "actionId": self.action_id,
            "toolId": self.tool_id,
            "target": self.target,
            "arguments": _json_safe(self.arguments),
            "permissions": [item.value for item in self.permissions],
            "risk": self.risk.value,
        }


@dataclass(frozen=True)
class ControlResult:
    action_id: str
    tool_id: str
    success: bool
    verified: bool
    message: str
    output: Mapping[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    missing_permissions: tuple[PermissionCategory, ...] = ()
    confirmation_required: bool = False
    adapter_id: str = ""
    timings_ms: Mapping[str, float] = field(default_factory=dict)
    completed_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actionId": self.action_id,
            "toolId": self.tool_id,
            "success": self.success,
            "verified": self.verified,
            "message": self.message,
            "output": _json_safe(self.output),
            "errors": list(self.errors),
            "missingPermissions": [item.value for item in self.missing_permissions],
            "confirmationRequired": self.confirmation_required,
            "adapterId": self.adapter_id,
            "timingsMs": {key: float(value) for key, value in self.timings_ms.items()},
            "completedAt": self.completed_at,
        }


@dataclass
class DesktopContext:
    active_application: str = ""
    last_application: str = ""
    last_window_title: str = ""
    last_window_handle: int | None = None
    current_media: str = ""
    current_media_provider: str = ""
    current_track: str = ""
    last_media_query: str = ""
    last_file: str = ""
    file_results: list[dict[str, Any]] = field(default_factory=list)
    current_url: str = ""
    last_web_query: str = ""
    web_results: list[dict[str, Any]] = field(default_factory=list)
    current_project: str = ""
    last_error: str = ""
    last_domain: str = ""
    last_target: str = ""
    last_action_id: str = ""
    last_result: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=_utc_now)

    def remember_error(self, error: str) -> None:
        self.last_error = _clean_text(error, 8_000)
        self.updated_at = _utc_now()

    def record(self, action: ControlAction, result: ControlResult) -> None:
        self.last_action_id = action.action_id
        self.last_result = result.to_dict()
        self.updated_at = _utc_now()
        if not result.success:
            if result.errors:
                self.last_error = _clean_text(result.errors[-1], 8_000)
            return

        self.last_domain = action.domain
        self.last_target = action.target
        output = dict(result.output)
        if action.domain == "application":
            if action.target:
                self.last_application = action.target
            if action.verb in {"open", "focus"} and result.verified:
                self.active_application = action.target
            window = output.get("window")
            if isinstance(window, Mapping):
                self.last_window_title = str(window.get("title", ""))
                handle = window.get("handle")
                self.last_window_handle = int(handle) if handle is not None else None
        elif action.domain == "media":
            self.current_media = action.target or self.current_media or "active media"
            provider = str(action.arguments.get("provider", "")).strip()
            if provider:
                self.current_media_provider = provider
            query = str(action.arguments.get("query", "")).strip()
            if query:
                self.last_media_query = query
            track = str(
                output.get("selectedTitle")
                or output.get("currentTrack")
                or (output.get("status") or {}).get("currentTrack")
                if isinstance(output.get("status") or {}, Mapping)
                else ""
            ).strip()
            if track:
                self.current_track = track
        elif action.domain == "file":
            if action.verb == "search":
                self.file_results = [
                    dict(item) for item in output.get("results", ()) if isinstance(item, Mapping)
                ]
                if len(self.file_results) == 1:
                    self.last_file = str(self.file_results[0].get("path", ""))
            elif action.target:
                self.last_file = action.target
        elif action.domain == "browser":
            if action.verb == "search":
                self.last_web_query = str(output.get("query", action.target))
                self.web_results = [
                    dict(item) for item in output.get("results", ()) if isinstance(item, Mapping)
                ]
            current_url = str(output.get("currentUrl", ""))
            if current_url:
                self.current_url = current_url
                self.last_target = current_url
        elif action.domain == "project" and action.target:
            self.current_project = action.target


@dataclass(frozen=True)
class RouteDecision:
    action: ControlAction | None
    escalate_to_model: bool
    reason: str
    clarification: str = ""
    duration_ms: float = 0.0
    route_type: str = "GENERAL_MODEL"
    model_invocations: int = 0


@dataclass(frozen=True)
class ConfirmationGrant:
    token: str
    action_id: str
    description: str
    expires_at: float


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    missing_permissions: tuple[PermissionCategory, ...] = ()
    confirmation_required: bool = False


@dataclass(frozen=True)
class _ConfirmationRecord:
    fingerprint: str
    expires_at: float


class PermissionBroker:
    """Persists category policy and issues exact, expiring, one-use action grants."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        defaults: Mapping[PermissionCategory | str, PolicyMode | str] | None = None,
        confirmation_ttl_seconds: float = 300.0,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.path = Path(path)
        self.confirmation_ttl_seconds = max(
            5.0, min(float(confirmation_ttl_seconds), 3_600.0)
        )
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._policies = {
            category: PolicyMode.ASK for category in PermissionCategory
        }
        for category, mode in dict(defaults or {}).items():
            self._policies[PermissionCategory(category)] = PolicyMode(mode)
        self._confirmations: dict[str, _ConfirmationRecord] = {}
        self._load()

    def _load(self) -> None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(value, dict) or value.get("version") != POLICY_VERSION:
            return
        policies = value.get("policies", {})
        if not isinstance(policies, dict):
            return
        for raw_category, raw_mode in policies.items():
            try:
                self._policies[PermissionCategory(raw_category)] = PolicyMode(raw_mode)
            except ValueError:
                continue

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": POLICY_VERSION,
            "policies": {
                category.value: mode.value
                for category, mode in sorted(
                    self._policies.items(), key=lambda item: item[0].value
                )
            },
        }
        temporary = self.path.with_name(
            f".{self.path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def policy(self, category: PermissionCategory | str) -> PolicyMode:
        with self._lock:
            return self._policies[PermissionCategory(category)]

    def set_policy(
        self,
        category: PermissionCategory | str,
        mode: PolicyMode | str,
    ) -> None:
        clean_category = PermissionCategory(category)
        clean_mode = PolicyMode(mode)
        with self._lock:
            self._policies[clean_category] = clean_mode
            if clean_mode == PolicyMode.DENY:
                self._confirmations.clear()
            self._save()

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return {
                category.value: self._policies[category].value
                for category in PermissionCategory
            }

    @staticmethod
    def _fingerprint(action: ControlAction) -> str:
        encoded = json.dumps(
            action.fingerprint_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def request_confirmation(
        self,
        action: ControlAction,
        *,
        description: str = "",
    ) -> ConfirmationGrant:
        now = self._monotonic()
        token = uuid.uuid4().hex
        expires_at = now + self.confirmation_ttl_seconds
        with self._lock:
            self._prune(now)
            self._confirmations[token] = _ConfirmationRecord(
                self._fingerprint(action), expires_at
            )
        detail = _clean_text(description, 500) or (
            f"Approve {action.tool_id} for {action.target or 'the selected target'}"
        )
        return ConfirmationGrant(token, action.action_id, detail, expires_at)

    def authorize(
        self,
        action: ControlAction,
        confirmation_token: str = "",
    ) -> AuthorizationDecision:
        with self._lock:
            modes = {
                category: self._policies.get(category, PolicyMode.ASK)
                for category in action.permissions
            }
            denied = tuple(
                category for category, mode in modes.items() if mode == PolicyMode.DENY
            )
            if denied:
                if confirmation_token:
                    self._confirmations.pop(confirmation_token, None)
                return AuthorizationDecision(
                    False,
                    "Permission denied: "
                    + ", ".join(category.value for category in denied),
                    denied,
                    False,
                )

            asking = tuple(
                category for category, mode in modes.items() if mode == PolicyMode.ASK
            )
            needs_confirmation = bool(asking) or action.risk == ActionRisk.DESTRUCTIVE
            if not needs_confirmation:
                return AuthorizationDecision(True, "Allowed by category policy.")
            if not confirmation_token:
                reason = (
                    "This destructive action requires exact confirmation."
                    if action.risk == ActionRisk.DESTRUCTIVE
                    else "Permission approval is required for: "
                    + ", ".join(category.value for category in asking)
                )
                return AuthorizationDecision(
                    False,
                    reason,
                    asking,
                    True,
                )
            if not self._consume_confirmation(confirmation_token, action):
                return AuthorizationDecision(
                    False,
                    "The confirmation was invalid, expired, already used, or for a different action.",
                    asking,
                    True,
                )
            return AuthorizationDecision(True, "Exact one-use confirmation accepted.")

    def _consume_confirmation(self, token: str, action: ControlAction) -> bool:
        now = self._monotonic()
        self._prune(now)
        record = self._confirmations.pop(str(token or ""), None)
        return bool(
            record
            and record.expires_at >= now
            and record.fingerprint == self._fingerprint(action)
        )

    def _prune(self, now: float | None = None) -> None:
        current = self._monotonic() if now is None else now
        self._confirmations = {
            token: record
            for token, record in self._confirmations.items()
            if record.expires_at >= current
        }

    def revoke_confirmations(self) -> None:
        with self._lock:
            self._confirmations.clear()


class ControlAdapter(Protocol):
    adapter_id: str

    def supports(self, action: ControlAction) -> bool: ...

    def availability(self, action: ControlAction | None = None) -> tuple[bool, str]: ...

    def execute(self, action: ControlAction, context: DesktopContext) -> ControlResult: ...


def _result(
    action: ControlAction,
    success: bool,
    verified: bool,
    message: str,
    *,
    output: Mapping[str, Any] | None = None,
    errors: Iterable[str] = (),
    adapter_id: str = "",
) -> ControlResult:
    return ControlResult(
        action.action_id,
        action.tool_id,
        success,
        verified,
        _clean_text(message, 4_000),
        _json_safe(dict(output or {})),
        tuple(_clean_text(error, 2_000) for error in errors if _clean_text(error, 2_000)),
        adapter_id=adapter_id,
    )


def _grant_token(grant: Any) -> str:
    token = _field(grant, "token", grant if isinstance(grant, str) else "")
    if not token:
        raise PermissionError("The desktop service did not issue an internal action grant.")
    return str(token)


def _window_value(window: Any) -> dict[str, Any]:
    return {
        "handle": int(_field(window, "handle", 0)),
        "title": str(_field(window, "title", "")),
        "pid": int(_field(window, "pid", 0)),
        "rect": list(_field(window, "rect", ())),
        "visible": bool(_field(window, "visible", True)),
        "minimized": bool(_field(window, "minimized", False)),
        "maximized": bool(_field(window, "maximized", False)),
    }


class DesktopApplicationAdapter:
    adapter_id = "desktop.application"
    _VERBS = {"open", "focus", "minimize", "close", "close_others"}

    def __init__(self, layer: Any):
        self.layer = layer

    def supports(self, action: ControlAction) -> bool:
        return action.domain == "application" and action.verb in self._VERBS

    def availability(self, action: ControlAction | None = None) -> tuple[bool, str]:
        applications_available = bool(getattr(self.layer, "applications", None))
        windows_available = bool(getattr(self.layer, "windows", None))
        available = (
            applications_available
            if action is not None and action.verb == "open"
            else applications_available and windows_available
        )
        return available, "" if available else "Desktop application services are unavailable."

    def execute(self, action: ControlAction, context: DesktopContext) -> ControlResult:
        target = action.target or context.last_application or context.active_application
        if not target:
            return _result(
                action,
                False,
                False,
                "No application target could be resolved.",
                errors=("Application target is ambiguous.",),
                adapter_id=self.adapter_id,
            )
        applications = self.layer.applications
        if action.verb == "close_others":
            windows = list(self.layer.windows.list_windows())
            exception = str(
                action.arguments.get("except", target or "MORICE")
            ).casefold()
            current_pid = os.getpid()
            selected = [
                item
                for item in windows
                if int(_field(item, "pid", 0)) != current_pid
                and exception
                not in str(_field(item, "title", "")).casefold()
                and "morice" not in str(_field(item, "title", "")).casefold()
            ]
            closed_handles: list[int] = []
            for window in selected:
                handle = int(_field(window, "handle", 0))
                if not handle:
                    continue
                grant = self.layer.windows.request(handle, "close")
                self.layer.windows.control(
                    handle,
                    "close",
                    _grant_token(grant),
                )
                closed_handles.append(handle)
            remaining = {
                int(_field(item, "handle", 0))
                for item in self.layer.windows.list_windows()
            }
            deadline = time.monotonic() + 3.0
            while remaining.intersection(closed_handles) and time.monotonic() < deadline:
                time.sleep(0.08)
                remaining = {
                    int(_field(item, "handle", 0))
                    for item in self.layer.windows.list_windows()
                }
            verified = not remaining.intersection(closed_handles)
            return _result(
                action,
                True,
                verified,
                (
                    f"Closed {len(closed_handles)} other application window(s); MORICE was preserved."
                    if verified
                    else "Close requests were sent, but some application windows remain open."
                ),
                output={
                    "closedHandles": closed_handles,
                    "preserved": target or "MORICE",
                },
                adapter_id=self.adapter_id,
            )
        if action.verb == "close":
            matches = self._matching_windows(target, context)
            if not matches:
                return _result(
                    action,
                    False,
                    False,
                    f"No open window matched {target}.",
                    errors=("Application window was not found.",),
                    adapter_id=self.adapter_id,
                )
            closed: list[int] = []
            for window in matches:
                handle = int(_field(window, "handle", 0))
                if not handle:
                    continue
                grant = self.layer.windows.request(handle, "close")
                self.layer.windows.control(handle, "close", _grant_token(grant))
                closed.append(handle)
            remaining = {
                int(_field(item, "handle", 0))
                for item in self.layer.windows.list_windows()
            }
            deadline = time.monotonic() + 3.0
            while remaining.intersection(closed) and time.monotonic() < deadline:
                time.sleep(0.08)
                remaining = {
                    int(_field(item, "handle", 0))
                    for item in self.layer.windows.list_windows()
                }
            verified = bool(closed) and not remaining.intersection(closed)
            return _result(
                action,
                bool(closed),
                verified,
                f"Closed {target}." if verified else f"Close was sent to {target}.",
                output={"closedHandles": closed},
                adapter_id=self.adapter_id,
            )
        if action.verb == "open":
            grant = applications.request_launch(target)
            candidate = applications.launch(target, _grant_token(grant))
            candidate_value = _json_safe(candidate)
            verified = self._verify_running(candidate)
            return _result(
                action,
                True,
                verified,
                (
                    f"Opened {target}."
                    if verified
                    else f"Launch request sent for {target}; the running process was not yet verified."
                ),
                output={"application": candidate_value},
                adapter_id=self.adapter_id,
            )

        matches = self._matching_windows(target, context)
        if not matches:
            return _result(
                action,
                False,
                False,
                f"No open window matched {target}.",
                errors=("Application window was not found.",),
                adapter_id=self.adapter_id,
            )
        if len(matches) > 1:
            exact = [
                item
                for item in matches
                if str(_field(item, "title", "")).casefold() == target.casefold()
            ]
            if len(exact) != 1:
                return _result(
                    action,
                    False,
                    False,
                    f"More than one window matched {target}.",
                    output={"matches": [_window_value(item) for item in matches]},
                    errors=("Window target is ambiguous.",),
                    adapter_id=self.adapter_id,
                )
            matches = exact
        window = matches[0]
        handle = int(_field(window, "handle", 0))
        grant = self.layer.windows.request(handle, action.verb)
        self.layer.windows.control(handle, action.verb, _grant_token(grant))
        after = next(
            (
                item
                for item in self.layer.windows.list_windows()
                if int(_field(item, "handle", 0)) == handle
            ),
            None,
        )
        verified = False
        if action.verb == "minimize":
            verified = bool(after and _field(after, "minimized", False))
        elif action.verb == "focus":
            verified = self._active_handle() == handle
        return _result(
            action,
            True,
            verified,
            (
                f"{action.verb.title()} verified for {target}."
                if verified
                else f"{action.verb.title()} was requested for {target}, but foreground state was not verified."
            ),
            output={"window": _window_value(after or window)},
            adapter_id=self.adapter_id,
        )

    def _verify_running(self, candidate: Any) -> bool:
        applications = self.layer.applications
        source = str(_field(candidate, "source", ""))
        deadline = time.monotonic() + (
            8.0 if source in {"start-app", "known-app-id"} else 1.0
        )
        while True:
            running = False
            if callable(getattr(applications, "is_running", None)):
                running = bool(applications.is_running(candidate))
            else:
                try:
                    processes = applications.list_processes()
                except Exception:
                    processes = ()
                names = {
                    Path(str(_field(item, "image_name", ""))).stem.casefold()
                    for item in processes
                }
                candidate_names = {
                    Path(str(_field(candidate, "name", ""))).stem.casefold(),
                    Path(str(_field(candidate, "target", ""))).stem.casefold(),
                }
                candidate_names.discard("")
                running = bool(names.intersection(candidate_names))
            if running:
                try:
                    title = str(_field(candidate, "name", "")).casefold()
                    visible = any(
                        title in str(_field(window, "title", "")).casefold()
                        for window in self.layer.windows.list_windows()
                    )
                except Exception:
                    visible = False
                if visible or source not in {"start-app", "known-app-id"}:
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)

    def _matching_windows(
        self, target: str, context: DesktopContext
    ) -> list[Any]:
        windows = list(self.layer.windows.list_windows())
        if context.last_window_handle is not None and target.casefold() in {
            "it",
            "that",
            "this",
            context.last_application.casefold(),
        }:
            selected = [
                item
                for item in windows
                if int(_field(item, "handle", 0)) == context.last_window_handle
            ]
            if selected:
                return selected
        needle = target.casefold()
        return [
            item
            for item in windows
            if needle in str(_field(item, "title", "")).casefold()
        ]

    def _active_handle(self) -> int | None:
        windows = self.layer.windows
        active = getattr(windows, "active_window", None)
        try:
            value = active() if callable(active) else getattr(windows, "active_handle", None)
        except Exception:
            return None
        if value is None:
            return None
        if isinstance(value, int):
            return value
        handle = _field(value, "handle", None)
        return int(handle) if handle is not None else None


class DesktopMediaAdapter:
    adapter_id = "desktop.media"
    _VERBS = {
        "pause",
        "resume",
        "next",
        "previous",
        "restart",
        "volume",
        "set_volume",
        "mute",
        "status",
        "play_query",
    }

    def __init__(self, layer: Any):
        self.layer = layer

    def supports(self, action: ControlAction) -> bool:
        return action.domain == "media" and action.verb in self._VERBS

    def availability(self, action: ControlAction | None = None) -> tuple[bool, str]:
        available = bool(getattr(self.layer, "media", None))
        return available, "" if available else "Media control is unavailable."

    def execute(self, action: ControlAction, context: DesktopContext) -> ControlResult:
        media = self.layer.media
        provider = str(
            action.arguments.get("provider")
            or context.current_media_provider
            or ""
        ).strip()
        before = self._status(media, provider, fast=action.verb != "status")
        if action.verb == "status":
            track = before.get("currentTrack")
            artist = before.get("artist")
            state = before.get("playbackState", "unknown")
            detail = (
                f"{track} by {artist} is {state}."
                if track and artist
                else (
                    f"{track} is {state}."
                    if track
                    else f"No track metadata is currently exposed by {provider or 'the active media session'}."
                )
            )
            return _result(
                action,
                True,
                bool(before.get("sessionAvailable") or before.get("amazonUi")),
                detail,
                output=before,
                adapter_id=self.adapter_id,
            )
        command = self._command(action)
        state_before = self._playback_state(before)
        if action.verb == "pause" and state_before == "paused":
            return _result(
                action,
                True,
                True,
                "Media is already paused.",
                output={"status": before, "commandSent": False},
                adapter_id=self.adapter_id,
            )
        if action.verb == "resume" and state_before == "playing":
            return _result(
                action,
                True,
                True,
                "Media is already playing.",
                output={"status": before, "commandSent": False},
                adapter_id=self.adapter_id,
            )
        arguments: dict[str, Any] = {}
        if provider:
            arguments["provider"] = provider
        if action.verb == "play_query":
            arguments["query"] = str(action.arguments.get("query", action.target))
        elif action.verb == "set_volume":
            arguments["percent"] = float(action.arguments.get("percent", 0.0))
        elif action.verb == "volume" and "amount" in action.arguments:
            arguments["amount"] = float(action.arguments.get("amount", 5.0))
        try:
            grant = media.request(command, **arguments)
            detail = media.control(command, _grant_token(grant), **arguments)
        except TypeError:
            if arguments and hasattr(media, "default_music_provider"):
                raise
            grant = media.request(command)
            detail = media.control(command, _grant_token(grant))
        if isinstance(detail, Mapping) and isinstance(detail.get("status"), Mapping):
            after = dict(detail["status"])
        elif action.verb in {"set_volume", "volume", "mute"} and isinstance(
            detail, Mapping
        ):
            after = dict(detail)
        else:
            after = self._status(media, provider, fast=True)
        verified = self._verify(action, before, after)
        if isinstance(detail, Mapping) and "verified" in detail:
            verified = bool(detail.get("verified"))
        elif action.verb == "restart" and isinstance(detail, Mapping) and "restartVerified" in detail:
            verified = bool(detail.get("restartVerified"))
        return _result(
            action,
            True,
            verified,
            (
                f"Media action verified: {action.verb}."
                if verified
                else f"Media command sent: {action.verb}; playback state is unavailable for verification."
            ),
            output={
                "command": command,
                "detail": str(detail),
                **(dict(detail) if isinstance(detail, Mapping) else {}),
                "before": before,
                "status": after,
                "commandSent": True,
            },
            adapter_id=self.adapter_id,
        )

    @staticmethod
    def _status(
        media: Any,
        provider: str = "",
        *,
        fast: bool = False,
    ) -> dict[str, Any]:
        try:
            value = media.status(provider, fast=fast)
        except TypeError:
            try:
                value = media.status(provider)
            except TypeError:
                value = media.status()
        except Exception:
            return {}
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _playback_state(status: Mapping[str, Any]) -> str:
        raw = status.get("playbackState", status.get("state", ""))
        if isinstance(raw, bool):
            return "playing" if raw else "paused"
        clean = str(raw).casefold()
        if clean in {"playing", "play"}:
            return "playing"
        if clean in {"paused", "pause", "stopped", "stop"}:
            return "paused"
        if isinstance(status.get("playing"), bool):
            return "playing" if status["playing"] else "paused"
        return ""

    @staticmethod
    def _command(action: ControlAction) -> str:
        if action.verb in {"pause", "resume"}:
            return "play-pause"
        if action.verb == "restart":
            return action.verb
        if action.verb == "play_query":
            return "play-query"
        if action.verb == "set_volume":
            return "volume-set"
        if action.verb == "volume":
            direction = str(action.arguments.get("direction", "up")).casefold()
            return "volume-down" if direction == "down" else "volume-up"
        if action.verb == "mute":
            return "mute"
        return action.verb

    def _verify(
        self,
        action: ControlAction,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
    ) -> bool:
        if action.verb == "pause":
            return self._playback_state(after) == "paused"
        if action.verb == "resume":
            return self._playback_state(after) == "playing"
        if action.verb in {"next", "previous"}:
            old_track = before.get("currentTrack")
            new_track = after.get("currentTrack")
            return bool(new_track and new_track != old_track)
        if action.verb == "volume":
            old_volume = before.get("volume")
            new_volume = after.get("volume")
            if not isinstance(old_volume, (int, float)) or not isinstance(
                new_volume, (int, float)
            ):
                return False
            direction = str(action.arguments.get("direction", "up")).casefold()
            return new_volume < old_volume if direction == "down" else new_volume > old_volume
        if action.verb == "mute":
            return bool(after.get("muted"))
        if action.verb == "restart":
            position = after.get("playbackPosition")
            return isinstance(position, (int, float)) and position <= 3.0
        if action.verb == "set_volume":
            volume = after.get("volume")
            expected = float(action.arguments.get("percent", 0.0))
            return isinstance(volume, (int, float)) and abs(volume - expected) <= 1.0
        if action.verb == "play_query":
            return self._playback_state(after) == "playing"
        return False


class DesktopFileAdapter:
    adapter_id = "desktop.files"
    _VERBS = {"search", "open", "reveal", "open_recent"}

    def __init__(
        self,
        layer: Any,
        *,
        roots: Iterable[str | os.PathLike[str]],
        open_path: Callable[[str], Any] | None = None,
        reveal_path: Callable[[str], Any] | None = None,
    ):
        self.layer = layer
        self.roots = tuple(
            Path(root).expanduser().resolve()
            for root in roots
            if str(root).strip()
        )
        self.open_path = open_path
        self.reveal_path = reveal_path

    def supports(self, action: ControlAction) -> bool:
        return action.domain == "file" and action.verb in self._VERBS

    def availability(self, action: ControlAction | None = None) -> tuple[bool, str]:
        available = bool(getattr(self.layer, "files", None)) and bool(self.roots)
        return (
            available,
            "" if available else "File control has no approved search roots.",
        )

    def execute(self, action: ControlAction, context: DesktopContext) -> ControlResult:
        if action.verb == "open_recent":
            recent_files = getattr(self.layer.files, "recent_files", None)
            if not callable(recent_files):
                return _result(
                    action,
                    False,
                    False,
                    "Recent project-file discovery is unavailable.",
                    errors=("The file provider does not expose recent files.",),
                    adapter_id=self.adapter_id,
                )
            values = recent_files(self.roots, limit=120)
            extensions = {
                ".c",
                ".cc",
                ".cpp",
                ".cs",
                ".css",
                ".go",
                ".html",
                ".java",
                ".js",
                ".jsx",
                ".kt",
                ".py",
                ".rs",
                ".swift",
                ".ts",
                ".tsx",
                ".vue",
            }
            paths: list[Path] = []
            for item in values:
                value = _json_safe(item)
                raw_path = (
                    value.get("path", "")
                    if isinstance(value, Mapping)
                    else str(value or "")
                )
                try:
                    candidate = self._validated_path(str(raw_path))
                except (FileNotFoundError, PermissionError, ValueError):
                    continue
                if candidate.is_file() and candidate.suffix.casefold() in extensions:
                    paths.append(candidate)
            if not paths:
                return _result(
                    action,
                    False,
                    False,
                    "No recent coding file was found in the approved folders.",
                    errors=("No recent source file matched.",),
                    adapter_id=self.adapter_id,
                )
            path = paths[0]
            files = self.layer.files
            if callable(getattr(files, "open", None)):
                detail = files.open(str(path))
                mode = "desktop"
            elif self.open_path is not None:
                detail = self.open_path(str(path))
                mode = "desktop"
            else:
                detail = files.preview(str(path))
                mode = "preview"
            return _result(
                action,
                True,
                path.exists(),
                f"Opened the most recent coding file: {path.name}.",
                output={
                    "path": str(path),
                    "mode": mode,
                    "detail": _json_safe(detail),
                },
                adapter_id=self.adapter_id,
            )

        if action.verb == "search":
            query = _clean_text(action.target or action.arguments.get("query", ""), 1_000)
            if not query:
                return _result(
                    action,
                    False,
                    False,
                    "A file search query is required.",
                    errors=("File search query is empty.",),
                    adapter_id=self.adapter_id,
                )
            requested = action.arguments.get("roots", ())
            roots = self._validated_roots(requested) if requested else self.roots
            limit = max(1, min(500, int(action.arguments.get("limit", 80))))
            matches = self.layer.files.search(query, roots, limit=limit)
            results = []
            for item in matches:
                value = _json_safe(item)
                if isinstance(value, Mapping):
                    results.append(dict(value))
                else:
                    results.append({"path": str(value)})
            return _result(
                action,
                True,
                True,
                f"Found {len(results)} matching file(s).",
                output={"query": query, "results": results},
                adapter_id=self.adapter_id,
            )

        path = self._validated_path(action.target or context.last_file)
        files = self.layer.files
        if action.verb == "open":
            if callable(getattr(files, "open", None)):
                detail = files.open(str(path))
                mode = "desktop"
            elif self.open_path is not None:
                detail = self.open_path(str(path))
                mode = "desktop"
            else:
                detail = files.preview(str(path))
                mode = "preview"
            verified = path.exists()
            return _result(
                action,
                True,
                verified,
                (
                    f"Opened {path.name}."
                    if mode == "desktop"
                    else f"Prepared a verified preview for {path.name}."
                ),
                output={"path": str(path), "mode": mode, "detail": _json_safe(detail)},
                adapter_id=self.adapter_id,
            )

        if callable(getattr(files, "reveal", None)):
            detail = files.reveal(str(path))
        elif self.reveal_path is not None:
            detail = self.reveal_path(str(path))
        else:
            return _result(
                action,
                False,
                False,
                "Reveal in Explorer is unavailable in the current file provider.",
                errors=("The file provider does not expose a reveal operation.",),
                adapter_id=self.adapter_id,
            )
        return _result(
            action,
            True,
            path.exists() and path.parent.is_dir(),
            f"Revealed {path.name} in its containing folder.",
            output={"path": str(path), "folder": str(path.parent), "detail": _json_safe(detail)},
            adapter_id=self.adapter_id,
        )

    def _validated_roots(self, values: Any) -> tuple[Path, ...]:
        if isinstance(values, (str, os.PathLike)):
            values = (values,)
        roots = tuple(Path(value).expanduser().resolve() for value in values)
        if not roots:
            raise PermissionError("No file roots were selected.")
        for root in roots:
            if not root.is_dir() or not self._inside_approved_root(root):
                raise PermissionError(f"File root is outside approved locations: {root}")
        return roots

    def _validated_path(self, value: str) -> Path:
        if not value:
            raise ValueError("No file target could be resolved.")
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        if not self._inside_approved_root(path):
            raise PermissionError(f"File target is outside approved locations: {path}")
        return path

    def _inside_approved_root(self, path: Path) -> bool:
        for root in self.roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False


class BrowserAdapter:
    adapter_id = "browser.native"
    _VERBS = {"search", "open", "back", "reload"}
    _SITE_DOMAINS = {
        "reddit": "reddit.com",
        "github": "github.com",
        "youtube": "youtube.com",
        "youtube music": "music.youtube.com",
        "stackoverflow": "stackoverflow.com",
        "stack overflow": "stackoverflow.com",
    }

    def __init__(
        self,
        *,
        browser: Any = None,
        web_search: Callable[[str], Any] | None = None,
    ):
        self.browser = browser
        self.web_search = web_search

    def supports(self, action: ControlAction) -> bool:
        return action.domain == "browser" and action.verb in self._VERBS

    def availability(self, action: ControlAction | None = None) -> tuple[bool, str]:
        if action is not None and action.verb == "search":
            return (
                self.web_search is not None,
                "" if self.web_search else "No web search provider is configured.",
            )
        return (
            self.browser is not None,
            "" if self.browser is not None else "No browser controller is configured.",
        )

    def execute(self, action: ControlAction, context: DesktopContext) -> ControlResult:
        if action.verb == "search":
            if self.web_search is None:
                return _result(
                    action,
                    False,
                    False,
                    "Web search is unavailable.",
                    errors=("No web search provider is configured.",),
                    adapter_id=self.adapter_id,
                )
            query = _clean_text(action.target or action.arguments.get("query", ""), 2_000)
            site = self._site_domain(str(action.arguments.get("site", "")))
            if not query:
                return _result(
                    action,
                    False,
                    False,
                    "A web search query is required.",
                    errors=("Web search query is empty.",),
                    adapter_id=self.adapter_id,
                )
            provider_query = f"site:{site} {query}" if site else query
            raw = self.web_search(provider_query)
            results = self._normalize_results(raw)
            return _result(
                action,
                True,
                True,
                f"Web search returned {len(results)} result(s).",
                output={
                    "query": query,
                    "site": site,
                    "providerQuery": provider_query,
                    "results": results,
                },
                adapter_id=self.adapter_id,
            )

        if self.browser is None:
            return _result(
                action,
                False,
                False,
                "Browser control is unavailable.",
                errors=("No browser controller is configured.",),
                adapter_id=self.adapter_id,
            )
        before = self._current_url()
        if action.verb == "open":
            url = self._validated_url(action.target)
            navigate = getattr(self.browser, "open", None) or getattr(
                self.browser, "navigate", None
            )
            if not callable(navigate):
                raise RuntimeError("The browser provider cannot navigate.")
            navigate(url)
            after = self._current_url()
            verified = self._urls_equal(url, after)
            return _result(
                action,
                True,
                verified,
                (
                    f"Opened {url}."
                    if verified
                    else f"Navigation requested for {url}; the current URL was not verified."
                ),
                output={"requestedUrl": url, "currentUrl": after},
                adapter_id=self.adapter_id,
            )
        if action.verb == "back":
            back = getattr(self.browser, "back", None)
            if not callable(back):
                raise RuntimeError("The browser provider cannot navigate backward.")
            back()
            after = self._current_url()
            verified = bool(after and after != before)
            return _result(
                action,
                True,
                verified,
                "Navigated back." if verified else "Back was requested but the URL did not change.",
                output={"previousUrl": before, "currentUrl": after},
                adapter_id=self.adapter_id,
            )
        reload_page = getattr(self.browser, "reload", None)
        if not callable(reload_page):
            raise RuntimeError("The browser provider cannot reload.")
        reload_page()
        after = self._current_url()
        load_succeeded = getattr(self.browser, "last_load_succeeded", None)
        verified = bool(after and after == before and load_succeeded is True)
        return _result(
            action,
            True,
            verified,
            "Reload verified." if verified else "Reload requested; page load was not verified.",
            output={"currentUrl": after},
            adapter_id=self.adapter_id,
        )

    def _current_url(self) -> str:
        if self.browser is None:
            return ""
        value = getattr(self.browser, "current_url", "")
        try:
            value = value() if callable(value) else value
        except Exception:
            return ""
        return str(value or "")

    @classmethod
    def _site_domain(cls, value: str) -> str:
        clean = _clean_text(value, 200).casefold()
        if not clean:
            return ""
        clean = cls._SITE_DOMAINS.get(clean, clean)
        clean = re.sub(r"^https?://", "", clean).split("/", 1)[0]
        if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", clean):
            raise ValueError("Site constraint must be a valid domain.")
        return clean

    @staticmethod
    def _validated_url(value: str) -> str:
        clean = _clean_text(value, 4_000)
        if not re.match(r"^[a-z][a-z0-9+.-]*://", clean, flags=re.IGNORECASE):
            clean = f"https://{clean}"
        parsed = urlparse(clean)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Only valid HTTP or HTTPS URLs can be opened.")
        return clean

    @staticmethod
    def _urls_equal(left: str, right: str) -> bool:
        return left.rstrip("/").casefold() == right.rstrip("/").casefold()

    @staticmethod
    def _normalize_results(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, Mapping):
            raw_items: Sequence[Any] = value.get("results", ())
        elif isinstance(value, str):
            blocks = re.split(r"\n\s*\n", value.strip()) if value.strip() else []
            raw_items = []
            for block in blocks:
                source = re.search(r"(?:Source|URL):\s*(https?://\S+)", block)
                if not source:
                    continue
                lines = [line.strip() for line in block.splitlines() if line.strip()]
                raw_items.append(
                    {
                        "title": lines[0] if lines else source.group(1),
                        "snippet": " ".join(lines[1:-1]),
                        "url": source.group(1).rstrip(".,)"),
                    }
                )
        elif isinstance(value, Sequence):
            raw_items = value
        else:
            raw_items = ()
        results: list[dict[str, Any]] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, Mapping):
                continue
            url = str(item.get("url", item.get("link", ""))).strip()
            try:
                url = BrowserAdapter._validated_url(url)
            except ValueError:
                continue
            results.append(
                {
                    "id": str(item.get("id", index + 1)),
                    "title": _clean_text(item.get("title", url), 500),
                    "snippet": _clean_text(item.get("snippet", ""), 2_000),
                    "url": url,
                }
            )
            if len(results) >= 50:
                break
        return results


class DesktopSystemAdapter:
    adapter_id = "desktop.system"

    def __init__(self, layer: Any):
        self.layer = layer

    def supports(self, action: ControlAction) -> bool:
        return action.domain == "system" and action.verb == "status"

    def availability(self, action: ControlAction | None = None) -> tuple[bool, str]:
        available = bool(getattr(self.layer, "system_monitor", None))
        return available, "" if available else "System monitoring is unavailable."

    def execute(self, action: ControlAction, context: DesktopContext) -> ControlResult:
        metric = str(action.arguments.get("metric", "all")).casefold()
        monitor = self.layer.system_monitor
        if metric in {"ram", "ram_usage"} and callable(
            getattr(monitor, "memory_status", None)
        ):
            sample = _json_safe(monitor.memory_status())
        elif metric == "gpu" and callable(getattr(monitor, "gpu_status", None)):
            sample = _json_safe(monitor.gpu_status())
        elif metric == "processes":
            sample = {}
        else:
            sample = _json_safe(monitor.sample())
        if not isinstance(sample, Mapping):
            sample = {}
        processes: list[dict[str, Any]] = []
        if metric in {"all", "processes", "ram_usage"}:
            try:
                raw_processes = self.layer.applications.list_processes()
            except Exception:
                raw_processes = ()
            processes = [dict(_json_safe(item)) for item in raw_processes]
            processes.sort(
                key=lambda item: int(item.get("memory_kb", item.get("memoryKb", 0)) or 0),
                reverse=True,
            )
            processes = processes[: max(1, min(200, int(action.arguments.get("limit", 30))))]
        if metric == "ram":
            keys = {
                "memory_total_gb",
                "memory_available_gb",
                "memory_percent",
                "memoryTotalGb",
                "memoryAvailableGb",
                "memoryPercent",
            }
            output = {key: value for key, value in sample.items() if key in keys}
        elif metric == "gpu":
            keys = {
                "gpu_percent",
                "vram_used_mb",
                "vram_total_mb",
                "gpuPercent",
                "vramUsedMb",
                "vramTotalMb",
            }
            output = {key: value for key, value in sample.items() if key in keys}
        elif metric == "ram_usage":
            output = {
                "memoryTotalGb": sample.get(
                    "memory_total_gb", sample.get("memoryTotalGb")
                ),
                "memoryAvailableGb": sample.get(
                    "memory_available_gb", sample.get("memoryAvailableGb")
                ),
                "memoryPercent": sample.get(
                    "memory_percent", sample.get("memoryPercent")
                ),
                "processCount": sample.get(
                    "process_count", sample.get("processCount", len(processes))
                ),
                "processes": processes,
            }
        elif metric == "processes":
            output = {"processes": processes, "processCount": len(processes)}
        else:
            output = {"sample": dict(sample), "processes": processes}
        return _result(
            action,
            True,
            True,
            "System state collected from the local machine.",
            output=output,
            adapter_id=self.adapter_id,
        )


class DesktopScreenshotAdapter:
    adapter_id = "desktop.screenshot"

    def __init__(self, layer: Any):
        self.layer = layer

    def supports(self, action: ControlAction) -> bool:
        return action.domain == "screenshot" and action.verb == "capture"

    def availability(self, action: ControlAction | None = None) -> tuple[bool, str]:
        available = bool(getattr(self.layer, "screenshots", None))
        return available, "" if available else "Screenshot capture is unavailable."

    def execute(self, action: ControlAction, context: DesktopContext) -> ControlResult:
        manager = self.layer.screenshots
        mode = str(action.arguments.get("mode", "full") or "full").casefold()
        grant = manager.request(mode)
        captured = manager.capture(mode, grant.token)
        return _result(
            action,
            True,
            bool(captured.path and Path(captured.path).is_file()),
            "Screenshot captured.",
            output={
                "path": captured.path,
                "width": captured.width,
                "height": captured.height,
                "mode": captured.mode,
            },
            adapter_id=self.adapter_id,
        )


class UnavailableComputerUseAdapter:
    adapter_id = "computer_use.unavailable"
    reason = (
        "Computer Use is unavailable: no approved observed-state UI automation "
        "provider is configured. MORICE will not use blind screen coordinates."
    )

    def supports(self, action: ControlAction) -> bool:
        return action.domain == "computer"

    def availability(self, action: ControlAction | None = None) -> tuple[bool, str]:
        return False, self.reason

    def execute(self, action: ControlAction, context: DesktopContext) -> ControlResult:
        return _result(
            action,
            False,
            False,
            self.reason,
            errors=(self.reason,),
            adapter_id=self.adapter_id,
        )


@dataclass(frozen=True)
class _AdapterEntry:
    priority: int
    order: int
    adapter: ControlAdapter


class ControlProviderRegistry:
    def __init__(
        self,
        permission_broker: PermissionBroker,
        *,
        context: DesktopContext | None = None,
        perf_counter: Callable[[], float] = time.perf_counter,
    ):
        self.permission_broker = permission_broker
        self.context = context or DesktopContext()
        self._perf_counter = perf_counter
        self._entries: list[_AdapterEntry] = []
        self._order = 0
        self._lock = threading.RLock()

    def register(self, adapter: ControlAdapter, *, priority: int = 0) -> None:
        if not _clean_text(getattr(adapter, "adapter_id", ""), 120):
            raise ValueError("Control adapters require a stable adapter_id.")
        with self._lock:
            self._order += 1
            self._entries.append(_AdapterEntry(int(priority), self._order, adapter))

    def capabilities(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            entries = tuple(self._entries)
        values = []
        for entry in sorted(entries, key=lambda item: (-item.priority, item.order)):
            try:
                available, reason = entry.adapter.availability(None)
            except Exception as exc:
                available, reason = False, f"Adapter health check failed: {exc}"
            values.append(
                {
                    "adapterId": entry.adapter.adapter_id,
                    "available": bool(available),
                    "reason": str(reason),
                    "priority": entry.priority,
                }
            )
        return tuple(values)

    def execute(
        self,
        action: ControlAction,
        *,
        confirmation_token: str = "",
    ) -> ControlResult:
        started = self._perf_counter()
        auth_started = self._perf_counter()
        authorization = self.permission_broker.authorize(action, confirmation_token)
        auth_ms = (self._perf_counter() - auth_started) * 1_000
        if not authorization.allowed:
            total_ms = (self._perf_counter() - started) * 1_000
            result = ControlResult(
                action.action_id,
                action.tool_id,
                False,
                False,
                authorization.reason,
                errors=(authorization.reason,),
                missing_permissions=authorization.missing_permissions,
                confirmation_required=authorization.confirmation_required,
                timings_ms={
                    "route": action.route_duration_ms,
                    "authorization": auth_ms,
                    "selection": 0.0,
                    "execution": 0.0,
                    "total": total_ms,
                },
            )
            self.context.record(action, result)
            return result

        selection_started = self._perf_counter()
        with self._lock:
            matches = [
                entry
                for entry in self._entries
                if entry.adapter.supports(action)
            ]
        matches.sort(key=lambda item: (-item.priority, item.order))
        selected: ControlAdapter | None = None
        unavailable_reason = ""
        unavailable_adapter = ""
        for entry in matches:
            try:
                available, reason = entry.adapter.availability(action)
            except Exception as exc:
                available, reason = False, f"Adapter health check failed: {exc}"
            if available:
                selected = entry.adapter
                break
            if not unavailable_reason:
                unavailable_reason = str(reason)
                unavailable_adapter = entry.adapter.adapter_id
        selection_ms = (self._perf_counter() - selection_started) * 1_000
        if selected is None:
            message = unavailable_reason or f"No adapter supports {action.tool_id}."
            total_ms = (self._perf_counter() - started) * 1_000
            result = ControlResult(
                action.action_id,
                action.tool_id,
                False,
                False,
                message,
                errors=(message,),
                adapter_id=unavailable_adapter,
                timings_ms={
                    "route": action.route_duration_ms,
                    "authorization": auth_ms,
                    "selection": selection_ms,
                    "execution": 0.0,
                    "total": total_ms,
                },
            )
            self.context.record(action, result)
            return result

        execution_started = self._perf_counter()
        try:
            result = selected.execute(action, self.context)
            if not isinstance(result, ControlResult):
                raise TypeError("Control adapter returned an invalid result type.")
            if result.action_id != action.action_id or result.tool_id != action.tool_id:
                raise ValueError("Control adapter returned a mismatched action result.")
        except Exception as exc:  # noqa: BLE001
            result = _result(
                action,
                False,
                False,
                f"{action.tool_id} failed: {exc}",
                errors=(f"{type(exc).__name__}: {exc}",),
                adapter_id=selected.adapter_id,
            )
        execution_ms = (self._perf_counter() - execution_started) * 1_000
        total_ms = (self._perf_counter() - started) * 1_000
        result = replace(
            result,
            adapter_id=result.adapter_id or selected.adapter_id,
            timings_ms={
                **{key: float(value) for key, value in result.timings_ms.items()},
                "route": action.route_duration_ms,
                "authorization": auth_ms,
                "selection": selection_ms,
                "execution": execution_ms,
                "total": total_ms,
            },
        )
        self.context.record(action, result)
        return result


def build_pc_control_registry(
    layer: Any,
    permission_broker: PermissionBroker,
    *,
    context: DesktopContext | None = None,
    file_roots: Iterable[str | os.PathLike[str]] = (),
    browser: Any = None,
    web_search: Callable[[str], Any] | None = None,
    open_path: Callable[[str], Any] | None = None,
    reveal_path: Callable[[str], Any] | None = None,
) -> ControlProviderRegistry:
    registry = ControlProviderRegistry(permission_broker, context=context)
    registry.register(DesktopApplicationAdapter(layer), priority=100)
    registry.register(DesktopMediaAdapter(layer), priority=100)
    registry.register(
        DesktopFileAdapter(
            layer,
            roots=file_roots,
            open_path=open_path,
            reveal_path=reveal_path,
        ),
        priority=100,
    )
    registry.register(
        BrowserAdapter(browser=browser, web_search=web_search), priority=100
    )
    registry.register(DesktopSystemAdapter(layer), priority=100)
    registry.register(DesktopScreenshotAdapter(layer), priority=100)
    registry.register(UnavailableComputerUseAdapter(), priority=-100)
    return registry


class FastActionRouter:
    """Routes high-confidence routine language without invoking a large model."""

    _SITE_URLS = {
        "github": "https://github.com",
        "reddit": "https://www.reddit.com",
        "youtube": "https://www.youtube.com",
        "youtube music": "https://music.youtube.com",
    }
    _ORDINALS = {
        "first": 0,
        "1st": 0,
        "one": 0,
        "second": 1,
        "2nd": 1,
        "two": 1,
        "third": 2,
        "3rd": 2,
        "three": 2,
    }

    def __init__(
        self,
        context: DesktopContext | None = None,
        *,
        default_music_provider: str = "Amazon Music",
        perf_counter: Callable[[], float] = time.perf_counter,
    ):
        self.context = context or DesktopContext()
        self.default_music_provider = (
            _clean_text(default_music_provider, 120) or "Amazon Music"
        )
        self._perf_counter = perf_counter

    def set_default_music_provider(self, provider: str) -> None:
        clean = _clean_text(provider, 120)
        if clean:
            self.default_music_provider = clean

    def _music_provider(self, raw: str = "") -> str:
        clean = _clean_text(raw, 120).casefold()
        if clean in {"", "music", "music app", "the music app"}:
            return self.default_music_provider
        return {
            "amazon music": "Amazon Music",
            "spotify": "Spotify",
            "youtube music": "YouTube Music",
        }.get(clean, _clean_text(raw, 120))

    def route(self, text: str, context: DesktopContext | None = None) -> RouteDecision:
        started = self._perf_counter()
        state = context or self.context
        source = _clean_text(text, 8_000)
        clean = source.casefold().strip(" .!?\t\r\n")
        if not clean:
            return self._escalate(started, "The request is empty.", "What would you like me to do?")

        if re.fullmatch(
            r"(?:take|capture|make) (?:a |the )?(?:full |desktop |screen )?screenshot",
            clean,
        ):
            return self._action(
                started,
                "screenshot",
                "capture",
                "desktop",
                permissions=(PermissionCategory.SCREEN_ACCESS,),
                source=source,
                arguments={"mode": "full"},
            )

        compound_music = re.fullmatch(
            r"(?:open|launch|start) (amazon music|spotify|youtube music|(?:the )?music(?: app)?) "
            r"(?:and|and then|then) (?:play|search for and play) (.+)",
            clean,
        )
        if compound_music:
            raw_provider, query = compound_music.groups()
            provider = self._music_provider(raw_provider)
            return self._action(
                started,
                "media",
                "play_query",
                query.strip(),
                permissions=(
                    PermissionCategory.APPLICATION_CONTROL,
                    PermissionCategory.MEDIA_CONTROL,
                ),
                source=source,
                arguments={"provider": provider, "query": query.strip()},
            )
        if self._looks_complex(clean):
            return self._escalate(
                started,
                "The request contains multiple dependent or diagnostic actions.",
            )

        result_reference = re.fullmatch(
            r"open (?:the )?(first|1st|one|second|2nd|two|third|3rd|three|last)(?: useful)? result",
            clean,
        )
        if result_reference:
            results = state.web_results
            if not results:
                return self._escalate(
                    started,
                    "No prior web results are available.",
                    "Which result should I open?",
                )
            word = result_reference.group(1)
            index = len(results) - 1 if word == "last" else self._ORDINALS[word]
            if index >= len(results):
                return self._escalate(
                    started,
                    "The referenced result number is unavailable.",
                    f"I only have {len(results)} result(s). Which one should I open?",
                )
            url = str(results[index].get("url", ""))
            if not url:
                return self._escalate(
                    started,
                    "The referenced result has no verified URL.",
                    "Which page should I open?",
                )
            return self._action(
                started,
                "browser",
                "open",
                url,
                permissions=(
                    PermissionCategory.BROWSER_CONTROL,
                    PermissionCategory.NETWORK_ACCESS,
                ),
                source=source,
                arguments={"resultIndex": index},
            )

        if re.fullmatch(r"(?:show|reveal) (?:it|that|the file) in (?:file )?explorer", clean):
            if not state.last_file:
                return self._escalate(
                    started,
                    "No prior file can resolve the reference.",
                    "Which file should I reveal in Explorer?",
                )
            return self._action(
                started,
                "file",
                "reveal",
                state.last_file,
                permissions=(PermissionCategory.FILE_READ,),
                source=source,
            )

        if re.fullmatch(
            r"(?:pause|pause it|pause that|pause (?:the )?music|pause playback)",
            clean,
        ):
            return self._action(
                started,
                "media",
                "pause",
                state.current_media or self.default_music_provider,
                permissions=(PermissionCategory.MEDIA_CONTROL,),
                source=source,
                arguments={
                    "provider": state.current_media_provider
                    or self.default_music_provider
                },
            )
        if re.fullmatch(
            r"(?:continue|resume|resume it|resume (?:the )?music|continue (?:the )?music|continue playing|play it)",
            clean,
        ):
            return self._action(
                started,
                "media",
                "resume",
                state.current_media or self.default_music_provider,
                permissions=(PermissionCategory.MEDIA_CONTROL,),
                source=source,
                arguments={
                    "provider": state.current_media_provider
                    or self.default_music_provider
                },
            )
        if re.fullmatch(r"(?:next|next (?:song|track)|skip|skip it|skip this|skip that)", clean):
            return self._action(
                started,
                "media",
                "next",
                state.current_media or self.default_music_provider,
                permissions=(PermissionCategory.MEDIA_CONTROL,),
                source=source,
                arguments={
                    "provider": state.current_media_provider
                    or self.default_music_provider
                },
            )
        if re.fullmatch(r"(?:previous|previous (?:song|track)|go to the previous (?:song|track))", clean):
            return self._action(
                started,
                "media",
                "previous",
                state.current_media or self.default_music_provider,
                permissions=(PermissionCategory.MEDIA_CONTROL,),
                source=source,
                arguments={
                    "provider": state.current_media_provider
                    or self.default_music_provider
                },
            )
        if re.fullmatch(r"(?:restart|restart it|restart this (?:song|track)|start this (?:song|track) over)", clean):
            return self._action(
                started,
                "media",
                "restart",
                state.current_media or self.default_music_provider,
                permissions=(PermissionCategory.MEDIA_CONTROL,),
                source=source,
                arguments={
                    "provider": state.current_media_provider
                    or self.default_music_provider
                },
            )
        if re.fullmatch(
            r"(?:what(?:'s| is) (?:playing|this song|the current song)|what song is (?:this|playing)|who is this|who(?:'s| is) this)",
            clean,
        ):
            return self._action(
                started,
                "media",
                "status",
                state.current_media or self.default_music_provider,
                permissions=(PermissionCategory.READ_SYSTEM_STATE,),
                source=source,
                arguments={
                    "provider": state.current_media_provider
                    or self.default_music_provider
                },
            )
        if re.fullmatch(r"(?:mute|mute it|mute the audio|mute the sound)", clean):
            return self._action(
                started,
                "media",
                "mute",
                state.current_media or "active media",
                permissions=(PermissionCategory.MEDIA_CONTROL,),
                source=source,
                arguments={
                    "provider": state.current_media_provider
                    or self.default_music_provider
                },
            )
        exact_volume = re.fullmatch(
            r"(?:set (?:the )?volume to|volume) (\d{1,3})(?:\s*%| percent)?",
            clean,
        )
        if exact_volume:
            percent = max(0, min(100, int(exact_volume.group(1))))
            return self._action(
                started,
                "media",
                "set_volume",
                "system audio",
                permissions=(PermissionCategory.MEDIA_CONTROL,),
                source=source,
                arguments={"percent": percent},
            )
        volume = re.fullmatch(
            r"(?:turn (?:it|the volume|the sound) (up|down)|volume (up|down)|(?:a |a little |little )?(louder|quieter|softer))",
            clean,
        )
        if volume:
            word = next(item for item in volume.groups() if item)
            direction = "down" if word in {"down", "quieter", "softer"} else "up"
            return self._action(
                started,
                "media",
                "volume",
                state.current_media or "system audio",
                permissions=(PermissionCategory.MEDIA_CONTROL,),
                source=source,
                arguments={"direction": direction, "step": "small"},
            )

        if re.fullmatch(
            r"(?:put|play|start)(?: some)? music(?: on)?",
            clean,
        ):
            return self._action(
                started,
                "media",
                "resume",
                state.current_media or self.default_music_provider,
                permissions=(
                    PermissionCategory.APPLICATION_CONTROL,
                    PermissionCategory.MEDIA_CONTROL,
                ),
                source=source,
                arguments={
                    "provider": state.current_media_provider
                    or self.default_music_provider
                },
            )

        spotify_track = re.fullmatch(
            r"play (.+?) on spotify",
            clean,
        )
        if spotify_track:
            query = spotify_track.group(1).strip()
            return self._action(
                started,
                "browser",
                "search",
                query,
                permissions=(
                    PermissionCategory.BROWSER_CONTROL,
                    PermissionCategory.NETWORK_ACCESS,
                ),
                source=source,
                arguments={
                    "query": query,
                    "site": "open.spotify.com",
                    "intent": "play-on-spotify",
                },
            )

        provider_track = re.fullmatch(
            r"play (.+?) (?:on|using) (amazon music|youtube music)",
            clean,
        )
        if provider_track:
            query, raw_provider = provider_track.groups()
            provider = self._music_provider(raw_provider)
            return self._action(
                started,
                "media",
                "play_query",
                query.strip(),
                permissions=(
                    PermissionCategory.APPLICATION_CONTROL,
                    PermissionCategory.MEDIA_CONTROL,
                ),
                source=source,
                arguments={"provider": provider, "query": query.strip()},
            )

        generic_track = re.fullmatch(
            r"(?:play|put on) (?!(?:some )?music$)(?:the (?:song|artist|album|playlist) )?(.+)",
            clean,
        )
        if generic_track:
            query = generic_track.group(1).strip()
            if query in {"my playlist", "a playlist", "the playlist"}:
                return self._clarify(
                    started,
                    "A playlist name is required for deterministic selection.",
                    "Which Amazon Music playlist should I play?",
                )
            provider = state.current_media_provider or self.default_music_provider
            return self._action(
                started,
                "media",
                "play_query",
                query,
                permissions=(
                    PermissionCategory.APPLICATION_CONTROL,
                    PermissionCategory.MEDIA_CONTROL,
                ),
                source=source,
                arguments={"provider": provider, "query": query},
            )

        close_others = re.fullmatch(
            r"close (?:everything|all(?: applications| apps| windows)?) except (.+)",
            clean,
        )
        if close_others:
            exception = close_others.group(1).strip()
            return self._action(
                started,
                "application",
                "close_others",
                exception,
                permissions=(
                    PermissionCategory.APPLICATION_CONTROL,
                    PermissionCategory.WINDOW_CONTROL,
                ),
                source=source,
                arguments={"except": exception},
                risk=ActionRisk.DESTRUCTIVE,
            )

        close_application = re.fullmatch(
            r"close (amazon music|spotify|youtube music|(?:the )?music(?: app)?)",
            clean,
        )
        if close_application:
            target = self._music_provider(close_application.group(1))
            return self._action(
                started,
                "application",
                "close",
                target,
                permissions=(
                    PermissionCategory.APPLICATION_CONTROL,
                    PermissionCategory.WINDOW_CONTROL,
                ),
                source=source,
            )

        close_reference = re.fullmatch(r"(?:close|quit|exit) (.+)", clean)
        if close_reference:
            target = self._resolve_application_reference(
                close_reference.group(1), state
            )
            if not target:
                return self._clarify(
                    started,
                    "The application reference is ambiguous.",
                    "Which application should I close?",
                )
            return self._action(
                started,
                "application",
                "close",
                target,
                permissions=(
                    PermissionCategory.APPLICATION_CONTROL,
                    PermissionCategory.WINDOW_CONTROL,
                ),
                source=source,
            )

        if re.fullmatch(
            r"move (?:it|that|this|(?:that|this|the) window) (?:over )?there",
            clean,
        ):
            return self._escalate(
                started,
                "The destination for the window is ambiguous.",
                "Where should I move the window: left, right, another monitor, or specific coordinates?",
            )

        app_control = re.fullmatch(r"(focus|switch to|minimize) (.+)", clean)
        if app_control:
            raw_verb, raw_target = app_control.groups()
            verb = "focus" if raw_verb in {"focus", "switch to"} else "minimize"
            target = self._resolve_application_reference(raw_target, state)
            if not target:
                return self._escalate(
                    started,
                    "The application reference is ambiguous.",
                    f"Which application should I {verb}?",
                )
            return self._action(
                started,
                "application",
                verb,
                target,
                permissions=(
                    PermissionCategory.APPLICATION_CONTROL,
                    PermissionCategory.WINDOW_CONTROL,
                ),
                source=source,
            )

        ram_match = re.search(
            r"\b(?:(?:what(?:'s| is)|show|check|how much)(?: my| the)?(?: current)? (?:ram|memory)(?: usage| use| available| status)?|what(?:'s| is) using my (?:ram|memory)|using my (?:ram|memory))\b",
            clean,
        )
        if ram_match:
            wants_processes = bool(
                re.search(r"\b(?:what(?:'s| is) )?using my (?:ram|memory)\b", clean)
            )
            return self._action(
                started,
                "system",
                "status",
                "memory usage",
                permissions=(PermissionCategory.READ_SYSTEM_STATE,),
                source=source,
                arguments={
                    "metric": "ram_usage" if wants_processes else "ram",
                    "limit": 20,
                },
            )
        if re.search(r"\b(?:gpu|vram|graphics card)\b", clean) and re.search(
            r"\b(?:status|usage|using|how much|show|what)\b", clean
        ):
            return self._action(
                started,
                "system",
                "status",
                "gpu",
                permissions=(PermissionCategory.READ_SYSTEM_STATE,),
                source=source,
                arguments={"metric": "gpu"},
            )
        if re.search(r"\b(?:running processes|process list|what is running|what's running)\b", clean):
            return self._action(
                started,
                "system",
                "status",
                "processes",
                permissions=(PermissionCategory.READ_SYSTEM_STATE,),
                source=source,
                arguments={"metric": "processes", "limit": 50},
            )
        if re.fullmatch(r"(?:system status|pc status|computer status|show system status)", clean):
            return self._action(
                started,
                "system",
                "status",
                "system",
                permissions=(PermissionCategory.READ_SYSTEM_STATE,),
                source=source,
                arguments={"metric": "all"},
            )

        site_search = re.fullmatch(
            r"(?:search|look on) (reddit|github|youtube|youtube music|stackoverflow|stack overflow) for (.+)",
            clean,
        )
        if site_search:
            site, raw_query = site_search.groups()
            query = self._resolve_query_reference(raw_query, state)
            if not query:
                return self._escalate(
                    started,
                    "The web query refers to missing context.",
                    "What should I search for?",
                )
            return self._action(
                started,
                "browser",
                "search",
                query,
                permissions=(
                    PermissionCategory.BROWSER_CONTROL,
                    PermissionCategory.NETWORK_ACCESS,
                ),
                source=source,
                arguments={"query": query, "site": site},
            )
        web_search = re.fullmatch(
            r"(?:search (?:the )?(?:web|internet|online) for|look up|search for online) (.+)",
            clean,
        )
        if web_search:
            query = self._resolve_query_reference(web_search.group(1), state)
            if not query:
                return self._escalate(
                    started,
                    "The web query refers to missing context.",
                    "What should I search for?",
                )
            return self._action(
                started,
                "browser",
                "search",
                query,
                permissions=(
                    PermissionCategory.BROWSER_CONTROL,
                    PermissionCategory.NETWORK_ACCESS,
                ),
                source=source,
                arguments={"query": query},
            )
        lookup = re.fullmatch(r"(?:search this|look this up|look that up)", clean)
        if lookup:
            query = state.last_error or state.last_web_query or state.last_target
            if not query:
                return self._escalate(
                    started,
                    "No contextual query could be resolved.",
                    "What should I search for?",
                )
            return self._action(
                started,
                "browser",
                "search",
                query,
                permissions=(
                    PermissionCategory.BROWSER_CONTROL,
                    PermissionCategory.NETWORK_ACCESS,
                ),
                source=source,
                arguments={"query": query},
            )

        file_search = re.fullmatch(r"(?:find|locate|search (?:my )?files for) (.+)", clean)
        if file_search and self._looks_like_file_query(file_search.group(1), clean):
            query = file_search.group(1)
            return self._action(
                started,
                "file",
                "search",
                query,
                permissions=(PermissionCategory.FILE_READ,),
                source=source,
                arguments={"query": query, "limit": 80},
            )

        if re.fullmatch(
            r"open (?:that|the) thing i was (?:coding|working on) yesterday",
            clean,
        ):
            return self._action(
                started,
                "file",
                "open_recent",
                "recent coding file",
                permissions=(PermissionCategory.FILE_READ,),
                source=source,
                arguments={"kind": "source", "days": 1},
            )

        if clean in {"go back", "back", "browser back"}:
            if state.last_domain == "media":
                return self._action(
                    started,
                    "media",
                    "previous",
                    state.current_media or "active media",
                    permissions=(PermissionCategory.MEDIA_CONTROL,),
                    source=source,
                )
            if state.last_domain == "browser" or state.current_url:
                return self._action(
                    started,
                    "browser",
                    "back",
                    state.current_url,
                    permissions=(PermissionCategory.BROWSER_CONTROL,),
                    source=source,
                )
            return self._escalate(
                started,
                "Back could refer to browser navigation or media history.",
                "Should I go back in the browser or play the previous track?",
            )
        if clean in {"reload", "reload it", "refresh the page", "reload the page"}:
            if not state.current_url and state.last_domain != "browser":
                return self._escalate(
                    started,
                    "No current browser page is known.",
                    "Which page should I reload?",
                )
            return self._action(
                started,
                "browser",
                "reload",
                state.current_url,
                permissions=(PermissionCategory.BROWSER_CONTROL,),
                source=source,
            )

        if re.fullmatch(r"open (?:it|that|this)", clean):
            resolved = self._open_reference(state)
            if resolved is None:
                return self._escalate(
                    started,
                    "The object reference is ambiguous.",
                    "What should I open?",
                )
            domain, target = resolved
            permissions = {
                "file": (PermissionCategory.FILE_READ,),
                "browser": (
                    PermissionCategory.BROWSER_CONTROL,
                    PermissionCategory.NETWORK_ACCESS,
                ),
                "application": (PermissionCategory.APPLICATION_CONTROL,),
            }[domain]
            return self._action(
                started,
                domain,
                "open",
                target,
                permissions=permissions,
                source=source,
            )

        open_target = re.fullmatch(r"(?:open|launch|start) (.+)", clean)
        if open_target:
            target = open_target.group(1).strip()
            target = re.sub(r"^(?:the |application |app )", "", target).strip()
            if target in {"music", "music app"}:
                target = self.default_music_provider
            if target in self._SITE_URLS:
                return self._action(
                    started,
                    "browser",
                    "open",
                    self._SITE_URLS[target],
                    permissions=(
                        PermissionCategory.BROWSER_CONTROL,
                        PermissionCategory.NETWORK_ACCESS,
                    ),
                    source=source,
                )
            if re.match(r"^https?://", target) or re.fullmatch(
                r"[a-z0-9.-]+\.[a-z]{2,}(?:/\S*)?", target
            ):
                return self._action(
                    started,
                    "browser",
                    "open",
                    target,
                    permissions=(
                        PermissionCategory.BROWSER_CONTROL,
                        PermissionCategory.NETWORK_ACCESS,
                    ),
                    source=source,
                )
            if self._looks_like_path(target):
                return self._action(
                    started,
                    "file",
                    "open",
                    target,
                    permissions=(PermissionCategory.FILE_READ,),
                    source=source,
                )
            if re.search(r"\b(?:project|repository|repo)\b", target):
                return self._escalate(
                    started,
                    "Opening a project requires project-location context.",
                )
            return self._action(
                started,
                "application",
                "open",
                target,
                permissions=(PermissionCategory.APPLICATION_CONTROL,),
                source=source,
            )

        return self._escalate(
            started,
            "No deterministic fast-path action matched the request.",
        )

    def _action(
        self,
        started: float,
        domain: str,
        verb: str,
        target: str,
        *,
        permissions: tuple[PermissionCategory, ...],
        source: str,
        arguments: Mapping[str, Any] | None = None,
        risk: ActionRisk = ActionRisk.ROUTINE,
    ) -> RouteDecision:
        duration = (self._perf_counter() - started) * 1_000
        action = ControlAction(
            domain,
            verb,
            target,
            arguments or {},
            permissions,
            risk,
            source,
            route_duration_ms=duration,
        )
        return RouteDecision(
            action,
            False,
            "Fast-path match.",
            duration_ms=duration,
            route_type="FAST_TOOL",
            model_invocations=0,
        )

    def _clarify(
        self,
        started: float,
        reason: str,
        clarification: str,
    ) -> RouteDecision:
        duration = (self._perf_counter() - started) * 1_000
        return RouteDecision(
            None,
            False,
            reason,
            clarification,
            duration,
            "FAST_TOOL",
            0,
        )

    def _escalate(
        self,
        started: float,
        reason: str,
        clarification: str = "",
    ) -> RouteDecision:
        duration = (self._perf_counter() - started) * 1_000
        return RouteDecision(None, True, reason, clarification, duration)

    @staticmethod
    def _looks_complex(clean: str) -> bool:
        if re.search(
            r"\b(?:figure out why|debug|diagnose|tell me before changing|before changing anything)\b",
            clean,
        ):
            return True
        action_words = re.findall(
            r"\b(?:open|launch|focus|minimize|pause|skip|find|locate|search|run|test|build|fix|move|copy|rename)\b",
            clean,
        )
        return len(action_words) > 1 and bool(
            re.search(r"(?:,|;)\s*(?:and|then)?|\b(?:and then|then|and)\b", clean)
        )

    @staticmethod
    def _resolve_application_reference(raw: str, context: DesktopContext) -> str:
        target = raw.strip()
        if target in {"it", "that", "this", "that app", "this app", "the app"}:
            return context.last_application or context.active_application
        target = re.sub(r"^(?:the |application |app )", "", target).strip()
        return re.sub(r"\s+window$", "", target).strip()

    @staticmethod
    def _resolve_query_reference(raw: str, context: DesktopContext) -> str:
        query = raw.strip()
        deictic = re.fullmatch(
            r"(?:this|that|this error|that error|this issue|that issue|this problem|that problem)",
            query,
        )
        if deictic:
            return context.last_error or context.last_web_query or context.last_target
        if re.search(r"\bthis (?:error|issue|problem)\b", query):
            if not context.last_error:
                return ""
            return re.sub(
                r"\bthis (?:error|issue|problem)\b",
                context.last_error,
                query,
            )
        contextual_issue = re.search(
            r"\bthis(?: [a-z0-9+#._-]+){1,4} (?:error|issue|problem)\b",
            query,
        )
        if contextual_issue:
            if not context.last_error:
                return ""
            return (
                query[: contextual_issue.start()]
                + context.last_error
                + query[contextual_issue.end() :]
            ).strip()
        return query

    @staticmethod
    def _looks_like_file_query(query: str, full_text: str) -> bool:
        return bool(
            re.search(
                r"\b(?:file|folder|document|pdf|docx|xlsx|pptx|csv|txt|python|code|screenshot|project)\b",
                f"{query} {full_text}",
            )
            or re.search(r"\.[a-z0-9]{1,8}\b", query)
        )

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        return bool(
            re.match(r"^[a-z]:[\\/]", value, flags=re.IGNORECASE)
            or value.startswith(("/", "./", "../", "~"))
            or re.search(r"\.[a-z0-9]{1,8}$", value, flags=re.IGNORECASE)
        )

    @staticmethod
    def _open_reference(context: DesktopContext) -> tuple[str, str] | None:
        if context.last_domain == "file" and context.last_file:
            return "file", context.last_file
        if context.last_domain == "browser":
            if context.current_url:
                return "browser", context.current_url
            if context.web_results:
                url = str(context.web_results[0].get("url", ""))
                if url:
                    return "browser", url
        if context.last_domain == "application" and context.last_application:
            return "application", context.last_application
        candidates = [
            ("file", context.last_file),
            ("browser", context.current_url),
            ("application", context.last_application),
        ]
        resolved = [(domain, target) for domain, target in candidates if target]
        return resolved[0] if len(resolved) == 1 else None


__all__ = [
    "ActionRisk",
    "AuthorizationDecision",
    "BrowserAdapter",
    "ConfirmationGrant",
    "ControlAction",
    "ControlAdapter",
    "ControlProviderRegistry",
    "ControlResult",
    "DesktopApplicationAdapter",
    "DesktopContext",
    "DesktopFileAdapter",
    "DesktopMediaAdapter",
    "DesktopSystemAdapter",
    "FastActionRouter",
    "PermissionBroker",
    "PermissionCategory",
    "PolicyMode",
    "RouteDecision",
    "UnavailableComputerUseAdapter",
    "build_pc_control_registry",
]
