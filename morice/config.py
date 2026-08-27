from __future__ import annotations

import os
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, MutableMapping


DEFAULT_ELEVENLABS_VOICE_ID = "oTWkNN1jSpFLkYHKcSXU"
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_flash_v2_5"
DEFAULT_TTS_OUTPUT_FORMAT = "pcm_24000"
_API_KEY_PLACEHOLDERS = {
    "",
    "<USER_MUST_INSERT_NEW_KEY_HERE>",
    "YOUR_API_KEY",
    "YOUR_ELEVENLABS_API_KEY",
}
_LOAD_LOCK = threading.Lock()
_DOTENV_LOADED = False


def application_root() -> Path:
    """Return the directory that owns local, untracked runtime configuration."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def local_data_dir(*, environ: Mapping[str, str] | None = None) -> Path:
    """Return MORICE's machine-local data root.

    ``MORICE_LOCAL_DATA_DIR`` lets installations keep models, native runtimes,
    downloads, and temporary work away from the Windows system drive.
    """

    environment = environ if environ is not None else os.environ
    configured = str(environment.get("MORICE_LOCAL_DATA_DIR", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = str(environment.get("LOCALAPPDATA", "")).strip()
    if local_app_data:
        return (Path(local_app_data) / "MORICE").resolve()
    return (application_root() / ".morice").resolve()


def configure_process_temp_dir(
    *,
    environ: MutableMapping[str, str] | None = None,
) -> Path:
    """Route MORICE-owned temporary files through its local data root.

    Setting the process environment also covers child tools launched by
    project mode. The operating system's global TEMP/TMP settings are left
    untouched.
    """

    environment = environ if environ is not None else os.environ
    configured = str(environment.get("MORICE_TEMP_DIR", "")).strip()
    directory = (
        Path(configured).expanduser().resolve()
        if configured
        else local_data_dir(environ=environment) / "temp"
    )
    directory.mkdir(parents=True, exist_ok=True)
    normalized = str(directory)
    environment["MORICE_TEMP_DIR"] = normalized
    environment["TEMP"] = normalized
    environment["TMP"] = normalized
    environment["TMPDIR"] = normalized
    tempfile.tempdir = normalized
    return directory


def load_environment(*, root: str | os.PathLike[str] | None = None) -> Path:
    """Load MORICE's local .env once without replacing process-level settings."""

    global _DOTENV_LOADED
    dotenv_path = Path(root).resolve() / ".env" if root else application_root() / ".env"
    with _LOAD_LOCK:
        if not _DOTENV_LOADED:
            try:
                from dotenv import load_dotenv
            except ImportError:
                # Source checkouts without optional voice dependencies remain usable.
                pass
            else:
                load_dotenv(dotenv_path=dotenv_path, override=False)
            _DOTENV_LOADED = True
    return dotenv_path


def _clean(value: Any, limit: int = 500) -> str:
    return "".join(
        character
        for character in str(value or "").strip()
        if character not in "\r\n\t\x00"
    )[:limit]


def _boolean(value: Any, default: bool) -> bool:
    text = str(value or "").strip().casefold()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def _number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = default
    return max(minimum, min(maximum, amount))


@dataclass(frozen=True)
class TTSConfig:
    enabled: bool = True
    provider: str = "elevenlabs"
    voice_id: str = DEFAULT_ELEVENLABS_VOICE_ID
    model_id: str = DEFAULT_ELEVENLABS_MODEL_ID
    streaming: bool = True
    speech_speed: float = 1.0
    automatic_fallback: bool = True
    output_device: int | None = None
    output_format: str = DEFAULT_TTS_OUTPUT_FORMAT
    request_timeout_seconds: float = 20.0
    api_key: str = field(default="", repr=False, compare=False)

    @property
    def api_configured(self) -> bool:
        return self.api_key.strip() not in _API_KEY_PLACEHOLDERS

    @property
    def api_status(self) -> str:
        return (
            "ElevenLabs API: Configured"
            if self.api_configured
            else "ElevenLabs API: Not configured"
        )

    @property
    def sample_rate(self) -> int:
        try:
            return int(self.output_format.rsplit("_", maxsplit=1)[-1])
        except (TypeError, ValueError):
            return 24_000

    def public_dict(self) -> dict[str, Any]:
        """Return diagnostics safe for logs, UI, telemetry, and crash reports."""

        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "voiceId": self.voice_id,
            "modelId": self.model_id,
            "streaming": self.streaming,
            "speechSpeed": self.speech_speed,
            "automaticFallback": self.automatic_fallback,
            "outputDevice": self.output_device,
            "outputFormat": self.output_format,
            "requestTimeoutSeconds": self.request_timeout_seconds,
            "apiStatus": self.api_status,
        }


def load_tts_config(
    settings: Mapping[str, Any] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    root: str | os.PathLike[str] | None = None,
) -> TTSConfig:
    """Build TTS configuration without ever persisting or exposing an API key."""

    load_environment(root=root)
    values = settings or {}
    environment = environ if environ is not None else os.environ
    provider = _clean(values.get("tts_provider", "elevenlabs"), 40).casefold()
    if provider not in {"elevenlabs", "local"}:
        provider = "elevenlabs"
    voice_id = _clean(
        environment.get("ELEVENLABS_VOICE_ID")
        or values.get("tts_voice_id")
        or DEFAULT_ELEVENLABS_VOICE_ID,
        160,
    )
    model_id = _clean(
        environment.get("ELEVENLABS_MODEL_ID")
        or values.get("tts_model_id")
        or DEFAULT_ELEVENLABS_MODEL_ID,
        120,
    )
    output_format = _clean(
        environment.get("ELEVENLABS_OUTPUT_FORMAT")
        or values.get("tts_output_format")
        or DEFAULT_TTS_OUTPUT_FORMAT,
        40,
    )
    if not output_format.startswith("pcm_"):
        output_format = DEFAULT_TTS_OUTPUT_FORMAT
    output_device: int | None
    try:
        raw_device = str(values.get("tts_output_device", "")).strip()
        output_device = int(raw_device) if raw_device else None
    except (TypeError, ValueError):
        output_device = None
    return TTSConfig(
        enabled=_boolean(values.get("tts_enabled", "true"), True),
        provider=provider,
        voice_id=voice_id or DEFAULT_ELEVENLABS_VOICE_ID,
        model_id=model_id or DEFAULT_ELEVENLABS_MODEL_ID,
        streaming=_boolean(values.get("tts_streaming", "true"), True),
        speech_speed=_number(values.get("tts_speech_speed", 1.0), 1.0, 0.7, 1.2),
        automatic_fallback=_boolean(values.get("tts_automatic_fallback", "true"), True),
        output_device=output_device,
        output_format=output_format,
        request_timeout_seconds=_number(
            environment.get("ELEVENLABS_TIMEOUT_SECONDS", 20.0),
            20.0,
            3.0,
            120.0,
        ),
        api_key=_clean(environment.get("ELEVENLABS_API_KEY", ""), 1_000),
    )
