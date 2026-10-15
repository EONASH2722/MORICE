"""Sequential/parallel measurements of the same actual local build pipeline."""
from __future__ import annotations
import argparse
import json
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from morice.project_build.contracts import Requirement
from morice.project_build.planning import scaffold
from morice.runtime_services import RuntimeServices, _process_memory_mb, _nvidia_gpu_metrics

def large_manifest():
    files=[]
    for scope in ("backend","frontend","utilities","data"):
        for index in range(12):
            content="def add(a,b):\n    return a+b\n"+"\n".join(f"def transform_{n}(value):\n    return (value * {n+1}) % 997\n" for n in range(120))
            files.append({"path":f"{scope}/module_{index}.py","content":content})
    files.extend([{"path":"main.py","content":"from backend.module_0 import add\nprint(add(2,3))\n"},
        {"path":"tests/test_integration.py","content":"import unittest\nfrom backend.module_0 import add\nfrom frontend.module_0 import transform_2\nclass IntegrationTests(unittest.TestCase):\n    def test_add(self): self.assertEqual(add(2,3),5)\n    def test_frontend(self): self.assertEqual(transform_2(2),6)\n"}])
    return {"files":files}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output",default="build/phase4-benchmark.json"); args=parser.parse_args()
    results={}; ram=[]; stop=threading.Event(); started=time.perf_counter(); cpu=time.process_time()
    def sample():
        while not stop.is_set(): ram.append(_process_memory_mb()); stop.wait(.02)
    sampler=threading.Thread(target=sample,daemon=True); sampler.start()
    with tempfile.TemporaryDirectory(prefix="morice-phase4-bench-") as directory:
        root=Path(directory); services=RuntimeServices(root/"runtime",project_root=root); builder=services.autonomous_builder.project_runtime
        def approve(task):
            if task.capability_requirement in {"filesystem.apply_patch","terminal.run"}:
                return services.agent.tools.permissions.grant(task.capability_requirement,task.inputs)
            return ""
        try:
            for name in ("small","multi_scope"):
                measured={}; peaks={}; cards=[]
                for mode in ("sequential","parallel"):
                    samples=[]
                    for run in range(3):
                        project=root/f"{name}-{mode}-{run}"
                        manifest=scaffold("Build a Python calculator",project) if name=="small" else large_manifest()
                        owners=None if name=="small" else {v:[f"{v}/*"] for v in ("backend","frontend","utilities","data","tests")}
                        if owners: owners["integration"]=["main.py"]
                        run_services=RuntimeServices(root/f"runtime-{name}-{mode}-{run}",project_root=project)
                        builder=run_services.autonomous_builder.project_runtime
                        try:
                            session=builder.create(project,"Build a Python addition project",manifest,ownership=owners,
                                requirements=[Requirement("Actual output equals 5",check={"kind":"command_output","contains":"5"})],
                                runtime={"kind":"command","command":[sys.executable,"main.py","2","3"]} if name=="small" else {"kind":"command","command":[sys.executable,"main.py"]})
                            def run_approve(task):
                                if task.capability_requirement in {"filesystem.apply_patch","terminal.run"}:
                                    return run_services.agent.tools.permissions.grant(task.capability_requirement,task.inputs)
                                return ""
                            begin=time.perf_counter()
                            result=builder.build(session,authorize=run_approve,sequential=mode=="sequential")
                            samples.append((time.perf_counter()-begin)*1000)
                            if not result.success: raise AssertionError(result.result_card())
                            cards.append(result.result_card()); peaks[mode]=max(peaks.get(mode,0),result.metrics["worker_peak"])
                        finally:
                            run_services.shutdown()
                    measured[mode+"_ms"]=statistics.median(samples); measured[mode+"_samples_ms"]=samples
                results[name]={**measured,"speedup":measured["sequential_ms"]/measured["parallel_ms"],"peak_workers":peaks,"verified_runs":len(cards)}
            # Direct typed fast action stays outside the agent runtime.
            from morice.kernel.adapters import register_echo
            from morice.kernel import TaskNode, ExecutionContext
            register_echo(services.kernel) if not services.kernel.registry.search("kernel.echo") else None
            direct=[]
            for _ in range(250):
                begin=time.perf_counter(); result=services.kernel.run_task(TaskNode("kernel.echo",{"value":"fast"}), ExecutionContext()); direct.append((time.perf_counter()-begin)*1000)
                assert result.success
            results["direct_echo_median_ms"]=statistics.median(direct)
            results["leases_after"]=len(services.kernel.resources.snapshot())
        finally:
            services.shutdown()
    stop.set(); sampler.join(1); elapsed=time.perf_counter()-started; gpu,vram=_nvidia_gpu_metrics()
    results.update(wall_seconds=elapsed,cpu_process_seconds=time.process_time()-cpu,average_process_cpu_one_core_percent=(time.process_time()-cpu)/elapsed*100,
        peak_process_ram_mb=max(ram,default=0),gpu_utilization_end_percent=gpu,gpu_vram_used_end_mb=vram,
        notes=["No artificial waits: actual isolated patches, AST checks, archive builds, unit tests, CLI runs and artifact readback.",
            "Medians of three fresh projects per mode. Fresh services/journal for every sample; planning/create time excluded equally. Implementation through final artifact/source verification included.",
            "CPU/RAM describe this process; short-lived child-process CPU/RAM are not included. GPU/VRAM are host end samples, not inference peaks.",
            "No model loaded; deterministic evidence does not establish real model latency or repair quality."])
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(results,indent=2),encoding="utf-8"); print(json.dumps(results,indent=2))

if __name__=="__main__": main()
