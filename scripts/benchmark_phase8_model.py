"""Actual existing GGUF/server benchmark with usage counts and owned cleanup."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def gpu():
    try:
        return subprocess.run(["nvidia-smi","--query-gpu=name,memory.used,memory.total,utilization.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=5).stdout.strip()
    except (OSError,subprocess.TimeoutExpired):return None


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--model",default=str(ROOT/"Parable-Qwen3-4B-Claude-Fable-5-GGUF-Q5_K_M.gguf"))
    parser.add_argument("--output",default="build/phase8-model.json");args=parser.parse_args()
    with socket.socket() as probe:probe.bind(("127.0.0.1",0));port=probe.getsockname()[1]
    os.environ["MORICE_LLAMA_SERVER_PORT"]=str(port)
    from morice import llama_server
    from morice.kernel import CapabilityKernel,ExecutionContext,CancellationToken,TaskNode,TaskGraph
    from morice.kernel.adapters import register_calculation
    from morice.agent_runtime import AgentCoordinator
    from morice.agent_runtime.models import ModelReply
    import psutil
    output={"model":str(Path(args.model).resolve()),"server":llama_server.selected_server_path(),"hardware_gpu_scope":"Host-wide samples; server ownership and its RSS are measured separately.","gpu_before":gpu(),"requests":[]}
    owned=None;kernel=None;agents=None
    try:
        start=time.perf_counter();base=llama_server.ensure_server(args.model,n_ctx=2048,n_gpu_layers=0,n_threads=6,n_batch=256)
        output["cold_load_ms"]=(time.perf_counter()-start)*1000
        owned=llama_server._SERVER_PROCESS
        assert owned is not None,"Benchmark must own its server on an isolated port"
        process=psutil.Process(owned.pid)
        output["owned_server"]={"pid":owned.pid,"rss_bytes":process.memory_info().rss,"threads":process.num_threads(),"gpu_loaded":gpu()}
        def request(prompt,max_tokens=64,cancel=None):
            payload={"model":"local-gguf","messages":[{"role":"user","content":prompt}],"stream":True,
                "stream_options":{"include_usage":True},"max_tokens":max_tokens,"temperature":0,
                "chat_template_kwargs":{"enable_thinking":False}}
            start=time.perf_counter();first=None;chunks=[];usage={};timings={}
            with urlopen(Request(base+"/v1/chat/completions",json.dumps(payload).encode(),{"Content-Type":"application/json"}),timeout=90) as response:
                for line in response:
                    if cancel is not None and cancel.cancelled:break
                    if not line.startswith(b"data: "):continue
                    raw=line[6:].strip()
                    if raw==b"[DONE]":break
                    event=json.loads(raw)
                    if event.get("usage"):usage=event["usage"]
                    if event.get("timings"):timings=event["timings"]
                    for choice in event.get("choices",[]):
                        text=choice.get("delta",{}).get("content","") or choice.get("delta",{}).get("reasoning_content","")
                        if text:
                            if first is None:first=time.perf_counter()
                            chunks.append(text)
            value={"ttft_ms":(first-start)*1000 if first else None,"total_ms":(time.perf_counter()-start)*1000,
                "usage":usage,"server_timings":timings,"output_characters":sum(map(len,chunks)),"text":"".join(chunks)}
            if usage.get("completion_tokens") and first:
                value["measured_end_to_end_tokens_per_second"]=usage["completion_tokens"]/((time.perf_counter()-start))
            return value
        for name,prompt in (("cold_short","State the result of 2+3 in one sentence."),
            ("warm_short","State the result of 2+3 in one sentence."),
            ("long_context","Summarize this controlled scientific context in two sentences: "+"An ideal mixture uses additive constituent volumes; observed density is 1333.333 kg/m3. "*100),
            ("tool_context",'The verified calculator returned {"value":5,"verified":true}. Explain the result briefly.')):
            value=request(prompt);assert value["ttft_ms"] is not None
            output["requests"].append({"name":name,**value})
        kernel=CapabilityKernel();register_calculation(kernel);agents=AgentCoordinator(kernel)
        backend_measurements=[]
        def backend(*,prompt,model_id,max_output_tokens,context):
            value=request(prompt,min(64,max_output_tokens),context.cancellation_token);backend_measurements.append(value)
            return ModelReply(value["text"],model_id,value["usage"].get("prompt_tokens",0),value["usage"].get("completion_tokens",0))
        agents.models.configure("phase8-local",backend)
        graph=TaskGraph((TaskNode("agent.reason",{"prompt":"Explain the verified density of an ideal mixture briefly."},constraints={"role":"analyst"}),))
        completed=[]
        context=ExecutionContext(metadata={"model_config":{"selected_model":"phase8-local","max_output_tokens":64}})
        driver=threading.Thread(target=lambda:completed.append(agents.run(graph,context)),daemon=True);driver.start()
        direct=[]
        until=time.monotonic()+120
        while driver.is_alive() and time.monotonic()<until:
            stamp=time.perf_counter();result=kernel.dispatch("python.calculate",{"expression":"2+3"});assert result.success
            direct.append((time.perf_counter()-stamp)*1000);time.sleep(.01)
        driver.join(5);assert not driver.is_alive() and completed and completed[0].success
        output["agent"]={"metrics":completed[0].metrics,"backend":backend_measurements,"direct_requests_during_generation":len(direct),"direct_max_ms":max(direct,default=0)}
        output["owned_server_after"]={"rss_bytes":process.memory_info().rss,"threads":process.num_threads(),"gpu_host_wide":gpu()}
        output["completed"]=True
    except Exception as exc:
        output["completed"]=False;output["error"]=f"{type(exc).__name__}: {exc}"
    finally:
        if agents:agents.shutdown()
        if kernel:kernel.shutdown()
        llama_server.stop_server()
        output["owned_server_stopped"]=owned is None or owned.poll() is not None
        output["gpu_after_cleanup"]=gpu()
        target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(output,indent=2),encoding="utf-8")
    print(json.dumps({"output":args.output,"completed":output["completed"],"error":output.get("error"),"cold_load_ms":output.get("cold_load_ms"),"owned_server_stopped":output["owned_server_stopped"]}))
    return 0 if output["completed"] and output["owned_server_stopped"] else 1


if __name__=="__main__":raise SystemExit(main())
