from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path
from typing import Any

from .plugin_sdk import PluginManifest


MAX_MESSAGE_BYTES = 4 * 1024 * 1024
MAX_LOG_CHARS = 16_000
_PROTOCOL_STREAM = sys.stdout
_WRITE_LOCK = threading.Lock()


def _write_message(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=True, default=str, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_MESSAGE_BYTES:
        encoded = json.dumps(
            {
                "type": "error",
                "error": "Plugin response exceeded the 4 MB transport limit.",
            },
            separators=(",", ":"),
        )
    with _WRITE_LOCK:
        _PROTOCOL_STREAM.write(encoded + "\n")
        _PROTOCOL_STREAM.flush()


class PluginHostAPI:
    def __init__(
        self,
        plugin_id: str,
        storage_root: Path,
        core_root: Path,
        grants: set[str],
    ):
        self.plugin_id = plugin_id
        self.storage_root = storage_root
        self.core_root = core_root.resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.grants = frozenset(grants)

    def has_permission(self, permission: str) -> bool:
        return permission in self.grants

    def require_permission(self, permission: str) -> None:
        if permission not in self.grants:
            raise PermissionError(
                f"Plugin {self.plugin_id!r} was not granted {permission!r}."
            )

    def log(self, level: str, message: str, **metadata: Any) -> None:
        _write_message(
            {
                "type": "event",
                "event": "log",
                "payload": {
                    "level": str(level).upper()[:16],
                    "message": str(message)[:MAX_LOG_CHARS],
                    "metadata": _json_safe(metadata),
                },
            }
        )

    def notify(self, title: str, message: str, level: str = "info") -> None:
        self.require_permission("notifications")
        _write_message(
            {
                "type": "event",
                "event": "notification",
                "payload": {
                    "title": str(title)[:160],
                    "message": str(message)[:2000],
                    "level": str(level)[:20],
                },
            }
        )

    def settings_get(self, key: str, default: Any = None) -> Any:
        return self.storage_get(f"settings.{_storage_key(key)}", default)

    def settings_set(self, key: str, value: Any) -> None:
        self.storage_set(f"settings.{_storage_key(key)}", value)

    def request_visualization(self, instruction: dict[str, Any]) -> None:
        self.emit("visualization.requested", {"instruction": _json_safe(instruction)})

    def request_workspace(self, workspace_id: str, payload: dict[str, Any] | None = None) -> None:
        self.emit(
            "workspace.requested",
            {"workspaceId": str(workspace_id)[:100], "payload": _json_safe(payload or {})},
        )

    def memory_updated(self, scope: str, keys: list[str] | tuple[str, ...]) -> None:
        self.require_permission("memory.write")
        self.emit(
            "memory.updated",
            {"scope": str(scope)[:100], "keys": [str(key)[:160] for key in keys[:200]]},
        )

    def automation_triggered(self, automation_id: str, status: str) -> None:
        self.require_permission("automation")
        self.emit(
            "automation.triggered",
            {"automationId": str(automation_id)[:100], "status": str(status)[:100]},
        )

    def emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        _write_message(
            {
                "type": "event",
                "event": "plugin.event",
                "payload": {
                    "name": str(event)[:160],
                    "data": _json_safe(payload or {}),
                },
            }
        )

    def storage_get(self, key: str, default: Any = None) -> Any:
        return self._load_storage().get(_storage_key(key), default)

    def storage_set(self, key: str, value: Any) -> None:
        safe_key = _storage_key(key)
        payload = self._load_storage()
        payload[safe_key] = _json_safe(value)
        encoded = json.dumps(payload, ensure_ascii=True, indent=2)
        if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("Plugin storage quota exceeded (2 MB).")
        target = self.storage_root / "storage.json"
        temporary = self.storage_root / "storage.tmp"
        temporary.write_text(encoded, encoding="utf-8")
        os.replace(temporary, target)

    def storage_delete(self, key: str) -> bool:
        payload = self._load_storage()
        removed = payload.pop(_storage_key(key), None) is not None
        if removed:
            self._write_storage(payload)
        return removed

    def file_read_text(self, path: str, max_bytes: int = 2 * 1024 * 1024) -> str:
        self.require_permission("filesystem.read")
        target = Path(path).expanduser().resolve()
        limit = max(1, min(8 * 1024 * 1024, int(max_bytes)))
        if not target.is_file():
            raise FileNotFoundError(target)
        if target.stat().st_size > limit:
            raise ValueError(f"File exceeds the {limit}-byte plugin read limit.")
        return target.read_text(encoding="utf-8")

    def file_write_text(self, path: str, content: str) -> dict[str, Any]:
        self.require_permission("filesystem.write")
        target = Path(path).expanduser().resolve()
        if _inside(target, self.core_root):
            raise PermissionError("Plugins cannot modify MORICE core files.")
        encoded = str(content).encode("utf-8")
        if len(encoded) > 8 * 1024 * 1024:
            raise ValueError("Plugin file writes are limited to 8 MB.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            temporary.write_bytes(encoded)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return {"path": str(target), "bytes": len(encoded)}

    def file_list(self, path: str, limit: int = 500) -> list[dict[str, Any]]:
        self.require_permission("filesystem.read")
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(root)
        result = []
        for item in sorted(root.iterdir(), key=lambda value: value.name.casefold()):
            result.append(
                {
                    "name": item.name,
                    "path": str(item),
                    "directory": item.is_dir(),
                    "bytes": item.stat().st_size if item.is_file() else 0,
                }
            )
            if len(result) >= max(1, min(2_000, int(limit))):
                break
        return result

    def fetch_json(self, url: str, timeout: float = 15.0) -> Any:
        self.require_permission("network")
        target = str(url).strip()
        if not target.startswith("https://"):
            raise PermissionError("Plugin network requests require HTTPS.")
        request = urllib.request.Request(
            target,
            headers={"User-Agent": f"MORICE-Plugin/{self.plugin_id}"},
        )
        with urllib.request.urlopen(
            request,
            timeout=max(1.0, min(30.0, float(timeout))),
        ) as response:
            payload = response.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError("Plugin network response exceeds 2 MB.")
        return _json_safe(json.loads(payload.decode("utf-8")))

    def run_process(
        self,
        command: list[str] | tuple[str, ...],
        *,
        cwd: str = "",
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        self.require_permission("process")
        arguments = [str(item) for item in command]
        if not arguments or len(arguments) > 100:
            raise ValueError("Plugin process command must contain 1-100 arguments.")
        completed = subprocess.run(
            arguments,
            cwd=str(Path(cwd).expanduser().resolve()) if cwd else None,
            capture_output=True,
            text=True,
            shell=False,
            timeout=max(0.1, min(60.0, float(timeout))),
        )
        return {
            "returnCode": completed.returncode,
            "stdout": completed.stdout[:1_000_000],
            "stderr": completed.stderr[:1_000_000],
        }

    def request_desktop_action(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.require_permission("desktop.control")
        self.emit(
            "desktop.action.requested",
            {"action": str(action)[:100], "payload": _json_safe(payload or {})},
        )

    def _load_storage(self) -> dict[str, Any]:
        target = self.storage_root / "storage.json"
        if not target.exists():
            return {}
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_storage(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=True, indent=2)
        if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("Plugin storage quota exceeded (2 MB).")
        target = self.storage_root / "storage.json"
        temporary = self.storage_root / "storage.tmp"
        temporary.write_text(encoded, encoding="utf-8")
        os.replace(temporary, target)


def _storage_key(value: str) -> str:
    key = str(value or "").strip()
    if not key or len(key) > 160:
        raise ValueError("Plugin storage key must contain 1-160 characters.")
    return key


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=True)
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)
    return value


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _install_resource_limits() -> None:
    try:
        import resource
    except ImportError:
        return
    limits = (
        (getattr(resource, "RLIMIT_NOFILE", None), 128, 128),
        (getattr(resource, "RLIMIT_NPROC", None), 16, 16),
        (getattr(resource, "RLIMIT_AS", None), 1024**3, 1024**3),
    )
    for resource_id, soft, hard in limits:
        if resource_id is None:
            continue
        try:
            resource.setrlimit(resource_id, (soft, hard))
        except (OSError, ValueError):
            pass


def _install_audit_hook(
    *,
    plugin_root: Path,
    storage_root: Path,
    core_root: Path,
    grants: set[str],
) -> None:
    plugin_root = plugin_root.resolve()
    storage_root = storage_root.resolve()
    core_root = core_root.resolve()
    interpreter_roots = tuple(
        path.resolve()
        for value in {sys.prefix, sys.base_prefix}
        if value and (path := Path(value)).exists()
    )

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event == "open" and args:
            try:
                target = Path(os.fspath(args[0])).resolve()
            except (TypeError, ValueError, OSError):
                return
            mode = str(args[1]) if len(args) > 1 else "r"
            flags = int(args[2]) if len(args) > 2 and isinstance(args[2], int) else 0
            writing = any(marker in mode for marker in "wax+") or bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if writing:
                if _inside(target, storage_root):
                    return
                if _inside(target, core_root):
                    raise PermissionError("Plugins cannot modify MORICE core files.")
                if "filesystem.write" not in grants:
                    raise PermissionError("filesystem.write permission was not granted.")
                return
            allowed_runtime_read = _inside(target, plugin_root) or _inside(target, storage_root)
            allowed_runtime_read = allowed_runtime_read or any(
                _inside(target, root) for root in interpreter_roots
            )
            if not allowed_runtime_read and "filesystem.read" not in grants:
                raise PermissionError("filesystem.read permission was not granted.")
        elif event in {
            "os.remove",
            "os.rmdir",
            "os.mkdir",
            "os.chmod",
            "os.chown",
            "os.utime",
            "os.truncate",
        } and args:
            _validate_write_target(
                args[0],
                storage_root=storage_root,
                core_root=core_root,
                grants=grants,
            )
        elif event in {"os.rename", "os.replace"} and len(args) >= 2:
            _validate_write_target(
                args[0],
                storage_root=storage_root,
                core_root=core_root,
                grants=grants,
            )
            _validate_write_target(
                args[1],
                storage_root=storage_root,
                core_root=core_root,
                grants=grants,
            )
        elif event in {"os.link", "os.symlink"} and len(args) >= 2:
            _validate_write_target(
                args[1],
                storage_root=storage_root,
                core_root=core_root,
                grants=grants,
            )
        elif event.startswith(("socket.", "urllib.", "http.client")):
            if "network" not in grants:
                raise PermissionError("network permission was not granted.")
        elif event in {
            "subprocess.Popen",
            "os.system",
            "os.exec",
            "os.posix_spawn",
            "os.spawn",
            "pty.spawn",
        }:
            if "process" not in grants:
                raise PermissionError("process permission was not granted.")
        elif event in {"ctypes.dlopen", "ctypes.dlsym"}:
            raise PermissionError("Native library loading is unavailable to plugins.")

    sys.addaudithook(audit)


def _validate_write_target(
    value: Any,
    *,
    storage_root: Path,
    core_root: Path,
    grants: set[str],
) -> None:
    try:
        target = Path(os.fspath(value)).resolve()
    except (TypeError, ValueError, OSError):
        return
    if _inside(target, storage_root):
        return
    if _inside(target, core_root):
        raise PermissionError("Plugins cannot modify MORICE core files.")
    if "filesystem.write" not in grants:
        raise PermissionError("filesystem.write permission was not granted.")


def _load_plugin(entry_path: Path, api: PluginHostAPI) -> Any:
    module_name = f"morice_extension_{api.plugin_id.replace('.', '_').replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, entry_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load plugin entry point: {entry_path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        spec.loader.exec_module(module)
        if callable(getattr(module, "create_plugin", None)):
            plugin = module.create_plugin(api)
        elif hasattr(module, "Plugin"):
            plugin = module.Plugin(api)
        else:
            plugin = module
    startup_output = captured.getvalue().strip()
    if startup_output:
        api.log("INFO", startup_output[:MAX_LOG_CHARS], source="plugin stdout")
    return plugin


def _call_optional(plugin: Any, method: str, *args: Any) -> Any:
    callback = getattr(plugin, method, None)
    return callback(*args) if callable(callback) else None


def _dispatch(plugin: Any, request: dict[str, Any]) -> Any:
    method = str(request.get("method", ""))
    params = request.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("Plugin request parameters must be an object.")
    if method in {"start", "stop", "pause", "resume"}:
        return _call_optional(plugin, f"on_{method}")
    if method == "event":
        callback = getattr(plugin, "on_event", None)
        return callback(str(params.get("event", "")), params.get("payload") or {}) if callable(callback) else None
    routes: dict[str, tuple[str, tuple[Any, ...]]] = {
        "command": (
            "handle_command",
            (str(params.get("id", "")), params.get("arguments") or {}),
        ),
        "tool": (
            "handle_tool",
            (str(params.get("id", "")), params.get("arguments") or {}),
        ),
        "render": (
            "render",
            (str(params.get("id", "")), str(params.get("prompt", ""))),
        ),
        "model": (
            "generate",
            (str(params.get("id", "")), params.get("messages") or [], params.get("options") or {}),
        ),
        "automation": (
            "run_automation",
            (str(params.get("id", "")), params.get("payload") or {}),
        ),
        "memory": (
            "handle_memory",
            (
                str(params.get("id", "")),
                str(params.get("operation", "")),
                params.get("payload") or {},
            ),
        ),
        "voice": (
            "handle_voice",
            (
                str(params.get("id", "")),
                str(params.get("operation", "")),
                params.get("payload") or {},
            ),
        ),
    }
    if method not in routes:
        raise ValueError(f"Unsupported plugin host method: {method}")
    callback_name, arguments = routes[method]
    callback = getattr(plugin, callback_name, None)
    if not callable(callback):
        raise NotImplementedError(f"Plugin does not implement {callback_name}().")
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        result = callback(*arguments)
    if captured.getvalue().strip():
        _write_message(
            {
                "type": "event",
                "event": "log",
                "payload": {
                    "level": "INFO",
                    "message": captured.getvalue().strip()[:MAX_LOG_CHARS],
                    "metadata": {"source": "plugin stdout"},
                },
            }
        )
    return _json_safe(result)


def run_host(args: argparse.Namespace) -> int:
    plugin_root = Path(args.plugin_root).resolve()
    storage_root = Path(args.storage_root).resolve()
    core_root = Path(args.core_root).resolve()
    manifest = PluginManifest.from_path(plugin_root / "plugin.json")
    grants = set(json.loads(args.grants))
    undeclared = grants - {permission.value for permission in manifest.permissions}
    if undeclared:
        raise PermissionError(
            "Host received undeclared permissions: " + ", ".join(sorted(undeclared))
        )
    entry_path = (plugin_root / manifest.entry_point).resolve()
    entry_path.relative_to(plugin_root)
    if not entry_path.is_file():
        raise FileNotFoundError(f"Plugin entry point is missing: {manifest.entry_point}")
    _install_resource_limits()
    _install_audit_hook(
        plugin_root=plugin_root,
        storage_root=storage_root,
        core_root=core_root,
        grants=grants,
    )
    api = PluginHostAPI(manifest.plugin_id, storage_root, core_root, grants)
    plugin = _load_plugin(entry_path, api)
    _write_message(
        {
            "type": "ready",
            "pluginId": manifest.plugin_id,
            "pid": os.getpid(),
            "apiVersion": manifest.api_version,
        }
    )
    for line in sys.stdin:
        if len(line.encode("utf-8")) > MAX_MESSAGE_BYTES:
            _write_message({"type": "error", "error": "Request exceeded 4 MB."})
            continue
        try:
            request = json.loads(line)
            request_id = str(request.get("id", ""))
            started = time.perf_counter()
            result = _dispatch(plugin, request)
            _write_message(
                {
                    "type": "response",
                    "id": request_id,
                    "result": result,
                    "durationMs": round((time.perf_counter() - started) * 1000, 3),
                }
            )
            if request.get("method") == "stop":
                return 0
        except Exception as exc:
            _write_message(
                {
                    "type": "response",
                    "id": str(locals().get("request_id", "")),
                    "error": str(exc),
                    "exceptionType": type(exc).__name__,
                    "traceback": traceback.format_exc(limit=8),
                }
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MORICE isolated plugin host")
    parser.add_argument("--plugin-root", required=True)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--core-root", required=True)
    parser.add_argument("--grants", default="[]")
    return parser


def main() -> int:
    try:
        return run_host(build_parser().parse_args())
    except Exception as exc:
        _write_message(
            {
                "type": "fatal",
                "error": str(exc),
                "exceptionType": type(exc).__name__,
                "traceback": traceback.format_exc(limit=10),
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
