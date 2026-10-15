"""CONTROLLED loopback HTTP contract, not an installed ComfyUI/model test."""
import io,json,struct,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

from morice.agent_runtime import AgentCoordinator
from morice.kernel import CapabilityKernel,ExecutionContext
from morice.media_lab.contracts import ImageModelDescriptor,ImageRequest
from morice.media_lab.runtime import MediaLab
from morice.media_lab.providers import ComfyUIProvider
from test_media_lab import hardware,wait_until


@pytest.fixture
def comfy(tmp_path):
    state={'running':False,'cancelled':False,'freed':False,'slow':False,'posts':[], 'redirect':False}
    image=Image.new('RGB',(64,64));image.putdata([(x*3,y*3,(x+y)*2) for y in range(64) for x in range(64)])
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value=None,binary=None):
            data=binary if binary is not None else json.dumps(value).encode() if value is not None else b''
            self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if state['redirect']:
                self.send_response(302);self.send_header('Location','http://127.0.0.1:1/forbidden');self.end_headers();return
            if self.path=='/system_stats':self.reply({'system':{'comfyui_version':'CONTROLLED-API-fixture'},'devices':[{'type':'cuda','torch_vram_total':0 if state['freed'] else 512*2**20}]})
            elif self.path=='/queue':self.reply({'queue_running':[[0,'owned-prompt']] if state['running'] else [],'queue_pending':[]})
            elif self.path.startswith('/history/'):
                if state['slow']:self.reply({})
                else:
                    state['running']=False
                    self.reply({'owned-prompt':{'status':{'status_str':'success'},'outputs':{'7':{'images':[{'filename':'fixture.png','subfolder':'','type':'output'}]}}}})
            elif self.path.startswith('/view?'):self.reply(binary=buffer.getvalue())
            else:self.send_error(404)
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))));state['posts'].append((self.path,body))
            if self.path=='/prompt':
                state['running']=True;state['freed']=False;self.reply({'prompt_id':'owned-prompt'})
            elif self.path=='/interrupt':
                assert body['prompt_id']=='owned-prompt';state['running']=False;state['cancelled']=True;self.reply()
            elif self.path=='/free':state['freed']=True;self.reply()
            elif self.path=='/queue':self.reply()
            else:self.send_error(404)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    folder=tmp_path/'checkpoints';folder.mkdir()
    checkpoint=folder/'controlled.safetensors';header=json.dumps({'w':{'dtype':'F32','shape':[1],'data_offsets':[0,4]}}).encode();checkpoint.write_bytes(struct.pack('<Q',len(header))+header+b'\0'*4)
    provider=ComfyUIProvider(f'http://127.0.0.1:{server.server_port}',dedicated=True,checkpoint_directory=folder)
    kernel=CapabilityKernel();agents=AgentCoordinator(kernel)
    lab=MediaLab(kernel,agents,tmp_path/'data',providers={'comfyui':provider},hardware_probe=hardware)
    lab.models.register(ImageModelDescriptor('comfy-fixture','CONTROLLED HTTP contract','controlled','comfyui',str(checkpoint),estimated_vram_mb=128,estimated_ram_mb=128,minimum_vram_mb=64,default_steps=2))
    lab.inspect_model('comfy-fixture')
    try:yield lab,provider,state
    finally:
        lab.close();agents.shutdown();kernel.shutdown();server.shutdown();server.server_close();thread.join(timeout=2)


def test_comfy_http_generation_decodes_and_verifies_model_unload(comfy):
    lab,provider,state=comfy
    identifier,future=lab.submit(ImageRequest('CONTROLLED HTTP image',model_id='comfy-fixture',width=64,height=64))
    assert future.result(timeout=8).success
    assert lab.artifact(identifier)['decoded'] and state['freed'] and not lab.kernel.resources.snapshot()
    assert any(path=='/free' and body=={'unload_models':True,'free_memory':True} for path,body in state['posts'])


def test_comfy_cancellation_interrupts_only_owned_prompt_and_unloads(comfy):
    lab,provider,state=comfy;state['slow']=True
    identifier,future=lab.submit(ImageRequest('CONTROLLED cancel',model_id='comfy-fixture',width=64,height=64))
    wait_until(lambda:state['running'])
    assert lab.cancel(identifier)
    assert not future.result(timeout=8).success
    assert state['cancelled'] and state['freed'] and not lab.kernel.resources.snapshot()
    assert lab.result(identifier)['status']=='CANCELLED'


def test_comfy_redirect_is_rejected_before_target_request(comfy):
    lab,provider,state=comfy;state['redirect']=True
    assert not provider.health()['available']
    with pytest.raises(ValueError,match='redirect'):
        provider._json('/queue')
