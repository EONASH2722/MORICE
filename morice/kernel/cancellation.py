"""Linked cooperative cancellation, including interruptible backoff."""
from __future__ import annotations

import threading
import time


class CancelledError(Exception):
    pass


class CancellationToken:
    def __init__(self, parent: CancellationToken | None = None):
        self._event = threading.Event()
        self.parent = parent
        self.reason = ""

    @property
    def cancelled(self) -> bool:
        return self._event.is_set() or bool(self.parent and self.parent.cancelled)

    def cancel(self, reason: str = "Cancelled by user.") -> None:
        self.reason = reason
        self._event.set()

    def child(self) -> CancellationToken:
        return CancellationToken(self)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError(self.reason or "Parent task cancelled.")

    def wait(self, seconds: float) -> bool:
        end = time.monotonic() + max(0.0, seconds)
        while not self.cancelled:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return False
            self._event.wait(min(remaining, 0.02))
        return True
