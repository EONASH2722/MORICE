from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def split_asset(source: Path, output_dir: Path, part_size: int) -> dict[str, object]:
    source = source.resolve()
    output_dir = output_dir.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Release asset does not exist: {source}")
    if part_size < 1024 * 1024:
        raise ValueError("Part size must be at least 1 MiB.")

    output_dir.mkdir(parents=True, exist_ok=True)
    part_records: list[dict[str, object]] = []
    with source.open("rb") as input_handle:
        index = 1
        while True:
            chunk = input_handle.read(part_size)
            if not chunk:
                break
            name = f"{source.name}.part{index:02d}"
            target = output_dir / name
            with tempfile.NamedTemporaryFile(
                prefix=f".{name}.", suffix=".tmp", dir=output_dir, delete=False
            ) as temporary:
                temporary.write(chunk)
                temporary_path = Path(temporary.name)
            temporary_path.replace(target)
            part_records.append(
                {
                    "name": name,
                    "bytes": target.stat().st_size,
                    "sha256": _sha256(target),
                }
            )
            index += 1

    if len(part_records) < 2:
        raise ValueError("Asset is small enough to publish without splitting.")

    manifest = {
        "schema": "morice.release-parts.v1",
        "output": source.name,
        "bytes": source.stat().st_size,
        "sha256": _sha256(source),
        "parts": part_records,
    }
    manifest_path = output_dir / f"{source.name}.parts.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"manifest": str(manifest_path), **manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description="Split a large release asset into verified parts.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--part-size", type=int, default=1_900_000_000)
    arguments = parser.parse_args()
    print(
        json.dumps(
            split_asset(arguments.source, arguments.output_dir, arguments.part_size),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
