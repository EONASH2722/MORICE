from __future__ import annotations

import argparse
from pathlib import Path
import re


def validate_version(root: Path) -> tuple[str, list[str]]:
    root = root.resolve()
    version_text = (root / "morice" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'^VERSION\s*=\s*"([^"]+)"', version_text, re.MULTILINE)
    if not match:
        return "", ["morice/version.py does not define VERSION"]
    version = match.group(1)
    errors: list[str] = []
    checks = {
        "README latest release link": (
            root / "README.md",
            "https://github.com/EONASH2722/MORICE/releases/latest",
        ),
        "README Python package": (
            root / "README.md",
            f"morice_ai-{version}-py3-none-any.whl",
        ),
        "changelog": (root / "CHANGELOG.md", f"[{version}]"),
        "installer default": (
            root / "installer" / "MORICE.iss",
            f'#define MyAppVersion "{version}"',
        ),
        "executable file version": (
            root / "installer" / "version_info.txt",
            f"'FileVersion', '{version}'",
        ),
    }
    for label, (path, needle) in checks.items():
        if not path.is_file() or needle not in path.read_text(encoding="utf-8"):
            errors.append(f"{label} does not contain {needle!r}")
    notes = root / "docs" / f"release-notes-{version}.md"
    if not notes.is_file():
        errors.append(f"release notes are missing: {notes.name}")
    return version, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MORICE version consistency.")
    parser.add_argument("--root", required=True, type=Path)
    arguments = parser.parse_args()
    version, errors = validate_version(arguments.root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"MORICE version metadata is consistent: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
