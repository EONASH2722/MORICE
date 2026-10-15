"""Crash, streaming, storage and burst evidence through existing authorities."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from morice.action_runtime import ActionBinding, ActionJournal, ActionMethod, Observation, VerifiedActionRuntime
from morice.kernel import CapabilityDescriptor, CapabilityKernel, ExecutionContext, ExecutionResult, TaskNode, TaskStatus, VerificationResult, VerificationStatus
from morice.unified_intelligence import PermissionState


def mutation_runtime(root, handler):
    kernel=CapabilityKernel()
    for name in ("file_write","browser_control"):kernel.permissions.controller.set_state(name,PermissionState.GRANTED)
    journal=ActionJournal(root/"attempts.json");actions=VerifiedActionRuntime(kernel,journal)
    kernel.registry.register(CapabilityDescriptor("phase8.crash_mutation","Owned crash fixture",required_permissions=("file_write",),supports_verification=True),handler,
        verifier=lambda *args:VerificationResult(VerificationStatus.INCONCLUSIVE))
    def observe(spec,ctx,*args):
        path=root/"effect.bin"
        return Observation(spec.action_id,"actual_file_read",{"sha256":hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""})
    actions.register("phase8.crash_mutation",ActionBinding(ActionMethod.FILESYSTEM,
        lambda inputs,expected:{"sha256":hashlib.sha256(b"one mutation").hexdigest()},observe,
        lambda spec,observed,before:VerificationResult(VerificationStatus.VERIFIED if observed.state==spec.desired_state else VerificationStatus.FAILED)))
    return kernel,actions


def test_owned_child_dies_after_actual_mutation_restart_observes_without_replay(tmp_path):
    child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--crash-child",str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        until=time.monotonic()+10
        while not (tmp_path/"ready").exists() and child.poll() is None and time.monotonic()<until:time.sleep(.01)
        assert (tmp_path/"ready").exists(),child.stderr.read().decode() if child.poll() is not None else "Owned child did not reach mutation"
        child.kill();child.wait(timeout=5)
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=5)
        child.stderr.close()
    calls=[]
    kernel,actions=mutation_runtime(tmp_path,lambda args,ctx:calls.append("replayed"))
    try:
        assert actions.journal.interrupted()[0]["phase"]=="executing"
        assert (tmp_path/"effect.bin").read_bytes()==b"one mutation"
        result=actions.reconcile(TaskNode("phase8.crash_mutation",{},task_id="owned-crash"),ExecutionContext())
        assert result.success and result.output["reconciled"] and result.verification.status==VerificationStatus.VERIFIED
        assert calls==[] and kernel.resources.snapshot()=={}
    finally:kernel.shutdown()


def test_streaming_audio_begins_before_generation_finishes_and_barge_in_is_bounded():
    from dataclasses import replace
    from morice.config import TTSConfig
    from morice.voice_runtime import VoiceRuntime
    release=threading.Event();first_audio=threading.Event();generation_done=threading.Event();stages={};sinks=[]
    class Sink:
        def __init__(self):self.aborted=False;self.writes=0
        def start(self,**kwargs):pass
        def write(self,data):
            assert not self.aborted;self.writes+=1
            stages.setdefault("first_audio_played",time.perf_counter());first_audio.set()
        def abort(self):self.aborted=True
        def close(self):pass
    class Provider:
        def stream_audio(self,chunks,config,cancel):
            stages.setdefault("first_tts_request_sent",time.perf_counter())
            iterator=iter(chunks);next(iterator);yield b"\x00\x01"*1000
            for part in iterator:
                if cancel.is_set():return
                yield b"\x00\x01"*1000
    def sink_factory(config):
        sink=Sink();sinks.append(sink);return sink
    def generated():
        yield "This is the first sentence, ready for streaming speech. "
        release.wait(3)
        yield "The remaining sentence follows after audio begins. "
        stages["generation_completed"]=time.perf_counter();generation_done.set()
    voice=VoiceRuntime(replace(TTSConfig(api_key="owned-fixture-credential"),enabled=True),
        provider_factory=lambda config:Provider(),sink_factory=sink_factory)
    try:
        handle=voice.speak_stream(generated())
        assert first_audio.wait(2) and not generation_done.is_set()
        assert stages["first_tts_request_sent"]<=stages["first_audio_played"]
        before=time.perf_counter();assert voice.interrupt();latency=time.perf_counter()-before
        assert latency<.5
        writes=sinks[0].writes;release.set();assert handle.wait(2) is not None
        assert sinks[0].aborted and sinks[0].writes==writes
        newer=voice.speak_stream(iter(["The new answer owns this speech request. "]))
        assert newer.wait(2) is not None and sinks[-1].writes>0
    finally:release.set();voice.shutdown()


def test_event_storm_unsubscribe_reentrant_callbacks_and_concurrent_publishers():
    from morice.kernel.events import EventBus,EventType,KernelEvent
    bus=EventBus(max_pending=1024);observed=[];lock=threading.Lock()
    def receive(event):
        with lock:observed.append(event.event_id)
    key=bus.subscribe(receive)
    threads=[threading.Thread(target=lambda:[bus.publish(KernelEvent(EventType.TASK_PROGRESS)) for _ in range(2500)]) for _ in range(4)]
    for thread in threads:thread.start()
    for thread in threads:thread.join(10);assert not thread.is_alive()
    assert len(observed)+bus.dropped_events==10000
    assert len(set(observed))==len(observed)
    bus.unsubscribe(key);bus.publish(KernelEvent(EventType.TASK_STARTED));count=len(observed)
    assert len(observed)==count and len(bus._queue)==0
    bus.clear()


def test_sqlite_interrupted_transaction_rolls_back_without_destroying_prior_evidence(tmp_path):
    from morice.research.store import ResearchStore
    store=ResearchStore(tmp_path/"knowledge.db")
    project=store.create("Owned rollback fixture")
    store.add(project,"observation","Retained evidence",{"x":1},"UNKNOWN")
    before=store.snapshot(project)
    with pytest.raises(RuntimeError):
        with store.connect() as db:
            db.execute("DELETE FROM research_records WHERE project_id=?",(project,))
            raise RuntimeError("Controlled transaction interruption")
    assert store.snapshot(project)==before


def test_corrupt_journal_blocks_action_but_direct_reads_remain_usable(tmp_path):
    (tmp_path/"attempts.json").write_text('{"version":1,"attempts":[')
    called=[];kernel,actions=mutation_runtime(tmp_path,lambda args,ctx:called.append(True))
    from morice.kernel.adapters import register_echo
    register_echo(kernel)
    try:
        result=kernel.dispatch("phase8.crash_mutation",{})
        assert not result.success and result.status==TaskStatus.BLOCKED and called==[]
        assert kernel.dispatch("kernel.echo",{"text":"still usable"}).success
        assert kernel.resources.snapshot()=={}
    finally:kernel.shutdown()


@pytest.mark.parametrize("contents", ['{', '[]', '{"version":99}', '{"version":1,"graph":{},"records":null}'])
def test_corrupt_agent_checkpoint_preserves_bytes_and_admits_no_work(tmp_path,contents):
    from morice.agent_runtime import AgentCoordinator
    kernel=CapabilityKernel();agents=AgentCoordinator(kernel);path=tmp_path/"checkpoint.json";path.write_text(contents)
    try:
        with pytest.raises((ValueError,KeyError)):agents.restore(path)
        assert path.read_text()==contents and not agents.status() and not kernel.resources.snapshot()
    finally:agents.shutdown();kernel.shutdown()


def test_crash_diagnostics_redact_canary_without_removing_useful_stack(tmp_path):
    from morice.runtime_services import CrashRecoveryManager
    recovery=CrashRecoveryManager(tmp_path)
    try:
        raise RuntimeError("Authorization: Bearer crash-private-canary")
    except RuntimeError as exc:recovery.record_exception(type(exc),exc,exc.__traceback__)
    value=recovery.crash_path.read_text()
    assert "crash-private-canary" not in value and "RuntimeError" in value and "test_crash_diagnostics" in value


if __name__=="__main__" and len(sys.argv)>1 and sys.argv[1]=="--crash-child":
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    root=Path(sys.argv[2])
    def effect(args,ctx):
        (root/"effect.bin").write_bytes(b"one mutation");(root/"ready").write_text("mutation completed before verification")
        threading.Event().wait(30)
        return ExecutionResult(TaskStatus.SUCCEEDED,True,{})
    kernel,actions=mutation_runtime(root,effect)
    kernel.run_task(TaskNode("phase8.crash_mutation",{},task_id="owned-crash"),ExecutionContext())
