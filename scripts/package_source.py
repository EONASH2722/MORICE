from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile


EXCLUDED_PARTS = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "release",
    "voice_models",
}
EXCLUDED_SUFFIXES = {".gguf", ".log", ".pyc", ".pyo", ".whl"}


def _source_files(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    files: list[Path] = []
    for item in completed.stdout.decode("utf-8").split("\0"):
        if not item:
            continue
        relative = Path(item)
        path = root / relative
        if not path.is_file() or path.is_symlink():
            continue
        if EXCLUDED_PARTS.intersection(relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if path.stat().st_size > 100 * 1024 * 1024:
            continue
        files.append(path)
    return sorted(set(files))


def package_source(root: Path, output: Path) -> dict[str, int | str]:
    root = root.resolve()
    output = output.resolve()
    files = _source_files(root)
    if not files:
        raise ValueError("No source files were found.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                archive.write(path, f"MORICE-0.7.0-vnext/{path.relative_to(root).as_posix()}")
        with zipfile.ZipFile(temporary, "r") as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"Source archive failed at {bad_member}.")
            if len(archive.infolist()) != len(files):
                raise ValueError("Source archive file count mismatch.")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(output), "files": len(files), "bytes": output.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a clean MORICE source archive.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(package_source(arguments.root, arguments.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
