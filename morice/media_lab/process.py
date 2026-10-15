"""Bounded, owned inference subprocesses; cancellation reaps before releasing work."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from ..kernel import CancelledError
from ..process_ownership import spawn_owned_process,reap_owned_job,owned_process_running
from .storage import atomic_json,read_json


class MediaWorkerError(RuntimeError):
    def __init__(self,message,*,oom=False,cleanup_confirmed=True):
        super().__init__(message);self.oom=oom;self.cleanup_confirmed=cleanup_confirmed


class OwnedMediaProcesses:
    def __init__(self):self._processes={};self._lock=threading.RLock();self._closed=False

    def snapshot(self):
        with self._lock:return [{'generation_id':key,'pid':p.pid,'running':owned_process_running(p)} for key,p in self._processes.items()]

    @staticmethod
    def reap(process,observed_descendants=()):
        if reap_owned_job(process) is True:return True
        descendants=list(observed_descendants)
        try:
            import psutil
            if process.poll() is None:
                for child in psutil.Process(process.pid).children(recursive=True):
                    if child not in descendants:descendants.append(child)
        except Exception:pass  # Process may have exited before the telemetry probe.
        for child in descendants:
            try:child.terminate()
            except (OSError,psutil.NoSuchProcess):pass
        if process.poll() is None:
            try:process.terminate()
            except OSError:
                if process.poll() is None:raise
            try:process.wait(timeout=.4)
            except subprocess.TimeoutExpired:
                try:process.kill()
                except OSError:
                    if process.poll() is None:raise
                process.wait(timeout=2)
        for child in descendants:
            try:
                child.wait(timeout=.4)
            except Exception:
                try:child.kill();child.wait(timeout=2)
                except psutil.NoSuchProcess:pass
        return process.poll() is not None and all(not child.is_running() for child in descendants)

    def run(self,identifier,command,directory,context,*,progress=None,ram_limit_mb=None,ram_margin_mb=2048):
        directory=Path(directory);out=directory/'worker-events.jsonl';err=directory/'worker-stderr.log'
        env=os.environ.copy()
        for name in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(name,None)
        env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',PYTHONUNBUFFERED='1')
        metrics={};tail=deque(maxlen=30);result=None
        started=time.perf_counter();peak_ram=0;observed_descendants=[]
        with self._lock:
            if self._closed:raise RuntimeError('Media process owner is closed.')
            if identifier in self._processes:raise ValueError('Duplicate owned media process.')
            # Files avoid unbounded pipes/readers and reader thread leaks.
            with out.open('wb') as stdout,err.open('wb') as stderr:
                process=spawn_owned_process(command,cwd=directory,stdout=stdout,stderr=stderr,env=env,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self._processes[identifier]=process
        ownership=[]
        def record_owner(owned):
            item={'pid':owned.pid,'created_at':owned.create_time()}
            if item not in ownership:
                ownership.append(item)
                atomic_json(directory/'worker-owner.json',{'schema':1,'generation_id':identifier,'processes':ownership})
        try:
            with out.open('rb') as stream:
                worker_exited=False
                while True:
                    if context.cancellation_token:context.cancellation_token.raise_if_cancelled()
                    if context.deadline is not None and time.monotonic()>=context.deadline:
                        raise MediaWorkerError('Media worker deadline exceeded.')
                    if out.stat().st_size>4*1024*1024 or err.stat().st_size>8*1024*1024:
                        raise MediaWorkerError('Media worker exceeded output log budget.')
                    position=stream.tell();line=stream.readline(64*1024+1)
                    if len(line)>64*1024:raise MediaWorkerError('Worker event exceeds byte budget.')
                    if line and not line.endswith(b'\n'):
                        if worker_exited:
                            raise MediaWorkerError('Owned media worker ended with an incomplete event.')
                        stream.seek(position);line=b''
                    if line:
                        try:
                            event=json.loads(line)
                            if not isinstance(event,dict):continue
                        except (ValueError,UnicodeDecodeError):continue
                        tail.append(event)
                        if event.get('type')=='progress' and progress:progress(event)
                        if event.get('type')=='result':result=event
                        if event.get('type')=='error':raise MediaWorkerError(str(event.get('message','Worker failed.'))[:1500],oom=event.get('oom') is True)
                        continue
                    try:
                        import psutil
                        parent=psutil.Process(process.pid)
                        record_owner(parent)
                        children=parent.children(recursive=True)
                        for child in children:
                            record_owner(child)
                            if child not in observed_descendants:observed_descendants.append(child)
                        resident=0
                        for owned in [parent,*children]:
                            try:resident+=owned.memory_info().rss
                            except psutil.NoSuchProcess:pass
                        peak_ram=max(peak_ram,resident)
                        if ram_limit_mb and peak_ram/2**20>ram_limit_mb:
                            raise MediaWorkerError('Owned worker exceeded its admitted RAM budget.',oom=True)
                        if psutil.virtual_memory().available/2**20<ram_margin_mb:
                            raise MediaWorkerError('Host RAM safety margin reached; inference stopped.',oom=True)
                    except MediaWorkerError:raise
                    except Exception:pass  # Sampling cannot turn an exited worker into failure.
                    if process.poll() is not None:
                        # The child can flush its terminal event between our
                        # EOF read and poll(). Once exit is confirmed, drain
                        # the stable file before deciding whether it replied.
                        if worker_exited:break
                        worker_exited=True
                        continue
                    if context.cancellation_token:context.cancellation_token.wait(.03)
                    else:time.sleep(.03)
            if process.returncode or result is None:raise MediaWorkerError('Owned media worker exited without a valid result (exit '+str(process.returncode)+').')
            metrics.update(result.get('metrics',{}));metrics.update(worker_wall_ms=(time.perf_counter()-started)*1000,peak_ram_mb=peak_ram/2**20,ram_scope='sum of RSS across owned worker process tree',worker_exit_code=process.returncode)
            return {**result,'metrics':metrics}
        finally:
            # Only the actual Popen object created here is terminated. Foreign
            # services, model files and unrelated encoders are never touched.
            try:stopped=self.reap(process,observed_descendants)
            except Exception as exc:raise MediaWorkerError('Owned worker cleanup failed: '+type(exc).__name__,cleanup_confirmed=False) from exc
            with self._lock:
                if stopped:self._processes.pop(identifier,None)
            if not stopped:raise MediaWorkerError('Worker termination could not be confirmed.',cleanup_confirmed=False)

    def close(self):
        with self._lock:self._closed=True;processes=tuple(self._processes.items())
        for identifier,process in processes:
            if self.reap(process):
                with self._lock:self._processes.pop(identifier,None)
        if self.snapshot():raise RuntimeError('Media workers remain alive.')


def recover_owned_temp(directory,history):
    """Remove interrupted temp files only after persisted PID identity is gone."""
    import shutil
    try:import psutil
    except ImportError:return {'removed':[],'quarantined':[],'reason':'Process identity telemetry unavailable; no interrupted temp files removed.'}
    root=Path(directory).resolve();removed=[];quarantined=[]
    for count,path in enumerate(root.iterdir()):
        if count>=256:break
        identifier=path.name
        if len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier) or path.is_symlink() or not path.is_dir():continue
        record=history.get(identifier)
        if not record or record['status'] not in {'INTERRUPTED','FAILED','CANCELLED'}:continue
        try:
            value=read_json(path/'worker-owner.json',limit=16*1024)
            if value.get('schema')!=1 or value.get('generation_id')!=identifier or not 1<=len(value['processes'])<=32:raise ValueError('No bounded ownership proof.')
            for item in value['processes']:
                if type(item['pid']) is not int or item['pid']<=0 or type(item['created_at']) not in (int,float):raise ValueError('Invalid process identity.')
                try:
                    process=psutil.Process(item['pid'])
                    if abs(process.create_time()-item['created_at'])<.001 and process.is_running():raise ValueError('Owned worker remains alive; refuse cleanup.')
                except psutil.NoSuchProcess:pass
            if path.resolve().parent!=root:raise ValueError('Temp directory escaped storage.')
            shutil.rmtree(path);removed.append(identifier)
        except (OSError,ValueError,TypeError,KeyError,psutil.Error):quarantined.append(identifier)
    return {'removed':removed,'quarantined':quarantined}
