"""Media admission and completion must remain truthful when storage fails."""
import hashlib
import json
import pytest
from PIL import Image

from test_media_lab import media, request, run
from test_media_integrations import attach_fixture
from test_device_mesh import mesh_nodes, pair
from dataclasses import replace
from morice.kernel import EventType, ResourceClaim


def test_failed_admission_does_not_leave_phantom_queue_entry(media,monkeypatch):
    with monkeypatch.context() as patcher:
        def unavailable(*_args,**_kwargs):raise OSError('controlled unavailable history')
        patcher.setattr(media.history_store,'save',unavailable)
        with pytest.raises(OSError,match='controlled unavailable history'):
            media.submit(request())
    assert not media._jobs and not media._futures
    assert not media.kernel.resources.snapshot()
    assert run(media)[1].success


def test_terminal_storage_failure_never_reports_success_or_strands_future(media,monkeypatch):
    original=media.history_store.save;events=[]
    subscription=media.kernel.events.subscribe(lambda event:events.append(event.event_type))
    def unavailable_terminal(identifier,value):
        if value.get('terminal_recorded'):raise OSError('controlled terminal history failure')
        return original(identifier,value)
    monkeypatch.setattr(media.history_store,'save',unavailable_terminal)
    try:
        identifier,future=media.submit(request())
        result=future.result(timeout=4)
        assert not result.success
        assert len([error for error in result.errors if 'history' in error.message.lower()])==1
        assert media.result(identifier)['status']!='SUCCEEDED'
        assert EventType.MEDIA_COMPLETED not in events
        assert not media._jobs and not media._futures
        assert not media.kernel.resources.snapshot() and not media.providers['test'].processes.snapshot()
        with pytest.raises(ValueError,match='completed verified artifacts'):
            media.artifact(identifier)
        # Losing the history write must not destroy the user's decoded work.
        output=media.directory/'outputs'/identifier
        images=list(output.glob('*.png'));assert len(images)==1
        with Image.open(images[0]) as image:
            image.load();assert image.size==(64,64)
        metadata=json.loads((output/'generation.json').read_text())
        assert hashlib.sha256(images[0].read_bytes()).hexdigest()==metadata['artifacts'][0]['sha256']
    finally:media.kernel.events.unsubscribe(subscription)


def test_transient_terminal_write_failure_is_persisted_as_failure(media,monkeypatch):
    original=media.history_store.save;failures=[]
    def unavailable_success(identifier,value):
        if value.get('terminal_recorded') and value['status']=='SUCCEEDED' and not failures:
            failures.append(identifier)
            raise OSError('controlled single terminal write failure')
        return original(identifier,value)
    monkeypatch.setattr(media.history_store,'save',unavailable_success)
    identifier,result=run(media)
    assert failures==[identifier] and not result.success
    stored=media.result(identifier)
    assert stored['status']=='FAILED' and stored['terminal_recorded'] and not stored['artifacts']
    assert result.output['status']=='FAILED' and not result.artifacts
    assert not media._jobs and not media._futures and not media.load_error
    assert run(media)[1].success


def test_remote_terminal_write_failure_settles_future_and_clears_queue(media,mesh_nodes,tmp_path,monkeypatch):
    client,node,_=mesh_nodes;observed={}
    def generate(args,_context):
        observed.update(generation_id=args['generation_id'],status='SUCCEEDED')
        return dict(observed)
    node.node.register('media.image.generate',generate,lambda _args,_context:dict(observed),
        resources=(ResourceClaim('CPU'),),read_only=False)
    target=pair(client,node,grants=('device.status','file.receive','media.image.generate'))
    lab=attach_fixture(media,client.kernel,client.agents,tmp_path/'remote-media')
    original=lab.history_store.save
    def unavailable_terminal(identifier,value):
        if value.get('completed_at'):raise OSError('controlled remote terminal history failure')
        return original(identifier,value)
    monkeypatch.setattr(lab.history_store,'save',unavailable_terminal)
    try:
        identifier,future=lab.submit(replace(request(),node_id=target))
        result=future.result(timeout=12)
        assert not result.success and any('history' in error.message.lower() for error in result.errors)
        assert lab.result(identifier)['status']!='SUCCEEDED'
        assert not lab._jobs and not lab._futures and lab.load_error
    finally:lab.close()


def test_failed_direct_dispatch_finalizes_media_job_and_removes_temp_files(media):
    result = media.kernel.dispatch('media.image.generate', {'request': request('crash').to_dict()},
                                   task_id='custom-media-task')
    assert not result.success
    history = media.history()
    assert len(history) == 1 and history[0]['status'] == 'FAILED'
    assert history[0]['terminal_recorded']
    assert not media.status()['queue']
    assert not list((media.directory / 'temp').iterdir())


def test_direct_dispatch_terminal_history_failure_releases_queue_entry(media,monkeypatch):
    original = media.history_store.save

    def unavailable_terminal(identifier, value):
        if value.get('terminal_recorded'):
            raise OSError('controlled direct terminal history failure')
        return original(identifier, value)

    monkeypatch.setattr(media.history_store, 'save', unavailable_terminal)
    result = media.kernel.dispatch('media.image.generate', {'request': request().to_dict()})
    assert not result.success
    assert not media.status()['queue']
    assert not media.kernel.resources.snapshot()
    assert any('history' in error.message.lower() for error in result.errors)
