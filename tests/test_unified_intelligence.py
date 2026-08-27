from __future__ import annotations

import threading
import time
import unittest

from morice.unified_intelligence import (
    CapabilityCall,
    CapabilityOutcome,
    CapabilityRegistry,
    CapabilitySpec,
    ContextEntity,
    ExecutionPath,
    GoalExecutionOrchestrator,
    GoalState,
    PermissionController,
    PermissionState,
    RiskClass,
    SemanticInterpreter,
    WorkingMemory,
)


class UnifiedGoalExecutionTests(unittest.TestCase):
    def test_instant_route_never_invokes_semantic_backend(self):
        registry = CapabilityRegistry()
        registry.register(
            CapabilitySpec(
                "media.pause",
                "Pause media",
                "Pause the current media session.",
                verification_required=False,
            ),
            lambda _args, _cancel: CapabilityOutcome(True, True),
        )

        def semantic_backend(*_args):
            raise AssertionError("instant route called the semantic model")

        orchestrator = GoalExecutionOrchestrator(
            registry,
            semantic=SemanticInterpreter(semantic_backend),
            fast_router=lambda request, _context: (
                CapabilityCall("pause", "media.pause")
                if request.casefold() == "pause"
                else None
            ),
        )
        try:
            plan = orchestrator.plan("Pause")
            result = orchestrator.execute(plan)
        finally:
            orchestrator.shutdown()

        self.assertEqual(plan.path, ExecutionPath.INSTANT)
        self.assertEqual(result.state, GoalState.COMPLETED)

    def test_independent_capabilities_execute_in_parallel_and_verify(self):
        registry = CapabilityRegistry()
        starts: list[float] = []
        lock = threading.Lock()

        def handler(arguments, _cancel):
            with lock:
                starts.append(time.perf_counter())
            time.sleep(0.04)
            return CapabilityOutcome(True, True, output=arguments)

        for capability in ("camera.frame", "system.info"):
            registry.register(
                CapabilitySpec(
                    capability,
                    capability,
                    capability,
                    verification_required=False,
                    concurrent=True,
                ),
                handler,
            )

        def backend(_request, _context, _capabilities):
            return {
                "goal": "identify visible hardware compatibility",
                "complexity": "agentic",
                "candidateCapabilities": ["camera.frame", "system.info"],
                "actions": [
                    {"stepId": "camera", "capability": "camera.frame"},
                    {"stepId": "system", "capability": "system.info"},
                ],
                "confidence": 0.93,
            }

        orchestrator = GoalExecutionOrchestrator(
            registry, semantic=SemanticInterpreter(backend), max_parallel=2
        )
        try:
            plan = orchestrator.plan("Will this board work with my PC?")
            result = orchestrator.execute(plan)
        finally:
            orchestrator.shutdown()

        self.assertEqual(plan.path, ExecutionPath.AGENTIC)
        self.assertEqual(plan.parallel_layers, (("camera", "system"),))
        self.assertEqual(result.state, GoalState.COMPLETED)
        self.assertLess(abs(starts[0] - starts[1]), 0.03)

    def test_context_reference_uses_active_recent_entity(self):
        memory = WorkingMemory()
        memory.observe(
            ContextEntity(
                "music-1",
                "application",
                "Amazon Music",
                aliases=("music", "it"),
                active=True,
            )
        )

        resolved = memory.resolve("it", expected_kinds=("application",))

        self.assertIsNotNone(resolved.entity)
        self.assertEqual(resolved.entity.label, "Amazon Music")
        self.assertFalse(resolved.needs_clarification)

    def test_retryable_failure_recovers_within_limit(self):
        registry = CapabilityRegistry()
        attempts = 0

        def flaky(_arguments, _cancel):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return CapabilityOutcome(False, False, error="temporary", retryable=True)
            return CapabilityOutcome(True, True)

        registry.register(
            CapabilitySpec(
                "service.restore",
                "Restore service",
                "Restore and verify a service.",
                max_retries=2,
                verification_required=False,
            ),
            flaky,
        )
        orchestrator = GoalExecutionOrchestrator(
            registry,
            semantic=SemanticInterpreter(
                lambda *_args: {
                    "goal": "restore service",
                    "actions": [{"capability": "service.restore"}],
                }
            ),
        )
        try:
            result = orchestrator.execute(orchestrator.plan("Get it back online"))
        finally:
            orchestrator.shutdown()

        self.assertEqual(result.state, GoalState.COMPLETED)
        self.assertEqual(attempts, 2)
        self.assertEqual(result.recovery_count, 1)

    def test_high_risk_action_requires_exact_one_use_approval(self):
        registry = CapabilityRegistry()
        registry.register(
            CapabilitySpec(
                "system.destructive",
                "Destructive operation",
                "A test-only high-risk action.",
                permissions=("system_settings",),
                risk=RiskClass.HIGH,
                verification_required=False,
            ),
            lambda _args, _cancel: CapabilityOutcome(True, True),
        )
        permissions = PermissionController(
            states={"system_settings": PermissionState.GRANTED}
        )
        backend = SemanticInterpreter(
            lambda *_args: {
                "goal": "high risk test",
                "actions": [{"stepId": "danger", "capability": "system.destructive"}],
            }
        )
        orchestrator = GoalExecutionOrchestrator(
            registry, semantic=backend, permissions=permissions
        )
        try:
            denied_plan = orchestrator.plan("perform the test operation")
            denied = orchestrator.execute(denied_plan)
            approved_plan = orchestrator.plan("perform the test operation")
            token = permissions.issue_one_use(
                approved_plan.task_id, "system.destructive", {}
            )
            approved = orchestrator.execute(
                approved_plan, approval_tokens={"danger": token}
            )
        finally:
            orchestrator.shutdown()

        self.assertEqual(denied.state, GoalState.FAILED)
        self.assertIn("one-use", denied.error)
        self.assertEqual(approved.state, GoalState.COMPLETED)


if __name__ == "__main__":
    unittest.main()
