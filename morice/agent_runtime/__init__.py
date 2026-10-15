"""Parallel agents are scoped workers over the MORICE capability kernel."""
from .contracts import AgentResult, AgentRole, ContextPacket, ContextPolicy, RuntimeLimits, WorkerState
from .coordinator import AgentCoordinator, WorkflowResult
from .models import ModelBudget, ModelReply, SharedModelAdapter
from .planner import WorkflowPlanner
from .roles import RoleRegistry, default_roles
from .state import SharedTaskState
from .workers import WorkerManager
