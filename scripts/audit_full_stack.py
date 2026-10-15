"""Read-only source/dependency inventory; import graphs distinguish lazy edges."""
from __future__ import annotations
import ast
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--output',default='build/phase8-final-audit.json');arguments=parser.parse_args()
paths={}
for source in (ROOT/'morice').rglob('*.py'):
    parts=list(source.relative_to(ROOT).with_suffix('').parts)
    if parts[-1]=='__init__':parts.pop()
    paths['.'.join(parts)]=source
authorities={'CapabilityKernel','TaskGraph','WorkerManager','AgentCoordinator',
    'SharedTaskState','ResourceManager','PermissionManager','VerifiedActionRuntime',
    'ProjectBuildRuntime','ResearchRuntime','AmbientService'}
definitions={name:[] for name in authorities};edges={name:set() for name in paths}
top_edges={name:set() for name in paths};counts={};fingerprint=hashlib.sha256()
for name,path in sorted(paths.items()):
    data=path.read_bytes();fingerprint.update(str(path.relative_to(ROOT)).encode());fingerprint.update(data)
    tree=ast.parse(data);counts[name]=len(data.splitlines())
    package=name if path.name=='__init__.py' else name.rpartition('.')[0]
    top_ids=set()
    def collect(nodes):
        for node in nodes:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):continue
            if isinstance(node,(ast.Import,ast.ImportFrom)):top_ids.add(id(node))
            for child in ast.iter_child_nodes(node):
                if not isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):collect([child])
    collect(tree.body)
    for node in ast.walk(tree):
        if isinstance(node,ast.ClassDef) and node.name in definitions:
            definitions[node.name].append({'module':name,'line':node.lineno})
        targets=[]
        if isinstance(node,ast.Import):targets=[item.name for item in node.names]
        elif isinstance(node,ast.ImportFrom):
            base=node.module or ''
            if node.level:base=importlib.util.resolve_name('.'*node.level+base,package)
            targets=[base]+[base+'.'+item.name for item in node.names]
        for target in targets:
            if target in paths:
                edges[name].add(target)
                if id(node) in top_ids:top_edges[name].add(target)
def components(graph):
    index={};low={};stack=[];active=set();result=[]
    def visit(name):
        index[name]=low[name]=len(index);stack.append(name);active.add(name)
        for target in graph[name]:
            if target not in index:visit(target);low[name]=min(low[name],low[target])
            elif target in active:low[name]=min(low[name],index[target])
        if low[name]==index[name]:
            group=[]
            while True:
                target=stack.pop();active.remove(target);group.append(target)
                if target==name:break
            if len(group)>1:result.append(sorted(group))
    for name in graph:
        if name not in index:visit(name)
    return sorted(result,key=lambda group:(-len(group),group))
dependencies={}
for name in ('PySide6','numpy','Pillow','sounddevice','vosk','pypdf','pint','cryptography',
    'psutil','PyInstaller','build','pytest','pytest-subtests','playwright','llama-cpp-python'):
    try:dependencies[name]=importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:dependencies[name]=None
check=subprocess.run([sys.executable,'-m','pip','check'],capture_output=True,text=True,timeout=60)
value={'module_count':len(paths),'source_sha256':fingerprint.hexdigest(),
    'largest_modules':sorted(counts.items(),key=lambda item:-item[1])[:15],
    'authority_definitions':definitions,'top_level_cycles':components(top_edges),
    'all_scope_cycles':components(edges),'dependencies':dependencies,
    'pip_check':{'exit':check.returncode,'output':check.stdout.strip()},
    'python':sys.version,'platform':platform.platform(),
    'limits':'Static package import graph includes exports. Function imports are lazy. Native dependency availability and runtime initialization remain separate; no CVE-database audit.'}
expected={'CapabilityKernel':'morice.kernel.execution','TaskGraph':'morice.kernel.tasks',
    'WorkerManager':'morice.agent_runtime.workers','AgentCoordinator':'morice.agent_runtime.coordinator',
    'SharedTaskState':'morice.agent_runtime.state','ResourceManager':'morice.kernel.resources',
    'PermissionManager':'morice.kernel.permissions','VerifiedActionRuntime':'morice.action_runtime.runtime',
    'ProjectBuildRuntime':'morice.project_build.runtime','ResearchRuntime':'morice.research.runtime',
    'AmbientService':'morice.ambient.service'}
value['execution_authorities']={name:[item for item in definitions[name] if item['module']==module]
    for name,module in expected.items()}
assert all(len(items)==1 for items in value['execution_authorities'].values())
value['same_name_other_domains']={name:[item for item in definitions[name] if item['module']!=expected[name]]
    for name in expected if any(item['module']!=expected[name] for item in definitions[name])}
(ROOT/arguments.output).write_text(json.dumps(value,indent=2),encoding='utf-8')
print(json.dumps({'modules':len(paths),'top_level_cycles':value['top_level_cycles'],
    'all_scope_cycle_sizes':[len(items) for items in value['all_scope_cycles']],
    'pip_check':value['pip_check']},indent=2))
