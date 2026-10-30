import os,subprocess,sys,time
from pathlib import Path
import pytest
from morice.process_ownership import spawn_owned_process,reap_owned_job

@pytest.mark.skipif(os.name!='nt',reason='Windows Job memory-cap acceptance; POSIX worker limits have a separate implementation.')
def test_owned_process_has_real_os_memory_limit():
    process=spawn_owned_process([sys.executable,'-c','data=bytearray(512*1024*1024);print(len(data))'],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,memory_limit_bytes=128*1024**2,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        stdout,stderr=process.communicate(timeout=10)
        assert process.returncode!=0 and b'536870912' not in stdout
        assert b'MemoryError' in stderr or process.returncode!=0
    finally:assert reap_owned_job(process) is True

def test_invalid_owned_process_budget_is_rejected():
    if os.name!='nt':pytest.skip('Windows prelaunch validation')
    with pytest.raises(ValueError):spawn_owned_process([sys.executable,'-c','raise AssertionError("must not execute")'],memory_limit_bytes=-1)
