import json
import os


DEFAULT_SETTINGS = {
    "response_style": "",
    "wake_phrase": "wake up son",
    "user_title": "All Father",
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
    return settings


def save_settings(settings: dict) -> None:
    os.makedirs(_settings_dir(), exist_ok=True)
    clean = dict(DEFAULT_SETTINGS)
    clean["response_style"] = normalize_response_style(settings.get("response_style", ""))
    clean["wake_phrase"] = normalize_wake_phrase(settings.get("wake_phrase", ""))
    clean["user_title"] = normalize_user_title(settings.get("user_title", ""))
    with open(settings_path(), "w", encoding="utf-8") as handle:
        json.dump(clean, handle, indent=2)
