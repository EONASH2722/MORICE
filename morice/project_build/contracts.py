"""Project domain state; task, permission and verification contracts stay shared."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum


class BuildStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HealthStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NOT_CHECKED = "not_checked"
    UNAVAILABLE = "unavailable"


@dataclass
class Requirement:
    text: str
    category: str = "functional"
    origin: str = "user_requested"
    check: dict = field(default_factory=dict)
    requirement_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "not_verified"
    evidence: list = field(default_factory=list)

    def __post_init__(self):
        if not self.text.strip() or self.origin not in {"user_requested", "inferred_default", "optional_suggestion", "technical_necessity"}:
            raise ValueError("Requirements need text and an explicit origin.")
        if self.status not in {"done", "partial", "failed", "deferred", "not_verified"}:
            raise ValueError("Invalid requirement status.")


@dataclass(frozen=True)
class BuildLimits:
    max_repairs: int = 3
    max_wall_seconds: float = 300
    max_files: int = 80
    max_file_bytes: int = 2_000_000
    max_workspace_bytes: int = 20_000_000
    max_model_calls: int = 8
    max_attempts_per_issue: int = 2

    def __post_init__(self):
        import math
        if not 0 <= self.max_repairs <= 5 or not 1 <= self.max_model_calls <= 16 or not 1 <= self.max_attempts_per_issue <= 5:
            raise ValueError("Invalid repair/model bounds.")
        if not math.isfinite(self.max_wall_seconds) or not 1 <= self.max_wall_seconds <= 3600:
            raise ValueError("Build wall-time must be within 1..3600 seconds.")
        if not 1 <= self.max_files <= 128 or not 1 <= self.max_file_bytes <= 2_000_000 or not 1 <= self.max_workspace_bytes <= 100_000_000:
            raise ValueError("Invalid workspace bounds.")


@dataclass
class ProjectBuildSession:
    project_root: str
    user_goal: str
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    project_id: str = ""
    requirements: list[Requirement] = field(default_factory=list)
    constraints: dict = field(default_factory=dict)
    target_platform: str = "local"
    framework: str = ""
    language: str = ""
    fingerprint: dict = field(default_factory=dict)
    architecture: dict = field(default_factory=dict)
    ownership: dict = field(default_factory=dict)
    changes: list = field(default_factory=list)
    commands: dict = field(default_factory=dict)
    dependencies: dict = field(default_factory=dict)
    health: dict = field(default_factory=lambda: {k: HealthStatus.NOT_CHECKED.value for k in
        ("source", "dependencies", "build", "tests", "runtime", "ui", "artifacts")})
    definition_of_done: list = field(default_factory=list)
    task_graphs: list = field(default_factory=list)
    workers: list = field(default_factory=list)
    command_evidence: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    screenshots: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    repair_history: list = field(default_factory=list)
    applied_changes: dict = field(default_factory=dict)
    last_undo_id: str = ""
    status: str = BuildStatus.PLANNED.value
    milestone: str = "planning"
    revision: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metrics: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        data = dict(value)
        data["requirements"] = [Requirement(**r) for r in data.get("requirements", ())]
        return cls(**data)

    @property
    def success(self):
        return self.status == BuildStatus.VERIFIED.value

    def result_card(self):
        return {"session_id": self.session_id, "project": self.project_root, "status": self.status,
            "requirements": {"verified": sum(r.status == "done" for r in self.requirements), "total": len(self.requirements)},
            "health": dict(self.health), "artifacts": list(self.artifacts),
            "issues": [v for v in self.issues if v.get("status") != "resolved"]}
