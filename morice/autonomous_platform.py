from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .agent_orchestrator import AgentOrchestrator
from .agent_types import AgentRequestContext, IntentType
from .platform_types import (
    AgentEnvelope,
    AgentRole,
    DelegatedWorkItem,
    KnowledgeEdge,
    KnowledgeNode,
    PlatformRun,
    ProjectDashboard,
    RunState,
    WorkItemState,
)
from .project_index import ProjectIndex, ProjectIndexer


MAX_RUNS = 200
MAX_MESSAGES_PER_RUN = 500
MAX_KNOWLEDGE_RESULTS = 100
MAX_PROJECT_ISSUES = 100
_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*"
    r"([^\s,;]{6,})"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _redact(value: str) -> str:
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def _tokens(value: str) -> set[str]:
    return {
        item
        for item in re.findall(r"[a-z0-9_+#.-]+", (value or "").casefold())
        if len(item) > 1
    }


class SpecialistAgentRegistry:
    """Maps typed intents to focused responsibilities without duplicating model state."""

    ROLE_DESCRIPTIONS: dict[AgentRole, str] = {
        AgentRole.ORCHESTRATOR: "Coordinates intent, context, tools, validation, and recovery.",
        AgentRole.CODING: "Plans and creates production-quality source changes.",
        AgentRole.RESEARCH: "Collects and evaluates relevant evidence.",
        AgentRole.PLANNING: "Builds dependency-aware execution plans.",
        AgentRole.DOCUMENTATION: "Produces documentation and release notes from verified work.",
        AgentRole.DEBUGGING: "Diagnoses failed builds, tests, tools, and runtime behavior.",
        AgentRole.TESTING: "Selects, runs, and interprets validation workflows.",
        AgentRole.VISUALIZATION: "Prepares deterministic renderer instructions and validates artifacts.",
        AgentRole.SIMULATION: "Prepares and validates deterministic simulation state.",
        AgentRole.DESKTOP: "Coordinates approved desktop and application actions.",
        AgentRole.FILE: "Indexes, reads, previews, and stages workspace file changes.",
        AgentRole.VOICE: "Coordinates voice input, wake, transcription, and speech capabilities.",
    }

    INTENT_ROLES: dict[IntentType, AgentRole] = {
        IntentType.CODING: AgentRole.CODING,
        IntentType.PROGRAMMING: AgentRole.CODING,
        IntentType.PROJECT_MODIFICATION: AgentRole.CODING,
        IntentType.INTERNET_SEARCH: AgentRole.RESEARCH,
        IntentType.DOCUMENT_ANALYSIS: AgentRole.RESEARCH,
        IntentType.PLANNING: AgentRole.PLANNING,
        IntentType.REASONING: AgentRole.PLANNING,
        IntentType.FILE_EDITING: AgentRole.FILE,
        IntentType.FILE_SEARCH: AgentRole.FILE,
        IntentType.TERMINAL_TASK: AgentRole.TESTING,
        IntentType.SYSTEM_TASK: AgentRole.DESKTOP,
        IntentType.DESKTOP_CONTROL: AgentRole.DESKTOP,
        IntentType.VISUALIZATION: AgentRole.VISUALIZATION,
        IntentType.MATHEMATICS: AgentRole.VISUALIZATION,
        IntentType.SIMULATION: AgentRole.SIMULATION,
        IntentType.PHYSICS: AgentRole.SIMULATION,
        IntentType.CHEMISTRY: AgentRole.VISUALIZATION,
        IntentType.BIOLOGY: AgentRole.VISUALIZATION,
    }

    def role_for(self, intent: IntentType) -> AgentRole:
        return self.INTENT_ROLES.get(intent, AgentRole.ORCHESTRATOR)

    def snapshot(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "id": role.value,
                "description": description,
            }
            for role, description in self.ROLE_DESCRIPTIONS.items()
        )


class MultiAgentCoordinator:
    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self.path = self.directory / "runs.json"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.registry = SpecialistAgentRegistry()
        self._runs: dict[str, PlatformRun] = {}
        self._lock = threading.RLock()
        self._load()

    def create_run(
        self,
        context: AgentRequestContext,
        *,
        project_root: str = "",
    ) -> PlatformRun:
        now = _utc_now()
        items: list[DelegatedWorkItem] = []
        for subtask in context.plan.subtasks:
            destructive = subtask.intent in {
                IntentType.PROJECT_MODIFICATION,
                IntentType.FILE_EDITING,
                IntentType.DESKTOP_CONTROL,
                IntentType.SYSTEM_TASK,
            }
            state = (
                WorkItemState.WAITING_APPROVAL
                if destructive
                else WorkItemState.PENDING
            )
            items.append(
                DelegatedWorkItem(
                    item_id=subtask.subtask_id,
                    title=subtask.title,
                    description=subtask.description,
                    role=self.registry.role_for(subtask.intent),
                    intent=subtask.intent.value,
                    dependencies=subtask.dependencies,
                    suggested_tools=subtask.suggested_tools,
                    destructive=destructive,
                    state=state,
                )
            )
        run = PlatformRun(
            run_id=uuid.uuid4().hex,
            request_id=context.request_id,
            request=context.request,
            state=(
                RunState.WAITING_APPROVAL
                if any(item.destructive for item in items)
                else RunState.PLANNED
            ),
            work_items=items,
            created_at=now,
            updated_at=now,
            project_root=project_root,
        )
        for item in items:
            run.messages.append(
                AgentEnvelope(
                    message_id=uuid.uuid4().hex,
                    run_id=run.run_id,
                    sender=AgentRole.ORCHESTRATOR,
                    recipient=item.role,
                    kind="assignment",
                    payload={
                        "workItemId": item.item_id,
                        "description": item.description,
                        "suggestedTools": list(item.suggested_tools),
                        "requiresApproval": item.destructive,
                    },
                    created_at=now,
                )
            )
        with self._lock:
            self._runs[run.run_id] = run
            self._trim()
            self._save()
        return run

    def grant_item(self, run_id: str, item_id: str) -> bool:
        with self._lock:
            run = self._require(run_id)
            item = self._item(run, item_id)
            if item.state != WorkItemState.WAITING_APPROVAL:
                return False
            item.state = WorkItemState.PENDING
            run.state = RunState.PLANNED
            self._refresh(run)
            self._save()
            return True

    def start_item(self, run_id: str, item_id: str) -> DelegatedWorkItem:
        with self._lock:
            run = self._require(run_id)
            item = self._item(run, item_id)
            if item.state == WorkItemState.WAITING_APPROVAL:
                raise PermissionError("This work item needs explicit approval.")
            if any(
                self._item(run, dependency).state != WorkItemState.COMPLETED
                for dependency in item.dependencies
            ):
                item.state = WorkItemState.BLOCKED
                raise RuntimeError("Work item dependencies are not complete.")
            if item.state not in {
                WorkItemState.PENDING,
                WorkItemState.BLOCKED,
                WorkItemState.FAILED,
            }:
                raise RuntimeError(f"Work item cannot start from {item.state.value}.")
            item.attempts += 1
            item.state = WorkItemState.RUNNING
            item.error = ""
            run.state = RunState.RUNNING
            self._refresh(run)
            self._save()
            return item

    def complete_item(
        self,
        run_id: str,
        item_id: str,
        result: dict[str, Any],
        *,
        verified: bool,
    ) -> PlatformRun:
        with self._lock:
            run = self._require(run_id)
            item = self._item(run, item_id)
            item.result = dict(result)
            if verified:
                item.state = WorkItemState.COMPLETED
                for artifact in result.get("artifacts", ()):
                    if isinstance(artifact, dict):
                        run.artifacts.append(dict(artifact))
            else:
                item.state = WorkItemState.FAILED
                item.error = str(result.get("error", "Result was not verified."))[:2_000]
                run.errors.append(item.error)
            run.messages.append(
                AgentEnvelope(
                    uuid.uuid4().hex,
                    run.run_id,
                    item.role,
                    AgentRole.ORCHESTRATOR,
                    "result",
                    {
                        "workItemId": item.item_id,
                        "verified": verified,
                        "summary": str(result.get("summary", ""))[:2_000],
                    },
                    _utc_now(),
                    correlation_id=item.item_id,
                )
            )
            self._refresh(run)
            self._save()
            return run

    def recover_item(self, run_id: str, item_id: str) -> bool:
        with self._lock:
            run = self._require(run_id)
            item = self._item(run, item_id)
            if item.state != WorkItemState.FAILED or item.attempts >= item.max_attempts:
                return False
            item.state = WorkItemState.PENDING
            item.error = ""
            run.recovery_count += 1
            run.state = RunState.RECOVERING
            self._refresh(run)
            self._save()
            return True

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.state in {RunState.COMPLETED, RunState.CANCELLED}:
                return False
            for item in run.work_items:
                if item.state not in {WorkItemState.COMPLETED, WorkItemState.FAILED}:
                    item.state = WorkItemState.CANCELLED
            run.state = RunState.CANCELLED
            self._refresh(run)
            self._save()
            return True

    def finalize(
        self,
        run_id: str,
        *,
        success: bool,
        summary: str = "",
    ) -> PlatformRun:
        """Close a mirrored request without claiming unapproved mutations ran."""
        with self._lock:
            run = self._require(run_id)
            if run.state in {
                RunState.COMPLETED,
                RunState.FAILED,
                RunState.CANCELLED,
            }:
                return run

            detail = str(summary or "").strip()[:2_000]
            for item in run.work_items:
                if item.state in {
                    WorkItemState.COMPLETED,
                    WorkItemState.FAILED,
                    WorkItemState.CANCELLED,
                }:
                    continue
                if item.destructive and item.state == WorkItemState.WAITING_APPROVAL:
                    item.state = WorkItemState.CANCELLED
                    item.result = {
                        "executed": False,
                        "summary": (
                            "Not executed by the autonomous coordinator because "
                            "this exact mutation was not approved."
                        ),
                    }
                    continue
                if success:
                    item.state = WorkItemState.COMPLETED
                    item.result = {
                        "verified": True,
                        "summary": detail or "The request completed successfully.",
                    }
                else:
                    item.state = WorkItemState.FAILED
                    item.error = detail or "The request did not complete."
                    run.errors.append(item.error)

            run.messages.append(
                AgentEnvelope(
                    message_id=uuid.uuid4().hex,
                    run_id=run.run_id,
                    sender=AgentRole.ORCHESTRATOR,
                    recipient=AgentRole.ORCHESTRATOR,
                    kind="run_completed" if success else "run_failed",
                    payload={
                        "success": success,
                        "summary": detail,
                        "unapprovedMutationsExecuted": False,
                    },
                    created_at=_utc_now(),
                )
            )
            run.state = RunState.COMPLETED if success else RunState.FAILED
            run.progress = 100
            run.updated_at = _utc_now()
            run.messages = run.messages[-MAX_MESSAGES_PER_RUN:]
            self._save()
            return run

    def get(self, run_id: str) -> PlatformRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def recent(self, limit: int = 20) -> tuple[PlatformRun, ...]:
        with self._lock:
            values = sorted(
                self._runs.values(),
                key=lambda item: item.updated_at,
                reverse=True,
            )
            return tuple(values[: max(1, min(int(limit), 100))])

    def snapshot(self) -> dict[str, Any]:
        recent = self.recent(20)
        return {
            "runCount": len(self._runs),
            "activeRuns": sum(
                run.state
                not in {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}
                for run in recent
            ),
            "agents": self.registry.snapshot(),
            "recentRuns": [run.to_dict() for run in recent],
        }

    def _refresh(self, run: PlatformRun) -> None:
        completed = sum(
            item.state == WorkItemState.COMPLETED for item in run.work_items
        )
        total = max(1, len(run.work_items))
        run.progress = int((completed / total) * 100)
        states = {item.state for item in run.work_items}
        if states and states <= {WorkItemState.COMPLETED}:
            run.state = RunState.COMPLETED
            run.progress = 100
        elif WorkItemState.RUNNING in states:
            run.state = RunState.RUNNING
        elif WorkItemState.WAITING_APPROVAL in states:
            run.state = RunState.WAITING_APPROVAL
        elif states and states <= {
            WorkItemState.COMPLETED,
            WorkItemState.FAILED,
            WorkItemState.CANCELLED,
        }:
            run.state = (
                RunState.FAILED
                if WorkItemState.FAILED in states
                else RunState.CANCELLED
            )
        run.updated_at = _utc_now()
        run.messages = run.messages[-MAX_MESSAGES_PER_RUN:]

    @staticmethod
    def _item(run: PlatformRun, item_id: str) -> DelegatedWorkItem:
        for item in run.work_items:
            if item.item_id == item_id:
                return item
        raise KeyError(item_id)

    def _require(self, run_id: str) -> PlatformRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def _trim(self) -> None:
        if len(self._runs) <= MAX_RUNS:
            return
        ordered = sorted(self._runs.values(), key=lambda item: item.updated_at)
        for run in ordered[: len(self._runs) - MAX_RUNS]:
            self._runs.pop(run.run_id, None)

    def _save(self) -> None:
        _atomic_json_write(
            self.path,
            {
                "version": 1,
                "runs": [run.to_dict() for run in self._runs.values()],
            },
        )

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return
        for value in data.get("runs", ())[-MAX_RUNS:]:
            try:
                work_items = [
                    DelegatedWorkItem(
                        item_id=str(item["item_id"]),
                        title=str(item["title"]),
                        description=str(item["description"]),
                        role=AgentRole(str(item["role"])),
                        intent=str(item["intent"]),
                        dependencies=tuple(item.get("dependencies", ())),
                        suggested_tools=tuple(item.get("suggested_tools", ())),
                        destructive=bool(item.get("destructive", False)),
                        state=WorkItemState(str(item.get("state", "pending"))),
                        attempts=max(0, int(item.get("attempts", 0))),
                        max_attempts=max(1, int(item.get("max_attempts", 2))),
                        result=dict(item.get("result", {})),
                        error=str(item.get("error", "")),
                    )
                    for item in value.get("workItems", ())
                ]
                run = PlatformRun(
                    run_id=str(value["runId"]),
                    request_id=str(value["requestId"]),
                    request=str(value["request"]),
                    state=RunState(str(value.get("state", "planned"))),
                    work_items=work_items,
                    created_at=str(value.get("createdAt", "")) or _utc_now(),
                    updated_at=str(value.get("updatedAt", "")) or _utc_now(),
                    project_root=str(value.get("projectRoot", "")),
                    progress=max(0, min(100, int(value.get("progress", 0)))),
                    recovery_count=max(0, int(value.get("recoveryCount", 0))),
                    artifacts=[
                        dict(item)
                        for item in value.get("artifacts", ())
                        if isinstance(item, dict)
                    ],
                    warnings=[str(item) for item in value.get("warnings", ())],
                    errors=[str(item) for item in value.get("errors", ())],
                )
                self._runs[run.run_id] = run
            except (KeyError, TypeError, ValueError):
                continue


class KnowledgeGraphStore:
    """A bounded local graph with deterministic relevance ranking."""

    NODE_KINDS = {
        "project",
        "note",
        "research",
        "conversation",
        "document",
        "code",
        "symbol",
        "plugin",
        "preference",
        "visualization",
        "simulation",
    }

    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "knowledge.db"
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.path,
            timeout=10,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def add_node(
        self,
        kind: str,
        title: str,
        content: str,
        *,
        project_id: str = "",
        metadata: dict[str, Any] | None = None,
        node_id: str = "",
    ) -> KnowledgeNode:
        clean_kind = kind.strip().casefold()
        if clean_kind not in self.NODE_KINDS:
            raise ValueError(f"Unsupported knowledge node type: {kind}")
        clean_title = _redact(str(title).strip())[:500]
        clean_content = _redact(str(content).strip())[:250_000]
        if not clean_title and not clean_content:
            raise ValueError("Knowledge nodes require a title or content.")
        clean_metadata = self._safe_metadata(metadata or {})
        identifier = node_id.strip() or uuid.uuid4().hex
        now = _utc_now()
        with self._lock, self._connection:
            previous = self._connection.execute(
                "SELECT created_at FROM nodes WHERE node_id = ?",
                (identifier,),
            ).fetchone()
            created = str(previous["created_at"]) if previous else now
            self._connection.execute(
                """
                INSERT INTO nodes (
                    node_id, kind, title, content, project_id, metadata,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    kind=excluded.kind,
                    title=excluded.title,
                    content=excluded.content,
                    project_id=excluded.project_id,
                    metadata=excluded.metadata,
                    updated_at=excluded.updated_at
                """,
                (
                    identifier,
                    clean_kind,
                    clean_title,
                    clean_content,
                    str(project_id)[:200],
                    json.dumps(clean_metadata, ensure_ascii=False),
                    created,
                    now,
                ),
            )
        return KnowledgeNode(
            identifier,
            clean_kind,
            clean_title,
            clean_content,
            str(project_id)[:200],
            clean_metadata,
            created,
            now,
        )

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        *,
        weight: float = 1.0,
    ) -> KnowledgeEdge:
        clean_relation = re.sub(r"[^a-z0-9_.-]+", "_", relation.casefold()).strip("_")
        if not clean_relation:
            raise ValueError("Knowledge edges require a relation.")
        clean_weight = max(0.0, min(float(weight), 100.0))
        with self._lock, self._connection:
            count = self._connection.execute(
                "SELECT COUNT(*) AS total FROM nodes WHERE node_id IN (?, ?)",
                (source_id, target_id),
            ).fetchone()["total"]
            if count != 2 and source_id != target_id:
                raise KeyError("Both knowledge nodes must exist.")
            if source_id == target_id:
                count = self._connection.execute(
                    "SELECT COUNT(*) AS total FROM nodes WHERE node_id = ?",
                    (source_id,),
                ).fetchone()["total"]
                if count != 1:
                    raise KeyError(source_id)
            self._connection.execute(
                """
                INSERT INTO edges(source_id, target_id, relation, weight)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation)
                DO UPDATE SET weight=excluded.weight
                """,
                (source_id, target_id, clean_relation, clean_weight),
            )
        return KnowledgeEdge(source_id, target_id, clean_relation, clean_weight)

    def search(
        self,
        query: str,
        *,
        project_id: str = "",
        kinds: Iterable[str] = (),
        limit: int = 12,
    ) -> tuple[KnowledgeNode, ...]:
        terms = _tokens(query)
        if not terms:
            return ()
        kind_values = {
            str(kind).strip().casefold()
            for kind in kinds
            if str(kind).strip().casefold() in self.NODE_KINDS
        }
        sql = "SELECT * FROM nodes"
        arguments: list[Any] = []
        filters: list[str] = []
        if project_id:
            filters.append("(project_id = ? OR project_id = '')")
            arguments.append(str(project_id)[:200])
        if kind_values:
            placeholders = ",".join("?" for _ in kind_values)
            filters.append(f"kind IN ({placeholders})")
            arguments.extend(sorted(kind_values))
        if filters:
            sql += " WHERE " + " AND ".join(filters)
        sql += " ORDER BY updated_at DESC LIMIT 5000"
        with self._lock:
            rows = self._connection.execute(sql, arguments).fetchall()
        ranked: list[KnowledgeNode] = []
        for row in rows:
            title_tokens = _tokens(str(row["title"]))
            content_tokens = _tokens(str(row["content"]))
            overlap = terms & (title_tokens | content_tokens)
            if not overlap:
                continue
            score = (
                len(terms & title_tokens) * 5.0
                + len(terms & content_tokens) * 2.0
                + (1.0 if project_id and row["project_id"] == project_id else 0.0)
            ) / max(1, len(terms))
            ranked.append(self._row_to_node(row, score))
        ranked.sort(key=lambda item: (-item.score, item.title.casefold()))
        return tuple(ranked[: max(1, min(int(limit), MAX_KNOWLEDGE_RESULTS))])

    def related(
        self,
        node_id: str,
        *,
        relation: str = "",
        limit: int = 20,
    ) -> tuple[tuple[KnowledgeEdge, KnowledgeNode], ...]:
        query = """
            SELECT e.source_id, e.target_id, e.relation, e.weight, n.*
            FROM edges e
            JOIN nodes n ON n.node_id = CASE
                WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END
            WHERE (e.source_id = ? OR e.target_id = ?)
        """
        arguments: list[Any] = [node_id, node_id, node_id]
        if relation:
            query += " AND e.relation = ?"
            arguments.append(relation.casefold())
        query += " ORDER BY e.weight DESC LIMIT ?"
        arguments.append(max(1, min(int(limit), 100)))
        with self._lock:
            rows = self._connection.execute(query, arguments).fetchall()
        return tuple(
            (
                KnowledgeEdge(
                    str(row["source_id"]),
                    str(row["target_id"]),
                    str(row["relation"]),
                    float(row["weight"]),
                ),
                self._row_to_node(row),
            )
            for row in rows
        )

    def index_project(self, index: ProjectIndex) -> dict[str, int]:
        project_id = hashlib.sha256(index.root.encode("utf-8")).hexdigest()[:24]
        project = self.add_node(
            "project",
            Path(index.root).name,
            json.dumps(
                {
                    "languages": index.languages,
                    "frameworks": index.frameworks,
                    "dependencies": index.dependencies,
                    "buildSystems": index.build_systems,
                    "entryPoints": index.entry_points,
                },
                ensure_ascii=False,
            ),
            project_id=project_id,
            metadata={"root": index.root, "truncated": index.truncated},
            node_id=f"project:{project_id}",
        )
        files = 0
        symbols = 0
        for item in index.files[:2_000]:
            file_id = "code:" + hashlib.sha256(
                f"{project_id}:{item.path}".encode("utf-8")
            ).hexdigest()[:32]
            file_node = self.add_node(
                "code",
                item.path,
                f"{item.language} {' '.join(item.imports[:100])}",
                project_id=project_id,
                metadata={
                    "path": item.path,
                    "language": item.language,
                    "digest": item.digest,
                    "size": item.size,
                },
                node_id=file_id,
            )
            self.add_edge(project.node_id, file_node.node_id, "contains")
            files += 1
            for symbol in item.symbols[:100]:
                symbol_id = "symbol:" + hashlib.sha256(
                    f"{file_id}:{symbol.kind}:{symbol.name}:{symbol.line}".encode("utf-8")
                ).hexdigest()[:32]
                symbol_node = self.add_node(
                    "symbol",
                    symbol.name,
                    f"{symbol.kind} in {symbol.file}:{symbol.line}",
                    project_id=project_id,
                    metadata=asdict(symbol),
                    node_id=symbol_id,
                )
                self.add_edge(file_node.node_id, symbol_node.node_id, "declares")
                symbols += 1
        return {"projects": 1, "files": files, "symbols": symbols}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT kind, COUNT(*) AS total FROM nodes GROUP BY kind"
            ).fetchall()
            edges = self._connection.execute(
                "SELECT COUNT(*) AS total FROM edges"
            ).fetchone()["total"]
            size = self.path.stat().st_size if self.path.exists() else 0
        kinds = {str(row["kind"]): int(row["total"]) for row in rows}
        return {
            "nodes": sum(kinds.values()),
            "edges": int(edges),
            "kinds": kinds,
            "bytes": size,
        }

    def export(self, path: str | os.PathLike[str]) -> Path:
        target = Path(path).expanduser().resolve()
        with self._lock:
            nodes = [
                self._row_to_node(row).to_dict()
                for row in self._connection.execute(
                    "SELECT * FROM nodes ORDER BY updated_at DESC"
                ).fetchall()
            ]
            edges = [
                {
                    "source_id": row["source_id"],
                    "target_id": row["target_id"],
                    "relation": row["relation"],
                    "weight": row["weight"],
                }
                for row in self._connection.execute(
                    "SELECT * FROM edges ORDER BY source_id, target_id"
                ).fetchall()
            ]
        _atomic_json_write(
            target,
            {
                "version": 1,
                "exportedAt": _utc_now(),
                "nodes": nodes,
                "edges": edges,
            },
        )
        return target

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL NOT NULL,
                    PRIMARY KEY(source_id, target_id, relation),
                    FOREIGN KEY(source_id) REFERENCES nodes(node_id) ON DELETE CASCADE,
                    FOREIGN KEY(target_id) REFERENCES nodes(node_id) ON DELETE CASCADE
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS nodes_project ON nodes(project_id)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS nodes_kind ON nodes(kind)"
            )

    @staticmethod
    def _safe_metadata(value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        return json.loads(_redact(encoded)) if len(encoded) <= 100_000 else {
            "truncated": True
        }

    @staticmethod
    def _row_to_node(row: sqlite3.Row, score: float = 0.0) -> KnowledgeNode:
        try:
            metadata = json.loads(str(row["metadata"]))
        except (TypeError, ValueError):
            metadata = {}
        return KnowledgeNode(
            str(row["node_id"]),
            str(row["kind"]),
            str(row["title"]),
            str(row["content"]),
            str(row["project_id"]),
            metadata if isinstance(metadata, dict) else {},
            str(row["created_at"]),
            str(row["updated_at"]),
            score,
        )


class ProjectWorkflowEngine:
    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self.path = self.directory / "project-workflows.json"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            data = {"workflows": []}
        self._workflows = {
            str(item.get("workflowId")): item
            for item in data.get("workflows", ())
            if isinstance(item, dict) and item.get("workflowId")
        }
        self._approvals: dict[str, tuple[str, str]] = {}

    def plan_feature(self, project_root: str, request: str) -> dict[str, Any]:
        root = Path(project_root).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        if not request.strip():
            raise ValueError("A feature request is required.")
        workflow_id = uuid.uuid4().hex
        stages = [
            self._stage("plan", "Analyze feature and project context", False),
            self._stage("preview", "Generate and display multi-file diff", False),
            self._stage("apply", "Apply approved source changes", True),
            self._stage("build", "Run the detected build", False),
            self._stage("test", "Run focused and project tests", False),
            self._stage("debug", "Diagnose and retry verified failures", False),
            self._stage("document", "Update documentation and changelog", True),
            self._stage("memory", "Record verified project knowledge", False),
        ]
        workflow = {
            "workflowId": workflow_id,
            "root": str(root),
            "request": request.strip()[:20_000],
            "state": "planned",
            "createdAt": _utc_now(),
            "updatedAt": _utc_now(),
            "stages": stages,
        }
        with self._lock:
            self._workflows[workflow_id] = workflow
            self._save()
        return json.loads(json.dumps(workflow))

    def update_stage(
        self,
        workflow_id: str,
        stage_id: str,
        state: str,
        *,
        result: dict[str, Any] | None = None,
        approval_token: str = "",
    ) -> dict[str, Any]:
        allowed = {
            "pending",
            "waiting_approval",
            "running",
            "completed",
            "failed",
            "cancelled",
        }
        if state not in allowed:
            raise ValueError(f"Unsupported workflow state: {state}")
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                raise KeyError(workflow_id)
            stage = next(
                (item for item in workflow["stages"] if item["stageId"] == stage_id),
                None,
            )
            if stage is None:
                raise KeyError(stage_id)
            if stage["requiresApproval"] and state == "running":
                approved = self._approvals.pop(approval_token, None)
                if approved != (workflow_id, stage_id):
                    raise PermissionError(
                        "Destructive stages require exact one-use approval."
                    )
            stage["state"] = state
            stage["result"] = dict(result or {})
            stage["updatedAt"] = _utc_now()
            states = {item["state"] for item in workflow["stages"]}
            if states <= {"completed"}:
                workflow["state"] = "completed"
            elif "failed" in states:
                workflow["state"] = "failed"
            elif "running" in states:
                workflow["state"] = "running"
            elif "waiting_approval" in states:
                workflow["state"] = "waiting_approval"
            workflow["updatedAt"] = _utc_now()
            self._save()
            return json.loads(json.dumps(workflow))

    def request_stage_approval(self, workflow_id: str, stage_id: str) -> str:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if workflow is None:
                raise KeyError(workflow_id)
            stage = next(
                (item for item in workflow["stages"] if item["stageId"] == stage_id),
                None,
            )
            if stage is None:
                raise KeyError(stage_id)
            if not stage["requiresApproval"]:
                raise ValueError("This workflow stage does not require approval.")
            token = uuid.uuid4().hex
            self._approvals[token] = (workflow_id, stage_id)
            return token

    def recent(self, limit: int = 20) -> tuple[dict[str, Any], ...]:
        with self._lock:
            values = sorted(
                self._workflows.values(),
                key=lambda item: str(item.get("updatedAt", "")),
                reverse=True,
            )
            return tuple(json.loads(json.dumps(item)) for item in values[:limit])

    @staticmethod
    def _stage(stage_id: str, title: str, destructive: bool) -> dict[str, Any]:
        return {
            "stageId": stage_id,
            "title": title,
            "requiresApproval": destructive,
            "state": "waiting_approval" if destructive else "pending",
            "result": {},
            "updatedAt": _utc_now(),
        }

    def _save(self) -> None:
        _atomic_json_write(
            self.path,
            {"version": 1, "workflows": list(self._workflows.values())},
        )


class ProjectDashboardService:
    def __init__(
        self,
        knowledge: KnowledgeGraphStore,
        git_service: Any,
        *,
        indexer: ProjectIndexer | None = None,
    ):
        self.knowledge = knowledge
        self.git = git_service
        self.indexer = indexer or ProjectIndexer()
        self._cache: dict[str, tuple[float, ProjectDashboard]] = {}
        self._lock = threading.RLock()

    def build(
        self,
        root: str,
        *,
        workspace: Any = None,
        runs: Iterable[PlatformRun] = (),
        performance: dict[str, Any] | None = None,
        refresh: bool = False,
    ) -> ProjectDashboard:
        target = Path(root).expanduser().resolve()
        if not target.is_dir():
            raise NotADirectoryError(str(target))
        key = os.path.normcase(str(target))
        with self._lock:
            cached = self._cache.get(key)
            if cached and not refresh and time.monotonic() - cached[0] < 5:
                return cached[1]
        index = self.indexer.build(target)
        project_id = hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:24]
        git = self.git.inspect(target)
        tasks = tuple(
            {
                "runId": run.run_id,
                "request": run.request,
                "state": run.state.value,
                "progress": run.progress,
            }
            for run in runs
            if not run.project_root
            or os.path.normcase(run.project_root) == os.path.normcase(str(target))
        )[:50]
        memory = tuple(
            node.to_dict()
            for node in self.knowledge.search(
                target.name,
                project_id=project_id,
                limit=20,
            )
        )
        dashboard = ProjectDashboard(
            root=str(target),
            name=target.name,
            overview={
                "files": len(index.files),
                "languages": index.languages,
                "frameworks": index.frameworks,
                "entryPoints": index.entry_points,
                "assets": len(index.assets),
                "truncated": index.truncated,
                "warnings": index.warnings,
            },
            tasks=tasks,
            timeline=tuple(git.get("timeline", ())),
            architecture={
                "frameworks": index.frameworks,
                "buildSystems": index.build_systems,
                "entryPoints": index.entry_points,
                "configuration": index.configuration,
            },
            dependencies=index.dependencies,
            git=git,
            recent_commits=tuple(git.get("commits", ())),
            issues=self._issues(target, index),
            open_files=tuple(
                str(item)
                for item in getattr(workspace, "open_editors", ())
            )[:50],
            memory=memory,
            renderer_status=str(
                getattr(workspace, "renderer_status", "idle")
            ),
            build_status=str(getattr(workspace, "build_status", "unknown")),
            test_results=tuple(
                item
                for item in getattr(workspace, "benchmarks", ())
                if isinstance(item, dict)
            )[-50:],
            performance=dict(performance or {}),
            generated_at=_utc_now(),
        )
        with self._lock:
            self._cache[key] = (time.monotonic(), dashboard)
        return dashboard

    @staticmethod
    def _issues(root: Path, index: ProjectIndex) -> tuple[dict[str, Any], ...]:
        issues: list[dict[str, Any]] = []
        marker = re.compile(r"\b(TODO|FIXME|HACK|BUG)\b[:\s-]*(.*)", re.IGNORECASE)
        for item in index.files:
            if len(issues) >= MAX_PROJECT_ISSUES or not item.digest:
                break
            path = root / item.path
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, 1):
                match = marker.search(line)
                if not match:
                    continue
                issues.append(
                    {
                        "kind": match.group(1).upper(),
                        "path": item.path,
                        "line": line_number,
                        "message": match.group(2).strip()[:500],
                    }
                )
                if len(issues) >= MAX_PROJECT_ISSUES:
                    break
        return tuple(issues)


class UnifiedPlatformOrchestrator:
    """Coordinates Phase 7 services while keeping execution in verified subsystems."""

    def __init__(
        self,
        directory: str | os.PathLike[str],
        agent: AgentOrchestrator,
        *,
        git_service: Any,
        logger: Callable[..., Any] | None = None,
    ):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.agent = agent
        self.logger = logger
        self.knowledge = KnowledgeGraphStore(self.directory / "knowledge")
        self.multi_agent = MultiAgentCoordinator(self.directory / "agents")
        self.workflows = ProjectWorkflowEngine(self.directory / "projects")
        self.dashboard = ProjectDashboardService(self.knowledge, git_service)

    def prepare(
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
    ) -> tuple[AgentRequestContext, PlatformRun]:
        project_id = (
            hashlib.sha256(
                str(Path(project_root).resolve()).encode("utf-8")
            ).hexdigest()[:24]
            if project_root and Path(project_root).is_dir()
            else ""
        )
        relevant = self.knowledge.search(request, project_id=project_id, limit=8)
        knowledge_context = "\n".join(
            f"[{item.kind}] {item.title}: {item.content[:1_200]}"
            for item in relevant
        )
        combined_context = persistent_context
        if knowledge_context:
            combined_context += (
                "\n\nRelevant local knowledge graph context:\n" + knowledge_context
            )
        context = self.agent.prepare_request(
            request,
            history=history,
            project_root=project_root,
            selected_model=selected_model,
            available_models=available_models,
            capabilities=capabilities,
            persistent_context=combined_context,
            context_tokens=context_tokens,
        )
        run = self.multi_agent.create_run(context, project_root=project_root)
        self._log(
            "INFO",
            "Unified platform request prepared.",
            {
                "requestId": context.request_id,
                "runId": run.run_id,
                "agents": [item.role.value for item in run.work_items],
                "knowledgeResults": len(relevant),
            },
        )
        return context, run

    def remember_interaction(
        self,
        request: str,
        response: str,
        *,
        project_root: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeNode:
        project_id = (
            hashlib.sha256(
                str(Path(project_root).resolve()).encode("utf-8")
            ).hexdigest()[:24]
            if project_root and Path(project_root).is_dir()
            else ""
        )
        return self.knowledge.add_node(
            "conversation",
            request[:180],
            f"User: {request}\nMORICE: {response}",
            project_id=project_id,
            metadata=metadata,
        )

    def finish(
        self,
        run_id: str,
        *,
        success: bool,
        summary: str = "",
    ) -> PlatformRun | None:
        if not run_id:
            return None
        run = self.multi_agent.finalize(
            run_id,
            success=success,
            summary=summary,
        )
        self._log(
            "INFO" if success else "ERROR",
            "Unified platform request completed." if success else "Unified platform request failed.",
            {
                "requestId": run.request_id,
                "runId": run.run_id,
                "state": run.state.value,
                "progress": run.progress,
            },
        )
        return run

    def index_project(self, root: str) -> dict[str, int]:
        index = ProjectIndexer().build(root)
        return self.knowledge.index_project(index)

    def snapshot(
        self,
        *,
        project_root: str = "",
        workspace: Any = None,
        performance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dashboard: dict[str, Any] = {}
        dashboard_error = ""
        if project_root and Path(project_root).is_dir():
            try:
                dashboard = self.dashboard.build(
                    project_root,
                    workspace=workspace,
                    runs=self.multi_agent.recent(100),
                    performance=performance,
                ).to_dict()
            except (OSError, RuntimeError, ValueError) as exc:
                dashboard_error = str(exc)
        return {
            "orchestrator": self.multi_agent.snapshot(),
            "knowledge": self.knowledge.stats(),
            "project": dashboard,
            "projectError": dashboard_error,
            "workflows": list(self.workflows.recent(20)),
        }

    def shutdown(self) -> None:
        self.knowledge.close()

    def _log(self, level: str, message: str, metadata: dict[str, Any]) -> None:
        if self.logger:
            self.logger(
                level,
                message,
                category="platform",
                metadata=metadata,
            )
