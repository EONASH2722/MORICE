"""Real controlled HTTP, signed receiver, DPAPI and selected Windows process costs."""
import hashlib,hmac,json,os,statistics,subprocess,sys,tempfile,time,tracemalloc,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/"tests")]
from test_ambient_connectors_security import fixture_server,system,drain
from morice.ambient import AmbientEvent,Trigger,Trust
from morice.runtime_services import _process_memory_mb

def timed(callback,repeats=20):
    values=[]
    for _ in range(repeats):
        start=time.perf_counter();callback();values.append((time.perf_counter()-start)*1000)
    return {"median_ms":statistics.median(values),"max_ms":max(values),"samples":len(values)}

with tempfile.TemporaryDirectory(prefix="morice-ambient-bench-") as directory:
    server=fixture_server.__wrapped__();url,state=next(server)
    fixture=system.__wrapped__(Path(directory),(url,state));s=next(fixture)
    child=None
    try:
        s.ambient.start(user_confirmed=True)
        before=_process_memory_mb();cpu=time.process_time();wall=time.perf_counter();time.sleep(2.5)
        elapsed=time.perf_counter()-wall;cpu_elapsed=time.process_time()-cpu
        result={"idle_seconds":elapsed,"idle_cpu_seconds":cpu_elapsed,"idle_one_core_percent":100*cpu_elapsed/elapsed,
            "idle_ram_before_mb":before,"idle_ram_after_mb":_process_memory_mb(),"model_calls":0}
        s.ambient.stop();s.ambient._stop.clear()
        counter=[0]
        def dispatch():
            counter[0]+=1;s.ambient.publish(AmbientEvent("benchmark.no_action","owned-fixture","local",trust=Trust.LOCAL_OS,dedupe_key=str(counter[0])));s.ambient.tick()
        result["event_dispatch"]=timed(dispatch,100)
        watch=Trigger("Benchmark notice","benchmark.notice",enabled=True,cooldown_seconds=0)
        s.ambient.create(watch,user_confirmed=True)
        def trigger():
            counter[0]+=1;s.ambient.publish(AmbientEvent("benchmark.notice","owned-fixture","local",trust=Trust.LOCAL_OS,dedupe_key=str(counter[0])));s.ambient.tick()
        result["trigger_and_verified_notification"]=timed(trigger,20)
        result["condition_evaluation"]=timed(lambda:s.ambient.dry_run(watch.trigger_id,AmbientEvent("benchmark.notice","owned-fixture","local",trust=Trust.LOCAL_OS)),500)
        def read():assert s.kernel.dispatch("connector.fixture.issue.read",{"number":1}).success
        result["provider_read"]=timed(read,30)
        result["polling"]=timed(lambda:s.kernel.dispatch("connector.fixture.events.poll",{}),10)
        secret="benchmark-signed-secret-local-only"
        s.provider.configure_webhook(secret,user_confirmed=True)
        receiver=s.ambient.connectors.start_webhooks(user_confirmed=True)
        def webhook():
            counter[0]+=1
            body=json.dumps({"action":"assigned","assignee":{"login":"fixture-owner"},"repository":{"full_name":"owner/repo"},"issue":{"id":counter[0],"number":counter[0],"state":"open"}}).encode()
            headers={"X-Hub-Signature-256":"sha256="+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest(),"X-GitHub-Event":"issues","X-GitHub-Delivery":"fixture-"+str(counter[0])}
            with urllib.request.urlopen(urllib.request.Request(receiver+"/webhooks/fixture",body,headers),timeout=3) as response:assert response.status==202
            s.ambient.tick()
        result["signed_webhook_http"]=timed(webhook,20)
        selected=s.tmp/"selected";selected.mkdir()
        for i in range(4):(selected/f"fixture-{i}.txt").write_text("Owned harmless metadata fixture")
        child=subprocess.Popen([getattr(sys,"_base_executable",sys.executable),"-c","import time; time.sleep(30)"],creationflags=subprocess.CREATE_NO_WINDOW)
        s.security.enable(sources=("files","processes"),directories=(selected,),process_ids=(child.pid,),user_confirmed=True)
        def scan():assert s.kernel.dispatch("security.scan",{}).success
        result["selected_security_collection"]=timed(scan,20)
        s.security.disable()
        drain(s)
        before=_process_memory_mb();tracemalloc.start();start=time.perf_counter()
        for i in range(10000):s.ambient.publish(AmbientEvent("benchmark.burst","owned-fixture","local",trust=Trust.LOCAL_OS,dedupe_key=str(i)))
        elapsed=time.perf_counter()-start;current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        result["burst"]={"events":10000,"seconds":elapsed,"queue_depth":len(s.ambient._queue),"dropped":s.ambient.metrics["dropped"],
            "traced_peak_bytes":peak,"rss_before_mb":before,"rss_after_mb":_process_memory_mb()}
        result["interactive_calculation_during_backlog"]=timed(lambda:s.kernel.dispatch("python.calculate",{"expression":"2+3"}),50)
        drain(s);result["model_calls"]=s.ambient.metrics["model_calls"]
        result["agent_graph_retention_bound"]=len(s.agents._graphs)
        result["leases_after"]=len(s.kernel.resources.snapshot())
        assert result["burst"]["queue_depth"]<=256 and result["model_calls"]==result["leases_after"]==0
        Path("build/phase7-benchmark.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    finally:
        if child and child.poll() is None:child.terminate();child.wait(timeout=3)
        try:next(fixture)
        except StopIteration:pass
        try:next(server)
        except StopIteration:pass
