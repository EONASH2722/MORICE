"""One authorization boundary reusing MORICE's existing policy authorities."""
from __future__ import annotations

from ..unified_intelligence import PermissionController, PermissionDecision, PermissionState, RiskClass
from .contracts import ExecutionContext
from .registry import CapabilityEntry


class PermissionManager:
    def __init__(self, controller: PermissionController | None = None):
        self.controller = controller or PermissionController()

    def authorize(self, entry: CapabilityEntry, inputs: dict, context: ExecutionContext) -> PermissionDecision:
        desktop = self.controller.desktop_automation_authorization(
            entry.descriptor.capability_id, (*entry.descriptor.required_permissions,*context.permissions))
        if not desktop.allowed:
            return desktop
        # A scoped legacy token may satisfy ASK; it cannot override an explicit
        # host denial, an unavailable permission or an outstanding OS grant.
        blocked=tuple(group for group in dict.fromkeys((*entry.descriptor.required_permissions,*context.permissions))
            if self.controller.state(group) in {PermissionState.DENIED,PermissionState.UNSUPPORTED,PermissionState.OS_REQUIRED})
        if blocked:
            return PermissionDecision(False,denied=blocked,reason='Permission denied, unsupported or requires an OS grant: '+', '.join(blocked))
        if entry.permission_check is not None:
            decision = entry.permission_check(inputs, context)
            if not decision.allowed or not context.permissions:
                return decision
            return self.controller.authorize(task_id=context.task_id,
                capability_id=entry.descriptor.capability_id, arguments=inputs,
                permissions=context.permissions, risk=RiskClass.LOW)
        d = entry.descriptor
        return self.controller.authorize(
            task_id=context.task_id, capability_id=d.capability_id,
            arguments=inputs, permissions=tuple(dict.fromkeys((*d.required_permissions, *context.permissions))),
            risk=d.risk_level, approval_token=context.approval_token,
        )


class RiskClassifier:
    @staticmethod
    def classify(entry: CapabilityEntry, *, destructive: bool = False) -> RiskClass:
        return RiskClass.CRITICAL if destructive else entry.descriptor.risk_level
