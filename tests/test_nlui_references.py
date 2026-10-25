import pytest

from morice.nlui.references import select_target
from morice.research.history import ChatHistory


def test_named_current_temporal_and_missing_targets_use_actual_records():
    records=[{'id':'a','objective':'Energy notebook','updated':'2026-10-24T10:00:00+00:00'},
             {'id':'b','objective':'Energy redesign','updated':'2026-10-25T10:00:00+00:00'},
             {'id':'c','objective':'Unrelated notebook','updated':'2026-10-25T11:00:00+00:00'}]
    assert select_target('latest Energy',records).record['id']=='b'
    assert select_target('original',records).record['id']=='a'
    assert select_target('that',records,active_id='a').record['id']=='a'
    assert select_target('not present',records).record is None
    ambiguous=select_target('Energy',records)
    assert ambiguous.record is None and {c['id'] for c in ambiguous.choices}=={'a','b'}


def test_timestamp_ties_missing_dates_and_previous_are_not_guessed():
    records=[{'id':'a','name':'First','updated':10},{'id':'b','name':'Second','updated':10}]
    assert select_target('latest',records).record is None
    assert select_target('previous',records).record is None
    assert select_target('latest',[{'id':'a','name':'Unknown date'}]).record is None


def test_pending_and_presentation_state_share_chat_retention_and_scope(tmp_path):
    history=ChatHistory(tmp_path/'knowledge.db')
    history.save('first',[{'role':'user','content':'Open my project.'}],merge=True)
    history.save('other',[{'role':'user','content':'Unrelated.'}],merge=True)
    pending={'request_id':'request','question_turn_key':'message','requires_reauthorization':True,
             'choices':[{'id':'a','label':'First project'}]}
    assert history.put_ui_state('first','nlui_pending',pending,expires=200,now=100)
    assert history.get_ui_state('first','nlui_pending',now=150)==pending
    assert history.get_ui_state('other','nlui_pending',now=150) is None
    assert history.get_ui_state('first','nlui_pending',now=201) is None
    assert history.put_ui_state('first','nlui_presentation',{'style':'compact'})
    history.delete('first')
    assert history.get_ui_state('first','nlui_presentation') is None
    assert history.open('other')['messages']


def test_pending_store_refuses_nested_grants_and_oversized_payloads(tmp_path):
    history=ChatHistory(tmp_path/'knowledge.db')
    history.save('chat',[{'role':'user','content':'A fixture.'}],merge=True)
    with pytest.raises(ValueError,match='grants'):
        history.put_ui_state('chat','nlui_pending',{'parameters':{'permission_token':'not-a-real-token'}})
    with pytest.raises(ValueError,match='64 KiB'):
        history.put_ui_state('chat','nlui_pending',{'text':'x'*70000})
