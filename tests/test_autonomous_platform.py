from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from morice.agent_orchestrator import AgentOrchestrator
from morice.agent_types import IntentType
from morice.autonomous_platform import (
    KnowledgeGraphStore,
    MultiAgentCoordinator,
    ProjectDashboardService,
    ProjectWorkflowEngine,
    SpecialistAgentRegistry,
    UnifiedPlatformOrchestrator,
)
from morice.platform_services import (
    EncryptedBackupManager,
    ExactApprovalManager,
    ExportManager,
    FirstRunService,
    GitRepositoryService,
    RepairService,
    SecureVault,
    UpdateService,
)
from morice.platform_types import AgentRole, RunState, WorkItemState
from morice.updater import _apply_portable_update, run_updater


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return completed.stdout.strip()


class MultiAgentPlatformTests(unittest.TestCase):
    def test_specialists_map_intents_to_clear_roles(self):
        registry = SpecialistAgentRegistry()
        self.assertEqual(registry.role_for(IntentType.CODING), AgentRole.CODING)
        self.assertEqual(
            registry.role_for(IntentType.INTERNET_SEARCH),
            AgentRole.RESEARCH,
        )
        self.assertEqual(
            registry.role_for(IntentType.SIMULATION),
            AgentRole.SIMULATION,
        )
        self.assertEqual(len(registry.snapshot()), 12)

    def test_coordinator_tracks_approval_progress_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = AgentOrchestrator(Path(directory) / "agent")
            context = agent.prepare_request(
                "Build the project, run tests, and plot its benchmark."
            )
            coordinator = MultiAgentCoordinator(Path(directory) / "coordinator")
            run = coordinator.create_run(context, project_root=directory)
            destructive = next(item for item in run.work_items if item.destructive)
            self.assertEqual(run.state, RunState.WAITING_APPROVAL)
            self.assertEqual(destructive.state, WorkItemState.WAITING_APPROVAL)
            with self.assertRaises(PermissionError):
                coordinator.start_item(run.run_id, destructive.item_id)
            self.assertTrue(coordinator.grant_item(run.run_id, destructive.item_id))
            coordinator.start_item(run.run_id, destructive.item_id)
            coordinator.complete_item(
                run.run_id,
                destructive.item_id,
                {"error": "controlled failure"},
                verified=False,
            )
            self.assertTrue(coordinator.recover_item(run.run_id, destructive.item_id))
            coordinator.start_item(run.run_id, destructive.item_id)
            updated = coordinator.complete_item(
                run.run_id,
                destructive.item_id,
                {"summary": "verified"},
                verified=True,
            )
            self.assertGreater(updated.progress, 0)
            self.assertEqual(updated.recovery_count, 1)
            restored = MultiAgentCoordinator(Path(directory) / "coordinator")
            self.assertIsNotNone(restored.get(run.run_id))

    def test_finalize_closes_run_without_claiming_unapproved_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = AgentOrchestrator(Path(directory) / "agent")
            context = agent.prepare_request("Build the project and explain the result.")
            coordinator = MultiAgentCoordinator(Path(directory) / "coordinator")
            run = coordinator.create_run(context, project_root=directory)

            completed = coordinator.finalize(
                run.run_id,
                success=True,
                summary="The visible response was delivered.",
            )

            self.assertEqual(completed.state, RunState.COMPLETED)
            self.assertEqual(completed.progress, 100)
            destructive = [item for item in completed.work_items if item.destructive]
            self.assertTrue(destructive)
            self.assertTrue(
                all(item.state == WorkItemState.CANCELLED for item in destructive)
            )
            self.assertTrue(
                all(item.result.get("executed") is False for item in destructive)
            )
            self.assertEqual(coordinator.snapshot()["activeRuns"], 0)

    def test_unified_orchestrator_retrieves_relevant_local_knowledge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = AgentOrchestrator(root / "agent")
            git_service = GitRepositoryService()
            platform = UnifiedPlatformOrchestrator(
                root / "platform",
                base,
                git_service=git_service,
            )
            platform.knowledge.add_node(
                "note",
                "renderer cache",
                "Renderer cache is bounded to 256 MB.",
            )
            context, run = platform.prepare(
                "How is the renderer cache bounded?",
                capabilities=("graph",),
            )
            self.assertEqual(context.request_id, run.request_id)
            self.assertTrue(
                any(
                    "Renderer cache is bounded" in message["content"]
                    for message in context.conversation
                )
            )
            completed = platform.finish(
                run.run_id,
                success=True,
                summary="Knowledge answer delivered.",
            )
            self.assertIsNotNone(completed)
            self.assertEqual(completed.state, RunState.COMPLETED)
            self.assertEqual(platform.snapshot()["orchestrator"]["activeRuns"], 0)
            platform.shutdown()


class KnowledgeAndProjectTests(unittest.TestCase):
    def test_knowledge_graph_search_relations_and_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            graph = KnowledgeGraphStore(directory)
            project = graph.add_node("project", "MORICE", "desktop platform")
            note = graph.add_node(
                "note",
                "API setup",
                "api_key=super-secret-value renderer notes",
            )
            graph.add_edge(project.node_id, note.node_id, "references", weight=2)
            results = graph.search("renderer notes")
            related = graph.related(project.node_id)
            self.assertEqual(results[0].node_id, note.node_id)
            self.assertNotIn("super-secret-value", results[0].content)
            self.assertEqual(related[0][0].relation, "references")
            export = graph.export(Path(directory) / "graph.json")
            self.assertTrue(export.is_file())
            graph.close()

    def test_project_index_populates_graph_dashboard_and_issues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text(
                "import json\n# TODO: add validation\ndef launch():\n    return True\n",
                encoding="utf-8",
            )
            graph = KnowledgeGraphStore(root / ".state")
            dashboard = ProjectDashboardService(graph, GitRepositoryService()).build(
                str(root),
                refresh=True,
            )
            self.assertEqual(dashboard.overview["files"], 1)
            self.assertEqual(dashboard.overview["languages"]["Python"], 1)
            self.assertEqual(dashboard.issues[0]["kind"], "TODO")
            graph.close()

    def test_project_workflow_requires_approval_for_destructive_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = ProjectWorkflowEngine(Path(directory) / ".state")
            workflow = engine.plan_feature(directory, "Add a renderer")
            apply_stage = next(
                item for item in workflow["stages"] if item["stageId"] == "apply"
            )
            self.assertTrue(apply_stage["requiresApproval"])
            self.assertEqual(apply_stage["state"], "waiting_approval")
            with self.assertRaises(PermissionError):
                engine.update_stage(
                    workflow["workflowId"],
                    "apply",
                    "running",
                )
            token = engine.request_stage_approval(
                workflow["workflowId"],
                "apply",
            )
            engine.update_stage(
                workflow["workflowId"],
                "apply",
                "running",
                approval_token=token,
            )
            updated = engine.update_stage(
                workflow["workflowId"],
                "apply",
                "completed",
                result={"verified": True},
            )
            self.assertEqual(
                next(
                    item
                    for item in updated["stages"]
                    if item["stageId"] == "apply"
                )["state"],
                "completed",
            )


@unittest.skipUnless(bool(__import__("shutil").which("git")), "Git is unavailable")
class GitServiceTests(unittest.TestCase):
    def test_git_mutations_are_exact_approved_and_inspectable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            service = GitRepositoryService()
            init_args = {"root": str(root.resolve())}
            token = service.request("init", init_args)
            service.initialize(str(root), token)
            git(root, "config", "user.name", "MORICE Test")
            git(root, "config", "user.email", "morice@example.invalid")
            (root / "app.py").write_text("print('ready')\n", encoding="utf-8")
            commit_args = {
                "root": str(root.resolve()),
                "message": "initial",
                "paths": ("app.py",),
            }
            with self.assertRaises(PermissionError):
                service.commit(str(root), "initial", ("app.py",), "bad-token")
            token = service.request("commit", commit_args)
            snapshot = service.commit(str(root), "initial", ("app.py",), token)
            self.assertTrue(snapshot["repository"])
            self.assertFalse(snapshot["dirty"])
            self.assertEqual(snapshot["commits"][0]["subject"], "initial")
            branch_args = {"root": str(root.resolve()), "name": "feature/test"}
            token = service.request("branch", branch_args)
            snapshot = service.create_branch(str(root), "feature/test", token)
            self.assertEqual(snapshot["branch"], "feature/test")
            with self.assertRaises(PermissionError):
                service.create_branch(str(root), "feature/test-2", token)


class BackupExportUpdateTests(unittest.TestCase):
    def test_portable_release_packager_creates_valid_rooted_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "dist" / "MORICE"
            (source / "_internal").mkdir(parents=True)
            (source / "MORICE.exe").write_bytes(b"executable")
            (source / "_internal" / "runtime.dll").write_bytes(b"runtime")
            output = root / "release" / "MORICE-portable.zip"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).parents[1] / "scripts" / "package_portable.py"),
                    "--source",
                    str(source),
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            report = json.loads(completed.stdout)
            self.assertEqual(report["files"], 2)
            with zipfile.ZipFile(output, "r") as archive:
                self.assertEqual(
                    sorted(archive.namelist()),
                    ["MORICE/MORICE.exe", "MORICE/_internal/runtime.dll"],
                )
                self.assertIsNone(archive.testzip())

    def test_export_skips_detected_secret_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "notes.md").write_text("verified notes", encoding="utf-8")
            (source / ".env").write_text("API_KEY=hidden", encoding="utf-8")
            (source / "config.txt").write_text(
                "token=also-hidden-value",
                encoding="utf-8",
            )
            target = ExportManager().export_bundle(
                root / "export.zip",
                {"project": source},
            )
            with zipfile.ZipFile(target) as archive:
                names = set(archive.namelist())
            self.assertIn("project/notes.md", names)
            self.assertNotIn("project/.env", names)
            self.assertNotIn("project/config.txt", names)

    def test_update_staging_verifies_hash_and_exact_install_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "MORICE.zip"
            package.write_bytes(b"verified update")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            manifest = {
                "version": "0.7.1",
                "channel": "beta",
                "url": "https://example.invalid/MORICE.zip",
                "sha256": digest,
                "size": package.stat().st_size,
                "releaseNotes": "Phase 7",
                "publishedAt": "2026-07-29T00:00:00Z",
            }
            approvals = ExactApprovalManager()
            updates = UpdateService(root / "updates", approvals)
            staged = updates.stage_local(package, manifest)
            token = updates.request_install()
            instruction = updates.schedule_install(token)
            self.assertTrue(staged.is_file())
            self.assertEqual(
                json.loads(instruction.read_text(encoding="utf-8"))["version"],
                "0.7.1",
            )
            with self.assertRaises(PermissionError):
                updates.schedule_install(token)
            bad = dict(manifest)
            bad["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                updates.stage_local(package, bad)
            unsupported = root / "MORICE.txt"
            unsupported.write_bytes(b"not an update package")
            unsupported_manifest = dict(manifest)
            unsupported_manifest["sha256"] = hashlib.sha256(
                unsupported.read_bytes()
            ).hexdigest()
            unsupported_manifest["size"] = unsupported.stat().st_size
            with self.assertRaisesRegex(ValueError, "portable .zip"):
                updates.stage_local(unsupported, unsupported_manifest)

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_dpapi_vault_and_encrypted_backup_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = SecureVault(root / "vault")
            vault.set("api.primary", "private-value")
            self.assertEqual(vault.get("api.primary"), "private-value")
            source = root / "source"
            source.mkdir()
            (source / "notes.txt").write_text("backup data", encoding="utf-8")
            manager = EncryptedBackupManager(vault)
            backup = manager.create(root / "backup.morice", {"settings": source})
            restored = root / "restored"
            self.assertEqual(manager.restore(backup, restored), 1)
            self.assertEqual(
                (restored / "settings" / "notes.txt").read_text(encoding="utf-8"),
                "backup data",
            )

    def test_portable_updater_applies_verified_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "install"
            install.mkdir()
            (install / "MORICE.exe").write_bytes(b"old")
            package = root / "update.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("MORICE/MORICE.exe", b"new")
                archive.writestr("MORICE/_internal/version.txt", b"0.7.1")
            updates = root / "updates"
            updates.mkdir()
            instruction = updates / "pending-update.json"
            instruction.write_text(
                json.dumps(
                    {
                        "package": str(package),
                        "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
                        "version": "0.7.1",
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(run_updater(str(instruction), str(install), 0), 0)
            self.assertEqual((install / "MORICE.exe").read_bytes(), b"new")
            self.assertTrue((updates / "last-update-result.json").is_file())

    def test_portable_updater_removes_new_files_during_failed_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "install"
            install.mkdir()
            (install / "MORICE.exe").write_bytes(b"old")
            package = root / "update.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("MORICE/MORICE.exe", b"new")
                archive.writestr("MORICE/new.txt", b"new file")
                archive.writestr("MORICE/z-trigger.txt", b"fail here")

            real_replace = os.replace
            calls = 0

            def fail_third_replace(source, destination):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError("controlled replace failure")
                return real_replace(source, destination)

            with mock.patch("morice.updater.os.replace", side_effect=fail_third_replace):
                with self.assertRaisesRegex(OSError, "controlled replace failure"):
                    _apply_portable_update(
                        package,
                        install,
                        root / "rollback",
                    )

            self.assertEqual((install / "MORICE.exe").read_bytes(), b"old")
            self.assertFalse((install / "new.txt").exists())
            self.assertFalse((install / "z-trigger.txt").exists())

    def test_installer_update_waits_for_success_and_records_no_fake_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "install"
            install.mkdir()
            (install / "MORICE.exe").write_bytes(b"current")
            package = root / "MORICE-update.exe"
            package.write_bytes(b"installer")
            updates = root / "updates"
            updates.mkdir()
            instruction = updates / "pending-update.json"
            instruction.write_text(
                json.dumps(
                    {
                        "package": str(package),
                        "sha256": hashlib.sha256(
                            package.read_bytes()
                        ).hexdigest(),
                        "version": "0.7.1",
                    }
                ),
                encoding="utf-8",
            )

            completed = mock.Mock(returncode=0)
            with mock.patch(
                "morice.updater.subprocess.run",
                return_value=completed,
            ) as run, mock.patch(
                "morice.updater.subprocess.Popen"
            ) as relaunch:
                self.assertEqual(
                    run_updater(str(instruction), str(install), 0),
                    0,
                )

            run.assert_called_once()
            relaunch.assert_called_once_with(
                [str(install / "MORICE.exe")],
                cwd=install,
            )
            result = json.loads(
                (updates / "last-update-result.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(result["success"])
            self.assertEqual(result["rollback"], "")


class SetupAndRepairTests(unittest.TestCase):
    def test_first_run_profile_has_model_fit_and_permissions(self):
        from morice.model_catalog import gpu_profile_from_values

        with tempfile.TemporaryDirectory() as directory:
            service = FirstRunService(directory)
            report = service.inspect(
                gpu_profile_from_values("RTX 3050", 6_144, "test")
            )
            selected = [
                item["modelClass"]
                for item in report["recommendedModels"]
                if item["fit"]
            ]
            self.assertEqual(selected, ["7B Q4/Q5"])
            self.assertTrue(report["permissions"])
            workspace = Path(directory) / "workspace"
            self.assertTrue(service.complete(str(workspace), {}).is_file())

    def test_repair_service_reports_required_assets_truthfully(self):
        with tempfile.TemporaryDirectory() as directory:
            report = RepairService().inspect(directory)
            self.assertFalse(report["healthy"])
            self.assertIn("morice/assets/morice_logo.ico", report["missing"])


class PlatformStressTests(unittest.TestCase):
    def test_large_project_dashboard_and_knowledge_retrieval_stay_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src"
            source.mkdir()
            for index in range(1_200):
                (source / f"module_{index}.py").write_text(
                    f"def feature_{index}():\n    return {index}\n",
                    encoding="utf-8",
                )
            state = Path(directory).parent / f"{root.name}-knowledge"
            graph = KnowledgeGraphStore(state)
            try:
                dashboard = ProjectDashboardService(
                    graph,
                    GitRepositoryService(),
                ).build(str(root), refresh=True)
                self.assertEqual(dashboard.overview["files"], 1_200)
                self.assertLessEqual(len(dashboard.issues), 100)
                for index in range(1_000):
                    graph.add_node(
                        "note",
                        f"Renderer note {index}",
                        f"bounded scheduler value {index}",
                    )
                results = graph.search("bounded scheduler value 777", limit=12)
                self.assertLessEqual(len(results), 12)
                self.assertTrue(results)
            finally:
                graph.close()
                __import__("shutil").rmtree(state, ignore_errors=True)

    def test_run_history_is_bounded_under_many_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = AgentOrchestrator(root / "agent")
            coordinator = MultiAgentCoordinator(root / "coordinator")
            for index in range(215):
                context = agent.prepare_request(f"Explain test request {index}")
                coordinator.create_run(context)
            self.assertEqual(coordinator.snapshot()["runCount"], 200)


if __name__ == "__main__":
    unittest.main()
