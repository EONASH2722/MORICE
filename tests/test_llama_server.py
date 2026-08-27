from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from morice import llama_server


class LlamaServerSelectionTests(unittest.TestCase):
    def test_explicit_server_path_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "llama-server.exe"
            executable.touch()
            with patch.dict(
                os.environ,
                {"MORICE_LLAMA_SERVER_PATH": str(executable)},
                clear=False,
            ):
                self.assertEqual(
                    llama_server.selected_server_path(),
                    str(executable.resolve()),
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
                self.assertEqual(
                    llama_server.selected_server_path(),
                    str(executable),
                )

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
                self.assertEqual(llama_server.selected_server_path(), str(executable))

    def test_gpu_layer_override_is_normalized(self):
        with patch.dict(os.environ, {"MORICE_GPU_LAYERS": "all"}, clear=False):
            self.assertEqual(llama_server._gpu_layers(0), "all")
        with patch.dict(os.environ, {"MORICE_GPU_LAYERS": "invalid"}, clear=False):
            self.assertEqual(llama_server._gpu_layers(0), "auto")


if __name__ == "__main__":
    unittest.main()
