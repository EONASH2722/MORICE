"""Initialize real services and the main window with isolated local settings."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["MORICE_PRELOAD"] = "0"
os.environ["MORICE_DISABLE_SESSION"] = "1"
os.environ["MORICE_DISABLE_RECOVERY"] = "1"
os.environ["MORICE_REDUCE_MOTION"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from morice import settings
from morice.pyside_app import MoriceWindow
from morice.runtime_services import RuntimeServices

with tempfile.TemporaryDirectory(prefix="morice-actions-startup-") as directory:
    root = Path(directory)
    with patch("morice.settings._settings_dir", return_value=str(root / "settings")):
        settings.save_settings({**settings.DEFAULT_SETTINGS, "tts_enabled": "false", "stt_enabled": "false", "desktop_pet_enabled": "false"})
        app = QApplication([]); started = time.perf_counter()
        runtime = RuntimeServices(root / "runtime", project_root=root)
        constructor_ms = (time.perf_counter()-started)*1000
        recovery = runtime.start()
        window = MoriceWindow(runtime, recovery); window.show(); app.processEvents()
        result = {"constructor_ms": constructor_ms, "ui_initialized": True,
            "critical_failures": len(runtime.health_report.critical_failures),
            "capabilities": len(runtime.kernel.registry.search()), "roles": len(runtime.agents.roles.all()),
            "same_kernel": runtime.agents.kernel is runtime.kernel and runtime.actions.kernel is runtime.kernel,
            "browser_attached": runtime.pc_browser.bridge is window._action_browser_bridge,
            "agent_pool_lazy": runtime.agents._drivers is None,
            "wall_ms": (time.perf_counter()-started)*1000}
        window.close(); app.processEvents(); runtime.shutdown()
        result["leases_after"] = len(runtime.kernel.resources.snapshot())
        Path("build/phase3-startup.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        assert result["critical_failures"] == 0 and result["same_kernel"] and result["browser_attached"]
