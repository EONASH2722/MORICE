"""Owned staging and baseline checks reuse the existing atomic patch provider."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
from pathlib import Path
from ..redaction import redact_data as redact_diagnostics, redact_text


def redact_data(value):
    # Build checkpoints contain filename-indexed hashes, including legitimate
    # names such as tokenizer.py. Preserve those structural keys and values.
    return redact_diagnostics(value, redact_keys=False)


IGNORED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".morice-build", "dist", "build", ".gradle", "target"}
SECRET_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", "credentials.json", "secrets.json", "secrets.txt", ".npmrc", ".pypirc"}


def secret_path(path):
    value = Path(path)
    return value.name.casefold() in SECRET_NAMES or any(p.casefold() in {".ssh",".aws",".gnupg"} for p in value.parts) or value.name.casefold().startswith(".env.") or value.suffix.casefold() in {".pem", ".key", ".p12", ".pfx"}


def safe_path(root, relative):
    root = Path(root).resolve()
    value = str(relative).replace("\\", "/")
    if not value or Path(value).is_absolute() or ":" in value or any(p in {"..", ""} for p in value.split("/")):
        raise ValueError("Project path must stay inside its authorized root.")
    if any(part.rstrip(" .") != part or part.split(".")[0].casefold() in {"con","prn","aux","nul",*(f"com{i}" for i in range(1,10)),*(f"lpt{i}" for i in range(1,10))} for part in value.split("/")):
        raise ValueError("Project path selects a Windows device or an ambiguous filename.")
    target = (root / value).resolve()
    if not target.is_relative_to(root) or any(p.casefold() in IGNORED for p in Path(value).parts) or secret_path(value):
        raise ValueError("Project path escapes scope or selects protected/generated data.")
    return target


def baseline(path):
    path = Path(path)
    if path.exists() and not path.is_file():
        raise ValueError("Patch target is not a regular file.")
    return {"expected_exists": True, "expected_sha256": hashlib.sha256(path.read_bytes()).hexdigest()} if path.is_file() else {"expected_exists": False}


def owned_area(root, session_id, *parts):
    root=Path(root).resolve()
    if not re.fullmatch(r"[a-f0-9]{32}",session_id):
        raise ValueError("Invalid staging session identity.")
    area=root/".morice-build"/session_id
    target=area.joinpath(*parts).resolve()
    if not target.is_relative_to(root) or not target.is_relative_to(area.resolve()):
        raise ValueError("Owned project cache escapes its authorized root.")
    return target


def normalize_changes(root, files, limits):
    if not files or len(files) > limits.max_files:
        raise ValueError("Generated file count exceeds the project budget.")
    from ..project_runtime import validate_project_file
    result, seen = [], set()
    for item in files:
        name, content = str(item["path"]).replace("\\", "/"), item["content"]
        target = safe_path(root, name)
        key = os.path.normcase(str(target))
        if key in seen or not isinstance(content, str) or len(content.encode("utf-8")) > limits.max_file_bytes:
            raise ValueError("Duplicate path or invalid/oversized source content.")
        seen.add(key)
        if "PRIVATE KEY-----" in content or any(len(secret) >= 8 and secret in content for key, secret in os.environ.items() if re.search(r"(?i)token|secret|password|api.?key", key)):
            raise ValueError("Generated source contains private credential material.")
        if re.search(r"(?i)(?:api[_-]?key|password|secret|token)[\"']?\s*[:=]\s*[\"'][^\"'\r\n]{8,}[\"']", content):
            raise ValueError("Hardcoded credentials must be moved to user-managed secret configuration.")
        validate_project_file(name, content)
        result.append({"path": name, "content": content, **baseline(target)})
    return result


def assign_owners(changes, ownership=None):
    owners = {}
    for change in changes:
        name = change["path"]
        if ownership:
            matches = [worker for worker, patterns in ownership.items() if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)]
            if len(matches) != 1:
                raise ValueError(f"Exactly one worker must own {name}.")
            worker = matches[0]
        elif name.startswith("tests/") or Path(name).name.startswith("test_"):
            worker = "tests"
        elif name.startswith(("backend/", "api/")) or Path(name).suffix == ".py":
            worker = "backend"
        elif name.startswith(("frontend/", "src/")) or Path(name).suffix in {".html", ".css", ".js", ".tsx", ".jsx"}:
            worker = "frontend"
        else:
            worker = "integration"
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,40}", worker) or worker.casefold() in {"con", "prn", "aux", "nul"}:
            raise ValueError("Worker ownership identifiers must be safe directory names.")
        owners.setdefault(worker, []).append(name)
    if len(owners) > 8:
        raise ValueError("Coding ownership exceeds worker scope budget.")
    if len({v.casefold() for v in owners}) != len(owners):
        raise ValueError("Worker staging identities overlap on Windows.")
    return owners


def copy_relevant(root, stage, limits):
    root, stage = Path(root).resolve(), Path(stage).resolve()
    if stage.exists():
        raise ValueError("A staging workspace must be new.")
    stage.mkdir(parents=True)
    size, count = 0, 0
    for directory, names, files in os.walk(root):
        names[:] = [n for n in names if n.casefold() not in IGNORED and not Path(directory, n).is_symlink()]
        for name in files:
            source = Path(directory, name)
            if source.is_symlink() or secret_path(source) or source.stat().st_size > limits.max_file_bytes:
                continue
            size += source.stat().st_size; count += 1
            if size > limits.max_workspace_bytes or count > 6000:
                raise ValueError("Relevant staging copy exceeds its budget.")
            target = stage / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def clean_owned_stage(directory, allowed_directory):
    directory, allowed = Path(directory).resolve(), Path(allowed_directory).resolve()
    if not directory.is_relative_to(allowed) or directory == allowed:
        raise ValueError("Cleanup target is outside the owned staging area.")
    if directory.is_dir():
        shutil.rmtree(directory)
