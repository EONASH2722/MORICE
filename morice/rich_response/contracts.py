"""Versioned data-only rich responses. Payloads cannot carry executable actions."""
from __future__ import annotations

from dataclasses import asdict,dataclass,field
import json
import re
import uuid


SOURCE_KINDS=frozenset({'experiment','research_project','research_record','media_generation',
    'build_session','workspace','chat_calculation','chat_metadata','personal_memory','spatial',
    'research_catalog','experiment_catalog','media_catalog','experiment_comparison','chat_dataset','security_lab'})
COMPONENTS={
    'metrics':{'fields','columns'},'status':{'fields'},'validation':{'fields'},
    'table':{'columns','filter','sort','page_size'},'chart':{'x','ys','style','x_label','y_label','unit','table','table_expanded','table_filter','table_sort','selected'},
    'calculator':{'parameter','minimum','maximum','step','strategy','output','values'},'math':{'formula'},
    'diagram':{'nodes','edges','orientation'},'timeline':{'fields'},'progress':{'refresh_seconds'},
    'files':{'formats'},'preview':{'artifact','fit'},'mesh':{'artifact','wireframe','camera','selected'},
    'assembly':{'explode','wireframe','selected','hidden','camera'},'media':{'indices','compare'},
    'spatial':{'mode','unit'},'simulation':{'parameter','output'},'comparison':{'fields'},
}
FORBIDDEN=frozenset({'command','script','python','javascript','html','path','url','permissions','approval_token',
    'permission_token','credentials','password','api_key','callback','function','execute','code'})


def bounded_data(value,*,maximum=65536):
    try:raw=json.dumps(value,ensure_ascii=False,allow_nan=False)
    except (ValueError,TypeError,RecursionError) as exc:raise ValueError('Response data must be finite JSON.') from exc
    if len(raw.encode('utf-8'))>maximum:raise ValueError('Response data exceeds its storage bound.')
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1
        if depth>10 or count>4096:raise ValueError('Response data exceeds structural bounds.')
        if isinstance(item,dict):
            if any(not isinstance(key,str) or key.casefold() in FORBIDDEN for key in item):
                raise ValueError('Executable content, paths and permission grants are not response configuration.')
            pending.extend((child,depth+1) for child in item.values())
        elif isinstance(item,list):pending.extend((child,depth+1) for child in item)
    return raw


def text(value,limit,name):
    if not isinstance(value,str) or len(value)>limit or '\x00' in value:raise ValueError('Invalid '+name+'.')
    return value


def validate_config(kind,config):
    strings={'x','x_label','y_label','unit','filter','table_filter','parameter','strategy','output','formula','artifact','selected','fit','orientation','style','mode'}
    booleans={'table','table_expanded','wireframe','compare'}
    numbers={'minimum','maximum','step','explode','refresh_seconds'}
    lists={'fields','ys','hidden','formats','indices','nodes','edges'}
    for key,value in config.items():
        if key in strings:text(value,4000 if key=='formula' else 200,'component '+key)
        elif key in booleans and type(value) is not bool:raise ValueError(key+' must be boolean.')
        elif key in numbers and type(value) not in (int,float):raise ValueError(key+' must be numeric.')
        elif key in lists and (not isinstance(value,list) or len(value)>128):raise ValueError(key+' must be a bounded list.')
    for key in {'fields','ys','hidden','formats'} & config.keys():
        if any(not isinstance(item,str) or len(item)>160 for item in config[key]):raise ValueError('Invalid named response field.')
    if 'indices' in config and any(type(item) is not int or not 0<=item<16 for item in config['indices']):raise ValueError('Invalid media index.')
    if 'columns' in config:
        if kind=='metrics':
            if type(config['columns']) is not int or not 1<=config['columns']<=4:raise ValueError('Metrics support one to four columns.')
        elif not isinstance(config['columns'],list) or len(config['columns'])>32 or any(not isinstance(c,str) or len(c)>160 for c in config['columns']):
            raise ValueError('Invalid table columns.')
    if 'page_size' in config and (type(config['page_size']) is not int or not 5<=config['page_size']<=200):raise ValueError('Invalid table page size.')
    for key in {'sort','table_sort'} & config.keys():
        value=config[key]
        if not isinstance(value,dict) or set(value)-{'field','descending'} or not isinstance(value.get('field'),str) or type(value.get('descending',False)) is not bool:
            raise ValueError('Invalid table sort configuration.')
    if kind=='chart' and config.get('style','line') not in {'line','bar','scatter'}:raise ValueError('Unsupported chart style.')
    if 'explode' in config and not 0<=config['explode']<=2:raise ValueError('Exploded view exceeds its supported range.')
    if 'refresh_seconds' in config and not .5<=config['refresh_seconds']<=30:raise ValueError('Invalid refresh interval.')
    if 'step' in config and config['step']<=0:raise ValueError('Calculator step must be positive.')
    if 'values' in config:
        value=config['values']
        if (not isinstance(value,dict) or len(value)>64 or any(not isinstance(k,str) or not k.isidentifier() or type(v) not in (int,float) or abs(v)>1e12 for k,v in value.items())):
            raise ValueError('Calculator state must contain bounded actual parameter values.')
    if 'camera' in config:
        value=config['camera']
        if (not isinstance(value,dict) or set(value)!={'yaw','pitch','zoom'} or any(type(v) not in (int,float) for v in value.values())
                or not -1.6<=value['pitch']<=1.6 or not .15<=value['zoom']<=12 or abs(value['yaw'])>1e6):
            raise ValueError('Invalid bounded mesh camera state.')
    if 'minimum' in config and 'maximum' in config and config['minimum']>=config['maximum']:raise ValueError('Calculator bounds must be increasing.')
    if kind=='diagram':
        nodes=config.get('nodes',[]);edges=config.get('edges',[])
        for node in nodes:
            if not isinstance(node,dict) or set(node)-{'id','label'} or not isinstance(node.get('id'),str) or not isinstance(node.get('label'),str):
                raise ValueError('Diagram nodes require plain identities and labels.')
        identities={node['id'] for node in nodes}
        if len(identities)!=len(nodes):raise ValueError('Duplicate diagram nodes.')
        for edge in edges:
            if not isinstance(edge,dict) or set(edge)-{'from','to','label'} or edge.get('from') not in identities or edge.get('to') not in identities:
                raise ValueError('Diagram edge must link actual nodes.')
        if config.get('orientation','vertical') not in {'vertical','horizontal'}:raise ValueError('Unknown diagram direction.')


@dataclass(frozen=True)
class SourceRef:
    kind:str
    id:str
    revision:str=''
    scope:str=''

    def __post_init__(self):
        if not isinstance(self.kind,str) or self.kind not in SOURCE_KINDS:raise ValueError('Unsupported rich response source owner.')
        if not isinstance(self.id,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,240}',self.id):raise ValueError('Source identity must be bounded data.')
        text(self.revision,240,'source revision');text(self.scope,128,'source scope')

    @classmethod
    def from_dict(cls,value):
        if not isinstance(value,dict) or set(value)-{'kind','id','revision','scope'}:raise ValueError('Unknown source fields.')
        try:return cls(**value)
        except TypeError as exc:raise ValueError('Invalid source reference.') from exc


@dataclass(frozen=True)
class Component:
    kind:str
    source:SourceRef|None=None
    title:str=''
    config:dict=field(default_factory=dict)
    id:str=field(default_factory=lambda:uuid.uuid4().hex)

    def __post_init__(self):
        if not isinstance(self.kind,str) or self.kind not in COMPONENTS:raise ValueError('Unsupported response component.')
        if self.source is not None and not isinstance(self.source,SourceRef):raise ValueError('Invalid component source.')
        if self.source is None and self.kind not in {'math','diagram'}:raise ValueError('This component requires a real source reference.')
        text(self.title,160,'component title')
        if not isinstance(self.id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',self.id):raise ValueError('Invalid component identity.')
        if not isinstance(self.config,dict) or set(self.config)-COMPONENTS[self.kind]:raise ValueError('Unknown component configuration.')
        bounded_data(self.config,maximum=16384)
        validate_config(self.kind,self.config)

    @classmethod
    def from_dict(cls,value):
        if not isinstance(value,dict) or set(value)-{'kind','source','title','config','id'}:raise ValueError('Unknown component fields.')
        value=dict(value)
        if value.get('source') is not None:value['source']=SourceRef.from_dict(value['source'])
        try:return cls(**value)
        except TypeError as exc:raise ValueError('Invalid component specification.') from exc


@dataclass(frozen=True)
class ResponsePlan:
    conversation_id:str
    components:tuple[Component,...]
    summary:str=''
    profile:str='auto'
    schema:int=1
    id:str=field(default_factory=lambda:uuid.uuid4().hex)

    def __post_init__(self):
        if type(self.schema) is not int or self.schema!=1:raise ValueError('Unsupported response schema version.')
        text(self.conversation_id,128,'conversation identity');text(self.summary,20000,'response summary')
        if not self.conversation_id or not isinstance(self.id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',self.id):raise ValueError('Invalid response identity.')
        if not isinstance(self.profile,str) or self.profile not in {'auto','compact','detailed','visual','technical'}:raise ValueError('Unknown presentation profile.')
        if not isinstance(self.components,tuple) or not 1<=len(self.components)<=24 or any(not isinstance(c,Component) for c in self.components):
            raise ValueError('A response requires 1–24 registered components.')
        if len({c.id for c in self.components})!=len(self.components):raise ValueError('Duplicate component identities.')
        bounded_data(self.to_dict())

    def to_dict(self):
        value=asdict(self);value['components']=[asdict(c) for c in self.components];return value

    @classmethod
    def from_dict(cls,value):
        if not isinstance(value,dict) or set(value)-{'conversation_id','components','summary','profile','schema','id'}:
            raise ValueError('Unknown rich response fields.')
        bounded_data(value);value=dict(value)
        if not isinstance(value.get('components'),list):raise ValueError('Response components must be a list.')
        value['components']=tuple(Component.from_dict(item) for item in value['components'])
        try:return cls(**value)
        except TypeError as exc:raise ValueError('Invalid response plan.') from exc
