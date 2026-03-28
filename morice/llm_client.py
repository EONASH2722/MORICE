import json
import os
import urllib.error
import urllib.request

from .core import SYSTEM_PROMPT
from .local_llama import chat as local_chat
from .llama_server import ensure_server

DEFAULT_MODEL = os.getenv("MORICE_MODEL", "").strip()
DEFAULT_BASE_URL = os.getenv("MORICE_OLLAMA_URL", "http://localhost:11434")
DEFAULT_GGUF = os.getenv("MORICE_GGUF_PATH", "").strip()
DEFAULT_CTX = int(os.getenv("MORICE_CTX", "4096"))
DEFAULT_GPU_LAYERS = int(os.getenv("MORICE_GPU_LAYERS", "0"))
DEFAULT_CHAT_FORMAT = os.getenv("MORICE_CHAT_FORMAT", "").strip() or None
DEFAULT_THREADS = int(os.getenv("MORICE_THREADS", str(max(1, (os.cpu_count() or 4) - 2))))
DEFAULT_BATCH = int(os.getenv("MORICE_BATCH", "64"))
DEFAULT_USE_SERVER = os.getenv("MORICE_LLAMA_SERVER", "0") == "1"


def _post_json(url, payload, timeout):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_prompt(messages):
    lines = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        lines.append(f"{role.upper()}: {content}")
    lines.append("ASSISTANT:")
    return "\n".join(lines)


def _try_chat_endpoint(base_url, payload, timeout):
    chat_url = f"{base_url.rstrip('/')}/api/chat"
    data = _post_json(chat_url, payload, timeout)
    content = data.get("message", {}).get("content", "").strip()
    return content or "(No response)"


def _try_generate_endpoint(base_url, messages, model, timeout):
    generate_url = f"{base_url.rstrip('/')}/api/generate"
    prompt_payload = {
        "model": model,
        "prompt": _build_prompt(messages),
        "stream": False,
    }
    data = _post_json(generate_url, prompt_payload, timeout)
    content = data.get("response", "").strip()
    return content or "(No response)"


def _try_openai_chat(base_url, payload, timeout):
    openai_url = f"{base_url.rstrip('/')}/v1/chat/completions"
    data = _post_json(openai_url, payload, timeout)
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    return content or "(No response)"


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
            "algorithm",
        }
    )


def _resolve_gguf_path():
    if DEFAULT_GGUF and os.path.exists(DEFAULT_GGUF):
        return DEFAULT_GGUF
    return ""


def chat(
    history,
    user_message,
    extra_system=None,
    model=DEFAULT_MODEL,
    base_url=DEFAULT_BASE_URL,
    timeout=120,
    precision_mode: bool = False,
    math_steps_mode: bool = False,
):
    temperature = 0.2 if _needs_precision(user_message) else 0.7
    top_p = 0.9 if _needs_precision(user_message) else 0.95
    if precision_mode:
        temperature = 0.1
        top_p = 0.85
    gguf_path = _resolve_gguf_path()
    if gguf_path:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        system_additions = []
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

        if DEFAULT_USE_SERVER:
            payload = {
                "model": "local-gguf",
                "messages": messages,
                "stream": False,
                "temperature": temperature,
                "top_p": top_p,
            }
            try:
                base_url = ensure_server(
                    gguf_path,
                    DEFAULT_CTX,
                    DEFAULT_GPU_LAYERS,
                    DEFAULT_THREADS,
                    DEFAULT_BATCH,
                )
                return _try_openai_chat(base_url, payload, timeout)
            except Exception as exc:  # noqa: BLE001
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
    system_additions = []
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

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "top_p": top_p},
    }

    try:
        return _try_chat_endpoint(base_url, payload, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 500:
            return (
                "(MORICE) Ollama returned 500. Make sure it is running and the model exists. "
                f"Try: ollama run {model}"
            )
        if exc.code not in {404, 405}:
            return f"(MORICE) Model error: {exc}"
    except urllib.error.URLError as exc:
        return (
            f"(MORICE) Could not reach the local model at {base_url}. "
            f"Details: {exc}"
        )

    try:
        return _try_generate_endpoint(base_url, messages, model, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 500:
            return (
                "(MORICE) Ollama returned 500. Make sure it is running and the model exists. "
                f"Try: ollama run {model}"
            )
        if exc.code not in {404, 405}:
            return f"(MORICE) Model error: {exc}"
    except urllib.error.URLError as exc:
        return (
            f"(MORICE) Could not reach the local model at {base_url}. "
            f"Details: {exc}"
        )

    try:
        return _try_openai_chat(base_url, payload, timeout)
    except urllib.error.URLError as exc:
        return (
            f"(MORICE) Could not reach the local model at {base_url}. "
            f"Details: {exc}"
        )
