"""Cheap presentation selection from real domain outputs, without another model router."""
from __future__ import annotations

import csv
import hashlib
import math
import re

from .contracts import Component,ResponsePlan,SourceRef
from .sources import digest


def parse_user_table(content):
    """Read a bounded literal CSV/Markdown table, never numbers invented by a model."""
    if not isinstance(content,str) or len(content)>200000:return []
    lines=content.splitlines();groups=[];group=[]
    for line in lines:
        if '|' in line or ',' in line:
            group.append(line.strip())
        elif group:groups.append(group);group=[]
    if group:groups.append(group)
    for group in groups:
        if len(group)<3:continue
        delimiter='|' if '|' in group[0] else ','
        try:cells=list(csv.reader([line.strip('|') if delimiter=='|' else line for line in group[:1002]],delimiter=delimiter))
        except csv.Error:continue
        cells=[[item.strip() for item in row] for row in cells]
        columns=cells[0]
        if not 2<=len(columns)<=24 or any(not c or len(c)>120 for c in columns) or len(set(columns))!=len(columns):continue
        rows=[]
        for values in cells[1:]:
            if all(re.fullmatch(r':?-{3,}:?',value or '') for value in values):continue
            if len(values)!=len(columns):rows=[];break
            parsed={}
            for column,value in zip(columns,values):
                try:number=float(value)
                except ValueError:parsed[column]=value[:2000]
                else:parsed[column]=number if math.isfinite(number) else value
            rows.append(parsed)
        if rows:return rows[:1000]
    return []


def numeric_columns(rows):
    if not rows:return []
    return [key for key in rows[0] if all(type(row.get(key)) in (int,float) and math.isfinite(row[key]) for row in rows)]


def wants_data_presentation(content):
    """Prompt data supplements a reply only when its presentation is requested."""
    if not isinstance(content,str):return False
    # Ignore tables and code: examples and input values do not request a UI.
    prose=re.sub(r'```.*?```|~~~.*?~~~','',content,flags=re.S)
    lines=[line for line in prose.splitlines() if '|' not in line]
    for line in lines:
        clean=line.strip().casefold()
        if re.search(r'\b(?:do not|don\'t|no|without)\b.{0,40}\b(?:interactive|chart|graph|plot|dashboard)\b',clean):continue
        clean=re.sub(r'^(?:[-*]\s+|\d+[.)]\s+)?(?:(?:please\s+)|(?:(?:can|could|would) you\s+))*','',clean)
        if re.match(r'^(?:plot|graph|chart|visuali[sz]e)\b',clean):return True
        if re.match(r'^(?:show|display|present|render|make|create|give|use|add|include)\b.{0,100}\b(?:interactive|chart|graph|plot|dashboard)\b',clean):return True
    return False


class ResponsePlanner:
    """Layout metadata only. Source resolution, execution and policy stay with owners."""

    def from_nlui(self,result,context,profile='auto'):
        components=[];seen=set()
        def add(kind,source,title='',config=None):
            key=(kind,source.kind,source.id)
            if key not in seen:
                components.append(Component(kind,source,title,config or {}));seen.add(key)
        for execution in result.executions:
            if not execution.get('success') or not isinstance(execution.get('output'),dict):continue
            value=execution['output'];capability=execution.get('capability_id','')
            if value.get('lab_job_id'):
                source=SourceRef('security_lab',value['lab_job_id'],scope=context.conversation_id)
                add('status',source,'Actual Security Lab outcome')
                add('metrics',source,'Candidate workload and elapsed time',{'fields':['tested_candidates','candidate_count','seconds']})
                add('table',source,'Actual attempts, checks or findings')
                add('files',source,'Verified recovered artifacts')
            if value.get('build_session_id'):
                source=SourceRef('build_session',value['build_session_id'],scope=context.conversation_id)
                add('progress',source,'Actual Builder state')
                add('validation',source,'Recorded project checks')
                add('table',source,'Command receipts and open issues')
                add('files',source,'Actual build artifacts')
            elif value.get('record'):
                row=value['record'];payload=row['payload'];data=payload.get('result',{})
                source=SourceRef('research_record',value['project_id']+':'+row['id'],str(row['revision']),context.conversation_id)
                if payload.get('method')=='research.calculate':
                    add('calculator',source,'Explore the saved calculation');add('math',source,'Supplied expression')
                if isinstance(data,dict) and (data.get('parts') or data.get('stl')):
                    add('assembly' if len(data.get('parts',[]))>1 else 'mesh',source,'Actual saved geometry')
                if isinstance(data,dict) and (data.get('parts') or data.get('stl') or data.get('bom') or data.get('checksums')):
                    add('files',source,'Actual saved files')
                add('validation',source,'Stored operation receipt')
            elif value.get('experiment'):
                row=value['experiment'];source=SourceRef('experiment',row['id'],str(row['updated']),context.conversation_id)
                add('metrics',source,'Computational run summary',{'fields':['completed_runs','estimate.planned_runs','summary.valid_runs','summary.invalid_runs']})
                if row.get('runs'):
                    spec=row['spec'];x='input_'+next(iter(spec.get('parameter_ranges',{})),'') if spec.get('parameter_ranges') else 'run'
                    add('chart',source,'Saved run outputs',{'x':x,'ys':['output_'+spec['metric']],'table':True})
                    add('calculator',source,'Explore the supplied model')
                add('simulation',SourceRef('experiment',row['id'],scope=context.conversation_id),'Experiment controls')
                if row.get('summary',{}).get('artifacts'):add('files',source,'Actual experiment files')
            elif value.get('comparison'):
                row=value['comparison'];source=SourceRef('experiment_comparison',row['first']+':'+row['second'],scope=context.conversation_id)
                add('comparison',source,'Saved model comparison');add('table',source,'Parameters and best sampled outputs')
            elif 'projects' in value:
                add('table',SourceRef('research_catalog','saved',scope=context.conversation_id),'Research notebooks')
            elif 'experiments' in value:
                add('table',SourceRef('experiment_catalog',value['project_id'],scope=context.conversation_id),'Saved experiments')
            elif value.get('media_items'):
                for item in value['media_items'][:4]:
                    source=SourceRef('media_generation',item['id'],scope=context.conversation_id)
                    add('media',source,'Actual generated artifact');add('files',source,'Verified artifact file')
            elif 'generations' in value:
                add('table',SourceRef('media_catalog','saved',scope=context.conversation_id),'Media history')
            elif value.get('generation_id'):
                add('progress',SourceRef('media_generation',value['generation_id'],scope=context.conversation_id),'Media job')
            elif value.get('spatial_context'):
                source=SourceRef('spatial','current',digest(value['spatial_context']),context.conversation_id)
                add('spatial',source,'Actual geographic result')
            elif value.get('domain') and 'snapshot' in value:
                source=SourceRef('workspace',value['domain'],scope=context.conversation_id)
                add('status',source,value['domain'].title()+' status');add('table',source,'Current records')
            elif 'preferences' in value:
                add('table',SourceRef('personal_memory','saved',scope=context.conversation_id),'Saved preferences')
            elif 'chats' in value:
                add('table',SourceRef('chat_metadata',context.conversation_id,scope=context.conversation_id),'Saved conversations')
        if not components:return None
        return ResponsePlan(context.conversation_id,tuple(components[:24]),result.message,profile)

    def from_user_message(self,message,conversation_id,profile='auto'):
        if message.get('role')!='user' or not message.get('message_id'):return None
        content=message.get('content','')
        if not isinstance(content,str) or len(content)>200000:return None
        if not wants_data_presentation(content):return None
        revision=hashlib.sha256(content.encode()).hexdigest()
        # This trigger is cheap; actual scientific parsing/recalculation stays lazy.
        if ('coil resistance' in content.casefold() and 'coupling' in content.casefold() and '|' in content):
            from ..research.harvester import parse_harvester_table
            if parse_harvester_table(content) is not None:
                source=SourceRef('chat_calculation',message['message_id'],revision,conversation_id)
                return ResponsePlan(conversation_id,(
                    Component('chart',source,'Conditional model outputs',{'x':'excitation_g','ys':['dc_potential','mechanical_input'],'table':True}),
                    Component('calculator',source,'Explore load and operating strategy'),
                ),profile=profile)
        rows=parse_user_table(content)
        if not rows:return None
        source=SourceRef('chat_dataset',message['message_id'],revision,conversation_id)
        columns=numeric_columns(rows)
        components=([Component('chart',source,'User supplied values',{'x':columns[0],'ys':columns[1:5],'table':True})]
            if len(columns)>=2 else [Component('table',source,'User supplied data')])
        return ResponsePlan(conversation_id,tuple(components),profile=profile)
