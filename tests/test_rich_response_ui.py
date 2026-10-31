"""Actual Qt chat mounting, chart/table interaction, persistence and disposal."""
import time
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from test_fast_memory_ui import app,window,pump
from test_research_lab import density_spec,wait_experiment
from morice.pyside_app import ChatBubble
from morice.ui_next.rich_response import RichResponseHost
from morice.ui_next.rich_charts import ChartView
from morice.rich_response import Component,ResponsePlan,SourceRef
from morice.ui_next.rich_controls import CalculatorView
from morice.ui_next.rich_mesh import MeshView


def capture_native(window,name):
    directory=os.getenv('MORICE_QA_SCREENSHOTS','')
    if directory:
        target=Path(directory);target.mkdir(parents=True,exist_ok=True)
        assert window.grab().save(str(target/(name+'.png')))


def read_widget(window,app,widget):
    # Direct native navigation must mark the same user-scroll epoch as wheel
    # and scrollbar input, so pending asynchronous restores yield to it.
    window._history_scroll_epoch+=1;window.follow_latest=False
    window._user_scroll_guard_until=time.monotonic()+.75
    window.scroll.ensureWidgetVisible(widget);app.processEvents()


def visible_section(window,app,host,kind):
    state=next(state for state in host.sections.values() if state['component'].kind==kind)
    window.follow_latest=False;state['toggle'].setChecked(True)
    # Native input arrives after pending layout work; direct test property
    # changes must settle geometry before choosing the scroll destination.
    app.processEvents();host.select_section(state['component'].id);window.scroll.ensureWidgetVisible(state['toggle'],20,20);app.processEvents();host.schedule_visibility()
    try:pump(app,lambda:state['view'] is not None)
    except AssertionError:
        raise AssertionError({'kind':kind,'closed':host.closed,'route':window.active_route,'visible':host.isVisible(),
            'error':state['error'],'loading':state['loading'],'placeholder':state['placeholder'].text(),
            'header_y':state['toggle'].mapTo(window.scroll.viewport(),__import__('PySide6.QtCore',fromlist=['QPoint']).QPoint()).y(),
            'viewport_height':window.scroll.viewport().height()})
    return state['view']


def test_nlui_results_mount_native_chart_link_table_and_restore_same_message(window,app):
    window._session_enabled=True;window._render_chat_messages([])
    project=window.runtime.research.create('Owned rich response test',window._chat_id)
    window._research_project_id=project
    lab=window.runtime.research.laboratory
    prepared=lab.prepare(density_spec(parameter_ranges={'fraction_a':{'min':0,'max':1,'unit':'','points':5}}),project_id=project)
    lab.start(prepared['id']);wait_experiment(lab,prepared['id'])
    window.input.setText('Show my latest experiment results');window.on_send()
    pump(app,lambda:not window.is_busy)
    pump(app,lambda:bool(window.findChildren(RichResponseHost)))
    host=window.findChildren(RichResponseHost)[-1]
    view=visible_section(window,app,host,'chart');app.processEvents()
    read_widget(window,app,view.canvas)
    QTest.qWait(140);app.processEvents();window.follow_latest=False
    pump(app,lambda:bool(view.canvas._points))
    point,index,key=view.canvas._points[2]
    QTest.mouseClick(view.canvas,Qt.LeftButton,pos=point.toPoint());app.processEvents()
    pump(app,lambda:view.table is not None and bool(view.table.model.rows) and bool(view.table.table.selectionModel().selectedRows()))
    assert view.table.table.selectionModel().selectedRows()
    selected=view.table.table.selectionModel().selectedRows()[0].row()
    assert view.table.model.rows[selected]['run']==view.canvas.rows[index]['run']
    capture_native(window,'actual-chart-and-linked-table')
    view.table.search.setText('no-such-actual-value')
    pump(app,lambda:view.table.total==0)
    assert view.table.model.rowCount()==0
    assert len(window._message_rows)==2 and [m['role'] for m in window.history]==['user','assistant']
    identifier=window.history[-1]['message_id']
    saved=window.runtime.chat_history.get_response_plans(window._chat_id,[identifier])
    assert saved[identifier]['conversation_id']==window._chat_id
    window.navigate('settings');app.processEvents()
    assert all(state['view'] is None for state in host.sections.values())
    assert not host.jobs
    window.navigate('chats');app.processEvents()
    pump(app,lambda:bool(host.findChildren(ChartView)))
    window._render_chat_messages(window.history)
    pump(app,lambda:any(getattr(row.findChild(ChatBubble),'_response_host',None) is not None for row in window._message_rows))
    assert len(window._message_rows)==2


def test_native_calculator_uses_actual_units_and_persists_exploration_without_changing_source(window,app):
    window._session_enabled=True;window._render_chat_messages([])
    research=window.runtime.research;project=research.create('Owned actual calculation')
    recorded=research.run_recorded(project,'research.calculate',{'expression':'force*distance',
        'inputs':{'force':{'value':3,'unit':'N'},'distance':{'value':2,'unit':'m'}},'output_unit':'J'})
    assert recorded['execution'].success
    source=SourceRef('research_record',project+':'+recorded['record_id'],scope=window._chat_id)
    window._append_direct_reply('Explore the supplied work calculation.','The supplied inputs give six joules.',address=False)
    plan=ResponsePlan(window._chat_id,(Component('calculator',source,'Actual work calculation'),Component('math',source,'Supplied expression'),
        Component('validation',source,'Actual operation receipt')))
    window._present_response_plan(plan)
    host=window.findChildren(RichResponseHost)[-1]
    view=visible_section(window,app,host,'calculator')
    try:pump(app,lambda:view.last_result is not None)
    except AssertionError:
        raise AssertionError({'status':view.status.text(),'note':view.note.text(),'disposed':view._disposed,
            'host_visible':host._visible,'generation':host.generation,'jobs':len(host.jobs),'inputs':{k:f.text() for k,f in view.inputs.items()}})
    assert view.last_result['outputs']['result']==6
    read_widget(window,app,view.inputs['force'])
    view.inputs['force'].setFocus();view.inputs['force'].selectAll();QTest.keyClicks(view.inputs['force'],'5')
    pump(app,lambda:view.last_result is not None and view.last_result['outputs']['result']==10)
    assert view.last_result['units']['result']=='joule'
    saved=window.runtime.chat_history.get_response_plans(window._chat_id,[window.history[-1]['message_id']])
    config=next(c['config'] for c in next(iter(saved.values()))['components'] if c['kind']=='calculator')
    assert config['values']['force']==5
    original=next(r for r in research.store.snapshot(project)['records'] if r['id']==recorded['record_id'])
    assert original['payload']['inputs']['inputs']['force']['value']==3
    window.input.setText('Set force to 7 N');window.on_send();pump(app,lambda:not window.is_busy)
    assert 'Updated Actual work calculation' in window.history[-1]['content']
    view=visible_section(window,app,host,'calculator')
    pump(app,lambda:view.last_result is not None and view.last_result['outputs']['result']==14)


def test_native_actual_assembly_controls_and_file_export(window,app,tmp_path,monkeypatch):
    from hashlib import sha256
    from morice.ui_next.rich_files import FilesView
    from morice.unified_intelligence import PermissionState
    window._session_enabled=True;window._render_chat_messages([])
    research=window.runtime.research;project=research.create('Owned two-part geometry')
    manifests=[]
    for length in (10,20):
        value=research.execute('research.cad',{name:{'value':length,'unit':'mm'} for name in ('width','height','depth')})
        assert value.success;manifests.append(value.output)
    parts=[{'id':str(index),'name':'Actual part '+str(index+1),'stl':m['stl'],'sha256':m['sha256'],'units':'m',
        'translation':[index*.03,0,0]} for index,m in enumerate(manifests)]
    identifier=research.store.add(project,'result','Actual two-part geometry',{'inputs':{'parts':2},'method':'Owned verified box collection',
        'result':{'parts':parts,'units':'m'}},'CALCULATED')
    source=SourceRef('research_record',project+':'+identifier,scope=window._chat_id)
    window._append_direct_reply('Show the actual owned geometry files.','Two actual generated parts are available.',address=False)
    plan=ResponsePlan(window._chat_id,(Component('assembly',source,'Actual two-part assembly'),Component('files',source,'Actual source files')))
    window._present_response_plan(plan);host=window.findChildren(RichResponseHost)[-1]
    pump(app,lambda:bool(host.findChildren(MeshView)) and len(host.findChildren(MeshView)[0].parts)==2)
    view=host.findChildren(MeshView)[0];read_widget(window,app,view.canvas)
    assert sum(p['mesh'].triangles for p in view.parts)==24
    capture_native(window,'actual-two-part-geometry')
    QTest.mouseClick(view.wire,Qt.LeftButton);view.explode.setValue(100);app.processEvents()
    assert view.canvas.wireframe and view.canvas.explode==1
    view.part_list.item(0).setCheckState(Qt.Unchecked);app.processEvents()
    assert 'part:0' in view.canvas.hidden
    view.camera(1.2,.3);view.part_list.setCurrentRow(1)
    component=next(c for c in host.plan.components if c.kind=='assembly')
    assert component.config['camera']['yaw']==1.2 and component.config['selected']=='part:1'
    state=host.sections[component.id];host.release(state,preserve_height=False);host.schedule_visibility()
    view=visible_section(window,app,host,'assembly');pump(app,lambda:len(view.parts)==2)
    assert view.canvas.yaw==1.2 and view.canvas.selected=='part:1' and view.canvas.wireframe and view.canvas.explode==1
    files=visible_section(window,app,host,'files');artifact=files.context.snapshot.artifacts[0]
    destination=tmp_path/'actual-export.stl'
    monkeypatch.setattr('PySide6.QtWidgets.QFileDialog.getSaveFileName',lambda *args,**kwargs:(str(destination),''))
    window.runtime.kernel.permissions.controller.set_state('file_write',PermissionState.DENIED)
    files.export(artifact);app.processEvents();assert not destination.exists()
    window.runtime.kernel.permissions.controller.set_state('file_write',PermissionState.ASK)
    files.export(artifact);pump(app,lambda:destination.is_file())
    assert sha256(destination.read_bytes()).hexdigest()==artifact.sha256
    assert not window.runtime.desktop_automation_enabled


def test_native_actual_file_previews_decode_image_svg_pdf_and_video(window,app):
    from hashlib import sha256
    from io import BytesIO
    import struct
    from PIL import Image
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage,QColor,QPainter,QPdfWriter
    research=window.runtime.research;directory=research.directory/'owned-preview-fixture';directory.mkdir(parents=True)
    image=QImage(96,64,QImage.Format_RGB32);image.fill(QColor('#198abb'))
    painter=QPainter(image);painter.fillRect(12,12,40,30,QColor('#e8ba37'));painter.end();assert image.save(str(directory/'actual.png'))
    (directory/'actual.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="96" height="64"><rect width="96" height="64" fill="#198abb"/><circle cx="40" cy="30" r="14" fill="#e8ba37"/></svg>')
    writer=QPdfWriter(str(directory/'actual.pdf'));painter=QPainter(writer);painter.drawText(100,200,'Actual owned MORICE preview fixture');painter.end();del writer
    # Small real MJPEG AVI fixture. The native decoder, not this writer, verifies playback.
    def chunk(name,data):return name+struct.pack('<I',len(data))+data+(b'\0' if len(data)%2 else b'')
    frames=[]
    for index in range(6):
        frame=Image.new('RGB',(64,48),(index*35,90,210-index*25));stream=BytesIO();frame.save(stream,format='JPEG');frames.append(stream.getvalue())
    main=struct.pack('<14I',200000,max(map(len,frames))*5,0,0x10,len(frames),0,1,max(map(len,frames)),64,48,0,0,0,0)
    stream=struct.pack('<4s4sIHH8I4h',b'vids',b'MJPG',0,0,0,0,1,5,0,len(frames),max(map(len,frames)),0xffffffff,0,0,0,64,48)
    bitmap=struct.pack('<IiiHH4sIiiII',40,64,48,1,24,b'MJPG',64*48*3,0,0,0,0)
    header=chunk(b'LIST',b'hdrl'+chunk(b'avih',main)+chunk(b'LIST',b'strl'+chunk(b'strh',stream)+chunk(b'strf',bitmap)))
    movie=b'';index=b''
    for frame in frames:
        index+=struct.pack('<4sIII',b'00dc',0x10,len(movie)+4,len(frame));movie+=chunk(b'00dc',frame)
    body=b'AVI '+header+chunk(b'LIST',b'movi'+movie)+chunk(b'idx1',index)
    (directory/'actual.avi').write_bytes(b'RIFF'+struct.pack('<I',len(body))+body)
    checks={p.name:sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
    project=research.create('Owned actual previews');record=research.store.add(project,'result','Actual local preview collection',
        {'result':{'directory':str(directory),'checksums':checks}},'USER_DATA')
    window._render_chat_messages([]);window._append_direct_reply('Show the owned files.','Actual fixture files.',address=False)
    window._present_response_plan(ResponsePlan(window._chat_id,(Component('files',SourceRef('research_record',project+':'+record,scope=window._chat_id),'Actual previews'),)))
    host=window.findChildren(RichResponseHost)[-1];files=visible_section(window,app,host,'files')
    artifacts={a.name:a for a in files.context.snapshot.artifacts}
    def preview(name):
        files.open_preview(artifacts[name]);pump(app,lambda:files.preview is not None and not files.preview._disposed and files.preview.artifact.name==name)
        return files.preview
    view=preview('actual.png');pump(app,lambda:view.image._has_image)
    assert view.image.scene_owner.items()[0].pixmap().size()==QSize(96,64)
    view=preview('actual.svg');pump(app,lambda:view.preview is not None)
    assert view.preview.renderer().isValid()
    view=preview('actual.pdf');assert view.preview.pdf_document.pageCount()==1
    assert not view.preview.pdf_document.render(0,QSize(160,160)).isNull()
    read_widget(window,app,view);capture_native(window,'actual-file-and-pdf-preview')
    view=preview('actual.avi');assert view.player is not None;view.play_verified()
    pump(app,lambda:view._decoded_frames>0,timeout=15)
    assert view.player.duration()>0
    player=view.player;window.navigate('settings');app.processEvents()
    assert host.sections[next(iter(host.sections))]['view'] is None
    from shiboken6 import isValid
    assert not isValid(player) or player.source().isEmpty()


def test_native_math_diagram_and_actual_geographic_recalculation(window,app):
    from PySide6.QtWidgets import QLabel
    from morice.ui_next.rich_science import MathView,DiagramView,SpatialResultView
    from morice.rich_response.sources import digest
    spatial=window.runtime.spatial;result=spatial.handle_text('Show Chennai and Tokyo')
    assert result and result['context']['result']['distance']>0
    source=SourceRef('spatial','current',digest(spatial.snapshot()),window._chat_id)
    window._render_chat_messages([]);window._append_direct_reply('Show actual geographic results.','Actual offline geographic calculation.',address=False)
    window._present_response_plan(ResponsePlan(window._chat_id,(
        Component('math',title='Supplied expression',config={'formula':'E = F d'}),
        Component('diagram',title='Explanation flow',config={'nodes':[{'id':'a','label':'Supplied inputs'},{'id':'b','label':'Calculated result'}],'edges':[{'from':'a','to':'b','label':'calculate'}]}),
        Component('spatial',source,'Actual Chennai to Tokyo'))))
    host=window.findChildren(RichResponseHost)[-1]
    view=visible_section(window,app,host,'math');assert isinstance(view,MathView) and any('E = F d' in label.text() for label in view.findChildren(QLabel))
    view=visible_section(window,app,host,'diagram');assert isinstance(view,DiagramView)
    read_widget(window,app,view.canvas);pump(app,lambda:len(view.canvas._node_rects)==2)
    view.canvas.setFocus();QTest.keyClick(view.canvas,Qt.Key_Right);assert view.canvas.pan_x!=0
    QTest.keyClick(view.canvas,Qt.Key_Home);assert view.canvas.pan_x==0
    view=visible_section(window,app,host,'spatial');assert isinstance(view,SpatialResultView)
    kilometres=result['context']['result']['distance'];view.unit.setCurrentText('miles')
    pump(app,lambda:'miles' in view.value.text())
    assert abs(view.canvas.context['result']['distance']-kilometres/1.609344)<1e-5


def test_native_latest_project_and_transcribed_navigation_use_first_party_bindings(window,app,tmp_path,monkeypatch):
    from morice.workspace_state import WorkspaceState
    from morice.speech_runtime import TranscriptResult
    first=tmp_path/'first-owned-project';second=tmp_path/'second-owned-project';first.mkdir();second.mkdir()
    window._select_existing_project_folder(str(first))
    # Separate actual user selections beyond Windows' clock granularity. Tied
    # timestamps correctly require clarification and have their own tests.
    QTest.qWait(25);app.processEvents();window._select_existing_project_folder(str(second))
    restored=WorkspaceState.from_dict(window.workspace_state.to_dict());assert len(restored.recent_projects)==2
    window.input.setText('Open my latest project');window.on_send();pump(app,lambda:not window.is_busy)
    assert window.active_route=='projects' and window.project_folder==str(second), {'route':window.active_route,'history':window.history[-2:],'busy':window.is_busy}
    assert not window.runtime.desktop_automation_enabled
    (second/'test_owned_project.py').write_text("from pathlib import Path\ndef test_owned():\n    Path('owned-ran.txt').write_text('owned')\n    assert 2+2 == 4\n")
    original=window.nlui_port._execute;confirm={'allowed':False}
    def execute(capability,arguments,conversation_id=''):
        if capability=='host.confirm':return {'confirmed':confirm['allowed']}
        return original(capability,arguments,conversation_id)
    monkeypatch.setattr(window.nlui_port,'_execute',execute)
    window.input.setText('Run the project tests');window.on_send();pump(app,lambda:not window.is_busy)
    assert not (second/'owned-ran.txt').exists() and 'not authorized' in window.history[-1]['content']
    confirm['allowed']=True
    window.input.setText('Run the project tests');window.on_send();pump(app,lambda:not window.is_busy,timeout=20)
    assert (second/'owned-ran.txt').read_text()=='owned'
    assert 'exit code 0' in window.history[-1]['content']
    window.project_folder=str(first);window.project_folder_input.setText(str(first))
    window.input.setText('Open my second-owned-project project, then run the project tests');window.on_send();pump(app,lambda:not window.is_busy,timeout=20)
    assert window.project_folder==str(second) and 'exit code 0' in window.history[-1]['content']
    window.input.setText('Run the project tests, then fix this project');window.on_send();pump(app,lambda:not window.is_busy,timeout=20)
    assert 'No failing-test repair was needed' in window.history[-1]['content'] and not window.pending_project_patch
    confirm['allowed']=False
    window.input.setText('Run the project tests, then fix this project');window.on_send();pump(app,lambda:not window.is_busy,timeout=20)
    assert 'No repair or alternate action was started' in window.history[-1]['content'] and not window.pending_project_patch
    window.chat_mode='voice';window._voice_conversation_active=True;window._speech_base_text=''
    window._on_speech_transcript(TranscriptResult('owned-transcript','Open Settings',250))
    pump(app,lambda:window.nlui_port.context().route=='settings')
    assert window.chat_mode=='voice' and window._voice_conversation_active
    assert window.history[-2]['content']=='Open Settings'


def test_native_project_proposal_review_apply_and_actual_build_receipts(window,app,tmp_path,monkeypatch):
    from morice.ui_next.rich_controls import ProgressView,ValidationView
    root=tmp_path/'owned-addition-project';root.mkdir()
    window._select_existing_project_folder(str(root));window.project_access='limited'
    # The production deterministic starter still enters the same Builder and
    # preview/apply pipeline. No model or desktop-control permission is needed.
    monkeypatch.setattr(window,'_configure_project_backend',lambda **kwargs:'')
    window.input.setText('Build a simple Python addition calculator in this project');window.on_send()
    pump(app,lambda:not window.is_busy,timeout=25)
    assert window.pending_project_patch and not (root/'main.py').exists()
    session_id=window._pending_build_session.session_id
    assert window.changes_apply_btn.isEnabled() and 'review' in window.history[-1]['content'].casefold()
    window.navigate('chats')
    host=next(host for host in window._rich_hosts if any(c.source.kind=='build_session' for c in host.plan.components))
    progress=visible_section(window,app,host,'progress');assert isinstance(progress,ProgressView)
    assert 'Planned' in progress.status.text() and 'No build has completed' in progress.details.text()
    window._apply_pending_project_patch()
    pump(app,lambda:window._last_project_build_id==session_id and not window._project_build_id,timeout=50)
    session=window.runtime.autonomous_builder.project_runtime.load(session_id)
    assert (root/'main.py').is_file() and session.health['tests']=='pass',session.result_card()
    assert any(row['stage']=='test' and row['status']=='passed' for row in session.command_evidence)
    progress.refresh();pump(app,lambda:not progress._loading)
    assert progress.status.text().split(': ')[1].casefold()==session.status
    validation=visible_section(window,app,host,'validation');assert isinstance(validation,ValidationView)
    QTest.mouseClick(validation.refresh_button,Qt.LeftButton);pump(app,lambda:validation.refresh_button.isEnabled())
    assert any('Tests: pass' in label.text() for label in validation.findChildren(__import__('PySide6.QtWidgets',fromlist=['QLabel']).QLabel))
    window.input.setText('Show project test results');window.on_send();pump(app,lambda:not window.is_busy)
    assert 'test: passed (exit 0)' in window.history[-1]['content']


def test_native_failed_tests_prepare_scoped_repair_using_actual_logs(window,app,tmp_path,monkeypatch):
    import json
    from morice.agent_runtime.models import ModelReply
    root=tmp_path/'owned-repair-project';root.mkdir();(root/'tests').mkdir()
    (root/'main.py').write_text('def add(a, b):\n    return a - b\n')
    (root/'tests/test_main.py').write_text('import unittest\nfrom main import add\nclass ActualTests(unittest.TestCase):\n    def test_actual_add(self):\n        self.assertEqual(add(2, 3), 5)\n')
    unrelated=root/'unrelated.txt';unrelated.write_text('Preserve this owned file.')
    prompts=[]
    def backend(**kwargs):
        prompts.append(kwargs['prompt'])
        return ModelReply(json.dumps({'files':[{'path':'main.py','content':'def add(a, b):\n    return a + b\n'}]}),'owned-repair-fixture',200,80)
    window.runtime.agents.models.configure('owned-repair-fixture',backend)
    monkeypatch.setattr(window,'_configure_project_backend',lambda **kwargs:'owned-repair-fixture')
    original=window.nlui_port._execute
    monkeypatch.setattr(window.nlui_port,'_execute',lambda cap,args,conversation_id='':{'confirmed':True} if cap=='host.confirm' else original(cap,args,conversation_id))
    window._select_existing_project_folder(str(root));window.project_access='limited'
    window.input.setText('Run the project tests, then fix this project');window.on_send();pump(app,lambda:not window.is_busy,timeout=30)
    assert prompts and 'Actual prior test output' in prompts[0] and 'FAILED' in prompts[0]
    assert window.pending_project_patch and [c['path'] for c in window.pending_project_patch['changes']]==['main.py']
    identifier=window._pending_build_session.session_id
    assert 'return a - b' in (root/'main.py').read_text()
    window._apply_pending_project_patch()
    pump(app,lambda:window._last_project_build_id==identifier and not window._project_build_id,timeout=50)
    session=window.runtime.autonomous_builder.project_runtime.load(identifier)
    assert session.health['tests']=='pass' and 'return a + b' in (root/'main.py').read_text()
    assert unrelated.read_text()=='Preserve this owned file.'


def test_native_metrics_status_comparison_timeline_low_quality_and_theme_switch(window,app):
    from dataclasses import replace
    from PySide6.QtWidgets import QLabel
    from morice.ui_next.rich_primitives import MetricsView,StatusView,TimelineView
    from morice.ui_next.rich_controls import ComparisonView
    research=window.runtime.research;project=research.create('Owned low quality acceptance')
    research.store.add(project,'observation','Actual recorded note',{'purpose':'Owned native acceptance'},'USER_DATA')
    lab=research.laboratory;identifiers=[]
    for points in (3,5):
        row=lab.prepare(density_spec(parameter_ranges={'fraction_a':{'min':0,'max':1,'unit':'','points':points}}),project_id=project)
        lab.start(row['id']);wait_experiment(lab,row['id']);identifiers.append(row['id'])
    window.theme_engine.apply_profile(replace(window.theme_engine.profile,quality='LOW',reduced_motion=True,high_contrast=True))
    window.resize(900,650);window._append_direct_reply('Show actual low quality results.','Actual controlled computational results.',address=False)
    source=SourceRef('experiment',identifiers[1],scope=window._chat_id)
    plan=ResponsePlan(window._chat_id,(Component('metrics',source,'Actual counts',{'fields':['completed_runs']}),
        Component('status',source,'Actual state'),Component('comparison',SourceRef('experiment_comparison',':'.join(identifiers),scope=window._chat_id),'Actual comparison'),
        Component('timeline',SourceRef('research_project',project,scope=window._chat_id),'Actual saved record history')))
    window._present_response_plan(plan);host=next(h for h in window._rich_hosts if h.plan.id==plan.id)
    metrics=visible_section(window,app,host,'metrics');assert isinstance(metrics,MetricsView)
    assert any(label.text()=='5' for label in metrics.findChildren(QLabel))
    status=visible_section(window,app,host,'status');assert isinstance(status,StatusView)
    assert any('COMPLETED' in label.text() for label in status.findChildren(QLabel))
    compare=visible_section(window,app,host,'comparison');assert isinstance(compare,ComparisonView)
    assert any('→' in label.text() for label in compare.findChildren(QLabel))
    timeline=visible_section(window,app,host,'timeline');assert isinstance(timeline,TimelineView)
    assert any('Actual recorded note' in timeline.events.item(i).text() for i in range(timeline.events.count()))
    window.theme_engine.apply_profile(replace(window.theme_engine.profile,preset='ICE'));app.processEvents()
    assert not host.closed and window.theme_engine.profile.reduced_motion and window.theme_engine.profile.quality=='LOW'
    capture_native(window,'actual-low-quality-native-history')


def test_late_section_above_does_not_push_selected_result_out_of_view(window,app,monkeypatch):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel
    from morice.rich_response.registry import ResponseComponentRegistry
    from morice.ui_next.rich_primitives import StatusView
    research=window.runtime.research
    above=research.create('Actual earlier stored source');selected=research.create('Actual selected stored source')
    research.store.add(above,'observation','Owned observation',{'value':3},'USER_DATA')
    registry=ResponseComponentRegistry();mounted=[]
    def tall_actual_source(component,context):
        view=QWidget();view.setMinimumHeight(1100);layout=QVBoxLayout(view)
        layout.addWidget(QLabel(context.snapshot.title+' · '+str(len(context.snapshot.rows))+' actual saved records'))
        mounted.append(context.snapshot.source.id)
        return view
    registry.register('metrics',tall_actual_source);registry.register('status',StatusView)
    monkeypatch.setattr('morice.ui_next.rich_response.native_registry',lambda:registry)
    window._append_direct_reply('Show the two actual sources.','Actual saved source display.',address=False)
    components=(Component('metrics',SourceRef('research_project',above,scope=window._chat_id),'Earlier source'),
        Component('status',SourceRef('research_project',selected,scope=window._chat_id),'Selected source'))
    plan=ResponsePlan(window._chat_id,components);window._present_response_plan(plan)
    host=next(h for h in window._rich_hosts if h.plan.id==plan.id);held=[]
    original=host.bridge.submit
    def submit(title,operation,callback,**kwargs):
        def delivered(envelope):
            snapshot=envelope.get('value')
            if title=='Load response source' and envelope['ok'] and snapshot.source.id==above:
                held.append((callback,envelope))
            else:callback(envelope)
        return original(title,operation,delivered,**kwargs)
    monkeypatch.setattr(host.bridge,'submit',submit)
    try:
        state=host.sections[components[1].id]
        pump(app,lambda:bool(held))
        # Select the lower section through its actual native toggle while the
        # earlier source's actual background result awaits delivery. Holding
        # delivery avoids blocking the deliberately single background worker.
        state['toggle'].setChecked(False);state['toggle'].setChecked(True)
        view=visible_section(window,app,host,'status');QTest.qWait(250);app.processEvents()
        offset=state['toggle'].mapTo(window.scroll.viewport(),QPoint()).y()
        assert 0<=offset<window.scroll.viewport().height()
        callback,envelope=held.pop();callback(envelope)
        assert above in mounted
        QTest.qWait(250);app.processEvents()
        position=state['toggle'].mapTo(window.scroll.viewport(),QPoint()).y()
        assert abs(position-offset)<=8 and 0<=position<window.scroll.viewport().height()
        assert state['view'] is view and not window.follow_latest
    finally:held.clear()


def test_native_virtualizing_rich_row_cancels_its_worker_and_preserves_bounded_chat(window,app):
    import threading
    from morice.premium_experience import MAX_VISIBLE_CHAT_WIDGETS
    window._render_chat_messages([]);window._append_direct_reply('Show workspace status.','Actual status.',address=False)
    source=SourceRef('workspace','activity',scope=window._chat_id)
    window._present_response_plan(ResponsePlan(window._chat_id,(Component('status',source,'Actual activity'),)))
    host=window.findChildren(RichResponseHost)[-1];view=visible_section(window,app,host,'status')
    started=threading.Event();cancelled=threading.Event();callbacks=[]
    def operation(token):
        started.set();until=time.monotonic()+3
        while not token.cancelled and time.monotonic()<until:time.sleep(.01)
        if token.cancelled:cancelled.set()
    from morice.ui_next.rich_response import RichRenderContext
    component=next(iter(host.sections.values()))['component']
    context=RichRenderContext(host,component,host.sources.resolve(source))
    token=context.submit(view,'Owned disposal fixture',operation,lambda result:callbacks.append(result),cancellable=True)
    pump(app,started.is_set)
    for index in range(MAX_VISIBLE_CHAT_WIDGETS+5):window.append_message('MORICE','Actual later fixture '+str(index),force_scroll=True)
    app.processEvents();pump(app,cancelled.is_set)
    assert host.closed and token.cancelled and not host.jobs and not callbacks
    assert len(window._message_rows)==MAX_VISIBLE_CHAT_WIDGETS


def test_native_geographic_chat_history_rehydrates_its_original_snapshot(window,app):
    window._session_enabled=True;window._render_chat_messages([])
    window.input.setText('Show Chennai and Tokyo');window.on_send();pump(app,lambda:not window.is_busy)
    window.navigate('chats');pump(app,lambda:bool(window.findChildren(RichResponseHost)))
    host=next(host for host in window._rich_hosts if not host.closed)
    source=host.plan.components[0].source
    assert source.id==window.history[-1]['message_id']
    original=host.sources.resolve(source).data
    window.runtime.spatial.handle_text('Show London and New York')
    window._render_chat_messages(window.history)
    pump(app,lambda:any(not item.closed and item.plan.id==host.plan.id for item in window._rich_hosts))
    restored=next(item for item in window._rich_hosts if not item.closed and item.plan.id==host.plan.id)
    assert restored.sources.resolve(source).data==original
    assert restored.sources.resolve(source).data['destination']!=window.runtime.spatial.snapshot()['destination']


def test_native_job_controls_pause_resume_and_cancel_existing_experiment(window,app):
    from dataclasses import replace
    research=window.runtime.research;lab=research.laboratory
    tool=research.simulations.get('ideal_mixture_density');original=tool.evaluate
    def measured_slow_fixture(parameters):time.sleep(.04);return original(parameters)
    research.simulations.tools[tool.tool_id]=replace(tool,evaluate=measured_slow_fixture)
    row=lab.prepare(density_spec(),chat_id=window._chat_id)
    source=SourceRef('experiment',row['id'],scope=window._chat_id)
    window._render_chat_messages([]);window._append_direct_reply('Control the actual owned experiment.','Prepared computational fixture.',address=False)
    window._present_response_plan(ResponsePlan(window._chat_id,(Component('simulation',source,'Actual experiment controls'),)))
    host=next(host for host in window._rich_hosts if not host.closed);view=visible_section(window,app,host,'simulation')
    run,pause,cancel=view.buttons
    assert run.isEnabled() and not pause.isEnabled() and not view.timer.isActive()
    QTest.mouseClick(run,Qt.LeftButton);pump(app,lambda:pause.isEnabled() and 'Running' in view.status.text())
    QTest.mouseClick(pause,Qt.LeftButton);pump(app,lambda:lab.get(row['id'])['status']=='PAUSED')
    pump(app,lambda:run.isEnabled() and not view.timer.isActive())
    completed=lab.get(row['id'])['completed_runs'];assert completed<row['estimate']['planned_runs']
    QTest.mouseClick(run,Qt.LeftButton);pump(app,lambda:pause.isEnabled() and 'Running' in view.status.text())
    QTest.mouseClick(cancel,Qt.LeftButton);pump(app,lambda:lab.get(row['id'])['status']=='CANCELLED')
    pump(app,lambda:not view.timer.isActive())
    assert lab.get(row['id'])['completed_runs']>=completed


def test_native_chart_exports_actual_png_svg_pdf_and_preserves_denial_and_existing_files(window,app,tmp_path,monkeypatch):
    from PIL import Image
    from pypdf import PdfReader
    from xml.etree import ElementTree
    from PySide6.QtWidgets import QPushButton
    from morice.unified_intelligence import PermissionState
    content='Plot these actual supplied observations for this owned fixture; values do not claim instrument validation.\nx,y\n1,2\n2,4\n3,9'
    window._render_chat_messages([]);window._append_direct_reply(content,'The supplied values can be explored.',address=False);window._present_user_data()
    host=next(host for host in window._rich_hosts if not host.closed);view=visible_section(window,app,host,'chart')
    window.scroll.ensureWidgetVisible(view.canvas);app.processEvents()
    button=next(button for button in view.findChildren(QPushButton) if button.text()=='Export chart…')
    original=window.nlui_port._execute;selections=[]
    def execute(capability,arguments,conversation_id=''):
        if capability=='file.destination':
            path=tmp_path/arguments['name'];selections.append(path);return {'destination':str(path)}
        return original(capability,arguments,conversation_id)
    monkeypatch.setattr(window.nlui_port,'_execute',execute)
    policy=window.runtime.kernel.permissions.controller
    policy.set_state('file_write',PermissionState.DENIED);QTest.mouseClick(button,Qt.LeftButton)
    pump(app,lambda:'does not allow' in view.values.text());assert not selections
    policy.set_state('file_write',PermissionState.ASK)
    for format in ('PNG','SVG','PDF'):
        view.export_format.setCurrentText(format);QTest.mouseClick(button,Qt.LeftButton)
        destination=tmp_path/('MORICE-chart.'+format.casefold())
        pump(app,lambda:destination.is_file() and 'verified its destination hash' in view.values.text())
        if format=='PNG':
            with Image.open(destination) as image:assert image.width>200 and image.height>=280;image.verify()
        elif format=='SVG':assert ElementTree.parse(destination).getroot().tag.endswith('svg')
        else:assert len(PdfReader(destination).pages)==1
    original_bytes=(tmp_path/'MORICE-chart.png').read_bytes()
    view.export_format.setCurrentText('PNG');QTest.mouseClick(button,Qt.LeftButton)
    pump(app,lambda:'never silently overwrites' in view.values.text())
    assert (tmp_path/'MORICE-chart.png').read_bytes()==original_bytes
    assert not tuple((window.runtime.directory/'response-cache').glob('chart-*'))
    import csv,json
    for command,name in (('Export this table as CSV','MORICE-source-sample.csv'),('Export this data as JSON','MORICE-source-sample.json'),('Export this as PDF','MORICE-response-report.pdf')):
        window.input.setText(command);window.on_send();pump(app,lambda:not window.is_busy,timeout=20)
        assert (tmp_path/name).is_file(),window.history[-1]['content']
    with (tmp_path/'MORICE-source-sample.csv').open(newline='',encoding='utf-8') as stream:assert len(list(csv.reader(stream)))==4
    data=json.loads((tmp_path/'MORICE-source-sample.json').read_text(encoding='utf-8'))
    assert data['sample_rows']==3 and [row['y'] for row in data['rows']]==[2,4,9]
    text=' '.join(('\n'.join(page.extract_text() for page in PdfReader(tmp_path/'MORICE-response-report.pdf').pages)).split())
    assert 'MORICE response report' in text and 'Source:' in text and 'USER_DATA' in text
    assert not tuple((window.runtime.directory/'response-cache').iterdir())


def test_native_find_conversation_shows_matching_transcript_sources_instead_of_all_history(window,app):
    window._session_enabled=True;window._render_chat_messages([])
    history=window.runtime.chat_history
    messages=[{'role':'user','content':'A neutral saved conversation'},{'role':'assistant','content':'A fusion reactor uses tungsten walls.'},{'role':'assistant','content':'A neutral preview'}]
    history.save('actual-earlier',messages);history.save('private-earlier',messages);history.configure('private-earlier','Private',retention='session')
    window.input.setText('Find the chat about fusion');window.on_send();pump(app,lambda:not window.is_busy)
    host=next(host for host in window._rich_hosts if not host.closed);view=visible_section(window,app,host,'table')
    pump(app,lambda:bool(view.model.rows))
    assert [row['id'] for row in view.model.rows]==['actual-earlier']
    assert 'fusion reactor' in view.model.rows[0]['matching_excerpt']
