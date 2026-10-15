"""Owned Qt lifecycle/load soak. No hardware/provider or compositor claims."""
from __future__ import annotations

import argparse
from collections import deque
from contextlib import ExitStack
import gc
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def summary(values):
    ordered = sorted(values)
    return {'samples': len(ordered), 'median_ms': statistics.median(ordered) if ordered else None,
            'p95_ms': ordered[int((len(ordered)-1)*.95)] if ordered else None,
            'worst_ms': max(ordered, default=None)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=300)
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--output', default='build/phase10-soak-current')
    args = parser.parse_args()
    if not 60 <= args.seconds <= 3600:
        parser.error('Use a bounded 60–3600 second soak.')
    output = (ROOT/args.output).resolve();output.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    for path in sorted((ROOT/'morice').rglob('*.py')):
        digest.update(str(path.relative_to(ROOT)).encode());digest.update(path.read_bytes())
    with tempfile.TemporaryDirectory(prefix='morice-ui-soak-') as directory, ExitStack() as cleanup:
        root = Path(directory)
        os.environ.update(APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local'),
            MORICE_LOCAL_DATA_DIR=str(root/'data'),MORICE_RUNTIME_DIR=str(root/'runtime'),
            MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',
            MORICE_NODE_NETWORK='0',MORICE_REDUCE_MOTION='0',MORICE_START_AWAKE='1',
            QT_QPA_PLATFORM='windows' if args.native else 'offscreen')
        import psutil
        from PySide6.QtCore import QTimer,Qt,QCoreApplication,QEvent
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication,QWidget
        from morice import settings
        import morice.runtime_services as runtime_module
        from morice.runtime_services import RuntimeServices
        from morice.kernel import CapabilityDescriptor,ExecutionResult,TaskStatus,TaskGraph,TaskNode
        from morice.agent_runtime import AgentRole
        from morice.unified_intelligence import PermissionState
        from morice.pyside_app import create_application_window
        from geographiclib.geodesic import Geodesic

        settings.save_settings({**settings.DEFAULT_SETTINGS,'pet_enabled':'false',
            'tts_enabled':'false','stt_enabled':'false','model_path':''})
        app=QApplication([]);process=psutil.Process()
        runtime=RuntimeServices(root/'runtime',project_root=ROOT);runtime_module._RUNTIME_SERVICES=runtime
        cleanup.callback(runtime.shutdown)
        cleanup.callback(app.processEvents)
        window=create_application_window(runtime,runtime.start());window.resize(1366,840);window.show()
        cleanup.callback(window.close)
        window.activateWindow();app.processEvents()
        runtime.kernel.permissions.controller.set_state('microphone_access',PermissionState.DENIED)
        window.wake_controller.update_preferences(enabled=True)
        # Meaningful, cancellable CPU work goes through the existing coordinator.
        # This fixture does not claim to create physical GPU or VRAM pressure.
        def calculate(inputs,context):
            total=0.
            for i in range(3000):
                if i % 32 == 0:context.cancellation_token.raise_if_cancelled()
                total += Geodesic.WGS84.Inverse(13.08784,80.27847,inputs['latitude']+i/100000,-74.00597)['s12']
            return ExecutionResult(TaskStatus.SUCCEEDED,True,{'distance_sum':total})
        runtime.kernel.registry.register(CapabilityDescriptor('phase10.soak','Owned cancellable geodesic load',supports_cancellation=True),calculate)
        runtime.agents.roles.register(AgentRole('phase10_soak','Owned validation','Actual deterministic CPU load',('phase10.soak',),result_schema={}))
        intervals=deque(maxlen=20000);stamp=[time.monotonic()]
        timer=QTimer();timer.setInterval(20)
        def pulse():
            now=time.monotonic();intervals.append((now-stamp[0])*1000);stamp[0]=now
        timer.timeout.connect(pulse);timer.start()
        routes=('home','spatial','media','home','research','settings','activity','projects','devices','tools','voice','artifacts','history','plugins','automations','connectors','security')
        presets=('MORICE','ARCTIC','SOLAR','CRIMSON','AMETHYST','MONOCHROME')
        samples=[];futures=[];cycles=0;wake_cycles=0;child_cycles=0;cancelled=0
        started=time.monotonic();next_cycle=started;next_sample=started;end=started+args.seconds
        try:
            while time.monotonic()<end:
                now=time.monotonic()
                if now>=next_cycle:
                    route=routes[cycles%len(routes)];window.navigate(route)
                    if route=='spatial':
                        runtime.spatial.set_pair('Chennai','New York');window.routes[route].set_context(runtime.spatial.snapshot())
                    if route=='settings':window.theme_engine.update(preset=presets[(cycles//len(routes))%len(presets)],persist=False)
                    if cycles%17==0:
                        graph=TaskGraph(tuple(TaskNode('phase10.soak',{'latitude':latitude},constraints={'role':'phase10_soak'}) for latitude in (40.,41.)))
                        future=runtime.agents.submit(graph);futures.append((graph,future))
                    if cycles%17==8:
                        window.wake_controller.activate('owned lifecycle test · microphone denied');window.wake_controller.cancel();wake_cycles+=1
                    if cycles%34==16:
                        window._open_new_window();child=window._child_windows[-1];child.close()
                        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents();child_cycles+=1
                    cycles+=1;next_cycle=now+1.5
                if now>=next_sample:
                    gc.collect();app.processEvents()
                    sample={'seconds':round(now-started,2),'rss_mb':process.memory_info().rss/2**20,
                        'threads':process.num_threads(),'handles':process.num_handles(),
                        'qt_widgets':len(app.allWidgets()),'effects':window.effect_clock.diagnostics(),
                        'bridge':window.ui_bridge.diagnostics(),'selected_quality':window.effect_policy.budget.selected,
                        'effective_quality':window.effect_policy.budget.effective,'policy_sources':dict(window.effect_policy._loads)}
                    samples.append(sample);next_sample=now+10
                    print(json.dumps({'sample':sample['seconds'],'rss_mb':round(sample['rss_mb'],2),'widgets':sample['qt_widgets'],'cycles':cycles}),flush=True)
                QTest.qWait(20)
            for graph,future in futures:
                if not future.done():runtime.agents.cancel(graph.graph_id);cancelled+=1
            deadline=time.monotonic()+15
            while not all(f.done() for _,f in futures) and time.monotonic()<deadline:QTest.qWait(20)
            assert all(f.done() for _,f in futures),'Owned graph did not settle.'
            results=[future.result() for _,future in futures if not future.cancelled()]
            window.navigate('home');window.theme_engine.update(reduced_motion=True,persist=False)
            QTest.qWait(250);window.effect_clock.timer.stop()
            window.showMinimized();QTest.qWait(150)
            assert not window.effect_clock.timer.isActive()
            window.showNormal();app.processEvents();assert window.grab().save(str(output/'final-core.png'))
            timer.stop();window.close();app.processEvents();runtime.shutdown()
            record={'status':'OWNED_QT_SOAK_PASSED','source_sha256':digest.hexdigest(),
                'seconds':time.monotonic()-started,'cycles':cycles,'wake_lifecycle_cycles':wake_cycles,
                'child_window_cycles':child_cycles,'actual_workflows':len(futures),'cancel_requests':cancelled,
                'workflow_statuses':[result.status for result in results],'samples':samples,
                'ui_schedule':summary(intervals),'shutdown':runtime.shutdown_report,
                'leases_after':len(runtime.kernel.resources.snapshot()),
                'effects_after':window.effect_clock.diagnostics(),
                'scope':'Owned Qt process/timer scheduling and deterministic CPU load; real coordinator, no models or physical audio. Paint/compositor latency and physical GPU load are not measured. Wake lifecycle uses denied microphone; real PCM wake demo is separate.'}
            assert record['shutdown']['clean'] and record['leases_after']==0
            assert record['effects_after']['subscribers']==0
            assert record['effects_after']['closed'] and not record['effects_after']['timer_active']
            (output/'evidence.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
            print(json.dumps({key:record[key] for key in ('status','seconds','cycles','ui_schedule','shutdown','leases_after')}),flush=True)
        finally:
            timer.stop();window.close();app.processEvents();runtime.shutdown()


if __name__=='__main__':main()
