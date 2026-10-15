"""Graph admission on MORICE's reserved interactive/background worker lanes."""
from __future__ import annotations

import threading
import copy
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import replace
from typing import Protocol

from .cancellation import CancellationToken
from .contracts import ErrorCode, ExecutionContext, ExecutionResult, Priority, TaskStatus, new_id
from .resources import ResourceReservation
from .events import EventType, KernelEvent
from .tasks import TaskGraph


class Planner(Protocol):
    def plan(self, goal: str, context: ExecutionContext) -> TaskGraph: ...


class TaskScheduler:
    def __init__(self, kernel, workers=None):
        self.kernel = kernel
        self.workers = workers
        self._interactive = None
        self._background = None
        self._jobs: dict[str, tuple[Future, CancellationToken, TaskGraph]] = {}
        self._lock = threading.RLock()
        self._closed = False
        self._parallel_pool = None
        self._parallel_capacity = None
        self._parallel_roots = {}
        self._deferred = {}
        self._deferred_thread = None
        self._deferred_wake = threading.Event()
        self._deferred_sequence = 0
        self.max_deferred = 32

    def run_parallel(self, graph: TaskGraph, context: ExecutionContext, *, max_workers: int = 4,
                     executor=None, completed=None, cancelled=None, pool_capacity=None):
        """Bounded DAG driver. Workers execute copies; only this driver commits nodes.

        The shared pool limits concurrency across workflows. Existing reserved UI
        pools remain available, so a graph driver cannot starve its own children.
        """
        if not 1 <= max_workers <= 8:
            raise ValueError("Parallel workers must be within 1..8.")
        graph.validate()
        if not graph.run_lock.acquire(blocking=False):
            raise ValueError("This graph is already running.")
        root = context.cancellation_token or CancellationToken()
        ctx = replace(context, cancellation_token=root)
        with self._lock:
            if self._closed:
                graph.run_lock.release()
                raise ValueError("Scheduler is shut down.")
            if self._parallel_pool is None:
                self._parallel_capacity = pool_capacity or max_workers
                self._parallel_pool = ThreadPoolExecutor(self._parallel_capacity, thread_name_prefix="morice-agent-task")
            pool = self._parallel_pool
            capacity = min(max_workers, self._parallel_capacity)
            self._parallel_roots[graph.graph_id] = root
        pending = {}
        execute = executor or self.kernel.run_task
        waiting_since = {}
        reservations = {}
        def admit(task):
            if cancelled and cancelled(task.task_id):
                return True
            if self.kernel.actions is not None:
                self.kernel.actions.prepare_task(task)
            try:
                entry = self.kernel.prepare_provider(task, ctx)
            except ValueError as error:
                graph.finish(task, ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE, str(error)))
                return False
            if entry is None:
                return True  # Kernel reports missing capabilities.
            from .contracts import Availability
            if self.kernel.registry.health(entry.descriptor.capability_id, node_id=entry.descriptor.node_id).status not in {Availability.AVAILABLE, Availability.DEGRADED}:
                return True  # Unavailable primary may have an authorized alternative.
            claims = self.kernel.resource_claims(task, entry, ctx)
            for claim in claims:
                descriptor = self.kernel.resources.descriptor(claim.resource, claim.node_id)
                if descriptor is None or not descriptor.available or claim.amount > descriptor.capacity:
                    return True  # Kernel reports invalid/unavailable resource requests.
            owner = new_id()
            if self.kernel.resources.acquire(owner, claims):
                reservations[task.task_id] = ResourceReservation(owner, task.task_id, task.capability_requirement, claims)
                if task.task_id in waiting_since:
                    self.kernel.events.publish(KernelEvent(EventType.TASK_RESUMED, task_id=task.task_id))
                    waiting_since.pop(task.task_id)
                return True
            if task.task_id not in waiting_since:
                waiting_since[task.task_id] = time.monotonic()
                self.kernel.events.publish(KernelEvent(EventType.TASK_WAITING, task_id=task.task_id,
                    payload={"reason": "Waiting for scheduler resource admission."}))
            limit = task.timeout or entry.descriptor.timeout
            if time.monotonic() - waiting_since[task.task_id] >= limit:
                graph.finish(task, ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE, "Resource admission timed out."))
            return False
        try:
            while True:
                expired = ctx.deadline is not None and time.monotonic() >= ctx.deadline
                if expired:
                    root.cancel("Workflow deadline exceeded.")
                if root.cancelled:
                    for task in graph.tasks:
                        if task.status in {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.WAITING}:
                            graph.finish(task, ExecutionResult.failure(ErrorCode.TIMEOUT if expired else ErrorCode.CANCELLED, root.reason))
                else:
                    while len(pending) < capacity:
                        task = graph.claim_ready(admit)
                        if task is None:
                            break
                        if cancelled and cancelled(task.task_id):
                            if reservation := reservations.pop(task.task_id, None):
                                self.kernel.resources.release(reservation.owner)
                            graph.finish(task, ExecutionResult.failure(ErrorCode.CANCELLED, "Branch cancelled."))
                            continue
                        # Do not copy a legacy domain object from a checkpoint.
                        clone = copy.copy(task)
                        clone.inputs = copy.deepcopy(task.inputs)
                        clone.constraints = copy.deepcopy(task.constraints)
                        reservation = reservations.get(task.task_id)
                        task_ctx = replace(ctx, metadata={**ctx.metadata, "_resource_reservation": reservation})
                        pending[pool.submit(execute, clone, task_ctx)] = task
                if not pending:
                    remaining = [t for t in graph.tasks if not t.status.terminal]
                    if not remaining:
                        break
                    if graph.ready():
                        root.wait(.01)
                        continue
                    for task in remaining:
                        graph.finish(task, ExecutionResult.failure(ErrorCode.DEPENDENCY_MISSING, "No executable dependency path remains."))
                    break
                done, _ = wait(tuple(pending), timeout=.025, return_when=FIRST_COMPLETED)
                for future in done:
                    task = pending.pop(future)
                    reservation = reservations.pop(task.task_id, None)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = ExecutionResult.failure(ErrorCode.INTERNAL_ERROR, "Worker failed.", detail=f"{type(exc).__name__}: {exc}")
                    if reservation and not reservation.started:
                        self.kernel.resources.release(reservation.owner)
                    if completed:
                        try:
                            completed(task, result)
                        except Exception as exc:
                            result = ExecutionResult.failure(ErrorCode.INTERNAL_ERROR, "Result collection failed.", detail=str(exc))
                    graph.finish(task, result)
            return graph.result()
        finally:
            for reservation in reservations.values():
                if not reservation.started:
                    self.kernel.resources.release(reservation.owner)
            with self._lock:
                self._parallel_roots.pop(graph.graph_id, None)
            graph.run_lock.release()

    def submit(self, graph: TaskGraph, context: ExecutionContext | None = None, *, priority: Priority = Priority.NORMAL) -> Future:
        graph.validate()
        ctx = context or ExecutionContext()
        token = ctx.cancellation_token.child() if ctx.cancellation_token else CancellationToken()
        ctx = replace(ctx, cancellation_token=token)
        with self._lock:
            if self._closed or graph.graph_id in self._jobs:
                raise ValueError("Scheduler closed or graph already submitted.")
            if self.workers:
                future = self.workers.submit("capability-graph", self.kernel.run_graph, graph, ctx,
                    priority="interactive" if priority == Priority.INTERACTIVE else "background")
            else:
                if self._interactive is None:
                    self._interactive = ThreadPoolExecutor(2, thread_name_prefix="morice-kernel-interactive")
                    self._background = ThreadPoolExecutor(2, thread_name_prefix="morice-kernel-background")
                pool = self._interactive if priority == Priority.INTERACTIVE else self._background
                future = pool.submit(self.kernel.run_graph, graph, ctx)
            self._jobs[graph.graph_id] = (future, token, graph)
            future.add_done_callback(lambda _: self._forget(graph.graph_id))
            return future

    def _forget(self, graph_id: str) -> None:
        with self._lock:
            self._jobs.pop(graph_id, None)

    def enqueue_task(self, task, context=None, *, prepare=None, max_workers=4):
        """Bounded single-task admission on the SAME pool used by agent graphs.

        Resource waits stay in this short-lived scheduler driver, never in a
        bounded execution worker. The driver exits when all jobs finish.
        """
        if not 1 <= max_workers <= 8:
            raise ValueError("Invalid shared worker limit.")
        ctx = context or ExecutionContext()
        token = ctx.cancellation_token.child() if ctx.cancellation_token else CancellationToken()
        future = Future()
        with self._lock:
            if self._closed or task.task_id in self._deferred or len(self._deferred) >= self.max_deferred:
                raise ValueError("Scheduler queue is full, duplicate, or closed.")
            if self._parallel_pool is None:
                self._parallel_capacity = max_workers
                self._parallel_pool = ThreadPoolExecutor(max_workers, thread_name_prefix="morice-agent-task")
            self._deferred_sequence += 1
            self._deferred[task.task_id] = {"task":task, "context":replace(ctx,cancellation_token=token),
                "token":token, "future":future, "prepare":prepare, "created":time.monotonic(),
                "sequence":self._deferred_sequence, "running":False, "waiting":False}
            if self._deferred_thread is None or not self._deferred_thread.is_alive():
                self._deferred_thread = threading.Thread(target=self._drive_deferred, name="morice-kernel-admission", daemon=True)
                self._deferred_thread.start()
            self._deferred_wake.set()
        return future

    def _finish_deferred(self, identifier, result):
        with self._lock:
            job = self._deferred.pop(identifier, None)
            self._deferred_wake.set()
        if job is not None:
            task = job["task"]
            task.result, task.status, task.outputs, task.completed_at = result, result.status, result.output, time.time()
            if not job["future"].done():
                job["future"].set_result(result)

    def _drive_deferred(self):
        while True:
            with self._lock:
                if not self._deferred:
                    self._deferred_thread = None
                    return
                jobs = list(self._deferred.values())
                running = sum(j["running"] for j in jobs)
            now = time.monotonic()
            # Aging eventually brings a background request ahead of new previews.
            jobs.sort(key=lambda j:(int(j["task"].priority) - (now-j["created"])/2, j["sequence"]))
            for job in jobs:
                task, ctx, token = job["task"], job["context"], job["token"]
                if job["running"]:
                    continue
                if job["future"].cancelled():
                    token.cancel("Queued task cancelled.")
                if self._closed or token.cancelled:
                    self._finish_deferred(task.task_id, ExecutionResult.failure(ErrorCode.CANCELLED,"Queued task cancelled."))
                    continue
                deadline = min(ctx.deadline or float("inf"), job["created"] + (task.timeout or 300))
                if now >= deadline:
                    self._finish_deferred(task.task_id,ExecutionResult.failure(ErrorCode.TIMEOUT,"Resource admission deadline exceeded."))
                    continue
                if running >= self._parallel_capacity:
                    break
                reservation = None
                try:
                    ready = job["prepare"](task,ctx) if job["prepare"] else True
                    entry = self.kernel.prepare_provider(task,ctx)
                    if entry is None:
                        raise ValueError("Capability is not registered.")
                    claims = self.kernel.resource_claims(task,entry,ctx) if ready else ()
                    if ready:
                        for c in claims:
                            descriptor = self.kernel.resources.descriptor(c.resource,c.node_id)
                            total = sum(v.amount for v in claims if (v.resource,v.node_id)==(c.resource,c.node_id))
                            if descriptor is None or not descriptor.available or total > descriptor.capacity:
                                raise ValueError("Resource request exceeds available capacity: " + c.resource)
                    owner = new_id()
                    if not ready or not self.kernel.resources.acquire(owner,claims):
                        if not job["waiting"]:
                            job["waiting"] = True
                            self.kernel.events.publish(KernelEvent(EventType.TASK_WAITING,task_id=task.task_id,payload={"reason":"Waiting for scheduler resource admission."}))
                        continue
                    reservation = ResourceReservation(owner,task.task_id,task.capability_requirement,claims)
                    # Freeze the deadline, admission claims and copied input used
                    # by permission checking and execution.
                    run_ctx = replace(ctx, deadline=deadline, metadata={**ctx.metadata,"_resource_reservation":reservation})
                    clone = copy.copy(task); clone.inputs = copy.deepcopy(task.inputs)
                    with self._lock:
                        if task.task_id not in self._deferred:
                            self.kernel.resources.release(owner)
                            continue
                        if not job["future"].set_running_or_notify_cancel():
                            self.kernel.resources.release(owner)
                            token.cancel("Queued task cancelled.")
                            self._deferred.pop(task.task_id, None)
                            continue
                        job["running"] = True
                        inner = self._parallel_pool.submit(self.kernel.run_task,clone,run_ctx)
                        job["inner"] = inner
                    running += 1
                    def collect(done, identifier=task.task_id, lease=reservation):
                        try:
                            result = done.result()
                        except Exception as exc:
                            result = ExecutionResult.failure(ErrorCode.INTERNAL_ERROR,"Scheduled task failed.",detail=type(exc).__name__)
                        if not lease.started:
                            self.kernel.resources.release(lease.owner)
                        self._finish_deferred(identifier,result)
                    inner.add_done_callback(collect)
                except Exception as exc:
                    if reservation and not reservation.started:
                        self.kernel.resources.release(reservation.owner)
                    self._finish_deferred(task.task_id,ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE,"Task admission failed.",detail=str(exc)[:1000]))
            self._deferred_wake.wait(.05)
            self._deferred_wake.clear()

    def cancel(self, graph_id: str) -> bool:
        with self._lock:
            if deferred := self._deferred.get(graph_id):
                deferred["token"].cancel("Task cancelled by user.")
                self._deferred_wake.set()
                return True
            job = self._jobs.get(graph_id)
            if not job:
                if root := self._parallel_roots.get(graph_id):
                    root.cancel()
                    return True
                return False
            job[1].cancel()
            if job[0].cancel():
                for task in job[2].tasks:
                    if not task.status.terminal:
                        job[2].finish(task, ExecutionResult.failure(ErrorCode.CANCELLED, "Queued workflow cancelled."))
            return True

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            for deferred in self._deferred.values():
                deferred["token"].cancel("Scheduler shutdown.")
            self._deferred_wake.set()
            for root in self._parallel_roots.values():
                root.cancel("Scheduler shutdown.")
            for future, token, graph in tuple(self._jobs.values()):
                token.cancel("Scheduler shutdown.")
                if future.cancel():
                    for task in graph.tasks:
                        if not task.status.terminal:
                            graph.finish(task, ExecutionResult.failure(ErrorCode.CANCELLED, "Queued workflow cancelled."))
        for pool in (self._interactive, self._background, self._parallel_pool):
            if pool:
                pool.shutdown(wait=False, cancel_futures=True)
