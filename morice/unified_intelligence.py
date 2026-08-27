from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol


class CapabilityState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PERMISSION_REQUIRED = "permission_required"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class RiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AccessMode(str, Enum):
    STANDARD = "standard"
    FULL = "full"


class PermissionState(str, Enum):
    ASK = "ask"
    GRANTED = "granted"
    DENIED = "denied"
    OS_REQUIRED = "os_required"
    UNSUPPORTED = "unsupported"


class ExecutionPath(str, Enum):
    INSTANT = "instant"
    SEMANTIC = "semantic"
    AGENTIC = "agentic"


class GoalState(str, Enum):
    PLANNED = "planned"
    WAITING_PERMISSION = "waiting_permission"
    RUNNING = "running"
    RECOVERING = "recovering"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _now() -> float:
    return time.time()


def _clean_text(value: Any, limit: int = 8_000) -> str:
    return " ".join(str(value or "").split())[:limit]


def _safe_json(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return str(value)


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    required: tuple[str, ...] = ()
    denied: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class _OneUseApproval:
    task_id: str
    capability_id: str
    arguments_digest: str
    expires_at: float


class PermissionController:
    """Device- and action-aware permission policy with exact one-use approvals.

    Full access only activates permission groups already granted by the host/user.
    It never changes unsupported, denied, OS-gated, or high-risk confirmation rules.
    """

    def __init__(
        self,
        *,
        mode: AccessMode | str = AccessMode.STANDARD,
        states: Mapping[str, PermissionState | str] | None = None,
        approval_ttl_seconds: float = 120.0,
    ):
        self.mode = AccessMode(mode)
        self.approval_ttl_seconds = max(5.0, float(approval_ttl_seconds))
        self._states = {
            str(group): PermissionState(state)
            for group, state in (states or {}).items()
        }
        self._approvals: dict[str, _OneUseApproval] = {}
        self._lock = threading.RLock()

    def set_mode(
        self,
        mode: AccessMode | str,
        *,
        supported_and_authorized: Iterable[str] = (),
    ) -> None:
        with self._lock:
            self.mode = AccessMode(mode)
            if self.mode == AccessMode.FULL:
                for group in supported_and_authorized:
                    clean = str(group).strip()
                    if clean and self._states.get(clean) not in {
                        PermissionState.DENIED,
                        PermissionState.UNSUPPORTED,
                        PermissionState.OS_REQUIRED,
                    }:
                        self._states[clean] = PermissionState.GRANTED

    def set_state(self, group: str, state: PermissionState | str) -> None:
        clean = str(group).strip()
        if not clean:
            raise ValueError("Permission group cannot be empty.")
        with self._lock:
            self._states[clean] = PermissionState(state)

    def state(self, group: str) -> PermissionState:
        with self._lock:
            return self._states.get(str(group), PermissionState.ASK)

    def issue_one_use(
        self,
        task_id: str,
        capability_id: str,
        arguments: Mapping[str, Any],
    ) -> str:
        if not task_id or not capability_id:
            raise ValueError("Task and capability identifiers are required.")
        token = uuid.uuid4().hex
        with self._lock:
            self._approvals[token] = _OneUseApproval(
                task_id,
                capability_id,
                _fingerprint(arguments),
                _now() + self.approval_ttl_seconds,
            )
        return token

    def authorize(
        self,
        *,
        task_id: str,
        capability_id: str,
        arguments: Mapping[str, Any],
        permissions: Iterable[str],
        risk: RiskClass | str,
        approval_token: str = "",
    ) -> PermissionDecision:
        clean_risk = RiskClass(risk)
        required: list[str] = []
        denied: list[str] = []
        for group in dict.fromkeys(str(item) for item in permissions if str(item)):
            state = self.state(group)
            if state in {PermissionState.DENIED, PermissionState.UNSUPPORTED}:
                denied.append(group)
            elif state != PermissionState.GRANTED:
                required.append(group)
        if denied:
            return PermissionDecision(
                False,
                denied=tuple(denied),
                reason="Permission denied or unsupported: " + ", ".join(denied),
            )
        if required:
            return PermissionDecision(
                False,
                required=tuple(required),
                reason="Permission is required: " + ", ".join(required),
            )
        needs_exact = clean_risk == RiskClass.HIGH or (
            clean_risk == RiskClass.MEDIUM and not tuple(permissions)
        )
        if needs_exact and not self._consume_one_use(
            approval_token,
            task_id,
            capability_id,
            arguments,
        ):
            return PermissionDecision(
                False,
                required=("exact_action_confirmation",),
                reason="This action needs an exact one-use confirmation.",
            )
        return PermissionDecision(True)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._prune()
            return {
                "mode": self.mode.value,
                "groups": {
                    key: value.value for key, value in sorted(self._states.items())
                },
                "pendingExactApprovals": len(self._approvals),
            }

    def _consume_one_use(
        self,
        token: str,
        task_id: str,
        capability_id: str,
        arguments: Mapping[str, Any],
    ) -> bool:
        if not token:
            return False
        with self._lock:
            self._prune()
            record = self._approvals.pop(token, None)
        return bool(
            record
            and record.task_id == task_id
            and record.capability_id == capability_id
            and record.arguments_digest == _fingerprint(arguments)
            and record.expires_at >= _now()
        )

    def _prune(self) -> None:
        expired = [
            token
            for token, record in self._approvals.items()
            if record.expires_at < _now()
        ]
        for token in expired:
            self._approvals.pop(token, None)


@dataclass(frozen=True)
class ContextEntity:
    entity_id: str
    kind: str
    label: str
    aliases: tuple[str, ...] = ()
    source: str = "conversation"
    payload: dict[str, Any] = field(default_factory=dict)
    observed_at: float = field(default_factory=_now)
    salience: float = 0.7
    half_life_seconds: float = 900.0
    active: bool = False

    def score(self, at: float | None = None) -> float:
        age = max(0.0, (at or _now()) - self.observed_at)
        half_life = max(1.0, self.half_life_seconds)
        recency = 0.5 ** (age / half_life)
        return max(0.0, min(1.0, self.salience)) * recency + (
            0.24 if self.active else 0.0
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReferenceResolution:
    reference: str
    entity: ContextEntity | None
    confidence: float
    alternatives: tuple[ContextEntity, ...] = ()
    needs_clarification: bool = False


class WorkingMemory:
    """Bounded situation model with explicit recency decay and task history."""

    def __init__(self, *, max_entities: int = 256, max_tasks: int = 100):
        self.max_entities = max(16, int(max_entities))
        self.max_tasks = max(10, int(max_tasks))
        self._entities: dict[str, ContextEntity] = {}
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = threading.RLock()

    def observe(self, entity: ContextEntity) -> None:
        if not entity.entity_id or not entity.kind or not entity.label:
            raise ValueError("Context entities need an id, kind, and label.")
        with self._lock:
            if entity.active:
                self._entities = {
                    key: (
                        ContextEntity(
                            **{
                                **value.to_dict(),
                                "active": False,
                            }
                        )
                        if value.kind == entity.kind and value.active
                        else value
                    )
                    for key, value in self._entities.items()
                }
            self._entities[entity.entity_id] = entity
            self._trim_entities()

    def resolve(
        self,
        reference: str,
        *,
        expected_kinds: Iterable[str] = (),
        source_preference: Iterable[str] = (),
        minimum_confidence: float = 0.42,
        ambiguity_margin: float = 0.12,
    ) -> ReferenceResolution:
        clean = _clean_text(reference, 500).casefold()
        kinds = {str(item).casefold() for item in expected_kinds if str(item)}
        sources = tuple(str(item).casefold() for item in source_preference if str(item))
        now = _now()
        scored: list[tuple[float, ContextEntity]] = []
        with self._lock:
            values = tuple(self._entities.values())
        for entity in values:
            if kinds and entity.kind.casefold() not in kinds:
                continue
            names = {entity.label.casefold(), *(item.casefold() for item in entity.aliases)}
            lexical = 0.0
            if clean and clean in names:
                lexical = 0.55
            elif clean and any(clean in name or name in clean for name in names):
                lexical = 0.3
            source_bonus = 0.0
            if sources and entity.source.casefold() in sources:
                source_bonus = max(
                    0.02,
                    0.12 - (0.02 * sources.index(entity.source.casefold())),
                )
            kind_bonus = 0.1 if kinds else 0.0
            score = min(1.0, entity.score(now) + lexical + source_bonus + kind_bonus)
            scored.append((score, entity))
        scored.sort(key=lambda item: (-item[0], -item[1].observed_at, item[1].label))
        if not scored or scored[0][0] < minimum_confidence:
            return ReferenceResolution(reference, None, 0.0, needs_clarification=True)
        top_score, top = scored[0]
        alternatives = tuple(item[1] for item in scored[1:4])
        ambiguous = bool(
            len(scored) > 1
            and scored[1][0] >= minimum_confidence
            and top_score - scored[1][0] < ambiguity_margin
        )
        return ReferenceResolution(
            reference,
            None if ambiguous else top,
            top_score,
            alternatives,
            needs_clarification=ambiguous,
        )

    def record_task(self, task: TaskRecord) -> None:
        with self._lock:
            self._tasks[task.task_id] = task
            while len(self._tasks) > self.max_tasks:
                self._tasks.pop(next(iter(self._tasks)), None)

    def task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def latest_task(self) -> TaskRecord | None:
        with self._lock:
            return next(reversed(self._tasks.values()), None) if self._tasks else None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            entities = sorted(
                self._entities.values(),
                key=lambda item: (-item.score(), -item.observed_at),
            )[:64]
            tasks = list(self._tasks.values())[-20:]
        return {
            "entities": [item.to_dict() for item in entities],
            "tasks": [item.to_dict() for item in tasks],
        }

    def _trim_entities(self) -> None:
        if len(self._entities) <= self.max_entities:
            return
        ordered = sorted(
            self._entities.values(),
            key=lambda item: (item.active, item.score(), item.observed_at),
        )
        for entity in ordered[: len(self._entities) - self.max_entities]:
            self._entities.pop(entity.entity_id, None)


@dataclass(frozen=True)
class GoalSpec:
    request: str
    objective: str
    desired_state: dict[str, Any] = field(default_factory=dict)
    target_hints: tuple[dict[str, Any], ...] = ()
    required_information: tuple[str, ...] = ()
    candidate_capabilities: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    confidence: float = 0.5
    complexity: str = "semantic"
    presentation: tuple[str, ...] = ("text",)
    raw_transcript: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityOutcome:
    success: bool
    verified: bool
    output: Any = None
    error: str = ""
    retryable: bool = False
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapabilityHandler(Protocol):
    def __call__(
        self,
        arguments: Mapping[str, Any],
        cancel_event: threading.Event,
    ) -> CapabilityOutcome | Mapping[str, Any]: ...


class CapabilityVerifier(Protocol):
    def __call__(self, outcome: CapabilityOutcome) -> bool: ...


@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    display_name: str
    description: str
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    state: CapabilityState = CapabilityState.AVAILABLE
    risk: RiskClass = RiskClass.LOW
    alternatives: tuple[str, ...] = ()
    concurrent: bool = True
    background: bool = True
    speculative_safe: bool = False
    estimated_latency_ms: float = 100.0
    verification_required: bool = True
    max_retries: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        value["risk"] = self.risk.value
        return value


@dataclass(frozen=True)
class CapabilityCall:
    call_id: str
    capability_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()
    verify: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionPlan:
    task_id: str
    goal: GoalSpec
    path: ExecutionPath
    calls: tuple[CapabilityCall, ...]
    parallel_layers: tuple[tuple[str, ...], ...]
    resolved_targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing_information: tuple[str, ...] = ()
    clarification: str = ""
    route_latency_ms: float = 0.0

    @property
    def ready(self) -> bool:
        return not self.clarification and not self.missing_information

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "goal": self.goal.to_dict(),
            "path": self.path.value,
            "calls": [item.to_dict() for item in self.calls],
            "parallelLayers": [list(item) for item in self.parallel_layers],
            "resolvedTargets": _safe_json(self.resolved_targets),
            "missingInformation": list(self.missing_information),
            "clarification": self.clarification,
            "routeLatencyMs": self.route_latency_ms,
            "ready": self.ready,
        }


@dataclass
class TaskRecord:
    task_id: str
    request: str
    objective: str
    state: GoalState = GoalState.PLANNED
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    attempted_capabilities: list[str] = field(default_factory=list)
    recovery_count: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        return value


class CapabilityRegistry:
    def __init__(self):
        self._specs: dict[str, CapabilitySpec] = {}
        self._handlers: dict[str, CapabilityHandler] = {}
        self._verifiers: dict[str, CapabilityVerifier] = {}
        self._lock = threading.RLock()

    def register(
        self,
        spec: CapabilitySpec,
        handler: CapabilityHandler | None = None,
        verifier: CapabilityVerifier | None = None,
    ) -> None:
        if not spec.capability_id.strip():
            raise ValueError("Capability id cannot be empty.")
        with self._lock:
            self._specs[spec.capability_id] = spec
            if handler is not None:
                self._handlers[spec.capability_id] = handler
            if verifier is not None:
                self._verifiers[spec.capability_id] = verifier

    def update_state(
        self,
        capability_id: str,
        state: CapabilityState | str,
        *,
        detail: str = "",
    ) -> None:
        with self._lock:
            spec = self._specs.get(capability_id)
            if spec is None:
                raise KeyError(capability_id)
            value = spec.to_dict()
            value["state"] = CapabilityState(state)
            value["risk"] = spec.risk
            value["metadata"] = {**spec.metadata, "stateDetail": detail}
            self._specs[capability_id] = CapabilitySpec(**value)

    def spec(self, capability_id: str) -> CapabilitySpec | None:
        with self._lock:
            return self._specs.get(capability_id)

    def handler(self, capability_id: str) -> CapabilityHandler | None:
        with self._lock:
            return self._handlers.get(capability_id)

    def verifier(self, capability_id: str) -> CapabilityVerifier | None:
        with self._lock:
            return self._verifiers.get(capability_id)

    def candidates_for(self, information: str) -> tuple[CapabilitySpec, ...]:
        with self._lock:
            values = tuple(self._specs.values())
        return tuple(
            sorted(
                (
                    spec
                    for spec in values
                    if information in spec.provides
                    and spec.state
                    in {CapabilityState.AVAILABLE, CapabilityState.PERMISSION_REQUIRED}
                ),
                key=lambda item: (
                    item.state != CapabilityState.AVAILABLE,
                    item.risk != RiskClass.LOW,
                    item.estimated_latency_ms,
                    item.capability_id,
                ),
            )
        )

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(
                spec.to_dict()
                for spec in sorted(self._specs.values(), key=lambda item: item.capability_id)
            )


class SemanticBackend(Protocol):
    def __call__(
        self,
        request: str,
        context: Mapping[str, Any],
        capabilities: Iterable[Mapping[str, Any]],
    ) -> Mapping[str, Any]: ...


class SemanticInterpreter:
    """Validates a compact model-produced goal/capability decision.

    The backend is intentionally injectable so local/cloud models can share the same
    schema. Without a backend, the safe fallback is conversation only; it never
    guesses that camera, screen, network, or physical control is required.
    """

    def __init__(self, backend: SemanticBackend | None = None):
        self.backend = backend

    def interpret(
        self,
        request: str,
        *,
        context: Mapping[str, Any],
        capabilities: Iterable[Mapping[str, Any]],
        raw_transcript: str = "",
    ) -> tuple[GoalSpec, tuple[dict[str, Any], ...]]:
        clean = _clean_text(request, 20_000)
        if not clean:
            raise ValueError("A request is required.")
        if self.backend is None:
            return (
                GoalSpec(
                    request=clean,
                    objective=clean,
                    candidate_capabilities=("conversation.respond",),
                    confidence=0.35,
                    complexity="semantic",
                    raw_transcript=_clean_text(raw_transcript, 20_000),
                ),
                (),
            )
        payload = self.backend(clean, context, capabilities)
        if not isinstance(payload, Mapping):
            raise ValueError("Semantic backend must return a structured mapping.")
        goal = GoalSpec(
            request=clean,
            objective=_clean_text(payload.get("goal") or payload.get("objective") or clean),
            desired_state=_safe_mapping(payload.get("desiredState", {})),
            target_hints=tuple(
                _safe_mapping(item)
                for item in _bounded_sequence(payload.get("targets", ()), 20)
                if isinstance(item, Mapping)
            ),
            required_information=_string_tuple(
                payload.get("requiredInformation", ()), 40
            ),
            candidate_capabilities=_string_tuple(
                payload.get("candidateCapabilities", ()), 40
            ),
            constraints=_string_tuple(payload.get("constraints", ()), 40),
            confidence=max(0.0, min(1.0, _number(payload.get("confidence"), 0.5))),
            complexity=(
                str(payload.get("complexity", "semantic"))
                if str(payload.get("complexity", "semantic"))
                in {"instant", "semantic", "agentic"}
                else "semantic"
            ),
            presentation=_string_tuple(payload.get("presentation", ("text",)), 10),
            raw_transcript=_clean_text(raw_transcript, 20_000),
        )
        actions = tuple(
            _safe_mapping(item)
            for item in _bounded_sequence(payload.get("actions", ()), 100)
            if isinstance(item, Mapping)
        )
        return goal, actions


class GoalExecutionOrchestrator:
    """Goal-first execution without placing heavy reasoning on the instant path."""

    def __init__(
        self,
        capabilities: CapabilityRegistry,
        *,
        semantic: SemanticInterpreter | None = None,
        memory: WorkingMemory | None = None,
        permissions: PermissionController | None = None,
        fast_router: Callable[[str, Mapping[str, Any]], CapabilityCall | None]
        | None = None,
        status_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
        max_parallel: int = 4,
        max_recovery_attempts: int = 3,
    ):
        self.capabilities = capabilities
        self.semantic = semantic or SemanticInterpreter()
        self.memory = memory or WorkingMemory()
        self.permissions = permissions or PermissionController()
        self.fast_router = fast_router
        self.status_callback = status_callback
        self.max_parallel = max(1, min(16, int(max_parallel)))
        self.max_recovery_attempts = max(0, min(8, int(max_recovery_attempts)))
        self._cancel: dict[str, threading.Event] = {}
        self._background = ThreadPoolExecutor(
            max_workers=self.max_parallel,
            thread_name_prefix="morice-goal",
        )
        self._lock = threading.RLock()

    def plan(
        self,
        request: str,
        *,
        context: Mapping[str, Any] | None = None,
        raw_transcript: str = "",
    ) -> ExecutionPlan:
        started = time.perf_counter()
        task_id = uuid.uuid4().hex
        situation = {
            **self.memory.snapshot(),
            **_safe_mapping(context or {}),
        }
        if self.fast_router is not None:
            fast_call = self.fast_router(request, situation)
            if fast_call is not None:
                spec = self.capabilities.spec(fast_call.capability_id)
                if spec and spec.state in {
                    CapabilityState.AVAILABLE,
                    CapabilityState.PERMISSION_REQUIRED,
                }:
                    goal = GoalSpec(
                        request=_clean_text(request, 20_000),
                        objective=_clean_text(request, 20_000),
                        candidate_capabilities=(fast_call.capability_id,),
                        confidence=1.0,
                        complexity="instant",
                        raw_transcript=_clean_text(raw_transcript, 20_000),
                    )
                    plan = ExecutionPlan(
                        task_id,
                        goal,
                        ExecutionPath.INSTANT,
                        (fast_call,),
                        ((fast_call.call_id,),),
                        route_latency_ms=(time.perf_counter() - started) * 1000,
                    )
                    self.memory.record_task(
                        TaskRecord(task_id, goal.request, goal.objective)
                    )
                    return plan
        goal, requested_actions = self.semantic.interpret(
            request,
            context=situation,
            capabilities=self.capabilities.snapshot(),
            raw_transcript=raw_transcript,
        )
        resolved, clarification = self._resolve_targets(goal)
        calls, missing = self._compile_calls(goal, requested_actions, resolved)
        layers = self._parallel_layers(calls)
        path = (
            ExecutionPath.AGENTIC
            if goal.complexity == "agentic" or len(calls) > 2
            else ExecutionPath.SEMANTIC
        )
        plan = ExecutionPlan(
            task_id,
            goal,
            path,
            calls,
            layers,
            resolved,
            tuple(missing),
            clarification,
            (time.perf_counter() - started) * 1000,
        )
        self.memory.record_task(TaskRecord(task_id, goal.request, goal.objective))
        return plan

    def execute(
        self,
        plan: ExecutionPlan,
        *,
        approval_tokens: Mapping[str, str] | None = None,
    ) -> TaskRecord:
        task = self.memory.task(plan.task_id)
        if task is None:
            task = TaskRecord(plan.task_id, plan.goal.request, plan.goal.objective)
            self.memory.record_task(task)
        if not plan.ready:
            task.state = GoalState.FAILED
            task.error = plan.clarification or (
                "Missing capability or information: "
                + ", ".join(plan.missing_information)
            )
            task.updated_at = _now()
            return task
        cancel_event = threading.Event()
        with self._lock:
            self._cancel[plan.task_id] = cancel_event
        call_map = {item.call_id: item for item in plan.calls}
        results: dict[str, CapabilityOutcome] = {}
        task.state = GoalState.RUNNING
        task.updated_at = _now()
        self._status("started", {"taskId": task.task_id, "objective": task.objective})
        try:
            for layer in plan.parallel_layers:
                if cancel_event.is_set():
                    task.state = GoalState.CANCELLED
                    break
                runnable = [call_map[call_id] for call_id in layer]
                if len(runnable) == 1 or not all(
                    (self.capabilities.spec(item.capability_id) or _UNAVAILABLE_SPEC).concurrent
                    for item in runnable
                ):
                    layer_results = {
                        call.call_id: self._run_call(
                            task,
                            call,
                            results,
                            cancel_event,
                            approval_tokens or {},
                        )
                        for call in runnable
                    }
                else:
                    layer_results = self._run_parallel(
                        task,
                        runnable,
                        results,
                        cancel_event,
                        approval_tokens or {},
                    )
                results.update(layer_results)
                if any(not value.success for value in layer_results.values()):
                    task.state = GoalState.FAILED
                    break
            if task.state == GoalState.RUNNING:
                task.state = GoalState.VERIFYING
                self._status("verifying", {"taskId": task.task_id})
                complete = bool(results) and all(
                    value.success and value.verified for value in results.values()
                )
                if not results:
                    complete = True
                task.state = GoalState.COMPLETED if complete else GoalState.FAILED
            task.result = {
                "verified": task.state == GoalState.COMPLETED,
                "outcomes": {
                    call_id: outcome.to_dict() for call_id, outcome in results.items()
                },
            }
            if task.state == GoalState.FAILED and not task.error:
                errors = [item.error for item in results.values() if item.error]
                task.error = errors[-1] if errors else "The goal could not be verified."
            self._status(
                "completed" if task.state == GoalState.COMPLETED else task.state.value,
                {
                    "taskId": task.task_id,
                    "verified": task.state == GoalState.COMPLETED,
                    "error": task.error,
                },
            )
            return task
        finally:
            task.updated_at = _now()
            with self._lock:
                self._cancel.pop(plan.task_id, None)

    def submit(
        self,
        plan: ExecutionPlan,
        *,
        approval_tokens: Mapping[str, str] | None = None,
    ) -> Future[TaskRecord]:
        return self._background.submit(
            self.execute,
            plan,
            approval_tokens=approval_tokens,
        )

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            event = self._cancel.get(task_id)
        if event is None:
            return False
        event.set()
        self._status("cancelled", {"taskId": task_id})
        return True

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            events = tuple(self._cancel.values())
        for event in events:
            event.set()
        self._background.shutdown(wait=wait, cancel_futures=True)

    def _resolve_targets(
        self, goal: GoalSpec
    ) -> tuple[dict[str, dict[str, Any]], str]:
        resolved: dict[str, dict[str, Any]] = {}
        for item in goal.target_hints:
            reference = _clean_text(item.get("reference", ""), 500)
            if not reference:
                continue
            result = self.memory.resolve(
                reference,
                expected_kinds=_string_tuple(item.get("expectedKinds", ()), 20),
                source_preference=_string_tuple(item.get("sourcePreference", ()), 20),
            )
            if result.entity is not None:
                resolved[reference] = result.entity.to_dict()
                continue
            if bool(item.get("required", True)):
                labels = [candidate.label for candidate in result.alternatives[:2]]
                suffix = f" ({' or '.join(labels)})" if labels else ""
                return resolved, f"Which target do you mean by {reference!r}{suffix}?"
        return resolved, ""

    def _compile_calls(
        self,
        goal: GoalSpec,
        requested_actions: tuple[dict[str, Any], ...],
        resolved: Mapping[str, Any],
    ) -> tuple[tuple[CapabilityCall, ...], list[str]]:
        calls: list[CapabilityCall] = []
        missing: list[str] = []
        used_ids: set[str] = set()
        if requested_actions:
            for index, item in enumerate(requested_actions, 1):
                capability_id = str(item.get("capability", "")).strip()
                if not capability_id:
                    continue
                spec = self.capabilities.spec(capability_id)
                if spec is None or spec.state in {
                    CapabilityState.UNAVAILABLE,
                    CapabilityState.UNSUPPORTED,
                    CapabilityState.FAILED,
                }:
                    missing.append(capability_id)
                    continue
                call_id = str(item.get("stepId") or f"step-{index}")[:120]
                if call_id in used_ids:
                    call_id = f"{call_id}-{index}"
                used_ids.add(call_id)
                arguments = _safe_mapping(item.get("arguments", {}))
                if resolved:
                    arguments.setdefault("resolvedTargets", _safe_json(resolved))
                calls.append(
                    CapabilityCall(
                        call_id,
                        capability_id,
                        arguments,
                        _string_tuple(item.get("dependsOn", ()), 50),
                        bool(item.get("verify", True)),
                    )
                )
        else:
            selected: list[CapabilitySpec] = []
            for information in goal.required_information:
                candidates = self.capabilities.candidates_for(information)
                preferred = [
                    item
                    for item in candidates
                    if item.capability_id in goal.candidate_capabilities
                ]
                if preferred:
                    candidates = tuple(preferred) + tuple(
                        item for item in candidates if item not in preferred
                    )
                if not candidates:
                    missing.append(information)
                    continue
                selected.append(candidates[0])
            for capability_id in goal.candidate_capabilities:
                spec = self.capabilities.spec(capability_id)
                if spec is None or spec.state in {
                    CapabilityState.UNAVAILABLE,
                    CapabilityState.UNSUPPORTED,
                    CapabilityState.FAILED,
                }:
                    missing.append(capability_id)
                elif spec not in selected:
                    selected.append(spec)
            selected = self._expand_requirements(selected, missing)
            for index, spec in enumerate(selected, 1):
                calls.append(
                    CapabilityCall(
                        f"step-{index}",
                        spec.capability_id,
                        {"resolvedTargets": _safe_json(resolved)} if resolved else {},
                        tuple(
                            call.call_id
                            for call in calls
                            if call.capability_id in spec.requires
                        ),
                    )
                )
        known_ids = {call.call_id for call in calls}
        normalized: list[CapabilityCall] = []
        for call in calls:
            dependencies = tuple(
                dependency for dependency in call.dependencies if dependency in known_ids
            )
            normalized.append(
                CapabilityCall(
                    call.call_id,
                    call.capability_id,
                    call.arguments,
                    dependencies,
                    call.verify,
                )
            )
        return tuple(normalized), list(dict.fromkeys(missing))

    def _expand_requirements(
        self,
        initial: list[CapabilitySpec],
        missing: list[str],
    ) -> list[CapabilitySpec]:
        ordered: list[CapabilitySpec] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(spec: CapabilitySpec) -> None:
            if spec.capability_id in visited:
                return
            if spec.capability_id in visiting:
                missing.append("capability_cycle:" + spec.capability_id)
                return
            visiting.add(spec.capability_id)
            for requirement in spec.requires:
                dependency = self.capabilities.spec(requirement)
                if dependency is None or dependency.state not in {
                    CapabilityState.AVAILABLE,
                    CapabilityState.PERMISSION_REQUIRED,
                }:
                    missing.append(requirement)
                    continue
                visit(dependency)
            visiting.remove(spec.capability_id)
            visited.add(spec.capability_id)
            ordered.append(spec)

        for item in initial:
            visit(item)
        return ordered

    @staticmethod
    def _parallel_layers(
        calls: Iterable[CapabilityCall],
    ) -> tuple[tuple[str, ...], ...]:
        values = {item.call_id: item for item in calls}
        remaining = set(values)
        completed: set[str] = set()
        layers: list[tuple[str, ...]] = []
        while remaining:
            ready = tuple(
                sorted(
                    call_id
                    for call_id in remaining
                    if set(values[call_id].dependencies) <= completed
                )
            )
            if not ready:
                raise ValueError("Capability plan contains a dependency cycle.")
            layers.append(ready)
            remaining.difference_update(ready)
            completed.update(ready)
        return tuple(layers)

    def _run_parallel(
        self,
        task: TaskRecord,
        calls: list[CapabilityCall],
        prior_results: Mapping[str, CapabilityOutcome],
        cancel_event: threading.Event,
        approval_tokens: Mapping[str, str],
    ) -> dict[str, CapabilityOutcome]:
        results: dict[str, CapabilityOutcome] = {}
        with ThreadPoolExecutor(
            max_workers=min(self.max_parallel, len(calls)),
            thread_name_prefix="morice-capability",
        ) as pool:
            futures = {
                pool.submit(
                    self._run_call,
                    task,
                    call,
                    prior_results,
                    cancel_event,
                    approval_tokens,
                ): call.call_id
                for call in calls
            }
            for future in as_completed(futures):
                call_id = futures[future]
                try:
                    results[call_id] = future.result()
                except Exception as exc:  # noqa: BLE001
                    results[call_id] = CapabilityOutcome(
                        False,
                        False,
                        error=f"Capability worker failed: {exc}",
                    )
        return results

    def _run_call(
        self,
        task: TaskRecord,
        call: CapabilityCall,
        prior_results: Mapping[str, CapabilityOutcome],
        cancel_event: threading.Event,
        approval_tokens: Mapping[str, str],
    ) -> CapabilityOutcome:
        if cancel_event.is_set():
            return CapabilityOutcome(False, False, error="Cancelled.")
        dependency_results = {
            dependency: prior_results[dependency].to_dict()
            for dependency in call.dependencies
            if dependency in prior_results
        }
        arguments = dict(call.arguments)
        if dependency_results:
            arguments["dependencyResults"] = dependency_results
        candidates = [call.capability_id]
        original = self.capabilities.spec(call.capability_id)
        if original:
            candidates.extend(original.alternatives)
        last = CapabilityOutcome(False, False, error="No available capability handler.")
        for capability_id in dict.fromkeys(candidates):
            if cancel_event.is_set():
                return CapabilityOutcome(False, False, error="Cancelled.")
            spec = self.capabilities.spec(capability_id)
            handler = self.capabilities.handler(capability_id)
            if spec is None or handler is None or spec.state != CapabilityState.AVAILABLE:
                continue
            decision = self.permissions.authorize(
                task_id=task.task_id,
                capability_id=capability_id,
                arguments=arguments,
                permissions=spec.permissions,
                risk=spec.risk,
                approval_token=(
                    approval_tokens.get(call.call_id)
                    or approval_tokens.get(capability_id)
                    or ""
                ),
            )
            if not decision.allowed:
                task.state = GoalState.WAITING_PERMISSION
                return CapabilityOutcome(
                    False,
                    False,
                    error=decision.reason,
                    metadata={
                        "requiredPermissions": list(decision.required),
                        "deniedPermissions": list(decision.denied),
                    },
                )
            retries = min(spec.max_retries, self.max_recovery_attempts)
            for attempt in range(retries + 1):
                if cancel_event.is_set():
                    return CapabilityOutcome(False, False, error="Cancelled.")
                self._status(
                    "executing",
                    {
                        "taskId": task.task_id,
                        "callId": call.call_id,
                        "capability": capability_id,
                        "label": spec.display_name,
                        "attempt": attempt + 1,
                    },
                )
                started = time.perf_counter()
                task.attempted_capabilities.append(capability_id)
                try:
                    raw = handler(arguments, cancel_event)
                    outcome = _coerce_outcome(raw, (time.perf_counter() - started) * 1000)
                except Exception as exc:  # noqa: BLE001
                    outcome = CapabilityOutcome(
                        False,
                        False,
                        error=str(exc),
                        retryable=attempt < retries,
                        duration_ms=(time.perf_counter() - started) * 1000,
                    )
                verified = outcome.verified
                if outcome.success and call.verify and spec.verification_required:
                    verifier = self.capabilities.verifier(capability_id)
                    verified = bool(verifier and verifier(outcome))
                elif outcome.success and (not call.verify or not spec.verification_required):
                    verified = True
                outcome = CapabilityOutcome(
                    outcome.success,
                    verified,
                    outcome.output,
                    outcome.error,
                    outcome.retryable,
                    outcome.duration_ms,
                    outcome.metadata,
                )
                task.observations.append(
                    {
                        "callId": call.call_id,
                        "capability": capability_id,
                        "attempt": attempt + 1,
                        "success": outcome.success,
                        "verified": outcome.verified,
                        "error": outcome.error,
                    }
                )
                if outcome.success and outcome.verified:
                    task.completed_steps.append(call.call_id)
                    # Recovery is a transient execution phase. Once a retry or
                    # alternate capability verifies the requested state, resume
                    # normal execution so the outer plan can finish.
                    task.state = GoalState.RUNNING
                    return outcome
                last = outcome
                if attempt < retries and outcome.retryable:
                    task.state = GoalState.RECOVERING
                    task.recovery_count += 1
                    self._status(
                        "recovering",
                        {
                            "taskId": task.task_id,
                            "callId": call.call_id,
                            "capability": capability_id,
                        },
                    )
                    continue
                break
            if not last.success or not last.verified:
                task.recovery_count += 1
                task.state = GoalState.RECOVERING
                continue
        task.failed_steps.append(call.call_id)
        task.error = last.error or "The action could not be verified."
        return last

    def _status(self, kind: str, payload: Mapping[str, Any]) -> None:
        if self.status_callback:
            self.status_callback(kind, _safe_mapping(payload))


def _coerce_outcome(value: Any, duration_ms: float) -> CapabilityOutcome:
    if isinstance(value, CapabilityOutcome):
        if value.duration_ms > 0:
            return value
        return CapabilityOutcome(
            value.success,
            value.verified,
            value.output,
            value.error,
            value.retryable,
            duration_ms,
            value.metadata,
        )
    if isinstance(value, Mapping):
        return CapabilityOutcome(
            bool(value.get("success", False)),
            bool(value.get("verified", False)),
            _safe_json(value.get("output")),
            _clean_text(value.get("error", ""), 4_000),
            bool(value.get("retryable", False)),
            max(0.0, _number(value.get("durationMs"), duration_ms)),
            _safe_mapping(value.get("metadata", {})),
        )
    return CapabilityOutcome(False, False, error="Capability returned an invalid result.")


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key)[:200]: _safe_json(item) for key, item in value.items()}


def _bounded_sequence(value: Any, maximum: int) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return ()
    items: list[Any] = []
    for item in value:
        items.append(item)
        if len(items) >= maximum:
            break
    return tuple(items)


def _string_tuple(value: Any, maximum: int) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            clean
            for item in _bounded_sequence(value, maximum)
            if (clean := _clean_text(item, 500))
        )
    )


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


_UNAVAILABLE_SPEC = CapabilitySpec(
    "unavailable",
    "Unavailable",
    "Unavailable capability",
    state=CapabilityState.UNAVAILABLE,
)


__all__ = [
    "AccessMode",
    "CapabilityCall",
    "CapabilityOutcome",
    "CapabilityRegistry",
    "CapabilitySpec",
    "CapabilityState",
    "ContextEntity",
    "ExecutionPath",
    "ExecutionPlan",
    "GoalExecutionOrchestrator",
    "GoalSpec",
    "GoalState",
    "PermissionController",
    "PermissionDecision",
    "PermissionState",
    "ReferenceResolution",
    "RiskClass",
    "SemanticInterpreter",
    "TaskRecord",
    "WorkingMemory",
]
