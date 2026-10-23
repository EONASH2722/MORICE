import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from functools import wraps
import inspect
import uuid
import threading

from .core import SYSTEM_PROMPT, current_datetime_summary, emotional_checkin_response, short_form_hints
from .local_llama import chat as local_chat
from .local_llama import stream_chat as local_stream_chat
from .llama_server import ensure_server
from .personalization import address_message, identity_instruction
from .composer_help import sampling_settings

DEFAULT_MODEL = os.getenv("MORICE_MODEL", "").strip()
DEFAULT_BASE_URL = os.getenv("MORICE_OLLAMA_URL", "http://localhost:11434")
DEFAULT_GGUF = os.getenv("MORICE_GGUF_PATH", "").strip()
DEFAULT_CTX = int(os.getenv("MORICE_CTX", "8192"))
DEFAULT_GPU_LAYERS = int(os.getenv("MORICE_GPU_LAYERS", "0"))
DEFAULT_CHAT_FORMAT = os.getenv("MORICE_CHAT_FORMAT", "").strip() or None
DEFAULT_THREADS = int(os.getenv("MORICE_THREADS", str(max(2, (os.cpu_count() or 4) // 2))))
DEFAULT_BATCH = int(os.getenv("MORICE_BATCH", "256"))
DEFAULT_USE_SERVER = os.getenv("MORICE_LLAMA_SERVER", "1") == "1"
DEFAULT_MAX_TOKENS = int(os.getenv("MORICE_MAX_TOKENS", "2048"))
_OLLAMA_PROCESS = None
DEFAULT_BUNDLED_GGUF = "Qwen2.5-Coder-7B-Instruct-abliterated-Q4_K_M.gguf"
OFFICIAL_QWEN_GGUF = "qwen2.5-coder-7b-instruct-q4_k_m.gguf"
_MODEL_GENERATION_LOCK = threading.Lock()
_MODEL_GENERATION_OWNER = None


@contextmanager
def _generation_slot(cancel_event=None, timeout=180):
    global _MODEL_GENERATION_OWNER
    if _MODEL_GENERATION_OWNER == threading.get_ident():
        # A suspended stream may be resumed/closed by this same thread. Waiting
        # for it here would prevent the caller from ever releasing that stream.
        raise RuntimeError('The active model is busy. Close its stream before starting another.')
    started=time.monotonic()
    while not _MODEL_GENERATION_LOCK.acquire(timeout=0.05):
        if cancel_event is not None and cancel_event.is_set():
            yield False
            return
        if time.monotonic()-started>max(1,float(timeout)):
            raise RuntimeError('The active model is busy. Retry after generation completes.')
    _MODEL_GENERATION_OWNER = threading.get_ident()
    try:
        yield not (cancel_event is not None and cancel_event.is_set())
    finally:
        _MODEL_GENERATION_OWNER = None
        _MODEL_GENERATION_LOCK.release()


def _report_telemetry(callback, event: str, **payload) -> None:
    if not callable(callback):
        return
    try:
        callback(
            str(event),
            {"atNs": time.perf_counter_ns(), **payload},
        )
    except Exception:
        # Instrumentation must never make a response fail.
        pass


@contextmanager
def _local_model_claim(path, *, execution_scope=True):
    from .runtime_services import peek_runtime_services
    runtime = peek_runtime_services()
    if not path or runtime is None:
        yield
        return
    resources = runtime.kernel.resources
    if resources.current_holds("LOCAL_MODEL"):
        yield  # The shared kernel already admitted this agent/model call.
        return
    if runtime.kernel._closed:
        raise RuntimeError("Local model runtime is shutting down.")
    entry = runtime.kernel.registry.lookup("agent.reason")
    claims = entry.descriptor.supported_resources
    owner = "local-chat-" + uuid.uuid4().hex
    if not resources.acquire(owner, claims):
        raise RuntimeError("Local model resources are busy; retry after active work finishes.")
    try:
        if execution_scope:
            with resources.execution_scope(owner):
                yield
        else:
            # A suspended generator must not leave a caller-thread ContextVar
            # set: a second independent stream could otherwise borrow its lease.
            yield
    finally:
        resources.release(owner)


def _shared_model_resources(function):
    signature = inspect.signature(function)
    def selected(args, kwargs):
        bound = signature.bind_partial(*args, **kwargs).arguments
        if function.__name__ in {"prewarm_local_model", "prime_local_chat_prefix"}:
            return bound.get("gguf_path", "")
        model = bound.get("model") or DEFAULT_MODEL
        return _resolve_gguf_path(bound.get("gguf_path") or "", model, bool(bound.get("model")))
    if function.__name__ == "stream_chat":
        @wraps(function)
        def streaming(*args, **kwargs):
            with _generation_slot(kwargs.get('cancel_event'),kwargs.get('timeout',180)) as admitted:
                if admitted:
                    with _local_model_claim(selected(args, kwargs), execution_scope=False):
                        yield from function(*args, **kwargs)
        return streaming
    @wraps(function)
    def complete(*args, **kwargs):
        with _generation_slot(timeout=kwargs.get('timeout',180)):
            with _local_model_claim(selected(args, kwargs)):
                return function(*args, **kwargs)
    return complete


def reset_model_runtime() -> None:
    from .runtime_services import peek_runtime_services
    runtime = peek_runtime_services()
    if runtime is not None and any(c.resource == "LOCAL_MODEL" for claims in runtime.kernel.resources.snapshot().values() for c in claims):
        raise RuntimeError("An active local model lease must finish before unloading.")
    with _generation_slot():
        _unload_owned_models()


def unload_idle_model_for_media(resources, owner) -> None:
    """Unload idle owned weights while the existing Kernel fences new models.

    This is not a permission bypass: the caller already holds actual exclusive
    GPU/LOCAL_MODEL claims and no active model call can hold a concurrent lease.
    The media adapter must measure VRAM again before loading its own model.
    """
    leases = resources.snapshot()
    owned = leases.get(owner, ())
    if (not resources.current_holds("LOCAL_MODEL") or not resources.current_holds("GPU")
            or any(not any(c.resource == key and c.node_id == "local" and c.exclusive for c in owned) for key in ("GPU", "LOCAL_MODEL"))
            or any(c.resource == "LOCAL_MODEL" and c.node_id == "local" for key, claims in leases.items() if key != owner for c in claims)):
        raise RuntimeError("Idle model unload requires exclusive shared media admission.")
    _unload_owned_models()


def _unload_owned_models() -> None:
    global _OLLAMA_PROCESS
    try:
        from .llama_server import stop_server

        stop_server()
    except Exception:
        pass
    if _OLLAMA_PROCESS and _OLLAMA_PROCESS.poll() is None:
        _OLLAMA_PROCESS.terminate()
        try:
            _OLLAMA_PROCESS.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _OLLAMA_PROCESS.kill()
            _OLLAMA_PROCESS.wait(timeout=8)
    _OLLAMA_PROCESS = None
    try:
        from .local_llama import clear_cache

        clear_cache()
    except Exception:
        pass


@_shared_model_resources
def prewarm_local_model(gguf_path: str) -> str:
    """Load a selected GGUF into the local server without generating text."""

    selected = os.path.abspath(str(gguf_path or "").strip())
    if not selected or not os.path.isfile(selected):
        raise FileNotFoundError(selected or "No GGUF model was selected.")
    if os.path.splitext(selected)[1].casefold() != ".gguf":
        raise ValueError("Only GGUF models can be prewarmed.")
    if not DEFAULT_USE_SERVER:
        return selected
    return ensure_server(
        selected,
        DEFAULT_CTX,
        DEFAULT_GPU_LAYERS,
        DEFAULT_THREADS,
        DEFAULT_BATCH,
    )


@_shared_model_resources
def prime_local_chat_prefix(
    gguf_path: str,
    *,
    extra_system: str = "",
    timeout: float = 60.0,
) -> dict[str, object]:
    """Evaluate MORICE's stable chat prefix once so the first turn can reuse it."""

    selected = os.path.abspath(str(gguf_path or "").strip())
    if not selected or not os.path.isfile(selected):
        raise FileNotFoundError(selected or "No GGUF model was selected.")
    server_url = ensure_server(
        selected,
        DEFAULT_CTX,
        DEFAULT_GPU_LAYERS,
        DEFAULT_THREADS,
        DEFAULT_BATCH,
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    clean_extra = str(extra_system or "").strip()
    if clean_extra:
        messages.append({"role": "system", "content": clean_extra})
    messages.append(
        {
            "role": "user",
            "content": "Reply with only the word Ready.",
        }
    )
    payload = {
        "model": "local-gguf",
        "messages": messages,
        "stream": True,
        "temperature": 0.0,
        "top_p": 0.8,
        "max_tokens": 8,
        "reasoning_budget": 0,
        "chat_template_kwargs": {"enable_thinking": False},
        "stream_options": {"include_usage": True},
    }
    events: list[tuple[str, dict[str, object]]] = []
    output = "".join(
        _try_openai_chat_stream(
            server_url,
            payload,
            max(10.0, float(timeout)),
            telemetry=lambda event, metadata: events.append((event, metadata)),
        )
    )
    usage = next(
        (
            dict(metadata.get("usage") or {})
            for event, metadata in reversed(events)
            if event == "model_usage"
        ),
        {},
    )
    return {
        "ready": bool(output.strip()),
        "promptTokens": int(usage.get("prompt_tokens") or 0),
        "completionTokens": int(usage.get("completion_tokens") or 0),
    }


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


def _post_stream_json(url, payload, timeout, cancel_event=None, telemetry=None):
    """Yield SSE or newline-delimited JSON events from a local model backend."""

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "text/event-stream, application/x-ndjson, application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        _report_telemetry(
            telemetry,
            "model_response_connected",
            status=getattr(response, "status", None),
        )
        first_event = True
        for raw_line in response:
            if cancel_event is not None and cancel_event.is_set():
                break
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                if first_event:
                    first_event = False
                    _report_telemetry(telemetry, "backend_first_event")
                yield value


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
    input_token_budget = max(512, DEFAULT_CTX - DEFAULT_MAX_TOKENS - 768)
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
    system_budget=max(256,int(character_budget*.55))
    bounded=[]; remaining=system_budget
    for item in system_messages:
        if remaining<=0: break
        text=item['content'][:remaining]
        bounded.append({**item,'content':text});remaining-=len(text)
    system_messages=bounded
    fixed_size = sum(len(message["content"]) for message in system_messages + latest)

    if latest and fixed_size > character_budget:
        available = max(0, character_budget - sum(
            len(message["content"]) for message in system_messages
        ))
        content = latest[0]["content"]
        if len(content) > available:
            marker='\n[Prompt excerpt omitted to fit context.]\n'
            head = max(0, (available-len(marker)) // 2)
            tail = max(0, available-head-len(marker))
            latest[0] = {
                **latest[0],
                "content": (
                    content[:head]
                    + marker
                    + (content[-tail:] if tail else '')
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


def _fit_backend_context(base_url,messages,max_output_tokens,*,telemetry=None):
    """Use the installed model tokenizer when the byte upper bound is too large.

    Tiny prompts avoid extra HTTP calls. Older backends without these endpoints
    fall back to a conservative UTF-8 byte budget rather than an unbounded guess.
    """
    budget=max(256,DEFAULT_CTX-int(max_output_tokens)-128)
    clean=[dict(m) for m in messages]
    def byte_count():return sum(len(m['content'].encode('utf-8'))+32 for m in clean)+64
    if byte_count()<=budget:return clean
    exact=True
    for _ in range(16):
        if exact:
            try:
                prompt=_post_json(base_url.rstrip('/')+'/apply-template',{'messages':clean},2)['prompt']
                count=len(_post_json(base_url.rstrip('/')+'/tokenize',{'content':prompt,'add_special':True,'parse_special':True},2)['tokens'])
            except (OSError,ValueError,KeyError,TypeError):
                exact=False;count=byte_count()
        else: count=byte_count()
        if count<=budget:
            _report_telemetry(telemetry,'context_budget_checked',inputTokens=count,exact=exact,budgetTokens=budget)
            return clean
        history_index=next((i for i,m in enumerate(clean[:-1]) if m['role']!='system'),None)
        if history_index is not None:
            clean.pop(history_index);continue
        # Preserve the base system instructions and the current user request.
        index=max(range(1,len(clean)),key=lambda i:len(clean[i]['content'])) if len(clean)>1 else 0
        if index==0:raise ValueError('Base system instructions exceed the selected model context.')
        content=clean[index]['content']; target=max(32,int(len(content)*min(.75,budget/max(1,count)*.85)))
        if clean[index]['role']=='user':
            marker='\n[Context excerpt omitted.]\n';head=max(0,(target-len(marker))//2)
            clean[index]['content']=content[:head]+marker+content[-max(1,target-head-len(marker)):]
        else:clean[index]['content']=content[:target]
    raise ValueError('The request could not fit within the selected model context.')


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


def _try_openai_chat_stream(
    base_url,
    payload,
    timeout,
    cancel_event=None,
    telemetry=None,
):
    openai_url = f"{base_url.rstrip('/')}/v1/chat/completions"
    running_payload = dict(payload)
    running_payload["stream"] = True
    emitted = False
    useful_emitted = False
    for event in _post_stream_json(
        openai_url,
        running_payload,
        timeout,
        cancel_event,
        telemetry,
    ):
        if cancel_event is not None and cancel_event.is_set():
            break
        choice = (event.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        text = delta.get("content") or choice.get("text") or ""
        if text:
            if not useful_emitted and str(text).strip():
                useful_emitted = True
                _report_telemetry(telemetry, "model_first_useful_token")
            emitted = True
            yield str(text)
        usage = event.get("usage")
        timings = event.get("timings")
        if isinstance(usage, dict) or isinstance(timings, dict):
            _report_telemetry(
                telemetry,
                "model_usage",
                usage=usage if isinstance(usage, dict) else {},
                timings=timings if isinstance(timings, dict) else {},
            )
    _report_telemetry(telemetry, "model_stream_complete", emitted=emitted)
    if not emitted and not (cancel_event is not None and cancel_event.is_set()):
        yield "(No response)"


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
            address_message("My local model stumbled.") + fallback_hint + " "
            f"Fast fix: reopen Ollama or switch MORICE to a lighter model like deepseek-r1:1.5b. "
            f"Current model: {requested_model}."
        )
    return (
        address_message("My local model stumbled.") + " Fast fix: reopen Ollama or set MORICE_MODEL to a lighter local model like "
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


def _try_ollama_messages_stream(
    base_url,
    messages,
    model,
    timeout,
    temperature,
    top_p,
    cancel_event=None,
):
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": DEFAULT_MAX_TOKENS,
        },
    }
    emitted = False
    for event in _post_stream_json(
        f"{base_url.rstrip('/')}/api/chat",
        payload,
        timeout,
        cancel_event,
    ):
        if cancel_event is not None and cancel_event.is_set():
            break
        message = event.get("message") or {}
        text = message.get("content") or event.get("response") or ""
        if text:
            emitted = True
            yield str(text)
    if not emitted and not (cancel_event is not None and cancel_event.is_set()):
        yield "(No response)"


def _friendly_local_timeout_reply() -> str:
    return (
        address_message("The local model took too long on that one.") + " I kept MORICE alive. "
        "Try sending a shorter prompt, turning Precision off, or letting the queued message run next."
    )


def _runtime_context() -> str:
    return (
        f"Runtime context: {current_datetime_summary()} "
        "Use this for date, day, month, year, and time questions."
    )


def _needs_runtime_context(text: str) -> bool:
    lowered = str(text or "").casefold()
    return any(
        phrase in lowered
        for phrase in (
            "what time",
            "current time",
            "what date",
            "today's date",
            "todays date",
            "what day",
            "current date",
            "this month",
            "this year",
        )
    )


def _conversation_messages(
    history,
    user_message,
    *,
    extra_system=None,
    precision_mode: bool = False,
    math_steps_mode: bool = False,
):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    system_additions = [identity_instruction()]
    if _needs_runtime_context(user_message):
        system_additions.append(_runtime_context())
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
    return _fit_messages_to_context(messages)


@_shared_model_resources
def stream_chat(
    history,
    user_message,
    extra_system=None,
    model: str | None = None,
    base_url=DEFAULT_BASE_URL,
    timeout=120,
    precision_mode: bool = False,
    math_steps_mode: bool = False,
    gguf_path: str | None = None,
    *,
    cancel_event=None,
    max_tokens: int | None = None,
    enable_reasoning: bool = False,
    telemetry=None,
):
    """Yield response text while a local GGUF or Ollama backend is generating."""

    explicit_model = bool((model or "").strip())
    model = (model or DEFAULT_MODEL).strip()
    sampling = sampling_settings(precision_mode, _needs_precision(user_message))
    temperature, top_p = sampling.temperature, sampling.top_p
    selected_path = (gguf_path or "").strip()
    if selected_path and os.path.splitext(selected_path)[1].lower() != ".gguf":
        yield "(MORICE) Selected model file is not a GGUF model."
        return
    resolved_path = _resolve_gguf_path(selected_path, model, explicit_model)
    if selected_path and not resolved_path:
        yield "(MORICE) Selected model file was not found. Use Change model and pick the file again."
        return
    messages = _conversation_messages(
        history,
        user_message,
        extra_system=extra_system,
        precision_mode=precision_mode,
        math_steps_mode=math_steps_mode,
    )
    prompt_characters = sum(
        len(str(message.get("content") or "")) for message in messages
    )
    _report_telemetry(
        telemetry,
        "prompt_assembled",
        messages=len(messages),
        characters=prompt_characters,
        estimatedTokens=max(1, (prompt_characters + 3) // 4),
        historyMessages=len(history or ()),
    )
    if resolved_path:
        if DEFAULT_USE_SERVER:
            payload = {
                "model": "local-gguf",
                "messages": messages,
                "stream": True,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max(
                    32,
                    min(
                        DEFAULT_MAX_TOKENS,
                        int(max_tokens or DEFAULT_MAX_TOKENS),
                    ),
                ),
                # llama.cpp/Qwen can otherwise spend several seconds emitting
                # hidden reasoning_content before the first visible token.
                # Deep/project requests opt back in through the tier router.
                "reasoning_budget": -1 if enable_reasoning else 0,
                "chat_template_kwargs": {
                    "enable_thinking": bool(enable_reasoning),
                },
                "stream_options": {"include_usage": True},
            }
            try:
                prepare_started = time.perf_counter_ns()
                _report_telemetry(telemetry, "model_prepare_started")
                server_url = ensure_server(
                    resolved_path,
                    DEFAULT_CTX,
                    DEFAULT_GPU_LAYERS,
                    DEFAULT_THREADS,
                    DEFAULT_BATCH,
                )
                payload['messages']=_fit_backend_context(server_url,payload['messages'],payload['max_tokens'],telemetry=telemetry)
                _report_telemetry(
                    telemetry,
                    "model_ready",
                    prepareMs=(time.perf_counter_ns() - prepare_started) / 1_000_000.0,
                )
                _report_telemetry(telemetry, "model_request_submitted")
                if telemetry is None:
                    yield from _try_openai_chat_stream(
                        server_url,
                        payload,
                        timeout,
                        cancel_event,
                    )
                else:
                    yield from _try_openai_chat_stream(
                        server_url,
                        payload,
                        timeout,
                        cancel_event,
                        telemetry=telemetry,
                    )
            except Exception as exc:  # noqa: BLE001
                _report_telemetry(
                    telemetry,
                    "model_error",
                    errorType=type(exc).__name__,
                )
                if cancel_event is not None and cancel_event.is_set():
                    return
                yield (
                    _friendly_local_timeout_reply()
                    if _is_timeout_error(exc)
                    else f"(MORICE) Local server error: {exc}"
                )
            return
        try:
            yield from local_stream_chat(
                messages,
                resolved_path,
                DEFAULT_CTX,
                DEFAULT_GPU_LAYERS,
                DEFAULT_CHAT_FORMAT,
                DEFAULT_THREADS,
                DEFAULT_BATCH,
                temperature,
                top_p,
                cancel_event=cancel_event,
            )
        except Exception as exc:  # noqa: BLE001
            if cancel_event is None or not cancel_event.is_set():
                yield f"(MORICE) Local model error: {exc}"
        return
    if not model:
        yield "(MORICE) MORICE_MODEL is not set. Set it or configure MORICE_GGUF_PATH for offline mode."
        return
    _ensure_ollama(base_url)
    fallback_models = _fallback_models(model, base_url, user_message)
    for candidate in (model, *fallback_models):
        if cancel_event is not None and cancel_event.is_set():
            return
        try:
            yield from _try_ollama_messages_stream(
                base_url,
                messages,
                candidate,
                timeout,
                temperature,
                top_p,
                cancel_event,
            )
            return
        except urllib.error.HTTPError as exc:
            if exc.code not in {404, 405, 500}:
                yield f"(MORICE) Model error: HTTP {exc.code}"
                return
        except urllib.error.URLError as exc:
            if not _is_timeout_error(exc):
                break
        except Exception:
            continue
    if cancel_event is None or not cancel_event.is_set():
        yield _friendly_backend_reply(
            user_message,
            model,
            fallback_models[0] if fallback_models else "",
        )


@_shared_model_resources
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
    enable_reasoning: bool = False,
):
    explicit_model = bool((model or "").strip())
    model = (model or DEFAULT_MODEL).strip()
    sampling = sampling_settings(precision_mode, _needs_precision(user_message))
    temperature, top_p = sampling.temperature, sampling.top_p
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
        system_additions = [_runtime_context(), identity_instruction()]
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
                "reasoning_budget": -1 if enable_reasoning else 0,
                "chat_template_kwargs": {
                    "enable_thinking": bool(enable_reasoning),
                },
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
                    # Repeating the same oversized local generation used to turn
                    # one timeout into a 420-second wait.  The server keeps its
                    # prompt cache, so the next user request can retry explicitly.
                    if _is_timeout_error(exc):
                        return _friendly_local_timeout_reply()
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
    system_additions = [_runtime_context(), identity_instruction()]
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
