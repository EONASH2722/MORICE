from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from morice.platform_services import SecureVault


APP_VERSION = "0.8.0-android"
KEY_ALIAS = "morice-android"


def _run(command: list[str], *, cwd: Path, environment: dict[str, str]) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        text=True,
    )
    if completed.returncode:
        raise SystemExit(completed.returncode)


def _java_home() -> Path:
    configured = os.environ.get("JAVA_HOME", "").strip()
    candidates = [
        Path(configured) if configured else Path("missing"),
        Path(r"C:\Program Files\Android\openjdk\jdk-21.0.8"),
        Path(r"C:\Program Files\Android\Android Studio\jbr"),
    ]
    for candidate in candidates:
        if (candidate / "bin" / "keytool.exe").is_file():
            return candidate
    raise SystemExit("A JDK with keytool is required to sign MORICE Android.")


def _android_sdk(repo: Path) -> Path:
    configured = (
        os.environ.get("ANDROID_SDK_ROOT", "").strip()
        or os.environ.get("ANDROID_HOME", "").strip()
    )
    candidates = [
        Path(configured) if configured else Path("missing"),
        repo.drive + r"\QC-OS-Data\Android\Sdk",
    ]
    for value in candidates:
        candidate = Path(value)
        if (candidate / "platform-tools" / "adb.exe").is_file():
            return candidate
    raise SystemExit("Android SDK not found. Set ANDROID_SDK_ROOT.")


def _apksigner(sdk: Path) -> Path:
    candidates = sorted(
        sdk.glob("build-tools/*/apksigner.bat"),
        key=lambda path: tuple(int(part) if part.isdigit() else 0 for part in path.parent.name.split(".")),
        reverse=True,
    )
    if not candidates:
        raise SystemExit("Android apksigner was not found in the selected SDK.")
    return candidates[0]


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    data_root = Path(
        os.environ.get("MORICE_LOCAL_DATA_DIR", "").strip()
        or (Path(repo.drive + "\\") / "MORICE_DATA")
    ).resolve()
    signing = data_root / "android-signing"
    signing.mkdir(parents=True, exist_ok=True)
    vault = SecureVault(signing / "vault")
    password = vault.get("android-release-password")
    if not password:
        password = secrets.token_urlsafe(36)
        vault.set("android-release-password", password)
    keystore = signing / "morice-release.p12"
    java_home = _java_home()
    sdk = _android_sdk(repo)
    environment = dict(os.environ)
    environment.update(
        {
            "JAVA_HOME": str(java_home),
            "ANDROID_HOME": str(sdk),
            "ANDROID_SDK_ROOT": str(sdk),
            "MORICE_ANDROID_KEYSTORE": str(keystore),
            "MORICE_ANDROID_KEY_ALIAS": KEY_ALIAS,
            "MORICE_ANDROID_STORE_PASSWORD": password,
            "MORICE_ANDROID_KEY_PASSWORD": password,
        }
    )
    if not keystore.is_file():
        _run(
            [
                str(java_home / "bin" / "keytool.exe"),
                "-genkeypair",
                "-storetype",
                "PKCS12",
                "-keystore",
                str(keystore),
                "-alias",
                KEY_ALIAS,
                "-keyalg",
                "RSA",
                "-keysize",
                "4096",
                "-validity",
                "10000",
                "-dname",
                "CN=MORICE Android, OU=MORICE, O=MORICE, C=IN",
                "-storepass",
                password,
                "-keypass",
                password,
            ],
            cwd=repo,
            environment=environment,
        )
    gradle = repo / "android" / "gradlew.bat"
    _run(
        [str(gradle), "--no-daemon", "lintRelease", "assembleRelease"],
        cwd=repo / "android",
        environment=environment,
    )
    source = repo / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
    if not source.is_file():
        raise SystemExit("Gradle completed without producing the signed release APK.")
    _run(
        [str(_apksigner(sdk)), "verify", "--verbose", "--print-certs", str(source)],
        cwd=repo,
        environment=environment,
    )
    release = repo / "release"
    release.mkdir(parents=True, exist_ok=True)
    target = release / f"MORICE-Android-{APP_VERSION}.apk"
    shutil.copy2(source, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = release / f"MORICE-Android-{APP_VERSION}.json"
    manifest.write_text(
        json.dumps(
            {
                "version": APP_VERSION,
                "file": target.name,
                "bytes": target.stat().st_size,
                "sha256": digest,
                "signed": True,
                "keyAlias": KEY_ALIAS,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"apk": str(target), "bytes": target.stat().st_size, "sha256": digest}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
