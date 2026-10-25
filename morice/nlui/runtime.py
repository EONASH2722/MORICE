"""Capability discovery and intent adaptation; execution stays in the Kernel."""
from __future__ import annotations

from dataclasses import replace
import time
import json
import re
import threading
import weakref
import uuid

from ..kernel import (CapabilityDescriptor,ExecutionContext,ExecutionResult,TaskStatus,
    TaskGraph,TaskNode,VerificationResult,VerificationStatus)
from ..kernel.contracts import VerificationPolicy
from ..kernel.tasks import DependencyPolicy
from .contracts import ActiveContext,IntentResolution,NaturalLanguageResult,Operation


ROUTES=('home','chats','projects','research','spatial','media','devices','automations',
        'connectors','security','history','plugins','settings','tools','activity','voice','artifacts')
ROUTE_ALIASES={
    'home':'home','core':'home','chat':'chats','chats':'chats','conversation':'chats',
    'project':'projects','projects':'projects','builder':'projects','project builder':'projects',
    'research':'research','research lab':'research','lab':'research','experiments':'research',
    'spatial':'spatial','spatial lab':'spatial','globe':'spatial','earth':'spatial',
    'media':'media','media lab':'media','image gallery':'media','media queue':'media',
    'devices':'devices','device connections':'devices','my devices':'devices','paired devices':'devices',
    'automations':'automations','automation':'automations','notifications':'automations',
    'connectors':'connectors','security':'security','security findings':'security',
    'history':'history','chat history':'history','plugins':'plugins','plugin center':'plugins',
    'settings':'settings','preferences':'settings','tools':'tools','activity':'activity',
    'activity center':'activity','voice':'voice','live action':'voice','artifacts':'artifacts',
}
COLORS={'purple':'#a855f7','violet':'#8b5cf6','blue':'#3b82f6','ice blue':'#7dd3fc',
        'cyan':'#22d3ee','red':'#ef4444','green':'#22c55e','orange':'#f97316',
        'yellow':'#eab308','pink':'#ec4899','white':'#ffffff'}


def object_schema(properties,required=()):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}


def appearance_schema():
    from ..ui_next.appearance_profile import AppearanceProfile,PRESETS
    fields={};defaults=AppearanceProfile().to_dict()
    enums={'preset':list(PRESETS),'density':['compact','comfortable','spacious'],
        'quality':['LOW','BALANCED','HIGH','ULTRA'],'cursor_glow':['OFF','MINIMAL','NORMAL','HIGH'],
        'particles':['OFF','LOW','NORMAL'],'field_palette':['STATE','CYAN','VIOLET','THEME']}
    ranges={'font_scale':(.8,1.8),'core_scale':(.5,1.5),'motion_speed':(.5,2),'radius':(0,32),'orbital_complexity':(1,6)}
    for key,value in defaults.items():
        if key=='schema':continue
        if key in enums:fields[key]={'type':'string','enum':enums[key]}
        elif type(value) is bool:fields[key]={'type':'boolean'}
        elif type(value) in (int,float):
            low,high=ranges.get(key,(0,1));fields[key]={'type':'integer' if type(value) is int else 'number','minimum':low,'maximum':high}
        elif key.endswith(('_accent','_tone')):fields[key]={'type':'string','pattern':'^(?:#[a-fA-F0-9]{6})?$','maxLength':7}
        else:fields[key]={'type':'string','maxLength':100}
    return object_schema(fields)


UI_CONTRACTS={
    'ui.preference':('Change a conversational preference',object_schema({
        'key':{'type':'string','enum':['precision','math_steps','presentation','auto_open','show_plan','automatic_model_selection','preferred_name','form_of_address','personal_memory_enabled','chat_memory_enabled','project_memory_enabled']},
        'value':{'anyOf':[{'type':'boolean'},{'type':'string','maxLength':80}],
            'description':'For presentation use auto, compact, detailed, visual or technical. Flags use a boolean. Names use plain text.'}},('key','value')),('Use compact responses','Turn off precision mode','Call me Alex','Show plans for complex requests','Change response presentation to technical'),
        'Validated existing Settings controls','Actual preference owner and persisted Settings value are reread.'),
    'ui.undo_appearance':('Undo the last appearance change',object_schema({}),('Undo that appearance change','Revert the last theme change'),
        'ThemeEngine revision-checked restore','Restore is allowed only if the theme still matches that action; actual saved profile is reread.'),
    'ui.navigate':('Open MORICE workspace',object_schema({'route':{'type':'string','enum':list(ROUTES)}},('route',)),
        ('Open Settings','Take me to Research Lab','Show the media queue','Go back to Chat'),'Native workspace navigation','Visible route and selected page match the requested workspace.'),
    'ui.settings':('Open a settings category',object_schema({'category':{'type':'string','maxLength':80,
        'enum':['Appearance','Profiles','Personalization','Models','Permissions & control','Memory','Voice','Wake','Desktop pet','Workspace']}},('category',)),
        ('Show memory settings','Open Appearance Lab','Open automation permissions'),'Settings category selection','Actual selected Settings category and page are reread.'),
    'ui.appearance':('Change MORICE appearance',object_schema({'changes':appearance_schema(),'relative':object_schema({key:{'type':'number','minimum':-1,'maximum':1} for key in ('glow','font_scale','core_scale')})}),
        ('Make the interface purple','Turn down the glow','Reduce particles','Enable Reduced Motion'),'Central ThemeEngine controls','Validated theme state and persisted appearance are independently reread.'),
    'ui.window':('Control the MORICE window',object_schema({'action':{'type':'string','enum':['maximize','minimize','restore','focus_chat','resize','monitor']},
        'width':{'type':'integer','minimum':720,'maximum':7680},'height':{'type':'integer','minimum':500,'maximum':4320},
        'monitor':{'type':'integer','minimum':0,'maximum':15}},('action',)),
        ('Maximize MORICE','Minimize MORICE','Focus chat','Move MORICE to the second monitor'),'Native MORICE window controls','Actual Qt window state, geometry, focus or screen is reread.'),
}


class NaturalLanguageController:
    def __init__(self,runtime):
        self.runtime=runtime;self.kernel=runtime.kernel
        self._ports={};self._lock=threading.RLock();self.last_resolution={}
        self._pending={}
        self._register_ui()
        from .domains import register_domains
        register_domains(self)
        from .workspace_domains import register_workspace_domains
        register_workspace_domains(self)
        from .control_domains import register_control_domains
        register_control_domains(self)
        from .connected_domains import register_connected_domains
        register_connected_domains(self)
        from .history_domains import register_history_domains
        register_history_domains(self)
        from .spatial_domain import register_spatial_domain
        register_spatial_domain(self)
        from .response_domain import register_response_domain
        register_response_domain(self)
        from .device_security_domains import register_device_security
        register_device_security(self)

    def attach_window(self,port):
        with self._lock:self._ports[port.window_id]=weakref.ref(port)

    def detach_window(self,window_id):
        with self._lock:self._ports.pop(window_id,None)

    def _port(self,context):
        with self._lock:reference=self._ports.get(context.active_window)
        port=reference() if reference else None
        if port is None:raise RuntimeError('The target MORICE window is no longer available.')
        return port

    def _register_ui(self):
        for identifier,(title,schema,intents,ui_action,contract) in UI_CONTRACTS.items():
            if self.kernel.registry.lookup(identifier):continue
            def execute(arguments,context,cid=identifier):
                output=self._port(context).execute(cid,arguments,context)
                return ExecutionResult(TaskStatus.SUCCEEDED,True,output,verification_required=True)
            def verify(result,expected,context,cid=identifier):
                arguments=context.metadata['task_inputs']
                valid=self._port(context).verify(cid,arguments,result.output,context)
                return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
                    ('Requested native UI state and current saved state were independently read.',) if valid else (),
                    '' if valid else 'The requested MORICE UI state was not observed.')
            self.kernel.registry.register(CapabilityDescriptor(identifier,title,description=title,
                provider='morice-nlui',category='interface',input_schema=schema,
                supports_verification=True,supports_cancellation=True,inline=True,
                natural_language_intents=intents,ui_action=ui_action,verification_contract=contract,
                idempotent=identifier!='ui.appearance',undo_supported=identifier=='ui.appearance',
                failure_modes=('Window closed','Unsupported target','Invalid parameters','State changed before verification')),
                execute,verifier=verify)

    def catalog(self):
        return [descriptor.to_dict() for descriptor in self.kernel.registry.search()
            if descriptor.natural_language_intents]

    def semantic_candidate(self,text):
        """Only unresolved first-party imperative requests spend a model call."""
        clean=self._clean(text)
        return (len(clean)<=1500 and not re.search(r'\b(?:engineering audit|scientific audit|do not generate|explain why|derive|equations?)\b',clean)
            and bool(re.match(r'^(?:open|show|change|make|set|switch|compare|run|pause|cancel|export|list|find|reduce|increase|lower|raise|resize|focus|move|navigate|take|enable|disable|turn|prepare|create|resume)\b',clean))
            and bool(re.search(r'\b(?:morice|settings|workspace|theme|interface|accent|research|experiment|simulation|sweep|builder|media|generation|connector|automation|security|plugin|glow|particles|core|presentation|calculator|table|chart|assembly)\b',clean)))

    def propose(self,text,context,*,cancellation=None,model_id=''):
        """Use the configured shared model, then the existing WorkflowPlanner validator."""
        from ..agent_runtime.models import ModelBudget
        from ..agent_runtime.planner import WorkflowPlanner
        from ..kernel import CancellationToken
        def words_of(value):
            return {word[:-1] if len(word)>4 and word.endswith('s') else word for word in re.findall(r'\w+',value.casefold())}
        words=words_of(text)
        catalog=self.catalog()
        catalog.sort(key=lambda d:3*len(words & words_of(d['name']+' '+ ' '.join(d['natural_language_intents'])))+
            len(words & words_of(json.dumps(d['input_schema'],ensure_ascii=False))),reverse=True)
        selected=[];size=0
        for descriptor in catalog:
            value={k:descriptor[k] for k in ('capability_id','name','input_schema','natural_language_intents')}
            encoded=json.dumps(value,ensure_ascii=False)
            if size+len(encoded)>6500:continue
            selected.append(value);size+=len(encoded)
            if len(selected)>=10:break
        token=cancellation or CancellationToken()
        maximum=12 if re.search(r'\b(?:and|then)\b|;|[.!?]\s+\w',text,re.I) else 1
        prompt=('Convert the user request to registered first-party MORICE intent data. Return only JSON '
            '{"operations":[{"capability_id":"...","arguments":{}}],"question":""}. '
            'Use only the supplied catalog. Do not execute anything. Never invent target IDs, paths, parameters, permissions or results. '
            'Use current/latest/selected references when the user actually requests them. Ask one question with operations=[] if details are missing or no capability fits. '
            'When operations is nonempty, question must be empty. Permission grants are manual: open ui.settings category Permissions & control; never enable desktop control yourself. '
            'Response presentation uses ui.preference key presentation; appearance changes only theme/effects. Only change settings explicitly requested by the user.')
        packet={'user_request':str(text)[:4000],'catalog':selected,'active_route':context.route,
            'project_selected':bool(context.project_id),'research_notebook_selected':bool(context.research_project_id)}
        while selected and len(json.dumps({'task':prompt,'context_data':packet},ensure_ascii=False).encode('utf-8'))>10500:
            selected.pop()
        execution=ExecutionContext(conversation_id=context.conversation_id,active_window=context.window_id,
            cancellation_token=token,deadline=time.monotonic()+90,
            metadata={'packet':packet,'model_budget':ModelBudget(1,16000),
                'response_schema':WorkflowPlanner.intent_schema(selected,max_operations=maximum),
                'model_config':{'selected_model':model_id,'allow_fallback':False,'max_output_tokens':1024}})
        result=self.kernel.dispatch('agent.reason',{'prompt':prompt},execution)
        if not result.success:raise ValueError('; '.join(error.message for error in result.errors))
        if result.output['text'].lstrip().startswith('(MORICE)'):raise ValueError(result.output['text'][:1000])
        try:steps,question=WorkflowPlanner.capability_steps(result.output['text'],selected)
        except json.JSONDecodeError as exc:raise ValueError('The selected model returned invalid intent JSON. No action was run. Try a more specific request or another configured model.') from exc
        if len(steps)>maximum:raise ValueError('The model proposed extra operations for a single request. No action was run.')
        steps=[(cid,{**args,'request':text} if cid in {'nlui.research.prepare','nlui.project.propose','nlui.media.generate','nlui.media.transform','nlui.automation.control','nlui.spatial.command'} else args) for cid,args in steps]
        return IntentResolution(operations=tuple(Operation(cid,args) for cid,args in steps),
            question=question or ('' if steps else 'That request has no supported capability binding yet.'),route='semantic')

    def remember_semantic_question(self,text,question,context):
        with self._lock:self._pending[context.conversation_id]={
            'mode':'semantic','request_id':uuid.uuid4().hex,'request_text':str(text)[:4000],
            'question':str(question)[:1000],'choices':[],'expires':time.time()+900,'requires_reauthorization':True}

    @staticmethod
    def _clean(text):
        clean=' '.join(str(text or '').strip().casefold().split()).strip(' .!?')
        return re.sub(r'^(?:(?:morice[, ]+)|(?:please\s+)|(?:(?:can|could|would) you\s+)|(?:i(?: would)? (?:want|like) (?:you )?to\s+))+','',clean)

    def resolve(self,text,context:ActiveContext):
        clean=self._clean(text)
        if not clean or len(clean)>12000:return IntentResolution()
        # Resolve explicit sequences before greedy domain patterns can consume
        # the following action as a project name or part of a build goal.
        parts=re.split(r'\s*(?:;|\band then\b|\bthen\b)\s*(?=(?:[^"]*"[^"]*")*[^"]*$)',str(text),flags=re.I)
        if 1<len(parts)<=12:
            steps=[self.resolve(part.strip(' ,'),context) for part in parts]
            if all(step.operations and not step.question for step in steps):
                resolution=IntentResolution(operations=tuple(op for step in steps for op in step.operations),route='task_graph')
                self.last_resolution={'route':resolution.route,'capabilities':[o.capability_id for o in resolution.operations],'needs_clarification':False}
                return resolution
            return IntentResolution(question='One part of that sequence needs more detail. Send the actions separately so I can resolve their exact targets.',route='task_graph')
        from .spatial_domain import resolve_spatial
        resolution=resolve_spatial(clean,context)
        if not resolution.matched:
            from .response_domain import resolve_response
            resolution=resolve_response(clean,context,raw=text)
        if not resolution.matched:resolution=self._resolve_ui(clean,context)
        identity=re.fullmatch(r'\s*(?:please )?(call me|address me as|set my preferred name to) ([^\r\n.!?]{1,80})[.!?]?\s*',str(text),re.I)
        if identity:
            resolution=IntentResolution(operations=(Operation('ui.preference',{
                'key':'form_of_address' if identity[1].casefold()=='address me as' else 'preferred_name','value':identity[2].strip()}),),route='direct')
        if not resolution.matched:
            resolution=self._resume_pending(clean,context) or resolution
        if not resolution.matched:
            from .domains import resolve_domain
            resolution=resolve_domain(clean,context,raw=text)
        if not resolution.matched:
            from .workspace_domains import resolve_workspace
            resolution=resolve_workspace(clean,context,raw=text)
        if not resolution.matched:
            from ..media_lab.intents import route_media_intent
            if route_media_intent(text) is not None:
                resolution=IntentResolution(operations=(Operation('nlui.media.generate',{'request':text}),),route='domain')
        if not resolution.matched:
            from .control_domains import resolve_control
            resolution=resolve_control(clean,context,raw=text)
        if not resolution.matched:
            from .connected_domains import resolve_connected
            resolution=resolve_connected(clean,context)
        if not resolution.matched:
            from .history_domains import resolve_history
            resolution=resolve_history(clean,context)
        if not resolution.matched:
            from .device_security_domains import resolve_device_security
            resolution=resolve_device_security(clean,context)
        if not resolution.matched:
            parts=[p.strip(' ,') for p in re.split(r'\s*(?:;|\band then\b|\bthen\b|\band\b)\s*',clean) if p.strip(' ,')]
            if 1<len(parts)<=12:
                from .domains import resolve_domain
                steps=[]
                for part in parts:
                    step=resolve_spatial(part,context)
                    if not step.matched:
                        from .response_domain import resolve_response
                        step=resolve_response(part,context)
                    if not step.matched:step=self._resolve_ui(part,context)
                    if not step.matched:step=resolve_domain(part,context)
                    if not step.matched:
                        from .workspace_domains import resolve_workspace
                        step=resolve_workspace(part,context)
                    if not step.matched:
                        from .control_domains import resolve_control
                        step=resolve_control(part,context)
                    if not step.matched:
                        from .connected_domains import resolve_connected
                        step=resolve_connected(part,context)
                    if not step.matched:
                        from .history_domains import resolve_history
                        step=resolve_history(part,context)
                    if not step.matched:
                        from .device_security_domains import resolve_device_security
                        step=resolve_device_security(part,context)
                    steps.append(step)
                if all(step.operations and not step.question for step in steps):
                    resolution=IntentResolution(operations=tuple(operation for step in steps for operation in step.operations),route='task_graph')
        self.last_resolution={'route':resolution.route,'capabilities':[o.capability_id for o in resolution.operations],
            'needs_clarification':bool(resolution.question)}
        return resolution

    def restore_pending(self,conversation_id):
        value=self.runtime.chat_history.get_ui_state(conversation_id,'nlui_pending')
        if isinstance(value,dict) and value.get('expires',0)>time.time():
            if (value.get('mode')=='semantic' and isinstance(value.get('request_text'),str)
                    and len(value['request_text'])<=4000 and isinstance(value.get('question'),str)
                    and isinstance(value.get('request_id'),str)):
                value=dict(value);value['question_turn_key']=''
                with self._lock:self._pending[conversation_id]=value
                return
            operations=value.get('operations')
            choices=value.get('choices');slot=value.get('slot')
            if (isinstance(choices,list) and 0<len(choices)<=20 and all(isinstance(c,dict)
                    and isinstance(c.get('id'),str) and isinstance(c.get('label'),str) for c in choices)
                    and isinstance(value.get('question'),str) and isinstance(value.get('request_id'),str)
                    and slot in {'reference','project_reference','first','second','choice','device_reference','artifact'}
                    and isinstance(operations,list) and 0<len(operations)<=12 and all(isinstance(o,dict)
                    and o.get('capability_id') in {d.capability_id for d in self.kernel.registry.search(provider='morice-nlui-domain')}
                    and isinstance(o.get('arguments'),dict) for o in operations)):
                value=dict(value);value['question_turn_key']=''
                with self._lock:self._pending[conversation_id]=value

    def commit_pending(self,context,*,persist=True):
        with self._lock:
            value=self._pending.get(context.conversation_id)
            if value is None:
                if persist:self.runtime.chat_history.clear_ui_state(context.conversation_id,'nlui_pending')
                return
            value['question_turn_key']=context.last_turn_key
            snapshot=dict(value)
        if persist:self.runtime.chat_history.put_ui_state(context.conversation_id,'nlui_pending',snapshot,expires=value['expires'])

    def _resume_pending(self,clean,context):
        with self._lock:value=self._pending.get(context.conversation_id)
        if not value:return None
        if value.get('expires',0)<=time.time():
            with self._lock:self._pending.pop(context.conversation_id,None)
            return None
        if clean in {'resume pending request','continue that request','resume that request','continue pending request'}:
            choices='\n'.join(f'{i+1}. {choice["label"]}' for i,choice in enumerate(value['choices']))
            return IntentResolution(request_id=value['request_id'],question=value['question']+'\n'+choices,choices=tuple(value.get('choices',())),route='clarification')
        if value.get('question_turn_key')!=context.last_turn_key:return None
        if clean in {'cancel pending request','forget that request','never mind'}:
            with self._lock:self._pending.pop(context.conversation_id,None)
            return IntentResolution(question='Pending request cancelled.',route='clarification')
        if value.get('mode')=='semantic':
            return IntentResolution(route='semantic_pending',context_request=(value['request_text']+'\nMORICE asked: '+value['question']+'\nUser clarification: '+clean)[:6000],
                # A nonempty question marks a routed clarification, not authority.
                question='Resolving your clarification.')
        choices=value.get('choices',[]);answer=None
        ordinals={'first':0,'one':0,'1':0,'second':1,'two':1,'2':1,'third':2,'three':2,'3':2}
        candidate=re.sub(r'^(?:the |choose |select |use |open )','',clean)
        if candidate in ordinals and ordinals[candidate]<len(choices):answer=choices[ordinals[candidate]]['id']
        else:
            matches=[c for c in choices if candidate in {str(c['id']).casefold(),str(c['label']).casefold()}]
            if len(matches)==1:answer=matches[0]['id']
        if answer is None:return None
        operations=[Operation(o['capability_id'],dict(o['arguments'])) for o in value['operations']]
        first=operations[0]
        operations[0]=Operation(first.capability_id,{**first.arguments,value['slot']:answer})
        with self._lock:self._pending.pop(context.conversation_id,None)
        return IntentResolution(request_id=value['request_id'],operations=tuple(operations),route='continuation')

    def _resolve_ui(self,clean,context):
        memory=re.fullmatch(r'(?:turn (on|off)|(enable|disable)) (personal memory|current[ -]chat memory|project memory)',clean)
        if memory:
            key={'personal memory':'personal_memory_enabled','current-chat memory':'chat_memory_enabled','current chat memory':'chat_memory_enabled','project memory':'project_memory_enabled'}[memory[3]]
            return IntentResolution(operations=(Operation('ui.preference',{'key':key,'value':memory[1]=='on' or memory[2]=='enable'}),),route='direct')
        if clean in {'undo that appearance change','undo the last appearance change','revert the last theme change'}:
            return IntentResolution(operations=(Operation('ui.undo_appearance'),),route='direct')
        preference=re.fullmatch(r'(?:use|switch to|set) (auto|compact|detailed|visual|technical) (?:responses|replies|presentation)',clean)
        if preference is None:
            match=re.fullmatch(r'(?:change|set|switch) (?:the )?(?:response |reply )?presentation to (auto|compact|detailed|visual|technical)',clean)
            preference=match
        if preference:return IntentResolution(operations=(Operation('ui.preference',{'key':'presentation','value':preference[1]}),),route='direct')
        flag=re.fullmatch(r'(?:turn (on|off)|(enable|disable)) (precision(?: mode)?|math steps|plans for complex requests|automatic model selection)',clean)
        if flag:
            key={'precision':'precision','precision mode':'precision','math steps':'math_steps','plans for complex requests':'show_plan','automatic model selection':'automatic_model_selection'}[flag[3]]
            return IntentResolution(operations=(Operation('ui.preference',{'key':key,'value':flag[1]=='on' or flag[2]=='enable'}),),route='direct')
        if re.fullmatch(r'(?:enable|turn on|allow) (?:full )?desktop automation(?: (?:permission|control))?(?: for morice)?(?: without (?:asking|confirmation))?',clean):
            return IntentResolution(operations=(Operation('ui.settings',{'category':'Permissions & control'}),),
                question='Turn on Desktop automation here, then send your request again. MORICE cannot grant this permission to itself.',route='direct')
        settings=re.fullmatch(r'(?:open|show|go to|take me to) (?:the )?(memory|model|models|voice|wake|appearance|appearance lab|automation|permission|permissions|desktop automation)(?: settings| options)?',clean)
        if settings:
            if settings[1]=='automation':
                return IntentResolution(operations=(Operation('ui.navigate',{'route':'automations'}),),route='direct')
            name={'model':'Models','models':'Models','voice':'Voice','wake':'Wake','memory':'Memory',
                'appearance':'Appearance','appearance lab':'Appearance','automation':'Permissions & control',
                'permission':'Permissions & control','permissions':'Permissions & control','desktop automation':'Permissions & control'}[settings[1]]
            return IntentResolution(operations=(Operation('ui.settings',{'category':name}),),route='direct')
        nav=re.fullmatch(r'(?:open|show|switch to|go to|go back to|take me to|let\'?s go to)(?: the| my)? (.+)',clean)
        target=nav[1] if nav else 'home' if clean in {'take me home','go home','back to core'} else ''
        if target in ROUTE_ALIASES:
            return IntentResolution(operations=(Operation('ui.navigate',{'route':ROUTE_ALIASES[target]}),),route='direct')
        if clean in {'show what morice is working on','show me what morice is currently working on','what are you working on'}:
            return IntentResolution(operations=(Operation('ui.navigate',{'route':'activity'}),),route='direct')
        if clean in {'focus chat','focus the chat','focus the composer'}:
            return IntentResolution(operations=(Operation('ui.window',{'action':'focus_chat'}),),route='direct')
        window=re.fullmatch(r'(maximize|minimize|restore) (?:the )?(?:morice|morice window|this window)',clean)
        if window:return IntentResolution(operations=(Operation('ui.window',{'action':window[1]}),),route='direct')
        resize=re.fullmatch(r'(?:resize|make) (?:the )?morice(?: window)? (?:to )?(\d{3,4})\s*(?:x|by|×)\s*(\d{3,4})(?: pixels)?',clean)
        if resize:return IntentResolution(operations=(Operation('ui.window',{'action':'resize','width':int(resize[1]),'height':int(resize[2])}),),route='direct')
        monitor=re.fullmatch(r'move morice(?: window)? to (?:the )?(first|second|third|\d+) monitor',clean)
        if monitor:
            index={'first':0,'second':1,'third':2}.get(monitor[1],int(monitor[1])-1 if monitor[1].isdigit() else -1)
            return IntentResolution(operations=(Operation('ui.window',{'action':'monitor','monitor':index}),),route='direct')
        changes={};relative={}
        color=re.fullmatch(r'(?:(?:make|change|set|switch|turn) (?:the )?(?:ui|interface|accent|primary colou?r|primary colou?r accent)(?: colou?r)?(?: to)?|use) (.+?)(?: as (?:the )?(?:primary )?accent)?',clean)
        if color is None:color=re.fullmatch(r'(?:switch to|use) (.+?)(?: as (?:the )?(?:primary )?accent)?',clean)
        if color and (color[1] in COLORS or re.fullmatch(r'#[0-9a-f]{6}',color[1])):
            changes['primary_accent']=COLORS.get(color[1],color[1])
        theme=re.fullmatch(r'(?:set|change|switch|use) (?:the )?theme(?: to)? (.+)',clean)
        if theme:
            preset={'ice blue':'ICE','purple':'AMETHYST','violet':'AMETHYST','default':'MORICE'}.get(theme[1],theme[1].upper())
            if preset in {'MORICE','GLASS','OBSIDIAN','ICE','AMETHYST','MIDNIGHT','NEON','MONOCHROME','CUSTOM','ARCTIC','SOLAR','CRIMSON'}:changes['preset']=preset
        if re.fullmatch(r'(?:turn off|disable|stop) (?:the )?particles',clean):changes['particles']='OFF'
        if re.fullmatch(r'(?:reduce|turn down|use less|decrease) (?:the )?particles',clean):changes['particles']='LOW'
        if re.fullmatch(r'(?:enable|turn on|use) reduced motion',clean):changes['reduced_motion']=True
        if re.fullmatch(r'(?:disable|turn off) reduced motion',clean):changes['reduced_motion']=False
        if re.fullmatch(r'(?:disable|turn off) (?:the )?cursor trails?',clean):changes['cursor_trail']=False
        if re.fullmatch(r'(?:use low effects(?: while gaming)?|turn down background effects|reduce background effects)',clean):changes['quality']='LOW'
        if re.fullmatch(r'(?:make|increase) (?:the )?text (?:larger|bigger)',clean):relative['font_scale']=.1
        if re.fullmatch(r'(?:increase|turn up|raise) (?:the )?glow',clean):relative['glow']=.15
        if re.fullmatch(r'(?:reduce|turn down|decrease|lower) (?:the )?glow',clean):relative['glow']=-.15
        if re.fullmatch(r'(?:make|reduce) (?:the )?core smaller',clean):relative['core_scale']=-.1
        if re.fullmatch(r'(?:make|increase) (?:the )?core (?:larger|bigger)',clean):relative['core_scale']=.1
        numeric=re.fullmatch(r'(?:set|change) (?:the )?(glow|glass|blur|font scale|core size|motion strength|animation speed|corner radius|field intensity|core brightness)(?: to)? (\d+(?:\.\d+)?)(%)?',clean)
        if numeric:
            key={'font scale':'font_scale','core size':'core_scale','motion strength':'motion_strength','animation speed':'motion_speed',
                'corner radius':'radius','field intensity':'field_intensity','core brightness':'core_brightness'}.get(numeric[1],numeric[1])
            value=float(numeric[2])/(100 if numeric[3] else 1)
            changes[key]=int(value) if key=='radius' and value.is_integer() else value
        density=re.fullmatch(r'(?:use|set|switch to) (compact|comfortable|spacious) (?:ui|layout|density)',clean)
        if density:changes['density']=density[1]
        if changes or relative:
            return IntentResolution(operations=(Operation('ui.appearance',{'changes':changes,'relative':relative}),),route='direct')
        return IntentResolution()

    def execute(self,resolution,context:ActiveContext,*,cancellation=None,progress=None):
        execution_context=ExecutionContext(conversation_id=context.conversation_id,active_window=context.window_id,
            project_id=context.project_id,research_project_id=context.research_project_id,
            user_request_id=resolution.request_id,cancellation_token=cancellation,progress=progress,
            metadata={'nlui':{'research_project_id':context.research_project_id,'project_id':context.project_id,
                'selected':list(context.selected),'conversation_id':context.conversation_id,'route':context.route}})
        nodes=[]
        for operation in resolution.operations:
            node=TaskNode(operation.capability_id,dict(operation.arguments),dependencies=(nodes[-1].task_id,) if nodes else (),
                verification_policy=VerificationPolicy(required=True))
            if (nodes and nodes[-1].capability_requirement=='nlui.project.check' and nodes[-1].inputs.get('action')=='test'
                    and operation.capability_id=='nlui.project.propose' and re.match(r'^(?:fix|repair)\b',self._clean(operation.arguments.get('request','')))):
                node.dependency_policy=DependencyPolicy.COMPLETED
                execution_context.metadata['nlui'].setdefault('repair_after_test',{})[node.task_id]=nodes[-1].task_id
            nodes.append(node)
        graph=TaskGraph(tuple(nodes),graph_id=resolution.request_id,goal='Natural-language request')
        result=self.kernel.run_graph(graph,execution_context)
        executions=tuple(n.result.to_dict() for n in result.tasks if n.result)
        for index,node in enumerate(result.tasks):
            if node.result and isinstance(node.result.output,dict) and node.result.output.get('clarification'):
                asked=node.result.output['clarification']
                remaining=list(resolution.operations[index:])
                if asked.get('arguments'):
                    first=remaining[0];remaining[0]=Operation(first.capability_id,{**first.arguments,**asked['arguments']})
                with self._lock:self._pending[context.conversation_id]={
                    'request_id':resolution.request_id,'question':asked['question'],'choices':asked['choices'],
                    'slot':asked['slot'],'expires':time.time()+900,'requires_reauthorization':True,
                    'operations':[{'capability_id':o.capability_id,'arguments':o.arguments} for o in remaining]}
                choices='\n'.join(f'{i+1}. {choice["label"]}' for i,choice in enumerate(asked['choices']))
                return NaturalLanguageResult(resolution.request_id,'awaiting_input',asked['question']+('\n'+choices if choices else ''),executions)
        if result.success:
            with self._lock:self._pending.pop(context.conversation_id,None)
            messages=[str(n.result.output.get('message','')) for n in result.tasks if n.result and isinstance(n.result.output,dict)]
            return NaturalLanguageResult(resolution.request_id,'completed','\n'.join(m for m in messages if m),executions)
        completed=[n for n in result.tasks if n.result and n.result.success]
        errors=[e.message+(' '+e.detail if e.detail and e.message=='Capability execution failed.' else '') for n in result.tasks if n.result for e in n.result.errors]
        status='cancelled' if cancellation and cancellation.cancelled else 'partial' if completed else 'failed'
        completed_messages=[str(n.result.output.get('message','')) for n in completed if isinstance(n.result.output,dict)]
        message='\n'.join(completed_messages+['; '.join(errors) or 'The request could not be completed.'])
        return NaturalLanguageResult(resolution.request_id,status,message,executions)
