"""Bounded exact-origin HTTP contracts; no discovery or login guessing."""
from __future__ import annotations
import datetime,hashlib,http.client,ipaddress,json,re,time,urllib.parse
from pathlib import Path

class ScopedClient:
    def __init__(self,origin,*,budget=24,seconds=30):
        parsed=urllib.parse.urlsplit(origin)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {'','/'} or parsed.query or parsed.fragment:raise ValueError('Configure one exact HTTP(S) origin without credentials or path.')
        if parsed.scheme=='http':
            try:local=ipaddress.ip_address(parsed.hostname).is_private
            except ValueError:local=parsed.hostname=='localhost'
            if not local:raise ValueError('External endpoints require verified HTTPS.')
        self.origin=origin.rstrip('/');self.host=parsed.hostname;self.port=parsed.port;self.tls=parsed.scheme=='https'
        self.remaining=min(24,int(budget));self.deadline=time.monotonic()+min(120,seconds);self.requests=0
    def request(self,method,path,token='',data=None):
        if method not in {'GET','HEAD','POST'} or not path.startswith('/') or path.startswith('//') or '\\' in path or '\r' in path or '\n' in path:raise ValueError('Request is outside the typed HTTP contract.')
        url=urllib.parse.urlsplit(self.origin+path)
        if url.hostname!=self.host or url.port!=self.port or url.scheme!=('https' if self.tls else 'http'):raise ValueError('Request origin changed.')
        if self.remaining<=0 or time.monotonic()>self.deadline:raise TimeoutError('HTTP request budget reached.')
        self.remaining-=1;self.requests+=1
        connection=(http.client.HTTPSConnection if self.tls else http.client.HTTPConnection)(self.host,self.port,timeout=min(5,max(.1,self.deadline-time.monotonic())))
        headers={'Accept':'application/json','Content-Type':'application/json'}
        if token:
            if len(token)>16000 or any(c in token for c in '\r\n'):raise ValueError('Invalid credential material.')
            headers['Authorization']='Bearer '+token
        body=json.dumps(data).encode() if data is not None else None
        if body is not None and len(body)>65536:raise ValueError('Request body exceeds its contract.')
        try:
            connection.request(method,path,body=body,headers=headers);response=connection.getresponse();raw=response.read(256*1024+1)
            if len(raw)>256*1024:raise ValueError('Response exceeds its contract.')
            try:value=json.loads(raw) if raw else {}
            except (ValueError,UnicodeError):value={}
            return response.status,value,{k.lower():v[:1000] for k,v in response.getheaders() if k.lower() in {'content-type','content-security-policy','x-content-type-options','strict-transport-security','x-frame-options'}}
        finally:connection.close()

def assess_endpoint(origin):
    client=ScopedClient(origin,budget=1,seconds=10);started=time.monotonic();status,_,headers=client.request('GET','/')
    return {'status':'COMPLETED','origin':client.origin,'http_status':status,'headers':headers,'requests':client.requests,
        'checks':[{'header':key,'present':key in headers,'state':'OBSERVED' if key in headers else 'REVIEW_REQUIRED'}
            for key in ('x-content-type-options','content-security-policy','strict-transport-security')],
        'seconds':time.monotonic()-started,'limitation':'One explicit origin and one read-only request; missing headers are contextual review items, not confirmed vulnerabilities. Redirects are not followed.'}

def vox_delivery(manifest_path,credentials,*,progress=lambda value:None):
    config=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    required={'origin','project_root','sender_id','recipient_id','sender_identity','recipient_identity','recipient_lookup','send','stored','recipient_readback','fields'}
    if set(config)!=required:raise ValueError('Supply the documented exact VOX API mapping; endpoints are never guessed.')
    project=Path(config['project_root']).resolve(strict=True)
    if not project.is_dir() or project==Path(project.anchor):raise ValueError('Select the actual source repository for the configured service.')
    for key in ('sender_id','recipient_id'):
        if not re.fullmatch(r'[A-Za-z0-9_:@.-]{1,128}',config[key]) or config[key] in {'.','..'}:raise ValueError('Invalid confirmed test identity.')
    if config['sender_id']==config['recipient_id']:raise ValueError('Use two distinct explicitly supplied test identities.')
    sender=credentials.get('sender_token','');recipient=credentials.get('recipient_token','')
    if not sender or not recipient:return {'status':'MISSING_KEY','message':'Supply both authorized test-account tokens privately. No message was sent.'}
    fields=config['fields']
    if set(fields)!={'id','sender','recipient','text','identity','timestamp'} or any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9_.]{1,80}',x) for x in fields.values()):raise ValueError('Invalid API field mapping.')
    def field(value,name):
        for key in fields[name].split('.'):value=value[key]
        return value
    from .challenge import PHRASE
    values={'sender':config['sender_id'],'recipient':config['recipient_id'],'text':PHRASE,'message_id':''}
    def endpoint(name):
        item=config[name]
        if not isinstance(item,dict) or set(item)-{'method','path','payload'}:raise ValueError('Invalid mapped API operation.')
        if item.get('method','GET')!=('POST' if name=='send' else 'GET'):raise ValueError('Identity/readback operations must be GET; the single send operation must be POST.')
        path=item['path']
        for key,value in values.items():path=path.replace('{'+key+'}',urllib.parse.quote(str(value),safe=''))
        if '{' in path or '}' in path:raise ValueError('Unresolved endpoint parameter.')
        payload=item.get('payload')
        if payload is not None:
            if not isinstance(payload,dict) or len(payload)>12:raise ValueError('Invalid message mapping.')
            payload={k:values[v[1:-1]] if isinstance(v,str) and v.startswith('{') and v.endswith('}') and v[1:-1] in values else v for k,v in payload.items()}
        return item.get('method','GET'),path,payload
    client=ScopedClient(config['origin'],budget=12,seconds=45);checks=[];started=time.time()
    def get(name,token):
        method,path,data=endpoint(name);status,value,_=client.request(method,path,token,data)
        if status not in {200,201,202}:raise ValueError('Mapped '+name+' request did not return a valid success status; delivery is unverified.')
        return value
    for name,token,identity in (('sender_identity',sender,values['sender']),('recipient_identity',recipient,values['recipient'])):
        actual=get(name,token)
        if str(field(actual,'identity'))!=identity:raise ValueError('Authorized token identity did not match the confirmed account.')
        checks.append({'test':name,'passed':True})
    lookup=get('recipient_lookup',sender)
    if str(field(lookup,'identity'))!=values['recipient']:raise ValueError('Recipient lookup mismatch; no message was sent.')
    progress({'stage':'Verified test identities','completed':3,'planned':6})
    ack=get('send',sender);identifier=str(field(ack,'id'))
    if not re.fullmatch(r'[A-Za-z0-9_:@.-]{1,128}',identifier) or identifier in {'.','..'}:raise ValueError('Invalid stored message ID.')
    values['message_id']=identifier
    stamp=field(ack,'timestamp')
    try:
        timestamp=float(stamp)
        if timestamp>1e11:timestamp/=1000
    except (ValueError,TypeError):timestamp=datetime.datetime.fromisoformat(str(stamp).replace('Z','+00:00')).timestamp()
    if not started-60<=timestamp<=time.time()+300:raise ValueError('Acknowledged message timestamp does not establish a new delivery within the clock-skew allowance.')
    def canonical(message):return {name:str(field(message,name)) for name in ('id','sender','recipient','text','timestamp')}
    expected={'id':identifier,'sender':values['sender'],'recipient':values['recipient'],'text':PHRASE,'timestamp':str(stamp)}
    for name,token in (('stored',sender),('recipient_readback',recipient)):
        actual=canonical(get(name,token))
        if actual!=expected:return {'status':'PARTIAL','message_delivery':'UNVERIFIED','message':'Acknowledgement/stored/recipient readback do not agree.','requests':client.requests}
        checks.append({'test':name,'passed':True})
    return {'status':'COMPLETED','message_delivery':'VERIFIED','environment':'USER_CONFIGURED_AUTHORIZED_TARGET','origin':client.origin,
        'message':expected,'receipt_sha256':hashlib.sha256(json.dumps(expected,sort_keys=True).encode()).hexdigest(),'tests':checks,'requests':client.requests,
        'limitation':'Legitimate delivery through owner-supplied API mappings and two confirmed test identities. No online password guessing or recipient impersonation.'}
