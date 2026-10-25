"""Exact observed file/device/finding references over existing Mesh and Security."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

from ..kernel import CapabilityDescriptor,ErrorCode,ExecutionResult,TaskNode,VerificationPolicy,VerificationResult,VerificationStatus
from ..unified_intelligence import PermissionState
from ..rich_response import Component
from ..rich_response.sources import ResponseSources
from .contracts import IntentResolution,Operation
from .domains import success,clarification
from .references import select_target


def mesh_send(controller,args,context):
    mesh=controller.runtime.device_mesh
    if not mesh.enabled:return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,'Device Mesh is off. Enable it and pair the intended device in Devices first.')
    rows=[{**row,'id':row['node_id']} for row in mesh.registry.snapshot() if row['trust']=='trusted']
    reference=args.get('device_reference','')
    try:node=mesh.registry.resolve(reference);selected=next(row for row in rows if row['id']==node)
    except (ValueError,StopIteration):
        choice=select_target(reference,rows,kind='paired device')
        if choice.record is None:return clarification(choice.question,choice.choices,'device_reference')
        selected=choice.record;node=selected['id']
    if selected['capabilities'].get('file.receive') not in {'available','degraded'}:
        return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,'The selected device has no available file Inbox capability.')
    permission=controller.kernel.permissions.controller
    if permission.state('file_read')!=PermissionState.GRANTED or permission.state('node:'+node+':file.receive')!=PermissionState.GRANTED:
        return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Authorize local file reading and file.receive for this exact device in Devices, then resend. Existing denials remain in force.')
    target=controller._port(context).execute('response.inspect',{'kinds':('files','preview','mesh','assembly','media'),
        'reference':args.get('reference',''),'deduplicate_source':True},context)
    if target.get('choices'):return clarification('Which displayed source contains the file?',target['choices'],'reference')
    source=Component.from_dict(target['component']).source
    owner=ResponseSources(controller.runtime,context.conversation_id);snapshot=owner.resolve(source)
    files=[{'id':item.id,'title':item.name,'artifact':item} for item in snapshot.artifacts if item.available]
    artifact_ref=args.get('artifact','current')
    formats=[row for row in files if row['artifact'].path.suffix.casefold().lstrip('.')==artifact_ref.casefold()]
    chosen=select_target('current' if len(formats)==1 else artifact_ref,formats or files,kind='actual file')
    if chosen.record is None:return clarification(chosen.question,chosen.choices,'artifact')
    artifact=chosen.record['artifact']
    details='Send this actual file to the selected device Inbox?\n'+artifact.name+'\nSHA-256: '+artifact.sha256+'\nDevice: '+selected['name']+'\nDevice ID: '+node
    if not controller._port(context).execute('host.confirm',{'details':details},context)['confirmed']:
        return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'The file transfer was not authorized.')
    fresh=owner.resolve(source);actual=next((item for item in fresh.artifacts if item.id==artifact.id and item.available),None)
    if actual is None or actual.sha256!=artifact.sha256:raise ValueError('The actual file changed before transfer. Refresh its source first.')
    receipt=mesh.send_file(actual.path,node,context=context)
    return success('Transferred '+actual.name+' to '+selected['name']+' and verified the remote Inbox file hash.',
        mesh_transfer={'node_id':node,'source':str(actual.path),'sha256':actual.sha256,'size':actual.size,'receipt':receipt},provenance='SYSTEM_STATE')


def verify_mesh(controller,result,context):
    from ..device_mesh.transfers import file_hash
    value=result.output['mesh_transfer'];receipt=value['receipt']
    valid=(receipt.get('complete') and receipt.get('sha256')==value['sha256'] and receipt.get('size')==value['size']
        and file_hash(value['source'])==value['sha256'] and controller.runtime.device_mesh.store.get(value['node_id']) is not None)
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Existing authenticated Mesh adapter independently verified the remote Inbox bytes; local source hash reread.',) if valid else ())


def security_control(controller,args,context):
    service=controller.runtime.security;action=args['action']
    if action=='scan':
        if not service.enabled:return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,'Security monitoring is off. Choose its monitored sources and enable it in Security first.')
        result=controller.kernel.dispatch('security.scan',{},context)
        if not result.success:return result
        return success('Collected the configured security metadata. This scan does not establish that the PC is safe.',security_receipt=result.to_dict())
    rows=[{**row,'id':row['finding_id'],'title':row['summary'],'created':row['timestamp']} for row in service.snapshot()['findings'] if row['status']=='OPEN']
    selected=next((row['id'] for row in context.metadata.get('nlui',{}).get('selected',()) if row.get('kind')=='security_finding'),'')
    reference=args.get('reference','latest')
    if reference in {'selected','this','that','current'} and not selected:
        return clarification('Choose the actual finding to review first.',tuple({'id':row['id'],'label':row['title']} for row in rows))
    chosen=select_target(reference,rows,active_id=selected,kind='security finding')
    if chosen.record is None:return clarification(chosen.question,chosen.choices)
    finding=chosen.record
    if action=='read':
        context.metadata['nlui']['selected']=[{'kind':'security_finding','id':finding['id']}]
        return success('Selected security finding: '+finding['summary']+'\nRecommendation: '+finding['recommendation'],finding=finding,provenance='SYSTEM_STATE')
    authority=controller.kernel.permissions.controller
    if authority.state('security.contain')!=PermissionState.GRANTED:
        return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Containment is not authorized. Review and enable its permission in Security before requesting this action.')
    if finding['node_id']!='local':return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,'Remote containment needs an authorized adapter on that exact device; local actions cannot substitute for it.')
    if finding.get('process_id'):
        identity=service.select_process(finding['process_id'])
        if 'start_identity:'+str(identity['start_time']) not in finding['evidence'] or Path(identity['executable']).resolve()!=Path(finding['file_path']).resolve():
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'The process identity changed since this finding. Collect fresh evidence before containment.')
        capability='security.process.terminate';inputs=identity;details='Terminate this observed process?\n'+repr(identity)
    elif finding.get('file_path'):
        hashes=[text[7:] for text in finding['evidence'] if text.startswith('sha256:') and re.fullmatch('[a-f0-9]{64}',text[7:])]
        if len(hashes)!=1:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'This finding has no unique observed file hash. Collect fresh evidence first.')
        capability='security.file.quarantine';inputs={'path':finding['file_path'],'sha256':hashes[0],'reason':'User-selected finding '+finding['finding_id']}
        details='Preserve this file in protected quarantine and remove its original?\n'+finding['file_path']+'\nSHA-256: '+hashes[0]
    else:return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,'This finding has no implemented containment target. Review its recommendation in Security.')
    if not controller._port(context).execute('host.confirm',{'details':details},context)['confirmed']:
        return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Containment was not confirmed. No substitute action was attempted.')
    task=TaskNode(capability,inputs,verification_policy=VerificationPolicy(required=True))
    token=authority.issue_one_use(task.task_id,capability,inputs)
    result=controller.kernel.run_task(task,replace(context,approval_token=token))
    if not result.success:return result
    return success('The selected containment action was independently observed and verified.',security_receipt=result.to_dict(),finding=finding,provenance='SYSTEM_STATE')


def verify_security(controller,result,context):
    value=result.output
    if value.get('security_receipt'):
        receipt=value['security_receipt'];valid=receipt['success'] and (receipt.get('verification') or {}).get('status')=='verified'
    else:valid=any(row['finding_id']==value['finding']['finding_id'] and row['evidence']==value['finding']['evidence'] for row in controller.runtime.security.snapshot()['findings'])
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Actual existing Security owner receipt or saved finding independently checked; no automatic permission grant or alternate target.',) if valid else ())


def register_device_security(controller):
    for identifier,title,schema,intents,handler,verifier in (
        ('nlui.mesh.send','Send an actual displayed file to a paired device',{'type':'object','required':['device_reference'],'properties':{
            key:{'type':'string','maxLength':160} for key in ('device_reference','reference','artifact')},'additionalProperties':False},
            ('Send this STL file to my tablet','Send that file to Node B'),mesh_send,verify_mesh),
        ('nlui.security.control','Review or act on an exact security finding',{'type':'object','required':['action'],'properties':{
            'action':{'type':'string','enum':['read','scan','contain']},'reference':{'type':'string','maxLength':500}},'additionalProperties':False},
            ('Show the latest security finding','Run a security scan','Contain the selected finding'),security_control,verify_security)):
        controller.kernel.registry.register(CapabilityDescriptor(identifier,title,provider='morice-nlui-domain',category='devices' if 'mesh' in identifier else 'security',
            input_schema=schema,supports_verification=True,supports_cancellation=True,preview_supported=True,natural_language_intents=intents,
            ui_action='Existing authenticated Mesh/Security owner with exact target confirmation',verification_contract='Existing owner verifies actual bytes/process state; no denied permission is granted or retried elsewhere.'),
            lambda args,ctx,h=handler:h(controller,args,ctx),verifier=lambda result,expected,ctx,v=verifier:v(controller,result,ctx))


def resolve_device_security(clean,context):
    match=re.fullmatch(r'send (?:this |that |the )?(?:(stl|pdf|png|svg|zip) )?file to (.{1,160})',clean)
    if match:return IntentResolution(operations=(Operation('nlui.mesh.send',{'device_reference':match[2],**({'artifact':match[1]} if match[1] else {})}),),route='domain')
    if clean in {'run a security scan','run security scan','scan the configured security sources'}:
        return IntentResolution(operations=(Operation('nlui.security.control',{'action':'scan'}),),route='domain')
    match=re.fullmatch(r'(show|review|contain|quarantine) (?:the |this )?(latest|last|selected|current|that)? ?(?:security )?finding',clean)
    if match:return IntentResolution(operations=(Operation('nlui.security.control',{'action':'read' if match[1] in {'show','review'} else 'contain','reference':match[2] or 'selected'}),),route='domain')
    if clean=='contain that' and any(row.get('kind')=='security_finding' for row in context.selected):
        return IntentResolution(operations=(Operation('nlui.security.control',{'action':'contain','reference':'selected'}),),route='domain')
    return IntentResolution()
