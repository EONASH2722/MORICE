from __future__ import annotations

import ctypes
import base64
import importlib.metadata
import json
import os
import platform
import socket
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser
from collections import defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from . import __version__
from .agent_orchestrator import AgentOrchestrator
from .platform_services import PlatformServices
from .plugin_manager import PluginManager
from .desktop_environment import DesktopIntegrationLayer
from .desktop_assistant import collect_system_snapshot
from .config import load_tts_config
from .connectivity import BluetoothManager, NetworkManager
from .device_intelligence import (
    DeviceAdapterRegistry,
    DeviceController,
    DeviceRegistry,
    EnvironmentRegistry,
)
from .live_vision import LiveVisionRuntime, LlamaCppVisionProvider
from .autonomous_builder import AutonomousBuilder
from .node_protocol import (
    LanDiscovery,
    MessageType,
    MoriceNodeClient,
    MoriceNodeServer,
    NodeDescriptor,
    NodeIdentity,
    ProtocolMessage,
    TrustedNode,
    TrustedNodeStore,
)
from .pc_control import (
    DesktopContext,
    FastActionRouter,
    PermissionBroker,
    PermissionCategory,
    PolicyMode,
    build_pc_control_registry,
)
from .platform_adapters import select_platform_adapter
from .realtime_intelligence import RealtimeIntelligence
from .settings import load_settings, normalize_boolean_setting
from .speech_runtime import SpeechInputConfig, SpeechToTextRuntime
from .voice_runtime import VoiceRuntime
from .web_search import search_web
from .unified_intelligence import (
    CapabilityRegistry,
    GoalExecutionOrchestrator,
    PermissionController,
    PermissionState,
    WorkingMemory,
)

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
        last_error: OSError | None = None
        for attempt in range(3):
            try:
                os.replace(temporary, path)
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                try:
                    if path.exists():
                        path.chmod(path.stat().st_mode | stat.S_IWRITE)
                except OSError:
                    pass
                if attempt < 2:
                    time.sleep(0.04 * (attempt + 1))
        if last_error is not None:
            raise last_error
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


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
        workers = max(2, min(12, int(max_workers)))
        # Interactive work has reserved threads so an index scan, download, or
        # maintenance burst cannot queue ahead of the current conversation.
        self._interactive_executor = ThreadPoolExecutor(
            max_workers=max(2, workers - 2),
            thread_name_prefix="morice-interactive",
        )
        self._background_executor = ThreadPoolExecutor(
            max_workers=min(2, workers),
            thread_name_prefix="morice-background",
        )
        self._futures: dict[str, tuple[str, Future]] = {}
        self._lock = threading.RLock()
        self._closed = False

    def submit(
        self,
        name: str,
        function,
        *args,
        priority: str = "background",
        **kwargs,
    ) -> Future:
        with self._lock:
            if self._closed:
                raise RuntimeError("MORICE background task manager is shut down.")
            task_id = uuid.uuid4().hex
            started = time.perf_counter()
            executor = (
                self._interactive_executor
                if str(priority).casefold() in {"interactive", "foreground", "high"}
                else self._background_executor
            )
            future = executor.submit(function, *args, **kwargs)
            self._futures[task_id] = (str(name), future)

        def completed(done: Future) -> None:
            duration_ms = (time.perf_counter() - started) * 1000
            self.profiler.record_duration(str(name), duration_ms)
            try:
                error = done.exception()
            except BaseException as exc:  # cancelled futures can raise
                error = exc
            # Future waiters are notified before callbacks necessarily finish.
            # Keep the final log write inside the manager lock so shutdown either
            # waits for it or closes the manager first and suppresses the write.
            # This prevents late callbacks from touching removed runtime storage.
            with self._lock:
                self._futures.pop(task_id, None)
                if self._closed:
                    return
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

    def shutdown(self, *, drain_seconds: float = 2.0) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            futures = tuple(future for _name, future in self._futures.values())
        for future in futures:
            future.cancel()
        if futures and drain_seconds > 0:
            # Give short native discovery and metrics calls time to leave their
            # subprocesses. Long-running downloads/model jobs remain bounded by
            # this timeout and never stall application exit indefinitely.
            wait(futures, timeout=max(0.0, min(5.0, float(drain_seconds))))
        self._interactive_executor.shutdown(wait=False, cancel_futures=True)
        self._background_executor.shutdown(wait=False, cancel_futures=True)


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
        self.last_write_error = ""

    def begin_session(self) -> RecoveryInfo:
        with self._lock:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self.last_write_error = str(exc)
                return RecoveryInfo(
                    False,
                    "Crash recovery is temporarily unavailable; MORICE continued safely.",
                )
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
            try:
                _atomic_json_write(
                    self.marker_path,
                    {
                        "sessionId": self.session_id,
                        "pid": os.getpid(),
                        "startedAt": _utc_now(),
                    },
                )
                self.last_write_error = ""
            except OSError as exc:
                # Recovery is protective state, not a reason to prevent the
                # desktop app from launching (for example after a stale locked
                # marker from a frozen process).
                self.last_write_error = str(exc)
                return RecoveryInfo(
                    available=bool(previous_unclean and payload),
                    reason=(
                        "The previous session may not have closed cleanly. "
                        "Recovery storage is temporarily locked, so MORICE continued without replacing it."
                    ),
                    payload=payload,
                    crash=crash,
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
            try:
                _atomic_json_write(self.snapshot_path, clean)
                self.last_write_error = ""
            except OSError as exc:
                self.last_write_error = str(exc)

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
            try:
                _atomic_json_write(self.crash_path, record)
                self.last_write_error = ""
            except OSError as exc:
                self.last_write_error = str(exc)

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
                except OSError as exc:
                    self.last_write_error = str(exc)


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
    voice: dict[str, Any] = field(default_factory=dict)
    speech_input: dict[str, Any] = field(default_factory=dict)
    live_vision: dict[str, Any] = field(default_factory=dict)
    realtime: dict[str, Any] = field(default_factory=dict)
    pc_control: dict[str, Any] = field(default_factory=dict)
    unified_intelligence: dict[str, Any] = field(default_factory=dict)
    devices: dict[str, Any] = field(default_factory=dict)
    connectivity: dict[str, Any] = field(default_factory=dict)


class _SystemBrowserController:
    """Small verified bridge to the user's registered Windows browser."""

    def __init__(self) -> None:
        self._current_url = ""
        self._lock = threading.RLock()

    @property
    def current_url(self) -> str:
        with self._lock:
            return self._current_url

    def open(self, url: str) -> None:
        if not webbrowser.open(str(url), new=2, autoraise=True):
            raise RuntimeError("Windows did not accept the browser request.")
        with self._lock:
            self._current_url = str(url)


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
        self.autonomous_builder = AutonomousBuilder(base / "builder")
        settings = load_settings()
        self.default_music_provider = str(
            settings.get("default_music_provider", "Amazon Music")
        ).strip() or "Amazon Music"
        self.desktop = DesktopIntegrationLayer(
            base / "desktop",
            default_music_provider=self.default_music_provider,
        )
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
        identity_pem = self.platform_services.vault.get("morice.node.identity", "")
        try:
            self.node_identity = NodeIdentity.from_pem(identity_pem) if identity_pem else NodeIdentity()
        except ValueError:
            self.node_identity = NodeIdentity()
        if not identity_pem:
            self.platform_services.vault.set(
                "morice.node.identity",
                self.node_identity.private_pem(),
            )
        node_device_id = self.platform_services.vault.get("morice.node.device-id", "")
        if not node_device_id:
            node_device_id = "desktop-" + uuid.uuid4().hex
            self.platform_services.vault.set("morice.node.device-id", node_device_id)
        self.node_descriptor = NodeDescriptor(
            node_device_id,
            socket.gethostname() or "MORICE Desktop",
            platform.system().casefold() or "windows",
            (
                "system.status",
                "chat.complete",
                "vision.analyze",
                "application.open",
                "media.control",
                "screen.capture",
                "project.status",
                "project.run",
                "notification.receive",
                "file.receive",
            ),
            APP_VERSION,
            ("lan", "direct-ip", "future-relay"),
            {"identityFingerprint": self.node_identity.fingerprint},
        )
        self.trusted_nodes = TrustedNodeStore(base / "nodes" / "trusted.json")
        try:
            node_port = int(os.getenv("MORICE_NODE_PORT", "47651") or 47651)
        except ValueError:
            node_port = 47651
        self.node_server = MoriceNodeServer(
            self.node_descriptor,
            self.trusted_nodes,
            self._dispatch_node_message,
            port=node_port,
            error_callback=self._log_node_error,
            identity=self.node_identity,
        )
        self.node_client = MoriceNodeClient(self.node_descriptor, self.trusted_nodes)
        self.node_discovery = LanDiscovery(self.node_descriptor, node_port=node_port)
        tts_config = load_tts_config(settings, root=core_root)
        if not tts_config.api_configured:
            vault_key = self.platform_services.vault.get("elevenlabs.api-key", "")
            if vault_key:
                tts_config = replace(tts_config, api_key=vault_key)

        def safe_voice_log(event: str, metadata: dict[str, Any]) -> None:
            self.logs.log(
                "INFO" if not event.endswith("failure") else "WARNING",
                "Voice runtime event.",
                category="voice",
                metadata=dict(metadata),
            )

        self.voice = VoiceRuntime(tts_config, safe_logger=safe_voice_log)
        raw_input_device = str(settings.get("stt_input_device", "")).strip()
        try:
            input_device: int | str | None = (
                int(raw_input_device) if raw_input_device else None
            )
        except ValueError:
            input_device = raw_input_device or None
        try:
            max_listen = float(settings.get("stt_max_listen_seconds", "30"))
        except (TypeError, ValueError):
            max_listen = 30.0
        speech_config = SpeechInputConfig(
            enabled=normalize_boolean_setting(
                str(settings.get("stt_enabled", "true")), default=True
            ),
            input_device=input_device,
            max_listen_seconds=max(5.0, min(120.0, max_listen)),
            auto_send=normalize_boolean_setting(
                str(settings.get("stt_auto_send", "true")), default=True
            ),
        )
        self.speech_input = SpeechToTextRuntime(
            speech_config,
            safe_logger=safe_voice_log,
        )

        def safe_vision_log(event: str, metadata: dict[str, Any]) -> None:
            failure = str(metadata.get("failureCode", "")).strip()
            self.logs.log(
                "WARNING" if failure else "INFO",
                "Live Vision runtime event.",
                category="vision",
                metadata={"event": str(event), **dict(metadata)},
            )

        vision_provider = LlamaCppVisionProvider(
            model_path=str(settings.get("vision_model_path", "")).strip() or None,
            mmproj_path=str(settings.get("vision_mmproj_path", "")).strip() or None,
            hf_repository=str(settings.get("vision_hf_repository", "")).strip(),
            gpu_layers=0,
            logger=safe_vision_log,
        )
        self.live_vision = LiveVisionRuntime(
            vision_provider,
            enabled=normalize_boolean_setting(
                str(settings.get("vision_processing_enabled", "true")),
                default=True,
            ),
            logger=safe_vision_log,
        )
        self.realtime = RealtimeIntelligence()

        routine_pc_defaults = {
            PermissionCategory.READ_SYSTEM_STATE: PolicyMode.ALLOW,
            PermissionCategory.APPLICATION_CONTROL: PolicyMode.ALLOW,
            PermissionCategory.WINDOW_CONTROL: PolicyMode.ALLOW,
            PermissionCategory.MEDIA_CONTROL: PolicyMode.ALLOW,
            PermissionCategory.FILE_READ: PolicyMode.ALLOW,
            PermissionCategory.BROWSER_CONTROL: PolicyMode.ALLOW,
            PermissionCategory.NETWORK_ACCESS: PolicyMode.ALLOW,
            # A direct "take a screenshot" utterance is itself an explicit,
            # one-shot capture request; the lower desktop manager still issues
            # and consumes an exact scoped grant for the capture parameters.
            PermissionCategory.SCREEN_ACCESS: PolicyMode.ALLOW,
        }
        self.pc_permissions = PermissionBroker(
            base / "pc-control" / "permissions.json",
            defaults=routine_pc_defaults,
        )
        self.pc_context = DesktopContext()
        self.pc_browser = _SystemBrowserController()
        file_roots = tuple(
            str(path)
            for path in (
                Path.home() / "Desktop",
                Path.home() / "Documents",
                Path.home() / "Downloads",
                core_root,
            )
            if path.is_dir()
        )
        open_path = None
        reveal_path = None
        if os.name == "nt":
            open_path = lambda value: os.startfile(value)  # type: ignore[attr-defined]
            reveal_path = lambda value: subprocess.Popen(
                ["explorer.exe", "/select,", str(value)],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        self.pc_control = build_pc_control_registry(
            self.desktop,
            self.pc_permissions,
            context=self.pc_context,
            file_roots=file_roots,
            browser=self.pc_browser,
            web_search=search_web,
            open_path=open_path,
            reveal_path=reveal_path,
        )
        self.pc_router = FastActionRouter(
            self.pc_context,
            default_music_provider=self.default_music_provider,
        )
        # Shared goal/device foundations are always present, even when no
        # external hardware adapters are installed. Empty registries report
        # unsupported capability honestly instead of fabricating control.
        self.unified_permissions = PermissionController(
            states={
                "application_control": PermissionState.GRANTED,
                "file_read": PermissionState.GRANTED,
                "media": PermissionState.GRANTED,
                "network": PermissionState.GRANTED,
                "read_system_state": PermissionState.GRANTED,
                "connected_devices": PermissionState.ASK,
            }
        )
        self.unified_capabilities = CapabilityRegistry()
        self.unified_memory = WorkingMemory()
        self.goals = GoalExecutionOrchestrator(
            self.unified_capabilities,
            memory=self.unified_memory,
            permissions=self.unified_permissions,
        )
        self.device_registry = DeviceRegistry(base / "devices" / "registry.json")
        self.device_adapters = DeviceAdapterRegistry()
        self.device_controller = DeviceController(
            self.device_registry,
            self.device_adapters,
            self.unified_permissions,
        )
        self.environment_registry = EnvironmentRegistry()
        self.host_adapter = select_platform_adapter()
        self.network = NetworkManager()
        self.bluetooth = BluetoothManager()
        self.health_report = HealthReport(_utc_now(), ())
        self.recovery_info = RecoveryInfo(False)
        self._live_camera_diagnostics: dict[str, Any] = {}
        self._started = False
        self._shutdown = False
        self._lock = threading.RLock()

    def _log_node_error(self, error: Exception, address: Any) -> None:
        self.logs.log(
            "WARNING",
            f"MORICE node request failed: {error}",
            category="nodes",
            metadata={"address": str(address)},
        )

    def resolve_node(self, reference: str = "") -> TrustedNode:
        """Resolve one enrolled node by id, name, platform, or a natural device noun."""

        candidates = [node for node in self.trusted_nodes.list() if not node.revoked]
        if not candidates:
            raise LookupError("No paired MORICE devices are available.")
        clean = " ".join(str(reference or "").casefold().split())
        if not clean and len(candidates) == 1:
            return candidates[0]
        aliases = {
            "phone": "android",
            "my phone": "android",
            "android": "android",
            "tablet": "android",
            "pc": "windows",
            "computer": "windows",
            "desktop": "windows",
            "laptop": "windows",
        }
        target = aliases.get(clean, clean)
        matches = [
            node
            for node in candidates
            if target
            and (
                target == node.descriptor.device_id.casefold()
                or target == node.descriptor.device_name.casefold()
                or target == node.descriptor.platform.casefold()
                or target in node.descriptor.device_name.casefold()
            )
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise LookupError(f"No paired MORICE device matches {reference or 'that device'}.")
        raise LookupError(
            "More than one paired device matches; specify the device name."
        )

    def send_node_task(
        self,
        capability: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        device: str = "",
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Invoke an explicitly granted structured capability on a paired node."""

        trusted = self.resolve_node(device)
        clean_capability = str(capability or "").strip()
        if not clean_capability or not trusted.remote_allows(clean_capability):
            raise PermissionError(
                f"{trusted.descriptor.device_name} has not granted {clean_capability or 'that capability'}."
            )
        host = str(trusted.descriptor.metadata.get("host", "") or "").strip()
        try:
            port = int(trusted.descriptor.metadata.get("port", 0) or 0)
        except (TypeError, ValueError):
            port = 0
        if not host or not 0 < port <= 65_535:
            raise ConnectionError(
                f"{trusted.descriptor.device_name} has no reachable LAN endpoint. Pair it again while both devices are online."
            )
        task_id = uuid.uuid4().hex
        response = self.node_client.send(
            trusted.descriptor.device_id,
            host,
            port,
            MessageType.TASK_REQUEST,
            {
                "capability": clean_capability,
                "arguments": dict(arguments or {}),
            },
            task_id=task_id,
            timeout=max(2.0, min(float(timeout), 300.0)),
        )
        payload = dict(response.payload)
        payload.setdefault("taskId", task_id)
        payload.setdefault("deviceId", trusted.descriptor.device_id)
        payload.setdefault("deviceName", trusted.descriptor.device_name)
        payload.setdefault("verified", False)
        if response.message_type == MessageType.ERROR:
            payload.setdefault("error", "The remote MORICE node rejected the task.")
        return payload

    def _dispatch_node_message(
        self,
        message: ProtocolMessage,
        trusted: TrustedNode,
    ) -> ProtocolMessage:
        def response(
            message_type: MessageType,
            payload: dict[str, Any],
        ) -> ProtocolMessage:
            return ProtocolMessage(
                message_type,
                self.node_descriptor.device_id,
                message.sender_id,
                payload,
                task_id=message.task_id,
            )

        if message.message_type in {MessageType.HELLO, MessageType.CAPABILITIES}:
            return response(
                MessageType.CAPABILITIES,
                {
                    "descriptor": self.node_descriptor.to_dict(),
                    "authorizedForPeer": list(trusted.allowed_capabilities),
                    "online": True,
                },
            )
        if message.message_type == MessageType.DEVICE_STATE:
            return response(
                MessageType.DEVICE_STATE,
                {
                    "descriptor": self.node_descriptor.to_dict(),
                    "online": True,
                    "serverPort": self.node_server.bound_port,
                },
            )
        if message.message_type == MessageType.TASK_CANCEL:
            cancelled = bool(message.task_id and self.goals.cancel(message.task_id))
            return response(
                MessageType.TASK_RESULT,
                {"verified": cancelled, "cancelled": cancelled},
            )
        if message.message_type != MessageType.TASK_REQUEST:
            return response(
                MessageType.ERROR,
                {"error": f"Unsupported node message: {message.message_type.value}"},
            )

        capability = str(message.payload.get("capability", ""))
        arguments = (
            dict(message.payload.get("arguments", {}))
            if isinstance(message.payload.get("arguments"), Mapping)
            else {}
        )
        try:
            if capability == "system.status":
                snapshot = asdict(collect_system_snapshot())
                return response(
                    MessageType.TASK_RESULT,
                    {"verified": True, "capability": capability, "result": snapshot},
                )
            if capability == "chat.complete":
                prompt = " ".join(str(arguments.get("message", "")).split())[:20_000]
                if not prompt:
                    raise ValueError("A chat message is required.")
                from .llm_client import chat

                settings = load_settings()
                answer = chat(
                    [],
                    prompt,
                    extra_system=(
                        "This request came from the user's paired MORICE Android companion. "
                        "Respond naturally and do not claim a device action unless a verified tool result is present."
                    ),
                    model=str(settings.get("model_name", "")).strip() or None,
                    gguf_path=str(settings.get("model_path", "")).strip() or None,
                    timeout=120,
                    precision_mode=bool(arguments.get("precision", False)),
                )
                return response(
                    MessageType.TASK_RESULT,
                    {
                        "verified": bool(str(answer).strip()),
                        "capability": capability,
                        "result": {"message": str(answer)},
                    },
                )
            if capability == "vision.analyze":
                encoded = str(arguments.get("jpegBase64", ""))
                if not encoded or len(encoded) > 14_000_000:
                    raise ValueError("A bounded JPEG frame is required.")
                jpeg = base64.b64decode(encoded, validate=True)
                prompt = " ".join(
                    str(arguments.get("prompt", "Describe what is visible.")).split()
                )[:2_000]
                self.live_vision.publish_frame(
                    jpeg,
                    source="paired-android",
                    deviceId=message.sender_id,
                )
                vision_result = self.live_vision.analyze_latest(
                    prompt,
                    request_id=message.task_id or message.message_id,
                ).result(timeout=120)
                return response(
                    MessageType.TASK_RESULT if vision_result.success else MessageType.ERROR,
                    {
                        "verified": vision_result.success,
                        "capability": capability,
                        "result": vision_result.public_dict(),
                        "error": "" if vision_result.success else vision_result.message,
                    },
                )
            if capability == "application.open":
                target = " ".join(str(arguments.get("application", "")).split())[:300]
                if not target:
                    raise ValueError("An application name is required.")
                candidate = self.desktop.applications.resolve(target)
                if candidate is None:
                    raise FileNotFoundError(f"Application not found: {target}")
                grant = self.desktop.applications.request_launch(candidate.name)
                self.desktop.applications.launch(candidate.name, grant.token)
                deadline = time.monotonic() + 8.0
                running = self.desktop.applications.is_running(candidate)
                while not running and time.monotonic() < deadline:
                    time.sleep(0.1)
                    running = self.desktop.applications.is_running(candidate)
                return response(
                    MessageType.TASK_RESULT,
                    {
                        "verified": running,
                        "capability": capability,
                        "result": {"application": candidate.name, "running": running},
                    },
                )
            if capability == "media.control":
                action = str(arguments.get("action", "")).strip().casefold()
                if action not in self.desktop.media.SUPPORTED_ACTIONS:
                    raise ValueError(f"Unsupported media action: {action}")
                media_arguments = {
                    key: value for key, value in arguments.items() if key != "action"
                }
                grant = self.desktop.media.request(action, **media_arguments)
                result = self.desktop.media.control(
                    action,
                    grant.token,
                    **media_arguments,
                )
                verified = bool(
                    result.get("verified", False)
                    if isinstance(result, Mapping)
                    else result
                )
                return response(
                    MessageType.TASK_RESULT,
                    {"verified": verified, "capability": capability, "result": result},
                )
            if capability == "project.status":
                return response(
                    MessageType.TASK_RESULT,
                    {
                        "verified": True,
                        "capability": capability,
                        "result": self.unified_memory.snapshot(),
                    },
                )
            raise RuntimeError(
                f"Capability {capability or '(missing)'} is advertised for explicit adapters but has no active safe handler on this node."
            )
        except Exception as exc:  # noqa: BLE001
            return response(
                MessageType.ERROR,
                {"verified": False, "capability": capability, "error": str(exc)[:2_000]},
            )

    def set_default_music_provider(self, provider: str) -> None:
        clean = " ".join(str(provider or "").split())[:120]
        if not clean:
            return
        self.default_music_provider = clean
        self.desktop.applications.set_default_music_provider(clean)
        self.desktop.media.set_default_music_provider(clean)
        self.pc_router.set_default_music_provider(clean)

    def update_live_camera_diagnostics(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._live_camera_diagnostics = dict(payload or {})

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
            self.workers.submit(
                "application-discovery",
                self.desktop.applications.refresh_discovery,
            )
            if normalize_boolean_setting(
                os.getenv("MORICE_NODE_NETWORK", "true"), default=True
            ):
                try:
                    self.node_server.start()
                    self.node_discovery.node_port = self.node_server.bound_port
                    self.node_discovery.start_responder()
                except OSError as exc:
                    self.logs.log(
                        "WARNING",
                        f"MORICE node networking is unavailable: {exc}",
                        category="nodes",
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
        for distribution in (
            "PySide6",
            "numpy",
            "Pillow",
            "sounddevice",
            "vosk",
            "elevenlabs",
            "python-dotenv",
        ):
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
            voice={
                "state": self.voice.status().state.value,
                "provider": self.voice.status().provider,
                "apiConfigured": self.voice.status().api_configured,
                "queued": self.voice.status().queued,
                "active": self.voice.status().active,
                "lastErrorCode": self.voice.status().last_error_code.value,
            },
            speech_input=self.speech_input.diagnostics(),
            live_vision={
                **self.live_vision.diagnostics(),
                "camera": dict(self._live_camera_diagnostics),
            },
            realtime=self.realtime.snapshot(),
            pc_control={
                "permissions": self.pc_permissions.snapshot(),
                "capabilities": self.pc_control.capabilities(),
                "context": {
                    "activeApplication": self.pc_context.active_application,
                    "lastFile": self.pc_context.last_file,
                    "currentUrl": self.pc_context.current_url,
                    "lastActionId": self.pc_context.last_action_id,
                },
            },
            unified_intelligence={
                "permissions": self.unified_permissions.snapshot(),
                "capabilities": self.unified_capabilities.snapshot(),
                "workingMemory": self.unified_memory.snapshot(),
            },
            devices={
                "registry": self.device_registry.snapshot(),
                "environment": self.environment_registry.snapshot(),
                "node": self.node_descriptor.to_dict(),
                "nodeServer": {
                    "running": self.node_server.running,
                    "port": self.node_server.bound_port,
                    "pairing": self.node_server.pairing_status(),
                },
                "trustedNodes": [item.to_dict() for item in self.trusted_nodes.list()],
            },
            connectivity={
                "host": {
                    "adapter": self.host_adapter.adapter_id,
                    "profile": self.host_adapter.profile().to_dict(),
                    "capabilities": [
                        item.to_dict() for item in self.host_adapter.capabilities()
                    ],
                },
                "network": self.network.snapshot().to_dict(),
                "bluetooth": self.bluetooth.snapshot().to_dict(),
            },
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
                ("node discovery", self.node_discovery.stop),
                ("node server", self.node_server.stop),
                ("voice", self.voice.shutdown),
                ("speech input", self.speech_input.shutdown),
                ("live vision", self.live_vision.shutdown),
                ("goal orchestrator", self.goals.shutdown),
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
