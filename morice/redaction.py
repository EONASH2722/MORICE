"""Bounded credential removal for diagnostics, never an authorization mechanism."""
from __future__ import annotations

import os
import re

SECRET_KEY = re.compile(r"(?i)password|secret|token|authorization|cookie|credential|api.?key|private.?key|pairing.?code")
_ASSIGNMENT = re.compile(r"(?i)((?:api[_-]?key|password|secret|token|authorization|cookie|credential)[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)")
_BEARER = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
_PRIVATE_KEY = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.S)
_URL_CREDENTIALS = re.compile(r"(?i)\b(https?://)[^\s/@]+:[^\s/@]+@")


def _environment_secrets():
    return tuple(secret for key, secret in os.environ.items() if SECRET_KEY.search(key) and len(secret) >= 8)


def redact_text(value, *, _secrets=None):
    value = str(value)
    value = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)
    value = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)
    value = _BEARER.sub(r"\1 [REDACTED]", value)
    value = _ASSIGNMENT.sub(r'\1"[REDACTED]"', value)
    for secret in _environment_secrets() if _secrets is None else _secrets:
        value = value.replace(secret, "[REDACTED]")
    return value


def redact_data(value, *, _depth=0, max_string=None, max_items=None, redact_keys=True, _secrets=None):
    if _depth >= 12:
        return "[depth limit]"
    if _secrets is None:
        # Snapshot once per record, without a cache that could miss rotation.
        _secrets = _environment_secrets()
    if isinstance(value, str):
        return redact_text(value, _secrets=_secrets)[:max_string]
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if redact_keys and SECRET_KEY.search(str(key)) else
                redact_data(item, _depth=_depth+1, max_string=max_string, max_items=max_items, redact_keys=redact_keys, _secrets=_secrets)
                for key, item in list(value.items())[:max_items]
                if key not in {"approval_token", "permission_token", "task_approvals"}}
    if isinstance(value, (list, tuple)):
        return [redact_data(item, _depth=_depth+1, max_string=max_string, max_items=max_items, redact_keys=redact_keys, _secrets=_secrets) for item in value[:max_items]]
    return value
