"""Source-referenced candidates; only a real regression confirms a finding."""
from __future__ import annotations
import ast, hashlib, json, re, time
from pathlib import Path
from .contracts import Budget, Limits, LimitReached, redacted, sha256

SKIP={'.git','node_modules','build','dist','.venv','__pycache__','vendor','.gradle','output','artifacts','.pytest_cache','.morice','.idea','.vscode'}
CALLS={'eval':('dynamic_evaluation','high'),'exec':('dynamic_execution','high'),
    'pickle.loads':('unsafe_deserialization','high'),'pickle.load':('unsafe_deserialization','high'),
    'yaml.load':('yaml_loader_review','medium'),'os.system':('shell_execution','high')}

def call_name(node):
    if isinstance(node,ast.Name):return node.id
    if isinstance(node,ast.Attribute):return call_name(node.value)+'.'+node.attr
    return ''

def scan(root,limits=None):
    root=Path(root).resolve(strict=True);budget=Budget(limits or Limits());rows=[];inventory=[];count=0;total=0;errors=[]
    if not root.is_dir() or root==Path(root.anchor) or str(root).startswith('\\\\'):raise ValueError('Choose one local project directory.')
    pending=[root]
    while pending:
        folder=pending.pop();budget.check()
        for path in sorted(folder.iterdir()):
            budget.check()
            if path.is_symlink():continue
            if path.is_dir():
                if path.name not in SKIP:pending.append(path)
                if len(pending)>2000:raise LimitReached()
                continue
            if count>=300:pending.clear();errors.append({'reason':'source file count budget reached'});break
            if path.name in {'package.json','requirements.txt','pyproject.toml','Cargo.toml','pom.xml','build.gradle','package-lock.json','pnpm-lock.yaml'}:
                inventory.append({'file':str(path.relative_to(root)),'sha256':sha256(path) if path.stat().st_size<1024**2 else None,
                    'advisory_status':'NOT_CHECKED','reason':'No advisory database was supplied; no CVE is inferred from a package name.'})
            if path.suffix not in {'.py','.js','.ts','.jsx','.tsx','.java','.kt','.c','.cpp','.rs'}:continue
            if path.stat().st_size>256*1024:errors.append({'file':str(path.relative_to(root)),'reason':'file size limit'});continue
            count+=1;total+=path.stat().st_size
            if total>16*1024**2:pending.clear();errors.append({'reason':'source byte budget reached'});break
            raw=path.read_bytes();text=raw.decode('utf-8',errors='replace');source_hash=hashlib.sha256(raw).hexdigest()
            def add(line,category,severity,reason):
                fingerprint=hashlib.sha256((str(path.relative_to(root))+str(line)+category+source_hash).encode()).hexdigest()
                rows.append({'finding_id':fingerprint[:20],'file':str(path.relative_to(root)),'line':line,'category':category,
                    'severity':severity,'state':'POSSIBLE','confidence':'Static candidate; data flow/reproduction required.',
                    'evidence':reason,'source_sha256':source_hash,'fix_status':'not_applied'})
            if path.suffix=='.py':
                try:tree=ast.parse(text)
                except SyntaxError:errors.append({'file':str(path.relative_to(root)),'reason':'Python parse failure'});continue
                for node in ast.walk(tree):
                    if isinstance(node,ast.Call):
                        name=call_name(node.func)
                        if name in CALLS:
                            category,severity=CALLS[name];add(node.lineno,category,severity,'AST call to '+name+'; inspect whether untrusted input reaches it.')
                        if name.startswith('subprocess.') and any(k.arg=='shell' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords):
                            add(node.lineno,'shell_command_review','high','AST subprocess call enables shell=True.')
                        if name.endswith('.execute') and node.args and isinstance(node.args[0],(ast.JoinedStr,ast.BinOp)):
                            add(node.lineno,'sql_construction_review','high','Query expression is constructed dynamically; parameter binding needs review.')
                    if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str) and len(node.value.value)>=8:
                        if any(isinstance(t,ast.Name) and re.search(r'password|secret|api_key|access_token',t.id,re.I) for t in node.targets):
                            add(node.lineno,'embedded_secret_review','high','A credential-like variable has a literal value; the value is withheld.')
            else:
                for index,line in enumerate(text.splitlines(),1):
                    if re.search(r'\beval\s*\(|\binnerHTML\s*=|dangerouslySetInnerHTML',line):
                        add(index,'untrusted_content_review','medium','Static pattern needs language-aware/data-flow review; no exploitability claim.')
            if len(rows)>500:pending.clear();rows=rows[:500];errors.append({'reason':'finding count budget reached'});break
    partial=any('budget reached' in row.get('reason','') for row in errors)
    return {'status':'RESOURCE_LIMIT_REACHED' if partial else 'COMPLETED','root':str(root),'files_scanned':count,'source_bytes':total,'findings':rows,
        'dependency_inventory':inventory[:50],'errors':errors[:50],'seconds':time.monotonic()-budget.started,
        'limitation':'Python AST and bounded source patterns. Candidate findings are not verified vulnerabilities; advisory checks require a supplied trusted database.'}

