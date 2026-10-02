"""Persistent, collision-safe special-event scheduling for desktop pets."""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class PetEventDefinition:
    event_id: str
    pet_id: str
    minimum_interval: float
    maximum_interval: float
    probability: float
    priority: int
    sequence: tuple[tuple[str, float], ...]
    combat: bool = False


PET_EVENT_DEFINITIONS: tuple[PetEventDefinition, ...] = (
    PetEventDefinition(
        "ironman_armor_off",
        "ironman_mark42",
        2 * 60 * 60,
        5 * 60 * 60,
        0.60,
        3,
        (
            ("landing", 1.1),
            ("superhero_landing", 1.2),
            ("armor_off", 11.5),
            ("stabilize", 1.2),
            ("takeoff", 1.0),
            ("hover", 1.6),
        ),
    ),
    PetEventDefinition(
        "ironman_villain",
        "ironman_mark42",
        14 * 60,
        34 * 60,
        0.78,
        2,
        (
            ("enemy_alert", 1.2),
            ("enemy_chase", 2.5),
            ("enemy_attack", 2.4),
            ("enemy_victory", 1.8),
            ("stabilize", 1.0),
        ),
        combat=True,
    ),
    PetEventDefinition(
        "spiderman_symbiote",
        "spiderman",
        4 * 60 * 60,
        10 * 60 * 60,
        0.52,
        3,
        (
            ("symbiote_notice", 1.8),
            ("symbiote_transform", 4.5),
            ("symbiote_active", 8.0),
            ("symbiote_struggle", 4.5),
            ("symbiote_remove", 5.5),
            ("react", 1.2),
            ("perch", 1.4),
        ),
    ),
    PetEventDefinition(
        "spiderman_villain",
        "spiderman",
        12 * 60,
        30 * 60,
        0.80,
        2,
        (
            ("enemy_alert", 1.0),
            ("enemy_chase", 2.3),
            ("enemy_web", 2.8),
            ("enemy_victory", 2.2),
            ("swing", 1.8),
        ),
        combat=True,
    ),
    PetEventDefinition(
        "horse_graze_and_rear",
        "horse",
        9 * 60,
        22 * 60,
        0.90,
        1,
        (("graze", 7.5), ("rear", 1.8), ("gallop", 4.0), ("idle", 1.2)),
    ),
    PetEventDefinition(
        "skeleton_collapse_chain",
        "skeleton",
        8 * 60,
        20 * 60,
        0.92,
        1,
        (
            ("skeleton_collapse", 2.0),
            ("skeleton_scatter", 2.8),
            ("skeleton_reform", 3.2),
            ("react", 1.0),
        ),
    ),
    PetEventDefinition(
        "dog_special_play",
        "dog",
        7 * 60,
        18 * 60,
        0.92,
        1,
        (
            ("fetch_ready", 1.2),
            ("fetch_chase", 3.4),
            ("fetch_return", 3.2),
            ("fetch_celebrate", 2.2),
        ),
    ),
    PetEventDefinition(
        "cat_deep_sleep",
        "cat",
        10 * 60,
        25 * 60,
        0.94,
        1,
        (("cat_bed", 2.0), ("cat_deep_sleep", 12.0), ("cat_stretch", 3.0)),
    ),
)


_FREQUENCY_SCALE = {
    "off": None,
    "low": 2.0,
    "normal": 1.0,
    "high": 0.28,
    "showcase": 0.001,
}


def normalize_event_frequency(value: object) -> str:
    clean = str(value or "").strip().casefold()
    return clean if clean in _FREQUENCY_SCALE else "normal"


class RareEventScheduler:
    """Persist due-times so restarts cannot reset or repeatedly fire events."""

    def __init__(
        self,
        path: str | Path,
        *,
        frequency: str = "normal",
        definitions: Iterable[PetEventDefinition] = PET_EVENT_DEFINITIONS,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        self.frequency = normalize_event_frequency(frequency)
        self.definitions = tuple(definitions)
        self.rng = rng or random.Random()
        self.clock = clock
        self._state = self._load()

    def set_frequency(self, frequency: object) -> None:
        requested = normalize_event_frequency(frequency)
        if requested == self.frequency:
            return
        old_scale = _FREQUENCY_SCALE[self.frequency]
        new_scale = _FREQUENCY_SCALE[requested]
        self.frequency = requested
        if new_scale is None:
            return
        current = self.clock()
        ratio = new_scale / (old_scale if old_scale is not None else 1.0)
        dirty = False
        for record in self._state.get("events", {}).values():
            due_at = float(record.get("next_due", 0.0) or 0.0)
            if due_at > current:
                record["next_due"] = current + max(5.0, (due_at - current) * ratio)
                dirty = True
        if dirty:
            self._save()

    def event(self, event_id: str) -> PetEventDefinition | None:
        return next((item for item in self.definitions if item.event_id == event_id), None)

    def sequence(self, event_id: str) -> tuple[tuple[str, float], ...]:
        definition = self.event(event_id)
        return definition.sequence if definition is not None else ()

    def claim_due(
        self,
        pet_id: str,
        *,
        now: float | None = None,
        allow_combat: bool = True,
    ) -> PetEventDefinition | None:
        scale = _FREQUENCY_SCALE[self.frequency]
        if scale is None:
            return None
        current = self.clock() if now is None else float(now)
        candidates = sorted(
            (
                item
                for item in self.definitions
                if item.pet_id == pet_id and (allow_combat or not item.combat)
            ),
            key=lambda item: item.priority,
            reverse=True,
        )
        dirty = False
        for definition in candidates:
            record = self._state.setdefault("events", {}).setdefault(
                definition.event_id, {}
            )
            due_at = float(record.get("next_due", 0.0) or 0.0)
            if due_at <= 0.0:
                record["next_due"] = self._next_due(definition, current, scale)
                dirty = True
                continue
            if current < due_at:
                continue
            if self.rng.random() > definition.probability:
                retry_window = max(30.0, definition.minimum_interval * scale * 0.20)
                record["next_due"] = current + self.rng.uniform(
                    retry_window * 0.6, retry_window
                )
                dirty = True
                continue
            record["last_run"] = current
            record["next_due"] = self._next_due(definition, current, scale)
            self._save()
            return definition
        if dirty:
            self._save()
        return None

    def _next_due(
        self, definition: PetEventDefinition, current: float, scale: float
    ) -> float:
        minimum = max(5.0, definition.minimum_interval * scale)
        maximum = max(minimum, definition.maximum_interval * scale)
        return current + self.rng.uniform(minimum, maximum)

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("events", {}), dict):
                return data
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
        return {"version": 1, "events": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(self._state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


__all__ = [
    "PET_EVENT_DEFINITIONS",
    "PetEventDefinition",
    "RareEventScheduler",
    "normalize_event_frequency",
]
