"""Worker lifecycle around kernel execution; no tools or model instances here."""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field, replace

from ..kernel import (CancellationToken, ErrorCode, EventType, ExecutionResult, KernelEvent,
    TaskStatus, VerificationStatus)
from ..kernel.contracts import new_id
from .contracts import AgentResult, WorkerState
from .state import build_packet


@dataclass
class WorkerRecord:
    worker_id: str
    task_id: str
    role: str
    state: WorkerState = WorkerState.CREATED
    progress: str = ""
    description: str = ""
    started_at: float | None = None
    completed_at: float | None = None
    queued_at: float = field(default_factory=time.perf_counter)


def result_state(result):
    if result.status == TaskStatus.BLOCKED:
        return WorkerState.BLOCKED
    if result.status == TaskStatus.SKIPPED:
        return WorkerState.SKIPPED
    if result.status == TaskStatus.CANCELLED:
        return WorkerState.CANCELLED
    if any(e.code == ErrorCode.TIMEOUT for e in result.errors):
        return WorkerState.TIMED_OUT
    return WorkerState.SUCCEEDED if result.success else WorkerState.FAILED


class WorkerManager:
    def __init__(self, kernel, roles, state, limits):
        self.kernel, self.roles, self.state, self.limits = kernel, roles, state, limits
        self._records = {}
        self._tokens = {}
        self._cancelled = set()
        self._lock = threading.RLock()
        self._active = 0
        self.peak = 0
        self._active_by_workflow = {}
        self._peak_by_workflow = {}
        self._subscription = kernel.events.subscribe(self._event)

    def prepare(self, graph):
        with self._lock:
            self._active_by_workflow[graph.graph_id] = 0
            self._peak_by_workflow[graph.graph_id] = 0
            for task in graph.tasks:
                key = (graph.graph_id, task.task_id)
                role = self.roles.select(task)
                state = result_state(task.result) if task.status.terminal and task.result else WorkerState.WAITING
                self._records[key] = WorkerRecord(new_id(), task.task_id, role.role_id, state, description=task.description)

    def _event(self, event):
        if event.event_type not in {EventType.TASK_VERIFYING, EventType.TASK_PROGRESS, EventType.TASK_WAITING, EventType.TASK_RESUMED}:
            return
        # Task IDs are globally unique within this coordinator's live workflows.
        changes = []
        with self._lock:
            for (workflow_id, _), record in self._records.items():
                if record.task_id == event.task_id and record.state in {WorkerState.RUNNING, WorkerState.VERIFYING, WorkerState.WAITING}:
                    if event.event_type == EventType.TASK_VERIFYING:
                        record.state = WorkerState.VERIFYING
                    elif event.event_type == EventType.TASK_WAITING:
                        record.state = WorkerState.WAITING
                        record.progress = str(event.payload.get("reason", ""))
                    elif event.event_type == EventType.TASK_RESUMED:
                        record.state = WorkerState.RUNNING
                        record.progress = "Resources available."
                    else:
                        record.progress = str(event.payload.get("message", ""))[:500]
                    if event.event_type != EventType.TASK_PROGRESS:
                        changes.append(KernelEvent(EventType.WORKER_CHANGED, source="agents", task_id=record.task_id,
                            payload={"workflow_id": workflow_id, "role": record.role, "state": record.state.value}))
        # Public state notifications extend this owner. Never emit provider
        # bodies or publish while holding the worker record lock.
        for change in changes:
            self.kernel.events.publish(change)

    def execute(self, graph, task, context):
        key = (graph.graph_id, task.task_id)
        with self._lock:
            record = self._records[key]
            role = self.roles.select(task)
            token = context.cancellation_token.child() if context.cancellation_token else CancellationToken()
            self._tokens[key] = token
            if key in self._cancelled:
                token.cancel("Branch cancelled.")
            record.state = WorkerState.READY
            record.started_at = time.time()
            queue_ms = (time.perf_counter() - record.queued_at) * 1000
            self._active += 1
            self.peak = max(self.peak, self._active)
            self._active_by_workflow[graph.graph_id] = self._active_by_workflow.get(graph.graph_id, 0) + 1
            self._peak_by_workflow[graph.graph_id] = max(self._peak_by_workflow.get(graph.graph_id, 0), self._active_by_workflow[graph.graph_id])
            record.state = WorkerState.RUNNING
        self.kernel.events.publish(KernelEvent(EventType.WORKER_CHANGED, source="agents", task_id=task.task_id,
            payload={"workflow_id": graph.graph_id, "role": record.role, "state": record.state.value}))
        try:
            packet = build_packet(graph, task, role, context, self.state, self.limits.max_context_chars)
            # Metadata is constructed from an allowlist; no conversation or other
            # branches' results enter worker context. Approval stays opaque.
            approvals = context.metadata.get("task_approvals", {})
            ctx = replace(context, active_window="", active_device="", user_preferences={},
                active_files=packet.files, project_id=packet.project, cancellation_token=token,
                approval_token=approvals.get(task.task_id, context.approval_token),
                permissions=tuple(dict.fromkeys((*context.permissions, *role.required_permissions))),
                metadata={"packet": asdict(packet), "workflow_id": graph.graph_id,
                    "role": role.role_id, "model_budget": context.metadata.get("model_budget"),
                    "model_requirements": role.model_requirements,
                    "model_config": context.metadata.get("model_config", {})})
            if context.metadata.get("_resource_reservation") is not None:
                ctx = replace(ctx, metadata={**ctx.metadata, "_resource_reservation": context.metadata["_resource_reservation"]})
            if context.metadata.get("project_session_id"):
                ctx = replace(ctx, metadata={**ctx.metadata, "project_session_id": context.metadata["project_session_id"]})
            # Carry only bounded causality references from the ambient driver;
            # provider bodies, event instructions and permissions are excluded.
            if context.metadata.get("ambient") is True:
                ctx=replace(ctx,metadata={**ctx.metadata,"ambient":True,
                    "ambient_depth":min(8,max(0,int(context.metadata.get("ambient_depth",0)))),
                    "ambient_correlation":str(context.metadata.get("ambient_correlation",""))[:256],
                    "event_receipt":str(context.metadata.get("event_receipt",""))[:1024]})
            task.constraints.setdefault("resource_wait_seconds", self.limits.max_runtime)
            task.timeout = task.timeout or min(self.limits.max_runtime, self.kernel.prepare_provider(task, ctx).descriptor.timeout)
            task.verification_policy = task.verification_policy if task.verification_policy.required else role.default_verification_policy
            result = self.kernel.run_task(task, ctx)
            result.metrics.update(context_estimated_tokens=packet.estimated_tokens, context_truncated=int(packet.truncated), agent_queue_ms=queue_ms)
            return result
        except Exception as exc:
            return ExecutionResult.failure(ErrorCode.INTERNAL_ERROR, "Worker could not execute.", detail=f"{type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._active -= 1
                self._active_by_workflow[graph.graph_id] -= 1
                self._tokens.pop(key, None)

    def collect(self, graph, task, result, *, publish=True):
        key = (graph.graph_id, task.task_id)
        with self._lock:
            record = self._records[key]
            if key in self._cancelled and result.success:
                result.success, result.status = False, TaskStatus.CANCELLED
                from ..kernel import ExecutionError
                result.errors.append(ExecutionError(ErrorCode.CANCELLED, "Branch cancelled before result collection."))
            record.state = result_state(result)
            record.completed_at = time.time()
            output = result.output
            if record.role in {"researcher", "browser"} and isinstance(output, dict) and "content" in output:
                import json
                try:
                    document = json.loads(output["content"])
                except (ValueError, TypeError):
                    document = {}
                output = {**output, "claims": document.get("claims", {}) if isinstance(document, dict) else {},
                    "evidence": [output["content"][:500]], "sources": [{"path": output["path"]}],
                    "uncertainties": ["Content is source data; claims require independent verification."], "open_questions": []}
            elif record.role in {"researcher", "browser"}:
                output = {"claims": {}, "evidence": list(result.evidence), "sources": list(result.artifacts),
                    "uncertainties": [] if result.success else ["Source task did not complete."], "open_questions": [], "data": output}
            if record.role == "tester":
                ran = isinstance(output, dict) and "exitCode" in output
                output = {"test_status": "passed" if ran and output["exitCode"] == 0 and result.success else
                    "failed" if ran else "unavailable" if any(e.code == ErrorCode.CAPABILITY_UNAVAILABLE for e in result.errors) else "not_run",
                    "execution": output}
            if result.success:
                from ..kernel.schema import validate_schema
                try:
                    validate_schema(output, self.roles.resolve(record.role).result_schema)
                except ValueError as exc:
                    from ..kernel import ExecutionError
                    result.success, result.status = False, TaskStatus.FAILED
                    result.errors.append(ExecutionError(ErrorCode.INVALID_INPUT, f"Role result schema failed: {exc}"))
                    record.state = WorkerState.FAILED
            summary = f"{self.roles.resolve(record.role).display_name}: {record.state.value}"
            agent = AgentResult(record.worker_id, record.role, task.task_id, record.state, summary, output,
                tuple(result.artifacts), tuple(result.evidence), tuple(result.warnings),
                tuple({"code": e.code.value, "message": e.message} for e in result.errors), dict(result.metrics),
                result.verification_required, result.verification.status.value if result.verification else VerificationStatus.NOT_APPLICABLE.value,
                result.retryable)
            self.state.put(graph.graph_id, task.task_id, record.worker_id, agent)
        event = KernelEvent(EventType.WORKER_CHANGED, source="agents", task_id=task.task_id,
            payload={"workflow_id": graph.graph_id, "role": record.role, "state": record.state.value})
        if publish:
            self.kernel.events.publish(event)
        return event

    def cancel_branch(self, workflow_id, task_id):
        key = (workflow_id, task_id)
        with self._lock:
            if key not in self._records:
                return False
            self._cancelled.add(key)
            if token := self._tokens.get(key):
                token.cancel("Branch cancelled.")
            return True

    def is_cancelled(self, workflow_id, task_id):
        with self._lock:
            return (workflow_id, task_id) in self._cancelled

    def snapshot(self, workflow_id):
        with self._lock:
            return [asdict(record) for (workflow, _), record in self._records.items() if workflow == workflow_id]

    def forget(self, workflow_id):
        with self._lock:
            self._records = {k: v for k, v in self._records.items() if k[0] != workflow_id}
            self._cancelled = {k for k in self._cancelled if k[0] != workflow_id}
            self._active_by_workflow.pop(workflow_id, None)
            self._peak_by_workflow.pop(workflow_id, None)

    def peak_for(self, workflow_id):
        with self._lock:
            return self._peak_by_workflow.get(workflow_id, 0)

    def shutdown(self):
        with self._lock:
            for token in self._tokens.values():
                token.cancel("Agent runtime shutdown.")
        self.kernel.events.unsubscribe(self._subscription)
