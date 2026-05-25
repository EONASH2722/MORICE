import os
import sys


def _asset_path(*parts: str) -> str:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "morice", "assets", *parts)


def _project_path(*parts: str) -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def _configure_local_model_defaults():
    configured_model = os.getenv("MORICE_MODEL", "").strip()
    configured_gguf = os.getenv("MORICE_GGUF_PATH", "").strip()
    if configured_gguf:
        return

    gguf_candidates = [
        _project_path("Hermes-3-Llama-3.1-8B.Q4_K_M.gguf"),
        _asset_path("Hermes-3-Llama-3.1-8B.Q4_K_M.gguf"),
    ]
    server_path = _asset_path("llama-bin", "llama-server.exe")

    gguf_path = next((path for path in gguf_candidates if os.path.exists(path)), "")
    stale_llama_model = any(
        marker in configured_model.lower()
        for marker in ("llama3", "llama-3", "meta-llama")
    )
    if configured_model and not stale_llama_model and not gguf_path:
        return
    if gguf_path:
        os.environ["MORICE_GGUF_PATH"] = gguf_path
        if not configured_model or stale_llama_model:
            os.environ["MORICE_MODEL"] = "local-gguf"
    if os.path.exists(server_path):
        os.environ.setdefault("MORICE_LLAMA_SERVER_PATH", server_path)
        os.environ.setdefault("MORICE_LLAMA_SERVER", "1")


def _fix_pyside_paths():
    base_dir = os.path.dirname(sys.executable)
    internal_dir = os.path.join(base_dir, "_internal")
    shiboken_dir = os.path.join(internal_dir, "shiboken6")
    pyside_dir = os.path.join(internal_dir, "PySide6")

    for path in (internal_dir, shiboken_dir, pyside_dir):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
        if os.path.isdir(path):
            try:
                os.add_dll_directory(path)
            except Exception:
                pass


_configure_local_model_defaults()
_fix_pyside_paths()

from morice.pyside_app import run_app


if __name__ == "__main__":
    run_app()
