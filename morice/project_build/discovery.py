"""Reuse project indexing/workflows; inspect only the active development stack."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from ..project_builder import analyze_project_request
from ..project_workflows import discover_project_workflow


def fingerprint(root, goal, indexer):
    root = Path(root).resolve()
    index = indexer.build(root)
    workflow = discover_project_workflow(str(root), goal)
    return {"languages": index.languages, "frameworks": list(index.frameworks),
        "package_managers": list(index.build_systems), "entry_points": list(index.entry_points),
        "dependencies": list(index.dependencies), "git": index.git, "file_count": len(index.files),
        "truncated": index.truncated, "workflow": workflow.to_dict()}


def project_python(root):
    local = Path(root, ".venv", "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python")
    if local.is_file():
        return str(local)
    if getattr(sys,"frozen",False):
        return shutil.which("python") or shutil.which("python3") or shutil.which("py") or "python"
    return sys.executable


def commands_for(root, goal, overrides=None, *, environment_root=None):
    root = Path(root).resolve()
    workflow = discover_project_workflow(str(root), goal)
    spec = analyze_project_request(goal, bool(list(root.iterdir())))
    kind = workflow.adapter_id
    if kind == "generic" and spec.language == "Python":
        kind = "python"
    if kind == "generic" and spec.kind == "web":
        kind = "web"
    helper = str(Path(__file__).with_name("localtools.py"))
    environment_root = Path(environment_root or root).resolve()
    py = project_python(environment_root)
    commands = {"dependencies": (), "build": workflow.build_command, "test": workflow.test_command, "run": workflow.run_command}
    dependencies = {"manager": kind, "isolation": "project_local", "declared": []}
    runtime = {"kind": "unavailable"}
    if kind in {"python", "web"}:
        commands["dependencies"] = (py, helper, "dependencies", str(root))
        commands["build"] = (py, helper, f"{kind}-build", str(root))
        if kind == "python":
            if (root / "requirements.txt").is_file():
                py = str(environment_root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
                commands["dependencies"] = (project_python(environment_root), helper, "prepare-env", str(root))
                commands["build"] = (py, helper, "python-build", str(root))
            has_tests = (root / "tests").is_dir() or any(root.glob("test_*.py"))
            commands["test"] = (py, "-m", "unittest", "discover", "-s", "tests" if (root / "tests").is_dir() else ".", "-v") if has_tests else ()
            if workflow.test_command and not (root / "requirements.txt").is_file():
                commands["test"] = workflow.test_command
            entry = next((name for name in ("main.py", "app.py") if (root / name).is_file()), "")
            commands["run"] = (py, entry) if entry else ()
            runtime = {"kind": "command", "command": list(commands["run"])}
            if (root / "requirements.txt").is_file():
                dependencies["declared"] = (root / "requirements.txt").read_text(encoding="utf-8").splitlines()[:100]
        else:
            commands["test"] = (py, helper, "web-test", str(root))
            runtime = {"kind": "web", "serve_root": str(root / "dist"), "path": "/"}
    elif kind == "node":
        package = json.loads((root / "package.json").read_text(encoding="utf-8")) if (root / "package.json").is_file() else {}
        scripts = package.get("scripts", {})
        manager = "pnpm" if (root / "pnpm-lock.yaml").is_file() else "yarn" if (root / "yarn.lock").is_file() else "npm"
        executable = shutil.which(manager) or manager
        commands["dependencies"] = (executable, "ci" if manager == "npm" and (root / "package-lock.json").is_file() else "install")
        commands["build"] = (executable, "run", "build") if "build" in scripts else ()
        commands["test"] = (executable, "run", "test") if "test" in scripts else ()
        run_script = next((s for s in ("dev", "start") if s in scripts), "")
        commands["run"] = (executable, "run", run_script) if run_script else ()
        dependencies.update(manager=manager, declared=sorted({**package.get("dependencies", {}), **package.get("devDependencies", {})}), scripts=scripts)
    elif kind == "dotnet":
        commands["dependencies"] = (workflow.tool_path or "dotnet", "restore")
    elif kind == "rust":
        commands["dependencies"] = (workflow.tool_path or "cargo", "fetch", "--locked") if (root / "Cargo.lock").is_file() else (workflow.tool_path or "cargo", "fetch")
    elif kind == "go":
        commands["dependencies"] = (workflow.tool_path or "go", "mod", "download")
    commands = {k: list(v) for k, v in commands.items()}
    for stage, value in (overrides or {}).items():
        if stage not in commands or not isinstance(value, (list, tuple)) or not all(isinstance(v, str) and v for v in value):
            raise ValueError("Command overrides require a known stage and explicit argv.")
        commands[stage] = list(value)
    return kind, commands, dependencies, runtime


def forbidden_command(command):
    import re
    text = " ".join(command).casefold()
    return bool(re.search(r"\bgit\s+(?:commit|push|merge|tag|rebase|reset|clean)\b|\b(?:npm|pnpm)\s+publish\b|\b(?:vercel|netlify)\s+deploy\b", text))
