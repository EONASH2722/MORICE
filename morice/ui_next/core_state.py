"""Public presentation state over the existing Kernel, workers and voice owners.

This module never schedules work, grants permissions or fabricates progress.
Only bounded public event metadata is retained; no prompts or reasoning text.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
import math
import time

from PySide6.QtCore import QObject, Signal, Slot, QTimer


class CoreState(str, Enum):
    IDLE = 'IDLE'
    ARMED = 'ARMED'
    LISTENING = 'LISTENING'
    UNDERSTANDING = 'UNDERSTANDING'
    THINKING = 'THINKING'
    WORKING = 'WORKING'
    MULTI_AGENT = 'MULTI_AGENT'
    SPEAKING = 'SPEAKING'
    SUCCESS = 'SUCCESS'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    SECURITY_ALERT = 'SECURITY_ALERT'
    MEDIA_GENERATING = 'MEDIA_GENERATING'
    RESEARCH_RUNNING = 'RESEARCH_RUNNING'
    WAITING_FOR_USER = 'WAITING_FOR_USER'


LABELS = {
    CoreState.IDLE: ('Ready when you are', 'Your private workspace'),
    CoreState.ARMED: ('Ready for your wake phrase', 'Voice is armed'),
    CoreState.LISTENING: ('Listening', 'Microphone input'),
    CoreState.UNDERSTANDING: ('Understanding your request', 'Voice command'),
    CoreState.THINKING: ('Preparing a response', 'Response in progress'),
    CoreState.WORKING: ('Working on your request', 'Live task activity'),
    CoreState.MULTI_AGENT: ('Working together', 'Active agent roles'),
    CoreState.SPEAKING: ('Speaking', 'Voice playback'),
    CoreState.SUCCESS: ('Completed', 'Task finished successfully'),
    CoreState.WARNING: ('Needs attention', 'Review the reported outcome'),
    CoreState.ERROR: ('Could not complete', 'Open Activity for details'),
    CoreState.SECURITY_ALERT: ('Security finding reported', 'Review evidence in Security'),
    CoreState.MEDIA_GENERATING: ('Creating media', 'Live generation activity'),
    CoreState.RESEARCH_RUNNING: ('Research is running', 'Live research activity'),
    CoreState.WAITING_FOR_USER: ('Waiting', 'A task needs input or a resource'),
}


@dataclass(frozen=True)
class CoreSnapshot:
    state: CoreState = CoreState.IDLE
    title: str = LABELS[CoreState.IDLE][0]
    detail: str = LABELS[CoreState.IDLE][1]
    # Node names are real capability/role identifiers, never imagined agents.
    nodes: tuple[str, ...] = ()
    audio_level: float = 0.0


class CorePresentation(QObject):
    changed = Signal(object)

    def __init__(self, owner, bridge, parent=None):
        super().__init__(parent)
        self.owner = owner; self.runtime = owner.runtime
        self.tasks = OrderedDict(); self.agents = OrderedDict(); self.media = OrderedDict(); self.workflows = OrderedDict()
        self.snapshot = CoreSnapshot(); self._wake = 'IDLE'; self._outcome = None
        self._closed = False; self.dropped_nodes = 0
        self.notice_timer = QTimer(self); self.notice_timer.setSingleShot(True); self.notice_timer.timeout.connect(self.sample)
        bridge.event_arrived.connect(self.runtime_event)

    def _put(self, table, key, value):
        if not key: return
        table[key] = value; table.move_to_end(key)
        while len(table) > 128: table.popitem(last=False); self.dropped_nodes += 1

    def _notice(self, state, seconds=3):
        priority = {CoreState.SUCCESS: 0, CoreState.WARNING: 1, CoreState.ERROR: 2, CoreState.SECURITY_ALERT: 3}
        if self._outcome and time.monotonic() < self._outcome[1] and priority.get(self._outcome[0], 0) > priority.get(state, 0): return
        self._outcome = (state, time.monotonic() + seconds)
        self.notice_timer.start(round(seconds * 1000) + 10)

    @Slot(str)
    def wake_changed(self, state):
        self._wake = state; self.sample()

    @Slot(object)
    def runtime_event(self, event):
        if self._closed: return
        kind = event.get('type', ''); payload = event.get('payload', {})
        identifier = str(event.get('task_id', ''))[:100]
        capability = str(payload.get('capability_id', '') or payload.get('capability_requirement', ''))[:100]
        if kind in {'task_queued', 'task_started', 'task_resumed', 'task_verifying', 'task_waiting'}:
            previous = self.tasks.get(identifier, {})
            self._put(self.tasks, identifier, {'capability': capability or previous.get('capability', ''), 'kind': kind, 'source': event.get('source', '')})
        elif kind in {'task_completed', 'task_failed', 'user_cancelled'}:
            self.tasks.pop(identifier, None)
            if not self.workflows and kind != 'user_cancelled' and payload.get('status') != 'cancelled':
                self._notice(CoreState.SUCCESS if kind == 'task_completed' else CoreState.ERROR)
        elif kind == 'workflow_changed':
            workflow = str(payload.get('workflow_id', ''))[:100]
            if payload.get('state') == 'running': self._put(self.workflows, workflow, 'running')
            elif payload.get('state') == 'completed':
                self.workflows.pop(workflow, None)
                status = payload.get('status')
                if status == 'succeeded': self._notice(CoreState.SUCCESS)
                elif status in {'failed', 'timed_out'}: self._notice(CoreState.ERROR)
                elif status == 'cancelled':
                    if self._outcome and self._outcome[0] == CoreState.SUCCESS: self._outcome = None; self.notice_timer.stop()
                else: self._notice(CoreState.WARNING)
        elif kind == 'worker_changed':
            key = (str(payload.get('workflow_id', ''))[:100], identifier)
            if payload.get('state') in {'running', 'verifying'}:
                self._put(self.agents, key, str(payload.get('role', ''))[:80])
            else: self.agents.pop(key, None)
        elif kind in {'media_queued', 'media_started'}:
            self._put(self.media, identifier, kind)
        elif kind in {'media_completed', 'media_failed', 'media_cancelled'}:
            self.media.pop(identifier, None)
            if kind != 'media_cancelled': self._notice(CoreState.SUCCESS if kind == 'media_completed' else CoreState.ERROR)
        elif kind == 'media_oom': self._notice(CoreState.WARNING, 6)
        elif kind == 'security_finding':
            severity = str(payload.get('severity', event.get('severity', ''))).lower()
            self._notice(CoreState.SECURITY_ALERT if severity in {'high', 'critical'} else CoreState.WARNING, 12)
        self.sample()

    @staticmethod
    def _level(value):
        try: value = float(value)
        except (ValueError, TypeError): return 0.0
        return min(1., max(0., value / 100)) if math.isfinite(value) else 0.0

    def sample(self):
        """Cheap lock-protected existing status/PCM reads; no worker or device probe."""
        if self._closed: return False
        state = CoreState.IDLE; audio = 0.; detail = ''
        voice = self.runtime.voice.status(); speech = self.runtime.speech_input.status()
        wake = getattr(self.owner, 'wake_controller', None)
        nodes = tuple(dict.fromkeys(role for role in self.agents.values() if role))[:8]
        if not nodes:
            nodes = tuple(dict.fromkeys(task['capability'] for task in self.tasks.values() if task['capability']))[:8]
        notice = self._outcome
        if notice is not None and time.monotonic() >= notice[1]: self._outcome = notice = None
        if notice is not None and notice[0] == CoreState.SECURITY_ALERT: state = notice[0]
        elif getattr(voice.state, 'value', '') == 'playing':
            state = CoreState.SPEAKING; audio = self._level(self.runtime.voice.audio_level())
        elif speech.listening:
            # The existing live-voice gate waits for the user's wake phrase.
            # A saved "enabled" preference alone does not imply a running mic.
            if getattr(self.owner, 'chat_mode', '') == 'voice' and not getattr(self.owner, 'awake', True) and not (wake is not None and wake.active):
                state = CoreState.ARMED
            else:
                state = CoreState.LISTENING; audio = self._level(self.runtime.speech_input.audio_level())
        elif wake is not None and wake.active and self._wake in {'UNDERSTANDING', 'WORKING', 'ERROR'}:
            state = CoreState[self._wake]
        elif 'media_started' in self.media.values(): state = CoreState.MEDIA_GENERATING
        elif len(self.agents) > 1: state = CoreState.MULTI_AGENT
        elif any(task['kind'] == 'task_waiting' for task in self.tasks.values()):
            state = CoreState.WAITING_FOR_USER; detail = 'Waiting for a resource or authorization · see Activity'
        elif any(task['capability'].startswith('research.') for task in self.tasks.values()): state = CoreState.RESEARCH_RUNNING
        elif self.tasks or self.agents or self.workflows: state = CoreState.WORKING
        elif self.media: state = CoreState.WAITING_FOR_USER; detail = 'Media job is queued'
        elif getattr(self.owner, 'is_busy', False):
            state = CoreState.WORKING if getattr(self.owner, 'chat_mode', '') == 'project' else CoreState.THINKING
        elif voice.active or voice.queued: state = CoreState.WORKING; detail = 'Preparing spoken reply'
        elif notice is not None: state = notice[0]
        title, default = LABELS[state]
        updated = CoreSnapshot(state, title, detail or default, nodes, audio)
        if updated != self.snapshot: self.snapshot = updated; self.changed.emit(updated)
        return state != CoreState.IDLE or self._outcome is not None

    def close(self):
        self._closed = True; self.notice_timer.stop(); self.tasks.clear(); self.agents.clear(); self.media.clear(); self.workflows.clear()

    def diagnostics(self):
        return {'state': self.snapshot.state.value, 'task_nodes': len(self.tasks), 'agent_nodes': len(self.agents),
            'media_nodes': len(self.media), 'active_workflows': len(self.workflows), 'maximum_per_source': 128, 'dropped_nodes': self.dropped_nodes}
