from __future__ import annotations

import hashlib
import json
import os
import ctypes
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
import zipfile
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from . import __version__ as MORICE_VERSION
from .agent_types import RiskLevel, ToolDefinition
from .domain_engine import DiagramArtifact, DiagramEdge, DiagramNode
from .plugin_sdk import (
    LifecycleTransition,
    PluginEvent,
    PluginEventType,
    PluginManifest,
    PluginPermission,
    PluginRenderer,
    SemVer,
    PluginState,
    PluginValidationError,
    validate_transition,
    version_satisfies,
)
from .science_engine import ScienceArtifact


MAX_PACKAGE_BYTES = 128 * 1024 * 1024
MAX_PACKAGE_FILES = 2_000
MAX_UNPACKED_BYTES = 512 * 1024 * 1024
MAX_EVENT_HISTORY = 500
DEFAULT_CALL_TIMEOUT = 30.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=True, indent=2, default=str)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default
    return value


def _safe_relative(root: Path, value: str | os.PathLike[str]) -> Path:
    target = (root / Path(value)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise PluginValidationError("Plugin path escapes its permitted root.") from exc
    return target


class PermissionReviewRequired(PermissionError):
    def __init__(self, plugin_id: str, permissions: Iterable[str]):
        self.plugin_id = plugin_id
        self.permissions = tuple(sorted(set(permissions)))
        super().__init__(
            f"Plugin {plugin_id!r} requires a permission review: "
            + ", ".join(self.permissions)
        )


class PluginEventBus:
    def __init__(self, history_limit: int = MAX_EVENT_HISTORY):
        self._subscribers: dict[str, dict[str, Callable[[PluginEvent], None]]] = defaultdict(dict)
        self._history: deque[PluginEvent] = deque(maxlen=max(10, int(history_limit)))
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, callback: Callable[[PluginEvent], None]) -> str:
        token = uuid.uuid4().hex
        with self._lock:
            self._subscribers[str(event_type)][token] = callback
        return token

    def unsubscribe(self, token: str) -> bool:
        with self._lock:
            for callbacks in self._subscribers.values():
                if callbacks.pop(token, None) is not None:
                    return True
        return False

    def publish(
        self,
        event_type: str | PluginEventType,
        payload: Mapping[str, Any] | None = None,
        *,
        source: str = "morice",
    ) -> PluginEvent:
        event = PluginEvent(
            event_type=str(getattr(event_type, "value", event_type)),
            payload=dict(payload or {}),
            source=source,
            timestamp=time.time(),
        )
        with self._lock:
            self._history.append(event)
            callbacks = tuple(self._subscribers.get(event.event_type, {}).values())
            callbacks += tuple(self._subscribers.get("*", {}).values())
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                continue
        return event

    @property
    def history(self) -> tuple[PluginEvent, ...]:
        with self._lock:
            return tuple(self._history)


class PluginPermissionStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        value = _read_json(path, {})
        self._entries = value if isinstance(value, dict) else {}

    def review(
        self,
        manifest: PluginManifest,
        granted: Iterable[str | PluginPermission],
    ) -> None:
        declared = {permission.value for permission in manifest.permissions}
        grants = {
            str(getattr(permission, "value", permission))
            for permission in granted
        }
        undeclared = grants - declared
        if undeclared:
            raise PluginValidationError(
                "Cannot grant undeclared permissions: " + ", ".join(sorted(undeclared))
            )
        with self._lock:
            self._entries[manifest.plugin_id] = {
                "version": manifest.version,
                "declared": sorted(declared),
                "granted": sorted(grants),
                "denied": sorted(declared - grants),
                "reviewedAt": _utc_now(),
            }
            _atomic_json(self.path, self._entries)

    def revoke(self, plugin_id: str) -> None:
        with self._lock:
            self._entries.pop(plugin_id, None)
            _atomic_json(self.path, self._entries)

    def is_reviewed(self, manifest: PluginManifest) -> bool:
        if not manifest.permissions:
            return True
        entry = self._entries.get(manifest.plugin_id)
        declared = sorted(permission.value for permission in manifest.permissions)
        return bool(
            isinstance(entry, dict)
            and entry.get("version") == manifest.version
            and entry.get("declared") == declared
        )

    def grants(self, manifest: PluginManifest) -> frozenset[str]:
        if not manifest.permissions:
            return frozenset()
        entry = self._entries.get(manifest.plugin_id)
        if not isinstance(entry, dict) or not self.is_reviewed(manifest):
            return frozenset()
        return frozenset(str(value) for value in entry.get("granted", ()))

    def snapshot(self, plugin_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if plugin_id:
                return dict(self._entries.get(plugin_id, {}))
            return json.loads(json.dumps(self._entries))


@dataclass
class PluginDiagnostics:
    load_time_ms: float = 0.0
    calls: int = 0
    failures: int = 0
    crashes: int = 0
    restarts: int = 0
    last_call_ms: float = 0.0
    total_call_ms: float = 0.0
    last_error: str = ""
    warnings: list[str] = field(default_factory=list)
    logs: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=200))

    @property
    def average_call_ms(self) -> float:
        return self.total_call_ms / self.calls if self.calls else 0.0

    @property
    def performance_score(self) -> int:
        penalty = min(55, self.failures * 8 + self.crashes * 15)
        latency_penalty = min(30, int(self.average_call_ms / 100))
        return max(0, 100 - penalty - latency_penalty)

    def to_dict(
        self,
        *,
        process: Mapping[str, Any] | None = None,
        dependencies: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        return {
            "loadTimeMs": round(self.load_time_ms, 3),
            "calls": self.calls,
            "failures": self.failures,
            "crashes": self.crashes,
            "restarts": self.restarts,
            "lastCallMs": round(self.last_call_ms, 3),
            "averageCallMs": round(self.average_call_ms, 3),
            "lastError": self.last_error,
            "warnings": list(self.warnings),
            "logs": list(self.logs),
            "performanceScore": self.performance_score,
            "process": dict(process or {}),
            "dependencies": [dict(item) for item in dependencies],
        }


class PluginSandbox:
    def __init__(
        self,
        manifest: PluginManifest,
        plugin_root: Path,
        storage_root: Path,
        core_root: Path,
        grants: Iterable[str],
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.manifest = manifest
        self.plugin_root = plugin_root
        self.storage_root = storage_root
        self.core_root = core_root
        self.grants = frozenset(grants)
        self.event_callback = event_callback
        self.process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1_000)
        self._stderr: deque[str] = deque(maxlen=100)
        self._reader: threading.Thread | None = None
        self._error_reader: threading.Thread | None = None
        self._call_lock = threading.RLock()

    @property
    def running(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    @property
    def pid(self) -> int:
        return int(self.process.pid) if self.process else 0

    def start(self, timeout: float = 10.0) -> float:
        if self.running:
            return 0.0
        started = time.perf_counter()
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            value for value in (str(self.core_root), existing_pythonpath) if value
        )
        host_arguments = [
            "--plugin-root",
            str(self.plugin_root),
            "--storage-root",
            str(self.storage_root),
            "--core-root",
            str(self.core_root),
            "--grants",
            json.dumps(sorted(self.grants)),
        ]
        command = (
            [sys.executable, "--morice-plugin-host", *host_arguments]
            if getattr(sys, "frozen", False)
            else [
                sys.executable,
                "-u",
                "-m",
                "morice.plugin_host",
                *host_arguments,
            ]
        )
        creation_flags = (
            int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if os.name == "nt"
            else 0
        )
        self.process = subprocess.Popen(
            command,
            cwd=str(self.core_root),
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creation_flags,
        )
        self._reader = threading.Thread(
            target=self._read_stdout,
            name=f"plugin-{self.manifest.plugin_id}-stdout",
            daemon=True,
        )
        self._error_reader = threading.Thread(
            target=self._read_stderr,
            name=f"plugin-{self.manifest.plugin_id}-stderr",
            daemon=True,
        )
        self._reader.start()
        self._error_reader.start()
        deadline = time.monotonic() + max(0.1, timeout)
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                detail = "\n".join(self._stderr) or "Plugin host exited during startup."
                raise RuntimeError(detail)
            try:
                message = self._messages.get(timeout=min(0.1, deadline - time.monotonic()))
            except queue.Empty:
                continue
            if message.get("type") == "ready":
                return (time.perf_counter() - started) * 1000
            if message.get("type") in {"fatal", "error"}:
                raise RuntimeError(str(message.get("error", "Plugin host failed.")))
            self._handle_event(message)
        self.terminate()
        raise TimeoutError(f"Plugin {self.manifest.plugin_id!r} did not start in time.")

    def call(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = DEFAULT_CALL_TIMEOUT,
    ) -> tuple[Any, float]:
        with self._call_lock:
            if not self.running or self.process is None or self.process.stdin is None:
                raise RuntimeError(f"Plugin {self.manifest.plugin_id!r} is not running.")
            request_id = uuid.uuid4().hex
            encoded = json.dumps(
                {"id": request_id, "method": method, "params": dict(params or {})},
                ensure_ascii=True,
                separators=(",", ":"),
            )
            if len(encoded.encode("utf-8")) > 4 * 1024 * 1024:
                raise ValueError("Plugin request exceeds the 4 MB transport limit.")
            try:
                self.process.stdin.write(encoded + "\n")
                self.process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise RuntimeError("Plugin process closed its input stream.") from exc
            deadline = time.monotonic() + max(0.1, min(300.0, timeout))
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    detail = "\n".join(self._stderr)
                    raise RuntimeError(detail or "Plugin process crashed.")
                try:
                    message = self._messages.get(
                        timeout=min(0.1, max(0.01, deadline - time.monotonic()))
                    )
                except queue.Empty:
                    continue
                if message.get("type") == "event":
                    self._handle_event(message)
                    continue
                if message.get("id") != request_id:
                    continue
                if message.get("error"):
                    raise RuntimeError(str(message["error"]))
                return message.get("result"), float(message.get("durationMs", 0.0))
            self.terminate()
            raise TimeoutError(
                f"Plugin call {self.manifest.plugin_id}:{method} exceeded {timeout:.1f}s."
            )

    def stop(self, timeout: float = 2.0) -> None:
        if self.running:
            try:
                self.call("stop", timeout=timeout)
            except (RuntimeError, TimeoutError, OSError):
                pass
        self.terminate()

    def terminate(self) -> None:
        process = self.process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass
        self.process = None

    def _read_stdout(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                value = {
                    "type": "event",
                    "event": "log",
                    "payload": {
                        "level": "WARNING",
                        "message": line.strip()[:4_000],
                        "metadata": {"source": "unstructured stdout"},
                    },
                }
            if isinstance(value, dict):
                try:
                    self._messages.put(value, timeout=0.2)
                except queue.Full:
                    continue

    def _read_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            if line.strip():
                self._stderr.append(line.rstrip()[:4_000])

    def _handle_event(self, message: dict[str, Any]) -> None:
        if message.get("type") == "event" and self.event_callback:
            self.event_callback(message)


@dataclass
class PluginRecord:
    manifest: PluginManifest
    root: Path
    state: PluginState = PluginState.INSTALLED
    enabled: bool = True
    pinned_version: str = ""
    diagnostics: PluginDiagnostics = field(default_factory=PluginDiagnostics)
    transitions: deque[LifecycleTransition] = field(
        default_factory=lambda: deque(maxlen=100)
    )
    sandbox: PluginSandbox | None = field(default=None, repr=False)
    modified_at: float = 0.0
    registered_tools: list[str] = field(default_factory=list)
    registered_renderers: list[str] = field(default_factory=list)
    last_used_at: float = field(default_factory=time.monotonic)

    def transition(self, state: PluginState, reason: str) -> None:
        if state == self.state:
            return
        validate_transition(self.state, state)
        transition = LifecycleTransition(self.state, state, reason, time.time())
        self.transitions.append(transition)
        self.state = state

    def to_dict(
        self,
        permissions: Mapping[str, Any] | None = None,
        *,
        process: Mapping[str, Any] | None = None,
        dependencies: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        return {
            "id": self.manifest.plugin_id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "description": self.manifest.description,
            "author": self.manifest.author,
            "categories": [value.value for value in self.manifest.categories],
            "permissions": [value.value for value in self.manifest.permissions],
            "permissionReview": dict(permissions or {}),
            "state": self.state.value,
            "enabled": self.enabled,
            "pinnedVersion": self.pinned_version,
            "pid": self.sandbox.pid if self.sandbox else 0,
            "diagnostics": self.diagnostics.to_dict(
                process=process,
                dependencies=dependencies,
            ),
            "transitions": [
                {
                    "previous": item.previous.value,
                    "current": item.current.value,
                    "reason": item.reason,
                    "timestamp": item.timestamp,
                }
                for item in self.transitions
            ],
            "contributions": {
                "commands": len(self.manifest.contributions.commands),
                "tools": len(self.manifest.contributions.tools),
                "renderers": len(self.manifest.contributions.renderers),
                "themes": len(self.manifest.contributions.themes),
                "workspaces": len(self.manifest.contributions.workspaces),
                "models": len(self.manifest.contributions.models),
                "ui": len(self.manifest.contributions.ui),
                "memory": len(self.manifest.contributions.memory),
                "automations": len(self.manifest.contributions.automations),
                "voice": len(self.manifest.contributions.voice),
            },
        }


class PluginRendererProxy:
    def __init__(
        self,
        manager: "PluginManager",
        plugin_id: str,
        specification: PluginRenderer,
    ):
        self.manager = manager
        self.plugin_id = plugin_id
        self.specification = specification
        self.renderer_id = specification.renderer_id
        self.label = specification.title
        self.interactive = specification.interactive

    def can_render(self, prompt: str) -> bool:
        lowered = prompt.casefold()
        return bool(self.specification.keywords) and any(
            keyword.casefold() in lowered for keyword in self.specification.keywords
        )

    def render(self, prompt: str) -> ScienceArtifact | None:
        self.manager.publish_event(
            PluginEventType.RENDERER_STARTED,
            {"pluginId": self.plugin_id, "rendererId": self.renderer_id},
        )
        try:
            result = self.manager.invoke(
                self.plugin_id,
                "render",
                {"id": self.renderer_id, "prompt": prompt},
                timeout=self.specification.timeout_seconds,
            )
            artifact = _science_artifact_from_plugin(
                result, prompt, self.specification.title
            )
            self.manager.publish_event(
                PluginEventType.RENDERER_FINISHED,
                {
                    "pluginId": self.plugin_id,
                    "rendererId": self.renderer_id,
                    "succeeded": True,
                },
            )
            return artifact
        except Exception:
            self.manager.publish_event(
                PluginEventType.RENDERER_FINISHED,
                {
                    "pluginId": self.plugin_id,
                    "rendererId": self.renderer_id,
                    "succeeded": False,
                },
            )
            raise

    def validate(self, artifact: ScienceArtifact) -> tuple[bool, str]:
        diagram = artifact.diagram
        if artifact.kind != "diagram" or not isinstance(diagram, DiagramArtifact):
            return False, "Plugin renderers must return a validated diagram artifact."
        node_ids = {node.node_id for node in diagram.nodes}
        if not node_ids:
            return False, "Plugin renderer returned no nodes."
        if len(node_ids) != len(diagram.nodes):
            return False, "Plugin renderer returned duplicate node ids."
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in diagram.edges):
            return False, "Plugin renderer returned an edge with an unknown endpoint."
        return True, ""

    def estimate_bytes(self, artifact: ScienceArtifact) -> int:
        diagram = artifact.diagram
        if not isinstance(diagram, DiagramArtifact):
            return 1
        return max(1, (len(diagram.nodes) * 256) + (len(diagram.edges) * 128))


def _science_artifact_from_plugin(
    value: Any,
    prompt: str,
    default_title: str,
) -> ScienceArtifact:
    if not isinstance(value, Mapping):
        raise ValueError("Plugin renderer must return a JSON object.")
    kind = str(value.get("kind", "diagram")).casefold()
    if kind != "diagram":
        raise ValueError(
            "Plugin renderer output kind is unsupported. Use the deterministic diagram schema."
        )
    raw_nodes = value.get("nodes", ())
    raw_edges = value.get("edges", ())
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError("Plugin diagram nodes and edges must be lists.")
    if len(raw_nodes) > 2_000 or len(raw_edges) > 5_000:
        raise ValueError("Plugin diagram exceeds MORICE's safe rendering limits.")
    nodes = [
        DiagramNode(
            str(item.get("id", ""))[:100],
            str(item.get("label", ""))[:500],
            str(item.get("lane", ""))[:100],
        )
        for item in raw_nodes
        if isinstance(item, Mapping)
    ]
    edges = [
        DiagramEdge(
            str(item.get("source", ""))[:100],
            str(item.get("target", ""))[:100],
            str(item.get("label", ""))[:300],
        )
        for item in raw_edges
        if isinstance(item, Mapping)
    ]
    title = str(value.get("title", default_title)).strip()[:200] or default_title
    artifact = DiagramArtifact(
        title=title,
        diagram_type=str(value.get("diagramType", "flowchart"))[:80],
        nodes=nodes,
        edges=edges,
        instruction={"source": "plugin", "prompt": prompt[:4_000]},
        notes=[str(item)[:500] for item in value.get("notes", ())[:20]],
    )
    return ScienceArtifact(
        kind="diagram",
        title=title,
        instruction={"source": "plugin"},
        diagram=artifact,
    )


@dataclass(frozen=True)
class MarketplaceEntry:
    plugin_id: str
    name: str
    version: str
    description: str
    download_url: str
    sha256: str
    author: str = ""
    category: str = ""
    verified: bool = False
    featured: bool = False
    downloads: int = 0
    rating: float = 0.0
    screenshots: tuple[str, ...] = ()
    documentation: str = ""
    release_notes: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MarketplaceEntry":
        plugin_id = str(value.get("id", "")).strip()
        if not plugin_id:
            raise PluginValidationError("Marketplace entry has no plugin id.")
        version = str(value.get("version", "")).strip()
        from .plugin_sdk import SemVer

        SemVer.parse(version)
        return cls(
            plugin_id=plugin_id,
            name=str(value.get("name", plugin_id))[:120],
            version=version,
            description=str(value.get("description", ""))[:2000],
            download_url=str(value.get("downloadUrl", ""))[:2000],
            sha256=str(value.get("sha256", "")).casefold(),
            author=str(value.get("author", ""))[:200],
            category=str(value.get("category", ""))[:100],
            verified=bool(value.get("verified", False)),
            featured=bool(value.get("featured", False)),
            downloads=max(0, int(value.get("downloads", 0))),
            rating=max(0.0, min(5.0, float(value.get("rating", 0.0)))),
            screenshots=tuple(str(item)[:2000] for item in value.get("screenshots", ())[:10]),
            documentation=str(value.get("documentation", ""))[:2000],
            release_notes=str(value.get("releaseNotes", ""))[:10_000],
        )


class PluginMarketplace:
    def __init__(self):
        self.entries: tuple[MarketplaceEntry, ...] = ()
        self.source = ""
        self.updated_at = ""

    def refresh(self, source: str | Path, timeout: float = 10.0) -> tuple[MarketplaceEntry, ...]:
        text_source = str(source)
        if text_source.startswith(("http://", "https://")):
            if not text_source.startswith("https://"):
                raise PluginValidationError("Marketplace catalogs require HTTPS.")
            request = urllib.request.Request(
                text_source,
                headers={"User-Agent": f"MORICE/{MORICE_VERSION}"},
            )
            with urllib.request.urlopen(request, timeout=max(1.0, timeout)) as response:
                if int(response.headers.get("Content-Length", 0) or 0) > 4 * 1024 * 1024:
                    raise PluginValidationError("Marketplace catalog is too large.")
                data = response.read(4 * 1024 * 1024 + 1)
        else:
            data = Path(source).read_bytes()
        if len(data) > 4 * 1024 * 1024:
            raise PluginValidationError("Marketplace catalog is too large.")
        payload = json.loads(data.decode("utf-8"))
        records = payload.get("plugins", ()) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise PluginValidationError("Marketplace catalog must contain a plugin list.")
        self.entries = tuple(
            MarketplaceEntry.from_dict(item)
            for item in records[:2_000]
            if isinstance(item, Mapping)
        )
        self.source = text_source
        self.updated_at = _utc_now()
        return self.entries

    def search(
        self,
        query: str = "",
        *,
        category: str = "",
        verified_only: bool = False,
    ) -> tuple[MarketplaceEntry, ...]:
        terms = query.casefold().split()
        result = []
        for entry in self.entries:
            haystack = f"{entry.name} {entry.description} {entry.author}".casefold()
            if terms and not all(term in haystack for term in terms):
                continue
            if category and entry.category.casefold() != category.casefold():
                continue
            if verified_only and not entry.verified:
                continue
            result.append(entry)
        return tuple(
            sorted(
                result,
                key=lambda item: (
                    not item.featured,
                    not item.verified,
                    -item.rating,
                    -item.downloads,
                    item.name.casefold(),
                ),
            )
        )


class PluginManager:
    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        core_root: str | os.PathLike[str] | None = None,
        logger: Callable[..., None] | None = None,
    ):
        self.directory = Path(directory).resolve()
        self.core_root = Path(core_root or Path(__file__).resolve().parents[1]).resolve()
        self.install_root = self.directory / "installed"
        self.storage_root = self.directory / "storage"
        self.backup_root = self.directory / "backups"
        self.download_root = self.directory / "downloads"
        for path in (
            self.install_root,
            self.storage_root,
            self.backup_root,
            self.download_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
        self.state_path = self.directory / "state.json"
        self.permissions = PluginPermissionStore(self.directory / "permissions.json")
        self.events = PluginEventBus()
        self.marketplace = PluginMarketplace()
        self.logger = logger
        self.records: dict[str, PluginRecord] = {}
        self.tool_registry = None
        self.renderer_registry = None
        self.notification_callback: Callable[[str, str], None] | None = None
        self._command_callback: Callable[[], None] | None = None
        self._lock = threading.RLock()
        self._hot_reload_thread: threading.Thread | None = None
        self._hot_reload_stop = threading.Event()
        self._event_executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="plugin-events",
        )
        self._saved_state = _read_json(self.state_path, {})
        self._configuration_path = self.directory / "configuration.json"
        configuration = _read_json(self._configuration_path, {})
        self.auto_updates_enabled = bool(
            configuration.get("automaticUpdates", False)
            if isinstance(configuration, dict)
            else False
        )
        self._last_auto_update = 0.0
        self._process_samples: dict[int, tuple[float, float]] = {}
        self._shutdown = False

    def bind(
        self,
        *,
        tool_registry: Any = None,
        renderer_registry: Any = None,
        notification_callback: Callable[[str, str], None] | None = None,
        command_callback: Callable[[], None] | None = None,
    ) -> None:
        if tool_registry is not None:
            self.tool_registry = tool_registry
        if renderer_registry is not None:
            self.renderer_registry = renderer_registry
        if notification_callback is not None:
            self.notification_callback = notification_callback
        if command_callback is not None:
            self._command_callback = command_callback
        for record in tuple(self.records.values()):
            if record.state == PluginState.RUNNING or (
                record.enabled
                and record.manifest.lazy
                and record.state == PluginState.VALIDATED
            ):
                self._register_contributions(record)

    def discover(self) -> tuple[PluginRecord, ...]:
        discovered: dict[str, PluginRecord] = {}
        for manifest_path in sorted(self.install_root.glob("*/plugin.json")):
            try:
                manifest = PluginManifest.from_path(manifest_path)
                root = manifest_path.parent.resolve()
                entry = _safe_relative(root, manifest.entry_point)
                if not entry.is_file():
                    raise PluginValidationError(
                        f"Plugin entry point is missing: {manifest.entry_point}"
                    )
                saved = self._saved_state.get(manifest.plugin_id, {})
                state_value = saved.get("state", PluginState.INSTALLED.value)
                if state_value in {
                    PluginState.RUNNING.value,
                    PluginState.LOADED.value,
                    PluginState.PAUSED.value,
                    PluginState.UPDATING.value,
                    PluginState.RECOVERY.value,
                }:
                    state_value = PluginState.VALIDATED.value
                try:
                    state = PluginState(state_value)
                except ValueError:
                    state = PluginState.INSTALLED
                record = PluginRecord(
                    manifest=manifest,
                    root=root,
                    state=state,
                    enabled=bool(saved.get("enabled", True)),
                    pinned_version=str(saved.get("pinnedVersion", "")),
                    modified_at=max(
                        manifest_path.stat().st_mtime,
                        entry.stat().st_mtime,
                    ),
                )
                self._validate_record(record)
                discovered[manifest.plugin_id] = record
            except Exception as exc:
                self._log("ERROR", f"Plugin discovery failed for {manifest_path}: {exc}")
        with self._lock:
            existing = self.records
            self.records = discovered
        for plugin_id, old_record in existing.items():
            if plugin_id not in discovered and old_record.sandbox:
                old_record.sandbox.stop()
        self._persist_state()
        return tuple(discovered[key] for key in sorted(discovered))

    def _validate_record(self, record: PluginRecord) -> None:
        manifest = record.manifest
        if not manifest.supports_platform():
            raise PluginValidationError(
                f"Plugin {manifest.plugin_id} does not support this platform."
            )
        if not manifest.supports_morice(MORICE_VERSION):
            raise PluginValidationError(
                f"Plugin {manifest.plugin_id} is incompatible with MORICE {MORICE_VERSION}."
            )
        for dependency in manifest.dependencies:
            if dependency.plugin_id == manifest.plugin_id:
                raise PluginValidationError("A plugin cannot depend on itself.")
        if record.state == PluginState.INSTALLED:
            record.transition(PluginState.VALIDATED, "Manifest and compatibility validated.")

    def review_permissions(
        self,
        plugin_id: str,
        granted: Iterable[str | PluginPermission],
    ) -> None:
        record = self.require(plugin_id)
        self.permissions.review(record.manifest, granted)
        self._persist_state()

    def dependency_order(self, plugin_ids: Iterable[str] | None = None) -> tuple[str, ...]:
        selected = set(plugin_ids or self.records)
        incoming: dict[str, int] = {plugin_id: 0 for plugin_id in selected}
        dependants: dict[str, set[str]] = defaultdict(set)
        for plugin_id in selected:
            record = self.require(plugin_id)
            for dependency in record.manifest.dependencies:
                installed = self.records.get(dependency.plugin_id)
                if installed is None:
                    if dependency.optional:
                        continue
                    raise PluginValidationError(
                        f"{plugin_id} requires missing plugin {dependency.plugin_id}."
                    )
                if not version_satisfies(installed.manifest.version, dependency.version):
                    raise PluginValidationError(
                        f"{plugin_id} requires {dependency.plugin_id} {dependency.version}; "
                        f"{installed.manifest.version} is installed."
                    )
                if dependency.plugin_id in selected:
                    incoming[plugin_id] += 1
                    dependants[dependency.plugin_id].add(plugin_id)
        ready = deque(sorted(key for key, count in incoming.items() if count == 0))
        ordered: list[str] = []
        while ready:
            plugin_id = ready.popleft()
            ordered.append(plugin_id)
            for dependant in sorted(dependants[plugin_id]):
                incoming[dependant] -= 1
                if incoming[dependant] == 0:
                    ready.append(dependant)
        if len(ordered) != len(selected):
            cycle = sorted(key for key, count in incoming.items() if count)
            raise PluginValidationError(
                "Plugin dependency cycle detected: " + ", ".join(cycle)
            )
        return tuple(ordered)

    def start_enabled(self) -> dict[str, str]:
        results: dict[str, str] = {}
        for plugin_id in self.dependency_order():
            record = self.records[plugin_id]
            if not record.enabled:
                continue
            try:
                if record.manifest.lazy:
                    self._register_contributions(record)
                    results[plugin_id] = "lazy"
                else:
                    self.start(plugin_id)
                    results[plugin_id] = "running"
            except PermissionReviewRequired:
                results[plugin_id] = "permission-review"
            except Exception as exc:
                results[plugin_id] = f"failed: {exc}"
        self.start_hot_reload()
        return results

    def start(self, plugin_id: str) -> PluginRecord:
        record = self.require(plugin_id)
        if record.state == PluginState.RUNNING and record.sandbox and record.sandbox.running:
            return record
        for dependency in record.manifest.dependencies:
            dependency_record = self.records.get(dependency.plugin_id)
            if dependency_record is None:
                if dependency.optional:
                    continue
                raise PluginValidationError(
                    f"Required plugin is missing: {dependency.plugin_id}"
                )
            if not version_satisfies(
                dependency_record.manifest.version, dependency.version
            ):
                raise PluginValidationError(
                    f"Incompatible dependency {dependency.plugin_id}."
                )
            if dependency_record.state != PluginState.RUNNING and not dependency.optional:
                self.start(dependency.plugin_id)
        if not self.permissions.is_reviewed(record.manifest):
            raise PermissionReviewRequired(
                plugin_id,
                (permission.value for permission in record.manifest.permissions),
            )
        if record.state in {PluginState.DISABLED, PluginState.FAILED}:
            if record.state == PluginState.FAILED:
                record.transition(PluginState.RECOVERY, "User or runtime requested recovery.")
            record.transition(PluginState.VALIDATED, "Plugin enabled for startup.")
        if record.state == PluginState.PAUSED and record.sandbox and record.sandbox.running:
            _result, duration = record.sandbox.call("resume", timeout=10.0)
            record.diagnostics.calls += 1
            record.diagnostics.last_call_ms = duration
            record.diagnostics.total_call_ms += duration
            record.transition(PluginState.RUNNING, "Plugin resumed.")
            self._register_contributions(record)
            self._persist_state()
            return record
        sandbox = PluginSandbox(
            record.manifest,
            record.root,
            self.storage_root / plugin_id,
            self.core_root,
            self.permissions.grants(record.manifest),
            lambda message: self._on_host_event(plugin_id, message),
        )
        started = time.perf_counter()
        try:
            load_time = sandbox.start()
            record.sandbox = sandbox
            record.diagnostics.load_time_ms = load_time
            record.modified_at = max(
                (record.root / "plugin.json").stat().st_mtime,
                (record.root / record.manifest.entry_point).stat().st_mtime,
            )
            if record.state != PluginState.LOADED:
                record.transition(PluginState.LOADED, "Isolated plugin process loaded.")
            sandbox.call("start", timeout=10.0)
            record.transition(PluginState.RUNNING, "Plugin lifecycle started.")
            record.enabled = True
            self._register_contributions(record)
            self.publish_event(
                PluginEventType.PLUGIN_LOADED,
                {"pluginId": plugin_id, "version": record.manifest.version},
            )
            self._log(
                "INFO",
                f"Plugin {plugin_id} started in {(time.perf_counter() - started) * 1000:.1f} ms.",
            )
        except Exception as exc:
            sandbox.terminate()
            record.sandbox = None
            self._mark_failed(record, exc, crash=False)
            raise
        finally:
            self._persist_state()
        return record

    def pause(self, plugin_id: str) -> None:
        record = self.require(plugin_id)
        if record.state != PluginState.RUNNING:
            return
        self.invoke(plugin_id, "pause", {})
        self._unregister_contributions(record)
        record.transition(PluginState.PAUSED, "Plugin paused.")
        self._persist_state()

    def resume(self, plugin_id: str) -> None:
        self.start(plugin_id)

    def disable(self, plugin_id: str) -> None:
        record = self.require(plugin_id)
        self._unregister_contributions(record)
        if record.sandbox:
            record.sandbox.stop()
            record.sandbox = None
        if record.state != PluginState.DISABLED:
            if record.state == PluginState.INSTALLED:
                record.transition(PluginState.DISABLED, "Plugin disabled.")
            elif record.state in {
                PluginState.VALIDATED,
                PluginState.LOADED,
                PluginState.RUNNING,
                PluginState.PAUSED,
                PluginState.FAILED,
            }:
                record.transition(PluginState.DISABLED, "Plugin disabled.")
        record.enabled = False
        self.publish_event(
            PluginEventType.PLUGIN_UNLOADED,
            {"pluginId": plugin_id},
        )
        self._persist_state()

    def recover(self, plugin_id: str) -> PluginRecord:
        record = self.require(plugin_id)
        if record.sandbox:
            record.sandbox.terminate()
            record.sandbox = None
        self._unregister_contributions(record)
        if record.state != PluginState.FAILED:
            self._mark_failed(record, RuntimeError("Recovery requested."), crash=False)
        record.diagnostics.restarts += 1
        return self.start(plugin_id)

    def invoke(
        self,
        plugin_id: str,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = DEFAULT_CALL_TIMEOUT,
    ) -> Any:
        record = self.require(plugin_id)
        if record.state != PluginState.RUNNING:
            self.start(plugin_id)
        sandbox = record.sandbox
        if sandbox is None:
            raise RuntimeError(f"Plugin {plugin_id!r} has no running sandbox.")
        started = time.perf_counter()
        try:
            result, host_duration = sandbox.call(method, params, timeout=timeout)
            elapsed = max(host_duration, (time.perf_counter() - started) * 1000)
            record.diagnostics.calls += 1
            record.diagnostics.last_call_ms = elapsed
            record.diagnostics.total_call_ms += elapsed
            record.last_used_at = time.monotonic()
            return result
        except Exception as exc:
            record.diagnostics.failures += 1
            record.diagnostics.last_error = str(exc)
            crashed = not sandbox.running
            if crashed:
                self._mark_failed(record, exc, crash=True)
            raise

    def invoke_command(
        self,
        plugin_id: str,
        command_id: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> Any:
        record = self.require(plugin_id)
        valid = {item.command_id for item in record.manifest.contributions.commands}
        if command_id not in valid:
            raise PluginValidationError(f"Unknown plugin command: {command_id}")
        return self.invoke(
            plugin_id,
            "command",
            {"id": command_id, "arguments": dict(arguments or {})},
        )

    def invoke_model(
        self,
        plugin_id: str,
        model_id: str,
        messages: Iterable[Mapping[str, Any]],
        options: Mapping[str, Any] | None = None,
        *,
        timeout: float = 120.0,
    ) -> Any:
        record = self.require(plugin_id)
        valid = {item.model_id for item in record.manifest.contributions.models}
        if model_id not in valid:
            raise PluginValidationError(f"Unknown plugin model: {model_id}")
        bounded_messages = [dict(item) for item in list(messages)[-200:]]
        result = self.invoke(
            plugin_id,
            "model",
            {
                "id": model_id,
                "messages": bounded_messages,
                "options": dict(options or {}),
            },
            timeout=timeout,
        )
        self.publish_event(
            PluginEventType.MODEL_LOADED,
            {"pluginId": plugin_id, "modelId": model_id},
        )
        return result

    def run_automation(
        self,
        plugin_id: str,
        automation_id: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout: float = 60.0,
    ) -> Any:
        record = self.require(plugin_id)
        valid = {
            str(item.get("id", ""))
            for item in record.manifest.contributions.automations
        }
        if automation_id not in valid:
            raise PluginValidationError(
                f"Unknown plugin automation: {automation_id}"
            )
        if PluginPermission.AUTOMATION.value not in self.permissions.grants(
            record.manifest
        ):
            raise PermissionError("The plugin was not granted automation permission.")
        result = self.invoke(
            plugin_id,
            "automation",
            {"id": automation_id, "payload": dict(payload or {})},
            timeout=timeout,
        )
        self.publish_event(
            PluginEventType.AUTOMATION_TRIGGERED,
            {
                "pluginId": plugin_id,
                "automationId": automation_id,
                "succeeded": True,
            },
        )
        return result

    def invoke_memory_provider(
        self,
        plugin_id: str,
        provider_id: str,
        operation: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> Any:
        record = self.require(plugin_id)
        valid = {
            str(item.get("id", ""))
            for item in record.manifest.contributions.memory
        }
        if provider_id not in valid:
            raise PluginValidationError(
                f"Unknown plugin memory provider: {provider_id}"
            )
        normalized = str(operation).strip().casefold()
        required = (
            PluginPermission.MEMORY_WRITE
            if normalized in {"delete", "remove", "set", "store", "update", "write"}
            else PluginPermission.MEMORY_READ
        )
        if required.value not in self.permissions.grants(record.manifest):
            raise PermissionError(
                f"The plugin was not granted {required.value} permission."
            )
        result = self.invoke(
            plugin_id,
            "memory",
            {
                "id": provider_id,
                "operation": normalized,
                "payload": dict(payload or {}),
            },
            timeout=timeout,
        )
        if required == PluginPermission.MEMORY_WRITE:
            self.publish_event(
                PluginEventType.MEMORY_UPDATED,
                {"pluginId": plugin_id, "providerId": provider_id},
            )
        return result

    def invoke_voice_provider(
        self,
        plugin_id: str,
        provider_id: str,
        operation: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout: float = 60.0,
    ) -> Any:
        record = self.require(plugin_id)
        valid = {
            str(item.get("id", ""))
            for item in record.manifest.contributions.voice
        }
        if provider_id not in valid:
            raise PluginValidationError(
                f"Unknown plugin voice provider: {provider_id}"
            )
        if PluginPermission.VOICE.value not in self.permissions.grants(
            record.manifest
        ):
            raise PermissionError("The plugin was not granted voice permission.")
        return self.invoke(
            plugin_id,
            "voice",
            {
                "id": provider_id,
                "operation": str(operation).strip().casefold(),
                "payload": dict(payload or {}),
            },
            timeout=timeout,
        )

    def publish_event(
        self,
        event_type: str | PluginEventType,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        event = self.events.publish(event_type, payload)
        self._fan_out_event(event)

    def _fan_out_event(
        self,
        event: PluginEvent,
        *,
        exclude_plugin_id: str = "",
    ) -> None:
        if self._shutdown:
            return
        for record in tuple(self.records.values()):
            if record.manifest.plugin_id == exclude_plugin_id:
                continue
            if record.state != PluginState.RUNNING or not record.sandbox:
                continue
            try:
                self._event_executor.submit(self._deliver_event, record, event)
            except RuntimeError:
                return

    def install(
        self,
        package: str | os.PathLike[str],
        *,
        expected_sha256: str = "",
        replace: bool = True,
    ) -> PluginRecord:
        source = Path(package).resolve()
        if not source.is_file() or not zipfile.is_zipfile(source):
            raise PluginValidationError("Plugin package must be a valid ZIP archive.")
        if source.stat().st_size > MAX_PACKAGE_BYTES:
            raise PluginValidationError("Plugin package exceeds 128 MB.")
        if expected_sha256:
            actual = _sha256_file(source)
            if actual.casefold() != expected_sha256.casefold():
                raise PluginValidationError("Plugin package checksum does not match.")
        staging_parent = Path(
            tempfile.mkdtemp(prefix="morice-plugin-", dir=str(self.directory))
        )
        try:
            with zipfile.ZipFile(source) as archive:
                members = archive.infolist()
                if len(members) > MAX_PACKAGE_FILES:
                    raise PluginValidationError("Plugin package contains too many files.")
                unpacked = sum(max(0, item.file_size) for item in members)
                if unpacked > MAX_UNPACKED_BYTES:
                    raise PluginValidationError("Plugin package expands beyond 512 MB.")
                for member in members:
                    member_path = Path(member.filename.replace("\\", "/"))
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise PluginValidationError("Plugin package contains an unsafe path.")
                    unix_mode = (member.external_attr >> 16) & 0o170000
                    if unix_mode == 0o120000:
                        raise PluginValidationError("Plugin packages cannot contain symlinks.")
                    target = (staging_parent / member_path).resolve()
                    target.relative_to(staging_parent.resolve())
                archive.extractall(staging_parent)
            manifest_paths = list(staging_parent.glob("plugin.json"))
            if not manifest_paths:
                manifest_paths = list(staging_parent.glob("*/plugin.json"))
            if len(manifest_paths) != 1:
                raise PluginValidationError(
                    "Plugin package must contain exactly one plugin.json at its root."
                )
            manifest = PluginManifest.from_path(manifest_paths[0])
            plugin_root = manifest_paths[0].parent
            if not _safe_relative(plugin_root, manifest.entry_point).is_file():
                raise PluginValidationError("Plugin package entry point is missing.")
            staged_record = PluginRecord(
                manifest=manifest,
                root=plugin_root.resolve(),
            )
            self._validate_record(staged_record)
            target = self.install_root / manifest.plugin_id
            backup: Path | None = None
            if target.exists():
                if not replace:
                    raise FileExistsError(f"Plugin is already installed: {manifest.plugin_id}")
                current_manifest = PluginManifest.from_path(target / "plugin.json")
                backup = self._backup(target, current_manifest)
                existing = self.records.get(manifest.plugin_id)
                if existing:
                    self.disable(manifest.plugin_id)
                shutil.rmtree(target)
            try:
                shutil.move(str(plugin_root), str(target))
            except Exception:
                if backup and not target.exists():
                    shutil.copytree(backup, target)
                raise
            record = PluginRecord(
                manifest=manifest,
                root=target.resolve(),
                state=staged_record.state,
                transitions=list(staged_record.transitions),
            )
            self.records[manifest.plugin_id] = record
            self.permissions.revoke(manifest.plugin_id)
            self._persist_state()
            self.publish_event(
                PluginEventType.PLUGIN_INSTALLED,
                {"pluginId": manifest.plugin_id, "version": manifest.version},
            )
            return record
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)

    def install_marketplace(self, entry: MarketplaceEntry) -> PluginRecord:
        if not entry.download_url.startswith("https://"):
            raise PluginValidationError("Marketplace downloads require HTTPS.")
        if not _valid_sha256(entry.sha256):
            raise PluginValidationError(
                "Marketplace installs require a SHA-256 package checksum."
            )
        destination = self._download_marketplace_package(entry)
        try:
            return self.install(destination, expected_sha256=entry.sha256)
        finally:
            destination.unlink(missing_ok=True)

    def _download_marketplace_package(self, entry: MarketplaceEntry) -> Path:
        if not entry.download_url.startswith("https://"):
            raise PluginValidationError("Marketplace downloads require HTTPS.")
        destination = self.download_root / (
            f"{entry.plugin_id}-{entry.version}-{uuid.uuid4().hex[:8]}.zip"
        )
        request = urllib.request.Request(
            entry.download_url,
            headers={"User-Agent": f"MORICE/{MORICE_VERSION}"},
        )
        with urllib.request.urlopen(request, timeout=30.0) as response:
            with destination.open("wb") as output:
                remaining = MAX_PACKAGE_BYTES + 1
                while remaining > 0:
                    chunk = response.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    output.write(chunk)
                    remaining -= len(chunk)
        if destination.stat().st_size > MAX_PACKAGE_BYTES:
            destination.unlink(missing_ok=True)
            raise PluginValidationError("Marketplace package exceeds 128 MB.")
        if _sha256_file(destination).casefold() != entry.sha256.casefold():
            destination.unlink(missing_ok=True)
            raise PluginValidationError("Marketplace package checksum does not match.")
        return destination

    def update(self, plugin_id: str, package: str | os.PathLike[str]) -> PluginRecord:
        record = self.require(plugin_id)
        if record.pinned_version:
            raise PluginValidationError(
                f"Plugin is pinned to {record.pinned_version}; unpin it before updating."
            )
        candidate = _manifest_from_package(Path(package))
        if candidate.plugin_id != plugin_id:
            raise PluginValidationError("Update package id does not match installed plugin.")
        if SemVer.parse(candidate.version) <= SemVer.parse(record.manifest.version):
            raise PluginValidationError(
                f"Update version {candidate.version} is not newer than "
                f"{record.manifest.version}."
            )
        was_running = record.state == PluginState.RUNNING
        record.transition(PluginState.UPDATING, "Plugin update started.")
        self._persist_state()
        updated = self.install(package, replace=True)
        if was_running and not updated.manifest.permissions:
            self.start(plugin_id)
        return updated

    def available_updates(self) -> tuple[MarketplaceEntry, ...]:
        updates = []
        for entry in self.marketplace.entries:
            record = self.records.get(entry.plugin_id)
            if (
                record
                and not record.pinned_version
                and SemVer.parse(entry.version) > SemVer.parse(record.manifest.version)
            ):
                updates.append(entry)
        return tuple(sorted(updates, key=lambda item: item.name.casefold()))

    def update_from_marketplace(self, entry: MarketplaceEntry) -> PluginRecord:
        record = self.require(entry.plugin_id)
        if record.pinned_version:
            raise PluginValidationError(
                f"Plugin is pinned to {record.pinned_version}; unpin it before updating."
            )
        if not _valid_sha256(entry.sha256):
            raise PluginValidationError(
                "Marketplace updates require a SHA-256 package checksum."
            )
        destination = self._download_marketplace_package(entry)
        try:
            return self.update(entry.plugin_id, destination)
        finally:
            destination.unlink(missing_ok=True)

    def set_automatic_updates(self, enabled: bool) -> None:
        self.auto_updates_enabled = bool(enabled)
        _atomic_json(
            self._configuration_path,
            {"automaticUpdates": self.auto_updates_enabled},
        )

    def update_history(self, plugin_id: str) -> tuple[dict[str, Any], ...]:
        root = self.backup_root / plugin_id
        history = []
        for path in sorted(
            root.glob("*") if root.exists() else (),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            try:
                manifest = PluginManifest.from_path(path / "plugin.json")
            except PluginValidationError:
                continue
            history.append(
                {
                    "version": manifest.version,
                    "createdAt": datetime.fromtimestamp(
                        path.stat().st_mtime, timezone.utc
                    ).isoformat(),
                    "path": str(path),
                }
            )
        return tuple(history)

    def rollback(self, plugin_id: str, version: str = "") -> PluginRecord:
        candidates = sorted(
            (self.backup_root / plugin_id).glob("*"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if version:
            candidates = [
                path
                for path in candidates
                if PluginManifest.from_path(path / "plugin.json").version == version
            ]
        if not candidates:
            raise FileNotFoundError(f"No rollback version is available for {plugin_id}.")
        current = self.records.get(plugin_id)
        if current:
            self.disable(plugin_id)
            shutil.rmtree(current.root, ignore_errors=True)
        target = self.install_root / plugin_id
        shutil.copytree(candidates[0], target)
        manifest = PluginManifest.from_path(target / "plugin.json")
        record = PluginRecord(manifest=manifest, root=target)
        self._validate_record(record)
        self.records[plugin_id] = record
        self.permissions.revoke(plugin_id)
        self._persist_state()
        return record

    def pin(self, plugin_id: str, version: str = "") -> None:
        record = self.require(plugin_id)
        if version and version != record.manifest.version:
            raise PluginValidationError("A plugin can only be pinned to its installed version.")
        record.pinned_version = version
        self._persist_state()

    def uninstall(self, plugin_id: str) -> None:
        record = self.require(plugin_id)
        self.disable(plugin_id)
        record.transition(PluginState.UNINSTALLED, "Plugin uninstalled.")
        shutil.rmtree(record.root, ignore_errors=False)
        self.permissions.revoke(plugin_id)
        self.records.pop(plugin_id, None)
        self._persist_state()
        self.publish_event(
            PluginEventType.PLUGIN_REMOVED,
            {"pluginId": plugin_id, "version": record.manifest.version},
        )

    def reload(self, plugin_id: str) -> PluginRecord:
        record = self.require(plugin_id)
        should_run = record.enabled
        self.disable(plugin_id)
        manifest = PluginManifest.from_path(record.root / "plugin.json")
        replacement = PluginRecord(
            manifest=manifest,
            root=record.root,
            enabled=should_run,
            pinned_version=record.pinned_version,
            diagnostics=record.diagnostics,
            transitions=record.transitions,
            modified_at=max(
                (record.root / "plugin.json").stat().st_mtime,
                (record.root / manifest.entry_point).stat().st_mtime,
            ),
        )
        self._validate_record(replacement)
        self.records[plugin_id] = replacement
        if should_run and self.permissions.is_reviewed(manifest):
            replacement.diagnostics.restarts += 1
            self.start(plugin_id)
        return replacement

    def start_hot_reload(self, interval: float = 1.0) -> None:
        if self._hot_reload_thread and self._hot_reload_thread.is_alive():
            return
        self._hot_reload_stop.clear()

        def monitor() -> None:
            while not self._hot_reload_stop.wait(max(0.25, interval)):
                for plugin_id, record in tuple(self.records.items()):
                    if record.state not in {PluginState.RUNNING, PluginState.PAUSED}:
                        continue
                    try:
                        modified = max(
                            (record.root / "plugin.json").stat().st_mtime,
                            (record.root / record.manifest.entry_point).stat().st_mtime,
                        )
                        if modified > record.modified_at + 1e-6:
                            self.reload(plugin_id)
                    except Exception as exc:
                        record.diagnostics.warnings.append(f"Hot reload failed: {exc}")
                self.unload_inactive()
                if (
                    self.auto_updates_enabled
                    and self.marketplace.entries
                    and time.monotonic() - self._last_auto_update > 1_800
                ):
                    self._last_auto_update = time.monotonic()
                    for entry in self.available_updates():
                        try:
                            self.update_from_marketplace(entry)
                        except Exception as exc:
                            record = self.records.get(entry.plugin_id)
                            if record:
                                record.diagnostics.warnings.append(
                                    f"Automatic update failed: {exc}"
                                )

        self._hot_reload_thread = threading.Thread(
            target=monitor,
            name="morice-plugin-hot-reload",
            daemon=True,
        )
        self._hot_reload_thread.start()

    def unload_inactive(self, max_idle_seconds: float = 1_800.0) -> tuple[str, ...]:
        unloaded: list[str] = []
        now = time.monotonic()
        for record in tuple(self.records.values()):
            if (
                not record.manifest.lazy
                or record.state != PluginState.RUNNING
                or now - record.last_used_at < max(1.0, max_idle_seconds)
            ):
                continue
            self._unregister_contributions(record)
            if record.sandbox:
                record.sandbox.stop()
                record.sandbox = None
            record.transition(PluginState.DISABLED, "Inactive lazy plugin unloaded.")
            record.transition(PluginState.VALIDATED, "Lazy plugin is ready on demand.")
            self._register_contributions(record)
            unloaded.append(record.manifest.plugin_id)
        if unloaded:
            self._persist_state()
        return tuple(unloaded)

    def stop_hot_reload(self) -> None:
        self._hot_reload_stop.set()
        thread = self._hot_reload_thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._hot_reload_thread = None

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self.stop_hot_reload()
        self.publish_event(PluginEventType.APPLICATION_STOPPING, {})
        self._shutdown = True
        self._event_executor.shutdown(wait=True, cancel_futures=False)
        for record in tuple(self.records.values()):
            self._unregister_contributions(record)
            if record.sandbox:
                record.sandbox.stop()
                record.sandbox = None
            if record.state in {
                PluginState.RUNNING,
                PluginState.PAUSED,
                PluginState.LOADED,
            }:
                record.state = PluginState.VALIDATED
        self._persist_state()

    def diagnostics(self, plugin_id: str | None = None) -> dict[str, Any]:
        if plugin_id:
            record = self.require(plugin_id)
            return record.to_dict(
                self.permissions.snapshot(plugin_id),
                process=self._process_metrics(record),
                dependencies=self._dependency_diagnostics(record),
            )
        return {
            "count": len(self.records),
            "running": sum(
                record.state == PluginState.RUNNING for record in self.records.values()
            ),
            "failed": sum(
                record.state == PluginState.FAILED for record in self.records.values()
            ),
            "plugins": [
                self.records[key].to_dict(
                    self.permissions.snapshot(key),
                    process=self._process_metrics(self.records[key]),
                    dependencies=self._dependency_diagnostics(self.records[key]),
                )
                for key in sorted(self.records)
            ],
            "eventHistory": len(self.events.history),
            "marketplace": {
                "source": self.marketplace.source,
                "updatedAt": self.marketplace.updated_at,
                "entries": len(self.marketplace.entries),
                "automaticUpdates": self.auto_updates_enabled,
                "availableUpdates": len(self.available_updates()),
            },
        }

    def command_contributions(self) -> tuple[dict[str, str], ...]:
        result = []
        for plugin_id in sorted(self.records):
            record = self.records[plugin_id]
            if not self._contributions_active(record):
                continue
            for command in record.manifest.contributions.commands:
                result.append(
                    {
                        "key": f"plugin:{plugin_id}:{command.command_id}",
                        "title": command.title,
                        "hint": command.description,
                        "keywords": " ".join(command.keywords),
                    }
                )
        return tuple(result)

    def themes(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "pluginId": plugin_id,
                "id": theme.theme_id,
                "title": theme.title,
                "stylesheet": theme.stylesheet,
            }
            for plugin_id, record in sorted(self.records.items())
            if self._contributions_active(record)
            for theme in record.manifest.contributions.themes
        )

    def workspaces(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "pluginId": plugin_id,
                "id": workspace.workspace_id,
                "title": workspace.title,
                "location": workspace.location,
                "icon": workspace.icon,
            }
            for plugin_id, record in sorted(self.records.items())
            if self._contributions_active(record)
            for workspace in record.manifest.contributions.workspaces
        )

    def models(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "pluginId": plugin_id,
                "id": model.model_id,
                "title": model.title,
                "provider": model.provider,
                "capabilities": model.capabilities,
            }
            for plugin_id, record in sorted(self.records.items())
            if self._contributions_active(record)
            for model in record.manifest.contributions.models
        )

    def contribution_catalog(self) -> dict[str, tuple[dict[str, Any], ...]]:
        def tagged(items: Iterable[Mapping[str, Any]], plugin_id: str):
            return tuple({"pluginId": plugin_id, **dict(item)} for item in items)

        settings: list[dict[str, Any]] = []
        memory: list[dict[str, Any]] = []
        automations: list[dict[str, Any]] = []
        voice: list[dict[str, Any]] = []
        for plugin_id, record in sorted(self.records.items()):
            if not self._contributions_active(record):
                continue
            contributions = record.manifest.contributions
            settings.extend(tagged(contributions.settings, plugin_id))
            memory.extend(tagged(contributions.memory, plugin_id))
            automations.extend(tagged(contributions.automations, plugin_id))
            voice.extend(tagged(contributions.voice, plugin_id))
        return {
            "themes": self.themes(),
            "workspaces": self.workspaces(),
            "models": self.models(),
            "settings": tuple(settings),
            "memory": tuple(memory),
            "automations": tuple(automations),
            "voice": tuple(voice),
            "ui": tuple(
                {
                    "pluginId": plugin_id,
                    "id": item.component_id,
                    "title": item.title,
                    "kind": item.kind,
                    "location": item.location,
                    "icon": item.icon,
                    "commandId": item.command_id,
                }
                for plugin_id, record in sorted(self.records.items())
                if self._contributions_active(record)
                for item in record.manifest.contributions.ui
            ),
        }

    @staticmethod
    def _contributions_active(record: PluginRecord) -> bool:
        return record.state == PluginState.RUNNING or (
            record.enabled
            and record.manifest.lazy
            and record.state == PluginState.VALIDATED
        )

    def require(self, plugin_id: str) -> PluginRecord:
        try:
            return self.records[plugin_id]
        except KeyError as exc:
            raise KeyError(f"Plugin is not installed: {plugin_id}") from exc

    def _dependency_diagnostics(self, record: PluginRecord) -> tuple[dict[str, Any], ...]:
        values = []
        for dependency in record.manifest.dependencies:
            installed = self.records.get(dependency.plugin_id)
            values.append(
                {
                    "id": dependency.plugin_id,
                    "requiredVersion": dependency.version,
                    "optional": dependency.optional,
                    "installedVersion": installed.manifest.version if installed else "",
                    "satisfied": bool(
                        installed
                        and version_satisfies(
                            installed.manifest.version, dependency.version
                        )
                    ),
                }
            )
        return tuple(values)

    def _process_metrics(self, record: PluginRecord) -> dict[str, Any]:
        pid = record.sandbox.pid if record.sandbox else 0
        raw = _process_resource_snapshot(pid)
        cpu_total = float(raw.get("cpuTimeSeconds", 0.0))
        now = time.monotonic()
        previous = self._process_samples.get(pid)
        cpu_percent = 0.0
        if pid and previous and now > previous[0]:
            cpu_percent = max(
                0.0,
                min(
                    100.0 * max(1, os.cpu_count() or 1),
                    ((cpu_total - previous[1]) / (now - previous[0])) * 100.0,
                ),
            )
        if pid:
            self._process_samples[pid] = (now, cpu_total)
        return {
            **raw,
            "cpuUsagePercent": round(cpu_percent, 2),
            "gpuUsage": "unavailable",
            "gpuReason": (
                "Per-plugin GPU accounting is not exposed by the portable Python host."
            ),
        }

    def _register_contributions(self, record: PluginRecord) -> None:
        self._unregister_contributions(record)
        if self.tool_registry is not None:
            for item in record.manifest.contributions.tools:
                risk = {
                    "read_only": RiskLevel.READ_ONLY,
                    "workspace_write": RiskLevel.WORKSPACE_WRITE,
                    "dangerous": RiskLevel.DANGEROUS,
                }.get(item.risk, RiskLevel.READ_ONLY)
                definition = ToolDefinition(
                    tool_id=item.tool_id,
                    display_name=item.title,
                    description=item.description,
                    input_schema=item.input_schema,
                    output_schema=item.output_schema,
                    permissions=item.permissions,
                    timeout_seconds=item.timeout_seconds,
                    risk=risk,
                    version=record.manifest.version,
                )

                def handler(
                    arguments: dict[str, Any],
                    *,
                    plugin_id: str = record.manifest.plugin_id,
                    tool_id: str = item.tool_id,
                    timeout: float = item.timeout_seconds,
                ) -> Any:
                    return self.invoke(
                        plugin_id,
                        "tool",
                        {"id": tool_id, "arguments": arguments},
                        timeout=timeout,
                    )

                self.tool_registry.register(definition, handler)
                record.registered_tools.append(item.tool_id)
        if self.renderer_registry is not None:
            for item in record.manifest.contributions.renderers:
                proxy = PluginRendererProxy(self, record.manifest.plugin_id, item)
                self.renderer_registry.register(proxy)
                record.registered_renderers.append(item.renderer_id)
        if self._command_callback:
            self._command_callback()

    def _unregister_contributions(self, record: PluginRecord) -> None:
        if self.tool_registry is not None:
            for tool_id in record.registered_tools:
                self.tool_registry.unregister(tool_id)
        if self.renderer_registry is not None:
            for renderer_id in record.registered_renderers:
                self.renderer_registry.unregister(renderer_id)
        record.registered_tools.clear()
        record.registered_renderers.clear()
        if self._command_callback:
            self._command_callback()

    def _on_host_event(self, plugin_id: str, message: dict[str, Any]) -> None:
        record = self.records.get(plugin_id)
        payload = message.get("payload") or {}
        event_name = str(message.get("event", ""))
        if record and event_name == "log":
            record.diagnostics.logs.append(
                {
                    "timestamp": _utc_now(),
                    "level": str(payload.get("level", "INFO")),
                    "message": str(payload.get("message", ""))[:16_000],
                    "metadata": payload.get("metadata") or {},
                }
            )
        elif event_name == "notification" and self.notification_callback:
            self.notification_callback(
                str(payload.get("message", "")),
                str(payload.get("level", "info")),
            )
            self.events.publish(
                PluginEventType.NOTIFICATION_CREATED,
                {
                    "pluginId": plugin_id,
                    "title": str(payload.get("title", "")),
                    "level": str(payload.get("level", "info")),
                },
                source=plugin_id,
            )
        elif event_name == "plugin.event":
            event_type = str(payload.get("name", "plugin.event"))
            event = self.events.publish(
                event_type,
                payload.get("data") or {},
                source=plugin_id,
            )
            self._fan_out_event(event, exclude_plugin_id=plugin_id)

    def _deliver_event(self, record: PluginRecord, event: PluginEvent) -> None:
        sandbox = record.sandbox
        if record.state != PluginState.RUNNING or sandbox is None:
            return
        try:
            sandbox.call(
                "event",
                {"event": event.event_type, "payload": event.payload},
                timeout=2.0,
            )
        except Exception as exc:
            record.diagnostics.warnings.append(
                f"Event delivery failed: {event.event_type}: {exc}"
            )

    def _mark_failed(
        self,
        record: PluginRecord,
        error: Exception,
        *,
        crash: bool,
    ) -> None:
        self._unregister_contributions(record)
        if record.sandbox:
            record.sandbox.terminate()
            record.sandbox = None
        record.diagnostics.last_error = str(error)
        if crash:
            record.diagnostics.crashes += 1
        if record.state != PluginState.FAILED:
            try:
                record.transition(PluginState.FAILED, str(error)[:500])
            except PluginValidationError:
                record.state = PluginState.FAILED
        self.publish_event(
            PluginEventType.PLUGIN_FAILED,
            {"pluginId": record.manifest.plugin_id, "error": str(error), "crash": crash},
        )
        self._persist_state()

    def _backup(self, root: Path, manifest: PluginManifest) -> Path:
        destination = (
            self.backup_root
            / manifest.plugin_id
            / f"{manifest.version}-{int(time.time() * 1000)}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root, destination)
        return destination

    def _persist_state(self) -> None:
        payload = {
            plugin_id: {
                "version": record.manifest.version,
                "state": record.state.value,
                "enabled": record.enabled,
                "pinnedVersion": record.pinned_version,
            }
            for plugin_id, record in self.records.items()
            if record.state != PluginState.UNINSTALLED
        }
        _atomic_json(self.state_path, payload)
        self._saved_state = payload

    def _log(self, level: str, message: str) -> None:
        if self.logger:
            try:
                self.logger(level, message, category="plugins")
                return
            except TypeError:
                try:
                    self.logger(level, message)
                    return
                except Exception:
                    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha256(value: str) -> bool:
    text = str(value or "").strip()
    return len(text) == 64 and all(character in "0123456789abcdefABCDEF" for character in text)


def _manifest_from_package(path: Path) -> PluginManifest:
    source = path.resolve()
    if not source.is_file() or not zipfile.is_zipfile(source):
        raise PluginValidationError("Plugin update must be a valid ZIP archive.")
    with zipfile.ZipFile(source) as archive:
        candidates = []
        for item in archive.infolist():
            relative = Path(item.filename.replace("\\", "/"))
            if (
                relative.name == "plugin.json"
                and len(relative.parts) <= 2
                and not relative.is_absolute()
                and ".." not in relative.parts
            ):
                candidates.append(item)
        if len(candidates) != 1:
            raise PluginValidationError(
                "Plugin package must contain exactly one plugin.json at its root."
            )
        if candidates[0].file_size > 512 * 1024:
            raise PluginValidationError("Plugin manifest is larger than 512 KB.")
        try:
            payload = json.loads(archive.read(candidates[0]).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError, KeyError) as exc:
            raise PluginValidationError(f"Plugin manifest is not valid JSON: {exc}") from exc
    return PluginManifest.from_dict(payload)


def _process_resource_snapshot(pid: int) -> dict[str, Any]:
    if pid <= 0:
        return {
            "pid": 0,
            "running": False,
            "memoryBytes": 0,
            "cpuTimeSeconds": 0.0,
        }
    if os.name == "nt":
        class FileTime(ctypes.Structure):
            _fields_ = [
                ("low", ctypes.c_ulong),
                ("high", ctypes.c_ulong),
            ]

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("pageFaultCount", ctypes.c_ulong),
                ("peakWorkingSetSize", ctypes.c_size_t),
                ("workingSetSize", ctypes.c_size_t),
                ("quotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("quotaPagedPoolUsage", ctypes.c_size_t),
                ("quotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("quotaNonPagedPoolUsage", ctypes.c_size_t),
                ("pagefileUsage", ctypes.c_size_t),
                ("peakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.GetProcessTimes.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ulong,
        ]
        handle = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
        if not handle:
            return {
                "pid": pid,
                "running": False,
                "memoryBytes": 0,
                "cpuTimeSeconds": 0.0,
            }
        try:
            memory = ProcessMemoryCounters()
            memory.cb = ctypes.sizeof(memory)
            working_set = 0
            if psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(memory), ctypes.sizeof(memory)
            ):
                working_set = int(memory.workingSetSize)
            creation = FileTime()
            exit_time = FileTime()
            kernel = FileTime()
            user = FileTime()
            cpu_time = 0.0
            if kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                kernel_ticks = (kernel.high << 32) | kernel.low
                user_ticks = (user.high << 32) | user.low
                cpu_time = (kernel_ticks + user_ticks) / 10_000_000.0
            return {
                "pid": pid,
                "running": True,
                "memoryBytes": working_set,
                "cpuTimeSeconds": round(cpu_time, 4),
            }
        finally:
            kernel32.CloseHandle(handle)
    stat_path = Path(f"/proc/{pid}/stat")
    statm_path = Path(f"/proc/{pid}/statm")
    try:
        fields = stat_path.read_text(encoding="utf-8").split()
        clock_ticks = float(os.sysconf("SC_CLK_TCK"))
        cpu_time = (float(fields[13]) + float(fields[14])) / clock_ticks
        pages = int(statm_path.read_text(encoding="utf-8").split()[1])
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        return {
            "pid": pid,
            "running": True,
            "memoryBytes": pages * page_size,
            "cpuTimeSeconds": round(cpu_time, 4),
        }
    except (OSError, ValueError, IndexError):
        return {
            "pid": pid,
            "running": False,
            "memoryBytes": 0,
            "cpuTimeSeconds": 0.0,
        }


__all__ = [
    "MarketplaceEntry",
    "PermissionReviewRequired",
    "PluginDiagnostics",
    "PluginEventBus",
    "PluginManager",
    "PluginMarketplace",
    "PluginPermissionStore",
    "PluginRecord",
    "PluginRendererProxy",
    "PluginSandbox",
]
