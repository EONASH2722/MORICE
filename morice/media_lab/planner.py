"""Physical fit estimates and empirical limits; ResourceManager admits all work."""
from __future__ import annotations

import math
from dataclasses import asdict,dataclass,replace

from .contracts import Quality,VideoRequest,VideoModelDescriptor


@dataclass(frozen=True)
class ResourcePlan:
    decision: str
    mode: str
    vram_mb: int
    ram_mb: int
    request: dict
    reason: str = ''
    warnings: tuple[str,...] = ()

    def to_dict(self):return asdict(self)


class MediaResourcePlanner:
    def __init__(self,settings):self.settings=settings

    def estimate(self,model,request,mode='direct'):
        area=request.width*request.height/(512*512)
        frame_factor=max(1,getattr(request,'frames',1)/8) if isinstance(request,VideoRequest) else 1
        vram=math.ceil(model.estimated_vram_mb*(.65+.35*area)*frame_factor)
        weights=sum(f.get('bytes',0) for f in model.files if f.get('path','').endswith('.safetensors'))/2**20
        # CPU-offload keeps the same weights in system memory, not an additional
        # copy of every GPU activation. Account for weights, runtime overhead,
        # staging buffers and decoded frames; live RAM is checked separately.
        ram=math.ceil(max(model.estimated_ram_mb,weights+1024)+request.width*request.height*4*getattr(request,'frames',1)*3/2**20)
        if mode=='offload':vram=max(model.minimum_vram_mb,math.ceil(vram*.55));ram+=512
        if mode=='low_vram':vram=math.ceil(vram*.85)
        return vram,ram

    def plan(self,model,request,hardware,*,claims=(),profiles=(),allow_unload=False,backend_version=''):
        if request.intent not in model.capabilities:raise ValueError("This model does not implement the requested workflow.")
        if request.width%model.dimension_multiple or request.height%model.dimension_multiple:raise ValueError("Dimensions must match the model's supported multiple.")
        if request.loras and not model.supports_lora:raise ValueError("This model/backend does not support approved LoRAs.")
        if request.width>min(model.maximum_resolution[0],self.settings.max_resolution) or request.height>min(model.maximum_resolution[1],self.settings.max_resolution):
            if not request.allow_fallback:raise ValueError("Requested dimensions exceed model/application limits.")
            width=min(request.width,model.maximum_resolution[0],self.settings.max_resolution)
            height=min(request.height,model.maximum_resolution[1],self.settings.max_resolution)
            request=replace(request,width=width//model.dimension_multiple*model.dimension_multiple,height=height//model.dimension_multiple*model.dimension_multiple)
        if isinstance(request,VideoRequest):
            if not isinstance(model,VideoModelDescriptor):raise ValueError("A video model is required.")
            maximum=min(model.maximum_frames,self.settings.max_video_frames)
            if request.frames>maximum:
                if not request.allow_fallback:raise ValueError("Frame count exceeds validated model/application bounds.")
                request=replace(request,frames=maximum,duration=None)
        default_steps=model.default_steps
        if Quality(request.quality)==Quality.FAST:default_steps=min(default_steps,8)
        if Quality(request.quality)==Quality.QUALITY:default_steps=min(model.maximum_steps,default_steps*2)
        if request.intent in {'IMAGE_TO_IMAGE','IMAGE_VARIATION','INPAINT','OUTPAINT'}:
            default_steps=max(default_steps,math.ceil(1/request.strength))
        request=replace(request,steps=request.steps or default_steps,guidance=model.default_guidance if request.guidance is None else request.guidance)
        if request.steps>model.maximum_steps:raise ValueError("Steps exceed model limits.")
        if request.intent in {'IMAGE_TO_IMAGE','IMAGE_VARIATION','INPAINT','OUTPAINT'} and request.steps*request.strength<1:raise ValueError("Image strength and step count would perform no diffusion step.")
        if not hardware.total_vram_mb or not hardware.ram_available_mb:
            return ResourcePlan('UNSUPPORTED','direct',0,0,request.to_dict(),'Live GPU/RAM telemetry unavailable.')
        if self.settings.high_power_only_on_ac and hardware.ac_power is False:
            return ResourcePlan('UNSUPPORTED','direct',0,0,request.to_dict(),'High-power media is configured for AC power only.')
        if hardware.disk_free_mb<max(512,request.width*request.height*getattr(request,'frames',1)*12/2**20):
            return ResourcePlan('UNSUPPORTED','direct',0,0,request.to_dict(),'Insufficient free disk space.')
        valid=[p for p in profiles if p.get('model_hash')==model.sha256 and p.get('hardware_fingerprint')==hardware.fingerprint and p.get('backend_version')==backend_version and p.get('settings',{}).get('intent')==request.intent]
        warnings=[]
        if hardware.ac_power is False:warnings.append('Running on battery; generation may be slow.')
        if Quality(request.quality)==Quality.MAXIMUM_THAT_FITS:
            fits=[p for p in valid if p.get('status')=='SUCCEEDED' and p.get('peak_vram_mb',0)+self.settings.vram_margin_mb<=hardware.free_vram_mb and p.get('peak_ram_mb',0)+self.settings.ram_margin_mb<=hardware.ram_available_mb]
            if not fits:return ResourcePlan('UNSUPPORTED','direct',0,0,request.to_dict(),'MAXIMUM_THAT_FITS requires current successful benchmark data.')
            best=max(fits,key=lambda p:p['settings']['width']*p['settings']['height']*p['settings'].get('frames',1))
            config=best['settings'];request=replace(request,width=config['width'],height=config['height'],steps=config['steps'],**({'frames':config['frames'],'duration':None} if isinstance(request,VideoRequest) else {}))
            modes=[best['mode']]
        else:
            modes=['direct']
            if model.supports_low_vram:modes.append('low_vram')
            if model.supports_cpu_offload and self.settings.cpu_offload:modes.append('offload')
        if any(c.node_id=='local' and c.resource in {'GPU','LOCAL_MODEL'} for c in claims):
            vram,ram=self.estimate(model,request)
            return ResourcePlan('QUEUE','direct',vram,ram,request.to_dict(),'An active local model/GPU lease must finish first.')
        for mode in modes:
            vram,ram=self.estimate(model,request,mode)
            known_oom=any(p.get('status')=='OOM' and p.get('mode')==mode and p.get('vram_budget_mb',vram)==vram and p.get('settings',{}).get('width')==request.width and p.get('settings',{}).get('height')==request.height and p.get('settings',{}).get('frames',1)==getattr(request,'frames',1) for p in valid)
            if known_oom:continue
            if vram+self.settings.vram_margin_mb>hardware.total_vram_mb:continue
            if ram+self.settings.ram_margin_mb>hardware.ram_available_mb:
                if allow_unload and ram+self.settings.ram_margin_mb<=hardware.ram_total_mb:
                    return ResourcePlan('UNLOAD_IDLE_MODEL_THEN_RUN',mode,vram,ram,request.to_dict(),'Release owned idle model memory, then remeasure both RAM and VRAM before allocation.',tuple(warnings))
                continue
            if vram+self.settings.vram_margin_mb<=hardware.free_vram_mb:
                decision={'direct':'RUN_DIRECT','low_vram':'RUN_LOW_VRAM','offload':'RUN_CPU_OFFLOAD'}[mode]
                return ResourcePlan(decision,mode,vram,ram,request.to_dict(),warnings=tuple(warnings))
            if allow_unload:
                return ResourcePlan('UNLOAD_IDLE_MODEL_THEN_RUN',mode,vram,ram,request.to_dict(),'Unload only MORICE-owned idle models under shared GPU/model leases.',tuple(warnings))
        if request.allow_fallback:
            if isinstance(request,VideoRequest) and request.frames>8:
                smaller=replace(request,frames=8,duration=None,allow_fallback=False)
                fallback=self.plan(model,smaller,hardware,claims=claims,profiles=valid,backend_version=backend_version)
                if fallback.decision.startswith('RUN_'):return replace(fallback,decision='REDUCE_FRAMES',warnings=(*fallback.warnings,'Frame count reduced to fit resources.'))
            if request.width>256 or request.height>256:
                ratio=min(1,512/max(request.width,request.height));multiple=model.dimension_multiple
                width=max(64,int(request.width*ratio*.75)//multiple*multiple);height=max(64,int(request.height*ratio*.75)//multiple*multiple)
                smaller=replace(request,width=width,height=height,allow_fallback=False)
                fallback=self.plan(model,smaller,hardware,claims=claims,profiles=valid,backend_version=backend_version)
                if fallback.decision.startswith('RUN_'):return replace(fallback,decision='REDUCE_RESOLUTION',warnings=(*fallback.warnings,'Resolution reduced to fit resources.'))
        return ResourcePlan('UNSUPPORTED','direct',*self.estimate(model,request),request.to_dict(),'No configuration fits the measured RAM/VRAM safety margins or known OOM history.')
