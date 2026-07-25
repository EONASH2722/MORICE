from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass


BINARY_ARTIFACT_EXTENSIONS = {
    ".apk",
    ".app",
    ".bin",
    ".dll",
    ".dmg",
    ".exe",
    ".jar",
    ".msi",
    ".so",
    ".zip",
}

PYTHON_STDLIB = {
    "argparse",
    "ast",
    "asyncio",
    "collections",
    "csv",
    "dataclasses",
    "datetime",
    "functools",
    "http",
    "io",
    "itertools",
    "json",
    "math",
    "os",
    "pathlib",
    "random",
    "re",
    "shutil",
    "statistics",
    "string",
    "subprocess",
    "sys",
    "textwrap",
    "time",
    "tkinter",
    "typing",
    "unittest",
    "uuid",
}

IMPORT_PACKAGE_ALIASES = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
}


class ProjectValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectLaunchPlan:
    kind: str
    label: str
    target: str
    command: tuple[str, ...] = ()


def validate_project_file(relative_path: str, content: str) -> None:
    path = (relative_path or "").replace("\\", "/").strip()
    ext = os.path.splitext(path)[1].lower()
    if ext in BINARY_ARTIFACT_EXTENSIONS:
        raise ProjectValidationError(
            f"MORICE cannot create a compiled binary like {path}. It must create source files and a build/run script instead."
        )
    if "\x00" in content:
        raise ProjectValidationError(f"{path} contains binary data. Project mode writes text source files only.")
    if ext == ".py":
        try:
            compile(content, path or "generated.py", "exec")
        except SyntaxError as exc:
            raise ProjectValidationError(f"Python syntax error in {path}: {exc.msg} on line {exc.lineno}.") from exc
    elif ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProjectValidationError(f"JSON error in {path}: {exc.msg}.") from exc
    elif ext in {".html", ".htm"}:
        if "<html" not in content.lower() and "<!doctype html" not in content.lower():
            raise ProjectValidationError(f"{path} does not contain a complete HTML document.")


def detect_python_requirements(files: dict[str, str]) -> list[str]:
    packages: set[str] = set()
    for path, content in files.items():
        if os.path.splitext(path)[1].lower() != ".py":
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if not name or name in PYTHON_STDLIB or name.startswith("_"):
                    continue
                packages.add(IMPORT_PACKAGE_ALIASES.get(name, name))
    return sorted(packages, key=str.lower)


def build_launch_plan(project_root: str) -> ProjectLaunchPlan | None:
    root = os.path.abspath(project_root or "")
    if not root or not os.path.isdir(root):
        return None

    for filename in ("run.bat", "start.bat", "launch.bat"):
        path = os.path.join(root, filename)
        if os.path.isfile(path):
            return ProjectLaunchPlan("batch", f"Run {filename}", path)

    index_html = os.path.join(root, "index.html")
    if os.path.isfile(index_html):
        return ProjectLaunchPlan("browser", "Open index.html", index_html)

    for filename in ("main.py", "app.py", "game.py"):
        path = os.path.join(root, filename)
        if os.path.isfile(path):
            return ProjectLaunchPlan("python", f"Run {filename}", path, (sys.executable, path))
    return None


def launch_project(plan: ProjectLaunchPlan) -> str:
    if plan.kind == "browser":
        os.startfile(plan.target)  # type: ignore[attr-defined]
        return f"Opened {os.path.basename(plan.target)} in your default browser."
    if plan.kind == "batch":
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", plan.target],
            cwd=os.path.dirname(plan.target),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        return f"Started {os.path.basename(plan.target)}."
    if plan.kind == "python":
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", *plan.command],
            cwd=os.path.dirname(plan.target),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        return f"Started {os.path.basename(plan.target)} with Python."
    raise ProjectValidationError("MORICE could not find a supported run target for this project.")


def build_run_script(project_root: str, requirements: list[str]) -> tuple[str, str] | None:
    root = os.path.abspath(project_root or "")
    if not root or not os.path.isdir(root):
        return None
    plan = build_launch_plan(root)
    if not plan or plan.kind != "python":
        return None
    lines = ["@echo off", "setlocal", "where python >nul 2>nul || (echo Python was not found on PATH. & pause & exit /b 1)"]
    if requirements:
        lines.append('python -m pip install -r "%~dp0requirements.txt"')
        lines.append("if errorlevel 1 pause")
    lines.append(f'python "%~dp0{os.path.basename(plan.target)}"')
    lines.append("if errorlevel 1 pause")
    lines.append("endlocal")
    return "run.bat", "\r\n".join(lines) + "\r\n"
