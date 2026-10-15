"""TLS 1.3, mutual pinned identities, explicit two-sided pairing, bounded RPC."""
from __future__ import annotations

import hmac
import secrets
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from ..node_protocol import NodeDescriptor
from .identity import certificate_id, certificate_pin
from .protocol import VERSION, OPERATIONS, RateLimit, encode, receive, identifier


class MeshTransport:
    def __init__(self, credentials, store, descriptor, dispatcher, *, host="127.0.0.1", port=0, pair_port=0):
        self.credentials, self.store, self.descriptor = credentials, store, descriptor
        self.dispatcher = dispatcher
        self.host, self.port, self.pair_port = host, port, pair_port
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._listeners, self._threads, self._connections = [], [], set()
        self._slots = threading.BoundedSemaphore(8)
        self._pool = None
        self._rates = {}
        self._global = RateLimit(10000)
        self._pair_until = 0
        self._pair_code = ""
        self._pair_failures = 0
        self._pending = {}
        self._server_context = None
        self._client_contexts = {}
        self.metrics = {"received": 0, "rejected": 0, "rpc_count": 0, "rpc_ms": 0.0}

    @property
    def running(self):
        return bool(self._listeners)

    def _refresh_context(self):
        certs = [n.identity_public_key for n in self.store.list() if not n.revoked]
        self._server_context = self.credentials.context(server=True, certificates=certs)
        self._client_contexts.clear()

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._refresh_context()
        self._pool = ThreadPoolExecutor(8, thread_name_prefix="morice-mesh-rpc")
        try:
            for pairing, port in ((False, self.port), (True, self.pair_port)):
                listener = socket.socket()
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((self.host, port))
                listener.listen(8)
                listener.settimeout(.2)
                self._listeners.append(listener)
                if pairing:
                    self.pair_port = listener.getsockname()[1]
                else:
                    self.port = listener.getsockname()[1]
                thread = threading.Thread(target=self._accept, args=(listener, pairing), daemon=True, name="morice-mesh-listener")
                self._threads.append(thread)
                thread.start()
        except BaseException:
            self.stop()
            raise

    def _accept(self, listener, pairing):
        while not self._stop.is_set():
            try:
                connection, address = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            connection.settimeout(2)
            with self._lock:
                self._connections.add(connection)
                permitted = self._slots.acquire(blocking=False)
            if not permitted:
                connection.close()
                with self._lock:
                    self._connections.discard(connection)
                continue
            try:
                self._pool.submit(self._serve, connection, address, pairing)
            except RuntimeError:
                connection.close()
                self._slots.release()

    def _serve(self, raw, address, pairing):
        connection = raw
        try:
            with self._lock:
                self._global.take()
                key = "ip:" + address[0]
                if key not in self._rates and len(self._rates) >= 128:
                    raise ValueError("Node admission limit reached.")
                self._rates.setdefault(key, RateLimit(3000)).take()
                ctx = self.credentials.context(server=True, pairing=True) if pairing else self._server_context
            connection = ctx.wrap_socket(raw, server_side=True)
            with self._lock:
                self._connections.discard(raw)
                self._connections.add(connection)
            request = receive(connection)
            operation = request.get("op")
            if operation not in OPERATIONS or set(request) - {"version", "op", "request_id", "sender", "payload"}:
                raise ValueError("Malformed RPC.")
            identifier(request.get("request_id"))
            sender = identifier(request.get("sender"))
            payload = request.get("payload", {})
            if not isinstance(payload, dict):
                raise ValueError("RPC payload must be an object.")
            if pairing:
                if operation not in {"pair", "pair_status"}:
                    raise PermissionError("Pairing endpoint cannot execute commands.")
                response = self._pairing(operation, sender, payload, address[0])
            else:
                peer_id = certificate_id(connection.getpeercert(binary_form=True))
                trusted = self.store.get(peer_id)
                if peer_id != sender or trusted is None or trusted.revoked or certificate_pin(connection.getpeercert(binary_form=True)) != certificate_pin(trusted.identity_public_key):
                    raise PermissionError("Untrusted peer identity.")
                response = self.dispatcher(operation, payload, trusted)
            with self._lock:
                self.metrics["received"] += 1
            connection.sendall(encode({"version": VERSION, "request_id": request["request_id"], "sender": self.credentials.node_id, "payload": response}))
        except (OSError, ValueError, KeyError, TypeError, PermissionError):
            with self._lock:
                self.metrics["rejected"] += 1
        finally:
            connection.close()
            with self._lock:
                self._connections.discard(raw)
                self._connections.discard(connection)
            self._slots.release()

    def enable_pairing(self, seconds=120):
        if not self.running:
            self.start()
        with self._lock:
            self._pair_until = time.monotonic() + min(120, max(1, float(seconds)))
            self._pair_code = f"{secrets.randbelow(1000000):06d}"
            self._pair_failures = 0
            self._pending.clear()
            return {"code": self._pair_code, "fingerprint": self.credentials.pin, "node_id": self.credentials.node_id,
                    "host": self.host, "pair_port": self.pair_port, "port": self.port, "expires_in": seconds}

    def pairing_status(self):
        with self._lock:
            return {"enabled": time.monotonic() < self._pair_until, "pending": [{"request_id": key, "node_id": p["descriptor"].device_id,
                     "name": p["descriptor"].device_name, "state": p["state"]} for key, p in self._pending.items()]}

    def disable_pairing(self):
        with self._lock:
            self._pair_until = 0
            self._pair_code = ""
            self._pending.clear()

    def _pairing(self, operation, sender, payload, host):
        with self._lock:
            if time.monotonic() >= self._pair_until:
                raise PermissionError("Pairing window expired or closed.")
            if operation == "pair_status":
                pending = self._pending.get(identifier(payload.get("pair_id")))
                if not pending or pending["descriptor"].device_id != sender:
                    raise PermissionError("No matching pairing request.")
                return {"state": pending["state"], "descriptor": self.descriptor.to_dict(), "certificate": self.credentials.certificate,
                        "port": self.port, "grants": list(pending.get("grants", ())) }
            if self._pair_failures >= 5 or not self._pair_code or not hmac.compare_digest(str(payload.get("code", "")), self._pair_code):
                self._pair_failures += 1
                raise PermissionError("Invalid pairing code.")
            if len(self.store.list()) >= 64 and self.store.get(sender) is None:
                raise ValueError("Trusted node limit reached.")
            cert = payload.get("certificate", "")
            if not isinstance(cert, str) or len(cert) > 8192 or certificate_id(cert) != sender:
                raise ValueError("Pairing identity does not match certificate.")
            descriptor = NodeDescriptor.from_dict(payload.get("descriptor", {}))
            if descriptor.device_id != sender:
                raise ValueError("Pairing descriptor identity mismatch.")
            if descriptor.protocol_version != VERSION or not 1 <= len(descriptor.device_name) <= 80:
                raise ValueError("Incompatible/invalid device descriptor.")
            pair_id = uuid.uuid4().hex
            port = descriptor.metadata.get("port", 0)
            if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
                raise ValueError("Invalid node service port.")
            self._pending[pair_id] = {"descriptor": replace(descriptor, metadata={"host": host, "port": port}), "certificate": cert, "state": "pairing"}
            self._pair_code = ""  # One attempt consumes the code; no replay.
            return {"pair_id": pair_id, "state": "pairing"}

    def approve_pair(self, pair_id, capabilities, *, user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Local pairing confirmation is required.")
        with self._lock:
            if time.monotonic() >= self._pair_until:
                raise PermissionError("Pairing expired.")
            pending = self._pending[pair_id]
            if pending["state"] != "pairing":
                raise PermissionError("Pairing was already consumed.")
            grants = tuple(capabilities)
            self.store.enroll(pending["descriptor"], pending["certificate"], b"", grants, user_approved=True)
            pending.update(state="trusted", grants=grants)
            self._refresh_context()

    def revoke(self, node_id):
        self.store.revoke(node_id)
        with self._lock:
            self._refresh_context()
            # RPCs are short lived. Closing all sockets also interrupts an already-authenticated revoked peer.
            for connection in tuple(self._connections):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()

    def rpc(self, host, port, operation, payload=None, *, peer_id="", pairing_pin="", timeout=2):
        if not self.running or self._stop.is_set():
            raise ConnectionError("Device Mesh is disabled.")
        if not .01 <= timeout <= 5:
            raise ValueError("RPC timeout must be within .01..5 seconds.")
        if pairing_pin:
            if len(pairing_pin) != 64:
                raise ValueError("Full certificate fingerprint required.")
            ctx = self.credentials.context(pairing=True)
            pin = pairing_pin
        else:
            peer = self.store.get(peer_id)
            if peer is None or peer.revoked:
                raise PermissionError("Remote node is untrusted or revoked.")
            pin = certificate_pin(peer.identity_public_key)
            with self._lock:
                ctx = self._client_contexts.get(peer_id)
                if ctx is None:
                    ctx = self.credentials.context(certificates=[peer.identity_public_key])
                    self._client_contexts[peer_id] = ctx
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        with socket.create_connection((host, int(port)), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=None) as connection:
                connection.settimeout(timeout)
                if not hmac.compare_digest(certificate_pin(connection.getpeercert(binary_form=True)), pin):
                    raise PermissionError("Remote certificate fingerprint mismatch.")
                with self._lock:
                    self._connections.add(connection)
                try:
                    connection.sendall(encode({"version": VERSION, "op": operation, "sender": self.credentials.node_id,
                        "request_id": request_id, "payload": payload or {}}))
                    result = receive(connection)
                    if result.get("request_id") != request_id or peer_id and result.get("sender") != peer_id:
                        raise ValueError("Mismatched RPC response.")
                    return result["payload"]
                finally:
                    with self._lock:
                        self._connections.discard(connection)
                        self.metrics["rpc_count"] += 1
                        self.metrics["rpc_ms"] += (time.perf_counter() - started) * 1000

    def stop(self):
        self._stop.set()
        self.disable_pairing()
        with self._lock:
            for value in (*self._listeners, *self._connections):
                try:
                    value.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                value.close()
            self._listeners.clear()
            self._connections.clear()
        for thread in self._threads:
            thread.join(1)
        self._threads.clear()
        if self._pool:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None
