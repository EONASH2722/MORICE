import json
import os


DEFAULT_SETTINGS = {
    "response_style": "",
    "wake_phrase": "wake up son",
    "user_title": "All Father",
    "emoji_level": "medium",
    "maturity_level": "none",
    "font_family": "Segoe UI",
    "custom_font_path": "",
    "chat_mode": "normal",
    "project_folder": "",
    "project_access": "folder",
    "project_lookup_mode": "online",
    "model_path": "",
    "model_name": "",
    "gpu_name": "",
    "gpu_vram_mb": "",
    "animation_speed": "normal",
    "reduced_motion": "false",
    "high_contrast": "false",
    "large_text": "false",
    "ui_scale": "1.0",
    "transparency": "92",
    "workspace_preset": "balanced",
    "settings_profile": "Default",
    "default_music_provider": "Amazon Music",
    "tts_enabled": "true",
    "tts_provider": "elevenlabs",
    "tts_voice_id": "oTWkNN1jSpFLkYHKcSXU",
    "tts_model_id": "eleven_flash_v2_5",
    "tts_streaming": "true",
    "tts_speech_speed": "1.0",
    "tts_automatic_fallback": "true",
    "tts_output_device": "",
    "tts_output_format": "pcm_24000",
    "stt_enabled": "true",
    "stt_auto_send": "true",
    "stt_input_device": "",
    "stt_max_listen_seconds": "30",
    "vision_processing_enabled": "true",
    "vision_hf_repository": "ggml-org/SmolVLM2-500M-Video-Instruct-GGUF:Q8_0",
    "vision_model_path": "",
    "vision_mmproj_path": "",
    "camera_device_id": "",
    "camera_resolution": "1280x720",
    "camera_fps": "30",
    "camera_mirror": "true",
    "continuous_visual_awareness": "false",
}


def normalize_response_style(value: str) -> str:
    text = (value or "").strip()
    return text[:1200]


def normalize_wake_phrase(value: str) -> str:
    text = " ".join((value or "").strip().split())
    return text[:80] or DEFAULT_SETTINGS["wake_phrase"]


def normalize_user_title(value: str) -> str:
    text = " ".join((value or "").strip().split())
    text = "".join(ch for ch in text if ch not in "\r\n\t")
    return text[:42] or DEFAULT_SETTINGS["user_title"]


def normalize_emoji_level(value: str) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "off": "none",
        "no": "none",
        "minimal": "none",
        "balanced": "medium",
        "normal": "medium",
        "well": "expressive",
        "many": "expressive",
        "high": "expressive",
    }
    text = aliases.get(text, text)
    return text if text in {"none", "medium", "expressive"} else DEFAULT_SETTINGS["emoji_level"]


def normalize_maturity_level(value: str) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "off": "none",
        "no": "none",
        "clean": "none",
        "balanced": "medium",
        "moderate": "medium",
        "normal": "medium",
        "high": "full",
        "mature": "full",
        "unrestricted": "full",
    }
    text = aliases.get(text, text)
    return (
        text
        if text in {"none", "medium", "full"}
        else DEFAULT_SETTINGS["maturity_level"]
    )


def normalize_font_family(value: str) -> str:
    text = " ".join(str(value or "").strip().split())
    text = "".join(
        ch for ch in text if ch not in "\r\n\t\x00{};\"'"
    ).strip()
    return text[:100] or DEFAULT_SETTINGS["font_family"]


def normalize_custom_font_path(value: str) -> str:
    text = str(value or "").strip().strip('"')
    if not text:
        return DEFAULT_SETTINGS["custom_font_path"]
    text = "".join(ch for ch in text if ch not in "\r\n\t\x00")
    path = os.path.abspath(os.path.expanduser(text))
    if os.path.splitext(path)[1].lower() not in {".ttf", ".otf", ".ttc"}:
        return DEFAULT_SETTINGS["custom_font_path"]
    return path[:500]


def normalize_chat_mode(value: str) -> str:
    text = (value or "").strip().lower()
    return text if text in {"normal", "project", "voice"} else DEFAULT_SETTINGS["chat_mode"]


def normalize_project_folder(value: str) -> str:
    text = (value or "").strip().strip('"')
    if not text:
        return DEFAULT_SETTINGS["project_folder"]
    text = "".join(ch for ch in text if ch not in "\r\n\t")
    return os.path.abspath(os.path.expanduser(text))[:500]


def normalize_project_access(value: str) -> str:
    text = (value or "").strip().lower()
    return text if text in {"folder", "full"} else DEFAULT_SETTINGS["project_access"]


def normalize_project_lookup_mode(value: str) -> str:
    text = (value or "").strip().lower().replace("_", "-")
    aliases = {"online": "online", "online+local": "online", "local+online": "online", "local": "local"}
    return aliases.get(text, DEFAULT_SETTINGS["project_lookup_mode"])


def normalize_model_path(value: str) -> str:
    text = (value or "").strip().strip('"')
    if not text:
        return DEFAULT_SETTINGS["model_path"]
    text = "".join(ch for ch in text if ch not in "\r\n\t")
    return os.path.abspath(os.path.expanduser(text))[:500]


def normalize_model_name(value: str) -> str:
    text = (value or "").strip()
    text = "".join(ch for ch in text if ch not in "\r\n\t")
    return text[:160]


def normalize_gpu_name(value: str) -> str:
    text = " ".join((value or "").strip().split())
    text = "".join(ch for ch in text if ch not in "\r\n\t")
    return text[:160]


def normalize_gpu_vram_mb(value: str) -> str:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return DEFAULT_SETTINGS["gpu_vram_mb"]
    try:
        amount = int(float(text))
    except ValueError:
        return DEFAULT_SETTINGS["gpu_vram_mb"]
    if amount <= 0:
        return DEFAULT_SETTINGS["gpu_vram_mb"]
    return str(min(amount, 1024 * 1024))


def normalize_animation_speed(value: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"slow", "normal", "fast"} else DEFAULT_SETTINGS["animation_speed"]


def normalize_boolean_setting(value: str, *, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def normalize_ui_scale(value: str) -> float:
    try:
        amount = float(str(value or "").strip())
    except ValueError:
        amount = float(DEFAULT_SETTINGS["ui_scale"])
    return max(0.8, min(1.6, amount))


def normalize_transparency(value: str) -> int:
    try:
        amount = int(float(str(value or "").strip()))
    except ValueError:
        amount = int(DEFAULT_SETTINGS["transparency"])
    return max(70, min(100, amount))


def normalize_workspace_preset(value: str) -> str:
    text = str(value or "").strip().lower()
    return (
        text
        if text in {"balanced", "focus", "science", "project", "research"}
        else DEFAULT_SETTINGS["workspace_preset"]
    )


def normalize_settings_profile(value: str) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())
    text = "".join(ch for ch in text if ch not in '\r\n\t{}[]"\'')
    return text[:60] or DEFAULT_SETTINGS["settings_profile"]


def normalize_music_provider(value: str) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    text = "".join(ch for ch in text if ch not in '\r\n\t{}[]"\'')
    return text[:120] or DEFAULT_SETTINGS["default_music_provider"]


def normalize_tts_provider(value: str) -> str:
    text = str(value or "").strip().casefold()
    return text if text in {"elevenlabs", "local"} else DEFAULT_SETTINGS["tts_provider"]


def normalize_tts_voice_id(value: str) -> str:
    text = "".join(
        character
        for character in str(value or "").strip()
        if character not in "\r\n\t\x00"
    )
    return text[:160] or DEFAULT_SETTINGS["tts_voice_id"]


def normalize_tts_model_id(value: str) -> str:
    text = "".join(
        character
        for character in str(value or "").strip()
        if character not in "\r\n\t\x00"
    )
    return text[:120] or DEFAULT_SETTINGS["tts_model_id"]


def normalize_tts_speed(value: str) -> float:
    try:
        amount = float(str(value or "").strip())
    except ValueError:
        amount = float(DEFAULT_SETTINGS["tts_speech_speed"])
    return max(0.7, min(1.2, amount))


def normalize_tts_output_device(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(max(0, int(text)))
    except ValueError:
        return ""


def normalize_tts_output_format(value: str) -> str:
    text = str(value or "").strip().casefold()
    return text if text in {"pcm_16000", "pcm_22050", "pcm_24000", "pcm_44100"} else DEFAULT_SETTINGS["tts_output_format"]


def normalize_stt_input_device(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(max(0, int(text)))
    except ValueError:
        clean = "".join(ch for ch in text if ch not in "\r\n\t\x00")
        return clean[:160]


def normalize_stt_max_listen_seconds(value: str) -> float:
    try:
        amount = float(str(value or "").strip())
    except ValueError:
        amount = float(DEFAULT_SETTINGS["stt_max_listen_seconds"])
    return max(5.0, min(120.0, amount))


def normalize_vision_hf_repository(value: str) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    text = "".join(ch for ch in text if ch not in "\r\n\t\"'")
    return text[:300]


def normalize_vision_path(value: str) -> str:
    text = str(value or "").strip().strip('"')
    if not text:
        return ""
    text = "".join(ch for ch in text if ch not in "\r\n\t\x00")
    return os.path.abspath(os.path.expanduser(text))[:500]


def normalize_camera_device_id(value: str) -> str:
    text = "".join(
        ch for ch in str(value or "").strip() if ch not in "\r\n\t\x00"
    )
    return text[:500]


def normalize_camera_resolution(value: str) -> str:
    text = str(value or "").strip().lower().replace(" ", "")
    try:
        width_text, height_text = text.split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["camera_resolution"]
    if not (320 <= width <= 7680 and 240 <= height <= 4320):
        return DEFAULT_SETTINGS["camera_resolution"]
    return f"{width}x{height}"


def normalize_camera_fps(value: str) -> int:
    try:
        amount = int(round(float(str(value or "").strip())))
    except ValueError:
        amount = int(DEFAULT_SETTINGS["camera_fps"])
    return max(5, min(120, amount))


def _settings_dir() -> str:
    base = os.getenv("APPDATA", "").strip()
    if base:
        return os.path.join(base, "MORICE")
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".morice"))


def settings_path() -> str:
    return os.path.join(_settings_dir(), "settings.json")


def wake_signal_path() -> str:
    return os.path.join(_settings_dir(), "wake.signal")


def load_settings() -> dict:
    path = settings_path()
    if not os.path.exists(path):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return dict(DEFAULT_SETTINGS)

    settings = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        for key in settings:
            if isinstance(data.get(key), str):
                settings[key] = data[key]
    settings["response_style"] = normalize_response_style(settings.get("response_style", ""))
    settings["wake_phrase"] = normalize_wake_phrase(settings.get("wake_phrase", ""))
    settings["user_title"] = normalize_user_title(settings.get("user_title", ""))
    settings["emoji_level"] = normalize_emoji_level(settings.get("emoji_level", ""))
    settings["maturity_level"] = normalize_maturity_level(
        settings.get("maturity_level", "")
    )
    settings["font_family"] = normalize_font_family(settings.get("font_family", ""))
    settings["custom_font_path"] = normalize_custom_font_path(
        settings.get("custom_font_path", "")
    )
    settings["chat_mode"] = normalize_chat_mode(settings.get("chat_mode", ""))
    settings["project_folder"] = normalize_project_folder(settings.get("project_folder", ""))
    settings["project_access"] = normalize_project_access(settings.get("project_access", ""))
    settings["project_lookup_mode"] = normalize_project_lookup_mode(settings.get("project_lookup_mode", ""))
    settings["model_path"] = normalize_model_path(settings.get("model_path", ""))
    settings["model_name"] = normalize_model_name(settings.get("model_name", ""))
    settings["gpu_name"] = normalize_gpu_name(settings.get("gpu_name", ""))
    settings["gpu_vram_mb"] = normalize_gpu_vram_mb(settings.get("gpu_vram_mb", ""))
    settings["animation_speed"] = normalize_animation_speed(
        settings.get("animation_speed", "")
    )
    settings["reduced_motion"] = str(
        normalize_boolean_setting(settings.get("reduced_motion", ""))
    ).lower()
    settings["high_contrast"] = str(
        normalize_boolean_setting(settings.get("high_contrast", ""))
    ).lower()
    settings["large_text"] = str(
        normalize_boolean_setting(settings.get("large_text", ""))
    ).lower()
    settings["ui_scale"] = str(normalize_ui_scale(settings.get("ui_scale", "")))
    settings["transparency"] = str(
        normalize_transparency(settings.get("transparency", ""))
    )
    settings["workspace_preset"] = normalize_workspace_preset(
        settings.get("workspace_preset", "")
    )
    settings["settings_profile"] = normalize_settings_profile(
        settings.get("settings_profile", "")
    )
    settings["default_music_provider"] = normalize_music_provider(
        settings.get("default_music_provider", "")
    )
    settings["tts_enabled"] = str(
        normalize_boolean_setting(settings.get("tts_enabled", ""), default=True)
    ).lower()
    settings["tts_provider"] = normalize_tts_provider(settings.get("tts_provider", ""))
    settings["tts_voice_id"] = normalize_tts_voice_id(settings.get("tts_voice_id", ""))
    settings["tts_model_id"] = normalize_tts_model_id(settings.get("tts_model_id", ""))
    settings["tts_streaming"] = str(
        normalize_boolean_setting(settings.get("tts_streaming", ""), default=True)
    ).lower()
    settings["tts_speech_speed"] = str(
        normalize_tts_speed(settings.get("tts_speech_speed", ""))
    )
    settings["tts_automatic_fallback"] = str(
        normalize_boolean_setting(
            settings.get("tts_automatic_fallback", ""), default=True
        )
    ).lower()
    settings["tts_output_device"] = normalize_tts_output_device(
        settings.get("tts_output_device", "")
    )
    settings["tts_output_format"] = normalize_tts_output_format(
        settings.get("tts_output_format", "")
    )
    settings["stt_enabled"] = str(
        normalize_boolean_setting(settings.get("stt_enabled", ""), default=True)
    ).lower()
    settings["stt_auto_send"] = str(
        normalize_boolean_setting(settings.get("stt_auto_send", ""), default=True)
    ).lower()
    settings["stt_input_device"] = normalize_stt_input_device(
        settings.get("stt_input_device", "")
    )
    settings["stt_max_listen_seconds"] = str(
        normalize_stt_max_listen_seconds(
            settings.get("stt_max_listen_seconds", "")
        )
    )
    settings["vision_processing_enabled"] = str(
        normalize_boolean_setting(
            settings.get("vision_processing_enabled", ""), default=True
        )
    ).lower()
    settings["vision_hf_repository"] = normalize_vision_hf_repository(
        settings.get("vision_hf_repository", "")
    )
    settings["vision_model_path"] = normalize_vision_path(
        settings.get("vision_model_path", "")
    )
    settings["vision_mmproj_path"] = normalize_vision_path(
        settings.get("vision_mmproj_path", "")
    )
    settings["camera_device_id"] = normalize_camera_device_id(
        settings.get("camera_device_id", "")
    )
    settings["camera_resolution"] = normalize_camera_resolution(
        settings.get("camera_resolution", "")
    )
    settings["camera_fps"] = str(normalize_camera_fps(settings.get("camera_fps", "")))
    settings["camera_mirror"] = str(
        normalize_boolean_setting(settings.get("camera_mirror", ""), default=True)
    ).lower()
    settings["continuous_visual_awareness"] = str(
        normalize_boolean_setting(settings.get("continuous_visual_awareness", ""))
    ).lower()
    return settings


def save_settings(settings: dict) -> None:
    os.makedirs(_settings_dir(), exist_ok=True)
    clean = dict(DEFAULT_SETTINGS)
    clean["response_style"] = normalize_response_style(settings.get("response_style", ""))
    clean["wake_phrase"] = normalize_wake_phrase(settings.get("wake_phrase", ""))
    clean["user_title"] = normalize_user_title(settings.get("user_title", ""))
    clean["emoji_level"] = normalize_emoji_level(settings.get("emoji_level", ""))
    clean["maturity_level"] = normalize_maturity_level(
        settings.get("maturity_level", "")
    )
    clean["font_family"] = normalize_font_family(settings.get("font_family", ""))
    clean["custom_font_path"] = normalize_custom_font_path(
        settings.get("custom_font_path", "")
    )
    clean["chat_mode"] = normalize_chat_mode(settings.get("chat_mode", ""))
    clean["project_folder"] = normalize_project_folder(settings.get("project_folder", ""))
    clean["project_access"] = normalize_project_access(settings.get("project_access", ""))
    clean["project_lookup_mode"] = normalize_project_lookup_mode(settings.get("project_lookup_mode", ""))
    clean["model_path"] = normalize_model_path(settings.get("model_path", ""))
    clean["model_name"] = normalize_model_name(settings.get("model_name", ""))
    clean["gpu_name"] = normalize_gpu_name(settings.get("gpu_name", ""))
    clean["gpu_vram_mb"] = normalize_gpu_vram_mb(settings.get("gpu_vram_mb", ""))
    clean["animation_speed"] = normalize_animation_speed(
        settings.get("animation_speed", "")
    )
    clean["reduced_motion"] = str(
        normalize_boolean_setting(settings.get("reduced_motion", ""))
    ).lower()
    clean["high_contrast"] = str(
        normalize_boolean_setting(settings.get("high_contrast", ""))
    ).lower()
    clean["large_text"] = str(
        normalize_boolean_setting(settings.get("large_text", ""))
    ).lower()
    clean["ui_scale"] = str(normalize_ui_scale(settings.get("ui_scale", "")))
    clean["transparency"] = str(
        normalize_transparency(settings.get("transparency", ""))
    )
    clean["workspace_preset"] = normalize_workspace_preset(
        settings.get("workspace_preset", "")
    )
    clean["settings_profile"] = normalize_settings_profile(
        settings.get("settings_profile", "")
    )
    clean["default_music_provider"] = normalize_music_provider(
        settings.get("default_music_provider", "")
    )
    clean["tts_enabled"] = str(
        normalize_boolean_setting(settings.get("tts_enabled", ""), default=True)
    ).lower()
    clean["tts_provider"] = normalize_tts_provider(settings.get("tts_provider", ""))
    clean["tts_voice_id"] = normalize_tts_voice_id(settings.get("tts_voice_id", ""))
    clean["tts_model_id"] = normalize_tts_model_id(settings.get("tts_model_id", ""))
    clean["tts_streaming"] = str(
        normalize_boolean_setting(settings.get("tts_streaming", ""), default=True)
    ).lower()
    clean["tts_speech_speed"] = str(
        normalize_tts_speed(settings.get("tts_speech_speed", ""))
    )
    clean["tts_automatic_fallback"] = str(
        normalize_boolean_setting(
            settings.get("tts_automatic_fallback", ""), default=True
        )
    ).lower()
    clean["tts_output_device"] = normalize_tts_output_device(
        settings.get("tts_output_device", "")
    )
    clean["tts_output_format"] = normalize_tts_output_format(
        settings.get("tts_output_format", "")
    )
    clean["stt_enabled"] = str(
        normalize_boolean_setting(settings.get("stt_enabled", ""), default=True)
    ).lower()
    clean["stt_auto_send"] = str(
        normalize_boolean_setting(settings.get("stt_auto_send", ""), default=True)
    ).lower()
    clean["stt_input_device"] = normalize_stt_input_device(
        settings.get("stt_input_device", "")
    )
    clean["stt_max_listen_seconds"] = str(
        normalize_stt_max_listen_seconds(
            settings.get("stt_max_listen_seconds", "")
        )
    )
    clean["vision_processing_enabled"] = str(
        normalize_boolean_setting(
            settings.get("vision_processing_enabled", ""), default=True
        )
    ).lower()
    clean["vision_hf_repository"] = normalize_vision_hf_repository(
        settings.get("vision_hf_repository", "")
    )
    clean["vision_model_path"] = normalize_vision_path(
        settings.get("vision_model_path", "")
    )
    clean["vision_mmproj_path"] = normalize_vision_path(
        settings.get("vision_mmproj_path", "")
    )
    clean["camera_device_id"] = normalize_camera_device_id(
        settings.get("camera_device_id", "")
    )
    clean["camera_resolution"] = normalize_camera_resolution(
        settings.get("camera_resolution", "")
    )
    clean["camera_fps"] = str(normalize_camera_fps(settings.get("camera_fps", "")))
    clean["camera_mirror"] = str(
        normalize_boolean_setting(settings.get("camera_mirror", ""), default=True)
    ).lower()
    clean["continuous_visual_awareness"] = str(
        normalize_boolean_setting(settings.get("continuous_visual_awareness", ""))
    ).lower()
    with open(settings_path(), "w", encoding="utf-8") as handle:
        json.dump(clean, handle, indent=2)
