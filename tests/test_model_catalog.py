import os
import tempfile
import unittest

from morice.model_catalog import (
    gpu_profile_from_values,
    local_model_result,
    model_compatibility,
    model_run_plan,
    verify_ai_model_file,
)


class ModelCatalogTests(unittest.TestCase):
    def test_non_model_file_is_rejected_even_when_large(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "page.html")
            with open(path, "wb") as handle:
                handle.write(b"<html>")
                handle.truncate(2 * 1024 * 1024)

            verification = verify_ai_model_file(path)

            self.assertFalse(verification.ok)
            self.assertFalse(verification.direct_chat)

    def test_gguf_magic_is_required_for_direct_chat(self):
        with tempfile.TemporaryDirectory() as folder:
            invalid = os.path.join(folder, "invalid.gguf")
            valid = os.path.join(folder, "valid.gguf")
            with open(invalid, "wb") as handle:
                handle.write(b"NOPE")
                handle.truncate(2 * 1024 * 1024)
            with open(valid, "wb") as handle:
                handle.write(b"GGUF")
                handle.truncate(2 * 1024 * 1024)

            self.assertFalse(verify_ai_model_file(invalid).ok)
            self.assertTrue(verify_ai_model_file(valid).direct_chat)

    def test_gpu_fit_and_run_plan_are_derived_from_detected_vram(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "qwen2.5-coder-7b-q4_k_m.gguf")
            with open(path, "wb") as handle:
                handle.write(b"GGUF")
                handle.truncate(4 * 1024 * 1024 * 1024)
            result = local_model_result(path)
            profile = gpu_profile_from_values("RTX 3050 Laptop", "6 GB", "test")

            compatibility = model_compatibility(result, profile)
            plan = model_run_plan(result, profile)

            self.assertGreater(compatibility.required_vram_mb, 4096)
            self.assertIn(
                compatibility.level,
                {"usable", "good", "excellent", "cpu-assisted"},
            )
            self.assertNotEqual(plan.label, "Detect GPU first")


if __name__ == "__main__":
    unittest.main()
