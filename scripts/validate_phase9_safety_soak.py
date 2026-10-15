"""Actual CUDA OOM plus a CONTROLLED native UI/queue/artifact soak."""
import faulthandler,json,os,struct,sys,time,uuid
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
os.environ.update(QT_QPA_PLATFORM='offscreen',MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_NODE_NETWORK='0')
from PySide6.QtWidgets import QApplication
from morice.config import local_data_dir
from morice.runtime_services import RuntimeServices
import morice.runtime_services as runtime_module
from morice.media_lab.runtime import MediaLab
from morice.media_lab.hardware import probe_hardware
from morice.media_lab.contracts import ImageModelDescriptor,ImageRequest
from morice.media_lab.storage import atomic_json
from morice import settings
from morice.pyside_app import MoriceWindow
from test_media_lab import FixtureProvider
import psutil

data=local_data_dir();owned_root=data/'temp'/('phase9-safety-'+uuid.uuid4().hex);owned_root.mkdir()
output=ROOT/'build'/'phase9-safety-soak.json';trace=(ROOT/'build'/'phase9-safety-soak.trace').open('w');faulthandler.enable(file=trace);faulthandler.dump_traceback_later(60,repeat=True,file=trace)
class Provider(FixtureProvider):
    def generate(self,identifier,model,request,plan,directory,context,progress):
        if request.prompt=='actual-allocator-oom':
            return self.processes.run(identifier,[str(data/'media-python'/'Scripts'/'python.exe'),'-I',str(ROOT/'tests'/'fixtures'/'cuda_oom_worker.py')],directory,context,progress=progress,ram_limit_mb=1536,ram_margin_mb=2048)
        return super().generate(identifier,model,request,plan,directory,context,progress)

report={'scope':'ACTUAL bounded CUDA allocator OOM; recovery/soak images are CONTROLLED Pillow fixtures, not diffusion model validation','cases':[]}
app=QApplication([]);runtime=RuntimeServices(owned_root/'runtime',project_root=ROOT);runtime_module._RUNTIME_SERVICES=runtime;window=None
try:
    with patch('morice.settings._settings_dir',return_value=str(owned_root/'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false','desktop_pet_enabled':'false'})
        provider=Provider();media=MediaLab(runtime.kernel,runtime.agents,owned_root/'data',providers={'test':provider},register=False,hardware_probe=lambda:probe_hardware(data));runtime._media_lab=media
        folder=owned_root/'fixture-model';folder.mkdir();header=json.dumps({'w':{'dtype':'F32','shape':[1],'data_offsets':[0,4]}}).encode();(folder/'controlled.safetensors').write_bytes(struct.pack('<Q',len(header))+header+b'\0'*4)
        model=ImageModelDescriptor('controlled-safety','CONTROLLED safety contract','controlled','test',str(folder),estimated_vram_mb=128,estimated_ram_mb=128,minimum_vram_mb=64,default_steps=2)
        media.models.register(model);media.inspect_model(model.model_id)
        window=MoriceWindow(runtime,runtime.start());window.show();app.processEvents()
        rss_before=psutil.Process().memory_info().rss;ticks=0;latencies=[]
        for i in range(16):
            identifier,future=media.submit(ImageRequest('actual-allocator-oom' if i==0 else 'CONTROLLED UI recovery image',model_id=model.model_id,width=64,height=64,seed=i))
            start=time.perf_counter()
            while not future.done():
                stamp=time.perf_counter();app.processEvents();ticks+=1
                assert runtime.kernel.dispatch('python.calculate',{'expression':'2+3'}).success
                latencies.append((time.perf_counter()-stamp)*1000)
                if time.perf_counter()-start>90:media.cancel(identifier);raise TimeoutError('Bounded safety fixture timed out.')
                time.sleep(.03)
            result=future.result();record=media.result(identifier)
            report['cases'].append({'generation_id':identifier,'success':result.success,'result':result.to_dict(),'history':record})
            if i==0:assert not result.success and any('ACTUAL bounded CUDA OutOfMemoryError' in e.detail for e in result.errors)
            else:assert result.success and media.artifact(identifier)['decoded']
            assert not runtime.kernel.resources.snapshot() and not provider.processes.snapshot()
            atomic_json(output,report);print(json.dumps({'case':i,'success':result.success,'elapsed_s':time.perf_counter()-start}),flush=True)
        report.update(success=True,ui_scope='Actual MoriceWindow on offscreen Qt platform',ui_ticks=ticks,fast_action_p95_ms=sorted(latencies)[int(.95*(len(latencies)-1))],rss_before=rss_before,rss_after=psutil.Process().memory_info().rss,leases_after=0,owned_workers_after=provider.processes.snapshot(),hardware_after=media.hardware(refresh=True).to_dict())
except Exception as exc:
    report['success']=False;report['error']=type(exc).__name__+': '+str(exc);raise
finally:
    if window is not None:window.close();app.processEvents()
    runtime.shutdown();report['shutdown']=runtime.shutdown_report;atomic_json(output,report)
    faulthandler.cancel_dump_traceback_later();trace.close()
