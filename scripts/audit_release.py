from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile


FORBIDDEN_PARTS = {
    ".pytest_cache",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
    "node_modules",
    "release",
    "tests",
}
FORBIDDEN_SUFFIXES = {".gguf", ".log", ".pyc", ".pyo"}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "ElevenLabs-style key": re.compile(r"\bsk_[A-Za-z0-9_-]{20,}\b"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unsafe_member(name: str, *, allow_tests: bool = False) -> str | None:
    path = PurePosixPath(name)
    if path.name.casefold() == ".env":
        return "runtime secret file '.env'"
    hidden_directories = [
        part for part in path.parts[:-1] if part.startswith(".") and part != ".github"
    ]
    if hidden_directories:
        return f"forbidden hidden directory {hidden_directories[0]!r}"
    parts = {part.lower() for part in path.parts}
    forbidden = set(FORBIDDEN_PARTS)
    if allow_tests:
        forbidden.discard("tests")
    hit = sorted(parts.intersection(forbidden))
    if hit:
        return f"forbidden path component {hit[0]!r}"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return f"forbidden suffix {path.suffix.lower()!r}"
    return None


def _scan_text(name: str, payload: bytes) -> list[str]:
    if len(payload) > 4 * 1024 * 1024 or b"\0" in payload[:4096]:
        return []
    text = payload.decode("utf-8", errors="ignore")
    return [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(text)]


def _audit_zip(path: Path, *, allow_tests: bool = False) -> dict[str, object]:
    unsafe: list[str] = []
    secrets: list[str] = []
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError(f"{path.name} failed ZIP integrity at {bad_member}")
        members = [item for item in archive.infolist() if not item.is_dir()]
        for item in members:
            reason = _unsafe_member(item.filename, allow_tests=allow_tests)
            if reason:
                unsafe.append(f"{item.filename}: {reason}")
            if item.file_size <= 4 * 1024 * 1024:
                for label in _scan_text(item.filename, archive.read(item)):
                    secrets.append(f"{item.filename}: {label}")
    return {
        "format": "zip",
        "files": len(members),
        "uncompressedBytes": sum(item.file_size for item in members),
        "unsafeMembers": unsafe,
        "possibleSecrets": secrets,
    }


def _audit_tar(path: Path, *, allow_tests: bool = False) -> dict[str, object]:
    unsafe: list[str] = []
    secrets: list[str] = []
    with tarfile.open(path, "r:gz") as archive:
        members = [item for item in archive.getmembers() if item.isfile()]
        for item in members:
            reason = _unsafe_member(item.name, allow_tests=allow_tests)
            if reason:
                unsafe.append(f"{item.name}: {reason}")
            if item.size <= 4 * 1024 * 1024:
                handle = archive.extractfile(item)
                if handle:
                    for label in _scan_text(item.name, handle.read()):
                        secrets.append(f"{item.name}: {label}")
    return {
        "format": "tar.gz",
        "files": len(members),
        "uncompressedBytes": sum(item.size for item in members),
        "unsafeMembers": unsafe,
        "possibleSecrets": secrets,
    }


def _verify_parts(release: Path) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for manifest_path in sorted(release.glob("*.parts.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        errors: list[str] = []
        combined = hashlib.sha256()
        combined_bytes = 0
        for part in manifest.get("parts", []):
            part_path = release / str(part["name"])
            if not part_path.is_file():
                errors.append(f"missing {part_path.name}")
                continue
            actual_hash = _sha256(part_path)
            if actual_hash != str(part["sha256"]).lower():
                errors.append(f"hash mismatch for {part_path.name}")
            if part_path.stat().st_size != int(part["bytes"]):
                errors.append(f"size mismatch for {part_path.name}")
            with part_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                    combined.update(chunk)
                    combined_bytes += len(chunk)
        if combined.hexdigest() != str(manifest.get("sha256", "")).lower():
            errors.append("combined SHA-256 mismatch")
        if combined_bytes != int(manifest.get("bytes", -1)):
            errors.append("combined size mismatch")
        reports.append(
            {
                "manifest": manifest_path.name,
                "parts": len(manifest.get("parts", [])),
                "combinedBytes": combined_bytes,
                "errors": errors,
            }
        )
    return reports


def _verify_checksums(release: Path) -> list[str]:
    path = release / "checksums.json"
    if not path.is_file():
        return ["checksums.json is missing"]
    entries = json.loads(path.read_text(encoding="utf-8-sig"))
    errors: list[str] = []
    for entry in entries:
        asset = release / str(entry["Name"])
        if not asset.is_file():
            errors.append(f"checksum asset missing: {asset.name}")
            continue
        if asset.stat().st_size != int(entry["Bytes"]):
            errors.append(f"checksum size mismatch: {asset.name}")
        if _sha256(asset) != str(entry["SHA256"]).lower():
            errors.append(f"checksum mismatch: {asset.name}")
    return errors


def audit_release(release: Path, version: str, verify_checksums: bool) -> dict[str, object]:
    release = release.resolve()
    reports: list[dict[str, object]] = []
    errors: list[str] = []
    for path in sorted(release.iterdir()):
        if not path.is_file() or path.name in {"checksums.json", "SHA256SUMS.txt"}:
            continue
        item: dict[str, object] = {
            "name": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        try:
            if path.suffix.lower() in {".zip", ".whl"}:
                allow_tests = "source" in path.name.lower()
                item.update(_audit_zip(path, allow_tests=allow_tests))
            elif path.name.endswith(".tar.gz"):
                item.update(_audit_tar(path, allow_tests=True))
        except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
            errors.append(f"{path.name}: {exc}")
        reports.append(item)
        errors.extend(
            f"{path.name}: {problem}"
            for problem in item.get("unsafeMembers", [])
        )
        errors.extend(
            f"{path.name}: possible {problem}"
            for problem in item.get("possibleSecrets", [])
        )

    part_reports = _verify_parts(release)
    for report in part_reports:
        errors.extend(
            f"{report['manifest']}: {problem}" for problem in report["errors"]
        )
    if verify_checksums:
        errors.extend(_verify_checksums(release))
    if not any(version in report["name"] for report in reports):
        errors.append(f"no release asset contains version {version}")
    return {
        "schema": "morice.release-audit.v1",
        "version": version,
        "assets": reports,
        "splitAssets": part_reports,
        "errors": errors,
        "status": "passed" if not errors else "failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit MORICE release assets.")
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-checksums", action="store_true")
    arguments = parser.parse_args()
    report = audit_release(
        arguments.release,
        arguments.version,
        arguments.verify_checksums,
    )
    payload = json.dumps(report, indent=2)
    if arguments.report:
        arguments.report.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
