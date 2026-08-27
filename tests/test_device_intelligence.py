from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from morice.device_intelligence import (
    CommandField,
    DeviceAdapterRegistry,
    DeviceCapability,
    DeviceCommandResult,
    DeviceController,
    DeviceRecord,
    DeviceRegistry,
    DeviceTransport,
    EnrollmentState,
    OnlineState,
    SafetyConstraint,
    VerificationRule,
)
from morice.unified_intelligence import (
    PermissionController,
    PermissionState,
    RiskClass,
)


class FakeMotorAdapter:
    adapter_id = "fake-motor"

    def __init__(self):
        self.rpm = 0
        self.commands = []

    def command(self, _device, _capability, command, arguments):
        self.commands.append((command, dict(arguments)))
        if command == "set_speed":
            self.rpm = int(arguments["rpm"])
        elif command == "stop":
            self.rpm = 0
        return DeviceCommandResult(True, output={"accepted": True})

    def telemetry(self, _device, _keys):
        return {"rpm": self.rpm}

    def reconnect(self, _device):
        return True


def motor_record() -> DeviceRecord:
    motion = DeviceCapability(
        "motion",
        commands={
            "set_speed": (CommandField("rpm", "integer", minimum=0, maximum=3000),),
            "stop": (),
        },
        permission_group="connected_devices",
        risk=RiskClass.MEDIUM,
        safety_constraints=(
            SafetyConstraint("rpm", minimum=0, maximum=3000, detail="RPM hard limit"),
        ),
        verification={
            "set_speed": (VerificationRule("rpm", argument_key="rpm"),),
            "stop": (VerificationRule("rpm", expected=0),),
        },
        emergency_commands=("stop",),
    )
    return DeviceRecord(
        "motor-1",
        "Workshop Motor",
        "motor_controller",
        "embedded",
        DeviceTransport.SERIAL,
        "fake-motor",
        location="Workshop",
        online_state=OnlineState.ONLINE,
        capabilities={"motion": motion},
        aliases=("the motor",),
    )


class DeviceIntelligenceTests(unittest.TestCase):
    def test_discovery_does_not_grant_control_and_enrollment_is_explicit(self):
        registry = DeviceRegistry()
        registry.discover(motor_record())

        self.assertEqual(registry.get("motor-1").enrollment, EnrollmentState.DISCOVERED)
        with self.assertRaises(PermissionError):
            registry.pair("motor-1", user_confirmed=False)

        registry.pair("motor-1", user_confirmed=True)
        registry.authorize("motor-1", ("motion",), user_confirmed=True)
        enrolled = registry.enroll("motor-1")
        self.assertTrue(enrolled.controllable)

    def test_hard_safety_limit_blocks_command_before_adapter(self):
        registry = DeviceRegistry()
        record = motor_record()
        record.enrollment = EnrollmentState.ENROLLED
        record.authorized_capabilities = {"motion"}
        registry.discover(record)
        adapters = DeviceAdapterRegistry()
        adapter = FakeMotorAdapter()
        adapters.register(adapter)
        controller = DeviceController(
            registry,
            adapters,
            PermissionController(
                states={"connected_devices": PermissionState.GRANTED}
            ),
        )

        result = controller.execute(
            task_id="task",
            device_id="motor-1",
            capability_id="motion",
            command="set_speed",
            arguments={"rpm": 5000},
        )

        self.assertFalse(result.success)
        self.assertIn("maximum", result.error)
        self.assertEqual(adapter.commands, [])

    def test_authorized_device_command_is_observed_and_verified(self):
        registry = DeviceRegistry()
        record = motor_record()
        record.enrollment = EnrollmentState.ENROLLED
        record.authorized_capabilities = {"motion"}
        registry.discover(record)
        adapters = DeviceAdapterRegistry()
        adapter = FakeMotorAdapter()
        adapters.register(adapter)
        permissions = PermissionController(
            states={"connected_devices": PermissionState.GRANTED}
        )
        controller = DeviceController(registry, adapters, permissions)
        token = permissions.issue_one_use(
            "task", "device.motor-1.motion.set_speed", {"rpm": 1200}
        )

        result = controller.execute(
            task_id="task",
            device_id="motor-1",
            capability_id="motion",
            command="set_speed",
            arguments={"rpm": 1200},
            approval_token=token,
        )

        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertEqual(result.output["telemetry"]["rpm"], 1200)

    def test_registry_persists_only_explicitly_enrolled_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "devices.json"
            registry = DeviceRegistry(path)
            registry.discover(motor_record())
            registry.pair("motor-1", user_confirmed=True)
            registry.authorize("motor-1", ("motion",), user_confirmed=True)
            registry.enroll("motor-1")

            reloaded = DeviceRegistry(path)

        self.assertEqual(
            reloaded.get("motor-1").enrollment, EnrollmentState.ENROLLED
        )
        self.assertEqual(reloaded.get("motor-1").authorized_capabilities, {"motion"})


if __name__ == "__main__":
    unittest.main()
