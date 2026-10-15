"""Maximum supported cheap sweep and interactive responsiveness under real load."""
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from morice.research.runtime import ResearchRuntime
from morice.kernel.adapters import register_echo
from benchmark_device_mesh import process_info

with tempfile.TemporaryDirectory(prefix='morice-research-limits-') as directory:
    root=Path(directory);runtime=ResearchRuntime(root/'knowledge.db',root/'research')
    register_echo(runtime.kernel)
    try:
        spec={'title':'Maximum bounded benign mixture grid','objective':'Measure real bounded sweep throughput',
            'simulation_engine':'ideal_mixture_density','parameters':{'density_a':{'value':1000,'unit':'kg/m^3'},'density_b':{'value':2000,'unit':'kg/m^3'},'fraction_a':{'value':.5,'unit':''}},
            'experiment_type':'PARAMETER_SWEEP','parameter_ranges':{'fraction_a':{'min':0,'max':1,'unit':'','points':10000}}}
        start=time.perf_counter();prepared=runtime.laboratory.prepare(spec);compile_ms=(time.perf_counter()-start)*1000
        assert prepared['estimate']['planned_runs']==10000
        rss_before=process_info(os.getpid())['rss'];cpu_start=time.process_time();start=time.perf_counter()
        runtime.laboratory.start(prepared['id']);echo=[];calc=[];observed=[]
        while time.perf_counter()-start<120:
            row=runtime.laboratory.get(prepared['id']);observed.append(row['completed_runs'])
            if row['status'] not in {'QUEUED','RUNNING'}:break
            if len(echo)<250:
                at=time.perf_counter();assert runtime.kernel.dispatch('kernel.echo',{'text':'interactive'}).success;echo.append((time.perf_counter()-at)*1000)
                at=time.perf_counter();assert runtime.execute('research.calculate',{'expression':'x+1','inputs':{'x':{'value':1,'unit':''}}}).success;calc.append((time.perf_counter()-at)*1000)
            time.sleep(.01)
        assert row['status']=='COMPLETED' and row['completed_runs']==10000,row
        elapsed=time.perf_counter()-start
        result={'planned_runs':10000,'completed_runs':row['completed_runs'],'compile_ms':compile_ms,'execution_seconds':elapsed,'runs_per_second':10000/elapsed,
            'actual_progress_samples':len(observed),'observed_partial_progress':any(0<v<10000 for v in observed),'interactive_samples':len(echo),
            'interactive_echo_median_ms':statistics.median(echo),'interactive_echo_max_ms':max(echo),
            'interactive_calculation_median_ms':statistics.median(calc),'interactive_calculation_max_ms':max(calc),
            'cpu_seconds':time.process_time()-cpu_start,'rss_before_bytes':rss_before,'rss_after_bytes':process_info(os.getpid())['rss'],
            'disk_bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),'worker_limit':runtime.agents.limits.max_workers,
            'batch_size':25,'model_calls':0,'gpu_used':False,'vram_measured':False,'no_speedup_claim':'Each cheap model runs directly; parallel workers provide bounded orchestration and verified checkpoints, not guaranteed acceleration.'}
    finally:runtime.close()
    result['leases_after']=len(runtime.kernel.resources.snapshot());assert result['leases_after']==0
    Path('build/phase6-limits-benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
