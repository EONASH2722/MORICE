from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .unified_intelligence import CapabilityState


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class HostProfile:
    platform: str
    version: str
    architecture: str
    machine: str
    processor: str
    logical_cpu_count: int
    python: str
    shells: tuple[str, ...]
    package_managers: tuple[str, ...]
    storage_total_bytes: int
    storage_free_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdapterCapability:
    capability_id: str
    state: CapabilityState
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "capabilityId": self.capability_id,
            "state": self.state.value,
            "detail": self.detail,
        }


class PlatformAdapter:
    adapter_id = "generic"

    def __init__(self, *, environ: Mapping[str, str] | None = None):
        self.environ = dict(os.environ if environ is None else environ)

    def profile(self) -> HostProfile:
        shells = tuple(
            item
            for item in (
                shutil.which("pwsh"),
                shutil.which("powershell"),
                shutil.which("bash"),
                shutil.which("zsh"),
                shutil.which("sh"),
            )
            if item
        )
        managers = tuple(
            name
            for name in (
                "winget",
                "choco",
                "scoop",
                "apt",
                "dnf",
                "yum",
                "pacman",
                "brew",
                "pkg",
            )
            if shutil.which(name)
        )
        try:
            root = Path(Path.cwd().anchor or os.sep)
            storage = shutil.disk_usage(root)
            total, free = int(storage.total), int(storage.free)
        except OSError:
            total, free = 0, 0
        return HostProfile(
            platform=platform.system() or "Unknown",
            version=platform.version(),
            architecture=platform.machine(),
            machine=platform.node(),
            processor=platform.processor(),
            logical_cpu_count=os.cpu_count() or 1,
            python=sys.version.split()[0],
            shells=shells,
            package_managers=managers,
            storage_total_bytes=total,
            storage_free_bytes=free,
        )

    def capabilities(self) -> tuple[AdapterCapability, ...]:
        return (
            AdapterCapability("system.profile", CapabilityState.AVAILABLE),
            AdapterCapability("terminal.run", CapabilityState.AVAILABLE),
            AdapterCapability("browser.open", CapabilityState.AVAILABLE),
            AdapterCapability(
                "privileged.helper",
                CapabilityState.PERMISSION_REQUIRED,
                "Elevation must use the host operating system's supported authorization flow.",
            ),
        )

    def run_command(
        self,
        arguments: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        command = [str(item) for item in arguments]
        if not command or not command[0].strip():
            raise ValueError("A direct executable argument list is required.")
        completed = subprocess.run(
            command,
            cwd=str(Path(cwd).resolve()) if cwd else None,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=max(0.1, min(3_600.0, float(timeout))),
            check=False,
            shell=False,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return {
            "success": completed.returncode == 0,
            "verified": True,
            "exitCode": completed.returncode,
            "stdout": completed.stdout[-250_000:],
            "stderr": completed.stderr[-250_000:],
        }

    def open_url(self, url: str) -> dict[str, Any]:
        clean = str(url or "").strip()
        if not clean.startswith(("http://", "https://")):
            raise ValueError("Only HTTP and HTTPS URLs are supported.")
        accepted = bool(webbrowser.open(clean, new=2, autoraise=False))
        return {
            "success": accepted,
            "verified": accepted,
            "url": clean,
            "detail": "The host accepted the URL." if accepted else "The host rejected the URL.",
        }


class WindowsAdapter(PlatformAdapter):
    adapter_id = "windows"

    def capabilities(self) -> tuple[AdapterCapability, ...]:
        return super().capabilities() + (
            AdapterCapability("windows.media_sessions", CapabilityState.AVAILABLE),
            AdapterCapability("windows.window_control", CapabilityState.AVAILABLE),
            AdapterCapability(
                "windows.uac_helper",
                CapabilityState.PERMISSION_REQUIRED,
                "UAC approval is required for elevated operations.",
            ),
        )


class LinuxAdapter(PlatformAdapter):
    adapter_id = "linux"

    def capabilities(self) -> tuple[AdapterCapability, ...]:
        desktop = bool(
            self.environ.get("WAYLAND_DISPLAY") or self.environ.get("DISPLAY")
        )
        return super().capabilities() + (
            AdapterCapability(
                "linux.desktop_control",
                CapabilityState.AVAILABLE if desktop else CapabilityState.UNAVAILABLE,
                "No graphical desktop session was detected." if not desktop else "",
            ),
            AdapterCapability(
                "linux.polkit_helper",
                CapabilityState.PERMISSION_REQUIRED,
                "polkit or sudo authorization is required.",
            ),
        )


class MacOSAdapter(PlatformAdapter):
    adapter_id = "macos"

    def capabilities(self) -> tuple[AdapterCapability, ...]:
        return super().capabilities() + (
            AdapterCapability(
                "macos.accessibility",
                CapabilityState.PERMISSION_REQUIRED,
                "macOS Accessibility permission is required.",
            ),
            AdapterCapability(
                "macos.automation",
                CapabilityState.PERMISSION_REQUIRED,
                "macOS Automation permission is required.",
            ),
        )


class AndroidAdapter(PlatformAdapter):
    adapter_id = "android"

    def capabilities(self) -> tuple[AdapterCapability, ...]:
        companion = bool(self.environ.get("MORICE_ANDROID_COMPANION"))
        return super().capabilities() + (
            AdapterCapability(
                "android.companion",
                CapabilityState.AVAILABLE if companion else CapabilityState.PERMISSION_REQUIRED,
                "An explicitly authorized MORICE companion or ADB session is required."
                if not companion
                else "",
            ),
        )


class GenericPosixAdapter(PlatformAdapter):
    adapter_id = "posix"


def select_platform_adapter(
    system: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> PlatformAdapter:
    environment = os.environ if environ is None else environ
    detected = (system or platform.system()).strip().casefold()
    if environment.get("ANDROID_ROOT") or environment.get("ANDROID_DATA"):
        return AndroidAdapter(environ=environment)
    if detected == "windows":
        return WindowsAdapter(environ=environment)
    if detected == "linux":
        return LinuxAdapter(environ=environment)
    if detected in {"darwin", "macos"}:
        return MacOSAdapter(environ=environment)
    if os.name == "posix":
        return GenericPosixAdapter(environ=environment)
    return PlatformAdapter(environ=environment)


__all__ = [
    "AdapterCapability",
    "AndroidAdapter",
    "GenericPosixAdapter",
    "HostProfile",
    "LinuxAdapter",
    "MacOSAdapter",
    "PlatformAdapter",
    "WindowsAdapter",
    "select_platform_adapter",
]
