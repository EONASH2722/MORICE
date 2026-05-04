import os
import sys


def _asset_path(*parts: str) -> str:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "morice", "assets", *parts)


def _configure_local_model_defaults():
    if os.getenv("MORICE_MODEL", "").strip() or os.getenv("MORICE_GGUF_PATH", "").strip():
        return

    gguf_path = _asset_path("Meta-Llama-3.1-8B-Instruct-Q5_K_M.gguf")
    server_path = _asset_path("llama-bin", "llama-server.exe")

    if os.path.exists(gguf_path):
        os.environ.setdefault("MORICE_GGUF_PATH", gguf_path)
        os.environ.setdefault("MORICE_MODEL", "local-gguf")
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
