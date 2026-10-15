"""Actual isolated app + Phase 7 panels, with no account/network initialization."""
import json,os,statistics,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
os.environ.update(QT_QPA_PLATFORM="offscreen",MORICE_PRELOAD="0",MORICE_DISABLE_SESSION="1",MORICE_DISABLE_RECOVERY="1",MORICE_REDUCE_MOTION="1",MORICE_NODE_NETWORK="0")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from morice import settings
from morice.runtime_services import RuntimeServices
from morice.pyside_app import MoriceWindow
from morice.ambient.ui import AmbientDialog

with tempfile.TemporaryDirectory(prefix="morice-ambient-startup-") as directory:
    root=Path(directory)
    with patch("morice.settings._settings_dir",return_value=str(root/"settings")):
        settings.save_settings({**settings.DEFAULT_SETTINGS,"tts_enabled":"false","stt_enabled":"false","desktop_pet_enabled":"false"})
        app=QApplication([]);start=time.perf_counter();services=RuntimeServices(root/"runtime",project_root=root)
        result={"constructor_ms":(time.perf_counter()-start)*1000,"ambient_lazy":services._ambient_service is None}
        recovery=services.start();window=MoriceWindow(services,recovery);window.show();app.processEvents()
        result.update(startup_ms=(time.perf_counter()-start)*1000,critical_failures=len(services.health_report.critical_failures),
            research_lazy=services._research_runtime is None,mesh_lazy=services._device_mesh is None,
            builder_lazy=services.autonomous_builder._project_runtime is None,agent_drivers_lazy=services.agents._drivers is None,
            roles=len(services.agents.roles.all()))
        start=time.perf_counter();dialog=AmbientDialog(services,window);dialog.show();app.processEvents()
        result.update(panel_initialization_ms=(time.perf_counter()-start)*1000,
            shared_kernel=services.ambient.kernel is services.kernel and services.ambient.agents is services.agents,
            security_uses_existing_actions=services.ambient.security.actions is services.actions,
            monitoring_off=not services.ambient.enabled and not services.ambient.security.enabled,
            connectors_empty=not services.ambient.connectors.providers,
            panel_bypasses_agent_pool=services.agents._drivers is None,ambient_status=services.ambient.health,
            security_status=services.ambient.security.snapshot()["status"])
        samples=[]
        for _ in range(100):
            start=time.perf_counter();assert services.kernel.dispatch("kernel.echo",{"text":"local"}).success;samples.append((time.perf_counter()-start)*1000)
        result["direct_echo_median_ms"]=statistics.median(samples)
        samples=[]
        for _ in range(20):
            start=time.perf_counter();assert services.kernel.dispatch("python.calculate",{"expression":"2+3"}).success;samples.append((time.perf_counter()-start)*1000)
        result["direct_calculation_median_ms"]=statistics.median(samples)
        dialog.close();window.close();app.processEvents();services.shutdown()
        result["leases_after"]=len(services.kernel.resources.snapshot())
        result["timing_thread_stopped"]=services.ambient._thread is None
        assert all(result[k] for k in ("ambient_lazy","research_lazy","mesh_lazy","builder_lazy","agent_drivers_lazy","shared_kernel","security_uses_existing_actions","monitoring_off","connectors_empty","panel_bypasses_agent_pool","timing_thread_stopped"))
        assert result["critical_failures"]==result["leases_after"]==0
        Path("build/phase7-startup.json").write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
