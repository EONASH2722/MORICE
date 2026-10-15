"""Explicit, bounded discovery and integrity inspection of local model bundles."""
from __future__ import annotations

import hashlib
import json
import struct
import threading
from dataclasses import replace
from pathlib import Path

from ..kernel import Availability,CapabilityDescriptor,ExecutionResult,TaskStatus
from .contracts import ImageModelDescriptor,VideoModelDescriptor,ModelState
from .storage import atomic_json,file_hash,read_json


PIPELINES = {
    "StableDiffusionPipeline":("stable-diffusion",("TEXT_TO_IMAGE","IMAGE_TO_IMAGE","IMAGE_VARIATION","INPAINT","OUTPAINT")),
    "StableDiffusionInpaintPipeline":("stable-diffusion-inpaint",("INPAINT","OUTPAINT")),
    "StableDiffusionXLPipeline":("stable-diffusion-xl",("TEXT_TO_IMAGE","IMAGE_TO_IMAGE","IMAGE_VARIATION","INPAINT","OUTPAINT")),
    "StableDiffusionXLInpaintPipeline":("stable-diffusion-xl-inpaint",("INPAINT","OUTPAINT")),
    "StableVideoDiffusionPipeline":("stable-video-diffusion",("IMAGE_TO_VIDEO",)),
}
COMPONENTS={"UNet2DConditionModel","UNetSpatioTemporalConditionModel","AutoencoderKL","AutoencoderKLTemporalDecoder",
    "CLIPTextModel","CLIPTextModelWithProjection","CLIPTokenizer","CLIPImageProcessor","CLIPVisionModelWithProjection",
    "EulerDiscreteScheduler","EulerAncestralDiscreteScheduler","DDIMScheduler","PNDMScheduler","LMSDiscreteScheduler",
    "DPMSolverMultistepScheduler","StableDiffusionSafetyChecker"}


def inspect_safetensors(path):
    path=Path(path)
    with path.open("rb") as stream:
        prefix=stream.read(8)
        if len(prefix)!=8:raise ValueError("Truncated safetensors header.")
        length=struct.unpack("<Q",prefix)[0]
        if not 2<=length<=16*1024*1024 or length+8>path.stat().st_size:
            raise ValueError("Invalid safetensors header length.")
        header=json.loads(stream.read(length))
    if not isinstance(header,dict) or not any(k!="__metadata__" for k in header):raise ValueError("Empty tensor bundle.")
    spans=[];payload=path.stat().st_size-length-8
    sizes={"F64":8,"F32":4,"F16":2,"BF16":2,"I64":8,"I32":4,"I16":2,"I8":1,"U8":1,"BOOL":1}
    for name,entry in header.items():
        if name=="__metadata__":continue
        if not isinstance(entry,dict) or entry.get("dtype") not in sizes:raise ValueError("Unsupported tensor metadata.")
        shape=entry.get("shape");offset=entry.get("data_offsets")
        if not isinstance(shape,list) or len(shape)>8 or any(type(n)is not int or n<0 for n in shape):raise ValueError("Invalid tensor shape.")
        if not isinstance(offset,list) or len(offset)!=2 or any(type(n)is not int for n in offset):raise ValueError("Invalid tensor offsets.")
        size=sizes[entry['dtype']]
        for n in shape:size*=n
        if not 0<=offset[0]<=offset[1]<=payload or offset[1]-offset[0]!=size:raise ValueError("Tensor data bounds do not match shape.")
        spans.append(tuple(offset))
    spans.sort()
    if any(a[1]>b[0] for a,b in zip(spans,spans[1:])):raise ValueError("Overlapping tensor payloads.")
    return len(spans)


class MediaModelRegistry:
    def __init__(self,kernel,directory,source_root,providers):
        self.kernel=kernel;self.path=Path(directory)/"models.json";self.source_root=Path(source_root).resolve()
        self.providers=providers;self._models={};self._lock=threading.RLock();self.load_error=""
        if self.path.exists():
            try:
                value=read_json(self.path)
                if value.get('schema')!=1 or len(value['models'])>256:raise ValueError("Unknown/oversized model registry.")
                for item in value['models']:
                    item=dict(item);cls=VideoModelDescriptor if item.pop('kind','image')=='video' else ImageModelDescriptor
                    item['health']=ModelState(item['health'])
                    for key in ('capabilities','files','recommended_resolution','maximum_resolution'):
                        item[key]=tuple(item[key])
                    if item.get('maximum_tested_resolution'):item['maximum_tested_resolution']=tuple(item['maximum_tested_resolution'])
                    # Persisted metadata never establishes current loadability.
                    model=cls(**item)
                    self.register(replace(model,health=ModelState.DISCOVERED,health_reason="Health must be rechecked after restart."),persist=False)
            except (OSError,ValueError,TypeError,KeyError) as exc:self.load_error=str(exc)

    def _save(self):
        if self.load_error:raise ValueError("Corrupt registry preserved; explicit repair required.")
        atomic_json(self.path,{'schema':1,'models':[{**m.to_dict(),'kind':'video' if isinstance(m,VideoModelDescriptor) else 'image'} for m in self._models.values()]})

    def register(self,model,*,persist=True):
        path=Path(model.model_path).resolve()
        if path.is_relative_to(self.source_root):raise ValueError("Media model weights must remain outside the source tree.")
        if model.backend not in self.providers:raise ValueError("No configured adapter for model backend.")
        with self._lock:
            if len(self._models)>=256 and model.model_id not in self._models:raise ValueError("Model registry full.")
            self._models[model.model_id]=replace(model,model_path=str(path))
            cap='media.model.inspect.'+model.model_id
            if self.kernel.registry.lookup(cap) is None:
                self.kernel.registry.register(CapabilityDescriptor(cap,model.display_name,category='media-model',inline=True),
                    lambda inputs,ctx,identifier=model.model_id:ExecutionResult(TaskStatus.SUCCEEDED,True,self.get(identifier).to_dict()))
            if persist:self._save()
        return self.get(model.model_id)

    def get(self,identifier):
        with self._lock:
            if identifier not in self._models:raise ValueError("Unknown local media model: "+identifier)
            return self._models[identifier]

    def search(self,query='',kind=None):
        with self._lock:models=list(self._models.values())
        return [m for m in models if query.casefold() in (m.model_id+' '+m.display_name+' '+m.architecture).casefold() and (kind is None or isinstance(m,VideoModelDescriptor)==(kind=='video'))]

    def enable(self,identifier,enabled=True):
        model=self.get(identifier)
        return self.register(replace(model,enabled=bool(enabled),health=ModelState.DISCOVERED if enabled else ModelState.DISABLED))

    def discover(self,directories):
        found=[];seen=0
        for directory in tuple(directories)[:16]:
            root=Path(directory).resolve()
            if not root.is_dir():continue
            candidates=[root] if (root/'model_index.json').is_file() else []
            for child in root.iterdir():
                seen+=1
                if seen>512:break
                if child.is_dir() and not child.is_symlink() and (child/'model_index.json').is_file():candidates.append(child)
            for path in candidates:
                try:
                    index=read_json(path/'model_index.json',limit=64*1024);pipeline=index.get('_class_name','')
                    architecture,caps=PIPELINES.get(pipeline,('unknown',()))
                    cls=VideoModelDescriptor if 'VIDEO' in ' '.join(caps) else ImageModelDescriptor
                    identifier='local-'+hashlib.sha256(str(path).encode()).hexdigest()[:16]
                    if any(m.model_path==str(path) for m in self.search()):continue
                    fp16=any(path.glob('*/*.fp16.safetensors'))
                    model=cls(identifier,path.name,architecture,'diffusers',str(path),pipeline_class=pipeline,capabilities=caps,
                        precision='fp16' if fp16 else 'fp32',variant='fp16' if fp16 else None,
                        health=ModelState.DISCOVERED if pipeline in PIPELINES else ModelState.INCOMPATIBLE)
                    found.append(self.register(model))
                except (OSError,ValueError,TypeError):continue
        return found

    def inspect(self,identifier,token=None):
        model=self.get(identifier)
        if not model.enabled:return self.register(replace(model,health=ModelState.DISABLED))
        try:
            root=Path(model.model_path)
            if not root.exists():raise ValueError("Model path is missing.")
            if model.backend=='diffusers':
                index=read_json(root/'model_index.json',limit=64*1024)
                if index.get('_class_name') not in PIPELINES or index['_class_name']!=model.pipeline_class:raise ValueError("Unimplemented or mismatched pipeline class.")
                for key,component in index.items():
                    if key=='requires_safety_checker' and type(component) is bool:continue
                    if key.startswith('_'):continue
                    if component in (None,[None,None]):continue
                    if not isinstance(component,list) or len(component)!=2 or component[0] not in {'diffusers','transformers','stable_diffusion'} or component[1] not in COMPONENTS:
                        raise ValueError("Unreviewed executable model component: "+key)
                # Model-specific components and tokenizers must be present.
                if not any(root.glob('unet/*.safetensors')) or not any(root.glob('vae/*.safetensors')):
                    raise ValueError("Required safetensors components are missing.")
            candidates=[]
            for candidate in root.rglob('*') if root.is_dir() else [root]:
                candidates.append(candidate)
                if len(candidates)>512:raise ValueError("Model bundle exceeds bounded inventory.")
            files=[]
            for path in sorted(candidates):
                if path.is_symlink() or not path.resolve().is_relative_to(root.resolve() if root.is_dir() else root.parent.resolve()):raise ValueError("Model bundle contains a path escape.")
                if not path.is_file() or '.cache' in path.parts:continue
                if path.suffix in {'.py','.pkl','.pickle','.ckpt','.bin','.pt','.pth'}:raise ValueError("Executable/pickle model files are not accepted.")
                if path.suffix=='.safetensors':inspect_safetensors(path)
                if path.suffix=='.json':read_json(path)
                files.append({'path':str(path.relative_to(root)) if root.is_dir() else path.name,'bytes':path.stat().st_size,'sha256':file_hash(path,token)})
            if not files:raise ValueError("Empty model bundle.")
            digest=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
            provider=self.providers[model.backend]
            health=provider.health(model)
            state=ModelState.UNBENCHMARKED if health.get('available') else ModelState.MISSING_DEPENDENCY
            return self.register(replace(model,sha256=digest,files=tuple(files),health=state,health_reason=health.get('reason','Inspected; an actual isolated load/generation remains required.')))
        except (OSError,ValueError,KeyError,TypeError) as exc:
            return self.register(replace(model,health=ModelState.FAILED_HEALTH,health_reason=str(exc)[:1000]))

    def verify_unchanged(self,model,token=None):
        root=Path(model.model_path)
        if not model.sha256 or not model.files:raise ValueError("Model requires integrity inspection before use.")
        for item in model.files:
            path=(root/item['path']) if root.is_dir() else root
            if not path.resolve().is_relative_to(root.resolve() if root.is_dir() else root.parent.resolve()) or path.is_symlink() or path.stat().st_size!=item['bytes'] or file_hash(path,token)!=item['sha256']:
                raise ValueError("Model changed after inspection; recheck required.")
