from __future__ import annotations

import subprocess
import unittest

from morice.connectivity import (
    BluetoothManager,
    ConnectivityState,
    NetworkManager,
    UnsupportedBluetoothProvider,
    WindowsBluetoothProvider,
)


class _Connection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class ConnectivityTests(unittest.TestCase):
    def test_network_observation_is_bounded_cached_and_truthful(self):
        calls = []

        def connector(address, timeout):
            calls.append((address, timeout))
            return _Connection()

        manager = NetworkManager(connector=connector, cache_seconds=60)
        first = manager.observe(force=True)
        second = manager.observe()
        self.assertEqual(first.state, ConnectivityState.ONLINE)
        self.assertIs(first, second)
        self.assertEqual(len(calls), 1)

    def test_offline_probe_does_not_claim_online(self):
        def connector(address, timeout):
            del address, timeout
            raise OSError("offline")

        snapshot = NetworkManager(connector=connector).observe(force=True)
        self.assertEqual(snapshot.state, ConnectivityState.OFFLINE)
        self.assertIn("offline", snapshot.error)

    def test_unobserved_network_snapshot_is_unknown_without_probe(self):
        manager = NetworkManager(connector=lambda *args, **kwargs: self.fail("probe"))
        self.assertEqual(manager.snapshot().state, ConnectivityState.UNKNOWN)

    def test_unsupported_bluetooth_is_reported_not_fabricated(self):
        snapshot = BluetoothManager(
            UnsupportedBluetoothProvider(), system="Linux"
        ).discover(force=True)
        self.assertFalse(snapshot.supported)
        self.assertEqual(snapshot.devices, ())

    def test_windows_bluetooth_parses_native_discovery(self):
        output = (
            '[{"InstanceId":"BTH\\\\A","FriendlyName":"Headphones",'
            '"Status":"OK","Class":"Bluetooth"}]'
        )

        def runner(*args, **kwargs):
            del args, kwargs
            return subprocess.CompletedProcess([], 0, output, "")

        snapshot = WindowsBluetoothProvider(runner=runner).discover()
        self.assertTrue(snapshot.supported)
        self.assertEqual(snapshot.devices[0].name, "Headphones")
        self.assertIsNone(snapshot.devices[0].connected)


if __name__ == "__main__":
    unittest.main()
