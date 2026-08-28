from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .project_workflows import (
    ArtifactVerification,
    ProjectWorkflow,
    command_text,
    discover_project_workflow,
    verify_project_artifacts,
)


@dataclass(frozen=True)
class CommandEvidence:
    stage: str
    command: tuple[str, ...]
    attempted: bool
    success: bool
    exit_code: int | None
    duration_ms: float
    output: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "command": list(self.command),
            "commandText": command_text(self.command),
        }


@dataclass
class BuildSession:
    session_id: str
    root: str
    goal: str
    target_state: str
    workflow: dict[str, Any]
    state: str = "planned"
    milestone: str = "inspect"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    attempts: int = 0
    changed_files: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutonomousBuilder:
    """Engine-neutral project state, execution, observation, and verification loop."""

    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def plan(self, root: str, goal: str) -> BuildSession:
        project = Path(root).expanduser().resolve()
        if not project.is_dir():
            raise NotADirectoryError(str(project))
        clean_goal = " ".join(str(goal or "").split())
        if not clean_goal:
            raise ValueError("A project goal is required.")
        workflow = discover_project_workflow(str(project), clean_goal)
        session = BuildSession(
            uuid.uuid4().hex,
            str(project),
            clean_goal[:20_000],
            f"The requested outcome is present and verified: {clean_goal[:1_000]}",
            workflow.to_dict(),
        )
        self._event(
            session,
            "inspect",
            f"Detected {workflow.label} from {workflow.detected_from}.",
            {"evidence": list(workflow.evidence), "tool": workflow.tool_path},
        )
        self._save(session)
        return session

    def verify(
        self,
        session: BuildSession,
        expected_files: Mapping[str, str],
        *,
        run_build: bool = True,
        run_tests: bool = True,
        timeout: float = 180.0,
    ) -> tuple[ArtifactVerification, tuple[CommandEvidence, ...]]:
        workflow = discover_project_workflow(session.root, session.goal)
        session.state = "verifying"
        session.milestone = "verify-files"
        session.attempts += 1
        artifacts = verify_project_artifacts(session.root, expected_files)
        session.changed_files = list(artifacts.files)
        self._event(
            session,
            "verify-files",
            artifacts.summary(),
            {
                "expected": artifacts.expected,
                "verified": artifacts.verified,
                "success": artifacts.success,
            },
        )
        evidence: list[CommandEvidence] = []
        if artifacts.success and run_build:
            evidence.append(self._run(workflow, "build", workflow.build_command, timeout))
        if artifacts.success and run_tests:
            evidence.append(self._run(workflow, "test", workflow.test_command, timeout))
        material = [item for item in evidence if item.attempted]
        command_success = all(item.success for item in material)
        session.evidence.extend(item.to_dict() for item in evidence)
        for item in evidence:
            self._event(
                session,
                item.stage,
                (
                    f"{item.stage.title()} passed."
                    if item.success
                    else item.reason or f"{item.stage.title()} failed."
                ),
                item.to_dict(),
            )
        if not artifacts.success or not command_success:
            session.state = "needs-repair"
            session.milestone = "diagnose"
        elif material:
            session.state = "verified"
            session.milestone = "complete"
        else:
            session.state = "files-verified"
            session.milestone = "runtime-verification-unavailable"
        session.updated_at = time.time()
        self._save(session)
        return artifacts, tuple(evidence)

    def repair_loop(
        self,
        session: BuildSession,
        expected_files: Mapping[str, str],
        repair: Callable[[BuildSession, tuple[CommandEvidence, ...]], bool],
        *,
        max_attempts: int = 3,
        timeout: float = 180.0,
    ) -> tuple[ArtifactVerification, tuple[CommandEvidence, ...]]:
        """Retry only when a caller performs a concrete repair; never fake self-healing."""

        last_artifacts: ArtifactVerification | None = None
        last_evidence: tuple[CommandEvidence, ...] = ()
        for _ in range(max(1, min(int(max_attempts), 5))):
            last_artifacts, last_evidence = self.verify(
                session,
                expected_files,
                timeout=timeout,
            )
            if session.state in {"verified", "files-verified"}:
                return last_artifacts, last_evidence
            if not repair(session, last_evidence):
                break
            self._event(session, "repair", "A concrete repair was applied; retesting.")
        assert last_artifacts is not None
        return last_artifacts, last_evidence

    def load(self, session_id: str) -> BuildSession | None:
        path = self.directory / f"{session_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return BuildSession(**value)
        except (FileNotFoundError, OSError, TypeError, ValueError):
            return None

    def _run(
        self,
        workflow: ProjectWorkflow,
        stage: str,
        command: Iterable[str],
        timeout: float,
    ) -> CommandEvidence:
        argv = tuple(str(item) for item in command if str(item))
        if not argv:
            return CommandEvidence(
                stage,
                (),
                False,
                False,
                None,
                0.0,
                reason=f"No {stage} command was detected for {workflow.label}.",
            )
        started = time.perf_counter()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(
                argv,
                cwd=workflow.root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(5.0, min(float(timeout), 900.0)),
                check=False,
                creationflags=flags,
            )
            output = completed.stdout[-40_000:]
            success = completed.returncode == 0
            return CommandEvidence(
                stage,
                argv,
                True,
                success,
                completed.returncode,
                (time.perf_counter() - started) * 1000.0,
                output,
                "" if success else f"{stage.title()} exited with code {completed.returncode}.",
            )
        except subprocess.TimeoutExpired as exc:
            output = str(exc.stdout or "")[-40_000:]
            return CommandEvidence(
                stage,
                argv,
                True,
                False,
                None,
                (time.perf_counter() - started) * 1000.0,
                output,
                f"{stage.title()} timed out.",
            )
        except OSError as exc:
            return CommandEvidence(
                stage,
                argv,
                True,
                False,
                None,
                (time.perf_counter() - started) * 1000.0,
                reason=f"{stage.title()} could not start: {exc}",
            )

    def _event(
        self,
        session: BuildSession,
        stage: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        session.events.append(
            {
                "at": time.time(),
                "stage": stage,
                "message": " ".join(str(message).split())[:2_000],
                "details": dict(details or {}),
            }
        )
        session.events = session.events[-500:]
        session.updated_at = time.time()

    def _save(self, session: BuildSession) -> None:
        target = self.directory / f"{session.session_id}.json"
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        with self._lock:
            temporary.write_text(
                json.dumps(session.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(temporary, target)


__all__ = ["AutonomousBuilder", "BuildSession", "CommandEvidence"]
