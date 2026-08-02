from __future__ import annotations

import ctypes
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from collections import defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import __version__
from .agent_orchestrator import AgentOrchestrator
from .platform_services import PlatformServices
from .plugin_manager import PluginManager
from .desktop_environment import DesktopIntegrationLayer

APP_VERSION = __version__
MAX_LOG_RECORDS = 2_000
MAX_METRIC_SAMPLES = 360
MAX_RECOVERY_HISTORY = 160
MAX_RECOVERY_BYTES = 8 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_data_dir() -> Path:
    configured = os.getenv("MORICE_RUNTIME_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    app_data = os.getenv("APPDATA", "").strip()
    if app_data:
        return Path(app_data) / "MORICE" / "runtime"
    return Path(__file__).resolve().parent.parent / ".morice" / "runtime"


def _atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass(frozen=True)
class StructuredLogRecord:
    timestamp: str
    level: str
    category: str
    message: str
    logger: str = "morice"
    thread: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class StructuredLogManager:
    def __init__(
        self,
        directory: str | os.PathLike[str] | None = None,
        *,
        max_file_bytes: int = 5 * 1024 * 1024,
        backups: int = 3,
    ):
        self.directory = Path(directory) if directory else runtime_data_dir() / "logs"
        self.path = self.directory / "morice.jsonl"
        self.max_file_bytes = max(64 * 1024, int(max_file_bytes))
        self.backups = max(1, min(10, int(backups)))
        self._records: deque[StructuredLogRecord] = deque(maxlen=MAX_LOG_RECORDS)
        self._lock = threading.RLock()
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.path.is_file():
            return
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        for line in lines[-MAX_LOG_RECORDS:]:
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    continue
                self._records.append(
                    StructuredLogRecord(
                        timestamp=str(value.get("timestamp", "")),
                        level=str(value.get("level", "INFO")),
                        category=str(value.get("category", "application")),
                        message=str(value.get("message", "")),
                        logger=str(value.get("logger", "morice")),
                        thread=str(value.get("thread", "")),
                        metadata=(
                            value.get("metadata")
                            if isinstance(value.get("metadata"), dict)
                            else {}
                        ),
                    )
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                continue

    def _rotate_if_needed(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < self.max_file_bytes:
            return
        oldest = self.path.with_suffix(f".jsonl.{self.backups}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backups - 1, 0, -1):
            source = self.path.with_suffix(f".jsonl.{index}")
            if source.exists():
                source.replace(self.path.with_suffix(f".jsonl.{index + 1}"))
        self.path.replace(self.path.with_suffix(".jsonl.1"))

    def log(
        self,
        level: str,
        message: str,
        *,
        category: str = "application",
        logger: str = "morice",
        metadata: dict[str, Any] | None = None,
    ) -> StructuredLogRecord:
        normalized_level = str(level or "INFO").upper()
        if normalized_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            normalized_level = "INFO"
        clean_metadata: dict[str, Any] = {}
        for key, value in (metadata or {}).items():
            try:
                json.dumps(value)
                clean_metadata[str(key)] = value
            except (TypeError, ValueError):
                clean_metadata[str(key)] = repr(value)
        record = StructuredLogRecord(
            timestamp=_utc_now(),
            level=normalized_level,
            category=str(category or "application")[:80],
            message=str(message or "")[:100_000],
            logger=str(logger or "morice")[:120],
            thread=threading.current_thread().name[:120],
            metadata=clean_metadata,
        )
        payload = json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._records.append(record)
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                self._rotate_if_needed()
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(payload + "\n")
            except OSError:
                # Logging must never take down the application it observes.
                pass
        return record

    def tail(self, limit: int = 300) -> list[StructuredLogRecord]:
        with self._lock:
            return list(self._records)[-max(1, min(MAX_LOG_RECORDS, int(limit))):]

    def search(
        self,
        query: str = "",
        *,
        level: str = "",
        category: str = "",
        limit: int = 500,
    ) -> list[StructuredLogRecord]:
        needle = str(query or "").strip().casefold()
        wanted_level = str(level or "").strip().upper()
        wanted_category = str(category or "").strip().casefold()
        matches: list[StructuredLogRecord] = []
        for record in reversed(self.tail(MAX_LOG_RECORDS)):
            haystack = (
                f"{record.message} {record.category} {record.logger} "
                f"{json.dumps(record.metadata, ensure_ascii=False)}"
            ).casefold()
            if needle and needle not in haystack:
                continue
            if wanted_level and record.level != wanted_level:
                continue
            if wanted_category and record.category.casefold() != wanted_category:
                continue
            matches.append(record)
            if len(matches) >= max(1, min(MAX_LOG_RECORDS, int(limit))):
                break
        return list(reversed(matches))

    def categories(self) -> list[str]:
        return sorted({record.category for record in self.tail(MAX_LOG_RECORDS)})


@dataclass(frozen=True)
class MetricSample:
    timestamp: float
    cpu_percent: float
    memory_mb: float
    gpu_percent: float | None
    vram_used_mb: float | None
    disk_read_mb_s: float
    disk_write_mb_s: float
    token_speed_tps: float
    frame_time_ms: float
    fps: float
    thread_count: int
    task_queue: int


def _process_memory_mb() -> float:
    if os.name == "nt":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("page_fault_count", ctypes.c_ulong),
                ("peak_working_set_size", ctypes.c_size_t),
                ("working_set_size", ctypes.c_size_t),
                ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                ("quota_paged_pool_usage", ctypes.c_size_t),
                ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                ("quota_non_paged_pool_usage", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(
            process, ctypes.byref(counters), counters.cb
        ):
            return counters.working_set_size / (1024 * 1024)
        return 0.0
    try:
        import resource

        amount = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return amount / 1024 if sys.platform != "darwin" else amount / (1024 * 1024)
    except (ImportError, OSError, ValueError):
        return 0.0


def _process_io_bytes() -> tuple[int, int]:
    if os.name != "nt":
        return 0, 0

    class ProcessIoCounters(ctypes.Structure):
        _fields_ = [
            ("read_operation_count", ctypes.c_ulonglong),
            ("write_operation_count", ctypes.c_ulonglong),
            ("other_operation_count", ctypes.c_ulonglong),
            ("read_transfer_count", ctypes.c_ulonglong),
            ("write_transfer_count", ctypes.c_ulonglong),
            ("other_transfer_count", ctypes.c_ulonglong),
        ]

    counters = ProcessIoCounters()
    process = ctypes.windll.kernel32.GetCurrentProcess()
    if ctypes.windll.kernel32.GetProcessIoCounters(
        process,
        ctypes.byref(counters),
    ):
        return int(counters.read_transfer_count), int(counters.write_transfer_count)
    return 0, 0


def _nvidia_gpu_metrics() -> tuple[float | None, float | None]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None, None
    try:
        completed = subprocess.run(
            [
                executable,
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=True,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if os.name == "nt"
                else 0
            ),
        )
        first_line = completed.stdout.strip().splitlines()[0]
        utilization, memory_used = first_line.split(",", maxsplit=1)
        return (
            max(0.0, min(100.0, float(utilization.strip()))),
            max(0.0, float(memory_used.strip())),
        )
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None, None


class PerformanceProfiler:
    def __init__(self):
        self._samples: deque[MetricSample] = deque(maxlen=MAX_METRIC_SAMPLES)
        self._durations: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=300)
        )
        self._counters: dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()
        self._last_wall = time.perf_counter()
        self._last_cpu = time.process_time()
        self._frame_time_ms = 0.0
        self._task_queue = 0
        self._current_renderer = ""
        self._token_speed_tps = 0.0
        self._last_io_read, self._last_io_write = _process_io_bytes()
        self._last_gpu_sample = 0.0
        self._gpu_percent: float | None = None
        self._vram_used_mb: float | None = None

    @contextmanager
    def measure(self, name: str, category: str = "operation") -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record_duration(f"{category}.{name}", (time.perf_counter() - started) * 1000)

    def record_duration(self, name: str, duration_ms: float) -> None:
        duration = max(0.0, float(duration_ms))
        with self._lock:
            self._durations[str(name)].append(duration)
            self._counters[f"{name}.count"] += 1

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[str(name)] += int(amount)

    def set_frame_time(self, frame_time_ms: float) -> None:
        with self._lock:
            self._frame_time_ms = max(0.0, float(frame_time_ms))

    def set_task_queue(self, count: int) -> None:
        with self._lock:
            self._task_queue = max(0, int(count))

    def set_current_renderer(self, renderer_id: str) -> None:
        with self._lock:
            self._current_renderer = str(renderer_id or "")

    def record_model_completion(self, characters: int, duration_ms: float) -> float:
        duration_seconds = max(0.001, float(duration_ms) / 1000.0)
        estimated_tokens = max(0.0, float(characters)) / 4.0
        speed = estimated_tokens / duration_seconds
        with self._lock:
            self._token_speed_tps = speed
        return speed

    @property
    def current_renderer(self) -> str:
        with self._lock:
            return self._current_renderer

    def sample(self) -> MetricSample:
        now = time.perf_counter()
        cpu_now = time.process_time()
        wall_delta = max(0.001, now - self._last_wall)
        cpu_delta = max(0.0, cpu_now - self._last_cpu)
        self._last_wall = now
        self._last_cpu = cpu_now
        cpu_percent = min(
            100.0,
            (cpu_delta / wall_delta) * 100.0 / max(1, os.cpu_count() or 1),
        )
        with self._lock:
            frame_time = self._frame_time_ms
            task_queue = self._task_queue
            token_speed = self._token_speed_tps
        io_read, io_write = _process_io_bytes()
        disk_read_mb_s = max(
            0.0,
            (io_read - self._last_io_read) / (1024 * 1024) / wall_delta,
        )
        disk_write_mb_s = max(
            0.0,
            (io_write - self._last_io_write) / (1024 * 1024) / wall_delta,
        )
        self._last_io_read, self._last_io_write = io_read, io_write
        if now - self._last_gpu_sample >= 5.0:
            self._gpu_percent, self._vram_used_mb = _nvidia_gpu_metrics()
            self._last_gpu_sample = now
        fps = 1000.0 / frame_time if frame_time > 0 else 0.0
        sample = MetricSample(
            timestamp=time.time(),
            cpu_percent=cpu_percent,
            memory_mb=_process_memory_mb(),
            gpu_percent=self._gpu_percent,
            vram_used_mb=self._vram_used_mb,
            disk_read_mb_s=disk_read_mb_s,
            disk_write_mb_s=disk_write_mb_s,
            token_speed_tps=token_speed,
            frame_time_ms=frame_time,
            fps=fps,
            thread_count=threading.active_count(),
            task_queue=task_queue,
        )
        with self._lock:
            self._samples.append(sample)
        return sample

    def samples(self) -> list[MetricSample]:
        with self._lock:
            return list(self._samples)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            durations = {
                name: {
                    "count": len(values),
                    "averageMs": sum(values) / len(values) if values else 0.0,
                    "maxMs": max(values) if values else 0.0,
                }
                for name, values in self._durations.items()
            }
            return {
                "durations": durations,
                "counters": dict(self._counters),
                "currentRenderer": self._current_renderer,
            }


class BackgroundTaskManager:
    def __init__(
        self,
        logs: StructuredLogManager,
        profiler: PerformanceProfiler,
        *,
        max_workers: int = 6,
    ):
        self.logs = logs
        self.profiler = profiler
        self._executor = ThreadPoolExecutor(
            max_workers=max(2, min(12, int(max_workers))),
            thread_name_prefix="morice-worker",
        )
        self._futures: dict[str, tuple[str, Future]] = {}
        self._lock = threading.RLock()
        self._closed = False

    def submit(self, name: str, function, *args, **kwargs) -> Future:
        with self._lock:
            if self._closed:
                raise RuntimeError("MORICE background task manager is shut down.")
            task_id = uuid.uuid4().hex
            started = time.perf_counter()
            future = self._executor.submit(function, *args, **kwargs)
            self._futures[task_id] = (str(name), future)

        def completed(done: Future) -> None:
            duration_ms = (time.perf_counter() - started) * 1000
            self.profiler.record_duration(str(name), duration_ms)
            with self._lock:
                self._futures.pop(task_id, None)
            try:
                error = done.exception()
            except BaseException as exc:  # cancelled futures can raise
                error = exc
            self.logs.log(
                "ERROR" if error else "INFO",
                (
                    f"Background task '{name}' failed: {error}"
                    if error
                    else f"Background task '{name}' completed in {duration_ms:.1f} ms."
                ),
                category="worker",
                metadata={"taskId": task_id, "durationMs": duration_ms},
            )

        future.add_done_callback(completed)
        return future

    @property
    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for _name, future in self._futures.values() if not future.done())

    @property
    def task_names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                name for name, future in self._futures.values() if not future.done()
            )

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: str
    detail: str
    critical: bool = False
    category: str = "application"


@dataclass(frozen=True)
class HealthReport:
    timestamp: str
    checks: tuple[HealthCheck, ...]

    @property
    def status(self) -> str:
        if any(check.status == "failed" and check.critical for check in self.checks):
            return "failed"
        if any(check.status in {"failed", "degraded"} for check in self.checks):
            return "degraded"
        return "healthy"

    @property
    def critical_failures(self) -> tuple[HealthCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status == "failed" and check.critical
        )


class StartupHealthChecker:
    DEPENDENCIES = (
        ("PySide6", "PySide6"),
        ("numpy", "numpy"),
        ("Pillow", "PIL"),
        ("sounddevice", "sounddevice"),
        ("vosk", "vosk"),
    )

    def __init__(
        self,
        project_root: str | os.PathLike[str] | None = None,
        runtime_directory: str | os.PathLike[str] | None = None,
    ):
        self.project_root = (
            Path(project_root).resolve()
            if project_root
            else Path(__file__).resolve().parent.parent
        )
        self.runtime_directory = (
            Path(runtime_directory)
            if runtime_directory
            else runtime_data_dir()
        )

    def _dependency_check(self, distribution: str, module_name: str) -> HealthCheck:
        try:
            module = __import__(module_name)
            try:
                version = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                version = str(getattr(module, "__version__", "") or "bundled")
            return HealthCheck(
                f"Dependency: {distribution}",
                "healthy",
                version,
                category="dependency",
            )
        except ImportError as exc:
            return HealthCheck(
                f"Dependency: {distribution}",
                "failed",
                str(exc),
                critical=distribution in {"PySide6", "numpy"},
                category="dependency",
            )

    def run(
        self,
        *,
        renderer_capabilities: Iterable[Any] = (),
        model_path: str = "",
        model_name: str = "",
        tools: Iterable[str] = (),
        gpu: dict[str, Any] | None = None,
    ) -> HealthReport:
        checks: list[HealthCheck] = []
        runtime_dir = self.runtime_directory
        try:
            runtime_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=runtime_dir, delete=True):
                pass
            checks.append(
                HealthCheck(
                    "Runtime storage",
                    "healthy",
                    str(runtime_dir),
                    critical=True,
                    category="storage",
                )
            )
        except OSError as exc:
            checks.append(
                HealthCheck(
                    "Runtime storage",
                    "failed",
                    str(exc),
                    critical=True,
                    category="storage",
                )
            )

        for asset in (
            self.project_root / "morice" / "assets" / "morice_logo.ico",
            self.project_root / "morice" / "assets" / "morice-logo-rgb.png",
            self.project_root / "morice" / "assets" / "web" / "katex.min.js",
        ):
            checks.append(
                HealthCheck(
                    f"Asset: {asset.name}",
                    "healthy" if asset.is_file() else "failed",
                    str(asset),
                    critical=True,
                    category="asset",
                )
            )

        checks.extend(
            self._dependency_check(distribution, module_name)
            for distribution, module_name in self.DEPENDENCIES
        )

        try:
            from .settings import load_settings, settings_path

            path = Path(settings_path())
            if path.is_file():
                with path.open("r", encoding="utf-8") as handle:
                    raw_settings = json.load(handle)
                if not isinstance(raw_settings, dict):
                    raise ValueError("Settings root must be a JSON object.")
            load_settings()
            checks.append(
                HealthCheck(
                    "Settings configuration",
                    "healthy",
                    str(path),
                    critical=True,
                    category="configuration",
                )
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            checks.append(
                HealthCheck(
                    "Settings configuration",
                    "failed",
                    str(exc),
                    critical=True,
                    category="configuration",
                )
            )

        selected_model = Path(model_path) if model_path else None
        if selected_model and selected_model.is_file():
            model_detail = f"{model_name or selected_model.name} ({selected_model.stat().st_size} bytes)"
            checks.append(
                HealthCheck("AI model", "healthy", model_detail, category="model")
            )
        else:
            bundled = tuple(self.project_root.glob("*.gguf"))
            status = "healthy" if bundled else "degraded"
            detail = (
                f"Bundled model: {bundled[0].name}"
                if bundled
                else "No GGUF is available. Model-backed chat will be unavailable."
            )
            checks.append(HealthCheck("AI model", status, detail, category="model"))

        capabilities = tuple(renderer_capabilities)
        available = [item for item in capabilities if getattr(item, "available", False)]
        unavailable = [item for item in capabilities if not getattr(item, "available", False)]
        checks.append(
            HealthCheck(
                "Renderer registry",
                "healthy" if available else "failed",
                f"{len(available)} available, {len(unavailable)} unavailable",
                critical=True,
                category="renderer",
            )
        )
        tool_names = tuple(str(tool).strip() for tool in tools if str(tool).strip())
        checks.append(
            HealthCheck(
                "Tool registry",
                "healthy" if tool_names else "degraded",
                (
                    f"{len(tool_names)} desktop tools registered"
                    if tool_names
                    else "No desktop tools were reported during startup."
                ),
                category="tool",
            )
        )
        gpu_profile = dict(gpu or {})
        gpu_detected = bool(gpu_profile.get("detected"))
        gpu_name = str(gpu_profile.get("name") or "").strip()
        vram_mb = max(0, int(gpu_profile.get("vramMb") or 0))
        checks.append(
            HealthCheck(
                "GPU profile",
                "healthy" if gpu_detected else "degraded",
                (
                    f"{gpu_name or 'GPU'} ({vram_mb} MB VRAM)"
                    if gpu_detected
                    else "GPU detection is pending or no compatible GPU was reported."
                ),
                category="hardware",
            )
        )
        return HealthReport(_utc_now(), tuple(checks))


@dataclass(frozen=True)
class RecoveryInfo:
    available: bool
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    crash: dict[str, Any] = field(default_factory=dict)


class CrashRecoveryManager:
    def __init__(self, directory: str | os.PathLike[str] | None = None):
        self.directory = Path(directory) if directory else runtime_data_dir() / "recovery"
        self.marker_path = self.directory / "session.lock"
        self.snapshot_path = self.directory / "recovery.json"
        self.crash_path = self.directory / "last-crash.json"
        self.session_id = uuid.uuid4().hex
        self._lock = threading.RLock()
        self._previous_sys_hook = None
        self._previous_thread_hook = None
        self._hooks_installed = False

    def begin_session(self) -> RecoveryInfo:
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            previous_unclean = self.marker_path.exists()
            payload: dict[str, Any] = {}
            crash: dict[str, Any] = {}
            if previous_unclean:
                for path, target in (
                    (self.snapshot_path, payload),
                    (self.crash_path, crash),
                ):
                    try:
                        loaded = json.loads(path.read_text(encoding="utf-8"))
                        if isinstance(loaded, dict):
                            target.update(loaded)
                    except (OSError, ValueError, json.JSONDecodeError):
                        pass
            _atomic_json_write(
                self.marker_path,
                {
                    "sessionId": self.session_id,
                    "pid": os.getpid(),
                    "startedAt": _utc_now(),
                },
            )
            return RecoveryInfo(
                available=bool(previous_unclean and payload),
                reason=(
                    "The previous MORICE session did not shut down cleanly."
                    if previous_unclean
                    else ""
                ),
                payload=payload,
                crash=crash,
            )

    def save_snapshot(self, payload: dict[str, Any]) -> None:
        clean = dict(payload)
        history = clean.get("history")
        if isinstance(history, list):
            clean["history"] = history[-MAX_RECOVERY_HISTORY:]
        clean["sessionId"] = self.session_id
        clean["savedAt"] = _utc_now()
        encoded = json.dumps(clean, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_RECOVERY_BYTES:
            clean["history"] = clean.get("history", [])[-40:]
            encoded = json.dumps(clean, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_RECOVERY_BYTES:
            raise ValueError("Recovery snapshot exceeds the 8 MB safety limit.")
        with self._lock:
            _atomic_json_write(self.snapshot_path, clean)

    def record_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback,
        *,
        thread_name: str = "",
    ) -> None:
        record = {
            "sessionId": self.session_id,
            "timestamp": _utc_now(),
            "thread": thread_name or threading.current_thread().name,
            "exceptionType": getattr(exc_type, "__name__", str(exc_type)),
            "message": str(exc_value),
            "stackTrace": "".join(
                traceback.format_exception(exc_type, exc_value, exc_traceback)
            )[-300_000:],
        }
        with self._lock:
            _atomic_json_write(self.crash_path, record)

    def install_exception_hooks(self, logs: StructuredLogManager) -> None:
        if self._hooks_installed:
            return
        self._previous_sys_hook = sys.excepthook
        self._previous_thread_hook = getattr(threading, "excepthook", None)

        def sys_hook(exc_type, exc_value, exc_traceback):
            self.record_exception(exc_type, exc_value, exc_traceback, thread_name="main")
            logs.log(
                "CRITICAL",
                f"Unhandled exception: {exc_value}",
                category="crash",
                metadata={"exceptionType": getattr(exc_type, "__name__", str(exc_type))},
            )
            if self._previous_sys_hook:
                self._previous_sys_hook(exc_type, exc_value, exc_traceback)

        def thread_hook(args):
            self.record_exception(
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
                thread_name=getattr(args.thread, "name", ""),
            )
            logs.log(
                "CRITICAL",
                f"Unhandled worker exception: {args.exc_value}",
                category="crash",
                metadata={
                    "exceptionType": getattr(args.exc_type, "__name__", str(args.exc_type)),
                    "thread": getattr(args.thread, "name", ""),
                },
            )
            if self._previous_thread_hook:
                self._previous_thread_hook(args)

        sys.excepthook = sys_hook
        if hasattr(threading, "excepthook"):
            threading.excepthook = thread_hook
        self._hooks_installed = True

    def uninstall_exception_hooks(self) -> None:
        if not self._hooks_installed:
            return
        if self._previous_sys_hook is not None:
            sys.excepthook = self._previous_sys_hook
        if self._previous_thread_hook is not None and hasattr(threading, "excepthook"):
            threading.excepthook = self._previous_thread_hook
        self._hooks_installed = False

    def mark_clean(self) -> None:
        with self._lock:
            for path in (self.marker_path, self.snapshot_path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass


@dataclass(frozen=True)
class RuntimeSnapshot:
    application: dict[str, Any]
    platform: dict[str, Any]
    model: dict[str, Any]
    gpu: dict[str, Any]
    renderers: tuple[dict[str, Any], ...]
    tools: tuple[str, ...]
    workers: dict[str, Any]
    performance: MetricSample
    profiler: dict[str, Any]
    health: HealthReport
    dependencies: dict[str, str]
    agent: dict[str, Any]
    desktop: dict[str, Any]
    plugins: dict[str, Any]
    autonomous_platform: dict[str, Any]


class RuntimeServices:
    def __init__(
        self,
        directory: str | os.PathLike[str] | None = None,
        *,
        project_root: str | os.PathLike[str] | None = None,
    ):
        base = Path(directory) if directory else runtime_data_dir()
        self.directory = base
        self.logs = StructuredLogManager(base / "logs")
        self.profiler = PerformanceProfiler()
        self.workers = BackgroundTaskManager(self.logs, self.profiler)
        self.recovery = CrashRecoveryManager(base / "recovery")
        self.health_checker = StartupHealthChecker(project_root, base)
        self.agent = AgentOrchestrator(base / "agent", logger=self.logs.log)
        self.desktop = DesktopIntegrationLayer(base / "desktop")
        core_root = (
            Path(project_root).resolve()
            if project_root
            else (
                Path(sys.executable).resolve().parent
                if getattr(sys, "frozen", False)
                else Path(__file__).resolve().parents[1]
            )
        )
        self.plugins = PluginManager(
            base / "plugins",
            core_root=core_root,
            logger=self.logs.log,
        )
        self.platform_services = PlatformServices(
            base / "platform",
            self.agent,
            application_root=core_root,
            logger=self.logs.log,
        )
        self.health_report = HealthReport(_utc_now(), ())
        self.recovery_info = RecoveryInfo(False)
        self._started = False
        self._shutdown = False
        self._lock = threading.RLock()

    @property
    def started(self) -> bool:
        with self._lock:
            return self._started and not self._shutdown

    def start(self) -> RecoveryInfo:
        with self._lock:
            if self._shutdown:
                raise RuntimeError(
                    "MORICE runtime services cannot restart after shutdown."
                )
            if self._started:
                return self.recovery_info
            self.recovery_info = self.recovery.begin_session()
            self.recovery.install_exception_hooks(self.logs)
            self.desktop.automations.start_scheduler()
            self.plugins.discover()
            plugin_startup = self.plugins.start_enabled()
            self.plugins.publish_event(
                "application.started",
                {"version": APP_VERSION, "pid": os.getpid()},
            )
            self.logs.log(
                "INFO",
                "MORICE runtime services started.",
                category="startup",
                metadata={
                    "version": APP_VERSION,
                    "pid": os.getpid(),
                    "plugins": plugin_startup,
                },
            )
            self._started = True
            self._shutdown = False
            return self.recovery_info

    def run_health_check(
        self,
        *,
        renderer_capabilities: Iterable[Any] = (),
        model_path: str = "",
        model_name: str = "",
        tools: Iterable[str] = (),
        gpu: dict[str, Any] | None = None,
    ) -> HealthReport:
        with self.profiler.measure("startup-health-check", "startup"):
            report = self.health_checker.run(
                renderer_capabilities=renderer_capabilities,
                model_path=model_path,
                model_name=model_name,
                tools=tools,
                gpu=gpu,
            )
        self.health_report = report
        self.logs.log(
            "INFO" if report.status == "healthy" else "WARNING",
            f"Startup health check: {report.status}.",
            category="health",
            metadata={
                "checks": len(report.checks),
                "criticalFailures": len(report.critical_failures),
                "criticalFailureDetails": [
                    {
                        "name": check.name,
                        "detail": check.detail,
                    }
                    for check in report.critical_failures
                ],
            },
        )
        return report

    def snapshot(
        self,
        *,
        renderer_capabilities: Iterable[Any] = (),
        model: dict[str, Any] | None = None,
        gpu: dict[str, Any] | None = None,
        tools: Iterable[str] = (),
        task_queue: int = 0,
        renderer_cache_bytes: int = 0,
        project_root: str = "",
    ) -> RuntimeSnapshot:
        task_queue = max(0, int(task_queue)) + self.workers.pending_count
        self.profiler.set_task_queue(task_queue)
        performance = self.profiler.sample()
        renderers = tuple(
            {
                "id": str(getattr(item, "renderer_id", "")),
                "label": str(getattr(item, "label", "")),
                "available": bool(getattr(item, "available", False)),
                "interactive": bool(getattr(item, "interactive", False)),
                "backend": str(getattr(item, "backend", "")),
                "reason": str(getattr(item, "reason", "")),
            }
            for item in renderer_capabilities
        )
        dependencies: dict[str, str] = {}
        for distribution in ("PySide6", "numpy", "Pillow", "sounddevice", "vosk"):
            try:
                dependencies[distribution] = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                dependencies[distribution] = "unavailable"
        try:
            from PySide6.QtCore import qVersion

            qt_version = qVersion()
        except ImportError:
            qt_version = "unavailable"
        plugin_diagnostics = self.plugins.diagnostics()
        workspace = None
        if project_root:
            clean_project_root = os.path.normcase(
                str(Path(project_root).expanduser().resolve())
            )
            workspace = next(
                (
                    item
                    for item in self.desktop.workspaces.list()
                    if os.path.normcase(item.root) == clean_project_root
                ),
                None,
            )
        platform_snapshot = self.platform_services.snapshot(
            project_root=project_root,
            workspace=workspace,
            performance={
                "cpuPercent": performance.cpu_percent,
                "memoryMb": performance.memory_mb,
                "fps": performance.fps,
                "taskQueue": task_queue,
            },
            health=self.health_report,
            plugins=plugin_diagnostics,
            renderers=renderers,
        )
        return RuntimeSnapshot(
            application={
                "name": "MORICE",
                "version": APP_VERSION,
                "pid": os.getpid(),
                "started": self._started,
            },
            platform={
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "qt": qt_version,
            },
            model=dict(model or {}),
            gpu=dict(gpu or {}),
            renderers=renderers,
            tools=tuple(str(tool) for tool in tools),
            workers={
                "threadCount": performance.thread_count,
                "activeNames": tuple(thread.name for thread in threading.enumerate()),
                "activeTasks": self.workers.task_names,
                "taskQueue": task_queue,
                "rendererCacheBytes": max(0, int(renderer_cache_bytes)),
            },
            performance=performance,
            profiler=self.profiler.summary(),
            health=self.health_report,
            dependencies=dependencies,
            agent=self.agent.snapshot(),
            desktop=self.desktop.snapshot(),
            plugins=plugin_diagnostics,
            autonomous_platform=platform_snapshot,
        )

    def save_recovery_snapshot(self, payload: dict[str, Any]) -> None:
        if not self._started:
            return
        try:
            self.recovery.save_snapshot(payload)
        except (OSError, ValueError) as exc:
            self.logs.log(
                "ERROR",
                f"Recovery snapshot failed: {exc}",
                category="recovery",
            )

    def shutdown(self, *, clean: bool = True) -> None:
        with self._lock:
            if self._shutdown:
                return
            failures: list[str] = []
            shutdown_steps = (
                ("platform", self.platform_services.shutdown),
                ("plugins", self.plugins.shutdown),
                ("desktop", self.desktop.shutdown),
                ("workers", self.workers.shutdown),
                ("exception hooks", self.recovery.uninstall_exception_hooks),
            )
            for name, callback in shutdown_steps:
                try:
                    callback()
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{name}: {exc}")
                    self.logs.log(
                        "ERROR",
                        f"Runtime shutdown step failed: {name}: {exc}",
                        category="shutdown",
                    )
            if clean and not failures:
                try:
                    self.recovery.mark_clean()
                except OSError as exc:
                    failures.append(f"recovery: {exc}")
                    self.logs.log(
                        "ERROR",
                        f"Could not mark the runtime session clean: {exc}",
                        category="shutdown",
                    )
            self._shutdown = True
            self._started = False
            self.logs.log(
                "INFO" if not failures else "ERROR",
                (
                    "MORICE runtime services stopped."
                    if not failures
                    else "MORICE runtime services stopped with cleanup errors."
                ),
                category="shutdown",
                metadata={"clean": clean and not failures, "failures": failures},
            )


_RUNTIME_SERVICES: RuntimeServices | None = None
_RUNTIME_LOCK = threading.Lock()


def get_runtime_services() -> RuntimeServices:
    global _RUNTIME_SERVICES
    with _RUNTIME_LOCK:
        if _RUNTIME_SERVICES is None:
            _RUNTIME_SERVICES = RuntimeServices()
        return _RUNTIME_SERVICES
