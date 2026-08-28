from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class ActionState(str, Enum):
    STARTED = "started"
    VERIFIED = "verified"
    FOUND = "found"
    RUNNING = "running"
    FAILED = "failed"


@dataclass(frozen=True)
class SpeechDelivery:
    """Small, deterministic delivery hints; computing these never calls a model."""

    speed: float = 1.0
    stability: float = 0.5
    style: float = 0.0
    kind: str = "explanation"

    def provider_settings(self) -> dict[str, float]:
        return {
            "speed": max(0.7, min(1.2, float(self.speed))),
            "stability": max(0.0, min(1.0, float(self.stability))),
            "style": max(0.0, min(1.0, float(self.style))),
        }


_VERIFIED_ACTIONS: Mapping[str, str] = {
    "application.open": "Opened.",
    "application.close": "Closed.",
    "application.focus": "Focused.",
    "application.minimize": "Minimized.",
    "application.maximize": "Maximized.",
    "media.pause": "Paused.",
    "media.resume": "Playing.",
    "media.next": "Skipped.",
    "media.previous": "Previous track.",
    "media.restart": "Restarted.",
    "media.set_volume": "Done.",
    "media.adjust_volume": "Done.",
}


def action_acknowledgement(
    action: str,
    state: ActionState,
    *,
    failure: str = "",
) -> str:
    """Return a tiny response only when the supplied state makes it truthful."""

    action_id = str(action or "").strip().casefold()
    if state is ActionState.VERIFIED:
        return _VERIFIED_ACTIONS.get(action_id, "Done.")
    if state is ActionState.STARTED:
        return "On it."
    if state is ActionState.FOUND:
        return "Found it."
    if state is ActionState.RUNNING:
        return "Almost."
    reason = " ".join(str(failure or "").split())
    return "Not yet." + (f" {reason}" if reason else "")


def speech_delivery(text: str, *, warning: bool = False, urgent: bool = False) -> SpeechDelivery:
    """Infer lightweight ElevenLabs delivery values without delaying first audio."""

    clean = " ".join(str(text or "").split())
    words = re.findall(r"[\w']+", clean, flags=re.UNICODE)
    warning_text = bool(
        warning
        or re.search(
            r"\b(?:warning|failed|failure|danger|unsafe|denied|cannot|can't|not yet|error)\b",
            clean,
            flags=re.IGNORECASE,
        )
    )
    if warning_text:
        return SpeechDelivery(0.96, 0.68, 0.08, "warning")
    if urgent or (len(words) <= 4 and len(clean) <= 42):
        return SpeechDelivery(1.12, 0.42, 0.18, "acknowledgement")
    if len(words) >= 45:
        return SpeechDelivery(0.98, 0.56, 0.04, "explanation")
    return SpeechDelivery()


__all__ = [
    "ActionState",
    "SpeechDelivery",
    "action_acknowledgement",
    "speech_delivery",
]
