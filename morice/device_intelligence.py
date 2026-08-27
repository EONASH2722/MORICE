from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from .unified_intelligence import (
    CapabilityOutcome,
    PermissionController,
    RiskClass,
)


class EnrollmentState(str, Enum):
    DISCOVERED = "discovered"
    PAIRED = "paired"
    AUTHORIZED = "authorized"
    ENROLLED = "enrolled"
    REVOKED = "revoked"


class OnlineState(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"
    FAILED = "failed"


class DeviceTransport(str, Enum):
    LOCAL = "local"
    USB = "usb"
    SERIAL = "serial"
    BLUETOOTH = "bluetooth"
    BLE = "ble"
    LAN = "lan"
    WIFI = "wifi"
    HTTP = "http"
    WEBSOCKET = "websocket"
    MQTT = "mqtt"
    MATTER = "matter"
    CUSTOM = "custom"


def _now() -> float:
    return time.time()


def _safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return str(value)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


@dataclass(frozen=True)
class CommandField:
    name: str
    value_type: str = "string"
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[Any, ...] = ()

    def validate(self, arguments: Mapping[str, Any]) -> str:
        if self.name not in arguments:
            return f"Missing required argument: {self.name}" if self.required else ""
        value = arguments[self.name]
        if self.value_type == "number" and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            return f"{self.name} must be a number."
        if self.value_type == "integer" and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            return f"{self.name} must be an integer."
        if self.value_type == "boolean" and not isinstance(value, bool):
            return f"{self.name} must be a boolean."
        if self.value_type == "string" and not isinstance(value, str):
            return f"{self.name} must be a string."
        if self.choices and value not in self.choices:
            return f"{self.name} is not an allowed value."
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                return f"{self.name} is below its hard minimum of {self.minimum}."
            if self.maximum is not None and value > self.maximum:
                return f"{self.name} exceeds its hard maximum of {self.maximum}."
        return ""


@dataclass(frozen=True)
class SafetyConstraint:
    field: str
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: tuple[Any, ...] = ()
    detail: str = ""

    def validate(self, arguments: Mapping[str, Any]) -> str:
        if self.field not in arguments:
            return ""
        value = arguments[self.field]
        if self.allowed_values and value not in self.allowed_values:
            return self.detail or f"{self.field} violates the device safety policy."
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                return self.detail or (
                    f"{self.field} is below the device safety minimum {self.minimum}."
                )
            if self.maximum is not None and value > self.maximum:
                return self.detail or (
                    f"{self.field} exceeds the device safety maximum {self.maximum}."
                )
        return ""


@dataclass(frozen=True)
class VerificationRule:
    telemetry_key: str
    argument_key: str = ""
    expected: Any = None
    tolerance: float = 0.0

    def verify(self, arguments: Mapping[str, Any], telemetry: Mapping[str, Any]) -> bool:
        if self.telemetry_key not in telemetry:
            return False
        actual = telemetry[self.telemetry_key]
        expected = (
            arguments.get(self.argument_key)
            if self.argument_key
            else self.expected
        )
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return abs(float(actual) - float(expected)) <= max(0.0, self.tolerance)
        return actual == expected


@dataclass(frozen=True)
class DeviceCapability:
    capability_id: str
    commands: dict[str, tuple[CommandField, ...]]
    telemetry_keys: tuple[str, ...] = ()
    permission_group: str = "connected_devices"
    risk: RiskClass = RiskClass.LOW
    safety_constraints: tuple[SafetyConstraint, ...] = ()
    verification: dict[str, tuple[VerificationRule, ...]] = field(default_factory=dict)
    emergency_commands: tuple[str, ...] = ()

    def validate(self, command: str, arguments: Mapping[str, Any]) -> str:
        schema = self.commands.get(command)
        if schema is None:
            return f"Unsupported command {command!r} for {self.capability_id}."
        for item in schema:
            error = item.validate(arguments)
            if error:
                return error
        declared = {item.name for item in schema}
        unknown = sorted(set(arguments) - declared)
        if unknown:
            return "Unknown command arguments: " + ", ".join(unknown)
        for constraint in self.safety_constraints:
            error = constraint.validate(arguments)
            if error:
                return error
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilityId": self.capability_id,
            "commands": {
                key: [asdict(item) for item in value]
                for key, value in self.commands.items()
            },
            "telemetryKeys": list(self.telemetry_keys),
            "permissionGroup": self.permission_group,
            "risk": self.risk.value,
            "safetyConstraints": [asdict(item) for item in self.safety_constraints],
            "verification": {
                key: [asdict(item) for item in value]
                for key, value in self.verification.items()
            },
            "emergencyCommands": list(self.emergency_commands),
        }


@dataclass
class DeviceRecord:
    device_id: str
    display_name: str
    device_type: str
    platform: str
    transport: DeviceTransport
    driver: str
    location: str = ""
    connection: dict[str, Any] = field(default_factory=dict)
    enrollment: EnrollmentState = EnrollmentState.DISCOVERED
    online_state: OnlineState = OnlineState.UNKNOWN
    capabilities: dict[str, DeviceCapability] = field(default_factory=dict)
    authorized_capabilities: set[str] = field(default_factory=set)
    telemetry: dict[str, Any] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    last_seen: float = field(default_factory=_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def controllable(self) -> bool:
        return (
            self.enrollment == EnrollmentState.ENROLLED
            and self.online_state == OnlineState.ONLINE
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "deviceId": self.device_id,
            "displayName": self.display_name,
            "deviceType": self.device_type,
            "platform": self.platform,
            "transport": self.transport.value,
            "driver": self.driver,
            "location": self.location,
            "connection": _safe(self.connection),
            "enrollment": self.enrollment.value,
            "onlineState": self.online_state.value,
            "capabilities": {
                key: value.to_dict() for key, value in self.capabilities.items()
            },
            "authorizedCapabilities": sorted(self.authorized_capabilities),
            "telemetry": _safe(self.telemetry),
            "aliases": list(self.aliases),
            "lastSeen": self.last_seen,
            "metadata": _safe(self.metadata),
            "controllable": self.controllable,
        }


class DeviceRegistry:
    """Trust-gated device registry. Discovery never implies authorization."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path) if path else None
        self._devices: dict[str, DeviceRecord] = {}
        self._lock = threading.RLock()
        self._load()

    def discover(self, record: DeviceRecord) -> DeviceRecord:
        if not record.device_id or not record.display_name or not record.driver:
            raise ValueError("Discovered devices need id, name, and driver.")
        with self._lock:
            existing = self._devices.get(record.device_id)
            if existing and existing.enrollment in {
                EnrollmentState.PAIRED,
                EnrollmentState.AUTHORIZED,
                EnrollmentState.ENROLLED,
            }:
                record.enrollment = existing.enrollment
                record.authorized_capabilities = set(existing.authorized_capabilities)
            record.last_seen = _now()
            self._devices[record.device_id] = record
            self._save()
            return record

    def pair(self, device_id: str, *, user_confirmed: bool) -> DeviceRecord:
        if not user_confirmed:
            raise PermissionError("Pairing requires explicit user confirmation.")
        with self._lock:
            record = self._require(device_id)
            if record.enrollment == EnrollmentState.REVOKED:
                raise PermissionError("This device was revoked.")
            record.enrollment = EnrollmentState.PAIRED
            self._save()
            return record

    def authorize(
        self,
        device_id: str,
        capabilities: Iterable[str],
        *,
        user_confirmed: bool,
    ) -> DeviceRecord:
        if not user_confirmed:
            raise PermissionError("Device authorization requires explicit confirmation.")
        with self._lock:
            record = self._require(device_id)
            if record.enrollment not in {
                EnrollmentState.PAIRED,
                EnrollmentState.AUTHORIZED,
                EnrollmentState.ENROLLED,
            }:
                raise RuntimeError("The device must be paired before authorization.")
            requested = {str(item) for item in capabilities if str(item)}
            unknown = requested - set(record.capabilities)
            if unknown:
                raise ValueError(
                    "Device does not advertise capabilities: " + ", ".join(sorted(unknown))
                )
            record.authorized_capabilities = requested
            record.enrollment = EnrollmentState.AUTHORIZED
            self._save()
            return record

    def enroll(self, device_id: str) -> DeviceRecord:
        with self._lock:
            record = self._require(device_id)
            if record.enrollment != EnrollmentState.AUTHORIZED:
                raise PermissionError("Only an authorized device can be enrolled.")
            record.enrollment = EnrollmentState.ENROLLED
            self._save()
            return record

    def revoke(self, device_id: str) -> DeviceRecord:
        with self._lock:
            record = self._require(device_id)
            record.enrollment = EnrollmentState.REVOKED
            record.authorized_capabilities.clear()
            self._save()
            return record

    def update_state(
        self,
        device_id: str,
        *,
        online_state: OnlineState | str | None = None,
        telemetry: Mapping[str, Any] | None = None,
    ) -> DeviceRecord:
        with self._lock:
            record = self._require(device_id)
            if online_state is not None:
                record.online_state = OnlineState(online_state)
            if telemetry is not None:
                record.telemetry.update(_safe(telemetry))
            record.last_seen = _now()
            self._save()
            return record

    def get(self, device_id: str) -> DeviceRecord | None:
        with self._lock:
            return self._devices.get(device_id)

    def resolve(
        self,
        reference: str,
        *,
        active_device_id: str = "",
        location: str = "",
    ) -> tuple[DeviceRecord | None, tuple[DeviceRecord, ...]]:
        clean = " ".join(str(reference).casefold().split())
        with self._lock:
            values = tuple(self._devices.values())
        scored: list[tuple[float, DeviceRecord]] = []
        for device in values:
            if device.enrollment != EnrollmentState.ENROLLED:
                continue
            names = {
                device.device_id.casefold(),
                device.display_name.casefold(),
                device.device_type.casefold(),
                *(item.casefold() for item in device.aliases),
            }
            score = 0.0
            if clean in names:
                score += 0.65
            elif clean and any(clean in item or item in clean for item in names):
                score += 0.35
            if device.device_id == active_device_id:
                score += 0.35
            if location and device.location.casefold() == location.casefold():
                score += 0.15
            score += 0.12 if device.online_state == OnlineState.ONLINE else 0.0
            if score > 0:
                scored.append((min(1.0, score), device))
        scored.sort(key=lambda item: (-item[0], -item[1].last_seen, item[1].display_name))
        if not scored:
            return None, ()
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.12:
            return None, tuple(item[1] for item in scored[:3])
        return scored[0][1], tuple(item[1] for item in scored[1:3])

    def devices(self, *, enrolled_only: bool = False) -> tuple[DeviceRecord, ...]:
        with self._lock:
            values = tuple(self._devices.values())
        if enrolled_only:
            values = tuple(
                item for item in values if item.enrollment == EnrollmentState.ENROLLED
            )
        return tuple(sorted(values, key=lambda item: item.display_name.casefold()))

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.to_dict() for item in self.devices())

    def _require(self, device_id: str) -> DeviceRecord:
        record = self._devices.get(device_id)
        if record is None:
            raise KeyError(device_id)
        return record

    def _save(self) -> None:
        if self.path:
            _atomic_json(
                self.path,
                {"version": 1, "devices": [item.to_dict() for item in self._devices.values()]},
            )

    def _load(self) -> None:
        if not self.path:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return
        for item in payload.get("devices", ()):
            if not isinstance(item, Mapping):
                continue
            try:
                record = device_record_from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue
            self._devices[record.device_id] = record


@dataclass(frozen=True)
class DeviceCommandResult:
    accepted: bool
    output: Any = None
    error: str = ""
    retryable: bool = False
    verified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class DeviceAdapter(Protocol):
    adapter_id: str

    def command(
        self,
        device: DeviceRecord,
        capability_id: str,
        command: str,
        arguments: Mapping[str, Any],
    ) -> DeviceCommandResult: ...

    def telemetry(
        self,
        device: DeviceRecord,
        keys: Iterable[str],
    ) -> Mapping[str, Any]: ...

    def reconnect(self, device: DeviceRecord) -> bool: ...


class DeviceAdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, DeviceAdapter] = {}
        self._lock = threading.RLock()

    def register(self, adapter: DeviceAdapter) -> None:
        adapter_id = str(getattr(adapter, "adapter_id", "")).strip()
        if not adapter_id:
            raise ValueError("Device adapters need an adapter_id.")
        with self._lock:
            self._adapters[adapter_id] = adapter

    def adapter(self, adapter_id: str) -> DeviceAdapter | None:
        with self._lock:
            return self._adapters.get(adapter_id)


class DeviceController:
    """Structured physical/device execution with hard limits and observation."""

    def __init__(
        self,
        devices: DeviceRegistry,
        adapters: DeviceAdapterRegistry,
        permissions: PermissionController,
        *,
        max_reconnect_attempts: int = 1,
    ):
        self.devices = devices
        self.adapters = adapters
        self.permissions = permissions
        self.max_reconnect_attempts = max(0, min(3, int(max_reconnect_attempts)))

    def execute(
        self,
        *,
        task_id: str,
        device_id: str,
        capability_id: str,
        command: str,
        arguments: Mapping[str, Any] | None = None,
        approval_token: str = "",
    ) -> CapabilityOutcome:
        started = time.perf_counter()
        args = dict(arguments or {})
        device = self.devices.get(device_id)
        if device is None:
            return self._failure(started, "Device was not found.")
        if device.enrollment != EnrollmentState.ENROLLED:
            return self._failure(started, "Device is not enrolled and authorized.")
        if capability_id not in device.authorized_capabilities:
            return self._failure(started, "This device capability was not authorized.")
        capability = device.capabilities.get(capability_id)
        if capability is None:
            return self._failure(started, "Device does not advertise that capability.")
        error = capability.validate(command, args)
        if error:
            return self._failure(started, error)
        adapter = self.adapters.adapter(device.driver)
        if adapter is None:
            return self._failure(started, "No installed adapter can control this device.")
        operation_id = f"device.{device_id}.{capability_id}.{command}"
        emergency = command in capability.emergency_commands
        decision = self.permissions.authorize(
            task_id=task_id,
            capability_id=operation_id,
            arguments=args,
            permissions=(capability.permission_group,),
            risk=RiskClass.LOW if emergency else capability.risk,
            approval_token=approval_token,
        )
        if not decision.allowed:
            return self._failure(
                started,
                decision.reason,
                metadata={
                    "requiredPermissions": list(decision.required),
                    "deniedPermissions": list(decision.denied),
                },
            )
        if device.online_state != OnlineState.ONLINE:
            reconnected = False
            for _attempt in range(self.max_reconnect_attempts):
                try:
                    if adapter.reconnect(device):
                        reconnected = True
                        device.online_state = OnlineState.ONLINE
                        break
                except Exception:  # noqa: BLE001
                    continue
            if not reconnected:
                return self._failure(started, "The enrolled device is offline.")
        try:
            result = adapter.command(device, capability_id, command, args)
        except Exception as exc:  # noqa: BLE001
            return self._failure(started, str(exc), retryable=True)
        if not result.accepted:
            return self._failure(
                started,
                result.error or "The device rejected the command.",
                retryable=result.retryable,
                metadata=result.metadata,
            )
        rules = capability.verification.get(command, ())
        verified = result.verified
        telemetry: dict[str, Any] = {}
        if rules:
            keys = tuple(dict.fromkeys(rule.telemetry_key for rule in rules))
            try:
                telemetry = dict(adapter.telemetry(device, keys))
            except Exception as exc:  # noqa: BLE001
                return self._failure(
                    started,
                    f"Command was accepted but verification failed: {exc}",
                    metadata={"accepted": True},
                )
            verified = all(rule.verify(args, telemetry) for rule in rules)
            self.devices.update_state(
                device_id,
                online_state=OnlineState.ONLINE,
                telemetry=telemetry,
            )
        if not verified:
            return self._failure(
                started,
                "Command was accepted, but the requested state could not be verified.",
                metadata={
                    "accepted": True,
                    "telemetry": _safe(telemetry),
                    **result.metadata,
                },
            )
        return CapabilityOutcome(
            True,
            True,
            output={
                "deviceId": device_id,
                "capability": capability_id,
                "command": command,
                "result": _safe(result.output),
                "telemetry": _safe(telemetry),
            },
            duration_ms=(time.perf_counter() - started) * 1000,
            metadata={"emergency": emergency, **result.metadata},
        )

    @staticmethod
    def command_envelope(
        device_id: str,
        capability_id: str,
        command: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "protocol": "morice-device/1",
            "messageId": uuid.uuid4().hex,
            "deviceId": device_id,
            "capability": capability_id,
            "command": command,
            "arguments": _safe(arguments),
            "sentAt": _now(),
        }

    @staticmethod
    def _failure(
        started: float,
        error: str,
        *,
        retryable: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> CapabilityOutcome:
        return CapabilityOutcome(
            False,
            False,
            error=str(error)[:4_000],
            retryable=retryable,
            duration_ms=(time.perf_counter() - started) * 1000,
            metadata=dict(metadata or {}),
        )


class EnvironmentRegistry:
    def __init__(self):
        self._locations: dict[str, set[str]] = {}
        self._aliases: dict[str, str] = {}
        self._lock = threading.RLock()

    def set_location(
        self,
        location: str,
        device_ids: Iterable[str],
        *,
        aliases: Iterable[str] = (),
    ) -> None:
        clean = " ".join(str(location).split())
        if not clean:
            raise ValueError("Location cannot be empty.")
        with self._lock:
            self._locations[clean] = {str(item) for item in device_ids if str(item)}
            self._aliases[clean.casefold()] = clean
            for alias in aliases:
                self._aliases[str(alias).casefold()] = clean

    def devices_in(self, reference: str) -> tuple[str, ...]:
        with self._lock:
            location = self._aliases.get(str(reference).casefold(), reference)
            return tuple(sorted(self._locations.get(location, ())))

    def snapshot(self) -> dict[str, list[str]]:
        with self._lock:
            return {
                key: sorted(value) for key, value in sorted(self._locations.items())
            }


def device_record_from_dict(value: Mapping[str, Any]) -> DeviceRecord:
    capabilities: dict[str, DeviceCapability] = {}
    for key, raw in dict(value.get("capabilities", {})).items():
        commands = {
            str(command): tuple(CommandField(**dict(item)) for item in fields)
            for command, fields in dict(raw.get("commands", {})).items()
        }
        verification = {
            str(command): tuple(VerificationRule(**dict(item)) for item in rules)
            for command, rules in dict(raw.get("verification", {})).items()
        }
        capabilities[str(key)] = DeviceCapability(
            capability_id=str(raw.get("capabilityId", key)),
            commands=commands,
            telemetry_keys=tuple(raw.get("telemetryKeys", ())),
            permission_group=str(raw.get("permissionGroup", "connected_devices")),
            risk=RiskClass(raw.get("risk", RiskClass.LOW.value)),
            safety_constraints=tuple(
                SafetyConstraint(**dict(item))
                for item in raw.get("safetyConstraints", ())
            ),
            verification=verification,
            emergency_commands=tuple(raw.get("emergencyCommands", ())),
        )
    return DeviceRecord(
        device_id=str(value["deviceId"]),
        display_name=str(value["displayName"]),
        device_type=str(value.get("deviceType", "unknown")),
        platform=str(value.get("platform", "unknown")),
        transport=DeviceTransport(value.get("transport", DeviceTransport.CUSTOM.value)),
        driver=str(value.get("driver", "")),
        location=str(value.get("location", "")),
        connection=dict(value.get("connection", {})),
        enrollment=EnrollmentState(
            value.get("enrollment", EnrollmentState.DISCOVERED.value)
        ),
        online_state=OnlineState(value.get("onlineState", OnlineState.UNKNOWN.value)),
        capabilities=capabilities,
        authorized_capabilities=set(value.get("authorizedCapabilities", ())),
        telemetry=dict(value.get("telemetry", {})),
        aliases=tuple(value.get("aliases", ())),
        last_seen=float(value.get("lastSeen", _now())),
        metadata=dict(value.get("metadata", {})),
    )


__all__ = [
    "CommandField",
    "DeviceAdapter",
    "DeviceAdapterRegistry",
    "DeviceCapability",
    "DeviceCommandResult",
    "DeviceController",
    "DeviceRecord",
    "DeviceRegistry",
    "DeviceTransport",
    "EnrollmentState",
    "EnvironmentRegistry",
    "OnlineState",
    "SafetyConstraint",
    "VerificationRule",
    "device_record_from_dict",
]
