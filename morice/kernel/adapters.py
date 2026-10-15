"""Incremental adapters; existing implementations remain policy authorities."""
from __future__ import annotations

import hashlib
import platform
import shutil
from dataclasses import replace
from pathlib import Path

from ..agent_types import PermissionStatus, RiskLevel, ToolCall, ToolResult, ToolStatus
from ..unified_intelligence import PermissionDecision, RiskClass
from .contracts import (Availability, CapabilityDescriptor, ErrorCode, ExecutionContext,
    ExecutionResult, ResourceClaim, TaskStatus, VerificationResult, VerificationStatus)
from .registry import CapabilityHealth


def legacy_verifier(result, expected, context) -> VerificationResult:
    legacy = result.legacy_result
    verified = bool(legacy is not None and legacy.success and legacy.verified)
    return VerificationResult(VerificationStatus.VERIFIED if verified else VerificationStatus.FAILED,
        tuple(result.observations) if verified else (), "Existing adapter could not verify the outcome." if not verified else "")


def from_tool_result(value: ToolResult) -> ExecutionResult:
    if not value.success:
        code = ErrorCode.PERMISSION_DENIED if value.permission_status in {PermissionStatus.REQUIRED, PermissionStatus.DENIED} else ErrorCode.TIMEOUT if isinstance(value.output, dict) and value.output.get("timedOut") else ErrorCode.EXECUTION_FAILED
        result = ExecutionResult.failure(code, "; ".join(value.errors) or "Tool failed.", retryable=value.retryable)
    else:
        result = ExecutionResult(TaskStatus.SUCCEEDED, True, output=value.output, verification_required=True)
    result.legacy_result = value
    result.output = value.output  # failed test/process evidence must survive too
    result.warnings.extend(value.warnings)
    result.artifacts.extend(value.artifacts)
    result.observations.append(f"Existing tool reported verified={value.verified}.")
    return result


def tool_result_from_kernel(result: ExecutionResult, call: ToolCall) -> ToolResult:
    value = result.legacy_result
    if isinstance(value, ToolResult):
        value.success = result.success
        value.verified = bool(result.success and result.verification and result.verification.status == VerificationStatus.VERIFIED)
        value.errors.extend(e.message for e in result.errors if e.message not in value.errors)
    else:
        value = ToolResult(call.tool_id, result.success, result.metrics.get("execution_ms", 0), output=result.output,
            errors=[e.message for e in result.errors], warnings=list(result.warnings),
            permission_status=PermissionStatus.REQUIRED if any(e.code == ErrorCode.PERMISSION_DENIED for e in result.errors) else PermissionStatus.NOT_REQUIRED)
    value.metadata.update(kernelTaskId=result.task_id, kernelExecutionId=result.execution_id, kernelStatus=result.status.value)
    return value


def register_tool_adapters(kernel, tools) -> None:
    # Representative migration. Registration is data-driven from existing tool
    # definitions; later providers can register without editing the kernel.
    selected = {"filesystem.search", "filesystem.preview_patch", "filesystem.apply_patch", "project.index", "project.verify", "terminal.run", "git.status", "git.diff", "action.undo"}
    for definition in tools.registry.definitions():
        if definition.tool_id not in selected:
            continue
        def permission_check(inputs, context, d=definition):
            call = ToolCall(d.tool_id, inputs, call_id=context.task_id, permission_token=context.approval_token)
            allowed = d.risk == RiskLevel.READ_ONLY and not d.permissions or tools.permissions.check(call)
            return PermissionDecision(allowed, reason="" if allowed else "Explicit permission is required before this tool can run.")
        def execute(inputs, context, d=definition):
            call = ToolCall(d.tool_id, inputs, call_id=context.task_id, permission_token=context.approval_token)
            return from_tool_result(tools.executor._execute_legacy(call, execution_context=context, record=False))
        def completed(result, context, d=definition):
            call = ToolCall(d.tool_id, context.metadata["task_inputs"], call_id=context.task_id)
            value = tool_result_from_kernel(result, call)
            result.legacy_result = value
            tools.executor._record(call, value, d)
        def verify(result, expected, context, d=definition):
            verification = legacy_verifier(result, expected, context)
            # Check actual bytes, not merely the old executor's success flag.
            if d.tool_id == "filesystem.apply_patch" and result.success:
                for change in context.metadata["task_inputs"]["changes"]:
                    path = Path(context.metadata["task_inputs"]["root"]).resolve() / change["path"]
                    if not path.is_file() or hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(change["content"].encode("utf-8")).digest():
                        return VerificationResult(VerificationStatus.FAILED, message="Written file content did not match the approved patch.")
                return VerificationResult(VerificationStatus.VERIFIED, ("Approved patch bytes read back from disk.",))
            return verification
        def health(d=definition):
            current = tools.registry.definition(d.tool_id)
            if current is None or current.health_status != ToolStatus.READY:
                return CapabilityHealth(Availability.UNAVAILABLE, "Existing tool is not ready.")
            missing = [name for name in current.dependencies if not shutil.which(name)]
            return CapabilityHealth(Availability.UNAVAILABLE if missing else Availability.AVAILABLE, "Missing executables: " + ", ".join(missing) if missing else "")
        claims = (ResourceClaim("DISK", exclusive=True),) if definition.tool_id == "filesystem.apply_patch" else ()
        kernel.registry.register(CapabilityDescriptor(definition.tool_id, definition.display_name, definition.description,
            version=definition.version, provider="builtin-tools", category=definition.tool_id.split(".")[0],
            input_schema=definition.input_schema, output_schema=definition.output_schema,
            required_permissions=definition.permissions,
            risk_level={RiskLevel.READ_ONLY: RiskClass.LOW, RiskLevel.WORKSPACE_WRITE: RiskClass.MEDIUM, RiskLevel.DANGEROUS: RiskClass.HIGH}[definition.risk],
            supported_platforms=definition.supported_platforms, supported_resources=claims,
            supports_background=True, supports_cancellation=definition.cancellation_supported,
            supports_verification=True, supports_retry=definition.idempotent,
            timeout=definition.timeout_seconds, inline=definition.risk == RiskLevel.WORKSPACE_WRITE and not definition.cancellation_supported),
            execute, verifier=verify, health_check=health, permission_check=permission_check, on_completed=completed)
    tools.executor.kernel = kernel


def register_pc_adapters(kernel, registry) -> None:
    from ..pc_control import ActionRisk, ControlAction, PermissionCategory
    from .resources import ResourceDescriptor
    if kernel.resources.descriptor("MEDIA_SESSION") is None:
        kernel.resources.register(ResourceDescriptor("MEDIA_SESSION"))
    for capability_id, permissions, claims in (
        ("application.open", (PermissionCategory.APPLICATION_CONTROL,), (ResourceClaim("FOREGROUND_UI", exclusive=True),)),
        *((f"application.{verb}", (PermissionCategory.APPLICATION_CONTROL, PermissionCategory.WINDOW_CONTROL), (ResourceClaim("FOREGROUND_UI", exclusive=True),)) for verb in ("focus", "restore", "maximize", "minimize", "close", "close_others")),
        *((f"browser.{verb}", (PermissionCategory.BROWSER_CONTROL, PermissionCategory.NETWORK_ACCESS, *extra),
            (ResourceClaim("BROWSER_SESSION", exclusive=True), *((ResourceClaim("DISK", exclusive=True),) if verb == "download" else ()))) for verb, extra in (
            ("open", ()), ("navigate", ()), ("back", ()), ("forward", ()), ("reload", ()), ("find", ()), ("click", ()), ("type", ()),
            ("submit", ()), ("download", (PermissionCategory.FILE_WRITE,)), ("upload", (PermissionCategory.FILE_READ,)),
            ("extract", ()), ("tab_open", ()), ("tab_switch", ()), ("tab_close", ()))),
        *((f"media.{verb}", (PermissionCategory.MEDIA_CONTROL,), (ResourceClaim("MEDIA_SESSION", exclusive=True),
            *((ResourceClaim("FOREGROUND_UI", exclusive=True),) if verb in {"pause", "resume", "next", "previous", "restart", "play_query"} else ()))) for verb in ("set_volume", "pause", "resume", "mute", "volume", "next", "previous", "restart", "play_query", "status")),
        ("system.status", (PermissionCategory.READ_SYSTEM_STATE,), ()),
        ("file.open", (PermissionCategory.FILE_READ,), (ResourceClaim("FOREGROUND_UI", exclusive=True),)),
        *((f"file.{verb}", (PermissionCategory.FILE_READ,), (ResourceClaim("FOREGROUND_UI", exclusive=True),)) for verb in ("reveal", "open_recent")),
        ("file.search", (PermissionCategory.FILE_READ,), ()),
        ("screenshot.capture", (PermissionCategory.SCREEN_ACCESS,), (ResourceClaim("FOREGROUND_UI", exclusive=True),)),
    ):
        def action_for(inputs, context, cid=capability_id, required=permissions):
            action = context.metadata.get("control_action")
            if action is not None:
                if action.tool_id != cid:
                    raise ValueError("PC action does not match its capability permission contract.")
                return replace(action, permissions=tuple(dict.fromkeys((*action.permissions, *required))),
                    risk=ActionRisk.DESTRUCTIVE if cid in {"browser.click", "browser.submit", "browser.upload", "application.close_others"} else action.risk)
            domain, verb = cid.split(".", 1)
            return ControlAction(domain, verb, inputs.get("target", ""), inputs.get("arguments", {}),
                required, ActionRisk.DESTRUCTIVE if cid in {"browser.click", "browser.submit", "browser.upload", "application.close_others"} else ActionRisk.ROUTINE, action_id=context.task_id)
        def permission_check(inputs, context, make_action=action_for):
            # Preview only. The old registry consumes the exact grant once.
            action = make_action(inputs, context)
            decision = registry.permission_broker.authorize(action, consume_confirmation=False,
                confirmation_token=context.approval_token)
            return PermissionDecision(decision.allowed, reason=decision.reason)
        def execute(inputs, context, make_action=action_for):
            action = make_action(inputs, context)
            value = registry._execute_legacy(action, confirmation_token=context.approval_token,
                execution_context=context if kernel.actions is not None else None, record=False)
            result = ExecutionResult(TaskStatus.SUCCEEDED, True, output=dict(value.output), verification_required=True) if value.success else ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, value.message)
            result.legacy_result = value
            result.output = dict(value.output)
            result.observations.append(value.message)
            return result
        def completed(result, context, make_action=action_for):
            from ..pc_control import ControlResult
            action = make_action(context.metadata["task_inputs"], context)
            verified = bool(result.success and result.verification and result.verification.status == VerificationStatus.VERIFIED)
            value = result.legacy_result
            message = "Desired state was observed; no duplicate action was needed." if result.metrics.get("action_noop") else "Action verified from observed state." if verified else result.verification.message if result.verification else "Action could not be verified."
            if isinstance(value, ControlResult):
                value = replace(value, success=result.success, verified=verified, message=message,
                    errors=tuple(dict.fromkeys((*value.errors, *(e.message for e in result.errors)))),
                    timings_ms={**value.timings_ms, **result.metrics})
            else:
                value = ControlResult(action.action_id, action.tool_id, result.success, verified, message,
                    output=result.output or {}, errors=tuple(e.message for e in result.errors), timings_ms=result.metrics)
            result.legacy_result = value
            registry.context.record(action, value)
        def health(cid=capability_id):
            domain, verb = cid.split(".", 1)
            probe = ControlAction(domain, verb)
            with registry._lock:
                entries = tuple(registry._entries)
            for entry in entries:
                if entry.adapter.supports(probe):
                    available, reason = entry.adapter.availability(probe)
                    if available:
                        return CapabilityHealth(Availability.AVAILABLE)
            return CapabilityHealth(Availability.UNAVAILABLE, "No PC adapter is available.")
        kernel.registry.register(CapabilityDescriptor(capability_id, capability_id.replace(".", " ").title(),
            provider="pc-control", category="desktop", required_permissions=tuple(p.value for p in permissions),
            risk_level=RiskClass.HIGH if capability_id in {"browser.click", "browser.submit", "browser.upload"} else RiskClass.LOW,
            supported_resources=claims, supports_verification=True, supports_retry=True, inline=not capability_id.startswith("browser."), timeout=30),
            execute, verifier=legacy_verifier, health_check=health, permission_check=permission_check, on_completed=completed)
    registry.kernel = kernel


def register_calculation(kernel) -> None:
    """Same deterministic scalar provider for desktop and lightweight compute nodes."""
    def calculate(inputs, context):
        from ..science_engine import _evaluate_scalar
        value = _evaluate_scalar(inputs["expression"], float(inputs.get("x", 0)))
        return ExecutionResult(TaskStatus.SUCCEEDED, True, output={"value": value}, observations=["Guarded scalar evaluator returned a value."])
    def verify_calculation(result, expected, context):
        import math
        value = result.output["value"]
        wanted = expected.get("value") if isinstance(expected, dict) else expected
        valid = math.isfinite(value) and (wanted is None or math.isclose(value, float(wanted)))
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED, ("Finite numeric result checked against expected value when supplied.",))
    kernel.registry.register(CapabilityDescriptor("python.calculate", "Python calculation", category="science",
        input_schema={"type": "object", "required": ["expression"], "properties": {"expression": {"type": "string"}, "x": {"type": "number"}}},
        supports_verification=True), calculate, verifier=verify_calculation)


def register_native_adapters(kernel, desktop) -> None:
    def read_file(inputs, context):
        # Reuse desktop FileAccessManager's bounded preview implementation.
        preview = desktop.files.preview(inputs["path"])
        if not preview.available or preview.kind not in {"text", "json", "csv"}:
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT, preview.reason or "This file does not have a text preview.")
        return ExecutionResult(TaskStatus.SUCCEEDED, True, output={"path": preview.path, "content": preview.text},
            observations=["Desktop file preview returned content."], legacy_result=preview, verification_required=True)
    def verify_read(result, expected, context):
        path = Path(result.output["path"])
        text = result.output["content"]
        actual = path.read_text(encoding="utf-8", errors="replace")[:len(text)]
        return VerificationResult(VerificationStatus.VERIFIED if actual == text else VerificationStatus.FAILED,
            ("File preview content checked against disk.",))
    kernel.registry.register(CapabilityDescriptor("filesystem.read", "Read file preview", provider="desktop-files",
        required_permissions=("file_read",), input_schema={"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}},
        supports_verification=True), read_file, verifier=verify_read)

    register_calculation(kernel)

    def graph(inputs, context):
        from ..visualization import GraphRendererPlugin
        artifact = GraphRendererPlugin().render(inputs["prompt"])
        if artifact is None:
            return ExecutionResult.failure(ErrorCode.EXECUTION_FAILED, "Graph renderer returned no artifact.")
        return ExecutionResult(TaskStatus.SUCCEEDED, True, output={"kind": artifact.kind, "title": artifact.title},
            artifacts=[{"kind": artifact.kind, "title": artifact.title}], legacy_result=artifact, verification_required=True)
    def verify_graph(result, expected, context):
        from ..visualization import GraphRendererPlugin
        valid, reason = GraphRendererPlugin().validate(result.legacy_result)
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED, ("Existing graph plugin validated artifact geometry and finite data.",) if valid else (), reason)
    kernel.registry.register(CapabilityDescriptor("graph.render", "Render graph artifact", category="visualization",
        input_schema={"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"}}},
        supports_verification=True), graph, verifier=verify_graph)


def register_echo(kernel) -> None:
    def execute(inputs, context):
        context.cancellation_token.raise_if_cancelled()
        return ExecutionResult(TaskStatus.SUCCEEDED, True, output=inputs.get("value"))
    kernel.registry.register(CapabilityDescriptor("kernel.echo", "Echo", category="development", inline=True), execute)
