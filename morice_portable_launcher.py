import os
import sys


def _asset_path(name: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "morice", "assets", name)


def main():
    os.environ.setdefault("MORICE_LLAMA_SERVER", "1")
    os.environ.setdefault("MORICE_GGUF_PATH", _asset_path("Meta-Llama-3.1-8B-Instruct-Q5_K_M.gguf"))
    os.environ.setdefault("MORICE_LLAMA_SERVER_PATH", _asset_path(os.path.join("llama-bin", "llama-server.exe")))
    os.environ.setdefault("MORICE_MODEL", "local-gguf")
    from morice.pyside_app import run_app

    run_app()


if __name__ == "__main__":
    sys.exit(main())
