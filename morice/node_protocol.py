from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import socketserver
import struct
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


PROTOCOL_VERSION = "morice-node/1"
DISCOVERY_MAGIC = "MORICE_NODE_DISCOVERY/1"
MAX_FRAME_BYTES = 16 * 1024 * 1024
DEFAULT_PORT = 47651
DEFAULT_DISCOVERY_PORT = 47652


class MessageType(str, Enum):
    HELLO = "HELLO"
    PAIR_REQUEST = "PAIR_REQUEST"
    PAIR_CHALLENGE = "PAIR_CHALLENGE"
    PAIR_ACCEPT = "PAIR_ACCEPT"
    CAPABILITIES = "CAPABILITIES"
    TASK_REQUEST = "TASK_REQUEST"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_RESULT = "TASK_RESULT"
    TASK_CANCEL = "TASK_CANCEL"
    DEVICE_STATE = "DEVICE_STATE"
    MEMORY_SYNC = "MEMORY_SYNC"
    NOTIFICATION = "NOTIFICATION"
    FILE_TRANSFER = "FILE_TRANSFER"
    VISION_REQUEST = "VISION_REQUEST"
    SCREEN_REQUEST = "SCREEN_REQUEST"
    ERROR = "ERROR"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    clean = str(value)
    return base64.urlsafe_b64decode(clean + "=" * (-len(clean) % 4))


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _clean_tuple(values: Iterable[Any], limit: int = 100) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))[:limit]


@dataclass(frozen=True)
class NodeDescriptor:
    device_id: str
    device_name: str
    platform: str
    capabilities: tuple[str, ...]
    app_version: str = ""
    connection_types: tuple[str, ...] = ("lan",)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.device_id or not self.device_name or not self.platform:
            raise ValueError("A MORICE node needs device id, name, and platform.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "deviceId": self.device_id,
            "deviceName": self.device_name,
            "platform": self.platform,
            "capabilities": list(self.capabilities),
            "appVersion": self.app_version,
            "connectionTypes": list(self.connection_types),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> NodeDescriptor:
        return cls(
            str(value.get("deviceId", ""))[:200],
            str(value.get("deviceName", ""))[:200],
            str(value.get("platform", ""))[:100],
            _clean_tuple(value.get("capabilities", ()), 200),
            str(value.get("appVersion", ""))[:100],
            _clean_tuple(value.get("connectionTypes", ("lan",)), 20),
            dict(value.get("metadata", {})) if isinstance(value.get("metadata"), Mapping) else {},
        )


@dataclass(frozen=True)
class ProtocolMessage:
    message_type: MessageType
    sender_id: str
    recipient_id: str
    payload: dict[str, Any]
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    task_id: str = ""
    sent_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": PROTOCOL_VERSION,
            "type": self.message_type.value,
            "messageId": self.message_id,
            "taskId": self.task_id,
            "senderId": self.sender_id,
            "recipientId": self.recipient_id,
            "sentAt": self.sent_at,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ProtocolMessage:
        if value.get("protocol") != PROTOCOL_VERSION:
            raise ValueError("Unsupported MORICE node protocol version.")
        message_id = str(value.get("messageId", ""))
        sender = str(value.get("senderId", ""))
        recipient = str(value.get("recipientId", ""))
        payload = value.get("payload", {})
        if not message_id or not sender or not recipient or not isinstance(payload, Mapping):
            raise ValueError("Malformed MORICE node message.")
        return cls(
            MessageType(str(value.get("type", ""))),
            sender,
            recipient,
            dict(payload),
            message_id[:200],
            str(value.get("taskId", ""))[:200],
            float(value.get("sentAt", 0.0)),
        )


class NodeIdentity:
    def __init__(self, private_key: ec.EllipticCurvePrivateKey | None = None):
        self._private_key = private_key or ec.generate_private_key(ec.SECP256R1())

    @property
    def public_key(self) -> ec.EllipticCurvePublicKey:
        return self._private_key.public_key()

    @property
    def public_key_bytes(self) -> bytes:
        return self.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )

    @property
    def public_key_text(self) -> str:
        return _b64(self.public_key_bytes)

    @property
    def fingerprint(self) -> str:
        digest = hashlib.sha256(self.public_key_bytes).hexdigest().upper()
        return ":".join(digest[index : index + 4] for index in range(0, 24, 4))

    def private_pem(self) -> str:
        return self._private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii")

    @classmethod
    def from_pem(cls, value: str | bytes) -> NodeIdentity:
        key = serialization.load_pem_private_key(
            value.encode("ascii") if isinstance(value, str) else value,
            password=None,
        )
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError("MORICE node identity must be an EC private key.")
        return cls(key)

    @staticmethod
    def parse_public(value: str) -> ec.EllipticCurvePublicKey:
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _unb64(value))


def derive_pair_key(
    private_key: ec.EllipticCurvePrivateKey,
    peer_public_text: str,
    request_nonce: bytes,
    response_nonce: bytes,
) -> bytes:
    shared = private_key.exchange(ec.ECDH(), NodeIdentity.parse_public(peer_public_text))
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=request_nonce + response_nonce,
        info=b"MORICE authenticated node pairing v1",
    ).derive(shared)


def verification_code(key: bytes, first_id: str, second_id: str) -> str:
    ordered = "|".join(sorted((first_id, second_id))).encode("utf-8")
    number = int.from_bytes(hmac.new(key, b"verify|" + ordered, hashlib.sha256).digest()[:4], "big")
    return f"{number % 1_000_000:06d}"


@dataclass
class PairingInitiator:
    descriptor: NodeDescriptor
    identity: NodeIdentity
    ephemeral: ec.EllipticCurvePrivateKey = field(default_factory=lambda: ec.generate_private_key(ec.SECP256R1()))
    request_nonce: bytes = field(default_factory=lambda: secrets.token_bytes(16))

    def request(self, recipient_id: str = "unpaired") -> ProtocolMessage:
        public = self.ephemeral.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        return ProtocolMessage(
            MessageType.PAIR_REQUEST,
            self.descriptor.device_id,
            recipient_id,
            {
                "descriptor": self.descriptor.to_dict(),
                "identityPublicKey": self.identity.public_key_text,
                "ephemeralPublicKey": _b64(public),
                "requestNonce": _b64(self.request_nonce),
            },
        )

    def complete(self, challenge: ProtocolMessage) -> tuple[bytes, str, NodeDescriptor, str]:
        if challenge.message_type != MessageType.PAIR_CHALLENGE:
            raise ValueError("Expected a pairing challenge.")
        payload = challenge.payload
        response_nonce = _unb64(str(payload["responseNonce"]))
        key = derive_pair_key(
            self.ephemeral,
            str(payload["ephemeralPublicKey"]),
            self.request_nonce,
            response_nonce,
        )
        expected = verification_code(key, self.descriptor.device_id, challenge.sender_id)
        received = str(payload.get("verificationCode", ""))
        if not hmac.compare_digest(expected, received):
            raise ValueError("Pairing verification code mismatch.")
        peer = NodeDescriptor.from_dict(dict(payload["descriptor"]))
        return key, expected, peer, str(payload["identityPublicKey"])


@dataclass
class PairingResponder:
    descriptor: NodeDescriptor
    identity: NodeIdentity

    def challenge(
        self,
        request: ProtocolMessage,
    ) -> tuple[ProtocolMessage, bytes, str, NodeDescriptor, str]:
        if request.message_type != MessageType.PAIR_REQUEST:
            raise ValueError("Expected a pairing request.")
        payload = request.payload
        peer = NodeDescriptor.from_dict(dict(payload["descriptor"]))
        ephemeral = ec.generate_private_key(ec.SECP256R1())
        response_nonce = secrets.token_bytes(16)
        request_nonce = _unb64(str(payload["requestNonce"]))
        key = derive_pair_key(
            ephemeral,
            str(payload["ephemeralPublicKey"]),
            request_nonce,
            response_nonce,
        )
        code = verification_code(key, request.sender_id, self.descriptor.device_id)
        public = ephemeral.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        response = ProtocolMessage(
            MessageType.PAIR_CHALLENGE,
            self.descriptor.device_id,
            request.sender_id,
            {
                "descriptor": self.descriptor.to_dict(),
                "identityPublicKey": self.identity.public_key_text,
                "ephemeralPublicKey": _b64(public),
                "responseNonce": _b64(response_nonce),
                "verificationCode": code,
                "requestMessageId": request.message_id,
            },
        )
        return response, key, code, peer, str(payload["identityPublicKey"])


@dataclass
class TrustedNode:
    descriptor: NodeDescriptor
    identity_public_key: str
    session_key: str
    allowed_capabilities: tuple[str, ...] = ()
    remote_capabilities: tuple[str, ...] = ()
    paired_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    revoked: bool = False

    def key_bytes(self) -> bytes:
        return _unb64(self.session_key)

    def allows(self, capability: str) -> bool:
        return not self.revoked and capability in self.allowed_capabilities

    def remote_allows(self, capability: str) -> bool:
        return not self.revoked and capability in self.remote_capabilities

    def to_dict(self) -> dict[str, Any]:
        return {
            "descriptor": self.descriptor.to_dict(),
            "identityPublicKey": self.identity_public_key,
            "sessionKey": self.session_key,
            "allowedCapabilities": list(self.allowed_capabilities),
            "remoteCapabilities": list(self.remote_capabilities),
            "pairedAt": self.paired_at,
            "lastSeen": self.last_seen,
            "revoked": self.revoked,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TrustedNode:
        return cls(
            NodeDescriptor.from_dict(dict(value.get("descriptor", {}))),
            str(value.get("identityPublicKey", "")),
            str(value.get("sessionKey", "")),
            _clean_tuple(value.get("allowedCapabilities", ()), 200),
            _clean_tuple(
                value.get(
                    "remoteCapabilities",
                    value.get("descriptor", {}).get("capabilities", ()),
                ),
                200,
            ),
            float(value.get("pairedAt", time.time())),
            float(value.get("lastSeen", time.time())),
            bool(value.get("revoked", False)),
        )


class TrustedNodeStore:
    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path) if path else None
        self._nodes: dict[str, TrustedNode] = {}
        self._lock = threading.RLock()
        self._load()

    def enroll(
        self,
        descriptor: NodeDescriptor,
        identity_public_key: str,
        session_key: bytes,
        capabilities: Iterable[str],
        *,
        user_approved: bool,
        remote_capabilities: Iterable[str] = (),
    ) -> TrustedNode:
        if not user_approved:
            raise PermissionError("Pairing must be approved by the user on this node.")
        # These are the local capabilities this peer may invoke.  They are
        # intentionally independent from the capabilities the peer advertises.
        requested = set(_clean_tuple(capabilities, 200))
        node = TrustedNode(
            descriptor,
            identity_public_key,
            _b64(session_key),
            tuple(sorted(requested)),
            tuple(sorted(set(_clean_tuple(remote_capabilities, 200)))),
        )
        with self._lock:
            self._nodes[descriptor.device_id] = node
            self._save()
        return node

    def get(self, device_id: str) -> TrustedNode | None:
        with self._lock:
            return self._nodes.get(device_id)

    def list(self) -> tuple[TrustedNode, ...]:
        with self._lock:
            return tuple(sorted(self._nodes.values(), key=lambda item: item.descriptor.device_name.casefold()))

    def set_permissions(
        self,
        device_id: str,
        capabilities: Iterable[str],
        *,
        user_approved: bool,
    ) -> TrustedNode:
        if not user_approved:
            raise PermissionError("Permission changes require user approval.")
        with self._lock:
            node = self._nodes[device_id]
            requested = set(_clean_tuple(capabilities, 200))
            node.allowed_capabilities = tuple(sorted(requested))
            self._save()
            return node

    def revoke(self, device_id: str) -> None:
        with self._lock:
            node = self._nodes[device_id]
            node.revoked = True
            node.allowed_capabilities = ()
            node.remote_capabilities = ()
            self._save()

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        temporary.write_text(
            json.dumps({"version": 1, "nodes": [node.to_dict() for node in self._nodes.values()]}, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def _load(self) -> None:
        if not self.path:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return
        for item in payload.get("nodes", ()):
            try:
                node = TrustedNode.from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue
            self._nodes[node.descriptor.device_id] = node


class SecureChannel:
    def __init__(self, local_id: str, peer_id: str, key: bytes, *, max_clock_skew: float = 300.0):
        if len(key) != 32:
            raise ValueError("MORICE node channels require a 256-bit key.")
        self.local_id = local_id
        self.peer_id = peer_id
        self._aes = AESGCM(key)
        self.max_clock_skew = max_clock_skew
        self._seen: set[str] = set()
        self._order: deque[str] = deque(maxlen=4096)
        self._lock = threading.RLock()

    def seal(self, message: ProtocolMessage) -> bytes:
        if message.sender_id != self.local_id or message.recipient_id != self.peer_id:
            raise ValueError("Message endpoints do not match this secure channel.")
        nonce = secrets.token_bytes(12)
        aad_value = {
            "protocol": PROTOCOL_VERSION,
            "senderId": self.local_id,
            "recipientId": self.peer_id,
            "messageId": message.message_id,
        }
        ciphertext = self._aes.encrypt(nonce, _canonical(message.to_dict()), _canonical(aad_value))
        return _canonical({**aad_value, "nonce": _b64(nonce), "ciphertext": _b64(ciphertext)})

    def open(self, envelope: bytes | str | Mapping[str, Any]) -> ProtocolMessage:
        if isinstance(envelope, Mapping):
            value = dict(envelope)
        else:
            value = json.loads(envelope.decode("utf-8") if isinstance(envelope, bytes) else envelope)
        if value.get("protocol") != PROTOCOL_VERSION:
            raise ValueError("Unsupported encrypted envelope version.")
        if value.get("senderId") != self.peer_id or value.get("recipientId") != self.local_id:
            raise PermissionError("Encrypted envelope endpoints do not match the channel.")
        message_id = str(value.get("messageId", ""))
        if not message_id:
            raise ValueError("Encrypted envelope has no message id.")
        with self._lock:
            if message_id in self._seen:
                raise PermissionError("Replay detected for MORICE node message.")
        aad = {
            "protocol": PROTOCOL_VERSION,
            "senderId": self.peer_id,
            "recipientId": self.local_id,
            "messageId": message_id,
        }
        plaintext = self._aes.decrypt(
            _unb64(str(value["nonce"])),
            _unb64(str(value["ciphertext"])),
            _canonical(aad),
        )
        message = ProtocolMessage.from_dict(json.loads(plaintext))
        if message.message_id != message_id:
            raise ValueError("Encrypted envelope/message id mismatch.")
        if abs(time.time() - message.sent_at) > self.max_clock_skew:
            raise PermissionError("MORICE node message is outside the accepted clock window.")
        with self._lock:
            if len(self._order) == self._order.maxlen:
                self._seen.discard(self._order[0])
            self._order.append(message_id)
            self._seen.add(message_id)
        return message


def encode_frame(payload: bytes) -> bytes:
    if not payload or len(payload) > MAX_FRAME_BYTES:
        raise ValueError("Invalid MORICE node frame size.")
    return struct.pack("!I", len(payload)) + payload


def receive_frame(connection: socket.socket) -> bytes:
    header = _receive_exact(connection, 4)
    size = struct.unpack("!I", header)[0]
    if size <= 0 or size > MAX_FRAME_BYTES:
        raise ValueError("Invalid MORICE node frame size.")
    return _receive_exact(connection, size)


def _receive_exact(connection: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while received < size:
        chunk = connection.recv(size - received)
        if not chunk:
            raise ConnectionError("MORICE node connection closed during a frame.")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


class NodeRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server: MoriceNodeServer = self.server.owner  # type: ignore[attr-defined]
        self.request.settimeout(server.request_timeout)
        try:
            raw_frame = receive_frame(self.request)
            envelope = json.loads(raw_frame)
            if envelope.get("protocol") == PROTOCOL_VERSION and envelope.get("type") in {
                MessageType.PAIR_REQUEST.value,
                MessageType.PAIR_ACCEPT.value,
            }:
                pairing_response = server.handle_pairing(
                    ProtocolMessage.from_dict(envelope),
                    self.client_address,
                )
                self.request.sendall(encode_frame(_canonical(pairing_response.to_dict())))
                return
            sender_id = str(envelope.get("senderId", ""))
            trusted = server.store.get(sender_id)
            if trusted is None or trusted.revoked:
                raise PermissionError("This MORICE node is not paired.")
            channel = SecureChannel(server.descriptor.device_id, sender_id, trusted.key_bytes())
            message = channel.open(envelope)
            response = server.dispatch(message, trusted)
            self.request.sendall(encode_frame(channel.seal(response)))
        except Exception as exc:  # noqa: BLE001
            server.on_error(exc, self.client_address)


class _ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class MoriceNodeServer:
    def __init__(
        self,
        descriptor: NodeDescriptor,
        store: TrustedNodeStore,
        dispatcher: Callable[[ProtocolMessage, TrustedNode], ProtocolMessage],
        *,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        request_timeout: float = 30.0,
        error_callback: Callable[[Exception, Any], None] | None = None,
        identity: NodeIdentity | None = None,
    ):
        self.descriptor = descriptor
        self.store = store
        self.dispatcher = dispatcher
        self.host = host
        self.port = int(port)
        self.request_timeout = request_timeout
        self.error_callback = error_callback
        self.identity = identity
        self._pairing_until = 0.0
        self._pending_pairings: dict[str, dict[str, Any]] = {}
        self._pairing_lock = threading.RLock()
        self._server: _ThreadingServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def bound_port(self) -> int:
        if not self._server:
            return 0
        return int(self._server.server_address[1])

    def start(self) -> None:
        if self.running:
            return
        server = _ThreadingServer((self.host, self.port), NodeRequestHandler)
        server.owner = self  # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name="morice-node-server", daemon=True)
        self._thread.start()

    def enable_pairing(self, seconds: float = 120.0) -> float:
        if self.identity is None:
            raise RuntimeError("This node server has no pairing identity.")
        duration = max(15.0, min(float(seconds), 600.0))
        with self._pairing_lock:
            self._pairing_until = time.time() + duration
            self._pending_pairings.clear()
            return self._pairing_until

    def disable_pairing(self) -> None:
        with self._pairing_lock:
            self._pairing_until = 0.0
            self._pending_pairings.clear()

    def pairing_status(self) -> dict[str, Any]:
        with self._pairing_lock:
            remaining = max(0.0, self._pairing_until - time.time())
            pending = tuple(
                {
                    "deviceId": item["descriptor"].device_id,
                    "deviceName": item["descriptor"].device_name,
                    "platform": item["descriptor"].platform,
                    "verificationCode": item["code"],
                    "expiresAt": item["expiresAt"],
                }
                for item in self._pending_pairings.values()
            )
        return {"enabled": remaining > 0, "remainingSeconds": remaining, "pending": pending}

    def handle_pairing(
        self,
        message: ProtocolMessage,
        client_address: Any = None,
    ) -> ProtocolMessage:
        with self._pairing_lock:
            if time.time() >= self._pairing_until:
                raise PermissionError("Desktop pairing is not currently enabled by the user.")
            expired = [
                key for key, value in self._pending_pairings.items()
                if time.time() >= float(value["expiresAt"])
            ]
            for key in expired:
                self._pending_pairings.pop(key, None)
            if message.message_type == MessageType.PAIR_REQUEST:
                if self.identity is None:
                    raise RuntimeError("Node pairing identity is unavailable.")
                challenge, key, code, peer, identity_key = PairingResponder(
                    self.descriptor,
                    self.identity,
                ).challenge(message)
                self._pending_pairings[peer.device_id] = {
                    "descriptor": peer,
                    "identityPublicKey": identity_key,
                    "key": key,
                    "code": code,
                    "expiresAt": min(self._pairing_until, time.time() + 120.0),
                    "host": str(client_address[0]) if client_address else "",
                }
                return challenge
            if message.message_type != MessageType.PAIR_ACCEPT:
                raise ValueError("Unsupported pairing message.")
            pending = self._pending_pairings.get(message.sender_id)
            if not pending:
                raise PermissionError("No live pairing challenge exists for this device.")
            supplied_code = str(message.payload.get("verificationCode", ""))
            if not hmac.compare_digest(supplied_code, str(pending["code"])):
                raise PermissionError("Pairing verification code did not match.")
            requested = set(_clean_tuple(message.payload.get("requestedCapabilities", ()), 200))
            unknown = requested - set(self.descriptor.capabilities)
            if unknown:
                raise PermissionError(
                    "The peer requested unavailable capabilities: " + ", ".join(sorted(unknown))
                )
            node_port = int(message.payload.get("nodePort", 0) or 0)
            peer_descriptor = pending["descriptor"]
            if pending.get("host") or node_port:
                peer_descriptor = replace(
                    peer_descriptor,
                    metadata={
                        **peer_descriptor.metadata,
                        "host": str(pending.get("host", "")),
                        "port": node_port,
                    },
                )
            self.store.enroll(
                peer_descriptor,
                pending["identityPublicKey"],
                pending["key"],
                requested,
                user_approved=True,
                remote_capabilities=(
                    set(_clean_tuple(message.payload.get("offeredCapabilities", ()), 200))
                    & set(peer_descriptor.capabilities)
                ),
            )
            self._pending_pairings.pop(message.sender_id, None)
            return ProtocolMessage(
                MessageType.PAIR_ACCEPT,
                self.descriptor.device_id,
                message.sender_id,
                {
                    "paired": True,
                    "grantedCapabilities": sorted(requested),
                    "descriptor": self.descriptor.to_dict(),
                },
                task_id=message.task_id,
            )

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server:
            server.shutdown()
            server.server_close()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def dispatch(self, message: ProtocolMessage, trusted: TrustedNode) -> ProtocolMessage:
        capability = str(message.payload.get("capability", ""))
        if message.message_type in {
            MessageType.TASK_REQUEST,
            MessageType.VISION_REQUEST,
            MessageType.SCREEN_REQUEST,
            MessageType.FILE_TRANSFER,
        } and (not capability or not trusted.allows(capability)):
            return ProtocolMessage(
                MessageType.ERROR,
                self.descriptor.device_id,
                message.sender_id,
                {"error": "The requested capability is not authorized on this node.", "capability": capability},
                task_id=message.task_id,
            )
        return self.dispatcher(message, trusted)

    def on_error(self, error: Exception, address: Any) -> None:
        if self.error_callback:
            self.error_callback(error, address)


class MoriceNodeClient:
    def __init__(self, descriptor: NodeDescriptor, store: TrustedNodeStore):
        self.descriptor = descriptor
        self.store = store

    def send(
        self,
        peer_id: str,
        host: str,
        port: int,
        message_type: MessageType,
        payload: Mapping[str, Any],
        *,
        task_id: str = "",
        timeout: float = 30.0,
    ) -> ProtocolMessage:
        trusted = self.store.get(peer_id)
        if trusted is None or trusted.revoked:
            raise PermissionError("The target MORICE node is not paired.")
        capability = str(payload.get("capability", ""))
        if capability and not trusted.remote_allows(capability):
            raise PermissionError("The requested capability is not authorized on the target node.")
        channel = SecureChannel(self.descriptor.device_id, peer_id, trusted.key_bytes())
        message = ProtocolMessage(
            message_type,
            self.descriptor.device_id,
            peer_id,
            dict(payload),
            task_id=task_id,
        )
        with socket.create_connection((host, int(port)), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(encode_frame(channel.seal(message)))
            response = receive_frame(connection)
        return channel.open(response)

    def pair(
        self,
        host: str,
        port: int,
        identity: NodeIdentity,
        requested_capabilities: Iterable[str],
        *,
        confirm_code: Callable[[str, NodeDescriptor], bool],
        local_permissions_for_peer: Iterable[str] = (),
        local_node_port: int = 0,
        timeout: float = 15.0,
    ) -> TrustedNode:
        initiator = PairingInitiator(self.descriptor, identity)
        request = initiator.request("unpaired")
        with socket.create_connection((host, int(port)), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(encode_frame(_canonical(request.to_dict())))
            challenge = ProtocolMessage.from_dict(json.loads(receive_frame(connection)))
        key, code, peer, identity_public_key = initiator.complete(challenge)
        if not confirm_code(code, peer):
            raise PermissionError("Pairing was not confirmed by the user.")
        accept = ProtocolMessage(
            MessageType.PAIR_ACCEPT,
            self.descriptor.device_id,
            peer.device_id,
            {
                "verificationCode": code,
                "requestedCapabilities": list(_clean_tuple(requested_capabilities, 200)),
                "offeredCapabilities": list(_clean_tuple(local_permissions_for_peer, 200)),
                "nodePort": max(0, min(int(local_node_port), 65535)),
            },
        )
        with socket.create_connection((host, int(port)), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(encode_frame(_canonical(accept.to_dict())))
            accepted = ProtocolMessage.from_dict(json.loads(receive_frame(connection)))
        if accepted.message_type != MessageType.PAIR_ACCEPT or not accepted.payload.get("paired"):
            raise PermissionError(str(accepted.payload.get("error", "Pairing was rejected.")))
        # Local permissions describe which capabilities this peer may invoke
        # when the current node later acts as a server.
        peer = replace(
            peer,
            metadata={**peer.metadata, "host": str(host), "port": int(port)},
        )
        return self.store.enroll(
            peer,
            identity_public_key,
            key,
            local_permissions_for_peer,
            user_approved=True,
            remote_capabilities=_clean_tuple(
                accepted.payload.get("grantedCapabilities", ()), 200
            ),
        )


class LanDiscovery:
    def __init__(self, descriptor: NodeDescriptor, *, node_port: int = DEFAULT_PORT, discovery_port: int = DEFAULT_DISCOVERY_PORT):
        self.descriptor = descriptor
        self.node_port = int(node_port)
        self.discovery_port = int(discovery_port)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start_responder(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._respond, name="morice-node-discovery", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _respond(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.discovery_port))
            sock.settimeout(0.5)
            while not self._stop.is_set():
                try:
                    payload, address = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if payload.decode("utf-8", errors="ignore") != DISCOVERY_MAGIC:
                    continue
                response = {
                    "protocol": PROTOCOL_VERSION,
                    "descriptor": self.descriptor.to_dict(),
                    "port": self.node_port,
                    "pairingRequired": True,
                }
                sock.sendto(_canonical(response), address)

    @staticmethod
    def discover(*, timeout: float = 1.2, discovery_port: int = DEFAULT_DISCOVERY_PORT) -> tuple[dict[str, Any], ...]:
        found: dict[str, dict[str, Any]] = {}
        deadline = time.monotonic() + max(0.1, timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.2)
            sock.sendto(DISCOVERY_MAGIC.encode("utf-8"), ("255.255.255.255", int(discovery_port)))
            while time.monotonic() < deadline:
                try:
                    payload, address = sock.recvfrom(16_384)
                except socket.timeout:
                    continue
                try:
                    value = json.loads(payload)
                    descriptor = NodeDescriptor.from_dict(value["descriptor"])
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
                found[descriptor.device_id] = {**value, "host": address[0]}
        return tuple(found.values())


__all__ = [
    "DEFAULT_DISCOVERY_PORT",
    "DEFAULT_PORT",
    "LanDiscovery",
    "MessageType",
    "MoriceNodeClient",
    "MoriceNodeServer",
    "NodeDescriptor",
    "NodeIdentity",
    "PairingInitiator",
    "PairingResponder",
    "ProtocolMessage",
    "SecureChannel",
    "TrustedNode",
    "TrustedNodeStore",
    "derive_pair_key",
    "encode_frame",
    "receive_frame",
    "verification_code",
]
