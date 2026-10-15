"""Durable attempt detail beside existing ActionHistory; no second final history."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from ..redaction import redact_text


_SECRET = re.compile(r"password|secret|token|authorization|cookie|credential|api.?key", re.I)


def redact(value, key="", _depth=0):
    if _depth >= 12:
        return "[depth limit]"
    if key.casefold() in {"value", "text", "content", "goal", "data", "audio", "frame", "pairing_code", "private_key"}:
        return "[omitted]"
    if _SECRET.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k)[:120]: redact(v, str(k), _depth+1) for k, v in list(value.items())[:256]}
    if isinstance(value, (list, tuple)):
        return [redact(v, _depth=_depth+1) for v in value[:80]]
    if isinstance(value, str):
        if value.startswith(("https://", "http://")):
            parsed = urlsplit(value)
            host = parsed.hostname or ""
            if parsed.port:
                host += f":{parsed.port}"
            value = urlunsplit((parsed.scheme, host, parsed.path,
                urlencode([(k, "[redacted]" if _SECRET.search(k) else v) for k, v in parse_qsl(parsed.query)]), ""))
        return redact_text(value[:1500])
    return value


class ActionJournal:
    def __init__(self, path=None, *, limit=500):
        self.path = Path(path) if path else None
        self.limit = max(10, min(2000, limit))
        self._lock = threading.RLock()
        self._attempts = {}
        self.load_error = ""
        if self.path and self.path.is_file():
            try:
                if self.path.stat().st_size > 16 * 1024 * 1024:
                    raise ValueError("Journal exceeds its recovery size budget.")
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("attempts"), list):
                    raise ValueError("Unsupported journal schema.")
                attempts = data["attempts"]
                if any(not isinstance(v, dict) or not isinstance(v.get("attempt_id"), str) or not 1 <= len(v["attempt_id"]) <= 128 for v in attempts):
                    raise ValueError("Invalid journal attempt identity.")
                self._attempts = {v["attempt_id"]: v for v in attempts[-self.limit:]}
            except (OSError, ValueError, TypeError, RecursionError):
                self.load_error = "Action journal is unreadable or unsupported; preserve it and review recovery before mutating actions."

    def update(self, attempt_id, *, terminal=False, finalize=False, durable=True, **fields):
        with self._lock:
            if self.load_error:
                raise RuntimeError(self.load_error)
            item = self._attempts.setdefault(attempt_id, {"attempt_id": attempt_id, "started_at": time.time()})
            if item.get("terminal") and not finalize:
                return  # Detached late work cannot overwrite cancellation.
            item.update(redact(fields))
            item["updated_at"] = time.time()
            item["terminal"] = terminal
            while len(self._attempts) > self.limit:
                self._attempts.pop(next(iter(self._attempts)))
            if self.path and durable:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
                try:
                    with temporary.open("w", encoding="utf-8") as stream:
                        json.dump({"version": 1, "attempts": list(self._attempts.values())}, stream, ensure_ascii=False, allow_nan=False)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, self.path)
                finally:
                    temporary.unlink(missing_ok=True)

    def attempts(self, action_id=""):
        with self._lock:
            return tuple(json.loads(json.dumps(v)) for v in self._attempts.values() if not action_id or v.get("action_id") == action_id)

    def interrupted(self):
        return tuple(v for v in self.attempts() if not v.get("terminal"))
