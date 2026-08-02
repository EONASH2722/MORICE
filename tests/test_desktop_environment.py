from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from morice.desktop_environment import (
    ApplicationManager,
    AutomationEngine,
    ClipboardManager,
    DesktopIntegrationLayer,
    DesktopManager,
    DesktopPermissionManager,
    FileManager,
    DocumentManager,
    MemoryManager,
    MultimodalContextManager,
    NotificationManager,
    ScreenshotManager,
    SearchEverywhereResult,
    SessionManager,
    SessionState,
    WindowManager,
    WorkspaceManager,
)
from morice.runtime_services import RuntimeServices


class PermissionAndControlTests(unittest.TestCase):
    def test_grant_is_exact_short_lived_and_one_use(self):
        permissions = DesktopPermissionManager(ttl_seconds=10)
        grant = permissions.request(
            "application.launch",
            {"target": "demo.exe"},
            description="Launch demo",
        )

        self.assertFalse(
            permissions.consume(
                grant.token, "application.launch", {"target": "changed.exe"}
            )
        )
        second = permissions.request(
            "application.launch",
            {"target": "demo.exe"},
            description="Launch demo",
        )
        self.assertTrue(
            permissions.consume(
                second.token, "application.launch", {"target": "demo.exe"}
            )
        )
        self.assertFalse(
            permissions.consume(
                second.token, "application.launch", {"target": "demo.exe"}
            )
        )

    def test_application_launch_requires_matching_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "demo.exe"
            executable.write_bytes(b"MZ")
            permissions = DesktopPermissionManager()
            applications = ApplicationManager(Path(directory), permissions)

            with self.assertRaises(PermissionError):
                applications.launch(str(executable), "")
            grant = applications.request_launch(str(executable))
            with mock.patch("morice.desktop_environment.subprocess.Popen") as popen:
                candidate = applications.launch(str(executable), grant.token)

            self.assertEqual(candidate.target, str(executable.resolve()))
            popen.assert_called_once()
            self.assertEqual(applications.recent[0], str(executable.resolve()))

    def test_application_restart_uses_one_exact_approval_for_both_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "demo.exe"
            executable.write_bytes(b"MZ")
            permissions = DesktopPermissionManager()
            applications = ApplicationManager(Path(directory), permissions)
            grant = applications.request_restart(
                str(executable), image_name="demo.exe"
            )
            completed = mock.Mock(returncode=0, stdout="closed", stderr="")
            with mock.patch(
                "morice.desktop_environment.subprocess.run",
                return_value=completed,
            ) as run, mock.patch(
                "morice.desktop_environment.subprocess.Popen"
            ) as popen:
                applications.restart(
                    str(executable),
                    grant.token,
                    image_name="demo.exe",
                )

            run.assert_called_once()
            popen.assert_called_once()
            with self.assertRaises(PermissionError):
                applications.restart(
                    str(executable),
                    grant.token,
                    image_name="demo.exe",
                )

    def test_clipboard_is_opt_in_and_memory_only(self):
        permissions = DesktopPermissionManager()
        clipboard = ClipboardManager(permissions)
        self.assertIsNone(clipboard.observe("secret"))
        grant = clipboard.request_monitoring()
        clipboard.enable(grant.token)

        code = clipboard.observe("def example():\n    return 1")
        url = clipboard.observe("https://example.com")

        self.assertEqual(code.kind, "code")
        self.assertEqual(url.kind, "url")
        self.assertEqual(len(clipboard.history()), 2)
        self.assertTrue(clipboard.pin(code.item_id))
        self.assertTrue(clipboard.history()[0].pinned)
        clipboard.disable(clear=True)
        self.assertEqual(clipboard.history(), [])


class FileIntelligenceTests(unittest.TestCase):
    def test_semantic_search_understands_type_project_and_recency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Transformer Lab"
            project.mkdir()
            (project / "pyproject.toml").write_text(
                "[project]\nname='transformer-lab'\n", encoding="utf-8"
            )
            source = project / "attention_model.py"
            source.write_text("print('ready')\n", encoding="utf-8")
            files = FileManager(root / "state")

            results = files.search("find my latest Python project", [root])

            self.assertTrue(results)
            self.assertEqual(results[0].path, str(source.resolve()))
            self.assertIn("requested file type", results[0].reasons)
            self.assertIn("inside a project", results[0].reasons)

    def test_duplicate_detection_hashes_contents_not_only_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.bin").write_bytes(b"same bytes")
            (root / "second.bin").write_bytes(b"same bytes")
            (root / "third.bin").write_bytes(b"different!")
            files = FileManager(root / "state")

            groups = files.duplicates([root])

            self.assertEqual(len(groups), 1)
            self.assertEqual(
                {Path(path).name for path in groups[0]},
                {"first.bin", "second.bin"},
            )

    def test_previews_extract_real_office_text_and_archive_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "notes.docx"
            with zipfile.ZipFile(document, "w") as archive:
                archive.writestr(
                    "word/document.xml",
                    (
                        '<w:document xmlns:w="urn:test"><w:body>'
                        "<w:p><w:t>Verified office text</w:t></w:p>"
                        "</w:body></w:document>"
                    ),
                )
            archive_path = root / "assets.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("readme.txt", "hello")
            files = FileManager(root / "state")

            office = files.preview(document)
            archive = files.preview(archive_path)

            self.assertTrue(office.available)
            self.assertEqual(office.kind, "docx")
            self.assertIn("Verified office text", office.text)
            self.assertTrue(archive.available)
            self.assertIn("readme.txt", archive.entries)

    def test_malformed_archive_fails_honestly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            broken = root / "broken.docx"
            broken.write_bytes(b"not a zip")
            preview = FileManager(root / "state").preview(broken)

            self.assertFalse(preview.available)
            self.assertIn("failed", preview.reason.casefold())

    def test_document_analysis_has_real_citations_entities_formulas_and_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "experiment.csv"
            document.write_text(
                "Scientist,Formula,Result\n"
                "Ada Lovelace,y = x^2,Validated\n"
                "Grace Hopper,f(x) = x + 1,Reviewed\n",
                encoding="utf-8",
            )
            files = FileManager(root / "state")
            analysis = DocumentManager(files).analyze(
                document, query="Grace formula"
            )

            self.assertTrue(analysis.text_available)
            self.assertTrue(analysis.citations)
            self.assertIn("Grace Hopper", analysis.entities)
            self.assertTrue(any("f(x)" in formula for formula in analysis.formulas))
            self.assertEqual(analysis.tables[0][0][0], "Scientist")

    def test_multimodal_context_tracks_multiple_files_and_cross_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.md"
            second = root / "second.txt"
            first.write_text("Renderer validation uses exact samples.", encoding="utf-8")
            second.write_text("Desktop memory remains bounded.", encoding="utf-8")
            files = FileManager(root / "state")
            documents = DocumentManager(files)
            multimodal = MultimodalContextManager(files, documents)

            attachments = multimodal.attach([first, second])
            hits = multimodal.cross_reference("bounded memory")

            self.assertEqual(len(attachments), 2)
            self.assertEqual(len(multimodal.list()), 2)
            self.assertEqual(Path(hits[0].path).name, "second.txt")


class StateManagerTests(unittest.TestCase):
    def test_notifications_persist_and_dismiss(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notifications = NotificationManager(root)
            item = notifications.publish(
                "Build complete", "All tests passed.", severity="success"
            )
            self.assertTrue(notifications.dismiss(item.notification_id))

            restored = NotificationManager(root).history()
            self.assertEqual(len(restored), 1)
            self.assertTrue(restored[0].dismissed)
            self.assertEqual(restored[0].severity, "success")

    def test_notifications_discard_non_json_metadata_without_breaking_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notifications = NotificationManager(root)
            item = notifications.publish(
                "Safe metadata",
                "The notification remains usable.",
                metadata={"unsafe": object()},
            )

            self.assertEqual(item.metadata, {})
            self.assertEqual(NotificationManager(root).history()[0].metadata, {})

    def test_memory_is_scoped_relevant_bounded_and_exportable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = MemoryManager(root)
            relevant = memory.add(
                "project",
                "The renderer uses deterministic graph validation.",
                project_id="morice",
                tags=("renderer", "validation"),
            )
            memory.add("user", "The user prefers compact status reports.")

            matches = memory.retrieve(
                "graph renderer validation", project_id="morice"
            )

            self.assertEqual(matches[0].memory_id, relevant.memory_id)
            self.assertTrue(memory.update(relevant.memory_id, pinned=True))
            exported = memory.export(root / "export.json")
            payload = json.loads(exported.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["records"]), 2)
            memory.set_enabled(False)
            self.assertEqual(memory.retrieve("renderer"), [])
            with self.assertRaises(RuntimeError):
                memory.add("user", "disabled")

    def test_project_workspace_and_session_restore_are_structured(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "project"
            project_root.mkdir()
            (project_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
            workspaces = WorkspaceManager(root / "state")
            project = workspaces.register(str(project_root))
            workspaces.update(
                project.project_id,
                tasks=["Run tests"],
                open_editors=[str(project_root / "main.py")],
                build_status="passed",
            )
            sessions = SessionManager(root / "state")
            sessions.save(
                SessionState(
                    "session",
                    "",
                    project_ids=[project.project_id],
                    editors=[str(project_root / "main.py")],
                    pending_tasks=["Run tests"],
                )
            )

            restored_project = WorkspaceManager(root / "state").get(project.project_id)
            restored_session = SessionManager(root / "state").load()

            self.assertEqual(restored_project.build_status, "passed")
            self.assertEqual(restored_session.project_ids, [project.project_id])
            self.assertEqual(restored_session.pending_tasks, ["Run tests"])

    def test_automation_is_disabled_by_default_and_runs_registered_actions_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            permissions = DesktopPermissionManager()
            notifications = NotificationManager(root)
            engine = AutomationEngine(root, permissions, notifications)
            calls = []
            engine.register_action("test.record", lambda values: calls.append(values["value"]))
            workflow = engine.create(
                "Record build",
                "build.completed",
                "test.record",
                arguments={"value": "passed"},
            )

            self.assertEqual(engine.trigger("build.completed"), [])
            grant = engine.request_enable(workflow.workflow_id)
            engine.enable(workflow.workflow_id, grant.token)
            engine.trigger("build.completed")

            self.assertEqual(calls, ["passed"])
            with self.assertRaises(ValueError):
                engine.create("Unsafe", "event", "terminal.run")

    def test_automation_conditions_variables_and_interval_schedule_are_real(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            permissions = DesktopPermissionManager()
            notifications = NotificationManager(root)
            engine = AutomationEngine(root, permissions, notifications)
            calls = []
            engine.register_action(
                "test.record", lambda values: calls.append(values["message"])
            )
            workflow = engine.create(
                "Scheduled project report",
                "schedule:interval:60",
                "test.record",
                arguments={"message": "${project} passed"},
                conditions={"status": "passed"},
                variables={"project": "MORICE"},
            )
            grant = engine.request_enable(workflow.workflow_id)
            engine.enable(workflow.workflow_id, grant.token)

            self.assertEqual(
                engine.trigger(
                    workflow.event,
                    {"status": "failed", "project": "MORICE"},
                ),
                [],
            )
            engine.trigger(
                workflow.event,
                {"status": "passed", "project": "MORICE"},
            )
            self.assertEqual(calls, ["MORICE passed"])
            workflow.last_run_at = ""
            engine.run_due(datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc))
            self.assertEqual(calls[-1], "MORICE passed")

    def test_automation_rejects_non_json_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            permissions = DesktopPermissionManager()
            notifications = NotificationManager(root)
            engine = AutomationEngine(root, permissions, notifications)
            engine.register_action("test.record", lambda _values: None)

            with self.assertRaisesRegex(ValueError, "JSON-compatible"):
                engine.create(
                    "Invalid",
                    "event",
                    "test.record",
                    arguments={"callback": object()},
                )


class IntegrationTests(unittest.TestCase):
    def test_desktop_manager_alias_exposes_the_complete_integration_layer(self):
        self.assertIs(DesktopManager, DesktopIntegrationLayer)

    def test_search_everywhere_combines_files_projects_memory_and_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "Project Atlas"
            project_root.mkdir()
            (project_root / "atlas.py").write_text("print('atlas')\n", encoding="utf-8")
            layer = DesktopIntegrationLayer(root / "runtime")
            project = layer.workspaces.register(str(project_root))
            layer.memory.add("project", "Atlas renderer notes", project_id=project.project_id)
            layer.search.register(
                "commands",
                lambda query: (
                    SearchEverywhereResult(
                        "commands", "Open Atlas", "Command", "open-project", 50.0
                    ),
                )
                if "atlas" in query.casefold()
                else (),
            )

            results = layer.search.search("Atlas", roots=[root])

            categories = {item.category for item in results}
            self.assertTrue({"files", "projects", "memory", "commands"}.issubset(categories))
            layer.shutdown()

    def test_screenshot_requires_permission_and_validates_saved_output(self):
        class FakeImage:
            width = 320
            height = 200

            @staticmethod
            def save(path, _format):
                Path(path).write_bytes(b"validated-png")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            permissions = DesktopPermissionManager()
            windows = WindowManager(permissions)
            screenshots = ScreenshotManager(root, permissions, windows)
            with self.assertRaises(PermissionError):
                screenshots.capture("full", "")
            grant = screenshots.request("full")
            with mock.patch("PIL.ImageGrab.grab", return_value=FakeImage()):
                result = screenshots.capture("full", grant.token)

            self.assertEqual((result.width, result.height), (320, 200))
            self.assertGreater(Path(result.path).stat().st_size, 0)

    def test_runtime_snapshot_exposes_desktop_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeServices(directory)
            runtime.start()
            snapshot = runtime.snapshot()
            runtime.shutdown()

            self.assertIn("capabilities", snapshot.desktop)
            self.assertTrue(snapshot.desktop["capabilities"]["files"])
            self.assertTrue(snapshot.desktop["capabilities"]["searchEverywhere"])


if __name__ == "__main__":
    unittest.main()
