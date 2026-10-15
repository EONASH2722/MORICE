"""Optional semantic hypotheses from existing Live Vision; no new model or success flag."""
from __future__ import annotations

import hashlib
import io
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from ..kernel import Availability, CapabilityDescriptor, CapabilityHealth, ErrorCode, ExecutionResult, ResourceClaim, TaskStatus, VerificationResult, VerificationStatus


class ScreenVisionObserver:
    def __init__(self, kernel, desktop, live_vision):
        self.kernel, self.desktop, self.live_vision = kernel, desktop, live_vision
        self._cache = OrderedDict()

    def execute(self, inputs, context):
        from PIL import Image
        from ..live_vision import VisionFrame
        target = self.desktop.windows.active_window()
        capture = self.kernel.dispatch("screenshot.capture", {"target": "", "arguments": {"mode": "full"}}, context)
        if not capture.success or target != self.desktop.windows.active_window():
            return ExecutionResult.failure(ErrorCode.VERIFICATION_FAILED, "Screenshot target changed or capture failed.")
        path = Path(capture.output["path"])
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        key = (digest, str(inputs.get("prompt", "Describe the active screen.")), target)
        cached = self._cache.get(key)
        if cached is not None:
            return ExecutionResult(TaskStatus.SUCCEEDED, True, output={**cached, "cached": True})
        jpeg = io.BytesIO()
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            image.convert("RGB").save(jpeg, "JPEG", quality=85)
        frame = VisionFrame(digest, datetime.now(timezone.utc), time.monotonic_ns(), width, height, jpeg.getvalue(), camera_id=f"screen:{target}")
        class CancellationView:
            def is_set(self):
                return context.cancellation_token.cancelled or time.monotonic() >= context.deadline
            def wait(self, timeout=0):
                context.cancellation_token.wait(min(timeout, max(0, context.deadline - time.monotonic())))
                return self.is_set()
        value = self.live_vision.provider.analyze(frame, key[1], cancel_event=CancellationView(), request_id=context.task_id)
        if not value.success or value.frame_id != frame.frame_id or value.frame_timestamp != frame.timestamp or target != self.desktop.windows.active_window():
            return ExecutionResult.failure(ErrorCode.VERIFICATION_FAILED, "Semantic result does not match the captured screen frame.")
        output = {"frame_id": digest, "target_handle": target, "captured_at": frame.timestamp,
            "semantic_hypothesis": value.summary, "extracted_text": value.extracted_text,
            "uncertainty": value.uncertainty, "usable_for_action_verification": False, "cached": False}
        self._cache[key] = output
        while len(self._cache) > 8:
            self._cache.popitem(last=False)
        return ExecutionResult(TaskStatus.SUCCEEDED, True, output=output,
            evidence=["Existing vision provider analyzed the actual matching screen frame; semantic claims require independent checks."])


def register_screen_vision(kernel, desktop, live_vision):
    observer = ScreenVisionObserver(kernel, desktop, live_vision)
    def health():
        status = live_vision.provider.status()
        return CapabilityHealth(Availability.AVAILABLE if status.available else Availability.UNAVAILABLE,
            "" if status.available else "Existing semantic vision provider has no configured model/projector.")
    kernel.registry.register(CapabilityDescriptor("vision.screen_observe", "Observe semantic screen hypotheses",
        required_permissions=("screen_access", "vision"), supported_resources=(ResourceClaim("GPU", exclusive=True),),
        supports_cancellation=True, supports_verification=True), observer.execute,
        health_check=health, verifier=lambda result, expected, ctx: VerificationResult(VerificationStatus.VERIFIED,
            tuple(result.evidence), "Provider output is frame-associated; screen-state claims remain unverified."))
    return observer
