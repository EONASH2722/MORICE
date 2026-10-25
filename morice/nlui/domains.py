"""Typed goal bindings to existing domain services, with fresh-state verifiers."""
from __future__ import annotations

import re

from ..kernel import (CapabilityDescriptor,ErrorCode,ExecutionError,ExecutionResult,
    TaskStatus,VerificationResult,VerificationStatus)
from .contracts import IntentResolution,Operation
from .references import label,select_target,timestamp


REFERENCE_SCHEMA={'type':'string','maxLength':500}


def schema(*names,required=()):
    return {'type':'object','properties':{name:({'type':'string','maxLength':4000} if name=='request' else REFERENCE_SCHEMA) for name in names},'required':list(required),'additionalProperties':False}


RESEARCH_CONTRACTS={
    'nlui.research.prepare':('Prepare a bounded computational experiment',schema('request','project_reference',required=('request',)),
        ('Prepare an oscillator experiment with supplied physical inputs','Create a mixture density parameter sweep'),False),
    'nlui.research.open':('Open a research notebook',schema('reference'),('Open my latest research project','Open my energy research'),True),
    'nlui.research.list':('List research notebooks',schema(),('Show my research projects','List my research notebooks'),True),
    'nlui.research.experiments':('Show saved experiments',schema('project_reference'),('Show my experiments','List experiments in this project'),True),
    'nlui.research.result':('Show saved experiment results',schema('reference','project_reference'),('Show my latest parameter sweep','Show the previous simulation'),True),
    'nlui.research.compare':('Compare saved experiment results',schema('first','second','project_reference'),('Compare the latest two experiments','Compare the last two simulations'),True),
    'nlui.research.record':('Show an actual saved research calculation or artifact',
        {'type':'object','properties':{'reference':REFERENCE_SCHEMA,'project_reference':REFERENCE_SCHEMA,
            'record_type':{'type':'string','enum':['result','calculation','cad','files']}},'additionalProperties':False},
        ('Show my latest CAD model','Show the latest saved calculation','Show my latest research files'),True),
    **{f'nlui.research.{verb}':(f'{verb.title()} a saved experiment',schema('reference','project_reference'),
        (f'{verb.title()} the selected experiment',),False) for verb in ('run','pause','cancel')},
}


def clarification(question,choices=(),slot='reference'):
    if not choices:
        return ExecutionResult.failure(ErrorCode.INVALID_INPUT,question)
    return ExecutionResult(TaskStatus.BLOCKED,False,
        output={'clarification':{'question':question,'choices':list(choices),'slot':slot}},
        errors=[ExecutionError(ErrorCode.INVALID_INPUT,question)])


def success(message,**values):
    return ExecutionResult(TaskStatus.SUCCEEDED,True,{'message':message,**values},verification_required=True)


def project_for(runtime,args,context):
    active=context.metadata.get('nlui',{}).get('research_project_id') or context.research_project_id
    return select_target(args.get('project_reference','current'),runtime.research.store.list_projects(),active_id=active,kind='research notebook')


def research_handler(controller,identifier,args,context):
    runtime=controller.runtime;research=runtime.research
    if identifier=='nlui.research.list':
        projects=research.store.list_projects()
        return success(f'{len(projects)} saved research notebook(s).' if projects else 'No saved research notebooks are available.',
            projects=projects,provenance='USER_DATA')
    if identifier=='nlui.research.open':
        active=context.metadata.get('nlui',{}).get('research_project_id') or context.research_project_id
        selected=select_target(args.get('reference','current'),research.store.list_projects(),active_id=active,kind='research notebook')
        if selected.record is None:return clarification(selected.question,selected.choices)
        project=research.store.snapshot(selected.record['id'])
        controller._port(context).execute('research.select',{'project_id':project['id'],'objective':project['objective']},context)
        context.metadata['nlui']['research_project_id']=project['id']
        return success(f'Opened research notebook: {project["objective"]}.',project_id=project['id'],updated=project['updated'],
            source_refs=[{'kind':'research_project','id':project['id'],'revision':project['updated']}])
    selected=project_for(runtime,args,context)
    if selected.record is None:return clarification(selected.question,selected.choices,'project_reference')
    project_id=selected.record['id'];laboratory=research.laboratory
    if identifier=='nlui.research.record':
        rows=research.store.snapshot(project_id)['records'];kind=args.get('record_type','result')
        def eligible(row):
            payload=row.get('payload',{});value=payload.get('result',{})
            if kind=='calculation':return payload.get('method')=='research.calculate'
            if kind=='cad':return isinstance(value,dict) and bool(value.get('stl') or value.get('parts'))
            if kind=='files':return isinstance(value,dict) and bool(value.get('stl') or value.get('bom') or value.get('checksums'))
            return row.get('kind')=='result'
        rows=[r for r in rows if eligible(r)]
        active=next((r.get('id','').partition(':')[2] for r in context.metadata.get('nlui',{}).get('selected',()) if r.get('kind')=='research_record'),'')
        chosen=select_target(args.get('reference','latest'),rows,active_id=active,kind='saved '+kind)
        if chosen.record is None:return clarification(chosen.question,chosen.choices)
        row=chosen.record
        if row['stale']:return ExecutionResult.failure(ErrorCode.INVALID_INPUT,'That saved result is stale. Recompute it in Research before using its files or calculator.')
        return success('Loaded saved result: '+row['title']+'.',record=row,project_id=project_id,
            source_refs=[{'kind':'research_record','id':project_id+':'+row['id'],'revision':str(row['revision'])}],provenance=row['provenance'])
    if identifier=='nlui.research.prepare':
        selected_id=next((r.get('id') for r in context.metadata.get('nlui',{}).get('selected',()) if r.get('kind')=='experiment'),None)
        prior=laboratory.get(selected_id)['spec'] if selected_id and any(r['id']==selected_id for r in laboratory.list(project_id)) else None
        row=laboratory.prepare(args['request'],project_id=project_id,chat_id=context.conversation_id,context=prior)
        context.metadata['nlui']['selected']=[{'kind':'experiment','id':row['id']}]
        return success(f'Prepared {row["title"]}: {row["estimate"]["planned_runs"]} computational runs. It has not started.',
            experiment_id=row['id'],project_id=project_id,status=row['status'],prepared=True,provenance='SIMULATED',
            source_refs=[{'kind':'experiment','id':row['id'],'revision':row['updated']}])
    rows=laboratory.list(project_id)
    if identifier=='nlui.research.experiments':
        return success(f'{len(rows)} saved experiment(s) in {label(selected.record)}.' if rows else 'This notebook has no saved experiments yet.',
            project_id=project_id,experiments=rows,provenance='SIMULATED')
    if identifier=='nlui.research.compare':
        if len(rows)<2:return clarification('This notebook needs two saved experiments before they can be compared.',(), 'first')
        if args.get('first') or args.get('second'):
            first=select_target(args.get('first',''),rows,kind='experiment')
            if first.record is None:return clarification(first.question,first.choices,'first')
            second=select_target(args.get('second',''),[r for r in rows if r['id']!=first.record['id']],kind='experiment')
            if second.record is None:return clarification(second.question,second.choices,'second')
            pair=[first.record,second.record]
        else:
            if any(timestamp(r) is None for r in rows):return clarification('Which first experiment should I compare?',tuple({'id':r['id'],'label':label(r)} for r in rows),'first')
            ordered=sorted(rows,key=lambda r:(timestamp(r),r['id']),reverse=True)
            if len(ordered)>2 and timestamp(ordered[1])==timestamp(ordered[2]):
                return clarification('Several experiments share the latest timestamps. Choose the first one to compare.',tuple({'id':r['id'],'label':label(r)} for r in rows),'first')
            pair=list(reversed(ordered[:2]))
        if pair[0]['id']==pair[1]['id']:return clarification('Choose a different second experiment.',tuple({'id':r['id'],'label':label(r)} for r in rows if r['id']!=pair[0]['id']),'second')
        compared=laboratory.compare(pair[0]['id'],pair[1]['id'])
        return success(f'Compared {label(pair[0])} and {label(pair[1])}. These are computational runs, not hardware measurements.',
            comparison=compared,project_id=project_id,
            source_refs=[{'kind':'experiment','id':r['id'],'revision':r['updated']} for r in pair],provenance='SIMULATED')
    active=next((r.get('id','') for r in context.metadata.get('nlui',{}).get('selected',()) if r.get('kind')=='experiment'),'')
    chosen=select_target(args.get('reference','current'),rows,active_id=active,kind='experiment')
    if chosen.record is None:return clarification(chosen.question,chosen.choices)
    row=chosen.record;identifier_value=row['id']
    if identifier=='nlui.research.result':
        result=laboratory.get(identifier_value,True,run_limit=1000)
        return success(f'{result["title"]}: {result["status"].replace("_"," ").lower()}; {result["completed_runs"]} saved computational runs.',
            experiment=result,project_id=project_id,provenance='SIMULATED',
            source_refs=[{'kind':'experiment','id':identifier_value,'revision':result['updated']}])
    verb=identifier.rsplit('.',1)[1]
    if verb=='run':
        started=laboratory.start(identifier_value)
        message='Experiment started; results are still running.' if started else 'The experiment is already queued or running.'
    elif verb=='pause':laboratory.pause(identifier_value);message='Pause requested; completed runs are retained.'
    elif verb=='cancel':laboratory.cancel(identifier_value);message='Cancellation requested; completed runs are retained.'
    else:raise ValueError('Unsupported research operation.')
    current=laboratory.get(identifier_value)
    return success(message,experiment_id=identifier_value,project_id=project_id,status=current['status'],requested_action=verb,
        source_refs=[{'kind':'experiment','id':identifier_value,'revision':current['updated']}])


def verify_research(controller,identifier,result,context):
    value=result.output;runtime=controller.runtime
    if identifier=='nlui.research.list':valid=value['projects']==runtime.research.store.list_projects()
    elif identifier=='nlui.research.open':
        project=runtime.research.store.snapshot(value['project_id'])
        valid=(project['updated']==value['updated'] and controller._port(context).verify('research.select',
            {'project_id':value['project_id']},value,context))
    elif identifier=='nlui.research.experiments':
        valid=value['experiments']==runtime.research.laboratory.list(value['project_id'])
    elif identifier=='nlui.research.record':
        row=next((r for r in runtime.research.store.snapshot(value['project_id'])['records'] if r['id']==value['record']['id']),None)
        valid=row==value['record'] and not row['stale']
    elif identifier=='nlui.research.prepare':
        fresh=runtime.research.laboratory.get(value['experiment_id'])
        valid=fresh['project_id']==value['project_id'] and fresh['status']=='PREPARED'
    elif identifier=='nlui.research.result':
        fresh=runtime.research.laboratory.get(value['experiment']['id'],True,run_limit=1000)
        valid=fresh==value['experiment']
    elif identifier=='nlui.research.compare':
        compared=value['comparison'];valid=runtime.research.laboratory.compare(compared['first'],compared['second'])==compared
    else:
        current=runtime.research.laboratory.get(value['experiment_id'])
        action=value['requested_action'];control=runtime.research.laboratory.controls.get(value['experiment_id'])
        valid=(current['status'] in {'QUEUED','RUNNING','COMPLETED','COMPLETED_WITH_WARNINGS'} if action=='run'
            else current['status'] in {'PAUSED','COMPLETED','COMPLETED_WITH_WARNINGS','FAILED'} or bool(control and control['pause'].is_set()) if action=='pause'
            else current['status'] in {'CANCELLED','COMPLETED','COMPLETED_WITH_WARNINGS','FAILED'} or bool(control and control['cancel'].is_set()))
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Actual saved research state reread; scientific assumptions remain unverified.',) if valid else (),
        '' if valid else 'Research state changed or the requested state was not observed.')


def register_domains(controller):
    for identifier,(title,input_schema,intents,idempotent) in RESEARCH_CONTRACTS.items():
        if controller.kernel.registry.lookup(identifier):continue
        controller.kernel.registry.register(CapabilityDescriptor(identifier,title,description=title,
            provider='morice-nlui-domain',category='research',input_schema=input_schema,
            supports_verification=True,supports_cancellation=True,idempotent=idempotent,
            natural_language_intents=intents,ui_action='Existing Research workspace and laboratory',
            verification_contract='Reread actual project, experiment, queued control or comparison state.'),
            lambda args,ctx,cid=identifier:research_handler(controller,cid,args,ctx),
            verifier=lambda result,expected,ctx,cid=identifier:verify_research(controller,cid,result,ctx))


def resolve_domain(clean,context,raw=None):
    match=re.fullmatch(r'(?:show|open|view) (?:my |the )?(?:(latest|last|previous|selected|current) )?(?:saved )?(cad model|assembly|mesh|calculation|research files|research result)',clean)
    if match:
        kind={'cad model':'cad','assembly':'cad','mesh':'cad','calculation':'calculation','research files':'files','research result':'result'}[match[2]]
        return IntentResolution(operations=(Operation('nlui.research.record',{'reference':match[1] or 'latest','record_type':kind}),),route='domain')
    match=re.fullmatch(r'(run|start|pause|cancel|stop|show|resume) (?:it|that|this)(?: again)?',clean)
    if match and any(r.get('kind')=='experiment' for r in context.selected):
        verb={'start':'run','resume':'run','show':'result','stop':'cancel'}.get(match[1],match[1])
        return IntentResolution(operations=(Operation('nlui.research.'+verb,{'reference':'selected'}),),route='domain')
    if (re.match(r'^(?:test|run) (?:this|it) from\b',clean) or re.match(r'^(?:increase|decrease) \w+ by [\d.]+\s*%',clean)) and any(r.get('kind')=='experiment' for r in context.selected):
        operations=[Operation('nlui.research.prepare',{'request':raw or clean})]
        if re.search(r'\b(?:rerun|run it|run again)\b',clean):operations.append(Operation('nlui.research.run',{'reference':'selected'}))
        return IntentResolution(operations=tuple(operations),route='domain')
    if re.match(r'^(?:prepare|create) (?:an? |my |the )?.*(?:experiment|parameter sweep|simulation)\b',clean):
        return IntentResolution(operations=(Operation('nlui.research.prepare',{'request':raw or clean}),),route='domain')
    if clean in {'show my research projects','list research projects','list my research notebooks','show my research notebooks'}:
        return IntentResolution(operations=(Operation('nlui.research.list'),),route='domain')
    match=re.fullmatch(r'(?:open|show|resume) (?:my |the )?(?:(.*?) )?(?:research project|research notebook|notebook)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.research.open',{'reference':match[1] or 'current'}),),route='domain')
    match=re.fullmatch(r'(?:open|show) my (.+) research',clean)
    if match:return IntentResolution(operations=(Operation('nlui.research.open',{'reference':match[1]}),),route='domain')
    if clean in {'show my experiments','list experiments','list experiments in this project','show the experiments'}:
        return IntentResolution(operations=(Operation('nlui.research.experiments'),),route='domain')
    if re.fullmatch(r'compare (?:the )?(?:latest|last|most recent) two (?:experiments|simulations|runs)',clean):
        return IntentResolution(operations=(Operation('nlui.research.compare'),),route='domain')
    match=re.fullmatch(r'(show|open|run|start|resume|pause|cancel|stop) (?:my |the )?(?:(.*?) )?(?:experiment|simulation|parameter sweep)(?: results)?',clean)
    if match:
        verb={'show':'result','open':'result','run':'run','start':'run','resume':'run','stop':'cancel'}.get(match[1],match[1])
        return IntentResolution(operations=(Operation('nlui.research.'+verb,{'reference':match[2] or 'current'}),),route='domain')
    return IntentResolution()
