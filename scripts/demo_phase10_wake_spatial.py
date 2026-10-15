"""Actual Vosk + Windows SAPI PCM through the owned Qt wake/Spatial workflow.

Only the physical input/output devices are replaced by bounded memory transports.
Recognition, wake confidence, handoff, UI callbacks, TTS, Kernel and math are real.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(QT_QPA_PLATFORM='windows' if '--native' in sys.argv else 'offscreen',
    MORICE_PRELOAD='0', MORICE_DISABLE_SESSION='1', MORICE_DISABLE_RECOVERY='1',
    MORICE_START_AWAKE='1', MORICE_NODE_NETWORK='0', MORICE_REDUCE_MOTION='1')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from morice import settings
import morice.runtime_services as runtime_module
from morice.runtime_services import RuntimeServices
from morice.speech_runtime import SpeechInputConfig, find_vosk_model
from morice.local_speech_provider import WindowsSpeechProvider
from morice.config import TTSConfig
from morice.wake_runtime import write_wake_request
from morice.pyside_app import create_application_window
from morice.ui_next.wake import WakeState
import morice_wake_listener as listener
from vosk import Model


class QueuedPcmInput:
    def __init__(self, source):
        self.source = source; self.pcm = b''; self.offset = 0; self.stopped = threading.Event()

    def start(self): pass

    def read(self, timeout):
        if self.stopped.is_set(): return None
        if self.offset >= len(self.pcm):
            try: self.pcm = self.source.get(timeout=timeout)
            except queue.Empty: return None
            self.offset = 0
        data = self.pcm[self.offset:self.offset + 4000]; self.offset += len(data)
        return data

    def stop(self): self.stopped.set()
    def abort(self): self.stopped.set()


class PcmSink:
    def __init__(self):
        self.pcm = bytearray(); self.aborted = threading.Event(); self.closed = False
        self.sample_rate = 0

    def start(self, *, sample_rate, channels=1, dtype='int16'):
        assert channels == 1 and dtype == 'int16'; self.sample_rate = sample_rate

    def write(self, pcm):
        if self.aborted.is_set(): return
        self.pcm.extend(pcm)
        # Real PCM recorded at the provider's rate. A paced memory transport
        # allows the actual SPEAKING state to be observed without a loudspeaker.
        self.aborted.wait(min(.025, len(pcm) / (2 * self.sample_rate)))

    def abort(self): self.aborted.set()
    def close(self): self.closed = True


output = Path(sys.argv[sys.argv.index('--output')+1]).resolve() if '--output' in sys.argv else ROOT / 'build/phase10-wake-spatial-demo'
output.mkdir(parents=True, exist_ok=True)
app = QApplication.instance() or QApplication([])
audio = queue.Queue(maxsize=2); sinks = []; events = []; recognitions = []


def wait_until(predicate, label, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate(): return
        QTest.qWait(15)
    raise AssertionError('Timed out: ' + label)


def input_pcm(index):
    return (ROOT / f'build/phase10-voice-pcm/{index}.pcm').read_bytes() + bytes(64000)


def save_state(label, window):
    target = output / f'{label}.png'; assert window.grab().save(str(target))
    row = {'label': label, 'route': window.active_route, 'visible': window.isVisible(),
        'minimized': window.isMinimized(), 'context': window.runtime.spatial.snapshot(),
        'wake': window.wake_controller.diagnostics(), 'screenshot': str(target)}
    events.append(row); print(json.dumps({'label': label, 'route': row['route'],
        'wake': row['wake']['state'], 'result': {key: value for key, value in (row['context']['result'] or {}).items() if key in ('mode', 'metres', 'distance', 'unit', 'algorithm')}}), flush=True)


with tempfile.TemporaryDirectory(prefix='morice-wake-demo-') as directory:
    root = Path(directory); os.environ.update(APPDATA=str(root/'roaming'), LOCALAPPDATA=str(root/'local'), MORICE_LOCAL_DATA_DIR=str(root/'data'))
    with patch('morice.settings._settings_dir', return_value=str(root / 'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS, 'tts_provider': 'local',
            'tts_output_format': 'pcm_16000', 'tts_enabled': 'true', 'stt_enabled': 'true',
            'stt_auto_send': 'true', 'pet_enabled': 'false'})
        runtime = RuntimeServices(root / 'runtime', project_root=ROOT)
        runtime_module._RUNTIME_SERVICES = runtime
        runtime.speech_input.configure(SpeechInputConfig(model_path=find_vosk_model(), max_listen_seconds=30))
        runtime.speech_input._audio_factory = lambda config: QueuedPcmInput(audio)
        def make_sink(config):
            sink = PcmSink(); sinks.append(sink); return sink
        runtime.voice._sink_factory = make_sink
        window = create_application_window(runtime, runtime.start()); window.show(); app.processEvents()
        runtime.speech_input.prewarm()
        window.speech_transcript_ready.connect(lambda value: recognitions.append({
            'text': value.text, 'error': value.error_code, 'cancelled': value.cancelled,
            'duration_ms': value.duration_ms}))
        try:
            # Existing constrained recognizer and production confidence gate.
            wake_model = Model(find_vosk_model()); wake_attempts = []
            for utterance, expected in (('Morice.', 'morice'), ('Hey Morris.', 'hey morris'), ('Wake up Morice.', 'wake up morice')):
                pcm = b''.join(WindowsSpeechProvider().stream_audio((utterance,), TTSConfig(provider='local', output_format='pcm_16000'), threading.Event())) + bytes(64000)
                wake_recognizer = listener.make_recognizer(wake_model, 'morice'); wake_payload = None
                for offset in range(0, len(pcm), 4000):
                    if wake_recognizer.AcceptWaveform(pcm[offset:offset + 4000]):
                        candidate = json.loads(wake_recognizer.Result())
                        if candidate.get('text'): wake_payload = candidate; break
                if wake_payload is None: wake_payload = json.loads(wake_recognizer.FinalResult())
                accepted = listener.confident_wake_result(wake_payload, expected)
                wake_attempts.append({'utterance': utterance, 'payload': wake_payload, 'accepted': accepted,
                    'pcm_sha256': hashlib.sha256(pcm).hexdigest(), 'pcm_bytes': len(pcm)})
                print(json.dumps({'wake_attempt': wake_attempts[-1]}), flush=True)
                if accepted: break
            assert accepted, wake_attempts
            window.showMinimized(); app.processEvents()
            write_wake_request('magic phrase: ' + wake_payload['text'], path=window.wake_signal_path)
            window._check_external_wake_signal()
            wait_until(lambda: runtime.speech_input.status().listening, 'wake owns existing STT')
            assert window.isMinimized(), 'Wake activation raised the main window.'
            assert window.wake_controller.overlay.isVisible()
            assert window.wake_controller.overlay.testAttribute(Qt.WA_ShowWithoutActivating)
            assert window.wake_controller.overlay.grab().save(str(output / 'wake-listening.png'))
            for index, label, ready in (
                (1, 'earth', lambda c: window.active_route == 'spatial' and window.isVisible() and not window.isMinimized()),
                (2, 'locations-ambiguous', lambda c: bool(c['pending'])),
                (3, 'surface-km', lambda c: bool(c['result']) and c['result'].get('mode') == 'GEODESIC'),
                (4, 'surface-miles', lambda c: bool(c['result']) and c['result'].get('unit') == 'miles'),
                (5, 'chord-miles', lambda c: bool(c['result']) and c['result'].get('mode') == 'CHORD'),
                (6, 'new-york-chord-miles', lambda c: c['destination'] is not None and c['destination']['identifier'] == 'geonames:5128581'),
            ):
                wait_until(lambda: runtime.speech_input.status().listening and not runtime.voice.status().active
                    and runtime.voice.status().queued == 0 and window.wake_controller.state == WakeState.LISTENING,
                    'ready for ' + label, 30)
                count = len([r for r in recognitions if not r['cancelled'] and not r['error']]); messages = len(window.history)
                audio.put(input_pcm(index), timeout=1)
                wait_until(lambda: len([r for r in recognitions if not r['cancelled'] and not r['error']]) > count
                    and len(window.history) > messages and ready(runtime.spatial.snapshot())
                    and window.ui_bridge.diagnostics()['pending_deliveries'] == 0, label, 30)
                save_state(label, window)
                if index == 2:
                    view = window.routes['spatial']
                    candidate = next((view.candidates.item(i) for i in range(view.candidates.count())
                        if view.candidates.item(i).data(Qt.UserRole)[1] == 'geonames:5368361'), None)
                    assert candidate is not None, 'LA US candidate was not actually displayed.'
                    view.candidates.setCurrentItem(candidate)
                    QTest.keyClick(view.candidates, Qt.Key_Return)
                    wait_until(lambda: not runtime.spatial.snapshot()['pending'] and bool(runtime.spatial.snapshot()['result']), 'actual LA candidate selection')
                    save_state('locations-confirmed', window)
            context = runtime.spatial.snapshot()
            assert context['origin']['identifier'] == 'geonames:1264527'
            assert context['mode'] == 'CHORD' and context['unit'] == 'miles'
            assert context['result']['provenance'] == 'COMPUTED'
            assert len(context['result']['path']) == 2
            wait_until(lambda: not runtime.voice.status().active and runtime.voice.status().queued == 0
                and window.wake_controller.state == WakeState.LISTENING, 'final actual TTS completed', 30)
            assert any(s.pcm for s in sinks), 'No actual reply audio generated.'
            print(json.dumps({'actual_reply_sinks': [{'bytes': len(s.pcm), 'closed': s.closed, 'aborted': s.aborted.is_set()} for s in sinks]}), flush=True)
            assert len(sinks) == 6 and all(s.pcm and s.closed and not s.aborted.is_set() for s in sinks), 'Every command must deliver exactly one complete PCM reply.'
            window.wake_controller.cancel(); wait_until(lambda: not runtime.speech_input.status().listening, 'wake cancellation')
            assert not window.wake_controller.timeout.isActive()
            assert not window.wake_controller.overlay.isVisible()
            window.close(); app.processEvents(); runtime.shutdown()
            evidence = {'scope': 'Actual Windows SAPI PCM + existing Vosk wake/STT + existing VoiceRuntime TTS + Kernel + native owned Qt. Bounded memory audio transports; no physical microphone/speaker or cloud claim.',
                'status': 'CONTROLLED_WAKE_SPATIAL_WORKFLOW_PASSED', 'wake_payload': wake_payload, 'wake_attempts': wake_attempts,
                'wake_confidence': listener.recognition_confidence(wake_payload), 'recognitions': recognitions,
                'events': events, 'tts': [{'bytes': len(s.pcm), 'sha256': hashlib.sha256(s.pcm).hexdigest(),
                    'sample_rate': s.sample_rate, 'closed': s.closed, 'aborted': s.aborted.is_set()} for s in sinks],
                'wake_final': window.wake_controller.diagnostics(), 'shutdown': runtime.shutdown_report}
            assert evidence['shutdown']['clean']
            (output / 'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            print(json.dumps({'status': evidence['status'], 'tts_count': len(sinks), 'shutdown': evidence['shutdown']}), flush=True)
        finally:
            window.wake_controller.cancel(); window.close(); app.processEvents(); runtime.shutdown()
