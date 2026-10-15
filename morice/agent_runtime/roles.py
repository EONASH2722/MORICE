"""Functional roles authorize capabilities, never implement their tools."""
from __future__ import annotations

import fnmatch
import threading
from dataclasses import replace

from .contracts import AgentRole, ContextPolicy


class RoleRegistry:
    def __init__(self):
        self._roles = {}
        self._lock = threading.RLock()

    def register(self, role: AgentRole):
        if not role.role_id or not role.allowed_capabilities:
            raise ValueError("Roles require an id and allowed capabilities.")
        with self._lock:
            if role.role_id in self._roles:
                raise ValueError("Duplicate role id.")
            self._roles[role.role_id] = role

    def resolve(self, role_id: str) -> AgentRole:
        with self._lock:
            role = self._roles.get(role_id)
            if role is None or not role.enabled:
                raise ValueError(f"Role unavailable: {role_id}")
            return role

    def disable(self, role_id: str):
        with self._lock:
            self._roles[role_id] = replace(self.resolve(role_id), enabled=False)

    def allows(self, role_id, capability):
        return any(fnmatch.fnmatchcase(capability, pattern) for pattern in self.resolve(role_id).allowed_capabilities)

    def select(self, task):
        requested = task.constraints.get("role")
        if requested:
            role = self.resolve(requested)
        else:
            preferred = {"filesystem.read": "researcher", "filesystem.apply_patch": "coder",
                "filesystem.preview_patch": "coder", "terminal.run": "tester", "project.verify": "verifier",
                "python.calculate": "analyst", "agent.compare": "analyst", "agent.verify": "verifier", "project.inspect": "verifier",
                "agent.synthesize": "coordinator", "browser.search": "browser", "vision.inspect": "vision",
                "simulation.run": "simulation", "research.ingest": "researcher", "research.simulate": "simulation",
                "research.calculate": "analyst", "research.statistics": "analyst", "research.symbolic": "analyst",
                "research.cad": "analyst", "research.verify": "verifier", "research.model_compare": "analyst",
                "research.trajectory": "simulation", "research.material": "simulation"}
            role = self.resolve("vision" if task.capability_requirement.startswith("media.") else preferred.get(task.capability_requirement, "researcher"))
        if not self.allows(role.role_id, task.capability_requirement):
            raise ValueError(f"Role {role.role_id} cannot use {task.capability_requirement}.")
        return role

    def all(self):
        with self._lock:
            return tuple(self._roles.values())


def default_roles():
    registry = RoleRegistry()
    definitions = (
        ("coordinator", "Coordinator", ("agent.synthesize",), ("planning", "structured_output"), ContextPolicy()),
        ("researcher", "Researcher", ("filesystem.read", "filesystem.search", "project.index", "git.*", "agent.reason", "kernel.echo", "device.status", "file.receive", "file.send", "research.ingest", "research.refresh_source", "connector.*", "security.scan", "notification.publish"), ("long_context",), ContextPolicy(True, True)),
        ("coder", "Coder", ("filesystem.read", "filesystem.preview_patch", "filesystem.apply_patch", "project.index", "agent.reason"), ("coding",), ContextPolicy(True, True)),
        ("tester", "Tester", ("terminal.run", "process.start", "process.stop", "project.verify", "filesystem.read"), (), ContextPolicy(True, True)),
        ("analyst", "Analyst", ("python.calculate", "agent.compare", "graph.render", "agent.reason", "research.calculate", "research.statistics", "research.symbolic", "research.cad", "research.model_compare", "security.scan"), ("reasoning",), ContextPolicy()),
        ("verifier", "Verifier", ("agent.verify", "artifact.verify", "project.verify", "project.inspect", "filesystem.read", "terminal.run", "agent.reason", "research.verify", "security.*"), ("reasoning",), ContextPolicy(True, True)),
        ("browser", "Web Researcher", ("browser.*", "agent.reason"), ("long_context",), ContextPolicy()),
        ("vision", "Vision Analyst", ("vision.inspect", "vision.screen_observe", "screenshot.capture", "camera.capture", "camera.stream", "screen.capture", "media.*"), ("vision",), ContextPolicy(False, True)),
        ("simulation", "Simulation Worker", ("simulation.run", "python.calculate", "graph.render", "research.simulate", "research.trajectory", "research.material"), (), ContextPolicy()),
    )
    for name, display, allowed, models, policy in definitions:
        registry.register(AgentRole(name, display, f"{display} using registered MORICE capabilities.", allowed,
            preferred_capabilities=tuple(cap for cap in allowed if "*" not in cap),
            model_requirements=models, context_policy=policy,
            resource_profile={"coder": ("DISK",), "tester": ("CPU",), "researcher": ("IO",),
                "browser": ("IO",), "simulation": ("CPU",), "vision": ("GPU",)}.get(name, ()),
            result_schema={"type": "object", "required": ["claims", "evidence", "sources", "uncertainties", "open_questions"]}
                if name in {"researcher", "browser"} else {"type": "object"}))
    return registry
