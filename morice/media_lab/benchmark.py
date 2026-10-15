"""Increasing safe benchmark jobs, chained through the existing scheduler.

No benchmark worker pool, sleeps, synthetic progress, or subjective quality score.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import replace

from ..kernel import ExecutionResult,TaskStatus,ExecutionContext,Priority
from .contracts import ImageRequest,VideoRequest,VideoModelDescriptor,Quality,ModelState
from .storage import atomic_json


class MediaBenchmark:
    def __init__(self,media):self.media=media;self.identifier=uuid.uuid4().hex;self.rows=[];self.configs=[];self.cursor=0;self.ooms=0;self.cancelled=False

    def submit(self,args,ctx):
        if getattr(self.media,'_benchmark_active',None):raise ValueError('A media benchmark is already active.')
        identifiers=args.get('model_ids',[])
        if not isinstance(identifiers,list) or len(identifiers)>4:raise ValueError('Benchmark at most four explicitly selected models.')
        models=[self.media.models.get(i) for i in identifiers] if identifiers else self.media.models.search()
        models=[m for m in models if m.enabled and m.health in {ModelState.AVAILABLE,ModelState.UNBENCHMARKED}][:4]
        modes=args.get('modes',['direct'])
        if not isinstance(modes,list) or not modes or len(modes)>3 or any(m not in {'direct','low_vram','offload'} for m in modes):raise ValueError('Invalid benchmark mode list.')
        for model in models:
            if isinstance(model,VideoModelDescriptor):
                references=tuple(args.get('reference_images',()))
                if 'IMAGE_TO_VIDEO' not in model.capabilities or len(references)!=1:continue
                for frames in (8,16):
                    if frames>min(model.maximum_frames,self.media.settings.max_video_frames):continue
                    for mode in modes:
                        request=VideoRequest(args.get('prompt','A slow cinematic camera movement.'),model.model_id,reference_images=references,width=model.recommended_resolution[0],height=model.recommended_resolution[1],frames=frames,output_format=args.get('video_format','GIF'),seed=1234,steps=model.default_steps)
                        self.configs.append((model,request,mode))
            else:
                if 'TEXT_TO_IMAGE' not in model.capabilities:continue
                for size in args.get('resolutions',[512,640,768]):
                    if type(size)is not int or size<64 or size>768:raise ValueError('Benchmark dimensions must start small, within 64..768.')
                    if size>min(*model.maximum_resolution,self.media.settings.max_resolution):continue
                    for mode in modes:
                        request=ImageRequest(args.get('prompt','A small observatory on a green hill at sunrise, detailed concept art.'),model.model_id,width=size,height=size,steps=model.default_steps,seed=1234,quality=Quality.BALANCED)
                        self.configs.append((model,request,mode))
        if not self.configs:raise ValueError('No inspected compatible models/workflows for this benchmark.')
        if len(self.configs)>24:raise ValueError('Benchmark configuration count exceeds its budget.')
        self.context=replace(ctx,deadline=min(ctx.deadline or float('inf'),time.monotonic()+1800))
        self.media._benchmark_active=self
        self._write('QUEUED');self._advance()
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{'benchmark_id':self.identifier,'status':'QUEUED','configurations':len(self.configs),'json_path':str(self.media.directory/'benchmarks'/('benchmark_'+self.identifier+'.json'))})

    def _write(self,status):
        value={'schema':1,'benchmark_id':self.identifier,'status':status,'configurations':len(self.configs),'completed':len(self.rows),'rows':self.rows,'ooms':self.ooms,'quality_assessment':'User review; no objective aesthetic score claimed.'}
        root=self.media.directory/'benchmarks';atomic_json(root/('benchmark_'+self.identifier+'.json'),value)
        lines=['# Generative media benchmark','','Status: '+status,'','| Model | Resolution | Steps/frames | Mode | Peak process RAM MiB | Peak allocated VRAM MiB | Generation ms | Status |','|---|---|---|---|---:|---:|---:|---|']
        for row in self.rows:
            s=row['settings'];lines.append(f"| {row['model_id']} | {s['width']}x{s['height']} | {s.get('frames',s['steps'])} | {row['mode']} | {row.get('peak_ram_mb','unmeasured')} | {row.get('peak_vram_mb','unmeasured')} | {row.get('generation_ms','unmeasured')} | {row['status']} |")
        (root/('benchmark_'+self.identifier+'.md')).write_text('\n'.join(lines)+'\n',encoding='utf-8')

    def _advance(self):
        if self.cancelled or self.media._closed or self.ooms>=2 or self.cursor>=len(self.configs):
            self._write('CANCELLED' if self.cancelled or self.media._closed else 'STOPPED_RESOURCE_DANGER' if self.ooms>=2 else 'COMPLETED')
            self.media._benchmark_active=None;return
        model,request,mode=self.configs[self.cursor];self.cursor+=1
        try:
            identifier,future=self.media.submit(request,self.context,priority=Priority.BACKGROUND,benchmark_mode=mode)
            self.current_generation=identifier
        except Exception as exc:
            self.rows.append(self.media._profile(model,request,mode,{'status':'UNSUPPORTED','error':str(exc)[:1000]}));self._advance();return
        def collect(done):
            result=done.result();record=self.media.result(identifier)
            is_oom=any('OOM' in e.detail or 'out of memory' in e.detail.lower() or 'RAM' in e.detail for e in result.errors)
            status='SUCCEEDED' if result.success else 'OOM' if is_oom else 'FAILED'
            if is_oom:self.ooms+=1
            metrics=record.get('metrics',{}) if record else {}
            self.rows.append(self.media._profile(model,request,mode,{'status':status,**metrics,'generation_id':identifier}))
            self._write('RUNNING');self._advance()
        future.add_done_callback(collect)

    def cancel(self):
        self.cancelled=True
        if getattr(self,'current_generation',None):self.media.cancel(self.current_generation)
