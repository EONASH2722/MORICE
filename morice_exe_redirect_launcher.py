import os
import subprocess
import sys
from tkinter import messagebox


def _target_exe() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        return os.path.join(base, "MORICE", "MORICE.exe")
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "dist", "MORICE", "MORICE.exe")


def main() -> int:
    target = _target_exe()
    if not os.path.exists(target):
        messagebox.showerror("MORICE", f"Fixed MORICE executable was not found:\n{target}")
        return 1

    subprocess.Popen([target], close_fds=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
