import os
import sys


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


_fix_pyside_paths()

from morice.pyside_app import run_app


if __name__ == "__main__":
    run_app()
