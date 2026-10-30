"""Owned actual worker/cryptography/repair checks for wheel and frozen builds."""
import hashlib,os,time
from pathlib import Path

def probe(runtime,app):
    from PySide6.QtTest import QTest
    from .recovery import envelope_fixture
    import pyzipper
    root=runtime.directory/'security-lab-package-fixtures';root.mkdir(exist_ok=True)
    archive=root/'owned.zip';plain=b'Actual packaged ZIP recovery and readback.'
    with pyzipper.AESZipFile(archive,'w',compression=pyzipper.ZIP_DEFLATED,encryption=pyzipper.WZ_AES) as output:
        output.setpassword(b'packaged-owned-fixture');output.writestr('owned.txt',plain)
    lab=runtime.security_lab;rows=[]
    def run(action,**kwargs):
        identifier=lab.prepare(action,**kwargs);future=runtime.workers.submit('Packaging Security Lab '+action,lambda:lab.run(action,identifier))
        deadline=time.monotonic()+45
        while not future.done() and time.monotonic()<deadline:app.processEvents();QTest.qWait(10)
        assert future.done(),'Packaged security worker did not finish'
        result=future.result();assert result.success,result.to_dict()
        row=lab.snapshot(identifier);rows.append({'action':action,'status':row['status']});return row
    recovered=run('recover',path=archive,secret_ref=lab.supply(['wrong','packaged-owned-fixture']))
    assert recovered['status']=='RECOVERED' and Path(recovered['artifacts'][0]['path']).read_bytes()==plain
    wrong=run('recover',path=archive,secret_ref=lab.supply(['incorrect']))
    assert wrong['status']=='WRONG_KEY' and not wrong['artifacts']
    envelope=root/'key.enc';key=os.urandom(32);envelope.write_bytes(envelope_fixture(b'Authenticated packaged direct-key content.',key=key))
    missing=run('estimate',path=envelope)
    assert missing['status']=='MISSING_KEY' and not missing['result']['feasible']
    direct=run('recover',path=envelope,secret_ref=lab.supply(key=key))
    assert direct['status']=='RECOVERED'
    challenge=run('challenge')
    assert challenge['result']['findings'][0]['after_status']==403 and challenge['result']['remediation']['verified']
    return {'owned_actual_crypto_workers':True,'rows':rows,'zip_plaintext_sha256':hashlib.sha256(plain).hexdigest(),
        'fixture_source_repair_verified':True,'scope':'Owned local fixtures; no physical device or live external account is exercised.'}
