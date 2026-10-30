"""OS ownership for existing managed subprocesses; no execution authority.

Windows launchers can create a suspended child between a process-tree snapshot
and cancellation. Assign the suspended root to a kill-on-close Job before
resuming its initial thread. The existing runtime still owns all permissions,
leases, deadlines and worker admission. Non-Windows process groups are retained.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time


if os.name == 'nt':
    import ctypes
    from ctypes import wintypes as w

    class _BasicLimits(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
            ('flags',w.DWORD),('minimum_ws',ctypes.c_size_t),('maximum_ws',ctypes.c_size_t),
            ('active_limit',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]

    class _IoCounters(ctypes.Structure):
        _fields_=[(name,ctypes.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]

    class _ExtendedLimits(ctypes.Structure):
        _fields_=[('basic',_BasicLimits),('io',_IoCounters),('process_memory',ctypes.c_size_t),
            ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]

    class _Accounting(ctypes.Structure):
        _fields_=[(name,ctypes.c_longlong) for name in ('user','kernel','period_user','period_kernel')]+[
            (name,w.DWORD) for name in ('faults','total','active','terminated')]

    _api=ctypes.WinDLL('kernel32',use_last_error=True)
    for name,result,arguments in (
        ('CreateJobObjectW',w.HANDLE,[ctypes.c_void_p,w.LPCWSTR]),
        ('SetInformationJobObject',w.BOOL,[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]),
        ('AssignProcessToJobObject',w.BOOL,[w.HANDLE,w.HANDLE]),
        ('TerminateJobObject',w.BOOL,[w.HANDLE,w.UINT]),
        ('QueryInformationJobObject',w.BOOL,[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.c_void_p]),
        ('CloseHandle',w.BOOL,[w.HANDLE]),
        ('OpenThread',w.HANDLE,[w.DWORD,w.BOOL,w.DWORD]),
        ('GetProcessIdOfThread',w.DWORD,[w.HANDLE]),
        ('ResumeThread',w.DWORD,[w.HANDLE]),
    ):
        function=getattr(_api,name);function.restype=result;function.argtypes=arguments

    def _checked(value):
        if not value:raise ctypes.WinError(ctypes.get_last_error())
        return value

    def _resume_initial_thread(pid):
        import psutil
        # Use psutil's native per-process query. A Python Toolhelp loop releases
        # and reacquires the GIL for every thread on the machine, causing seconds
        # of launch delay when a native GUI is painting concurrently.
        found=psutil.Process(pid).threads()
        # Before its first instruction the owned root has one initial thread.
        # Preserve fail-closed layout and handle identity checks before resume.
        if len(found)!=1:raise OSError('Cannot identify the owned suspended process initial thread.')
        thread=_checked(_api.OpenThread(2|0x0800,False,found[0].id))
        try:
            if _api.GetProcessIdOfThread(thread)!=pid:raise OSError('Owned process initial thread identity changed before resume.')
            if _api.ResumeThread(thread)!=1:raise OSError('Owned process initial thread did not resume from its expected suspension.')
        finally:_api.CloseHandle(thread)

    class _WindowsJob:
        def __init__(self, memory_limit_bytes=None):
            if memory_limit_bytes is not None and (type(memory_limit_bytes) is not int or memory_limit_bytes<16*1024**2):raise ValueError('Invalid owned process memory budget.')
            self.lock=threading.RLock();self.handle=_checked(_api.CreateJobObjectW(None,None))
            limits=_ExtendedLimits();limits.basic.flags=0x2000  # KILL_ON_JOB_CLOSE
            if memory_limit_bytes is not None:
                limits.basic.flags|=0x100|0x200
                limits.process_memory=memory_limit_bytes;limits.job_memory=memory_limit_bytes
            try:_checked(_api.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)))
            except BaseException:self.close();raise

        def assign(self,process):
            _checked(_api.AssignProcessToJobObject(self.handle,int(process._handle)))

        def active(self):
            value=_Accounting()
            _checked(_api.QueryInformationJobObject(self.handle,1,ctypes.byref(value),ctypes.sizeof(value),None))
            return value.active

        def close(self):
            if self.handle:
                handle=self.handle;self.handle=None;_api.CloseHandle(handle)

        def reap(self,process,timeout):
            with self.lock:
                if not self.handle:return True
                _checked(_api.TerminateJobObject(self.handle,1))
                deadline=time.monotonic()+timeout
                process.wait(timeout=max(.01,deadline-time.monotonic()))
                while self.active():
                    if time.monotonic()>=deadline:raise TimeoutError('Owned Windows process family did not terminate within its cleanup budget.')
                    time.sleep(.01)
                self.close();return True

        def __del__(self):
            # Last-handle close also stops the family on normal object disposal.
            try:self.close()
            except Exception:pass


def spawn_owned_process(*arguments,**options):
    """Return a normal Popen with Windows family ownership established first."""
    memory_limit=options.pop('memory_limit_bytes',None)
    if memory_limit is not None and (type(memory_limit) is not int or memory_limit<16*1024**2):raise ValueError('Invalid owned process memory budget.')
    if os.name!='nt':
        if memory_limit is not None:
            options['env']={**options.get('env',os.environ),'MORICE_WORKER_MEMORY_LIMIT':str(memory_limit)}
        return subprocess.Popen(*arguments,**options)
    job=_WindowsJob(memory_limit);process=None
    try:
        options['creationflags']=options.get('creationflags',0)|4  # CREATE_SUSPENDED
        process=subprocess.Popen(*arguments,**options)
        job.assign(process)
        process._morice_windows_job=job
        _resume_initial_thread(process.pid)
        return process
    except BaseException:
        # No command instruction runs if assignment/resume fails. Cleanup uses
        # only the exact process created above and our private, unnamed Job.
        try:
            if process is not None:
                if process.poll() is None:process.kill()
                process.wait(timeout=2)
        finally:job.close()
        raise


def reap_owned_job(process,timeout=2.):
    """True for a verified empty Windows Job; None for existing fallback paths."""
    job=getattr(process,'_morice_windows_job',None)
    if job is None:return None
    return job.reap(process,timeout)


def owned_process_running(process):
    """Observe the managed family, including children of an exited launcher."""
    job=getattr(process,'_morice_windows_job',None)
    if job is not None:
        with job.lock:return bool(job.handle and job.active())
    return process.poll() is None
