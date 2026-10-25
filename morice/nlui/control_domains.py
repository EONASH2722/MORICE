"""Bounded project checks and explicit automation requests over existing owners."""
from __future__ import annotations

from dataclasses import asdict,replace
from pathlib import Path
import re
import html

from ..kernel import CapabilityDescriptor,ErrorCode,ExecutionResult,VerificationResult,VerificationStatus
from .contracts import IntentResolution,Operation
from .domains import schema,success,clarification
from .references import select_target


def project_handler(controller,args,context):
    root=context.metadata.get('nlui',{}).get('project_id') or context.project_id
    if not root or not Path(root).is_dir():return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Choose the project folder in Projects first, then send this request again.')
    context=replace(context,project_id=root)
    if args['action']=='test':
        from ..project_build.discovery import commands_for
        from ..unified_intelligence import PermissionState
        from ..redaction import redact_text
        if controller.kernel.permissions.controller.state('process.execute') in {PermissionState.DENIED,PermissionState.UNSUPPORTED,PermissionState.OS_REQUIRED}:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Process-execution policy does not allow running project tests.')
        _,commands,_,_=commands_for(root,'Run the existing project tests')
        command=commands.get('test',[])
        if not command:return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,'No test command was discovered for this project. Configure its test suite in Projects first.')
        details='Run this discovered project test command?\nFolder: '+root+'\nArguments: '+repr(command)
        if not controller._port(context).execute('host.confirm',{'details':details},context)['confirmed']:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Project tests were not authorized. No command was run.')
        inputs={'cwd':root,'command':command,'timeout':120}
        token=controller.runtime.agent.permission_token('terminal.run',inputs)
        result=controller.kernel.dispatch('terminal.run',inputs,replace(context,approval_token=token))
        output=result.output or {};excerpt=redact_text(str(output.get('stdout',''))+'\n'+str(output.get('stderr','')))[-1600:]
        context.metadata['nlui'].setdefault('project_test_receipts',{})[context.task_id]={
            'root':root,'evidence':result.to_dict(),'excerpt':excerpt}
        if not result.success:
            result.errors=[replace(error,message=error.message+('\n'+excerpt if excerpt.strip() else '')) for error in result.errors]
            return result
        return success('Project test command completed with exit code 0.\n'+excerpt,root=root,action='test',evidence=result.to_dict(),provenance='SYSTEM_STATE')
    capability={'verify':'project.verify','index':'project.index','diff':'git.diff','status':'git.status'}[args['action']]
    # The selected project folder is host context, never a path invented by a model.
    result=controller.kernel.dispatch(capability,{'root':root},context)
    if not result.success:return result
    return success('Project '+args['action']+' read from the selected folder.',root=root,action=args['action'],
        evidence=result.to_dict(),provenance='SYSTEM_STATE')


def open_project(controller,args,context):
    rows=controller._port(context).execute('project.catalog',{},context)['projects']
    selected=select_target(args.get('reference','current'),rows,active_id=context.metadata.get('nlui',{}).get('project_id') or context.project_id,kind='project folder')
    if selected.record is None:return clarification(selected.question,selected.choices)
    root=selected.record['id']
    controller._port(context).execute('project.select',{'root':root},context)
    context.metadata['nlui']['project_id']=root
    return success('Opened saved project folder: '+selected.record['title']+'.',root=root,provenance='SYSTEM_STATE')


def verify_open_project(controller,result,context):
    valid=controller._port(context).verify('project.select',{'root':result.output['root']},result.output,context)
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Actual selected project folder, native field and workspace route independently reread.',) if valid else ())


def verify_project(controller,result,context):
    value=result.output
    root=context.metadata.get('nlui',{}).get('project_id') or context.project_id
    valid=(str(Path(root).resolve())==str(Path(value['root']).resolve())
        and value['evidence']['success'] and (value['evidence'].get('verification') or {}).get('status')=='verified')
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Existing project tool completed its own independent verification in the selected folder.',) if valid else ())


def propose_project(controller,args,context):
    from ..project_build.contracts import BuildLimits
    from ..unified_intelligence import PermissionState
    root=context.metadata.get('nlui',{}).get('project_id') or context.project_id
    if not root or not Path(root).is_dir():return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Choose an existing project folder in Projects first, then resend.')
    evidence=''
    preceding=context.metadata.get('nlui',{}).get('repair_after_test',{}).get(context.task_id)
    if preceding:
        receipt=context.metadata['nlui'].get('project_test_receipts',{}).get(preceding,{})
        recorded=receipt.get('evidence',{});output=recorded.get('output') or {}
        if receipt.get('root')!=root or type(output.get('exitCode')) is not int or output.get('timedOut') or output.get('cancelled') or any(
                error['code'] in {'permission_denied','cancelled','capability_unavailable','timeout'} for error in recorded.get('errors',[])):
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'The preceding test command did not produce an authorized completed run. No repair or alternate action was started.')
        if recorded.get('success'):
            return success('The selected project tests passed. No failing-test repair was needed.',provenance='SYSTEM_STATE')
        evidence=receipt['excerpt']
    if controller.kernel.permissions.controller.state('file_read')!=PermissionState.GRANTED:
        return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Project source reading is not authorized. Existing denials remain in force.')
    selected=controller._port(context).execute('project.prepare_proposal',{'root':root,'request':args['request']},context)
    if not selected.get('ready'):return ExecutionResult.failure(ErrorCode.INVALID_INPUT,selected.get('reason','The project is not ready for a new proposal.'))
    builder=controller.runtime.autonomous_builder.project_runtime
    session=builder.generate(root,args['request'],replace(context,project_id=root,metadata={**context.metadata,
        'model_config':{'selected_model':selected['model_id'],'allow_fallback':False,'max_output_tokens':1024}}),limits=BuildLimits(max_model_calls=3,max_repairs=2,max_wall_seconds=180),failure_evidence=evidence)
    if not session.changes:
        reasons='; '.join(row['evidence'] for row in session.issues)
        return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,'No applicable source patch was prepared. '+reasons[:1800])
    preview=controller.kernel.dispatch('filesystem.preview_patch',{'root':root,'changes':session.changes},replace(context,project_id=root))
    if not preview.success:return preview
    files={row['path']:row for row in preview.output['files']}
    for change in session.changes:
        observed=files[change['path']]
        if observed['exists']!=change['expected_exists'] or change['expected_exists'] and observed['beforeSha256']!=change['expected_sha256']:
            return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'Project source changed while preparing the patch. Generate a fresh proposal before applying changes.')
    diff='<pre>'+html.escape('\n'.join(row['diff'] for row in files.values()))+'</pre>'
    outcome=controller._port(context).execute('project.review',{'session_id':session.session_id,'root':root,'diff_html':diff},context)
    return success(('Prepared the source patch and started the existing apply/build workflow.' if outcome['auto_apply_started'] else
        'Prepared '+str(len(session.changes))+' file change(s) for review in Projects. Apply the patch there to write it and run its checks.'),
        build_session_id=session.session_id,review=outcome,provenance='GENERATED_CODE')


def verify_proposal(controller,result,context):
    if not result.output.get('build_session_id'):
        preceding=context.metadata.get('nlui',{}).get('repair_after_test',{}).get(context.task_id)
        receipt=context.metadata.get('nlui',{}).get('project_test_receipts',{}).get(preceding,{})
        return VerificationResult(VerificationStatus.VERIFIED if receipt.get('evidence',{}).get('success') else VerificationStatus.FAILED,
            ('Actual preceding successful test receipt independently checked; no repair performed.',))
    session=controller.runtime.autonomous_builder.project_runtime.load(result.output['build_session_id'])
    valid=bool(session.changes) and controller._port(context).verify('project.review',{},result.output['review'],context)
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Actual normalized source proposal and its existing native review/apply state independently reread; no build completion is claimed.',) if valid else ())


def project_result(controller,args,context):
    observed=controller._port(context).execute('project.build_catalog',{},context)
    chosen=select_target(args.get('reference','latest'),observed['builds'],active_id=observed['active_id'],kind='known build for this project')
    if chosen.record is None:return clarification(chosen.question,chosen.choices)
    session=controller.runtime.autonomous_builder.project_runtime.load(chosen.record['id'])
    selected=controller._port(context).execute('project.show_build',{'session_id':session.session_id},context)
    receipts=[row for row in session.command_evidence if row['stage']=='test']
    if args.get('failures_only'):receipts=[row for row in receipts if row['status']!='passed']
    from ..redaction import redact_text
    detail='\n'.join(row['stage']+': '+row['status']+' (exit '+str(row.get('exit_code'))+')\n'+redact_text(row.get('stdout','')+'\n'+row.get('stderr',''))[-1600:] for row in receipts[-3:])
    return success('Saved build state: '+session.status+'. These are recorded results for the selected project.\n'+
        (detail or 'No matching test receipt was recorded for this build.'),build_session_id=session.session_id,selection=selected,provenance='SYSTEM_STATE')


def verify_project_result(controller,result,context):
    valid=controller._port(context).verify('project.show_build',{},result.output['selection'],context)
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Actual saved build checkpoint and selected project identity independently reread.',) if valid else ())


def plugin_control(controller,args,context):
    manager=controller.runtime.plugins
    chosen=select_target(args.get('reference','current'),manager.diagnostics()['plugins'],kind='installed plugin')
    if chosen.record is None:return clarification(chosen.question,chosen.choices)
    record=manager.require(chosen.record['id']);action=args['action']
    if action in {'start','resume'} and not manager.permissions.is_reviewed(record.manifest):
        return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'Review this plugin\'s declared permissions in Plugins first. Natural-language requests cannot grant them.')
    if not controller._port(context).execute('host.confirm',{'details':action.title()+' this installed plugin?\n'+record.manifest.name+'\nID: '+record.manifest.plugin_id+'\nExisting reviewed plugin permissions remain in force.'},context)['confirmed']:
        return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'The plugin action was not authorized.')
    getattr(manager,action)(record.manifest.plugin_id)
    value=manager.diagnostics(record.manifest.plugin_id)
    return success('Installed plugin '+action+' request completed: '+value['state']+'.',plugin=value,provenance='SYSTEM_STATE')


def verify_plugin(controller,result,context):
    actual=controller.runtime.plugins.diagnostics(result.output['plugin']['id'])
    valid=actual['state']==result.output['plugin']['state']
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Existing plugin owner independently reread its actual lifecycle state.',) if valid else ())


def automation_handler(controller,args,context):
    service=controller.runtime.ambient;action=args['action']
    if action=='create':
        trigger=service.from_request(args['request'],project_id=context.research_project_id or context.project_id)
        details=('Create this notification watch?\n'+trigger.name+'\nEvent: '+trigger.event_type+
            '\nProject scope: '+(trigger.project_id or 'all permitted events')+'\nOnly authenticated, permitted events can trigger it.')
        if not controller._port(context).execute('host.confirm',{'details':details},context)['confirmed']:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'The notification watch was not authorized.')
        value=service.create(replace(trigger,enabled=True),user_confirmed=True)
        return success('Notification watch created. Ambient monitoring '+('is running.' if service.enabled else 'is off; enable it in Automations to receive matching events.'),
            watch=asdict(value),requested_action=action,provenance='SYSTEM_STATE')
    rows=[{**r,'id':r['trigger_id'],'created':r.get('created_at')} for r in service.snapshot()['watches']]
    chosen=select_target(args.get('reference','current'),rows,kind='automation')
    if chosen.record is None:return clarification(chosen.question,chosen.choices)
    row=chosen.record
    if action=='delete':
        if not controller._port(context).execute('host.confirm',{'details':'Delete this saved notification watch?\n'+row['name']+'\nID: '+row['id']},context)['confirmed']:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'The notification watch deletion was not authorized.')
        service.delete(row['id'])
        return success('Deleted the selected notification watch.',deleted_watch_id=row['id'],provenance='SYSTEM_STATE')
    if action=='pause':value=service.update(row['id'],paused=True)
    elif action=='resume':
        if not controller._port(context).execute('host.confirm',{'details':'Resume this automation?\n'+row['name']+'\nAction: '+row['action']},context)['confirmed']:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'The automation resume was not authorized.')
        value=service.update(row['id'],paused=False,enabled=True,user_confirmed=True)
    else:raise ValueError('Unsupported automation control.')
    return success('Automation '+('paused.' if action=='pause' else 'resumed.'),watch=asdict(value),requested_action=action,provenance='SYSTEM_STATE')


def verify_automation(controller,result,context):
    if result.output.get('deleted_watch_id'):
        valid=not any(row['trigger_id']==result.output['deleted_watch_id'] for row in controller.runtime.ambient.snapshot()['watches'])
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
            ('Selected watch identity independently confirmed absent from its existing store.',) if valid else ())
    expected=result.output['watch'];rows=controller.runtime.ambient.snapshot()['watches']
    valid=any(row['trigger_id']==expected['trigger_id'] and row['paused']==expected['paused'] and row['enabled']==expected['enabled'] for row in rows)
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Actual saved automation state independently reread.',) if valid else ())


def register_control_domains(controller):
    registrations=(
        ('nlui.plugin.control','Control an installed and reviewed plugin',{'type':'object','required':['action'],'properties':{
            'action':{'type':'string','enum':['start','pause','resume','disable']},'reference':{'type':'string','maxLength':500}},'additionalProperties':False},
            ('Pause the installed example plugin','Resume my plugin','Disable this plugin'),plugin_control,verify_plugin),
        ('nlui.project.result','Show saved build results and recorded tests',{'type':'object','properties':{
            'reference':{'type':'string','maxLength':500},'failures_only':{'type':'boolean'}},'additionalProperties':False},
            ('Open the latest build','Show project test results','Show failing tests'),project_result,verify_project_result),
        ('nlui.project.propose','Prepare a project change using the existing Builder',schema('request',required=('request',)),
            ('Fix this project','Fix the failing tests in this project','Build a simple Python addition calculator in this project'),propose_project,verify_proposal),
        ('nlui.project.open','Open a saved project folder',schema('reference'),
            ('Open my latest project','Open the previous project','Open my dashboard project'),open_project,verify_open_project),
        ('nlui.project.check','Inspect or test the selected project',{'type':'object','required':['action'],'properties':{'action':{'type':'string','enum':['verify','index','diff','status','test']}},'additionalProperties':False},
            ('Check this project','Show project changes','Show Git status','Run the project tests'),project_handler,verify_project),
        ('nlui.automation.control','Control a notification watch',{'type':'object','required':['action'],'properties':{
            'action':{'type':'string','enum':['create','pause','resume','delete']},'request':{'type':'string','maxLength':4000},'reference':{'type':'string','maxLength':500}},'additionalProperties':False},
            ('Notify me when research completes','Notify me when battery is below 20%','Pause this automation','Resume the build notification','Delete my latest automation'),automation_handler,verify_automation))
    for identifier,title,input_schema,intents,handler,verifier in registrations:
        controller.kernel.registry.register(CapabilityDescriptor(identifier,title,provider='morice-nlui-domain',category=identifier.split('.')[1],
            input_schema=input_schema,supports_verification=True,supports_cancellation=True,natural_language_intents=intents,
            timeout=150 if identifier=='nlui.project.propose' else 150 if identifier=='nlui.project.check' else 45,
            ui_action='Existing project tool or Ambient watch owner',verification_contract='Existing tool verification or independently reread saved watch state.',
            preview_supported=identifier in {'nlui.automation.control','nlui.project.propose'}),
            lambda args,ctx,h=handler:h(controller,args,ctx),verifier=lambda result,expected,ctx,v=verifier:v(controller,result,ctx))


def resolve_control(clean,context,raw=None):
    match=re.fullmatch(r'(start|pause|resume|disable) (?:my |the )?(.+?) plugin',clean)
    if match:return IntentResolution(operations=(Operation('nlui.plugin.control',{'action':match[1],'reference':match[2]}),),route='domain')
    if clean in {'show failing tests','show the failing tests','show project test results','show test results'}:
        return IntentResolution(operations=(Operation('nlui.project.result',{'reference':'latest','failures_only':'failing' in clean}),),route='domain')
    match=re.fullmatch(r'(?:open|show) (?:my |the )?(latest|previous|current) build',clean)
    if match:return IntentResolution(operations=(Operation('nlui.project.result',{'reference':match[1]}),),route='domain')
    if (re.match(r'^(?:fix|repair|build|implement|add|update)\b',clean) and re.search(r'\b(?:this|the|selected) project\b',clean)) or clean in {'fix the failures','fix failing tests'}:
        return IntentResolution(operations=(Operation('nlui.project.propose',{'request':raw or clean}),),route='domain')
    match=re.fullmatch(r'(?:open|show|resume) (?:my |the )?(?:(.*?) )?(?:project|project folder)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.project.open',{'reference':match[1] or 'current'}),),route='domain')
    project={'check this project':'verify','verify this project':'verify','inspect this project':'index',
        'show project changes':'diff','show git status':'status','check project sources':'verify','run the project tests':'test',
        'run project tests':'test','run the tests for this project':'test','test this project':'test','rerun the project tests':'test','run tests again':'test','run its tests':'test'}
    if clean in project:return IntentResolution(operations=(Operation('nlui.project.check',{'action':project[clean]}),),route='domain')
    if re.match(r'^notify me when\b',clean) and re.search(r'\b(build|research|experiment|battery|issue)\b',clean):
        return IntentResolution(operations=(Operation('nlui.automation.control',{'action':'create','request':raw or clean}),),route='domain')
    match=re.fullmatch(r'(pause|resume|delete) (?:the |my )?(?:(.*?) )?(?:automation|notification watch)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.automation.control',{'action':match[1],'reference':match[2] or 'current'}),),route='domain')
    return IntentResolution()
