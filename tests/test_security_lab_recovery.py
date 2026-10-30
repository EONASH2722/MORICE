"""Owned encrypted fixtures; no external accounts or private files."""
import base64,gzip,json,os,struct,time,zipfile
from pathlib import Path
import pytest
from morice.security_lab.contracts import Limits,Budget,IntegrityFailure,member_name
from morice.security_lab.forensics import inspect,decode,MAGIC
from morice.security_lab.recovery import recover,feasibility,envelope_fixture,candidate_values

@pytest.fixture
def archive(tmp_path):
    import pyzipper
    path=tmp_path/'owner.zip'
    with pyzipper.AESZipFile(path,'w',compression=pyzipper.ZIP_DEFLATED,encryption=pyzipper.WZ_AES) as output:
        output.setpassword(b'owned-fixture-pass');output.writestr('notes.txt',b'An actual complete owned recovery fixture.\n')
    return path

def test_actual_archive_candidates_authentication_and_readback(archive,tmp_path):
    original=archive.read_bytes();report=inspect(archive)
    assert report['encryption']['password_based'] and 'AES' in report['encryption']['scheme']
    result=recover(archive,tmp_path/'result',['incorrect','owned-fixture-pass'])
    assert result['status']=='RECOVERED' and result['tested']==2
    assert Path(result['artifacts'][0]['path']).read_bytes()==b'An actual complete owned recovery fixture.\n'
    assert archive.read_bytes()==original and 'owned-fixture-pass' not in json.dumps(result)

@pytest.mark.parametrize('values,status',[(['bad'],'WRONG_KEY'),(['bad','also-bad'],'CANDIDATES_EXHAUSTED'),([],'MISSING_KEY')])
def test_wrong_missing_and_exhausted(archive,tmp_path,values,status):
    result=recover(archive,tmp_path/'out',values);assert result['status']==status and not result['artifacts']
    assert not list((tmp_path/'out').rglob('notes.txt'))

@pytest.mark.parametrize('algorithm',['AES-256-GCM','CHACHA20-POLY1305'])
def test_actual_known_key_and_unavailable_random_key(tmp_path,algorithm):
    key=os.urandom(32);path=tmp_path/'known.enc';path.write_bytes(envelope_fixture(b'Exact original plaintext',key=key,algorithm=algorithm))
    estimate=feasibility(path)
    assert estimate['status']=='MISSING_KEY' and not estimate['feasible'] and 'not practical' in estimate['reason']
    result=recover(path,tmp_path/'out',key=key)
    assert result['status']=='RECOVERED' and Path(result['artifacts'][0]['path']).read_bytes()==b'Exact original plaintext'
    assert 'AEAD tag authenticated' in result['verification']

def test_password_kdf_salt_and_actual_cost(tmp_path):
    path=tmp_path/'password.enc';path.write_bytes(envelope_fixture(b'Authenticated password-based content',password='owner-pass'))
    info=inspect(path)['encryption'];assert info['kdf']['name']=='PBKDF2-HMAC-SHA256' and info['offline_verification']
    estimate=feasibility(path,['wrong','owner-pass']);assert estimate['candidate_count']==2 and estimate['seconds_per_rejection_measured']>0
    assert recover(path,tmp_path/'out',['wrong','owner-pass'])['status']=='RECOVERED'

def test_corrupted_archive_authentication_failure(archive,tmp_path):
    with zipfile.ZipFile(archive) as output:info=output.infolist()[0]
    data=bytearray(archive.read_bytes());name,extra=struct.unpack_from('<HH',data,info.header_offset+26)
    offset=info.header_offset+30+name+extra+info.compress_size-1;data[offset]^=1
    broken=tmp_path/'broken.zip';broken.write_bytes(data)
    result=recover(broken,tmp_path/'out',['owned-fixture-pass'])
    assert result['status']=='INTEGRITY_CHECK_FAILED' and not result['artifacts']
    assert not list((tmp_path/'out').rglob('notes.txt'))

def test_unsupported_and_high_entropy_not_encryption(tmp_path):
    path=tmp_path/'random.dat';path.write_bytes(os.urandom(4096));result=inspect(path)
    assert result['format']=='UNKNOWN' and result['encryption']['scheme']=='unknown'
    assert recover(path,tmp_path/'out',['anything'])['status']=='UNSUPPORTED_FORMAT'

def test_candidate_limit_cancellation_and_progress(archive,tmp_path):
    seen=[];result=recover(archive,tmp_path/'out',['one','two','three'],limits=Limits(candidates=2),progress=seen.append)
    assert result['status']=='RESOURCE_LIMIT_REACHED' and result['tested']==2 and seen[0]['tested']==1
    assert recover(archive,tmp_path/'cancel',['a'],cancel=lambda:True)['status']=='CANCELLED'

def test_encoding_chain_and_source_preservation(tmp_path):
    path=tmp_path/'sample.dat';data=base64.b64encode(gzip.compress('தமிழ் Hindi हिन्दी\n'.encode()));path.write_bytes(data)
    destination=tmp_path/'decoded';destination.mkdir();result=decode(path,destination)
    assert result['chain']==['BASE64','GZIP'] and path.read_bytes()==data
    assert 'TAMIL' in inspect(result['artifacts'][0]['path'])['text']['scripts']

@pytest.mark.parametrize('path',['../escape','/absolute','C:/outside','safe/../../bad','stream:secret','NUL.txt','COM1','trailing.'])
def test_archive_escape_and_windows_aliases(path):
    with pytest.raises(IntegrityFailure):member_name(path)

def test_decompression_bomb_bound(tmp_path):
    path=tmp_path/'bomb.gz';path.write_bytes(gzip.compress(b'A'*1000000));out=tmp_path/'out';out.mkdir()
    from morice.security_lab.contracts import LimitReached
    with pytest.raises(LimitReached):decode(path,out,Limits(output_bytes=8192))
    assert not list(out.iterdir())

def test_only_explicit_candidate_conventions():
    assert candidate_values(['given','given'],[{'template':'Owner{value}!','values':[2025,2026]}])==['given','Owner2025!','Owner2026!']
    with pytest.raises(ValueError):candidate_values([], [{'template':'{private_profile}','values':['x']}])
