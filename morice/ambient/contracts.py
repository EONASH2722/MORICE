"""Event provenance is assigned by authenticated adapters, never by external text."""
from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum


class Trust(str, Enum):
    LOCAL_OS = "LOCAL_OS"
    TRUSTED_NODE = "TRUSTED_NODE"
    SIGNED_WEBHOOK = "SIGNED_WEBHOOK"
    CONNECTED_PROVIDER = "CONNECTED_PROVIDER"
    UNTRUSTED_CONTENT = "UNTRUSTED_CONTENT"


class Autonomy(IntEnum):
    NOTIFY = 0
    READ = 1
    LOCAL_REVERSIBLE = 2
    CONFIRM = 3


@dataclass(frozen=True)
class AmbientEvent:
    event_type: str
    source: str
    source_id: str
    payload: dict = field(default_factory=dict)
    trust: Trust = Trust.UNTRUSTED_CONTENT
    severity: str = "INFO"
    project_id: str = ""
    device_id: str = ""
    authorization_context: str = ""
    dedupe_key: str = ""
    correlation_id: str = ""
    depth: int = 0
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self):
        if not self.event_type or not self.source or len(self.event_type) > 120 or len(self.source) > 120:
            raise ValueError("Event type and source are required and bounded.")
        Trust(self.trust)
        if self.severity not in {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValueError("Unknown event severity.")
        if not math.isfinite(self.timestamp) or not 0 <= self.depth <= 8:
            raise ValueError("Invalid event timestamp/depth.")
        for value in (self.source_id, self.project_id, self.device_id, self.authorization_context,
                      self.dedupe_key, self.correlation_id, self.event_id):
            if not isinstance(value, str) or len(value) > 256:
                raise ValueError("Event references must be bounded strings.")
        # Only a small structured envelope reaches the persistent audit. Provider
        # bodies, tokens and private content belong to on-demand read capabilities.
        if not isinstance(self.payload, dict) or len(self.payload) > 24:
            raise ValueError("Event payload exceeds its envelope budget.")
        forbidden = {"token", "secret", "password", "authorization", "cookie", "body", "content", "prompt"}
        for key, value in self.payload.items():
            if not isinstance(key, str) or any(part in key.lower() for part in forbidden):
                raise ValueError("Private content cannot be persisted in event envelopes.")
            if not isinstance(value, (str, int, float, bool, type(None))) or isinstance(value, str) and len(value) > 512:
                raise ValueError("Event payload must contain bounded scalars.")
        json.dumps(self.payload, allow_nan=False)


@dataclass(frozen=True)
class AmbientBudget:
    max_pending: int = 256
    max_events_per_tick: int = 32
    max_actions_per_minute: int = 20
    max_inflight: int = 1
    max_model_calls: int = 0
    max_network_calls_per_minute: int = 30
    max_tick_seconds: float = .025
    max_history: int = 5000
    poll_min_seconds: float = 15.0

    def __post_init__(self):
        if not (8 <= self.max_pending <= 4096 and 1 <= self.max_events_per_tick <= 128
                and 1 <= self.max_inflight <= 2 and 1 <= self.max_actions_per_minute <= 120
                and 0 <= self.max_model_calls <= 8 and 1 <= self.max_network_calls_per_minute <= 120
                and 100 <= self.max_history <= 50000 and .001 <= self.max_tick_seconds <= .1
                and 1 <= self.poll_min_seconds <= 3600):
            raise ValueError("Invalid ambient budget.")


@dataclass
class Trigger:
    name: str
    event_type: str
    conditions: dict = field(default_factory=dict)
    action: str = "notification.publish"
    arguments: dict = field(default_factory=dict)
    level: Autonomy = Autonomy.NOTIFY
    trust: tuple[str, ...] = (Trust.LOCAL_OS.value, Trust.TRUSTED_NODE.value,
                              Trust.SIGNED_WEBHOOK.value, Trust.CONNECTED_PROVIDER.value)
    source_id: str = ""
    project_id: str = ""
    device_id: str = ""
    enabled: bool = False
    target_node_id: str = "local"
    expected_outcome: dict | None = None
    paused: bool = False
    cooldown_seconds: float = 60
    expires_at: float | None = None
    schedule_at: float | None = None
    interval_seconds: float | None = None
    notification_policy: str = "matched"
    min_severity: str = "INFO"
    quiet_start_hour: int | None = None
    quiet_end_hour: int | None = None
    critical_override: bool = False
    trigger_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self):
        self.level = Autonomy(self.level)
        if not self.name or len(self.name) > 160 or not self.event_type or len(self.event_type) > 120:
            raise ValueError("A bounded watch name and event type are required.")
        if not math.isfinite(self.cooldown_seconds) or not 0 <= self.cooldown_seconds <= 86400:
            raise ValueError("Invalid cooldown.")
        if len(self.conditions) > 16 or len(self.arguments) > 24:
            raise ValueError("Watch configuration is too large.")
        for key, condition in self.conditions.items():
            if not isinstance(condition, dict) or set(condition) != {"op", "value"} or condition["op"] not in {"eq", "ne", "lt", "le", "gt", "ge"}:
                raise ValueError("Conditions require a deterministic operator and scalar value.")
            AmbientEvent("validation", "local", "", {key: condition["value"]})
        if self.notification_policy not in {"matched", "failed_only", "quiet"} or self.min_severity not in {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValueError("Invalid notification policy.")
        for hour in (self.quiet_start_hour, self.quiet_end_hour):
            if hour is not None and not 0 <= hour < 24:
                raise ValueError("Invalid quiet period.")
        for stamp in (self.expires_at, self.schedule_at):
            if stamp is not None and not math.isfinite(stamp):
                raise ValueError("Invalid watch timestamp.")
        if self.interval_seconds is not None and (not math.isfinite(self.interval_seconds) or self.interval_seconds < 60):
            raise ValueError("Recurring schedules require at least 60 seconds.")
        if any(t not in {e.value for e in Trust} for t in self.trust):
            raise ValueError("Invalid trust filter.")
        raw = json.dumps(self.arguments, allow_nan=False)
        def secret_key(value,depth=0):
            if depth>4:return True
            if isinstance(value,dict):
                return any(any(word in str(key).lower() for word in ("token","password","secret","cookie","approval")) or secret_key(v,depth+1) for key,v in value.items())
            if isinstance(value,list):return any(secret_key(v,depth+1) for v in value)
            return False
        if len(raw) > 8192 or secret_key(self.arguments):
            raise ValueError("Secrets/approval tokens must not be stored in watch templates.")
        if not isinstance(self.target_node_id,str) or not self.target_node_id or len(self.target_node_id)>128:
            raise ValueError("A bounded target node is required.")
