"""First-party domain adapters. Owners retain storage, jobs and permissions."""
from __future__ import annotations

import re
import time
from dataclasses import replace
from pathlib import Path

from ..kernel import CapabilityDescriptor,ErrorCode,ExecutionResult,VerificationResult,VerificationStatus
from .contracts import IntentResolution,Operation
from .domains import schema,success,clarification
from .references import label,select_target


STATUS_DOMAINS=('builder','media','devices','automations','connectors','security','plugins','activity')


def snapshot(runtime,domain):
    if domain=='builder':return runtime.autonomous_builder.project_runtime.snapshot()
    if domain=='media':return runtime.media.status()
    if domain=='devices':return runtime.device_mesh.snapshot()
    if domain in {'automations','connectors','security'}:
        value=runtime.ambient.snapshot()
        return {key:value[key] for key in ({'automations':('enabled','health','watches','receipts'),
            'connectors':('connectors',),'security':('security',)}[domain]) if key in value}
    if domain=='plugins':return runtime.plugins.diagnostics()
    if domain=='activity':return {'workflows':runtime.agents.status()}
    raise ValueError('Unsupported workspace domain.')


def status_handler(controller,args,context):
    domain=args['domain'];value=snapshot(controller.runtime,domain)
    # Fresh observations are descriptive, never fabricated outcome badges.
    return success(f'{domain.title()} status read from the current workspace service.',domain=domain,
        snapshot=value,observed_at=time.time(),provenance='SYSTEM_STATE')


def verify_status(controller,result,context):
    # Verify origin through another owner read. Active job counters may advance.
    value=snapshot(controller.runtime,result.output['domain'])
    valid=isinstance(value,dict) and isinstance(result.output.get('snapshot'),dict)
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Existing workspace service independently reread; job counters are point-in-time observations.',) if valid else ())


def media_handler(controller,identifier,args,context):
    media=controller.runtime.media
    if identifier=='nlui.media.generate':
        from ..media_lab.intents import route_media_intent
        request=route_media_intent(args['request'])
        if request is None:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'No supported image or video request was identified.')
        generation_id,_future=media.submit(request,context)
        return success('Media generation queued. It is still running; use “show media status” to follow it.',
            generation_id=generation_id,queued=True,provenance='GENERATED')
    rows=[{**r,'id':r.get('generation_id') or r.get('id'),'created':r.get('created_at'),
        'title':r.get('request',{}).get('prompt') or r.get('generation_id') or r.get('id')}
        for r in media.history(limit=100)]
    if identifier=='nlui.media.history':
        return success(f'{len(rows)} saved media generation(s).',generations=rows,provenance='GENERATED')
    if identifier=='nlui.media.compare':
        complete=[r for r in rows if r.get('status')=='SUCCEEDED']
        if len(complete)<2:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Two completed local generations are needed for comparison.')
        # Explicit latest IDs come from the owner's ordered history; no invented image.
        pair=complete[:2];items=[]
        for row in pair:items.append({'id':row['id'],'artifact':media.artifact(row['id'])})
        return success('Loaded the latest two verified local generations for comparison.',media_items=items,provenance='GENERATED')
    active=next((r.get('id','') for r in context.metadata.get('nlui',{}).get('selected',()) if r.get('kind')=='generation'),'')
    chosen=select_target(args.get('reference','latest'),rows,active_id=active,kind='generation')
    if chosen.record is None:return clarification(chosen.question,chosen.choices)
    row=chosen.record;identifier_value=row['id']
    if identifier=='nlui.media.cancel':
        cancelled=media.cancel(identifier_value)
        if not cancelled:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'That generation has no cancellable active job.')
        return success('Cancellation requested for the selected media generation.',generation_id=identifier_value,cancel_requested=True)
    artifact=media.artifact(identifier_value)
    if identifier=='nlui.media.transform':
        from ..media_lab.contracts import ImageRequest,VideoRequest
        from ..unified_intelligence import PermissionState
        if artifact.get('frames'):return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Choose an actual image source for this workflow; video editing needs a compatible video adapter.')
        action=args['action'];request=(VideoRequest(args['request'],intent='IMAGE_TO_VIDEO',reference_images=(artifact['path'],)) if action=='animate' else
            ImageRequest(args['request'],intent='IMAGE_VARIATION' if action=='variations' else 'IMAGE_TO_IMAGE',reference_images=(artifact['path'],),count=args.get('count',1)))
        try:media.select_model(request)
        except ValueError as exc:return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,str(exc))
        state=controller.kernel.permissions.controller.state('file_read')
        if state in {PermissionState.DENIED,PermissionState.UNSUPPORTED,PermissionState.OS_REQUIRED}:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'File-read permission does not allow using this reference image.')
        if state==PermissionState.ASK and not controller._port(context).execute('host.confirm',{'details':
                'Use this actual image as the reference for '+request.intent+'?\n'+Path(artifact['path']).name+'\nSHA-256: '+artifact['sha256']},context)['confirmed']:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Use of the reference image was not authorized.')
        generation_id,_future=media.submit(request,replace(context,active_files=(*context.active_files,artifact['path'])))
        return success('Queued the requested '+action+' using the verified source image. Generation is still running.',
            generation_id=generation_id,source_generation_id=identifier_value,queued=True,provenance='GENERATED')
    if identifier=='nlui.media.save':
        from ..unified_intelligence import PermissionState
        if controller.kernel.permissions.controller.state('file_write') in {PermissionState.DENIED,PermissionState.UNSUPPORTED,PermissionState.OS_REQUIRED}:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'File-write permission does not allow exporting this artifact.')
        destination=controller._port(context).execute('file.destination',{'name':Path(artifact['path']).name},context).get('destination','')
        if not destination:return ExecutionResult.failure(ErrorCode.CANCELLED,'File export cancelled.')
        exported=media.export(identifier_value,destination,replace(context,active_files=(*context.active_files,destination)))
        if not exported.success:return exported
        return success('Exported the actual generated file and verified its destination hash.',generation_id=identifier_value,
            exported={'destination':destination,'sha256':artifact['sha256']},provenance='GENERATED')
    return success('Loaded the verified generated artifact.',media_items=[{'id':identifier_value,'artifact':artifact}],provenance='GENERATED')


def verify_media(controller,identifier,result,context):
    value=result.output;media=controller.runtime.media
    if identifier in {'nlui.media.generate','nlui.media.transform'}:valid=media.result(value['generation_id']) is not None
    elif identifier=='nlui.media.save':
        from ..media_lab.storage import file_hash
        valid=file_hash(value['exported']['destination'])==value['exported']['sha256']==media.artifact(value['generation_id'])['sha256']
    elif identifier=='nlui.media.history':valid=all(media.result(r['id']) is not None for r in value['generations'])
    elif identifier=='nlui.media.cancel':
        row=media.result(value['generation_id']);valid=bool(value['cancel_requested'] and row is not None)
    else:valid=all(media.artifact(item['id'])['sha256']==item['artifact']['sha256'] for item in value['media_items'])
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Saved media records and artifact hashes independently reread.',) if valid else ())


def register_workspace_domains(controller):
    kernel=controller.kernel
    kernel.registry.register(CapabilityDescriptor('nlui.workspace.status','Read workspace status',provider='morice-nlui-domain',
        category='workspace',input_schema={'type':'object','required':['domain'],'properties':{
            'domain':{'type':'string','enum':list(STATUS_DOMAINS)}},'additionalProperties':False},
        supports_verification=True,idempotent=True,natural_language_intents=tuple('Show '+domain+' status' for domain in STATUS_DOMAINS),
        ui_action='Existing first-party workspace service',verification_contract='Independently reread the same service; snapshot is time stamped.'),
        lambda args,ctx:status_handler(controller,args,ctx),verifier=lambda result,expected,ctx:verify_status(controller,result,ctx))
    for verb,title,intents in (
        ('generate','Queue image or video generation',('Generate an image of a lighthouse','Make a video of clouds')),
        ('history','Show media history',('Show my generated images','Show my media history')),
        ('result','Show a verified generation',('Show my latest generated image','Open my last video')),
        ('compare','Compare generated artifacts',('Compare my latest two images','Compare my last two videos')),
        ('cancel','Cancel a generation',('Cancel the latest generation',)),
        ('transform','Edit, vary or animate an actual generated image',('Edit this image to brighten it','Make three variations of this image','Animate my latest image')),
        ('save','Export a verified generation to a selected file',('Save my latest image','Export this generation',))):
        identifier='nlui.media.'+verb
        input_schema=(schema('request',required=('request',)) if verb=='generate' else schema('reference'))
        if verb=='transform':input_schema={'type':'object','required':['action','request'],'properties':{
            'action':{'type':'string','enum':['edit','variations','animate']},'reference':{'type':'string','maxLength':500},
            'request':{'type':'string','maxLength':4000},'count':{'type':'integer','minimum':1,'maximum':8}},'additionalProperties':False}
        kernel.registry.register(CapabilityDescriptor(identifier,title,provider='morice-nlui-domain',category='media',
            input_schema=input_schema,supports_verification=True,supports_cancellation=True,
            idempotent=verb not in {'generate','cancel','transform','save'},natural_language_intents=intents,ui_action='Media history and verified artifact owner',
            verification_contract='Reread history and verify actual artifact hash, or observe cancellation admission.'),
            lambda args,ctx,cid=identifier:media_handler(controller,cid,args,ctx),
            verifier=lambda result,expected,ctx,cid=identifier:verify_media(controller,cid,result,ctx))


def resolve_workspace(clean,context,raw=None):
    match=re.fullmatch(r'(edit|restyle|animate) (?:my |the )?(this|that|latest|last|selected)? ?(?:generated )?(?:image|photo|picture)(?: .*)?',clean)
    if match:return IntentResolution(operations=(Operation('nlui.media.transform',{'action':'animate' if match[1]=='animate' else 'edit',
        'reference':match[2] or 'selected','request':raw or clean}),),route='domain')
    match=re.fullmatch(r'(?:make|create|generate) (one|two|three|four|five|six|seven|eight|[1-8]) variations (?:of|from) (?:my |the )?(this|that|latest|last|selected)? ?(?:generated )?image(?: .*)?',clean)
    if match:return IntentResolution(operations=(Operation('nlui.media.transform',{'action':'variations','count':int(match[1]) if match[1].isdigit() else
        ('one','two','three','four','five','six','seven','eight').index(match[1])+1,'reference':match[2] or 'selected','request':raw or clean}),),route='domain')
    match=re.fullmatch(r'(save|export) (?:my |the )?(this|that|latest|last|selected)? ?(?:generated )?(?:image|video|generation)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.media.save',{'reference':match[2] or 'selected'}),),route='domain')
    match=re.fullmatch(r'(?:show|check|what is|read) (?:the |my )?('+ '|'.join(STATUS_DOMAINS)+r')(?: lab)? (?:status|queue|activity)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.workspace.status',{'domain':match[1]}),),route='domain')
    aliases={'show connected devices':'devices','show security findings':'security','list my automations':'automations',
        'list my connectors':'connectors','show build progress':'builder','show agent activity':'activity','show installed plugins':'plugins'}
    if clean in aliases:return IntentResolution(operations=(Operation('nlui.workspace.status',{'domain':aliases[clean]}),),route='domain')
    if clean in {'show my generated images','show my media history','list generated videos','show my generations'}:
        return IntentResolution(operations=(Operation('nlui.media.history'),),route='domain')
    if re.fullmatch(r'compare (?:my |the )?(?:latest|last) two (?:images|videos|generations)',clean):
        return IntentResolution(operations=(Operation('nlui.media.compare'),),route='domain')
    match=re.fullmatch(r'(show|open|cancel|stop) (?:my |the )?(?:(.*?) )?(?:generated image|generated video|generation|video)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.media.'+('cancel' if match[1] in {'cancel','stop'} else 'result'),
        {'reference':match[2] or 'latest'}),),route='domain')
    return IntentResolution()
