"""Rendered layout failure/repair and live console faults in a real Qt process."""
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

@pytest.mark.skipif(os.name != "nt", reason="Windows/Qt release environment integration")
def test_real_web_layout_repair_python_cancel_resume_and_dirty_project(tmp_path):
    repository=Path(__file__).resolve().parents[1]
    output=tmp_path/"evidence.json"
    process=subprocess.run([sys.executable,str(repository/"scripts/demo_project_builder.py"),"--output",str(output)],
        cwd=repository,capture_output=True,text=True,timeout=100)
    assert process.returncode==0,process.stdout+process.stderr
    value=json.loads(output.read_text(encoding="utf-8"))
    assert value["completed"] and not value["errors"]
    web=value["web_visual_repair"]
    assert web["status"]=="verified" and len(web["repairs"])==1
    assert len(web["screenshots"])>=3
    assert [390,720] in [v["viewport"] for v in web["screenshots"]]
    assert any(v["category"]=="visual" and v["status"]=="resolved" for v in web["issues"])
    assert value["console_failure"]["health"]["ui"]=="fail"
    assert value["logic_repair"]["status"]=="verified"
    assert value["cancel"]["status"]=="cancelled" and value["resume"]["status"]=="verified"
    assert value["existing_dirty"]["status"]=="verified"
    assert value["leases_after"]==0 and value["active_processes_after"]==0
