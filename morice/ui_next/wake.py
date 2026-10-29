"""Compact presentation/controller for the existing wake and voice pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
import math
import time

from pathlib import Path
import json

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient, QPixmap
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QApplication

from .themes import stylesheet
from .icons import icon
from ..media_lab.storage import atomic_json
from ..kernel import CancellationToken
from .core_view import draw_core
from .core_state import CoreSnapshot, CoreState


class WakeState(str, Enum):
    IDLE = 'IDLE'
    LISTENING = 'LISTENING'
    UNDERSTANDING = 'UNDERSTANDING'
    WORKING = 'WORKING'
    SPEAKING = 'SPEAKING'
    ERROR = 'ERROR'


@dataclass(frozen=True)
class WakePreferences:
    enabled: bool = True
    orb_enabled: bool = True
    position: str = 'bottom_center'
    size: int = 80
    idle_visible: bool = False
    transcript: bool = True
    fullscreen: str = 'small_overlay'
    activation_sound: bool = False
    command_timeout: float = 8.0
    processing_timeout: float = 30.0
    idle_timeout: float = 5.0

    def __post_init__(self):
        for key in ('enabled', 'orb_enabled', 'idle_visible', 'transcript', 'activation_sound'):
            if type(getattr(self, key)) is not bool: raise ValueError('Wake switches must be boolean data.')
        if self.position not in {'bottom_center', 'bottom_left', 'bottom_right'} or self.fullscreen not in {'audio_only', 'small_overlay', 'normal_overlay', 'disabled_overlay'}:
            raise ValueError('Unknown wake position/fullscreen policy.')
        if type(self.size) is not int or not 48 <= self.size <= 160:
            raise ValueError('Wake orb size must be within 48…160.')
        for value in (self.command_timeout, self.processing_timeout, self.idle_timeout):
            if type(value) not in (int, float) or not math.isfinite(value) or not 1 <= value <= 60: raise ValueError('Wake timeout must be bounded.')


class WakeOrb(QWidget):
    def __init__(self, theme, policy, clock, parent=None):
        super().__init__(parent)
        self.theme = theme; self.policy = policy; self.clock = clock
        self.state = WakeState.IDLE; self.level = 0.; self._phase = 0.; self.setFixedSize(80, 80)
        self.level_source = None
        self.setAccessibleName('MORICE wake state'); clock.subscribe(self, self.tick)

    def tick(self, delta):
        if self.state == WakeState.IDLE: return False
        previous = self.level; self.level = self.level_source() if self.level_source is not None else 0.
        moving = self.policy.budget.decorative_motion and self.policy.budget.effective != 'LOW'
        if moving: self._phase += delta * self.theme.profile.motion_speed
        if moving or self.level != previous: self.update()
        return moving or self.state in {WakeState.LISTENING, WakeState.SPEAKING}

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        level = min(1., max(0., self.level / 100)) if math.isfinite(self.level) else 0.
        snapshot = CoreSnapshot(state=CoreState(self.state.value), audio_level=level)
        draw_core(painter, QRectF(self.rect()), snapshot, self.theme.tokens, self._phase, min(3, self.theme.profile.orbital_complexity), self.theme.profile.core_brightness, self.policy.budget.decorative_motion and self.policy.budget.effective != 'LOW', self.theme.profile.motion_strength)
        painter.end()


class WakeOverlay(QWidget):
    cancelled = Signal()
    reviewed_command = Signal()

    def __init__(self, theme, policy, clock):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.theme = theme; self.setObjectName('WakeOverlay'); self.setAttribute(Qt.WA_ShowWithoutActivating); self.setAttribute(Qt.WA_QuitOnClose, False)
        layout = QVBoxLayout(self); layout.setContentsMargins(18, 12, 18, 12); layout.setSpacing(6)
        self.orb = WakeOrb(theme, policy, clock); layout.addWidget(self.orb, alignment=Qt.AlignHCenter)
        self.state_label = QLabel('MORICE'); self.state_label.setAlignment(Qt.AlignCenter); layout.addWidget(self.state_label)
        self.transcript = QLabel(); self.transcript.setAlignment(Qt.AlignCenter); self.transcript.setWordWrap(True); self.transcript.setMaximumWidth(360); self.transcript.setTextFormat(Qt.PlainText); layout.addWidget(self.transcript)
        row = QHBoxLayout(); self.run = QPushButton('Send command'); self.run.clicked.connect(self.reviewed_command); self.run.hide()
        self.cancel = QPushButton('Cancel'); self.cancel.clicked.connect(self.cancelled); row.addWidget(self.run); row.addWidget(self.cancel); layout.addLayout(row)
        self.run.setIcon(icon('send', theme)); self.cancel.setIcon(icon('stop', theme))
        self.setStyleSheet(stylesheet(theme.tokens)); theme.changed.connect(self._theme)

    def _theme(self, *_):
        self.setStyleSheet(stylesheet(self.theme.tokens)); self.run.setIcon(icon('send', self.theme)); self.cancel.setIcon(icon('stop', self.theme)); self.update()

    def place(self, preferences, screen=None):
        self.orb.setFixedSize(preferences.size, preferences.size); self.adjustSize()
        screen = screen or QApplication.primaryScreen()
        if screen is None: return
        area = screen.availableGeometry(); margin = 24
        x = area.left() + margin if preferences.position == 'bottom_left' else area.right() - self.width() - margin if preferences.position == 'bottom_right' else area.center().x() - self.width() // 2
        self.move(max(area.left(), min(x, area.right() - self.width())), max(area.top(), area.bottom() - self.height() - margin))


class WakeController(QObject):
    """No recognizer, microphone or TTS worker: existing window callbacks own them."""
    changed = Signal(str)

    def __init__(self, window, theme, policy, clock, preferences=None):
        super().__init__(window)
        self.owner = window; self.runtime = window.runtime; self.preference_error = ''
        self.preferences_path = self.runtime.directory / 'renovation/wake.json'
        if preferences is None and self.preferences_path.exists():
            try:
                if self.preferences_path.stat().st_size > 8192: raise ValueError('Wake preferences too large.')
                preferences = WakePreferences(**json.loads(self.preferences_path.read_text()))
            except (OSError, ValueError, TypeError) as exc:
                self.preference_error = str(exc); preferences = WakePreferences(enabled=False)
        self.preferences = preferences or WakePreferences()
        self.overlay = WakeOverlay(theme, policy, clock); self.clock = clock; self.theme = theme
        self.state = WakeState.IDLE; self.active = False; self._return_mode = 'normal'; self._started_at = 0.; self._deadline = 0.; self._pending_text = ''
        self.transitions = []; self._fullscreen = False
        self.tts_request_id = ''
        self.stt_request_id = ''; self.epoch = 0; self.interaction_token = None
        self.timeout = QTimer(self); self.timeout.setSingleShot(True); self.timeout.timeout.connect(self._expired)
        self.overlay.cancelled.connect(self.cancel); self.overlay.reviewed_command.connect(self.submit_reviewed)

    def set_state(self, state, message='', timeout=None):
        self.state = WakeState(state); self.transitions.append({'state': self.state.value, 'at': time.monotonic()}); self.transitions = self.transitions[-100:]
        self.overlay.orb.state = self.state; self.overlay.state_label.setText(message or self.state.value.title())
        self.overlay.orb.level_source = self.runtime.speech_input.audio_level if self.state == WakeState.LISTENING else self.runtime.voice.audio_level if self.state == WakeState.SPEAKING else None
        self.overlay.orb.setAccessibleName('MORICE ' + self.state.value.lower()); self.overlay.orb.update()
        self.changed.emit(self.state.value); self.timeout.stop()
        if timeout is not None:
            self._deadline = time.monotonic() + timeout; self.timeout.start(round(timeout * 1000))
        self.clock.request()

    def activate(self, source='existing wake listener', *, fullscreen=False):
        if not self.preferences.enabled: return False
        if not self.active: self._return_mode = self.owner.chat_mode
        if self.interaction_token is not None: self.interaction_token.cancel('wake-rearmed')
        self.epoch += 1; self.interaction_token = CancellationToken(); self.stt_request_id = ''; self.tts_request_id = ''
        self.runtime.speech_input.cancel('wake-rearmed')
        self._fullscreen = bool(fullscreen); self.active = True; self._started_at = time.monotonic()
        self.runtime.voice.interrupt('wake-barge-in'); self.runtime.realtime.cancel_active('wake-barge-in')
        self._pending_text = ''; self.overlay.transcript.clear(); self.overlay.run.hide()
        small = fullscreen and self.preferences.fullscreen == 'small_overlay'
        self.overlay.transcript.setVisible(self.preferences.transcript and not small)
        self.overlay.place(replace(self.preferences, size=min(64, self.preferences.size)) if small else self.preferences, self.owner.screen())
        show = self.preferences.orb_enabled and not (fullscreen and self.preferences.fullscreen in {'audio_only', 'disabled_overlay'})
        if show: self.overlay.show()
        else: self.overlay.hide()
        if self.preferences.activation_sound: QApplication.beep()
        self.set_state(WakeState.LISTENING, 'Listening…', self.preferences.command_timeout)
        if self.owner.chat_mode != 'voice': self.owner._set_chat_mode('voice')
        else:
            self.owner._voice_conversation_active = True; self.owner.awake = True; self.owner._begin_voice_listening()
        return True

    def partial(self, text):
        if not self.active: return
        if self.preferences.transcript: self.overlay.transcript.setText(str(text)[:240])
        self.overlay.orb.level = self.runtime.speech_input.audio_level()

    def transcript(self, result):
        if not self.active: return False
        if result is not None and (not self.stt_request_id or result.request_id != self.stt_request_id): return True
        if result is None or result.cancelled or result.error_code or not result.text.strip():
            self.set_state(WakeState.ERROR, result.message if result is not None else 'Speech input unavailable.', 2)
            return True
        self._pending_text = result.text.strip()
        if self._pending_text.casefold().strip(' .?!') in {'cancel', 'stop', 'never mind', 'nevermind', 'go to sleep'}:
            self.cancel(); return True
        if self.preferences.transcript: self.overlay.transcript.setText(self._pending_text[:240])
        self.set_state(WakeState.UNDERSTANDING, 'Understanding…', self.preferences.processing_timeout)
        self.owner.input.setText(self._pending_text)
        if self.runtime.speech_input.config.auto_send: self.submit_reviewed()
        else:
            self.overlay.run.show();self.overlay.state_label.setText('Review the transcript, then send.')
            # Manual transcript review needs its real Send/Cancel controls even
            # when the main chat replaced the optional listening orb.
            self.overlay.show()
        return True

    def submit_reviewed(self):
        if not self.active or not self._pending_text: return
        self.owner._pending_transcript = None; self.overlay.run.hide()
        self.set_state(WakeState.WORKING, 'Working…', self.preferences.processing_timeout)
        self.owner.on_send()

    def result(self, text):
        if not self.active: return
        if self.preferences.transcript: self.overlay.transcript.setText(str(text)[:240])
        status = self.runtime.voice.status()
        if status.active or status.queued or self.tts_request_id:
            self.set_state(WakeState.SPEAKING if status.state.value == 'playing' else WakeState.WORKING,
                'Speaking…' if status.state.value == 'playing' else 'Preparing speech…', self.preferences.processing_timeout)
        else: self.continue_listening()

    def voice_event(self, event, metadata):
        if self.active and metadata.get('requestId') == self.tts_request_id and event == 'playback_started':
            self.set_state(WakeState.SPEAKING, 'Speaking…', self.preferences.processing_timeout)

    def continue_listening(self):
        if not self.active: return
        self._pending_text = ''; self.tts_request_id = ''
        if not self.runtime.speech_input.status().listening: self.stt_request_id = ''
        self.set_state(WakeState.LISTENING, 'Listening for a follow-up…', min(self.preferences.command_timeout, self.preferences.idle_timeout))
        self.owner._begin_voice_listening()

    def playback_finished(self, result):
        if not self.active: return False
        if result is not None and result.request_id != self.tts_request_id: return True
        if result is not None and result.cancelled and self.state in {WakeState.LISTENING, WakeState.UNDERSTANDING, WakeState.WORKING}: return True
        if result is not None and not result.success and not result.cancelled:
            self.set_state(WakeState.ERROR, result.message, 2)
        else: self.continue_listening()
        return True

    def finish(self):
        if not self.active: return
        self.active = False; self._pending_text = ''; self.tts_request_id = ''; self.stt_request_id = ''; self.timeout.stop(); self.epoch += 1
        if self.interaction_token is not None: self.interaction_token.cancel('wake-interaction-finished')
        self.owner._stop_voice_mode_io('wake-interaction-finished')
        self.owner.chat_mode = self._return_mode
        self.set_state(WakeState.IDLE, 'MORICE')
        self.overlay.orb.level = 0; self.overlay.run.hide()
        if self.preferences.idle_visible and self.preferences.orb_enabled:
            self.overlay.transcript.clear(); self.overlay.place(self.preferences); self.overlay.show()
        else: self.overlay.hide()

    def cancel(self):
        if self.active:
            self.runtime.voice.interrupt('wake-cancel'); self.runtime.speech_input.cancel('wake-cancel'); self.runtime.realtime.cancel_active('wake-cancel')
            self.finish()

    def _expired(self):
        self.cancel()

    def close(self):
        self.cancel(); self.timeout.stop(); self.clock.unsubscribe_id(id(self.overlay.orb)); self.overlay.close()
        return True

    def update_preferences(self, **changes):
        self.preferences = replace(self.preferences, **changes)
        atomic_json(self.preferences_path, asdict(self.preferences)); self.preference_error = ''
        if not self.preferences.enabled: self.cancel()
        self.overlay.place(self.preferences, self.owner.screen())

    def diagnostics(self):
        return {'state': self.state.value, 'active': self.active, 'overlay_visible': self.overlay.isVisible(), 'timer_active': self.timeout.isActive(),
            'fullscreen_policy': self.preferences.fullscreen, 'transitions': list(self.transitions), 'recognizer_owner': 'existing SpeechToTextRuntime', 'tts_owner': 'existing VoiceRuntime'}
