from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import zipfile


def package_portable(source: Path, output: Path) -> dict[str, int | str]:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Portable source directory does not exist: {source}")
    if output == source or source in output.parents:
        raise ValueError("Portable output must be outside the source directory.")

    files = sorted(path for path in source.rglob("*") if path.is_file())
    if not files:
        raise ValueError("Portable source directory is empty.")
    if len(files) > 100_000:
        raise ValueError("Portable package exceeds the 100,000 file safety limit.")
    for path in files:
        if path.is_symlink():
            raise ValueError(f"Portable packages cannot contain symlinks: {path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    os.close(fd)
    temporary = Path(temporary_name)
    total_bytes = sum(path.stat().st_size for path in files)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            for path in files:
                relative = path.relative_to(source).as_posix()
                archive.write(path, f"MORICE/{relative}")
        with zipfile.ZipFile(temporary, mode="r", allowZip64=True) as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"Portable archive validation failed at {bad_member}.")
            if len(archive.infolist()) != len(files):
                raise ValueError("Portable archive file count does not match its source.")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    result: dict[str, int | str] = {
        "path": str(output),
        "files": len(files),
        "sourceBytes": total_bytes,
        "archiveBytes": output.stat().st_size,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Zip64 MORICE portable release.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    print(
        json.dumps(
            package_portable(arguments.source, arguments.output),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
