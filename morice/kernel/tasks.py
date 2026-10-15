"""Serializable dependency graphs with atomic worker claims."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .contracts import (ErrorCode, ExecutionMode, ExecutionResult, Priority, ResourceClaim,
                        RetryPolicy, TaskStatus, VerificationPolicy, json_value, new_id)


class DependencyPolicy(str, Enum):
    SUCCESS = "success"
    COMPLETED = "completed"
    FAILURE = "failure"


@dataclass
class TaskNode:
    capability_requirement: str
    inputs: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=new_id)
    parent_task_id: str = ""
    goal: str = ""
    description: str = ""
    dependencies: tuple[str, ...] = ()
    dependency_policy: DependencyPolicy = DependencyPolicy.SUCCESS
    priority: Priority = Priority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    execution_mode: ExecutionMode = ExecutionMode.FOREGROUND
    outputs: Any = None
    constraints: dict[str, Any] = field(default_factory=dict)
    permissions: tuple[str, ...] = ()
    resource_requirements: tuple[ResourceClaim, ...] = ()
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    timeout: float | None = None
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    verification_policy: VerificationPolicy = field(default_factory=VerificationPolicy)
    optional: bool = False
    skip_if_unavailable: bool = False
    result: ExecutionResult | None = None
    attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {name: (self.result.to_dict() if self.result else None) if name == "result" else json_value(getattr(self, name)) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TaskNode:
        value = dict(value)
        value["status"] = TaskStatus(value["status"])
        value["priority"] = Priority(value["priority"])
        value["dependency_policy"] = DependencyPolicy(value["dependency_policy"])
        value["execution_mode"] = ExecutionMode(value["execution_mode"])
        for name in ("dependencies", "permissions"):
            value[name] = tuple(value.get(name, ()))
        value["resource_requirements"] = tuple(ResourceClaim(**c) for c in value.get("resource_requirements", ()))
        retry = dict(value.get("retry_policy", {}))
        retry["retryable_errors"] = tuple(ErrorCode(c) for c in retry.get("retryable_errors", (ErrorCode.EXECUTION_FAILED,)))
        retry["alternative_capabilities"] = tuple(retry.get("alternative_capabilities", ()))
        value["retry_policy"] = RetryPolicy(**retry)
        value["verification_policy"] = VerificationPolicy(**value.get("verification_policy", {}))
        if value.get("result"):
            value["result"] = ExecutionResult.from_dict(value["result"])
        # Never silently replay a possibly completed mutation after a crash.
        if value["status"] in {TaskStatus.RUNNING, TaskStatus.VERIFYING, TaskStatus.RETRYING, TaskStatus.WAITING}:
            value["status"] = TaskStatus.BLOCKED
            value["result"] = ExecutionResult.failure(ErrorCode.INTERNAL_ERROR, "Interrupted task requires review before resuming.")
        return cls(**value)


@dataclass(frozen=True)
class GraphResult:
    graph_id: str
    success: bool
    tasks: tuple[TaskNode, ...]
    warnings: tuple[str, ...] = ()


class TaskGraph:
    def __init__(self, tasks: tuple[TaskNode, ...] = (), *, graph_id: str | None = None, goal: str = ""):
        self.graph_id = graph_id or new_id()
        self.goal = goal
        self._tasks: dict[str, TaskNode] = {}
        self._lock = threading.RLock()
        self.run_lock = threading.Lock()
        for task in tasks:
            self.add(task)

    @property
    def tasks(self) -> tuple[TaskNode, ...]:
        with self._lock:
            return tuple(self._tasks.values())

    def add(self, task: TaskNode) -> None:
        with self._lock:
            if self.run_lock.locked():
                raise ValueError("Cannot add tasks while a graph is executing.")
            if task.task_id in self._tasks:
                raise ValueError(f"Duplicate task id: {task.task_id}")
            self._tasks[task.task_id] = task

    def get(self, task_id: str) -> TaskNode:
        with self._lock:
            return self._tasks[task_id]

    def validate(self) -> None:
        with self._lock:
            visited: set[str] = set()
            visiting: set[str] = set()
            def visit(task_id: str) -> None:
                if task_id in visiting:
                    raise ValueError("Task graph contains a cycle.")
                if task_id in visited:
                    return
                if task_id not in self._tasks:
                    raise ValueError(f"Unknown task dependency: {task_id}")
                visiting.add(task_id)
                for dependency in self._tasks[task_id].dependencies:
                    visit(dependency)
                visiting.remove(task_id)
                visited.add(task_id)
            for task_id in self._tasks:
                visit(task_id)

    def ready(self) -> tuple[TaskNode, ...]:
        with self._lock:
            ready = []
            for task in self._tasks.values():
                if task.status not in {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.WAITING}:
                    continue
                parents = [self._tasks[p] for p in task.dependencies]
                if any(not p.status.terminal for p in parents):
                    continue
                satisfied = (
                    task.dependency_policy == DependencyPolicy.COMPLETED
                    or task.dependency_policy == DependencyPolicy.SUCCESS and all(p.status == TaskStatus.SUCCEEDED for p in parents)
                    or task.dependency_policy == DependencyPolicy.FAILURE and any(p.status in {TaskStatus.FAILED, TaskStatus.BLOCKED} for p in parents)
                )
                if not satisfied:
                    task.status = TaskStatus.SKIPPED if task.dependency_policy == DependencyPolicy.FAILURE else TaskStatus.BLOCKED
                    task.completed_at = time.time()
                    task.result = ExecutionResult(task.status, False, warnings=["Dependency condition was not satisfied."], task_id=task.task_id)
                    continue
                task.status = TaskStatus.READY
                ready.append(task)
            return tuple(sorted(ready, key=lambda t: (t.priority, t.created_at, t.task_id)))

    def claim_ready(self, predicate=None) -> TaskNode | None:
        with self._lock:
            ready = self.ready()
            if not ready:
                return None
            task = next((item for item in ready if predicate is None or predicate(item)), None)
            if task is None:
                return None
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            return task

    def finish(self, task: TaskNode, result: ExecutionResult) -> None:
        with self._lock:
            task.result = result
            task.status = result.status
            task.outputs = result.output
            task.completed_at = time.time()

    def result(self) -> GraphResult:
        tasks = self.tasks
        success = all(t.status in {TaskStatus.SUCCEEDED, TaskStatus.SKIPPED} or t.optional and t.status.terminal and t.status != TaskStatus.CANCELLED for t in tasks)
        warnings = tuple(f"Optional task {t.task_id}: {t.status.value}" for t in tasks if t.optional and t.status != TaskStatus.SUCCEEDED)
        return GraphResult(self.graph_id, success, tasks, warnings)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {"version": 1, "graph_id": self.graph_id, "goal": self.goal, "tasks": [t.to_dict() for t in self._tasks.values()]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False)

    @classmethod
    def from_json(cls, value: str) -> TaskGraph:
        data = json.loads(value)
        if data.get("version") != 1:
            raise ValueError("Unsupported task graph version.")
        graph = cls(tuple(TaskNode.from_dict(t) for t in data["tasks"]), graph_id=data["graph_id"], goal=data["goal"])
        graph.validate()
        return graph
