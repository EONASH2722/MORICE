"""Small serializable intent/context records; no execution or permission owner."""
from __future__ import annotations

from dataclasses import dataclass,field
import time
import uuid


@dataclass(frozen=True)
class Operation:
    capability_id: str
    arguments: dict=field(default_factory=dict)


@dataclass
class IntentResolution:
    request_id: str=field(default_factory=lambda:uuid.uuid4().hex)
    operations: tuple[Operation,...]=()
    question: str=''
    choices: tuple[dict,...]=()
    unresolved_slot: str=''
    source_refs: tuple[dict,...]=()
    route: str='unmatched'
    context_request: str=''
    created_at: float=field(default_factory=time.time)

    @property
    def matched(self):return bool(self.operations or self.question)


@dataclass(frozen=True)
class ActiveContext:
    conversation_id: str
    window_id: str
    route: str='chats'
    project_id: str=''
    research_project_id: str=''
    selected: tuple[dict,...]=()
    last_turn_key: str=''


@dataclass(frozen=True)
class NaturalLanguageResult:
    request_id: str
    status: str
    message: str
    executions: tuple[dict,...]=()
    source_refs: tuple[dict,...]=()
    presentation: dict|None=None
