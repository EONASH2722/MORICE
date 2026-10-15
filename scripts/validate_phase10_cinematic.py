"""Owned native Qt cinematic probe. Fixtures are labelled; no physical GPU claim."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.update(QT_QPA_PLATFORM='windows',MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_NODE_NETWORK='0',MORICE_REDUCE_MOTION='0',MORICE_START_AWAKE='1')

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLabel
import psutil
from morice import settings
import morice.runtime_services as runtime_module
from morice.runtime_services import RuntimeServices
from morice.kernel import CapabilityDescriptor,ExecutionResult,TaskStatus,TaskGraph,TaskNode
from morice.agent_runtime import AgentRole
from morice.pyside_app import create_application_window
from morice.ui_next.core_state import CoreState,CoreSnapshot,LABELS


def stats(values):
    values=sorted(values)
    return {'samples':len(values),'median_ms':statistics.median(values) if values else 0,'p95_ms':values[int((len(values)-1)*.95)] if values else 0,'worst_ms':max(values,default=0)}


def pump(app,predicate,timeout=12):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        app.processEvents()
        if predicate():return
        QTest.qWait(10)
    assert predicate(),'Owned Qt operation did not finish.'


out=Path(sys.argv[sys.argv.index('--output')+1]).resolve() if '--output' in sys.argv else ROOT/'build/phase10-cinematic';out.mkdir(parents=True,exist_ok=True)
app=QApplication.instance() or QApplication([]);process=psutil.Process()
evidence={'status':'STAGED_CINEMATIC_PROBE','scope':'Owned native Qt, controlled Qt pointer delivery, actual existing Kernel/AgentCoordinator. State gallery is explicitly a development fixture. Paint CPU timings exclude the compositor. No physical microphone/GPU pressure/monitor-removal claim.','quality':{},'state_fixture':{},'actual_states':[]}
with tempfile.TemporaryDirectory(prefix='morice-cinematic-') as directory:
    root=Path(directory);os.environ.update(APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local'),MORICE_LOCAL_DATA_DIR=str(root/'data'))
    with patch('morice.settings._settings_dir',return_value=str(root/'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false','pet_enabled':'false'})
        runtime=RuntimeServices(root/'runtime',project_root=ROOT);runtime_module._RUNTIME_SERVICES=runtime
        window=create_application_window(runtime,runtime.start());window.resize(1366,840);window.show();window.activateWindow();app.processEvents()
        window.theme_engine.update(background_effects=True,reduced_motion=False,quality='BALANCED',persist=False)
        canvas=window.routes['home'].canvas;field=window.material_backdrop;model=window.core_presentation
        banner=QLabel('DEVELOPMENT STATE FIXTURE · visual states below are not live jobs');banner.setAlignment(Qt.AlignCenter);banner.setProperty('role','secondary');window.presentation_root.layout().insertWidget(1,banner)
        for state in CoreState:
            title,detail=LABELS[state];snapshot=CoreSnapshot(state,title,detail,('fixture role A','fixture role B') if state==CoreState.MULTI_AGENT else (),.35 if state in {CoreState.LISTENING,CoreState.SPEAKING} else 0)
            model.snapshot=snapshot;model.changed.emit(snapshot);canvas.update();window.effect_clock.timer.stop();app.processEvents()
            # Freeze fixture polling for capture; real runtime polling follows.
            window.effect_clock.timer.stop();target=out/('fixture-'+state.value.lower()+'.png');assert window.grab().save(str(target));evidence['state_fixture'][state.value]=str(target)
        banner.hide();model.sample();window.effect_clock.request()
        actual=[];model.changed.connect(lambda snap:actual.append(snap.state.value))
        # Same Phase 2 coordinator as the rest of this RuntimeServices.
        runtime.agents.roles.register(AgentRole('cinematic_validation','Owned validation','Controlled presentation fixture',('phase10.validation',),result_schema={}))
        def owned_work(args,ctx):
            ctx.cancellation_token.wait(.45);ctx.cancellation_token.raise_if_cancelled()
            return ExecutionResult(TaskStatus.SUCCEEDED,True,{'value':args['value']})
        runtime.kernel.registry.register(CapabilityDescriptor('phase10.validation','Owned presentation validation',supports_cancellation=True),owned_work)
        graph=TaskGraph(tuple(TaskNode('phase10.validation',{'value':i},constraints={'role':'cinematic_validation'}) for i in range(2)))
        future=runtime.workers.submit('phase10-native-agent-state',lambda:runtime.agents.run(graph))
        pump(app,lambda:model.snapshot.state==CoreState.MULTI_AGENT)
        assert model.snapshot.nodes==('cinematic_validation',);assert window.grab().save(str(out/'actual-multi-agent.png'))
        pump(app,lambda:future.done() and not model.agents and not model.tasks)
        result=future.result();assert result.success and result.metrics['active_peak']==2;evidence['actual_phase2']=result.metrics
        window.input.setText('2+3');window.on_send();pump(app,lambda:not window.is_busy);window.navigate('home')
        # Resolve actual geography through the retained UI access path.
        QTest.mouseClick(window.action_deck.buttons['spatial'],Qt.LeftButton);window.routes['spatial'].command('show Chennai and New York')
        pump(app,lambda:not window.routes['spatial']._busy);evidence['spatial_result']=runtime.spatial.snapshot()['result'];assert evidence['spatial_result']['metres']>13_000_000
        window.navigate('home');window.activateWindow();app.processEvents()
        for quality in ('LOW','BALANCED','HIGH','ULTRA'):
            window.theme_engine.update(quality=quality,reduced_motion=False,persist=False);app.processEvents();canvas.paint_samples.clear();field.paint_samples.clear();field.raster_samples.clear()
            before=process.cpu_times();rss=process.memory_info().rss;end=time.monotonic()+6;started=time.monotonic()
            while time.monotonic()<end:QTest.qWait(25)
            after=process.cpu_times();elapsed=time.monotonic()-started
            evidence['quality'][quality]={'effective':window.effect_policy.budget.effective,'policy_reason':window.effect_policy.budget.reason,'policy_sources':dict(window.effect_policy._loads),'seconds':elapsed,'cpu_one_core_percent':100*((after.user+after.system)-(before.user+before.system))/elapsed,'rss_start_mb':rss/2**20,'rss_end_mb':process.memory_info().rss/2**20,'core_paint_cpu':stats(canvas.paint_samples),'field_paint_cpu':stats(field.paint_samples),'field_raster_cpu':stats(field.raster_samples),'field':field.diagnostics()}
            assert window.grab().save(str(out/('quality-'+quality.lower()+'.png')))
        # Existing native pointer stays intact; deliver an owned Qt input event.
        local=QPointF(window.width()*.7,window.height()*.35);global_point=QPointF(window.mapToGlobal(local.toPoint()))
        app.sendEvent(window,QMouseEvent(QEvent.MouseMove,local,global_point,Qt.NoButton,Qt.NoButton,Qt.NoModifier));QTest.qWait(250)
        assert field._pointer is not None;assert window.grab().save(str(out/'cursor-reactive.png'))
        window.theme_engine.update(reduced_motion=True,persist=False);QTest.qWait(140);assert not window.effect_clock.timer.isActive()
        phase=field._phase;QTest.qWait(180);assert field._phase==phase;assert window.grab().save(str(out/'reduced-motion.png'));evidence['reduced_motion_static']=True
        # Pressure is a labelled policy fixture; no claim of an actual OOM.
        window.effect_policy.set_load('VRAM_PRESSURE',source='owned-policy-fixture');assert window.effect_policy.budget.effective=='LOW' and window.effect_policy.budget.selected=='ULTRA'
        window.effect_policy.set_load('NORMAL',source='owned-policy-fixture');evidence['pressure_fixture_preserves_selection']=True
        window.theme_engine.update(reduced_motion=False,persist=False);window.showMinimized();QTest.qWait(140);assert not window.effect_clock.timer.isActive();evidence['minimized_clock_stops']=True
        window.showNormal();window.activateWindow();app.processEvents();window.navigate('home');window.effect_clock.request();QTest.qWait(150)
        evidence['actual_states']=list(dict.fromkeys(actual));evidence['core']=model.diagnostics();evidence['bridge']=window.ui_bridge.diagnostics();evidence['clock']=window.effect_clock.diagnostics()
        evidence['logo_sha256']=hashlib.sha256((ROOT/'morice/assets/morice-logo-rgb.png').read_bytes()).hexdigest()
        window.close();app.processEvents();runtime.shutdown();evidence['shutdown']=runtime.shutdown_report;assert evidence['shutdown']['clean']
        (out/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        print(json.dumps({'status':evidence['status'],'states':evidence['actual_states'],'quality':{key:{name:value[name] for name in ('effective','cpu_one_core_percent','core_paint_cpu','field_raster_cpu')} for key,value in evidence['quality'].items()},'shutdown':evidence['shutdown']}),flush=True)
