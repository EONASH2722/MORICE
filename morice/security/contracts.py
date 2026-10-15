from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class IncidentState(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    CONTAINED = "CONTAINED"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    MONITORING = "MONITORING"


@dataclass(frozen=True)
class SecurityFinding:
    category: str
    severity: str
    summary: str
    evidence: tuple[str, ...]
    object_ref: str
    confidence: float = 1.0
    recommendation: str = "Review the recorded evidence; no automatic containment."
    node_id: str = "local"
    process_id: int | None = None
    file_path: str = ""
    network_ref: str = ""
    status: str = "OPEN"
    indicator_origin: str = ""
    finding_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.severity not in {"INFO","LOW","MEDIUM","HIGH","CRITICAL"} or not 0 <= self.confidence <= 1:
            raise ValueError("Invalid finding severity/confidence.")
        if self.category not in {"SUSPICIOUS_PROCESS","SUSPICIOUS_CHILD_PROCESS","PERSISTENCE","UNEXPECTED_STARTUP", "NETWORK_LISTENER",
                                 "KNOWN_HASH","RESOURCE_ANOMALY","FILE_CHANGE","SECURITY_TOOL_DISABLED","UNKNOWN"}:
            raise ValueError("Invalid finding category.")
