"""Bounded planning, DAG admission, result synthesis and safe checkpoints."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ..kernel import (CancellationToken, CapabilityKernel, ErrorCode, EventType, ExecutionContext, ResourceClaim,
    ExecutionResult, KernelEvent, ResourceDescriptor, TaskGraph, TaskNode, TaskScheduler, TaskStatus)
from .capabilities import claim_conflicts, register_existing_services, register_workflow_capabilities
from .contracts import RuntimeLimits, WorkerState
from .models import ModelBudget, SharedModelAdapter
from .planner import WorkflowPlanner, parallel_decision, semantic_key
from .roles import default_roles
from .state import SharedTaskState
from .workers import WorkerManager
from ..kernel.contracts import new_id


@dataclass(frozen=True)
class WorkflowResult:
    workflow_id: str
    success: bool
    status: str
    summary: str
    output: dict
    results: dict
    warnings: tuple[str, ...]
    metrics: dict


class AgentCoordinator:
    def __init__(self, kernel: CapabilityKernel, *, limits=None, model_router=None, roles=None, planner=None):
        self.kernel = kernel
        self.limits = limits or RuntimeLimits.for_host()
        self.roles = roles or default_roles()
        self.planner = planner or WorkflowPlanner()
        self.state = SharedTaskState()
        self.workers = WorkerManager(kernel, self.roles, self.state, self.limits)
        if kernel.scheduler is None:
            kernel.scheduler = TaskScheduler(kernel)
        for resource, capacity in (("CPU", self.limits.max_cpu_tasks), ("IO", self.limits.max_io_tasks),
            ("LOCAL_MODEL", 1), ("GPU", 1), ("VRAM_MB", self.limits.vram_mb)):
            if kernel.resources.descriptor(resource) is None:
                kernel.resources.register(ResourceDescriptor(resource, capacity))
        if kernel.resources.descriptor("DISK") is None:
            kernel.resources.register(ResourceDescriptor("DISK"))
        register_workflow_capabilities(kernel, self.state)
        register_existing_services(kernel)
        if model_router is None:
            from ..model_router import ModelRouter
            model_router = ModelRouter()
        self.models = SharedModelAdapter(kernel, model_router, self.limits)
        self._graphs = {}
        self._contexts = {}
        self._tokens = {}
        self._results = {}
        self._fingerprints = {}
        self._lock = threading.RLock()
        self._admission = threading.BoundedSemaphore(self.limits.max_workflows)
        self._drivers = None
        self._submitted = set()
        self._closed = False

    def validate(self, graph):
        if not 1 <= len(graph.tasks) <= self.limits.max_subtasks:
            raise ValueError("Workflow task count exceeds its budget.")
        graph.validate()
        seen, depth = set(), {}
        def task_depth(task):
            if task.task_id not in depth:
                depth[task.task_id] = 1 + max((task_depth(graph.get(p)) for p in task.dependencies), default=0)
            return depth[task.task_id]
        for task in graph.tasks:
            if task_depth(task) > self.limits.max_depth:
                raise ValueError("Workflow dependency depth exceeds its budget.")
            role = self.roles.select(task)
            entry = self.kernel.prepare_provider(task)
            if entry is None:
                raise ValueError(f"Capability is not registered: {task.capability_requirement}")
            from ..kernel.schema import validate_schema
            validate_schema(task.inputs, entry.descriptor.input_schema)
            if self.kernel.actions is not None:
                self.kernel.actions.prepare_task(task)
            if task.capability_requirement == "filesystem.apply_patch":
                for change in task.inputs["changes"]:
                    if "expected_exists" not in change or change["expected_exists"] and not change.get("expected_sha256"):
                        raise ValueError("Agent patches require preview existence/hash baselines to detect write conflicts.")
            if entry.permission_check is None:
                from ..unified_intelligence import PermissionState
                for permission in (*entry.descriptor.required_permissions, *task.permissions, *role.required_permissions):
                    if self.kernel.permissions.controller.state(permission) in {PermissionState.DENIED, PermissionState.UNSUPPORTED}:
                        raise ValueError(f"Plan permission is unavailable: {permission}")
            resource = "CPU" if task.capability_requirement in {"terminal.run", "project.verify", "python.calculate"} else "IO" if task.capability_requirement in {"filesystem.read", "filesystem.search", "project.index", "git.status", "git.diff"} else None
            if resource and not any(c.resource == resource for c in (*entry.descriptor.supported_resources, *task.resource_requirements)):
                task.resource_requirements += (ResourceClaim(resource, node_id=entry.descriptor.node_id),)
            if task.retry_policy.max_attempts > self.limits.max_attempts:
                raise ValueError("Task retry budget exceeded.")
            for alternative in task.retry_policy.alternative_capabilities:
                if self.kernel.registry.lookup(alternative) is None or not self.roles.allows(role.role_id, alternative):
                    raise ValueError("Retry alternative is unavailable or forbidden by the role.")
            key = semantic_key(task)
            if key in seen:
                raise ValueError("Duplicate task: use one dependency result or specify a distinct approach.")
            seen.add(key)
            claims = self.kernel.resource_claims(task, entry)
            for claim in claims:
                descriptor = self.kernel.resources.descriptor(claim.resource, claim.node_id)
                amount = sum(c.amount for c in claims if (c.resource, c.node_id) == (claim.resource, claim.node_id))
                if descriptor is None or not descriptor.available or amount > descriptor.capacity:
                    raise ValueError(f"Invalid resource request: {claim.resource} on {claim.node_id}")
            if task.timeout is not None and not 0 < task.timeout <= self.limits.max_runtime:
                raise ValueError("Task timeout exceeds workflow budget.")
            # Permissions are enforced at execution, after exact user approvals;
            # plan validation never manufactures an approval.

    def plan(self, goal, context=None):
        started = time.perf_counter()
        graph = self.planner.route(goal, context or ExecutionContext())
        if graph is not None:
            self.validate(graph)
            self.kernel.telemetry.record(graph.graph_id, "", "", "planning", (time.perf_counter()-started)*1000)
        return graph

    @staticmethod
    def useful(graph):
        return parallel_decision(graph)

    def submit(self, graph, context=None, *, sequential=False):
        self.validate(graph)
        with self._lock:
            if self._closed or graph.graph_id in self._submitted or graph.graph_id in self._tokens:
                raise ValueError("Workflow is already submitted or runtime is shut down.")
            if len(self._tokens) >= self.limits.max_workflows:
                raise ValueError("Concurrent workflow admission limit reached.")
            self._submitted.add(graph.graph_id)
            if self._drivers is None:
                self._drivers = ThreadPoolExecutor(self.limits.max_workflows, thread_name_prefix="morice-agent-coordinator")
            ctx = context or ExecutionContext()
            token = ctx.cancellation_token.child() if ctx.cancellation_token else CancellationToken()
            self._tokens[graph.graph_id] = token  # cancellation works before driver starts
            future = self._drivers.submit(self._submitted_run, graph, replace(ctx, cancellation_token=token), sequential)
            future.add_done_callback(lambda done: self._queued_done(graph, done))
            return future

    def _queued_done(self, graph, future):
        if not future.cancelled():
            return
        with self._lock:
            self._submitted.discard(graph.graph_id)
            token = self._tokens.pop(graph.graph_id, None)
            if token:
                token.cancel("Queued workflow cancelled.")
            for task in graph.tasks:
                if not task.status.terminal:
                    graph.finish(task, ExecutionResult.failure(ErrorCode.CANCELLED, "Queued workflow cancelled."))
            self._graphs[graph.graph_id] = graph
            self._results[graph.graph_id] = WorkflowResult(graph.graph_id, False, "cancelled", "Queued workflow cancelled.", {}, {}, (), {})

    def _submitted_run(self, graph, context, sequential):
        with self._lock:
            self._submitted.discard(graph.graph_id)
        try:
            return self.run(graph, context, sequential=sequential, _submitted=True)
        finally:
            with self._lock:
                self._tokens.pop(graph.graph_id, None)

    def run(self, graph, context=None, *, sequential=False, _submitted=False):
        self.validate(graph)
        ctx = context or ExecutionContext()
        if not self._admission.acquire(blocking=False):
            raise ValueError("Concurrent workflow admission limit reached.")
        with self._lock:
            if self._closed or not _submitted and (graph.graph_id in self._tokens or graph.graph_id in self._submitted):
                self._admission.release()
                raise ValueError("Workflow already active or runtime closed.")
            active_ids = {t.task_id for gid, g in self._graphs.items() if gid in self._tokens for t in g.tasks}
            if active_ids.intersection(t.task_id for t in graph.tasks):
                self._admission.release()
                raise ValueError("Task IDs must be unique across active workflows.")
            token = ctx.cancellation_token or CancellationToken()
            previous = self._fingerprints.get(graph.graph_id)
            if previous:
                current = self._signature(graph)
                changed = {key for key, signature in current.items() if previous.get(key) != signature}
                self._invalidate(graph, changed)
            model_budget = ctx.metadata.get("model_budget")
            if model_budget is None:
                model_budget = ModelBudget(self.limits.max_model_calls, self.limits.max_model_tokens)
            if not isinstance(model_budget, ModelBudget) or model_budget.max_calls > self.limits.max_model_calls or model_budget.max_tokens > self.limits.max_model_tokens:
                self._admission.release()
                raise ValueError("Shared model budget exceeds coordinator limits.")
            ctx = replace(ctx, cancellation_token=token,
                deadline=min(ctx.deadline or float("inf"), time.monotonic()+self.limits.max_runtime),
                metadata={**ctx.metadata, "model_budget": model_budget})
            self._tokens[graph.graph_id], self._graphs[graph.graph_id], self._contexts[graph.graph_id] = token, graph, ctx
            self._fingerprints[graph.graph_id] = self._signature(graph)
            self.workers.prepare(graph)
        started = time.perf_counter()
        self.kernel.events.publish(KernelEvent(EventType.WORKFLOW_CHANGED, source="agents", payload={"workflow_id": graph.graph_id, "state": "running"}))
        terminal_status = "failed"
        try:
            result = self.kernel.scheduler.run_parallel(graph, ctx, max_workers=1 if sequential else self.limits.max_workers,
                pool_capacity=self.limits.max_workers,
                executor=lambda task, context: self.workers.execute(graph, task, context),
                completed=lambda task, value: self._collect(graph, task, value),
                cancelled=lambda task_id: self.workers.is_cancelled(graph.graph_id, task_id))
            collected = self.state.outputs(graph.graph_id, [t.task_id for t in graph.tasks])
            for task in graph.tasks:
                if task.result and (task.task_id not in collected or task.status == TaskStatus.BLOCKED and collected[task.task_id].get("status") != "blocked"):
                    self._collect(graph, task, task.result)
            records = self.state.outputs(graph.graph_id, [t.task_id for t in graph.tasks])
            conflicts = claim_conflicts(records)
            finals = [t.result.output for t in graph.tasks if t.capability_requirement == "agent.synthesize" and t.result and isinstance(t.result.output, dict)]
            output = finals[-1] if finals else {"results": records, "conflicts": conflicts}
            success = result.success and not conflicts
            if self._signature(graph) != self._fingerprints[graph.graph_id]:
                success = False
                output = {**output, "verified": False, "summary": "Plan changed during execution; outputs require review."}
            status = "timed_out" if ctx.deadline <= time.monotonic() else "cancelled" if token.cancelled else "succeeded" if success else "failed"
            warnings = list(result.warnings)
            if conflicts:
                warnings.append("Conflicting claims remain unresolved; no result selected silently.")
            metrics = {"wall_ms": (time.perf_counter()-started)*1000, "workers_created": len(self.workers.snapshot(graph.graph_id)),
                "active_peak": self.workers.peak_for(graph.graph_id), "failures": sum(t.status == TaskStatus.FAILED for t in graph.tasks),
                "retries": sum(max(0, (t.result.metrics.get("attempts", 1) if t.result else 1)-1) for t in graph.tasks),
                "model_budget": ctx.metadata["model_budget"].snapshot()}
            task_ids = {t.task_id for t in graph.tasks}
            telemetry = [r for r in self.kernel.telemetry.records() if r.task_id in task_ids]
            metrics.update(planning_ms=sum(r.duration_ms for r in self.kernel.telemetry.records() if r.task_id == graph.graph_id and r.stage == "planning"),
                resource_wait_ms=sum(r.duration_ms for r in telemetry if r.stage == "resource_wait"),
                verification_ms=sum(r.duration_ms for r in telemetry if r.stage == "verification_completed"),
                cumulative_execution_ms=sum(t.result.metrics.get("execution_ms", 0) for t in graph.tasks if t.result),
                agent_queue_ms=sum(t.result.metrics.get("agent_queue_ms", 0) for t in graph.tasks if t.result))
            value = WorkflowResult(graph.graph_id, success and status == "succeeded", status,
                output.get("summary", f"{sum(t.status == TaskStatus.SUCCEEDED for t in graph.tasks)}/{len(graph.tasks)} tasks succeeded."),
                output, records, tuple(warnings), metrics)
            terminal_status = value.status
            with self._lock:
                self._results[graph.graph_id] = value
            return value
        finally:
            with self._lock:
                self._tokens.pop(graph.graph_id, None)
                self._contexts.pop(graph.graph_id, None)
                # Bounded history, retaining active workflows.
                while len(self._graphs) > 20:
                    old = next((gid for gid in self._graphs if gid not in self._tokens), None)
                    if old is None:
                        break
                    self._graphs.pop(old, None)
                    self._results.pop(old, None)
                    self._fingerprints.pop(old, None)
                    self.state.forget(old)
                    self.workers.forget(old)
            self._admission.release()
            self.kernel.events.publish(KernelEvent(EventType.WORKFLOW_CHANGED, source="agents",
                payload={"workflow_id": graph.graph_id, "state": "completed", "status": terminal_status}))

    def cancel(self, workflow_id, task_id=None):
        if task_id:
            return self.workers.cancel_branch(workflow_id, task_id)
        with self._lock:
            if token := self._tokens.get(workflow_id):
                token.cancel("Workflow cancelled by user.")
                return True
            return False

    def cancel_all(self):
        with self._lock:
            ids = tuple(self._tokens)
        return sum(self.cancel(identifier) for identifier in ids)

    def _collect(self, graph, task, value):
        with self._lock:
            event = self.workers.collect(graph, task, value, publish=False)
            task.attempts = int(value.metrics.get("attempts", 0))
            graph.finish(task, value)
        self.kernel.events.publish(event)

    def status(self, workflow_id=None):
        with self._lock:
            ids = [workflow_id] if workflow_id else list(self._tokens)
            result = []
            for identifier in ids:
                graph = self._graphs.get(identifier)
                if graph is None:
                    continue
                tasks = graph.tasks
                workers = self.workers.snapshot(identifier)
                running_ids = {r["task_id"] for r in workers if r["state"] in {WorkerState.RUNNING, WorkerState.VERIFYING}}
                result.append({"workflow_id": identifier, "goal": graph.goal[:1000],
                    "state": "running" if identifier in self._tokens else self._results[identifier].status if identifier in self._results else "interrupted",
                    "total": len(tasks), "completed": sum(t.status.terminal for t in tasks),
                    "active": [t.description or t.task_id for t in tasks if t.task_id in running_ids],
                    "waiting": [t.description or t.task_id for t in tasks if not t.status.terminal and t.task_id not in running_ids],
                    "failures": [t.description or t.task_id for t in tasks if t.status in {TaskStatus.FAILED, TaskStatus.BLOCKED}],
                    "workers": workers})
            return result

    def status_text(self):
        snapshots = self.status()
        if not snapshots:
            return "No agent workflow is running."
        return "\n".join(f"{s['completed']}/{s['total']} tasks complete. Running: {', '.join(s['active']) or 'none'}. Waiting: {len(s['waiting'])}. Failures: {len(s['failures'])}." for s in snapshots)

    @staticmethod
    def _signature(graph):
        execution_fields = {"status", "outputs", "result", "attempts", "started_at", "completed_at", "created_at"}
        return {t.task_id: hashlib.sha256(json.dumps({"goal": graph.goal,
            "task": {key: value for key, value in t.to_dict().items() if key not in execution_fields}}, sort_keys=True).encode()).hexdigest() for t in graph.tasks}

    def checkpoint(self, workflow_id, path):
        with self._lock:
            graph = self._graphs[workflow_id]
            # Snapshot and result collection share this lock through _collect.
            data = {"version": 1, "graph": graph.to_dict(), "records": self.state.snapshot(workflow_id),
                "fingerprints": self._fingerprints.get(workflow_id, self._signature(graph)),
                "capability_versions": {t.task_id: self.kernel.prepare_provider(t).descriptor.version for t in graph.tasks}}
            encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(encoded) > 64 * 1024 * 1024:
                raise ValueError("Workflow checkpoint exceeds the recovery budget.")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + "." + new_id() + ".tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def restore(self, path, context=None):
        path = Path(path)
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Workflow checkpoint exceeds the recovery budget.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Unsupported workflow checkpoint.")
        if any(not isinstance(data.get(key), dict) for key in ("graph", "fingerprints", "capability_versions")) or not isinstance(data.get("records"), list) or len(data["records"]) > self.limits.max_subtasks:
            raise ValueError("Invalid workflow checkpoint schema.")
        graph = TaskGraph.from_json(json.dumps(data["graph"]))
        with self._lock:
            if graph.graph_id in self._tokens:
                raise ValueError("Cannot restore an active workflow.")
        self.validate(graph)
        signatures = self._signature(graph)
        changed = {task.task_id for task in graph.tasks if signatures[task.task_id] != data["fingerprints"].get(task.task_id)
            or self.kernel.prepare_provider(task).descriptor.version != data["capability_versions"].get(task.task_id)}
        for task in graph.tasks:
            # Recheck completed source reads; arbitrary mutations/processes are
            # never replayed. A changed preview invalidates downstream results.
            if task.status == TaskStatus.SUCCEEDED and task.capability_requirement == "filesystem.read":
                probe = TaskNode("filesystem.read", task.inputs, constraints={"node_id": task.constraints.get("node_id", "local")})
                value = self.kernel.run_task(probe, context or ExecutionContext())
                if not value.success or value.output != task.outputs:
                    changed.add(task.task_id)
            if task.status == TaskStatus.SUCCEEDED and task.capability_requirement == "filesystem.apply_patch":
                for change in task.inputs.get("changes", []):
                    path = str(Path(task.inputs["root"]) / change["path"])
                    probe = TaskNode("filesystem.read", {"path": path}, constraints={"node_id": task.constraints.get("node_id", "local")})
                    value = self.kernel.run_task(probe, context or ExecutionContext())
                    if not value.success or value.output["content"] != change["content"]:
                        changed.add(task.task_id)
        changed = self._invalidate(graph, changed)
        interrupted = {t["task_id"] for t in data["graph"]["tasks"] if t["status"] in {"running", "waiting", "verifying", "retrying"}}
        if self.kernel.actions is not None:
            for task in graph.tasks:
                if task.task_id in interrupted and task.task_id not in changed:
                    entry = self.kernel.prepare_provider(task)
                    if self.kernel.actions.supports(task, entry):
                        observation = self.kernel.actions.reconcile(task, context or ExecutionContext())
                        graph.finish(task, observation)
                        changed.add(task.task_id)  # Old worker output is no longer evidence.
        with self._lock:
            if graph.graph_id in self._tokens:
                raise ValueError("Cannot restore an active workflow.")
            self._graphs[graph.graph_id] = graph
            self._fingerprints[graph.graph_id] = self._signature(graph)
            self.state.forget(graph.graph_id)
            self.state.restore(graph.graph_id, [r for r in data["records"] if r["task_id"] not in changed])
        return graph

    @staticmethod
    def _invalidate(graph, changed):
        changed = set(changed)
        while True:
            descendants = {t.task_id for t in graph.tasks if set(t.dependencies).intersection(changed)}
            if descendants <= changed:
                break
            changed |= descendants
        for task in graph.tasks:
            if task.task_id in changed:
                task.status = TaskStatus.BLOCKED
                task.result = ExecutionResult.failure(ErrorCode.INVALID_INPUT, "Stale task input; replan before resuming.")
                task.result.status = TaskStatus.BLOCKED
                task.outputs = None
        return changed

    def shutdown(self):
        with self._lock:
            self._closed = True
        self.cancel_all()
        self.workers.shutdown()
        if self._drivers:
            self._drivers.shutdown(wait=False, cancel_futures=True)
