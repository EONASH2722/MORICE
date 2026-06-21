import json
import math
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass


KNOWN_MODEL_EXTENSIONS = {
    ".gguf",
    ".ggml",
    ".bin",
    ".safetensors",
    ".onnx",
    ".pt",
    ".pth",
    ".ckpt",
    ".model",
}

DIRECT_CHAT_EXTENSIONS = {".gguf"}
MIN_MODEL_BYTES = 1024 * 1024
USER_AGENT = "MORICE-model-browser/1.0"

OFFICIAL_OWNER_SITES = {
    "meta-llama": "https://www.llama.com/",
    "mistralai": "https://mistral.ai/",
    "google": "https://ai.google.dev/gemma",
    "deepseek-ai": "https://www.deepseek.com/",
    "qwen": "https://qwenlm.github.io/",
    "microsoft": "https://www.microsoft.com/en-us/research/project/phi-3-2/",
    "tiiuae": "https://www.tii.ae/",
    "01-ai": "https://www.01.ai/",
    "openbmb": "https://www.openbmb.cn/",
    "stabilityai": "https://stability.ai/",
}

TRUSTED_GGUF_OWNERS = {
    "bartowski",
    "lmstudio-community",
    "thebloke",
    "maziyarpanahi",
    "unsloth",
    "nousresearch",
    "teknium",
    "second-state",
}


@dataclass(frozen=True)
class ModelVerification:
    ok: bool
    direct_chat: bool
    kind: str
    message: str


@dataclass(frozen=True)
class GpuProfile:
    name: str
    vram_mb: int
    source: str
    detected: bool
    message: str


@dataclass(frozen=True)
class ModelCompatibility:
    level: str
    label: str
    color: str
    score: int
    required_vram_mb: int
    smoothness: str
    message: str


@dataclass(frozen=True)
class ModelWorth:
    label: str
    score: int
    color: str
    message: str


@dataclass(frozen=True)
class ModelRunPlan:
    label: str
    color: str
    message: str
    context_hint: str
    offload_hint: str


UNKNOWN_COMPATIBILITY = ModelCompatibility(
    "unknown",
    "Unknown",
    "#aeb4bf",
    0,
    0,
    "Detect GPU VRAM first.",
    "GPU VRAM is not detected yet, so MORICE cannot estimate smoothness for this model.",
)

UNKNOWN_RUN_PLAN = ModelRunPlan(
    "Detect GPU first",
    "#aeb4bf",
    "MORICE can verify the model file, but it needs detected VRAM before it can grade GPU smoothness.",
    "Use the default context until GPU fit is known.",
    "GPU offload recommendation is unavailable.",
)


def format_size(size: int | None) -> str:
    if not size or size <= 0:
        return "unknown size"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def _parse_vram_mb(value) -> int:
    if value is None:
        return 0
    if isinstance(value, bytes):
        if not value:
            return 0
        return int(int.from_bytes(value[:8], "little", signed=False) / (1024 * 1024))
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric <= 0:
            return 0
        if numeric > 1024 * 1024:
            return int(numeric / (1024 * 1024))
        return int(numeric)
    text = str(value).strip().lower().replace(",", "")
    if not text:
        return 0
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return 0
    amount = float(match.group(1))
    if "tb" in text:
        return int(amount * 1024 * 1024)
    if "gb" in text or "gib" in text:
        return int(amount * 1024)
    if "kb" in text:
        return int(amount / 1024)
    if "byte" in text or amount > 1024 * 1024:
        return int(amount / (1024 * 1024))
    return int(amount)


def gpu_profile_from_values(name: str = "", vram_mb: int | str = 0, source: str = "settings") -> GpuProfile:
    clean_name = " ".join((name or "").split())[:160]
    clean_vram = max(0, _parse_vram_mb(vram_mb))
    detected = bool(clean_name or clean_vram)
    if clean_name and clean_vram:
        message = f"{clean_name} with {format_size(clean_vram * 1024 * 1024)} VRAM."
    elif clean_name:
        message = f"{clean_name}; VRAM was not detected."
    elif clean_vram:
        message = f"Detected {format_size(clean_vram * 1024 * 1024)} VRAM."
    else:
        message = "GPU VRAM not detected."
    return GpuProfile(clean_name, clean_vram, source, detected, message)


def gpu_profile_summary(profile: GpuProfile | None) -> str:
    if not profile or not profile.detected:
        return "GPU not detected"
    name = profile.name or "Detected GPU"
    if profile.vram_mb > 0:
        return f"{name} - {format_size(profile.vram_mb * 1024 * 1024)} VRAM"
    return f"{name} - VRAM unknown"


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _profile_from_env() -> GpuProfile | None:
    name = os.getenv("MORICE_GPU_NAME", "").strip()
    vram = os.getenv("MORICE_GPU_VRAM_MB", "").strip() or os.getenv("MORICE_GPU_VRAM", "").strip()
    vram_gb = os.getenv("MORICE_VRAM_GB", "").strip()
    if not vram and vram_gb:
        vram = f"{vram_gb} GB"
    if not name and not vram:
        return None
    profile = gpu_profile_from_values(name or "GPU override", vram, "environment")
    return GpuProfile(profile.name, profile.vram_mb, profile.source, profile.detected, "Using GPU profile from environment.")


def _detect_nvidia_smi() -> GpuProfile | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        output = subprocess.check_output(
            [
                exe,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
            creationflags=_creationflags(),
        )
    except Exception:
        return None

    best_name = ""
    best_vram = 0
    for raw_line in output.splitlines():
        parts = [part.strip() for part in raw_line.split(",")]
        if len(parts) < 2:
            continue
        vram = _parse_vram_mb(parts[1])
        if vram > best_vram:
            best_name = parts[0]
            best_vram = vram
    if best_name or best_vram:
        profile = gpu_profile_from_values(best_name, best_vram, "nvidia-smi")
        return GpuProfile(profile.name, profile.vram_mb, profile.source, profile.detected, "Detected with nvidia-smi.")
    return None


def _clean_gpu_name(value) -> str:
    if isinstance(value, bytes):
        for encoding in ("utf-16le", "utf-8", "latin-1"):
            try:
                text = value.decode(encoding, errors="ignore")
                break
            except Exception:
                text = ""
    else:
        text = str(value or "")
    text = text.replace("\x00", " ")
    return " ".join(text.split())[:160]


def _skip_gpu_name(name: str) -> bool:
    lowered = name.lower()
    return any(
        marker in lowered
        for marker in {
            "basic display",
            "remote display",
            "virtual display",
            "parsec",
            "rdp",
        }
    )


def _detect_windows_registry() -> GpuProfile | None:
    if os.name != "nt":
        return None
    try:
        import winreg
    except Exception:
        return None

    best_name = ""
    best_vram = 0
    base_path = r"SYSTEM\CurrentControlSet\Control\Video"
    try:
        base_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path)
    except OSError:
        return None

    with base_key:
        index = 0
        while True:
            try:
                adapter_group = winreg.EnumKey(base_key, index)
            except OSError:
                break
            index += 1
            group_path = f"{base_path}\\{adapter_group}"
            try:
                group_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, group_path)
            except OSError:
                continue
            with group_key:
                sub_index = 0
                while True:
                    try:
                        adapter_key_name = winreg.EnumKey(group_key, sub_index)
                    except OSError:
                        break
                    sub_index += 1
                    if not adapter_key_name.isdigit():
                        continue
                    try:
                        adapter_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{group_path}\\{adapter_key_name}")
                    except OSError:
                        continue
                    with adapter_key:
                        try:
                            raw_name, _ = winreg.QueryValueEx(adapter_key, "HardwareInformation.AdapterString")
                        except OSError:
                            raw_name = ""
                        name = _clean_gpu_name(raw_name)
                        if not name or _skip_gpu_name(name):
                            continue
                        vram = 0
                        for value_name in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                            try:
                                raw_vram, _ = winreg.QueryValueEx(adapter_key, value_name)
                            except OSError:
                                continue
                            vram = max(vram, _parse_vram_mb(raw_vram))
                        if vram > best_vram:
                            best_name = name
                            best_vram = vram

    if best_name or best_vram:
        profile = gpu_profile_from_values(best_name, best_vram, "windows-registry")
        return GpuProfile(profile.name, profile.vram_mb, profile.source, profile.detected, "Detected from Windows GPU registry.")
    return None


def _detect_windows_cim() -> GpuProfile | None:
    if os.name != "nt":
        return None
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return None
    command = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"
    )
    try:
        output = subprocess.check_output(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=8,
            creationflags=_creationflags(),
        )
    except Exception:
        return None
    try:
        data = json.loads(output)
    except Exception:
        return None
    adapters = data if isinstance(data, list) else [data]
    best_name = ""
    best_vram = 0
    for adapter in adapters:
        if not isinstance(adapter, dict):
            continue
        name = _clean_gpu_name(adapter.get("Name", ""))
        if not name or _skip_gpu_name(name):
            continue
        vram = _parse_vram_mb(adapter.get("AdapterRAM"))
        if vram > best_vram:
            best_name = name
            best_vram = vram
    if best_name or best_vram:
        profile = gpu_profile_from_values(best_name, best_vram, "windows-cim")
        return GpuProfile(profile.name, profile.vram_mb, profile.source, profile.detected, "Detected from Windows hardware inventory.")
    return None


def detect_gpu_profile() -> GpuProfile:
    for detector in (_profile_from_env, _detect_nvidia_smi, _detect_windows_registry, _detect_windows_cim):
        profile = detector()
        if profile and profile.detected:
            return profile
    return GpuProfile("", 0, "", False, "GPU VRAM not detected. You can still use CPU/Ollama models.")


def _model_size_bytes_from_name(name: str) -> int:
    lowered = name.lower()
    param_match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*b(?![a-z])", lowered)
    if not param_match:
        return 0
    params_b = float(param_match.group(1))
    bytes_per_param = 0.68
    quant_match = re.search(r"\bq([2-8])(?:_[a-z0-9]+)?\b", lowered)
    if quant_match:
        bytes_per_param = {
            "2": 0.42,
            "3": 0.52,
            "4": 0.64,
            "5": 0.78,
            "6": 0.92,
            "8": 1.08,
        }.get(quant_match.group(1), bytes_per_param)
    elif "f16" in lowered or "bf16" in lowered:
        bytes_per_param = 2.05
    return int(params_b * 1_000_000_000 * bytes_per_param)


def estimate_model_vram_mb(result: dict) -> int:
    size = result.get("size") if isinstance(result, dict) else None
    try:
        size_bytes = int(size or 0)
    except (TypeError, ValueError):
        size_bytes = 0
    if size_bytes <= 0 and isinstance(result, dict):
        name = " ".join(str(result.get(key, "")) for key in ("title", "repo_id", "filename"))
        size_bytes = _model_size_bytes_from_name(name)
    if size_bytes <= 0:
        return 0
    model_mb = size_bytes / (1024 * 1024)
    return int(model_mb * 1.12 + 1024)


def model_compatibility(result: dict, profile: GpuProfile | None) -> ModelCompatibility:
    if not profile or profile.vram_mb <= 0:
        return UNKNOWN_COMPATIBILITY
    required = estimate_model_vram_mb(result)
    if required <= 0:
        return ModelCompatibility(
            "unknown",
            "Unknown",
            "#aeb4bf",
            0,
            0,
            "Model size is unknown.",
            f"{gpu_profile_summary(profile)} detected, but MORICE could not estimate this model's VRAM need.",
        )

    ratio = profile.vram_mb / required
    if ratio >= 1.60:
        level, label, color, score, smooth = "excellent", "Excellent", "#0c7a43", 96, "Should feel very smooth with room for context and multitasking."
    elif ratio >= 1.22:
        level, label, color, score, smooth = "good", "Good", "#35c46f", 82, "Should run smoothly with sensible GPU offload."
    elif ratio >= 0.86:
        level, label, color, score, smooth = "usable", "Usable", "#ffd166", 60, "Should run, but expect slower replies or a smaller context if VRAM is busy."
    elif ratio >= 0.52:
        level, label, color, score, smooth = "cpu-assisted", "CPU assisted", "#ff9f6e", 38, "Can still work through CPU or partial offload, but it will not feel fast."
    else:
        level, label, color, score, smooth = "very-low", "Too heavy", "#ff6767", 16, "Likely too heavy for this GPU. Pick a smaller quant or a smaller model."

    message = (
        f"{label} GPU fit. Estimated comfortable need: {format_size(required * 1024 * 1024)} VRAM; "
        f"detected: {format_size(profile.vram_mb * 1024 * 1024)} on {profile.name or 'your GPU'}. "
        f"{smooth}"
    )
    return ModelCompatibility(level, label, color, score, required, smooth, message)


def model_run_plan(result: dict, profile: GpuProfile | None) -> ModelRunPlan:
    compatibility = model_compatibility(result, profile)
    if compatibility.score <= 0:
        return UNKNOWN_RUN_PLAN

    if compatibility.level == "excellent":
        return ModelRunPlan(
            "Recommended",
            compatibility.color,
            "Best experience for this PC. MORICE can use the model directly and should stay responsive.",
            "Default 4096 context is safe; advanced users can try higher context.",
            "GPU offload should be comfortable if llama GPU layers are enabled.",
        )
    if compatibility.level == "good":
        return ModelRunPlan(
            "Balanced",
            compatibility.color,
            "Strong fit. This is a good daily-driver choice for chat and project work.",
            "Default 4096 context is recommended.",
            "Use moderate GPU offload; close heavy GPU apps for smoother replies.",
        )
    if compatibility.level == "usable":
        return ModelRunPlan(
            "Usable",
            compatibility.color,
            "This should work, but speed depends on free VRAM and CPU fallback.",
            "Keep context around 2048-4096 if replies feel slow.",
            "Use low or partial GPU offload; reduce GPU layers if loading fails.",
        )
    if compatibility.level == "cpu-assisted":
        return ModelRunPlan(
            "CPU assisted",
            compatibility.color,
            "MORICE can try it, but it is better as a quality test than a fast default model.",
            "Use a smaller context, around 2048.",
            "Expect CPU-heavy replies or very low GPU offload.",
        )
    return ModelRunPlan(
        "Not recommended",
        compatibility.color,
        "This model is likely too large for the detected GPU. Choose a smaller model or lower quant.",
        "Keep context low if you install anyway.",
        "GPU offload is likely to fail or provide little benefit.",
    )


def _log_score(value, high: int, weight: int) -> int:
    try:
        amount = max(0, int(value or 0))
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return 0
    return min(weight, int((math.log10(amount + 1) / math.log10(high + 1)) * weight))


def model_worth(result: dict, compatibility: ModelCompatibility | None = None) -> ModelWorth:
    trust_rank = int((result or {}).get("source_rank") or 0)
    trust_score = min(28, max(8, int(trust_rank / 8))) if trust_rank else 8
    download_score = _log_score((result or {}).get("downloads"), 500_000, 22)
    like_score = _log_score((result or {}).get("likes"), 8_000, 12)
    file_score = max(0, min(14, int((result or {}).get("file_score") or 0) // 10))
    query_score = max(0, min(10, int((result or {}).get("query_score") or 0) // 12))
    fit_score = 0
    if compatibility and compatibility.score:
        fit_score = min(14, max(0, int(compatibility.score * 0.14)))

    score = max(1, min(100, trust_score + download_score + like_score + file_score + query_score + fit_score))
    if score >= 84:
        label, color = "Excellent value", "#0c7a43"
    elif score >= 68:
        label, color = "Strong pick", "#42d77d"
    elif score >= 50:
        label, color = "Worth a look", "#ffd166"
    elif score >= 34:
        label, color = "Niche pick", "#ff9f6e"
    else:
        label, color = "Low evidence", "#ff6767"

    source_label = (result or {}).get("source_label") or "trusted model source"
    size_text = (result or {}).get("size_text") or format_size((result or {}).get("size"))
    fit_text = compatibility.label if compatibility else "Unknown"
    message = (
        f"{label}. Worth score {score}/100 based on source trust, downloads, likes, quant/file match, "
        f"search match, and GPU fit. Source: {source_label}; size: {size_text}; GPU fit: {fit_text}."
    )
    return ModelWorth(label, score, color, message)


def local_model_result(path: str) -> dict:
    filename = os.path.basename(path or "model.gguf")
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    result = {
        "repo_id": "local",
        "filename": filename,
        "title": f"Local model / {filename}",
        "family": _model_family(filename, filename, {}),
        "size": size,
        "size_text": format_size(size),
        "downloads": 0,
        "likes": 0,
        "pipeline_tag": "text-generation",
        "license": "Local file license",
        "tags_text": "local, gguf",
        "source_label": "Local verified GGUF file",
        "source_rank": 150,
        "query_score": 0,
        "file_score": _score_file(filename),
        "official_url": "",
        "detail_url": path,
        "download_url": "",
    }
    result["speciality"] = model_speciality(result)
    return result


def default_model_download_dir() -> str:
    base = os.getenv("LOCALAPPDATA", "").strip()
    if base:
        return os.path.join(base, "MORICE", "models")
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".morice", "models"))


def _read_prefix(path: str, size: int = 4096) -> bytes:
    with open(path, "rb") as handle:
        return handle.read(size)


def _looks_like_safetensors(path: str, file_size: int) -> bool:
    if file_size < 16:
        return False
    try:
        prefix = _read_prefix(path, 8)
        header_len = int.from_bytes(prefix, "little")
        if header_len <= 0 or header_len > min(file_size - 8, 128 * 1024 * 1024):
            return False
        with open(path, "rb") as handle:
            handle.seek(8)
            header = handle.read(min(header_len, 1024 * 1024))
        data = json.loads(header.decode("utf-8"))
    except Exception:
        return False
    return isinstance(data, dict) and bool(data)


def verify_ai_model_file(path: str) -> ModelVerification:
    if not path or not os.path.isfile(path):
        return ModelVerification(False, False, "", "That file does not exist.")
    try:
        file_size = os.path.getsize(path)
    except OSError:
        return ModelVerification(False, False, "", "MORICE could not read that file.")
    if file_size < MIN_MODEL_BYTES:
        return ModelVerification(False, False, "", "That file is too small to be a real AI model.")

    ext = os.path.splitext(path)[1].lower()
    try:
        prefix = _read_prefix(path, 16)
    except OSError:
        return ModelVerification(False, False, "", "MORICE could not inspect that file.")

    if ext == ".gguf" or prefix.startswith(b"GGUF"):
        if not prefix.startswith(b"GGUF"):
            return ModelVerification(False, False, "GGUF", "That .gguf file is not a valid GGUF model.")
        return ModelVerification(True, True, "GGUF", "Verified GGUF model. MORICE can use it directly.")

    if ext == ".safetensors" and _looks_like_safetensors(path, file_size):
        return ModelVerification(
            True,
            False,
            "SafeTensors",
            "Verified SafeTensors model file. This PC build needs GGUF for direct chat.",
        )

    if ext in KNOWN_MODEL_EXTENSIONS:
        return ModelVerification(
            True,
            ext.lstrip(".").upper() in DIRECT_CHAT_EXTENSIONS,
            ext.lstrip(".").upper(),
            f"Looks like an AI model file ({ext}). This PC build needs GGUF for direct chat.",
        )

    name = os.path.basename(path).lower()
    modelish_name = any(word in name for word in ("model", "llama", "mistral", "qwen", "gemma", "phi", "hermes"))
    if modelish_name and file_size >= 64 * 1024 * 1024:
        return ModelVerification(
            True,
            False,
            "unknown",
            "This looks like a large AI model file, but MORICE cannot identify a direct-chat format.",
        )
    return ModelVerification(False, False, "", "MORICE could not verify that file as a usable AI model.")


def _get_json(url: str, timeout: int = 30):
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _quote_repo_file(filename: str) -> str:
    return "/".join(urllib.parse.quote(part) for part in filename.split("/"))


def _score_file(filename: str) -> int:
    lowered = filename.lower()
    score = 0
    for marker, value in (
        ("q4_k_m", 120),
        ("q5_k_m", 90),
        ("q4", 70),
        ("q5", 60),
        ("instruct", 25),
        ("chat", 20),
        ("8b", 16),
        ("7b", 14),
    ):
        if marker in lowered:
            score += value
    if "mmproj" in lowered or "vision" in lowered:
        score -= 100
    if _is_split_gguf(filename):
        score -= 500
    return score


def _is_split_gguf(filename: str) -> bool:
    return bool(re.search(r"-\d{5}-of-\d{5}\.gguf$", filename.lower()))


def _card_data(detail: dict) -> dict:
    data = detail.get("cardData")
    return data if isinstance(data, dict) else {}


def _list_text(value) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    return str(value or "")


def _model_text(detail: dict, repo_id: str, filename: str = "") -> str:
    card = _card_data(detail)
    fields = [
        repo_id,
        filename,
        detail.get("pipeline_tag", ""),
        _list_text(detail.get("tags", [])),
        _list_text(card.get("tags", [])),
        _list_text(card.get("language", [])),
        _list_text(card.get("base_model", "")),
        _list_text(card.get("library_name", "")),
    ]
    return " ".join(fields).lower()


def _model_family(repo_id: str, filename: str, detail: dict | None = None) -> str:
    text = f"{repo_id} {filename} {_list_text((_card_data(detail or {})).get('base_model', ''))}".lower()
    families = (
        ("DeepSeek", ("deepseek",)),
        ("Qwen", ("qwen",)),
        ("Llama", ("llama", "codellama")),
        ("Mistral", ("mistral", "mixtral", "codestral")),
        ("Gemma", ("gemma",)),
        ("Phi", ("phi-", "phi3", "phi4", "phi_")),
        ("Hermes", ("hermes",)),
        ("Nous", ("nous",)),
        ("Falcon", ("falcon",)),
        ("Yi", ("yi-", "01-ai")),
        ("StarCoder", ("starcoder",)),
        ("LLaVA", ("llava",)),
    )
    for family, markers in families:
        if any(marker in text for marker in markers):
            return family
    owner = repo_id.split("/", 1)[0] if "/" in repo_id else repo_id
    return owner or "Model"


def _official_url(repo_id: str, detail: dict) -> str:
    owner = repo_id.split("/", 1)[0].lower() if "/" in repo_id else repo_id.lower()
    if owner in OFFICIAL_OWNER_SITES:
        return OFFICIAL_OWNER_SITES[owner]
    text = _model_text(detail, repo_id)
    for marker, url in (
        ("deepseek", OFFICIAL_OWNER_SITES["deepseek-ai"]),
        ("qwen", OFFICIAL_OWNER_SITES["qwen"]),
        ("llama", OFFICIAL_OWNER_SITES["meta-llama"]),
        ("mistral", OFFICIAL_OWNER_SITES["mistralai"]),
        ("mixtral", OFFICIAL_OWNER_SITES["mistralai"]),
        ("codestral", OFFICIAL_OWNER_SITES["mistralai"]),
        ("gemma", OFFICIAL_OWNER_SITES["google"]),
        ("phi", OFFICIAL_OWNER_SITES["microsoft"]),
    ):
        if marker in text:
            return url
    return f"https://huggingface.co/{repo_id}"


def _trust_label(repo_id: str, detail: dict) -> tuple[str, int]:
    owner = repo_id.split("/", 1)[0].lower() if "/" in repo_id else repo_id.lower()
    if owner in OFFICIAL_OWNER_SITES:
        return "Official Hugging Face repo", 220
    if owner in TRUSTED_GGUF_OWNERS:
        return "Trusted GGUF build on Hugging Face", 180
    likes = int(detail.get("likes") or 0)
    downloads = int(detail.get("downloads") or 0)
    if downloads >= 10000 or likes >= 100:
        return "Popular Hugging Face model repo", 145
    return "Hugging Face model repo", 110


def _license_text(detail: dict) -> str:
    card = _card_data(detail)
    license_value = card.get("license") or detail.get("license") or ""
    if isinstance(license_value, list):
        license_value = ", ".join(str(item) for item in license_value)
    return str(license_value or "License not listed").strip()


def model_speciality(result: dict) -> str:
    text = " ".join(
        str(result.get(key, ""))
        for key in ("repo_id", "filename", "title", "pipeline_tag", "tags_text", "family")
    ).lower()
    points: list[str] = []
    if any(marker in text for marker in ("coder", "code", "codestral", "starcoder", "programming")):
        points.append("coding, debugging, and project edits")
    if any(marker in text for marker in ("reason", "r1", "math", "logic")):
        points.append("reasoning, math, and careful problem solving")
    if any(marker in text for marker in ("instruct", "chat", "assistant", "hermes", "nous")):
        points.append("chat and instruction following")
    if any(marker in text for marker in ("vision", "llava", "vl", "multimodal")):
        points.append("vision or multimodal workflows when the matching projector is available")
    if any(marker in text for marker in ("embedding", "embed")):
        points.append("embedding/search tasks rather than normal chat")
    if any(marker in text for marker in ("qwen", "aya", "bloom", "yi-")):
        points.append("multilingual prompts")
    if any(marker in text for marker in ("1b", "1.5b", "2b", "3b", "mini", "small")):
        points.append("fast lightweight local replies")
    if any(marker in text for marker in ("70b", "72b", "120b", "405b")):
        points.append("high-quality output on very strong hardware")
    if not points:
        family = result.get("family") or "This model"
        points.append(f"{family} style general local assistant work")
    deduped = []
    for point in points:
        if point not in deduped:
            deduped.append(point)
    return "Best for " + ", ".join(deduped[:3]) + "."


def _query_match_score(query: str, repo_id: str, filename: str) -> int:
    query_words = [word for word in re.split(r"[^a-z0-9.]+", query.lower()) if len(word) >= 2]
    haystack = f"{repo_id} {filename}".lower()
    score = 0
    if query.lower() in haystack:
        score += 120
    score += sum(16 for word in query_words if word in haystack)
    return score


def _result_sort_key(result: dict) -> tuple[int, int, int, int]:
    return (
        int(result.get("source_rank") or 0),
        int(result.get("query_score") or 0),
        int(result.get("downloads") or 0),
        int(result.get("file_score") or 0),
    )


def _result_from_file(detail: dict, repo_id: str, file_item: dict, query: str) -> dict:
    filename = file_item["filename"]
    source_label, source_rank = _trust_label(repo_id, detail)
    tags = detail.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    card = _card_data(detail)
    result = {
        "repo_id": repo_id,
        "filename": filename,
        "title": f"{repo_id} / {os.path.basename(filename)}",
        "family": _model_family(repo_id, filename, detail),
        "size": file_item.get("size"),
        "size_text": format_size(file_item.get("size")),
        "downloads": detail.get("downloads") or 0,
        "likes": detail.get("likes") or 0,
        "pipeline_tag": detail.get("pipeline_tag") or card.get("pipeline_tag") or "text-generation",
        "license": _license_text(detail),
        "tags_text": ", ".join(str(tag) for tag in tags[:8]),
        "source_label": source_label,
        "source_rank": source_rank,
        "query_score": _query_match_score(query, repo_id, filename),
        "file_score": file_item.get("score") or 0,
        "official_url": _official_url(repo_id, detail),
        "detail_url": f"https://huggingface.co/{repo_id}",
        "download_url": (
            f"https://huggingface.co/{repo_id}/resolve/main/{_quote_repo_file(filename)}?download=true"
        ),
    }
    result["speciality"] = model_speciality(result)
    return result


def _search_hf_models(search: str, limit: int = 12) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "search": search,
            "sort": "downloads",
            "direction": "-1",
            "limit": str(limit),
        }
    )
    return _get_json(f"https://huggingface.co/api/models?{params}", timeout=30)


def _model_detail(repo_id: str) -> dict:
    return _get_json(f"https://huggingface.co/api/models/{urllib.parse.quote(repo_id, safe='/')}", timeout=30)


def search_huggingface_gguf(query: str, limit: int = 18) -> list[dict]:
    clean_query = " ".join((query or "").split())
    if not clean_query:
        return []

    model_candidates: list[dict] = []
    seen_repos: set[str] = set()

    if "/" in clean_query and not clean_query.endswith("/"):
        try:
            detail = _model_detail(clean_query)
            repo_id = (detail.get("modelId") or detail.get("id") or clean_query).strip()
            if repo_id:
                model_candidates.append(detail)
                seen_repos.add(repo_id.lower())
        except Exception:
            pass

    for search in (clean_query, f"{clean_query} gguf", f"{clean_query} GGUF"):
        try:
            models = _search_hf_models(search, limit=12)
        except Exception:
            continue
        for model in models:
            repo_id = (model.get("modelId") or model.get("id") or "").strip()
            if not repo_id or "/" not in repo_id:
                continue
            key = repo_id.lower()
            if key in seen_repos:
                continue
            seen_repos.add(key)
            model_candidates.append(model)

    results: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for model in model_candidates[:28]:
        repo_id = (model.get("modelId") or model.get("id") or "").strip()
        if not repo_id or "/" not in repo_id:
            continue
        try:
            detail = model if model.get("siblings") else _model_detail(repo_id)
        except Exception:
            continue
        siblings = detail.get("siblings") or []
        gguf_files = []
        for sibling in siblings:
            filename = (sibling.get("rfilename") or "").strip()
            if filename.lower().endswith(".gguf") and not _is_split_gguf(filename):
                gguf_files.append(
                    {
                        "filename": filename,
                        "size": sibling.get("size"),
                        "score": _score_file(filename),
                    }
                )
        for item in sorted(gguf_files, key=lambda entry: entry["score"], reverse=True)[:3]:
            key = (repo_id, item["filename"])
            if key in seen:
                continue
            seen.add(key)
            result = _result_from_file(detail, repo_id, item, clean_query)
            if not result["downloads"]:
                result["downloads"] = model.get("downloads") or 0
            results.append(result)

    results = sorted(results, key=_result_sort_key, reverse=True)
    return results[:limit]


def safe_download_name(repo_id: str, filename: str) -> str:
    base = f"{repo_id.replace('/', '__')}__{os.path.basename(filename)}"
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:180] or "morice-model.gguf"


def download_model_result(result: dict, target_dir: str, progress=None) -> str:
    os.makedirs(target_dir, exist_ok=True)
    url = result.get("download_url", "")
    repo_id = result.get("repo_id", "model")
    filename = result.get("filename", "model.gguf")
    if not url:
        raise ValueError("Selected model result does not include a download URL.")
    target_path = os.path.join(target_dir, safe_download_name(repo_id, filename))
    part_path = target_path + ".part"

    if os.path.exists(target_path):
        verification = verify_ai_model_file(target_path)
        if verification.ok and verification.direct_chat:
            if progress:
                progress(100, "Already installed and verified.")
            return target_path

    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            with open(part_path, "wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        percent = int((downloaded / total) * 100) if total else 0
                        progress(percent, f"Downloaded {format_size(downloaded)} / {format_size(total)}")

        os.replace(part_path, target_path)
    except Exception:
        try:
            os.remove(part_path)
        except OSError:
            pass
        raise

    verification = verify_ai_model_file(target_path)
    if not verification.ok or not verification.direct_chat:
        try:
            os.remove(target_path)
        except OSError:
            pass
        raise ValueError(verification.message)
    if progress:
        progress(100, "Installed and verified.")
    return target_path
