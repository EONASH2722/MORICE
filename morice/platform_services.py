from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import urllib.parse
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from . import __version__
from .autonomous_platform import UnifiedPlatformOrchestrator
from .model_catalog import GpuProfile, detect_gpu_profile
from .platform_types import ReleaseCheck


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_EXPORT_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 25_000
UPDATE_CHANNELS = {"stable", "beta"}
SENSITIVE_FILE_NAMES = {
    ".env",
    ".env.local",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "secrets.json",
}
SECRET_PATTERN = re.compile(
    r"(?i)(sk-[a-z0-9_-]{16,}|gh[pousr]_[a-z0-9]{20,}|"
    r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]{6,})"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> Path:
    normalized = value.replace("\\", "/").strip("/")
    path = Path(normalized)
    if (
        not normalized
        or path.is_absolute()
        or ".." in path.parts
        or "\x00" in normalized
    ):
        raise ValueError(f"Unsafe archive path: {value}")
    return path


class ExactApprovalManager:
    def __init__(self, *, ttl_seconds: float = 300.0):
        self.ttl_seconds = max(10.0, min(float(ttl_seconds), 3_600.0))
        self._grants: dict[str, tuple[str, float]] = {}
        self._lock = threading.RLock()

    def request(self, action: str, arguments: dict[str, Any]) -> str:
        token = uuid.uuid4().hex
        signature = self._signature(action, arguments)
        with self._lock:
            self._grants[token] = (signature, time.monotonic() + self.ttl_seconds)
        return token

    def consume(self, token: str, action: str, arguments: dict[str, Any]) -> bool:
        if not token:
            return False
        with self._lock:
            value = self._grants.pop(token, None)
        if value is None:
            return False
        expected, expires_at = value
        return time.monotonic() <= expires_at and hmac.compare_digest(
            expected,
            self._signature(action, arguments),
        )

    @staticmethod
    def _signature(action: str, arguments: dict[str, Any]) -> str:
        return hashlib.sha256(
            action.encode("utf-8") + b"\0" + _canonical(arguments)
        ).hexdigest()


class GitRepositoryService:
    """Read-only Git inspection plus exact-approval mutation operations."""

    def __init__(self, approvals: ExactApprovalManager | None = None):
        self.approvals = approvals or ExactApprovalManager()

    def inspect(self, root: str | os.PathLike[str]) -> dict[str, Any]:
        target = Path(root).expanduser().resolve()
        if not target.is_dir():
            raise NotADirectoryError(str(target))
        if not (target / ".git").exists():
            return {
                "available": bool(shutil.which("git")),
                "repository": False,
                "root": str(target),
                "branch": "",
                "dirty": False,
                "status": (),
                "branches": (),
                "commits": (),
                "tags": (),
                "conflicts": (),
                "timeline": (),
            }
        status = self._run(target, "status", "--short", "--branch")
        branch = self._run(target, "branch", "--show-current").strip()
        branches = tuple(
            line.strip().removeprefix("* ").strip()
            for line in self._run(target, "branch", "--format=%(refname:short)").splitlines()
            if line.strip()
        )
        commits: list[dict[str, Any]] = []
        log = self._run(
            target,
            "log",
            "-30",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%h%x1f%an%x1f%ad%x1f%s",
        )
        for line in log.splitlines():
            parts = line.split("\x1f", 4)
            if len(parts) == 5:
                commits.append(
                    {
                        "sha": parts[0],
                        "shortSha": parts[1],
                        "author": parts[2],
                        "date": parts[3],
                        "subject": parts[4],
                    }
                )
        tags = tuple(
            line.strip()
            for line in self._run(
                target,
                "tag",
                "--sort=-creatordate",
            ).splitlines()[:100]
            if line.strip()
        )
        conflicts = tuple(
            line[3:].strip()
            for line in status.splitlines()
            if len(line) > 3 and "U" in line[:2]
        )
        timeline = tuple(
            {
                "kind": "commit",
                "id": item["sha"],
                "label": item["subject"],
                "timestamp": item["date"],
                "author": item["author"],
            }
            for item in commits
        )
        return {
            "available": True,
            "repository": True,
            "root": str(target),
            "branch": branch,
            "dirty": any(
                line and not line.startswith("##") for line in status.splitlines()
            ),
            "status": tuple(status.splitlines()),
            "branches": branches,
            "commits": tuple(commits),
            "tags": tags,
            "conflicts": conflicts,
            "timeline": timeline,
        }

    def diff(
        self,
        root: str | os.PathLike[str],
        *,
        staged: bool = False,
        path: str = "",
    ) -> str:
        target = self._repository(root)
        arguments = ["diff"]
        if staged:
            arguments.append("--cached")
        arguments.extend(["--no-ext-diff", "--"])
        if path:
            relative = _safe_relative(path)
            arguments.append(relative.as_posix())
        return self._run(target, *arguments)[-500_000:]

    def history(
        self,
        root: str | os.PathLike[str],
        *,
        path: str = "",
        limit: int = 100,
    ) -> tuple[dict[str, str], ...]:
        target = self._repository(root)
        arguments = [
            "log",
            f"-{max(1, min(int(limit), 500))}",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%an%x1f%ad%x1f%s",
        ]
        if path:
            arguments.extend(["--", _safe_relative(path).as_posix()])
        values = []
        for line in self._run(target, *arguments).splitlines():
            parts = line.split("\x1f", 3)
            if len(parts) == 4:
                values.append(
                    {
                        "sha": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "subject": parts[3],
                    }
                )
        return tuple(values)

    def request(self, action: str, arguments: dict[str, Any]) -> str:
        if action not in {
            "init",
            "clone",
            "branch",
            "merge",
            "commit",
            "tag",
            "revert",
            "resolve",
            "release",
        }:
            raise ValueError(f"Unsupported Git action: {action}")
        return self.approvals.request(f"git.{action}", arguments)

    def initialize(self, root: str, token: str) -> dict[str, Any]:
        arguments = {"root": str(Path(root).expanduser().resolve())}
        self._authorize("init", arguments, token)
        target = Path(arguments["root"])
        target.mkdir(parents=True, exist_ok=True)
        self._run_checked(target, "init")
        return self.inspect(target)

    def clone(self, source: str, destination: str, token: str) -> dict[str, Any]:
        target = Path(destination).expanduser().resolve()
        arguments = {"source": source.strip(), "destination": str(target)}
        self._authorize("clone", arguments, token)
        if not arguments["source"]:
            raise ValueError("A Git source is required.")
        if target.exists():
            raise FileExistsError(str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run_checked(target.parent, "clone", arguments["source"], str(target))
        return self.inspect(target)

    def create_branch(self, root: str, name: str, token: str) -> dict[str, Any]:
        target = self._repository(root)
        clean_name = self._ref(name)
        arguments = {"root": str(target), "name": clean_name}
        self._authorize("branch", arguments, token)
        self._run_checked(target, "switch", "-c", clean_name)
        return self.inspect(target)

    def merge(self, root: str, branch: str, token: str) -> dict[str, Any]:
        target = self._repository(root)
        clean_branch = self._ref(branch)
        arguments = {"root": str(target), "branch": clean_branch}
        self._authorize("merge", arguments, token)
        self._run_checked(target, "merge", "--no-edit", clean_branch)
        return self.inspect(target)

    def commit(
        self,
        root: str,
        message: str,
        paths: Iterable[str],
        token: str,
    ) -> dict[str, Any]:
        target = self._repository(root)
        clean_paths = tuple(_safe_relative(path).as_posix() for path in paths)
        clean_message = message.strip()[:500]
        if not clean_message or not clean_paths:
            raise ValueError("Commit requires a message and explicit paths.")
        arguments = {
            "root": str(target),
            "message": clean_message,
            "paths": clean_paths,
        }
        self._authorize("commit", arguments, token)
        self._run_checked(target, "add", "--", *clean_paths)
        self._run_checked(target, "commit", "-m", clean_message, "--", *clean_paths)
        return self.inspect(target)

    def tag(self, root: str, name: str, message: str, token: str) -> dict[str, Any]:
        target = self._repository(root)
        clean_name = self._ref(name)
        clean_message = message.strip()[:500] or clean_name
        arguments = {
            "root": str(target),
            "name": clean_name,
            "message": clean_message,
        }
        self._authorize("tag", arguments, token)
        self._run_checked(target, "tag", "-a", clean_name, "-m", clean_message)
        return self.inspect(target)

    def revert(self, root: str, commit: str, token: str) -> dict[str, Any]:
        target = self._repository(root)
        clean_commit = self._commit_ref(commit)
        arguments = {"root": str(target), "commit": clean_commit}
        self._authorize("revert", arguments, token)
        self._run_checked(target, "revert", "--no-edit", clean_commit)
        return self.inspect(target)

    def resolve_conflict(
        self,
        root: str,
        path: str,
        content: str,
        token: str,
    ) -> dict[str, Any]:
        target = self._repository(root)
        relative = _safe_relative(path)
        destination = (target / relative).resolve()
        try:
            destination.relative_to(target)
        except ValueError as exc:
            raise ValueError("Conflict path escapes the repository.") from exc
        arguments = {
            "root": str(target),
            "path": relative.as_posix(),
            "contentSha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
        self._authorize("resolve", arguments, token)
        temporary = destination.with_suffix(destination.suffix + ".morice.tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, destination)
        self._run_checked(target, "add", "--", relative.as_posix())
        return self.inspect(target)

    def create_release(
        self,
        root: str,
        version: str,
        notes: str,
        token: str,
    ) -> Path:
        target = self._repository(root)
        clean_version = self._ref(version)
        clean_notes = notes.strip()[:100_000]
        arguments = {
            "root": str(target),
            "version": clean_version,
            "notesSha256": hashlib.sha256(clean_notes.encode("utf-8")).hexdigest(),
        }
        self._authorize("release", arguments, token)
        if clean_version not in self.inspect(target)["tags"]:
            self._run_checked(
                target,
                "tag",
                "-a",
                clean_version,
                "-m",
                clean_notes[:500] or clean_version,
            )
        release_dir = target / "release"
        release_dir.mkdir(exist_ok=True)
        manifest = release_dir / f"{clean_version}.json"
        _atomic_json_write(
            manifest,
            {
                "version": clean_version,
                "notes": clean_notes,
                "commit": self._run(target, "rev-parse", "HEAD").strip(),
                "createdAt": _utc_now(),
                "published": False,
                "detail": (
                    "This is a verified local release record. Remote publication "
                    "requires an explicitly configured provider."
                ),
            },
        )
        return manifest

    def _authorize(
        self,
        action: str,
        arguments: dict[str, Any],
        token: str,
    ) -> None:
        if not self.approvals.consume(f"{token}", f"git.{action}", arguments):
            raise PermissionError(
                f"Git {action} needs a matching, unexpired, one-use approval."
            )

    @staticmethod
    def _repository(root: str | os.PathLike[str]) -> Path:
        target = Path(root).expanduser().resolve()
        if not target.is_dir() or not (target / ".git").exists():
            raise ValueError("Select an existing Git repository.")
        return target

    @staticmethod
    def _ref(value: str) -> str:
        clean = value.strip()
        if not clean or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", clean):
            raise ValueError("Invalid Git reference.")
        if ".." in clean or clean.endswith(("/", ".", ".lock")):
            raise ValueError("Invalid Git reference.")
        return clean

    @staticmethod
    def _commit_ref(value: str) -> str:
        clean = value.strip()
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", clean):
            raise ValueError("Rollback requires an exact commit hash.")
        return clean

    @staticmethod
    def _run(root: Path, *arguments: str) -> str:
        if not shutil.which("git"):
            return ""
        try:
            completed = subprocess.run(
                ["git", *arguments],
                cwd=root,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=30,
                check=False,
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return completed.stdout[-500_000:] if completed.returncode == 0 else ""

    @staticmethod
    def _run_checked(root: Path, *arguments: str) -> str:
        if not shutil.which("git"):
            raise RuntimeError("Git is not installed.")
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=120,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-4_000:]
            raise RuntimeError(detail or f"Git {' '.join(arguments)} failed.")
        return completed.stdout[-500_000:]


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class SecureVault:
    """Windows DPAPI-backed local secret storage. It fails closed elsewhere."""

    HEADER = b"MORICE-DPAPI-1\n"

    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "vault.json"
        self._lock = threading.RLock()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            data = {}
        self._values = {
            str(key): str(value)
            for key, value in data.get("values", {}).items()
            if isinstance(key, str) and isinstance(value, str)
        }

    @property
    def available(self) -> bool:
        return os.name == "nt" and hasattr(ctypes, "windll")

    def set(self, key: str, value: str) -> None:
        clean_key = self._key(key)
        encrypted = self.protect(value.encode("utf-8"))
        with self._lock:
            self._values[clean_key] = base64.b64encode(encrypted).decode("ascii")
            self._save()

    def get(self, key: str, default: str = "") -> str:
        clean_key = self._key(key)
        with self._lock:
            encoded = self._values.get(clean_key)
        if not encoded:
            return default
        try:
            value = self.unprotect(base64.b64decode(encoded, validate=True))
            return value.decode("utf-8")
        except (OSError, UnicodeError, ValueError):
            return default

    def delete(self, key: str) -> bool:
        clean_key = self._key(key)
        with self._lock:
            removed = self._values.pop(clean_key, None) is not None
            if removed:
                self._save()
            return removed

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._values))

    def protect(self, value: bytes) -> bytes:
        if not value:
            raise ValueError("Cannot protect an empty value.")
        if not self.available:
            raise RuntimeError("Secure local storage requires Windows DPAPI.")
        buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
        input_blob = _DataBlob(
            len(value),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        output_blob = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        succeeded = crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "MORICE local vault",
            None,
            None,
            None,
            0x1,
            ctypes.byref(output_blob),
        )
        if not succeeded:
            raise OSError(ctypes.get_last_error(), "Windows DPAPI encryption failed.")
        try:
            return self.HEADER + ctypes.string_at(
                output_blob.pbData,
                output_blob.cbData,
            )
        finally:
            kernel32.LocalFree(output_blob.pbData)

    def unprotect(self, value: bytes) -> bytes:
        if not value.startswith(self.HEADER):
            raise ValueError("Unsupported secure payload.")
        payload = value[len(self.HEADER) :]
        buffer = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
        input_blob = _DataBlob(
            len(payload),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        output_blob = _DataBlob()
        description = ctypes.c_wchar_p()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        succeeded = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            ctypes.byref(description),
            None,
            None,
            None,
            0x1,
            ctypes.byref(output_blob),
        )
        if not succeeded:
            raise OSError(ctypes.get_last_error(), "Windows DPAPI decryption failed.")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree(output_blob.pbData)

    @staticmethod
    def _key(value: str) -> str:
        clean = re.sub(r"[^a-z0-9_.-]+", "-", value.casefold()).strip("-")
        if not clean or len(clean) > 120:
            raise ValueError("Invalid secure setting key.")
        return clean

    def _save(self) -> None:
        _atomic_json_write(
            self.path,
            {"version": 1, "values": self._values},
        )


class EncryptedBackupManager:
    HEADER = b"MORICE-BACKUP-1\n"

    def __init__(self, vault: SecureVault):
        self.vault = vault

    def create(
        self,
        target: str | os.PathLike[str],
        sources: dict[str, str | os.PathLike[str]],
    ) -> Path:
        destination = Path(target).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "backup.zip"
            manifest: list[dict[str, Any]] = []
            total = 0
            with zipfile.ZipFile(
                archive_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                for category, source_value in sorted(sources.items()):
                    source = Path(source_value).expanduser().resolve()
                    if not source.exists():
                        continue
                    for path, relative in self._files(source, category):
                        size = path.stat().st_size
                        total += size
                        if total > MAX_EXPORT_BYTES:
                            raise ValueError("Backup exceeds the 512 MB safety limit.")
                        archive.write(path, relative)
                        manifest.append(
                            {
                                "path": relative,
                                "bytes": size,
                                "sha256": _sha256_file(path),
                            }
                        )
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "version": 1,
                            "createdAt": _utc_now(),
                            "files": manifest,
                        },
                        indent=2,
                    ),
                )
            protected = self.vault.protect(archive_path.read_bytes())
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(self.HEADER + protected)
        os.replace(temporary, destination)
        return destination

    def restore(
        self,
        source: str | os.PathLike[str],
        target: str | os.PathLike[str],
        *,
        overwrite: bool = False,
    ) -> int:
        backup = Path(source).expanduser().resolve().read_bytes()
        if not backup.startswith(self.HEADER):
            raise ValueError("Unsupported MORICE backup.")
        archive_bytes = self.vault.unprotect(backup[len(self.HEADER) :])
        destination = Path(target).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        restored = 0
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "backup.zip"
            archive_path.write_bytes(archive_bytes)
            with zipfile.ZipFile(archive_path) as archive:
                members = archive.infolist()
                if len(members) > MAX_ARCHIVE_MEMBERS:
                    raise ValueError("Backup contains too many files.")
                manifest = json.loads(archive.read("manifest.json"))
                expected = {
                    str(item["path"]): str(item["sha256"])
                    for item in manifest.get("files", ())
                    if isinstance(item, dict)
                }
                for member in members:
                    if member.is_dir() or member.filename == "manifest.json":
                        continue
                    relative = _safe_relative(member.filename)
                    output = (destination / relative).resolve()
                    try:
                        output.relative_to(destination)
                    except ValueError as exc:
                        raise ValueError("Backup path escapes restore target.") from exc
                    if output.exists() and not overwrite:
                        continue
                    data = archive.read(member)
                    digest = hashlib.sha256(data).hexdigest()
                    if not hmac.compare_digest(expected.get(member.filename, ""), digest):
                        raise ValueError(f"Backup checksum failed: {member.filename}")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    temporary = output.with_suffix(output.suffix + ".morice.tmp")
                    temporary.write_bytes(data)
                    os.replace(temporary, output)
                    restored += 1
        return restored

    @staticmethod
    def _files(source: Path, category: str) -> Iterable[tuple[Path, str]]:
        clean_category = re.sub(r"[^a-z0-9_.-]+", "-", category.casefold()).strip("-")
        if not clean_category:
            raise ValueError("Backup categories require a name.")
        if source.is_file():
            if source.name.casefold() not in SENSITIVE_FILE_NAMES and not source.is_symlink():
                yield source, f"{clean_category}/{source.name}"
            return
        count = 0
        for path in source.rglob("*"):
            if count >= MAX_ARCHIVE_MEMBERS:
                raise ValueError("Backup contains too many files.")
            if (
                not path.is_file()
                or path.is_symlink()
                or path.name.casefold() in SENSITIVE_FILE_NAMES
            ):
                continue
            relative = path.relative_to(source).as_posix()
            yield path, f"{clean_category}/{relative}"
            count += 1


class ExportManager:
    def export_bundle(
        self,
        target: str | os.PathLike[str],
        sources: dict[str, str | os.PathLike[str]],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        destination = Path(target).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        manifest: list[dict[str, Any]] = []
        total = 0
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for category, source_value in sorted(sources.items()):
                source = Path(source_value).expanduser().resolve()
                if not source.exists():
                    continue
                for path, relative in EncryptedBackupManager._files(source, category):
                    size = path.stat().st_size
                    total += size
                    if total > MAX_EXPORT_BYTES:
                        raise ValueError("Export exceeds the 512 MB safety limit.")
                    if self._contains_secret(path):
                        continue
                    archive.write(path, relative)
                    manifest.append(
                        {
                            "path": relative,
                            "bytes": size,
                            "sha256": _sha256_file(path),
                        }
                    )
            archive.writestr(
                "morice-export.json",
                json.dumps(
                    {
                        "version": 1,
                        "applicationVersion": __version__,
                        "createdAt": _utc_now(),
                        "metadata": metadata or {},
                        "files": manifest,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
            )
        os.replace(temporary, destination)
        return destination

    @staticmethod
    def _contains_secret(path: Path) -> bool:
        if path.name.casefold() in SENSITIVE_FILE_NAMES:
            return True
        if path.stat().st_size > 2_000_000 or path.suffix.casefold() not in {
            ".json",
            ".jsonl",
            ".txt",
            ".md",
            ".toml",
            ".yaml",
            ".yml",
            ".ini",
            ".cfg",
            ".log",
        }:
            return False
        try:
            sample = path.read_text(encoding="utf-8", errors="ignore")[:250_000]
        except OSError:
            return True
        return bool(SECRET_PATTERN.search(sample))


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    channel: str
    url: str
    sha256: str
    size: int
    release_notes: str
    published_at: str
    minimum_version: str = ""

    @classmethod
    def from_value(cls, value: dict[str, Any]) -> "UpdateManifest":
        version = str(value.get("version", "")).strip()
        channel = str(value.get("channel", "stable")).casefold()
        url = str(value.get("url", "")).strip()
        sha256 = str(value.get("sha256", "")).casefold()
        size = max(0, int(value.get("size", 0)))
        if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,63}", version):
            raise ValueError("Update manifest has an invalid version.")
        if channel not in UPDATE_CHANNELS:
            raise ValueError("Update manifest has an invalid channel.")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("Update manifest requires a SHA-256 checksum.")
        if not url:
            raise ValueError("Update manifest requires a package URL.")
        return cls(
            version,
            channel,
            url,
            sha256,
            size,
            str(value.get("releaseNotes", ""))[:100_000],
            str(value.get("publishedAt", ""))[:100],
            str(value.get("minimumVersion", ""))[:64],
        )


class UpdateService:
    def __init__(
        self,
        directory: str | os.PathLike[str],
        approvals: ExactApprovalManager,
    ):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.staging = self.directory / "staging"
        self.staging.mkdir(exist_ok=True)
        self.state_path = self.directory / "updates.json"
        self.approvals = approvals
        self._lock = threading.RLock()
        try:
            self._state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            self._state = {
                "channel": "stable",
                "history": [],
                "pending": {},
                "rollback": {},
            }

    @property
    def channel(self) -> str:
        return str(self._state.get("channel", "stable"))

    def set_channel(self, channel: str) -> None:
        clean = channel.casefold()
        if clean not in UPDATE_CHANNELS:
            raise ValueError("Update channel must be stable or beta.")
        with self._lock:
            self._state["channel"] = clean
            self._save()

    def stage_local(
        self,
        source: str | os.PathLike[str],
        manifest_value: dict[str, Any],
    ) -> Path:
        manifest = UpdateManifest.from_value(manifest_value)
        package = Path(source).expanduser().resolve()
        if not package.is_file():
            raise FileNotFoundError(str(package))
        if package.suffix.casefold() not in {".zip", ".exe"}:
            raise ValueError("Updates must be a portable .zip or installer .exe.")
        self._verify(package, manifest)
        destination = self.staging / f"MORICE-{manifest.version}{package.suffix}"
        temporary = destination.with_name(
            destination.name + f".{uuid.uuid4().hex}.tmp"
        )
        try:
            if package != destination.resolve():
                shutil.copy2(package, temporary)
                os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        self._record_staged(destination, manifest)
        return destination

    def _record_staged(
        self,
        destination: Path,
        manifest: UpdateManifest,
    ) -> None:
        with self._lock:
            self._state["pending"] = {
                "manifest": asdict(manifest),
                "path": str(destination),
                "verifiedAt": _utc_now(),
                "status": "staged",
            }
            self._save()

    def download(
        self,
        manifest_value: dict[str, Any],
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        manifest = UpdateManifest.from_value(manifest_value)
        parsed_url = urllib.parse.urlparse(manifest.url)
        if parsed_url.scheme.casefold() != "https":
            raise ValueError("Remote updates must use HTTPS.")
        request = urllib.request.Request(
            manifest.url,
            headers={"User-Agent": f"MORICE/{__version__}"},
        )
        package_suffix = Path(parsed_url.path).suffix.casefold()
        if package_suffix not in {".zip", ".exe"}:
            raise ValueError("Update URL must point to a .zip or installer .exe.")
        destination = self.staging / f"MORICE-{manifest.version}{package_suffix}"
        temporary = destination.with_name(
            destination.name + f".{uuid.uuid4().hex}.tmp"
        )
        received = 0
        try:
            with urllib.request.urlopen(request, timeout=30) as response, temporary.open(
                "wb"
            ) as handle:
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > MAX_EXPORT_BYTES * 12:
                        raise ValueError("Update package exceeds the safety limit.")
                    handle.write(chunk)
                    if progress:
                        progress(received, manifest.size)
            self._verify(temporary, manifest)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        self._record_staged(destination, manifest)
        return destination

    def request_install(self) -> str:
        with self._lock:
            pending = dict(self._state.get("pending", {}))
        if pending.get("status") != "staged":
            raise RuntimeError("No verified update is staged.")
        arguments = {
            "path": pending.get("path", ""),
            "sha256": pending.get("manifest", {}).get("sha256", ""),
            "version": pending.get("manifest", {}).get("version", ""),
        }
        return self.approvals.request("update.install", arguments)

    def schedule_install(self, token: str) -> Path:
        with self._lock:
            pending = dict(self._state.get("pending", {}))
            arguments = {
                "path": pending.get("path", ""),
                "sha256": pending.get("manifest", {}).get("sha256", ""),
                "version": pending.get("manifest", {}).get("version", ""),
            }
            if not self.approvals.consume(token, "update.install", arguments):
                raise PermissionError("Update install needs exact one-use approval.")
            path = Path(str(arguments["path"]))
            manifest = UpdateManifest.from_value(dict(pending.get("manifest", {})))
            self._verify(path, manifest)
            instruction = self.directory / "pending-update.json"
            _atomic_json_write(
                instruction,
                {
                    "version": manifest.version,
                    "package": str(path),
                    "sha256": manifest.sha256,
                    "requestedAt": _utc_now(),
                    "status": "pending-restart",
                },
            )
            pending["status"] = "pending-restart"
            self._state["pending"] = pending
            self._save()
            return instruction

    def record_installed(self, version: str, package: str, rollback: str = "") -> None:
        with self._lock:
            history = list(self._state.get("history", ()))
            history.append(
                {
                    "version": version,
                    "package": package,
                    "installedAt": _utc_now(),
                }
            )
            self._state["history"] = history[-100:]
            self._state["rollback"] = {
                "path": rollback,
                "version": version,
            }
            self._state["pending"] = {}
            self._save()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    @staticmethod
    def _verify(path: Path, manifest: UpdateManifest) -> None:
        if manifest.size and path.stat().st_size != manifest.size:
            raise ValueError("Update size does not match its manifest.")
        digest = _sha256_file(path)
        if not hmac.compare_digest(digest, manifest.sha256):
            raise ValueError("Update checksum does not match its manifest.")

    def _save(self) -> None:
        _atomic_json_write(self.state_path, self._state)


class FirstRunService:
    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "first-run.json"
        self._cached: tuple[float, dict[str, Any]] | None = None

    def inspect(self, profile: GpuProfile | None = None) -> dict[str, Any]:
        if profile is None and self._cached and time.monotonic() - self._cached[0] < 30:
            return json.loads(json.dumps(self._cached[1]))
        gpu = profile or detect_gpu_profile()
        memory_mb = self._memory_mb()
        disk_free = shutil.disk_usage(self.directory).free
        recommendations = self._recommendations(gpu)
        result = {
            "complete": self.path.exists(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "gpu": {
                "name": gpu.name,
                "vramMb": gpu.vram_mb,
                "detected": gpu.detected,
                "source": gpu.source,
                "message": gpu.message,
            },
            "memoryMb": memory_mb,
            "diskFreeBytes": disk_free,
            "recommendedModels": recommendations,
            "optionalComponents": (
                "Wake listener",
                "Qt WebEngine browser",
                "Plugin SDK developer tools",
            ),
            "permissions": (
                "Workspace writes are previewed before approval.",
                "Desktop mutations use exact, expiring, one-use grants.",
                "Plugin permissions are reviewed per version.",
            ),
        }
        if profile is None:
            self._cached = (time.monotonic(), result)
        return json.loads(json.dumps(result))

    def complete(self, workspace: str, selections: dict[str, Any]) -> Path:
        target = Path(workspace).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        _atomic_json_write(
            self.path,
            {
                "version": 1,
                "completedAt": _utc_now(),
                "workspace": str(target),
                "selections": selections,
            },
        )
        self._cached = None
        return self.path

    @staticmethod
    def _recommendations(profile: GpuProfile) -> tuple[dict[str, Any], ...]:
        vram = profile.vram_mb
        lanes = [
            (0, 4_096, "3B Q4", "CPU or entry GPU"),
            (4_096, 6_144, "7B Q4", "CPU-assisted or partial GPU"),
            (6_144, 8_192, "7B Q4/Q5", "Good local default"),
            (8_192, 12_288, "8B-14B Q4", "Strong local reasoning"),
            (12_288, 24_576, "14B-32B Q4", "Large local models"),
            (24_576, 10**9, "32B+ quantized", "High-end local inference"),
        ]
        values = []
        for minimum, maximum, model, detail in lanes:
            fit = minimum <= vram < maximum if vram else minimum == 0
            values.append(
                {
                    "modelClass": model,
                    "vramRangeMb": (minimum, maximum if maximum < 10**9 else None),
                    "fit": fit,
                    "detail": detail,
                }
            )
        return tuple(values)

    @staticmethod
    def _memory_mb() -> int:
        try:
            import psutil  # type: ignore

            return int(psutil.virtual_memory().total / (1024 * 1024))
        except ImportError:
            pass
        if os.name == "nt":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys / (1024 * 1024))
        return 0


class RepairService:
    REQUIRED_FILES = (
        "morice/assets/morice_logo.ico",
        "morice/assets/morice-logo-rgb.png",
        "morice/assets/web/katex.min.js",
        "morice/assets/web/markdown-it.min.js",
    )

    def inspect(self, application_root: str | os.PathLike[str]) -> dict[str, Any]:
        root = Path(application_root).resolve()
        missing = [
            relative for relative in self.REQUIRED_FILES if not (root / relative).is_file()
        ]
        model_candidates = tuple(root.glob("*.gguf")) + tuple(
            (root / "morice" / "assets").glob("*.gguf")
            if (root / "morice" / "assets").is_dir()
            else ()
        )
        return {
            "root": str(root),
            "healthy": not missing,
            "missing": tuple(missing),
            "modelPresent": bool(model_candidates),
            "repairable": bool(missing),
            "detail": (
                "Copy missing signed release files from a matching MORICE package."
                if missing
                else "Core application assets are present."
            ),
        }


class ReleaseReadiness:
    def __init__(self, application_root: str | os.PathLike[str]):
        self.root = Path(application_root).resolve()

    def check(
        self,
        *,
        health: Any = None,
        plugins: dict[str, Any] | None = None,
        renderers: Iterable[dict[str, Any]] = (),
        tests: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checks: list[ReleaseCheck] = []
        critical_failures = getattr(health, "critical_failures", ())
        checks.append(
            ReleaseCheck(
                "Startup health",
                "passed" if not critical_failures else "failed",
                (
                    "No critical startup failures."
                    if not critical_failures
                    else f"{len(critical_failures)} critical startup failure(s)."
                ),
                critical=bool(critical_failures),
            )
        )
        repair = RepairService().inspect(self.root)
        checks.append(
            ReleaseCheck(
                "Core assets",
                "passed" if repair["healthy"] else "failed",
                repair["detail"],
                critical=not repair["healthy"],
            )
        )
        plugin_failures = int((plugins or {}).get("unhealthy", 0))
        checks.append(
            ReleaseCheck(
                "Plugins",
                "passed" if plugin_failures == 0 else "failed",
                f"{plugin_failures} unhealthy plugin(s).",
                critical=plugin_failures > 0,
            )
        )
        renderer_values = tuple(renderers)
        unavailable = [
            item.get("id", "unknown")
            for item in renderer_values
            if not item.get("available", False)
        ]
        checks.append(
            ReleaseCheck(
                "Renderers",
                "passed" if not unavailable else "warning",
                (
                    "All registered renderers are available."
                    if not unavailable
                    else "Unavailable: " + ", ".join(unavailable)
                ),
            )
        )
        test_value = tests or {}
        tests_passed = bool(test_value.get("passed", False))
        checks.append(
            ReleaseCheck(
                "Automated tests",
                "passed" if tests_passed else "not_run",
                str(test_value.get("detail", "Run the release test suite.")),
                critical=bool(test_value) and not tests_passed,
            )
        )
        installer = self.root / "installer" / "MORICE.iss"
        checks.append(
            ReleaseCheck(
                "Windows installer definition",
                "passed" if installer.is_file() else "failed",
                (
                    "Inno Setup definition is present."
                    if installer.is_file()
                    else "installer/MORICE.iss is missing."
                ),
                critical=not installer.is_file(),
            )
        )
        critical = [check for check in checks if check.critical and check.status != "passed"]
        return {
            "ready": not critical and tests_passed,
            "version": __version__,
            "checkedAt": _utc_now(),
            "checks": [check.to_dict() for check in checks],
            "criticalFailures": [check.name for check in critical],
        }


class PlatformServices:
    def __init__(
        self,
        directory: str | os.PathLike[str],
        agent: Any,
        *,
        application_root: str | os.PathLike[str],
        logger: Callable[..., Any] | None = None,
    ):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.application_root = Path(application_root).resolve()
        self.approvals = ExactApprovalManager()
        self.git = GitRepositoryService(self.approvals)
        self.vault = SecureVault(self.directory / "secure")
        self.backups = EncryptedBackupManager(self.vault)
        self.exports = ExportManager()
        self.updates = UpdateService(self.directory / "updates", self.approvals)
        self.first_run = FirstRunService(self.directory / "first-run")
        self.repair = RepairService()
        self.release = ReleaseReadiness(self.application_root)
        self.orchestrator = UnifiedPlatformOrchestrator(
            self.directory / "orchestrator",
            agent,
            git_service=self.git,
            logger=logger,
        )

    def snapshot(
        self,
        *,
        project_root: str = "",
        workspace: Any = None,
        performance: dict[str, Any] | None = None,
        health: Any = None,
        plugins: dict[str, Any] | None = None,
        renderers: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        return {
            **self.orchestrator.snapshot(
                project_root=project_root,
                workspace=workspace,
                performance=performance,
            ),
            "updates": self.updates.snapshot(),
            "firstRun": self.first_run.inspect(),
            "secureStorage": {
                "available": self.vault.available,
                "keys": len(self.vault.keys()),
            },
            "repair": self.repair.inspect(self.application_root),
            "release": self.release.check(
                health=health,
                plugins=plugins,
                renderers=renderers,
            ),
        }

    def shutdown(self) -> None:
        self.orchestrator.shutdown()
