"""Windows SAPI adapter for the existing VoiceRuntime TTSProvider contract."""
from __future__ import annotations

import os
import time


class WindowsSpeechProvider:
    name = 'local'

    def stream_audio(self, chunks, config, cancel):
        if os.name != 'nt': raise ImportError('Windows system speech is unavailable on this platform.')
        import comtypes
        from comtypes.client import CreateObject
        comtypes.CoInitialize()
        try:
            voice = CreateObject('SAPI.SpVoice', dynamic=True)
            if voice.GetVoices().Count < 1: raise ImportError('No installed Windows speech voice is available.')
            voice.Rate = max(-5, min(5, round((config.speech_speed - 1) * 5)))
            # SAPI's documented 16-bit mono format enumeration.
            formats = {8000: 6, 16000: 18, 22050: 22, 24000: 26, 32000: 30, 44100: 34, 48000: 38}
            if config.sample_rate not in formats: raise ValueError('System speech does not implement this PCM sample rate.')
            for chunk in chunks:
                if cancel.is_set(): return
                text = str(chunk).strip()
                if not text: continue
                if len(text) > 2000: raise ValueError('System speech chunk exceeds its text budget.')
                stream = CreateObject('SAPI.SpMemoryStream', dynamic=True)
                stream.Format.Type = formats[config.sample_rate]
                voice.AudioOutputStream = stream
                voice.Speak(text, 1)  # SVSFlagsAsync; no unbounded synchronous call.
                deadline = time.monotonic() + config.request_timeout_seconds
                while not voice.WaitUntilDone(20):
                    if cancel.is_set(): voice.Speak('', 3); return  # async + purge
                    if time.monotonic() >= deadline:
                        voice.Speak('', 3); raise TimeoutError('System speech synthesis timed out.')
                pcm = bytes(stream.GetData())
                if len(pcm) > 8 * 1024 * 1024: raise ValueError('System speech output exceeds its audio budget.')
                for start in range(0, len(pcm), 8192):
                    if cancel.is_set(): return
                    yield pcm[start:start + 8192]
        finally:
            comtypes.CoUninitialize()
