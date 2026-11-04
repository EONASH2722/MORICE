"""Probe failures are structured even in a windowed frozen executable."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

from morice.speech_probe import run
from morice.speech_runtime import TranscriptResult


def install_fixture(monkeypatch,tmp_path,result):
    monkeypatch.setenv('APPDATA',str(tmp_path/'appdata'))
    monkeypatch.setenv('MORICE_RUNTIME_DIR',str(tmp_path/'runtime'))
    monkeypatch.setattr('morice.local_speech_provider.WindowsSpeechProvider.stream_audio',lambda *_:iter([b'\0'*4000]))
    handle=SimpleNamespace(wait=Mock(return_value=result),cancel=Mock())
    runtime=SimpleNamespace(listen_once=Mock(return_value=handle),completion_timeout_seconds=Mock(return_value=170.),
        shutdown=Mock(),_refiner=SimpleNamespace(_process=None))
    def create(config,*,resources,audio_factory):
        audio_factory(config).stop()
        return runtime
    monkeypatch.setattr('morice.speech_runtime.SpeechToTextRuntime',create)
    return runtime,handle


def test_probe_uses_complete_budget_and_records_success(monkeypatch,tmp_path):
    result=TranscriptResult('owned','MORICE open Settings and set the volume to 45%.',1,provider='whisper')
    runtime,handle=install_fixture(monkeypatch,tmp_path,result)
    output=tmp_path/'success.json'
    assert run(output,'owned-model')==0
    record=json.loads(output.read_text())
    assert record['success'] and record['wait_budget_seconds']==170. and record['leases_after']==0
    handle.wait.assert_called_once_with(170.)
    runtime.shutdown.assert_called_once()


def test_probe_timeout_cancels_and_returns_json_without_raising(monkeypatch,tmp_path):
    runtime,handle=install_fixture(monkeypatch,tmp_path,None)
    output=tmp_path/'timeout.json'
    assert run(output,'owned-model')==1
    record=json.loads(output.read_text())
    assert not record['success'] and record['error_code']=='probe-timeout'
    handle.cancel.assert_called_once()
    runtime.shutdown.assert_called_once()


def test_probe_cleanup_failure_cannot_report_success_or_escape(monkeypatch,tmp_path):
    result=TranscriptResult('owned','MORICE open Settings and set the volume to 45%.',1,provider='whisper')
    runtime,_=install_fixture(monkeypatch,tmp_path,result)
    runtime.shutdown.side_effect=RuntimeError('Owned cleanup failure')
    output=tmp_path/'cleanup.json'
    assert run(output,'owned-model')==1
    record=json.loads(output.read_text())
    assert not record['success'] and record['error_type']=='RuntimeError'


def test_missing_probe_profile_is_structured_before_audio_or_runtime(monkeypatch,tmp_path):
    monkeypatch.delenv('MORICE_RUNTIME_DIR',raising=False)
    create=Mock();monkeypatch.setattr('morice.speech_runtime.SpeechToTextRuntime',create)
    output=tmp_path/'missing-profile.json'
    assert run(output,'owned-model')==1
    assert not json.loads(output.read_text())['success']
    create.assert_not_called()
