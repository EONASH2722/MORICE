"""Explicit live probes; no GPU polling, CUDA imports or model loading at boot."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class HardwareSnapshot:
    gpu_name: str = ""
    total_vram_mb: int = 0
    free_vram_mb: int = 0
    used_vram_mb: int = 0
    driver: str = ""
    ram_total_mb: int = 0
    ram_available_mb: int = 0
    cpu_count: int = 1
    disk_free_mb: int = 0
    gpu_temperature_c: float | None = None
    gpu_utilization: float | None = None
    gpu_power_w: float | None = None
    ac_power: bool | None = None
    measured_at: float = 0
    error: str = ""

    @property
    def fingerprint(self):
        value=(self.gpu_name,self.total_vram_mb,self.driver,self.ram_total_mb)
        return hashlib.sha256(json.dumps(value).encode()).hexdigest()

    def to_dict(self):
        return {**asdict(self),"fingerprint":self.fingerprint,"vram_scope":"host-wide, not process-attributed"}


def probe_hardware(directory):
    values={"cpu_count":os.cpu_count() or 1,"measured_at":time.time(),"disk_free_mb":shutil.disk_usage(directory).free//2**20}
    try:
        import psutil
        ram=psutil.virtual_memory();values.update(ram_total_mb=ram.total//2**20,ram_available_mb=ram.available//2**20)
        battery=psutil.sensors_battery()
        values["ac_power"]=battery.power_plugged if battery else None
    except (ImportError,OSError,AttributeError):
        values["error"]="RAM telemetry unavailable; GPU generation remains unavailable."
    executable=shutil.which("nvidia-smi")
    if executable:
        try:
            response=subprocess.run([executable,"--query-gpu=name,memory.total,memory.free,memory.used,driver_version,temperature.gpu,utilization.gpu,power.draw","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=3,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            if response.returncode:
                raise OSError("GPU telemetry command failed.")
            row=next(csv.reader(response.stdout.splitlines()))
            values.update(gpu_name=row[0].strip(),total_vram_mb=int(row[1]),free_vram_mb=int(row[2]),used_vram_mb=int(row[3]),driver=row[4].strip())
            for key,index in (("gpu_temperature_c",5),("gpu_utilization",6),("gpu_power_w",7)):
                try:values[key]=float(row[index])
                except ValueError:pass
        except (OSError,ValueError,StopIteration,subprocess.TimeoutExpired):
            values["error"]="Live NVIDIA GPU telemetry unavailable."
    else:
        values["error"]="No supported live GPU telemetry provider."
    return HardwareSnapshot(**values)
