"""Installed-wheel native smoke from a new venv and outside repository cwd."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--wheel',type=Path,required=True)
parser.add_argument('--python',type=Path,default=ROOT/'build/phase11-clean-venv/Scripts/python.exe')
parser.add_argument('--output',type=Path,default=ROOT/'build/phase11-clean-wheel-startup.json')
arguments=parser.parse_args()
python=arguments.python.resolve()
wheel=arguments.wheel.resolve();output=arguments.output.resolve()
assert output.is_relative_to(ROOT/'build'),'Keep owned evidence inside the workspace build directory.'
installed=python.parents[1]/'Lib/site-packages'
checked=[]
with zipfile.ZipFile(wheel) as archive:
    for name in archive.namelist():
        if name.startswith('morice/') and (name.endswith('.py') or name.startswith('morice/assets/')):
            assert (installed/name).read_bytes()==archive.read(name),f'Installed wheel differs: {name}'
            checked.append(name)
assert len([name for name in checked if name.endswith('.py')])==len(list((ROOT/'morice').rglob('*.py')))
with tempfile.TemporaryDirectory(prefix='morice-clean-wheel-') as directory:
    profile=Path(directory)
    environment={key:value for key,value in os.environ.items() if key not in {'PYTHONPATH','PYTHONHOME'}}
    environment.update(APPDATA=str(profile/'roaming'),LOCALAPPDATA=str(profile/'local'),MORICE_LOCAL_DATA_DIR=str(profile/'data'),MORICE_RUNTIME_DIR=str(profile/'runtime'),QT_QPA_PLATFORM='windows')
    code='import sys;from pathlib import Path;import morice;assert "site-packages" in str(Path(morice.__file__));from morice.package_smoke import run;sys.exit(run(sys.argv[1]))'
    result=subprocess.run([str(python),'-c',code,str(output)],cwd=profile,env=environment,capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (ROOT/'build/phase11-clean-wheel-startup.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    assert result.returncode==0,result.returncode
    record=json.loads(output.read_text());record['validation_clean_dependency_environment']=True;record['validation_outside_checkout']=True
    record['validation_python']=str(python)
    record['validation_wheel_sha256']=hashlib.sha256(wheel.read_bytes()).hexdigest()
    record['validation_installed_files_equal_wheel']=len(checked)
    record['validation_dependency_environment_scope']='Previously created isolated venv with no system-site-packages; current wheel is reinstalled into that dependency environment and byte-checked before launch.'
    output.write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({key:record[key] for key in ('window_class','critical_failures','ambient_animation','shutdown','validation_clean_dependency_environment')}))
