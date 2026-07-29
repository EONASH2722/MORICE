from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .agent_types import IntentType


@dataclass
class ModelHealth:
    model_id: str
    requests: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    generated_tokens: int = 0
    prompt_tokens: int = 0
    last_latency_ms: float = 0.0
    last_tokens_per_second: float = 0.0
    last_context_usage: float = 0.0
    last_error: str = ""
    last_used_at: float = 0.0
    gpu_layers: int = 0
    temperature: float = 0.2

    @property
    def average_latency_ms(self) -> float:
        return self.total_latency_ms / self.requests if self.requests else 0.0

    @property
    def success_rate(self) -> float:
        return (self.requests - self.failures) / self.requests if self.requests else 1.0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["average_latency_ms"] = self.average_latency_ms
        value["success_rate"] = self.success_rate
        return value


@dataclass(frozen=True)
class ModelRoute:
    preferred: str
    fallbacks: tuple[str, ...]
    reason: str
    task_profile: str
    temperature: float
    context_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelRouter:
    def __init__(self):
        self._health: dict[str, ModelHealth] = {}
        self._lock = threading.RLock()

    def route(
        self,
        intents: Iterable[IntentType],
        *,
        selected_model: str = "",
        available_models: Iterable[str] = (),
        context_tokens: int = 16_384,
    ) -> ModelRoute:
        intent_set = set(intents)
        available = tuple(dict.fromkeys(model for model in available_models if model))
        selected = selected_model.strip()
        profile = "general"
        aliases = ("general", "hermes", "llama", "mistral")
        temperature = 0.45
        if intent_set & {
            IntentType.CODING,
            IntentType.PROGRAMMING,
            IntentType.PROJECT_MODIFICATION,
            IntentType.FILE_EDITING,
        }:
            profile = "coding"
            aliases = ("coder", "qwen", "deepseek", "codestral")
            temperature = 0.15
        elif intent_set & {
            IntentType.MATHEMATICS,
            IntentType.PHYSICS,
            IntentType.CHEMISTRY,
            IntentType.REASONING,
            IntentType.PLANNING,
        }:
            profile = "reasoning"
            aliases = ("reason", "math", "deepseek", "qwen")
            temperature = 0.1
        elif IntentType.IMAGE_ANALYSIS in intent_set:
            profile = "vision"
            aliases = ("vision", "vl", "llava")
            temperature = 0.2
        candidates = list(available)
        candidates.sort(
            key=lambda model: (
                -sum(alias in model.lower() for alias in aliases),
                -self._score(model),
                model.lower(),
            )
        )
        preferred = selected or (candidates[0] if candidates else "selected-local-model")
        fallbacks = tuple(model for model in candidates if model != preferred)
        return ModelRoute(
            preferred=preferred,
            fallbacks=fallbacks,
            reason=f"{profile} intent profile selected",
            task_profile=profile,
            temperature=temperature,
            context_tokens=max(2_048, int(context_tokens)),
        )

    def record(
        self,
        model_id: str,
        *,
        success: bool,
        latency_ms: float,
        prompt_tokens: int = 0,
        generated_tokens: int = 0,
        context_limit: int = 0,
        error: str = "",
        gpu_layers: int = 0,
        temperature: float = 0.2,
    ) -> None:
        clean_id = model_id or "unknown"
        with self._lock:
            health = self._health.setdefault(clean_id, ModelHealth(clean_id))
            health.requests += 1
            health.failures += 0 if success else 1
            health.total_latency_ms += max(0.0, latency_ms)
            health.last_latency_ms = max(0.0, latency_ms)
            health.prompt_tokens += max(0, prompt_tokens)
            health.generated_tokens += max(0, generated_tokens)
            health.last_tokens_per_second = (
                generated_tokens / (latency_ms / 1000)
                if latency_ms > 0 and generated_tokens > 0
                else 0.0
            )
            health.last_context_usage = (
                min(1.0, prompt_tokens / context_limit)
                if context_limit > 0
                else 0.0
            )
            health.last_error = error
            health.last_used_at = time.time()
            health.gpu_layers = max(0, int(gpu_layers))
            health.temperature = float(temperature)

    def health(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                model_id: health.to_dict()
                for model_id, health in sorted(self._health.items())
            }

    def _score(self, model_id: str) -> float:
        health = self._health.get(model_id)
        if not health:
            return 0.75
        latency_penalty = min(0.35, math.log1p(health.average_latency_ms) / 40)
        return max(0.0, health.success_rate - latency_penalty)


class ContextManager:
    def __init__(self, *, chars_per_token: float = 3.8):
        self.chars_per_token = max(2.0, float(chars_per_token))

    def prepare(
        self,
        history: Iterable[dict[str, Any]],
        request: str,
        *,
        token_budget: int,
        project_context: str = "",
        persistent_context: str = "",
    ) -> tuple[tuple[dict[str, str], ...], dict[str, Any]]:
        budget_chars = max(4_000, int(token_budget * self.chars_per_token))
        reserved = len(request) + len(project_context) + len(persistent_context) + 1_000
        available = max(2_000, budget_chars - reserved)
        clean = [
            {
                "role": (
                    str(item.get("role", "user"))
                    if str(item.get("role", "user"))
                    in {"user", "assistant", "system", "tool"}
                    else "user"
                ),
                "content": str(item.get("content", "")),
            }
            for item in history
            if str(item.get("content", "")).strip()
        ]
        query_terms = set(re.findall(r"[a-z0-9_]+", request.lower()))
        selected_entries: list[tuple[int, dict[str, str]]] = []
        used = 0
        history_budget = max(1_000, int(available * 0.8))
        for index in range(len(clean) - 1, -1, -1):
            item = clean[index]
            content = item["content"]
            relevance = len(query_terms & set(re.findall(r"[a-z0-9_]+", content.lower())))
            if selected_entries and relevance == 0 and used > history_budget * 0.65:
                continue
            if used + len(content) > history_budget:
                continue
            selected_entries.append((index, item))
            used += len(content)
        if not selected_entries and clean:
            newest = dict(clean[-1])
            newest["content"] = newest["content"][-history_budget:]
            selected_entries.append((len(clean) - 1, newest))
            used = len(newest["content"])
        selected_entries.reverse()
        selected_indices = {index for index, _item in selected_entries}
        selected = [item for _index, item in selected_entries]
        omitted_items = [
            item for index, item in enumerate(clean) if index not in selected_indices
        ]
        omitted = len(omitted_items)
        if omitted:
            summary = self.summarize(
                omitted_items,
                max_chars=min(1_600, max(0, available - used)),
            )
            if summary:
                selected.insert(
                    0,
                    {
                        "role": "system",
                        "content": "Earlier conversation summary: " + summary,
                    },
                )
        system_context: list[dict[str, str]] = []
        if persistent_context.strip():
            system_context.append(
                {
                    "role": "system",
                    "content": persistent_context.strip()[-24_000:],
                }
            )
        if project_context.strip():
            system_context.append(
                {
                    "role": "system",
                    "content": (
                        "Verified project context:\n"
                        + project_context.strip()[-32_000:]
                    ),
                }
            )
        context_index = (
            1
            if selected
            and selected[0]["content"].startswith("Earlier conversation summary:")
            else 0
        )
        selected[context_index:context_index] = system_context
        return tuple(selected), {
            "budgetTokens": token_budget,
            "estimatedTokens": int(
                (
                    sum(len(item["content"]) for item in selected)
                    + len(request)
                    + 1_000
                )
                / self.chars_per_token
            ),
            "omittedMessages": omitted,
            "compressed": omitted > 0,
        }

    @staticmethod
    def summarize(history: list[dict[str, str]], *, max_chars: int = 1_600) -> str:
        points: list[str] = []
        for item in history:
            content = " ".join(item["content"].split())
            if not content:
                continue
            sentence = re.split(r"(?<=[.!?])\s+", content, maxsplit=1)[0]
            points.append(f"{item['role']}: {sentence[:240]}")
            if sum(len(point) for point in points) >= max_chars:
                break
        return " | ".join(points)[:max_chars]
