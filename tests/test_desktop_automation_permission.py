"""Desktop opt-in is enforced by existing policy authorities, not only the UI."""
from unittest.mock import Mock

import pytest

from morice.kernel import CapabilityDescriptor,CapabilityKernel,ExecutionContext,ExecutionResult,TaskStatus
from morice.kernel.permissions import PermissionManager
from morice.pc_control import (ActionRisk,ControlAction,DESKTOP_AUTOMATION_GUIDANCE,
    PermissionBroker,PermissionCategory,PolicyMode)
from morice.settings import DEFAULT_SETTINGS
from morice.unified_intelligence import PermissionController,PermissionDecision,PermissionState,RiskClass


def broker(tmp_path):
    return PermissionBroker(tmp_path/'policy.json',require_desktop_automation=True,
        defaults={PermissionCategory.DESKTOP_AUTOMATION:PolicyMode.DENY,
                  PermissionCategory.APPLICATION_CONTROL:PolicyMode.ALLOW})


def test_desktop_is_off_by_default_and_not_granted_by_action_text(tmp_path):
    assert DEFAULT_SETTINGS['desktop_automation_enabled']=='false'
    policy=broker(tmp_path)
    action=ControlAction('application','open','Notepad',permissions=())
    grant=policy.request_confirmation(action)
    denied=policy.authorize(action,grant.token)
    assert not denied.allowed and not denied.confirmation_required
    assert denied.reason==DESKTOP_AUTOMATION_GUIDANCE
    assert 'Settings → Permissions & control' in denied.reason


def test_enabled_toggle_keeps_exact_confirmations_and_revocation(tmp_path):
    policy=broker(tmp_path)
    action=ControlAction('application','close','Notepad',risk=ActionRisk.DESTRUCTIVE)
    policy.set_policy(PermissionCategory.DESKTOP_AUTOMATION,PolicyMode.ALLOW)
    assert policy.authorize(action).confirmation_required
    grant=policy.request_confirmation(action)
    assert policy.authorize(action,grant.token).allowed
    assert not policy.authorize(action,grant.token).allowed
    pending=policy.request_confirmation(action)
    policy.set_policy(PermissionCategory.DESKTOP_AUTOMATION,PolicyMode.DENY)
    assert not policy.authorize(action,pending.token).allowed
    policy.set_policy(PermissionCategory.DESKTOP_AUTOMATION,PolicyMode.ALLOW)
    assert not policy.authorize(action,pending.token).allowed


def test_gate_does_not_block_internal_work_or_read_only_pc_status(tmp_path):
    policy=broker(tmp_path)
    policy.set_policy(PermissionCategory.READ_SYSTEM_STATE,PolicyMode.ALLOW)
    assert policy.authorize(ControlAction('system','status',permissions=(PermissionCategory.READ_SYSTEM_STATE,))).allowed
    assert policy.authorize(ControlAction('ui','navigate','research')).allowed


def test_kernel_gate_also_precedes_legacy_custom_permission_callbacks():
    controller=PermissionController(states={'desktop_automation':PermissionState.DENIED})
    kernel=CapabilityKernel(permissions=PermissionManager(controller))
    called=Mock(return_value=ExecutionResult(TaskStatus.SUCCEEDED,True))
    kernel.registry.register(CapabilityDescriptor('computer.set_value','Set accessible value'),called,
        permission_check=lambda *_:PermissionDecision(True))
    try:
        result=kernel.dispatch('computer.set_value',{'target':'owned fixture'},ExecutionContext())
        assert not result.success and DESKTOP_AUTOMATION_GUIDANCE in result.errors[0].message
        called.assert_not_called()
        controller.set_state('desktop_automation',PermissionState.GRANTED)
        assert kernel.dispatch('computer.set_value',{'target':'owned fixture'},ExecutionContext()).success
        assert called.call_count==1
    finally:kernel.shutdown()


def test_revoking_host_permission_invalidates_existing_exact_grants():
    controller=PermissionController(states={'desktop_automation':'granted'})
    arguments={'target':'owned fixture'}
    token=controller.issue_one_use('task','computer.invoke',arguments)
    controller.set_state('desktop_automation','denied')
    controller.set_state('desktop_automation','granted')
    assert not controller.authorize(task_id='task',capability_id='computer.invoke',arguments=arguments,
        permissions=(),risk=RiskClass.HIGH,approval_token=token).allowed


@pytest.mark.parametrize('state',['denied','unsupported','requires_os_permission'])
def test_scoped_custom_permission_cannot_override_explicit_host_policy(state):
    # Legacy tool tokens must respect the same explicit host denial as NLUI.
    if state=='requires_os_permission':state=PermissionState.OS_REQUIRED.value
    controller=PermissionController(states={'file_write':state})
    kernel=CapabilityKernel(permissions=PermissionManager(controller));called=Mock()
    kernel.registry.register(CapabilityDescriptor('fixture.write','Owned fixture write',required_permissions=('file_write',)),called,
        permission_check=lambda *_:PermissionDecision(True))
    try:
        result=kernel.dispatch('fixture.write',{},ExecutionContext())
        assert not result.success and result.errors[0].code.value=='permission_denied'
        called.assert_not_called()
    finally:kernel.shutdown()
