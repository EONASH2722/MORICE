"""Explicit selection follows the existing file permission state."""
from ..unified_intelligence import PermissionState


def require_selected_file(runtime, permission):
    state = runtime.kernel.permissions.controller.state(permission)
    if state not in {PermissionState.ASK, PermissionState.GRANTED}:
        raise PermissionError(f'Existing {permission} policy is {state.value}; this action is unavailable.')
    # ASK consent is the explicit file selection, as in existing Research/Media.
    # This does not grant a permission or authorize any later arbitrary path.

