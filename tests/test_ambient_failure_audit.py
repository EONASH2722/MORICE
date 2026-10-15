"""Separate adversarial review of authorization, privacy and bounded failure paths."""
from __future__ import annotations

import hashlib
import hmac
import json
import socket
import threading
import time
import urllib.request
import urllib.error

import pytest
from test_ambient_connectors_security import system,fixture_server,event,drain
from morice.ambient import AmbientEvent,Trigger,Autonomy,Trust
from morice.connectors import ConnectorState
from morice.kernel import ExecutionContext,CancellationToken


@pytest.mark.parametrize("state",["ask","denied"])
def test_account_authorization_respects_existing_network_permission(system,state):
    from morice.unified_intelligence import PermissionState
    s=system
    s.kernel.permissions.controller.set_state("network",PermissionState(state))
    before=s.provider.auth_http.calls
    with pytest.raises(PermissionError,match="network permission"):
        s.ambient.connectors.begin_authorization("fixture",user_confirmed=True)
    assert s.provider.auth_http.calls==before
    assert s.provider.state==ConnectorState.CONNECTED


def test_concurrent_exact_confirmations_do_not_duplicate_external_write(system,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    s=system
    s.ambient.connectors.authorize_scopes("fixture",("read","write"),user_confirmed=True)
    s.ambient.create(Trigger("Single fixture write","fixture.ready",action="connector.fixture.issue.create",
        arguments={"title":"One effect from concurrent confirmations"},level=Autonomy.CONFIRM,
        enabled=True,cooldown_seconds=0),user_confirmed=True)
    s.ambient.publish(event());drain(s)
    key=s.ambient.store.receipts()[0]["key"]
    preview=s.ambient.preview_confirmation
    task=preview(key)
    tokens=[s.kernel.permissions.controller.issue_one_use(task.task_id,task.capability_requirement,task.inputs) for _ in range(2)]
    barrier=threading.Barrier(2)
    def simultaneous_preview(value):
        result=preview(value);barrier.wait(timeout=3);return result
    monkeypatch.setattr(s.ambient,"preview_confirmation",simultaneous_preview)
    def confirm(token):
        try:return s.ambient.confirm(key,token)
        except ValueError:return "already_claimed"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(confirm,tokens))
    assert sum(r=="already_claimed" for r in results)==1
    assert sum(r!="already_claimed" and r.success for r in results)==1
    assert s.fixture["posts"]==1 and s.ambient.store.receipts()[0]["state"]=="verified"


def test_real_http_webhook_valid_invalid_replay_headers_and_rotation(system):
    s=system
    s.ambient.create(Trigger("Webhook fixture","github.issue.assigned",enabled=True,cooldown_seconds=0),user_confirmed=True)
    secret="fixture-signed-secret-at-least-32"
    s.provider.configure_webhook(secret,user_confirmed=True)
    url=s.ambient.connectors.start_webhooks(user_confirmed=True)+"/webhooks/fixture"
    body=json.dumps({"action":"assigned","assignee":{"login":"fixture-owner"},"repository":{"full_name":"owner/repo"},"issue":{"id":101,"number":1,"state":"open"}}).encode()
    headers={"X-Hub-Signature-256":"sha256="+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest(),
        "X-GitHub-Delivery":"delivery-one","X-GitHub-Event":"issues"}
    with urllib.request.urlopen(urllib.request.Request(url,body,headers),timeout=3) as response:assert response.status==202
    drain(s)
    with urllib.request.urlopen(urllib.request.Request(url,body,{**headers,"X-GitHub-Delivery":"forged-different-delivery"}),timeout=3) as response:assert response.status==200
    drain(s);assert len(s.notifications.history())==1
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(urllib.request.Request(url,body,{**headers,"X-Hub-Signature-256":"sha256=invalid"}),timeout=3)
    assert error.value.code==403
    s.ambient.store.cursor("connector.webhook.fixture",[str(i) for i in range(1024)])
    with pytest.raises(ValueError,match="ledger is full"):s.provider.webhook(body,headers)
    s.provider.configure_webhook("new-fixture-secret-rotation-authorized",user_confirmed=True)
    with pytest.raises(PermissionError):s.provider.webhook(body,headers)


def test_bounded_refresh_rotates_os_encrypted_secrets_and_stops_after_failure(system):
    s=system
    s.vault.set("connector.fixture.refresh","original-fixture-refresh")
    s.provider._expires_at=time.time()-1
    result=s.kernel.dispatch("connector.fixture.auth.refresh",{})
    assert result.success and s.vault.get("connector.fixture.refresh")=="rotated-fixture-refresh"
    assert "original-fixture-refresh" not in s.vault.path.read_text()
    assert "rotated-fixture-refresh" not in s.vault.path.read_text()
    s.fixture["refresh_error"]=True;s.provider._expires_at=time.time()-1
    assert not s.kernel.dispatch("connector.fixture.auth.refresh",{}).success
    before=s.provider.auth_http.calls
    assert not s.kernel.dispatch("connector.fixture.auth.refresh",{}).success
    assert s.provider.auth_http.calls==before and s.provider.state==ConnectorState.AUTH_EXPIRED


def test_slow_provider_cancellation_releases_actual_leases_and_no_late_dispatch(system):
    s=system;s.fixture["delay"]=4
    watch=s.ambient.create(Trigger("Slow read","fixture.ready",action="connector.fixture.issue.read",
        arguments={"number":1},level=Autonomy.READ,enabled=True,cooldown_seconds=0),user_confirmed=True)
    s.ambient.publish(event());s.ambient.tick()
    job=next(iter(s.ambient._inflight.values()))
    s.ambient.update(watch.trigger_id,enabled=False)
    assert job["token"].cancelled
    drain(s,seconds=4)
    until=time.monotonic()+3
    while s.kernel.resources.snapshot() and time.monotonic()<until:time.sleep(.02)
    assert not s.kernel.resources.snapshot()
    before=s.fixture["reads"]
    s.ambient.publish(AmbientEvent("fixture.ready","fixture","fixture",trust=Trust.LOCAL_OS,dedupe_key="new"));drain(s)
    assert s.fixture["reads"]==before


def test_quiet_period_expired_conditions_and_critical_override(system):
    s=system;hour=time.localtime().tm_hour
    watch=s.ambient.create(Trigger("Quiet watch","fixture.ready",enabled=True,cooldown_seconds=0,
        quiet_start_hour=hour,quiet_end_hour=(hour+1)%24),user_confirmed=True)
    s.ambient.publish(event());drain(s)
    assert not s.notifications.history() and s.ambient.store.receipts()[0]["state"]=="notification_suppressed"
    s.ambient.update(watch.trigger_id,critical_override=True,user_confirmed=True)
    s.ambient.publish(AmbientEvent("fixture.ready","fixture","fixture",trust=Trust.LOCAL_OS,severity="CRITICAL",dedupe_key="critical"));drain(s)
    assert len(s.notifications.history())==1


def test_concurrent_provider_events_and_dispatch_do_not_deadlock(system):
    s=system
    s.ambient.create(Trigger("Concurrent","fixture.ready",enabled=True,cooldown_seconds=0),user_confirmed=True)
    def emit():
        for i in range(1000):s.ambient.publish(AmbientEvent("fixture.ready","fixture","fixture",trust=Trust.LOCAL_OS,dedupe_key=str(i)))
    publisher=threading.Thread(target=emit);publisher.start()
    end=time.monotonic()+3
    while publisher.is_alive() and time.monotonic()<end:s.ambient.tick()
    publisher.join(1);assert not publisher.is_alive()
    drain(s)
    assert s.ambient.metrics["model_calls"]==0 and len(s.notifications.history())<=20


def test_scope_denial_tampered_hash_and_platform_isolation(system):
    s=system
    root=s.tmp/"owned";root.mkdir();path=root/"fixture.txt";path.write_text("Safe fixture")
    s.security.enable(sources=("files",),directories=(root,),user_confirmed=True)
    s.security.authorize_containment(user_confirmed=True)
    from test_ambient_connectors_security import exact
    result=exact(s,"security.file.quarantine",{"path":str(path),"sha256":"0"*64})
    assert not result.success and path.exists()
    outside=s.tmp/"outside.txt";outside.write_text("Outside the selected monitoring scope")
    result=exact(s,"security.file.quarantine",{"path":str(outside),"sha256":hashlib.sha256(outside.read_bytes()).hexdigest()})
    assert not result.success and outside.exists()
    assert "Unavailable" in s.security.snapshot()["network_isolation"]


def test_real_owned_process_flagged_then_exactly_approved_termination(system):
    import os,sys,subprocess
    from morice.security.collectors import file_hash
    from test_ambient_connectors_security import exact
    s=system
    # Keep the approved containment fixture to one actual PID, without a venv
    # redirector whose child is intentionally outside exact-PID authorization.
    child=subprocess.Popen([getattr(sys,"_base_executable",sys.executable),"-c","import time; time.sleep(30)"],creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        s.security.enable(sources=("processes",),process_ids=(child.pid,),user_confirmed=True)
        identity=s.security.select_process(child.pid)
        s.security.indicator(file_hash(identity["executable"]),"local:owned-harmless-process-fixture",
            "Controlled known-indicator process, not malware",user_confirmed=True)
        assert s.kernel.dispatch("security.scan",{}).success
        finding=s.security.snapshot()["findings"][0]
        assert finding["process_id"]==child.pid and finding["severity"]=="HIGH"
        assert "malware" not in finding["summary"].lower()
        s.security.authorize_containment(user_confirmed=True)
        result=exact(s,"security.process.terminate",identity)
        assert result.success and child.wait(timeout=3)==1
        assert any(i["state"]=="CONTAINED" and i["actions"] for i in s.security.snapshot()["incidents"])
    finally:
        if child.poll() is None:child.terminate();child.wait(timeout=3)


def test_action_event_causality_stops_same_watch_loop(system):
    from morice.kernel import CapabilityDescriptor,ExecutionResult,TaskStatus,VerificationResult,VerificationStatus
    s=system
    def loop(arguments,context):
        s.ambient.publish(AmbientEvent("fixture.ready","fixture","fixture",trust=Trust.LOCAL_OS),context=context)
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{"completed":True})
    s.kernel.registry.register(CapabilityDescriptor("fixture.loop","Controlled causal loop",supports_verification=True),loop,
        verifier=lambda result,expected,context:VerificationResult(VerificationStatus.VERIFIED,("Owned deterministic loop fixture.",)))
    from dataclasses import replace
    role=s.agents.roles.resolve("researcher")
    s.agents.roles._roles["researcher"]=replace(role,allowed_capabilities=(*role.allowed_capabilities,"fixture.loop"))
    s.ambient.create(Trigger("No loop","fixture.ready",action="fixture.loop",level=Autonomy.LOCAL_REVERSIBLE,
        enabled=True,cooldown_seconds=0),user_confirmed=True)
    s.ambient.publish(event());drain(s)
    assert s.ambient.metrics["matched"]==1 and len(s.ambient.store.receipts())==1
