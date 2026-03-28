import os
import subprocess
import time
import urllib.request


_SERVER_PROCESS = None


def _server_base_url() -> str:
    host = os.getenv("MORICE_LLAMA_SERVER_HOST", "127.0.0.1")
    port = os.getenv("MORICE_LLAMA_SERVER_PORT", "8080")
    return f"http://{host}:{port}"


def _server_path() -> str:
    explicit = os.getenv("MORICE_LLAMA_SERVER_PATH", "").strip()
    if explicit and os.path.exists(explicit):
        return explicit
    root = os.path.dirname(__file__)
    candidates = [
        os.path.join(root, "assets", "llama-bin", "llama-server.exe"),
        os.path.join(root, "assets", "llama-server.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def _is_server_ready(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/v1/models", timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def ensure_server(model_path: str, n_ctx: int, n_gpu_layers: int, n_threads: int, n_batch: int) -> str:
    global _SERVER_PROCESS

    base_url = _server_base_url()
    if _is_server_ready(base_url):
        return base_url

    server_exe = _server_path()
    if not server_exe:
        raise RuntimeError("llama-server.exe not found")

    if _SERVER_PROCESS and _SERVER_PROCESS.poll() is None:
        return base_url

    args = [
        server_exe,
        "--model",
        model_path,
        "--host",
        os.getenv("MORICE_LLAMA_SERVER_HOST", "127.0.0.1"),
        "--port",
        os.getenv("MORICE_LLAMA_SERVER_PORT", "8080"),
        "--ctx-size",
        str(n_ctx),
        "--threads",
        str(n_threads),
        "--batch-size",
        str(n_batch),
    ]
    if n_gpu_layers > 0:
        args.extend(["--n-gpu-layers", str(n_gpu_layers)])

    _SERVER_PROCESS = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    for _ in range(60):
        if _is_server_ready(base_url):
            return base_url
        time.sleep(0.5)

    raise RuntimeError("llama-server failed to start")
