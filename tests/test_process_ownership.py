"""Real Windows child-family cancellation, independent of owner bookkeeping."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
import uuid

import psutil
import pytest

import morice.process_ownership as ownership

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows Job ownership regression')


def test_immediate_venv_cancellation_does_not_leave_suspended_launchers():
    for _ in range(12):
        process=ownership.spawn_owned_process([sys.executable,'-c','import time;time.sleep(30)',uuid.uuid4().hex],
            creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            assert ownership.reap_owned_job(process) is True
            assert process.poll() is not None
            assert process._morice_windows_job.handle is None
        finally:ownership.reap_owned_job(process)


def test_job_reaps_child_even_after_its_parent_exits():
    # The base interpreter avoids the venv launcher's own optional nested Job;
    # this child must actually outlive its root before our owner stops it.
    code=('import subprocess,sys;child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],'
        'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);print(child.pid,flush=True)')
    process=ownership.spawn_owned_process([sys._base_executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        stdout,stderr=process.communicate(timeout=10)
        assert process.returncode==0,stderr
        child=psutil.Process(int(stdout.strip()))
        assert child.is_running()
        assert ownership.owned_process_running(process)
        assert ownership.reap_owned_job(process) is True
        child.wait(timeout=2)
        assert not child.is_running()
        assert not ownership.owned_process_running(process)
    finally:ownership.reap_owned_job(process)


def test_reaping_owned_job_preserves_an_unrelated_process():
    command=[sys._base_executable,'-c','import time;time.sleep(30)']
    unrelated=subprocess.Popen(command,creationflags=subprocess.CREATE_NO_WINDOW)
    owned=None
    try:
        owned=ownership.spawn_owned_process(command,creationflags=subprocess.CREATE_NO_WINDOW)
        assert ownership.reap_owned_job(owned) is True
        assert unrelated.poll() is None
    finally:
        if owned is not None:ownership.reap_owned_job(owned)
        unrelated.kill();unrelated.wait(timeout=2)


def test_failed_assignment_never_executes_the_command(tmp_path):
    marker=tmp_path/'must-not-exist.txt';created=[]
    real_popen=subprocess.Popen
    def capture(*args,**kwargs):
        process=real_popen(*args,**kwargs);created.append(process);return process
    dependency=SimpleNamespace(**vars(subprocess));dependency.Popen=capture
    with patch.object(ownership,'subprocess',dependency),patch.object(ownership._WindowsJob,'assign',side_effect=OSError('Controlled assignment failure')):
        with pytest.raises(OSError,match='Controlled assignment failure'):
            ownership.spawn_owned_process([sys._base_executable,'-c','from pathlib import Path;import sys;Path(sys.argv[1]).write_text("executed")',str(marker)],
                creationflags=subprocess.CREATE_NO_WINDOW)
    assert created and all(process.poll() is not None for process in created)
    assert not marker.exists()
    assert subprocess.Popen is real_popen


def test_holder_crash_closes_job_and_stops_its_worker():
    marker='morice-job-crash-'+uuid.uuid4().hex
    code=('import json,os,psutil,subprocess,sys;from morice.process_ownership import spawn_owned_process;'
        'child=spawn_owned_process([sys._base_executable,"-c","import time;time.sleep(30)",sys.argv[1]],'
        'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW);'
        'print(json.dumps({"pid":child.pid,"created":psutil.Process(child.pid).create_time()}),flush=True);os._exit(17)')
    holder=subprocess.Popen([sys.executable,'-c',code,marker],cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    child=None
    try:
        stdout,stderr=holder.communicate(timeout=10)
        assert holder.returncode==17,stderr
        import json
        identity=json.loads(stdout.strip())
        try:
            child=psutil.Process(identity['pid'])
            if abs(child.create_time()-identity['created'])>.001:child=None
            else:child.wait(timeout=2)
        except psutil.NoSuchProcess:pass
        assert child is None or not child.is_running()
    finally:
        if holder.poll() is None:holder.kill();holder.wait(timeout=2)
        if child is not None and child.is_running():child.kill();child.wait(timeout=2)
