"""Existing ModelRouter plus an explicitly configured shared backend."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from ..agent_types import IntentType
from ..kernel import (Availability, CapabilityDescriptor, CapabilityHealth, ErrorCode, ExecutionResult,
    ResourceClaim, TaskStatus)


class ModelBudget:
    def __init__(self, calls, tokens):
        self.max_calls, self.max_tokens = calls, tokens
        self.calls = self.tokens_reserved = self.input_tokens = self.output_tokens = 0
        self._lock = threading.Lock()

    def reserve(self, input_bound, output_bound):
        with self._lock:
            if self.calls >= self.max_calls or self.tokens_reserved + input_bound + output_bound > self.max_tokens:
                raise ValueError("Workflow model budget exhausted.")
            self.calls += 1
            self.tokens_reserved += input_bound + output_bound

    def record(self, reply):
        with self._lock:
            self.input_tokens += reply.input_tokens
            self.output_tokens += reply.output_tokens

    def snapshot(self):
        with self._lock:
            return {"calls": self.calls, "tokens_reserved": self.tokens_reserved,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens}


@dataclass(frozen=True)
class ModelReply:
    text: str
    model_id: str
    input_tokens: int
    output_tokens: int


class SharedModelAdapter:
    """A callback must honor deadline/cancellation and max_output_tokens.

    No worker constructs or loads a model. Registration remains unavailable
    until the application's existing backend is explicitly supplied.
    """
    def __init__(self, kernel, router, limits):
        self.kernel, self.router, self.limits = kernel, router, limits
        self._backends = {}
        self._lock = threading.RLock()
        kernel.registry.register(CapabilityDescriptor("agent.reason", "Shared model reasoning",
            supported_resources=(ResourceClaim("LOCAL_MODEL"), ResourceClaim("GPU", exclusive=True),
                ResourceClaim("VRAM_MB", limits.vram_mb)), timeout=120, supports_cancellation=True,
            input_schema={"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string", "maxLength": 2000}}}),
            self.execute, health_check=self.health)

    def configure(self, model_id, backend):
        if not model_id or not callable(backend):
            raise ValueError("Shared model registration requires an id and callback.")
        with self._lock:
            self._backends[model_id] = backend
        self.kernel.registry.set_status("agent.reason", Availability.AVAILABLE)

    def health(self):
        with self._lock:
            return CapabilityHealth(Availability.AVAILABLE if self._backends else Availability.UNAVAILABLE,
                "" if self._backends else "No shared reasoning backend configured.")

    def execute(self, inputs, context):
        with self._lock:
            backends = dict(self._backends)
        config = context.metadata.get("model_config", {})
        requirements = context.metadata.get("model_requirements", ())
        intents = (IntentType.CODING,) if "coding" in requirements else (IntentType.IMAGE_ANALYSIS,) if "vision" in requirements else (IntentType.REASONING,)
        route = self.router.route(intents, selected_model=config.get("selected_model", ""), available_models=tuple(backends),
            context_tokens=self.limits.max_context_chars)
        candidates = (route.preferred, *route.fallbacks) if config.get("allow_fallback", True) else (route.preferred,)
        packet = context.metadata.get("packet", {})
        import json
        prompt = json.dumps({"task": inputs["prompt"], "context_data": packet}, ensure_ascii=False)
        input_bound = len(prompt.encode("utf-8"))
        output_bound = min(1024, int(config.get("max_output_tokens", 512)))
        if output_bound < 1 or input_bound > self.limits.max_context_chars:
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT, "Model context/output budget exceeded.")
        budget = context.metadata.get("model_budget")
        if not isinstance(budget, ModelBudget):
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT, "Reasoning requires a workflow model budget.")
        failures = []
        for candidate in candidates:
            backend = backends.get(candidate)
            if backend is None:
                failures.append(f"{candidate}: unavailable")
                continue
            try:
                budget.reserve(input_bound, output_bound)
            except ValueError as exc:
                return ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE, str(exc))
            started = time.perf_counter()
            try:
                context.cancellation_token.raise_if_cancelled()
                reply = backend(prompt=prompt, model_id=candidate, max_output_tokens=output_bound, context=context)
                if not isinstance(reply, ModelReply) or reply.model_id != candidate:
                    raise ValueError("Backend did not report the actual selected model.")
                if reply.input_tokens < 0 or reply.input_tokens > input_bound or reply.output_tokens < 0 or reply.output_tokens > output_bound or len(reply.text) > output_bound * 16:
                    raise ValueError("Backend violated token budget.")
                budget.record(reply)
                self.router.record(candidate, success=True, latency_ms=(time.perf_counter()-started)*1000,
                    prompt_tokens=reply.input_tokens, generated_tokens=reply.output_tokens)
                return ExecutionResult(TaskStatus.SUCCEEDED, True,
                    {"text": reply.text, "actual_model": reply.model_id, "fallback_used": candidate != route.preferred},
                    metrics={"input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens}, warnings=failures)
            except Exception as exc:
                from ..redaction import redact_text
                detail = redact_text(f"{type(exc).__name__}: {exc}")[:1500]
                failures.append(f"{candidate}: {detail}")
                self.router.record(candidate, success=False, latency_ms=(time.perf_counter()-started)*1000, error=detail)
        return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE, "No configured reasoning model completed.", detail="; ".join(failures))
