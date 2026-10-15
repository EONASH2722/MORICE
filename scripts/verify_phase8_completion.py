"""Fail closed on stale/missing local Phase 8 completion evidence."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8-sig'))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def latest(name):
    paths=list((ROOT/name).glob('*/evidence.json'))
    assert paths,name
    path=max(paths,key=lambda item:item.stat().st_mtime_ns)
    value=json.loads(path.read_text(encoding='utf-8'))
    assert value.get('completed') and value['errors']==[],str(path)
    return path,value
report=ROOT/'docs/full-stack-hardening-report.md';text=report.read_text(encoding='utf-8')
numbers=[int(item) for item in re.findall(r'^(\d+)\. \*\*',text,re.M)]
assert numbers==list(range(1,87)),numbers
tests=(ROOT/'build/phase8-release-source-tests.log').read_text(encoding='utf-8-sig')
match=re.search(r'(\d+) passed, (\d+) subtests passed in ([\d.]+)s',tests)
assert match and 'FAILED ' not in tests,tests[-1000:]
test_count,subtests=int(match[1]),int(match[2]);assert test_count==875 and subtests==62
for name in ('build/phase8-release-repeat-1.log','build/phase8-release-repeat-2.log'):
    assert '31 passed, 3 subtests passed' in (ROOT/name).read_text(encoding='utf-8-sig')
package=read('build/phase8-package.json');startup=read('build/phase8-release-startup.json')
smoke=read('build/phase8-isolated-startup-smoke.json');audit=read('build/phase8-final-audit.json')
after=read('build/phase8-after-final.json');comparison=read('build/phase8-benchmark-comparison.json')
model=read('build/phase8-model.json');voice=read('build/phase8-voice.json')
wheel=Path(package['wheel']);executable=Path(startup['executable'])
assert digest(wheel)==package['sha256'] and package['sha256'] in text
assert digest(executable)==package['frozen']['exe_sha256']==startup['executable_sha256']
assert package['frozen']['exe_sha256'] in text
assert package['source_equal_modules']==166 and package['frozen']['source_equal_modules']==164
fingerprint=hashlib.sha256()
for path in sorted((ROOT/'morice').rglob('*.py')):
    fingerprint.update(str(path.relative_to(ROOT)).encode());fingerprint.update(path.read_bytes())
assert fingerprint.hexdigest()==after['source_sha256'], 'Current source differs from final benchmark.'
assert audit['module_count']==166 and audit['pip_check']['exit']==0
assert startup['system_path_only'] and startup['python_environment_removed'] and startup['exit_code']==0
assert not Path(startup['cwd']).is_relative_to(ROOT)
assert smoke['frozen'] and smoke['window_created'] and len(smoke['health'])==26 and smoke['roles']==9
assert smoke['critical_failures']==smoke['leases_after']==0 and smoke['shutdown']['clean']
assert all(row['leases_after']==row['critical_failures']==0 for row in after['runs'])
assert comparison['practical_budgets_pass'] and model['completed'] and model['owned_server_stopped'] and voice['completed']
soak_path,soak=latest('build/phase8-release-soak');native_path,native=latest('build/phase8-native-acceptance')
for demo in (soak,native):
    assert all(demo['shared_authorities'].values()) and demo['notification_after_all_verified']
    assert demo['dashboard']['status']==demo['resume']['status']=='verified' and demo['delivery']['verified']
    assert [row['live_nodes_including_coordinator'] for row in demo['mesh_scale']]==[5,10]
    assert demo['cleanup']['shutdown']['clean'] and demo['cleanup']['shutdown']['pending_workers']==0
    assert all(demo['cleanup'][name]==0 for name in ('leases','owned_processes','mesh_sockets','mesh_listeners'))
    for record in demo['dashboard']['artifacts']+demo['dashboard']['screenshots']:
        assert digest(record['path'])==record['sha256'],record['path']
    for name,sha in demo['research_export']['checksums'].items():
        assert digest(Path(demo['research_export']['directory'])/name)==sha,name
    remote=Path(demo['run_root'])/'node-1/node/Inbox/project.zip'
    assert digest(remote)==demo['delivery']['artifacts'][0]['sha256']
    with zipfile.ZipFile(remote) as archive:assert archive.testzip() is None
    database=Path(demo['run_root'])/'runtime/platform/orchestrator/knowledge/knowledge.db'
    with sqlite3.connect('file:'+database.as_posix()+'?mode=ro',uri=True) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone()==('ok',)
        assert connection.execute('SELECT status,count(*) FROM lab_runs GROUP BY status').fetchall()==[('VALID',10000)]
    connection.close()
assert native['interactive_during_build']['verified'] and native['interactive_during_build']['same_agent_workflows']
assert 'Running:' in native['interactive_during_build']['status_response']
assert soak['soak']['requested_seconds']==120
assert all(row['leases']==row['owned_processes']==0 and row['retained_workflows']<=20 and row['log_records']<=2000 for row in soak['soak']['samples'])
result={'phase':8,'status':'complete_for_controlled_local_scope','phase9_started':False,
    'created_utc':datetime.now(timezone.utc).isoformat(),'report':str(report),'required_report_items':len(numbers),
    'source_sha256':fingerprint.hexdigest(),
    'regression':{'passed':test_count,'subtests_passed':subtests,'seconds':float(match[3]),
        'log':'build/phase8-release-source-tests.log','phase8_cases':31,'repeat_passes':2},
    'package':package,'outside_checkout_startup':startup,
    'acceptance':{'native':str(native_path),'soak':str(soak_path),'shared_authorities':native['shared_authorities'],
        'counts':soak['soak']['counts'],'rss_growth_bytes':soak['soak']['rss_growth_bytes'],
        'real_sweep_valid_rows_each':10000,'sqlite_integrity_each':'ok','owned_resources_after':soak['cleanup'],
        'native_calculator_verified':True,'dashboard_and_remote_archive_hashes_rechecked':True,
        'desktop_mobile_screenshots_visually_inspected':True},
    'first_attempt':{'final_dashboard_verified':1,'final_remote_calculations_verified':9,
        'final_transfer_verified':1,'native_calculator_verified':1,'controlled_broken_builder_verified':0,
        'scope':'Final controlled operation legs; preceding failed harness/initial regression runs remain preserved. No product-wide success-rate estimate.'},
    'recovery':{'connector_faults_verified':8,'builder_repair_verified':1,'builder_resume_verified':1,
        'mesh_reconnect_verified':1,'crash_observation_without_replay':1,
        'scope':'Finite actual/controlled scenarios covered by final passing tests and acceptance evidence.'},
    'benchmarks':['build/phase8-before-corrected.json','build/phase8-after-final.json',
        'build/phase8-benchmark-comparison.json','build/phase8-model.json','build/phase8-voice.json'],
    'known_constraints':['Source-cache-sensitive samples and slower frozen startup','Measured direct-p50 security overhead',
        'Two-minute soak, no MTBF or exhaustive lifetime leak guarantee','GPU samples host-wide; cached model residency needs Phase 9 accounting',
        'Physical voice/wake/cloud TTS and semantic vision provider availability','Production OAuth/relay and physical Android/Linux not validated',
        'Frozen Builder needs external project toolchains; arbitrary project code is not an OS sandbox',
        'Native/DNS work can exceed deadlines and retains truthful ownership','Manual evidence/archive/quarantine retention',
        'Formal accessibility, signed release and all Windows/Python versions unvalidated']}
(ROOT/'build/phase8-completion.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'status':result['status'],'report_items':len(numbers),'tests':test_count,
    'subtests':subtests,'source_sha256':result['source_sha256'],'output':'build/phase8-completion.json'},indent=2))
