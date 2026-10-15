"""Bounded nonredirecting transport. Delayed retries are rescheduled by ambient rules."""
from __future__ import annotations

import http.client
import json
import time
import socket
import threading
from urllib.parse import urlsplit


class ProviderHTTPError(RuntimeError):
    def __init__(self, status, retry_at=0):
        super().__init__(f"Provider request failed ({status}).")
        self.status, self.retry_at = status, retry_at


class BoundedHTTP:
    def __init__(self, base_url, *, fixture=False, timeout=2, max_bytes=1048576):
        self.base = urlsplit(base_url)
        if self.base.username or self.base.password or self.base.query or self.base.fragment:
            raise ValueError("Credentials/query fragments are forbidden in provider URLs.")
        if self.base.scheme != "https" and not (fixture and self.base.scheme == "http" and self.base.hostname in {"127.0.0.1", "localhost", "::1"}):
            raise ValueError("Providers require HTTPS; explicit fixtures may use loopback HTTP.")
        if not self.base.hostname or not 0 < timeout <= 5 or not 1024 <= max_bytes <= 2097152:
            raise ValueError("Invalid provider transport configuration.")
        self.fixture, self.timeout, self.max_bytes = fixture, timeout, max_bytes
        self.calls = 0

    def request(self, method, path, *, token="", payload=None, context=None, headers=None):
        if not path.startswith("/") or path.startswith("//") or "\r" in path or "\n" in path:
            raise ValueError("Provider paths must be relative to the configured origin.")
        def checkpoint():
            if context and context.cancellation_token:
                context.cancellation_token.raise_if_cancelled()
            if context and context.deadline and time.monotonic() >= context.deadline:
                raise TimeoutError("Provider deadline reached.")
        checkpoint()
        end=time.monotonic()+self.timeout
        remaining = max(.01, context.deadline - time.monotonic()) if context and context.deadline else self.timeout
        cls = http.client.HTTPSConnection if self.base.scheme == "https" else http.client.HTTPConnection
        conn = cls(self.base.hostname, self.base.port, timeout=min(self.timeout, remaining))
        request_headers = {"Accept": "application/json", "User-Agent": "MORICE-Connector/1.0", **(headers or {})}
        if token:
            request_headers["Authorization"] = "Bearer " + token
        data = None
        if payload is not None:
            data = json.dumps(payload, allow_nan=False).encode()
            if len(data) > 131072:
                raise ValueError("Provider write exceeds the request budget.")
            request_headers["Content-Type"] = "application/json"
        watchdog=None
        def expire():
            current=conn.sock
            if current is not None:
                try:current.shutdown(socket.SHUT_RDWR)
                except OSError:pass
                current.close()
        try:
            self.calls += 1
            conn.connect()
            checkpoint()
            remaining=min(end-time.monotonic(),context.deadline-time.monotonic() if context and context.deadline else self.timeout)
            if remaining<=0:raise TimeoutError("Provider connection exceeded its total budget.")
            watchdog=threading.Timer(remaining,expire);watchdog.daemon=True;watchdog.name="morice-http-deadline";watchdog.start()
            conn.request(method, self.base.path.rstrip("/") + path, data, request_headers)
            response = conn.getresponse()
            response_headers = {k.lower(): v for k, v in response.getheaders()}
            status = response.status
            raw = bytearray()
            while True:
                checkpoint()
                if time.monotonic()>=end:raise TimeoutError("Provider response exceeded its total budget.")
                chunk = response.read1(min(16384, self.max_bytes + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > self.max_bytes:
                    raise ValueError("Provider response exceeds the byte budget.")
            checkpoint()
            if status == 304:
                return status, None, response_headers
            if status >= 300:
                delay = response_headers.get("retry-after", "60")
                try:
                    seconds = min(3600, max(1, float(delay)))
                except ValueError:
                    from email.utils import parsedate_to_datetime
                    try:
                        seconds = min(3600, max(1, parsedate_to_datetime(delay).timestamp() - time.time()))
                    except (ValueError, TypeError, OverflowError):
                        seconds = 60
                raise ProviderHTTPError(status, time.time() + seconds if status == 429 or status == 403 and response_headers.get("x-ratelimit-remaining") == "0" else 0)
            value = json.loads(raw.decode("utf-8")) if raw else None
            return status, value, response_headers
        finally:
            if watchdog:watchdog.cancel()
            conn.close()
