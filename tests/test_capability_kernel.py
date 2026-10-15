"""Phase 1 contracts, lifecycle, real adapters and failure containment."""
from __future__ import annotations

import gc
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from morice.kernel import (
    Availability, CancellationToken, CapabilityDescriptor, CapabilityHealth,
    CapabilityKernel, ContextResolver, DependencyPolicy, ErrorCode, EventBus,
    EventType, ExecutionContext, ExecutionMode, ExecutionResult, KernelEvent,
    Priority, ResourceClaim, ResourceDescriptor, RetryPolicy, TaskGraph, TaskNode,
    TaskScheduler, TaskStatus, VerificationPolicy, VerificationResult, VerificationStatus,
)
from morice.kernel.adapters import register_echo, register_native_adapters, register_pc_adapters, register_tool_adapters
from morice.unified_intelligence import ContextEntity, PermissionState, RiskClass


def ok(inputs, context):
    return ExecutionResult(TaskStatus.SUCCEEDED, True, inputs.get("value", 1))


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.kernel = CapabilityKernel()
        register_echo(self.kernel)

    def tearDown(self):
        self.kernel.shutdown()

    def register(self, name="test.work", handler=ok, **kwargs):
        verifier = kwargs.pop("verifier", None)
        health = kwargs.pop("health_check", None)
        descriptor = CapabilityDescriptor(name, name, **kwargs)
        self.kernel.registry.register(descriptor, handler, verifier=verifier, health_check=health)
        return descriptor

    def test_register_discover_unregister_duplicate_and_lazy_health(self):
        check = Mock(return_value=CapabilityHealth(Availability.DEGRADED, "optional acceleration missing"))
        self.register(category="calculation", provider="test", required_permissions=("read_file",), health_check=check)
        self.assertEqual(check.call_count, 0)
        self.assertEqual(self.kernel.registry.search("calculation", permissions=("read_file",))[0].capability_id, "test.work")
        self.assertFalse(self.kernel.registry.search("calculation", permissions=()))
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(self.kernel.registry.health("test.work").status, Availability.DEGRADED)
        self.kernel.registry.health("test.work")
        self.assertEqual(check.call_count, 1)
        self.kernel.registry.health("test.work", refresh=True)
        self.assertEqual(check.call_count, 2)
        self.assertEqual(len(self.kernel.registry.search(provider="test", healthy=True)), 1)
        self.kernel.registry.unregister("test.work")
        self.assertIsNone(self.kernel.registry.lookup("test.work"))

    def test_broken_health_is_isolated_and_disabled_cannot_refresh_to_available(self):
        self.register(health_check=Mock(side_effect=ImportError("optional unavailable")))
        result = self.kernel.dispatch("test.work", {})
        self.assertEqual(result.errors[0].code, ErrorCode.CAPABILITY_UNAVAILABLE)
        self.assertTrue(self.kernel.dispatch("kernel.echo", {}).success)
        self.kernel.registry.set_status("test.work", Availability.DISABLED)
        self.assertEqual(self.kernel.registry.health("test.work", refresh=True).status, Availability.DISABLED)

    def test_diamond_graph_readiness_and_execution(self):
        tasks = [TaskNode("kernel.echo", task_id="A"), TaskNode("kernel.echo", task_id="B", dependencies=("A",)),
            TaskNode("kernel.echo", task_id="C", dependencies=("A",)), TaskNode("kernel.echo", task_id="D", dependencies=("B", "C"))]
        graph = TaskGraph(tuple(tasks))
        self.assertEqual([t.task_id for t in graph.ready()], ["A"])
        tasks[0].status = TaskStatus.SUCCEEDED
        self.assertEqual({t.task_id for t in graph.ready()}, {"B", "C"})
        tasks[0].status = TaskStatus.PENDING
        result = self.kernel.run_graph(graph)
        self.assertTrue(result.success)
        self.assertTrue(all(t.status == TaskStatus.SUCCEEDED for t in tasks))

    def test_failed_dependency_never_executes_but_recovery_and_completed_can(self):
        calls = []
        self.register("test.fail", lambda i, c: ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, "forced"))
        self.register("test.record", lambda i, c: (calls.append(c.task_id), ok(i, c))[1])
        graph = TaskGraph((TaskNode("test.fail", task_id="A"),
            TaskNode("test.record", task_id="B", dependencies=("A",)),
            TaskNode("test.record", task_id="C", dependencies=("A",), dependency_policy=DependencyPolicy.COMPLETED),
            TaskNode("test.record", task_id="D", dependencies=("A",), dependency_policy=DependencyPolicy.FAILURE)))
        result = self.kernel.run_graph(graph)
        self.assertFalse(result.success)
        self.assertEqual(graph.get("B").status, TaskStatus.BLOCKED)
        self.assertEqual(set(calls), {"C", "D"})

    def test_optional_failure_keeps_primary_success_with_warning(self):
        self.register("test.fail", lambda i, c: ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, "optional failure"))
        graph = TaskGraph((TaskNode("kernel.echo", task_id="A"), TaskNode("test.fail", task_id="B", optional=True, dependencies=("A",))))
        result = self.kernel.run_graph(graph)
        self.assertTrue(result.success)
        self.assertTrue(result.warnings)

    def test_optional_unavailable_skipped_and_unneeded_recovery_skipped(self):
        self.register(status=Availability.UNAVAILABLE)
        graph = TaskGraph((TaskNode("test.work", optional=True, skip_if_unavailable=True),
            TaskNode("kernel.echo", task_id="A"), TaskNode("kernel.echo", dependencies=("A",), dependency_policy=DependencyPolicy.FAILURE)))
        self.assertTrue(self.kernel.run_graph(graph).success)
        self.assertEqual(graph.tasks[0].status, TaskStatus.SKIPPED)
        self.assertEqual(graph.tasks[-1].status, TaskStatus.SKIPPED)

    def test_graph_rejects_cycle_missing_dependency_duplicate(self):
        for graph in (TaskGraph((TaskNode("kernel.echo", task_id="A", dependencies=("B",)),)),
            TaskGraph((TaskNode("kernel.echo", task_id="A", dependencies=("B",)), TaskNode("kernel.echo", task_id="B", dependencies=("A",))))):
            with self.assertRaises(ValueError):
                graph.validate()
        graph = TaskGraph((TaskNode("kernel.echo", task_id="A"),))
        with self.assertRaises(ValueError):
            graph.add(TaskNode("kernel.echo", task_id="A"))

    def test_verifier_overrides_success_and_missing_verifier_is_inconclusive(self):
        self.register(supports_verification=True, verifier=lambda r, e, c: VerificationResult(VerificationStatus.FAILED, ("forced mismatch",)))
        result = self.kernel.dispatch("test.work", {})
        self.assertFalse(result.success)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.errors[-1].code, ErrorCode.VERIFICATION_FAILED)
        required = self.kernel.dispatch("kernel.echo", {}, verification_policy=VerificationPolicy(required=True))
        self.assertFalse(required.success)
        self.assertEqual(required.verification.status, VerificationStatus.INCONCLUSIVE)

    def test_verifier_exception_is_inconclusive_and_contract_must_be_structured(self):
        self.register(verifier=Mock(side_effect=ValueError("bad verifier")))
        self.assertFalse(self.kernel.dispatch("test.work", {}).success)
        self.register("test.raw", lambda i, c: {"success": True})
        self.assertEqual(self.kernel.dispatch("test.raw", {}).errors[0].code, ErrorCode.INTERNAL_ERROR)

    def test_permission_denial_prevents_invocation_and_exact_grant_is_one_use(self):
        handler = Mock(side_effect=ok)
        self.register(handler=handler, required_permissions=("write_file",), risk_level=RiskClass.CRITICAL)
        controller = self.kernel.permissions.controller
        controller.set_state("write_file", PermissionState.DENIED)
        self.assertEqual(self.kernel.dispatch("test.work", {}).errors[0].code, ErrorCode.PERMISSION_DENIED)
        self.assertEqual(handler.call_count, 0)
        controller.set_state("write_file", PermissionState.GRANTED)
        token = controller.issue_one_use("known", "test.work", {})
        context = ExecutionContext(approval_token=token)
        self.assertTrue(self.kernel.dispatch("test.work", {}, context, task_id="known").success)
        self.assertFalse(self.kernel.dispatch("test.work", {}, context, task_id="known").success)
        self.assertEqual(handler.call_count, 1)

    def test_background_dummy_cancellation_propagates_stops_and_releases(self):
        started, stopped = threading.Event(), threading.Event()
        def slow(inputs, context):
            child = context.cancellation_token.child()
            started.set()
            try:
                while not child.wait(.01):
                    pass
                child.raise_if_cancelled()
            finally:
                stopped.set()
        self.register(handler=slow, supports_cancellation=True, supported_resources=(ResourceClaim("FOREGROUND_UI", exclusive=True),))
        scheduler = TaskScheduler(self.kernel)
        self.kernel.scheduler = scheduler
        graph = TaskGraph((TaskNode("test.work", task_id="slow", execution_mode=ExecutionMode.BACKGROUND), TaskNode("kernel.echo", dependencies=("slow",))))
        future = scheduler.submit(graph)
        self.assertTrue(started.wait(2))
        self.assertTrue(scheduler.cancel(graph.graph_id))
        result = future.result(3)
        self.assertFalse(result.success)
        self.assertTrue(stopped.is_set())
        self.assertTrue(all(t.status == TaskStatus.CANCELLED for t in graph.tasks))
        self.assertFalse(self.kernel.resources.snapshot())

    def test_cooperative_timeout_returns_timeout_and_scheduler_continues(self):
        def slow(i, c):
            c.cancellation_token.wait(5)
            c.cancellation_token.raise_if_cancelled()
            return ok(i, c)
        self.register(handler=slow, supports_cancellation=True, timeout=.05)
        result = self.kernel.dispatch("test.work", {})
        self.assertEqual(result.errors[0].code, ErrorCode.TIMEOUT)
        self.assertTrue(self.kernel.dispatch("kernel.echo", {}).success)

    def test_detached_work_keeps_lease_and_cannot_write_late_task_success(self):
        finish = threading.Event()
        self.register(handler=lambda i, c: (finish.wait(2), ok(i, c))[1], timeout=.02,
            supported_resources=(ResourceClaim("FOREGROUND_UI", exclusive=True),))
        task = TaskNode("test.work")
        result = self.kernel.run_task(task, ExecutionContext())
        self.assertEqual(result.errors[0].code, ErrorCode.TIMEOUT)
        self.assertTrue(self.kernel.resources.snapshot())
        blocked = self.kernel.dispatch("test.work", {})
        self.assertEqual(blocked.errors[0].code, ErrorCode.RESOURCE_UNAVAILABLE)
        finish.set()
        for _ in range(100):
            if not self.kernel.resources.snapshot():
                break
            time.sleep(.005)
        self.assertFalse(self.kernel.resources.snapshot())
        self.assertEqual(task.status, TaskStatus.FAILED)

    def test_resource_contention_excludes_overlapping_foreground_tasks(self):
        started, finish = threading.Event(), threading.Event()
        self.register(handler=lambda i, c: (started.set(), finish.wait(2), ok(i, c))[2],
            supported_resources=(ResourceClaim("FOREGROUND_UI", exclusive=True),))
        thread = threading.Thread(target=lambda: self.kernel.dispatch("test.work", {}))
        thread.start()
        self.assertTrue(started.wait(1))
        try:
            self.assertEqual(self.kernel.dispatch("test.work", {}).errors[0].code, ErrorCode.RESOURCE_UNAVAILABLE)
        finally:
            finish.set()
            thread.join(2)
        self.assertFalse(self.kernel.resources.snapshot())

    def test_claims_are_atomic_and_node_scoped_with_aggregate_capacity(self):
        resources = self.kernel.resources
        resources.register(ResourceDescriptor("GPU", 2, "phone"))
        self.assertTrue(resources.acquire("a", (ResourceClaim("GPU", 1, node_id="phone"),)))
        self.assertFalse(resources.acquire("b", (ResourceClaim("FOREGROUND_UI"), ResourceClaim("GPU", 2, node_id="phone"))))
        self.assertTrue(resources.acquire("c", (ResourceClaim("FOREGROUND_UI", exclusive=True),)))
        self.assertFalse(resources.acquire("d", (ResourceClaim("GPU", 1, node_id="phone"), ResourceClaim("GPU", 1, node_id="phone"))))
        resources.release("a")
        resources.release("c")

    def test_bounded_retry_and_explicit_alternative(self):
        attempts = []
        def fail(i, c):
            attempts.append(c.task_id)
            return ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, "transient", retryable=True)
        self.register(handler=fail, supports_retry=True)
        result = self.kernel.dispatch("test.work", {}, retry_policy=RetryPolicy(3))
        self.assertFalse(result.success)
        self.assertEqual(len(attempts), 3)
        fallback = self.kernel.dispatch("test.work", {}, retry_policy=RetryPolicy(2, alternative_capabilities=("kernel.echo",)))
        self.assertTrue(fallback.success)
        self.assertEqual(fallback.capability_id, "kernel.echo")

    def test_serialization_roundtrip_and_unsafe_interrupted_state_is_blocked(self):
        graph = TaskGraph((TaskNode("kernel.echo", {"value": "A"}, task_id="A"), TaskNode("kernel.echo", task_id="B", dependencies=("A",))), goal="example")
        self.kernel.run_graph(graph)
        loaded = TaskGraph.from_json(graph.to_json())
        self.assertEqual(loaded.graph_id, graph.graph_id)
        self.assertEqual(loaded.get("B").dependencies, ("A",))
        self.assertEqual(loaded.get("A").result.output, "A")
        self.assertEqual(loaded.get("A").status, TaskStatus.SUCCEEDED)
        graph.get("B").status = TaskStatus.RUNNING
        self.assertEqual(TaskGraph.from_json(graph.to_json()).get("B").status, TaskStatus.BLOCKED)

    def test_schema_invalid_input_platform_and_background_constraints(self):
        self.register(input_schema={"type": "object", "required": ["x"], "properties": {"x": {"type": "number"}}}, supports_background=False)
        self.assertEqual(self.kernel.dispatch("test.work", {"x": True}).errors[0].code, ErrorCode.INVALID_INPUT)
        self.assertEqual(self.kernel.dispatch("test.work", {"x": 1}, execution_mode=ExecutionMode.BACKGROUND).errors[0].code, ErrorCode.INVALID_INPUT)
        self.register("test.platform", supported_platforms=("fictional",))
        self.assertEqual(self.kernel.dispatch("test.platform", {}).errors[0].code, ErrorCode.CAPABILITY_UNAVAILABLE)

    def test_context_uses_structured_state_and_material_ambiguity_needs_clarification(self):
        resolver = self.kernel.context
        resolver.observe(ContextEntity("a", "file", "a.py", ("it",), salience=.8))
        resolver.observe(ContextEntity("b", "file", "b.py", ("it",), salience=.8))
        result = resolver.resolve("it", expected_kinds=("file",), material_action=True)
        self.assertTrue(result.needs_clarification)
        self.assertIsNone(result.entity)
        context = resolver.capture(project_id="workspace", active_files=("current.py",))
        self.assertEqual(context.project_id, "workspace")
        self.assertFalse(resolver.resolve("the current project", expected_kinds=("project",)).needs_clarification)

    def test_events_telemetry_and_history_have_stable_ids(self):
        events = []
        self.kernel.events.subscribe(events.append)
        result = self.kernel.dispatch("kernel.echo", {"value": 7})
        kinds = [e.event_type for e in events]
        self.assertLess(kinds.index(EventType.TASK_STARTED), kinds.index(EventType.TASK_COMPLETED))
        self.assertEqual(self.kernel.history()[-1]["task_id"], result.task_id)
        self.assertIn("execution_completed", {r.stage for r in self.kernel.telemetry.records()})
        self.assertIn("task_started", {r.stage for r in self.kernel.telemetry.records()})

    def test_priority_and_atomic_worker_claims_support_future_parallelism(self):
        graph = TaskGraph((TaskNode("kernel.echo", task_id="low", priority=Priority.LOW),
            TaskNode("kernel.echo", task_id="high", priority=Priority.INTERACTIVE)))
        claimed = []
        threads = [threading.Thread(target=lambda: claimed.append(graph.claim_ready().task_id)) for _ in range(2)]
        threads[0].start()
        threads[0].join()
        threads[1].start()
        threads[1].join()
        self.assertEqual(claimed, ["high", "low"])
        for node in graph.tasks:
            graph.finish(node, self.kernel.run_task(node, ExecutionContext()))
        self.assertTrue(graph.result().success)

    def test_retry_backoff_cannot_extend_task_deadline(self):
        self.register(handler=lambda i, c: ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, "retry", retryable=True), supports_retry=True)
        started = time.monotonic()
        result = self.kernel.dispatch("test.work", {}, timeout=.03, retry_policy=RetryPolicy(3, backoff=5))
        self.assertEqual(result.errors[0].code, ErrorCode.TIMEOUT)
        self.assertLess(time.monotonic() - started, .5)

    def test_resolved_inputs_use_memory_and_ambiguous_targets_never_execute(self):
        handler = Mock(side_effect=ok)
        self.register(handler=handler)
        self.kernel.context.observe(ContextEntity("a", "file", "a.py", ("it",), payload={"path": "a.py"}, salience=.8))
        self.kernel.context.observe(ContextEntity("b", "file", "b.py", ("it",), payload={"path": "b.py"}, salience=.8))
        constraints = {"references": {"path": {"reference": "it", "expected_kinds": ["file"]}}}
        result = self.kernel.dispatch("test.work", {}, constraints=constraints)
        self.assertEqual(result.errors[0].code, ErrorCode.INVALID_INPUT)
        handler.assert_not_called()
        self.assertTrue(self.kernel.context.resolve("nonexistent.py", expected_kinds=("file",), material_action=True).needs_clarification)
        self.kernel.context.memory = ContextResolver().memory
        self.kernel.context.observe(ContextEntity("a", "file", "a.py", payload={"path": "a.py"}, active=True))
        constraints["references"]["path"]["reference"] = "a.py"
        self.assertTrue(self.kernel.dispatch("test.work", {}, constraints=constraints).success)
        self.assertEqual(handler.call_args[0][0]["path"], "a.py")

    def test_graph_and_task_can_have_same_id_and_capability_dependency_missing(self):
        graph = TaskGraph((TaskNode("kernel.echo", task_id="same"),), graph_id="same")
        self.assertTrue(self.kernel.run_graph(graph).success)
        self.register(dependencies=("optional.missing",))
        self.assertEqual(self.kernel.dispatch("test.work", {}).errors[0].code, ErrorCode.DEPENDENCY_MISSING)

    def test_queued_graph_cancellation_sets_terminal_task_state(self):
        workers = Mock()
        from concurrent.futures import Future
        pending = Future()
        workers.submit.return_value = pending
        scheduler = TaskScheduler(self.kernel, workers)
        graph = TaskGraph((TaskNode("kernel.echo"),))
        scheduler.submit(graph)
        self.assertTrue(scheduler.cancel(graph.graph_id))
        self.assertEqual(graph.tasks[0].status, TaskStatus.CANCELLED)
        scheduler.shutdown()

    def test_interactive_lane_is_reserved_while_background_workers_are_busy(self):
        started = [threading.Event(), threading.Event()]
        finish = threading.Event()
        def background(inputs, context):
            started[inputs["slot"]].set()
            finish.wait(2)
            return ok(inputs, context)
        self.register(handler=background)
        scheduler = TaskScheduler(self.kernel)
        self.kernel.scheduler = scheduler
        futures = [scheduler.submit(TaskGraph((TaskNode("test.work", {"slot": slot}),))) for slot in range(2)]
        try:
            self.assertTrue(all(event.wait(1) for event in started))
            interactive = scheduler.submit(TaskGraph((TaskNode("kernel.echo"),)), priority=Priority.INTERACTIVE)
            self.assertTrue(interactive.result(.5).success)
        finally:
            finish.set()
            for future in futures:
                future.result(3)

    def test_throwing_adapter_does_not_break_other_capabilities(self):
        self.register(handler=Mock(side_effect=RuntimeError("broken adapter")))
        result = self.kernel.dispatch("test.work", {})
        self.assertEqual(result.errors[0].code, ErrorCode.EXECUTION_FAILED)
        self.assertIn("broken adapter", result.errors[0].detail)
        self.assertTrue(self.kernel.dispatch("kernel.echo", {}).success)

    def test_delegated_domain_grant_cannot_override_extra_task_permission(self):
        from morice.unified_intelligence import PermissionDecision
        handler = Mock(side_effect=ok)
        self.kernel.registry.register(CapabilityDescriptor("test.delegated", "Delegated"), handler,
            permission_check=lambda i, c: PermissionDecision(True))
        self.kernel.permissions.controller.set_state("send_message", PermissionState.DENIED)
        result = self.kernel.dispatch("test.delegated", {}, permissions=("send_message",))
        self.assertEqual(result.errors[0].code, ErrorCode.PERMISSION_DENIED)
        handler.assert_not_called()

    def test_completion_within_poll_interval_still_enforces_deadline(self):
        self.register(handler=lambda i, c: (time.sleep(.007), ok(i, c))[1])
        result = self.kernel.dispatch("test.work", {}, timeout=.001)
        self.assertEqual(result.errors[0].code, ErrorCode.TIMEOUT)


class EventBusTests(unittest.TestCase):
    def test_ordering_unsubscribe_duplicate_cleanup_exception_and_storm(self):
        bus = EventBus(max_pending=8)
        seen = []
        def callback(event):
            seen.append(event.source)
            if event.source == "first":
                bus.publish(KernelEvent(EventType.TASK_PROGRESS, source="second"))
        key = bus.subscribe(callback)
        self.assertEqual(bus.subscribe(callback), key)
        bus.publish(KernelEvent(EventType.TASK_STARTED, source="first"))
        self.assertEqual(seen, ["first", "second"])
        bus.unsubscribe(key)
        bus.publish(KernelEvent(EventType.TASK_STARTED))
        self.assertEqual(len(seen), 2)
        class Observer:
            def receive(self, event):
                raise AssertionError("Dead subscriber was called")
        observer = Observer()
        bus.subscribe(observer.receive)
        del observer
        gc.collect()
        bus.publish(KernelEvent(EventType.TASK_STARTED))
        self.assertEqual(len(bus._subscriptions), 0)
        bus.subscribe(lambda e: bus.publish(e))
        bus.publish(KernelEvent(EventType.TASK_PROGRESS))
        self.assertGreater(bus.dropped_events, 0)


class AdapterTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows process tree assertion")
    def test_terminal_cancellation_stops_child_process_tree(self):
        import ctypes
        from morice.agent_tools import BuiltinTools
        with tempfile.TemporaryDirectory() as directory:
            tools = BuiltinTools(Path(directory) / "tools")
            kernel = CapabilityKernel()
            register_tool_adapters(kernel, tools)
            child_file = Path(directory) / "child.pid"
            code = "import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)"
            inputs = {"cwd": directory, "command": [sys.executable, "-c", code, str(child_file)]}
            grant = tools.permissions.grant("terminal.run", inputs)
            results = []
            thread = threading.Thread(target=lambda: results.append(kernel.dispatch("terminal.run", inputs, ExecutionContext(approval_token=grant), task_id="parent")))
            thread.start()
            try:
                for _ in range(200):
                    if child_file.exists():
                        break
                    time.sleep(.01)
                self.assertTrue(child_file.exists())
                child_pid = int(child_file.read_text())
                self.assertTrue(kernel.cancel("parent"))
                thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(results[0].status, TaskStatus.CANCELLED)
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, child_pid)
                if handle:
                    exit_code = ctypes.c_ulong()
                    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                    ctypes.windll.kernel32.CloseHandle(handle)
                    self.assertNotEqual(exit_code.value, 259, "Command descendant is still active")
            finally:
                kernel.shutdown()
                thread.join(3)

    def test_existing_patch_search_project_verify_and_background_process_through_kernel(self):
        from morice.agent_tools import BuiltinTools
        from morice.agent_types import ToolCall, ToolResult
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            (root / "main.py").write_text("print('before')\n", encoding="utf-8")
            tools = BuiltinTools(Path(directory) / "tools")
            kernel = CapabilityKernel()
            kernel.resources.register(ResourceDescriptor("DISK"))
            register_tool_adapters(kernel, tools)
            try:
                args = {"root": str(root), "changes": [{"path": "main.py", "content": "print('after')\n"}]}
                denied = tools.executor.execute(ToolCall("filesystem.apply_patch", args))
                self.assertFalse(denied.success)
                token = tools.permissions.grant("filesystem.apply_patch", args)
                written = tools.executor.execute(ToolCall("filesystem.apply_patch", args, permission_token=token))
                self.assertTrue(written.success)
                self.assertTrue(written.verified)
                self.assertTrue(written.metadata["kernelTaskId"])
                self.assertEqual((root / "main.py").read_text(), "print('after')\n")
                searched = tools.executor.execute(ToolCall("filesystem.search", {"root": str(root), "query": "after"}))
                self.assertTrue(searched.success)
                self.assertTrue(tools.executor.execute(ToolCall("project.verify", {"root": str(root)})).verified)
                tools.registry._handlers["project.verify"] = lambda args: ToolResult("project.verify", True, 0, output={}, verified=False)
                unverified = tools.executor.execute(ToolCall("project.verify", {"root": str(root)}))
                self.assertFalse(unverified.success)
                self.assertFalse(tools.history.recent()[-1].success)
                command = {"cwd": str(root), "command": [sys.executable, "-c", "print(2+3)"]}
                token = tools.permissions.grant("terminal.run", command)
                result = kernel.dispatch("terminal.run", command, ExecutionContext(approval_token=token), execution_mode=ExecutionMode.BACKGROUND)
                self.assertTrue(result.success)
                self.assertEqual(result.output["stdout"].strip(), "5")
            finally:
                kernel.shutdown()

    def test_terminal_timeout_and_cancel_reap_process_and_leave_next_command_operational(self):
        from morice.agent_tools import BuiltinTools
        with tempfile.TemporaryDirectory() as directory:
            tools = BuiltinTools(Path(directory) / "tools")
            kernel = CapabilityKernel()
            register_tool_adapters(kernel, tools)
            try:
                inputs = {"cwd": directory, "command": [sys.executable, "-c", "import time; time.sleep(20)"]}
                grant = tools.permissions.grant("terminal.run", inputs)
                timeout = kernel.dispatch("terminal.run", inputs, ExecutionContext(approval_token=grant), timeout=.15)
                self.assertEqual(timeout.errors[0].code, ErrorCode.TIMEOUT)
                self.assertFalse(tools._active_processes)
                grant = tools.permissions.grant("terminal.run", inputs)
                result = []
                thread = threading.Thread(target=lambda: result.append(kernel.dispatch("terminal.run", inputs, ExecutionContext(approval_token=grant), task_id="process")))
                thread.start()
                for _ in range(100):
                    if tools._active_processes:
                        break
                    time.sleep(.01)
                self.assertTrue(tools.cancel("process"))
                thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(result[0].status, TaskStatus.CANCELLED)
                self.assertFalse(tools._active_processes)
            finally:
                kernel.shutdown()

    def test_real_read_calculation_graph_adapters(self):
        from morice.desktop_environment import DesktopIntegrationLayer
        with tempfile.TemporaryDirectory() as directory:
            desktop = DesktopIntegrationLayer(Path(directory) / "desktop")
            kernel = CapabilityKernel()
            kernel.permissions.controller.set_state("file_read", PermissionState.GRANTED)
            register_native_adapters(kernel, desktop)
            path = Path(directory) / "read.txt"
            path.write_text("kernel read test", encoding="utf-8")
            try:
                read = kernel.dispatch("filesystem.read", {"path": str(path)})
                self.assertTrue(read.success, read.errors)
                self.assertEqual(read.output["content"], "kernel read test")
                calculation = kernel.dispatch("python.calculate", {"expression": "x**2+3", "x": 2}, verification_policy=VerificationPolicy(expected_outcome=7))
                self.assertTrue(calculation.success, calculation.errors)
                self.assertTrue(kernel.dispatch("graph.render", {"prompt": "plot y = x^2"}).success)
            finally:
                kernel.shutdown()
                desktop.shutdown()

    def test_fast_pc_route_uses_kernel_without_model_and_preserves_verification(self):
        from morice.pc_control import (ControlProviderRegistry, ControlResult, DesktopContext,
            FastActionRouter, PermissionBroker, PermissionCategory, PolicyMode)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        broker = PermissionBroker(Path(temporary.name) / "permissions.json", defaults={PermissionCategory.APPLICATION_CONTROL: PolicyMode.ALLOW})
        registry = ControlProviderRegistry(broker)
        class Adapter:
            adapter_id = "test.application"
            def supports(self, action): return action.tool_id == "application.open"
            def availability(self, action=None): return True, ""
            def execute(self, action, context):
                return ControlResult(action.action_id, action.tool_id, True, True, "Observed application process.")
        registry.register(Adapter())
        kernel = CapabilityKernel()
        register_pc_adapters(kernel, registry)
        try:
            route = FastActionRouter(DesktopContext()).route("Open Calculator")
            self.assertEqual(route.model_invocations, 0)
            result = registry.execute(route.action)
            self.assertTrue(result.success)
            self.assertTrue(result.verified)
            self.assertEqual(kernel.history()[-1]["capability_id"], "application.open")
            registry._entries[0].adapter.execute = lambda a, c: ControlResult(a.action_id, a.tool_id, True, False, "Attempt only")
            self.assertFalse(registry.execute(route.action).success)
        finally:
            kernel.shutdown()

    def test_runtime_kernel_startup_ignores_broken_optional_capability(self):
        from morice.runtime_services import RuntimeServices
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeServices(directory)
            runtime.kernel.registry.register(CapabilityDescriptor("optional.broken", "Broken"), ok,
                health_check=Mock(side_effect=ImportError("missing extra")))
            try:
                self.assertTrue(runtime.kernel.dispatch("kernel.echo", {}).success)
                self.assertEqual(runtime.kernel.registry.health("optional.broken").status, Availability.UNAVAILABLE)
                self.assertGreaterEqual(len(runtime.kernel.registry.search()), 16)
            finally:
                runtime.shutdown()
