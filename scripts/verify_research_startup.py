"""Actual isolated main window and research panel startup, with cold services lazy."""
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
os.environ.update(QT_QPA_PLATFORM='offscreen',MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_REDUCE_MOTION='1',MORICE_NODE_NETWORK='0')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from morice import settings
from morice.runtime_services import RuntimeServices
from morice.pyside_app import MoriceWindow
from morice.research.ui import ResearchDialog

with tempfile.TemporaryDirectory(prefix='morice-research-startup-') as directory:
    root=Path(directory)
    with patch('morice.settings._settings_dir',return_value=str(root/'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false','desktop_pet_enabled':'false'})
        app=QApplication([]);started=time.perf_counter();services=RuntimeServices(root/'runtime',project_root=root)
        constructor_ms=(time.perf_counter()-started)*1000
        recovery=services.start();window=MoriceWindow(services,recovery);window.show();app.processEvents()
        result={'constructor_ms':constructor_ms,'wall_ms':(time.perf_counter()-started)*1000,
                'critical_failures':len(services.health_report.critical_failures),'research_lazy':services._research_runtime is None,
                'mesh_lazy':services._device_mesh is None,'builder_lazy':services.autonomous_builder._project_runtime is None,
                'agent_drivers_lazy':services.agents._drivers is None,'roles':len(services.agents.roles.all())}
        samples=[]
        for _ in range(250):
            start=time.perf_counter();assert services.kernel.dispatch('kernel.echo',{'text':'local'}).success;samples.append((time.perf_counter()-start)*1000)
        result['direct_echo_median_ms']=statistics.median(samples)
        start=time.perf_counter();research=services.research;result['research_initialization_ms']=(time.perf_counter()-start)*1000
        result['shared_kernel']=research.kernel is services.kernel and research.agents is services.agents and research.actions is services.actions
        project=research.create('Controlled startup kinetic energy calculation')
        start=time.perf_counter();value=research.run_recorded(project,'research.calculate',{'expression':'0.5*m*v**2','inputs':{'m':{'value':2,'unit':'kg'},'v':{'value':3,'unit':'m/s'}},'output_unit':'J'})
        result['first_verified_calculation_ms']=(time.perf_counter()-start)*1000
        assert value['execution'].success and value['execution'].output['result']['value']==9
        result['calculation_bypasses_agent_pool']=services.agents._drivers is None
        dialog=ResearchDialog(research,project,window);dialog.show();app.processEvents()
        result['research_ui_initialized']=dialog.projects.currentData()==project
        result['panel_bypasses_agent_pool']=services.agents._drivers is None
        assert services.autonomous_builder._project_runtime is None and services._device_mesh is None
        dialog.close();window.close();app.processEvents();services.shutdown()
        result['leases_after']=len(services.kernel.resources.snapshot());result['lab_dispatch_stopped']=not research.laboratory.worker.is_alive()
        assert all(result[k] for k in ['research_lazy','mesh_lazy','builder_lazy','agent_drivers_lazy','shared_kernel','calculation_bypasses_agent_pool','panel_bypasses_agent_pool','research_ui_initialized','lab_dispatch_stopped'])
        assert result['critical_failures']==result['leases_after']==0
        Path('build/phase6-startup.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
