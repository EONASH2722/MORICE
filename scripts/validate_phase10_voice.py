"""Actual existing Vosk model and Windows SAPI PCM; no live mic/cloud claims."""
import hashlib
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from morice.config import TTSConfig
from morice.local_speech_provider import WindowsSpeechProvider
from morice.speech_runtime import SpeechInputConfig, SpeechToTextRuntime, find_vosk_model

output = ROOT / 'build/phase10-voice-pcm'; output.mkdir(parents=True, exist_ok=True)
rows = []
class PcmSource:
    def __init__(self, pcm): self.pcm = pcm + b'\x00' * 64000; self.position = 0; self.stopped = False
    def start(self): pass
    def read(self, timeout):
        if self.stopped: return None
        if self.position >= len(self.pcm): self.stopped = True; return None
        data = self.pcm[self.position:self.position + 4000]; self.position += len(data); return data
    def stop(self): self.stopped = True
    def abort(self): self.stopped = True

model = find_vosk_model()
assert model, 'Existing local Vosk model unavailable.'
provider = WindowsSpeechProvider()
runtime = SpeechToTextRuntime(SpeechInputConfig(enabled=True, model_path=model, max_listen_seconds=8), audio_factory=lambda config: PcmSource(current_pcm[0]))
current_pcm = [b'']
try:
    for index, text in enumerate(('Morice.', 'Show Earth.', 'Show Chennai and Los Angeles.', "What is the distance as the crow flies?", 'Give it to me in miles.', 'Show the straight line distance too.', 'What about New York instead?')):
        pcm = b''.join(provider.stream_audio((text,), TTSConfig(provider='local', output_format='pcm_16000'), threading.Event()))
        assert pcm and len(pcm) % 2 == 0
        current_pcm[0] = pcm
        result = runtime.listen_once().wait(12)
        assert result is not None and result.text and not result.error_code and not result.cancelled
        target = output / (str(index) + '.pcm'); target.write_bytes(pcm)
        rows.append({'text_requested': text, 'text_recognized': result.text, 'pcm_sha256': hashlib.sha256(pcm).hexdigest(), 'pcm_bytes': len(pcm), 'recognition_ms': result.duration_ms, 'pcm_path': str(target)})
        print(json.dumps(rows[-1]), flush=True)
finally:
    runtime.shutdown()
(ROOT / 'build/phase10-actual-voice.json').write_text(json.dumps({'scope': 'ACTUAL Windows SAPI speech PCM + ACTUAL existing Vosk model; memory input/output, no physical mic/speaker or cloud validation', 'model_path': model, 'rows': rows}, indent=2), encoding='utf-8')
