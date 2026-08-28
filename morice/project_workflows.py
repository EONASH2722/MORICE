from __future__ import annotations

import os
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ProjectAdapter:
    adapter_id: str
    label: str
    markers: tuple[str, ...] = ()
    request_terms: tuple[str, ...] = ()
    executable_names: tuple[str, ...] = ()
    known_executables: tuple[str, ...] = ()
    build_candidates: tuple[tuple[str, ...], ...] = ()
    test_candidates: tuple[tuple[str, ...], ...] = ()
    run_candidates: tuple[tuple[str, ...], ...] = ()
    editor_required: bool = False


@dataclass(frozen=True)
class ProjectWorkflow:
    adapter_id: str
    label: str
    root: str
    detected_from: str
    tool_path: str = ""
    build_command: tuple[str, ...] = ()
    test_command: tuple[str, ...] = ()
    run_command: tuple[str, ...] = ()
    editor_required: bool = False
    evidence: tuple[str, ...] = ()

    @property
    def tool_available(self) -> bool:
        return bool(self.tool_path) or self.adapter_id in {"web", "generic"}

    def to_dict(self) -> dict[str, object]:
        return {
            "adapterId": self.adapter_id,
            "label": self.label,
            "root": self.root,
            "detectedFrom": self.detected_from,
            "toolPath": self.tool_path,
            "toolAvailable": self.tool_available,
            "buildCommand": list(self.build_command),
            "testCommand": list(self.test_command),
            "runCommand": list(self.run_command),
            "editorRequired": self.editor_required,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ArtifactVerification:
    root: str
    expected: int
    verified: int
    missing: tuple[str, ...] = ()
    mismatched: tuple[str, ...] = ()
    empty: tuple[str, ...] = ()
    files: tuple[dict[str, object], ...] = ()

    @property
    def success(self) -> bool:
        return (
            self.expected > 0
            and self.verified == self.expected
            and not self.missing
            and not self.mismatched
            and not self.empty
        )

    def summary(self) -> str:
        if self.success:
            return f"Verified {self.verified}/{self.expected} generated files on disk."
        problems = [
            *(f"missing {item}" for item in self.missing),
            *(f"content mismatch {item}" for item in self.mismatched),
            *(f"empty {item}" for item in self.empty),
        ]
        return "Artifact verification failed: " + "; ".join(problems[:8])


def _windows_program_files(*parts: str) -> str:
    base = os.environ.get("ProgramFiles", r"C:\Program Files")
    return str(Path(base, *parts))


ADAPTERS: tuple[ProjectAdapter, ...] = (
    ProjectAdapter(
        "unreal",
        "Unreal Engine",
        markers=("*.uproject", "Config/DefaultEngine.ini"),
        request_terms=("unreal", "uproject", "blueprint"),
        executable_names=("UnrealEditor.exe",),
        known_executables=(
            _windows_program_files("Epic Games", "UE_5.6", "Engine", "Binaries", "Win64", "UnrealEditor.exe"),
            _windows_program_files("Epic Games", "UE_5.5", "Engine", "Binaries", "Win64", "UnrealEditor.exe"),
            _windows_program_files("Epic Games", "UE_5.4", "Engine", "Binaries", "Win64", "UnrealEditor.exe"),
        ),
        editor_required=True,
    ),
    ProjectAdapter(
        "unity",
        "Unity",
        markers=("ProjectSettings/ProjectVersion.txt", "Assets"),
        request_terms=("unity", "unity hub"),
        executable_names=("Unity.exe",),
        known_executables=(
            _windows_program_files("Unity", "Hub", "Editor", "6000.0.0f1", "Editor", "Unity.exe"),
        ),
        editor_required=True,
    ),
    ProjectAdapter(
        "roblox",
        "Roblox Studio",
        markers=("*.rbxl", "*.rbxlx", "*.project.json", "default.project.json"),
        request_terms=("roblox", "roblox studio", "luau", "rojo"),
        executable_names=("RobloxStudioBeta.exe", "rojo.exe"),
        editor_required=True,
    ),
    ProjectAdapter(
        "godot",
        "Godot",
        markers=("project.godot",),
        request_terms=("godot", "gdscript"),
        executable_names=("godot.exe", "godot4.exe"),
        run_candidates=(("godot", "--path", ".", "--editor"),),
        editor_required=True,
    ),
    ProjectAdapter(
        "android",
        "Android",
        markers=("settings.gradle", "settings.gradle.kts", "app/src/main/AndroidManifest.xml"),
        request_terms=("android", "apk", "gradle"),
        executable_names=("gradlew.bat", "gradle.bat"),
        build_candidates=(("gradlew.bat", "assembleDebug"), ("gradle", "assembleDebug")),
        test_candidates=(("gradlew.bat", "test"), ("gradle", "test")),
    ),
    ProjectAdapter(
        "dotnet",
        ".NET / Visual Studio",
        markers=("*.sln", "*.csproj", "*.fsproj", "*.vbproj"),
        request_terms=("visual studio", ".net", "c#", "csharp"),
        executable_names=("dotnet.exe", "devenv.exe"),
        build_candidates=(("dotnet", "build"),),
        test_candidates=(("dotnet", "test", "--no-build"),),
        run_candidates=(("dotnet", "run"),),
    ),
    ProjectAdapter(
        "node",
        "Node.js",
        markers=("package.json",),
        request_terms=("node", "react", "next.js", "vite", "javascript", "typescript"),
        executable_names=("npm.cmd", "node.exe"),
        build_candidates=(("npm", "run", "build"),),
        test_candidates=(("npm", "test", "--", "--runInBand"),),
        run_candidates=(("npm", "run", "dev"),),
    ),
    ProjectAdapter(
        "python",
        "Python",
        markers=("pyproject.toml", "requirements.txt", "main.py", "app.py"),
        request_terms=("python", "pygame", "django", "fastapi"),
        executable_names=("python.exe", "py.exe"),
        test_candidates=(("python", "-m", "pytest"),),
    ),
    ProjectAdapter(
        "java",
        "Java",
        markers=("pom.xml", "build.gradle", "build.gradle.kts"),
        request_terms=("java", "maven", "spring"),
        executable_names=("mvn.cmd", "gradlew.bat", "gradle.bat"),
        build_candidates=(("mvn", "package"), ("gradlew.bat", "build")),
        test_candidates=(("mvn", "test"), ("gradlew.bat", "test")),
    ),
    ProjectAdapter(
        "rust",
        "Rust",
        markers=("Cargo.toml",),
        request_terms=("rust", "cargo", "bevy"),
        executable_names=("cargo.exe",),
        build_candidates=(("cargo", "build"),),
        test_candidates=(("cargo", "test"),),
        run_candidates=(("cargo", "run"),),
    ),
    ProjectAdapter(
        "go",
        "Go",
        markers=("go.mod",),
        request_terms=("golang", "go app", "go project"),
        executable_names=("go.exe",),
        build_candidates=(("go", "build", "./..."),),
        test_candidates=(("go", "test", "./..."),),
        run_candidates=(("go", "run", "."),),
    ),
    ProjectAdapter(
        "web",
        "Web",
        markers=("index.html",),
        request_terms=("website", "web app", "html", "browser"),
    ),
)


def _marker_matches(root: Path, marker: str) -> tuple[str, ...]:
    if any(char in marker for char in "*?["):
        return tuple(str(path.relative_to(root)).replace("\\", "/") for path in root.glob(marker))
    path = root / marker
    return (marker,) if path.exists() else ()


def _find_tool(adapter: ProjectAdapter, root: Path) -> str:
    for name in adapter.executable_names:
        local = root / name
        if local.is_file():
            return str(local)
        found = shutil.which(name)
        if found:
            return found
    for candidate in adapter.known_executables:
        if Path(candidate).is_file():
            return candidate
    if adapter.adapter_id == "roblox" and os.name == "nt":
        versions = Path(os.environ.get("LOCALAPPDATA", ""), "Roblox", "Versions")
        if versions.is_dir():
            matches = sorted(versions.glob("*/RobloxStudioBeta.exe"), reverse=True)
            if matches:
                return str(matches[0])
    if adapter.adapter_id == "unity" and os.name == "nt":
        editors = Path(os.environ.get("ProgramFiles", r"C:\Program Files"), "Unity", "Hub", "Editor")
        if editors.is_dir():
            matches = sorted(editors.glob("*/Editor/Unity.exe"), reverse=True)
            if matches:
                return str(matches[0])
    if adapter.adapter_id == "unreal" and os.name == "nt":
        epic = Path(os.environ.get("ProgramFiles", r"C:\Program Files"), "Epic Games")
        if epic.is_dir():
            matches = sorted(epic.glob("UE_*/Engine/Binaries/Win64/UnrealEditor.exe"), reverse=True)
            if matches:
                return str(matches[0])
    return ""


def _usable_command(
    candidates: Iterable[tuple[str, ...]],
    root: Path,
    *,
    adapter_id: str = "",
    stage: str = "",
) -> tuple[str, ...]:
    for command in candidates:
        if not command:
            continue
        if adapter_id == "node" and len(command) >= 3 and command[1] == "run":
            try:
                package = json.loads((root / "package.json").read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, TypeError, ValueError):
                continue
            scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
            if not isinstance(scripts, dict) or command[2] not in scripts:
                continue
        if adapter_id == "node" and stage == "test":
            try:
                package = json.loads((root / "package.json").read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, TypeError, ValueError):
                continue
            scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
            if not isinstance(scripts, dict) or "test" not in scripts:
                continue
        if adapter_id == "python" and stage == "test":
            has_tests = (root / "tests").is_dir() or any(root.glob("test_*.py")) or any(root.glob("*_test.py"))
            if not has_tests:
                continue
        executable = command[0]
        if adapter_id == "python" and executable == "python":
            project_python = root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
                "python.exe" if os.name == "nt" else "python"
            )
            if project_python.is_file():
                return (str(project_python), *command[1:])
            current_python = Path(sys.executable)
            if not getattr(sys, "frozen", False) and current_python.is_file():
                return (str(current_python), *command[1:])
        local = root / executable
        if local.is_file() or shutil.which(executable):
            return command
    return ()


def discover_project_workflow(project_root: str, request: str = "") -> ProjectWorkflow:
    root = Path(project_root).resolve()
    lowered = " ".join(str(request or "").casefold().split())
    scored: list[tuple[int, int, ProjectAdapter, tuple[str, ...], str]] = []
    for index, adapter in enumerate(ADAPTERS):
        marker_hits = tuple(
            hit
            for marker in adapter.markers
            for hit in _marker_matches(root, marker)
        ) if root.is_dir() else ()
        term = next((term for term in adapter.request_terms if term in lowered), "")
        score = len(marker_hits) * 10 + (4 if term else 0)
        if score:
            scored.append((score, -index, adapter, marker_hits, term))
    if scored:
        _score, _index, adapter, marker_hits, term = max(scored, key=lambda item: (item[0], item[1]))
        detected_from = "project markers" if marker_hits else f"request term '{term}'"
    else:
        adapter = ProjectAdapter("generic", "Generic project")
        marker_hits = ()
        detected_from = "no engine-specific marker"
    tool_path = _find_tool(adapter, root)
    evidence = tuple(marker_hits[:8])
    if tool_path:
        evidence += (f"tool:{tool_path}",)
    return ProjectWorkflow(
        adapter.adapter_id,
        adapter.label,
        str(root),
        detected_from,
        tool_path,
        _usable_command(adapter.build_candidates, root, adapter_id=adapter.adapter_id, stage="build"),
        _usable_command(adapter.test_candidates, root, adapter_id=adapter.adapter_id, stage="test"),
        _usable_command(adapter.run_candidates, root, adapter_id=adapter.adapter_id, stage="run"),
        adapter.editor_required,
        evidence,
    )


def verify_project_artifacts(
    project_root: str,
    expected_files: Mapping[str, str],
) -> ArtifactVerification:
    root = Path(project_root).resolve()
    missing: list[str] = []
    mismatched: list[str] = []
    empty: list[str] = []
    files: list[dict[str, object]] = []
    verified = 0
    for relative, expected in expected_files.items():
        normalized = str(relative).replace("\\", "/").lstrip("/")
        target = (root / normalized).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            mismatched.append(normalized)
            continue
        if not target.is_file():
            missing.append(normalized)
            continue
        try:
            actual = target.read_text(encoding="utf-8")
            size = target.stat().st_size
        except OSError:
            mismatched.append(normalized)
            continue
        if expected and not actual:
            empty.append(normalized)
        if actual != expected:
            mismatched.append(normalized)
        else:
            verified += 1
        files.append({"path": normalized, "bytes": size, "matches": actual == expected})
    return ArtifactVerification(
        str(root),
        len(expected_files),
        verified,
        tuple(missing),
        tuple(mismatched),
        tuple(empty),
        tuple(files),
    )


def command_text(command: Iterable[str]) -> str:
    return " ".join(f'"{item}"' if " " in item else item for item in command)


__all__ = [
    "ADAPTERS",
    "ArtifactVerification",
    "ProjectAdapter",
    "ProjectWorkflow",
    "command_text",
    "discover_project_workflow",
    "verify_project_artifacts",
]
