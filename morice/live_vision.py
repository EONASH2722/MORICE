from __future__ import annotations

import base64
import io
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from PIL import Image, ImageChops, ImageFilter, ImageStat

from .config import local_data_dir
from .llama_server import selected_server_path


DEFAULT_VISUAL_MEMORY_SECONDS = 90.0
DEFAULT_MAX_FRAME_AGE_SECONDS = 2.5
DEFAULT_VISION_HF_REPOSITORY = (
    "ggml-org/SmolVLM2-500M-Video-Instruct-GGUF:Q8_0"
)
VISION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "extracted_text": {"type": "string"},
        "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        "uncertainty": {"type": "string"},
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "x": {"type": "number", "minimum": 0, "maximum": 1},
                    "y": {"type": "number", "minimum": 0, "maximum": 1},
                    "width": {"type": "number", "minimum": 0, "maximum": 1},
                    "height": {"type": "number", "minimum": 0, "maximum": 1},
                    "confidence": {
                        "type": ["number", "null"],
                        "minimum": 0,
                        "maximum": 1,
                    },
                },
                "required": ["label", "x", "y", "width", "height", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "extracted_text", "confidence", "uncertainty", "regions"],
    "additionalProperties": False,
}


class VisionState(str, Enum):
    DISABLED = "disabled"
    READY = "ready"
    ANALYZING = "analyzing"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True)
class FrameQuality:
    brightness: float
    contrast: float
    sharpness: float
    issues: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return not self.issues

    def public_dict(self) -> dict[str, Any]:
        return {
            "brightness": round(self.brightness, 2),
            "contrast": round(self.contrast, 2),
            "sharpness": round(self.sharpness, 2),
            "issues": list(self.issues),
            "usable": self.usable,
        }


@dataclass(frozen=True)
class VisionFrame:
    frame_id: str
    captured_at: datetime
    monotonic_ns: int
    width: int
    height: int
    jpeg: bytes = field(repr=False, compare=False)
    camera_id: str = ""
    mirrored: bool = False
    quality: FrameQuality | None = None

    @property
    def timestamp(self) -> str:
        return self.captured_at.astimezone(timezone.utc).isoformat()

    def age_seconds(self, *, now_ns: int | None = None) -> float:
        current = int(now_ns if now_ns is not None else time.monotonic_ns())
        return max(0.0, (current - self.monotonic_ns) / 1_000_000_000.0)

    def with_quality(self, quality: FrameQuality) -> "VisionFrame":
        return VisionFrame(
            self.frame_id,
            self.captured_at,
            self.monotonic_ns,
            self.width,
            self.height,
            self.jpeg,
            self.camera_id,
            self.mirrored,
            quality,
        )


@dataclass(frozen=True)
class VisionRegion:
    label: str
    x: float
    y: float
    width: float
    height: float
    confidence: float | None = None

    def public_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }
        if self.confidence is not None:
            result["confidence"] = self.confidence
        return result


@dataclass(frozen=True)
class VisionResult:
    request_id: str
    frame_id: str
    frame_timestamp: str
    provider: str
    success: bool
    summary: str = ""
    extracted_text: str = ""
    confidence: float | None = None
    uncertainty: str = ""
    regions: tuple[VisionRegion, ...] = ()
    failure_code: str = ""
    message: str = ""
    latency_ms: float = 0.0
    quality: FrameQuality | None = None

    @classmethod
    def failure(
        cls,
        request_id: str,
        frame: VisionFrame | None,
        code: str,
        message: str,
        *,
        provider: str = "none",
        latency_ms: float = 0.0,
        quality: FrameQuality | None = None,
    ) -> "VisionResult":
        return cls(
            request_id=request_id,
            frame_id=frame.frame_id if frame is not None else "",
            frame_timestamp=frame.timestamp if frame is not None else "",
            provider=provider,
            success=False,
            failure_code=str(code or "vision-failed")[:80],
            message=str(message or "Visual analysis failed.")[:800],
            latency_ms=max(0.0, float(latency_ms)),
            quality=quality or (frame.quality if frame is not None else None),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "frameId": self.frame_id,
            "frameTimestamp": self.frame_timestamp,
            "provider": self.provider,
            "success": self.success,
            "summary": self.summary,
            "extractedText": self.extracted_text,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "regions": [region.public_dict() for region in self.regions],
            "failureCode": self.failure_code,
            "message": self.message,
            "latencyMs": round(self.latency_ms, 2),
            "quality": self.quality.public_dict() if self.quality else None,
        }

    def context_text(self) -> str:
        if not self.success:
            return (
                "LIVE_VISION_RESULT: unavailable\n"
                f"Failure: {self.failure_code or 'vision-failed'}\n"
                f"Detail: {self.message}"
            )
        confidence = (
            f"{self.confidence:.2f}" if self.confidence is not None else "not provided"
        )
        parts = [
            "LIVE_VISION_RESULT: successfully processed actual camera frame",
            f"Frame timestamp: {self.frame_timestamp}",
            f"Provider: {self.provider}",
            f"Confidence: {confidence}",
            f"Observed summary: {self.summary}",
        ]
        if self.extracted_text:
            parts.append(f"Visible text: {self.extracted_text}")
        if self.uncertainty:
            parts.append(f"Uncertainty: {self.uncertainty}")
        parts.append(
            "Use only these processed observations. Do not add visual details that "
            "are not present above."
        )
        return "\n".join(parts)


@dataclass(frozen=True)
class VisionProviderStatus:
    provider: str
    available: bool
    ready: bool
    message: str
    model: str = ""
    gpu_layers: int = 0

    def public_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "available": self.available,
            "ready": self.ready,
            "message": self.message,
            "model": self.model,
            "gpuLayers": self.gpu_layers,
        }


class VisionProvider(Protocol):
    @property
    def name(self) -> str: ...

    def status(self) -> VisionProviderStatus: ...

    def prewarm(self) -> VisionProviderStatus: ...

    def analyze(
        self,
        frame: VisionFrame,
        prompt: str,
        *,
        cancel_event: threading.Event,
        request_id: str,
    ) -> VisionResult: ...

    def shutdown(self) -> None: ...


class FrameManager:
    """Own only the latest camera frame and lightweight scene statistics."""

    def __init__(self, *, max_frame_age_seconds: float = DEFAULT_MAX_FRAME_AGE_SECONDS):
        self.max_frame_age_seconds = max(0.25, float(max_frame_age_seconds))
        self._latest: VisionFrame | None = None
        self._scene_thumbnail: Image.Image | None = None
        self._scene_change = 0.0
        self._published = 0
        self._dropped = 0
        self._lock = threading.RLock()

    def publish(
        self,
        jpeg: bytes,
        *,
        width: int,
        height: int,
        camera_id: str = "",
        mirrored: bool = False,
        captured_at: datetime | None = None,
        monotonic_ns: int | None = None,
    ) -> VisionFrame:
        payload = bytes(jpeg or b"")
        if not payload:
            raise ValueError("A camera frame cannot be empty.")
        if int(width) <= 0 or int(height) <= 0:
            raise ValueError("A camera frame must have positive dimensions.")
        frame = VisionFrame(
            frame_id=uuid.uuid4().hex,
            captured_at=captured_at or datetime.now(timezone.utc),
            monotonic_ns=int(monotonic_ns or time.monotonic_ns()),
            width=int(width),
            height=int(height),
            jpeg=payload,
            camera_id=" ".join(str(camera_id or "").split())[:300],
            mirrored=bool(mirrored),
        )
        scene_change = self._measure_scene_change(payload)
        with self._lock:
            if self._latest is not None:
                self._dropped += 1
            self._latest = frame
            self._scene_change = scene_change
            self._published += 1
        return frame

    def latest(self, *, require_fresh: bool = True) -> VisionFrame | None:
        with self._lock:
            frame = self._latest
        if frame is None:
            return None
        if require_fresh and frame.age_seconds() > self.max_frame_age_seconds:
            return None
        return frame

    def clear(self) -> None:
        with self._lock:
            self._latest = None
            self._scene_thumbnail = None
            self._scene_change = 0.0

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            latest = self._latest
            return {
                "framesPublished": self._published,
                "framesReplaced": self._dropped,
                "latestFrameId": latest.frame_id if latest else "",
                "latestFrameAgeMs": (
                    round(latest.age_seconds() * 1000.0, 2) if latest else None
                ),
                "sceneChange": round(self._scene_change, 4),
            }

    def _measure_scene_change(self, jpeg: bytes) -> float:
        try:
            with Image.open(io.BytesIO(jpeg)) as image:
                thumbnail = image.convert("L")
                thumbnail.thumbnail((96, 54))
                thumbnail = thumbnail.copy()
        except Exception:
            return 0.0
        with self._lock:
            previous = self._scene_thumbnail
            self._scene_thumbnail = thumbnail
        if previous is None or previous.size != thumbnail.size:
            return 1.0
        difference = ImageChops.difference(previous, thumbnail)
        return max(0.0, min(1.0, ImageStat.Stat(difference).mean[0] / 255.0))


def assess_frame_quality(jpeg: bytes) -> FrameQuality:
    try:
        with Image.open(io.BytesIO(bytes(jpeg or b""))) as image:
            gray = image.convert("L")
            gray.thumbnail((320, 240))
            statistics = ImageStat.Stat(gray)
            brightness = float(statistics.mean[0])
            contrast = float(statistics.stddev[0])
            edges = gray.filter(ImageFilter.FIND_EDGES)
            sharpness = float(ImageStat.Stat(edges).mean[0])
    except Exception as exc:
        raise ValueError("The selected camera frame is not a readable image.") from exc
    issues: list[str] = []
    if brightness < 22.0:
        issues.append("too-dark")
    elif brightness > 245.0:
        issues.append("overexposed")
    if contrast < 7.0:
        issues.append("low-contrast")
    if sharpness < 2.2:
        issues.append("blurry")
    return FrameQuality(brightness, contrast, sharpness, tuple(issues))


class VisualMemory:
    """Short-lived structured context; raw camera bytes are never retained here."""

    def __init__(self, *, ttl_seconds: float = DEFAULT_VISUAL_MEMORY_SECONDS):
        self.ttl_seconds = max(5.0, float(ttl_seconds))
        self._result: VisionResult | None = None
        self._stored_ns = 0
        self._lock = threading.RLock()

    def remember(self, result: VisionResult) -> None:
        if not result.success:
            return
        sanitized = VisionResult(
            request_id=result.request_id,
            frame_id=result.frame_id,
            frame_timestamp=result.frame_timestamp,
            provider=result.provider,
            success=True,
            summary=result.summary,
            extracted_text=result.extracted_text,
            confidence=result.confidence,
            uncertainty=result.uncertainty,
            regions=result.regions,
            latency_ms=result.latency_ms,
            quality=result.quality,
        )
        with self._lock:
            self._result = sanitized
            self._stored_ns = time.monotonic_ns()

    def recall(self) -> VisionResult | None:
        with self._lock:
            result = self._result
            stored_ns = self._stored_ns
        if result is None:
            return None
        age = (time.monotonic_ns() - stored_ns) / 1_000_000_000.0
        if age > self.ttl_seconds:
            self.clear()
            return None
        return result

    def clear(self) -> None:
        with self._lock:
            self._result = None
            self._stored_ns = 0

    def diagnostics(self) -> dict[str, Any]:
        result = self.recall()
        return {
            "active": result is not None,
            "frameId": result.frame_id if result else "",
            "provider": result.provider if result else "",
            "ttlSeconds": self.ttl_seconds,
        }


class LlamaCppVisionProvider:
    """On-demand OpenAI-compatible multimodal provider backed by llama.cpp."""

    def __init__(
        self,
        *,
        server_path: str | os.PathLike[str] | None = None,
        model_path: str | os.PathLike[str] | None = None,
        mmproj_path: str | os.PathLike[str] | None = None,
        hf_repository: str | None = None,
        host: str = "127.0.0.1",
        port: int = 8081,
        timeout_seconds: float = 180.0,
        cache_dir: str | os.PathLike[str] | None = None,
        gpu_layers: int = 0,
        logger: Callable[[str, dict[str, Any]], None] | None = None,
        process_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
    ):
        data_root = local_data_dir()
        configured_server = str(server_path or os.getenv("MORICE_VISION_SERVER_PATH", "")).strip()
        if not configured_server:
            # Reuse the same resolver as conversational inference. This keeps a
            # clean portable build functional with the llama server bundled in
            # ``morice/assets/llama-bin`` while still preferring an installed
            # CUDA runtime from MORICE's local-data directory.
            configured_server = selected_server_path() or str(
                data_root / "llama-cuda" / "llama-server.exe"
            )
        self.server_path = Path(configured_server).expanduser().resolve()
        configured_model = str(model_path or os.getenv("MORICE_VISION_MODEL", "")).strip()
        configured_mmproj = str(mmproj_path or os.getenv("MORICE_VISION_MMPROJ", "")).strip()
        installed_pairs = (
            (
                Path(__file__).resolve().parent
                / "assets"
                / "vision"
                / "SmolVLM2-500M-Video-Instruct-Q8_0.gguf",
                Path(__file__).resolve().parent
                / "assets"
                / "vision"
                / "mmproj-SmolVLM2-500M-Video-Instruct-Q8_0.gguf",
            ),
            (
                data_root
                / "models"
                / "vision"
                / "SmolVLM2-500M-Video-Instruct-GGUF"
                / "SmolVLM2-500M-Video-Instruct-Q8_0.gguf",
                data_root
                / "models"
                / "vision"
                / "SmolVLM2-500M-Video-Instruct-GGUF"
                / "mmproj-SmolVLM2-500M-Video-Instruct-Q8_0.gguf",
            ),
            (
                data_root
                / "models"
                / "vision"
                / "SmolVLM2-2.2B-Instruct-GGUF"
                / "SmolVLM2-2.2B-Instruct-Q4_K_M.gguf",
                data_root
                / "models"
                / "vision"
                / "SmolVLM2-2.2B-Instruct-GGUF"
                / "mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf",
            ),
        )
        if not configured_model and not configured_mmproj:
            for installed_model, installed_mmproj in installed_pairs:
                if installed_model.is_file() and installed_mmproj.is_file():
                    configured_model = str(installed_model)
                    configured_mmproj = str(installed_mmproj)
                    break
        self.model_path = Path(configured_model).expanduser().resolve() if configured_model else None
        self.mmproj_path = Path(configured_mmproj).expanduser().resolve() if configured_mmproj else None
        self.hf_repository = " ".join(
            str(
                hf_repository
                if hf_repository is not None
                else os.getenv("MORICE_VISION_HF", "")
            ).split()
        )[:300]
        self.host = str(host or "127.0.0.1")
        self.port = max(1024, min(65535, int(port)))
        self.timeout_seconds = max(10.0, min(300.0, float(timeout_seconds)))
        self.cache_dir = Path(cache_dir or (data_root / "models" / "vision" / "cache"))
        # CPU is deliberate by default: the conversational LLM already occupies
        # most of the RTX 3050. A future resource-manager decision may raise this.
        self.gpu_layers = max(0, int(gpu_layers))
        self._logger = logger or (lambda _event, _metadata: None)
        self._process_factory = process_factory
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.RLock()

    @property
    def name(self) -> str:
        return "llama.cpp-multimodal"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def status(self) -> VisionProviderStatus:
        local_configured = bool(
            self.model_path is not None
            and self.model_path.is_file()
            and self.mmproj_path is not None
            and self.mmproj_path.is_file()
        )
        model_label = (
            self.model_path.name
            if local_configured and self.model_path is not None
            else self.hf_repository
        )
        if not self.server_path.is_file():
            return VisionProviderStatus(
                self.name,
                False,
                False,
                "The llama.cpp multimodal server is unavailable.",
                model_label,
                self.gpu_layers,
            )
        if not self.hf_repository and not local_configured:
            return VisionProviderStatus(
                self.name,
                False,
                False,
                "No compatible visual model and projector are configured.",
                model_label,
                self.gpu_layers,
            )
        ready = self._server_ready()
        return VisionProviderStatus(
            self.name,
            True,
            ready,
            "Vision provider is ready." if ready else "Vision provider is configured but not running.",
            model_label,
            self.gpu_layers,
        )

    def prewarm(self) -> VisionProviderStatus:
        status = self.status()
        if not status.available or status.ready:
            return status
        self._ensure_server()
        return self.status()

    def analyze(
        self,
        frame: VisionFrame,
        prompt: str,
        *,
        cancel_event: threading.Event,
        request_id: str,
    ) -> VisionResult:
        started = time.perf_counter()
        if cancel_event.is_set():
            return VisionResult.failure(
                request_id,
                frame,
                "cancelled",
                "Visual analysis was interrupted.",
                provider=self.name,
            )
        try:
            self._ensure_server()
        except Exception as exc:  # noqa: BLE001
            return VisionResult.failure(
                request_id,
                frame,
                "provider-unavailable",
                str(exc),
                provider=self.name,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        if cancel_event.is_set():
            return VisionResult.failure(
                request_id,
                frame,
                "cancelled",
                "Visual analysis was interrupted.",
                provider=self.name,
            )
        strict_prompt = (
            "Analyze only the supplied camera image. Never invent an object, text, "
            "condition, connection, or location that is not visibly supported. If the "
            "view is ambiguous, dark, blurry, cropped, or too distant, explain that in "
            "uncertainty. Return only JSON with keys summary, extracted_text, confidence, "
            "uncertainty, and regions. confidence must be 0 to 1. regions must be a list "
            "of optional normalized boxes with label, x, y, width, height, confidence; "
            "use an empty list unless a box is genuinely supported.\n\n"
            f"User request: {str(prompt or 'Describe what is visible.')[:2000]}"
        )
        image_url = "data:image/jpeg;base64," + base64.b64encode(frame.jpeg).decode("ascii")
        payload = {
            "model": "vision",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": strict_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 160,
            "response_format": {"type": "json_object", "schema": VISION_RESPONSE_SCHEMA},
            "stream": False,
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
            response_payload = json.loads(raw)
            content = str(response_payload["choices"][0]["message"]["content"] or "").strip()
            parsed = _parse_provider_json(content)
        except (OSError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return VisionResult.failure(
                request_id,
                frame,
                "inference-failed",
                f"The vision provider could not process the current frame: {exc}",
                provider=self.name,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        if cancel_event.is_set():
            return VisionResult.failure(
                request_id,
                frame,
                "cancelled",
                "Visual analysis was interrupted.",
                provider=self.name,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        summary = _clean_text(parsed.get("summary"), 1600)
        uncertainty = _clean_text(parsed.get("uncertainty"), 600)
        extracted_text = _clean_text(parsed.get("extracted_text"), 2000)
        if not summary:
            return VisionResult.failure(
                request_id,
                frame,
                "empty-result",
                "The vision provider returned no usable observation.",
                provider=self.name,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
        confidence = _confidence(parsed.get("confidence"))
        regions = _regions(parsed.get("regions"))
        return VisionResult(
            request_id=request_id,
            frame_id=frame.frame_id,
            frame_timestamp=frame.timestamp,
            provider=self.name,
            success=True,
            summary=summary,
            extracted_text=extracted_text,
            confidence=confidence,
            uncertainty=uncertainty,
            regions=regions,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            quality=frame.quality,
        )

    def shutdown(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()

    def _ensure_server(self) -> None:
        if self._server_ready():
            return
        status = self.status()
        if not status.available:
            raise RuntimeError(status.message)
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                command = [
                    str(self.server_path),
                    "--host",
                    self.host,
                    "--port",
                    str(self.port),
                    "--ctx-size",
                    "2048",
                    "--threads",
                    str(max(2, min(8, (os.cpu_count() or 4) - 1))),
                    "--threads-batch",
                    str(max(2, min(8, (os.cpu_count() or 4) - 1))),
                    "--batch-size",
                    "128",
                    "--ubatch-size",
                    "64",
                    "--parallel",
                    "1",
                    "--gpu-layers",
                    str(self.gpu_layers),
                    "--image-max-tokens",
                    "512",
                    # Use llama.cpp's built-in SmolVLM template rather than the
                    # model's embedded Jinja. ChatML starts the server but can
                    # silently degrade image grounding on this model family.
                    "--no-jinja",
                    "--chat-template",
                    "smolvlm",
                    "--json-schema",
                    json.dumps(VISION_RESPONSE_SCHEMA, separators=(",", ":")),
                    "--no-webui",
                ]
                if self.gpu_layers <= 0:
                    command.extend(["--device", "none", "--no-mmproj-offload"])
                local_configured = bool(
                    self.model_path is not None
                    and self.model_path.is_file()
                    and self.mmproj_path is not None
                    and self.mmproj_path.is_file()
                )
                if local_configured:
                    command.extend(
                        [
                            "--model",
                            str(self.model_path),
                            "--mmproj",
                            str(self.mmproj_path),
                        ]
                    )
                else:
                    command.extend(["--hf-repo", self.hf_repository])
                environment = os.environ.copy()
                environment["LLAMA_CACHE"] = str(self.cache_dir)
                startup_info = None
                creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self._process = self._process_factory(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    env=environment,
                    creationflags=creation_flags,
                    startupinfo=startup_info,
                )
                self._logger(
                    "vision-provider-start",
                    {
                        "provider": self.name,
                        "model": (
                            str(self.model_path)
                            if local_configured
                            else self.hf_repository
                        ),
                        "gpuLayers": self.gpu_layers,
                        "port": self.port,
                    },
                )
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            if self._server_ready():
                return
            with self._lock:
                process = self._process
            if process is not None and process.poll() is not None:
                raise RuntimeError(
                    f"The vision provider exited during startup (code {process.returncode})."
                )
            time.sleep(0.2)
        raise RuntimeError("The vision provider did not become ready in time.")

    def _server_ready(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=0.25):
                pass
            with urllib.request.urlopen(f"{self.base_url}/v1/models", timeout=0.6) as response:
                return 200 <= int(getattr(response, "status", 200)) < 300
        except (OSError, urllib.error.URLError):
            return False


class LiveVisionRuntime:
    """Coordinates fresh-frame selection, quality gates, inference, and memory."""

    def __init__(
        self,
        provider: VisionProvider,
        *,
        frame_manager: FrameManager | None = None,
        memory: VisualMemory | None = None,
        enabled: bool = True,
        logger: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self.provider = provider
        self.frames = frame_manager or FrameManager()
        self.memory = memory or VisualMemory()
        self.enabled = bool(enabled)
        self._logger = logger or (lambda _event, _metadata: None)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="morice-vision")
        self._active_request_id = ""
        self._active_cancel: threading.Event | None = None
        self._completed = 0
        self._failures = 0
        self._last_result: VisionResult | None = None
        self._state = VisionState.READY if enabled else VisionState.DISABLED
        self._lock = threading.RLock()

    @property
    def state(self) -> VisionState:
        with self._lock:
            return self._state

    def configure(self, *, enabled: bool) -> VisionState:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.cancel("vision-disabled")
            self.frames.clear()
            self.memory.clear()
        with self._lock:
            self._state = VisionState.READY if self.enabled else VisionState.DISABLED
            return self._state

    def publish_frame(self, jpeg: bytes, **metadata: Any) -> VisionFrame:
        if not self.enabled:
            raise RuntimeError("Vision processing is disabled.")
        return self.frames.publish(jpeg, **metadata)

    def analyze_latest(
        self,
        prompt: str,
        *,
        request_id: str | None = None,
        on_complete: Callable[[VisionResult], None] | None = None,
    ) -> Future[VisionResult]:
        clean_request_id = " ".join(str(request_id or "").split())[:120] or uuid.uuid4().hex
        clean_prompt = " ".join(str(prompt or "Describe what is visible.").split())[:2000]
        if not self.enabled:
            result = VisionResult.failure(
                clean_request_id,
                None,
                "vision-disabled",
                "Vision processing is disabled. Enable it explicitly to analyze the camera.",
            )
            return _completed_future(result, on_complete)
        frame = self.frames.latest(require_fresh=True)
        if frame is None:
            result = VisionResult.failure(
                clean_request_id,
                self.frames.latest(require_fresh=False),
                "no-fresh-frame",
                "I don't have a fresh camera frame. Turn the camera on and keep the item in view.",
            )
            return _completed_future(result, on_complete)
        self.cancel("superseded")
        cancel_event = threading.Event()
        with self._lock:
            self._active_request_id = clean_request_id
            self._active_cancel = cancel_event
            self._state = VisionState.ANALYZING

        def worker() -> VisionResult:
            started = time.perf_counter()
            try:
                quality = assess_frame_quality(frame.jpeg)
                assessed = frame.with_quality(quality)
                if quality.issues:
                    message = _quality_message(quality)
                    result = VisionResult.failure(
                        clean_request_id,
                        assessed,
                        quality.issues[0],
                        message,
                        provider=self.provider.name,
                        latency_ms=(time.perf_counter() - started) * 1000.0,
                        quality=quality,
                    )
                else:
                    result = self.provider.analyze(
                        assessed,
                        clean_prompt,
                        cancel_event=cancel_event,
                        request_id=clean_request_id,
                    )
            except Exception as exc:  # noqa: BLE001
                result = VisionResult.failure(
                    clean_request_id,
                    frame,
                    "vision-error",
                    f"Visual analysis failed safely: {exc}",
                    provider=self.provider.name,
                    latency_ms=(time.perf_counter() - started) * 1000.0,
                )
            with self._lock:
                current = self._active_request_id == clean_request_id
                if current:
                    self._active_request_id = ""
                    self._active_cancel = None
                    self._last_result = result
                    self._state = VisionState.READY if result.success else VisionState.ERROR
                    self._completed += 1
                    if not result.success:
                        self._failures += 1
            if current and result.success:
                self.memory.remember(result)
            self._logger("vision-result", result.public_dict())
            if current and on_complete is not None:
                try:
                    on_complete(result)
                except Exception:  # noqa: BLE001
                    pass
            return result

        return self._executor.submit(worker)

    def cancel(self, reason: str = "cancelled") -> bool:
        with self._lock:
            cancel_event = self._active_cancel
            active = bool(self._active_request_id)
            self._active_request_id = ""
            self._active_cancel = None
            if self.enabled:
                self._state = VisionState.READY
        if cancel_event is not None:
            cancel_event.set()
        if active:
            self._logger("vision-cancel", {"reason": str(reason or "cancelled")[:120]})
        return active

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            last = self._last_result
            state = self._state
            active_request_id = self._active_request_id
            completed = self._completed
            failures = self._failures
        return {
            "enabled": self.enabled,
            "state": state.value,
            "activeRequestId": active_request_id,
            "provider": self.provider.status().public_dict(),
            "frames": self.frames.diagnostics(),
            "memory": self.memory.diagnostics(),
            "requestsCompleted": completed,
            "requestFailures": failures,
            "lastResult": last.public_dict() if last else None,
        }

    def shutdown(self) -> None:
        self.cancel("shutdown")
        self.frames.clear()
        self.memory.clear()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.provider.shutdown()


def visual_intent(text: str) -> bool:
    clean = " ".join(str(text or "").casefold().split())
    if not clean:
        return False
    patterns = (
        r"\bwhat (?:am i holding|is this|is that|can you see)\b",
        r"\b(?:look at|describe|inspect|analy[sz]e|read) (?:this|that|the|what)\b",
        r"\bwhat(?:'s| is) (?:written|wrong|visible|there|this part)\b",
        r"\bwhich (?:cable|connector|part|component)\b",
        r"\bdoes (?:this|that) look\b",
        r"\bcan you see\b",
        r"\b(?:camera|view|pointing at|holding)\b",
    )
    return any(re.search(pattern, clean) for pattern in patterns)


def visual_follow_up(text: str) -> bool:
    clean = " ".join(str(text or "").casefold().split())
    return bool(
        re.search(
            r"\b(?:this part|that part|it|that|this|the same|search it|search this|copy that|copy it)\b",
            clean,
        )
    )


def _completed_future(
    result: VisionResult,
    callback: Callable[[VisionResult], None] | None,
) -> Future[VisionResult]:
    future: Future[VisionResult] = Future()
    future.set_result(result)
    if callback is not None:
        try:
            callback(result)
        except Exception:  # noqa: BLE001
            pass
    return future


def _clean_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").replace("\x00", "").split())[:limit]


def _confidence(value: Any) -> float | None:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, amount))


def _regions(value: Any) -> tuple[VisionRegion, ...]:
    if not isinstance(value, list):
        return ()
    results: list[VisionRegion] = []
    for item in value[:12]:
        if not isinstance(item, Mapping):
            continue
        label = _clean_text(item.get("label"), 100)
        if not label:
            continue
        try:
            x = max(0.0, min(1.0, float(item.get("x", 0.0))))
            y = max(0.0, min(1.0, float(item.get("y", 0.0))))
            width = max(0.0, min(1.0 - x, float(item.get("width", 0.0))))
            height = max(0.0, min(1.0 - y, float(item.get("height", 0.0))))
        except (TypeError, ValueError):
            continue
        if width <= 0.0 or height <= 0.0:
            continue
        results.append(
            VisionRegion(label, x, y, width, height, _confidence(item.get("confidence")))
        )
    return tuple(results)


def _parse_provider_json(text: str) -> dict[str, Any]:
    clean = str(text or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.IGNORECASE)
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, flags=re.DOTALL)
        if match is None:
            raise ValueError("The vision provider did not return valid JSON.")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError("The vision provider did not return valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("The vision provider returned a non-object JSON value.")
    required = {"summary", "extracted_text", "confidence", "uncertainty", "regions"}
    if not required.issubset(parsed):
        raise ValueError("The vision provider returned an unexpected JSON schema.")
    if not isinstance(parsed["summary"], str) or not parsed["summary"].strip():
        raise ValueError("The vision provider returned no summary.")
    if not isinstance(parsed["extracted_text"], str) or not isinstance(parsed["uncertainty"], str):
        raise ValueError("The vision provider returned invalid text fields.")
    if parsed["confidence"] is not None and not isinstance(parsed["confidence"], (int, float)):
        raise ValueError("The vision provider returned invalid confidence.")
    if not isinstance(parsed["regions"], list):
        raise ValueError("The vision provider returned invalid regions.")
    return parsed


def _quality_message(quality: FrameQuality) -> str:
    if "too-dark" in quality.issues:
        return "The image is too dark for a reliable answer. Add light or move the item closer."
    if "overexposed" in quality.issues:
        return "The image is overexposed. Reduce the light or change the camera angle."
    if "low-contrast" in quality.issues:
        return "I can't make out enough detail from this view. Move the item closer or improve the lighting."
    if "blurry" in quality.issues:
        return "The current frame is too blurry for a reliable answer. Hold the item still and move it closer."
    return "The current camera frame is not clear enough for reliable visual analysis."


__all__ = [
    "DEFAULT_VISION_HF_REPOSITORY",
    "VISION_RESPONSE_SCHEMA",
    "FrameManager",
    "FrameQuality",
    "LiveVisionRuntime",
    "LlamaCppVisionProvider",
    "VisionFrame",
    "VisionProvider",
    "VisionProviderStatus",
    "VisionRegion",
    "VisionResult",
    "VisionState",
    "VisualMemory",
    "assess_frame_quality",
    "visual_follow_up",
    "visual_intent",
]
