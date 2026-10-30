import base64,io,json,os,sqlite3,tarfile
from pathlib import Path
import pytest
from morice.security_lab.contracts import Limits,LimitReached
from morice.security_lab.forensics import inspect,decode
from morice.security_lab.ciphers import transform,decode_cipher
from morice.security_lab.recovery import envelope_fixture,recover,feasibility

@pytest.mark.parametrize('text,kind',[('{"answer":42}','JSON'),('<root><value>safe</value></root>','XML'),('name,value\none,1\ntwo,2\n','CSV')])
def test_complete_bounded_data_readers(tmp_path,text,kind):
    path=tmp_path/'unknown.dat';path.write_text(text,encoding='utf-8');assert inspect(path)['format']==kind

def test_readonly_sqlite_and_tar_inventory(tmp_path):
    path=tmp_path/'database.dat'
    with sqlite3.connect(path) as db:db.execute('CREATE TABLE owned(value TEXT)')
    before=path.read_bytes();assert inspect(path)['tables']==[{'name':'owned','type':'table'}] and path.read_bytes()==before
    archive=tmp_path/'container.dat'
    with tarfile.open(archive,'w') as output:
        item=tarfile.TarInfo('owned.txt');item.size=4;output.addfile(item,io.BytesIO(b'test'))
    assert inspect(archive)['members'][0]['name']=='owned.txt'

@pytest.mark.parametrize('value',[b'hi',b'hello',b'actual padded base32 source'])
def test_base32_is_not_misidentified_as_ciphertext(tmp_path,value):
    path=tmp_path/'encoded';path.write_bytes(base64.b32encode(value));out=tmp_path/'out';out.mkdir();result=decode(path,out)
    assert result['chain']==['BASE32'] and Path(result['artifacts'][0]['path']).read_bytes()==value

@pytest.mark.parametrize('method,key',[('ROT13',''),('ATBASH',''),('CAESAR','7'),('VIGENERE','OwnerKey')])
def test_explicit_educational_cipher_roundtrip(tmp_path,method,key):
    text='Actual owned puzzle text. தமிழ் remains Unicode.';encoded=transform(text,method,key)
    path=tmp_path/'cipher.txt';path.write_text(encoded,encoding='utf-8');out=tmp_path/'out';out.mkdir()
    result=decode_cipher(path,out,method,key)
    assert result['status']=='DECODED_CANDIDATE' and Path(result['artifacts'][0]['path']).read_text(encoding='utf-8')==text
    assert 'not proof' in result['limitation']

def test_real_pdf_password_and_page_tree_readback(tmp_path):
    from pypdf import PdfWriter,PdfReader
    writer=PdfWriter();writer.add_blank_page(width=200,height=200);writer.encrypt('owned-pdf-password',algorithm='AES-256')
    path=tmp_path/'protected.pdf'
    with path.open('wb') as stream:writer.write(stream)
    assert inspect(path)['encryption']['password_based']
    result=recover(path,tmp_path/'out',['incorrect','owned-pdf-password'])
    assert result['status']=='RECOVERED' and not PdfReader(result['artifacts'][0]['path']).is_encrypted

def test_direct_key_cost_counts_and_input_bounds(tmp_path):
    path=tmp_path/'direct.enc';key=os.urandom(32);path.write_bytes(envelope_fixture(b'actual direct-key content',key=key))
    estimate=feasibility(path,['irrelevant-password'],key)
    assert estimate['candidate_count']==1 and estimate['seconds_per_rejection_measured']>0
    result=recover(path,tmp_path/'out',['irrelevant-password'],key)
    assert result['status']=='RECOVERED' and result['total_candidates']==1
    with pytest.raises(LimitReached):inspect(path,Limits(input_bytes=1))

@pytest.mark.parametrize('kwargs',[{'seconds':float('inf')},{'candidates':0},{'members':1000000},{'input_bytes':True},{'candidates':1.5}])
def test_invalid_resource_budgets_are_rejected(kwargs):
    with pytest.raises(ValueError):Limits(**kwargs)
