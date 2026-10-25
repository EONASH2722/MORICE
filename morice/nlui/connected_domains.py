"""Connected-provider reads/writes keep scopes and exact original confirmations."""
from __future__ import annotations

from dataclasses import replace
import re

from ..kernel import CapabilityDescriptor,ErrorCode,ExecutionResult,TaskNode,VerificationPolicy,VerificationResult,VerificationStatus
from ..unified_intelligence import PermissionState
from .contracts import IntentResolution,Operation
from .domains import success,clarification
from .references import select_target


def connector_handler(controller,args,context):
    registry=controller.runtime.ambient.connectors
    rows=[{**r,'id':r['connector_id']} for r in registry.snapshot() if r['provider']=='github']
    selected=select_target(args.get('reference','current'),rows,kind='GitHub connector')
    if selected.record is None:return clarification(selected.question,selected.choices)
    cid=selected.record['id'];action=args['action'];capability='connector.'+cid+'.issue.'+action
    if action=='read':inputs={'number':args['number']}
    elif action=='list':inputs={'query':args.get('query',''),'state':args.get('state','open')}
    elif action=='create':inputs={'title':args['title'],'body':args.get('body','')}
    else:raise ValueError('Unsupported connector action.')
    entry=controller.kernel.registry.lookup(capability)
    if entry is None:return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,'The selected connector does not implement this operation.')
    authority=controller.kernel.permissions.controller
    if any(authority.state(group)!=PermissionState.GRANTED for group in entry.descriptor.required_permissions):
        return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Connect and authorize the required account/network scopes in Connectors before this action. Existing denials remain in force.')
    task=TaskNode(capability,inputs,verification_policy=VerificationPolicy(required=True))
    execution=context
    if action=='create':
        repository=selected.record.get('metadata',{}).get('repository',selected.record['name'])
        details='Create a remote GitHub issue in '+repository+'?\nTitle: '+inputs['title']+'\nBody:\n'+inputs['body']+'\nThis creates a new record with the repository’s visibility.'
        if not controller._port(context).execute('host.confirm',{'details':details},context)['confirmed']:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Issue creation was cancelled. No remote record was sent.')
        token=authority.issue_one_use(task.task_id,capability,inputs)
        execution=replace(context,approval_token=token)
    result=controller.kernel.run_task(task,execution)
    if not result.success:return result
    output=result.output
    message=(f'{len(output["issues"])} matching issue(s) in the latest repository page (up to 100 API records; not a full-repository search).'
        if action=='list' else 'Created and independently reread the GitHub issue.' if action=='create' else 'Read the selected GitHub issue.')
    return success(message,connector_id=cid,provider_result=output,evidence=result.to_dict(),provenance='CITED')


def verify_connector(controller,result,context):
    value=result.output;valid=(value['connector_id'] in controller.runtime.ambient.connectors.providers
        and value['evidence']['success'] and (value['evidence'].get('verification') or {}).get('status')=='verified')
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Existing authenticated provider verifier checked fresh object/page evidence.',) if valid else ())


def register_connected_domains(controller):
    controller.kernel.registry.register(CapabilityDescriptor('nlui.connector.issue','Use an authorized GitHub connector',provider='morice-nlui-domain',
        category='connector',input_schema={'type':'object','required':['action'],'properties':{
            'action':{'type':'string','enum':['list','read','create']},'reference':{'type':'string','maxLength':500},
            'number':{'type':'integer','minimum':1,'maximum':2147483647},'query':{'type':'string','maxLength':200},
            'state':{'type':'string','enum':['open','closed','all']},'title':{'type':'string','maxLength':256,'minLength':1},
            'body':{'type':'string','maxLength':4000}},'additionalProperties':False},
        supports_verification=True,supports_cancellation=True,preview_supported=True,
        natural_language_intents=('Show my GitHub issues','Read GitHub issue 12','Find recent GitHub issues about the UI','Create an issue with an explicit title and body'),
        ui_action='Existing ConnectorRegistry and provider scopes',verification_contract='Existing provider freshness and independent write readback; exact confirmation before external creation.'),
        lambda args,ctx:connector_handler(controller,args,ctx),verifier=lambda result,expected,ctx:verify_connector(controller,result,ctx))


def resolve_connected(clean,context):
    if clean in {'show my github issues','list github issues','show github issues'}:
        return IntentResolution(operations=(Operation('nlui.connector.issue',{'action':'list'}),),route='domain')
    match=re.fullmatch(r'(?:read|show|open) (?:github )?issue #?(\d+)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.connector.issue',{'action':'read','number':int(match[1])}),),route='domain')
    match=re.fullmatch(r'find (?:the )?(?:most recent |recent )?(?:github )?issues? about (.+)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.connector.issue',{'action':'list','query':match[1]}),),route='domain')
    return IntentResolution()
