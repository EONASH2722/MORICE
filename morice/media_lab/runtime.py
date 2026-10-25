"""Media domain state over the one Kernel, scheduler and ResourceManager.

No media-specific graph, worker pool, permission authority or verifier engine.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import asdict,replace
from pathlib import Path

from ..kernel import (Availability,CancelledError,CapabilityHealth,ErrorCode,EventType,ExecutionContext,
    ExecutionResult,KernelEvent,Priority,ResourceClaim,ResourceDescriptor,TaskNode,TaskStatus,VerificationPolicy,VerificationResult,VerificationStatus)
from ..unified_intelligence import PermissionDecision,PermissionState
from .artifacts import atomic_export,verify_image,verify_video
from .capabilities import INTENTS,register_media_capabilities
from .contracts import ImageRequest,VideoRequest,ImageModelDescriptor,VideoModelDescriptor,JobState,MediaSettings,ModelState
from .hardware import probe_hardware
from .planner import MediaResourcePlanner,ResourcePlan
from .process import MediaWorkerError,recover_owned_temp
from .providers import ComfyUIProvider,DiffusersProvider
from .registry import MediaModelRegistry
from .storage import MediaHistory,atomic_json,file_hash,read_json


class MediaLab:
    def __init__(self,kernel,agents,data_root,*,settings=None,providers=None,hardware_probe=None,source_root=None,register=True):
        if agents.kernel is not kernel or kernel.scheduler is None:raise ValueError('Media Lab requires the existing kernel, coordinator and scheduler.')
        self.kernel=kernel;self.agents=agents;self.root=Path(data_root).resolve();self.directory=self.root/'media'
        self.source_root=Path(source_root or Path(__file__).resolve().parents[2]).resolve()
        if self.directory.is_relative_to(self.source_root):raise ValueError('Media artifacts/weights must remain outside the source tree; configure MORICE_LOCAL_DATA_DIR.')
        self.settings_path=self.directory/'metadata'/'settings.json'
        self.load_error=''
        if settings is None and self.settings_path.exists():
            try:
                value=read_json(self.settings_path);value['model_directories']=tuple(value.get('model_directories',()))
                settings=MediaSettings(**value)
            except (OSError,ValueError,TypeError) as exc:self.load_error=str(exc)
        self.settings=settings or MediaSettings()
        for name in ('outputs','cache','temp','benchmarks','metadata'):(self.directory/name).mkdir(parents=True,exist_ok=True)
        for name in ('image','video','motion','vae','lora','control','upscale'):(self.root/'models'/name).mkdir(parents=True,exist_ok=True)
        self.providers=providers if providers is not None else {
            'diffusers':DiffusersProvider(os.getenv('MORICE_MEDIA_PYTHON','') or self._configured_python()),
            'comfyui':ComfyUIProvider(os.getenv('MORICE_COMFYUI_URL',''),dedicated=os.getenv('MORICE_COMFYUI_DEDICATED','0')=='1',checkpoint_directory=os.getenv('MORICE_COMFYUI_MODELS',''))}
        self._hardware_probe=hardware_probe or (lambda:probe_hardware(self.root));self._hardware=None;self._hardware_at=0
        self._lock=threading.RLock();self._closed=False;self._jobs={};self._futures={};self._unsafe_owners=set()
        self._encoder_tools={'ffmpeg':None,'ffprobe':None,'encoder_probe':'NOT_CHECKED','encoder_checked_at':None}
        self.history_store=MediaHistory(self.directory/'metadata',self.settings.max_history)
        self.temp_recovery=recover_owned_temp(self.directory/'temp',self.history_store)
        self.models=MediaModelRegistry(kernel,self.directory/'metadata',self.source_root,self.providers)
        self.planner=MediaResourcePlanner(self.settings);self.profiles=[]
        profile_path=self.directory/'benchmarks'/'profile.json'
        if profile_path.exists():
            try:
                profile=read_json(profile_path)
                if profile.get('schema')!=1 or len(profile['configurations'])>1000:raise ValueError('Invalid benchmark profile.')
                self.profiles=profile['configurations']
            except (OSError,ValueError,KeyError,TypeError) as exc:self.load_error=str(exc)
        self._subscription=kernel.events.subscribe(self._event)
        if register:register_media_capabilities(kernel,lambda:self)
        # A provider advertises its interfaces in the shared registry, while
        # per-request selection always rechecks the model/workflow health.
        for cap in INTENTS:kernel.registry.set_status(cap,Availability.DEGRADED,'No model loads at startup; inspect a compatible local bundle before generation.')

    def _configured_python(self):
        candidate=self.root/'media-python'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        return str(candidate) if candidate.is_file() else ''

    def hardware(self,*,refresh=False):
        with self._lock:
            if refresh or self._hardware is None or time.monotonic()-self._hardware_at>1:
                self._hardware=self._hardware_probe();self._hardware_at=time.monotonic()
                ram=max(1,self._hardware.ram_total_mb-self.settings.ram_margin_mb)
                if self.kernel.resources.descriptor('RAM_OFFLOAD_MB') is None:
                    self.kernel.resources.register(ResourceDescriptor('RAM_OFFLOAD_MB',ram))
            return self._hardware

    def discover(self):
        if self.load_error or self.models.load_error:raise ValueError('Media metadata needs repair before new work.')
        return self.models.discover(self.settings.model_directories or (str(self.root/'models'/'image'),str(self.root/'models'/'video')))

    def inspect_model(self,identifier,token=None):
        model=self.models.inspect(identifier,token);self._refresh_capabilities()
        return model

    def _refresh_capabilities(self):
        models=self.models.search()
        for cap,intent in INTENTS.items():
            implemented=any(m.enabled and intent in m.capabilities and m.health in {ModelState.AVAILABLE,ModelState.UNBENCHMARKED,ModelState.DEGRADED} for m in models)
            self.kernel.registry.set_status(cap,Availability.AVAILABLE if implemented else Availability.UNAVAILABLE,
                '' if implemented else 'No inspected compatible local provider/model implements '+intent+'.')

    @staticmethod
    def request(value,intent=None):
        value=dict(value)
        if intent is not None and value.get('intent',intent)!=intent:raise ValueError('Request workflow differs from capability.')
        if intent:value['intent']=intent
        return (VideoRequest if value.get('intent') in {'TEXT_TO_VIDEO','IMAGE_TO_VIDEO','VIDEO_UPSCALE'} else ImageRequest).from_dict(value)

    def select_model(self,request):
        if request.model_id:model=self.models.get(request.model_id)
        else:
            preferred=self.settings.preferred_video_model if isinstance(request,VideoRequest) else self.settings.preferred_image_model
            eligible=[m for m in self.models.search(kind='video' if isinstance(request,VideoRequest) else 'image') if request.intent in m.capabilities and m.enabled and m.health in {ModelState.AVAILABLE,ModelState.UNBENCHMARKED,ModelState.DEGRADED}]
            if not eligible:raise ValueError('VIDEO PROVIDER UNAVAILABLE' if isinstance(request,VideoRequest) else 'IMAGE PROVIDER UNAVAILABLE: inspect a compatible local model.')
            model=next((m for m in eligible if m.model_id==preferred),min(eligible,key=lambda m:m.estimated_vram_mb))
        if not model.enabled or model.health not in {ModelState.AVAILABLE,ModelState.UNBENCHMARKED,ModelState.DEGRADED}:raise ValueError('Model health does not permit generation: '+model.health.value)
        if request.intent not in model.capabilities:raise ValueError('Model does not implement this media workflow.')
        return model

    def plan_request(self,request,*,ignore_owner=None,force_mode=None):
        model=self.select_model(request);hardware=self.hardware(refresh=ignore_owner is not None)
        health=self.providers[model.backend].health(model)
        if not health.get('available'):raise ValueError(health.get('reason','Provider unavailable.'))
        claims=[c for owner,lease in self.kernel.resources.snapshot().items() if owner!=ignore_owner for c in lease]
        plan=self.planner.plan(model,request,hardware,claims=claims,profiles=self.profiles,
            allow_unload=self._has_owned_idle_llm(),backend_version=health.get('version',''))
        if force_mode:
            if force_mode not in {'direct','low_vram','offload'}:raise ValueError('Invalid benchmark mode.')
            if force_mode=='offload' and not model.supports_cpu_offload:raise ValueError('Offload unsupported by this model.')
            if force_mode=='low_vram' and not model.supports_low_vram:raise ValueError('Low VRAM mode unsupported.')
            vram,ram=self.planner.estimate(model,request,force_mode)
            if any(p.get('model_hash')==model.sha256 and p.get('hardware_fingerprint')==hardware.fingerprint and p.get('backend_version')==health.get('version','') and p.get('status')=='OOM' and p.get('mode')==force_mode and p.get('settings',{}).get('width')==request.width and p.get('settings',{}).get('height')==request.height and p.get('settings',{}).get('intent')==request.intent and p.get('vram_budget_mb')==vram for p in self.profiles):raise ValueError('This benchmark configuration already OOMed under the same budget.')
            if vram+self.settings.vram_margin_mb>hardware.free_vram_mb or ram+self.settings.ram_margin_mb>hardware.ram_available_mb:raise ValueError('Benchmark mode exceeds physical safety margins.')
            plan=replace(plan,mode=force_mode,vram_mb=vram,ram_mb=ram)
        return model,plan

    @staticmethod
    def _has_owned_idle_llm():
        # Existing owned server/cache only. Never stop a foreign Ollama/server.
        from .. import llama_server,local_llama
        process=llama_server._SERVER_PROCESS
        return bool((process is not None and process.poll() is None) or local_llama._LLM_CACHE)

    def file_permission(self,args,ctx):
        request=args.get('request',{})
        files=tuple(request.get('reference_images',()))+((request.get('mask'),) if request.get('mask') else ())
        state=self.kernel.permissions.controller.state('file_read')
        if not files:return PermissionDecision(True)
        if state in {PermissionState.DENIED,PermissionState.UNSUPPORTED,PermissionState.OS_REQUIRED}:return PermissionDecision(False,denied=('file_read',),reason='Existing file-read policy forbids reference imports.')
        selected={str(Path(p).resolve()) for p in ctx.active_files}
        allowed=state==PermissionState.GRANTED or state==PermissionState.ASK and all(str(Path(p).resolve()) in selected for p in files)
        return PermissionDecision(allowed,required=() if allowed else ('file_read',),reason='' if allowed else 'Choose reference images/mask explicitly under the existing file permission policy.')

    def resource_claims(self,args,ctx,intent):
        request=self.request(args['request'],intent);model=self.select_model(request);self.hardware()
        # Queue preparation selects a mode; direct Kernel callers receive a
        # conservative estimate and are physically rechecked before inference.
        mode=args.get('_mode','direct')
        if mode not in {'direct','low_vram','offload'}:raise ValueError('Invalid media execution mode.')
        vram,ram=self.planner.estimate(model,request,mode)
        return (ResourceClaim('VRAM_MB',vram),ResourceClaim('RAM_OFFLOAD_MB',ram))

    def submit(self,request,context=None,*,priority=Priority.NORMAL,benchmark_mode=None):
        if self._closed:raise RuntimeError('Media Lab is closed.')
        if self.load_error or self.models.load_error:raise ValueError('Corrupt media metadata preserved; repair required.')
        if not isinstance(request,ImageRequest):request=self.request(request)
        if request.node_id!='local':
            mesh=self.kernel.mesh
            if mesh is None or not mesh.enabled:raise ValueError('Requested media node is unavailable; node pinning forbids local fallback.')
            return self._submit_remote(request,context or ExecutionContext(),Priority(priority))
        model=self.select_model(request);identifier=uuid.uuid4().hex
        ctx=context or ExecutionContext();cap=next(k for k,v in INTENTS.items() if v==request.intent)
        task=TaskNode(cap,{'request':replace(request,model_id=model.model_id).to_dict(),'generation_id':identifier},task_id=identifier,priority=Priority(priority),timeout=1800)
        record={'generation_id':identifier,'status':'QUEUED','request':task.inputs['request'],'model':model.model_id,'backend':model.backend,'artifacts':[],'warnings':[],'errors':[],'created_at':time.time(),'project_id':ctx.project_id,'research_project_id':ctx.research_project_id}
        with self._lock:
            if len(self._jobs)>=32:raise ValueError('Bounded media queue is full.')
            self._jobs[identifier]=record
            self.history_store.save(identifier,record)
        self.kernel.events.publish(KernelEvent(EventType.MEDIA_QUEUED,source='media',task_id=identifier,project_id=ctx.project_id,payload={'generation_id':identifier,'status':'QUEUED'}))
        def prepare(node,context):
            if not self.file_permission(node.inputs,context).allowed:raise PermissionError('Reference file access requires existing authorization.')
            original=self.request(record['request'])
            _,plan=self.plan_request(original,force_mode=benchmark_mode)
            if plan.decision=='QUEUE':self._stage(identifier,'WAITING_FOR_RESOURCES');return False
            if plan.decision in {'UNSUPPORTED','REMOTE_NODE'}:raise ValueError(plan.reason)
            node.inputs['request']=plan.request;node.inputs['_mode']=plan.mode
            with self._lock:record.update(plan=plan.to_dict(),warnings=list(plan.warnings))
            return True
        try:
            future=self.kernel.scheduler.enqueue_task(task,ctx,prepare=prepare,max_workers=self.agents.limits.max_workers)
        except Exception:
            with self._lock:self._jobs.pop(identifier,None)
            record.update(status='FAILED',errors=['Scheduler refused admission.']);self.history_store.save(identifier,record);raise
        public=Future();public.set_running_or_notify_cancel()
        with self._lock:self._futures[identifier]=public
        def collect(done):
            try:result=done.result()
            except Exception as exc:result=ExecutionResult.failure(ErrorCode.CANCELLED if done.cancelled() else ErrorCode.INTERNAL_ERROR,'Media queue failed.',detail=type(exc).__name__)
            self._record_completed(identifier,result,ctx)
            with self._lock:self._futures.pop(identifier,None);self._jobs.pop(identifier,None)
            public.set_result(result)
        future.add_done_callback(collect)
        return identifier,public

    def _submit_remote(self,request,context,priority):
        if request.reference_images or request.mask:
            raise ValueError('Remote reference media requires an explicitly approved hash-verified Mesh file transfer first.')
        identifier=uuid.uuid4().hex;cap=next(k for k,v in INTENTS.items() if v==request.intent)
        task=TaskNode(cap,{'request':request.to_dict(),'generation_id':identifier},task_id=identifier,priority=priority,
            constraints={'node_id':request.node_id},timeout=1800,
            verification_policy=VerificationPolicy(True,{'generation_id':identifier,'status':'SUCCEEDED'}))
        # prepare_task publishes the authenticated node descriptor and its
        # node-scoped claims. The shared scheduler cannot choose a local fallback.
        entry=self.kernel.prepare_provider(task,context)
        if entry is None or entry.descriptor.node_id!=request.node_id:
            raise ValueError('Pinned node has no compatible published media capability.')
        record={'generation_id':identifier,'status':'QUEUED','request':request.to_dict(),'model':request.model_id,
            'backend':'device_mesh','node_id':request.node_id,'artifacts':[],'warnings':[],'errors':[],'created_at':time.time()}
        with self._lock:self._jobs[identifier]=record;self.history_store.save(identifier,record)
        public=Future();public.set_running_or_notify_cancel()
        with self._lock:self._futures[identifier]=public
        try:future=self.kernel.scheduler.enqueue_task(task,context,max_workers=self.agents.limits.max_workers)
        except Exception:
            with self._lock:self._jobs.pop(identifier,None);self._futures.pop(identifier,None)
            record.update(status='FAILED',errors=['Remote admission refused.']);self.history_store.save(identifier,record);raise
        def collect(done):
            result=done.result();verified=result.success and result.verification and result.verification.status==VerificationStatus.VERIFIED
            record.update(status='SUCCEEDED' if verified else 'CANCELLED' if result.status==TaskStatus.CANCELLED else 'FAILED',
                remote_output=result.output,verification=result.verification.status.value if result.verification else None,
                warnings=['Remote artifacts require existing Mesh hash-verified transfer before local use.'],errors=[e.message for e in result.errors],completed_at=time.time())
            self.history_store.save(identifier,record)
            with self._lock:self._jobs.pop(identifier,None);self._futures.pop(identifier,None)
            self.kernel.events.publish(KernelEvent(EventType.MEDIA_COMPLETED if verified else EventType.MEDIA_FAILED,source='media',task_id=identifier,
                project_id=context.project_id,payload={'generation_id':identifier,'node_id':request.node_id,'status':record['status']}))
            public.set_result(result)
        future.add_done_callback(collect)
        return identifier,public

    def _stage(self,identifier,stage,**progress):
        if stage not in JobState.__members__:return
        with self._lock:
            record=self._jobs.get(identifier)
            if record is None:return
            changed=record['status']!=stage
            record.update(status=stage,progress=progress)
            if changed:self.history_store.save(identifier,record)

    def _event(self,event):
        if event.event_type==EventType.TASK_WAITING:self._stage(event.task_id,'WAITING_FOR_RESOURCES')

    def execute(self,args,ctx,intent):
        request=self.request(args['request'],intent);identifier=args.get('generation_id') or uuid.uuid4().hex
        if len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier):raise ValueError('Invalid owned generation identifier.')
        model=self.select_model(request);owner=ctx.metadata.get('execution_id')
        if not self.kernel.resources.current_holds('GPU') or not self.kernel.resources.current_holds('LOCAL_MODEL'):raise ValueError('Media execution requires shared GPU/model admission.')
        lease=self.kernel.resources.snapshot().get(owner,())
        with self._lock:
            if identifier not in self._jobs:
                if len(self._jobs)>=32:raise ValueError('Bounded media queue is full.')
                record={'generation_id':identifier,'status':'LOADING_MODEL','request':request.to_dict(),'model':model.model_id,'backend':model.backend,'artifacts':[],'warnings':[],'errors':[],'created_at':time.time()}
                self._jobs[identifier]=record;self.history_store.save(identifier,record)
        self._stage(identifier,'LOADING_MODEL')
        self.kernel.events.publish(KernelEvent(EventType.MEDIA_STARTED,source='media',task_id=identifier,project_id=ctx.project_id,payload={'generation_id':identifier,'status':'LOADING_MODEL'}))
        if self._has_owned_idle_llm():
            from ..llm_client import unload_idle_model_for_media
            unload_idle_model_for_media(self.kernel.resources,owner)
        # Measure AFTER idle model release, while exclusive GPU/model leases
        # prevent another MORICE model from loading in the observation gap.
        hardware=self.hardware(refresh=True)
        mode=args.get('_mode','direct');vram,ram=self.planner.estimate(model,request,mode)
        if any(sum(c.amount for c in lease if c.resource==key)<needed for key,needed in (('VRAM_MB',vram),('RAM_OFFLOAD_MB',ram))):
            return ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE,'Actual media settings exceed admitted resource claims.')
        if vram+self.settings.vram_margin_mb>hardware.free_vram_mb or ram+self.settings.ram_margin_mb>hardware.ram_available_mb:
            return ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE,'Physical RAM/VRAM changed before inference; no allocation attempted.')
        directory=self.directory/'temp'/identifier
        if directory.exists():raise ValueError('Generation temp directory already exists; no automatic replay.')
        directory.mkdir()
        self.models.verify_unchanged(model,ctx.cancellation_token)
        # Validate/decode explicitly selected input before sending it to a worker.
        for reference in request.reference_images:verify_image(reference,allow_constant=True,token=ctx.cancellation_token)
        if request.mask:verify_image(request.mask,allow_constant=True,token=ctx.cancellation_token)
        plan=ResourcePlan('RUN_DIRECT',mode,vram,ram,request.to_dict())
        started=time.perf_counter()
        def progress(event):
            self._stage(identifier,event.get('stage','GENERATING'),**{k:v for k,v in event.items() if k in {'step','total_steps','frame_chunk','total_chunks','image_index','total_images'}})
            if ctx.progress:ctx.progress(event.get('stage','GENERATING')+(f" step {event['step']}/{event['total_steps']}" if 'step' in event else ''))
        try:
            provider=self.providers[model.backend]
            ctx.metadata['media_ram_margin_mb']=self.settings.ram_margin_mb
            warnings=[]
            try:
                generated=provider.generate(identifier,model,request,plan,directory,ctx,progress)
            except MediaWorkerError as initial:
                if not initial.oom or not initial.cleanup_confirmed or not request.allow_fallback:raise
                self.kernel.events.publish(KernelEvent(EventType.MEDIA_OOM,source='media',task_id=identifier,payload={'generation_id':identifier,'status':'OOM'}))
                self._profile(model,request,mode,{'status':'OOM','error':str(initial)[:1000]})
                ctx.cancellation_token.raise_if_cancelled()
                multiple=model.dimension_multiple
                smaller=replace(request,allow_fallback=False,
                    **({'frames':8,'duration':None} if isinstance(request,VideoRequest) and request.frames>8 else
                       {'width':max(64,int(request.width*.75)//multiple*multiple),'height':max(64,int(request.height*.75)//multiple*multiple)}))
                if smaller.width==request.width and smaller.height==request.height and getattr(smaller,'frames',1)==getattr(request,'frames',1):raise
                fallback_vram,fallback_ram=self.planner.estimate(model,smaller,mode)
                fresh=self.hardware(refresh=True)
                if fallback_vram>vram or fallback_ram>ram or fallback_vram+self.settings.vram_margin_mb>fresh.free_vram_mb or fallback_ram+self.settings.ram_margin_mb>fresh.ram_available_mb:raise
                # The first process has been physically reaped. One bounded
                # retry uses smaller settings under the original shared leases.
                request=smaller;plan=ResourcePlan('REDUCE_FRAMES' if isinstance(request,VideoRequest) else 'REDUCE_RESOLUTION',mode,fallback_vram,fallback_ram,request.to_dict())
                warnings.append('One authorized OOM retry reduced settings; requested and actual settings are recorded separately.')
                generated=provider.generate(identifier,model,request,plan,directory,ctx,progress)
            ctx.cancellation_token.raise_if_cancelled()
            files=generated.get('files',[])
            if len(files)!=request.count:raise ValueError('Backend returned an unexpected output count.')
            self._stage(identifier,'VERIFYING')
            artifacts=[]
            for i,value in enumerate(files):
                path=Path(value).resolve()
                if not path.is_relative_to(directory.resolve()) or path.is_symlink():raise ValueError('Backend artifact left its owned temp directory.')
                metadata=verify_video(path,request.width,request.height,request.frames,request.fps,motion_required=bool(request.motion),token=ctx.cancellation_token) if isinstance(request,VideoRequest) else verify_image(path,request.width,request.height,allow_constant=request.allow_constant,token=ctx.cancellation_token)
                artifacts.append({**metadata,'artifact_id':identifier+':'+str(i),'generation_id':identifier,'provenance':'GENERATED_VISUAL'})
            metrics=generated.get('metrics',{});metrics.update(generation_wall_ms=(time.perf_counter()-started)*1000)
            observed=self.hardware(refresh=True)
            metrics.update(host_vram_before_mb=hardware.used_vram_mb,host_vram_after_mb=observed.used_vram_mb)
            metadata={'schema':1,'generation_id':identifier,'model':model.to_dict(),'model_hash':model.sha256,
                'backend':model.backend,'backend_version':generated.get('backend_version','unknown'),'request':request.to_dict(),
                'mode':mode,'artifacts':artifacts,'metrics':metrics,'hardware':hardware.to_dict(),
                'reproducibility':'Seed/settings reproduce only within a compatible deterministic backend/hardware/version scope.',
                'warnings':warnings+list(generated.get('warnings',[]))+(['SVD conditions on its reference image, not this text prompt.'] if isinstance(request,VideoRequest) else [])}
            atomic_json(directory/'generation.json',metadata)
            return ExecutionResult(TaskStatus.SUCCEEDED,True,metadata,artifacts=artifacts,metrics=metrics,verification_required=True)
        except MediaWorkerError as exc:
            if not exc.cleanup_confirmed:
                # ResourceManager remains the authority; an additional retained
                # owner blocks new model work until physical cleanup is verified.
                self._unsafe_owners.add(owner)
                self.kernel.resources.retain(owner,'Media backend cleanup unconfirmed.')
            if exc.oom:
                self.kernel.events.publish(KernelEvent(EventType.MEDIA_OOM,source='media',task_id=identifier,payload={'generation_id':identifier,'status':'OOM'}))
                self._profile(model,request,mode,{'status':'OOM','error':str(exc)[:1000]})
            return ExecutionResult.failure(ErrorCode.RESOURCE_UNAVAILABLE if exc.oom else ErrorCode.EXECUTION_FAILED,'Media generation failed safely.',detail=str(exc)[:1500])

    def verify_result(self,result,ctx):
        try:
            value=result.output;request=self.request(value['request']);identifier=value['generation_id']
            directory=(self.directory/'temp'/identifier).resolve()
            for artifact in result.artifacts:
                path=Path(artifact['path']).resolve()
                if not path.is_relative_to(directory) or file_hash(path,ctx.cancellation_token)!=artifact['sha256']:raise ValueError('Artifact changed before shared verification.')
                if isinstance(request,VideoRequest):verify_video(path,request.width,request.height,request.frames,request.fps,motion_required=bool(request.motion),token=ctx.cancellation_token)
                else:verify_image(path,request.width,request.height,allow_constant=request.allow_constant,token=ctx.cancellation_token)
            # Physical artifact publication remains inside Kernel verification,
            # while the existing GPU/CPU/DISK leases are still held. Visibility
            # as a completed job is committed only after Kernel finalization.
            ctx.cancellation_token.raise_if_cancelled()
            self._publish(identifier,result)
            return VerificationResult(VerificationStatus.VERIFIED,tuple(a['sha256'] for a in result.artifacts),'All generated files independently decode and match requested settings and hashes.')
        except Exception as exc:return VerificationResult(VerificationStatus.FAILED,message=str(exc)[:1000])

    def completed(self,result,ctx):
        identifier=(result.output or {}).get('generation_id') if isinstance(result.output,dict) else None
        identifier=identifier or ctx.metadata.get('task_inputs',{}).get('generation_id') or ctx.task_id
        self._record_completed(identifier,result,ctx)
        with self._lock:
            if identifier not in self._futures:self._jobs.pop(identifier,None)

    def _record_completed(self,identifier,result,ctx):
        with self._lock:
            record=self._jobs.get(identifier) or self.history_store.get(identifier)
            if record is None:return
            if record.get('terminal_recorded'):return
            if result.success and result.verification and result.verification.status==VerificationStatus.VERIFIED:
                try:
                    result.output['status']='SUCCEEDED'
                    atomic_json(self.directory/'outputs'/identifier/'generation.json',result.output)
                    record.update(status='SUCCEEDED',artifacts=result.artifacts,settings=result.output['request'],metrics=result.metrics,verification=result.verification.status.value,
                        model_hash=result.output['model_hash'],backend_version=result.output['backend_version'],mode=result.output['mode'],warnings=result.output.get('warnings',[]))
                    model=self.models.get(record['model'])
                    self.models.register(replace(model,health=ModelState.AVAILABLE,health_reason='Real local generation and decoded artifact verified.',maximum_tested_resolution=(result.output['request']['width'],result.output['request']['height'])))
                except Exception as exc:
                    result.success=False;result.status=TaskStatus.FAILED
                    from ..kernel import ExecutionError
                    result.errors.append(ExecutionError(ErrorCode.VERIFICATION_FAILED,'Media publication failed.',str(exc)[:1000]));record.update(status='FAILED',artifacts=[],errors=[str(exc)[:1000]])
            else:record.update(status='CANCELLED' if result.status==TaskStatus.CANCELLED else 'FAILED',artifacts=[],errors=[e.message+(': '+e.detail if e.detail else '') for e in result.errors])
            record.update(terminal_recorded=True,completed_at=time.time());self.history_store.save(identifier,record)
        kind={'SUCCEEDED':EventType.MEDIA_COMPLETED,'FAILED':EventType.MEDIA_FAILED,'CANCELLED':EventType.MEDIA_CANCELLED}[record['status']]
        self.kernel.events.publish(KernelEvent(kind,source='media',task_id=identifier,project_id=ctx.project_id,payload={'generation_id':identifier,'status':record['status']}))
        self._clean_temp(identifier)

    def _publish(self,identifier,result):
        output=self.directory/'outputs'/identifier
        if output.exists():raise ValueError('Output generation directory already exists.')
        stage=self.directory/'outputs'/('.publishing-'+identifier);stage.mkdir()
        try:
            artifacts=[]
            for i,item in enumerate(result.artifacts):
                source=Path(item['path']);destination=stage/('media_'+identifier+'_'+str(i)+source.suffix)
                atomic_export(source,destination,item['sha256'])
                artifacts.append({**item,'path':str(output/destination.name)})
            metadata={**result.output,'artifacts':artifacts,'status':'VERIFIED_PENDING_COMMIT'}
            atomic_json(stage/'generation.json',metadata)
            os.rename(stage,output)
            result.artifacts=artifacts;result.output=metadata
        except Exception:
            if stage.exists() and stage.resolve().parent==(self.directory/'outputs').resolve():shutil.rmtree(stage)
            raise

    def _clean_temp(self,identifier):
        if len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier):return
        path=(self.directory/'temp'/identifier).resolve()
        if self._unsafe_owners:return
        if path.parent==(self.directory/'temp').resolve() and path.is_dir() and not path.is_symlink():shutil.rmtree(path)

    def _profile(self,model,request,mode,record):
        hardware=self.hardware();health=self.providers[model.backend].health(model)
        value={**record,'model_id':model.model_id,'model_hash':model.sha256,'backend_version':health.get('version',''),
            'hardware_fingerprint':hardware.fingerprint,'mode':mode,'settings':request.to_dict(),'timestamp':time.time(),
            'vram_budget_mb':self.planner.estimate(model,request,mode)[0]}
        with self._lock:
            self.profiles.append(value);self.profiles=self.profiles[-1000:]
            atomic_json(self.directory/'benchmarks'/'profile.json',{'schema':1,'hardware':hardware.to_dict(),'configurations':self.profiles})
        return value

    def cancel(self,identifier):return self.kernel.scheduler.cancel(identifier)

    def history(self,limit=100):return self.history_store.list(limit)

    def result(self,identifier):return self.history_store.get(identifier)

    def artifact(self,identifier,index=0):
        record=self.result(identifier)
        if record is None or record['status']!='SUCCEEDED':raise ValueError('Generation has no completed verified artifacts.')
        if record.get('node_id') and record['node_id']!='local':raise ValueError('Remote artifacts must be hash-transferred through Device Mesh before local use.')
        item=record['artifacts'][index];path=Path(item['path']).resolve()
        if not path.is_relative_to((self.directory/'outputs'/identifier).resolve()) or file_hash(path)!=item['sha256']:raise ValueError('Stored artifact changed or escaped output directory.')
        return item

    def export(self,identifier,destination,context=None,*,index=0):
        return self.kernel.dispatch('media.artifact.export',{'generation_id':identifier,'index':index,'destination':str(Path(destination).resolve())},context or ExecutionContext())

    def export_permission(self,args,context):
        state=self.kernel.permissions.controller.state('file_write')
        selected={str(Path(value).resolve()) for value in context.active_files}
        allowed=state==PermissionState.GRANTED or state==PermissionState.ASK and str(Path(args['destination']).resolve()) in selected
        return PermissionDecision(allowed,required=() if allowed else ('file_write',),
            reason='' if allowed else 'Choose the exact export destination under the existing file-write policy. Denied permissions remain in force.')

    def export_handler(self,args,ctx):
        artifact=self.artifact(args['generation_id'],int(args.get('index',0)))
        receipt=atomic_export(artifact['path'],args['destination'],artifact['sha256'])
        return ExecutionResult(TaskStatus.SUCCEEDED,True,receipt,verification_required=True)

    def contact_sheet(self,identifiers,context=None):
        return self.kernel.dispatch('media.artifact.contact_sheet',{'generation_ids':list(identifiers)},context or ExecutionContext())

    def preview_handler(self,args,ctx):
        from .preview import contact_sheet
        identifiers=args.get('generation_ids',[])
        if not isinstance(identifiers,list) or not 1<=len(identifiers)<=16:raise ValueError('Choose 1..16 completed generations.')
        artifacts=[self.artifact(identifier) for identifier in identifiers]
        receipt=contact_sheet(self.directory/'cache',artifacts,limit_bytes=self.settings.disk_cache_limit_mb*2**20,token=ctx.cancellation_token)
        return ExecutionResult(TaskStatus.SUCCEEDED,True,receipt,verification_required=True)

    def clear_derived_cache(self):
        return self.kernel.dispatch('media.cache.clear',{})

    def cache_clear_handler(self,args,ctx):
        from .preview import clear_cache
        return ExecutionResult(TaskStatus.SUCCEEDED,True,clear_cache(self.directory/'cache'))

    def storage_stats(self):
        from .preview import storage_stats
        return storage_stats(self.directory,self.models.search())

    @staticmethod
    def verify_export(result,ctx):
        try:
            receipt=result.output
            valid=Path(receipt['path']).is_file() and file_hash(receipt['path'],ctx.cancellation_token)==receipt['sha256']
            return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,(receipt['sha256'],))
        except Exception as exc:return VerificationResult(VerificationStatus.FAILED,message=str(exc))

    def update_settings(self,value):
        settings=MediaSettings(**value);atomic_json(self.settings_path,asdict(settings));self.settings=settings;self.planner=MediaResourcePlanner(settings)
        return asdict(settings)

    def status(self):
        with self._lock:jobs=[dict(j) for j in self._jobs.values()];encoder_tools=dict(self._encoder_tools)
        active=any(j['status'] in {'GENERATING','LOADING_MODEL','ENCODING'} for j in jobs)
        pressure=self._hardware is not None and self._hardware.free_vram_mb<self.settings.vram_margin_mb
        return {'schema':1,'models':[m.to_dict() for m in self.models.search()],'queue':jobs,'history':self.history(),
            'hardware':self._hardware.to_dict() if self._hardware else None,'settings':asdict(self.settings),
            'load_state':'VRAM_PRESSURE' if pressure else 'MEDIA_GENERATING' if active else 'GPU_BUSY' if any(c.resource=='GPU' for lease in self.kernel.resources.snapshot().values() for c in lease) else 'NORMAL',
            'workers':[p for provider in self.providers.values() if getattr(provider,'processes',None) for p in provider.processes.snapshot()],
            'diagnostics':{'metadata_error':self.load_error or self.models.load_error,**encoder_tools,
                'video_available':any(isinstance(m,VideoModelDescriptor) and m.health==ModelState.AVAILABLE for m in self.models.search()),'profiles':len(self.profiles),'temp_recovery':self.temp_recovery}}

    def probe_encoder_tools(self):
        # Explicit diagnostics only. PATH can contain slow/inaccessible mounts;
        # a presentation status poll must never rescan it every 1.5 seconds.
        values={'ffmpeg':shutil.which('ffmpeg'),'ffprobe':shutil.which('ffprobe'),
            'encoder_probe':'CHECKED','encoder_checked_at':time.time()}
        with self._lock:self._encoder_tools=values
        return dict(values)

    def status_result(self):return ExecutionResult(TaskStatus.SUCCEEDED,True,self.status())

    def start_benchmark(self,args,ctx):
        from .benchmark import MediaBenchmark
        return MediaBenchmark(self).submit(args,ctx)

    def close(self):
        with self._lock:self._closed=True;futures=tuple(self._futures.items())
        for identifier,future in futures:self.cancel(identifier)
        deadline=time.monotonic()+5
        for _,future in futures:
            try:future.result(timeout=max(.01,deadline-time.monotonic()))
            except Exception:pass
        for provider in self.providers.values():provider.close()
        self.kernel.events.unsubscribe(self._subscription)
        if self._unsafe_owners:raise RuntimeError('Media backend cleanup requires reconciliation; shared leases retained.')
