from unittest.mock import patch
import pytest

from morice.thinking import LEVELS,REASONING_TOKENS,reasoning_tokens,output_tokens,normalize_thinking_level
from morice import llm_client,settings


@pytest.mark.parametrize('level',LEVELS)
def test_selected_level_reaches_actual_local_backend_payload(level):
    payloads=[]
    def stream(url,payload,timeout,cancel_event=None):
        payloads.append(payload);yield 'Owned response'
    with patch.object(llm_client,'DEFAULT_USE_SERVER',True),patch.object(llm_client,'_resolve_gguf_path',return_value='owned.gguf'),\
        patch.object(llm_client,'ensure_server',return_value='http://local'),\
        patch.object(llm_client,'_fit_backend_context',side_effect=lambda url,messages,*args,**kwargs:messages),\
        patch.object(llm_client,'_try_openai_chat_stream',side_effect=stream):
        assert ''.join(llm_client.stream_chat([], 'Owned calculation request',enable_reasoning=True,
            max_tokens=8192,context_tokens=16384,thinking_level=level))=='Owned response'
    assert payloads[0]['reasoning_budget_tokens']==REASONING_TOKENS[level]
    assert payloads[0]['chat_template_kwargs']['enable_thinking']
    assert payloads[0]['max_tokens']==8192


def test_effort_keeps_answer_room_and_validates_saved_values(tmp_path,monkeypatch):
    assert normalize_thinking_level('Extra high')=='extra_high'
    assert normalize_thinking_level('unlimited')=='low'
    assert reasoning_tokens('extra_high',1536)==512
    assert output_tokens('extra_high',2048,4096)==4096-768
    monkeypatch.setattr(settings,'_settings_dir',lambda:str(tmp_path))
    settings.save_settings({**settings.DEFAULT_SETTINGS,'thinking_level':'high'})
    assert settings.load_settings()['thinking_level']=='high'


def test_fast_generation_remains_non_reasoning_even_with_an_effort_value():
    assert [reasoning_tokens(x,8192) for x in LEVELS]==[256,1024,2048,4096]
