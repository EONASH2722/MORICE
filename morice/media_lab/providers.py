"""Local backend API adapters. Model execution never imports ML in the desktop."""
from __future__ import annotations

import ipaddress
import json
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .process import MediaWorkerError,OwnedMediaProcesses
from .storage import atomic_json,read_json


class _NoBackendRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError('Local media backend redirects are not trusted.')


class DiffusersProvider:
    backend='diffusers'
    def __init__(self,python_executable=None,processes=None):
        self.python_executable=str(Path(python_executable).resolve()) if python_executable else ''
        self.processes=processes or OwnedMediaProcesses();self._health=None
        self.worker_path=Path(__file__).with_name('worker.py').resolve()

    def health(self,model=None):
        if not self.python_executable or not Path(self.python_executable).is_file():
            return {'available':False,'reason':'No compatible external media Python interpreter configured.','version':''}
        if self._health is None:
            try:
                probe=subprocess.run([self.python_executable,'-I',str(self.worker_path),'--probe'],capture_output=True,text=True,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self._health=json.loads(probe.stdout.splitlines()[-1]) if probe.returncode==0 else {'available':False,'reason':'External backend probe failed.','version':''}
            except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):
                self._health={'available':False,'reason':'External backend probe unavailable.','version':''}
        return dict(self._health)

    def generate(self,identifier,model,request,plan,directory,context,progress):
        health=self.health(model)
        if not health.get('available'):raise MediaWorkerError(health.get('reason','Diffusers unavailable.'))
        job=Path(directory)/'request.json'
        atomic_json(job,{'generation_id':identifier,'model':model.to_dict(),'request':request.to_dict(),'plan':plan.to_dict(),'output_directory':str(Path(directory).resolve())})
        return self.processes.run(identifier,[self.python_executable,'-I',str(self.worker_path),'--job',str(job)],directory,context,progress=progress,ram_limit_mb=plan.ram_mb,ram_margin_mb=context.metadata.get('media_ram_margin_mb',2048))

    def close(self):self.processes.close()


SAFE_COMFY_NODES={'CheckpointLoaderSimple','CLIPTextEncode','EmptyLatentImage','KSampler','VAEDecode','VAEEncode',
    'SaveImage','LoadImage','LoadImageMask','VAEEncodeForInpaint','SetLatentNoiseMask','ImagePadForOutpaint',
    'LoraLoader','UpscaleModelLoader','ImageUpscaleWithModel','ImageScale','ImageBatch'}


def validate_workflow(workflow):
    if not isinstance(workflow,dict) or not 1<=len(workflow)<=64:raise ValueError('Workflow must be a bounded API graph.')
    if len(json.dumps(workflow).encode())>256*1024:raise ValueError('Workflow byte budget exceeded.')
    for identifier,node in workflow.items():
        if not isinstance(identifier,str) or not identifier.isdigit() or not isinstance(node,dict) or set(node)-{'class_type','inputs','_meta'}:
            raise ValueError('Invalid workflow node schema.')
        if node.get('class_type') not in SAFE_COMFY_NODES:raise ValueError('Unreviewed executable/custom node: '+str(node.get('class_type')))
        inputs=node.get('inputs',{})
        if not isinstance(inputs,dict) or len(inputs)>32:raise ValueError('Invalid node inputs.')
        for key,value in inputs.items():
            if isinstance(value,list) and (len(value)!=2 or value[0] not in workflow or type(value[1]) is not int or not 0<=value[1]<=8):
                raise ValueError('Invalid workflow connection.')
            if isinstance(value,str) and len(value)>8000:raise ValueError('Workflow input too large.')
            if key in {'ckpt_name','lora_name','upscale_model','image','filename_prefix'} and isinstance(value,str):
                if value.startswith(('/', '\\')) or ':' in value or '..' in Path(value.replace('\\','/')).parts:
                    raise ValueError('Workflow file path escapes backend storage.')
    # Connections must form an acyclic graph.
    visiting=set();done=set()
    def visit(identifier):
        if identifier in visiting:raise ValueError('Cyclic workflow.')
        if identifier in done:return
        visiting.add(identifier)
        for value in workflow[identifier]['inputs'].values():
            if isinstance(value,list):visit(value[0])
        visiting.remove(identifier);done.add(identifier)
    for identifier in workflow:visit(identifier)
    return workflow


class ComfyUIProvider:
    backend='comfyui'
    def __init__(self,url='',*,dedicated=False,checkpoint_directory=None):
        parsed=urllib.parse.urlsplit(url) if url else None
        if parsed and (parsed.scheme!='http' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {'','/'} or parsed.query or parsed.fragment):
            raise ValueError('Use an explicitly configured loopback ComfyUI HTTP endpoint.')
        if parsed:
            try:local=ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:local=parsed.hostname=='localhost'
            if not local:raise ValueError('Remote media must use the existing Device Mesh, not this local adapter.')
        self.url=url.rstrip('/');self.dedicated=bool(dedicated);self.client_id='morice-media-'+uuid.uuid4().hex
        self.checkpoint_directory=Path(checkpoint_directory).resolve() if checkpoint_directory else None
        self._version='';self._active=None
        self._opener=urllib.request.build_opener(_NoBackendRedirect())

    def _json(self,path,data=None):
        body=json.dumps(data).encode() if data is not None else None
        request=urllib.request.Request(self.url+path,data=body,headers={'Content-Type':'application/json'})
        with self._opener.open(request,timeout=3) as response:
            if response.geturl()!=self.url+path:raise ValueError('Backend redirects are not trusted.')
            content=response.read(4*1024*1024+1)
            if len(content)>4*1024*1024:raise ValueError('Backend response too large.')
            return json.loads(content) if content else {}

    def _release_models(self):
        queue=self._json('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise MediaWorkerError('Dedicated backend acquired other work; model cleanup is unconfirmed.',cleanup_confirmed=False)
        self._json('/free',{'unload_models':True,'free_memory':True})
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            stats=self._json('/system_stats');devices=stats.get('devices',[])
            cuda=[d for d in devices if d.get('type')=='cuda']
            if cuda and all(type(d.get('torch_vram_total')) in (int,float) and d['torch_vram_total']<=64*2**20 for d in cuda):return
            time.sleep(.05)
        raise MediaWorkerError('ComfyUI model memory release could not be verified.',cleanup_confirmed=False)

    def health(self,model=None):
        if not self.url or not self.dedicated or self.checkpoint_directory is None:return {'available':False,'version':'','reason':'A dedicated local ComfyUI service and its reviewed checkpoint directory are required.'}
        if model and (not Path(model.model_path).is_file() or not Path(model.model_path).resolve().is_relative_to(self.checkpoint_directory)):
            return {'available':False,'version':'','reason':'Checkpoint does not belong to the explicitly configured ComfyUI model directory.'}
        try:
            info=self._json('/system_stats');self._version=info.get('system',{}).get('comfyui_version','unknown')
            return {'available':True,'version':self._version,'reason':'API reachable; model loadability is verified during actual generation.'}
        except (OSError,ValueError):return {'available':False,'version':self._version,'reason':'ComfyUI local API unavailable.'}

    def generate(self,identifier,model,request,plan,directory,context,progress):
        # The first reviewed graph supports checkpoint text-to-image only. Edits,
        # videos and custom nodes are not advertised by this provider.
        if request.intent!='TEXT_TO_IMAGE':raise ValueError('ComfyUI adapter currently implements text-to-image only.')
        if request.output_format.upper()!='PNG':raise ValueError('The reviewed ComfyUI graph currently exports PNG only.')
        queue=self._json('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):raise MediaWorkerError('Dedicated backend has other work; refuse ownership ambiguity.')
        workflow={
            '1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':str(Path(model.model_path).resolve().relative_to(self.checkpoint_directory)).replace('\\','/')}},
            '2':{'class_type':'CLIPTextEncode','inputs':{'text':request.prompt,'clip':['1',1]}},
            '3':{'class_type':'CLIPTextEncode','inputs':{'text':request.negative_prompt,'clip':['1',1]}},
            '4':{'class_type':'EmptyLatentImage','inputs':{'width':request.width,'height':request.height,'batch_size':request.count}},
            '5':{'class_type':'KSampler','inputs':{'model':['1',0],'positive':['2',0],'negative':['3',0],'latent_image':['4',0],'seed':request.seed,'steps':request.steps,'cfg':request.guidance,'sampler_name':'euler','scheduler':'normal','denoise':1}},
            '6':{'class_type':'VAEDecode','inputs':{'samples':['5',0],'vae':['1',2]}},
            '7':{'class_type':'SaveImage','inputs':{'filename_prefix':'media_'+identifier,'images':['6',0]}}}
        validate_workflow(workflow)
        prompt_id=self._json('/prompt',{'prompt':workflow,'client_id':self.client_id})['prompt_id'];self._active=prompt_id
        completed=False;started=time.perf_counter()
        try:
            progress({'type':'progress','stage':'GENERATING'})
            while True:
                context.cancellation_token.raise_if_cancelled()
                if context.deadline is not None and time.monotonic()>=context.deadline:raise MediaWorkerError('ComfyUI generation timed out.')
                history=self._json('/history/'+urllib.parse.quote(prompt_id,safe='')).get(prompt_id)
                if history:
                    status=history.get('status',{})
                    if status.get('status_str')!='success':raise MediaWorkerError('ComfyUI workflow failed.',oom='out of memory' in json.dumps(status).lower())
                    files=[]
                    for output in history.get('outputs',{}).values():
                        for item in output.get('images',[]):
                            if len(files)>=request.count:raise ValueError('Backend returned too many images.')
                            if item.get('type')!='output':raise ValueError('Backend artifact is incomplete.')
                            name=item['filename'];subfolder=item.get('subfolder','')
                            if '/' in name or '\\' in name or '..' in Path(subfolder.replace('\\','/')).parts:raise ValueError('Backend artifact path escape.')
                            query=urllib.parse.urlencode({'filename':name,'subfolder':subfolder,'type':'output'})
                            with self._opener.open(self.url+'/view?'+query,timeout=5) as response:
                                data=response.read(32*1024*1024+1)
                            if len(data)>32*1024*1024:raise ValueError('Image exceeds byte budget.')
                            path=Path(directory)/('image_'+str(len(files))+'.png');path.write_bytes(data);files.append(str(path))
                    completed=True
                    return {'type':'result','files':files,'metrics':{'generation_ms':(time.perf_counter()-started)*1000},'backend_version':self._version}
                context.cancellation_token.wait(.1)
        finally:
            try:
                if not completed:
                    self._json('/queue',{'delete':[prompt_id]})
                    queue=self._json('/queue')
                    running=queue.get('queue_running',[])
                    if running and all(row[1]==prompt_id for row in running):self._json('/interrupt',{'prompt_id':prompt_id})
                    until=time.monotonic()+3
                    while time.monotonic()<until:
                        queue=self._json('/queue')
                        if not any(row[1]==prompt_id for row in queue.get('queue_running',[])+queue.get('queue_pending',[])):break
                        time.sleep(.05)
                    else:raise MediaWorkerError('ComfyUI cleanup unconfirmed; retain resource lease.',cleanup_confirmed=False)
                self._release_models()
            except MediaWorkerError:raise
            except Exception as exc:raise MediaWorkerError('ComfyUI physical cleanup unavailable: '+type(exc).__name__,cleanup_confirmed=False) from exc
            self._active=None

    def close(self):
        if self._active:raise RuntimeError('ComfyUI owned request is still active.')
