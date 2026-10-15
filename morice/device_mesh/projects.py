"""Remote project providers reuse Project Builder; no second build orchestration."""
from __future__ import annotations

import ast
import zipfile

from .transfers import file_hash


def inspect_source_archive(inbox, args, context):
    path = inbox._target(args.get("name"))
    if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Source archive is unavailable or exceeds the inspection limit.")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if not infos or len(infos) > 128 or sum(i.file_size for i in infos) > 20 * 1024 * 1024:
            raise ValueError("Archive exceeds source inspection limits.")
        count = 0
        for member in infos:
            if member.is_dir():
                continue
            inbox._target(member.filename)  # Same secret/traversal/Windows-path guard; never extract.
            if member.file_size > 2 * 1024 * 1024:
                raise ValueError("Archive member exceeds source inspection limit.")
            if member.filename.endswith(".py"):
                ast.parse(archive.read(member).decode("utf-8"), filename=member.filename)
                count += 1
        if archive.testzip() is not None or count == 0:
            raise ValueError("Not a verified Python source archive.")
    return {"verified": True, "source_syntax_valid": True, "python_files": count,
            "size": path.stat().st_size, "sha256": file_hash(path)}


def bind_reviewed_builder(mesh, builder, session, *, authorize):
    if builder.kernel is not mesh.kernel or not callable(authorize):
        raise ValueError("A node must use its existing builder and permission authority.")
    def checked(args):
        if set(args) != {"session_id"} or args["session_id"] != session.session_id:
            raise PermissionError("Only this explicitly reviewed build session is exposed.")
    def execute(args, context):
        checked(args)
        value = builder.resume(session.session_id, context=context, authorize=authorize)
        return {"verified": value.success, "session_id": value.session_id, "health": value.health}
    def observe(args, context):
        checked(args)
        value = builder._sessions.get(session.session_id)
        from ..project_build.workspace import safe_path
        from pathlib import Path
        current = bool(value and value.success)
        if current:
            current = all((path := safe_path(value.project_root, name)).is_file() and file_hash(path) == wanted for name, wanted in value.applied_changes.items())
            current = current and all((path := Path(artifact["path"]).resolve()).is_relative_to(Path(value.project_root).resolve()) and path.is_file() and file_hash(path) == artifact["sha256"] for artifact in value.artifacts)
        return {"verified": current, "session_id": session.session_id,
                "health": value.health if value else {}}
    from ..unified_intelligence import RiskClass
    mesh.node.register("project.build", execute, observe, risk=RiskClass.HIGH)
    return "project.build"
