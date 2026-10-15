"""Source parity and actual isolated Phase 7 wheel imports; no publishing."""
import hashlib,json,os,subprocess,sys,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];wheel=next((root/"build/phase7-package").glob("*.whl"))
modules=[]
with zipfile.ZipFile(wheel) as archive:
    assert archive.testzip() is None
    for package in ("kernel","agent_runtime","action_runtime","project_build","device_mesh","research","ambient","connectors","security"):
        for source in (root/"morice"/package).glob("*.py"):
            name=source.relative_to(root).as_posix();assert archive.read(name)==source.read_bytes(),name;modules.append(name)
    entries=["morice/runtime_services.py","morice/pyside_app.py","morice/desktop_environment.py"]
    for name in entries:assert archive.read(name)==(root/name).read_bytes(),name
smoke='''import sys,json,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from morice.ambient import AmbientEvent,Trigger,AmbientService
from morice.connectors import GitHubProvider,ConnectorOperation
from morice.security import SecurityService
from morice.kernel import CapabilityKernel
from morice.agent_runtime import AgentCoordinator
from morice.desktop_environment import NotificationManager,AutomationEngine,DesktopPermissionManager
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);kernel=CapabilityKernel();agents=AgentCoordinator(kernel);notes=NotificationManager(root)
    service=AmbientService(kernel,agents,AutomationEngine(root,DesktopPermissionManager(),notes),notes,root/"knowledge.db")
    assert not service.enabled
    assert service.kernel is kernel and service.agents is agents
    print(json.dumps({"ambient_import":__import__("morice.ambient",fromlist=["x"]).__file__,"roles":len(agents.roles.all()),"monitoring_off":not service.enabled}))
    service.close();agents.shutdown();kernel.shutdown()
    assert not kernel.resources.snapshot()
'''
process=subprocess.run([sys.executable,"-I","-c",smoke,str(wheel)],capture_output=True,text=True,timeout=30,
    env={k:v for k,v in os.environ.items() if k!="PYTHONPATH"})
assert process.returncode==0,process.stdout+process.stderr
result={"wheel":str(wheel),"bytes":wheel.stat().st_size,"sha256":hashlib.sha256(wheel.read_bytes()).hexdigest(),
    "source_equal_modules":len(modules),"phase7_modules":sum(any('/'+p+'/' in n for p in ("ambient","connectors","security")) for n in modules),
    "source_equal_entrypoints":len(entries),"zip_integrity":True,"actual_wheel_smoke":json.loads(process.stdout),
    "scope":"Local source wheel. Frozen Windows executable and physical Android/Linux artifacts were not rebuilt in Phase 7."}
assert str(wheel) in result["actual_wheel_smoke"]["ambient_import"]
Path("build/phase7-package.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
