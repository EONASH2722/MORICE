from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from morice.node_protocol import (
    MessageType,
    MoriceNodeClient,
    MoriceNodeServer,
    NodeDescriptor,
    NodeIdentity,
    PairingInitiator,
    PairingResponder,
    ProtocolMessage,
    SecureChannel,
    TrustedNodeStore,
)


class NodeProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.desktop = NodeDescriptor(
            "desktop-1",
            "Desktop PC",
            "windows",
            ("system.status", "application.open", "media.control"),
        )
        self.phone = NodeDescriptor(
            "phone-1",
            "Phone",
            "android",
            ("camera.capture", "device.status", "notifications.read"),
        )

    def _pair(self):
        initiator = PairingInitiator(self.phone, NodeIdentity())
        responder = PairingResponder(self.desktop, NodeIdentity())
        request = initiator.request(self.desktop.device_id)
        challenge, responder_key, responder_code, peer, identity_key = responder.challenge(request)
        initiator_key, initiator_code, desktop_peer, desktop_identity = initiator.complete(challenge)
        self.assertEqual(responder_key, initiator_key)
        self.assertEqual(responder_code, initiator_code)
        self.assertEqual(peer.device_id, self.phone.device_id)
        self.assertEqual(desktop_peer.device_id, self.desktop.device_id)
        self.assertTrue(identity_key)
        self.assertTrue(desktop_identity)
        return initiator_key

    def test_pairing_derives_same_authenticated_key_and_code(self) -> None:
        key = self._pair()
        self.assertEqual(len(key), 32)

    def test_secure_channel_rejects_tampering_and_replay(self) -> None:
        key = self._pair()
        outgoing = SecureChannel("phone-1", "desktop-1", key)
        incoming = SecureChannel("desktop-1", "phone-1", key)
        message = ProtocolMessage(
            MessageType.TASK_REQUEST,
            "phone-1",
            "desktop-1",
            {"capability": "system.status"},
        )
        sealed = outgoing.seal(message)
        opened = incoming.open(sealed)
        self.assertEqual(opened.message_id, message.message_id)
        with self.assertRaises(PermissionError):
            incoming.open(sealed)
        value = json.loads(sealed)
        value["ciphertext"] = value["ciphertext"][:-2] + "AA"
        with self.assertRaises(Exception):
            SecureChannel("desktop-1", "phone-1", key).open(value)

    def test_store_requires_approval_and_scopes_permissions(self) -> None:
        key = self._pair()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "trusted.json")
            store = TrustedNodeStore(path)
            with self.assertRaises(PermissionError):
                store.enroll(
                    self.phone,
                    NodeIdentity().public_key_text,
                    key,
                    ("camera.capture",),
                    user_approved=False,
                )
            node = store.enroll(
                self.phone,
                NodeIdentity().public_key_text,
                key,
                ("camera.capture",),
                user_approved=True,
            )
            self.assertTrue(node.allows("camera.capture"))
            self.assertFalse(node.allows("notifications.read"))
            reloaded = TrustedNodeStore(path)
            self.assertTrue(reloaded.get("phone-1").allows("camera.capture"))  # type: ignore[union-attr]

    def test_loopback_task_is_encrypted_authorized_and_verified(self) -> None:
        key = self._pair()
        with tempfile.TemporaryDirectory() as directory:
            desktop_store = TrustedNodeStore(Path(directory, "desktop.json"))
            phone_store = TrustedNodeStore(Path(directory, "phone.json"))
            desktop_store.enroll(
                self.phone,
                NodeIdentity().public_key_text,
                key,
                ("device.status",),
                user_approved=True,
            )
            phone_store.enroll(
                self.desktop,
                NodeIdentity().public_key_text,
                key,
                ("system.status",),
                user_approved=True,
                remote_capabilities=("device.status",),
            )

            def dispatch(message, _trusted):
                return ProtocolMessage(
                    MessageType.TASK_RESULT,
                    "desktop-1",
                    message.sender_id,
                    {"verified": True, "ramPercent": 42},
                    task_id=message.task_id,
                )

            server = MoriceNodeServer(
                self.desktop,
                desktop_store,
                dispatch,
                host="127.0.0.1",
                port=0,
            )
            server.start()
            try:
                response = MoriceNodeClient(self.phone, phone_store).send(
                    "desktop-1",
                    "127.0.0.1",
                    server.bound_port,
                    MessageType.TASK_REQUEST,
                    {"capability": "device.status"},
                    task_id="task-1",
                )
            finally:
                server.stop()
        self.assertEqual(response.message_type, MessageType.TASK_RESULT)
        self.assertTrue(response.payload["verified"])

    def test_server_denies_unapproved_capability_before_dispatch(self) -> None:
        key = self._pair()
        with tempfile.TemporaryDirectory() as directory:
            desktop_store = TrustedNodeStore(Path(directory, "desktop.json"))
            phone_store = TrustedNodeStore(Path(directory, "phone.json"))
            desktop_store.enroll(
                self.phone,
                NodeIdentity().public_key_text,
                key,
                ("device.status",),
                user_approved=True,
            )
            phone_store.enroll(
                self.desktop,
                NodeIdentity().public_key_text,
                key,
                ("system.status",),
                user_approved=True,
                remote_capabilities=("camera.capture",),
            )
            server = MoriceNodeServer(
                self.desktop,
                desktop_store,
                lambda *_: self.fail("dispatcher should not run"),
                host="127.0.0.1",
                port=0,
            )
            server.start()
            try:
                response = MoriceNodeClient(self.phone, phone_store).send(
                    "desktop-1",
                    "127.0.0.1",
                    server.bound_port,
                    MessageType.TASK_REQUEST,
                    {"capability": "camera.capture"},
                )
            finally:
                server.stop()
        self.assertEqual(response.message_type, MessageType.ERROR)
        self.assertIn("not authorized", response.payload["error"])

    def test_network_pairing_requires_window_and_user_code_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            desktop_store = TrustedNodeStore(Path(directory, "desktop.json"))
            phone_store = TrustedNodeStore(Path(directory, "phone.json"))
            server = MoriceNodeServer(
                self.desktop,
                desktop_store,
                lambda *_: self.fail("dispatcher should not run during pairing"),
                host="127.0.0.1",
                port=0,
                identity=NodeIdentity(),
            )
            server.start()
            server.enable_pairing(30)
            seen: list[str] = []
            try:
                paired = MoriceNodeClient(self.phone, phone_store).pair(
                    "127.0.0.1",
                    server.bound_port,
                    NodeIdentity(),
                    ("system.status", "media.control"),
                    local_permissions_for_peer=("camera.capture",),
                    confirm_code=lambda code, peer: bool(
                        seen.append(f"{code}:{peer.device_id}") or True
                    ),
                )
            finally:
                server.stop()
        self.assertEqual(paired.descriptor.device_id, "desktop-1")
        self.assertTrue(seen[0].endswith(":desktop-1"))
        desktop_view = desktop_store.get("phone-1")
        self.assertTrue(desktop_view.allows("system.status"))  # type: ignore[union-attr]
        self.assertTrue(desktop_view.allows("media.control"))  # type: ignore[union-attr]
        self.assertTrue(paired.allows("camera.capture"))
        self.assertTrue(paired.remote_allows("system.status"))
        self.assertTrue(desktop_view.remote_allows("camera.capture"))  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
