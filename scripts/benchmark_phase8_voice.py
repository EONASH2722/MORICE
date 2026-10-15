"""Controlled PCM streaming timings; no cloud request or physical audio device."""
from dataclasses import replace
import json
from pathlib import Path
import statistics
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from morice.config import TTSConfig
from morice.voice_runtime import VoiceRuntime

def run():
    release=threading.Event();barge_release=threading.Event();played=threading.Event();stages={};sinks=[];started=time.perf_counter()
    def stage(name):stages.setdefault(name,(time.perf_counter()-started)*1000)
    class Sink:
        def __init__(self):self.writes=0;self.aborted=False
        def start(self,**kwargs):pass
        def write(self,data):
            assert not self.aborted;self.writes+=1;stage('first_audio_sink_write_ms');played.set()
        def abort(self):self.aborted=True
        def close(self):pass
    class Provider:
        def stream_audio(self,chunks,config,cancel):
            stage('first_tts_request_ms')
            for text in chunks:
                if cancel.is_set():return
                yield b'\x00\x01'*1000
    def sink_factory(config):
        sink=Sink();sinks.append(sink);return sink
    def generated():
        stage('first_text_delta_ms')
        yield 'The first complete sentence can begin streaming speech immediately. '
        release.wait(3)
        yield 'The remaining generated text follows the first audio. '
        stage('generation_completed_ms')
    voice=VoiceRuntime(replace(TTSConfig(api_key='phase8-owned-fixture'),enabled=True),
        provider_factory=lambda config:Provider(),sink_factory=sink_factory)
    try:
        old=voice.speak_stream(generated());assert played.wait(2)
        assert 'generation_completed_ms' not in stages
        # Normal completion establishes a genuine EOF timestamp. Cancellation
        # has a separate generation: aborted text need not ever reach its EOF.
        release.set();assert old.wait(2) is not None
        assert stages['first_tts_request_ms']<=stages['first_audio_sink_write_ms']<stages['generation_completed_ms']
        def interrupted_text():
            yield 'This independently owned answer is interrupted during generation. '
            barge_release.wait(3)
            yield 'This remaining text must not produce old audio after interruption. '
        played.clear();old=voice.speak_stream(interrupted_text());assert played.wait(2)
        stamp=time.perf_counter();assert voice.interrupt()
        stages['barge_in_ms']=(time.perf_counter()-stamp)*1000
        interrupted_sink=sinks[-1];writes=interrupted_sink.writes;barge_release.set();assert old.wait(2) is not None
        assert interrupted_sink.aborted and interrupted_sink.writes==writes
        new=voice.speak_stream(iter(['The next answer owns its own streaming speech request. ']))
        assert new.wait(2) is not None and sinks[-1].writes>0
        return {**stages,'audio_before_generation_complete':True,'old_audio_after_interrupt':False,
            'new_request_has_audio':True}
    finally:release.set();barge_release.set();voice.shutdown()

values=[run() for _ in range(3)]
def distribution(key):
    values_ms=[row[key] for row in values]
    return {'p50_ms':statistics.median(values_ms),'p95_ms':max(values_ms),'samples_ms':values_ms}
result={'scope':'Actual VoiceRuntime with controlled PCM provider and sink; no cloud TTS, physical audible output, microphone or wake measurement.',
    'runs':values,'metrics':{key:distribution(key) for key in values[0] if key.endswith('_ms')},
    'completed':True}
(ROOT/'build/phase8-voice.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'output':'build/phase8-voice.json','metrics':result['metrics']},indent=2))
