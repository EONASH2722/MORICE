"""Shared Kernel/worker/resource integration; no model, agent or policy owner."""
from __future__ import annotations
import base64, hashlib, json, os, queue, re, shutil, subprocess, sys, threading, time, uuid
from pathlib import Path
from ..kernel import (CapabilityDescriptor,ResourceDescriptor,ResourceClaim,ExecutionContext,ExecutionResult,TaskStatus,
    ErrorCode,VerificationResult,VerificationStatus,CancellationToken)
from ..process_ownership import spawn_owned_process,reap_owned_job
from ..unified_intelligence import PermissionDecision,PermissionState,RiskClass
from .contracts import Limits,LimitReached,local_file,member_name,sha256,redacted

OPERATIONS=('inspect','decode','cipher','estimate','recover','audit','challenge','endpoint','vox','status','cancel','devices','bluetooth','export','report','clear')
HEAVY={'inspect','decode','cipher','estimate','recover','audit','challenge','endpoint','vox'}

def register(kernel,owner):
    kernel.resources.register(ResourceDescriptor('SECURITY_LAB_CPU'))
    kernel.resources.register(ResourceDescriptor('SECURITY_LAB_ADB'))
    for operation in OPERATIONS:
        identifier='security.lab.'+operation
        if kernel.registry.lookup(identifier):continue
        schema={'type':'object','properties':{'job_id':{'type':'string','maxLength':64}},'required':['job_id'],'additionalProperties':False}
        kernel.registry.register(CapabilityDescriptor(identifier,'Security Lab '+operation,provider='morice-security-lab',category='security',
            input_schema=schema,required_permissions=(('file_write',) if operation in {'export','report','clear'} else
                ('connected_devices',) if operation=='devices' else ('network','file_read') if operation in {'vox','endpoint'} else () if operation in {'status','cancel'} else ('file_read',)),
            supports_verification=True,supports_cancellation=True,timeout=1210 if operation in HEAVY else 60,
            verification_contract='Independently read the actual local receipt, artifact/export hashes or exact cache-removal outcome; preserve domain failure states.',
            supported_resources=(ResourceClaim('SECURITY_LAB_CPU'),) if operation in HEAVY else (),
            natural_language_intents=('Analyze this encrypted archive','Try the recovery hints I provided','Cancel recovery') if operation in {'inspect','recover','cancel'} else ()),
            lambda args,ctx,op=operation:owner().execute(op,args['job_id'],ctx),
            permission_check=(lambda args,ctx,op=operation:owner().permission(op,args,ctx)) if operation in {'devices','export','report','clear'} else None,
            verifier=lambda result,expected,context:owner().verify(result,context),
            on_completed=lambda result,context:owner().completed(result,context))

class SecurityLab:
    def __init__(self,runtime):
        self.runtime=runtime;self.directory=runtime.directory/'security-lab';self.directory.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.jobs={};self.secrets={};self.tokens={};self.approvals={};self.cleared=set();self.selected=None;self.latest=None;self.closed=False
        self.task_jobs={};self.completions={}
        from .devices import AndroidDiagnostics
        resource_owner='security-lab-adb-'+uuid.uuid4().hex
        def claim_adb():
            if not runtime.kernel.resources.acquire(resource_owner,(ResourceClaim('SECURITY_LAB_ADB'),)):raise RuntimeError('ADB resource is unavailable.')
        self.android=AndroidDiagnostics(claim_adb,lambda:runtime.kernel.resources.release(resource_owner))
        for path in sorted(self.directory.glob('*/receipt.json'),key=lambda p:p.stat().st_mtime)[-32:]:
            try:
                if path.stat().st_size>2*1024**2:continue
                value=json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(value,dict) or not re.fullmatch('[a-f0-9]{32}',value.get('id','')) or path.parent.name!=value['id']:continue
                if value.get('action') not in OPERATIONS or not isinstance(value.get('created'),(int,float)):continue
                if value.get('state') in {'QUEUED','RUNNING','VERIFYING'}:value.update(state='INTERRUPTED',status='CANCELLED')
                self.jobs[value['id']]=value;self.latest=value['id']
            except (ValueError,KeyError,TypeError,OSError):continue
    def select(self,path):
        actual=local_file(path,128*1024**2)
        self.selected=str(actual);return str(actual)
    def supply(self,passwords=(),*,key=None,conventions=(),hint_files=(),vault_alias='',credential_material=None):
        from .recovery import candidate_values
        values=list(passwords)
        for name in list(hint_files)[:8]:
            path=local_file(name,256*1024)
            text=path.read_text(encoding='utf-8')
            values.extend(m.group(1).strip() for m in re.finditer(r'(?im)^\s*(?:password|passphrase|recovery password)\s*[:=]\s*(.{0,512})$',text))
        if vault_alias:
            if not vault_alias.startswith('security_lab.recovery.'):raise ValueError('Select a recovery key saved explicitly for this lab.')
            value=self.runtime.platform_services.vault.get(vault_alias)
            if not value:raise ValueError('The selected authorized recovery key is unavailable.')
            key=base64.b64decode(value,validate=True)
        candidates=candidate_values(values,conventions)
        if len(json.dumps(candidates).encode())>1024**2:raise LimitReached('Supplied candidate material exceeds 1 MiB.')
        if key is not None and len(key)!=32:raise ValueError('This adapter requires a 32-byte direct key.')
        if credential_material and (not isinstance(credential_material,dict) or set(credential_material)-{'sender_token','recipient_token'} or any(not isinstance(v,str) or len(v)>16000 for v in credential_material.values())):raise ValueError('Invalid private credential input.')
        identifier=uuid.uuid4().hex
        with self.lock:
            if len(self.secrets)>=8:raise LimitReached()
            self.secrets[identifier]={'passwords':candidates,'key':base64.b64encode(key).decode() if key is not None else None}
            if credential_material:
                self.secrets[identifier]['credential_material']=dict(credential_material)
        return identifier
    def remember_key(self,alias,key):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',alias) or len(key)!=32:raise ValueError('Use a named 32-byte recovery key.')
        self.runtime.platform_services.vault.set('security_lab.recovery.'+alias,base64.b64encode(key).decode())
    def prepare(self,action,*,path=None,secret_ref='',limits=None,conversation='',options=None):
        if action not in OPERATIONS:raise ValueError('Unsupported Security Lab operation.')
        limits=limits or Limits()
        with self.lock:
            if self.closed:raise RuntimeError('Security Lab is closed.')
            if len(self.jobs)>=32:raise LimitReached('Lab receipt capacity reached; export and clear old jobs first.')
            if sum(p.stat().st_size for p in self.directory.rglob('*') if p.is_file())>512*1024**2:raise LimitReached('Local evidence quota reached.')
            identifier=uuid.uuid4().hex;directory=self.directory/identifier;directory.mkdir()
            value={'id':identifier,'action':action,'conversation':conversation,'created':time.time(),'state':'QUEUED','status':'QUEUED',
                'path':str(path or self.selected or ''),'limits':limits.to_dict(),'progress':{},'result':{},'artifacts':[],
                'options':dict(options or {}),'secret_ref':secret_ref}
            self.jobs[identifier]=value;self.tokens[identifier]=CancellationToken();self.latest=identifier
            self._save(value)
            return identifier
    def _save(self,job):
        # Secret material and even its transient reference are not serialized.
        with self.lock:
            public={k:v for k,v in job.items() if k not in {'secret_ref','options'}}
            destination=self.directory/job['id']/'receipt.json';temporary=destination.with_suffix('.tmp')
            temporary.write_text(json.dumps(public,ensure_ascii=True),encoding='utf-8');os.replace(temporary,destination)
    def snapshot(self,identifier=None,conversation=''):
        with self.lock:
            job=self.jobs.get(identifier or self.latest)
            if job is None:raise ValueError('Select a Security Lab result first.')
            if conversation and job.get('conversation') and job['conversation']!=conversation:raise PermissionError('Result belongs to another conversation.')
            self._finalize(job)
            return json.loads(json.dumps({k:v for k,v in job.items() if k not in {'secret_ref','options'}}))
    def completed(self,result,context):
        # Kernel completion follows independent verification and resource release.
        # A timed-out detached worker remains busy until its physical lease ends.
        with self.lock:
            identifier=self.task_jobs.pop(context.task_id,None)
            if identifier not in self.jobs:return
            self.completions[identifier]=result
            job=self.jobs[identifier];self._finalize(job)
            if isinstance(result.output,dict) and result.output.get('lab_job_id')==identifier:
                result.output.update(result=self.snapshot(identifier),lab_status=job['status'],message=self.describe(job))
    def _finalize(self,job):
        result=self.completions.get(job['id'])
        if job['state']!='VERIFYING' or result is None or result.execution_id in self.runtime.kernel.resources.snapshot():return
        self.completions.pop(job['id'],None)
        if not result.success:
            state='CANCELLED' if result.status==TaskStatus.CANCELLED else 'INTEGRITY_CHECK_FAILED'
            job.update(status=state,artifacts=[],result={'status':state,'artifacts':[],'message':'The shared Kernel did not verify this operation.'})
        job['state']='COMPLETED';self._save(job)
    def run(self,action,identifier,*,progress=None,approval_token='',cancellation=None,conversation=None):
        token=CancellationToken() if action in {'status','cancel','export','report','clear'} else self.tokens[identifier]
        if cancellation is not None:token.parent=cancellation
        context=ExecutionContext(conversation_id=self.jobs[identifier]['conversation'] if conversation is None else conversation,cancellation_token=token,progress=progress,approval_token=approval_token)
        if approval_token:
            prepared=self.approvals.pop(approval_token,None)
            task,options=prepared if prepared else (None,{})
            if task is None or task.capability_requirement!='security.lab.'+action or task.inputs!={'job_id':identifier}:
                return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'The exact user-approved operation is unavailable.')
            from dataclasses import replace
            context=replace(context,metadata={'lab_selected_job':identifier,'lab_options':options})
            result=self.runtime.kernel.run_task(task,context)
        else:result=self.runtime.kernel.dispatch('security.lab.'+action,{'job_id':identifier},context)
        if not result.success and self.jobs[identifier]['state']=='QUEUED':
            with self.lock:
                secret=self.secrets.pop(self.jobs[identifier].get('secret_ref',''),None)
                if secret:secret.clear()
                state='CANCELLED' if token.cancelled else 'NOT_STARTED'
                self.jobs[identifier].update(state='COMPLETED',status=state,result={'status':state,'message':'The shared Kernel did not authorize or admit this operation.'})
                self._save(self.jobs[identifier])
        return result
    def cancel(self,identifier=None):
        with self.lock:
            identifier=identifier or self.latest;token=self.tokens.get(identifier)
            if token and self.jobs[identifier]['state'] in {'QUEUED','RUNNING','VERIFYING'}:
                token.cancel('Cancelled by user.')
                job=self.jobs[identifier]
                if job['state']=='QUEUED':
                    secret=self.secrets.pop(job.get('secret_ref',''),None)
                    if secret:secret.clear()
                    job.update(state='COMPLETED',status='CANCELLED',result={'status':'CANCELLED','artifacts':[]});self._save(job)
                return True
            return False
    def approve(self,identifier,action):
        from ..kernel import TaskNode
        authority=self.runtime.kernel.permissions.controller;task=TaskNode('security.lab.'+action,{'job_id':identifier})
        token=authority.issue_one_use(task.task_id,task.capability_requirement,task.inputs)
        if len(self.approvals)>=32:raise LimitReached()
        self.approvals[token]=(task,json.loads(json.dumps(self.jobs[identifier].get('options',{}))))
        return token
    def permission(self,action,args,context):
        group='connected_devices' if action=='devices' else 'file_write'
        authority=self.runtime.kernel.permissions.controller;state=authority.state(group)
        if state==PermissionState.GRANTED:return PermissionDecision(True)
        if state!=PermissionState.ASK:return PermissionDecision(False,denied=(group,),reason='Existing '+group+' permission is unavailable.')
        if context.metadata.get('lab_selected_job')!=args['job_id']:return PermissionDecision(False,required=(group,),reason='Select this exact operation in Security Lab.')
        return authority.authorize(task_id=context.task_id,capability_id='security.lab.'+action,arguments=args,permissions=(),risk=RiskClass.HIGH,approval_token=context.approval_token)
    def _worker(self,request,job,context):
        command=([sys.executable,'--morice-security-worker'] if getattr(sys,'frozen',False) else [sys.executable,'-m','morice.security_lab.worker'])
        environment={k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','MORICE_SMOKE_UI'}}
        if not getattr(sys,'frozen',False):environment['PYTHONPATH']=str(Path(__file__).resolve().parents[2])
        process=spawn_owned_process(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env=environment,memory_limit_bytes=512*1024**2,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        received=queue.Queue(maxsize=256);reader_error=[]
        def read():
            total=0
            try:
                while line:=process.stdout.readline(2*1024**2+1):
                    total+=len(line)
                    if len(line)>2*1024**2 or total>4*1024**2:raise ValueError()
                    packet=json.loads(line)
                    try:received.put(packet,timeout=1)
                    except queue.Full:raise ValueError()
            except Exception:reader_error.append('Worker output could not be validated.')
        thread=threading.Thread(target=read,daemon=True);thread.start();deadline=time.monotonic()+request['limits']['seconds']+3;result=None
        try:
            process.stdin.write(json.dumps(request).encode());process.stdin.close()
            while True:
                if context.cancellation_token and context.cancellation_token.cancelled:return {'status':'CANCELLED','artifacts':[]}
                if time.monotonic()>deadline:return {'status':'RESOURCE_LIMIT_REACHED','artifacts':[],'message':'Owned worker time limit reached.'}
                try:packet=received.get(timeout=.05)
                except queue.Empty:
                    if process.poll() is not None and not thread.is_alive():break
                    continue
                if packet.get('type')=='progress':
                    with self.lock:job['progress']=packet['value']
                    if context.progress:context.progress('Security Lab: '+str(packet['value'].get('tested',packet['value'].get('completed',0)))+' verified attempts/steps')
                elif packet.get('type')=='result':result=packet['value']
            if reader_error:raise ValueError(reader_error[0])
            if result is None:return {'status':'RESOURCE_LIMIT_REACHED','artifacts':[],'message':'Isolated worker exited without a valid result; no success is claimed.'}
            return result
        finally:
            reap_owned_job(process)
            if process.poll() is None:process.kill();process.wait(timeout=2)
            thread.join(timeout=1)
            process.stdout.close()
    def execute(self,action,identifier,context):
        with self.lock:
            job=self.jobs.get(identifier)
            if job is None:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Unknown Security Lab operation.')
            if job['action']!=action and action not in {'status','cancel','export','report','clear'}:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Operation does not match its prepared job.')
            if context.conversation_id and job.get('conversation') and context.conversation_id!=job['conversation']:
                return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Result belongs to another conversation.')
            if action=='status':return self._result(job)
            if action=='cancel':self.cancel(identifier);return self._result(job,'Cancellation requested.')
            if action=='clear':return self._clear(job)
            if action in {'export','report'}:return self._export(job,context,report=action=='report')
            if job['state']!='QUEUED':return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'This job already ran; prepare a new explicit attempt.')
            job['state']='RUNNING';job['status']='RUNNING';self._save(job)
            self.task_jobs[context.task_id]=identifier
            secrets=self.secrets.pop(job.get('secret_ref',''),{})
        started=time.monotonic();source=None
        try:
            request={'action':action,'limits':job['limits'],'output':str(self.directory/identifier/'output'),**secrets}
            Path(request['output']).mkdir(exist_ok=True)
            if action in {'inspect','decode','cipher','estimate','recover','vox'}:
                source=local_file(job['path'],job['limits']['input_bytes']);source_hash=sha256(source)
                clone=self.directory/identifier/'input.bin'
                with source.open('rb') as read,clone.open('xb') as write:
                    for chunk in iter(lambda:read.read(65536),b''):
                        if context.cancellation_token:context.cancellation_token.raise_if_cancelled()
                        write.write(chunk)
                        if write.tell()>job['limits']['input_bytes']:raise LimitReached()
                if sha256(clone)!=source_hash:raise ValueError('Selected source changed while copying.')
                request['path']=str(clone);job['input_sha256']=source_hash
            elif action=='audit':request['path']=job['path']
            elif action=='endpoint':request['origin']=job['options'].get('origin','')
            if action=='cipher':request['cipher_method']=job['options'].get('cipher_method','ROT13')
            if action=='challenge':value=self._challenge(request,job,context)
            elif action in HEAVY:value=self._worker(request,job,context)
            elif action=='devices':
                options=context.metadata.get('lab_options',job['options']);command=options.get('command','discover')
                if command=='pair':value=self.android.connect(options['endpoint'],secrets.get('passwords',[''])[0])
                elif command=='connect':value=self.android.connect(options['endpoint'])
                elif command=='diagnose':value=self.android.diagnose(options['serial'],options.get('package',''))
                else:value=self.android.discover()
            elif action=='bluetooth':
                from .devices import bluetooth_metadata
                value=bluetooth_metadata()
            else:raise ValueError('Unsupported operation')
            if source is not None and sha256(source)!=job['input_sha256']:
                value={'status':'INTEGRITY_CHECK_FAILED','artifacts':[],'message':'The original changed externally while this operation ran.'}
            if source is not None:
                value['original_name']=source.name;value['claimed_extension']=source.suffix
            if value.get('status') in {'CANCELLED','RESOURCE_LIMIT_REACHED','INTEGRITY_CHECK_FAILED','WRONG_KEY','CANDIDATES_EXHAUSTED'}:
                shutil.rmtree(request['output'],ignore_errors=True);Path(request['output']).mkdir()
            with self.lock:
                job['result']=value;job['artifacts']=value.get('artifacts',[]);job['state']='VERIFYING';job['status']=value.get('status','COMPLETED')
                job['seconds']=time.monotonic()-started;self._save(job)
            return self._result(job)
        except Exception as exc:
            from ..kernel import CancelledError
            state='CANCELLED' if isinstance(exc,CancelledError) else 'RESOURCE_LIMIT_REACHED' if isinstance(exc,LimitReached) else 'INTEGRITY_CHECK_FAILED'
            output=self.directory/identifier/'output'
            if output.is_dir():shutil.rmtree(output)
            with self.lock:job.update(state='VERIFYING',status=state,result={'status':state,'error_type':type(exc).__name__,'artifacts':[]});self._save(job)
            return self._result(job)
        finally:
            secrets.clear()
            clone=self.directory/identifier/'input.bin'
            clone.unlink(missing_ok=True)
    def _result(self,job,message=''):
        snapshot=self.snapshot(job['id'])
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{'message':message or self.describe(snapshot),'lab_job_id':job['id'],
            'lab_status':job['status'],'result':snapshot,'provenance':'COMPUTED'},verification_required=True)
    def _challenge(self,request,job,context):
        from dataclasses import replace
        from .challenge import VULNERABLE_POLICY,FIXED_POLICY
        from ..project_build.workspace import baseline
        fixture=Path(request['output'])/'owned-fixture';fixture.mkdir();target=fixture/'authorization.py'
        target.write_text(VULNERABLE_POLICY,encoding='utf-8')
        before=self._worker({**request,'policy_path':str(target)},job,context)
        finding=(before.get('findings') or [{}])[0]
        if finding.get('before_status')!=200:return before
        inputs={'root':str(fixture),'changes':[{'path':'authorization.py','content':FIXED_POLICY,**baseline(target)}]}
        # The user requested this generated fixture repair. The existing scoped
        # patch permission, action journal, undo store and verifier own the write.
        token=self.runtime.agent.tools.permissions.grant('filesystem.apply_patch',inputs)
        patched=self.runtime.kernel.dispatch('filesystem.apply_patch',inputs,replace(context,approval_token=token))
        if not patched.success or not patched.verification or patched.verification.status!=VerificationStatus.VERIFIED:
            return {**before,'status':'PARTIAL','remediation':'Existing verified patch adapter did not complete; no repair success claimed.'}
        after=self._worker({**request,'policy_path':str(target),'expected_secure':True},job,context)
        secure=(after.get('findings') or [{}])[0].get('before_status')==403
        finding.update(state='RETESTED' if secure else 'VERIFIED',fix_status='FIXED' if secure else 'RETEST_FAILED',
            after_status=(after.get('findings') or [{}])[0].get('before_status'),
            before_source_sha256=hashlib.sha256(VULNERABLE_POLICY.encode()).hexdigest(),after_source_sha256=sha256(target))
        return {**after,'status':'COMPLETED' if secure else 'PARTIAL','findings':[finding],
            'tests':before.get('tests',[])+after.get('tests',[]),
            'remediation':{'capability':'filesystem.apply_patch','verified':True,'execution_id':patched.execution_id,
                'undo_available':bool((patched.output or {}).get('undo_id'))},
            'source_repair':'Actual generated source file patched through the existing Builder file adapter and Verified Action Runtime, then the HTTP regression reran in a new owned worker.'}
    @staticmethod
    def describe(job):
        value=job.get('result',{});message='Security Lab — '+job['action']+': '+job['status']
        if 'tested' in value:message+=f". Tested {value['tested']} of {value.get('total_candidates',0)} supplied candidates."
        if value.get('verification'):message+=' '+value['verification']
        if value.get('reason'):message+=' '+value['reason']
        if value.get('format'):message+=' Detected '+value['format']+'.'
        if value.get('limitation'):message+=' '+value['limitation']
        return message
    def verify(self,result,context):
        cleared=(result.output or {}).get('cleared_job_id') if isinstance(result.output,dict) else None
        if cleared:
            valid=cleared in self.cleared and not (self.directory/cleared).exists()
            return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,('Selected local cached job was removed; original input and exported files were not touched.',) if valid else ())
        identifier=(result.output or {}).get('lab_job_id') if isinstance(result.output,dict) else None
        try:
            job=self.snapshot(identifier,context.conversation_id)
            for artifact in job.get('artifacts',[]):
                path=Path(artifact['path']).resolve()
                if not path.is_relative_to(self.directory.resolve()) or sha256(path)!=artifact['sha256']:raise ValueError()
            for exported in (result.output or {}).get('lab_export',[]):
                if sha256(exported['path'])!=exported['sha256']:raise ValueError()
            valid=job['id']==identifier
        except (ValueError,PermissionError,OSError):valid=False
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
            ('Actual local job receipt and all recovered artifact hashes checked. Failure outcomes remain failure outcomes; this receipt is not a decryption-success claim.',) if valid else ())
    def _clear(self,job):
        identifier=job['id'];target=self.directory/identifier;resolved=target.resolve()
        if job['state'] in {'QUEUED','RUNNING','VERIFYING'}:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Cancel and finish this operation before clearing its cache.')
        if resolved.parent!=self.directory.resolve() or resolved.name!=identifier or target.is_symlink():return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Cached job path changed; no deletion was attempted.')
        shutil.rmtree(target);self.jobs.pop(identifier);self.tokens.pop(identifier,None);self.cleared.add(identifier)
        if len(self.cleared)>64:self.cleared.pop()
        self.latest=max(self.jobs,key=lambda key:self.jobs[key]['created']) if self.jobs else None
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{'message':'Selected cached receipt and unexported output removed. Original input and exports retained.','cleared_job_id':identifier},verification_required=True)
    def _export(self,job,context,report=False):
        from ..media_lab.artifacts import atomic_export
        destination=Path(context.metadata.get('lab_options',job.get('options',{})).get('export_destination','')).expanduser()
        if not str(destination) or str(destination)=='.' or destination.exists():return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Choose a new export file/directory; existing content is never overwritten.')
        if str(destination).startswith('\\\\'):return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Select a local export destination.')
        destination=destination.resolve();member_name(destination.name);exported=[]
        if report:
            temporary=self.directory/job['id']/('report-'+uuid.uuid4().hex+'.json')
            try:
                with temporary.open('x',encoding='utf-8') as stream:json.dump(self.snapshot(job['id']),stream,indent=2)
                atomic_export(temporary,destination,sha256(temporary))
            finally:temporary.unlink(missing_ok=True)
            # Independent JSON readback precedes the export receipt.
            if json.loads(destination.read_text(encoding='utf-8'))['id']!=job['id']:raise ValueError('Report readback failed.')
            exported.append({'path':str(destination),'sha256':sha256(destination)})
        else:
            if job['status'] not in {'RECOVERED','DECODED_CANDIDATE'} or not job['artifacts']:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'No verified output files exist for this job.')
            destination.mkdir()
            try:
                for index,item in enumerate(job['artifacts']):
                    source=Path(item['path']).resolve()
                    if not source.is_relative_to((self.directory/job['id']).resolve()) or sha256(source)!=item['sha256']:raise ValueError('Recovered artifact changed.')
                    target=destination/member_name(item.get('logical_name',source.name));target.parent.mkdir(parents=True,exist_ok=True)
                    atomic_export(source,target,item['sha256'])
                    if sha256(target)!=item['sha256']:raise ValueError('Export readback failed.')
                    exported.append({'path':str(target),'sha256':item['sha256']})
            except BaseException:
                # Roll back only our unchanged files; never remove unrelated
                # data another process placed into the new export directory.
                for item in exported:
                    path=Path(item['path'])
                    if path.is_file() and sha256(path)==item['sha256']:path.unlink()
                for folder in sorted((p for p in destination.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
                    try:folder.rmdir()
                    except OSError:pass
                try:destination.rmdir()
                except OSError:pass
                raise
        job.setdefault('exports',[]).append({'path':str(destination),'verified':True,'time':time.time()});self._save(job)
        result=self._result(job,'Verified '+('report' if report else 'recovered files')+' exported to '+str(destination));result.output['lab_export']=exported
        return result
    def shutdown(self):
        with self.lock:
            self.closed=True
            for token in self.tokens.values():token.cancel('MORICE is shutting down.')
            self.secrets.clear()
        self.android.close()
