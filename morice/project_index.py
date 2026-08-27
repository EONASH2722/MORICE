from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


IGNORED_DIRECTORIES = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".morice",
    ".pytest_cache",
    ".ruff_cache",
    ".state",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "venv",
}
TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".cs": "C#",
    ".html": "HTML",
    ".css": "CSS",
    ".sql": "SQL",
}


@dataclass(frozen=True)
class IndexedSymbol:
    name: str
    kind: str
    file: str
    line: int


@dataclass(frozen=True)
class IndexedFile:
    path: str
    size: int
    modified_ns: int
    language: str = ""
    digest: str = ""
    symbols: tuple[IndexedSymbol, ...] = ()
    imports: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectIndex:
    root: str
    files: tuple[IndexedFile, ...]
    languages: dict[str, int]
    frameworks: tuple[str, ...]
    dependencies: tuple[str, ...]
    build_systems: tuple[str, ...]
    entry_points: tuple[str, ...]
    assets: tuple[str, ...]
    configuration: tuple[str, ...]
    git: dict[str, object]
    truncated: bool = False
    warnings: tuple[str, ...] = ()
    reused_files: int = 0
    changed_files: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ProjectIndexer:
    def __init__(self, *, max_files: int = 6_000, max_file_bytes: int = 1_000_000):
        self.max_files = max(1, int(max_files))
        self.max_file_bytes = max(4_096, int(max_file_bytes))
        self._cache: dict[str, ProjectIndex] = {}
        self._lock = threading.RLock()

    def invalidate(self, root: str | os.PathLike[str] | None = None) -> None:
        """Invalidate one cached project or every cached project."""

        with self._lock:
            if root is None:
                self._cache.clear()
            else:
                self._cache.pop(str(Path(root).expanduser().resolve()), None)

    def build(self, root: str | os.PathLike[str]) -> ProjectIndex:
        base = Path(root).expanduser().resolve()
        if not base.is_dir():
            raise ValueError("Project root must be an existing directory.")
        with self._lock:
            previous = self._cache.get(str(base))
        previous_files = {
            item.path: item for item in previous.files
        } if previous is not None else {}
        files: list[IndexedFile] = []
        languages: dict[str, int] = {}
        assets: list[str] = []
        configuration: list[str] = []
        warnings: list[str] = []
        truncated = False
        reused_files = 0
        changed_files = 0
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = [
                name for name in sorted(dirnames)
                if name not in IGNORED_DIRECTORIES
                and not (Path(dirpath) / name).is_symlink()
            ]
            for filename in sorted(filenames):
                if len(files) >= self.max_files:
                    truncated = True
                    break
                path = Path(dirpath) / filename
                if path.is_symlink():
                    continue
                relative = path.relative_to(base).as_posix()
                try:
                    stat = path.stat()
                except OSError as exc:
                    warnings.append(f"{relative}: {exc}")
                    continue
                extension = path.suffix.lower()
                language = LANGUAGE_BY_EXTENSION.get(extension, "")
                if language:
                    languages[language] = languages.get(language, 0) + 1
                if extension in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".wav", ".mp3", ".glb", ".gltf", ".obj"}:
                    assets.append(relative)
                if filename.lower() in {
                    ".env.example", "cargo.toml", "dockerfile", "package.json",
                    "pyproject.toml", "requirements.txt", "setup.cfg", "tsconfig.json",
                    "vite.config.js", "vite.config.ts",
                } or extension in {".toml", ".yaml", ".yml"}:
                    configuration.append(relative)
                digest = ""
                symbols: tuple[IndexedSymbol, ...] = ()
                imports: tuple[str, ...] = ()
                cached = previous_files.get(relative)
                if (
                    cached is not None
                    and cached.size == stat.st_size
                    and cached.modified_ns == stat.st_mtime_ns
                    and cached.language == language
                ):
                    digest = cached.digest
                    symbols = cached.symbols
                    imports = cached.imports
                    reused_files += 1
                elif extension in TEXT_EXTENSIONS and stat.st_size <= self.max_file_bytes:
                    changed_files += 1
                    try:
                        data = path.read_bytes()
                        digest = hashlib.sha256(data).hexdigest()[:16]
                        text = data.decode("utf-8", errors="replace")
                        symbols, imports = self._parse_source(relative, extension, text)
                    except OSError as exc:
                        warnings.append(f"{relative}: {exc}")
                files.append(
                    IndexedFile(
                        path=relative,
                        size=stat.st_size,
                        modified_ns=stat.st_mtime_ns,
                        language=language,
                        digest=digest,
                        symbols=symbols,
                        imports=imports,
                    )
                )
            if truncated:
                break
        names = {item.path.lower() for item in files}
        index = ProjectIndex(
            root=str(base),
            files=tuple(files),
            languages=dict(sorted(languages.items(), key=lambda item: (-item[1], item[0]))),
            frameworks=self._detect_frameworks(base, names),
            dependencies=self._detect_dependencies(base),
            build_systems=self._detect_build_systems(names),
            entry_points=self._detect_entry_points(names),
            assets=tuple(assets[:500]),
            configuration=tuple(configuration[:500]),
            git=self._git_context(base),
            truncated=truncated,
            warnings=tuple(warnings[:100]),
            reused_files=reused_files,
            changed_files=changed_files,
        )
        with self._lock:
            self._cache[str(base)] = index
        return index

    def search(
        self,
        index: ProjectIndex,
        query: str,
        *,
        limit: int = 20,
    ) -> tuple[dict[str, object], ...]:
        terms = {term for term in re.findall(r"[a-z0-9_]+", query.lower()) if len(term) > 1}
        ranked: list[tuple[int, dict[str, object]]] = []
        for item in index.files:
            haystack = " ".join(
                [
                    item.path.lower(),
                    item.language.lower(),
                    *(symbol.name.lower() for symbol in item.symbols),
                    *(item.imports),
                ]
            )
            score = sum(4 if term in item.path.lower() else 1 for term in terms if term in haystack)
            if score:
                ranked.append(
                    (
                        score,
                        {
                            "path": item.path,
                            "language": item.language,
                            "symbols": [asdict(symbol) for symbol in item.symbols[:30]],
                            "imports": list(item.imports[:30]),
                            "score": score,
                        },
                    )
                )
        ranked.sort(key=lambda entry: (-entry[0], str(entry[1]["path"])))
        return tuple(item for _, item in ranked[: max(1, int(limit))])

    @staticmethod
    def _parse_source(
        relative: str,
        extension: str,
        text: str,
    ) -> tuple[tuple[IndexedSymbol, ...], tuple[str, ...]]:
        symbols: list[IndexedSymbol] = []
        imports: list[str] = []
        if extension == ".py":
            try:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append(IndexedSymbol(node.name, "function", relative, node.lineno))
                    elif isinstance(node, ast.ClassDef):
                        symbols.append(IndexedSymbol(node.name, "class", relative, node.lineno))
                    elif isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imports.append(node.module)
            except SyntaxError:
                pass
        else:
            pattern = re.compile(
                r"^\s*(?:export\s+)?(?:async\s+)?(?:class|interface|enum|function|def|fn|struct)\s+([A-Za-z_]\w*)",
                re.MULTILINE,
            )
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                symbols.append(IndexedSymbol(match.group(1), "symbol", relative, line))
            imports.extend(
                match.group(1)
                for match in re.finditer(
                    r"(?:from|import|require\s*\()\s*['\"]?([@A-Za-z0-9_./-]+)",
                    text,
                )
            )
        return tuple(symbols[:500]), tuple(dict.fromkeys(imports))[:500]

    @staticmethod
    def _detect_frameworks(base: Path, names: set[str]) -> tuple[str, ...]:
        frameworks: set[str] = set()
        package_path = base / "package.json"
        if package_path.is_file():
            try:
                package = json.loads(package_path.read_text(encoding="utf-8"))
                dependencies = package.get("dependencies", {})
                development = package.get("devDependencies", {})
                deps = {
                    **(dependencies if isinstance(dependencies, dict) else {}),
                    **(development if isinstance(development, dict) else {}),
                }
                for package_name, label in {
                    "react": "React",
                    "next": "Next.js",
                    "vue": "Vue",
                    "svelte": "Svelte",
                    "three": "Three.js",
                    "phaser": "Phaser",
                    "vite": "Vite",
                    "express": "Express",
                }.items():
                    if package_name in deps:
                        frameworks.add(label)
            except (OSError, TypeError, ValueError):
                pass
        requirement_parts: list[str] = []
        for path in (base / "requirements.txt", base / "pyproject.toml"):
            if not path.is_file():
                continue
            try:
                requirement_parts.append(
                    path.read_text(encoding="utf-8", errors="replace").lower()
                )
            except OSError:
                continue
        requirements = "\n".join(requirement_parts)
        for marker, label in {
            "django": "Django",
            "fastapi": "FastAPI",
            "flask": "Flask",
            "pyside6": "PySide6",
            "pytest": "pytest",
        }.items():
            if marker in requirements:
                frameworks.add(label)
        if "cargo.toml" in names:
            frameworks.add("Cargo")
        return tuple(sorted(frameworks))

    @staticmethod
    def _detect_dependencies(base: Path) -> tuple[str, ...]:
        dependencies: set[str] = set()
        requirements = base / "requirements.txt"
        if requirements.is_file():
            try:
                lines = requirements.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except OSError:
                lines = ()
            for line in lines:
                clean = line.strip()
                if clean and not clean.startswith(("#", "-")):
                    dependencies.add(
                        re.split(r"[<>=!~;\[]", clean, maxsplit=1)[0]
                    )
        package_path = base / "package.json"
        if package_path.is_file():
            try:
                package = json.loads(package_path.read_text(encoding="utf-8"))
                runtime = package.get("dependencies", {})
                development = package.get("devDependencies", {})
                if isinstance(runtime, dict):
                    dependencies.update(runtime.keys())
                if isinstance(development, dict):
                    dependencies.update(development.keys())
            except (OSError, TypeError, ValueError):
                pass
        return tuple(sorted(dependencies))[:1_000]

    @staticmethod
    def _detect_build_systems(names: set[str]) -> tuple[str, ...]:
        markers = {
            "package.json": "npm",
            "cargo.toml": "Cargo",
            "cmakelists.txt": "CMake",
            "makefile": "Make",
            "gradlew": "Gradle",
            "pom.xml": "Maven",
            "pyproject.toml": "Python build",
            "requirements.txt": "Python requirements",
        }
        return tuple(label for marker, label in markers.items() if marker in names)

    @staticmethod
    def _detect_entry_points(names: set[str]) -> tuple[str, ...]:
        candidates = (
            "index.html", "src/main.ts", "src/main.tsx", "src/main.js", "src/index.js",
            "main.py", "app.py", "manage.py", "main.rs", "src/main.rs",
        )
        return tuple(candidate for candidate in candidates if candidate in names)

    @staticmethod
    def _git_context(base: Path) -> dict[str, object]:
        def run(*args: str) -> str:
            completed = subprocess.run(
                ["git", *args],
                cwd=base,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            return (
                completed.stdout[-100_000:].strip()
                if completed.returncode == 0
                else ""
            )

        try:
            root = run("rev-parse", "--show-toplevel")
            if not root:
                return {"repository": False}
            return {
                "repository": True,
                "root": root,
                "branch": run("branch", "--show-current"),
                "status": run("status", "--short"),
                "recent": run("log", "-5", "--pretty=%h %s").splitlines(),
            }
        except (OSError, subprocess.SubprocessError):
            return {"repository": False}
