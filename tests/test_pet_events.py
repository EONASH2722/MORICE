import json
import random

from morice.pet_events import PetEventDefinition, RareEventScheduler


def _definition(*, combat=False):
    return PetEventDefinition(
        "test_event",
        "dog",
        10.0,
        10.0,
        1.0,
        1,
        (("fetch_ready", 1.0), ("fetch_chase", 1.0)),
        combat=combat,
    )


def test_first_poll_only_schedules_and_persists(tmp_path):
    path = tmp_path / "events.json"
    scheduler = RareEventScheduler(
        path,
        definitions=(_definition(),),
        rng=random.Random(7),
        clock=lambda: 100.0,
    )

    assert scheduler.claim_due("dog") is None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["events"]["test_event"]["next_due"] == 110.0


def test_due_event_is_claimed_once_and_gets_new_cooldown(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(
        json.dumps({"version": 1, "events": {"test_event": {"next_due": 90.0}}}),
        encoding="utf-8",
    )
    scheduler = RareEventScheduler(
        path,
        definitions=(_definition(),),
        rng=random.Random(7),
        clock=lambda: 100.0,
    )

    event = scheduler.claim_due("dog")

    assert event is not None
    assert event.event_id == "test_event"
    assert scheduler.claim_due("dog") is None
    reloaded = RareEventScheduler(path, definitions=(_definition(),), clock=lambda: 100.0)
    assert reloaded.claim_due("dog") is None


def test_off_and_combat_filter_never_claim(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(
        json.dumps({"version": 1, "events": {"test_event": {"next_due": 1.0}}}),
        encoding="utf-8",
    )
    off = RareEventScheduler(
        path, frequency="off", definitions=(_definition(),), clock=lambda: 100.0
    )
    filtered = RareEventScheduler(
        path, definitions=(_definition(combat=True),), clock=lambda: 100.0
    )

    assert off.claim_due("dog") is None
    assert filtered.claim_due("dog", allow_combat=False) is None


def test_switching_to_showcase_rescales_existing_due_time(tmp_path):
    path = tmp_path / "events.json"
    path.write_text(
        json.dumps({"version": 1, "events": {"test_event": {"next_due": 1100.0}}}),
        encoding="utf-8",
    )
    scheduler = RareEventScheduler(
        path, frequency="normal", definitions=(_definition(),), clock=lambda: 100.0
    )

    scheduler.set_frequency("showcase")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["events"]["test_event"]["next_due"] == 105.0
