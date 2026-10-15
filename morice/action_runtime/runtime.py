"""Observe/verify extension. Kernel still authorizes, executes, retries and owns leases."""
from __future__ import annotations

import time
import uuid
import hashlib
import threading
from pathlib import Path
from dataclasses import asdict, replace

from ..kernel import CancellationToken, ErrorCode, ExecutionResult, TaskStatus, VerificationResult, VerificationStatus
from ..kernel.registry import CapabilityEntry
from ..kernel.contracts import CapabilityDescriptor
from ..kernel import ResourceClaim, ResourceDescriptor
from .contracts import ActionBinding, ActionSpec, Observation, UserInterventionRequired, VerificationLevel
from .journal import ActionJournal


class VerifiedActionRuntime:
    def __init__(self, kernel, journal=None):
        self.kernel = kernel
        self.journal = journal or ActionJournal()
        self._bindings = {}
        self._project_resources = set()
        self._prepare_lock = threading.RLock()
        kernel.actions = self

    def register(self, capability_id: str, binding: ActionBinding, node_id="local"):
        if self.kernel.registry.lookup(capability_id, node_id) is None:
            raise ValueError("Register the capability with the existing kernel first.")
        self._bindings[capability_id if node_id == "local" else (node_id, capability_id)] = binding

    @staticmethod
    def _binding_key(entry):
        d = entry.descriptor
        return d.capability_id if d.node_id == "local" else (d.node_id, d.capability_id)

    def supports(self, task, entry):
        return self._binding_key(entry) in self._bindings

    def prepare_task(self, task):
        if task.constraints.get("node_id", "local") != "local":
            return  # Remote workspaces and observations belong to that provider.
        if task.capability_requirement in self._bindings:
            alternatives = task.retry_policy.alternative_capabilities
            if task.capability_requirement in alternatives or len(set(alternatives)) != len(alternatives):
                raise ValueError("Recovery alternatives must use distinct registered methods.")
        if task.capability_requirement != "terminal.run" or not isinstance(task.inputs, dict) or not task.inputs.get("cwd"):
            return
        root = str(Path(task.inputs["cwd"]).resolve()).casefold()
        resource = "PROJECT_BUILD:" + hashlib.sha256(root.encode()).hexdigest()[:24]
        with self._prepare_lock:
            if resource not in self._project_resources:
                if len(self._project_resources) >= 256:
                    raise ValueError("Action runtime workspace resource limit reached.")
                self.kernel.resources.register(ResourceDescriptor(resource))
                self._project_resources.add(resource)
        if not any(c.resource == resource for c in task.resource_requirements):
            task.resource_requirements += (ResourceClaim(resource, exclusive=True),)

    def specification(self, task, entry):
        binding = self._bindings[self._binding_key(entry)]
        desired = binding.desired(task.inputs, task.verification_policy.expected_outcome)
        return ActionSpec(task.task_id, task.task_id, task.description or entry.descriptor.name,
            str(task.inputs.get("target", task.inputs.get("path", task.inputs.get("root", "")))),
            entry.descriptor.capability_id, binding.method, desired,
            VerificationLevel(task.constraints.get("verification_level", "normal")),
            min(10.0, max(.01, float(task.constraints.get("observation_timeout", 3.0)))),
            min(100, max(1, int(task.constraints.get("max_observations", 40)))),
            expected_outcome=task.verification_policy.expected_outcome)

    def _observe(self, binding, spec, context, result=None, before=None):
        if context.cancellation_token.cancelled:
            return Observation(spec.action_id, "cancelled", {}, errors=("Observation cancelled.",))
        if time.monotonic() >= context.deadline:
            return Observation(spec.action_id, "deadline", {}, errors=("Observation deadline reached.",))
        try:
            value = binding.observe(spec, context, result, before)
            if not isinstance(value, Observation) or value.action_id != spec.action_id:
                raise ValueError("Mismatched observation contract.")
            return value
        except UserInterventionRequired:
            raise
        except Exception as exc:
            return Observation(spec.action_id, "unavailable", {}, errors=(f"Observer unavailable: {type(exc).__name__}",))

    @staticmethod
    def _verify(binding, spec, observation, before):
        if spec.level == VerificationLevel.NONE:
            return VerificationResult(VerificationStatus.INCONCLUSIVE, message="Mutable action success requires observed evidence.")
        age = time.time() - observation.timestamp
        if observation.errors or age > spec.freshness_seconds or age < -1:
            return VerificationResult(VerificationStatus.INCONCLUSIVE, message="Fresh independent observation unavailable.")
        if observation.state.get("waiting_for_user"):
            return VerificationResult(VerificationStatus.INCONCLUSIVE, message="User action is required before verification can continue.")
        value = binding.verify(spec, observation, before)
        if not isinstance(value, VerificationResult):
            raise TypeError("Invalid verification result.")
        if value.status == VerificationStatus.VERIFIED and spec.expected_outcome is not None:
            expected = spec.expected_outcome
            if not isinstance(expected, dict):
                return VerificationResult(VerificationStatus.INCONCLUSIVE, message="This action requires a structured expected outcome.")
            for key, wanted in expected.items():
                if key not in observation.state:
                    return VerificationResult(VerificationStatus.INCONCLUSIVE, message=f"Expected field cannot be observed: {key}.")
                actual = observation.state[key]
                if key == "url":
                    from .verification import normalized_url
                    equal = normalized_url(str(actual)) == normalized_url(str(wanted))
                else:
                    equal = actual == wanted
                if not equal:
                    return VerificationResult(VerificationStatus.FAILED, message=f"Observed {key} differs from the expected outcome.")
        return value

    def execute(self, task, entry, context, execution_id):
        if self.journal.load_error:
            return self._waiting(self.journal.load_error)
        binding = self._bindings[self._binding_key(entry)]
        spec = self.specification(task, entry)
        self.journal.update(execution_id, action_id=spec.action_id, task_id=spec.task_id,
            capability_id=spec.capability_id, method=spec.method.value, target=spec.target,
            desired_state=spec.desired_state, risk=entry.descriptor.risk_level.value,
            permissions=list(entry.descriptor.required_permissions), phase="observing_before",
            preconditions={"authorization": "kernel", "resource_lease": execution_id},
            postconditions=spec.desired_state, verification_level=spec.level.value,
            workflow_id=context.metadata.get("workflow_id", ""),
            max_attempts=task.retry_policy.max_attempts, alternatives=list(task.retry_policy.alternative_capabilities), durable=False)
        before = self._observe(binding, spec, context)
        self.journal.update(execution_id, before=asdict(before), durable=False)
        if before.state.get("waiting_for_user"):
            return self._waiting("Target is ambiguous or requires user intervention.")
        current = self._verify(binding, spec, before, None)
        if binding.idempotent and current.status == VerificationStatus.VERIFIED:
            value = ExecutionResult(TaskStatus.SUCCEEDED, True, output={"already_satisfied": True},
                verification=current, verification_required=True, evidence=list(current.evidence))
            value.metrics.update(action_noop=1, action_observations=1)
            self.journal.update(execution_id, phase="verified_noop", after=asdict(before), durable=False)
            return value
        # Persist the intent before calling an existing mutating handler.
        self.journal.update(execution_id, phase="executing")
        last = None
        observations = 0
        def verify(result, expected, ctx):
            nonlocal last, observations
            until = min(ctx.deadline, time.monotonic() + spec.observation_timeout)
            delay = .01
            while observations < spec.max_observations:
                if ctx.cancellation_token.cancelled:
                    return VerificationResult(VerificationStatus.INCONCLUSIVE, message="Verification cancelled.")
                last = self._observe(binding, spec, ctx, result, before)
                observations += 1
                check = self._verify(binding, spec, last, before)
                self.journal.update(execution_id, phase="verifying", after=asdict(last),
                    verification_id=str(uuid.uuid4()), verification=check.status.value, durable=False)
                if check.status == VerificationStatus.VERIFIED or last.state.get("waiting_for_user") or time.monotonic() >= until:
                    return check
                ctx.cancellation_token.wait(min(delay, max(0, until - time.monotonic())))
                delay = min(.2, delay * 1.6)
            return check
        handler = binding.execute or entry.handler
        wrapped = replace(entry, handler=handler, verifier=verify)
        result = self.kernel._execute_and_verify(task, wrapped, context, execution_id, bypass_actions=True)
        if not observations:
            last = self._observe(binding, spec, context, result, before)
            observations = 1
            result.verification = self._verify(binding, spec, last, before)
            # An observed state cannot turn a rejected execution into success.
            self.journal.update(execution_id, phase="failed_attempt", after=asdict(last), durable=False)
        if (last and last.state.get("waiting_for_user")) or isinstance(result.output, dict) and result.output.get("waiting_for_user"):
            result.status, result.success, result.retryable = TaskStatus.BLOCKED, False, False
        # Identical retries are forbidden. Explicit alternative capabilities are
        # selected and authorized by the kernel's existing retry policy.
        result.retryable = bool(not result.success and task.attempts <= len(task.retry_policy.alternative_capabilities)
            and result.status not in {TaskStatus.CANCELLED, TaskStatus.BLOCKED}
            and not any(e.code in {ErrorCode.PERMISSION_DENIED, ErrorCode.TIMEOUT} for e in result.errors))
        result.metrics.update(action_observations=observations + 1, action_noop=0)
        undo = getattr(result.legacy_result, "metadata", {}).get("undoId", "")
        self.journal.update(execution_id, rollback_reference=undo, durable=False)
        return result

    @staticmethod
    def _waiting(message):
        return ExecutionResult(TaskStatus.BLOCKED, False, output={"action_status": "waiting_for_user"},
            verification=VerificationResult(VerificationStatus.INCONCLUSIVE, message=message))

    def attempt_finished(self, task, result, context):
        if self.journal.load_error:
            return
        entry = self.kernel.registry.lookup(context.capability_id, task.constraints.get("node_id", "local"))
        if entry is None or self._binding_key(entry) not in self._bindings:
            return
        if any(e.code == ErrorCode.CAPABILITY_UNAVAILABLE for e in result.errors) and task.attempts <= len(task.retry_policy.alternative_capabilities):
            result.retryable = True
        self.journal.update(result.execution_id, terminal=True, durable=False, action_id=task.task_id,
            task_id=task.task_id, target=str(task.inputs.get("target", task.inputs.get("root", ""))),
            risk=entry.descriptor.risk_level.value,
            permissions=list(entry.descriptor.required_permissions),
            max_attempts=task.retry_policy.max_attempts, alternatives=list(task.retry_policy.alternative_capabilities),
            capability_id=context.capability_id, method=self._bindings[self._binding_key(entry)].method.value,
            phase=result.status.value, success=result.success,
            verification=result.verification.status.value if result.verification else "not_observed",
            errors=[e.code.value for e in result.errors], metrics=result.metrics)

    def complete_task(self, task, result, context):
        if self.journal.load_error:
            return
        entry = self.kernel.registry.lookup(context.capability_id, task.constraints.get("node_id", "local"))
        if entry is not None and self._binding_key(entry) in self._bindings:
            self.journal.update(result.execution_id, terminal=True, finalize=True, phase=result.status.value,
                success=result.success, metrics=result.metrics, errors=[e.code.value for e in result.errors])

    def reconcile(self, task, context):
        """Read current state after interruption; never replay a mutation."""
        if self.journal.load_error:
            return self._waiting(self.journal.load_error)
        entry = self.kernel.registry.lookup(task.capability_requirement, task.constraints.get("node_id", "local"))
        if entry is None or not self.supports(task, entry):
            return self._waiting("No observer is available for this interrupted action.")
        permission = "file_read" if entry.descriptor.capability_id in {"filesystem.apply_patch", "artifact.verify", "file.open"} else "read_system_state" if entry.descriptor.capability_id.startswith(("application.", "media.")) else "browser_control"
        observation_entry = CapabilityEntry(CapabilityDescriptor("action.reconcile", "Observe interrupted action",
            required_permissions=entry.descriptor.required_permissions if entry.descriptor.node_id != "local" else (permission,)), lambda *args: None)
        decision = self.kernel.permissions.authorize(observation_entry, {"target": task.inputs.get("target", task.inputs.get("root", ""))}, replace(context, approval_token=""))
        if not decision.allowed:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED, decision.reason)
        spec = self.specification(task, entry)
        binding = self._bindings[self._binding_key(entry)]
        # No command invocation and no consumption/reuse of an old approval token.
        ctx = replace(context, task_id=task.task_id, capability_id=entry.descriptor.capability_id,
            deadline=min(context.deadline or float("inf"), time.monotonic() + spec.observation_timeout),
            cancellation_token=context.cancellation_token or CancellationToken(),
            metadata={**context.metadata, "task_inputs": task.inputs})
        owner = uuid.uuid4().hex
        claims = (*entry.descriptor.supported_resources, *task.resource_requirements)
        if not self.kernel.resources.acquire(owner, claims):
            return self._waiting("The interrupted action's resources are busy; observation requires review.")
        try:
            observation = self._observe(binding, spec, ctx)
        finally:
            self.kernel.resources.release(owner)
        check = self._verify(binding, spec, observation, None)
        if check.status == VerificationStatus.VERIFIED:
            return ExecutionResult(TaskStatus.SUCCEEDED, True, output={"reconciled": True, "observed_state": observation.state}, verification=check,
                evidence=list(check.evidence), artifacts=list(observation.state.get("files", [])))
        return self._waiting("Interrupted action needs review; no mutation was replayed.")

    def rollback(self, action_id, context):
        records = [v for v in self.journal.attempts(action_id) if v.get("rollback_reference")]
        workflow = context.metadata.get("workflow_id", "")
        if not records or not workflow or records[-1].get("workflow_id") != workflow:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED, "Rollback must belong to the requesting workflow.")
        return self.kernel.dispatch("action.undo", {"undo_id": records[-1]["rollback_reference"]}, context)
