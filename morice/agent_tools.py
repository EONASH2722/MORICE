from __future__ import annotations

import difflib
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .agent_types import (
    ActionRecord,
    PermissionStatus,
    RiskLevel,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolStatus,
)
from .project_index import ProjectIndexer, TEXT_EXTENSIONS
from .project_runtime import (
    ProjectValidationError,
    build_launch_plan,
    validate_project_file,
)


ToolHandler = Callable[[dict[str, Any]], ToolResult | dict[str, Any] | Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = None
    if path.is_file():
        try:
            existing_mode = path.stat().st_mode & 0o7777
        except OSError:
            existing_mode = None
    handle, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".morice-tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if existing_mode is not None:
            os.chmod(temporary, existing_mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ToolValidationError(ValueError):
    pass


class PermissionPolicy:
    def __init__(self):
        self._tokens: dict[str, tuple[str, str, float]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def fingerprint(tool_id: str, arguments: dict[str, Any]) -> str:
        payload = json.dumps(
            {"tool": tool_id, "arguments": arguments},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def grant(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        ttl_seconds: float = 300,
    ) -> str:
        token = uuid.uuid4().hex
        with self._lock:
            now = time.monotonic()
            self._tokens = {
                key: value
                for key, value in self._tokens.items()
                if value[2] > now
            }
            self._tokens[token] = (
                tool_id,
                self.fingerprint(tool_id, arguments),
                now + max(5.0, ttl_seconds),
            )
        return token

    def consume(self, call: ToolCall) -> bool:
        if not call.permission_token:
            return False
        with self._lock:
            entry = self._tokens.pop(call.permission_token, None)
        if not entry:
            return False
        tool_id, fingerprint, expires_at = entry
        return (
            tool_id == call.tool_id
            and fingerprint == self.fingerprint(call.tool_id, call.arguments)
            and time.monotonic() <= expires_at
        )


class ActionHistory:
    def __init__(self, directory: str | os.PathLike[str], *, limit: int = 2_000):
        self.directory = Path(directory)
        self.path = self.directory / "actions.jsonl"
        self.limit = max(100, int(limit))
        self.directory.mkdir(parents=True, exist_ok=True)
        self._records: list[ActionRecord] = []
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        for line in lines[-self.limit :]:
            try:
                item = json.loads(line)
                self._records.append(
                    ActionRecord(
                        action_id=str(item["action_id"]),
                        timestamp=str(item["timestamp"]),
                        tool_id=str(item["tool_id"]),
                        parameters=dict(item.get("parameters", {})),
                        duration_ms=float(item.get("duration_ms", 0)),
                        success=bool(item.get("success", False)),
                        verified=bool(item.get("verified", False)),
                        modified_files=tuple(item.get("modified_files", ())),
                        generated_files=tuple(item.get("generated_files", ())),
                        artifacts=tuple(item.get("artifacts", ())),
                        errors=tuple(item.get("errors", ())),
                        replayable=bool(item.get("replayable", False)),
                        undo_id=str(item.get("undo_id", "")),
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue

    def append(self, record: ActionRecord) -> None:
        serialized = json.dumps(record.to_dict(), ensure_ascii=False, default=str)
        with self._lock:
            self._records.append(record)
            self._records = self._records[-self.limit :]
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(serialized + "\n")
            if self.path.stat().st_size > 8 * 1024 * 1024:
                compact = (
                    "\n".join(
                        json.dumps(item.to_dict(), ensure_ascii=False, default=str)
                        for item in self._records
                    )
                    + "\n"
                )
                _atomic_write(self.path, compact.encode("utf-8"))

    def recent(self, limit: int = 100) -> tuple[ActionRecord, ...]:
        with self._lock:
            return tuple(self._records[-max(1, int(limit)) :])

    def get(self, action_id: str) -> ActionRecord | None:
        with self._lock:
            return next(
                (record for record in reversed(self._records) if record.action_id == action_id),
                None,
            )


class UndoStore:
    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        limit: int = 50,
        max_bytes: int = 512 * 1024 * 1024,
    ):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.limit = max(1, int(limit))
        self.max_bytes = max(16 * 1024 * 1024, int(max_bytes))
        self._lock = threading.RLock()

    def create(self, root: Path, changes: list[dict[str, Any]]) -> str:
        with self._lock:
            undo_id = uuid.uuid4().hex
            target = self.directory / undo_id
            target.mkdir(parents=True)
            entries: list[dict[str, Any]] = []
            try:
                for index, change in enumerate(changes):
                    relative = str(change["path"]).replace("\\", "/")
                    destination = _resolve_within(root, relative)
                    existed = destination.is_file()
                    backup = ""
                    if existed:
                        backup = f"{index}.bak"
                        (target / backup).write_bytes(destination.read_bytes())
                    after = str(change["content"]).encode("utf-8")
                    entries.append(
                        {
                            "path": relative,
                            "existed": existed,
                            "backup": backup,
                            "applied_sha256": hashlib.sha256(after).hexdigest(),
                        }
                    )
                (target / "manifest.json").write_text(
                    json.dumps({"root": str(root), "entries": entries}, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                shutil.rmtree(target, ignore_errors=True)
                raise
            self._prune(exclude=undo_id)
            return undo_id

    def restore(self, undo_id: str, *, force: bool = False) -> ToolResult:
        started = time.perf_counter()
        with self._lock:
            target = self.directory / undo_id
            manifest_path = target / "manifest.json"
            if not re.fullmatch(r"[a-f0-9]{32}", undo_id or "") or not manifest_path.is_file():
                return ToolResult(
                    "action.undo",
                    False,
                    (time.perf_counter() - started) * 1000,
                    errors=["Undo record was not found."],
                )
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                root = Path(manifest["root"]).resolve()
                operations: list[tuple[Path, bool, bytes | None]] = []
                current: list[tuple[Path, bool, bytes | None]] = []
                conflicts: list[str] = []
                for entry in manifest["entries"]:
                    destination = _resolve_within(root, entry["path"])
                    current_exists = destination.is_file()
                    current_data = destination.read_bytes() if current_exists else None
                    current.append((destination, current_exists, current_data))
                    expected_digest = str(entry.get("applied_sha256", ""))
                    if not force and (
                        not current_exists
                        or hashlib.sha256(current_data or b"").hexdigest() != expected_digest
                    ):
                        conflicts.append(str(entry["path"]))
                    if entry["existed"]:
                        backup_name = str(entry["backup"])
                        if not re.fullmatch(r"\d+\.bak", backup_name):
                            raise ValueError("Undo backup name is invalid.")
                        backup_data = (target / backup_name).read_bytes()
                        operations.append((destination, True, backup_data))
                    else:
                        operations.append((destination, False, None))
                if conflicts:
                    return ToolResult(
                        "action.undo",
                        False,
                        (time.perf_counter() - started) * 1000,
                        errors=[
                            "Undo stopped because files changed after the MORICE patch: "
                            + ", ".join(conflicts[:10])
                        ],
                    )
                modified = [str(path) for path, _, _ in operations]
                try:
                    for destination, should_exist, data in operations:
                        if should_exist:
                            _atomic_write(destination, data or b"")
                        elif destination.exists():
                            if not destination.is_file():
                                raise OSError(f"Undo target is not a file: {destination}")
                            destination.unlink()
                    verified = all(
                        (
                            path.is_file() and path.read_bytes() == data
                            if should_exist
                            else not path.exists()
                        )
                        for path, should_exist, data in operations
                    )
                    if not verified:
                        raise OSError("Undo verification failed.")
                except OSError as exc:
                    rollback_errors: list[str] = []
                    for path, should_exist, data in current:
                        try:
                            if should_exist:
                                _atomic_write(path, data or b"")
                            elif path.exists() and path.is_file():
                                path.unlink()
                        except OSError as rollback_exc:
                            rollback_errors.append(str(rollback_exc))
                    detail = f"Undo failed: {exc}"
                    if rollback_errors:
                        detail += "; rollback also failed: " + "; ".join(rollback_errors[:3])
                    return ToolResult(
                        "action.undo",
                        False,
                        (time.perf_counter() - started) * 1000,
                        errors=[detail],
                    )
                shutil.rmtree(target, ignore_errors=True)
                return ToolResult(
                    "action.undo",
                    True,
                    (time.perf_counter() - started) * 1000,
                    output={"restored": modified},
                    modified_files=modified,
                    verified=True,
                )
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                return ToolResult(
                    "action.undo",
                    False,
                    (time.perf_counter() - started) * 1000,
                    errors=[f"Undo failed: {exc}"],
                )

    def _prune(self, *, exclude: str = "") -> None:
        entries: list[tuple[Path, int, float]] = []
        for path in self.directory.iterdir():
            if not path.is_dir() or path.name == exclude:
                continue
            try:
                files = [item for item in path.rglob("*") if item.is_file()]
                size = sum(item.stat().st_size for item in files)
                modified = max((item.stat().st_mtime for item in files), default=path.stat().st_mtime)
                entries.append((path, size, modified))
            except OSError:
                continue
        entries.sort(key=lambda item: item[2], reverse=True)
        used = 0
        for index, (path, size, _modified) in enumerate(entries):
            used += size
            if index >= self.limit - 1 or used > self.max_bytes:
                shutil.rmtree(path, ignore_errors=True)


def _resolve_within(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ToolValidationError("A relative path inside the workspace is required.")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ToolValidationError("Path escapes the permitted workspace.") from exc
    return resolved


class ToolRegistry:
    def __init__(self):
        self._definitions: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._lock = threading.RLock()

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{2,80}", definition.tool_id):
            raise ValueError(f"Invalid tool id: {definition.tool_id}")
        with self._lock:
            if definition.tool_id in self._definitions:
                raise ValueError(f"Tool already registered: {definition.tool_id}")
            self._definitions[definition.tool_id] = definition
            self._handlers[definition.tool_id] = handler

    def definition(self, tool_id: str) -> ToolDefinition | None:
        return self._definitions.get(tool_id)

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def handler(self, tool_id: str) -> ToolHandler | None:
        return self._handlers.get(tool_id)

    def validate(self, call: ToolCall) -> ToolDefinition:
        definition = self.definition(call.tool_id)
        if not definition:
            raise ToolValidationError(f"Tool does not exist: {call.tool_id}")
        if definition.health_status != ToolStatus.READY:
            raise ToolValidationError(
                f"Tool is not ready: {definition.health_status.value}"
            )
        systems = {item.lower() for item in definition.supported_platforms}
        if "any" not in systems and platform.system().lower() not in systems:
            raise ToolValidationError(
                f"Tool does not support {platform.system()}."
            )
        missing = [
            dependency
            for dependency in definition.dependencies
            if not shutil.which(dependency)
        ]
        if missing:
            raise ToolValidationError(
                "Missing dependencies: " + ", ".join(missing)
            )
        self._validate_schema(call.arguments, definition.input_schema)
        return definition

    @staticmethod
    def _validate_schema(value: Any, schema: dict[str, Any], path: str = "arguments") -> None:
        expected = schema.get("type")
        types = {
            "object": dict,
            "array": list,
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
        }
        type_matches = expected not in types or isinstance(value, types[expected])
        if expected in {"integer", "number"} and isinstance(value, bool):
            type_matches = False
        if not type_matches:
            raise ToolValidationError(f"{path} must be {expected}.")
        if expected == "number" and not math.isfinite(float(value)):
            raise ToolValidationError(f"{path} must be finite.")
        if expected == "object":
            required = schema.get("required", ())
            for key in required:
                if key not in value:
                    raise ToolValidationError(f"{path}.{key} is required.")
            properties = schema.get("properties", {})
            for key, child in value.items():
                if key in properties:
                    ToolRegistry._validate_schema(child, properties[key], f"{path}.{key}")
                elif schema.get("additionalProperties") is False:
                    raise ToolValidationError(f"{path}.{key} is not supported.")
        elif expected == "array":
            if len(value) > int(schema.get("maxItems", 100_000)):
                raise ToolValidationError(f"{path} has too many items.")
            child = schema.get("items")
            if child:
                for index, item in enumerate(value):
                    ToolRegistry._validate_schema(item, child, f"{path}[{index}]")
        elif expected == "string":
            if len(value) > int(schema.get("maxLength", 1_000_000)):
                raise ToolValidationError(f"{path} is too long.")
            if pattern := schema.get("pattern"):
                if not re.fullmatch(pattern, value):
                    raise ToolValidationError(f"{path} has an invalid format.")
        if "enum" in schema and value not in schema["enum"]:
            raise ToolValidationError(f"{path} must be one of {schema['enum']}.")


class AgentToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        history: ActionHistory,
        permissions: PermissionPolicy,
        *,
        logger: Callable[..., Any] | None = None,
    ):
        self.registry = registry
        self.history = history
        self.permissions = permissions
        self.logger = logger

    def execute(self, call: ToolCall) -> ToolResult:
        started = time.perf_counter()
        try:
            definition = self.registry.validate(call)
        except ToolValidationError as exc:
            result = ToolResult(
                call.tool_id,
                False,
                (time.perf_counter() - started) * 1000,
                errors=[str(exc)],
            )
            self._record(call, result, None)
            return result
        permission_status = PermissionStatus.NOT_REQUIRED
        if definition.risk != RiskLevel.READ_ONLY or definition.permissions:
            if not self.permissions.consume(call):
                result = ToolResult(
                    call.tool_id,
                    False,
                    (time.perf_counter() - started) * 1000,
                    errors=[
                        "Explicit permission is required before this tool can run."
                    ],
                    permission_status=PermissionStatus.REQUIRED,
                )
                self._record(call, result, definition)
                return result
            permission_status = PermissionStatus.GRANTED
        handler = self.registry.handler(call.tool_id)
        if handler is None:
            result = ToolResult(
                call.tool_id,
                False,
                (time.perf_counter() - started) * 1000,
                errors=["Tool handler is unavailable."],
            )
            self._record(call, result, definition)
            return result
        try:
            handler_arguments = dict(call.arguments)
            handler_arguments["_call_id"] = call.call_id or uuid.uuid4().hex
            if (
                definition.risk != RiskLevel.READ_ONLY
                and not definition.cancellation_supported
            ):
                # A timed-out write must never continue mutating files after MORICE
                # reports failure. Mutation handlers therefore run synchronously
                # and enforce their own bounded subprocess/file operations.
                value = handler(handler_arguments)
            else:
                pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="morice-tool")
                future = pool.submit(handler, handler_arguments)
                try:
                    value = future.result(timeout=definition.timeout_seconds)
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)
            duration = (time.perf_counter() - started) * 1000
            if isinstance(value, ToolResult):
                result = value
                result.duration_ms = duration
                if result.tool_id != call.tool_id:
                    result.success = False
                    result.verified = False
                    result.errors.append(
                        f"Tool returned a mismatched id: {result.tool_id}."
                    )
                    result.tool_id = call.tool_id
            else:
                result = ToolResult(
                    call.tool_id,
                    True,
                    duration,
                    output=_safe_json(value),
                    verified=True,
                )
            result.permission_status = permission_status
            if result.success and result.output is not None:
                try:
                    self.registry._validate_schema(
                        result.output,
                        definition.output_schema,
                        "output",
                    )
                except ToolValidationError as exc:
                    result.success = False
                    result.verified = False
                    result.errors.append(f"Tool returned invalid output: {exc}")
        except FutureTimeout:
            result = ToolResult(
                call.tool_id,
                False,
                (time.perf_counter() - started) * 1000,
                errors=[f"Tool timed out after {definition.timeout_seconds:g} seconds."],
                retryable=definition.idempotent,
                permission_status=permission_status,
            )
        except Exception as exc:  # noqa: BLE001
            result = ToolResult(
                call.tool_id,
                False,
                (time.perf_counter() - started) * 1000,
                errors=[f"{type(exc).__name__}: {exc}"],
                retryable=definition.idempotent,
                permission_status=permission_status,
            )
        self._record(call, result, definition)
        return result

    def _record(
        self,
        call: ToolCall,
        result: ToolResult,
        definition: ToolDefinition | None,
    ) -> None:
        action_id = call.call_id or uuid.uuid4().hex
        parameters, replay_safe = self._history_parameters(call)
        record = ActionRecord(
            action_id=action_id,
            timestamp=_utc_now(),
            tool_id=call.tool_id,
            parameters=parameters,
            duration_ms=result.duration_ms,
            success=result.success,
            verified=result.verified,
            modified_files=tuple(result.modified_files),
            generated_files=tuple(result.generated_files),
            artifacts=tuple(result.artifacts),
            errors=tuple(result.errors),
            replayable=bool(
                definition
                and definition.idempotent
                and definition.risk == RiskLevel.READ_ONLY
                and result.success
                and replay_safe
            ),
            undo_id=str(result.metadata.get("undoId", "")),
        )
        try:
            self.history.append(record)
        except OSError as exc:
            result.warnings.append(f"Action history could not be saved: {exc}")
        if self.logger:
            try:
                self.logger(
                    "INFO" if result.success else "ERROR",
                    f"Tool {call.tool_id} {'completed' if result.success else 'failed'}.",
                    category="agent-tool",
                    metadata={
                        "actionId": action_id,
                        "durationMs": round(result.duration_ms, 2),
                        "verified": result.verified,
                        "errors": result.errors,
                    },
                )
            except Exception:  # noqa: BLE001
                result.warnings.append("The tool result could not be written to the runtime log.")

    @staticmethod
    def _history_parameters(call: ToolCall) -> tuple[dict[str, Any], bool]:
        arguments = dict(call.arguments)
        if call.tool_id in {"filesystem.preview_patch", "filesystem.apply_patch"}:
            changes = []
            for change in arguments.get("changes", ()):
                content = str(change.get("content", ""))
                changes.append(
                    {
                        "path": str(change.get("path", "")),
                        "contentBytes": len(content.encode("utf-8")),
                        "contentSha256": hashlib.sha256(
                            content.encode("utf-8")
                        ).hexdigest(),
                    }
                )
            return {
                "root": str(arguments.get("root", "")),
                "changes": changes,
            }, False
        return json.loads(json.dumps(arguments, default=str)), True


class BuiltinTools:
    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        logger: Callable[..., Any] | None = None,
    ):
        self.directory = Path(directory)
        self.registry = ToolRegistry()
        self.permissions = PermissionPolicy()
        self.history = ActionHistory(self.directory / "history")
        self.undo_store = UndoStore(self.directory / "undo")
        self.indexer = ProjectIndexer()
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._process_lock = threading.RLock()
        self._workspace_lock = threading.RLock()
        self.executor = AgentToolExecutor(
            self.registry,
            self.history,
            self.permissions,
            logger=logger,
        )
        self._register()

    def cancel(self, call_id: str) -> bool:
        with self._process_lock:
            process = self._active_processes.get(call_id)
        if process is None or process.poll() is not None:
            return False
        try:
            process.terminate()
            return True
        except OSError:
            return False

    def replay(self, action_id: str) -> ToolResult:
        record = self.history.get(action_id)
        if record is None:
            return ToolResult(
                "action.replay",
                False,
                0,
                errors=["Action was not found."],
            )
        if not record.replayable:
            return ToolResult(
                "action.replay",
                False,
                0,
                errors=["This action is not safe to replay automatically."],
            )
        return self.executor.execute(
            ToolCall(
                record.tool_id,
                dict(record.parameters),
                call_id=f"replay-{uuid.uuid4().hex}",
            )
        )

    def _register(self) -> None:
        object_schema = {"type": "object", "additionalProperties": True}
        self.registry.register(
            ToolDefinition(
                "filesystem.search",
                "Search Files",
                "Search file names and UTF-8 text inside a permitted workspace.",
                {
                    "type": "object",
                    "required": ["root", "query"],
                    "properties": {
                        "root": {"type": "string", "maxLength": 2_048},
                        "query": {"type": "string", "maxLength": 1_000},
                        "limit": {"type": "integer"},
                    },
                },
                object_schema,
                timeout_seconds=30,
            ),
            self._filesystem_search,
        )
        self.registry.register(
            ToolDefinition(
                "project.index",
                "Index Project",
                "Index project files, symbols, dependencies, build systems, and Git state.",
                {
                    "type": "object",
                    "required": ["root"],
                    "properties": {
                        "root": {"type": "string", "maxLength": 2_048},
                        "query": {"type": "string", "maxLength": 2_000},
                    },
                },
                object_schema,
                timeout_seconds=60,
            ),
            self._project_index,
        )
        self.registry.register(
            ToolDefinition(
                "project.verify",
                "Verify Project",
                "Validate text source files and detect a runnable entry point.",
                {
                    "type": "object",
                    "required": ["root"],
                    "properties": {
                        "root": {"type": "string", "maxLength": 2_048},
                    },
                },
                object_schema,
                timeout_seconds=90,
            ),
            self._project_verify,
        )
        change_schema = {
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {"type": "string", "maxLength": 2_048},
                "content": {"type": "string", "maxLength": 8_000_000},
                "expected_exists": {"type": "boolean"},
                "expected_sha256": {
                    "type": "string",
                    "pattern": r"[a-f0-9]{64}",
                },
            },
            "additionalProperties": False,
        }
        patch_input = {
            "type": "object",
            "required": ["root", "changes"],
            "properties": {
                "root": {"type": "string", "maxLength": 2_048},
                "changes": {"type": "array", "maxItems": 500, "items": change_schema},
            },
        }
        self.registry.register(
            ToolDefinition(
                "filesystem.preview_patch",
                "Preview Patch",
                "Generate a unified diff without modifying files.",
                patch_input,
                object_schema,
                timeout_seconds=30,
            ),
            self._preview_patch,
        )
        self.registry.register(
            ToolDefinition(
                "filesystem.apply_patch",
                "Apply Patch",
                "Atomically apply an approved multi-file patch and create undo data.",
                patch_input,
                object_schema,
                permissions=("workspace.write", "file.overwrite"),
                timeout_seconds=60,
                cancellation_supported=False,
                risk=RiskLevel.WORKSPACE_WRITE,
                idempotent=False,
            ),
            self._apply_patch,
        )
        self.registry.register(
            ToolDefinition(
                "action.undo",
                "Undo Action",
                "Restore files from a previous MORICE patch action.",
                {
                    "type": "object",
                    "required": ["undo_id"],
                    "properties": {
                        "undo_id": {
                            "type": "string",
                            "pattern": r"[a-f0-9]{32}",
                        }
                    },
                },
                object_schema,
                permissions=("workspace.write",),
                timeout_seconds=30,
                risk=RiskLevel.WORKSPACE_WRITE,
                idempotent=False,
            ),
            self._undo_action,
        )
        self.registry.register(
            ToolDefinition(
                "terminal.run",
                "Run Command",
                "Run one executable without shell expansion and capture output.",
                {
                    "type": "object",
                    "required": ["cwd", "command"],
                    "properties": {
                        "cwd": {"type": "string", "maxLength": 2_048},
                        "command": {
                            "type": "array",
                            "maxItems": 100,
                            "items": {"type": "string", "maxLength": 8_192},
                        },
                        "timeout": {"type": "number"},
                    },
                },
                object_schema,
                permissions=("process.execute",),
                timeout_seconds=615,
                cancellation_supported=True,
                risk=RiskLevel.DANGEROUS,
                idempotent=False,
            ),
            self._terminal_run,
        )
        for tool_id, display, args, timeout in (
            ("git.status", "Git Status", ("status", "--short", "--branch"), 20),
            ("git.diff", "Git Diff", ("diff", "--no-ext-diff"), 30),
            ("git.history", "Git History", ("log", "-20", "--pretty=%h %ad %s", "--date=short"), 20),
            ("git.branches", "Git Branches", ("branch", "--all", "--no-color"), 20),
        ):
            self.registry.register(
                ToolDefinition(
                    tool_id,
                    display,
                    f"Read {display.lower()} from a local repository.",
                    {
                        "type": "object",
                        "required": ["root"],
                        "properties": {
                            "root": {"type": "string", "maxLength": 2_048}
                        },
                    },
                    object_schema,
                    dependencies=("git",),
                    timeout_seconds=timeout,
                ),
                lambda arguments, command=args, registered_id=tool_id: self._git_read(
                    arguments,
                    command,
                    registered_id,
                ),
            )
        self.registry.register(
            ToolDefinition(
                "git.blame",
                "Git Blame",
                "Read line history for one workspace file.",
                {
                    "type": "object",
                    "required": ["root", "path"],
                    "properties": {
                        "root": {"type": "string", "maxLength": 2_048},
                        "path": {"type": "string", "maxLength": 2_048},
                    },
                },
                object_schema,
                dependencies=("git",),
                timeout_seconds=30,
            ),
            self._git_blame,
        )
        mutation_schema = {
            "type": "object",
            "required": ["root"],
            "properties": {
                "root": {"type": "string", "maxLength": 2_048},
                "message": {"type": "string", "maxLength": 10_000},
                "branch": {"type": "string", "maxLength": 500},
                "remote": {"type": "string", "maxLength": 500},
                "paths": {
                    "type": "array",
                    "maxItems": 500,
                    "items": {"type": "string", "maxLength": 2_048},
                },
            },
        }
        for tool_id, display, permission in (
            ("git.stash", "Git Stash", "git.stash"),
            ("git.restore", "Git Restore", "git.restore"),
            ("git.checkout", "Git Checkout", "git.checkout"),
            ("git.commit", "Git Commit", "git.commit"),
            ("git.push", "Git Push", "git.push"),
        ):
            self.registry.register(
                ToolDefinition(
                    tool_id,
                    display,
                    f"Run an explicitly approved {display.lower()} operation.",
                    mutation_schema,
                    object_schema,
                    permissions=(permission,),
                    dependencies=("git",),
                    timeout_seconds=180,
                    risk=RiskLevel.DANGEROUS,
                    idempotent=False,
                ),
                lambda arguments, operation=tool_id.split(".", 1)[1], registered_id=tool_id: self._git_mutation(
                    arguments,
                    operation,
                    registered_id,
                ),
            )

    def _filesystem_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        root = Path(arguments["root"]).expanduser().resolve()
        if not root.is_dir():
            raise ToolValidationError("Search root is not a directory.")
        query = str(arguments["query"]).strip().lower()
        if not query:
            raise ToolValidationError("Search query cannot be empty.")
        limit = max(1, min(500, int(arguments.get("limit", 100))))
        matches: list[dict[str, Any]] = []
        scanned = 0
        deadline = time.monotonic() + 25
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [
                name for name in dirnames
                if name not in {".git", "node_modules", ".venv", "dist", "build"}
                and not (Path(dirpath) / name).is_symlink()
            ]
            for filename in filenames:
                path = Path(dirpath) / filename
                if path.is_symlink():
                    continue
                scanned += 1
                if scanned > 50_000 or time.monotonic() >= deadline:
                    return {
                        "matches": matches,
                        "truncated": True,
                        "reason": "search budget reached",
                    }
                relative = path.relative_to(root).as_posix()
                if query in relative.lower():
                    matches.append({"path": relative, "line": 0, "preview": ""})
                if len(matches) >= limit:
                    return {"matches": matches, "truncated": True}
                try:
                    if path.stat().st_size > 1_000_000:
                        continue
                    with path.open("r", encoding="utf-8", errors="replace") as stream:
                        for line_number, line in enumerate(stream, start=1):
                            if query in line.lower():
                                matches.append(
                                    {
                                        "path": relative,
                                        "line": line_number,
                                        "preview": line.strip()[:500],
                                    }
                                )
                                if len(matches) >= limit:
                                    return {"matches": matches, "truncated": True}
                except OSError:
                    continue
        return {"matches": matches, "truncated": False}

    def _project_index(self, arguments: dict[str, Any]) -> dict[str, Any]:
        index = self.indexer.build(arguments["root"])
        value = index.to_dict()
        query = str(arguments.get("query", "")).strip()
        if query:
            relevant = list(self.indexer.search(index, query))
            value["relevant"] = relevant
            root = Path(index.root)
            context_files: list[dict[str, Any]] = []
            used = 0
            for item in relevant:
                if used >= 60_000:
                    break
                path = _resolve_within(root, str(item["path"]))
                try:
                    if not path.is_file() or path.stat().st_size > 1_000_000:
                        continue
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                remaining = 60_000 - used
                content = content[:remaining]
                used += len(content)
                context_files.append(
                    {
                        "path": item["path"],
                        "language": item.get("language", ""),
                        "content": content,
                    }
                )
            value["contextFiles"] = context_files
        return value

    @staticmethod
    def _project_verify(arguments: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()
        root = Path(arguments["root"]).expanduser().resolve()
        if not root.is_dir():
            raise ToolValidationError("Project root is not a directory.")
        failures: list[str] = []
        checked = 0
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [
                name
                for name in dirnames
                if name not in {".git", "node_modules", ".venv", "dist", "build"}
                and not (Path(dirpath) / name).is_symlink()
            ]
            for filename in filenames:
                path = Path(dirpath) / filename
                if path.is_symlink():
                    continue
                relative = path.relative_to(root).as_posix()
                if path.suffix.lower() not in TEXT_EXTENSIONS | {".bat"}:
                    continue
                try:
                    if path.stat().st_size > 2_000_000:
                        failures.append(f"{relative}: source file exceeds 2 MB")
                        continue
                    validate_project_file(
                        relative,
                        path.read_text(encoding="utf-8", errors="replace"),
                    )
                    checked += 1
                except (OSError, ProjectValidationError) as exc:
                    failures.append(f"{relative}: {exc}")
        plan = build_launch_plan(str(root))
        output = {
            "checked": checked,
            "failures": failures,
            "launch": (
                {
                    "kind": plan.kind,
                    "label": plan.label,
                    "target": plan.target,
                }
                if plan
                else None
            ),
        }
        return ToolResult(
            "project.verify",
            not failures,
            (time.perf_counter() - started) * 1000,
            output=output,
            errors=failures,
            verified=True,
        )

    @staticmethod
    def _preview_patch(arguments: dict[str, Any]) -> dict[str, Any]:
        root = Path(arguments["root"]).expanduser().resolve()
        if not root.is_dir():
            raise ToolValidationError("Patch root is not a directory.")
        files: list[dict[str, Any]] = []
        seen: set[str] = set()
        for change in arguments["changes"]:
            path = _resolve_within(root, change["path"])
            relative = path.relative_to(root).as_posix()
            if relative in seen:
                raise ToolValidationError(f"Patch contains duplicate path: {relative}")
            seen.add(relative)
            if path.exists() and not path.is_file():
                raise ToolValidationError(f"Patch target is not a file: {relative}")
            before_bytes = path.read_bytes() if path.is_file() else b""
            before = before_bytes.decode("utf-8", errors="replace")
            after = change["content"]
            diff = "".join(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile=f"a/{change['path']}",
                    tofile=f"b/{change['path']}",
                )
            )
            files.append(
                {
                    "path": change["path"],
                    "exists": path.exists(),
                    "beforeSha256": hashlib.sha256(before_bytes).hexdigest(),
                    "changed": before != after,
                    "diff": diff,
                }
            )
        return {
            "files": files,
            "changed": [item["path"] for item in files if item["changed"]],
        }

    def _apply_patch(self, arguments: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()
        with self._workspace_lock:
            root = Path(arguments["root"]).expanduser().resolve()
            if not root.is_dir():
                raise ToolValidationError("Patch root is not a directory.")
            changes: list[dict[str, Any]] = []
            seen: set[str] = set()
            for change in arguments["changes"]:
                destination = _resolve_within(root, change["path"])
                relative = destination.relative_to(root).as_posix()
                if relative in seen:
                    raise ToolValidationError(
                        f"Patch contains duplicate path: {relative}"
                    )
                seen.add(relative)
                if destination.exists() and not destination.is_file():
                    raise ToolValidationError(
                        f"Patch target is not a file: {relative}"
                    )
                before_exists = destination.is_file()
                before = destination.read_bytes() if before_exists else b""
                if "expected_exists" in change and (
                    bool(change["expected_exists"]) != before_exists
                ):
                    return ToolResult(
                        "filesystem.apply_patch",
                        False,
                        (time.perf_counter() - started) * 1000,
                        errors=[
                            f"{relative} changed after preview; refresh the patch before applying."
                        ],
                    )
                if expected := str(change.get("expected_sha256", "")):
                    if hashlib.sha256(before).hexdigest() != expected:
                        return ToolResult(
                            "filesystem.apply_patch",
                            False,
                            (time.perf_counter() - started) * 1000,
                            errors=[
                                f"{relative} changed after preview; refresh the patch before applying."
                            ],
                        )
                if before != change["content"].encode("utf-8"):
                    changes.append(change)
            if not changes:
                return ToolResult(
                    "filesystem.apply_patch",
                    True,
                    (time.perf_counter() - started) * 1000,
                    output={"changed": []},
                    warnings=["Patch did not change any files."],
                    verified=True,
                )
            undo_id = self.undo_store.create(root, changes)
            generated: list[str] = []
            modified: list[str] = []
            try:
                for change in changes:
                    destination = _resolve_within(root, change["path"])
                    existed = destination.exists()
                    _atomic_write(destination, change["content"].encode("utf-8"))
                    (modified if existed else generated).append(str(destination))
                verified = all(
                    _resolve_within(root, change["path"]).is_file()
                    and _resolve_within(root, change["path"]).read_bytes()
                    == change["content"].encode("utf-8")
                    for change in changes
                )
                if not verified:
                    raise OSError("One or more files failed post-write verification.")
            except OSError as exc:
                rollback = self.undo_store.restore(undo_id, force=True)
                errors = [f"Patch failed: {exc}"]
                if not rollback.success:
                    errors.extend(rollback.errors)
                return ToolResult(
                    "filesystem.apply_patch",
                    False,
                    (time.perf_counter() - started) * 1000,
                    output={"changed": []},
                    errors=errors,
                    verified=False,
                )
            return ToolResult(
                "filesystem.apply_patch",
                True,
                (time.perf_counter() - started) * 1000,
                output={"changed": [change["path"] for change in changes]},
                generated_files=generated,
                modified_files=modified,
                metadata={"undoId": undo_id},
                verified=True,
            )

    def _undo_action(self, arguments: dict[str, Any]) -> ToolResult:
        with self._workspace_lock:
            return self.undo_store.restore(arguments["undo_id"])

    def _terminal_run(self, arguments: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()
        cwd = Path(arguments["cwd"]).expanduser().resolve()
        if not cwd.is_dir():
            raise ToolValidationError("Command working directory is invalid.")
        command = arguments["command"]
        if not command:
            raise ToolValidationError("Command cannot be empty.")
        timeout = max(1.0, min(600.0, float(arguments.get("timeout", 300))))
        call_id = str(arguments.get("_call_id", ""))
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        with self._process_lock:
            self._active_processes[call_id] = process
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
        finally:
            with self._process_lock:
                self._active_processes.pop(call_id, None)
        return_code = process.returncode if process.returncode is not None else -1
        errors = []
        if timed_out:
            errors.append(f"Command timed out after {timeout:g} seconds.")
        elif return_code != 0:
            errors.append(f"Command exited with {return_code}.")
        return ToolResult(
            "terminal.run",
            return_code == 0 and not timed_out,
            (time.perf_counter() - started) * 1000,
            output={
                "stdout": stdout,
                "stderr": stderr,
                "exitCode": return_code,
                "timedOut": timed_out,
            },
            logs=[stdout, stderr],
            errors=errors,
            verified=return_code == 0 and not timed_out,
        )

    @staticmethod
    def _git_read(
        arguments: dict[str, Any],
        command: tuple[str, ...],
        tool_id: str,
    ) -> ToolResult:
        started = time.perf_counter()
        root = Path(arguments["root"]).expanduser().resolve()
        completed = subprocess.run(
            ["git", *command],
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return ToolResult(
            tool_id,
            completed.returncode == 0,
            (time.perf_counter() - started) * 1000,
            output={
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "exitCode": completed.returncode,
            },
            errors=[] if completed.returncode == 0 else [completed.stderr.strip() or "Git command failed."],
            verified=completed.returncode == 0,
        )

    @staticmethod
    def _git_blame(arguments: dict[str, Any]) -> ToolResult:
        root = Path(arguments["root"]).expanduser().resolve()
        path = _resolve_within(root, arguments["path"])
        return BuiltinTools._git_read(
            {"root": str(root)},
            ("blame", "--", path.relative_to(root).as_posix()),
            "git.blame",
        )

    @staticmethod
    def _git_mutation(
        arguments: dict[str, Any],
        operation: str,
        tool_id: str,
    ) -> ToolResult:
        root = Path(arguments["root"]).expanduser().resolve()
        command: list[str]
        if operation == "stash":
            command = ["stash", "push"]
            if message := str(arguments.get("message", "")).strip():
                command.extend(["-m", message])
        elif operation == "restore":
            paths = [str(path) for path in arguments.get("paths", ()) if str(path)]
            if not paths:
                raise ToolValidationError("Git restore requires at least one path.")
            for path in paths:
                _resolve_within(root, path)
            command = ["restore", "--", *paths]
        elif operation == "checkout":
            branch = str(arguments.get("branch", "")).strip()
            if not branch or branch.startswith("-"):
                raise ToolValidationError("Git checkout requires a valid branch name.")
            command = ["checkout", branch]
        elif operation == "commit":
            message = str(arguments.get("message", "")).strip()
            if not message:
                raise ToolValidationError("Git commit requires a message.")
            command = ["commit", "-m", message]
        elif operation == "push":
            remote = str(arguments.get("remote", "origin")).strip() or "origin"
            branch = str(arguments.get("branch", "")).strip()
            if remote.startswith("-") or branch.startswith("-"):
                raise ToolValidationError("Git push target is invalid.")
            command = ["push", remote]
            if branch:
                command.append(branch)
        else:
            raise ToolValidationError(f"Unsupported Git mutation: {operation}")
        return BuiltinTools._git_read(
            {"root": str(root)},
            tuple(command),
            tool_id,
        )
