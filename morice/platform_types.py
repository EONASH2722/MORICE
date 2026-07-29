from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    CODING = "coding"
    RESEARCH = "research"
    PLANNING = "planning"
    DOCUMENTATION = "documentation"
    DEBUGGING = "debugging"
    TESTING = "testing"
    VISUALIZATION = "visualization"
    SIMULATION = "simulation"
    DESKTOP = "desktop"
    FILE = "file"
    VOICE = "voice"


class RunState(str, Enum):
    PLANNED = "planned"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkItemState(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AgentEnvelope:
    message_id: str
    run_id: str
    sender: AgentRole
    recipient: AgentRole
    kind: str
    payload: dict[str, Any]
    created_at: str
    correlation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sender"] = self.sender.value
        value["recipient"] = self.recipient.value
        return value


@dataclass
class DelegatedWorkItem:
    item_id: str
    title: str
    description: str
    role: AgentRole
    intent: str
    dependencies: tuple[str, ...] = ()
    suggested_tools: tuple[str, ...] = ()
    destructive: bool = False
    state: WorkItemState = WorkItemState.PENDING
    attempts: int = 0
    max_attempts: int = 2
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["role"] = self.role.value
        value["state"] = self.state.value
        return value


@dataclass
class PlatformRun:
    run_id: str
    request_id: str
    request: str
    state: RunState
    work_items: list[DelegatedWorkItem]
    created_at: str
    updated_at: str
    project_root: str = ""
    progress: int = 0
    recovery_count: int = 0
    messages: list[AgentEnvelope] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "requestId": self.request_id,
            "request": self.request,
            "state": self.state.value,
            "workItems": [item.to_dict() for item in self.work_items],
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "projectRoot": self.project_root,
            "progress": self.progress,
            "recoveryCount": self.recovery_count,
            "messages": [message.to_dict() for message in self.messages],
            "artifacts": list(self.artifacts),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class ProjectDashboard:
    root: str
    name: str
    overview: dict[str, Any]
    tasks: tuple[dict[str, Any], ...]
    timeline: tuple[dict[str, Any], ...]
    architecture: dict[str, Any]
    dependencies: tuple[str, ...]
    git: dict[str, Any]
    recent_commits: tuple[dict[str, Any], ...]
    issues: tuple[dict[str, Any], ...]
    open_files: tuple[str, ...]
    memory: tuple[dict[str, Any], ...]
    renderer_status: str
    build_status: str
    test_results: tuple[dict[str, Any], ...]
    performance: dict[str, Any]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeNode:
    node_id: str
    kind: str
    title: str
    content: str
    project_id: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeEdge:
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReleaseCheck:
    name: str
    status: str
    detail: str
    critical: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
