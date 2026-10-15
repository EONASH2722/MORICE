"""Actual public evidence, model runs and export reproduction; no publication."""
from __future__ import annotations
import csv
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from morice.research.runtime import ResearchRuntime
from morice.research.service import ResearchService
from morice.research.artifacts import export_package
from morice.research.literature import LiteratureEvidence,evaluate_hypothesis
from morice.research.validation import convergence,calibration
from benchmark_device_mesh import process_info

def fetch(url,path):
    if not path.exists():
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MORICE controlled research verification'}),timeout=30) as stream:
            data=stream.read(25*1024**2+1)
        if len(data)>25*1024**2:raise ValueError('Public evidence exceeds bounds')
        path.write_bytes(data)
    return {'url':url,'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def wait(manager,identifier):
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        row=manager.get(identifier)
        if row['status'] not in {'QUEUED','RUNNING'}:return manager.get(identifier,True)
        time.sleep(.02)
    manager.cancel(identifier);raise TimeoutError('Controlled benchmark deadline')

def main():
    root=ROOT/'build/phase6-evidence';root.mkdir(parents=True,exist_ok=True)
    result={'source_scope':'Actual public paper and dataset; image, biomedical observations and controlled model inputs are explicitly synthetic.',
            'timings_ms':{},'cpu_models':True,'gpu_models':False,'vram_measurement':None}
    result['sources']=[fetch('https://journals.plos.org/plosmedicine/article/file?id=10.1371/journal.pmed.0020124&type=printable',root/'paper.pdf'),
        fetch('https://journals.plos.org/plosmedicine/article/file?id=10.1371/journal.pmed.1004085&type=printable',root/'correction.pdf'),
        fetch('https://archive.ics.uci.edu/static/public/53/iris.zip',root/'iris.zip')]
    with zipfile.ZipFile(root/'iris.zip') as archive:raw=archive.read('iris.data').decode('utf-8')
    rows=list(csv.reader(io.StringIO(raw)));rows=[r for r in rows if r]
    assert len(rows)==150
    data=root/'iris.csv'
    with data.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.writer(stream);writer.writerow(['sepal_length [cm]','sepal_width [cm]','petal_length [cm]','petal_width [cm]','class']);writer.writerows(rows)
    result['dataset_derivation']='Header added to actual UCI iris.data; source zip hash retained. Dataset versions have documented source corrections; do not silently substitute corrected rows.'
    from PIL import Image,ImageDraw
    photo=root/'fixture.png';image=Image.new('RGB',(320,200),'white');ImageDraw.Draw(image).text((15,15),'Synthetic controlled research diagram',fill='black');image.save(photo)
    runtime=ResearchRuntime(root/'knowledge.db',root/'research')
    cpu_before=time.process_time();rss_before=process_info(os.getpid())['rss']
    def timed(name,fn):
        begin=time.perf_counter();value=fn();result['timings_ms'][name]=(time.perf_counter()-begin)*1000;return value
    try:
        project=runtime.create('Do the ingested sources and observed dataset support the stated descriptive hypothesis?')
        assumption=runtime.store.add(project,'assumption','Use the retrieved UCI version without correcting individual rows',{'scope':'Dataset description; not a population causal claim'},'USER_DATA')
        hypothesis=runtime.store.add(project,'hypothesis','Mean sepal length is at least 6 cm',{'status':'PROPOSED'},'HYPOTHESIS')
        service=ResearchService(runtime.store.database,runtime.directory,runtime=runtime)
        ingested=timed('paper_csv_image_ingestion',lambda:service.run('Analyze the scientific paper and dataset',project_id=project,attachments=[root/'paper.pdf',root/'correction.pdf',data,photo]))
        assert not ingested['failures'],ingested['failures']
        sources=[r for r in runtime.project(project).records if r['kind']=='source'];paper=next(r for r in sources if r['title']=='paper.pdf')
        result['paper']={'pages':paper['payload']['metadata']['page_count'],'parsed_characters':len(paper['payload']['text']),
            'section_names':list(paper['payload']['sections']),'figure_context_candidates':len(paper['payload'].get('figure_context',[])),
            'warnings':paper['payload']['warnings'],'sha256':paper['payload']['sha256']}
        normalized=' '.join(paper['payload']['text'].split());start=normalized.lower().index('positive predictive value');excerpt=normalized[start:start+24]
        citation=LiteratureEvidence(runtime.store).cite(project,paper['id'],'Essay discusses the predictive value of research findings',excerpt=excerpt,
            citation={'title':'Why Most Published Research Findings Are False','author':'John P. A. Ioannidis','date':'2005-08-30',
                'doi':'10.1371/journal.pmed.0020124','url':'https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.0020124',
                'correction_doi':'10.1371/journal.pmed.1004085','type':'methodological essay; not clinical trial'})
        correction=next(r for r in sources if r['title']=='correction.pdf')
        runtime.store.relate(project,paper['id'],correction['id'],'invalidated_by')
        result['literature']={'citation_id':citation,'correction_source_id':correction['id'],'same_study_version_note':'2022 correction addresses Table 2 parentheses; not an independent confirming study.'}
        dataset=next(r for r in runtime.project(project).records if r['kind']=='dataset')
        result['dataset']={'rows':dataset['payload']['result']['rows'],'duplicates':dataset['payload']['result']['duplicate_rows'],
            'mean_sepal_length_cm':dataset['payload']['result']['columns'][0]['mean']}
        values=[float(r[0]) for r in rows]
        stats=timed('actual_dataset_statistics',lambda:runtime.run_recorded(project,'research.statistics',{'values':values,'unit':'cm'},dependencies=[dataset['id'],assumption]))
        assert stats['execution'].success
        result['hypothesis']=evaluate_hypothesis(runtime.store,project,hypothesis,[stats['record_id'],paper['id'],correction['id']],criterion={'min':6},actual=stats['execution'].output['mean'],provenance='CALCULATED',field='result.mean')
        calc=timed('unit_calculation_first',lambda:runtime.run_recorded(project,'research.calculate',{'expression':'0.5*m*v**2','inputs':{'m':{'value':2,'unit':'kg'},'v':{'value':3,'unit':'m/s'}},'output_unit':'J'},dependencies=[assumption]))
        assert calc['execution'].success and calc['execution'].output['result']['value']==9
        result['calculation']=calc['execution'].output['result'];result['agent_runtime_bypassed_for_simple_actions']=runtime._agents is None
        samples=[]
        for _ in range(100):
            begin=time.perf_counter();actual=runtime.execute('research.calculate',{'expression':'x+1','inputs':{'x':{'value':1,'unit':''}}});assert actual.success;samples.append((time.perf_counter()-begin)*1000)
        result['timings_ms']['warm_calculation_median']=statistics.median(samples)
        base={'title':'Benign ideal density sweep','objective':'Compare ideal volume-additive density','simulation_engine':'ideal_mixture_density',
            'parameters':{'density_a':{'value':1000,'unit':'kg/m^3'},'density_b':{'value':2000,'unit':'kg/m^3'},'fraction_a':{'value':.5,'unit':''}},
            'experiment_type':'PARAMETER_SWEEP','parameter_ranges':{'fraction_a':{'min':0,'max':1,'unit':'','points':1001}},'seed':42,'dependencies':[assumption]}
        result['experiments']=[]
        for label,updates in [('sweep',{}),('monte_carlo',{'experiment_type':'MONTE_CARLO','samples':1000,'constraints':{'density':{'min':{'value':1500,'unit':'kg/m^3'}}}}),
                ('optimization',{'experiment_type':'OPTIMIZATION','strategy':'coarse_refine','parameter_ranges':{'fraction_a':{'min':0,'max':1,'unit':'','points':101}}}),
                ('sensitivity',{'experiment_type':'SENSITIVITY_ANALYSIS','parameter_ranges':{'fraction_a':{'min':0,'max':1,'unit':'','points':21}}})]:
            prepared=timed(label+'_compile',lambda:runtime.laboratory.prepare({**base,**updates},project_id=project))
            def execute():
                runtime.laboratory.start(prepared['id']);return wait(runtime.laboratory,prepared['id'])
            completed=timed(label+'_execute',execute);assert completed['status']=='COMPLETED',completed['error']
            result['experiments'].append({'type':label,'id':completed['id'],'runs':completed['completed_runs'],'best':completed['summary']['best_observed'],
                'violation_fraction':completed['summary'].get('constraint_violation_fraction'),'artifacts':completed['summary']['artifacts']})
        particle={'mass':1,'x0':0,'y0':0,'vx':2,'vy':3,'ax':0,'ay':-1,'duration':2}
        trajectories=[runtime.run_recorded(project,'research.trajectory',{'parameters':particle,'steps':n,'method':'euler'}) for n in [10,20,40]]
        result['particle_convergence']=convergence([r['execution'].output['rows'][-1]['y'] for r in trajectories],.1)
        result['particle_errors_m']=[r['execution'].output['position_error_m'] for r in trajectories]
        result['model_data']=runtime.execute('research.model_compare',{'predicted':[1,2,3],'measured':[1,2.2,2.8],'unit':'m'}).output
        result['held_out_calibration']=calibration([0,1,2],[1,3,5],[3,4],[7,9])
        material=runtime.run_recorded(project,'research.material',{'parameters':{'length':1,'alpha_a':1e-5,'alpha_b':2e-5,'temperature_change':100},'allowable_mismatch_m':.0001})
        assert material['execution'].success;result['material']=material['execution'].output
        design=runtime.run_recorded(project,'research.cad',{'width':{'value':2,'unit':'cm'},'height':{'value':3,'unit':'cm'},'depth':{'value':4,'unit':'cm'},'density':{'value':1000,'unit':'kg/m^3'}},dependencies=[assumption])
        assert design['execution'].success;result['design']=design['execution'].output
        bio=runtime.run_recorded(project,'research.statistics',{'method':'bootstrap_mean','values':[2,4,3,6,1,5,4,7,2,3], 'unit':'mmHg','independent':True,'seed':42,'resamples':999})
        assert bio['execution'].success;result['biomedical']={'synthetic':True,'clinical_validation':False,'statistics':bio['execution'].output}
        unavailable=runtime.run_recorded(project,'research.simulate',{'tool_id':'uninstalled_cfd','parameters':{}})
        assert not unavailable['execution'].success;result['tool_failure']=unavailable['execution'].to_dict()
        package=timed('export_package',lambda:export_package(runtime.store.snapshot(project),root/'exports'));result['package']=package
        reproduced=timed('reproduction_subprocess',lambda:subprocess.run([sys.executable,str(Path(package['directory'])/'reproduce.py')],capture_output=True,text=True,timeout=45,env={**os.environ,'PYTHONPATH':str(ROOT)}))
        assert reproduced.returncode==0,reproduced.stderr;result['reproduced_output']=reproduced.stdout
        runtime.store.revise(project,assumption,{'scope':'Assumption changed after the export; dependent outputs must be recomputed'})
        result['stale_records']=runtime.integrity_metrics(project)['stale'];assert result['stale_records']>5
        result['structured_resume']=timed('reopen_project',lambda:runtime.project(project).resume_context())
        result['cpu_seconds']=time.process_time()-cpu_before;result['rss_before_bytes']=rss_before;result['rss_after_bytes']=process_info(os.getpid())['rss']
        result['disk_bytes']=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
        result['roles']=len(runtime.agents.roles.all());result['shared_worker_manager']=type(runtime.agents.manager).__name__ if hasattr(runtime.agents,'manager') else type(runtime.agents.workers).__name__
        result['optional_tools']={name:{'installed':importlib.util.find_spec(name) is not None,'version':importlib.metadata.version(name) if importlib.util.find_spec(name) is not None else None} for name in ['numpy','sympy','pint','pypdf','openpyxl','scipy','matplotlib','cadquery']}
        result['model_calls']=0;result['completed']=True
    finally:runtime.close()
    result['leases_after']=len(runtime.kernel.resources.snapshot());assert result['leases_after']==0
    (ROOT/'build/phase6-benchmark.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k in {'completed','timings_ms','cpu_seconds','rss_before_bytes','rss_after_bytes','disk_bytes','leases_after','roles','model_calls','stale_records','calculation','reproduced_output'}},indent=2))

if __name__=='__main__':main()
