import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

from .core import SYSTEM_PROMPT, current_datetime_summary, emotional_checkin_response, short_form_hints
from .local_llama import chat as local_chat
from .llama_server import ensure_server

DEFAULT_MODEL = os.getenv("MORICE_MODEL", "").strip()
DEFAULT_BASE_URL = os.getenv("MORICE_OLLAMA_URL", "http://localhost:11434")
DEFAULT_GGUF = os.getenv("MORICE_GGUF_PATH", "").strip()
DEFAULT_CTX = int(os.getenv("MORICE_CTX", "16384"))
DEFAULT_GPU_LAYERS = int(os.getenv("MORICE_GPU_LAYERS", "0"))
DEFAULT_CHAT_FORMAT = os.getenv("MORICE_CHAT_FORMAT", "").strip() or None
DEFAULT_THREADS = int(os.getenv("MORICE_THREADS", str(max(1, (os.cpu_count() or 4) - 2))))
DEFAULT_BATCH = int(os.getenv("MORICE_BATCH", "64"))
DEFAULT_USE_SERVER = os.getenv("MORICE_LLAMA_SERVER", "1") == "1"
DEFAULT_MAX_TOKENS = int(os.getenv("MORICE_MAX_TOKENS", "6144"))
_OLLAMA_PROCESS = None
DEFAULT_BUNDLED_GGUF = "Qwen2.5-Coder-7B-Instruct-abliterated-Q4_K_M.gguf"
OFFICIAL_QWEN_GGUF = "qwen2.5-coder-7b-instruct-q4_k_m.gguf"


def reset_model_runtime() -> None:
    try:
        from .llama_server import stop_server

        stop_server()
    except Exception:
        pass
    try:
        from .local_llama import clear_cache

        clear_cache()
    except Exception:
        pass


def _asset_path(*parts: str) -> str:
    return os.path.join(os.path.dirname(__file__), "assets", *parts)


def _project_path(*parts: str) -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", *parts))


def _is_stale_llama_model(model_name: str) -> bool:
    lowered = model_name.lower()
    return any(marker in lowered for marker in ("llama3", "llama-3", "meta-llama"))


def _post_json(url, payload, timeout):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url, timeout):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _ollama_exe() -> str:
    explicit = os.getenv("MORICE_OLLAMA_EXE", "").strip()
    if explicit and os.path.exists(explicit):
        return explicit
    discovered = shutil.which("ollama")
    if discovered:
        return discovered
    local_appdata = os.getenv("LOCALAPPDATA", "")
    candidate = os.path.join(local_appdata, "Programs", "Ollama", "ollama.exe")
    if candidate and os.path.exists(candidate):
        return candidate
    return ""


def _is_ollama_ready(base_url: str) -> bool:
    try:
        _get_json(f"{base_url.rstrip('/')}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def _ensure_ollama(base_url: str) -> bool:
    global _OLLAMA_PROCESS

    if _is_ollama_ready(base_url):
        return True

    exe = _ollama_exe()
    if not exe:
        return False

    if not _OLLAMA_PROCESS or _OLLAMA_PROCESS.poll() is not None:
        _OLLAMA_PROCESS = subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    for _ in range(30):
        if _is_ollama_ready(base_url):
            return True
        time.sleep(0.5)
    return False


def _build_prompt(messages):
    lines = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        lines.append(f"{role.upper()}: {content}")
    lines.append("ASSISTANT:")
    return "\n".join(lines)


def _merge_continuation(existing: str, continuation: str) -> str:
    existing = (existing or "").rstrip()
    continuation = (continuation or "").lstrip()
    if not existing:
        return continuation
    if not continuation:
        return existing
    maximum = min(600, len(existing), len(continuation))
    overlap = 0
    for size in range(maximum, 7, -1):
        if existing[-size:] == continuation[:size]:
            overlap = size
            break
    separator = "" if existing.endswith(("\n", " ")) else "\n"
    return existing + separator + continuation[overlap:]


def _fit_messages_to_context(messages):
    """Keep current instructions and prompt while dropping only oldest history."""
    input_token_budget = max(4096, DEFAULT_CTX - DEFAULT_MAX_TOKENS - 768)
    character_budget = input_token_budget * 4
    clean = [
        {
            "role": str(message.get("role", "user")),
            "content": str(message.get("content", "")),
        }
        for message in messages
    ]
    if sum(len(message["content"]) for message in clean) <= character_budget:
        return clean

    system_messages = [message for message in clean if message["role"] == "system"]
    conversation = [message for message in clean if message["role"] != "system"]
    latest = conversation[-1:] if conversation else []
    fixed_size = sum(len(message["content"]) for message in system_messages + latest)

    if latest and fixed_size > character_budget:
        available = max(1600, character_budget - sum(
            len(message["content"]) for message in system_messages
        ))
        content = latest[0]["content"]
        if len(content) > available:
            head = max(800, available // 2)
            tail = max(800, available - head - 80)
            latest[0] = {
                **latest[0],
                "content": (
                    content[:head]
                    + "\n\n[Middle of exceptionally long prompt omitted to fit the selected model context.]\n\n"
                    + content[-tail:]
                ),
            }

    selected = []
    used = sum(len(message["content"]) for message in system_messages + latest)
    for message in reversed(conversation[:-1]):
        size = len(message["content"])
        if used + size > character_budget:
            continue
        selected.append(message)
        used += size
    selected.reverse()
    return system_messages + selected + latest


def _try_chat_endpoint(base_url, payload, timeout):
    chat_url = f"{base_url.rstrip('/')}/api/chat"
    running_payload = dict(payload)
    running_payload["messages"] = list(payload.get("messages", []))
    content = ""
    for continuation_index in range(3):
        data = _post_json(chat_url, running_payload, timeout)
        part = data.get("message", {}).get("content", "").strip()
        content = _merge_continuation(content, part)
        finish_reason = str(data.get("done_reason") or "").lower()
        if finish_reason not in {"length", "max_tokens"}:
            break
        running_payload["messages"] = [
            *running_payload["messages"],
            {"role": "assistant", "content": part},
            {
                "role": "user",
                "content": (
                    "Continue exactly where the response stopped. Do not repeat prior text. "
                    "Finish every remaining section."
                ),
            },
        ]
        if continuation_index == 2:
            break
    return content or "(No response)"


def _try_generate_endpoint(base_url, messages, model, timeout):
    generate_url = f"{base_url.rstrip('/')}/api/generate"
    prompt_payload = {
        "model": model,
        "prompt": _build_prompt(messages),
        "stream": False,
        "options": {"num_predict": DEFAULT_MAX_TOKENS},
    }
    content = ""
    for continuation_index in range(3):
        data = _post_json(generate_url, prompt_payload, timeout)
        part = data.get("response", "").strip()
        content = _merge_continuation(content, part)
        finish_reason = str(data.get("done_reason") or "").lower()
        if finish_reason not in {"length", "max_tokens"}:
            break
        prompt_payload["prompt"] = (
            prompt_payload["prompt"]
            + part
            + "\nUSER: Continue exactly where the response stopped without repeating it."
            + "\nASSISTANT:"
        )
        if continuation_index == 2:
            break
    return content or "(No response)"


def _try_openai_chat(base_url, payload, timeout):
    openai_url = f"{base_url.rstrip('/')}/v1/chat/completions"
    running_payload = dict(payload)
    running_payload["messages"] = list(payload.get("messages", []))
    content = ""
    for continuation_index in range(3):
        data = _post_json(openai_url, running_payload, timeout)
        choice = data.get("choices", [{}])[0]
        part = choice.get("message", {}).get("content", "").strip()
        content = _merge_continuation(content, part)
        finish_reason = str(choice.get("finish_reason") or "").lower()
        if finish_reason not in {"length", "max_tokens"}:
            break
        running_payload["messages"] = [
            *running_payload["messages"],
            {"role": "assistant", "content": part},
            {
                "role": "user",
                "content": (
                    "Continue exactly where the response stopped. Do not repeat prior text. "
                    "Finish every remaining section."
                ),
            },
        ]
        if continuation_index == 2:
            break
    return content or "(No response)"


def _list_ollama_models(base_url, timeout=8):
    _ensure_ollama(base_url)
    try:
        data = _get_json(f"{base_url.rstrip('/')}/api/tags", timeout)
    except Exception:
        return []

    names = []
    for item in data.get("models", []):
        name = (item.get("name") or item.get("model") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _needs_precision(text: str) -> bool:
    lowered = text.lower()
    return any(
        key in lowered
        for key in {
            "code",
            "script",
            "python",
            "c#",
            "csharp",
            "java",
            "javascript",
            "typescript",
            "html",
            "css",
            "sql",
            "math",
            "equation",
            "solve",
            "derive",
            "proof",
            "calculate",
            "physics",
            "chemistry",
            "science",
            "rocket",
            "quantum",
            "riddle",
            "puzzle",
            "logic",
            "algorithm",
        }
    )


def _resolve_gguf_path(override_path=None, requested_model: str = "", explicit_model: bool = False):
    override_path = (override_path or "").strip()
    if override_path:
        if not os.path.exists(override_path):
            return ""
        if os.path.splitext(override_path)[1].lower() != ".gguf":
            return ""
        return override_path
    if explicit_model and requested_model:
        return ""
    if DEFAULT_GGUF and os.path.exists(DEFAULT_GGUF):
        return DEFAULT_GGUF
    candidates = [
        _project_path(DEFAULT_BUNDLED_GGUF),
        _asset_path(DEFAULT_BUNDLED_GGUF),
        _project_path(OFFICIAL_QWEN_GGUF),
        _asset_path(OFFICIAL_QWEN_GGUF),
    ]
    if DEFAULT_MODEL and not _is_stale_llama_model(DEFAULT_MODEL):
        return ""
    for bundled in candidates:
        if os.path.exists(bundled):
            return bundled
    return ""


def _fallback_models(requested_model, base_url, user_message):
    available = _list_ollama_models(base_url)
    if not available:
        return []

    is_precision_task = _needs_precision(user_message)

    def score(name):
        lowered = name.lower()
        value = 100
        if "-cloud" in lowered:
            value += 1000
        if requested_model and lowered == requested_model.lower():
            value += 300
        if "deepseek-r1:1.5b" in lowered:
            value -= 55
        if "deepseek-coder" in lowered:
            value -= 45 if is_precision_task else 5
        if "120b" in lowered:
            value += 400
        return value

    ordered = []
    for name in sorted(available, key=score):
        if "-cloud" in name.lower():
            continue
        if requested_model and name.lower() == requested_model.lower():
            continue
        ordered.append(name)
    return ordered


def _friendly_backend_reply(user_message, requested_model, fallback_used):
    emotional = emotional_checkin_response(user_message)
    if emotional:
        return emotional

    fallback_hint = ""
    if fallback_used:
        fallback_hint = f" I also tried {fallback_used}."
    if requested_model:
        return (
            f"My local model stumbled, All Father.{fallback_hint} "
            f"Fast fix: reopen Ollama or switch MORICE to a lighter model like deepseek-r1:1.5b. "
            f"Current model: {requested_model}."
        )
    return (
        "My local model stumbled, All Father. Fast fix: reopen Ollama or set MORICE_MODEL to a lighter local model like "
        "deepseek-r1:1.5b."
    )


def _is_timeout_error(exc):
    reason = getattr(exc, "reason", None)
    return isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(reason, (TimeoutError, socket.timeout))


def _try_ollama_messages(base_url, messages, model, timeout, temperature, top_p):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": DEFAULT_MAX_TOKENS,
        },
    }

    last_error = None

    try:
        return _try_chat_endpoint(base_url, payload, timeout)
    except urllib.error.HTTPError as exc:
        last_error = exc
        if exc.code not in {404, 405, 500}:
            raise
    except urllib.error.URLError:
        raise

    try:
        return _try_generate_endpoint(base_url, messages, model, timeout)
    except urllib.error.HTTPError as exc:
        last_error = exc
        if exc.code not in {404, 405, 500}:
            raise
    except urllib.error.URLError:
        raise

    try:
        return _try_openai_chat(base_url, payload, timeout)
    except urllib.error.URLError:
        raise
    except Exception as exc:  # noqa: BLE001
        last_error = exc

    if last_error:
        raise last_error
    raise RuntimeError("No supported local model endpoint succeeded.")


def _friendly_local_timeout_reply() -> str:
    return (
        "Qwen took too long on that one, All Father. I kept MORICE alive. "
        "Try sending a shorter prompt, turning Precision off, or letting the queued message run next."
    )


def _runtime_context() -> str:
    return (
        f"Runtime context: {current_datetime_summary()} "
        "Use this for date, day, month, year, and time questions."
    )


def chat(
    history,
    user_message,
    extra_system=None,
    model: str | None = None,
    base_url=DEFAULT_BASE_URL,
    timeout=120,
    precision_mode: bool = False,
    math_steps_mode: bool = False,
    gguf_path: str | None = None,
):
    explicit_model = bool((model or "").strip())
    model = (model or DEFAULT_MODEL).strip()
    temperature = 0.2 if _needs_precision(user_message) else 0.5
    top_p = 0.9 if _needs_precision(user_message) else 0.9
    if precision_mode:
        temperature = 0.1
        top_p = 0.85
    selected_path = (gguf_path or "").strip()
    if selected_path and os.path.splitext(selected_path)[1].lower() != ".gguf":
        return (
            "(MORICE) Selected model file is not a GGUF model. "
            "This PC build can run GGUF files directly; choose a .gguf file or use Ollama for other formats."
        )
    gguf_path = _resolve_gguf_path(selected_path, model, explicit_model)
    if selected_path and not gguf_path:
        return "(MORICE) Selected model file was not found. Use Change model and pick the file again."
    if gguf_path:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        system_additions = [_runtime_context()]
        hints = short_form_hints(user_message)
        if hints:
            system_additions.append(hints)
        if extra_system:
            system_additions.append(extra_system)
        if precision_mode:
            system_additions.append("Precision mode is on: be exact and avoid guesses.")
        if math_steps_mode:
            system_additions.append("Math steps mode is on: show all steps clearly.")
        if system_additions:
            messages.append({"role": "system", "content": "\n\n".join(system_additions)})
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        messages = _fit_messages_to_context(messages)

        if DEFAULT_USE_SERVER:
            payload = {
                "model": "local-gguf",
                "messages": messages,
                "stream": False,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": DEFAULT_MAX_TOKENS,
            }
            try:
                base_url = ensure_server(
                    gguf_path,
                    DEFAULT_CTX,
                    DEFAULT_GPU_LAYERS,
                    DEFAULT_THREADS,
                    DEFAULT_BATCH,
                )
                try:
                    return _try_openai_chat(base_url, payload, timeout)
                except Exception as exc:  # noqa: BLE001
                    if _is_timeout_error(exc):
                        try:
                            return _try_openai_chat(base_url, payload, max(timeout, 240))
                        except Exception as retry_exc:  # noqa: BLE001
                            if _is_timeout_error(retry_exc):
                                return _friendly_local_timeout_reply()
                            return f"(MORICE) Local server retry error: {retry_exc}"
                    return f"(MORICE) Local server error: {exc}"
            except Exception as exc:  # noqa: BLE001
                if _is_timeout_error(exc):
                    return _friendly_local_timeout_reply()
                return f"(MORICE) Local server error: {exc}"

        try:
            return local_chat(
                messages,
                gguf_path,
                DEFAULT_CTX,
                DEFAULT_GPU_LAYERS,
                DEFAULT_CHAT_FORMAT,
                DEFAULT_THREADS,
                DEFAULT_BATCH,
                temperature,
                top_p,
            )
        except Exception as exc:  # noqa: BLE001
            return f"(MORICE) Local model error: {exc}"

    if not model:
        return "(MORICE) MORICE_MODEL is not set. Set it or configure MORICE_GGUF_PATH for offline mode."
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    system_additions = [_runtime_context()]
    hints = short_form_hints(user_message)
    if hints:
        system_additions.append(hints)
    if extra_system:
        system_additions.append(extra_system)
    if precision_mode:
        system_additions.append("Precision mode is on: be exact and avoid guesses.")
    if math_steps_mode:
        system_additions.append("Math steps mode is on: show all steps clearly.")
    if system_additions:
        messages.append({"role": "system", "content": "\n\n".join(system_additions)})

    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    messages = _fit_messages_to_context(messages)

    _ensure_ollama(base_url)
    fallback_models = _fallback_models(model, base_url, user_message)

    try:
        return _try_ollama_messages(base_url, messages, model, timeout, temperature, top_p)
    except urllib.error.HTTPError as exc:
        if exc.code not in {404, 405, 500}:
            return f"(MORICE) Model error: {exc}"
    except urllib.error.URLError as exc:
        if not _is_timeout_error(exc):
            fallback_used = fallback_models[0] if fallback_models else ""
            return _friendly_backend_reply(user_message, model, fallback_used)
    except Exception:
        pass

    for fallback_model in fallback_models:
        try:
            return _try_ollama_messages(base_url, messages, fallback_model, max(timeout, 180), temperature, top_p)
        except urllib.error.HTTPError as exc:
            if exc.code not in {404, 405, 500}:
                return f"(MORICE) Model error: {exc}"
        except urllib.error.URLError as exc:
            if _is_timeout_error(exc):
                continue
            break
        except Exception:
            continue

    fallback_used = fallback_models[0] if fallback_models else ""
    return _friendly_backend_reply(user_message, model, fallback_used)
