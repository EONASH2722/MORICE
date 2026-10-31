"""Private local decoder process; never opens a microphone or downloads weights."""
from __future__ import annotations
import base64
import json
import os
import sys


def main(model_path):
    os.environ['HF_HUB_OFFLINE'] = '1'
    import numpy as np
    from faster_whisper import WhisperModel
    from .speech_refinement import MAX_PCM_BYTES, find_whisper_model
    def reply(value):
        sys.stdout.write(json.dumps(value, ensure_ascii=True) + '\n'); sys.stdout.flush()
    try:
        if not find_whisper_model(model_path): raise ValueError('model-unavailable')
        model = WhisperModel(model_path, device='cpu', compute_type='int8', cpu_threads=4, num_workers=1, local_files_only=True)
    except Exception:
        reply({'type': 'error', 'error': 'decoder-load-failed'}); return 1
    reply({'type': 'ready', 'provider': 'whisper', 'device': 'cpu', 'compute_type': 'int8'})
    while line := sys.stdin.buffer.readline(6 * 1024**2):
        identifier = ''
        try:
            if len(line) >= 6 * 1024**2: raise ValueError('audio-limit')
            request = json.loads(line); identifier = str(request['id'])[:128]
            pcm = base64.b64decode(request['pcm'], validate=True); rate = int(request['sample_rate'])
            if not pcm or len(pcm) > MAX_PCM_BYTES or len(pcm) % 2 or not 8000 <= rate <= 48000: raise ValueError('invalid-audio')
            samples = np.frombuffer(pcm, dtype='<i2')
            if rate == 16000: audio = samples.astype(np.float32) / 32768.
            else:
                import av
                frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format='s16', layout='mono'); frame.sample_rate = rate
                resampler = av.AudioResampler(format='flt', layout='mono', rate=16000)
                audio = np.concatenate([f.to_ndarray().reshape(-1) for f in resampler.resample(frame) + resampler.resample(None)])
            rms=float(np.sqrt(np.mean(audio**2)))
            if rms < .0003:
                reply({'type': 'transcript', 'id': identifier, 'text': '', 'segments': 0, 'uncertain': True}); continue
            if rms < .04: audio=np.clip(audio*min(12.,.08/rms),-1.,1.)
            segments, info = model.transcribe(audio, language=request.get('language') if request.get('language') in {'en', 'hi'} else None,
                beam_size=5, temperature=0., condition_on_previous_text=False, vad_filter=True,
                initial_prompt='MORICE. Research Lab. Builder. Settings. Desktop Orb.', word_timestamps=True)
            parts=[]; scores=[]
            for segment in segments:
                if segment.no_speech_prob > .65 and segment.avg_logprob < -.8: continue
                parts.append(segment.text.strip()); scores.append(segment.avg_logprob)
            text=' '.join(parts).strip()
            if len(text)>12000: raise ValueError('transcript-limit')
            reply({'type': 'transcript', 'id': identifier, 'text': text, 'segments': len(parts),
                'language': info.language, 'uncertain': not bool(text) or bool(scores and sum(scores)/len(scores)<-1.0)})
        except Exception:
            reply({'type': 'error', 'id': identifier, 'error': 'decode-failed'})
    return 0
