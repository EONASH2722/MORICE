"""Actual offline candidate verification; secrets never appear in receipts."""
from __future__ import annotations
import base64, hashlib, io, json, os, shutil, struct, tempfile, time, zipfile
from pathlib import Path
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from .contracts import Budget, Cancelled, IntegrityFailure, LimitReached, Limits, Outcome, Unsupported, WrongKey, member_name, sha256
from .forensics import MAGIC, signature, zip_metadata

def binary(value,maximum=128*1024**2):
    if not isinstance(value,str) or len(value)>maximum*2:raise IntegrityFailure()
    try:result=base64.b64decode(value,validate=True)
    except (ValueError,TypeError):raise IntegrityFailure() from None
    if len(result)>maximum:raise LimitReached()
    return result

def read_envelope(path,limits):
    if Path(path).stat().st_size>limits.input_bytes:raise LimitReached()
    payload=Path(path).read_bytes()
    if len(payload)>limits.input_bytes or not payload.startswith(MAGIC):raise IntegrityFailure()
    try:
        value=json.loads(payload[len(MAGIC):]);header=value['header'];cipher=binary(value['ciphertext'],limits.input_bytes)
        if set(value)!={'header','ciphertext'} or set(header)!={'version','algorithm','nonce','kdf'}:raise ValueError()
        if type(header['version']) is not int or header['version']!=1 or header['algorithm'] not in {'AES-256-GCM','CHACHA20-POLY1305'}:raise ValueError()
        if len(binary(header['nonce'],12))!=12 or len(cipher)<16:raise ValueError()
        kdf=header['kdf']
        if kdf=={'name':'direct-key'}:pass
        elif (set(kdf)=={'name','salt','iterations'} and kdf['name']=='PBKDF2-HMAC-SHA256'
            and type(kdf['iterations']) is int and 10000<=kdf['iterations']<=1000000 and len(binary(kdf['salt'],32)) in range(16,33)):pass
        else:raise ValueError()
        return header,cipher
    except (ValueError,TypeError,KeyError,UnicodeError):raise IntegrityFailure() from None

def envelope_fixture(plaintext,*,password=None,key=None,algorithm='AES-256-GCM',iterations=100000):
    """Documented fixture envelope around standard AEAD, not a universal file format."""
    if (password is None)==(key is None):raise ValueError('Supply one secret type.')
    kdf={'name':'direct-key'} if key is not None else {'name':'PBKDF2-HMAC-SHA256','salt':base64.b64encode(os.urandom(16)).decode(),'iterations':iterations}
    header={'version':1,'algorithm':algorithm,'nonce':base64.b64encode(os.urandom(12)).decode(),'kdf':kdf}
    if key is None:key=derive(password,header)
    aad=json.dumps(header,sort_keys=True,separators=(',',':')).encode()
    provider=AESGCM if algorithm=='AES-256-GCM' else ChaCha20Poly1305
    cipher=provider(key).encrypt(binary(header['nonce']),plaintext,aad)
    return MAGIC+json.dumps({'header':header,'ciphertext':base64.b64encode(cipher).decode()},separators=(',',':')).encode()

def derive(password,header):
    kdf=header['kdf']
    return PBKDF2HMAC(algorithm=hashes.SHA256(),length=32,salt=binary(kdf['salt']),iterations=kdf['iterations']).derive(password.encode('utf-8'))

def decrypt_envelope(path,password,key,destination,budget):
    header,cipher=read_envelope(path,budget.limits);budget.check()
    if header['kdf']['name']=='direct-key':
        if key is None:raise WrongKey()
        material=key
    else:
        if password is None:raise WrongKey()
        material=derive(password,header)
    if len(material)!=32:raise WrongKey()
    provider=AESGCM if header['algorithm']=='AES-256-GCM' else ChaCha20Poly1305
    aad=json.dumps(header,sort_keys=True,separators=(',',':')).encode()
    try:plain=provider(material).decrypt(binary(header['nonce']),cipher,aad)
    except InvalidTag:raise WrongKey() from None
    budget.check(len(plain));output=Path(destination)/'recovered.bin'
    with output.open('xb') as stream:stream.write(plain)
    return [{'path':str(output),'sha256':sha256(output),'bytes':len(plain),'detected_format':signature(plain[:4096])}], 'AEAD tag authenticated, metadata authenticated, complete plaintext readback SHA-256.'

def decrypt_zip(path,password,key,destination,budget):
    import pyzipper
    rows=zip_metadata(path,budget.limits)
    if not any(r['password_based'] for r in rows):raise Unsupported()
    if password is None:raise WrongKey()
    artifacts=[]
    try:
        with pyzipper.AESZipFile(path) as archive:
            archive.setpassword(password.encode('utf-8'))
            for info in archive.infolist():
                budget.check();name=member_name(info.filename)
                if info.is_dir():continue
                output=Path(destination)/name
                output.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(info) as source,output.open('xb') as target:
                    while block:=source.read(65536):budget.check(len(block));target.write(block)
                artifacts.append({'path':str(output),'logical_name':name,'sha256':sha256(output),'bytes':output.stat().st_size})
    except RuntimeError:raise WrongKey() from None
    except (zipfile.BadZipFile,pyzipper.BadZipFile):raise IntegrityFailure() from None
    if not artifacts:raise IntegrityFailure()
    return artifacts,'Every member fully read; AES HMAC or legacy CRC validated by ZIP reader; output readback SHA-256. Legacy CRC is not cryptographic authentication.'

def decrypt_pdf(path,password,key,destination,budget):
    from pypdf import PdfReader,PdfWriter
    reader=PdfReader(path,strict=True)
    if not reader.is_encrypted:raise Unsupported()
    if password is None or not reader.decrypt(password):raise WrongKey()
    budget.check();writer=PdfWriter()
    if len(reader.pages)>budget.limits.members:raise LimitReached()
    for page in reader.pages:budget.check();writer.add_page(page)
    output=Path(destination)/'recovered.pdf'
    with output.open('xb') as stream:writer.write(stream)
    budget.check(output.stat().st_size)
    check=PdfReader(output,strict=True)
    if check.is_encrypted or len(check.pages)!=len(reader.pages):raise IntegrityFailure()
    return [{'path':str(output),'sha256':sha256(output),'bytes':output.stat().st_size,'pages':len(check.pages)}], 'PDF password verifier accepted; complete document rewrite and page-tree readback. PDF standard security is not AEAD authentication.'

def provider_for(path):
    with Path(path).open('rb') as stream:kind=signature(stream.read(256))
    return {'ZIP':decrypt_zip,'MORICE_AEAD':decrypt_envelope,'PDF':decrypt_pdf}.get(kind)

def candidate_values(passwords,conventions=()):
    """Only explicit candidates/templates; no personal-profile collection."""
    seen=set();values=[]
    for password in passwords:
        if not isinstance(password,str) or len(password)>512:raise ValueError('Candidate exceeds input budget.')
        if password not in seen:seen.add(password);values.append(password)
        if len(values)>100000:raise LimitReached()
    for convention in conventions:
        template=convention['template'];substitutions=convention.get('values',[])
        if not isinstance(template,str) or len(template)>256 or template.count('{value}')!=1:raise ValueError('Use one explicit {value} substitution.')
        if len(substitutions)>10000:raise LimitReached()
        for item in substitutions:
            value=template.replace('{value}',str(item))
            if len(value)>512:raise LimitReached()
            if value not in seen:seen.add(value);values.append(value)
            if len(values)>100000:raise LimitReached()
    return values

def feasibility(path,passwords=(),key=None,limits=None):
    limits=limits or Limits()
    if Path(path).stat().st_size>limits.input_bytes:raise LimitReached()
    provider=provider_for(path);count=len(passwords);direct=False
    with Path(path).open('rb') as source:kind=signature(source.read(256))
    if kind=='MORICE_AEAD':
        header,_=read_envelope(path,limits);direct=header['kdf']['name']=='direct-key'
        if direct:count=int(key is not None)
    base={'candidate_count':count,'bounded_test_count':min(count,limits.candidates),'cpu':'One sequential verification worker; no GPU.',
        'ram_budget_bytes':512*1024**2,'time_limit_seconds':limits.seconds,'success_promised':False}
    if provider is None:return {**base,'status':'UNSUPPORTED_FORMAT','feasible':False,'reason':'No installed implemented recovery adapter for this format.'}
    with Path(path).open('rb') as source:kind=signature(source.read(256))
    if kind=='MORICE_AEAD':
        header,_=read_envelope(path,limits)
        if header['kdf']['name']=='direct-key' and key is None:
            return {**base,'status':'MISSING_KEY','feasible':False,'reason':'A random 256-bit direct key is required; exhaustive recovery is not practical.'}
    if not count:return {**base,'status':'MISSING_KEY','feasible':False,'reason':'Supply an authorized password list, documented convention or matching key.'}
    # Actual measured single-candidate rejection, isolated from export.
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='morice-recovery-cost-') as directory:
        try:provider(path,'MORICE-cost-probe-'+os.urandom(16).hex(),os.urandom(32) if direct else None,directory,Budget(limits))
        except (WrongKey,IntegrityFailure):pass
    measured=max(.00001,time.perf_counter()-started)
    estimate=measured*min(count,limits.candidates)
    return {**base,'status':'READY','feasible':True,'seconds_per_rejection_measured':measured,
        'estimated_candidate_seconds':estimate,'estimate_scope':'Measured wrong-candidate rejection; successful full decryption/readback can take longer.',
        'likely_budget_limited':estimate>limits.seconds or count>limits.candidates}

def recover(path,destination,passwords=(),key=None,limits=None,progress=lambda value:None,cancel=lambda:False):
    limits=limits or Limits();budget=Budget(limits,cancel);provider=provider_for(path)
    if Path(path).stat().st_size>limits.input_bytes:return {'status':'RESOURCE_LIMIT_REACHED','tested':0,'artifacts':[]}
    with Path(path).open('rb') as source:kind=signature(source.read(256))
    if kind=='MORICE_AEAD':
        try:
            header,_=read_envelope(path,limits)
            if header['kdf']['name']=='direct-key':passwords=();key=key
            elif not passwords:key=None
        except IntegrityFailure:return {'status':'INTEGRITY_CHECK_FAILED','tested':0,'artifacts':[]}
    elif not passwords:key=None
    original=sha256(path);tested=0;total=len(passwords) if passwords else (1 if key is not None else 0)
    result={'tested':0,'total_candidates':total,'source_sha256':original,'artifacts':[],'attempts':[]}
    try:
        budget.check()
        if provider is None:raise Unsupported()
        if not total:return {**result,'status':Outcome.MISSING_KEY.value}
        work=Path(destination);work.mkdir(parents=True,exist_ok=True)
        candidates=passwords if passwords else [None]
        for candidate in candidates:
            budget.check()
            if tested>=limits.candidates:raise LimitReached()
            tested+=1
            attempt=work/('attempt-'+str(tested));attempt.mkdir()
            try:
                artifacts,verification=provider(path,candidate,key,attempt,budget)
                budget.check()
                if sha256(path)!=original:raise IntegrityFailure()
                for artifact in artifacts:
                    if sha256(artifact['path'])!=artifact['sha256']:raise IntegrityFailure()
                return {**result,'status':Outcome.RECOVERED.value,'tested':tested,'artifacts':artifacts,
                    'verification':verification,'seconds':time.monotonic()-budget.started,
                    'attempts':result['attempts']+[{'candidate_index':tested,'outcome':'RECOVERED'}]}
            except WrongKey:
                shutil.rmtree(attempt)
                if len(result['attempts'])<200:result['attempts'].append({'candidate_index':tested,'outcome':'WRONG_KEY'})
            except BaseException:
                shutil.rmtree(attempt,ignore_errors=True);raise
            finally:
                elapsed=time.monotonic()-budget.started
                if tested==1 or tested==total or tested%max(1,total//100)==0:
                    progress({'tested':tested,'total_candidates':total,'remaining_candidates':max(0,total-tested),
                        'seconds':elapsed,'estimated_remaining_seconds':(elapsed/tested)*(total-tested)})
        state=Outcome.WRONG_KEY if total==1 else Outcome.CANDIDATES_EXHAUSTED
    except Cancelled:state=Outcome.CANCELLED
    except LimitReached:state=Outcome.RESOURCE_LIMIT_REACHED
    except Unsupported:state=Outcome.UNSUPPORTED_FORMAT
    except (IntegrityFailure,zipfile.BadZipFile,ValueError,OSError):state=Outcome.INTEGRITY_CHECK_FAILED
    return {**result,'status':state.value,'tested':tested,'seconds':time.monotonic()-budget.started,
        'limitation':'Authentication failure may mean a wrong secret or damaged ciphertext; no plaintext is exported without verification.'}
