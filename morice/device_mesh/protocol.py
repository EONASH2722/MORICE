"""Bounded TLS RPC framing. No encryption algorithms live in this protocol."""
from __future__ import annotations

import json
import math
import re
import struct
import time
from collections import deque

VERSION = "morice-mesh/2"
MAX_FRAME = 384 * 1024
CHUNK_BYTES = 128 * 1024
ID = re.compile(r"^[a-zA-Z0-9_.:-]{1,100}$")
CAPABILITY = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,4}$")
OPERATIONS = {"pair", "pair_status", "hello", "ping", "submit", "status", "observe", "cancel", "event"}


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid mesh identifier.")
    return value


def capability(value):
    if not isinstance(value, str) or not CAPABILITY.fullmatch(value):
        raise ValueError("Invalid capability name.")
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def bounded(value, depth=0):
    if depth > 12:
        raise ValueError("Message nesting exceeds limit.")
    if isinstance(value, dict):
        if len(value) > 128 or any(not isinstance(k, str) or len(k) > 120 for k in value):
            raise ValueError("Object exceeds limits.")
        for item in value.values():
            bounded(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 256:
            raise ValueError("Array exceeds limits.")
        for item in value:
            bounded(item, depth + 1)
    elif isinstance(value, str):
        if len(value) > 200000:
            raise ValueError("String exceeds limit.")
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite number.")
    elif value is not None and not isinstance(value, (int, bool)):
        raise ValueError("Unsupported message value.")


def encode(value):
    bounded(value)
    payload = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    if len(payload) > MAX_FRAME:
        raise ValueError("Message exceeds frame limit.")
    return struct.pack("!I", len(payload)) + payload


def receive(sock):
    def exact(size):
        result = bytearray()
        while len(result) < size:
            part = sock.recv(size - len(result))
            if not part:
                raise ConnectionError("Mesh connection closed.")
            result.extend(part)
        return bytes(result)
    size = struct.unpack("!I", exact(4))[0]
    if not 2 <= size <= MAX_FRAME:
        raise ValueError("Invalid mesh frame length.")
    try:
        value = json.loads(exact(size), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid number.")))
    except (RecursionError, UnicodeError) as error:
        raise ValueError("Invalid JSON message.") from error
    bounded(value)
    if not isinstance(value, dict) or value.get("version") != VERSION:
        raise ValueError("Incompatible mesh protocol.")
    return value


class RateLimit:
    def __init__(self, limit=120, seconds=60):
        self.limit, self.seconds = limit, seconds
        self.samples = deque()

    def take(self):
        now = time.monotonic()
        while self.samples and self.samples[0] <= now - self.seconds:
            self.samples.popleft()
        if len(self.samples) >= self.limit:
            raise ValueError("Mesh rate limit exceeded.")
        self.samples.append(now)
