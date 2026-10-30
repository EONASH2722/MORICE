import json,threading,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
import pytest
from morice.security_lab.webtests import ScopedClient,assess_endpoint,vox_delivery
from morice.security_lab.challenge import PHRASE
from morice.security_lab.devices import AndroidDiagnostics

@pytest.fixture
def api(tmp_path):
    state={'messages':{},'posts':0,'corrupt_readback':False,'calls':0}
    tokens={'fixture-sender-token':'sender','fixture-recipient-token':'recipient'}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,value):
            raw=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Length',str(len(raw)));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            state['calls']+=1;user=tokens.get(self.headers.get('Authorization','').removeprefix('Bearer '))
            if self.path=='/':self.reply(200,{'ok':True});return
            if self.path=='/redirect':self.send_response(302);self.send_header('Location','https://unrelated.invalid/');self.end_headers();return
            if not user:self.reply(401,{});return
            if self.path=='/me':self.reply(200,{'id':user});return
            if self.path=='/users/recipient':self.reply(200,{'id':'recipient'});return
            row=state['messages'].get(self.path.removeprefix('/messages/'))
            if not row:self.reply(404,{});return
            row=dict(row)
            if state['corrupt_readback'] and user=='recipient':row['text']='different'
            self.reply(200,row)
        def do_POST(self):
            user=tokens.get(self.headers.get('Authorization','').removeprefix('Bearer '))
            if user!='sender':self.reply(401,{});return
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));state['posts']+=1
            row={'id':str(state['posts']),'sender':user,'recipient':body['recipient'],'text':body['text'],'created_at':time.time()};state['messages'][row['id']]=row;self.reply(201,row)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    origin='http://127.0.0.1:'+str(server.server_port)
    config={'origin':origin,'project_root':str(tmp_path),'sender_id':'sender','recipient_id':'recipient',
        'sender_identity':{'path':'/me'},'recipient_identity':{'path':'/me'},'recipient_lookup':{'path':'/users/{recipient}'},
        'send':{'method':'POST','path':'/messages','payload':{'recipient':'{recipient}','text':'{text}'}},
        'stored':{'path':'/messages/{message_id}'},'recipient_readback':{'path':'/messages/{message_id}'},
        'fields':{'id':'id','sender':'sender','recipient':'recipient','text':'text','identity':'id','timestamp':'created_at'}}
    path=tmp_path/'mapping.json';path.write_text(json.dumps(config),encoding='utf-8')
    try:yield origin,path,state,config
    finally:server.shutdown();server.server_close();thread.join(timeout=2)

def test_actual_mapping_delivers_and_reads_both_accounts(api):
    origin,path,state,_=api;result=vox_delivery(path,{'sender_token':'fixture-sender-token','recipient_token':'fixture-recipient-token'})
    assert result['message_delivery']=='VERIFIED' and result['message']['text']==PHRASE and result['requests']==6
    assert state['posts']==1 and 'fixture-sender-token' not in json.dumps(result)

def test_api_readback_mismatch_is_not_delivery(api):
    _,path,state,_=api;state['corrupt_readback']=True
    result=vox_delivery(path,{'sender_token':'fixture-sender-token','recipient_token':'fixture-recipient-token'})
    assert result['status']=='PARTIAL' and result['message_delivery']=='UNVERIFIED'

def test_missing_or_wrong_identity_sends_nothing(api):
    _,path,state,config=api
    assert vox_delivery(path,{})['status']=='MISSING_KEY' and state['posts']==0
    with pytest.raises(ValueError):vox_delivery(path,{'sender_token':'fixture-recipient-token','recipient_token':'fixture-sender-token'})
    assert state['posts']==0

def test_budgets_and_redirects_do_not_expand_scope(api):
    origin,_,state,_=api;client=ScopedClient(origin,budget=1)
    assert client.request('GET','/redirect')[0]==302
    with pytest.raises(TimeoutError):client.request('GET','/')
    with pytest.raises(ValueError):ScopedClient(origin).request('GET','//other.invalid/')
    with pytest.raises(ValueError):ScopedClient('http://user:password@127.0.0.1')
    assert assess_endpoint(origin)['requests']==1

def test_device_unauthorized_and_exact_selection_contracts():
    adapter=AndroidDiagnostics();calls=[]
    def run(args,*a,**kw):
        calls.append(args)
        if args==['devices','-l']:return 'List of devices attached\nowned-1\tunauthorized\nowned-2\tdevice product:fixture\n'
        raise AssertionError('Unauthorized diagnostic command was attempted')
    adapter.path='fixture-adb'
    with patch.object(adapter,'_run',side_effect=run):
        rows=adapter.discover()['devices'];assert rows[0]['state']=='UNAUTHORIZED' and not rows[0]['authorized']
        assert adapter.diagnose('owned-1')['status']=='UNAUTHORIZED'
        assert adapter.diagnose('not-connected')['status']=='DISCONNECTED'
    assert all(call==['devices','-l'] for call in calls)

@pytest.mark.parametrize('endpoint',['8.8.8.8:5555','127.0.0.1:0','127.0.0.1:70000','device;anything:5555'])
def test_wireless_debug_endpoint_validation(endpoint):
    with pytest.raises(ValueError):AndroidDiagnostics.endpoint(endpoint)
