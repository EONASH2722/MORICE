"""Structured reference resolution, sharing the existing working memory."""
from __future__ import annotations

from ..unified_intelligence import ContextEntity, ReferenceResolution, WorkingMemory
from .contracts import ExecutionContext


class ContextResolver:
    def __init__(self, memory: WorkingMemory | None = None):
        self.memory = memory if memory is not None else WorkingMemory()

    def observe(self, entity: ContextEntity) -> None:
        self.memory.observe(entity)

    def resolve(self, reference: str, *, expected_kinds: tuple[str, ...] = (), material_action: bool = False) -> ReferenceResolution:
        clean = " ".join(reference.casefold().split())
        generic = {"this", "that", "it", "the other one"}
        inferred = {
            "my phone": ("device",), "the current project": ("project",),
            "the file we opened": ("file",), "the graph": ("graph",),
            "the previous simulation": ("simulation",),
        }
        kinds = expected_kinds or inferred.get(clean, ())
        resolution = self.memory.resolve(reference, expected_kinds=kinds)
        # Salience alone must not resolve an explicit unknown target to an
        # unrelated entity. The existing memory also serves semantic planners;
        # the kernel action boundary applies this stricter deterministic check.
        if clean not in generic and resolution.entity is not None:
            entity = resolution.entity
            names = {entity.label.casefold(), *(a.casefold() for a in entity.aliases)}
            if not any(clean == name or clean in name or name in clean for name in names):
                return ReferenceResolution(reference, None, 0.0, resolution.alternatives, True)
        # The caller must request clarification whenever this flag is true.
        return resolution

    def capture(self, *, desktop=None, project_id: str = "", **fields) -> ExecutionContext:
        active_files = fields.pop("active_files", ())
        if desktop is not None:
            path = str(getattr(desktop, "last_file", ""))
            if path:
                active_files = tuple(dict.fromkeys((*active_files, path)))
            fields.setdefault("active_window", str(getattr(desktop, "active_application", "")))
        entities = [("project", project_id, ("the current project", "this project"))] if project_id else []
        entities.extend(("file", path, ("the file we opened", "this", "it")) for path in active_files)
        for kind, label, aliases in entities:
            self.observe(ContextEntity(f"{kind}:{label}", kind, label, aliases, "runtime", {"path": label}, active=True))
        return ExecutionContext(project_id=project_id, active_files=tuple(active_files), **fields)
