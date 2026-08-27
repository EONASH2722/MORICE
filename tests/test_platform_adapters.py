from __future__ import annotations

import sys
import unittest

from morice.platform_adapters import (
    AndroidAdapter,
    LinuxAdapter,
    MacOSAdapter,
    WindowsAdapter,
    select_platform_adapter,
)
from morice.unified_intelligence import CapabilityState


class PlatformAdapterTests(unittest.TestCase):
    def test_host_adapter_selection_is_platform_specific(self):
        self.assertIsInstance(select_platform_adapter("Windows", environ={}), WindowsAdapter)
        self.assertIsInstance(select_platform_adapter("Linux", environ={}), LinuxAdapter)
        self.assertIsInstance(select_platform_adapter("Darwin", environ={}), MacOSAdapter)

    def test_android_requires_explicit_companion_authorization(self):
        adapter = select_platform_adapter(
            "Linux", environ={"ANDROID_ROOT": "/system"}
        )
        self.assertIsInstance(adapter, AndroidAdapter)
        state = {
            item.capability_id: item.state for item in adapter.capabilities()
        }
        self.assertEqual(state["android.companion"], CapabilityState.PERMISSION_REQUIRED)

    def test_linux_headless_session_reports_desktop_unavailable(self):
        adapter = LinuxAdapter(environ={})
        state = {item.capability_id: item.state for item in adapter.capabilities()}
        self.assertEqual(state["linux.desktop_control"], CapabilityState.UNAVAILABLE)

    def test_command_execution_uses_direct_argument_list_and_exit_code(self):
        adapter = select_platform_adapter()
        result = adapter.run_command(
            [sys.executable, "-c", "print('adapter-ok')"], timeout=5
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["verified"])
        self.assertIn("adapter-ok", result["stdout"])


if __name__ == "__main__":
    unittest.main()
