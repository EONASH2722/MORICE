import json,os,time
from pathlib import Path
from unittest.mock import patch
import pytest
from morice.kernel import CancellationToken,ExecutionContext,TaskNode
from morice.security_lab.recovery import envelope_fixture
from morice.unified_intelligence import PermissionState

@pytest.fixture
def runtime(tmp_path):
    from morice.runtime_services import RuntimeServices
    with patch.dict(os.environ,MORICE_PRELOAD='0',MORICE_NODE_NETWORK='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_LOCAL_DATA_DIR=str(tmp_path/'data')):
        value=RuntimeServices(tmp_path/'runtime',project_root=Path(__file__).resolve().parents[1])
        try:yield value
        finally:value.shutdown()

def test_actual_owned_worker_recovery_and_persistence(runtime,tmp_path):
    path=tmp_path/'owned.enc';path.write_bytes(envelope_fixture(b'Actual isolated-worker plaintext',password='private-candidate'))
    lab=runtime.security_lab;secret=lab.supply(['wrong','private-candidate']);identifier=lab.prepare('recover',path=path,secret_ref=secret,conversation='owned-chat')
    original=path.read_bytes();result=lab.run('recover',identifier)
    assert result.success and result.verification.status.value=='verified',result.to_dict()
    job=lab.snapshot(identifier);assert job['status']=='RECOVERED',job
    assert Path(job['artifacts'][0]['path']).read_bytes()==b'Actual isolated-worker plaintext'
    assert path.read_bytes()==original and secret not in lab.secrets and not runtime.kernel.resources.snapshot()
    receipt=(lab.directory/identifier/'receipt.json').read_text();assert 'private-candidate' not in receipt and secret not in receipt
    assert not (lab.directory/identifier/'input.bin').exists()
    with pytest.raises(PermissionError):lab.snapshot(identifier,'other-chat')

def test_cancelled_job_never_claims_decryption(runtime,tmp_path):
    path=tmp_path/'owned.enc';path.write_bytes(envelope_fixture(b'owned data',password='only-one'))
    lab=runtime.security_lab;secret=lab.supply(['wrong']*10);identifier=lab.prepare('recover',path=path,secret_ref=secret)
    lab.cancel(identifier);result=lab.run('recover',identifier)
    assert not result.success and result.status.value=='cancelled'
    assert secret not in lab.secrets and lab.snapshot(identifier)['status']=='CANCELLED'
    assert not runtime.kernel.resources.snapshot()

def test_shared_permission_denial_is_not_retried(runtime,tmp_path):
    path=tmp_path/'owned.txt';path.write_text('owned content')
    lab=runtime.security_lab;identifier=lab.prepare('inspect',path=path)
    runtime.kernel.permissions.controller.set_state('file_read',PermissionState.DENIED)
    result=lab.run('inspect',identifier)
    assert not result.success and not (lab.directory/identifier/'input.bin').exists()
    assert not runtime.kernel.resources.snapshot()

def test_actual_source_audit_and_loopback_before_after(runtime,tmp_path):
    project=tmp_path/'project';project.mkdir();(project/'vulnerable.py').write_text('def parse(value):\n    return eval(value)\n')
    lab=runtime.security_lab;identifier=lab.prepare('audit',path=project);result=lab.run('audit',identifier)
    assert result.success and lab.snapshot(identifier)['result']['findings'][0]['state']=='POSSIBLE'
    identifier=lab.prepare('challenge');result=lab.run('challenge',identifier)
    job=lab.snapshot(identifier);assert result.success and job['result'].get('message_delivery')=='VERIFIED',job
    assert job['result']['findings'][0]['before_status']==200 and job['result']['findings'][0]['after_status']==403
    assert all(row['passed'] for row in job['result']['tests'])
    assert job['result']['remediation']['verified'] and job['result']['remediation']['capability']=='filesystem.apply_patch'
    assert 'user in' in (lab.directory/identifier/'output/owned-fixture/authorization.py').read_text(encoding='utf-8')

def test_no_overwrite_export_and_independent_hashes(runtime,tmp_path):
    path=tmp_path/'owned.enc';path.write_bytes(envelope_fixture(b'exported owned content',key=b'K'*32))
    lab=runtime.security_lab;identifier=lab.prepare('recover',path=path,secret_ref=lab.supply(key=b'K'*32));assert lab.run('recover',identifier).success
    target=tmp_path/'export';lab.jobs[identifier]['options']['export_destination']=str(target)
    authority=runtime.kernel.permissions.controller
    def approved():
        token=lab.approve(identifier,'export')
        return lab.run('export',identifier,approval_token=token)
    result=approved();assert result.success,[(e.code.value,e.message,e.detail) for e in result.errors]
    assert next(target.iterdir()).read_bytes()==b'exported owned content'
    assert not approved().success and next(target.iterdir()).read_bytes()==b'exported owned content'

def test_rich_snapshot_is_actual_conversation_owned(runtime,tmp_path):
    from morice.rich_response.sources import ResponseSources
    from morice.rich_response import SourceRef
    path=tmp_path/'sample.txt';path.write_text('Actual source file')
    identifier=runtime.security_lab.prepare('inspect',path=path,conversation='one');assert runtime.security_lab.run('inspect',identifier).success
    snapshot=ResponseSources(runtime,'one').resolve(SourceRef('security_lab',identifier,scope='one'))
    assert snapshot.verified and snapshot.data['operation']=='inspect'
    with pytest.raises(PermissionError):ResponseSources(runtime,'two').resolve(SourceRef('security_lab',identifier,scope='two'))

def test_exact_export_scope_is_frozen_and_clear_keeps_original(runtime,tmp_path):
    path=tmp_path/'owned.enc';path.write_bytes(envelope_fixture(b'preserved input',key=b'K'*32));original=path.read_bytes()
    lab=runtime.security_lab;identifier=lab.prepare('recover',path=path,secret_ref=lab.supply(key=b'K'*32));assert lab.run('recover',identifier).success
    old=tmp_path/'selected';new=tmp_path/'not-selected';lab.jobs[identifier]['options']['export_destination']=str(old)
    token=lab.approve(identifier,'export');lab.jobs[identifier]['options']['export_destination']=str(new)
    assert lab.run('export',identifier,approval_token=token).success
    assert old.is_dir() and not new.exists()
    assert not lab.run('export',identifier,approval_token=token).success
    token=lab.approve(identifier,'clear');result=lab.run('clear',identifier,approval_token=token)
    assert result.success and result.verification.status.value=='verified'
    assert path.read_bytes()==original and old.is_dir() and not (lab.directory/identifier).exists()

def test_conversation_boundary_applies_before_execution(runtime,tmp_path):
    path=tmp_path/'owned.txt';path.write_text('Owned scoped file',encoding='utf-8')
    lab=runtime.security_lab;identifier=lab.prepare('inspect',path=path,conversation='first');assert lab.run('inspect',identifier).success
    result=lab.run('status',identifier,conversation='other')
    assert not result.success and not result.output


def test_completion_waits_for_kernel_verification_and_physical_release(runtime,tmp_path):
    import threading
    path=tmp_path/'owned.txt';path.write_text('Owned source',encoding='utf-8')
    lab=runtime.security_lab;identifier=lab.prepare('inspect',path=path)
    verify=lab.verify
    entered=threading.Event();release=threading.Event();results=[]
    def delayed(result,context):
        entered.set();assert release.wait(5)
        return verify(result,context)
    lab.verify=delayed
    thread=threading.Thread(target=lambda:results.append(lab.run('inspect',identifier)))
    thread.start()
    try:
        assert entered.wait(5)
        assert lab.snapshot(identifier)['state']=='VERIFYING'
        assert runtime.kernel.resources.snapshot()
    finally:
        release.set();thread.join(10);lab.verify=verify
    assert not thread.is_alive() and results[0].success
    assert lab.snapshot(identifier)['state']=='COMPLETED'
    assert results[0].output['result']['state']=='COMPLETED'
    assert not runtime.kernel.resources.snapshot()
    second=lab.prepare('inspect',path=path)
    assert lab.run('inspect',second).success
    assert lab.snapshot(second)['status']!='NOT_STARTED'


def test_invalid_credential_material_never_enters_secret_store(runtime):
    lab=runtime.security_lab
    with pytest.raises(ValueError):lab.supply(credential_material={'unrecognized':'private'})
    assert not lab.secrets
