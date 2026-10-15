"""Opt-in sampled sources hold existing resource leases until explicit cleanup."""
from __future__ import annotations

import base64
import hashlib
import threading
import time
import uuid
from dataclasses import dataclass

from ..kernel import ResourceClaim, ResourceDescriptor


@dataclass
class Stream:
    stream_id: str
    peer: str
    capability: str
    source: object
    fps: float
    expires: float
    last_frame: float = 0
    frames: int = 0
    bytes_sent: int = 0


class StreamManager:
    def __init__(self, kernel, *, max_streams=2):
        self.kernel, self.max_streams = kernel, max_streams
        self.sources, self.active = {}, {}
        self._lock = threading.RLock()

    def register_source(self, capability, factory, *, resource, available, permission):
        # Factories are installed by the local platform adapter, never by a remote message.
        self.sources[capability] = (factory, resource, available, permission)
        if self.kernel.resources.descriptor(resource) is None:
            self.kernel.resources.register(ResourceDescriptor(resource))
        if self.kernel.resources.descriptor("NETWORK") is None:
            self.kernel.resources.register(ResourceDescriptor("NETWORK", 2))

    def operate(self, capability, args, context):
        peer = context.metadata.get("mesh_peer", "local")
        with self._lock:
            self.expire()
            operation = args.get("op")
            if operation == "start":
                factory, resource, available, permission = self.sources[capability]
                from ..unified_intelligence import PermissionState
                if not available() or self.kernel.permissions.controller.state(permission) != PermissionState.GRANTED:
                    raise PermissionError("Platform capture permission is unavailable.")
                fps = args.get("fps", 1)
                ttl = args.get("ttl", 30)
                if isinstance(fps, bool) or not isinstance(fps, (float, int)) or not .2 <= fps <= 5 or isinstance(ttl, bool) or not isinstance(ttl, (float, int)) or not 1 <= ttl <= 60 or len(self.active) >= self.max_streams:
                    raise ValueError("Invalid sampled stream limits.")
                key = uuid.uuid4().hex
                if not self.kernel.resources.acquire("stream:" + key, (ResourceClaim(resource, exclusive=True), ResourceClaim("NETWORK"))):
                    raise ValueError("Capture resource is busy.")
                try:
                    source = factory(args)
                    self.active[key] = Stream(key, peer, capability, source, fps, time.monotonic() + ttl)
                except BaseException:
                    self.kernel.resources.release("stream:" + key)
                    raise
                return {"stream_id": key, "active": True, "fps": fps}
            key = args.get("stream_id")
            stream = self.active.get(key)
            if stream is None:
                if operation == "stop":
                    return {"active": False, "stream_id": key}
                raise ValueError("Stream has stopped or expired.")
            if stream.peer != peer or stream.capability != capability:
                raise PermissionError("Stream ownership mismatch.")
            if operation == "stop":
                self._stop(key)
                return {"stream_id": key, "active": False}
            if operation != "sample":
                raise ValueError("Unsupported stream operation.")
            if time.monotonic() - stream.last_frame < 1 / stream.fps:
                return {"stream_id": key, "active": True, "sample_ready": False}
            data = stream.source.read()  # Adapter contract: native bounded read, at most 1 second.
            if not isinstance(data, bytes) or not 0 < len(data) <= 128 * 1024:
                raise ValueError("Sample exceeds the bounded stream frame size.")
            stream.last_frame = time.monotonic()
            stream.frames += 1
            stream.bytes_sent += len(data)
            return {"stream_id": key, "active": True, "sample_ready": True, "sequence": stream.frames,
                    "sha256": hashlib.sha256(data).hexdigest(), "data": base64.b64encode(data).decode()}

    def observe(self, capability, args, context):
        peer = context.metadata.get("mesh_peer", "local")
        with self._lock:
            streams = [s for s in self.active.values() if s.peer == peer and s.capability == capability]
            stream = self.active.get(args.get("stream_id")) if args.get("stream_id") else streams[-1] if streams else None
            if stream and (stream.peer != peer or stream.capability != capability):
                raise PermissionError("Stream observation ownership mismatch.")
            return {"active": bool(stream), "stream_id": stream.stream_id if stream else args.get("stream_id", ""),
                    "sequence": stream.frames if stream else 0}

    def _stop(self, key):
        stream = self.active[key]
        stream.source.close()  # A failing native close retains its lease and handle for reconciliation.
        self.active.pop(key)
        self.kernel.resources.release("stream:" + key)

    def expire(self):
        from ..unified_intelligence import PermissionState
        with self._lock:
            for key, stream in list(self.active.items()):
                _, _, available, permission = self.sources[stream.capability]
                if time.monotonic() >= stream.expires or not available() or self.kernel.permissions.controller.state(permission) != PermissionState.GRANTED:
                    self._stop(key)

    def stop_owned(self, peer, capability):
        with self._lock:
            for key, stream in list(self.active.items()):
                if stream.peer == peer and stream.capability == capability:
                    self._stop(key)

    def disconnect(self, peer):
        with self._lock:
            for key, stream in list(self.active.items()):
                if stream.peer == peer:
                    self._stop(key)

    def close(self):
        with self._lock:
            for key in list(self.active):
                self._stop(key)

    def snapshot(self):
        with self._lock:
            return [{"stream_id": s.stream_id, "node_id": s.peer, "capability": s.capability,
                     "fps": s.fps, "frames": s.frames, "bytes": s.bytes_sent} for s in self.active.values()]
