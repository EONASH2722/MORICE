"""Read-only, redacted scan of tracked and publishable untracked files."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
names=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode('utf-8').split('\0')
public_database='morice/assets/spatial/cities.sqlite3'
patterns={
    'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'provider_credential':re.compile(r'(?<![\w-])(?:sk-(?:proj-)?[A-Za-z0-9_-]{28,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|hf_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})(?![\w-])'),
}
findings=[];files=[];databases=[]
for name in sorted(set(filter(None,names))):
    path=ROOT/name
    if not path.is_file():continue  # Preserved, intentional tracked deletions.
    relative=path.relative_to(ROOT).as_posix();size=path.stat().st_size
    if path.is_symlink():findings.append({'path':relative,'kind':'publishable_symlink'})
    if path.suffix.lower() in {'.gguf','.safetensors','.ckpt','.pem','.key','.pfx','.p12'} or path.name in {'settings.json','appearance.json','action-journal.json','.env','experience-profiles.json'} or path.name.startswith('.env.'):
        findings.append({'path':relative,'kind':'private_or_model_file'})
    if path.suffix.lower() in {'.sqlite','.sqlite3','.db'}:
        databases.append(relative)
        if relative!=public_database:findings.append({'path':relative,'kind':'private_database'})
    if size>50*1024*1024:findings.append({'path':relative,'kind':'oversized_file','bytes':size})
    data=path.read_bytes();files.append({'path':relative,'bytes':size,'sha256':hashlib.sha256(data).hexdigest()})
    if b'\0' in data[:4096]:continue
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:continue
    for number,line in enumerate(text.splitlines(),1):
        for kind,pattern in patterns.items():
            if pattern.search(line):findings.append({'path':relative,'line':number,'kind':kind,'value':'REDACTED'})
record={'status':'PASSED' if not findings else 'REVIEW_REQUIRED','scope':'Tracked and unignored publishable files. No value from a suspected secret is printed. Runtime/model directories and ignored files are outside this public-content scan.',
    'files':files,'file_count':len(files),'public_databases':databases,'findings':findings,
    'limitations':'Heuristic credential signatures do not prove absence of every possible secret; screenshots require separate visual/provenance review.'}
output=ROOT/'build/phase11-release-cleanliness.json';output.write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps({'status':record['status'],'file_count':len(files),'findings':findings}));raise SystemExit(bool(findings))
