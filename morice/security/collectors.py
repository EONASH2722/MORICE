"""Bounded metadata collection on the user's local Windows machine."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
from pathlib import Path
from ctypes import wintypes


def file_hash(path, max_bytes=8388608):
    path = Path(path)
    if path.stat().st_size > max_bytes or not path.is_file() or path.is_symlink():
        raise ValueError("Selected file exceeds its collection budget or is a link.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        remaining = max_bytes
        while chunk := stream.read(min(65536,remaining+1)):
            remaining -= len(chunk)
            if remaining < 0:
                raise ValueError("File grew beyond the collection budget.")
            digest.update(chunk)
    return digest.hexdigest()


class ProcessHandle:
    """A retained handle protects termination from PID reuse after observation."""
    def __init__(self, pid, *, terminate=False):
        if os.name != "nt" or not isinstance(pid,int) or pid <= 4 or pid == os.getpid():
            raise ValueError("Only non-system local Windows processes may be selected.")
        self.api = ctypes.WinDLL("kernel32",use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
        self.api.GetProcessTimes.argtypes = [wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        self.api.TerminateProcess.argtypes = [wintypes.HANDLE,wintypes.UINT]
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        self.handle = self.api.OpenProcess(0x1000 | 0x100000 | (1 if terminate else 0),False,pid)
        if not self.handle:
            raise OSError("Process metadata/termination access is unavailable.")
        self.pid = pid
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not self.api.QueryFullProcessImageNameW(self.handle,0,buffer,ctypes.byref(size)):
                raise OSError("Executable identity is unavailable.")
            times = [wintypes.FILETIME() for _ in range(4)]
            if not self.api.GetProcessTimes(self.handle,*[ctypes.byref(t) for t in times]):
                raise OSError("Process start identity is unavailable.")
            self.identity = {"pid":pid,"executable":str(Path(buffer.value).resolve()),
                             "start_time":(times[0].dwHighDateTime << 32) | times[0].dwLowDateTime}
        except Exception:
            self.close()
            raise

    def stopped(self):
        return self.api.WaitForSingleObject(self.handle,0) == 0

    def terminate(self):
        if not self.api.TerminateProcess(self.handle,1):
            raise OSError("The selected process could not be terminated.")
        return self.api.WaitForSingleObject(self.handle,2000) == 0

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()


class LockedFile:
    """Windows handle denies concurrent writes/deletes and deletes that exact file."""
    def __init__(self,path,*,create=False):
        if os.name != "nt":
            raise RuntimeError("Locked Windows evidence transfer is unavailable.")
        self.api=ctypes.WinDLL("kernel32",use_last_error=True)
        self.api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        self.api.CreateFileW.restype=wintypes.HANDLE
        self.api.ReadFile.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
        self.api.WriteFile.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]
        self.api.FlushFileBuffers.argtypes=[wintypes.HANDLE]
        self.api.CloseHandle.argtypes=[wintypes.HANDLE]
        self.api.SetFileInformationByHandle.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        self.api.GetFinalPathNameByHandleW.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
        self.api.GetFinalPathNameByHandleW.restype=wintypes.DWORD
        # GENERIC_READ | DELETE, share-read only, OPEN_EXISTING, reject final symlinks.
        self.handle=self.api.CreateFileW(str(path),0x80000000|0x10000|(0x40000000 if create else 0),0 if create else 1,None,1 if create else 3,0x00200000,None)
        if not self.handle or self.handle == wintypes.HANDLE(-1).value:
            self.handle=None
            if create and ctypes.get_last_error() in {80,183}:raise FileExistsError("Restore would overwrite an existing file.")
            raise OSError("File could not be locked for evidence preservation.")
        resolved=ctypes.create_unicode_buffer(32768)
        if not self.api.GetFinalPathNameByHandleW(self.handle,resolved,len(resolved),0):
            self.close();raise OSError("Locked file identity unavailable.")
        final=resolved.value.removeprefix("\\\\?\\")
        if Path(final).resolve()!=Path(path).absolute():
            if create:self.delete_on_close()
            self.close();raise ValueError("File identity left its selected path.")

    def read(self,max_bytes=8388608):
        raw=bytearray();buffer=ctypes.create_string_buffer(65536)
        while True:
            count=wintypes.DWORD()
            if not self.api.ReadFile(self.handle,buffer,len(buffer),ctypes.byref(count),None):
                raise OSError("Locked evidence could not be read.")
            if not count.value:break
            raw.extend(buffer.raw[:count.value])
            if len(raw)>max_bytes:raise ValueError("Locked evidence exceeds the byte budget.")
        return bytes(raw)

    def delete_on_close(self):
        disposition=ctypes.c_ubyte(1)
        if not self.api.SetFileInformationByHandle(self.handle,4,ctypes.byref(disposition),ctypes.sizeof(disposition)):
            raise OSError("Locked evidence could not be removed from its original location.")

    def write(self,raw,cancellation=None):
        try:
            for offset in range(0,len(raw),65536):
                if cancellation:cancellation.raise_if_cancelled()
                chunk=raw[offset:offset+65536];written=wintypes.DWORD()
                buffer=ctypes.create_string_buffer(chunk)
                if not self.api.WriteFile(self.handle,buffer,len(chunk),ctypes.byref(written),None) or written.value!=len(chunk):
                    raise OSError("Restored bytes could not be preserved completely.")
            if not self.api.FlushFileBuffers(self.handle):raise OSError("Restored bytes could not be flushed.")
        except BaseException:
            self.delete_on_close()
            raise

    def close(self):
        if self.handle:self.api.CloseHandle(self.handle);self.handle=None

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def processes(pids=(), limit=128):
    if os.name != "nt":
        raise RuntimeError("Windows process collector is unavailable on this host.")
    if not pids:
        api = ctypes.WinDLL("psapi",use_last_error=True)
        values = (wintypes.DWORD * 4096)()
        used = wintypes.DWORD()
        if not api.EnumProcesses(values,ctypes.sizeof(values),ctypes.byref(used)):
            raise OSError("Process enumeration unavailable.")
        pids = list(values)[:used.value // ctypes.sizeof(wintypes.DWORD)]
    rows, denied = [], 0
    for pid in list(pids)[:limit]:
        try:
            with ProcessHandle(pid) as process:
                rows.append(process.identity)
        except (OSError,ValueError):
            denied += 1
    return {"records":rows,"inaccessible":denied,"truncated":len(pids)>limit}


def powershell_metadata(source):
    scripts = {
        "network":"@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Select-Object -First 64 LocalAddress,LocalPort,OwningProcess,State) | ConvertTo-Json -Compress",
        "startup":"@(Get-CimInstance Win32_StartupCommand -ErrorAction Stop | Select-Object -First 64 Name,Location,User) | ConvertTo-Json -Compress",
        "logs":"@(Get-WinEvent -FilterHashtable @{LogName='System';Level=1,2} -MaxEvents 16 -ErrorAction Stop | Select-Object Id,ProviderName,TimeCreated) | ConvertTo-Json -Compress"
    }
    if os.name != "nt" or source not in scripts:
        raise RuntimeError("Selected Windows metadata collector is unavailable.")
    completed = subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",scripts[source]],
        capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
    if completed.returncode or len(completed.stdout) > 65536:
        raise RuntimeError("Metadata collection failed or exceeded its output budget.")
    value = json.loads(completed.stdout.decode("utf-8-sig")) if completed.stdout.strip() else []
    return value if isinstance(value,list) else [value]
