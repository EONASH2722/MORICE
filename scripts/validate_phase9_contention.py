"""Actual owned CUDA GGUF residency, queued media, unload and reload."""
import json,os,socket,sys,time
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
os.environ.update(MORICE_LLAMA_SERVER_PATH=r'E:\MORICE_DATA\llama-cuda\llama-server.exe',MORICE_LLAMA_SERVER_PORT=str(port),MORICE_GPU_LAYERS='99',MORICE_CTX='2048',MORICE_NODE_NETWORK='0')
from morice.runtime_services import RuntimeServices
import morice.runtime_services as runtime_module
from morice.config import local_data_dir
from morice import llama_server,llm_client
from morice.media_lab.contracts import ImageRequest
from morice.media_lab.storage import atomic_json

data=local_data_dir();runtime=RuntimeServices(data/'runtime'/'phase9-contention',project_root=ROOT);runtime_module._RUNTIME_SERVICES=runtime
target=ROOT/'build'/'phase9-actual-contention.json';report={'scope':'ACTUAL owned CUDA llama-server, approved SD-Turbo and same shared resource authorities','port':port}
owned=None
try:
    media=runtime.media;media.inspect_model('sd-turbo-fp16');report['before']=media.hardware(refresh=True).to_dict()
    gguf=ROOT/'Parable-Qwen3-4B-Claude-Fable-5-GGUF-Q5_K_M.gguf'
    with llm_client._local_model_claim(str(gguf)):
        start=time.perf_counter();base=llama_server.ensure_server(str(gguf),2048,99,6,256);owned=llama_server._SERVER_PROCESS
        assert owned is not None
        report['llm_load_ms']=(time.perf_counter()-start)*1000;report['llm_loaded']=media.hardware(refresh=True).to_dict();report['llm_pid']=owned.pid
        identifier,future=media.submit(ImageRequest('A polished brass observatory on a grassy hill, warm sunrise',model_id='sd-turbo-fp16',seed=91077))
        deadline=time.monotonic()+10
        while media.result(identifier)['status']!='WAITING_FOR_RESOURCES':
            assert not future.done() and time.monotonic()<deadline;time.sleep(.02)
        report['queued_generation_id']=identifier;report['queue_status']=media.result(identifier)['status']
        assert not media.providers['diffusers'].processes.snapshot()
        direct=[]
        for i in range(30):
            stamp=time.perf_counter();assert runtime.kernel.dispatch('python.calculate',{'expression':'2+3'}).success;direct.append((time.perf_counter()-stamp)*1000)
        report['fast_actions_while_queued']={'count':len(direct),'max_ms':max(direct)}
        payload={'model':'local-gguf','messages':[{'role':'user','content':'Reply with the word ready.'}],'max_tokens':4,'temperature':0,'chat_template_kwargs':{'enable_thinking':False}}
        with urlopen(Request(base+'/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=60) as response:chat=json.loads(response.read())
        report['actual_llm_usage']=chat.get('usage');assert chat.get('choices') and report['actual_llm_usage']['completion_tokens']>0
        assert owned.poll() is None and not future.done()
        report['active_chat_not_interrupted']=True
    # Releasing the model call leaves its actual warm owned server. Media must
    # unload only that idle server, then measure before loading its own weights.
    result=future.result(timeout=180);report['media_result']=result.to_dict();report['media_history']=media.result(identifier)
    assert result.success and owned.poll() is not None
    report['owned_idle_llm_unloaded']=True;report['after_media']=media.hardware(refresh=True).to_dict()
    assert not runtime.kernel.resources.snapshot() and not media.providers['diffusers'].processes.snapshot()
    with llm_client._local_model_claim(str(gguf)):
        start=time.perf_counter();llama_server.ensure_server(str(gguf),2048,99,6,256)
        report['llm_reload_ms']=(time.perf_counter()-start)*1000;report['llm_reloaded']=media.hardware(refresh=True).to_dict()
    report['success']=True
except Exception as exc:
    report['success']=False;report['error']=type(exc).__name__+': '+str(exc);raise
finally:
    runtime.shutdown();report['shutdown']=runtime.shutdown_report
    report['owned_llm_stopped']=llama_server._SERVER_PROCESS is None;report['gpu_after']=media.hardware(refresh=True).to_dict()
    atomic_json(target,report)
    print(json.dumps({'output':str(target),'success':report.get('success'),'error':report.get('error'),'shutdown':report['shutdown']}),flush=True)
