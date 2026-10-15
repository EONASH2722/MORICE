"""Requirement/architecture planning produces existing TaskGraph objects."""
from __future__ import annotations

import re
from pathlib import Path

from ..kernel import TaskGraph, TaskNode
from ..project_builder import analyze_project_request, build_project_fallback_manifest
from .contracts import Requirement
from .workspace import assign_owners, safe_path, baseline


def route(goal, file_count=0):
    small = bool(re.search(r"\b(?:change|rename|replace)\b.*\b(?:text|label|title|color)\b", goal, re.I))
    return "simple_edit" if small and file_count <= 1 else "single_worker" if file_count <= 1 and not re.search(r"\bbuild|create|new project\b", goal, re.I) else "project_build"


def extract_requirements(goal, checks=()):
    if not goal.strip():
        raise ValueError("A project goal is required.")
    if checks:
        return [v if isinstance(v, Requirement) else Requirement(**v) for v in checks]
    clauses = [v.strip(" .") for v in re.split(r"[;\n]+", goal) if v.strip(" .")]
    result = []
    for text in clauses:
        lowered = text.casefold()
        category = "ui" if any(v in lowered for v in ("layout", "sidebar", "responsive", "screenshot")) else "security" if any(v in lowered for v in ("auth", "password", "secure")) else "platform" if any(v in lowered for v in ("android", "windows", "linux")) else "functional"
        result.append(Requirement(text, category))
    return result


def architecture(goal, changes, requirements, supplied=None):
    spec = analyze_project_request(goal, True)
    return {"language": spec.language or "inferred from project", "framework": spec.framework or "existing/minimal",
        "modules": sorted({str(Path(v["path"]).parent).replace("\\", "/") for v in changes}),
        "storage": "existing project conventions", "testing": "actual commands and independent runtime checks",
        "assumptions": [{"origin": "inferred_default", "text": "Build and test locally; no publication."}],
        **(supplied or {})}


def scaffold(goal, root):
    spec = analyze_project_request(goal, Path(root).is_dir() and any(Path(root).iterdir()))
    if spec.language == "Python" and re.search(r"\bcalculator\b|\badd(?:s|ing)? two numbers\b", goal, re.I):
        if re.search(r"\b(?:subtract|multiply|divide|scientific|gui|tkinter|qt|database|history)\b",goal,re.I):
            return None
        return {"files": [
            {"path": "main.py", "content": "import argparse\n\ndef add(a, b):\n    return a + b\n\ndef main():\n    parser = argparse.ArgumentParser(description='Add two numbers')\n    parser.add_argument('a', type=float)\n    parser.add_argument('b', type=float)\n    args = parser.parse_args()\n    print(f'{add(args.a, args.b):g}')\n\nif __name__ == '__main__':\n    main()\n"},
            {"path": "tests/test_main.py", "content": "import unittest\nfrom main import add\n\nclass AdditionTests(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n    def test_negative(self):\n        self.assertEqual(add(-2, 3), 1)\n"}], "template": "stdlib_addition_cli"}
    return build_project_fallback_manifest(goal, str(root))


def implementation_graph(session, stages, limits):
    tasks = []
    helper = str(Path(__file__).with_name("localtools.py"))
    from .discovery import project_python
    for owner, root in stages.items():
        # Each private copy has its own baseline. Integration still uses the
        # reviewed project baseline, so refreshing staging cannot hide user edits.
        changes = [{"path": v["path"], "content": v["content"], **baseline(safe_path(root, v["path"]))}
            for v in session.changes if v["path"] in session.ownership[owner]]
        coder = TaskNode("filesystem.apply_patch", {"root": str(root), "changes": changes},
            description=f"Implement owned {owner} files", constraints={"role": "coder", "owner": owner})
        check = TaskNode("terminal.run", {"cwd": str(root), "command": [project_python(session.project_root), helper, "source-check", str(root), *session.ownership[owner]], "timeout": 30},
            dependencies=(coder.task_id,), description=f"Check {owner} implementation", constraints={"role": "tester"}, timeout=35)
        tasks.extend((coder, check))
    return TaskGraph(tuple(tasks), goal=session.user_goal)
