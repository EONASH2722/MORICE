"""Rendered browser observations extend Phase 3 with measurable layout evidence."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..kernel import CapabilityDescriptor, ExecutionResult, ResourceClaim, TaskStatus, VerificationResult, VerificationStatus
from .contracts import ActionBinding, ActionMethod, Observation
from .verification import normalized_url


def layout_verification(desired, state):
    if state.get("loaded") is not True or normalized_url(state.get("url", "")) != normalized_url(desired["url"]):
        return VerificationResult(VerificationStatus.FAILED, message="The requested running page was not inspected.")
    if not state.get("screenshot_sha256") or state.get("screenshot_bytes", 0) <= 0:
        return VerificationResult(VerificationStatus.INCONCLUSIVE, message="Actual rendered screenshot is unavailable.")
    if desired.get("viewport") and list(desired["viewport"]) != list(state.get("viewport", ())):
        return VerificationResult(VerificationStatus.INCONCLUSIVE, message="The requested responsive viewport was not actually rendered.")
    boxes = {v["selector"]: v for v in state.get("regions", ())}
    for check in desired.get("checks", ()):
        kind = check.get("kind")
        if kind == "visible":
            valid = boxes.get(check["selector"], {}).get("visible") is True
        elif kind == "no_overlap":
            a, b = boxes.get(check["a"], {}), boxes.get(check["b"], {})
            valid = a.get("visible") and b.get("visible") and (a["x"] + a["width"] <= b["x"] + 1 or b["x"] + b["width"] <= a["x"] + 1 or a["y"] + a["height"] <= b["y"] + 1 or b["y"] + b["height"] <= a["y"] + 1)
        elif kind == "no_horizontal_overflow":
            valid = state.get("scroll_width", float("inf")) <= state["viewport"][0] + 1
        elif kind == "readable_text":
            box = boxes.get(check["selector"], {})
            valid = box.get("visible") and box.get("font_size", 0) >= check.get("minimum_px", 12) and bool(box.get("text"))
        else:
            return VerificationResult(VerificationStatus.INCONCLUSIVE, message="Unsupported rendered layout requirement.")
        if not valid:
            return VerificationResult(VerificationStatus.FAILED, message=f"Rendered requirement failed: {kind}.")
    if state.get("console_errors"):
        return VerificationResult(VerificationStatus.FAILED, message="The running page reported console errors.")
    return VerificationResult(VerificationStatus.VERIFIED, ("Actual screenshot and DOM geometry checked against declared layout requirements.",))


def register_browser_inspection(kernel, actions, browser):
    kernel.registry.register(CapabilityDescriptor("browser.inspect", "Inspect actual rendered browser output",
        required_permissions=("browser_control", "screen_access", "file_write"),
        supported_resources=(ResourceClaim("BROWSER_SESSION", exclusive=True), ResourceClaim("FOREGROUND_UI", exclusive=True)),
        supports_verification=True, supports_cancellation=True, input_schema={"type": "object", "required": ["url", "screenshot_path"], "properties": {
            "url": {"type": "string"}, "screenshot_path": {"type": "string"}, "regions": {"type": "array"}, "checks": {"type": "array"}, "viewport": {"type": "array"}}}),
        lambda inputs, context: ExecutionResult(TaskStatus.SUCCEEDED, True, output={"inspection_requested": True}),
        verifier=lambda *args: VerificationResult(VerificationStatus.INCONCLUSIVE, message="Actual rendered inspection is required."))
    def observe(spec, context, result=None, before=None):
        state = browser.perform("inspect", "", spec.desired_state, context)
        path = Path(state["screenshot_path"])
        data = path.read_bytes()
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        state.update(screenshot_bytes=len(data), screenshot_sha256=hashlib.sha256(data).hexdigest())
        if result is not None:
            result.output = state
            result.artifacts = [{"path": str(path), "size": len(data), "sha256": state["screenshot_sha256"]}]
        return Observation(spec.action_id, "qt.browser.rendered_layout", state,
            ("Read actual screenshot bytes and observed rendered DOM rectangles.",), timestamp=state["timestamp"])
    actions.register("browser.inspect", ActionBinding(ActionMethod.BROWSER_DOM, lambda inputs, expected: dict(inputs),
        observe, lambda spec, observed, before: layout_verification(spec.desired_state, observed.state)))
