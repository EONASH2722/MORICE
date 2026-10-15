"""Bounded public lifecycle timings; no prompts or private reasoning."""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TimingRecord:
    task_id: str
    capability_id: str
    execution_id: str
    stage: str
    timestamp: float
    duration_ms: float = 0.0


class TelemetryCollector:
    def __init__(self, profiler: Any = None, logger=None, max_records: int = 2000):
        self._records: deque[TimingRecord] = deque(maxlen=max_records)
        self._lock = threading.RLock()
        self.profiler = profiler
        self.logger = logger

    def record(self, task_id: str, capability_id: str, execution_id: str, stage: str, duration_ms: float = 0.0) -> None:
        record = TimingRecord(task_id, capability_id, execution_id, stage, time.perf_counter(), duration_ms)
        with self._lock:
            self._records.append(record)
        if self.profiler:
            self.profiler.record_duration(f"kernel.{stage}", duration_ms)

    def records(self) -> tuple[TimingRecord, ...]:
        with self._lock:
            return tuple(self._records)
