"""Small real build/check tools run as owned subprocesses, never success stubs."""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import re
import shutil
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path


EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".morice-build", "dist", "build", "target", ".ssh", ".aws", ".gnupg"}


def sources(root):
    import os
    for directory, names, files in os.walk(root):
        names[:] = [v for v in names if v.casefold() not in EXCLUDED and not Path(directory, v).is_symlink()]
        for name in sorted(files):
            path = Path(directory, name)
            if path.is_symlink() or name.casefold() in {"id_rsa", "id_ed25519", "credentials.json", "secrets.json", "secrets.txt", ".npmrc", ".pypirc"} or name.startswith(".env") or path.suffix in {".key", ".pem", ".pfx", ".p12"}:
                continue
            yield path


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.refs = []; self.controls = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "link", "img"}:
            self.refs.append(attrs.get("src", attrs.get("href", "")))
        if tag in {"button", "input", "select"}:
            self.controls += 1


def source_check(root, paths=None):
    count = 0
    for path in [root / v for v in paths] if paths else sources(root):
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Source check path escapes root.")
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        elif path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix == ".html":
            PageParser().feed(path.read_text(encoding="utf-8"))
        count += 1
    if not count:
        raise ValueError("No source files were checked.")
    return count


def dependencies(root):
    results = {}
    path = root / "requirements.txt"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:(==|>=|<=|>|<)([0-9.]+))?", line)
            if not match:
                raise ValueError("Dependency declaration requires explicit resolution: " + line)
            name, operator, wanted = match.groups()
            actual = importlib.metadata.version(name)
            if wanted:
                a, w = tuple(int(v) for v in actual.split(".") if v.isdigit()), tuple(int(v) for v in wanted.split("."))
                if not {"==": a == w, ">=": a >= w, "<=": a <= w, ">": a > w, "<": a < w}[operator]:
                    raise ValueError(f"Dependency version mismatch: {name}")
            results[name] = actual
    return {"resolved": True, "versions": results, "python": sys.version.split()[0]}


def build(root, kind):
    source_check(root)
    output = root / "dist"; output.mkdir(exist_ok=True)
    files = list(sources(root))
    if kind == "web":
        for source in files:
            if source.suffix not in {".html", ".css", ".js", ".mjs", ".json", ".svg", ".png", ".jpg", ".woff", ".woff2"}:
                continue
            target = output / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        if not (output / "index.html").is_file():
            raise ValueError("Web build has no index.html.")
    artifact = output / "project.zip"
    with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(root).as_posix())
    with zipfile.ZipFile(artifact) as archive:
        if not archive.namelist() or archive.testzip() is not None:
            raise ValueError("Build artifact failed ZIP verification.")
    return {"artifact": str(artifact), "bytes": artifact.stat().st_size, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}


def prepare_environment(root):
    import os
    import subprocess
    import venv
    declared = root / "requirements.txt"
    for line in declared.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and not re.fullmatch(r"[A-Za-z0-9_.-]+(?:(?:==|>=|<=|>|<)[0-9.]+)?", line.strip()):
            raise ValueError("Only explicit package/version declarations are automatically installed.")
    environment = root / ".venv"
    if environment.is_symlink() or not environment.resolve().is_relative_to(root):
        raise ValueError("Project environment is a symlink.")
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(environment)
    process = subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(declared)],
        cwd=root, capture_output=True, text=True, timeout=55)
    if process.returncode:
        raise RuntimeError("Project dependency installation failed: " + process.stderr[-2000:])
    return {"environment":str(environment),"installed":True,"installer_exit_code":process.returncode}


def web_test(root):
    path = root / "dist" / "index.html"
    parser = PageParser(); parser.feed(path.read_text(encoding="utf-8"))
    for ref in parser.refs:
        if ref and not ref.startswith(("http:", "https:", "data:", "#", "//")):
            target = (path.parent / ref.split("?")[0]).resolve()
            if not target.is_relative_to(path.parent.resolve()) or not target.is_file() or target.stat().st_size == 0:
                raise AssertionError("Missing/invalid local web asset: " + ref)
    return {"passed": True, "assets_checked": len(parser.refs), "controls": parser.controls}


def main():
    operation, root = sys.argv[1], Path(sys.argv[2]).resolve()
    if operation == "source-check":
        result = {"checked": source_check(root, sys.argv[3:])}
    elif operation == "dependencies":
        result = dependencies(root)
    elif operation == "prepare-env":
        result = prepare_environment(root)
    elif operation in {"web-build", "python-build"}:
        result = build(root, operation.split("-")[0])
    elif operation == "web-test":
        result = web_test(root)
    else:
        raise ValueError("Unsupported local build operation.")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
