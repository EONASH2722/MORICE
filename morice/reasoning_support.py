"""Bounded goal/prerequisite context for practical choices; no action execution."""
import json,re
from dataclasses import dataclass

@dataclass(frozen=True)
class GoalContext:
    text:str=''
    verdict:str=''
    def __bool__(self):return bool(self.text)

def needs_prerequisites(text):
    if re.match(r'^\s*(?:translate|rewrite|proofread|quote|classify|summari[sz]e)\b',str(text),re.I):return False
    return bool(re.search(r'\b(?:(?:should|do) i\b[^?\n]{0,160}\bor\b|physical.world assumptions|but if\b)',str(text),re.I))

SCHEMA={'type':'object','properties':{'goal':{'type':'string'},'required_objects':{'type':'array','items':{'type':'string'}},
    'already_at_destination':{'type':'array','items':{'type':'string'}},'physical_prerequisites':{'type':'array','items':{'type':'string'}},
    'options':{'type':'array','items':{'type':'object','properties':{'action':{'type':'string'},'moves_to_destination':{'type':'array','items':{'type':'string'}}},'required':['action','moves_to_destination'],'additionalProperties':False}},
    'uncertainties':{'type':'array','items':{'type':'string'}}},
    'required':['goal','required_objects','already_at_destination','physical_prerequisites','options','uncertainties'],'additionalProperties':False}

def stated_goal(history,request):
    candidates=[request,*[row.get('content','') for row in reversed(history) if row.get('role')=='user']]
    for candidate in candidates:
        match=re.search(r'\bI (?:need|want|have|plan|intend|am trying|would like) to\b[^.!?\n]{1,300}',str(candidate),re.I)
        if match:return match.group(0)
    return ''

def feasible_options(value):
    required=set(value['required_objects']);already=set(value['already_at_destination'])
    if not already<=required:raise ValueError('Unknown prerequisite object.')
    rows=[]
    for option in value['options']:
        if not isinstance(option,dict) or set(option)!={'action','moves_to_destination'} or not isinstance(option['action'],str) or len(option['action'])>300:raise ValueError('Invalid option.')
        moved=option['moves_to_destination']
        if not isinstance(moved,list) or len(moved)>12 or any(not isinstance(item,str) or len(item)>600 for item in moved):raise ValueError('Invalid moved object.')
        missing=sorted(required-already-set(moved))
        rows.append({'action':option['action'],'missing_required_objects':missing,'satisfies_stated_transport_prerequisites':not missing})
    return rows

def prerequisites(history,request,selection,stream_function,*,cancel_event=None,context_tokens=16384):
    if cancel_event is not None and cancel_event.is_set():return GoalContext()
    instruction=("Extract the user's underlying task and its physical prerequisites. Do not replace that task with minimizing travel time. Do not recommend an option yet. "
        "Identify the object that must be processed, repaired, collected or otherwise acted on, and where that object must physically be. "
        "Distinguish the person's location from the object's location. Do not assume that an object is already at a destination unless "
        "the user states it, and do not invent pickup or delivery services. Earlier assistant advice may be wrong. "
        "required_objects must list only movable people/items that have to be at the task destination, never the destination itself. "
        "Use exactly the same object names throughout the JSON. For each option state what it physically moves to that destination; "
        "a person's arrival does not automatically transport a separate object. already_at_destination may contain only objects the user explicitly places there. "
        "Return only the requested JSON fields; uncertainties must distinguish missing information from stated facts.")
    goal=stated_goal(history,request)
    if goal:instruction+=' The explicit user goal to preserve is: '+json.dumps(goal)+'.'
    pieces=[];size=0
    for delta in stream_function(history,request,model=selection.get('name') or None,gguf_path=selection.get('path',''),
        extra_system=instruction,response_schema=SCHEMA,max_tokens=768,context_tokens=context_tokens,enable_reasoning=False,
        timeout=30,cancel_event=cancel_event,precision_mode=True):
        if cancel_event is not None and cancel_event.is_set():return GoalContext()
        size+=len(str(delta))
        if size>8000:return GoalContext()
        pieces.append(str(delta))
    try:
        value=json.loads(''.join(pieces))
        if not isinstance(value,dict) or set(value)!=set(SCHEMA['properties']) or not isinstance(value['goal'],str):return GoalContext()
        if any(not isinstance(value[key],list) or len(value[key])>12 or any(not isinstance(item,str) or len(item)>600 for item in value[key]) for key in ('required_objects','already_at_destination','physical_prerequisites','uncertainties')):return GoalContext()
        if not isinstance(value['options'],list) or not 1<=len(value['options'])<=6:return GoalContext()
        if len(value['goal'])>1000:return GoalContext()
        checks=feasible_options(value)
        if goal:value['goal']=goal
        context=('Model-generated goal/prerequisite context (not verified evidence):\n'+json.dumps(value,ensure_ascii=False)+
            '\nHost set-membership check over those model-supplied objects (not verification of the inferred facts):\n'+json.dumps(checks,ensure_ascii=False)+
            '\nReject options with missing required objects: they cannot accomplish the underlying task under these assumptions. Do not invent services, locations or speeds. Explain the actual prerequisite rather than making up travel calculations. Correct prior advice when it fails the goal; keep the requested answer format.')
        feasible=[row for row in checks if row['satisfies_stated_transport_prerequisites']]
        rejected=[row for row in checks if row['missing_required_objects']]
        verdict=''
        # A narrow, physically grounded binary choice can be stated directly
        # from the checked object movements. Do not let fluent prose reverse it.
        if goal and len(checks)==2 and len(feasible)==1 and rejected and value['physical_prerequisites'] and not re.search(r'\b(?:translate|json|poem|essay|words?|paragraphs?|in (?:french|german|hindi|tamil|spanish))\b',request,re.I):
            action=feasible[0]['action'];other=rejected[0];missing=', '.join(other['missing_required_objects'])
            prerequisite=value['physical_prerequisites'][0].rstrip(' .')
            verdict=action[:1].upper()+action[1:]+': '+prerequisite+'. '+other['action'][:1].upper()+other['action'][1:]+' leaves '+missing+' behind, so it cannot accomplish the stated goal.'
        return GoalContext(context,verdict)
    except (ValueError,TypeError):return GoalContext()
