from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from morice.project_workflows import (
    discover_project_workflow,
    verify_project_artifacts,
)


class ProjectWorkflowTests(unittest.TestCase):
    def test_detects_unreal_from_project_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "APEX.uproject").write_text("{}", encoding="utf-8")
            workflow = discover_project_workflow(directory, "fix the handling")
        self.assertEqual(workflow.adapter_id, "unreal")
        self.assertIn("APEX.uproject", workflow.evidence)

    def test_detects_unity_from_request_without_hard_coding_a_single_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("morice.project_workflows.shutil.which", return_value=None):
                workflow = discover_project_workflow(directory, "build a Unity racing game")
        self.assertEqual(workflow.adapter_id, "unity")
        self.assertFalse(workflow.tool_available)

    def test_detects_android_before_java_for_gradle_android_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app" / "src" / "main").mkdir(parents=True)
            (root / "settings.gradle").write_text("rootProject.name='Demo'", encoding="utf-8")
            (root / "app" / "src" / "main" / "AndroidManifest.xml").write_text(
                "<manifest />", encoding="utf-8"
            )
            workflow = discover_project_workflow(directory)
        self.assertEqual(workflow.adapter_id, "android")

    def test_exact_artifact_verification_reports_real_disk_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<html>ok</html>", encoding="utf-8")
            successful = verify_project_artifacts(
                directory, {"index.html": "<html>ok</html>"}
            )
            failed = verify_project_artifacts(
                directory,
                {"index.html": "different", "app.js": "console.log('x')"},
            )
        self.assertTrue(successful.success)
        self.assertEqual(successful.verified, 1)
        self.assertFalse(failed.success)
        self.assertIn("index.html", failed.mismatched)
        self.assertIn("app.js", failed.missing)


if __name__ == "__main__":
    unittest.main()
