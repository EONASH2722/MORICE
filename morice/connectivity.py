from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ConnectivityState(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NetworkSnapshot:
    state: ConnectivityState
    checked_at: float
    interface_addresses: tuple[str, ...]
    probe_host: str
    latency_ms: float | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "checkedAt": self.checked_at,
            "interfaceAddresses": list(self.interface_addresses),
            "probeHost": self.probe_host,
            "latencyMs": self.latency_ms,
            "error": self.error,
        }


class NetworkManager:
    """Fast, bounded connectivity observation with a short-lived cache."""

    def __init__(
        self,
        *,
        probe_host: str = "1.1.1.1",
        probe_port: int = 443,
        cache_seconds: float = 15.0,
        connector: Callable[..., Any] = socket.create_connection,
    ):
        self.probe_host = probe_host
        self.probe_port = int(probe_port)
        self.cache_seconds = max(0.0, float(cache_seconds))
        self._connector = connector
        self._cached: NetworkSnapshot | None = None
        self._lock = threading.RLock()

    @staticmethod
    def local_addresses() -> tuple[str, ...]:
        addresses: set[str] = set()
        try:
            records = socket.getaddrinfo(socket.gethostname(), None)
        except OSError:
            records = ()
        for record in records:
            try:
                address = str(record[4][0]).split("%", 1)[0]
            except (IndexError, TypeError):
                continue
            if address and address not in {"0.0.0.0", "::"}:
                addresses.add(address)
        return tuple(sorted(addresses))

    def observe(self, *, timeout: float = 0.35, force: bool = False) -> NetworkSnapshot:
        now = time.monotonic()
        with self._lock:
            if (
                not force
                and self._cached is not None
                and now - self._cached.checked_at < self.cache_seconds
            ):
                return self._cached
        started = time.perf_counter()
        error = ""
        state = ConnectivityState.OFFLINE
        try:
            connection = self._connector(
                (self.probe_host, self.probe_port),
                timeout=max(0.05, min(3.0, float(timeout))),
            )
            close = getattr(connection, "close", None)
            if callable(close):
                close()
            state = ConnectivityState.ONLINE
        except OSError as exc:
            error = str(exc)[:300]
        snapshot = NetworkSnapshot(
            state=state,
            checked_at=now,
            interface_addresses=self.local_addresses(),
            probe_host=self.probe_host,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
            error=error,
        )
        with self._lock:
            self._cached = snapshot
        return snapshot

    def snapshot(self) -> NetworkSnapshot:
        with self._lock:
            if self._cached is not None:
                return self._cached
        return NetworkSnapshot(
            state=ConnectivityState.UNKNOWN,
            checked_at=0.0,
            interface_addresses=self.local_addresses(),
            probe_host=self.probe_host,
        )


@dataclass(frozen=True)
class BluetoothDeviceInfo:
    device_id: str
    name: str
    status: str
    class_name: str = "Bluetooth"
    paired: bool | None = None
    connected: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BluetoothSnapshot:
    supported: bool
    provider: str
    devices: tuple[BluetoothDeviceInfo, ...]
    checked_at: float
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "provider": self.provider,
            "devices": [item.to_dict() for item in self.devices],
            "checkedAt": self.checked_at,
            "error": self.error,
        }


class BluetoothProvider(Protocol):
    provider_id: str

    def discover(self, timeout: float) -> BluetoothSnapshot: ...


class UnsupportedBluetoothProvider:
    provider_id = "unsupported"

    def discover(self, timeout: float = 5.0) -> BluetoothSnapshot:
        del timeout
        return BluetoothSnapshot(
            supported=False,
            provider=self.provider_id,
            devices=(),
            checked_at=time.time(),
            error="No supported native Bluetooth discovery adapter is installed.",
        )


class WindowsBluetoothProvider:
    """Read-only Windows PnP discovery; pairing/control remains explicit."""

    provider_id = "windows-pnp"

    _SCRIPT = (
        "$ErrorActionPreference='Stop';"
        "$items=Get-PnpDevice -Class Bluetooth | Select-Object InstanceId,FriendlyName,Status,Class;"
        "$items | ConvertTo-Json -Compress"
    )

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        powershell: str | None = None,
    ):
        self._runner = runner
        self._powershell = powershell or "powershell.exe"

    def discover(self, timeout: float = 5.0) -> BluetoothSnapshot:
        checked_at = time.time()
        try:
            completed = self._runner(
                [
                    self._powershell,
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    self._SCRIPT,
                ],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=max(0.5, min(20.0, float(timeout))),
                check=False,
                shell=False,
                creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return BluetoothSnapshot(True, self.provider_id, (), checked_at, str(exc)[:500])
        if completed.returncode != 0:
            return BluetoothSnapshot(
                True,
                self.provider_id,
                (),
                checked_at,
                (completed.stderr or "Bluetooth discovery failed.")[-500:],
            )
        raw = completed.stdout.strip()
        if not raw:
            values: Sequence[Mapping[str, Any]] = ()
        else:
            try:
                decoded = json.loads(raw)
                values = decoded if isinstance(decoded, list) else [decoded]
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                return BluetoothSnapshot(True, self.provider_id, (), checked_at, str(exc)[:500])
        devices: list[BluetoothDeviceInfo] = []
        for value in values:
            if not isinstance(value, Mapping):
                continue
            device_id = str(value.get("InstanceId") or "").strip()
            name = str(value.get("FriendlyName") or device_id or "Bluetooth device").strip()
            status = str(value.get("Status") or "Unknown").strip()
            if device_id:
                devices.append(
                    BluetoothDeviceInfo(
                        device_id=device_id,
                        name=name,
                        status=status,
                        class_name=str(value.get("Class") or "Bluetooth"),
                        # PnP Status=OK means the device node/driver is healthy;
                        # Windows does not guarantee it is actively connected.
                        connected=None,
                    )
                )
        devices.sort(key=lambda item: (item.name.casefold(), item.device_id.casefold()))
        return BluetoothSnapshot(True, self.provider_id, tuple(devices), checked_at)


class BluetoothManager:
    def __init__(
        self,
        provider: BluetoothProvider | None = None,
        *,
        system: str | None = None,
        cache_seconds: float = 20.0,
    ):
        detected = (system or platform.system()).casefold()
        self.provider = provider or (
            WindowsBluetoothProvider()
            if detected == "windows"
            else UnsupportedBluetoothProvider()
        )
        self.cache_seconds = max(0.0, float(cache_seconds))
        self._cached: BluetoothSnapshot | None = None
        self._lock = threading.RLock()

    def discover(self, *, timeout: float = 5.0, force: bool = False) -> BluetoothSnapshot:
        now = time.time()
        with self._lock:
            if (
                not force
                and self._cached is not None
                and now - self._cached.checked_at < self.cache_seconds
            ):
                return self._cached
        result = self.provider.discover(timeout)
        with self._lock:
            self._cached = result
        return result

    def snapshot(self) -> BluetoothSnapshot:
        with self._lock:
            if self._cached is not None:
                return self._cached
        supported = not isinstance(self.provider, UnsupportedBluetoothProvider)
        return BluetoothSnapshot(
            supported=supported,
            provider=self.provider.provider_id,
            devices=(),
            checked_at=0.0,
            error="Discovery has not run yet." if supported else "Bluetooth is unsupported.",
        )


__all__ = [
    "BluetoothDeviceInfo",
    "BluetoothManager",
    "BluetoothProvider",
    "BluetoothSnapshot",
    "ConnectivityState",
    "NetworkManager",
    "NetworkSnapshot",
    "UnsupportedBluetoothProvider",
    "WindowsBluetoothProvider",
]
