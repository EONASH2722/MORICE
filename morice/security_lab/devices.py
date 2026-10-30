"""Typed diagnostics; a private ADB server preserves the user's other sessions."""
from __future__ import annotations
import ipaddress, json, os, re, shutil, socket, subprocess, sys, threading, time
from pathlib import Path
from ..process_ownership import spawn_owned_process,reap_owned_job
from .contracts import redacted

def adb_path():
    candidates=[os.environ.get('MORICE_ADB_PATH',''),shutil.which('adb') or '']
    for name in ('ANDROID_HOME','ANDROID_SDK_ROOT'):
        if os.environ.get(name):candidates.append(str(Path(os.environ[name])/'platform-tools/adb.exe'))
    candidates.extend(str(Path(root)/'platform-tools/adb.exe') for root in (
        Path(os.environ.get('LOCALAPPDATA',''))/'Android/Sdk',Path(r'C:\Program Files (x86)\Android\android-sdk')))
    return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()),None)

class AndroidDiagnostics:
    def __init__(self,claim=lambda:None,release=lambda:None):
        self.path=adb_path();self.server=None;self.port=None;self.lock=threading.RLock();self.claim=claim;self.release=release;self.claimed=False
    def _start(self):
        if not self.path:raise RuntimeError('Android Platform Tools unavailable. Set MORICE_ADB_PATH to the official adb executable.')
        if self.server is not None and self.server.poll() is None:return
        if self.server is not None:self.close()
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));self.port=probe.getsockname()[1]
        self.claim();self.claimed=True
        try:
            # ADB's Windows listener rejects an explicit hostname. tcp:PORT
            # binds loopback unless -a is supplied; clients use 127.0.0.1.
            self.server=spawn_owned_process([self.path,'-L',f'tcp:{self.port}','nodaemon','server'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except BaseException:self.release();self.claimed=False;raise
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if self.server.poll() is not None:self.close();raise RuntimeError('Owned ADB server could not start.')
            try:
                with socket.create_connection(('127.0.0.1',self.port),timeout=.1):return
            except OSError:time.sleep(.05)
        self.close();raise TimeoutError('ADB server startup timed out.')
    def _run(self,args,secret=None,timeout=8):
        self._start()
        process=spawn_owned_process([self.path,'-H','127.0.0.1','-P',str(self.port),*args],
            stdin=subprocess.PIPE if secret is not None else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            # ADB diagnostics commands themselves select bounded output (logcat -t etc.).
            output,_=process.communicate((secret+'\n').encode() if secret is not None else None,timeout=timeout)
            if len(output)>256*1024:raise RuntimeError('ADB output exceeded its diagnostic budget.')
            text=output.decode('utf-8',errors='replace')
            if secret:text=text.replace(secret,'[REDACTED]')
            if process.returncode:raise RuntimeError('ADB operation failed: '+redacted(text)[:300])
            return redacted(text)
        finally:
            try:reap_owned_job(process)
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=2)
    def discover(self):
        with self.lock:
            if not self.path:return {'status':'UNAVAILABLE','reason':'Official Android Platform Tools not installed/configured.','devices':[]}
            rows=[]
            for line in self._run(['devices','-l']).splitlines():
                if not line or line.startswith(('List of devices','*')):continue
                parts=line.split()
                if len(parts)<2:continue
                state={'device':'CONNECTED','unauthorized':'UNAUTHORIZED','offline':'OFFLINE'}.get(parts[1],'DEGRADED')
                rows.append({'serial':parts[0],'state':state,'transport':'ADB_WIRELESS' if ':' in parts[0] else 'ADB_USB',
                    'metadata':' '.join(parts[2:])[:500],'authorized':parts[1]=='device'})
            return {'status':'COMPLETED','devices':rows,'adb_executable':self.path,'server_scope':'Owned loopback-only ADB server; existing default server untouched.'}
    @staticmethod
    def endpoint(value):
        host,port=value.rsplit(':',1);ip=ipaddress.ip_address(host)
        if not ip.is_private or not 1<=int(port)<=65535:raise ValueError('Use the selected private-network device IP and debugging port.')
        return value
    def connect(self,endpoint,pairing_code=None):
        with self.lock:
            endpoint=self.endpoint(endpoint)
            if pairing_code is not None:
                if not re.fullmatch(r'\d{6}',pairing_code):raise ValueError('Enter the six-digit code shown by Android Wireless debugging.')
                message=self._run(['pair',endpoint],secret=pairing_code,timeout=20)
                return {'status':'PAIRING_REQUIRED' if 'Successfully paired' not in message else 'PAIRED','message':message,
                    'next_step':'Select the connection port shown by Android; pairing and connection ports can differ.'}
            message=self._run(['connect',endpoint],timeout=15)
            return {**self.discover(),'connection_result':message,'requested_endpoint':endpoint}
    def diagnose(self,serial,package=''):
        with self.lock:
            if not re.fullmatch(r'[A-Za-z0-9_.:\-]{1,180}',serial):raise ValueError('Invalid device identity.')
            row=next((r for r in self.discover()['devices'] if r['serial']==serial),None)
            if not row or not row['authorized']:return {'status':row['state'] if row else 'DISCONNECTED','message':'The exact selected device is not authorized/connected. No substitute device was used.'}
            if package and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+',package):raise ValueError('Invalid Android package identifier.')
            commands={'android_version':['shell','getprop','ro.build.version.release'],
                'identity':['shell','getprop','ro.product.model'],'battery':['shell','dumpsys','battery'],
                'storage':['shell','df','-h','/data'],'memory':['shell','head','-n','12','/proc/meminfo'],
                'crashes':['logcat','-d','-b','crash','-t','80']}
            if package:commands['package']=['shell','dumpsys','package',package]
            results={};errors=[]
            for name,args in commands.items():
                try:
                    if self._run(['-s',serial,'get-state']).strip()!='device':raise RuntimeError('Selected device disconnected.')
                    results[name]=self._run(['-s',serial,*args])[:12000]
                except (OSError,RuntimeError,TimeoutError,subprocess.TimeoutExpired):errors.append(name+': unavailable or device disconnected');break
            return {'status':'PARTIAL' if errors else 'COMPLETED','serial':serial,'package':package,'results':results,'errors':errors,
                'limitation':'Logs are actual device output; probable crash causes require the matching application source. Bluetooth does not grant ADB access.'}
    def close(self):
        with self.lock:
            if self.server is not None:
                reap_owned_job(self.server)
                if self.server.poll() is None:self.server.kill();self.server.wait(timeout=2)
                self.server=None
            if self.claimed:self.release();self.claimed=False

def bluetooth_metadata():
    shell=shutil.which('pwsh') or shutil.which('powershell')
    if os.name!='nt' or not shell:return {'status':'UNAVAILABLE','devices':[],'reason':'Windows paired-device metadata provider unavailable.'}
    command="Get-PnpDevice -Class Bluetooth -PresentOnly -ErrorAction Stop | Select-Object -First 64 FriendlyName,Status,InstanceId | ConvertTo-Json -Compress"
    process=spawn_owned_process([shell,'-NoProfile','-NonInteractive','-Command',command],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        raw,_=process.communicate(timeout=12)
        if process.returncode:return {'status':'UNAVAILABLE','devices':[],'reason':'Bluetooth metadata permission/provider unavailable.'}
        rows=json.loads(raw.decode('utf-8-sig') or '[]');rows=rows if isinstance(rows,list) else [rows]
        return {'status':'COMPLETED','devices':rows[:64],'scope':'Present Windows Bluetooth devices/adapters only; no discovery scan or GATT writes.',
            'limitation':'This provider does not certify paired consent, BLE battery/GATT access or general device control.'}
    except (ValueError,OSError,subprocess.TimeoutExpired):return {'status':'UNAVAILABLE','devices':[],'reason':'Bluetooth diagnostic query did not complete.'}
    finally:reap_owned_job(process)
