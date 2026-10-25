"""GitHub OAuth device flow, repository-scoped issues and signed webhook envelopes."""
from __future__ import annotations

import hashlib
import http.client
import hmac
import json
import re
import threading
import time
from urllib.parse import quote

from ..ambient.contracts import AmbientEvent, Trust
from ..kernel import ErrorCode, ExecutionResult, TaskStatus, VerificationResult, VerificationStatus
from .contracts import ConnectorDescriptor, ConnectorState, ConnectorOperation
from .http import BoundedHTTP, ProviderHTTPError


class GitHubProvider:
    def __init__(self, connector_id, vault, *, repository, client_id="", api_url="https://api.github.com",
                 auth_url="https://github.com", fixture=False, api_version="2022-11-28"):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", connector_id) or not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
            raise ValueError("A safe connector id and owner/repository are required.")
        if not fixture and (api_url != "https://api.github.com" or auth_url != "https://github.com"):
            raise ValueError("This adapter supports the official GitHub origins only.")
        self.descriptor = ConnectorDescriptor(connector_id, "GitHub: " + repository, "github",
            capabilities=('issue.read','issue.create','issue.list','events.poll','auth.step','auth.refresh'),metadata={"repository": repository})
        self.vault, self.repository, self.client_id = vault, repository, client_id
        self.http = BoundedHTTP(api_url, fixture=fixture)
        self.auth_http = BoundedHTTP(auth_url, fixture=fixture)
        self.api_version = api_version
        self.state = ConnectorState.NOT_CONFIGURED
        self.retry_at = 0.0
        self._flow = None
        self._cache = {}
        self._lock = threading.RLock()
        self._generation = 0
        self._expires_at = 0
        self._refresh_attempted = False
        self._login = ""
        self.emit = lambda event: None
        self.cursor_get = lambda key: None
        self.cursor_set = lambda key, value: None

    def _key(self, kind):
        return f"connector.{self.descriptor.connector_id}.{kind}"

    def operations(self):
        return {"issue.read":ConnectorOperation(self.read_issue),"issue.create":ConnectorOperation(self.create_issue,"write",True),
                "issue.list":ConnectorOperation(self.list_issues,input_schema={'type':'object','properties':{
                    'query':{'type':'string','maxLength':200},'state':{'type':'string','enum':['open','closed','all']}},'additionalProperties':False}),
                "events.poll":ConnectorOperation(self.poll),"auth.step":ConnectorOperation(self.auth_step,"auth"),
                "auth.refresh":ConnectorOperation(self.refresh,"auth")}

    def configuration(self):
        return None if self.http.fixture else {"provider":"github","repository":self.repository,"client_id":self.client_id}

    def next_auth_operation(self,now):
        if self._flow and self._flow["next_at"]<=now:return "auth.step"
        if self._expires_at and self._expires_at<=now+30 and not self._refresh_attempted and self.vault.get(self._key("refresh")):
            return "auth.refresh"
        return None

    def begin_authorization(self, *, user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Connecting requires an explicit user authorization action.")
        if not self.client_id:
            raise ValueError("Register a GitHub OAuth app with device flow enabled and configure its client id.")
        if not self.vault.available:
            raise RuntimeError("OS secure storage is unavailable.")
        generation=self._generation
        _, value, _ = self.auth_http.request("POST", "/login/device/code",
            payload={"client_id": self.client_id, "scope": "repo"})
        if not isinstance(value, dict) or not all(value.get(k) for k in ("device_code", "user_code", "verification_uri", "expires_in")):
            raise ValueError("Provider did not return a valid authorization challenge.")
        if value["verification_uri"] != "https://github.com/login/device" and not self.http.fixture:
            raise ValueError("Unexpected verification origin.")
        with self._lock:
            if generation!=self._generation:
                raise PermissionError("Authorization was cancelled by disconnect.")
            interval=max(5,min(900,float(value.get("interval",5))))
            self._flow = {"device_code": value["device_code"], "expires_at": time.time() + min(900,float(value["expires_in"])),
                          "interval":interval,"next_at":time.time()+interval}
            self.state = ConnectorState.CONNECTING
            return {"user_code": value["user_code"], "verification_uri": value["verification_uri"], "expires_at": self._flow["expires_at"]}

    def authorization_step(self, *, now=None, context=None):
        now = time.time() if now is None else now
        flow = self._flow
        generation=self._generation
        if not flow or now >= flow["expires_at"]:
            self._flow = None
            self.state = ConnectorState.AUTH_EXPIRED
            return False
        if now < flow["next_at"]:
            return False
        flow["next_at"] = now + flow["interval"]
        _, value, _ = self.auth_http.request("POST", "/login/oauth/access_token", context=context,payload={"client_id": self.client_id,
            "device_code": flow["device_code"], "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        if value.get("error") in {"authorization_pending", "slow_down"}:
            if value["error"] == "slow_down":
                flow["interval"] += 5
                flow["next_at"] = now + flow["interval"]
            return False
        if not value.get("access_token"):
            self._flow = None
            self.state = ConnectorState.AUTH_EXPIRED
            return False
        with self._lock:
            if generation!=self._generation or self._flow is not flow:
                return False
            self._save_tokens(value,now)
            try:
                _,account,_=self._request("GET","/user",context)
                if not isinstance(account,dict) or not account.get("id") or not isinstance(account.get("login"),str) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}",account["login"]):
                    raise ValueError("Authenticated account identity was not observed.")
            except (ValueError,OSError,ProviderHTTPError):
                self._flow=None;self.state=ConnectorState.AUTH_EXPIRED
                raise
            self._login=account["login"]
            metadata=self.cursor_get("connector.auth."+self.descriptor.connector_id) or {}
            self.cursor_set("connector.auth."+self.descriptor.connector_id,{**metadata,"login":self._login})
            self._flow = None
            self.state = ConnectorState.CONNECTED
            return True

    def _save_tokens(self, value, now):
        if value.get("refresh_token"):
            self.vault.set(self._key("refresh"),value["refresh_token"])
        self.vault.set(self._key("access"),value["access_token"])
        self._expires_at = now + float(value.get("expires_in",0)) if value.get("expires_in") else 0
        prior=self.cursor_get("connector.auth."+self.descriptor.connector_id) or {}
        self.cursor_set("connector.auth."+self.descriptor.connector_id,{**prior,"expires_at":self._expires_at,
            "refresh_expires_at":now+float(value.get("refresh_token_expires_in",0)) if value.get("refresh_token_expires_in") else 0})
        self._refresh_attempted = False

    def auth_step(self, arguments, context):
        authorized = self.authorization_step(context=context)
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{"authorized":authorized,"state":self.state.value,"retrieved_at":time.time()},
            evidence=["Bounded OAuth authorization status retrieved; credentials remain in the OS vault."])

    def refresh(self, arguments, context):
        with self._lock:
            if self.state == ConnectorState.DISABLED or self._refresh_attempted:
                return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,"Refresh requires explicit reauthorization after a failed attempt.")
            self._refresh_attempted = True
            token = self.vault.get(self._key("refresh"))
            metadata = self.cursor_get("connector.auth."+self.descriptor.connector_id) or {}
            if not token or metadata.get("refresh_expires_at") and time.time() >= metadata["refresh_expires_at"]:
                self.state = ConnectorState.AUTH_EXPIRED
                return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,"Refresh token expired or unavailable; authorize the account again.")
            try:
                _,value,_ = self.auth_http.request("POST","/login/oauth/access_token",context=context,payload={
                    "client_id":self.client_id,"grant_type":"refresh_token","refresh_token":token})
                if not isinstance(value,dict) or not value.get("access_token") or not value.get("refresh_token"):
                    raise ValueError("Refresh did not return a token pair.")
                self._save_tokens(value,time.time())
                self.state = ConnectorState.CONNECTED
            except (ValueError,OSError,ProviderHTTPError):
                self.state = ConnectorState.AUTH_EXPIRED
                return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,"Provider refresh failed; authorize the account again.")
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{"state":self.state.value,"retrieved_at":time.time()},evidence=["OS-vault token pair rotated after bounded provider response."])

    def install_fixture_token(self, token, *, user_confirmed=False, expires_at=0):
        if not self.http.fixture or not user_confirmed:
            raise PermissionError("Token injection is restricted to explicitly authorized loopback fixtures.")
        self.vault.set(self._key("access"), token)
        self._expires_at = expires_at
        self._login = "fixture-owner"
        self.state = ConnectorState.CONNECTED

    def resume_auth(self):
        self.state = ConnectorState.CONNECTED if self.vault.get(self._key("access")) else ConnectorState.NOT_CONFIGURED
        self._expires_at = (self.cursor_get("connector.auth."+self.descriptor.connector_id) or {}).get("expires_at",0)
        self._login = (self.cursor_get("connector.auth."+self.descriptor.connector_id) or {}).get("login","")

    def configure_webhook(self, secret, *, user_confirmed=False):
        if not user_confirmed or not secret or len(secret) < 16:
            raise PermissionError("An explicitly configured webhook secret of at least 16 characters is required.")
        self.vault.set(self._key("webhook"), secret)
        self.cursor_set("connector.webhook."+self.descriptor.connector_id,[])

    def _request(self, method, path, context, payload=None, headers=None):
        with self._lock:
            if self.state in {ConnectorState.DISABLED, ConnectorState.NOT_CONFIGURED, ConnectorState.AUTH_EXPIRED}:
                raise ProviderHTTPError(401)
            if time.time() < self.retry_at:
                raise ProviderHTTPError(429, self.retry_at)
            if self._expires_at and time.time() >= self._expires_at:
                self.state = ConnectorState.AUTH_EXPIRED
                raise ProviderHTTPError(401)
            generation = self._generation
            token = self.vault.get(self._key("access"))
        if not token:
            self.state = ConnectorState.AUTH_EXPIRED
            raise ProviderHTTPError(401)
        try:
            result = self.http.request(method, path, token=token, payload=payload, context=context,
                headers={"X-GitHub-Api-Version": self.api_version, **(headers or {})})
        except ProviderHTTPError as exc:
            with self._lock:
                if generation == self._generation:
                    self.state = ConnectorState.AUTH_EXPIRED if exc.status == 401 else ConnectorState.RATE_LIMITED if exc.retry_at else ConnectorState.DEGRADED
                    self.retry_at = exc.retry_at
            raise
        except (OSError, http.client.HTTPException):
            with self._lock:
                if generation == self._generation:
                    self.state = ConnectorState.UNAVAILABLE
                    self.retry_at = time.time() + 60
            raise
        except ValueError:
            with self._lock:
                if generation == self._generation:
                    self.state = ConnectorState.DEGRADED
            raise
        with self._lock:
            if generation != self._generation:
                raise ProviderHTTPError(401)
            self.state = ConnectorState.CONNECTED
        return result

    def _issue_path(self, number=None):
        if number is not None and (not isinstance(number,int) or isinstance(number,bool) or not 1 <= number <= 2147483647):
            raise ValueError("A positive issue number is required.")
        return "/repos/" + self.repository + "/issues" + ("/" + str(number) if number else "")

    def read_issue(self, arguments, context):
        number = arguments["number"]
        path = self._issue_path(number)
        cached = self._cache.get(number)
        headers = {"If-None-Match": cached["etag"]} if cached and cached.get("etag") else {}
        status, value, response_headers = self._request("GET", path, context, headers=headers)
        if status == 304:
            if not cached:
                raise ValueError("304 without cached object.")
            value = cached["object"]
        if not isinstance(value,dict) or value.get("number") != number or not value.get("id"):
            raise ValueError("Issue identity was not observed.")
        self._cache[number] = {"etag": response_headers.get("etag", cached.get("etag", "") if cached else ""), "object": value}
        if len(self._cache) > 32:
            self._cache.pop(next(iter(self._cache)))
        return ExecutionResult(TaskStatus.SUCCEEDED, True, {"object": value, "trust": "UNTRUSTED_CONTENT",
            "retrieved_at": time.time(), "cache_revalidated": status == 304, "etag": self._cache[number]["etag"],
            "connector_id": self.descriptor.connector_id}, evidence=["Official API object identity and fresh retrieval/revalidation."])

    def list_issues(self,arguments,context):
        state=arguments.get('state','open');query=arguments.get('query','')
        if state not in {'open','closed','all'} or not isinstance(query,str) or len(query)>200:raise ValueError('Invalid bounded issue query.')
        _,values,_=self._request('GET',self._issue_path()+'?state='+state+'&sort=updated&direction=desc&per_page=100',context)
        if not isinstance(values,list) or len(values)>100:raise ValueError('Issue listing exceeded its page bound.')
        rows=[]
        for value in values:
            if not isinstance(value,dict) or not isinstance(value.get('number'),int) or not value.get('id'):
                raise ValueError('Provider issue identity is missing.')
            if value.get('pull_request'):continue
            if query and query.casefold() not in (str(value.get('title',''))+' '+str(value.get('body') or '')).casefold():continue
            rows.append({key:value.get(key) for key in ('id','number','title','state','html_url','updated_at')})
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{'issues':rows,'repository':self.repository,
            'retrieved_at':time.time(),'page_limit':100,'possibly_more':len(values)==100,'query':query,
            'trust':'UNTRUSTED_CONTENT','connector_id':self.descriptor.connector_id},
            evidence=['Fresh authenticated repository issue page; pull requests excluded. Filtering covers only this bounded page.'])

    def create_issue(self, arguments, context):
        title = arguments.get("title", "")
        if not isinstance(title,str) or not title.strip() or len(title) > 256:
            raise ValueError("A bounded issue title is required.")
        _, value, _ = self._request("POST", self._issue_path(), context, payload={"title": title, "body": arguments.get("body", "")})
        if not isinstance(value,dict) or not isinstance(value.get("number"),int):
            return ExecutionResult.failure(ErrorCode.VERIFICATION_FAILED, "Provider did not identify a created object; review before retrying.")
        read = self.read_issue({"number": value["number"]}, context)
        actual = read.output["object"]
        if actual.get("id") != value.get("id") or actual.get("title") != title or actual.get("body", "") != arguments.get("body", ""):
            return ExecutionResult.failure(ErrorCode.VERIFICATION_FAILED, "Created issue does not match the independently retrieved object.")
        read.output["write_verified"] = True
        return read

    def verify(self, result, expected, context):
        valid = result.success and isinstance(result.output,dict) and result.output.get("retrieved_at",0) > time.time() - 10
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.INCONCLUSIVE,
                                  tuple(result.evidence), "Fresh provider object observation." if valid else "No fresh provider evidence.")

    def poll(self, arguments, context):
        key = "github.poll." + self.descriptor.connector_id
        cursor = self.cursor_get(key) or {}
        suffix = "?state=all&sort=updated&direction=desc&per_page=30"
        if self._login:suffix+="&assignee="+quote(self._login,safe="")
        if cursor.get("since"):
            suffix += "&since=" + quote(cursor["since"], safe="")
        _, values, _ = self._request("GET", self._issue_path() + suffix, context)
        if not isinstance(values,list) or len(values) > 30:
            raise ValueError("Polling page exceeds its event budget.")
        emitted = 0
        since = cursor.get("since", "")
        for value in values:
            if not isinstance(value,dict) or not value.get("id") or not value.get("updated_at"):
                continue
            changed = str(value["updated_at"])
            # Cursor starts at the most recent page after offline time; no blind
            # pagination/replay. Overlapping revisions are deduped by event keys.
            assigned=any(a.get("login")==self._login for a in value.get("assignees",[]) if isinstance(a,dict))
            kind = "github.issue.assigned" if assigned else "github.issue.changed"
            event = AmbientEvent(kind, "github", self.descriptor.connector_id,
                {"number": value.get("number"), "object_id": value["id"], "state": value.get("state", "unknown")},
                trust=Trust.CONNECTED_PROVIDER, authorization_context="connector:" + self.descriptor.connector_id,
                dedupe_key=f"issue:{value['id']}:{changed}")
            if self.emit(event) is not False:
                emitted += 1
            since = max(since, changed)
        self.cursor_set(key, {"since": since})
        return ExecutionResult(TaskStatus.SUCCEEDED, True, {"discovered": emitted, "retrieved_at": time.time(), "truncated_reconciliation": len(values) == 30},
            evidence=["Bounded authenticated provider page retrieved."])

    def webhook(self, body, headers):
        if self.state != ConnectorState.CONNECTED or not isinstance(body,bytes) or len(body) > 131072:
            raise PermissionError("Webhook body/state rejected.")
        normalized = {k.lower(): v for k,v in headers.items()}
        secret = self.vault.get(self._key("webhook"))
        signature = normalized.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        delivery = normalized.get("x-github-delivery", "")
        if not secret or not hmac.compare_digest(signature, expected) or not re.fullmatch(r"[\w-]{1,128}", delivery):
            raise PermissionError("Webhook signature or delivery identity is invalid.")
        value = json.loads(body)
        if normalized.get("x-github-event") != "issues" or value.get("repository",{}).get("full_name") != self.repository:
            raise ValueError("Webhook event is outside the configured repository scope.")
        issue = value.get("issue", {})
        if not isinstance(issue.get("id"),int) or not isinstance(issue.get("number"),int):
            raise ValueError("Webhook issue identity is missing.")
        if value.get("action")=="assigned" and value.get("assignee",{}).get("login")!=self._login:
            return False
        body_hash=hashlib.sha256(body).hexdigest()
        replay_key="connector.webhook."+self.descriptor.connector_id
        with self._lock:
            seen=self.cursor_get(replay_key) or []
            if body_hash in seen:return False
            if len(seen)>=1024:
                raise ValueError("Webhook replay ledger is full; explicitly rotate the webhook secret before accepting more deliveries.")
            self.cursor_set(replay_key,seen+[body_hash])
        event = AmbientEvent("github.issue.assigned" if value.get("action") == "assigned" else "github.issue.changed",
            "github", self.descriptor.connector_id, {"object_id": issue["id"], "number": issue["number"], "state": issue.get("state", "unknown")},
            trust=Trust.SIGNED_WEBHOOK, authorization_context="connector:" + self.descriptor.connector_id,
            # GitHub signs the body, not delivery headers. A changed unsigned
            # delivery id cannot make a replayed signed body a new event.
            dedupe_key="body:" + body_hash)
        return self.emit(event)

    def disconnect(self):
        with self._lock:
            self._generation += 1
            self._flow = None
            self._cache.clear()
            self._login=""
            self.vault.delete(self._key("access"))
            self.vault.delete(self._key("webhook"))
            self.vault.delete(self._key("refresh"))
            self.state = ConnectorState.DISABLED
        # Local disconnect invalidates all local grants and subscriptions. Server
        # revocation requires the user to revoke the OAuth app in GitHub settings;
        # this public device client has no application client secret for DELETE.
