"""Validate source parity of the local Phase 6 wheel without publishing."""
import hashlib
import json
import zipfile
import os
import subprocess
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];wheel=next((root/'build/phase6-package').glob('*.whl'))
modules=[]
with zipfile.ZipFile(wheel) as archive:
    assert archive.testzip() is None
    for package in ['kernel','agent_runtime','action_runtime','project_build','device_mesh','research']:
        for source in (root/'morice'/package).glob('*.py'):
            name=source.relative_to(root).as_posix();assert archive.read(name)==source.read_bytes(),name;modules.append(name)
    entries=['morice/runtime_services.py','morice/pyside_app.py','morice/settings.py','morice/node_protocol.py','morice/visualization.py']
    for name in entries:assert archive.read(name)==(root/name).read_bytes(),name
result={'wheel':str(wheel),'bytes':wheel.stat().st_size,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
        'source_equal_modules':len(modules),'research_modules':sum('/research/' in n for n in modules),'source_equal_entrypoints':len(entries),'zip_integrity':True,
        'scope':'Source wheel; frozen Windows executable and hardware Android/Linux tests were not rebuilt by Phase 6.'}
smoke='''import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from morice.research.runtime import ResearchRuntime
with tempfile.TemporaryDirectory(prefix="morice-research-wheel-") as directory:
    root=Path(directory);runtime=ResearchRuntime(root/"knowledge.db",root/"research")
    try:
        calculation=runtime.execute("research.calculate",{"expression":"x**2","inputs":{"x":{"value":3,"unit":"m"}},"output_unit":"m^2"})
        assert calculation.success and calculation.output["result"]["value"]==9
        experiment=runtime.laboratory.prepare({"title":"Wheel smoke","objective":"Verify packaged model compilation","simulation_engine":"ideal_mixture_density","parameters":{"density_a":{"value":1000,"unit":"kg/m^3"},"density_b":{"value":2000,"unit":"kg/m^3"},"fraction_a":{"value":.5,"unit":""}}})
        assert experiment["estimate"]["model_fingerprint"]
        print(json.dumps({"imported_from":__import__("morice.research.runtime",fromlist=["x"]).__file__,"calculation":calculation.output["result"],"compiler_fingerprint":experiment["estimate"]["model_fingerprint"]}))
    finally:runtime.close()
    assert not runtime.kernel.resources.snapshot()
'''
process=subprocess.run([sys.executable,'-I','-c',smoke,str(wheel)],cwd=root,capture_output=True,text=True,timeout=30,
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'})
assert process.returncode==0,process.stdout+process.stderr
result['actual_wheel_smoke']=json.loads(process.stdout)
assert str(wheel) in result['actual_wheel_smoke']['imported_from']
(root/'build/phase6-package.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
