"""Validated deterministic decomposition, with an optional planner interface."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..kernel import DependencyPolicy, TaskGraph, TaskNode
from ..kernel.contracts import new_id


class WorkflowPlanner:
    def documents(self, paths, *, goal="Compare local documents and verify the evidence."):
        paths = tuple(dict.fromkeys(paths))
        if len(paths) < 2:
            raise ValueError("Document comparison requires at least two sources.")
        tasks = [TaskNode("filesystem.read", {"path": str(Path(path).resolve())}, task_id=new_id(),
            description=f"Inspect {Path(path).name}", constraints={"role": "researcher"}) for path in dict.fromkeys(paths)]
        reads = tuple(t.task_id for t in tasks)
        compare = TaskNode("agent.compare", dependencies=reads, description="Compare source evidence", constraints={"role": "analyst"})
        verify = TaskNode("agent.verify", dependencies=(compare.task_id,), description="Read sources independently", constraints={"role": "verifier"})
        final = TaskNode("agent.synthesize", dependencies=(compare.task_id, verify.task_id), dependency_policy=DependencyPolicy.COMPLETED,
            description="Report verified findings", constraints={"role": "coordinator"})
        return TaskGraph(tuple(tasks+[compare, verify, final]), goal=goal)

    def coding(self, candidates, *, goal="Apply approved candidates, run their tests, and verify artifacts."):
        if not candidates:
            raise ValueError("Coding workflow requires concrete candidate patches and commands.")
        tasks, branches, artifacts = [], [], []
        for candidate in candidates:
            root = str(Path(candidate["root"]).resolve())
            changes = candidate["changes"]
            coder = TaskNode("filesystem.apply_patch", {"root": root, "changes": changes},
                description=f"Apply {candidate['name']}", constraints={"role": "coder"})
            tester = TaskNode("terminal.run", {"cwd": root, "command": candidate["command"], "timeout": 60},
                dependencies=(coder.task_id,), description=f"Test {candidate['name']}", constraints={"role": "tester"}, timeout=70)
            tasks.extend((coder, tester))
            branches.append(tester.task_id)
            artifacts.extend({"path": str(Path(root) / change["path"]), "content": change["content"]} for change in changes)
        verify = TaskNode("agent.verify", {"artifacts": artifacts}, dependencies=tuple(branches),
            dependency_policy=DependencyPolicy.COMPLETED, description="Inspect test evidence and generated files", constraints={"role": "verifier"})
        final = TaskNode("agent.synthesize", dependencies=tuple(branches)+(verify.task_id,), dependency_policy=DependencyPolicy.COMPLETED,
            description="Report which candidates actually passed", constraints={"role": "coordinator"})
        return TaskGraph(tuple(tasks+[verify, final]), goal=goal)

    def project_checks(self, root, *, goal="Check project sources and repository state in parallel."):
        root = str(Path(root).resolve())
        tasks = [TaskNode("project.verify", {"root": root}, description="Validate project source", constraints={"role": "tester"}),
            TaskNode("git.status", {"root": root}, description="Inspect repository state", constraints={"role": "researcher"})]
        # This is a source check, not execution of the project's test suite.
        return TaskGraph(tuple(tasks), goal=goal)

    def route(self, goal, context):
        if re.fullmatch(r"(?:check|inspect) (?:this |the )?project in parallel[.!? ]*", goal.casefold()) and context.project_id:
            return self.project_checks(context.project_id, goal=goal)
        if re.search(r"\b(?:compare|analyze)\b", goal, re.I):
            paths = re.findall(r'"([^"\n]+)"', goal)
            if len(paths) >= 2 and all(Path(p).is_file() for p in paths):
                return self.documents(paths, goal=goal)
        return None  # preserve existing single-agent path on unsupported plans


def parallel_decision(graph):
    independent = sum(not task.dependencies for task in graph.tasks)
    verification = any(task.capability_requirement == "agent.verify" for task in graph.tasks)
    return len(graph.tasks) > 1 and (independent > 1 or verification)


def semantic_key(task):
    return json.dumps({"capability": task.capability_requirement, "inputs": task.inputs,
        "node_id": task.constraints.get("node_id", "local"),
        "dependencies": sorted(task.dependencies), "role": task.constraints.get("role"),
        "approach": task.constraints.get("approach")}, sort_keys=True, allow_nan=False)
