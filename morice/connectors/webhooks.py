"""Opt-in bounded loopback receiver for an explicitly configured HTTPS relay.

No public port, tunnel, deployment or subscription is created automatically.
One HTTP transport thread limits connection handling independently of agent work.
"""
from __future__ import annotations

import threading
import socket
from http.server import BaseHTTPRequestHandler,HTTPServer


class WebhookReceiver:
    def __init__(self,registry):
        self.registry=registry
        receiver=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                status=400
                try:
                    if self.headers.get("Transfer-Encoding"):
                        raise ValueError("Chunked webhook requests are unsupported.")
                    length=int(self.headers.get("Content-Length","0"))
                    if not 0<length<=131072:
                        raise ValueError("Webhook body exceeds its byte budget.")
                    prefix="/webhooks/"
                    if not self.path.startswith(prefix) or self.path[len(prefix):] not in receiver.registry.providers:
                        raise ValueError("Unknown connector route.")
                    body=self.rfile.read(length)
                    if len(body)!=length:raise ValueError("Incomplete webhook body.")
                    provider=receiver.registry.providers[self.path[len(prefix):]]
                    accepted=provider.webhook(body,dict(self.headers))
                    status=202 if accepted else 200
                except PermissionError:status=403
                except (ValueError,TypeError,KeyError,OSError,RecursionError):status=400
                self.send_response(status);self.send_header("Content-Length","0");self.end_headers()
        class Server(HTTPServer):
            request_queue_size=8
            def get_request(self):
                connection,address=super().get_request();connection.settimeout(2);return connection,address
            def process_request(self,request,address):
                def expire():
                    try:request.shutdown(socket.SHUT_RDWR)
                    except OSError:pass
                deadline=threading.Timer(2,expire);deadline.daemon=True;deadline.start()
                try:super().process_request(request,address)
                finally:deadline.cancel();deadline.join(.05)
        self.server=Server(("127.0.0.1",0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,name="morice-webhook-transport",daemon=True)
        self.thread.start()

    @property
    def url(self):return "http://127.0.0.1:"+str(self.server.server_port)

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)
