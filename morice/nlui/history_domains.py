"""Chat metadata and saved preferences use the existing history/memory owners."""
from __future__ import annotations

from dataclasses import asdict
import re

from ..kernel import CapabilityDescriptor,ErrorCode,ExecutionResult,VerificationResult,VerificationStatus
from .contracts import IntentResolution,Operation
from .domains import schema,success,clarification
from .references import select_target


def history_handler(controller,args,context):
    history=controller.runtime.chat_history
    rows=[{**r,'title':r['name'],'updated':r['created'] if args.get('reference') in {'oldest','first'} else r['last_used']}
        for r in history.search('',limit=1000)]
    if args['action']=='find':
        query=args.get('query','');found=history.search_transcripts(query,exclude_chat=context.conversation_id,limit=20)
        return success(f'Found {len(found)} matching saved conversation(s), with up to 20 shown. Session-private chats and the current chat are excluded. Use History → Rebuild index if older conversations are missing.',
            chats=found,query=query,provenance='USER_DATA')
    chosen=select_target(args.get('reference','current'),rows,active_id=context.conversation_id,kind='conversation')
    if chosen.record is None:return clarification(chosen.question,chosen.choices)
    identifier=chosen.record['id']
    controller._port(context).execute('history.open',{'chat_id':identifier},context)
    return success('Opened the selected saved conversation.',chat_id=identifier,provenance='USER_DATA')


def verify_history(controller,result,context):
    value=result.output
    valid=controller._port(context).verify('history.open',{'chat_id':value['chat_id']},value,context) if 'chat_id' in value else False
    # Metadata existence is reread without decompressing unrelated chats.
    if 'chats' in value:
        history=controller.runtime.chat_history
        actual={r['id'] for r in history.metadata([r['id'] for r in value['chats']]) if r['retention']!='session'}
        valid=all(row['id'] in actual and history.fetch_message(row['id'],row['matching_message_id']) is not None for row in value['chats'])
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Actual selected conversation or saved chat metadata independently reread.',) if valid else ())


def memory_handler(controller,args,context):
    memory=controller.runtime.desktop.memory
    rows=[asdict(row) for row in memory.list_preferences(args.get('query',''))][:200]
    return success(f'{len(rows)} saved preference record(s). Only approved, relevant, enabled preferences are applied.',
        preferences=rows,provenance='USER_DATA')


def verify_memory(controller,result,context):
    actual={row.memory_id:row.content for row in controller.runtime.desktop.memory.list_preferences()}
    valid=all(actual.get(row['memory_id'])==row['content'] for row in result.output['preferences'])
    return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,
        ('Saved preference identities/content independently reread; no permission state is derived from memory.',) if valid else ())


def register_history_domains(controller):
    for identifier,title,input_schema,intents,handler,verifier in (
        ('nlui.history.control','Find or reopen saved conversations',{'type':'object','required':['action'],'properties':{
            'action':{'type':'string','enum':['find','open']},'query':{'type':'string','maxLength':200},'reference':{'type':'string','maxLength':500}},'additionalProperties':False},
            ('Open our oldest conversation','Find the chat about the UI'),history_handler,verify_history),
        ('nlui.memory.list','Show saved preferences',schema('query'),('Show my saved preferences','Search my personal preferences'),memory_handler,verify_memory)):
        controller.kernel.registry.register(CapabilityDescriptor(identifier,title,provider='morice-nlui-domain',category='memory',
            input_schema=input_schema,idempotent=True,supports_verification=True,supports_cancellation=True,natural_language_intents=intents,
            ui_action='Existing ChatHistory and MemoryManager',verification_contract='Fresh stable-ID metadata/content read; no cross-chat transcript injection.'),
            lambda args,ctx,h=handler:h(controller,args,ctx),verifier=lambda result,expected,ctx,v=verifier:v(controller,result,ctx))


def resolve_history(clean,context):
    if clean in {'show my saved preferences','show saved preferences','list my preferences','show my personal memory'}:
        return IntentResolution(operations=(Operation('nlui.memory.list'),),route='domain')
    match=re.fullmatch(r'(?:open|show|resume) (?:our |my |the )?(oldest|first|latest|last|previous) (?:conversation|chat)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.history.control',{'action':'open','reference':match[1]}),),route='domain')
    match=re.fullmatch(r'find (?:the |our |my )?chat (?:where we discussed|about) (.+)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.history.control',{'action':'find','query':match[1]}),),route='domain')
    match=re.fullmatch(r'(?:open|resume) (?:our |my |the )?(.{1,160}) (?:chat|conversation)',clean)
    if match:return IntentResolution(operations=(Operation('nlui.history.control',{'action':'open','reference':match[1]}),),route='domain')
    return IntentResolution()
