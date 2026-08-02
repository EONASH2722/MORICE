"""Launch MORICE from ``python -m morice``."""

from .pyside_app import run_app


if __name__ == "__main__":
    raise SystemExit(run_app())
