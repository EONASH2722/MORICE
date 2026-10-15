"""Real isolated service/window/Devices startup with networking disabled by default."""
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ.update(QT_QPA_PLATFORM="offscreen", MORICE_PRELOAD="0", MORICE_DISABLE_SESSION="1",
                  MORICE_DISABLE_RECOVERY="1", MORICE_REDUCE_MOTION="1", MORICE_NODE_NETWORK="0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from morice import settings
from morice.pyside_app import MoriceWindow
from morice.runtime_services import RuntimeServices
from morice.device_mesh.ui import DevicesDialog

with tempfile.TemporaryDirectory(prefix="morice-mesh-startup-") as directory:
    root = Path(directory)
    with patch("morice.settings._settings_dir", return_value=str(root / "settings")):
        settings.save_settings({**settings.DEFAULT_SETTINGS, "tts_enabled": "false", "stt_enabled": "false", "desktop_pet_enabled": "false"})
        app = QApplication([]); started = time.perf_counter()
        runtime = RuntimeServices(root / "runtime", project_root=root)
        constructor_ms = (time.perf_counter() - started) * 1000
        recovery = runtime.start(); window = MoriceWindow(runtime, recovery); window.show(); app.processEvents()
        result = {"constructor_ms": constructor_ms, "wall_ms": (time.perf_counter() - started) * 1000,
            "critical_failures": len(runtime.health_report.critical_failures),
            "capabilities": len(runtime.kernel.registry.search()), "roles": len(runtime.agents.roles.all()),
            "same_kernel": runtime.agents.kernel is runtime.kernel and runtime.actions.kernel is runtime.kernel,
            "mesh_lazy_at_start": runtime._device_mesh is None, "agent_pool_lazy": runtime.agents._drivers is None,
            "builder_lazy": runtime.autonomous_builder._project_runtime is None}
        samples = []
        for _ in range(250):
            begin = time.perf_counter(); value = runtime.kernel.dispatch("kernel.echo", {"text": "local"})
            assert value.success; samples.append((time.perf_counter() - begin) * 1000)
        result["direct_echo_median_ms"] = statistics.median(samples)
        dialog = DevicesDialog(runtime, window); dialog.show(); app.processEvents()
        result.update(devices_ui_initialized=True, no_peers=len(dialog.rows) == 0,
                      mesh_disabled_in_devices=not runtime.device_mesh.enabled,
                      listeners_when_disabled=len(runtime.device_mesh.transport._listeners))
        assert not dialog.action_buttons["Send file"].isVisible()
        assert dialog.status.textFormat() == Qt.PlainText
        dialog.close(); window.close(); app.processEvents(); runtime.shutdown()
        result["leases_after"] = len(runtime.kernel.resources.snapshot())
        result["sockets_after"] = len(runtime.device_mesh.transport._connections)
        assert result["critical_failures"] == 0 and result["same_kernel"] and result["mesh_lazy_at_start"]
        assert result["listeners_when_disabled"] == result["leases_after"] == result["sockets_after"] == 0
        Path("build/phase5-startup.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
