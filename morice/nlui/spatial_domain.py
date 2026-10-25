"""The existing Spatial service owns locations, calculations and supported commands."""
from __future__ import annotations

from ..kernel import CapabilityDescriptor,ErrorCode,ExecutionResult,VerificationResult,VerificationStatus
from ..spatial.service import SpatialService
from .contracts import IntentResolution,Operation
from .domains import success,clarification
from ..rich_response.sources import digest as revision


def handler(controller,args,context):
    service=controller.runtime.spatial
    request=args.get('request','').strip().casefold()
    relative=(request.startswith(('add ','what about ','replace ','now replace ','in ','give it to me in ')) or
        request in {'how far','how far apart','what is the distance','show the path','show the great-circle path','chord distance','straight line distance',
            'driving distance','walking distance','cycling distance','route distance','as the crow flies',"what's the distance as the crow flies",'what is the distance as the crow flies'})
    metadata=context.metadata.get('nlui',{})
    selected=next((r for r in metadata.get('selected',()) if r.get('kind')=='spatial_context'),None)
    if relative and not args.get('choice') and metadata.get('route')!='spatial':
        if selected is None:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Choose the geographic places in this chat first, or open Spatial to use its visible markers.')
        if selected.get('revision')!=revision(service.snapshot()):
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'The Spatial workspace changed since this chat’s result. Choose the places again, or open Spatial to use its current visible markers.')
    if args.get('choice'):
        current=service.snapshot();pending=current['pending']
        if not pending or revision(pending)!=args.get('pending_revision'):
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'The location choices changed. Send the location request again.')
        slot=pending[0]['slot'];value=service.choose_candidate(slot,args['choice'])
        reply={'message':'Selected the actual geographic location.','context':value}
    else:
        reply=service.handle_text(args['request'],context=context)
        if reply is None:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'That Spatial operation has no implemented command binding.')
    value=reply['context']
    controller._port(context).execute('spatial.present',{'context':value},context)
    if value.get('pending'):
        pending=value['pending'];first=pending[0]
        result=clarification('Which geographic location should I use?',tuple({'id':r['identifier'],
            'label':r['label']+' · '+r.get('country','')+'/'+r.get('region','')} for r in first['candidates'][:20]),'choice')
        result.output['clarification']['arguments']={'pending_revision':revision(pending)}
        return result
    return success(reply['message'],spatial_context=value,provenance='CALCULATED',
        source_refs=[{'kind':'spatial_context','id':revision(value),'revision':revision(value)}])


def verify(controller,result,context):
    value=result.output['spatial_context']
    valid=controller.runtime.spatial.snapshot()==value
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Actual Spatial state independently reread; underlying geographic calculations use existing Kernel verifiers.',) if valid else ())


def register_spatial_domain(controller):
    controller.kernel.registry.register(CapabilityDescriptor('nlui.spatial.command','Use the current Spatial workspace',provider='morice-nlui-domain',
        category='spatial',input_schema={'type':'object','required':['request'],'properties':{
            'request':{'type':'string','maxLength':4000},'choice':{'type':'string','maxLength':200},
            'pending_revision':{'type':'string','maxLength':64}},'additionalProperties':False},
        supports_verification=True,supports_cancellation=True,idempotent=True,
        natural_language_intents=('Show Chennai','Add Tokyo','How far apart','In miles','Show the great-circle path','Now replace Tokyo with London'),
        ui_action='Existing SpatialService and interactive globe/map',verification_contract='Actual location IDs and deterministic calculations; stale ambiguity lists rejected.'),
        lambda args,ctx:handler(controller,args,ctx),verifier=lambda result,expected,ctx:verify(controller,result,ctx))


def resolve_spatial(text,context):
    if SpatialService.is_context_command(text):
        return IntentResolution(operations=(Operation('nlui.spatial.command',{'request':str(text)[:4000]}),),route='domain')
    return IntentResolution()
