from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .agent_tools import BuiltinTools
from .agent_types import (
    AgentExecutionResult,
    AgentRequestContext,
    ExecutionStage,
    IntentType,
    ProjectContext,
    ToolCall,
    ToolResult,
)
from .intent_router import IntentRouter
from .model_router import ContextManager, ModelRouter


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentOrchestrator:
    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        logger: Callable[..., Any] | None = None,
    ):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.logger = logger
        self.intent_router = IntentRouter()
        self.model_router = ModelRouter()
        self.context_manager = ContextManager()
        self.tools = BuiltinTools(self.directory / "tools", logger=logger)
        self._requests: dict[str, AgentRequestContext] = {}
        self._stage_status: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()

    def prepare_request(
        self,
        request: str,
        *,
        history: Iterable[dict[str, Any]] = (),
        project_root: str = "",
        selected_model: str = "",
        available_models: Iterable[str] = (),
        capabilities: Iterable[str] = (),
        persistent_context: str = "",
        context_tokens: int = 16_384,
    ) -> AgentRequestContext:
        if not (request or "").strip():
            raise ValueError("Agent request cannot be empty.")
        plan = self.intent_router.plan(request)
        status = {stage.value: "pending" for stage in ExecutionStage}
        status[ExecutionStage.INTENT_DETECTION.value] = "completed"
        project = ProjectContext()
        project_text = ""
        if project_root and Path(project_root).is_dir():
            index_result = self.tools.executor.execute(
                ToolCall(
                    "project.index",
                    {"root": project_root, "query": request},
                    call_id=f"{plan.request_id}:project-index",
                )
            )
            if index_result.success and isinstance(index_result.output, dict):
                summary = dict(index_result.output)
                relevant = tuple(summary.pop("relevant", ()))
                context_files = tuple(summary.pop("contextFiles", ()))
                project = ProjectContext(
                    root=str(Path(project_root).resolve()),
                    summary=summary,
                    relevant_files=context_files or relevant,
                )
                project_text = json.dumps(
                    {
                        "languages": summary.get("languages", {}),
                        "frameworks": summary.get("frameworks", ()),
                        "build_systems": summary.get("build_systems", ()),
                        "entry_points": summary.get("entry_points", ()),
                        "git": summary.get("git", {}),
                        "relevant": relevant,
                    },
                    ensure_ascii=False,
                    default=str,
                )
                status[ExecutionStage.PROJECT_CONTEXT.value] = "completed"
            else:
                status[ExecutionStage.PROJECT_CONTEXT.value] = "failed"
        else:
            status[ExecutionStage.PROJECT_CONTEXT.value] = "not_applicable"
        route = self.model_router.route(
            plan.intents,
            selected_model=selected_model,
            available_models=available_models,
            context_tokens=context_tokens,
        )
        conversation, budget = self.context_manager.prepare(
            history,
            request,
            token_budget=max(2_048, route.context_tokens - 2_048),
            project_context=project_text,
            persistent_context=persistent_context,
        )
        route_value = route.to_dict()
        route_value["context"] = budget
        renderer = self._renderer_for(plan.intents)
        status.update(
            {
                ExecutionStage.CONTEXT_RETRIEVAL.value: "completed",
                ExecutionStage.CONVERSATION_MEMORY.value: "completed",
                ExecutionStage.CAPABILITY_DETECTION.value: "completed",
                ExecutionStage.PLANNING.value: "completed",
                ExecutionStage.TOOL_SELECTION.value: "completed",
                ExecutionStage.RENDERER_SELECTION.value: (
                    "completed" if renderer else "not_applicable"
                ),
            }
        )
        context = AgentRequestContext(
            request_id=plan.request_id,
            request=request,
            plan=plan,
            conversation=conversation,
            project=project,
            capabilities=tuple(dict.fromkeys(str(item) for item in capabilities)),
            model_route=route_value,
            renderer=renderer,
            created_at=_utc_now(),
        )
        with self._lock:
            self._requests[context.request_id] = context
            self._stage_status[context.request_id] = status
            if len(self._requests) > 200:
                oldest = next(iter(self._requests))
                self._requests.pop(oldest, None)
                self._stage_status.pop(oldest, None)
        self._log(
            "INFO",
            "Agent request prepared.",
            {
                "requestId": context.request_id,
                "intents": [intent.value for intent in plan.intents],
                "renderer": renderer,
                "project": bool(project.root),
                "model": route.preferred,
            },
        )
        return context

    def execute(
        self,
        request_id: str,
        calls: Iterable[ToolCall],
        *,
        renderer_validator: Callable[[str], bool] | None = None,
    ) -> AgentExecutionResult:
        with self._lock:
            context = self._requests.get(request_id)
            status = self._stage_status.get(request_id, {}).copy()
        if context is None:
            return AgentExecutionResult(
                request_id,
                False,
                False,
                "The prepared agent request was not found.",
                errors=["Unknown request id."],
                stage_status=status,
            )
        results: list[ToolResult] = []
        status[ExecutionStage.PERMISSION_CHECK.value] = "completed"
        status[ExecutionStage.EXECUTION.value] = "in_progress"
        for call in calls:
            result = self.tools.executor.execute(call)
            results.append(result)
            definition = self.tools.registry.definition(call.tool_id)
            if (
                not result.success
                and result.retryable
                and definition is not None
                and definition.idempotent
            ):
                retry_call = ToolCall(
                    call.tool_id,
                    dict(call.arguments),
                    call_id=f"{call.call_id or uuid.uuid4().hex}:retry",
                )
                retry = self.tools.executor.execute(retry_call)
                retry.metadata["retryOf"] = call.call_id
                results.append(retry)
        status[ExecutionStage.EXECUTION.value] = (
            "completed" if all(item.success for item in results) else "failed"
        )
        verified = self._verify(results, context.renderer, renderer_validator)
        status[ExecutionStage.VERIFICATION.value] = (
            "completed" if verified else "failed"
        )
        status[ExecutionStage.RESULT_COLLECTION.value] = "completed"
        status[ExecutionStage.UI_UPDATE.value] = "pending"
        status[ExecutionStage.FINAL_RESPONSE.value] = "pending"
        errors = [error for result in results for error in result.errors]
        warnings = [warning for result in results for warning in result.warnings]
        artifacts = [artifact for result in results for artifact in result.artifacts]
        success = all(result.success for result in results) and verified
        if not results:
            if context.renderer:
                success = verified
            else:
                success = True
                verified = True
                status[ExecutionStage.VERIFICATION.value] = "not_applicable"
        message = (
            "The requested actions completed and their outputs were verified."
            if success
            else "The action did not complete with verified output."
        )
        result = AgentExecutionResult(
            request_id=request_id,
            success=success,
            verified=verified,
            message=message,
            tool_results=results,
            warnings=warnings,
            errors=errors,
            artifacts=artifacts,
            stage_status=status,
        )
        with self._lock:
            self._stage_status[request_id] = status
        self._log(
            "INFO" if success else "ERROR",
            "Agent execution finished.",
            {
                "requestId": request_id,
                "success": success,
                "verified": verified,
                "tools": [item.tool_id for item in results],
                "errors": errors,
            },
        )
        return result

    def mark_ui_complete(self, request_id: str, *, response_present: bool) -> None:
        with self._lock:
            status = self._stage_status.get(request_id)
            if status is None:
                return
            status[ExecutionStage.UI_UPDATE.value] = "completed"
            status[ExecutionStage.FINAL_RESPONSE.value] = (
                "completed" if response_present else "failed"
            )

    def permission_token(self, tool_id: str, arguments: dict[str, Any]) -> str:
        return self.tools.permissions.grant(tool_id, arguments)

    def cancel(self, call_id: str) -> bool:
        return self.tools.cancel(call_id)

    def request_context(self, request_id: str) -> AgentRequestContext | None:
        with self._lock:
            return self._requests.get(request_id)

    def record_model_result(
        self,
        request_id: str,
        *,
        success: bool,
        latency_ms: float,
        prompt_tokens: int = 0,
        generated_tokens: int = 0,
        error: str = "",
        gpu_layers: int = 0,
    ) -> None:
        with self._lock:
            context = self._requests.get(request_id)
        if not context:
            return
        route = context.model_route
        self.model_router.record(
            str(route.get("preferred", "unknown")),
            success=success,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            generated_tokens=generated_tokens,
            context_limit=int(route.get("context_tokens", 0)),
            error=error,
            gpu_layers=gpu_layers,
            temperature=float(route.get("temperature", 0.2)),
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            request_count = len(self._requests)
            active = next(reversed(self._requests.values()), None) if self._requests else None
            active_status = (
                self._stage_status.get(active.request_id, {}).copy()
                if active
                else {}
            )
        definitions = self.tools.registry.definitions()
        recent = self.tools.history.recent(25)
        return {
            "requestCount": request_count,
            "activeRequestId": active.request_id if active else "",
            "activeIntents": (
                [intent.value for intent in active.plan.intents] if active else []
            ),
            "activeStages": active_status,
            "toolCount": len(definitions),
            "tools": [definition.to_dict() for definition in definitions],
            "modelHealth": self.model_router.health(),
            "recentActions": [record.to_dict() for record in recent],
        }

    @staticmethod
    def _verify(
        results: list[ToolResult],
        renderer: str,
        renderer_validator: Callable[[str], bool] | None,
    ) -> bool:
        if any(not result.success or not result.verified for result in results):
            return False
        if renderer:
            if renderer_validator is None:
                return False
            try:
                return bool(renderer_validator(renderer))
            except Exception:  # noqa: BLE001
                return False
        return True

    @staticmethod
    def _renderer_for(intents: Iterable[IntentType]) -> str:
        intent_set = set(intents)
        if IntentType.SIMULATION in intent_set or IntentType.PHYSICS in intent_set:
            return "simulation"
        if IntentType.CHEMISTRY in intent_set:
            return "molecule"
        if IntentType.BIOLOGY in intent_set:
            return "biology"
        if IntentType.VISUALIZATION in intent_set or IntentType.MATHEMATICS in intent_set:
            return "graph"
        return ""

    def _log(self, level: str, message: str, metadata: dict[str, Any]) -> None:
        if self.logger:
            self.logger(
                level,
                message,
                category="agent",
                metadata=metadata,
            )
