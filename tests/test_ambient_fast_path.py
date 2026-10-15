"""Controlled native application path while the independent ambient queue is full."""
import time
from unittest.mock import patch
from morice.agent_runtime import AgentCoordinator
from morice.ambient import AmbientEvent,Trust
from test_ambient_cross_phase import attach


def test_open_calculator_direct_pc_path_bypasses_event_and_agent_queue(tmp_path):
    from test_verified_actions import VerifiedActionTests
    fixture=VerifiedActionTests(methodName="test_application_existing_window_no_duplicate_launch")
    fixture.setUp()
    agents=AgentCoordinator(fixture.kernel)
    service=attach(fixture.kernel,agents,tmp_path)
    try:
        for i in range(10000):service.publish(AmbientEvent("background.low","owned-fixture","local",trust=Trust.LOCAL_OS,dedupe_key=str(i)))
        fixture.windows.list_windows.return_value=[fixture.window()]
        start=time.monotonic()
        with patch("morice.action_runtime.desktop.os.name","posix"):
            result=fixture.run_task("application.open",{"target":"calculator"})
        assert result.success and result.verification.status.value=="verified"
        assert time.monotonic()-start<2
        assert agents._drivers is None and not service._inflight
        assert len(service._queue)==256
        fixture.desktop.applications.launch.assert_not_called()
    finally:service.close();agents.shutdown();fixture.tearDown()
