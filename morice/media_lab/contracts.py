"""Versioned media DTOs consumed by providers and the future Media UI."""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from enum import Enum


class ModelState(str, Enum):
    DISCOVERED = "DISCOVERED"
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    INCOMPATIBLE = "INCOMPATIBLE"
    DISABLED = "DISABLED"
    FAILED_HEALTH = "FAILED_HEALTH"
    UNBENCHMARKED = "UNBENCHMARKED"


class Quality(str, Enum):
    FAST = "FAST"
    BALANCED = "BALANCED"
    QUALITY = "QUALITY"
    MAXIMUM_THAT_FITS = "MAXIMUM_THAT_FITS"


class JobState(str, Enum):
    QUEUED = "QUEUED"
    WAITING_FOR_RESOURCES = "WAITING_FOR_RESOURCES"
    LOADING_MODEL = "LOADING_MODEL"
    GENERATING = "GENERATING"
    POSTPROCESSING = "POSTPROCESSING"
    ENCODING = "ENCODING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True)
class ImageModelDescriptor:
    model_id: str
    display_name: str
    architecture: str
    backend: str
    model_path: str
    source: str = "local"
    license: str = "UNKNOWN"
    precision: str = "fp16"
    quantization: str = "none"
    estimated_vram_mb: int = 4096
    estimated_ram_mb: int = 3072
    minimum_vram_mb: int = 2048
    recommended_resolution: tuple[int, int] = (512, 512)
    maximum_tested_resolution: tuple[int, int] | None = None
    capabilities: tuple[str, ...] = ("TEXT_TO_IMAGE",)
    supports_cpu_offload: bool = True
    supports_attention_slicing: bool = True
    supports_low_vram: bool = True
    supports_lora: bool = False
    supports_vae: bool = True
    version: str = ""
    health: ModelState = ModelState.DISCOVERED
    health_reason: str = "Not inspected or loaded."
    sha256: str = ""
    files: tuple[dict, ...] = ()
    dimension_multiple: int = 8
    maximum_resolution: tuple[int, int] = (1024, 1024)
    maximum_steps: int = 50
    default_steps: int = 20
    default_guidance: float = 7.5
    pipeline_class: str = ""
    variant: str | None = "fp16"
    enabled: bool = True

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", self.model_id):
            raise ValueError("Model ID must be a bounded stable identifier.")
        if self.backend not in {"diffusers", "comfyui", "test"}:
            raise ValueError("Unrecognized model backend.")
        if self.precision not in {"fp16", "fp32", "bf16"} or self.quantization != "none":
            raise ValueError("This adapter does not yet validate this precision/quantization.")
        if any(type(n) is not int or n < 1 for n in (self.estimated_vram_mb,self.estimated_ram_mb,self.minimum_vram_mb,self.dimension_multiple,self.maximum_steps,self.default_steps)):
            raise ValueError("Invalid model resource/dimension defaults.")
        if self.default_steps > self.maximum_steps or not math.isfinite(self.default_guidance):
            raise ValueError("Invalid model generation defaults.")

    def to_dict(self):
        value = asdict(self); value["health"] = self.health.value
        return value


@dataclass(frozen=True)
class VideoModelDescriptor(ImageModelDescriptor):
    recommended_frames: int = 8
    maximum_tested_frames: int | None = None
    maximum_frames: int = 16
    supports_frame_chunking: bool = False
    supports_temporal_tiling: bool = False
    capabilities: tuple[str, ...] = ("IMAGE_TO_VIDEO",)

    def __post_init__(self):
        super().__post_init__()
        if not 1 <= self.recommended_frames <= self.maximum_frames <= 256:
            raise ValueError("Invalid bounded video frame limits.")


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    model_id: str = ""
    intent: str = "TEXT_TO_IMAGE"
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    steps: int | None = None
    guidance: float | None = None
    seed: int = 0
    count: int = 1
    quality: Quality = Quality.BALANCED
    reference_images: tuple[str, ...] = ()
    mask: str = ""
    strength: float = 0.5
    controls: tuple[dict, ...] = ()
    loras: tuple[dict, ...] = ()
    output_format: str = "PNG"
    allow_fallback: bool = False
    allow_constant: bool = False
    node_id: str = "local"
    motion: str = ""

    def __post_init__(self):
        Quality(self.quality)
        if not isinstance(self.prompt,str) or not 1 <= len(self.prompt.strip()) <= 4000 or len(self.negative_prompt) > 4000:
            raise ValueError("A bounded non-empty prompt is required.")
        if type(self.width) is not int or type(self.height) is not int or not 64 <= self.width <= 4096 or not 64 <= self.height <= 4096:
            raise ValueError("Image dimensions must be within 64..4096.")
        if type(self.count) is not int or not 1 <= self.count <= 8 or type(self.seed) is not int or not 0 <= self.seed <= 2**32-8:
            raise ValueError("Invalid batch size or seed.")
        if self.steps is not None and (type(self.steps) is not int or not 1 <= self.steps <= 100):
            raise ValueError("Invalid bounded step count.")
        if self.guidance is not None and (not math.isfinite(self.guidance) or not 0 <= self.guidance <= 30):
            raise ValueError("Invalid guidance value.")
        if not math.isfinite(self.strength) or not 0 < self.strength <= 1:
            raise ValueError("Invalid image-to-image strength.")
        if len(self.reference_images) > 2 or self.controls or len(self.loras) > 4:
            raise ValueError("Unimplemented control guidance or excessive adapters/references.")
        if self.output_format.upper() not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Unsupported image output format.")
        if not self.node_id or len(self.node_id) > 128:
            raise ValueError("Invalid pinned node.")

    def to_dict(self):
        value=asdict(self); value["quality"]=Quality(self.quality).value
        for key in ("reference_images","controls","loras"):
            value[key]=list(value[key])
        return value

    @classmethod
    def from_dict(cls,value):
        value=dict(value)
        for k in ("reference_images","controls","loras"):
            value[k]=tuple(value.get(k,()))
        return cls(**value)


@dataclass(frozen=True)
class VideoRequest(ImageRequest):
    intent: str = "IMAGE_TO_VIDEO"
    frames: int = 8
    fps: int = 8
    duration: float | None = None
    output_format: str = "MP4"
    count: int = 1

    def __post_init__(self):
        # Validate common fields without lying about accepted video formats.
        image_fields={k:v for k,v in asdict(self).items() if k in ImageRequest.__dataclass_fields__}
        image_fields["output_format"]="PNG"
        ImageRequest(**image_fields)
        if self.output_format.upper() not in {"MP4","WEBM","GIF"}:
            raise ValueError("Unsupported video output format.")
        if type(self.frames) is not int or not 2 <= self.frames <= 256 or type(self.fps) is not int or not 1 <= self.fps <= 60 or self.count != 1:
            raise ValueError("Invalid bounded frame count/fps; video batches use separate jobs.")
        if self.duration is not None and (not math.isfinite(self.duration) or abs(self.duration-self.frames/self.fps)>1/self.fps):
            raise ValueError("Duration must agree with frame count and fps.")


@dataclass(frozen=True)
class MediaSettings:
    preferred_image_model: str = ""
    preferred_video_model: str = ""
    model_directories: tuple[str, ...] = ()
    quality_default: Quality = Quality.BALANCED
    max_resolution: int = 1024
    max_video_frames: int = 16
    cpu_offload: bool = True
    model_lifecycle: str = "ALWAYS_COLD"
    disk_cache_limit_mb: int = 256
    max_history: int = 500
    vram_margin_mb: int = 768
    ram_margin_mb: int = 2048
    high_power_only_on_ac: bool = False

    def __post_init__(self):
        Quality(self.quality_default)
        if self.model_lifecycle not in {"ALWAYS_COLD", "UNLOAD_AFTER_TASK"}:
            raise ValueError("KEEP_WARM/idle timers are not implemented by the isolated cold worker.")
        if not 64 <= self.max_resolution <= 2048 or not 2 <= self.max_video_frames <= 256 or not 1 <= self.max_history <= 5000:
            raise ValueError("Invalid media limits.")
        if not 256 <= self.vram_margin_mb <= 8192 or not 1024 <= self.ram_margin_mb <= 32768 or not 1 <= self.disk_cache_limit_mb <= 4096:
            raise ValueError("Invalid safety/cache margins.")
