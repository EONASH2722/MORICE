"""Owned local Whisper decoder: bounded PCM, cancellation and no model downloads."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

from .config import local_data_dir
from .process_ownership import spawn_owned_process, reap_owned_job

MAX_PCM_BYTES = 16_000 * 2 * 120


def find_whisper_model(explicit=""):
    override = explicit or os.getenv('MORICE_WHISPER_MODEL', '')
    candidates = [override] if str(override).strip() else [local_data_dir() / 'models/stt/faster-whisper-small']
    for candidate in candidates:
        if not str(candidate).strip(): continue
        path = Path(candidate).expanduser()
        if all((path / name).is_file() for name in ('config.json', 'model.bin', 'tokenizer.json')) and any((path/name).is_file() for name in ('vocabulary.txt','vocabulary.json')):
            return str(path.resolve())
    return ''


class RefinementError(RuntimeError): pass
class RefinementCancelled(RefinementError): pass


class WhisperRefiner:
    def __init__(self, model_path, *, resources=None, timeout=45.):
        self.model_path = str(model_path); self.resources = resources; self.timeout = timeout
        self._state_lock = threading.RLock(); self._operation = threading.Lock()
        self._process = None; self._reader = None; self._queue = None
        self._owner = 'speech-decoder:' + uuid.uuid4().hex; self._leased = False
        self._closed = False
        if resources is not None:
            from .kernel.resources import ResourceDescriptor
            if resources.descriptor('SPEECH_DECODER') is None: resources.register(ResourceDescriptor('SPEECH_DECODER'))

    def _acquire_operation(self, cancel):
        if cancel.is_set(): raise RefinementCancelled('cancelled')
        deadline = time.monotonic() + self.timeout
        while not self._operation.acquire(timeout=.05):
            if cancel.is_set(): raise RefinementCancelled('cancelled')
            if time.monotonic() > deadline: raise RefinementError('decoder-busy')

    @staticmethod
    def _read(process, messages):
        try:
            while line := process.stdout.readline(65537):
                if len(line) > 65536: break
                try: messages.put_nowait(json.loads(line))
                except (ValueError, queue.Full): break
        finally:
            try: messages.put_nowait({'type': 'stopped'})
            except queue.Full: pass

    def _receive(self, messages, cancel, *, expected='ready', identifier=None):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if cancel.is_set(): raise RefinementCancelled('cancelled')
            try: value = messages.get(timeout=.05)
            except queue.Empty: continue
            if self._closed or cancel.is_set():raise RefinementCancelled('cancelled')
            if not isinstance(value, dict): raise RefinementError('invalid-worker-response')
            if value.get('type') in {'error', 'stopped'}: raise RefinementError(value.get('error', 'decoder-stopped'))
            if value.get('type') == expected and (identifier is None or value.get('id') == identifier): return value
        raise RefinementError('decoder-timeout')

    def _start(self, cancel):
        with self._state_lock:
            if self._closed or cancel.is_set(): raise RefinementCancelled('decoder-closed')
            if self._process is not None and self._process.poll() is None: return self._process, self._queue
            if self._process is not None: self.stop()
            if not self.model_path: raise RefinementError('model-unavailable')
            if self.resources is not None and not self._leased:
                from .kernel.contracts import ResourceClaim
                if not self.resources.acquire(self._owner, (ResourceClaim('SPEECH_DECODER'),)): raise RefinementError('decoder-busy')
                self._leased = True
            command = [sys.executable]
            if not getattr(sys, 'frozen', False): command.append(str(Path(__file__).resolve().parents[1] / 'morice_app_launcher.py'))
            command.extend(('--morice-speech-worker', self.model_path))
            environment = {**os.environ, 'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
                'OMP_NUM_THREADS': '4','OPENBLAS_NUM_THREADS':'4','MKL_NUM_THREADS':'4'}
            try:
                process = spawn_owned_process(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    memory_limit_bytes=3 * 1024**3)
            except BaseException:
                if self._leased: self.resources.release(self._owner); self._leased = False
                raise
            self._process = process; self._queue = messages = queue.Queue(maxsize=8)
            self._reader = threading.Thread(target=self._read, args=(process, messages), daemon=True, name='morice-speech-decoder-output')
            self._reader.start()
        self._receive(messages, cancel)
        return process, messages

    def prewarm(self, cancel=None):
        cancel = cancel or threading.Event(); self._acquire_operation(cancel)
        try: self._start(cancel); return True
        except BaseException: self.stop(); raise
        finally: self._operation.release()

    def transcribe(self, pcm, sample_rate, *, language='en', cancel=None):
        if len(pcm) > MAX_PCM_BYTES or len(pcm) % 2: raise RefinementError('audio-limit')
        if not 8000 <= sample_rate <= 48000: raise RefinementError('sample-rate')
        cancel = cancel or threading.Event(); self._acquire_operation(cancel)
        try:
            process, messages = self._start(cancel); identifier = uuid.uuid4().hex
            request = {'id': identifier, 'pcm': base64.b64encode(pcm).decode('ascii'), 'sample_rate': sample_rate,
                       'language': language if language in {'en', 'hi'} else None}
            process.stdin.write(json.dumps(request).encode() + b'\n'); process.stdin.flush()
            return self._receive(messages, cancel, expected='transcript', identifier=identifier)
        except BaseException: self.stop(); raise
        finally: self._operation.release()

    def close(self):
        with self._state_lock: self._closed = True
        self.stop()

    def stop(self):
        with self._state_lock:
            process, reader = self._process, self._reader
            try:
                if process is not None and reap_owned_job(process, timeout=5.) is None:
                    if process.poll() is None: process.terminate()
                    process.wait(timeout=5.)
            except BaseException:
                if self._leased: self.resources.retain(self._owner, 'Speech decoder cleanup could not be verified.')
                raise
            else:
                self._process = self._reader = self._queue = None
                if reader is not None and reader is not threading.current_thread(): reader.join(1.)
                if process is not None:
                    for pipe in (process.stdin, process.stdout):
                        if pipe is not None: pipe.close()
                if self._leased: self.resources.confirm_cleanup(self._owner); self._leased = False


def correct_transcript(text):
    """Assistant-name spelling and known UI commands; preserve request arguments."""
    import re
    value = str(text).strip()
    pattern = r'^(?:morris|maurice|morice|mor ice)(?=\s*[,.!:]?\s+(?:opens?|shows?|start|stop|run|close|please|can|what|how|compare)\b)'
    corrected = re.sub(pattern, 'MORICE', value, count=1, flags=re.IGNORECASE)
    changes = [] if corrected == value else ['assistant-name']
    workspaces = r'(?:settings|home|core|chats?|projects?|builder|research(?:\s+lab)?|spatial|devices|media|automations|connectors|security|history|activity|tools|voice|artifacts|plugins)'
    imperative = re.sub(r'^(MORICE\s*[,.!:]?\s+)(opens|shows)(\s+(?:the\s+)?'+workspaces+r'\b)',lambda m:m[1]+m[2][:-1]+m[3],corrected,flags=re.IGNORECASE)
    if imperative != corrected: changes.append('workspace-command')
    return imperative, tuple(changes)
