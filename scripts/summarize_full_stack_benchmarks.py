"""Report measured regressions and practical budgets without hiding outliers."""
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
before=json.loads((ROOT/'build/phase8-before-corrected.json').read_text())
after=json.loads((ROOT/'build/phase8-after-final.json').read_text())
def metric(document,name):
    if name=='startup_ms':return document['startup']['p50_ms']
    if name=='idle_cpu_one_core_percent':return statistics.median(x[name] for x in document['runs'])
    if name.startswith('direct_'):return statistics.median(x['direct_calculation'][name.removeprefix('direct_')] for x in document['runs'])
    return statistics.median(x['idle_after'][name] for x in document['runs'])
names=['startup_ms','idle_cpu_one_core_percent','rss_bytes','threads','handles','sockets','children','direct_p50_ms','direct_p95_ms']
rows={}
for name in names:
    old=metric(before,name);new=metric(after,name)
    rows[name]={'before':old,'after':new,'change_percent':100*(new-old)/old if old else None,
        'relative_25_percent_regression':bool(old and new>1.25*old)}
baseline=ROOT/'build/phase7-package/morice_ai-0.8.0-py3-none-any.whl'
result={'baseline_wheel_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
    'before':'build/phase8-before-corrected.json','after':'build/phase8-after-final.json','metrics':rows,
    'budgets':{'source_startup_sample_max_ms':5000,'direct_calculation_sample_p95_ms':10},
    'practical_budgets_pass':after['startup']['max_ms']<5000 and all(x['direct_calculation']['p95_ms']<10 for x in after['runs']),
    'new_sources_clean_shutdown':all(x['leases_after']==x['critical_failures']==0 for x in after['runs']),
    'samples':{'startup_each':3,'direct_each_process':300,'event_each_process':10000,'idle_each_seconds':3},
    'outliers':{'before_startup_ms':before['startup']['max_ms'],'after_startup_ms':after['startup']['max_ms'],
        'before_direct_max_ms':max(x['direct_calculation']['max_ms'] for x in before['runs']),
        'after_direct_max_ms':max(x['direct_calculation']['max_ms'] for x in after['runs'])},
    'interpretation':'Direct p50 has a measured regression from diagnostic redaction and execution guards; its added absolute cost is reported, while p95 remains within the practical 10 ms budget. Startup samples are sequential, filesystem-cache-sensitive observations, not causal speedup proof; n=3 p95 is the largest sample. GPU metrics remain host-wide. Earlier observer-contaminated measurements are superseded.'}
(ROOT/'build/phase8-benchmark-comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
