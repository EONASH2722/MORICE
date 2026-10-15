"""Action evidence extends the kernel's existing result and verification contracts."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class VerificationLevel(str, Enum):
    NONE = "none"
    BASIC = "basic"
    NORMAL = "normal"
    STRICT = "strict"
    DOMAIN_SPECIFIC = "domain_specific"


class ActionMethod(str, Enum):
    APPLICATION_API = "application_api"
    OPERATING_SYSTEM = "operating_system"
    FILESYSTEM = "filesystem"
    CLI = "cli"
    BROWSER_DOM = "browser_dom"
    ACCESSIBILITY = "accessibility"
    FOREGROUND = "foreground"
    VISION = "vision"


@dataclass(frozen=True)
class ActionSpec:
    action_id: str
    task_id: str
    goal: str
    target: str
    capability_id: str
    method: ActionMethod
    desired_state: dict[str, Any]
    level: VerificationLevel = VerificationLevel.NORMAL
    observation_timeout: float = 3.0
    max_observations: int = 40
    freshness_seconds: float = 2.0
    rollback_reference: str = ""
    expected_outcome: Any = None


@dataclass(frozen=True)
class Observation:
    action_id: str
    source: str
    state: dict[str, Any]
    evidence: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    confidence: float = 1.0  # Descriptive only; never a success threshold.
    raw_reference: str = ""
    timestamp: float = field(default_factory=time.time)
    observation_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class ActionBinding:
    method: ActionMethod
    desired: Callable
    observe: Callable
    verify: Callable
    execute: Callable | None = None
    idempotent: bool = False


class UserInterventionRequired(RuntimeError):
    pass
