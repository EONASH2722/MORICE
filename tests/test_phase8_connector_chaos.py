"""Actual loopback HTTP faults through shared connector permissions and leases."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import socket
import threading
import time
import pytest
from test_ambient_connectors_security import system
from morice.connectors.contracts import ConnectorState
from morice.connectors.http import BoundedHTTP


@pytest.fixture
def fixture_server():
    state={'token':'phase8-chaos-owned-token','fault':None,'calls':0}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            state['calls']+=1;fault=state['fault']
            if fault=='reset':
                self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
            if fault=='timeout':time.sleep(.6)
            status=fault if isinstance(fault,int) else 200
            value={'id':42,'login':'phase8-owner'} if self.path=='/user' else {
                'id':101,'number':1,'title':'Observed fixture','body':'Untrusted fixture content'}
            raw=b'{' if fault=='bad_json' else json.dumps(value).encode()
            try:
                self.send_response(status);self.send_header('Content-Length',str(len(raw)))
                if status==429:self.send_header('Retry-After','30')
                self.end_headers();self.wfile.write(raw)
            except OSError:pass  # The deliberately timed-out client closed its socket.
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',state
    finally:server.shutdown();server.server_close();thread.join(2);assert not thread.is_alive()


@pytest.mark.parametrize('fault',[401,403,429,500,'timeout','reset','bad_json','outage'])
def test_provider_fault_is_truthful_bounded_and_recovers(system,fault):
    s=system;original=s.provider.http;original.timeout=.15;s.fixture['fault']=fault
    if fault=='outage':
        with socket.socket() as owned:
            owned.bind(('127.0.0.1',0));port=owned.getsockname()[1]
        s.provider.http=BoundedHTTP(f'http://127.0.0.1:{port}',fixture=True,timeout=.15)
    stamp=time.monotonic();result=s.kernel.dispatch('connector.fixture.issue.read',{'number':1})
    assert not result.success and time.monotonic()-stamp<2
    assert not s.kernel.resources.snapshot()
    expected=(ConnectorState.AUTH_EXPIRED if fault==401 else ConnectorState.RATE_LIMITED if fault==429 else
        ConnectorState.UNAVAILABLE if fault in {'timeout','reset','outage'} else ConnectorState.DEGRADED)
    assert s.provider.state==expected
    if fault==429 or fault in {'timeout','reset','outage'}:
        calls=s.provider.http.calls
        assert not s.kernel.dispatch('connector.fixture.issue.read',{'number':1}).success
        assert s.provider.http.calls==calls  # Retry scheduling never sleeps in a worker.
    s.fixture['fault']=None;s.provider.http=original;s.provider.retry_at=0
    if fault==401:
        s.provider.install_fixture_token(s.fixture['token'],user_confirmed=True)
        s.ambient.connectors.authorize_scopes('fixture',user_confirmed=True)
    # A warm cached AVAILABLE result must not hide a permanently unavailable
    # registration once the ordinary health cache refreshes after an outage.
    s.kernel.registry.health('connector.fixture.issue.read',refresh=True)
    recovered=s.kernel.dispatch('connector.fixture.issue.read',{'number':1})
    assert recovered.success and recovered.verification.status.value=='verified'
    assert s.provider.state==ConnectorState.CONNECTED and not s.kernel.resources.snapshot()
