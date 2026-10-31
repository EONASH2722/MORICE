"""Real packaged ASR acceptance with owned synthesized PCM, without a microphone."""
def run(output,model_path):
    import json,os,sys,threading,time
    from pathlib import Path
    from .config import TTSConfig
    from .local_speech_provider import WindowsSpeechProvider
    from .speech_runtime import SpeechInputConfig,SpeechToTextRuntime
    from .kernel.resources import ResourceManager
    if not os.getenv('APPDATA') or not os.getenv('MORICE_RUNTIME_DIR'):raise RuntimeError('An owned probe profile is required.')
    reference='MORICE open settings and set the volume to forty five percent.'
    pcm=b''.join(WindowsSpeechProvider().stream_audio([reference],TTSConfig(provider='local',output_format='pcm_16000'),threading.Event()))+b'\0'*64000
    class OwnedAudio:
        def __init__(self):self.position=0;self.stopped=False
        def start(self):pass
        def read(self,timeout):
            value=pcm[self.position:self.position+4000];self.position+=len(value)
            if not value:time.sleep(.01)
            return value or None
        def stop(self):self.stopped=True
        def abort(self):self.stopped=True
    audio=OwnedAudio();resources=ResourceManager()
    runtime=SpeechToTextRuntime(SpeechInputConfig(provider='whisper',accuracy_model_path=model_path,autocorrect=True),resources=resources,audio_factory=lambda _:audio)
    started=time.perf_counter()
    try:
        result=runtime.listen_once().wait(55)
        assert result is not None and not result.error_code and not result.cancelled,result
        assert result.provider=='whisper' and 'settings' in result.text.lower() and '45' in result.text,result
        assert result.text.startswith('MORICE') and audio.stopped,result
        record={'frozen':bool(getattr(sys,'frozen',False)),'provider':result.provider,'reference':reference,
            'transcript':result.text,'streaming_transcript':result.streaming_text,'corrections':list(result.corrections),
            'real_whisper_decode':True,'real_local_tts_fixture':True,'microphone_opened':False,'audio_played':False,
            'model_downloaded_by_application':False,'seconds':time.perf_counter()-started}
    finally:runtime.shutdown()
    assert not resources.snapshot() and not resources.retained()
    record['leases_after']=0;record['owned_decoder_closed']=runtime._refiner._process is None
    Path(output).write_text(json.dumps(record,indent=2),encoding='utf-8')
    return 0
