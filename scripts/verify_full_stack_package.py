"""Local archive integrity, full Python source parity and isolated wheel imports."""
import hashlib,json,os,subprocess,sys,tempfile,types,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
wheel=next((root/'build/phase8-package').glob('*.whl'));modules=[]
with zipfile.ZipFile(wheel) as archive:
    assert archive.testzip() is None
    for source in (root/'morice').rglob('*.py'):
        name=source.relative_to(root).as_posix()
        assert archive.read(name)==source.read_bytes(),name
        modules.append(name)
    assert not any(n.endswith(('.gguf','.env')) or 'settings.json' in n or 'secrets' in n for n in archive.namelist())
smoke='''import sys,json,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from morice.kernel import CapabilityKernel
from morice.agent_runtime import AgentCoordinator
from morice.action_runtime import ActionJournal,VerifiedActionRuntime
from morice.research.runtime import ResearchRuntime
from morice.ambient import AmbientService
from morice.device_mesh.node import create_node
from morice.desktop_environment import NotificationManager,AutomationEngine,DesktopPermissionManager
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory);kernel=CapabilityKernel();agents=AgentCoordinator(kernel);actions=VerifiedActionRuntime(kernel,ActionJournal(root/'journal.json'))
 research=ResearchRuntime(root/'knowledge.db',root/'research',kernel=kernel,agents=agents,actions=actions)
 result=research.execute('research.calculate',{'expression':'2+3','inputs':{}});assert result.success and result.output['result']['value']==5
 notes=NotificationManager(root);ambient=AmbientService(kernel,agents,AutomationEngine(root,DesktopPermissionManager(),notes),notes,root/'knowledge.db')
 assert research.kernel is ambient.kernel is kernel and research.agents is ambient.agents is agents and not ambient.enabled
 ambient.close();research.close();agents.shutdown();kernel.shutdown();assert not kernel.resources.snapshot()
 print(json.dumps({'package':__import__('morice').__file__,'roles':len(agents.roles.all()),'calculation_verified':True,'leases':0}))
'''
with tempfile.TemporaryDirectory(prefix='morice-wheel-cwd-') as directory:
    result=subprocess.run([sys.executable,'-I','-c',smoke,str(wheel)],cwd=directory,
        env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'},capture_output=True,text=True,timeout=45)
assert result.returncode==0,result.stdout+result.stderr
value={'wheel':str(wheel),'bytes':wheel.stat().st_size,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
    'source_equal_modules':len(modules),'zip_integrity':True,'isolated_import':json.loads(result.stdout)}
assert str(wheel) in value['isolated_import']['package']
frozen=root/'build/phase8-frozen/MORICE'
if frozen.exists() and '--wheel-only' not in sys.argv:
    files=[p for p in frozen.rglob('*') if p.is_file()]
    assert not any(p.suffix=='.gguf' or p.name in {'.env','settings.json','action-journal.json'} for p in files)
    value['frozen']={'directory':str(frozen),'files':len(files),'bytes':sum(p.stat().st_size for p in files),
        'exe_sha256':hashlib.sha256((frozen/'MORICE.exe').read_bytes()).hexdigest(),'model_weights_embedded':False}
    # Inspect the actual executable's embedded archive, not only a build cache.
    # Filenames and marshal string interning differ between source and packaging.
    # Compare executable instructions, arguments, names and nested constants.
    from PyInstaller.archive.readers import CArchiveReader
    embedded=CArchiveReader(str(frozen/'MORICE.exe')).open_embedded_archive('PYZ.pyz')
    def signature(code):
        return (code.co_code,code.co_names,code.co_varnames,code.co_freevars,code.co_cellvars,
            code.co_argcount,code.co_posonlyargcount,code.co_kwonlyargcount,code.co_flags,
            code.co_exceptiontable,
            tuple(signature(item) if isinstance(item,types.CodeType) else item for item in code.co_consts))
    verified=[];omitted=[]
    for source in (root/'morice').rglob('*.py'):
        parts=list(source.relative_to(root).with_suffix('').parts)
        if parts[-1]=='__init__': parts.pop()
        name='.'.join(parts)
        if name not in embedded.toc:
            omitted.append(name);continue
        compiled=compile(source.read_text(encoding='utf-8-sig'),str(source),'exec',dont_inherit=True,optimize=0)
        assert signature(compiled)==signature(embedded.extract(name)),name
        verified.append(name)
    required=('morice.kernel','morice.agent_runtime','morice.action_runtime','morice.project_build',
        'morice.device_mesh','morice.research','morice.ambient','morice.connectors','morice.security')
    assert not any(name.startswith(required) for name in omitted),omitted
    assert set(omitted)<= {'morice.cli','morice.__main__'},omitted
    value['frozen']['source_equal_modules']=len(verified)
    value['frozen']['omitted_cli_modules']=omitted
(root/'build/phase8-package.json').write_text(json.dumps(value,indent=2),encoding='utf-8');print(json.dumps(value,indent=2))
