from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from .config import local_data_dir


_SERVER_PROCESS: subprocess.Popen[bytes] | None = None
_SERVER_CONFIG: tuple[object, ...] | None = None
_SERVER_LOCK = threading.RLock()


def _server_base_url() -> str:
    host = os.getenv("MORICE_LLAMA_SERVER_HOST", "127.0.0.1")
    port = os.getenv("MORICE_LLAMA_SERVER_PORT", "8080")
    return f"http://{host}:{port}"


def _local_cuda_server() -> Path | None:
    """Return MORICE's separately installed CUDA runtime when it is usable.

    The CUDA archive is deliberately kept outside the repository and frozen app.
    That prevents hundreds of megabytes of machine-specific DLLs from being
    committed or bundled while still allowing a source checkout to use the GPU.
    """

    if os.getenv("MORICE_PREFER_CUDA_LLAMA", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return None
    if shutil.which("nvidia-smi") is None:
        return None
    candidate = local_data_dir() / "llama-cuda" / "llama-server.exe"
    return candidate if candidate.is_file() else None


def _server_path() -> str:
    explicit = os.getenv("MORICE_LLAMA_SERVER_PATH", "").strip()
    if explicit and os.path.isfile(explicit):
        return os.path.abspath(explicit)

    cuda_server = _local_cuda_server()
    if cuda_server is not None:
        return str(cuda_server)

    package_root = Path(__file__).resolve().parent
    repo_root = package_root.parent
    candidates = (
        package_root / "assets" / "llama-bin" / "llama-server.exe",
        package_root / "assets" / "llama-server.exe",
        repo_root / "third_party" / "llama-win-cpu" / "llama-server.exe",
    )
    for path in candidates:
        if path.is_file():
            return str(path)
    return ""


def selected_server_path() -> str:
    """Expose the selected executable for diagnostics without starting it."""

    return _server_path()


def _is_server_ready(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/v1/models", timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def stop_server() -> None:
    global _SERVER_PROCESS, _SERVER_CONFIG
    with _SERVER_LOCK:
        process = _SERVER_PROCESS
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=8)
        _SERVER_PROCESS = None
        _SERVER_CONFIG = None


def _gpu_layers(value: int) -> str:
    override = os.getenv("MORICE_GPU_LAYERS", "").strip().lower()
    if override in {"auto", "all"}:
        return override
    if override:
        try:
            return str(max(0, int(override)))
        except ValueError:
            pass
    if int(value) > 0:
        return str(int(value))
    # Modern llama.cpp safely resolves this to zero on a CPU-only backend.
    return "auto"


def ensure_server(
    model_path: str,
    n_ctx: int,
    n_gpu_layers: int,
    n_threads: int,
    n_batch: int,
) -> str:
    global _SERVER_PROCESS, _SERVER_CONFIG

    base_url = _server_base_url()
    model_path = os.path.abspath(model_path)
    server_exe = _server_path()
    if not server_exe:
        raise RuntimeError("llama-server.exe not found")

    layers = _gpu_layers(n_gpu_layers)
    ubatch = max(32, min(int(n_batch), int(os.getenv("MORICE_UBATCH_SIZE", "128"))))
    batch_threads = max(
        1,
        int(os.getenv("MORICE_BATCH_THREADS", str(max(int(n_threads), 8)))),
    )
    config: tuple[object, ...] = (
        model_path,
        server_exe,
        base_url,
        int(n_ctx),
        layers,
        int(n_threads),
        int(n_batch),
        ubatch,
        batch_threads,
    )

    with _SERVER_LOCK:
        if (
            _SERVER_PROCESS is not None
            and _SERVER_PROCESS.poll() is None
            and _SERVER_CONFIG == config
            and _is_server_ready(base_url)
        ):
            return base_url

        if _SERVER_PROCESS is not None and _SERVER_PROCESS.poll() is None:
            stop_server()

        # A server managed by the user may already own the configured endpoint.
        # Reuse it only when explicitly requested; otherwise fail transparently.
        if _is_server_ready(base_url):
            if os.getenv("MORICE_REUSE_LLAMA_SERVER", "0") == "1":
                return base_url
            raise RuntimeError(
                f"A different llama server is already listening at {base_url}"
            )

        args = [
            server_exe,
            "--model",
            model_path,
            "--host",
            os.getenv("MORICE_LLAMA_SERVER_HOST", "127.0.0.1"),
            "--port",
            os.getenv("MORICE_LLAMA_SERVER_PORT", "8080"),
            "--ctx-size",
            str(max(4096, int(n_ctx))),
            "--threads",
            str(max(1, int(n_threads))),
            "--threads-batch",
            str(batch_threads),
            "--batch-size",
            str(max(32, int(n_batch))),
            "--ubatch-size",
            str(ubatch),
            "--gpu-layers",
            layers,
            "--flash-attn",
            os.getenv("MORICE_FLASH_ATTN", "auto"),
            "--fit",
            "on",
            "--fit-target",
            os.getenv("MORICE_GPU_FIT_MARGIN_MB", "1024"),
            "--fit-ctx",
            os.getenv("MORICE_GPU_FIT_MIN_CTX", "4096"),
            "--parallel",
            "1",
            "--cache-prompt",
            "--cache-reuse",
            os.getenv("MORICE_CACHE_REUSE_TOKENS", "128"),
        ]

        draft_model = os.getenv("MORICE_SPECULATIVE_DRAFT_MODEL", "").strip()
        if draft_model and os.path.isfile(draft_model):
            args.extend(
                [
                    "--model-draft",
                    os.path.abspath(draft_model),
                    "--draft-max",
                    os.getenv("MORICE_SPECULATIVE_TOKENS", "8"),
                ]
            )

        _SERVER_PROCESS = subprocess.Popen(
            args,
            cwd=os.path.dirname(server_exe),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        _SERVER_CONFIG = config

    for _ in range(120):
        process = _SERVER_PROCESS
        if process is None or process.poll() is not None:
            stop_server()
            raise RuntimeError("llama-server exited before becoming ready")
        if _is_server_ready(base_url):
            return base_url
        time.sleep(0.25)

    stop_server()
    raise RuntimeError("llama-server failed to start")
