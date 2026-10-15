"""Shared execution boundary: select, authorize, lease, execute, verify."""
from __future__ import annotations

import logging
import copy
import math
import platform
import threading
import time
from collections import deque
from dataclasses import replace
from typing import Any

from .cancellation import CancelledError, CancellationToken
from .context import ContextResolver
from .contracts import (Availability, ErrorCode, ExecutionContext, ExecutionError,
                        ExecutionMode, ExecutionResult, TaskStatus, VerificationResult,
                        VerificationStatus, new_id)
from .events import EventBus, EventType, KernelEvent
from .permissions import PermissionManager
from .registry import CapabilityEntry, CapabilityRegistry
from .resources import ResourceManager
from .tasks import GraphResult, TaskGraph, TaskNode
from .telemetry import TelemetryCollector
from .schema import validate_schema


class CapabilityKernel:
    def __init__(self, *, permissions: PermissionManager | None = None, context: ContextResolver | None = None, telemetry: TelemetryCollector | None = None, max_execution_workers: int = 8):
        self.events = EventBus()
        self.registry = CapabilityRegistry(self.events)
        self.permissions = permissions or PermissionManager()
        self.context = context or ContextResolver()
        self.resources = ResourceManager()
        self.telemetry = telemetry or TelemetryCollector()
        self._active: dict[str, CancellationToken] = {}
        self._graphs: dict[str, CancellationToken] = {}
        self._lock = threading.RLock()
        self._slots = threading.BoundedSemaphore(max_execution_workers)
        self._history: deque[dict[str, Any]] = deque(maxlen=200)
        self._closed = False
        self.scheduler = None
        self.actions = None
        self.mesh = None  # Optional provider routing; local paths need no network.

    def prepare_provider(self, task, context=None):
        if self.mesh is not None:
            self.mesh.prepare_task(task, context)
        return self.registry.lookup(task.capability_requirement, task.constraints.get("node_id", "local"))

    def resource_claims(self, task, entry, context=None):
        """Resolve dynamic claims once per admission, using the existing authority."""
        extra = tuple(entry.resource_resolver(task.inputs, context or ExecutionContext())) if entry.resource_resolver else ()
        from .contracts import ResourceClaim
        if any(not isinstance(c, ResourceClaim) or c.node_id != entry.descriptor.node_id for c in extra):
            raise ValueError("Provider returned invalid or incorrectly scoped resource claims.")
        return (*entry.descriptor.supported_resources, *extra, *task.resource_requirements)

    def dispatch(self, capability_id: str, inputs: dict[str, Any], context: ExecutionContext | None = None, **task_fields) -> ExecutionResult:
        task = TaskNode(capability_id, inputs, **task_fields)
        return self.run_task(task, context or ExecutionContext())

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            token = self._active.get(task_id) or self._graphs.get(task_id)
            if token is None:
                return False
            token.cancel()
        self.events.publish(KernelEvent(EventType.USER_CANCELLED, task_id=task_id))
        return True

    def run_graph(self, graph: TaskGraph, context: ExecutionContext | None = None) -> GraphResult:
        graph.validate()
        if not graph.run_lock.acquire(blocking=False):
            raise ValueError("This graph is already running.")
        context = context or ExecutionContext()
        root = context.cancellation_token or CancellationToken()
        with self._lock:
            if graph.graph_id in self._graphs:
                graph.run_lock.release()
                raise ValueError("Graph id is already active.")
            self._graphs[graph.graph_id] = root
        try:
            while True:
                if root.cancelled:
                    for task in graph.tasks:
                        if not task.status.terminal:
                            graph.finish(task, ExecutionResult.failure(ErrorCode.CANCELLED, "Workflow cancelled."))
                    break
                task = graph.claim_ready()
                if task is None:
                    # Readiness may mark one dependency blocked, which makes a
                    # later child decidable on the next pass.
                    remaining = [t for t in graph.tasks if not t.status.terminal]
                    if remaining and graph.ready():
                        continue
                    for pending in remaining:
                        graph.finish(pending, ExecutionResult.failure(ErrorCode.DEPENDENCY_MISSING, "No executable dependency path remains."))
                    break
                result = self.run_task(task, replace(context, cancellation_token=root))
                graph.finish(task, result)
            return graph.result()
        finally:
            with self._lock:
                self._graphs.pop(graph.graph_id, None)
            graph.run_lock.release()

    def run_task(self, task: TaskNode, context: ExecutionContext) -> ExecutionResult:
        queued = time.perf_counter()
        token = context.cancellation_token.child() if context.cancellation_token else CancellationToken()
        with self._lock:
            if self._closed:
                return ExecutionResult.failure(ErrorCode.CANCELLED, "Capability kernel is shut down.")
            if task.task_id in self._active:
                return ExecutionResult.failure(ErrorCode.INVALID_INPUT, "Task is already executing.")
            self._active[task.task_id] = token
        self.telemetry.record(task.task_id, task.capability_requirement, "", "task_queued")
        self.events.publish(KernelEvent(EventType.TASK_QUEUED, task_id=task.task_id, project_id=context.project_id,
            payload={"capability_requirement": task.capability_requirement}))
        task.started_at = task.started_at or time.time()
        task.status = TaskStatus.RUNNING
        self.telemetry.record(task.task_id, task.capability_requirement, "", "task_started")
        self.events.publish(KernelEvent(EventType.TASK_STARTED, task_id=task.task_id, project_id=context.project_id,
            payload={"capability_requirement": task.capability_requirement}))
        result = ExecutionResult.failure(ErrorCode.INTERNAL_ERROR, "Execution did not produce a result.")
        entry = None
        ctx = context
        execution_id = ""
        try:
            task.inputs = copy.deepcopy(task.inputs)
            self.prepare_provider(task, context)
            if self.actions is not None:
                self.actions.prepare_task(task)
            for field, reference in task.constraints.get("references", {}).items():
                resolution = self.context.resolve(reference["reference"], expected_kinds=tuple(reference.get("expected_kinds", ())), material_action=True)
                if resolution.needs_clarification or resolution.entity is None:
                    raise ValueError(f"Please clarify the target for '{reference['reference']}' before this action can run.")
                task.inputs[field] = resolution.entity.payload.get(reference.get("payload_field", "path"), resolution.entity.label)
            candidates = (task.capability_requirement, *task.retry_policy.alternative_capabilities)
            primary = self.registry.lookup(task.capability_requirement, task.constraints.get("node_id", "local"))
            timeout = task.timeout if task.timeout is not None else primary.descriptor.timeout if primary else 30.0
            if not math.isfinite(timeout) or timeout <= 0:
                raise ValueError("Task timeout must be finite and positive.")
            task_deadline = time.monotonic() + timeout
            if context.deadline is not None:
                task_deadline = min(task_deadline, context.deadline)
            # The primary capability is retried unless explicit alternatives
            # were supplied. Every alternative is authorized independently.
            for attempt in range(task.retry_policy.max_attempts):
                if token.cancelled:
                    result = ExecutionResult.failure(ErrorCode.CANCELLED, "Task cancelled.")
                    break
                capability_id = candidates[min(attempt, len(candidates) - 1)]
                task.attempts += 1
                entry = self.registry.lookup(capability_id, task.constraints.get("node_id", "local"))
                if entry is None:
                    result = ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE, f"Capability is not registered: {capability_id}")
                    break
                if time.monotonic() >= task_deadline:
                    result = ExecutionResult.failure(ErrorCode.TIMEOUT, "Task execution deadline exceeded.")
                    break
                deadline = min(task_deadline, time.monotonic() + entry.descriptor.timeout)
                attempt_token = token.child()
                reservation = context.metadata.get("_resource_reservation")
                execution_id = reservation.owner if attempt == 0 and reservation is not None and reservation.task_id == task.task_id else new_id()
                ctx = context.for_task(task.task_id, capability_id, parent_task_id=task.parent_task_id,
                    cancellation_token=attempt_token, deadline=deadline,
                    permissions=tuple(dict.fromkeys((*context.permissions, *task.permissions))),
                    metadata={**context.metadata, "task_inputs": task.inputs, "expected_outcome": task.verification_policy.expected_outcome, "execution_id": execution_id},
                    progress=lambda message: self._progress(task, capability_id, execution_id, context, message))
                self.telemetry.record(task.task_id, capability_id, execution_id, "capability_selected")
                self.telemetry.record(task.task_id, capability_id, execution_id, "queue_latency", (time.perf_counter() - queued) * 1000)
                result = self._attempt(task, entry, ctx, execution_id)
                result.task_id, result.capability_id, result.execution_id = task.task_id, capability_id, execution_id
                if self.actions is not None:
                    self.actions.attempt_finished(task, result, ctx)
                if result.success or not result.retryable or not entry.descriptor.supports_retry:
                    break
                if not any(e.code in task.retry_policy.retryable_errors for e in result.errors):
                    break
                if attempt + 1 >= task.retry_policy.max_attempts:
                    break
                task.status = TaskStatus.RETRYING
                if token.wait(min(task.retry_policy.backoff * (2 ** attempt), max(0.0, task_deadline - time.monotonic()))):
                    result = ExecutionResult.failure(ErrorCode.CANCELLED, "Task cancelled during retry backoff.")
                    break
                task.status = TaskStatus.RUNNING
        except CancelledError:
            result = ExecutionResult.failure(ErrorCode.CANCELLED, "Capability cancelled.")
        except ValueError as exc:
            result = ExecutionResult.failure(ErrorCode.INVALID_INPUT, str(exc))
        except Exception as exc:
            logging.getLogger(__name__).error("Kernel task boundary failed (%s)", type(exc).__name__)
            result = ExecutionResult.failure(ErrorCode.INTERNAL_ERROR, "The task could not be completed.", detail=type(exc).__name__)
        finally:
            reservation = context.metadata.get("_resource_reservation")
            if reservation is not None and not reservation.started:
                self.resources.release(reservation.owner)
            with self._lock:
                self._active.pop(task.task_id, None)
        result.task_id = task.task_id
        if execution_id and ctx.capability_id:
            result.execution_id, result.capability_id = execution_id, ctx.capability_id
        result.metrics["attempts"] = task.attempts
        if token.cancelled and result.status != TaskStatus.CANCELLED:
            result.success = False
            result.status = TaskStatus.CANCELLED
            result.errors.append(ExecutionError(ErrorCode.CANCELLED, "Task cancelled."))
        task.result, task.status, task.outputs, task.completed_at = result, result.status, result.output, time.time()
        if self.actions is not None:
            self.actions.attempt_finished(task, result, ctx)
            self.actions.complete_task(task, result, ctx)
        if entry is not None and entry.on_completed is not None:
            try:
                entry.on_completed(result, ctx)
            except Exception as exc:
                logging.getLogger(__name__).error("Capability completion sink failed (%s)", type(exc).__name__)
                result.warnings.append(f"Task history could not be saved: {type(exc).__name__}.")
        self.telemetry.record(task.task_id, result.capability_id, result.execution_id, "task_completed", (time.perf_counter() - queued) * 1000)
        with self._lock:
            self._history.append({"task_id": task.task_id, "capability_id": result.capability_id,
                "execution_id": result.execution_id, "status": result.status.value,
                "duration_ms": (time.perf_counter() - queued) * 1000, "attempts": task.attempts})
        self.events.publish(KernelEvent(EventType.TASK_COMPLETED if result.success else EventType.TASK_FAILED,
            task_id=task.task_id, project_id=context.project_id,
            payload={"status": result.status.value, "capability_id": result.capability_id, "execution_id": result.execution_id},
            severity="info" if result.success else "warning"))
        if self.telemetry.logger:
            try:
                self.telemetry.logger("INFO" if result.success else "WARNING", "Capability task finished.", category="kernel",
                    metadata={"taskId": task.task_id, "capabilityId": result.capability_id, "executionId": result.execution_id,
                    "status": result.status.value, "errors": [e.message for e in result.errors], "diagnostics": [e.detail for e in result.errors if e.detail]})
            except Exception:
                logging.getLogger(__name__).exception("Kernel diagnostic sink failed")
        return result

    def _attempt(self, task: TaskNode, entry: CapabilityEntry, context: ExecutionContext, execution_id: str) -> ExecutionResult:
        d = entry.descriptor
        token = context.cancellation_token
        health = self.registry.health(d.capability_id, node_id=d.node_id)
        if health.status not in {Availability.AVAILABLE, Availability.DEGRADED}:
            if task.optional and task.skip_if_unavailable:
                return ExecutionResult(TaskStatus.SKIPPED, False, warnings=[health.reason or "Optional capability unavailable."])
            return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE, health.reason or "Capability unavailable.")
        if "any" not in d.supported_platforms and platform.system().casefold() not in {p.casefold() for p in d.supported_platforms}:
            return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE, "Capability does not support this platform.")
        if task.execution_mode == ExecutionMode.BACKGROUND and not d.supports_background:
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT, "Capability requires foreground execution.")
        for dependency in d.dependencies:
            if self.registry.lookup(dependency) is None or self.registry.health(dependency).status not in {Availability.AVAILABLE, Availability.DEGRADED}:
                return ExecutionResult.failure(ErrorCode.DEPENDENCY_MISSING, f"Capability dependency unavailable: {dependency}")
        try:
            validate_schema(task.inputs, d.input_schema)
        except ValueError as exc:
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT, str(exc))
        authorization = self.permissions.authorize(entry, task.inputs, context)
        if not authorization.allowed:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED, authorization.reason or "Permission required.")
        reservation = context.metadata.get("_resource_reservation")
        if (reservation is not None and reservation.owner == execution_id
                and reservation.task_id == task.task_id and reservation.capability_id == d.capability_id
                and self.resources.owns(execution_id, reservation.claims)):
            claims = reservation.claims
        else:
            claims = self.resource_claims(task, entry, context)
        for resource, limit in context.resource_budget.items():
            if sum(c.amount for c in claims if c.resource == resource) > limit:
                return ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE, f"Resource budget exceeded: {resource}")
        wait_started = time.perf_counter()
        wait_until = min(context.deadline, time.monotonic() + max(0.0, float(task.constraints.get("resource_wait_seconds", 0))))
        reservation = context.metadata.get("_resource_reservation")
        reserved = reservation is not None and reservation.owner == execution_id and reservation.task_id == task.task_id and reservation.claims == tuple(claims) and self.resources.owns(execution_id, tuple(claims))
        while not reserved and not self.resources.acquire(execution_id, tuple(claims)):
            if task.status != TaskStatus.WAITING:
                self.events.publish(KernelEvent(EventType.TASK_WAITING, task_id=task.task_id, project_id=context.project_id,
                    payload={"reason": "Waiting for required resources."}))
            task.status = TaskStatus.WAITING
            if token.cancelled:
                return ExecutionResult.failure(ErrorCode.CANCELLED, "Cancelled while waiting for resources.")
            if time.monotonic() >= wait_until:
                return ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE, "Required resources are busy or unavailable.")
            token.wait(0.01)
        self.telemetry.record(task.task_id, d.capability_id, execution_id, "resource_wait", (time.perf_counter() - wait_started) * 1000)
        if task.status == TaskStatus.WAITING:
            self.events.publish(KernelEvent(EventType.TASK_RESUMED, task_id=task.task_id, project_id=context.project_id))
        task.status = TaskStatus.RUNNING
        if reserved:
            reservation.started = True
        if token.cancelled or time.monotonic() >= context.deadline:
            self.resources.release(execution_id)
            return ExecutionResult.failure(ErrorCode.CANCELLED if token.cancelled else ErrorCode.TIMEOUT, "Execution deadline reached or task cancelled.")
        def body() -> ExecutionResult:
            try:
                with self.resources.execution_scope(execution_id):
                    return self._execute_and_verify(task, entry, context, execution_id)
            finally:
                # Ownership belongs to actual work, including detached work.
                if self.mesh is None or not self.mesh.lease_retained(execution_id):
                    self.resources.release(execution_id)
        if d.inline:
            result = body()
            if token.cancelled:
                return ExecutionResult.failure(ErrorCode.CANCELLED, "Task cancelled.")
            if time.monotonic() >= context.deadline:
                return ExecutionResult.failure(ErrorCode.TIMEOUT, "Capability exceeded its execution deadline.")
            return result
        if not self._slots.acquire(blocking=False):
            self.resources.release(execution_id)
            return ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE, "All execution slots are occupied.")
        done = threading.Event()
        values: list[ExecutionResult] = []
        def worker() -> None:
            try:
                values.append(body())
            except BaseException as exc:
                logging.getLogger(__name__).error("Capability worker failed (%s)", type(exc).__name__)
                values.append(ExecutionResult.failure(ErrorCode.INTERNAL_ERROR, "Capability worker failed.", detail=type(exc).__name__))
            finally:
                self._slots.release()
                done.set()
        threading.Thread(target=worker, daemon=True, name=f"morice-capability-{execution_id[:8]}").start()
        while not done.wait(0.01):
            if token.cancelled or time.monotonic() >= context.deadline:
                timed_out = not token.cancelled
                token.cancel("Task deadline exceeded." if timed_out else "Task cancelled.")
                # Give cooperative/subprocess adapters a bounded cleanup window.
                stopped = done.wait(1.0 if d.supports_cancellation else 0.25)
                result = ExecutionResult.failure(ErrorCode.TIMEOUT if timed_out else ErrorCode.CANCELLED,
                    "Capability timed out." if timed_out else "Task cancelled.")
                if not stopped:
                    result.warnings.append("Work is detached until it stops; its resource claims remain reserved.")
                return result
        if token.cancelled:
            return ExecutionResult.failure(ErrorCode.CANCELLED, "Task cancelled.")
        if time.monotonic() >= context.deadline:
            return ExecutionResult.failure(ErrorCode.TIMEOUT, "Capability completed after its deadline.")
        return values[0]

    def _execute_and_verify(self, task: TaskNode, entry: CapabilityEntry, context: ExecutionContext, execution_id: str, *, bypass_actions=False) -> ExecutionResult:
        if self.actions is not None and not bypass_actions and self.actions.supports(task, entry):
            return self.actions.execute(task, entry, context, execution_id)
        d = entry.descriptor
        started = time.perf_counter()
        self.telemetry.record(task.task_id, d.capability_id, execution_id, "execution_started")
        try:
            context.cancellation_token.raise_if_cancelled()
            result = entry.handler(dict(task.inputs), context)
            if not isinstance(result, ExecutionResult):
                return ExecutionResult.failure(ErrorCode.INTERNAL_ERROR, "Capability returned an invalid result contract.")
            if result.success:
                validate_schema(result.output, d.output_schema, "output")
        except CancelledError:
            return ExecutionResult.failure(ErrorCode.CANCELLED, "Capability cancelled.")
        except Exception as exc:
            logging.getLogger(__name__).error("Capability failed (%s)", type(exc).__name__)
            from ..redaction import redact_text
            return ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, "Capability execution failed.", detail=redact_text(f"{type(exc).__name__}: {exc}")[:1500], retryable=d.supports_retry)
        finally:
            self.telemetry.record(task.task_id, d.capability_id, execution_id, "execution_completed", (time.perf_counter() - started) * 1000)
        if not result.success:
            result.status = TaskStatus.FAILED if result.status not in {TaskStatus.CANCELLED, TaskStatus.SKIPPED} else result.status
            return result
        context.cancellation_token.raise_if_cancelled()
        required = result.verification_required or task.verification_policy.required or d.supports_verification
        verify_started = time.perf_counter()
        if entry.verifier:
            task.status = TaskStatus.VERIFYING
            self.events.publish(KernelEvent(EventType.TASK_VERIFYING, task_id=task.task_id, project_id=context.project_id))
            self.telemetry.record(task.task_id, d.capability_id, execution_id, "verification_started")
            try:
                verification = entry.verifier(result, task.verification_policy.expected_outcome, context)
                if not isinstance(verification, VerificationResult):
                    raise TypeError("Invalid verification contract.")
            except Exception as exc:
                logging.getLogger(__name__).error("Capability verifier failed (%s)", type(exc).__name__)
                verification = VerificationResult(VerificationStatus.INCONCLUSIVE, message=f"Verifier failed: {type(exc).__name__}.")
        else:
            verification = VerificationResult(VerificationStatus.INCONCLUSIVE if required else VerificationStatus.NOT_APPLICABLE)
        self.telemetry.record(task.task_id, d.capability_id, execution_id, "verification_completed", (time.perf_counter() - verify_started) * 1000)
        result.verification = verification
        result.evidence.extend(e for e in verification.evidence if e not in result.evidence)
        # An explicit failed/inconclusive verifier always overrides apparent success.
        if verification.status in {VerificationStatus.FAILED, VerificationStatus.INCONCLUSIVE} or required and verification.status != VerificationStatus.VERIFIED:
            result.success = False
            result.status = TaskStatus.FAILED
            result.errors.append(ExecutionError(ErrorCode.VERIFICATION_FAILED, verification.message or "Outcome could not be verified."))
        else:
            result.status = TaskStatus.SUCCEEDED
        result.metrics.update(execution_ms=(verify_started - started) * 1000, verification_ms=(time.perf_counter() - verify_started) * 1000)
        return result

    def _progress(self, task, capability_id, execution_id, context, message) -> None:
        if task.status.terminal or context.cancellation_token and context.cancellation_token.cancelled:
            return
        self.telemetry.record(task.task_id, capability_id, execution_id, "progress")
        self.events.publish(KernelEvent(EventType.TASK_PROGRESS, task_id=task.task_id, project_id=context.project_id, payload={"message": str(message)[:2000]}))
        if context.progress:
            context.progress(str(message))

    def history(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(dict(v) for v in self._history)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            for token in (*self._active.values(), *self._graphs.values()):
                token.cancel("Kernel shutdown.")
        if self.scheduler:
            self.scheduler.shutdown()
        self.events.clear()
