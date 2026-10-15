"""Agent identity and budgets; execution and verification stay in the kernel."""
from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..kernel import VerificationPolicy


class WorkerState(str, Enum):
    CREATED = "created"
    WAITING = "waiting"
    READY = "ready"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RuntimeLimits:
    max_workers: int = 4
    max_workflows: int = 2
    max_subtasks: int = 32
    max_depth: int = 8
    max_attempts: int = 2
    max_runtime: float = 300
    max_cpu_tasks: int = 2
    max_io_tasks: int = 4
    max_model_calls: int = 8
    max_model_tokens: int = 16_384
    max_context_chars: int = 12_000
    local_model_concurrency: int = 1
    vram_mb: int = 6144

    def __post_init__(self):
        bounds = {"max_workers": (1, 8), "max_workflows": (1, 4), "max_subtasks": (1, 128),
            "max_depth": (1, 16), "max_attempts": (1, 10), "max_cpu_tasks": (1, 8),
            "max_io_tasks": (1, 8), "max_model_calls": (0, 64), "max_model_tokens": (0, 262144),
            "max_context_chars": (1024, 64000), "local_model_concurrency": (1, 1), "vram_mb": (1, 131072)}
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            if not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{name} must be within {low}..{high}.")
        if not math.isfinite(self.max_runtime) or not 0 < self.max_runtime <= 3600:
            raise ValueError("Workflow runtime must be within 0..3600 seconds.")

    @classmethod
    def for_host(cls):
        # No GPU/model probe or import during startup. Configure VRAM explicitly
        # when the host differs; one local inference remains conservative.
        cpus = os.cpu_count() or 2
        return cls(max_workers=min(4, max(2, cpus // 2)), max_cpu_tasks=min(2, cpus))


@dataclass(frozen=True)
class ContextPolicy:
    include_project: bool = False
    include_files: bool = False
    upstream: bool = True


@dataclass(frozen=True)
class AgentRole:
    role_id: str
    display_name: str
    description: str
    allowed_capabilities: tuple[str, ...]
    preferred_capabilities: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    model_requirements: tuple[str, ...] = ()
    resource_profile: tuple[str, ...] = ()
    default_verification_policy: VerificationPolicy = field(default_factory=VerificationPolicy)
    context_policy: ContextPolicy = field(default_factory=ContextPolicy)
    result_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    enabled: bool = True


@dataclass(frozen=True)
class ContextPacket:
    workflow_id: str
    task_id: str
    goal: str
    task: str
    allowed_capabilities: tuple[str, ...]
    sources: tuple[dict[str, Any], ...]
    upstream: dict[str, Any]
    project: str = ""
    files: tuple[str, ...] = ()
    constraints: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False
    estimated_tokens: int = 0


@dataclass(frozen=True)
class AgentResult:
    worker_id: str
    role: str
    task_id: str
    status: WorkerState
    summary: str
    structured_output: Any
    artifacts: tuple[dict[str, Any], ...] = ()
    evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[dict[str, str], ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    verification_required: bool = False
    verification: str = "not_applicable"
    retryable: bool = False
    uncertainty: str = ""
