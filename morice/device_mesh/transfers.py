"""Bounded chunks in an explicitly shared inbox; hash proof before atomic publish."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

from ..kernel import ResourceClaim, ResourceDescriptor
from ..project_build.workspace import safe_path
from .protocol import CHUNK_BYTES, identifier


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


class FileInbox:
    def __init__(self, root, kernel, *, max_bytes=1024 * 1024 * 1024):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.partial = self.root / ".mesh-partials"
        self.partial.mkdir(exist_ok=True)
        if self.partial.resolve().parent != self.root or self.partial.is_symlink():
            raise ValueError("Unsafe partial-file directory.")
        self.kernel, self.max_bytes = kernel, max_bytes
        self._lock = threading.RLock()
        self.records = {}
        for path in self.partial.glob("*.json"):
            if not re.fullmatch(r"[a-f0-9]{32}", path.stem) or path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Unsafe persisted transfer metadata.")
            self._load(path.stem)
        self.expire()
        kernel.resources.register(ResourceDescriptor("TRANSFER_SLOT", 4))

    def _target(self, name):
        if not isinstance(name, str) or not name or len(name) > 240 or name.startswith(".mesh-partials"):
            raise ValueError("Invalid shared filename.")
        return safe_path(self.root, name)

    def _save(self, key, record):
        target = self.partial / (key + ".json")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(record), encoding="utf-8")
        os.replace(temporary, target)

    def _load(self, key):
        if key not in self.records:
            path = self.partial / (key + ".json")
            if path.exists():
                self.records[key] = json.loads(path.read_text())
        return self.records.get(key)

    def _release(self, key):
        self.kernel.resources.release("transfer:" + key)

    def _claim(self, key):
        owner = "transfer:" + key
        if owner not in self.kernel.resources.snapshot() and not self.kernel.resources.acquire(owner, (ResourceClaim("TRANSFER_SLOT"),)):
            raise ValueError("Transfer slots are exhausted.")

    def execute(self, args, context):
        key = identifier(args.get("transfer_id"))
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise ValueError("Transfer ID must be a UUID hex value.")
        peer = context.metadata.get("mesh_peer", "local")
        op = args.get("op")
        with self._lock:
            self.expire()
            record = self._load(key)
            if record and record["peer"] != peer:
                raise PermissionError("Transfer belongs to a different node.")
            if op == "begin":
                target = self._target(args.get("name"))
                size, digest = args.get("size"), args.get("sha256")
                if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= self.max_bytes or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                    raise ValueError("Invalid transfer size or digest.")
                if record and (record["name"], record["size"], record["sha256"]) != (args["name"], size, digest):
                    raise ValueError("Transfer ID was reused for different content.")
                if target.exists():
                    if target.is_file() and target.stat().st_size == size and file_hash(target) == digest:
                        self._release(key)
                        return {"complete": True, "size": size, "sha256": digest, "offset": size, "deduplicated": True}
                    raise FileExistsError("Destination already contains different data.")
                if record is None:
                    if len(self.records) >= 64 or len(list(self.partial.glob("*.json"))) >= 64:
                        raise ValueError("Transfer record limit reached.")
                    record = {"name": args["name"], "size": size, "sha256": digest, "peer": peer, "offset": 0,
                              "chunks": [], "complete": False, "updated": time.time()}
                    self.records[key] = record
                part = self.partial / (key + ".partial")
                if part.is_symlink():
                    raise ValueError("Partial path cannot be a symlink.")
                if not part.exists():
                    part.touch()
                # Verify every existing range before accepting a resume offset.
                with part.open("rb") as stream:
                    valid = all(hashlib.sha256(stream.read(length)).hexdigest() == sha for length, sha in record["chunks"])
                    valid = valid and stream.tell() == record["offset"] and not stream.read(1)
                if not valid:
                    self._release(key)
                    raise ValueError("Partial data is corrupt; explicit cancellation/restart required.")
                self._claim(key)
                record["updated"] = time.time()
                self._save(key, record)
                return self.observe(args, context)
            if record is None:
                if op == "cancel":
                    return {"cancelled": True, "complete": False}
                raise ValueError("Transfer does not exist.")
            if op == "chunk":
                self._claim(key)
                if record["complete"]:
                    return self.observe(args, context)
                data = base64.b64decode(args.get("data", ""), validate=True)
                offset = args.get("offset")
                if isinstance(offset, int) and not isinstance(offset, bool) and 0 <= offset < record["offset"] and 0 < len(data) <= CHUNK_BYTES:
                    part = self.partial / (key + ".partial")
                    if not part.is_symlink():
                        with part.open("rb") as stream:
                            stream.seek(offset)
                            if stream.read(len(data)) == data:
                                return self.observe(args, context)
                    raise ValueError("Duplicate transfer range differs from existing bytes.")
                if isinstance(offset, bool) or not isinstance(offset, int) or not 0 < len(data) <= CHUNK_BYTES or offset != record["offset"] or offset + len(data) > record["size"]:
                    raise ValueError("Invalid transfer range.")
                part = self.partial / (key + ".partial")
                if part.is_symlink():
                    raise ValueError("Unsafe partial path.")
                with part.open("r+b") as stream:
                    stream.seek(offset); stream.write(data); stream.flush(); os.fsync(stream.fileno())
                record["chunks"].append([len(data), hashlib.sha256(data).hexdigest()])
                record.update(offset=offset + len(data), updated=time.time())
                self._save(key, record)
                return self.observe(args, context)
            if op == "finish":
                target = self._target(record["name"])
                if record["complete"]:
                    return self.observe(args, context)
                part = self.partial / (key + ".partial")
                if part.is_symlink() or not part.exists() or part.stat().st_size != record["size"] or file_hash(part) != record["sha256"]:
                    self._release(key)
                    raise ValueError("Transfer size/hash verification failed.")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise FileExistsError("Destination changed during transfer.")
                # Atomic, no-overwrite hard link publishes only the fully verified bytes.
                os.link(part, target)
                part.unlink()
                record.update(complete=True, updated=time.time())
                self._release(key)
                self._save(key, record)
                return self.observe(args, context)
            if op == "cancel":
                if not record["complete"]:
                    (self.partial / (key + ".partial")).unlink(missing_ok=True)
                (self.partial / (key + ".json")).unlink(missing_ok=True)
                self.records.pop(key, None)
                self._release(key)
                return {"cancelled": True, "complete": False}
            if op == "status":
                return self.observe(args, context)
            raise ValueError("Unsupported transfer operation.")

    def observe(self, args, context):
        with self._lock:
            key = identifier(args["transfer_id"])
            record = self._load(key)
            if record is None:
                return {"complete": False, "cancelled": args.get("op") == "cancel"}
            if record["peer"] != context.metadata.get("mesh_peer", "local"):
                raise PermissionError("Transfer ownership mismatch.")
            path = self._target(record["name"]) if record["complete"] else self.partial / (key + ".partial")
            size = path.stat().st_size if path.exists() else 0
            digest = file_hash(path) if record["complete"] and path.is_file() else ""
            return {"complete": record["complete"] and size == record["size"] and digest == record["sha256"],
                    "offset": size, "size": record["size"], "sha256": digest, "name": record["name"]}

    def read(self, args, context):
        path = self._target(args.get("name"))
        if not path.is_file() or path.stat().st_size > self.max_bytes:
            raise ValueError("Shared source file is unavailable or too large.")
        size = path.stat().st_size
        if args.get("op") == "stat":
            return {"name": args["name"], "size": size, "sha256": file_hash(path)}
        if args.get("op") != "read":
            raise ValueError("Unsupported shared read operation.")
        offset = args.get("offset", 0)
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= size:
            raise ValueError("Invalid shared read range.")
        with path.open("rb") as stream:
            stream.seek(offset); data = stream.read(CHUNK_BYTES)
        return {"name": args["name"], "offset": offset, "size": size, "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(), "data": base64.b64encode(data).decode()}

    def observe_read(self, args, context):
        return {k: v for k, v in self.read(args, context).items() if k != "data"}

    def expire(self):
        with self._lock:
            for key, record in list(self.records.items()):
                if time.time() - record["updated"] > 300:
                    self._release(key)
                    if not record["complete"]:
                        (self.partial / (key + ".partial")).unlink(missing_ok=True)
                    (self.partial / (key + ".json")).unlink(missing_ok=True)
                    self.records.pop(key, None)

    def disconnect(self, peer):
        with self._lock:
            for key, record in self.records.items():
                if record["peer"] == peer:
                    self._release(key)

    def close(self):
        with self._lock:
            for key in self.records:
                self._release(key)
