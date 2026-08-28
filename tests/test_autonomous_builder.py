import tempfile
import unittest
from pathlib import Path

from morice.autonomous_builder import AutonomousBuilder


class AutonomousBuilderTests(unittest.TestCase):
    def test_web_project_verifies_files_without_claiming_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory, "site")
            root.mkdir()
            (root / "index.html").write_text("<h1>Ready</h1>", encoding="utf-8")
            builder = AutonomousBuilder(Path(directory, "state"))
            session = builder.plan(str(root), "Build a website")
            files, commands = builder.verify(
                session,
                {"index.html": "<h1>Ready</h1>"},
            )
            self.assertTrue(files.success)
            self.assertFalse(any(item.attempted for item in commands))
            self.assertEqual(session.state, "files-verified")
            self.assertIsNotNone(builder.load(session.session_id))

    def test_python_project_runs_real_tests_and_records_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory, "python-project")
            root.mkdir()
            source = "def add(a, b):\n    return a + b\n"
            (root / "main.py").write_text(source, encoding="utf-8")
            (root / "test_main.py").write_text(
                "from main import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
                encoding="utf-8",
            )
            builder = AutonomousBuilder(Path(directory, "state"))
            session = builder.plan(str(root), "Build and test the Python application")
            files, commands = builder.verify(session, {"main.py": source}, timeout=30)
            test = next(item for item in commands if item.stage == "test")
            self.assertTrue(files.success)
            self.assertTrue(test.attempted)
            self.assertTrue(test.success, test.output)
            self.assertEqual(session.state, "verified")


if __name__ == "__main__":
    unittest.main()
