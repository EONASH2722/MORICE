"""Typed display controls over the existing rich response and domain owners."""
from __future__ import annotations

from dataclasses import asdict,replace
import re

from ..kernel import CapabilityDescriptor,VerificationResult,VerificationStatus
from ..rich_response import Component
from ..rich_response.sources import ResponseSources
from .contracts import IntentResolution,Operation
from .domains import success,clarification


ACTIONS=('show_table','hide_table','filter','sort','style','parameter','strategy','explode','hide_part','show_part','wireframe','export_chart','export_data','export_report')
KINDS={'show_table':('chart','table'),'hide_table':('chart',),'filter':('table','chart'),'sort':('table','chart'),
    'style':('chart',),'parameter':('calculator',),'strategy':('calculator',),'explode':('assembly',),
    'hide_part':('assembly',),'show_part':('assembly',),'wireframe':('mesh','assembly'),'export_chart':('chart',),'export_data':('chart','table')}


def handler(controller,args,context):
    port=controller._port(context)
    if args['action']=='export_report':
        from ..unified_intelligence import PermissionState
        from ..kernel import ErrorCode,ExecutionResult
        if controller.kernel.permissions.controller.state('file_write') not in {PermissionState.ASK,PermissionState.GRANTED}:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'File-write policy does not allow exporting this report.')
        info=port.execute('response.report_info',{},context);snapshots=[];seen=set()
        with info['owner'].using_cancellation(context.cancellation_token):
            for value in info['plan']['components']:
                component=Component.from_dict(value);source=component.source
                if source and (source.kind,source.id) not in seen:
                    snapshots.append(info['owner'].resolve(source));seen.add((source.kind,source.id))
        destination=port.execute('file.destination',{'name':'MORICE-response-report.pdf'},context).get('destination','')
        if not destination:return ExecutionResult.failure(ErrorCode.CANCELLED,'Report export cancelled.')
        from pathlib import Path
        if Path(destination).suffix.casefold()!='.pdf':raise ValueError('Choose a filename ending in .pdf.')
        rendered=port.execute('response.report_capture',{'plan':info['plan'],'snapshots':snapshots},context)
        try:result=controller.kernel.dispatch('response.render.export',{'destination':destination},replace(context,
            active_files=(*context.active_files,destination),metadata={**context.metadata,'response_render':rendered}))
        finally:rendered.cleanup()
        if not result.success:return result
        return success('Exported the response report as selectable PDF text and actual bounded data; readable pages and the destination hash were verified.',response_export=result.output,provenance='SYSTEM_STATE')
    target=port.execute('response.inspect',{'kinds':KINDS[args['action']],'reference':args.get('reference','')},context)
    if target.get('choices'):return clarification('Which displayed component should I change?',target['choices'],'reference')
    component=Component.from_dict(target['component']);config=dict(component.config);action=args['action']
    value=args.get('text','');source=component.source
    if action in {'export_chart','export_data'}:
        from pathlib import Path
        from ..unified_intelligence import PermissionState
        from ..kernel import ErrorCode,ExecutionResult
        if controller.kernel.permissions.controller.state('file_write') not in {PermissionState.ASK,PermissionState.GRANTED}:
            return ExecutionResult.failure(ErrorCode.PERMISSION_DENIED,'File-write policy does not allow exporting this chart.')
        format=args.get('format','png' if action=='export_chart' else 'csv')
        if format not in ({'png','svg','pdf'} if action=='export_chart' else {'csv','json'}):raise ValueError('Choose a supported export format for this response.')
        destination=port.execute('file.destination',{'name':('MORICE-chart.' if action=='export_chart' else 'MORICE-source-sample.')+format},context).get('destination','')
        if not destination:return ExecutionResult.failure(ErrorCode.CANCELLED,'Chart export cancelled.')
        if Path(destination).suffix.casefold()!='.'+format:raise ValueError('Choose a filename ending in .'+format+' for this chart format.')
        if action=='export_chart':rendered=port.execute('response.capture',{**target,'format':format},context)
        else:
            from ..rich_response.exports import capture_data
            owner=port.execute('response.source_owner',{'plan_id':target['plan_id']},context)
            with owner.using_cancellation(context.cancellation_token):rendered=capture_data(owner,owner.resolve(source),format)
        try:
            result=controller.kernel.dispatch('response.render.export',{'destination':destination},replace(context,
                active_files=(*context.active_files,destination),metadata={**context.metadata,'response_render':rendered}))
        finally:rendered.cleanup()
        if not result.success:return result
        return success('Exported the actual '+format.upper()+(' chart' if action=='export_chart' else ' bounded source sample')+' and verified its destination hash.',response_export=result.output,provenance='SYSTEM_STATE')
    if action in {'show_table','hide_table'}:
        if component.kind=='chart':config.update(table=True,table_expanded=action=='show_table')
    elif action in {'filter','sort'}:
        key='filter' if action=='filter' else 'sort'
        if action=='sort':
            snapshot=ResponseSources(controller.runtime,context.conversation_id).resolve(source)
            fields=list(dict.fromkeys(k for row in snapshot.rows for k in row))
            matches=[f for f in fields if f.casefold().replace('_',' ')==value.casefold().replace('_',' ')]
            if len(matches)!=1:raise ValueError('Choose an actual source column: '+', '.join(fields[:24]))
            value={'field':matches[0],'descending':args.get('descending',False)}
        if component.kind=='chart':config.update(table=True,table_expanded=True);key='table_'+key
        config[key]=value
    elif action=='style':config['style']=value
    elif action in {'parameter','strategy'}:
        from ..rich_response.calculators import recipe
        owner=ResponseSources(controller.runtime,context.conversation_id);definition=recipe(owner,owner.resolve(source))
        if action=='strategy':
            if definition.get('tool_id')!='electromagnetic_harvester':raise ValueError('This model has no operating-strategy selector.')
            config['strategy']=value
        else:
            matches=[f for f in definition['parameters'] if f.casefold().replace('_',' ')==value.casefold().replace('_',' ')]
            if len(matches)!=1:raise ValueError('Choose an actual model parameter: '+', '.join(definition['parameters']))
            field=matches[0];number=args['value']
            if args.get('unit'):
                number=controller.runtime.research.simulations.quantity({'value':number,'unit':args['unit']},definition['units'][field])
            config['values']={**config.get('values',{}),field:number};config['strategy']=''
    elif action=='explode':config['explode']=args.get('value',1)
    elif action=='wireframe':config['wireframe']=args.get('enabled',True)
    elif action in {'hide_part','show_part'}:
        snapshot=ResponseSources(controller.runtime,context.conversation_id).resolve(source)
        parts=[a for a in snapshot.artifacts if a.path.suffix.casefold()=='.stl']
        matches=[a for a in parts if value.casefold() in {a.id.casefold(),a.name.casefold()}]
        if len(matches)!=1:raise ValueError('Choose an actual part by its exact name or ID: '+', '.join(a.name+' ('+a.id+')' for a in parts))
        hidden=set(config.get('hidden',[]))
        if action=='hide_part':hidden.add(matches[0].id)
        else:hidden.discard(matches[0].id)
        config['hidden']=sorted(hidden)
    updated=Component.from_dict({**asdict(component),'config':config})
    output=port.execute('response.apply',{**target,'updated':asdict(updated)},context)
    return success('Updated '+(component.title or component.kind)+('. The supplied model will recalculate in the visible calculator.' if action in {'parameter','strategy'} else '.'),
        response_control=output,provenance='SYSTEM_STATE')


def register_response_domain(controller):
    schema={'type':'object','required':['action'],'properties':{'action':{'type':'string','enum':list(ACTIONS)},
        'reference':{'type':'string','maxLength':160},'text':{'type':'string','maxLength':200},'unit':{'type':'string','maxLength':40},
        'format':{'type':'string','enum':['png','svg','pdf','csv','json']},
        'value':{'type':'number','minimum':-1e12,'maximum':1e12},'descending':{'type':'boolean'},'enabled':{'type':'boolean'}},'additionalProperties':False}
    def verify(result,expected,context):
        if result.output.get('response_export'):
            from ..media_lab.storage import file_hash
            receipt=result.output['response_export'];valid=file_hash(receipt['path'])==receipt['sha256']
            return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,('Actual chart export independently read back and hashed.',) if valid else ())
        valid=controller._port(context).verify('response.apply',{},result.output['response_control'],context)
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
            ('Actual response identity and validated display configuration independently reread; pending calculations are not completion receipts.',) if valid else ())
    controller.kernel.registry.register(CapabilityDescriptor('nlui.response.control','Control a displayed interactive result',
        provider='morice-nlui-domain',category='interface',input_schema=schema,supports_verification=True,supports_cancellation=True,
        natural_language_intents=('Show the data table','Filter this table to completed','Sort this table by run descending','Set load resistance to 30 ohm',
            'Explode this assembly','Hide part part:0','Use a bar chart','Export this graph as PDF','Export this table as CSV','Export this as PDF'),ui_action='Typed current-chat component configuration',
        verification_contract='Reread exact component identity and validated configuration; existing owners perform recalculations.'),
        lambda args,ctx:handler(controller,args,ctx),verifier=verify)


def resolve_response(clean,context,raw=None):
    args=None
    if clean in {'show the data table','show data table','show this as a table','show this data as a table','show the table','expand the table'}:args={'action':'show_table'}
    elif clean in {'hide the data table','hide data table','hide the table','collapse the table'}:args={'action':'hide_table'}
    elif clean in {'explode this assembly','explode the assembly','explode the model'}:args={'action':'explode','value':1}
    elif clean in {'collapse this assembly','assemble the parts','reset the explosion'}:args={'action':'explode','value':0}
    match=re.fullmatch(r'filter (?:this |the )?table (?:to|by|for) (.{1,200})',clean)
    if match:args={'action':'filter','text':match[1]}
    if clean in {'clear the table filter','clear table filter'}:args={'action':'filter','text':''}
    match=re.fullmatch(r'sort (?:this |the )?table by (.{1,160}?)(?: (ascending|descending))?',clean)
    if match:args={'action':'sort','text':match[1],'descending':match[2]=='descending'}
    match=re.fullmatch(r'(?:use|show|switch to) (?:a |the )?(line|bar|scatter) (?:chart|plot)',clean)
    if match:args={'action':'style','text':match[1]}
    match=re.fullmatch(r'(?:set|change) (?:the )?([\w ]{1,80}?) to (-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)(?: ([a-zµΩω/0-9^* -]{1,40}))?',clean)
    if match and (any(r.get('kind') in {'experiment','research_record','chat_calculation','response'} for r in context.selected)):
        original=re.search(r'\bto\s+-?\d+(?:\.\d+)?(?:e[+-]?\d+)?(?:\s+([\wµΩ/^* -]{1,40}))?[.!?]?\s*$',raw or clean,re.I)
        args={'action':'parameter','text':match[1],'value':float(match[2]),'unit':original[1].strip() if original and original[1] else ''}
    match=re.fullmatch(r'(?:hide|show) (?:the )?part (.{1,160})',clean)
    if match:args={'action':'hide_part' if clean.startswith('hide') else 'show_part','text':match[1]}
    match=re.fullmatch(r'(?:turn|switch) (on|off) wireframe',clean)
    if match:args={'action':'wireframe','enabled':match[1]=='on'}
    strategies={'maximize output':'maximum_output','use maximum output':'maximum_output','use balanced strategy':'balanced','maximize efficiency':'maximum_efficiency'}
    if clean in strategies:args={'action':'strategy','text':strategies[clean]}
    match=re.fullmatch(r'(?:export|save) (?:the |this )?(?:chart|graph|plot)(?: as (png|svg|pdf))?',clean)
    if match:args={'action':'export_chart','format':match[1] or 'png'}
    match=re.fullmatch(r'(?:export|save) (?:the |this )?(?:table|data|dataset) as (csv|json)',clean)
    if match:args={'action':'export_data','format':match[1]}
    if clean in {'export this as pdf','export this report as pdf','make a report from this','save this report as pdf'}:args={'action':'export_report','format':'pdf'}
    return IntentResolution(operations=(Operation('nlui.response.control',args),),route='domain') if args else IntentResolution()
