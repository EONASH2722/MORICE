"""Model-independent capability, context, result and policy contracts."""
from __future__ import annotations

import math
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any, Callable, Protocol

if TYPE_CHECKING:
    from .cancellation import CancellationToken

from ..unified_intelligence import RiskClass


def new_id() -> str:
    return uuid.uuid4().hex


def json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError(f"Not a JSON checkpoint value: {type(value).__name__}")


class Availability(str, Enum):
    REGISTERED = "registered"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    BLOCKED = "blocked"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    RETRYING = "retrying"

    @property
    def terminal(self) -> bool:
        return self in {self.BLOCKED, self.SUCCEEDED, self.FAILED, self.CANCELLED, self.SKIPPED}


class Priority(IntEnum):
    INTERACTIVE = 0
    NORMAL = 10
    BACKGROUND = 20
    LOW = 30


class ExecutionMode(str, Enum):
    FOREGROUND = "foreground"
    BACKGROUND = "background"


class ErrorCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    PERMISSION_DENIED = "permission_denied"
    DEPENDENCY_MISSING = "dependency_missing"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    EXECUTION_FAILED = "execution_failed"
    VERIFICATION_FAILED = "verification_failed"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    INTERNAL_ERROR = "internal_error"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ExecutionError:
    code: ErrorCode
    message: str
    detail: str = ""


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    evidence: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class ResourceClaim:
    resource: str
    amount: float = 1.0
    exclusive: bool = False
    node_id: str = "local"

    def __post_init__(self) -> None:
        if not self.resource or not self.node_id or not math.isfinite(self.amount) or self.amount <= 0:
            raise ValueError("Resource claims require a name, node and positive finite amount.")


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    name: str
    description: str = ""
    version: str = "1.0"
    provider: str = "morice"
    category: str = "general"
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    output_schema: dict[str, Any] = field(default_factory=dict)
    required_permissions: tuple[str, ...] = ()
    risk_level: RiskClass = RiskClass.LOW
    supported_platforms: tuple[str, ...] = ("any",)
    supported_resources: tuple[ResourceClaim, ...] = ()
    supports_background: bool = True
    supports_streaming: bool = False
    supports_cancellation: bool = False
    supports_verification: bool = False
    supports_retry: bool = False
    estimated_cost: float | None = None
    estimated_latency: float | None = None
    dependencies: tuple[str, ...] = ()
    status: Availability = Availability.REGISTERED
    timeout: float = 30.0
    # Short adapters with native bounded operations may avoid another thread.
    inline: bool = False
    node_id: str = "local"

    def __post_init__(self) -> None:
        if not self.capability_id or not self.name or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Capability id, name and positive finite timeout are required.")

    def to_dict(self) -> dict[str, Any]:
        return json_value(self)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    retryable_errors: tuple[ErrorCode, ...] = (ErrorCode.EXECUTION_FAILED,)
    backoff: float = 0.0
    alternative_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 10 or not math.isfinite(self.backoff) or self.backoff < 0:
            raise ValueError("Retries require 1..10 attempts and finite nonnegative backoff.")


@dataclass(frozen=True)
class VerificationPolicy:
    required: bool = False
    expected_outcome: Any = None


@dataclass
class ExecutionResult:
    status: TaskStatus
    success: bool
    output: Any = None
    observations: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[ExecutionError] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    retryable: bool = False
    verification_required: bool = False
    verification: VerificationResult | None = None
    execution_id: str = field(default_factory=new_id)
    task_id: str = ""
    capability_id: str = ""
    # Original domain object is retained only for in-process compatibility.
    legacy_result: Any = field(default=None, repr=False)

    @classmethod
    def failure(cls, code: ErrorCode, message: str, *, detail: str = "", retryable: bool = False) -> ExecutionResult:
        status = TaskStatus.CANCELLED if code == ErrorCode.CANCELLED else TaskStatus.FAILED
        return cls(status, False, errors=[ExecutionError(code, message, detail)], retryable=retryable)

    def to_dict(self) -> dict[str, Any]:
        return {key: json_value(getattr(self, key)) for key in self.__dataclass_fields__ if key != "legacy_result"}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ExecutionResult:
        value = dict(value)
        value["status"] = TaskStatus(value["status"])
        value["errors"] = [ExecutionError(ErrorCode(e["code"]), e["message"], e.get("detail", "")) for e in value.get("errors", ())]
        if v := value.get("verification"):
            value["verification"] = VerificationResult(VerificationStatus(v["status"]), tuple(v.get("evidence", ())), v.get("message", ""))
        return cls(**value)


@dataclass(frozen=True)
class ExecutionContext:
    user_request_id: str = ""
    conversation_id: str = ""
    project_id: str = ""
    research_project_id: str = ""
    active_files: tuple[str, ...] = ()
    active_window: str = ""
    active_device: str = ""
    permissions: tuple[str, ...] = ()
    user_preferences: dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    parent_task_id: str = ""
    capability_id: str = ""
    resource_budget: dict[str, float] = field(default_factory=dict)
    deadline: float | None = None  # monotonic; never serialized
    cancellation_token: CancellationToken | None = field(default=None, repr=False)
    approval_token: str = field(default="", repr=False)
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)
    progress: Callable[[str], None] | None = field(default=None, repr=False)

    def for_task(self, task_id: str, capability_id: str, **changes: Any) -> ExecutionContext:
        return replace(self, task_id=task_id, capability_id=capability_id, **changes)


class CapabilityHandler(Protocol):
    def __call__(self, inputs: dict[str, Any], context: ExecutionContext) -> ExecutionResult: ...


class Verifier(Protocol):
    def __call__(self, result: ExecutionResult, expected_outcome: Any, context: ExecutionContext) -> VerificationResult: ...
