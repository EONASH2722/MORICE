"""Exercise actual owned subprocess output at the EOF/exit boundary."""
import json
import sys
from unittest.mock import patch

import pytest

from morice.kernel import ExecutionContext
from morice.media_lab.process import OwnedMediaProcesses, MediaWorkerError
from morice.process_ownership import spawn_owned_process


@pytest.mark.parametrize('complete', [True, False])
def test_final_worker_event_written_after_eof_is_drained(tmp_path, complete):
    signal=tmp_path/'release-worker'
    code=(
        'import pathlib,sys,time\n'
        'signal=pathlib.Path(sys.argv[1])\n'
        'while not signal.exists(): time.sleep(.005)\n'
        'sys.stdout.write(sys.argv[2]);sys.stdout.flush()\n'
    )
    event=json.dumps({'type':'result','files':[],'metrics':{'controlled_exit_race':True}})
    output=event+('\n' if complete else '')
    def spawn_with_controlled_exit(*args, **kwargs):
        process=spawn_owned_process(*args, **kwargs)
        original_poll=process.poll
        def exit_before_poll_returns():
            if not signal.exists():
                # run() has reached EOF. Let the real child flush its final
                # event and exit before the parent observes the exit status.
                signal.write_text('release',encoding='utf-8')
                process.wait(timeout=10)
            return original_poll()
        process.poll=exit_before_poll_returns
        return process
    owner=OwnedMediaProcesses()
    try:
        with patch('morice.media_lab.process.spawn_owned_process',side_effect=spawn_with_controlled_exit):
            command=[sys.executable,'-I','-c',code,str(signal),output]
            if complete:
                result=owner.run('controlled-final-event',command,tmp_path,ExecutionContext(),ram_margin_mb=0)
                assert result['metrics']['controlled_exit_race'] is True
                assert result['metrics']['worker_exit_code']==0
            else:
                with pytest.raises(MediaWorkerError,match='incomplete event'):
                    owner.run('controlled-partial-event',command,tmp_path,ExecutionContext(),ram_margin_mb=0)
        assert signal.exists() and not owner.snapshot()
    finally:
        owner.close()
