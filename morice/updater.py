from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_UPDATE_FILES = 50_000
MAX_UPDATE_BYTES = 12 * 1024 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(name: str) -> Path:
    normalized = name.replace("\\", "/").strip("/")
    value = Path(normalized)
    if (
        not normalized
        or value.is_absolute()
        or ".." in value.parts
        or "\x00" in normalized
    ):
        raise ValueError(f"Unsafe update member: {name}")
    return value


def _wait_for_process(pid: int, timeout_seconds: float = 45.0) -> None:
    if pid <= 0:
        return
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.25)
    raise TimeoutError("MORICE did not close before the update timeout.")


def _extract_verified(package: Path, destination: Path) -> Path:
    total = 0
    with zipfile.ZipFile(package) as archive:
        members = archive.infolist()
        if len(members) > MAX_UPDATE_FILES:
            raise ValueError("Update contains too many files.")
        for member in members:
            relative = _safe_member(member.filename)
            if member.is_dir():
                continue
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Update packages cannot contain symbolic links.")
            total += max(0, member.file_size)
            if total > MAX_UPDATE_BYTES:
                raise ValueError("Update package exceeds the size limit.")
            output = (destination / relative).resolve()
            try:
                output.relative_to(destination)
            except ValueError as exc:
                raise ValueError("Update member escapes staging.") from exc
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, output.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
    candidates = [destination, *(path for path in destination.iterdir() if path.is_dir())]
    payload = next(
        (path for path in candidates if (path / "MORICE.exe").is_file()),
        None,
    )
    if payload is None:
        raise ValueError("Update package does not contain MORICE.exe.")
    return payload


def _apply_portable_update(
    package: Path,
    install_root: Path,
    rollback_root: Path,
) -> list[str]:
    changed: list[str] = []
    rollback_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="morice-update-") as directory:
        staging = Path(directory).resolve()
        payload = _extract_verified(package, staging)
        files = sorted(path for path in payload.rglob("*") if path.is_file())
        if len(files) > MAX_UPDATE_FILES:
            raise ValueError("Update contains too many files.")
        created: set[str] = set()
        try:
            for source in files:
                relative = source.relative_to(payload)
                relative_value = relative.as_posix()
                destination = (install_root / relative).resolve()
                try:
                    destination.relative_to(install_root)
                except ValueError as exc:
                    raise ValueError("Update destination escapes the installation.") from exc
                backup = rollback_root / relative
                if destination.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, backup)
                else:
                    created.add(relative_value)
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(destination.suffix + ".update.tmp")
                try:
                    shutil.copy2(source, temporary)
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
                changed.append(relative_value)
        except Exception:
            for relative_value in reversed(changed):
                relative = Path(relative_value)
                backup = rollback_root / relative
                destination = install_root / relative
                if backup.is_file():
                    temporary = destination.with_suffix(destination.suffix + ".rollback.tmp")
                    shutil.copy2(backup, temporary)
                    os.replace(temporary, destination)
                elif relative_value in created:
                    destination.unlink(missing_ok=True)
            raise
    return changed


def _record_result(instruction: Path, value: dict[str, Any]) -> None:
    target = instruction.with_name("last-update-result.json")
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, target)


def run_updater(
    instruction_path: str,
    install_root: str,
    parent_pid: int,
) -> int:
    instruction = Path(instruction_path).expanduser().resolve()
    root = Path(install_root).expanduser().resolve()
    try:
        value = json.loads(instruction.read_text(encoding="utf-8"))
        package = Path(str(value["package"])).expanduser().resolve()
        expected = str(value["sha256"]).casefold()
        version = str(value["version"])
        if not package.is_file() or _sha256(package) != expected:
            raise ValueError("The staged update failed checksum verification.")
        _wait_for_process(parent_pid)
        suffix = package.suffix.casefold()
        if suffix == ".exe":
            subprocess.Popen(
                [
                    str(package),
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/NORESTART",
                ],
                creationflags=CREATE_NO_WINDOW,
            )
            changed = ["installer launched"]
        elif suffix == ".zip":
            rollback = instruction.parent / "rollback" / version
            changed = _apply_portable_update(package, root, rollback)
        else:
            raise ValueError("Updates must be a verified .zip or installer .exe.")
        instruction.unlink(missing_ok=True)
        _record_result(
            instruction,
            {
                "success": True,
                "version": version,
                "changed": changed,
                "rollback": str(instruction.parent / "rollback" / version),
            },
        )
        executable = root / "MORICE.exe"
        relaunch_error = ""
        if suffix == ".zip" and executable.is_file():
            try:
                subprocess.Popen([str(executable)], cwd=root)
            except OSError as exc:
                relaunch_error = str(exc)
                _record_result(
                    instruction,
                    {
                        "success": True,
                        "version": version,
                        "changed": changed,
                        "rollback": str(instruction.parent / "rollback" / version),
                        "warning": f"Update applied but relaunch failed: {exc}",
                    },
                )
        return 0
    except Exception as exc:  # noqa: BLE001
        _record_result(
            instruction,
            {
                "success": False,
                "error": str(exc),
            },
        )
        return 1


def main(arguments: list[str] | None = None) -> int:
    values = list(arguments if arguments is not None else sys.argv[1:])
    if len(values) != 3:
        return 2
    try:
        pid = int(values[2])
    except ValueError:
        return 2
    return run_updater(values[0], values[1], pid)


if __name__ == "__main__":
    raise SystemExit(main())
