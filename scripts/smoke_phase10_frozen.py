"""Run the frozen app's production factory from an owned external profile."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--output',default='build/phase10-frozen-current-startup.json');args=parser.parse_args()
executable=Path(args.directory).resolve()/'MORICE.exe';assert executable.is_file()
executable_digest=hashlib.sha256(executable.read_bytes()).hexdigest()
output=(ROOT/args.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='morice-production-frozen-') as directory:
    root=Path(directory);environment={key:value for key,value in os.environ.items() if key not in {'PYTHONPATH','PYTHONHOME','MORICE_SMOKE_UI'}}
    environment.update(APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local'),MORICE_LOCAL_DATA_DIR=str(root/'data'),
        MORICE_RUNTIME_DIR=str(root/'runtime'),MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',
        MORICE_DISABLE_FIRST_RUN='1',MORICE_NODE_NETWORK='0',MORICE_REDUCE_MOTION='1',MORICE_PROBE_BACKGROUND='1',QT_QPA_PLATFORM='windows',
        PATH=os.pathsep.join((str(Path(os.environ['SystemRoot'])/'System32'),os.environ['SystemRoot'])))
    result=subprocess.run([str(executable),'--morice-smoke-test',str(output)],cwd=root,env=environment,
        capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==0,(result.returncode,result.stdout[-1200:],result.stderr[-1200:])
    record=json.loads(output.read_text(encoding='utf-8'))
    orb_output=output.with_name(output.stem+'-orb.json')
    orb_result=subprocess.run([str(executable),'--morice-orb-probe',str(orb_output)],cwd=root,env=environment,
        capture_output=True,text=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert orb_result.returncode==0,(orb_result.returncode,orb_result.stderr[-1200:])
    record['orb_pet']=json.loads(orb_output.read_text(encoding='utf-8'));record['orb_pet']['isolated_pet_process']=True
    assert record['frozen'] and record['production_window_factory'] and record['window_class']=='RenovatedWindow'
    assert record['critical_failures']==record['leases_after']==0 and record['shutdown']['clean']
    assert record['spatial_result']['metres']>13_000_000
    assert hashlib.sha256(executable.read_bytes()).hexdigest()==executable_digest
    record.update(validation_executable=str(executable),validation_exe_sha256=executable_digest,
                  validation_outside_checkout=True,validation_system_only_path=True)
    output.write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({key:record[key] for key in ('frozen','production_window_factory','window_class','ui_ticks','critical_failures','leases_after','shutdown')}))
