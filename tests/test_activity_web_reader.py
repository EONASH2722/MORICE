from email.message import Message
import io
from unittest.mock import Mock,patch

import pytest

from morice.activity import ActivityLedger
from morice.web_reader import read_page,supplied_urls,checked_url,MAX_BYTES
from morice import llm_client


def test_activity_uses_actual_states_and_does_not_finish_running_background_tools():
    ledger=ActivityLedger();ledger.update('phase:context','Preparing context')
    ledger.update('owned-tool','Opening an actual page')
    ledger.update('failed-tool','Reading an unavailable page',state='failed')
    ledger.finish()
    assert ledger.steps['phase:context'].state=='done'
    assert ledger.steps['owned-tool'].state=='active'
    assert ledger.steps['failed-tool'].state=='failed'
    assert '✓' in ledger.text() and '!' in ledger.text()


def test_activity_is_bounded_and_never_generates_imagined_steps():
    ledger=ActivityLedger();assert ledger.text()==''
    for i in range(100):ledger.update(str(i),'Actual event '+str(i))
    assert len(ledger.steps)==24 and '0' not in ledger.steps


def response(body,mime='text/html'):
    stream=io.BytesIO(body);headers=Message();headers['Content-Type']=mime+'; charset=utf-8'
    result=Mock();result.__enter__=Mock(return_value=result);result.__exit__=Mock(return_value=False)
    result.headers=headers;result.read=stream.read;result.geturl.return_value='https://example.com/source'
    return result


def test_supplied_page_is_actually_read_with_ordered_progress_and_untrusted_html_is_text():
    client=Mock();client.open.return_value=response(b'<title>Actual title</title><script>hidden()</script><p>Actual source body.</p>')
    events=[];page=read_page('https://example.com/source',opener=client,progress=events.append)
    assert page.title=='Actual title' and 'Actual source body.' in page.text and 'hidden' not in page.text
    assert [x.split(':')[0] for x in events]==['Opening link','Reading page','Page read']
    assert client.open.call_count==1


def test_reader_bounds_bytes_types_and_urls_without_pretending_success():
    assert supplied_urls('Read https://example.com/a. ```\nhttps://example.com/code\n```')==['https://example.com/a']
    for url in ('file:///C:/secret','https://user:password@example.com'):
        with pytest.raises(ValueError):checked_url(url)
    for body,mime in ((b'x'*(MAX_BYTES+1),'text/html'),(b'not a page','application/octet-stream')):
        client=Mock();client.open.return_value=response(body,mime);events=[]
        with pytest.raises(ValueError):read_page('https://example.com',opener=client,progress=events.append)
        assert not any(event.startswith('Page read:') for event in events)


def test_reasoning_start_receipt_is_real_but_does_not_copy_raw_reasoning_into_activity():
    events=[];tokens=[{'choices':[{'delta':{'reasoning_content':'Owned private model token fixture'}}]},
        {'choices':[{'delta':{'content':'The final answer.'}}]}]
    with patch.object(llm_client,'_post_stream_json',return_value=iter(tokens)):
        answer=''.join(llm_client._try_openai_chat_stream('http://owned',{'messages':[]},1,
            telemetry=lambda event,payload:events.append((event,payload))))
    assert answer=='The final answer.'
    assert any(event=='model_reasoning_started' for event,_ in events)
    assert 'Owned private' not in str(events)
