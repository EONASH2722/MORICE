import array
import threading
from unittest.mock import Mock,patch
import pytest
from morice.speech_runtime import SpeechInputConfig,SpeechToTextRuntime,SpeechInputState
from morice.speech_refinement import correct_transcript,RefinementError,RefinementCancelled,WhisperRefiner
from morice.kernel.resources import ResourceManager


@pytest.mark.parametrize('value,expected',[
    ('Morris. Compare the two charts.','MORICE. Compare the two charts.'),
    ('Maurice, open Settings.','MORICE, open Settings.'),
    ('Do not send 45 files to Janmesh._.X.','Do not send 45 files to Janmesh._.X.'),
    ('Email https://example.com/a?x=2 to Janmesh._.X.','Email https://example.com/a?x=2 to Janmesh._.X.'),
    ('Show Maurice the files.','Show Maurice the files.'),
    ('Morris is a person.','Morris is a person.'),
    ('MORICE opens settings and set the volume to 45%.','MORICE open settings and set the volume to 45%.'),
    ('MORICE deletes 5 files.','MORICE deletes 5 files.'),
    ('MORICE opens Janmesh._.X.','MORICE opens Janmesh._.X.'),
])
def test_correction_preserves_meaning_names_numbers_urls_and_negation(value,expected):
    result,changes=correct_transcript(value)
    assert result==expected and bool(changes)==(value!=expected)


class Audio:
    def __init__(self):self.stopped=False;self.used=False
    def start(self):pass
    def read(self,_):
        if not self.used:self.used=True;return array.array('h',[5000]*2000).tobytes()
        return None
    def stop(self):self.stopped=True
    def abort(self):self.stopped=True

class Recognizer:
    def accept(self,_):return True,'morris open sitting',''
    def finish(self):return ''


def runtime_for(refiner):
    audio=Audio()
    with patch.object(SpeechToTextRuntime,'_new_refiner',return_value=refiner):
        runtime=SpeechToTextRuntime(SpeechInputConfig(),recognizer_factory=lambda *_:Recognizer(),audio_factory=lambda _:audio)
    runtime._model_path='owned-fake-model';return runtime,audio


def test_refinement_uses_captured_audio_after_microphone_stops_and_keeps_original():
    refiner=Mock()
    runtime,audio=runtime_for(refiner)
    def transcribe(pcm,rate,**options):
        assert audio.stopped and runtime.status().state==SpeechInputState.TRANSCRIBING
        assert pcm==array.array('h',[5000]*2000).tobytes() and rate==16000
        return {'text':'Morris, open Settings.','uncertain':False}
    refiner.transcribe.side_effect=transcribe
    try:
        result=runtime.listen_once().wait(2)
        assert result.text=='MORICE, open Settings.' and result.provider=='whisper'
        assert result.streaming_text=='morris open sitting' and result.raw_text=='Morris, open Settings.'
        assert result.corrections==('assistant-name',) and not result.error_code
    finally:runtime.shutdown()


def test_failed_refinement_reports_vosk_fallback_without_fabricating_success():
    refiner=Mock();refiner.transcribe.side_effect=RefinementError('decoder-load-failed')
    runtime,audio=runtime_for(refiner)
    try:
        result=runtime.listen_once().wait(2)
        assert result.text=='morris open sitting' and result.provider=='vosk'
        assert result.refinement_error and 'larger recognizer was unavailable' in result.message
    finally:runtime.shutdown()


def test_uncertain_refinement_does_not_submit_an_action_guess():
    refiner=Mock();refiner.transcribe.return_value={'text':'Delete everything.','uncertain':True}
    runtime,_=runtime_for(refiner)
    try:
        result=runtime.listen_once().wait(2)
        assert result.text=='' and result.error_code=='unclear-speech'
    finally:runtime.shutdown()


def test_cancellation_during_refinement_discards_transcript():
    entered=threading.Event();refiner=Mock()
    def transcribe(*_,cancel,**__):
        entered.set();assert cancel.wait(2);raise RefinementCancelled('cancelled')
    refiner.transcribe.side_effect=transcribe;runtime,audio=runtime_for(refiner)
    try:
        handle=runtime.listen_once();assert entered.wait(1) and audio.stopped
        assert runtime.cancel();result=handle.wait(2)
        assert result.cancelled and result.error_code=='cancelled' and not result.text
    finally:runtime.shutdown()


def test_vosk_selection_never_loads_accuracy_model():
    with patch('morice.speech_runtime.WhisperRefiner') as create:
        runtime=SpeechToTextRuntime(SpeechInputConfig(provider='vosk',accuracy_model_path='unused'))
    try:assert not create.called and runtime._refiner is None
    finally:runtime.shutdown()


def test_failed_worker_cleanup_retains_lease_and_process_until_reconciled():
    resources=ResourceManager();refiner=WhisperRefiner('owned-model',resources=resources)
    from morice.kernel.contracts import ResourceClaim
    assert resources.acquire(refiner._owner,(ResourceClaim('SPEECH_DECODER'),))
    refiner._leased=True;process=Mock();refiner._process=process
    with patch('morice.speech_refinement.reap_owned_job',side_effect=TimeoutError('owned job still running')):
        with pytest.raises(TimeoutError):refiner.stop()
    assert resources.snapshot() and resources.retained() and refiner._process is process
    with patch('morice.speech_refinement.reap_owned_job',return_value=True):refiner.stop()
    assert not resources.snapshot() and not resources.retained() and refiner._process is None


def test_closed_decoder_cannot_restart_after_voice_session_ends():
    refiner=WhisperRefiner('owned-model');refiner.close()
    with patch('morice.speech_refinement.spawn_owned_process') as spawn:
        with pytest.raises(RefinementCancelled):refiner.prewarm()
    assert not spawn.called


def test_queued_warmup_cannot_reload_a_decoder_after_voice_exit():
    refiner=Mock();runtime,_=runtime_for(refiner);warm=runtime.accuracy_warmup()
    try:
        runtime.release_accuracy_model()
        assert warm() is False and not refiner.prewarm.called
    finally:runtime.shutdown()


def test_explicit_invalid_model_does_not_silently_select_another_model(tmp_path,monkeypatch):
    from morice.speech_refinement import find_whisper_model
    default=tmp_path/'models/stt/faster-whisper-small';default.mkdir(parents=True)
    for name in ('config.json','model.bin','tokenizer.json','vocabulary.txt'):(default/name).write_text('owned fixture')
    monkeypatch.setattr('morice.speech_refinement.local_data_dir',lambda:tmp_path)
    assert find_whisper_model()==str(default.resolve())
    assert find_whisper_model(str(tmp_path/'missing'))==''


def test_worker_cancellation_reaps_owned_family_and_resource_lease(tmp_path,monkeypatch):
    import os,sys,json,time,psutil
    if os.name!='nt':pytest.skip('Windows Job process ownership')
    from morice.process_ownership import spawn_owned_process
    fixture=tmp_path/'owned_decoder.py';child_file=tmp_path/'child.txt'
    fixture.write_text('import json,sys,subprocess,time\nfrom pathlib import Path\nchild=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\nPath(sys.argv[1]).write_text(str(child.pid))\nprint(json.dumps({"type":"ready"}),flush=True)\nfor line in sys.stdin:\n time.sleep(60)\n')
    def spawn(command,**options):return spawn_owned_process([sys.executable,'-u',str(fixture),str(child_file)],**options)
    monkeypatch.setattr('morice.speech_refinement.spawn_owned_process',spawn)
    resources=ResourceManager();refiner=WhisperRefiner('owned-fixture',resources=resources,timeout=10)
    cancelled=threading.Event();errors=[]
    def decode():
        try:refiner.transcribe(array.array('h',[5000]*2000).tobytes(),16000,cancel=cancelled)
        except RefinementCancelled:errors.append('cancelled')
    thread=threading.Thread(target=decode)
    try:
        refiner.prewarm();process=refiner._process;child=int(child_file.read_text());assert psutil.pid_exists(child)
        thread.start();time.sleep(.1);started=time.monotonic();cancelled.set();thread.join(3)
        assert not thread.is_alive() and errors==['cancelled'] and time.monotonic()-started<3
        assert process.poll() is not None and not psutil.pid_exists(child)
        assert not resources.snapshot() and not resources.retained()
    finally:cancelled.set();refiner.close();thread.join(2)


def test_old_capture_cleanup_cannot_clear_a_replacement_capture():
    import time
    old_stop=threading.Event();old_stopping=threading.Event()
    class BlockingAudio:
        def __init__(self,old=False):self.gate=threading.Event();self.old=old
        def start(self):pass
        def read(self,_):self.gate.wait(.1);return None
        def abort(self):self.gate.set()
        def stop(self):
            if self.old:old_stopping.set();old_stop.wait(2)
    first,second=BlockingAudio(True),BlockingAudio();audios=iter((first,second))
    runtime=SpeechToTextRuntime(SpeechInputConfig(provider='vosk'),recognizer_factory=lambda *_:Recognizer(),audio_factory=lambda _:next(audios));runtime._model_path='owned-fixture'
    try:
        a=runtime.listen_once();deadline=time.monotonic()+1
        while runtime._audio is not first and time.monotonic()<deadline:time.sleep(.01)
        b=runtime.listen_once();assert old_stopping.wait(1)
        deadline=time.monotonic()+1
        while runtime._audio is not second and time.monotonic()<deadline:time.sleep(.01)
        old_stop.set();assert a.wait(1).cancelled
        assert runtime._audio is second and runtime.status().state==SpeechInputState.LISTENING and runtime.status().listening
        runtime.cancel();assert b.wait(1).cancelled
    finally:old_stop.set();first.abort();second.abort();runtime.shutdown()
