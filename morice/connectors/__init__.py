"""Official API providers registered with the existing capability kernel."""
from .contracts import ConnectorDescriptor, ConnectorState, ConnectorProvider,ConnectorOperation
from .github import GitHubProvider
from .registry import ConnectorRegistry

__all__ = ["ConnectorDescriptor", "ConnectorState", "ConnectorProvider", "ConnectorOperation", "GitHubProvider", "ConnectorRegistry"]
