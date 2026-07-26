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
    return text if text in {"normal", "project"} else DEFAULT_SETTINGS["chat_mode"]


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
    with open(settings_path(), "w", encoding="utf-8") as handle:
        json.dump(clean, handle, indent=2)
