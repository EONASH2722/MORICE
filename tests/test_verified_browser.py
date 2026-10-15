"""Real browser/disk/process/window integration in a fresh Qt process."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="The owned-window demo requires the Windows observer.")
def test_real_browser_download_viewer_project_recovery_and_agent_integration():
    repository = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "verified.json"
        process = subprocess.run([sys.executable, str(repository / "scripts" / "demo_verified_actions.py"), "--output", str(output)],
            cwd=repository, capture_output=True, text=True, timeout=55)
        detail=output.read_text() if output.exists() else output.with_suffix('.partial.json').read_text() if output.with_suffix('.partial.json').exists() else 'No fixture evidence written.'
        assert process.returncode == 0, process.stdout + process.stderr + detail
        evidence = json.loads(output.read_text())
        assert not evidence["errors"]
        assert evidence["completed"]
        assert evidence["browser_file_demo"]["bytes"] == 42
        assert evidence["project_app_demo"]["exit_code"] == 0
        assert evidence["recovery_demo"]["attempts"] == 2
        assert evidence["parallel_integration"]["success"]
        assert evidence["leases_after"] == 0
        assert any(a["capability"] == "browser.open" and not a["success"] for a in evidence["actions"])
