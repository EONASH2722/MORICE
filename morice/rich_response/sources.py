"""Reference resolution over existing domain stores; no new result database."""
from __future__ import annotations

from dataclasses import asdict,dataclass,field,replace
import hashlib
import json
from pathlib import Path
import time
import threading
from contextlib import contextmanager

from .contracts import SourceRef


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,default=str).encode()).hexdigest()


@dataclass(frozen=True)
class VerifiedArtifact:
    id:str
    name:str
    path:Path
    sha256:str
    size:int
    unit:str=''
    available:bool=True
    reason:str=''


@dataclass
class SourceSnapshot:
    source:SourceRef
    title:str
    provenance:str
    revision:str
    data:dict
    rows:list=field(default_factory=list)
    units:dict=field(default_factory=dict)
    artifacts:list=field(default_factory=list)
    verified:bool=False
    observed_at:float=field(default_factory=time.time)
    limitation:str=''


class StaleSourceError(ValueError):pass


class ResponseSources:
    def __init__(self,runtime,conversation_id,*,messages=()):
        self.runtime=runtime;self.conversation_id=conversation_id
        self._cancellation=threading.local()
        self._messages={m['message_id']:dict(m) for m in messages if m.get('message_id') and m.get('role') in {'user','assistant'} and len(m.get('content',''))<=200000}

    def original_message(self,identifier):
        return self.runtime.chat_history.fetch_message(self.conversation_id,identifier) or self._messages.get(identifier)

    def current_cancellation(self):return getattr(self._cancellation,'token',None)

    @contextmanager
    def using_cancellation(self,token):
        previous=self.current_cancellation();self._cancellation.token=token
        try:
            if token is not None:token.raise_if_cancelled()
            yield
            if token is not None:token.raise_if_cancelled()
        finally:self._cancellation.token=previous

    def resolve(self,source):
        if not isinstance(source,SourceRef):raise ValueError('A typed source reference is required.')
        if source.scope and source.scope!=self.conversation_id:raise PermissionError('This rich result belongs to another conversation.')
        token=self.current_cancellation()
        if token is not None:token.raise_if_cancelled()
        value=getattr(self,'_'+source.kind)(source)
        if token is not None:token.raise_if_cancelled()
        if source.revision and source.revision!=value.revision:raise StaleSourceError('The source changed since this response. Refresh the result before acting on it.')
        return value

    @staticmethod
    def _artifact(identifier,name,path,expected_hash,root,unit='',*,strict=True,cancellation=None):
        from ..media_lab.storage import file_hash
        path=Path(path).resolve();root=Path(root).resolve()
        if not path.is_relative_to(root):raise ValueError('Artifact is outside its actual owner’s directory.')
        size=path.stat().st_size if path.is_file() else 0
        reason=('Artifact file is missing.' if not path.is_file() else 'Artifact exceeds the 512 MiB interactive export limit.' if size>512*1024**2
            else 'Artifact hash changed; preview and export are disabled.' if file_hash(path,cancellation)!=expected_hash else '')
        if reason and strict:raise StaleSourceError(reason)
        return VerifiedArtifact(identifier,str(name)[:200],path,expected_hash,size,unit,not bool(reason),reason)

    def _manifest(self,value,root):
        artifacts=[]
        if not isinstance(value,dict):return artifacts
        for key,hash_key in (('stl','sha256'),('bom','bom_sha256')):
            if value.get(key) and value.get(hash_key):
                artifacts.append(self._artifact(key,Path(value[key]).name,value[key],value[hash_key],root,value.get('units','') if key=='stl' else '',strict=False,cancellation=self.current_cancellation()))
        if value.get('directory') and isinstance(value.get('checksums'),dict):
            directory=Path(value['directory']).resolve()
            for name,expected in list(value['checksums'].items())[:100]:
                if not isinstance(name,str) or Path(name).name!=name:raise ValueError('Invalid owner artifact manifest entry.')
                artifacts.append(self._artifact(name,name,directory/name,expected,root,strict=False,cancellation=self.current_cancellation()))
        parts=value.get('parts',[])
        if parts:
            if not isinstance(parts,list) or len(parts)>12:raise ValueError('Assembly preview supports at most twelve actual mesh parts.')
            for index,part in enumerate(parts):
                if not isinstance(part,dict) or not part.get('stl') or not part.get('sha256'):raise ValueError('Each assembly part needs an actual STL and hash.')
                artifacts.append(self._artifact('part:'+str(part.get('id',index)),part.get('name',Path(part['stl']).name),
                    part['stl'],part['sha256'],root,part.get('units',value.get('units','')),strict=False,cancellation=self.current_cancellation()))
        if len({a.id for a in artifacts})!=len(artifacts):raise ValueError('Artifact manifest contains ambiguous duplicate identities.')
        return artifacts

    def _experiment(self,source):
        import math
        research=self.runtime.research;metadata=research.laboratory.get(source.id)
        stride=max(1,math.ceil(metadata['completed_runs']/1000))
        row=research.laboratory.get(source.id,True,run_limit=1000,run_stride=stride)
        record=next(r for r in research.store.snapshot(row['project_id'])['records'] if r['id']==row['record_id'])
        if record['stale']:raise StaleSourceError('Experiment inputs or model are stale. Recompute in Research before using this result.')
        tool=research.laboratory.registry.get(row['spec']['simulation_engine'])
        if row['estimate'].get('model_fingerprint')!=research.laboratory.registry.fingerprint(tool.tool_id):
            raise StaleSourceError('Experiment model or compiler changed. Recompute it before using current validation/downloads.')
        rows=self._run_rows(row['runs'])
        row['presentation_stride']=stride
        units={**{'input_'+k:v for k,v in tool.required_units.items()},**{'output_'+k:v for k,v in tool.supported_outputs.items()},'elapsed_ms':'ms'}
        artifacts=self._manifest(row['summary'].get('artifacts',{}),research.directory)
        return SourceSnapshot(source,row['title'],'SIMULATED',row['updated'],row,rows,units,artifacts,True,
            limitation='Computational model only; not a hardware measurement. '+str(tool.limitations))

    @staticmethod
    def _run_rows(runs):
        return [{'run':r['run_index'],**{'input_'+k:v for k,v in r['parameters'].items()},
            **{'output_'+k:v for k,v in r['outputs'].items()},'status':r['status'],'elapsed_ms':r['elapsed_ms']} for r in runs]

    def table_page(self,source,*,offset=0,limit=100,query='',sort=None):
        if type(offset) is not int or offset<0 or type(limit) is not int or not 5<=limit<=200 or not isinstance(query,str) or len(query)>200:
            raise ValueError('Invalid bounded table page request.')
        snapshot=self.resolve(source)
        if source.kind=='experiment':
            row=self.runtime.research.laboratory.get(source.id,True,run_limit=limit,run_offset=offset,run_filter=query,run_sort=sort)
            if source.revision and row['updated']!=source.revision:raise StaleSourceError('Experiment changed while loading the requested page.')
            return {'rows':self._run_rows(row['runs']),'count':row['matching_runs'],'offset':offset,'limit':limit}
        rows=snapshot.rows
        if not rows:
            # Workspace owners expose different bounded record collections.
            for key in ('watches','models','nodes','plugins','findings','sessions','workflows','connectors','receipts'):
                candidate=snapshot.data.get(key)
                if isinstance(candidate,list):rows=candidate;break
            if not rows and isinstance(snapshot.data.get('security'),dict):rows=snapshot.data['security'].get('findings',[])
        rows=[r for r in rows if isinstance(r,dict)]
        if query:rows=[r for r in rows if query.casefold() in json.dumps(r,ensure_ascii=False,default=str).casefold()]
        if sort:
            field=sort['field'];values=[r.get(field) for r in rows]
            numeric=all(v is None or type(v) in (int,float) for v in values)
            rows=sorted(rows,key=lambda r:(r.get(field) is None,r.get(field) if numeric and r.get(field) is not None else str(r.get(field,''))),reverse=sort.get('descending',False))
        return {'rows':rows[offset:offset+limit],'count':len(rows),'offset':offset,'limit':limit}

    def _research_catalog(self,source):
        rows=self.runtime.research.store.list_projects()[:1000]
        return SourceSnapshot(source,'Research notebooks','USER_DATA',digest(rows),{'count':len(rows)},rows,verified=True)

    def _experiment_catalog(self,source):
        rows=self.runtime.research.laboratory.list(source.id)
        shown=[{k:row[k] for k in ('id','title','status','completed_runs','created','updated')} for row in rows]
        return SourceSnapshot(source,'Saved experiments','SIMULATED',digest(shown),{'count':len(rows)},shown,verified=True)

    def _media_catalog(self,source):
        rows=self.runtime.media.history(limit=100)
        shown=[{'id':r['generation_id'],'prompt':r.get('request',{}).get('prompt',''),'status':r['status'],
            'model':r.get('model',''),'created':r.get('created_at')} for r in rows]
        return SourceSnapshot(source,'Media history','GENERATED_VISUAL',digest(shown),{'count':len(shown)},shown,verified=True)

    def _experiment_comparison(self,source):
        first,separator,second=source.id.partition(':')
        if not separator or first==second:raise ValueError('Choose two actual experiment identities.')
        a=self._experiment(SourceRef('experiment',first,scope=source.scope));b=self._experiment(SourceRef('experiment',second,scope=source.scope))
        comparison=self.runtime.research.laboratory.compare(first,second)
        tool=self.runtime.research.laboratory.registry.get(a.data['spec']['simulation_engine'])
        rows=[]
        for key in tool.required_units:
            rows.append({'parameter':key,'first':self.runtime.research.laboratory.registry.quantity(a.data['spec']['parameters'][key],tool.required_units[key]),
                'second':self.runtime.research.laboratory.registry.quantity(b.data['spec']['parameters'][key],tool.required_units[key]),'unit':tool.required_units[key]})
        for key,unit in tool.supported_outputs.items():
            left=a.data['summary'].get('best_observed',{}).get('outputs',{}).get(key)
            right=b.data['summary'].get('best_observed',{}).get('outputs',{}).get(key)
            if left is not None or right is not None:rows.append({'parameter':key,'first':left,'second':right,'unit':unit})
        return SourceSnapshot(source,a.title+' / '+b.title,'SIMULATED',digest(comparison),comparison,rows,verified=True,
            limitation=comparison['limitation']+' Best sampled candidates are not controlled experimental comparisons.')

    def _research_project(self,source):
        row=self.runtime.research.store.snapshot(source.id)
        rows=[{k:r[k] for k in ('id','kind','title','provenance','stale','revision','created') if k in r} for r in row['records']]
        return SourceSnapshot(source,row['objective'],'USER_DATA',row['updated'],row,rows,verified=True,
            limitation='Stored evidence integrity does not certify scientific assumptions.')

    def _research_record(self,source):
        project_id,separator,record_id=source.id.partition(':')
        if not separator:raise ValueError('Research record reference needs its actual notebook identity.')
        project=self.runtime.research.store.snapshot(project_id)
        row=next((r for r in project['records'] if r['id']==record_id),None)
        if row is None:raise ValueError('Research record is missing.')
        if row['stale']:raise StaleSourceError('Research record is stale; dependent views and downloads are disabled.')
        payload=row['payload'];value=payload.get('result',payload)
        files=self._manifest(value,self.runtime.research.directory)
        rows=value.get('rows',[]) if isinstance(value,dict) else value if isinstance(value,list) else []
        if not isinstance(rows,list):rows=[]
        return SourceSnapshot(source,row['title'],row['provenance'],str(row['revision']),payload,rows[:1000],artifacts=files,
            verified=row['provenance'] in {'CALCULATED','SIMULATED','CITED','USER_DATA'},limitation=str(payload.get('limitations',''))[:2000])

    def _media_generation(self,source):
        media=self.runtime.media;row=media.result(source.id)
        if row is None:raise ValueError('Media generation is missing.')
        artifacts=[]
        if row['status']=='SUCCEEDED':
            if row.get('node_id') and row['node_id']!='local':raise ValueError('Transfer the actual remote artifact through Device Mesh before local preview.')
            for index in range(min(16,len(row.get('artifacts',[])))):
                declared=row['artifacts'][index];error=''
                try:item=media.artifact(source.id,index)
                except (ValueError,OSError) as exc:item=declared;error=str(exc)
                artifact=self._artifact(str(index),Path(item['path']).name,item['path'],item['sha256'],media.directory/'outputs'/source.id,strict=False,cancellation=self.current_cancellation())
                artifacts.append(replace(artifact,available=False,reason=error) if error else artifact)
        return SourceSnapshot(source,str(row.get('request',{}).get('prompt','Generated media'))[:200],
            'GENERATED_VISUAL',digest(row),row,artifacts=artifacts,verified=bool(artifacts) and all(a.available for a in artifacts),
            limitation='Generated content; not evidence of an actual event or measurement.')

    def _build_session(self,source):
        owner=self.runtime.autonomous_builder.project_runtime;session=owner.load(source.id)
        if session is None:raise ValueError('Build session is missing.')
        row={**session.result_card(),'created':session.created_at,'updated':session.updated_at,
            'command_evidence':list(session.command_evidence[-100:]),'milestone':session.milestone};artifacts=[]
        for index,item in enumerate(row.get('artifacts',[])[:100]):
            if isinstance(item,dict) and item.get('path') and item.get('sha256'):
                artifacts.append(self._artifact(str(index),Path(item['path']).name,item['path'],item['sha256'],session.project_root,strict=False,cancellation=self.current_cancellation()))
        return SourceSnapshot(source,str(session.user_goal)[:200],'SYSTEM_STATE',digest(row),row,
            rows=row['command_evidence'] or row.get('issues',[])[:200],artifacts=artifacts,verified=session.success,
            limitation='Only recorded checks and actual artifact verification are evidence of completion.')

    def _workspace(self,source):
        from ..nlui.workspace_domains import snapshot
        row=snapshot(self.runtime,source.id)
        return SourceSnapshot(source,source.id.title()+' status','SYSTEM_STATE',digest(row),row,verified=True,
            limitation='Point-in-time service observation; active work can advance.')

    def _saved_source_data(self,source,owner):
        message=self.original_message(source.id)
        if not message or message['role']!='assistant':raise ValueError('The original response source is unavailable in this conversation.')
        attachments=message.get('attachments',[])
        if isinstance(attachments,str):
            if len(attachments.encode())>128*1024:raise ValueError('Response source attachments exceed their bound.')
            attachments=json.loads(attachments)
        if not isinstance(attachments,list):raise ValueError('Invalid saved source attachments.')
        saved=next((a for a in attachments[:30] if isinstance(a,dict) and a.get('kind')=='response_source' and a.get('owner')==owner and a.get('schema')==1),None)
        if saved is None:raise ValueError('The actual response source is missing.')
        if digest(saved['data'])!=saved.get('revision'):raise StaleSourceError('Saved response source failed its integrity check.')
        return saved['data']

    def _spatial(self,source):
        from ..spatial.contracts import SpatialContext
        row=self.runtime.spatial.snapshot() if source.id=='current' else SpatialContext.from_dict(self._saved_source_data(source,'spatial')).to_dict()
        return SourceSnapshot(source,'Spatial result','CALCULATED',digest(row),row,verified=not bool(row.get('pending')),
            limitation='Geographic calculation; a road-routing provider is required for driving/walking distances.')

    def _chat_metadata(self,source):
        if source.id==self.conversation_id:rows=self.runtime.chat_history.search('',limit=100)
        else:
            data=self._saved_source_data(source,'chat_search')
            if not isinstance(data,dict) or set(data)!={'query'} or not isinstance(data['query'],str) or len(data['query'])>200:raise ValueError('Invalid saved transcript query.')
            rows=self.runtime.chat_history.search_transcripts(data['query'],exclude_chat=self.conversation_id,limit=20)
        return SourceSnapshot(source,'Saved conversations','USER_DATA',digest(rows),{'count':len(rows)},rows,verified=True)

    def _personal_memory(self,source):
        rows=[asdict(r) for r in self.runtime.desktop.memory.list_preferences()][:200]
        return SourceSnapshot(source,'Saved preferences','USER_DATA',digest(rows),{'count':len(rows)},rows,verified=True,
            limitation='Only enabled, approved and relevant preferences are applied. Preferences cannot grant permissions.')

    def _chat_calculation(self,source):
        message=self.original_message(source.id)
        if not message or message['role']!='user':raise ValueError('The original calculation request is missing from this chat.')
        from ..research.harvester import parse_harvester_table,INPUT_UNITS,OUTPUT_UNITS
        spec=parse_harvester_table(message['content'])
        if spec is None:raise ValueError('This message has no supported deterministic calculation data.')
        rows=[];errors=[]
        import math
        from ..kernel import ExecutionContext
        context=ExecutionContext(conversation_id=self.conversation_id,cancellation_token=self.current_cancellation())
        for excitation in spec['accelerations_g'][:100]:
            parameters={**spec['parameters'],'acceleration':excitation*9.80665*(math.sqrt(2) if spec['rms'] else 1)}
            if self.current_cancellation() is not None:self.current_cancellation().raise_if_cancelled()
            result=self.runtime.research.execute('research.simulate',{'tool_id':'electromagnetic_harvester','parameters':parameters},context=context)
            if result.success and result.verification and result.verification.status.value=='verified':
                rows.append({'excitation_g':excitation,**result.output['outputs']})
            else:errors.append({'excitation_g':excitation,'reason':'; '.join(e.message for e in result.errors)})
        data={'specification':spec,'rows':rows,'errors':errors,'input_units':INPUT_UNITS,'output_units':OUTPUT_UNITS}
        return SourceSnapshot(source,'Conditional harvester calculation','CALCULATED',hashlib.sha256(message['content'].encode()).hexdigest(),
            data,rows,{'excitation_g':'g',**OUTPUT_UNITS},verified=bool(rows),
            limitation='Linear resistive model with supplied inputs. Potential DC excludes unspecified startup/quiescent losses; not measured usable power.')

    def _chat_dataset(self,source):
        message=self.original_message(source.id)
        if not message or message['role']!='user':raise ValueError('The original user dataset is unavailable in this chat.')
        from .planner import parse_user_table
        rows=parse_user_table(message['content'])
        if not rows:raise ValueError('The user message contains no supported bounded table.')
        identity='__source_row_id'
        while any(identity in row for row in rows):identity+='_'
        rows=[{**row,identity:'user-row:'+str(index)} for index,row in enumerate(rows)]
        return SourceSnapshot(source,'User supplied data','USER_DATA',hashlib.sha256(message['content'].encode()).hexdigest(),
            {'count':len(rows),'row_identity_field':identity},rows,verified=True,limitation='Values were supplied by the user; their real-world accuracy has not been independently established.')
