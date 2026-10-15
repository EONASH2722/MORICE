"""Inspect exact frozen executable bytecode and required public data/assets."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import types
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--output',default='build/phase10-frozen-current-parity.json');args=parser.parse_args()
directory=Path(args.directory).resolve();executable=directory/'MORICE.exe'
embedded=CArchiveReader(str(executable)).open_embedded_archive('PYZ.pyz')
def signature(code):
    return (code.co_code,code.co_names,code.co_varnames,code.co_freevars,code.co_cellvars,
        code.co_argcount,code.co_posonlyargcount,code.co_kwonlyargcount,code.co_flags,code.co_exceptiontable,
        tuple(signature(item) if isinstance(item,types.CodeType) else item for item in code.co_consts))
verified=[];omitted=[];fingerprint=hashlib.sha256()
for path in sorted((ROOT/'morice').rglob('*.py')):
    fingerprint.update(str(path.relative_to(ROOT)).encode());fingerprint.update(path.read_bytes())
    parts=list(path.relative_to(ROOT).with_suffix('').parts)
    if parts[-1]=='__init__':parts.pop()
    name='.'.join(parts)
    if name not in embedded.toc:omitted.append(name);continue
    compiled=compile(path.read_text(encoding='utf-8-sig'),str(path),'exec',dont_inherit=True,optimize=0)
    assert signature(compiled)==signature(embedded.extract(name)),name
    verified.append(name)
assert set(omitted)<={'morice.cli','morice.__main__'},omitted
data=[]
for source in [*(ROOT/'morice/assets/spatial').iterdir(),ROOT/'morice/assets/morice-logo-rgb.png',ROOT/'morice/assets/morice_logo.ico']:
    if source.is_file():
        relative=source.relative_to(ROOT);packaged=directory/'_internal'/relative
        assert packaged.read_bytes()==source.read_bytes(),str(relative)
        data.append(str(relative))
files=[path for path in directory.rglob('*') if path.is_file()]
assert not any(path.suffix in {'.gguf','.safetensors'} or path.name in {'.env','settings.json','action-journal.json','experience-profiles.json'} for path in files)
databases=[str(path.relative_to(directory)) for path in files if path.suffix=='.sqlite3']
assert databases==[str(Path('_internal/morice/assets/spatial/cities.sqlite3'))],databases
voice=directory/'_internal/voice_models/vosk-model-small-en-us-0.15'
assert voice.is_dir(),'Existing intentionally bundled Vosk must be preserved.'
record={'status':'FROZEN_ARCHIVE_PARITY_PASSED','production_window_factory':'morice.pyside_app.create_application_window','directory':str(directory),'files':len(files),
    'bytes':sum(path.stat().st_size for path in files),'exe_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
    'source_sha256':fingerprint.hexdigest(),'source_equal_modules':len(verified),'omitted_cli_modules':omitted,'asset_equal_files':data,
    'generative_media_or_gguf_weights_embedded':False,'existing_vosk_model_intentionally_embedded':True,
    'scope':'Embedded executable bytecode/public asset parity and exclusion scan; startup is a separate check.'}
(ROOT/args.output).write_text(json.dumps(record,indent=2),encoding='utf-8');print(json.dumps(record))
