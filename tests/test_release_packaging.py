from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit_release = _load_script("audit_release.py")
validate_version = _load_script("validate_version.py")


class ReleasePackagingTests(unittest.TestCase):
    def test_version_metadata_is_consistent(self):
        version, errors = validate_version.validate_version(ROOT)
        self.assertEqual(version, "0.7.0")
        self.assertEqual(errors, [])

    def test_release_builder_uses_authoritative_version_for_notes(self):
        build_script = (ROOT / "scripts" / "build-release.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('"docs\\release-notes-$Version.md"', build_script)
        self.assertNotIn('"docs\\release-notes-0.7.0.md"', build_script)

    def test_release_policy_rejects_private_and_cache_paths(self):
        self.assertIsNotNone(
            audit_release._unsafe_member("MORICE/.internal-tooling/task.json")
        )
        self.assertIsNone(audit_release._unsafe_member("MORICE/.github/workflows/ci.yml"))
        self.assertIsNotNone(audit_release._unsafe_member("MORICE/__pycache__/x.pyc"))
        self.assertIsNotNone(audit_release._unsafe_member("MORICE/model.gguf"))
        self.assertIsNone(audit_release._unsafe_member("MORICE/morice/assets/logo.png"))

    def test_zip_audit_reports_secret_material(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "probe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("MORICE/config.txt", "github_pat_" + "A" * 30)
            report = audit_release._audit_zip(archive_path)
            self.assertEqual(report["files"], 1)
            self.assertTrue(report["possibleSecrets"])


if __name__ == "__main__":
    unittest.main()
