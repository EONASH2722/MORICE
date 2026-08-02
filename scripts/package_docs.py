from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import zipfile


ROOT_FILES = (
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "LICENSE",
)


def package_docs(root: Path, output: Path) -> dict[str, int | str]:
    root = root.resolve()
    output = output.resolve()
    docs = root / "docs"
    files = [root / name for name in ROOT_FILES if (root / name).is_file()]
    files.extend(sorted(path for path in docs.rglob("*") if path.is_file()))
    if not files:
        raise ValueError("No documentation files were found.")
    if output == root or root in output.parents:
        # Release output is expected inside the root, but source content cannot include it.
        pass
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                archive.write(path, f"MORICE-Documentation/{path.relative_to(root).as_posix()}")
        with zipfile.ZipFile(temporary, "r") as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"Documentation archive failed at {bad_member}.")
            if len(archive.infolist()) != len(files):
                raise ValueError("Documentation archive file count mismatch.")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(output), "files": len(files), "bytes": output.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the MORICE documentation bundle.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(package_docs(arguments.root, arguments.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
