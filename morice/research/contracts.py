"""Scientific state views backed by the existing ResearchStore, not chat text."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Provenance(str, Enum):
    CITED = "CITED"
    USER_DATA = "USER_DATA"
    CALCULATED = "CALCULATED"
    SIMULATED = "SIMULATED"
    MEASURED = "MEASURED"
    GENERATED_VISUAL = "GENERATED_VISUAL"
    INFERRED = "INFERRED"
    ESTIMATED = "ESTIMATED"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ResearchQuestion:
    text: str
    domain: str = "computational"
    status: str = "OPEN"
    importance: str = "normal"
    answer_state: str = "Evidence insufficient"
    uncertainty: str = "Not quantified"


@dataclass(frozen=True)
class ResearchProject:
    project_id: str
    objective: str
    created_at: str
    updated_at: str
    records: tuple = ()
    relationships: tuple = ()
    timeline: tuple = ()
    related_chats: tuple = ()

    @classmethod
    def from_snapshot(cls, snapshot):
        return cls(snapshot["id"], snapshot["objective"], snapshot["created"], snapshot["updated"],
                   tuple(snapshot["records"]), tuple(snapshot["edges"]), tuple(snapshot["timeline"]),
                   tuple(snapshot["related_chats"]))

    def select(self, kind, *, current=True):
        return tuple(r for r in self.records if r["kind"] == kind and (not current or not r["stale"]))

    def resume_context(self):
        kinds = ("question", "hypothesis", "assumption", "open_question", "experiment", "result", "failure")
        return {"project_id": self.project_id, "objective": self.objective,
                **{kind: self.select(kind)[-20:] for kind in kinds},
                "stale_records": [r["id"] for r in self.records if r["stale"]],
                "source_ids": [r["id"] for r in self.select("source")],
                "related_chats": self.related_chats}
