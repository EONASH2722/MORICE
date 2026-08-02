from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    GENERAL_CHAT = "general_chat"
    CODING = "coding"
    MATHEMATICS = "mathematics"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    PROGRAMMING = "programming"
    PROJECT_MODIFICATION = "project_modification"
    FILE_EDITING = "file_editing"
    FILE_SEARCH = "file_search"
    INTERNET_SEARCH = "internet_search"
    IMAGE_ANALYSIS = "image_analysis"
    DOCUMENT_ANALYSIS = "document_analysis"
    TERMINAL_TASK = "terminal_task"
    SYSTEM_TASK = "system_task"
    DESKTOP_CONTROL = "desktop_control"
    VISUALIZATION = "visualization"
    SIMULATION = "simulation"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    REASONING = "reasoning"
    PLANNING = "planning"
    DATA_ANALYSIS = "data_analysis"


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGEROUS = "dangerous"


class PermissionStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    GRANTED = "granted"
    DENIED = "denied"
    REQUIRED = "required"


class ToolStatus(str, Enum):
    READY = "ready"
    DISABLED = "disabled"
    UNHEALTHY = "unhealthy"
    UNAVAILABLE = "unavailable"


class ExecutionStage(str, Enum):
    INTENT_DETECTION = "intent_detection"
    CONTEXT_RETRIEVAL = "context_retrieval"
    CONVERSATION_MEMORY = "conversation_memory"
    PROJECT_CONTEXT = "project_context"
    CAPABILITY_DETECTION = "capability_detection"
    PLANNING = "planning"
    TOOL_SELECTION = "tool_selection"
    PERMISSION_CHECK = "permission_check"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    RESULT_COLLECTION = "result_collection"
    RENDERER_SELECTION = "renderer_selection"
    UI_UPDATE = "ui_update"
    FINAL_RESPONSE = "final_response"


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    display_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permissions: tuple[str, ...] = ()
    supported_platforms: tuple[str, ...] = ("any",)
    timeout_seconds: float = 30.0
    cancellation_supported: bool = False
    dependencies: tuple[str, ...] = ()
    health_status: ToolStatus = ToolStatus.READY
    version: str = "1.0"
    risk: RiskLevel = RiskLevel.READ_ONLY
    idempotent: bool = True

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["health_status"] = self.health_status.value
        value["risk"] = self.risk.value
        return value


@dataclass(frozen=True)
class ToolCall:
    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""
    permission_token: str = ""


@dataclass
class ToolResult:
    tool_id: str
    success: bool
    duration_ms: float
    output: Any = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    permission_status: PermissionStatus = PermissionStatus.NOT_REQUIRED
    verified: bool = False
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["permission_status"] = self.permission_status.value
        return value


@dataclass(frozen=True)
class AgentSubtask:
    subtask_id: str
    title: str
    intent: IntentType
    description: str
    dependencies: tuple[str, ...] = ()
    suggested_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentPlan:
    request_id: str
    request: str
    intents: tuple[IntentType, ...]
    subtasks: tuple[AgentSubtask, ...]
    stages: tuple[ExecutionStage, ...] = tuple(ExecutionStage)
    public_summary: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "request": self.request,
            "intents": [intent.value for intent in self.intents],
            "subtasks": [
                {
                    **asdict(subtask),
                    "intent": subtask.intent.value,
                }
                for subtask in self.subtasks
            ],
            "stages": [stage.value for stage in self.stages],
            "publicSummary": list(self.public_summary),
        }


@dataclass(frozen=True)
class ProjectContext:
    root: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    relevant_files: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class AgentRequestContext:
    request_id: str
    request: str
    plan: AgentPlan
    conversation: tuple[dict[str, str], ...]
    project: ProjectContext
    capabilities: tuple[str, ...]
    model_route: dict[str, Any]
    renderer: str = ""
    created_at: str = ""


@dataclass
class AgentExecutionResult:
    request_id: str
    success: bool
    verified: bool
    message: str
    tool_results: list[ToolResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    stage_status: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "success": self.success,
            "verified": self.verified,
            "message": self.message,
            "toolResults": [result.to_dict() for result in self.tool_results],
            "warnings": self.warnings,
            "errors": self.errors,
            "artifacts": self.artifacts,
            "stageStatus": self.stage_status,
        }


@dataclass(frozen=True)
class ActionRecord:
    action_id: str
    timestamp: str
    tool_id: str
    parameters: dict[str, Any]
    duration_ms: float
    success: bool
    verified: bool
    modified_files: tuple[str, ...] = ()
    generated_files: tuple[str, ...] = ()
    artifacts: tuple[dict[str, Any], ...] = ()
    errors: tuple[str, ...] = ()
    replayable: bool = False
    undo_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
