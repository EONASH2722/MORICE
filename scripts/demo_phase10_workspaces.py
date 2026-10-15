"""Actual owned local Builder/Research/TLS Mesh/image workflow in staged Qt.

Generated projects, test-node credentials and settings stay in a unique build
evidence directory. Media metadata uses a separate owned validation data folder,
honoring the existing prohibition on source-tree media storage.
"""
from __future__ import annotations

import hashlib
import faulthandler
import json
import os
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
faulthandler.enable()
if '--trace-timeout' in sys.argv: faulthandler.dump_traceback_later(45, repeat=True)
os.environ.update(QT_QPA_PLATFORM='windows' if '--native' in sys.argv else 'offscreen',
    MORICE_PRELOAD='0', MORICE_DISABLE_SESSION='1', MORICE_DISABLE_RECOVERY='1',
    MORICE_START_AWAKE='1', MORICE_NODE_NETWORK='0', MORICE_REDUCE_MOTION='1')

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from morice import settings
from morice.runtime_services import RuntimeServices
from morice.kernel import CapabilityKernel
from morice.device_mesh import DeviceMesh
from morice.project_build.planning import scaffold
from morice.project_build.contracts import Requirement
from morice.pyside_app import create_application_window


resume_path = Path(sys.argv[sys.argv.index('--resume')+1]).resolve() if '--resume' in sys.argv else None
output = resume_path or ROOT / 'build/phase10-master-workspace' / uuid.uuid4().hex[:10]
if resume_path:
    assert output.is_relative_to((ROOT/'build/phase10-master-workspace').resolve()) and (output/'runtime').is_dir()
else: output.mkdir(parents=True)
app = QApplication.instance() or QApplication([]); evidence = {'scope': 'Actual controlled local fixtures in the staged native UI; no public/external/cloud actions.', 'output': str(output)}
last_tick = [time.perf_counter()]; intervals = []; pulses = QTimer(); pulses.setInterval(20)
def tick():
    now = time.perf_counter(); intervals.append((now-last_tick[0])*1000); last_tick[0] = now
pulses.timeout.connect(tick)


def until(predicate, description, seconds=30):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate(): return
        QTest.qWait(15)
    raise AssertionError('Timed out: '+description)


def capture(window, label):
    app.processEvents(); path = output/(label+'.png'); assert window.grab().save(str(path))
    evidence.setdefault('screenshots', {})[label] = str(path)


def click(view, text):
    button = next(button for button in view.findChildren(QPushButton) if button.text() == text)
    until(lambda:button.isVisible() and button.isEnabled(),'ready button: '+text)
    QTest.mouseClick(button, Qt.LeftButton)


media_data = Path(r'E:\MORICE_DATA\phase10-validation') / output.name
media_data.mkdir(parents=True, exist_ok=True)
assert not media_data.resolve().is_relative_to(ROOT)
os.environ['MORICE_LOCAL_DATA_DIR'] = str(media_data)
evidence['media_data_root'] = str(media_data)
os.environ.update(APPDATA=str(output/'roaming'), LOCALAPPDATA=str(output/'local'))
peer_kernel = CapabilityKernel(); peer = DeviceMesh(peer_kernel, output/'test-node', name='Owned localhost validation node')
with patch('morice.settings._settings_dir', return_value=str(output/'settings')):
    settings.save_settings({**settings.DEFAULT_SETTINGS, 'tts_enabled':'false', 'stt_enabled':'false', 'pet_enabled':'false'})
    runtime = RuntimeServices(output/'runtime', project_root=ROOT)
    with patch('morice.runtime_services._RUNTIME_SERVICES', runtime):
        construction_started = time.perf_counter()
        window = create_application_window(runtime, runtime.start()); window.show(); app.processEvents()
        evidence['owned_window_construct_and_first_events_ms'] = (time.perf_counter()-construction_started)*1000
        last_tick[0] = time.perf_counter(); pulses.start()
        try:
            # Real safe numeric result and persistent provenance, using the
            # same Research Kernel that backs the displayed workspace.
            window.navigate('research'); research = window.routes['research']
            prior = [row for row in research.manager.list() if row['title'] == 'Owned 10,000-run benign mixture sweep'
                and row['status'] == 'COMPLETED'] if resume_path else []
            if prior:
                research.project_id = prior[0]['project_id']; research._pending_select_id = prior[0]['id']
                research.projects.setCurrentIndex(research.projects.findData(research.project_id)); research.refresh()
                until(lambda: research.selected_id() == prior[0]['id'], 'reopen actual completed experiment selection')
            else:
                research.objective.setText('Compare benign ideal volume-additive densities')
                QTest.mouseClick(research.create_button, Qt.LeftButton)
                until(lambda: bool(research.project_id), 'Research project creation')
            calculated = {}
            project_id = research.project_id
            window.ui_bridge.submit('demo-recorded-calculation', lambda: runtime.research.run_recorded(project_id, 'research.calculate',
                {'expression':'0.5*m*v**2', 'inputs':{'m':{'value':2,'unit':'kg'}, 'v':{'value':3,'unit':'m/s'}}, 'output_unit':'J'}),
                lambda envelope: calculated.update(envelope))
            until(lambda: bool(calculated), 'verified scientific calculation on existing worker')
            assert calculated['ok'], calculated
            result = calculated['value']
            assert result['execution'].success and result['execution'].output['result']['value'] == 9
            evidence['calculation'] = {'value':result['execution'].output['result'], 'record_id':result['record_id'], 'verification':result['execution'].verification.status.value}
            specification = {'title':'Owned 10,000-run benign mixture sweep', 'objective':'Compare ideal mixture density over the complete bounded grid',
                'simulation_engine':'ideal_mixture_density', 'parameters':{'density_a':{'value':1000,'unit':'kg/m^3'},
                    'density_b':{'value':2000,'unit':'kg/m^3'}, 'fraction_a':{'value':.5,'unit':''}},
                'experiment_type':'PARAMETER_SWEEP', 'time_limit_seconds':300,
                'parameter_ranges':{'fraction_a':{'min':0,'max':1,'unit':'','points':10000}}}
            if prior:
                experiment = prior[0]['id']
                for index in range(research.experiments.rowCount()):
                    if research.experiments.item(index,0).data(Qt.UserRole) == experiment: research.experiments.selectRow(index); break
                research.tabs.setCurrentIndex(0)
            else:
                research.tabs.setCurrentIndex(4); research.specification.setPlainText(json.dumps(specification))
                QTest.mouseClick(research.prepare_button, Qt.LeftButton)
                until(lambda: not research._bridge_preparing and bool(research.selected_id()), 'reviewed specification preparation')
                experiment = research.selected_id()
            assert research.manager.get(experiment)['estimate']['planned_runs'] == 10000
            started = time.perf_counter()
            if not prior: click(research, 'Run / Resume')
            samples = []; resumed = []; deliberate_pause = bool(prior)
            deadline = time.monotonic()+600
            while time.monotonic() < deadline:
                app.processEvents(); row = research.manager.get(experiment); samples.append(row['completed_runs'])
                if not deliberate_pause and row['completed_runs'] >= 100 and row['status'] == 'RUNNING':
                    deliberate_pause = True; click(research, 'Pause')
                if row['status'] == 'PAUSED' and len(resumed) < 3:
                    resumed.append({'completed_runs':row['completed_runs'], 'error':row['error'], 'at_seconds':time.perf_counter()-started})
                    print(json.dumps({'explicit_ui_resume':resumed[-1]}), flush=True)
                    click(research, 'Run / Resume')
                    until(lambda:research.manager.get(experiment)['status'] != 'PAUSED','actual resume admission')
                    continue
                if row['status'] not in {'QUEUED','RUNNING'}: break
                if any(0 < value < 10000 for value in samples) and 'research-active' not in evidence.get('screenshots', {}):
                    capture(window, 'research-active'); window.navigate('spatial'); app.processEvents(); window.navigate('research')
                QTest.qWait(25)
            assert row['status'] in {'COMPLETED', 'COMPLETED_WITH_WARNINGS'} and row['completed_runs'] == 10000, row
            research.tick(); research.select()
            try:
                # Metadata polls may overlap without making already delivered
                # results stale. Require the actual terminal revision instead
                # of waiting for a fleeting global polling-idle state.
                until(lambda: not research._result_reading and research.runs.rowCount() == 500
                    and research._result_key[:4] == (experiment,row['updated'],10000,row['status']),
                    'actual terminal experiment results delivered')
            except AssertionError:
                print(json.dumps({'result_readiness_failure':{'metadata_pending':research._meta_reading,'results_pending':research._result_reading,
                    'rows_shown':research.runs.rowCount(),'selected_id':research.selected_id(),'result_key':research._result_key,
                    'bridge':window.ui_bridge.diagnostics(),'detail':research.detail.toPlainText()[:300]}}),flush=True)
                faulthandler.dump_traceback()
                raise
            capture(window, 'research-completed')
            evidence['sweep'] = {'id':experiment, 'status':row['status'], 'completed_runs':row['completed_runs'],
                'planned_runs':row['estimate']['planned_runs'], 'seconds':time.perf_counter()-started,
                'explicit_ui_resumes':resumed,
                'reopened_actual_completed_checkpoint':bool(prior),
                'partial_progress_observed':any(0 < value < 10000 for value in samples), 'summary':row['summary'],
                'result_rows_shown':research.runs.rowCount(), 'model_calls':0, 'scope':'Actual deterministic ideal-mixture computations, no experimental observation claim.'}
            print(json.dumps({'sweep':{key:value for key,value in evidence['sweep'].items() if key not in {'summary'}}}), flush=True)
            (output/'partial-evidence.json').write_text(json.dumps(evidence, indent=2, default=str))

            # Run the same existing Builder entry used by the Projects UI.
            project = output/'addition-calculator'; builder = runtime.autonomous_builder.project_runtime
            session = builder.create(project, 'Build a Python addition calculator', scaffold('Build a Python addition calculator', project),
                requirements=[Requirement('2 + 3 produces 5', check={'kind':'command_output','contains':'5'})],
                runtime={'kind':'command','command':[sys.executable,'main.py','2','3']})
            window.project_folder = str(project); window.project_folder_input.setText(str(project)); window._set_chat_mode('project')
            window._set_project_access('full'); window.navigate('projects'); window._start_project_build(session)
            until(lambda: window._last_project_build_id == session.session_id and not window._project_build_id, 'actual Builder build/tests', 60)
            assert session.success, session.result_card()
            assert (project/'main.py').is_file(); capture(window, 'project-verified')
            evidence['builder'] = {'result_card':session.result_card(), 'command_evidence':session.command_evidence,
                'main_sha256':hashlib.sha256((project/'main.py').read_bytes()).hexdigest(), 'scope':'Actual controlled owned local Python project, filesystem and process verification.'}
            print(json.dumps({'builder_status':session.status}), flush=True)
            (output/'partial-evidence.json').write_text(json.dumps(evidence, indent=2, default=str))

            # The second Kernel belongs solely to a real localhost TLS peer,
            # following the existing DeviceMesh protocol, not a UI authority.
            peer.enable(heartbeat=False); mesh = runtime.device_mesh; mesh.enable(heartbeat=False)
            challenge = peer.transport.enable_pairing()
            pending = mesh.begin_pair('127.0.0.1', challenge['pair_port'], challenge['code'], challenge['fingerprint'], user_confirmed=True)
            peer.approve_pair(pending['pair_id'], ('device.status','file.receive'), user_confirmed=True)
            node = mesh.finish_pair(pending, outbound_permissions=('device.status','file.receive'), inbound_permissions=('device.status',), user_confirmed=True).descriptor.device_id
            window.navigate('devices'); devices = window.routes['devices']; devices.refresh()
            index = next(i for i,row in enumerate(devices.rows) if row['node_id'] == node); devices.nodes.setCurrentRow(index)
            devices.tabs.setCurrentIndex(1); app.processEvents()
            assert devices.action_buttons['Send file'].isVisible()
            payload = output/'owned-test-transfer.bin'; payload.write_bytes(bytes(range(256))*4097)
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            with patch('morice.device_mesh.ui.QFileDialog.getOpenFileName', return_value=(str(payload), '')):
                devices.send_file()
                until(lambda: not devices._busy, 'verified localhost Mesh file transfer', 30)
            received = peer.node.inbox.root/payload.name
            assert received.is_file() and hashlib.sha256(received.read_bytes()).hexdigest() == digest
            capture(window, 'devices-transfer-verified'); evidence['mesh'] = {'node_id':node, 'bytes':payload.stat().st_size,
                'sha256':digest, 'received_path':str(received), 'status':devices.status.text(), 'scope':'Actual mutually authenticated TLS between two owned localhost test nodes; no physical phone/remote person.'}
            print(json.dumps({'mesh_bytes_verified':payload.stat().st_size}), flush=True)

            window.navigate('media'); assert window.active_route == 'media', window.status_line.text()
            media = window.routes['media']
            actual_image = Path(r'E:\MORICE_DATA\media\outputs\57285e6e591a41249245aee8bfb2d4f6\media_57285e6e591a41249245aee8bfb2d4f6_0.png')
            media.load_reference(actual_image); until(lambda: media.reference_metadata is not None, 'actual verified Phase 9 image decode')
            assert media.reference_metadata['sha256'] == '3852a5b4389960676c7e397248b02295cbce8e3567ca180783ef9cb46416b7b0'
            capture(window, 'actual-phase9-image'); evidence['media_loaded'] = media.reference_metadata
            evidence['media_constraint'] = 'Existing accepted Phase 9 RAM margin is preserved. No new heavy model generation, physical GPU contention, video or cloud validation is claimed by this UI fixture.'
            window.navigate('activity'); capture(window, 'activity-real-tasks')
            evidence['activity'] = {'tasks':window.routes['activity'].model.rowCount(), 'public_events':window.routes['activity'].events.count()}
            assert evidence['activity']['tasks'] > 0
            window.theme_engine.update(preset='ICE'); capture(window, 'ice-theme')
            window.theme_engine.update(preset='MORICE', reduced_motion=True); window.navigate('spatial')
            runtime.spatial.set_pair('Chennai','New York'); window.routes['spatial'].set_context(runtime.spatial.snapshot()); capture(window, 'spatial-surface')
            pulses.stop(); ordered = sorted(intervals)
            evidence['ui_timer_intervals'] = {'samples':len(ordered), 'median_ms':statistics.median(ordered),
                'p95_ms':ordered[int((len(ordered)-1)*.95)], 'worst_ms':max(ordered),
                'scope':'Owned Qt 20 ms responsiveness timer, including fixture DB sampling and PNG grabs. This is not compositor frame latency.'}
            window.close(); app.processEvents(); peer.close(); peer_kernel.shutdown(); runtime.shutdown()
            evidence['shutdown'] = runtime.shutdown_report; assert evidence['shutdown']['clean']
            evidence['status'] = 'CONTROLLED_WORKSPACE_DEMO_PASSED'
            (output/'evidence.json').write_text(json.dumps(evidence, indent=2, default=str), encoding='utf-8')
            (ROOT/'build/phase10-master-workspace-latest.json').write_text(json.dumps({'output':str(output), 'evidence':str(output/'evidence.json')}, indent=2))
            print(json.dumps({'status':evidence['status'], 'output':str(output), 'ui_timer':evidence['ui_timer_intervals'], 'shutdown':evidence['shutdown']}), flush=True)
        except BaseException as exc:
            evidence['status']='CONTROLLED_WORKSPACE_DEMO_FAILED';evidence['error']={'type':type(exc).__name__,'message':str(exc)}
            (output/'failure-evidence.json').write_text(json.dumps(evidence,indent=2,default=str),encoding='utf-8')
            print(json.dumps({'status':evidence['status'],'error':evidence['error'],'output':str(output)}),flush=True)
            raise
        finally:
            pulses.stop(); window.close(); app.processEvents(); peer.close(); peer_kernel.shutdown(); runtime.shutdown()
