"""Small, dependency-free primitives for MORICE's real-time intelligence path.

This module deliberately owns no UI objects, audio devices, model processes, or
filesystem watchers. It provides the coordination contracts those systems can
share: request epochs, latency marks, model-tier decisions, semantic speech
chunks, bounded memory ranking, and compact event-driven awareness.
"""

from __future__ import annotations

import html
import math
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Callable, Iterable, Mapping, Sequence


class LatencyStage(StrEnum):
    """Canonical milestones for a spoken MORICE request."""

    SPEECH_DETECTED = "t0_speech_detected"
    STT_FIRST_PARTIAL = "t1_stt_first_partial"
    STT_FINAL = "t2_stt_final"
    INTENT_IDENTIFIED = "t3_intent_identified"
    CONTEXT_ASSEMBLED = "t4_context_assembled"
    INFERENCE_BEGAN = "t5_inference_began"
    FIRST_LLM_TOKEN = "t6_first_llm_token"
    FIRST_CHUNK_READY = "t7_first_chunk_ready"
    TTS_CHUNK_RECEIVED = "t8_tts_chunk_received"
    FIRST_AUDIO_GENERATED = "t9_first_audio_generated"
    FIRST_AUDIO_AUDIBLE = "t10_first_audio_audible"
    GENERATION_COMPLETE = "t11_generation_complete"
    SPEECH_COMPLETE = "t12_speech_complete"

    # Compact aliases keep instrumentation call sites aligned with latency
    # diagrams while retaining descriptive names in exported diagnostics.
    T0 = SPEECH_DETECTED
    T1 = STT_FIRST_PARTIAL
    T2 = STT_FINAL
    T3 = INTENT_IDENTIFIED
    T4 = CONTEXT_ASSEMBLED
    T5 = INFERENCE_BEGAN
    T6 = FIRST_LLM_TOKEN
    T7 = FIRST_CHUNK_READY
    T8 = TTS_CHUNK_RECEIVED
    T9 = FIRST_AUDIO_GENERATED
    T10 = FIRST_AUDIO_AUDIBLE
    T11 = GENERATION_COMPLETE
    T12 = SPEECH_COMPLETE


_STAGE_INDEX = {stage: index for index, stage in enumerate(LatencyStage)}
_LATENCY_INTERVALS: dict[str, tuple[LatencyStage, LatencyStage]] = {
    "sttFirstPartialMs": (
        LatencyStage.SPEECH_DETECTED,
        LatencyStage.STT_FIRST_PARTIAL,
    ),
    "sttFinalMs": (LatencyStage.SPEECH_DETECTED, LatencyStage.STT_FINAL),
    "intentMs": (LatencyStage.STT_FINAL, LatencyStage.INTENT_IDENTIFIED),
    "contextMs": (
        LatencyStage.INTENT_IDENTIFIED,
        LatencyStage.CONTEXT_ASSEMBLED,
    ),
    "inferenceQueueMs": (
        LatencyStage.CONTEXT_ASSEMBLED,
        LatencyStage.INFERENCE_BEGAN,
    ),
    "timeToFirstTokenMs": (
        LatencyStage.INFERENCE_BEGAN,
        LatencyStage.FIRST_LLM_TOKEN,
    ),
    "timeToFirstChunkMs": (
        LatencyStage.INFERENCE_BEGAN,
        LatencyStage.FIRST_CHUNK_READY,
    ),
    "ttsFirstAudioMs": (
        LatencyStage.TTS_CHUNK_RECEIVED,
        LatencyStage.FIRST_AUDIO_GENERATED,
    ),
    "audioQueueMs": (
        LatencyStage.FIRST_AUDIO_GENERATED,
        LatencyStage.FIRST_AUDIO_AUDIBLE,
    ),
    "generationMs": (
        LatencyStage.INFERENCE_BEGAN,
        LatencyStage.GENERATION_COMPLETE,
    ),
    "responseToAudibleMs": (
        LatencyStage.STT_FINAL,
        LatencyStage.FIRST_AUDIO_AUDIBLE,
    ),
    "totalResponseMs": (
        LatencyStage.SPEECH_DETECTED,
        LatencyStage.SPEECH_COMPLETE,
    ),
}

_EVENT_INTERVALS: dict[str, tuple[str, str]] = {
    "uiDispatchMs": ("ui_request_received", "text_submitted"),
    "textSubmitToRouteMs": ("text_submitted", "route_completed"),
    "requestQueueMs": ("route_completed", "worker_started"),
    "contextAssemblyMs": ("context_started", "context_completed"),
    "modelSubmitMs": ("context_completed", "model_request_submitted"),
    "modelConnectMs": ("model_request_submitted", "model_response_connected"),
    "backendFirstEventMs": ("model_request_submitted", "backend_first_event"),
    "modelFirstUsefulTokenMs": (
        "model_request_submitted",
        "model_first_useful_token",
    ),
    "modelTokenToUiQueueMs": ("model_first_useful_token", "ui_delta_queued"),
    "uiRenderMs": ("ui_delta_queued", "ui_delta_displayed"),
    "modelTokenToSpeakableMs": (
        "model_first_useful_token",
        "first_speakable_chunk",
    ),
    "visionAnalysisMs": ("vision_started", "vision_completed"),
    "textSubmitToFirstVisibleMs": ("text_submitted", "first_visible_token"),
    "speechEndToTranscriptMs": ("speech_end", "transcript_final"),
    "speechEndToFirstModelTokenMs": ("speech_end", "first_model_token"),
    "speechEndToFirstAudibleMs": ("speech_end", "first_audio_audible"),
    "toolExecutionMs": ("tool_execution_started", "tool_execution_finished"),
    "fastCommandTotalMs": ("text_submitted", "fast_response_visible"),
    "ttsSubmissionToFirstAudioMs": ("tts_submitted", "first_audio_generated"),
    "endToEndMs": ("input_received", "response_complete"),
}


def _coerce_stage(value: LatencyStage | str) -> LatencyStage:
    if isinstance(value, LatencyStage):
        return value
    return LatencyStage(str(value))


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    """Return a small JSON-friendly representation for diagnostics."""

    if depth >= 3:
        return str(value)[:500]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value.replace("\x00", "")[:2_000]
    if isinstance(value, Mapping):
        return {
            str(key)[:120]: _compact_value(item, depth=depth + 1)
            for key, item in list(value.items())[:32]
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_compact_value(item, depth=depth + 1) for item in list(value)[:50]]
    return str(value)[:2_000]


class LatencyTrace:
    """Thread-safe, first-write-wins latency marks for one request."""

    def __init__(
        self,
        request_id: str,
        *,
        created_monotonic_ns: int | None = None,
        created_at: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ):
        clean_id = str(request_id or "").strip()
        if not clean_id:
            raise ValueError("A latency trace requires a request id.")
        self.request_id = clean_id
        self.created_monotonic_ns = (
            time.perf_counter_ns()
            if created_monotonic_ns is None
            else int(created_monotonic_ns)
        )
        if self.created_monotonic_ns < 0:
            raise ValueError("created_monotonic_ns cannot be negative.")
        self.created_at = time.time() if created_at is None else float(created_at)
        self._marks: dict[LatencyStage, int] = {}
        self._events: dict[str, int] = {}
        self._metadata: dict[str, Any] = dict(
            _compact_value(dict(metadata or {}))
        )
        self._counters: dict[str, int] = {}
        self._lock = threading.RLock()

    def mark(
        self,
        stage: LatencyStage | str,
        *,
        at_ns: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        """Record a stage once while rejecting contradictory timestamps."""

        clean_stage = _coerce_stage(stage)
        timestamp = time.perf_counter_ns() if at_ns is None else int(at_ns)
        if timestamp < self.created_monotonic_ns:
            return False
        stage_index = _STAGE_INDEX[clean_stage]
        with self._lock:
            if clean_stage in self._marks:
                return False
            for existing_stage, existing_at in self._marks.items():
                # Generation and audio synthesis overlap by design. T11 may
                # legitimately precede T8-T10 for a short completed answer.
                parallel_generation_audio = (
                    clean_stage == LatencyStage.GENERATION_COMPLETE
                    and existing_stage
                    in {
                        LatencyStage.TTS_CHUNK_RECEIVED,
                        LatencyStage.FIRST_AUDIO_GENERATED,
                        LatencyStage.FIRST_AUDIO_AUDIBLE,
                    }
                ) or (
                    existing_stage == LatencyStage.GENERATION_COMPLETE
                    and clean_stage
                    in {
                        LatencyStage.TTS_CHUNK_RECEIVED,
                        LatencyStage.FIRST_AUDIO_GENERATED,
                        LatencyStage.FIRST_AUDIO_AUDIBLE,
                    }
                )
                if parallel_generation_audio:
                    continue
                existing_index = _STAGE_INDEX[existing_stage]
                if existing_index < stage_index and existing_at > timestamp:
                    return False
                if existing_index > stage_index and existing_at < timestamp:
                    return False
            self._marks[clean_stage] = timestamp
            if metadata:
                stage_metadata = self._metadata.setdefault("stages", {})
                stage_metadata[clean_stage.value] = _compact_value(dict(metadata))
            return True

    def annotate(self, **metadata: Any) -> None:
        with self._lock:
            self._metadata.update(_compact_value(metadata))

    def mark_event(
        self,
        name: str,
        *,
        at_ns: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        """Record a named pipeline milestone without imposing speech-stage order.

        Typed, tool, model, STT, and TTS requests do not all share the same
        topology. Named events let each path expose its real milestones while
        the canonical T0-T12 speech trace remains backwards compatible.
        """

        clean_name = re.sub(r"[^a-z0-9_.-]+", "_", str(name or "").casefold()).strip(
            "_.-"
        )
        if not clean_name:
            raise ValueError("Event name cannot be empty.")
        timestamp = time.perf_counter_ns() if at_ns is None else int(at_ns)
        if timestamp < self.created_monotonic_ns:
            return False
        with self._lock:
            if clean_name in self._events:
                return False
            self._events[clean_name] = timestamp
            if metadata:
                event_metadata = self._metadata.setdefault("events", {})
                event_metadata[clean_name] = _compact_value(dict(metadata))
            return True

    def event_timestamp_ns(self, name: str) -> int | None:
        clean_name = str(name or "").strip().casefold()
        with self._lock:
            return self._events.get(clean_name)

    def event_duration_ms(self, start: str, end: str) -> float | None:
        with self._lock:
            start_ns = self._events.get(str(start or "").strip().casefold())
            end_ns = self._events.get(str(end or "").strip().casefold())
        if start_ns is None or end_ns is None or end_ns < start_ns:
            return None
        return (end_ns - start_ns) / 1_000_000.0

    def increment(self, name: str, amount: int = 1) -> int:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("Counter name cannot be empty.")
        with self._lock:
            self._counters[clean_name] = self._counters.get(clean_name, 0) + int(
                amount
            )
            return self._counters[clean_name]

    def set_counter(self, name: str, value: int) -> None:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("Counter name cannot be empty.")
        with self._lock:
            self._counters[clean_name] = max(0, int(value))

    def timestamp_ns(self, stage: LatencyStage | str) -> int | None:
        with self._lock:
            return self._marks.get(_coerce_stage(stage))

    def has(self, stage: LatencyStage | str) -> bool:
        with self._lock:
            return _coerce_stage(stage) in self._marks

    def duration_ms(
        self,
        start: LatencyStage | str,
        end: LatencyStage | str,
    ) -> float | None:
        start_stage = _coerce_stage(start)
        end_stage = _coerce_stage(end)
        with self._lock:
            start_ns = self._marks.get(start_stage)
            end_ns = self._marks.get(end_stage)
        if start_ns is None or end_ns is None or end_ns < start_ns:
            return None
        return (end_ns - start_ns) / 1_000_000.0

    def intervals(self) -> dict[str, float]:
        values: dict[str, float] = {}
        for name, (start, end) in _LATENCY_INTERVALS.items():
            duration = self.duration_ms(start, end)
            if duration is not None:
                values[name] = duration
        for name, (start, end) in _EVENT_INTERVALS.items():
            duration = self.event_duration_ms(start, end)
            if duration is not None:
                values[name] = duration
        return values

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            marks = dict(self._marks)
            events = dict(self._events)
            metadata = _compact_value(self._metadata)
            counters = dict(self._counters)
        return {
            "requestId": self.request_id,
            "createdAt": self.created_at,
            "stages": {
                stage.value: (timestamp - self.created_monotonic_ns) / 1_000_000.0
                for stage, timestamp in sorted(
                    marks.items(), key=lambda item: _STAGE_INDEX[item[0]]
                )
            },
            "events": {
                name: (timestamp - self.created_monotonic_ns) / 1_000_000.0
                for name, timestamp in sorted(events.items(), key=lambda item: item[1])
            },
            "intervals": self.intervals(),
            "counters": counters,
            "metadata": metadata,
            "generationComplete": LatencyStage.GENERATION_COMPLETE in marks,
            "speechComplete": LatencyStage.SPEECH_COMPLETE in marks,
        }


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * max(0.0, min(1.0, percentile))
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


class LatencyRegistry:
    """Bounded registry of recent request traces with percentile summaries."""

    def __init__(self, max_traces: int = 200):
        self.max_traces = max(1, int(max_traces))
        self._traces: deque[LatencyTrace] = deque()
        self._by_id: dict[str, LatencyTrace] = {}
        self._lock = threading.RLock()

    def begin(
        self,
        request_id: str | None = None,
        *,
        created_monotonic_ns: int | None = None,
        created_at: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LatencyTrace:
        trace = LatencyTrace(
            request_id or uuid.uuid4().hex,
            created_monotonic_ns=created_monotonic_ns,
            created_at=created_at,
            metadata=metadata,
        )
        with self._lock:
            if trace.request_id in self._by_id:
                raise ValueError(f"Duplicate request id: {trace.request_id}")
            if len(self._traces) >= self.max_traces:
                evicted = self._traces.popleft()
                self._by_id.pop(evicted.request_id, None)
            self._traces.append(trace)
            self._by_id[trace.request_id] = trace
        return trace

    def get(self, request_id: str) -> LatencyTrace | None:
        with self._lock:
            return self._by_id.get(str(request_id))

    def recent(self, limit: int | None = None) -> tuple[LatencyTrace, ...]:
        with self._lock:
            values = tuple(reversed(self._traces))
        if limit is None:
            return values
        return values[: max(0, int(limit))]

    def metric(
        self,
        start: LatencyStage | str,
        end: LatencyStage | str,
    ) -> dict[str, float | int]:
        values = [
            duration
            for trace in self.recent()
            if (duration := trace.duration_ms(start, end)) is not None
        ]
        return {
            "count": len(values),
            "p50Ms": _percentile(values, 0.50),
            "p95Ms": _percentile(values, 0.95),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "traceCount": len(self.recent()),
            "metrics": {
                name: self.metric(start, end)
                for name, (start, end) in _LATENCY_INTERVALS.items()
            }
            | {
                name: self.event_metric(start, end)
                for name, (start, end) in _EVENT_INTERVALS.items()
            },
        }

    def event_metric(self, start: str, end: str) -> dict[str, float | int]:
        values = [
            duration
            for trace in self.recent()
            if (duration := trace.event_duration_ms(start, end)) is not None
        ]
        return {
            "count": len(values),
            "p50Ms": _percentile(values, 0.50),
            "p95Ms": _percentile(values, 0.95),
        }


class ModelTier(StrEnum):
    REFLEX = "reflex"
    GENERAL = "general"
    DEEP = "deep"


def _coerce_tier(value: ModelTier | str) -> ModelTier:
    if isinstance(value, ModelTier):
        return value
    return ModelTier(str(value).strip().casefold())


@dataclass(frozen=True)
class RouteDecision:
    tier: ModelTier
    model_id: str
    reason: str
    host_action: bool = False
    safe_to_prefetch: bool = False
    requires_final: bool = False
    allow_escalation: bool = True
    context_tokens: int = 8_192
    max_output_tokens: int = 1_024
    explicit_override: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["tier"] = self.tier.value
        return value


class TieredModelRouter:
    """Fast deterministic routing without loading or invoking any model."""

    _ACKNOWLEDGEMENTS = {
        "ok",
        "okay",
        "thanks",
        "thank you",
        "got it",
        "understood",
        "yes",
        "no",
        "stop",
        "cancel",
    }
    _COMMAND_PATTERN = re.compile(
        r"^(?:/"
        r"(?:open|launch|folder|site|website|system|status|diagnostics|diag|"
        r"screenshot|play|pause|next|previous|mute|volume-up|volume-down|"
        r"close-app|find)"
        r"\b|"
        r"(?:open|launch|start|show|check|list|find|take|play|pause|mute|"
        r"close|kill|stop|delete|remove|shut\s*down|restart|turn\s+off|"
        r"volume\s+(?:up|down))\b)"
    )
    _READ_ONLY_PATTERN = re.compile(
        r"\b(?:show|check|list|find|inspect|status|usage|using|what|which|how much)\b"
    )
    _DESTRUCTIVE_PATTERN = re.compile(
        r"\b(?:delete|remove|erase|wipe|kill|terminate|close|shutdown|"
        r"shut\s+down|restart|format|uninstall|turn\s+off|disable)\b"
    )
    _MATH_PATTERN = re.compile(
        r"(?:^|\b)\d+(?:\.\d+)?\s*(?:%\s+of|[+\-*/x×÷])\s*"
        r"\d+(?:\.\d+)?(?:\b|$)",
        re.IGNORECASE,
    )
    _DEEP_PATTERN = re.compile(
        r"\b(?:"
        r"architecture|architectural|deadlock|race condition|repository audit|"
        r"audit (?:this|the) (?:repo|repository|codebase)|formal proof|"
        r"complex mathematics|derive|root cause|performance analysis|"
        r"security audit|large refactor|multiprocessing|distributed system|"
        r"research deeply|deep research|50[,\s]?000"
        r")\b",
        re.IGNORECASE,
    )
    _DEEP_INTENTS = {
        "architecture",
        "complex_reasoning",
        "deep_reasoning",
        "debugging",
        "repository_audit",
        "research",
    }
    _REFLEX_INTENTS = {
        "acknowledgement",
        "calculator",
        "command",
        "desktop_control",
        "intent_classification",
        "system_status",
    }

    def __init__(
        self,
        models: Mapping[ModelTier | str, str] | None = None,
        *,
        budgets: Mapping[ModelTier | str, tuple[int, int]] | None = None,
    ):
        configured: dict[ModelTier, str] = {}
        for key, value in (models or {}).items():
            model_id = str(value or "").strip()
            if model_id:
                configured[_coerce_tier(key)] = model_id
        self._models = configured
        self._budgets: dict[ModelTier, tuple[int, int]] = {
            ModelTier.REFLEX: (2_048, 192),
            ModelTier.GENERAL: (8_192, 1_024),
            ModelTier.DEEP: (16_384, 4_096),
        }
        for key, value in (budgets or {}).items():
            context, output = value
            self._budgets[_coerce_tier(key)] = (
                max(512, int(context)),
                max(32, int(output)),
            )

    @property
    def models(self) -> dict[ModelTier, str]:
        return dict(self._models)

    def route(
        self,
        text: str,
        *,
        intents: Iterable[object] = (),
        partial: bool = False,
        destructive: bool = False,
        override_model: str = "",
        override_tier: ModelTier | str | None = None,
    ) -> RouteDecision:
        clean = " ".join(str(text or "").strip().split())
        lowered = clean.casefold()
        intent_values = {
            str(getattr(intent, "value", intent)).strip().casefold()
            for intent in intents
            if str(getattr(intent, "value", intent)).strip()
        }
        command = bool(self._COMMAND_PATTERN.search(lowered))
        acknowledgement = lowered in self._ACKNOWLEDGEMENTS
        simple_math = bool(self._MATH_PATTERN.search(lowered))
        destructive_intent = destructive or bool(
            self._DESTRUCTIVE_PATTERN.search(lowered)
        )

        if override_tier is not None:
            tier = _coerce_tier(override_tier)
            reason = "Explicit model tier override."
        elif self._DEEP_PATTERN.search(lowered) or intent_values & self._DEEP_INTENTS:
            tier = ModelTier.DEEP
            reason = "Complex reasoning profile."
        elif command or acknowledgement or simple_math or intent_values & self._REFLEX_INTENTS:
            tier = ModelTier.REFLEX
            if command:
                reason = "Structured command profile."
            elif simple_math:
                reason = "Deterministic calculation profile."
            else:
                reason = "Short acknowledgement profile."
        else:
            tier = ModelTier.GENERAL
            reason = "General conversation profile."

        requires_final = bool(partial and (command or destructive_intent))
        safe_to_prefetch = bool(
            partial
            and command
            and not destructive_intent
            and self._READ_ONLY_PATTERN.search(lowered)
        )
        host_action = bool((command or simple_math) and not partial)
        if destructive_intent and partial:
            host_action = False
            safe_to_prefetch = False
            reason += " Destructive partial intent is held until final transcription."
        elif command and partial:
            host_action = False
            reason += " Partial command is classified but not executed."

        explicit_model = str(override_model or "").strip()
        if explicit_model:
            model_id = explicit_model
            explicit_override = True
            reason = "Explicit model override. " + reason
        else:
            model_id, fallback_tier = self._model_for(tier)
            explicit_override = False
            if fallback_tier is not None and fallback_tier != tier:
                reason += f" Using configured {fallback_tier.value} model fallback."

        context_tokens, max_output_tokens = self._budgets[tier]
        return RouteDecision(
            tier=tier,
            model_id=model_id,
            reason=reason,
            host_action=host_action,
            safe_to_prefetch=safe_to_prefetch,
            requires_final=requires_final,
            allow_escalation=not host_action and tier != ModelTier.DEEP,
            context_tokens=context_tokens,
            max_output_tokens=max_output_tokens,
            explicit_override=explicit_override,
        )

    def _model_for(self, tier: ModelTier) -> tuple[str, ModelTier | None]:
        if tier in self._models:
            return self._models[tier], tier
        fallback_order = {
            ModelTier.REFLEX: (ModelTier.GENERAL, ModelTier.DEEP),
            ModelTier.GENERAL: (ModelTier.DEEP, ModelTier.REFLEX),
            ModelTier.DEEP: (ModelTier.GENERAL, ModelTier.REFLEX),
        }[tier]
        for fallback in fallback_order:
            if fallback in self._models:
                return self._models[fallback], fallback
        return "", None


class RequestCancelledError(RuntimeError):
    pass


class CancellationToken:
    """Cancellation state tied to a monotonically increasing request epoch."""

    def __init__(self, epoch: int):
        self.epoch = max(1, int(epoch))
        self._event = threading.Event()
        self._reason = ""
        self._lock = threading.Lock()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def event(self) -> threading.Event:
        """Cancellation signal consumed by the streaming model adapters."""

        return self._event

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    def cancel(self, reason: str = "cancelled") -> bool:
        with self._lock:
            if self._event.is_set():
                return False
            self._reason = str(reason or "cancelled")[:500]
            self._event.set()
            return True

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise RequestCancelledError(self.reason or "Request cancelled.")

    def matches(self, epoch: int) -> bool:
        return self.epoch == int(epoch) and not self.cancelled


@dataclass(frozen=True)
class SemanticChunk:
    display_text: str
    spoken_text: str


class SemanticChunker:
    """Incrementally forms natural speech chunks while retaining display text."""

    _ABBREVIATIONS = {
        "a.m.",
        "approx.",
        "dr.",
        "e.g.",
        "etc.",
        "i.e.",
        "jr.",
        "mr.",
        "mrs.",
        "ms.",
        "p.m.",
        "prof.",
        "sr.",
        "st.",
        "vs.",
    }
    _FENCE = chr(96) * 3
    _FENCED_CODE = re.compile(r"\x60{3}[\s\S]*?(?:\x60{3}|$)")
    _INLINE_CODE = re.compile(r"\x60([^\x60\n]+)\x60")
    _MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\((?:[^()]|\([^)]*\))*\)")
    _MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((?:[^()]|\([^)]*\))*\)")
    _BARE_URL = re.compile(
        r"\b(?:https?://|www\.)[^\s<>()]+",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        min_clause_chars: int = 48,
        soft_clause_chars: int = 120,
        max_chunk_chars: int = 320,
        first_chunk_chars: int = 88,
        speak_code: bool = False,
    ):
        self.min_clause_chars = max(12, int(min_clause_chars))
        self.soft_clause_chars = max(
            self.min_clause_chars, int(soft_clause_chars)
        )
        self.max_chunk_chars = max(
            self.soft_clause_chars, int(max_chunk_chars)
        )
        self.first_chunk_chars = max(
            self.min_clause_chars,
            min(self.max_chunk_chars, int(first_chunk_chars)),
        )
        self.speak_code = bool(speak_code)
        self._buffer = ""
        self._fence_open = False
        self._chunks_emitted = 0

    @property
    def pending_display(self) -> str:
        return self._buffer

    def feed(self, delta: str) -> tuple[SemanticChunk, ...]:
        value = str(delta or "")
        if not value:
            return ()
        self._buffer += value
        chunks: list[SemanticChunk] = []
        while True:
            boundary = self._find_boundary()
            if boundary is None:
                break
            segment = self._buffer[:boundary]
            self._buffer = self._buffer[boundary:].lstrip()
            chunk = self._make_chunk(segment)
            if chunk is not None:
                chunks.append(chunk)
                self._chunks_emitted += 1
        return tuple(chunks)

    def flush(self) -> tuple[SemanticChunk, ...]:
        if not self._buffer.strip():
            self._buffer = ""
            self._fence_open = False
            return ()
        segment = self._buffer
        self._buffer = ""
        chunk = self._make_chunk(segment)
        self._fence_open = False
        if chunk is not None:
            self._chunks_emitted += 1
        return (chunk,) if chunk is not None else ()

    def reset(self) -> None:
        self._buffer = ""
        self._fence_open = False
        self._chunks_emitted = 0

    def _make_chunk(self, segment: str) -> SemanticChunk | None:
        self._advance_fence_state(segment)
        display = segment.strip()
        if not display:
            return None
        return SemanticChunk(display, self.to_spoken(display, speak_code=self.speak_code))

    def _advance_fence_state(self, segment: str) -> None:
        if segment.count(self._FENCE) % 2:
            self._fence_open = not self._fence_open

    def _find_boundary(self) -> int | None:
        text = self._buffer
        if not text:
            return None
        fence_open = self._fence_open
        link_depth = 0
        index = 0
        while index < len(text):
            if text.startswith(self._FENCE, index):
                fence_open = not fence_open
                index += len(self._FENCE)
                if (
                    not fence_open
                    and index >= self.min_clause_chars
                    and (index == len(text) or text[index].isspace())
                ):
                    return index
                continue
            character = text[index]
            if not fence_open:
                if text.startswith("](", index):
                    link_depth = 1
                    index += 2
                    continue
                if link_depth:
                    if character == "(":
                        link_depth += 1
                    elif character == ")":
                        link_depth -= 1
                    index += 1
                    continue
                if character == "\n":
                    line_length = index - text.rfind("\n", 0, index)
                    if (
                        (index + 1 < len(text) and text[index + 1] == "\n")
                        or line_length >= self.min_clause_chars
                    ):
                        return index + 1
                if character in ".!?":
                    if character == "." and self._period_is_internal(text, index):
                        index += 1
                        continue
                    end = index + 1
                    while end < len(text) and text[end] in ".!?":
                        end += 1
                    if end == len(text) or text[end].isspace():
                        return end
                if (
                    character in ";:"
                    and index >= self.min_clause_chars
                    and (index + 1 == len(text) or text[index + 1].isspace())
                ):
                    return index + 1
                if (
                    character == ","
                    and index >= self.soft_clause_chars
                    and (index + 1 == len(text) or text[index + 1].isspace())
                ):
                    return index + 1
                if (
                    self._chunks_emitted == 0
                    and index + 1 >= self.first_chunk_chars
                    and character.isspace()
                ):
                    # The first audible clause has a tighter latency budget than
                    # later speech. Split at a word boundary so speech can start
                    # while generation continues, without inventing filler.
                    return index + 1
                if index + 1 >= self.max_chunk_chars and character.isspace():
                    return index + 1
            index += 1

        if not fence_open and len(text) > self.max_chunk_chars:
            split = text.rfind(" ", 0, self.max_chunk_chars + 1)
            if split >= self.min_clause_chars:
                return split + 1
        return None

    @classmethod
    def _period_is_internal(cls, text: str, index: int) -> bool:
        # A numeric period at the current stream boundary may become a decimal
        # when the next model delta arrives (for example ``2.`` + ``1``).
        if index > 0 and index + 1 == len(text) and text[index - 1].isdigit():
            return True
        if (
            index > 0
            and index + 1 < len(text)
            and text[index - 1].isdigit()
            and text[index + 1].isdigit()
        ):
            return True
        prefix = text[: index + 1].casefold()
        match = re.search(r"([a-z](?:[a-z.]*)\.)$", prefix)
        token = match.group(1) if match else ""
        if token in cls._ABBREVIATIONS:
            return True
        if re.fullmatch(r"(?:[a-z]\.){2,}", token) or re.fullmatch(
            r"[a-z]\.", token
        ):
            return True
        token_start = max(
            prefix.rfind(" "),
            prefix.rfind("\n"),
            prefix.rfind("\t"),
            prefix.rfind("("),
        ) + 1
        surrounding = text[token_start:]
        if surrounding.casefold().startswith(("http://", "https://", "www.")):
            next_space = re.search(r"\s", surrounding)
            token_end = (
                token_start + next_space.start()
                if next_space
                else len(text)
            )
            return index < token_end - 1
        return False

    @classmethod
    def to_spoken(cls, text: str, *, speak_code: bool = False) -> str:
        value = str(text or "")
        if speak_code:
            value = value.replace(cls._FENCE, " ").replace(chr(96), "")
        else:
            value = cls._FENCED_CODE.sub(" Code block omitted. ", value)
            value = cls._INLINE_CODE.sub(r"\1", value)
        value = cls._MARKDOWN_IMAGE.sub(
            lambda match: f" Image: {match.group(1) or 'attached image'}. ",
            value,
        )
        value = cls._MARKDOWN_LINK.sub(lambda match: match.group(1), value)
        value = cls._BARE_URL.sub("a link", value)
        value = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", value)
        value = re.sub(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+", "", value)
        value = re.sub(
            r"(\*\*|__|~~)(?=\S)(.+?)(?<=\S)\1",
            r"\2",
            value,
        )
        value = re.sub(
            r"(?<!\w)([*_])(?=\S)(.+?)(?<=\S)\1(?!\w)",
            r"\2",
            value,
        )
        value = html.unescape(value)
        value = re.sub(r"\s+", " ", value).strip()
        return value


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


_MEMORY_TOKEN = re.compile(r"[a-z0-9_+#.-]{2,}", re.IGNORECASE)


def _memory_tokens(value: str) -> set[str]:
    return {token.casefold() for token in _MEMORY_TOKEN.findall(value or "")}


@dataclass(frozen=True)
class MemoryCandidate:
    memory_id: str
    content: str
    relevance: float = 0.0
    importance: float = 0.5
    confidence: float = 1.0
    scope: str = "global"
    source: str = "unknown"
    project_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.memory_id or "").strip():
            raise ValueError("Memory candidates require an id.")
        clean_content = str(self.content or "").strip()
        if not clean_content:
            raise ValueError("Memory candidates require content.")
        object.__setattr__(self, "content", clean_content)
        object.__setattr__(self, "relevance", _clamp01(self.relevance))
        object.__setattr__(self, "importance", _clamp01(self.importance))
        object.__setattr__(self, "confidence", _clamp01(self.confidence))
        object.__setattr__(self, "scope", str(self.scope or "global").casefold())
        object.__setattr__(self, "source", str(self.source or "unknown")[:200])
        object.__setattr__(self, "project_id", str(self.project_id or "")[:500])
        object.__setattr__(self, "metadata", dict(_compact_value(self.metadata)))


@dataclass(frozen=True)
class RankedMemory:
    candidate: MemoryCandidate
    score: float
    excerpt: str
    lexical_relevance: float
    recency: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "memoryId": self.candidate.memory_id,
            "content": self.excerpt,
            "score": self.score,
            "lexicalRelevance": self.lexical_relevance,
            "recency": self.recency,
            "importance": self.candidate.importance,
            "confidence": self.candidate.confidence,
            "scope": self.candidate.scope,
            "source": self.candidate.source,
            "projectId": self.candidate.project_id,
        }


def rank_memories(
    candidates: Iterable[MemoryCandidate],
    query: str,
    *,
    now: float | None = None,
    project_id: str = "",
    scopes: Iterable[str] = (),
    limit: int = 8,
    char_budget: int = 8_000,
    half_life_seconds: float = 30 * 24 * 60 * 60,
    min_score: float = 0.0,
) -> tuple[RankedMemory, ...]:
    """Rank applicable memories, enforcing expiry, scope, and output budget."""

    current_time = time.time() if now is None else float(now)
    clean_project = str(project_id or "")
    allowed_scopes = {
        str(scope).strip().casefold() for scope in scopes if str(scope).strip()
    }
    query_tokens = _memory_tokens(query)
    normalized_query = " ".join(str(query or "").casefold().split())
    half_life = max(1.0, float(half_life_seconds))
    ranked: list[RankedMemory] = []

    for candidate in candidates:
        if candidate.expires_at is not None and candidate.expires_at <= current_time:
            continue
        if allowed_scopes and candidate.scope not in allowed_scopes:
            continue
        if candidate.project_id:
            if not clean_project or candidate.project_id != clean_project:
                continue
        content_tokens = _memory_tokens(candidate.content)
        overlap = query_tokens & content_tokens
        if query_tokens:
            query_coverage = len(overlap) / len(query_tokens)
            content_specificity = len(overlap) / max(1, len(content_tokens))
            lexical = 0.78 * query_coverage + 0.22 * content_specificity
            if normalized_query and normalized_query in candidate.content.casefold():
                lexical = min(1.0, lexical + 0.15)
        else:
            lexical = 0.0
        updated = max(float(candidate.created_at), float(candidate.updated_at))
        age = max(0.0, current_time - updated)
        recency = math.exp(-math.log(2.0) * age / half_life)
        project_bonus = (
            0.05
            if clean_project and candidate.project_id == clean_project
            else 0.02
            if not candidate.project_id
            else 0.0
        )
        score = (
            0.43 * lexical
            + 0.14 * candidate.relevance
            + 0.16 * candidate.importance
            + 0.12 * recency
            + 0.10 * candidate.confidence
            + project_bonus
        )
        if score < float(min_score):
            continue
        ranked.append(
            RankedMemory(
                candidate=candidate,
                score=score,
                excerpt=candidate.content,
                lexical_relevance=lexical,
                recency=recency,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            -max(item.candidate.created_at, item.candidate.updated_at),
            item.candidate.memory_id,
        )
    )
    remaining = max(0, int(char_budget))
    selected: list[RankedMemory] = []
    for item in ranked:
        if len(selected) >= max(0, int(limit)) or remaining <= 0:
            break
        if remaining < 24:
            break
        excerpt = item.excerpt
        if len(excerpt) > remaining:
            excerpt = excerpt[: max(1, remaining - 1)].rstrip() + "…"
        selected.append(
            RankedMemory(
                candidate=item.candidate,
                score=item.score,
                excerpt=excerpt,
                lexical_relevance=item.lexical_relevance,
                recency=item.recency,
            )
        )
        remaining -= len(excerpt)
    return tuple(selected)


@dataclass(frozen=True)
class AwarenessEvent:
    sequence: int
    event_type: str
    timestamp: float
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "eventType": self.event_type,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class AwarenessSnapshot:
    current_project: str = ""
    active_application: str = ""
    current_model: str = ""
    model_state: str = "unloaded"
    git_branch: str = ""
    build_status: str = "unknown"
    test_status: str = "unknown"
    online: bool | None = None
    listening: bool = False
    recent_files: tuple[str, ...] = ()
    open_errors: tuple[str, ...] = ()
    pending_tasks: tuple[str, ...] = ()
    recent_tasks: tuple[str, ...] = ()
    utilization: Mapping[str, float | None] = field(default_factory=dict)
    last_event_at: float = 0.0
    event_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["utilization"] = dict(self.utilization)
        return value


class BackgroundMind:
    """A bounded event reducer; it never polls or invokes an LLM."""

    def __init__(
        self,
        *,
        max_events: int = 256,
        max_recent_files: int = 20,
        max_errors: int = 20,
        max_tasks: int = 30,
    ):
        self.max_events = max(1, int(max_events))
        self.max_recent_files = max(1, int(max_recent_files))
        self.max_errors = max(1, int(max_errors))
        self.max_tasks = max(1, int(max_tasks))
        self._events: deque[AwarenessEvent] = deque(maxlen=self.max_events)
        self._recent_files: deque[str] = deque(maxlen=self.max_recent_files)
        self._errors: deque[str] = deque(maxlen=self.max_errors)
        self._recent_tasks: deque[str] = deque(maxlen=self.max_tasks)
        self._pending_tasks: dict[str, str] = {}
        self._state: dict[str, Any] = {
            "current_project": "",
            "active_application": "",
            "current_model": "",
            "model_state": "unloaded",
            "git_branch": "",
            "build_status": "unknown",
            "test_status": "unknown",
            "online": None,
            "listening": False,
            "utilization": {},
            "last_event_at": 0.0,
            "event_count": 0,
        }
        self._subscribers: dict[str, Callable[[AwarenessEvent], None]] = {}
        self._lock = threading.RLock()

    def subscribe(self, callback: Callable[[AwarenessEvent], None]) -> str:
        if not callable(callback):
            raise TypeError("BackgroundMind subscriber must be callable.")
        token = uuid.uuid4().hex
        with self._lock:
            self._subscribers[token] = callback
        return token

    def unsubscribe(self, token: str) -> bool:
        with self._lock:
            return self._subscribers.pop(str(token), None) is not None

    def publish(
        self,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timestamp: float | None = None,
    ) -> AwarenessEvent:
        clean_type = str(event_type or "").strip().casefold()
        if not clean_type:
            raise ValueError("Awareness events require a type.")
        compact_payload = dict(_compact_value(dict(payload or {})))
        with self._lock:
            sequence = int(self._state["event_count"]) + 1
            event = AwarenessEvent(
                sequence,
                clean_type,
                time.time() if timestamp is None else float(timestamp),
                compact_payload,
            )
            self._events.append(event)
            self._state["event_count"] = sequence
            self._state["last_event_at"] = event.timestamp
            self._reduce(event)
            subscribers = tuple(self._subscribers.values())
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                continue
        return event

    record_event = publish

    def events(self, limit: int | None = None) -> tuple[AwarenessEvent, ...]:
        with self._lock:
            values = tuple(reversed(self._events))
        if limit is None:
            return values
        return values[: max(0, int(limit))]

    def snapshot(self) -> AwarenessSnapshot:
        with self._lock:
            state = dict(self._state)
            utilization = dict(state["utilization"])
            return AwarenessSnapshot(
                current_project=state["current_project"],
                active_application=state["active_application"],
                current_model=state["current_model"],
                model_state=state["model_state"],
                git_branch=state["git_branch"],
                build_status=state["build_status"],
                test_status=state["test_status"],
                online=state["online"],
                listening=state["listening"],
                recent_files=tuple(self._recent_files),
                open_errors=tuple(self._errors),
                pending_tasks=tuple(self._pending_tasks.values()),
                recent_tasks=tuple(self._recent_tasks),
                utilization=utilization,
                last_event_at=state["last_event_at"],
                event_count=state["event_count"],
            )

    @staticmethod
    def _payload_text(payload: Mapping[str, Any], *keys: str) -> str:
        for key in keys:
            value = str(payload.get(key, "") or "").strip()
            if value:
                return value[:2_000]
        return ""

    @staticmethod
    def _number(payload: Mapping[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = payload.get(key)
            if value is None or isinstance(value, bool):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _append_unique(target: deque[str], value: str) -> None:
        if not value:
            return
        try:
            target.remove(value)
        except ValueError:
            pass
        target.appendleft(value)

    def _reduce(self, event: AwarenessEvent) -> None:
        kind = event.event_type
        payload = event.payload
        if kind in {"project.opened", "project.changed", "workspace.changed"}:
            self._state["current_project"] = self._payload_text(
                payload, "root", "path", "project", "name"
            )
        elif kind == "project.closed":
            closing = self._payload_text(payload, "root", "path", "project")
            if not closing or closing == self._state["current_project"]:
                self._state["current_project"] = ""
        elif kind in {"application.activated", "application.focused"}:
            self._state["active_application"] = self._payload_text(
                payload, "name", "application", "title"
            )
        elif kind in {"file.modified", "file.opened", "file.created"}:
            self._append_unique(
                self._recent_files,
                self._payload_text(payload, "path", "file"),
            )
        elif kind in {"git.branch.changed", "git.changed"}:
            self._state["git_branch"] = self._payload_text(
                payload, "branch", "name"
            )
        elif kind in {"model.loading", "model.loaded", "model.failed", "model.unloaded"}:
            self._state["model_state"] = kind.rsplit(".", 1)[-1]
            model = self._payload_text(payload, "model", "modelId", "name")
            if model:
                self._state["current_model"] = model
            if kind == "model.unloaded":
                self._state["current_model"] = ""
            if kind == "model.failed":
                self._append_unique(
                    self._errors,
                    self._payload_text(payload, "error", "message")
                    or f"Model failed: {model or 'unknown model'}",
                )
        elif kind in {"build.started", "build.completed", "build.failed"}:
            self._state["build_status"] = kind.rsplit(".", 1)[-1]
            if kind == "build.failed":
                self._append_unique(
                    self._errors,
                    self._payload_text(payload, "error", "message")
                    or "Build failed.",
                )
        elif kind in {"test.started", "test.completed", "test.failed"}:
            self._state["test_status"] = kind.rsplit(".", 1)[-1]
            if kind == "test.failed":
                self._append_unique(
                    self._errors,
                    self._payload_text(payload, "error", "message")
                    or "Tests failed.",
                )
        elif kind in {"task.started", "task.queued"}:
            task_id = self._payload_text(payload, "taskId", "id") or str(
                event.sequence
            )
            label = self._payload_text(payload, "name", "title", "task") or task_id
            self._pending_tasks[task_id] = label
            while len(self._pending_tasks) > self.max_tasks:
                self._pending_tasks.pop(next(iter(self._pending_tasks)))
        elif kind in {"task.completed", "task.failed", "task.cancelled"}:
            task_id = self._payload_text(payload, "taskId", "id")
            label = self._pending_tasks.pop(task_id, "") if task_id else ""
            label = label or self._payload_text(payload, "name", "title", "task")
            self._append_unique(self._recent_tasks, label)
            if kind == "task.failed":
                self._append_unique(
                    self._errors,
                    self._payload_text(payload, "error", "message")
                    or f"Task failed: {label or task_id or 'unknown task'}",
                )
        elif kind in {"network.online", "internet.restored"}:
            self._state["online"] = True
        elif kind in {"network.offline", "internet.lost"}:
            self._state["online"] = False
        elif kind in {"microphone.activated", "voice.listening"}:
            self._state["listening"] = True
        elif kind in {"microphone.deactivated", "voice.idle"}:
            self._state["listening"] = False
        elif kind in {"system.metrics", "resource.sample", "system.utilization"}:
            self._state["utilization"] = {
                "cpuPercent": self._number(payload, "cpuPercent", "cpu_percent"),
                "memoryPercent": self._number(
                    payload, "memoryPercent", "memory_percent"
                ),
                "gpuPercent": self._number(payload, "gpuPercent", "gpu_percent"),
                "vramUsedMb": self._number(
                    payload, "vramUsedMb", "vram_used_mb"
                ),
                "vramTotalMb": self._number(
                    payload, "vramTotalMb", "vram_total_mb"
                ),
                "batteryPercent": self._number(
                    payload, "batteryPercent", "battery_percent"
                ),
            }
        elif kind in {"error.opened", "renderer.crashed", "service.failed"}:
            self._append_unique(
                self._errors,
                self._payload_text(payload, "error", "message", "title")
                or kind,
            )
        elif kind in {"error.resolved", "errors.cleared"}:
            error = self._payload_text(payload, "error", "message")
            if not error:
                self._errors.clear()
            else:
                self._errors = deque(
                    (item for item in self._errors if item != error),
                    maxlen=self.max_errors,
                )


@dataclass(frozen=True)
class RealtimeRequest:
    request_id: str
    epoch: int
    text: str
    route: RouteDecision
    trace: LatencyTrace
    cancellation: CancellationToken
    chunker: SemanticChunker


class RealtimeIntelligence:
    """Facade joining the isolated real-time coordination primitives."""

    def __init__(
        self,
        *,
        models: Mapping[ModelTier | str, str] | None = None,
        trace_capacity: int = 200,
        event_capacity: int = 256,
        chunker_factory: Callable[[], SemanticChunker] = SemanticChunker,
    ):
        self.latencies = LatencyRegistry(trace_capacity)
        self.router = TieredModelRouter(models)
        self.background = BackgroundMind(max_events=event_capacity)
        self._chunker_factory = chunker_factory
        self._active: RealtimeRequest | None = None
        self._epoch = 0
        self._lock = threading.RLock()

    def begin_request(
        self,
        text: str,
        *,
        request_id: str | None = None,
        intents: Iterable[object] = (),
        partial: bool = False,
        destructive: bool = False,
        override_model: str = "",
        override_tier: ModelTier | str | None = None,
        started_ns: int | None = None,
        initial_marks: Mapping[LatencyStage | str, int] | None = None,
        metadata: Mapping[str, Any] | None = None,
        input_event: str = "input_received",
    ) -> RealtimeRequest:
        clean_text = str(text or "").strip()
        if not clean_text:
            raise ValueError("A real-time request cannot be empty.")
        marks = {
            _coerce_stage(stage): int(timestamp)
            for stage, timestamp in (initial_marks or {}).items()
        }
        if started_ns is None and marks:
            started_ns = min(marks.values())
        with self._lock:
            if self._active is not None:
                self._active.cancellation.cancel("superseded by a newer request")
            self._epoch += 1
            trace = self.latencies.begin(
                request_id,
                created_monotonic_ns=started_ns,
                metadata=metadata,
            )
            trace.mark_event(input_event, at_ns=started_ns)
            trace.mark_event("routing_started")
            for stage, timestamp in sorted(
                marks.items(), key=lambda item: _STAGE_INDEX[item[0]]
            ):
                trace.mark(stage, at_ns=timestamp)
            route = self.router.route(
                clean_text,
                intents=intents,
                partial=partial,
                destructive=destructive,
                override_model=override_model,
                override_tier=override_tier,
            )
            trace.mark(
                LatencyStage.INTENT_IDENTIFIED,
                metadata={"tier": route.tier.value, "modelId": route.model_id},
            )
            trace.mark_event(
                "route_completed",
                metadata={"tier": route.tier.value, "hostAction": route.host_action},
            )
            request = RealtimeRequest(
                request_id=trace.request_id,
                epoch=self._epoch,
                text=clean_text,
                route=route,
                trace=trace,
                cancellation=CancellationToken(self._epoch),
                chunker=self._chunker_factory(),
            )
            self._active = request
            return request

    @property
    def active_request(self) -> RealtimeRequest | None:
        with self._lock:
            return self._active

    def is_current(self, epoch: int) -> bool:
        with self._lock:
            return bool(
                self._active
                and self._active.epoch == int(epoch)
                and self._active.cancellation.matches(epoch)
            )

    def cancel_active(self, reason: str = "interrupted") -> bool:
        with self._lock:
            active = self._active
        if active is None:
            return False
        cancelled = active.cancellation.cancel(reason)
        if cancelled:
            self.background.publish(
                "task.cancelled",
                {"taskId": active.request_id, "name": "response generation"},
            )
        return cancelled

    def mark(
        self,
        request_id: str,
        stage: LatencyStage | str,
        *,
        at_ns: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        trace = self.latencies.get(request_id)
        return bool(
            trace
            and trace.mark(stage, at_ns=at_ns, metadata=metadata)
        )

    def mark_event(
        self,
        request_id: str,
        name: str,
        *,
        at_ns: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        trace = self.latencies.get(request_id)
        return bool(
            trace
            and trace.mark_event(name, at_ns=at_ns, metadata=metadata)
        )

    def accept_delta(self, epoch: int, delta: str) -> tuple[SemanticChunk, ...]:
        with self._lock:
            active = self._active
            if (
                active is None
                or active.epoch != int(epoch)
                or active.cancellation.cancelled
            ):
                return ()
            if delta:
                active.trace.increment("generatedCharacters", len(delta))
            if delta and str(delta).strip():
                active.trace.mark(LatencyStage.FIRST_LLM_TOKEN)
                active.trace.mark_event("first_model_token")
            chunks = active.chunker.feed(delta)
            if chunks:
                active.trace.mark(LatencyStage.FIRST_CHUNK_READY)
            return chunks

    def complete_generation(self, epoch: int) -> tuple[SemanticChunk, ...]:
        with self._lock:
            active = self._active
            if (
                active is None
                or active.epoch != int(epoch)
                or active.cancellation.cancelled
            ):
                return ()
            chunks = active.chunker.flush()
            if chunks:
                active.trace.mark(LatencyStage.FIRST_CHUNK_READY)
            active.trace.mark(LatencyStage.GENERATION_COMPLETE)
            active.trace.mark_event("generation_complete")
            return chunks

    def finish_speech(self, epoch: int) -> bool:
        with self._lock:
            active = self._active
            if active is None or active.epoch != int(epoch):
                return False
            marked = active.trace.mark(LatencyStage.SPEECH_COMPLETE)
            active.trace.mark_event("response_complete")
            self._active = None
            return marked

    def rank_memory(
        self,
        candidates: Iterable[MemoryCandidate],
        query: str,
        **kwargs: Any,
    ) -> tuple[RankedMemory, ...]:
        return rank_memories(candidates, query, **kwargs)

    def record_event(
        self,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timestamp: float | None = None,
    ) -> AwarenessEvent:
        return self.background.publish(
            event_type,
            payload,
            timestamp=timestamp,
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = self._active
            active_value = (
                {
                    "requestId": active.request_id,
                    "epoch": active.epoch,
                    "route": active.route.to_dict(),
                    "cancelled": active.cancellation.cancelled,
                }
                if active
                else {}
            )
        return {
            "active": active_value,
            "latency": self.latencies.summary(),
            "awareness": self.background.snapshot().to_dict(),
        }


__all__ = [
    "AwarenessEvent",
    "AwarenessSnapshot",
    "BackgroundMind",
    "CancellationToken",
    "LatencyRegistry",
    "LatencyStage",
    "LatencyTrace",
    "MemoryCandidate",
    "ModelTier",
    "RankedMemory",
    "RealtimeIntelligence",
    "RealtimeRequest",
    "RequestCancelledError",
    "RouteDecision",
    "SemanticChunk",
    "SemanticChunker",
    "TieredModelRouter",
    "rank_memories",
]
