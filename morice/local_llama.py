import os


def _is_oom_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in {
            "out of memory",
            "cuda",
            "cublas",
            "gpu",
            "allocation",
            "cuda malloc",
        }
    )


_LLM_CACHE = {}


def _get_llm(
    model_path: str,
    n_ctx: int,
    n_gpu_layers: int,
    chat_format: str | None,
    n_threads: int,
    n_batch: int,
):
    try:
        from llama_cpp import Llama
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("llama-cpp-python is not installed") from exc

    key = (model_path, n_ctx, n_gpu_layers, chat_format, n_threads, n_batch)
    if key in _LLM_CACHE:
        return _LLM_CACHE[key]

    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            n_batch=n_batch,
            chat_format=chat_format or None,
        )
    except Exception as exc:  # noqa: BLE001
        allow_fallback = os.getenv("MORICE_GPU_FALLBACK", "1") == "1"
        if allow_fallback and n_gpu_layers > 0 and _is_oom_error(exc):
            fallback_key = (model_path, n_ctx, 0, chat_format, n_threads, n_batch)
            if fallback_key in _LLM_CACHE:
                return _LLM_CACHE[fallback_key]
            llm = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_gpu_layers=0,
                n_threads=n_threads,
                n_batch=n_batch,
                chat_format=chat_format or None,
            )
            _LLM_CACHE[fallback_key] = llm
            return llm
        raise

    _LLM_CACHE[key] = llm
    return llm


def chat(
    messages,
    model_path: str,
    n_ctx: int,
    n_gpu_layers: int,
    chat_format: str | None,
    n_threads: int,
    n_batch: int,
    temperature: float,
    top_p: float,
):
    llm = _get_llm(model_path, n_ctx, n_gpu_layers, chat_format, n_threads, n_batch)
    result = llm.create_chat_completion(
        messages=messages,
        temperature=temperature,
        top_p=top_p,
    )
    return result["choices"][0]["message"]["content"].strip()
