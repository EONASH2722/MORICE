from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from morice import llama_server


class LlamaServerSelectionTests(unittest.TestCase):
    def setUp(self):
        self._old_process = llama_server._SERVER_PROCESS
        self._old_config = llama_server._SERVER_CONFIG
        llama_server._SERVER_PROCESS = None
        llama_server._SERVER_CONFIG = None

    def tearDown(self):
        llama_server._SERVER_PROCESS = self._old_process
        llama_server._SERVER_CONFIG = self._old_config

    def assertSamePath(self, actual: str, expected: Path) -> None:
        self.assertTrue(
            os.path.samefile(actual, expected),
            f"Paths refer to different files: {actual!r} != {str(expected)!r}",
        )

    def test_explicit_server_path_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "llama-server.exe"
            executable.touch()
            with patch.dict(
                os.environ,
                {"MORICE_LLAMA_SERVER_PATH": str(executable)},
                clear=False,
            ):
                self.assertSamePath(
                    llama_server.selected_server_path(), executable.resolve()
                )

    def test_cuda_runtime_is_selected_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = (
                Path(directory) / "MORICE" / "llama-cuda" / "llama-server.exe"
            )
            executable.parent.mkdir(parents=True)
            executable.touch()
            environment = {
                "LOCALAPPDATA": directory,
                "MORICE_LOCAL_DATA_DIR": "",
                "MORICE_LLAMA_SERVER_PATH": "",
                "MORICE_PREFER_CUDA_LLAMA": "1",
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch("morice.llama_server.shutil.which", return_value="nvidia-smi"),
            ):
                self.assertSamePath(llama_server.selected_server_path(), executable)

    def test_cuda_runtime_honors_relocated_local_data(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "llama-cuda" / "llama-server.exe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            environment = {
                "MORICE_LOCAL_DATA_DIR": directory,
                "MORICE_LLAMA_SERVER_PATH": "",
                "MORICE_PREFER_CUDA_LLAMA": "1",
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch("morice.llama_server.shutil.which", return_value="nvidia-smi"),
            ):
                self.assertSamePath(llama_server.selected_server_path(), executable)

    def test_gpu_layer_override_is_normalized(self):
        with patch.dict(os.environ, {"MORICE_GPU_LAYERS": "all"}, clear=False):
            self.assertEqual(llama_server._gpu_layers(0), "all")
        with patch.dict(os.environ, {"MORICE_GPU_LAYERS": "invalid"}, clear=False):
            self.assertEqual(llama_server._gpu_layers(0), "auto")

    def test_matching_warm_server_is_reused_after_an_app_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "selected.gguf"
            executable = Path(directory) / "llama-server.exe"
            model.touch()
            executable.touch()
            dependency = SimpleNamespace(**vars(subprocess))
            with (
                patch.object(llama_server, "_server_path", return_value=str(executable)),
                patch.object(llama_server, "_is_server_ready", return_value=True),
                patch.object(
                    llama_server,
                    "_server_model_paths",
                    # Match the helper's actual normcase(abspath) contract.
                    # resolve() expands Windows 8.3 aliases and changes it.
                    return_value={os.path.normcase(os.path.abspath(model))},
                ),
                patch.object(llama_server, "subprocess", dependency),
                patch.object(dependency, "Popen") as popen,
            ):
                endpoint = llama_server.ensure_server(
                    str(model), 8192, 0, 4, 128
                )

        self.assertEqual(endpoint, "http://127.0.0.1:8080")
        popen.assert_not_called()

    def test_different_warm_server_is_not_silently_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "selected.gguf"
            executable = Path(directory) / "llama-server.exe"
            model.touch()
            executable.touch()
            with (
                patch.object(llama_server, "_server_path", return_value=str(executable)),
                patch.object(llama_server, "_is_server_ready", return_value=True),
                patch.object(
                    llama_server,
                    "_server_model_paths",
                    return_value={os.path.normcase(str(Path(directory) / "other.gguf"))},
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "different llama server or model"):
                    llama_server.ensure_server(str(model), 8192, 0, 4, 128)


if __name__ == "__main__":
    unittest.main()
