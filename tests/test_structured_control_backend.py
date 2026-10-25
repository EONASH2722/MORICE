"""Structured control uses the existing streaming transports; plain chat stays plain."""
from morice import llm_client,local_llama
from morice.agent_runtime.planner import WorkflowPlanner
from morice.nlui.runtime import UI_CONTRACTS


def test_selected_catalog_schema_requires_real_argument_nesting_and_no_extra_fields():
    schema=WorkflowPlanner.intent_schema([{'capability_id':'ui.appearance','input_schema':UI_CONTRACTS['ui.appearance'][1]}])
    operation=schema['properties']['operations']['items']['anyOf'][0]
    assert operation['additionalProperties'] is False
    assert operation['properties']['capability_id']=={'const':'ui.appearance'}
    assert 'particles' not in operation['properties']['arguments']['properties']
    assert operation['properties']['arguments']['properties']['changes']['properties']['particles']['enum']==['OFF','LOW','NORMAL']
    colors=operation['properties']['arguments']['properties']['changes']['properties']
    assert colors['primary_accent']['pattern'].startswith('^') and colors['primary_accent']['pattern'].endswith('$')


def test_existing_gguf_stream_receives_schema_only_for_structured_request(tmp_path,monkeypatch):
    model=tmp_path/'owned.gguf';model.write_bytes(b'GGUF');captured=[]
    monkeypatch.setattr(llm_client,'ensure_server',lambda *args:'http://owned-fixture')
    monkeypatch.setattr(llm_client,'_fit_backend_context',lambda url,messages,max_tokens,**kwargs:messages)
    def stream(url,payload,*args,**kwargs):captured.append(payload);yield '{}'
    monkeypatch.setattr(llm_client,'_try_openai_chat_stream',stream)
    schema={'type':'object','properties':{'value':{'type':'boolean'}},'required':['value'],'additionalProperties':False}
    assert ''.join(llm_client.stream_chat([],'Owned request',gguf_path=str(model),response_schema=schema))=='{}'
    assert captured[-1]['response_format']=={'type':'json_object','schema':schema} and captured[-1]['temperature']==0
    ''.join(llm_client.stream_chat([],'Ordinary conversation',gguf_path=str(model)))
    assert 'response_format' not in captured[-1]
    ''.join(llm_client.stream_chat([],'Owned intent packet',gguf_path=str(model),response_schema=schema,intent_mode=True,extra_system='Return only typed intent JSON.'))
    assert captured[-1]['messages']==[{'role':'system','content':'Return only typed intent JSON.'},{'role':'user','content':'Owned intent packet'}]


def test_existing_local_python_and_ollama_streams_receive_same_host_schema(monkeypatch):
    captured={};schema={'type':'object','properties':{'value':{'type':'boolean'}}}
    class Model:
        def create_chat_completion(self,**kwargs):captured.update(kwargs);return iter([{'choices':[{'delta':{'content':'{}'}}]}])
    monkeypatch.setattr(local_llama,'_get_llm',lambda *args:Model())
    assert ''.join(local_llama.stream_chat([],'owned.gguf',2048,0,None,2,128,0,.8,response_schema=schema))=='{}'
    assert captured['response_format']=={'type':'json_object','schema':schema}
    def events(url,payload,*args):captured.clear();captured.update(payload);yield {'message':{'content':'{}'}}
    monkeypatch.setattr(llm_client,'_post_stream_json',events)
    assert ''.join(llm_client._try_ollama_messages_stream('http://owned',[],'owned',10,0,.8,response_schema=schema))=='{}'
    assert captured['format']==schema and captured['stream'] is True
