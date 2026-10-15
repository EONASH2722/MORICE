from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol,Callable
import re


class ConnectorState(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class ConnectorDescriptor:
    connector_id: str
    name: str
    provider: str
    version: str = "1.0"
    auth_type: str = "oauth_device"
    capabilities: tuple[str, ...] = ("issue.read", "issue.create", "events.poll", "auth.step", "auth.refresh")
    event_types: tuple[str, ...] = ("github.issue.assigned", "github.issue.changed")
    permissions: tuple[str, ...] = ("issues.read", "issues.write")
    supports_webhooks: bool = True
    supports_polling: bool = True
    supports_streaming: bool = False
    supports_actions: bool = True
    supports_verification: bool = True
    rate_limit: int = 30
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}",self.connector_id) or not self.name or len(self.name)>160:
            raise ValueError("A safe connector id and bounded name are required.")
        if not 1<=len(self.capabilities)<=32 or any(not re.fullmatch(r"[a-z][a-z0-9_.]{0,80}",op) for op in self.capabilities):
            raise ValueError("Connector operations must use bounded capability identifiers.")


class ConnectorProvider(Protocol):
    descriptor: ConnectorDescriptor
    state: ConnectorState
    retry_at: float

    def operations(self) -> dict[str, ConnectorOperation]: ...
    def configuration(self) -> dict | None: ...
    def next_auth_operation(self, now: float) -> str | None: ...

    def read_issue(self, arguments, context): ...
    def create_issue(self, arguments, context): ...
    def poll(self, arguments, context): ...
    def verify(self, result, expected, context): ...
    def disconnect(self): ...


@dataclass(frozen=True)
class ConnectorOperation:
    handler: Callable
    scope: str = "read"
    write: bool = False
    input_schema: dict = field(default_factory=lambda:{"type":"object"})

    def __post_init__(self):
        if self.scope not in {"read","write","auth"} or self.write and self.scope!="write":
            raise ValueError("A provider write must use a distinct write scope.")
