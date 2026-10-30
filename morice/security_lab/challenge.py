"""Owned loopback messaging challenge; original application is never modified."""
from __future__ import annotations
import hashlib, http.client, json, secrets, threading, time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

PHRASE='I HAD STRINGS BUT NOW I AM FREE'
VULNERABLE_POLICY='def may_read(user, message):\n    return bool(user)\n'
FIXED_POLICY='def may_read(user, message):\n    return user in (message["sender"], message["recipient"])\n'

def run_challenge(*,repair=True,progress=lambda value:None,policy_path=None,expected_secure=False):
    """Real HTTP/storage assertions, a staged code repair and same-test retest."""
    # Sessions exist only in this isolated fixture and are never returned.
    sender,recipient,outsider='lab-sender','lab-recipient','lab-outsider'
    sessions={secrets.token_hex(24):sender,secrets.token_hex(24):recipient,secrets.token_hex(24):outsider}
    tokens={value:key for key,value in sessions.items()};messages={};request_ids={};counts={};lock=threading.Lock()
    vulnerable=VULNERABLE_POLICY;fixed=FIXED_POLICY
    if policy_path:
        from pathlib import Path
        source=Path(policy_path).read_text(encoding='utf-8')
        if source not in (vulnerable,fixed):raise ValueError('Only the exact generated fixture policy may execute.')
    else:source=vulnerable
    policy={};exec(compile(source,'<owned-messaging-fixture>','exec'),policy)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,value):
            raw=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            # Drain the bounded request before rejecting authentication. Closing
            # with unread bytes can reset the socket on Windows and discard the
            # actual 401 response while the client is still writing its body.
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:self.reply(413,{});return
                raw=self.rfile.read(size)
            except (ValueError,TypeError):self.reply(400,{});return
            user=sessions.get(self.headers.get('Authorization','').removeprefix('Bearer '))
            if not user:self.reply(401,{'error':'unauthenticated'});return
            if self.path!='/messages':self.reply(404,{});return
            try:
                data=json.loads(raw)
            except (ValueError,TypeError):self.reply(400,{});return
            if data.get('sender') not in (None,user):self.reply(403,{'error':'sender mismatch'});return
            if data.get('recipient') not in {sender,recipient,outsider} or not isinstance(data.get('text'),str) or len(data['text'])>512:self.reply(400,{});return
            with lock:
                key=(user,self.headers.get('Idempotency-Key',''))
                if key[1] and key in request_ids:message=messages[request_ids[key]]
                else:
                    counts[user]=counts.get(user,0)+1
                    if counts[user]>5:self.reply(429,{});return
                    identifier=secrets.token_hex(8);message={'id':identifier,'sender':user,'recipient':data['recipient'],'text':data['text'],'created_at':time.time()}
                    messages[identifier]=message
                    if key[1]:request_ids[key]=identifier
            self.reply(201,message)
        def do_GET(self):
            user=sessions.get(self.headers.get('Authorization','').removeprefix('Bearer '))
            if not user:self.reply(401,{});return
            with lock:message=messages.get(self.path.removeprefix('/messages/'))
            if not message:self.reply(404,{});return
            if not policy['may_read'](user,message):self.reply(403,{});return
            self.reply(200,message)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();port=server.server_port;requests=0;started=time.monotonic()
    def request(method,path,identity=None,data=None,request_id=''):
        nonlocal requests
        requests+=1
        if requests>24 or time.monotonic()-started>15:raise TimeoutError('Fixture budget reached')
        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
        headers={'Content-Type':'application/json'}
        if identity:headers['Authorization']='Bearer '+tokens.get(identity,'invalid')
        if request_id:headers['Idempotency-Key']=request_id
        try:
            connection.request(method,path,json.dumps(data) if data is not None else None,headers);response=connection.getresponse();body=response.read(65536)
            return response.status,json.loads(body)
        finally:connection.close()
    try:
        assertions=[]
        def check(name,condition):
            assertions.append({'test':name,'passed':bool(condition)})
            if not condition:raise AssertionError(name)
        check('unauthenticated creation rejected',request('POST','/messages',data={'recipient':recipient,'text':PHRASE})[0]==401)
        check('invalid session rejected',request('POST','/messages','invalid',{'recipient':recipient,'text':PHRASE})[0]==401)
        check('sender impersonation rejected',request('POST','/messages',sender,{'sender':outsider,'recipient':recipient,'text':PHRASE})[0]==403)
        status,message=request('POST','/messages',sender,{'recipient':recipient,'text':PHRASE},'owned-once')
        check('authenticated creation stored',status==201 and messages[message['id']]==message)
        path='/messages/'+message['id'];status,visible=request('GET',path,recipient)
        check('recipient readback exact',status==200 and visible==message and visible['text']==PHRASE)
        _,duplicate=request('POST','/messages',sender,{'recipient':recipient,'text':PHRASE},'owned-once')
        check('idempotent retry preserves message ID',duplicate['id']==message['id'] and len(messages)==1)
        before=request('GET',path,outsider)[0];finding={'category':'missing_conversation_authorization','state':'VERIFIED' if before==200 else 'NOT_REPRODUCED',
            'expected_status':403,'before_status':before,'test_reference':'outsider message read','target':'owned loopback messaging fixture'}
        if expected_secure:check('unauthorized read blocked after source repair',before==403)
        progress({'stage':'FINDING_VERIFIED','completed':7,'planned':10})
        if repair:
            exec(compile(fixed,'<owned-messaging-fixture>','exec'),policy)
            after=request('GET',path,outsider)[0];check('same unauthorized-read regression after repair',after==403)
            check('legitimate recipient still reads after repair',request('GET',path,recipient)[1]==message)
            finding.update(state='RETESTED',fix_status='FIXED',after_status=after,
                before_source_sha256=hashlib.sha256(vulnerable.encode()).hexdigest(),after_source_sha256=hashlib.sha256(fixed.encode()).hexdigest())
        return {'status':'COMPLETED','environment':'ISOLATED_LOCAL_FIXTURE','live_vox_tested':False,'message_delivery':'VERIFIED',
            'message':message,'tests':assertions,'findings':[finding],'requests':requests,'seconds':time.monotonic()-started,
            'limitation':'Real owned loopback fixture; not the user’s VOX backend. Live VOX repository/endpoints/test identities must be configured separately.'}
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
