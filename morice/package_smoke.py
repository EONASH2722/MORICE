"""Explicit local packaging probe using a caller-selected isolated profile."""
from __future__ import annotations


def run(output):
    import json
    import os
    from pathlib import Path
    import sys
    import time
    if not os.getenv("MORICE_RUNTIME_DIR") or not os.getenv("APPDATA"):
        raise RuntimeError("Packaging probe requires an explicitly isolated runtime and APPDATA.")
    os.environ.update(MORICE_PRELOAD="0",MORICE_DISABLE_SESSION="1",MORICE_DISABLE_RECOVERY="1",
        MORICE_NODE_NETWORK="0",MORICE_REDUCE_MOTION="1",MORICE_DISABLE_FIRST_RUN="1")
    from . import settings
    settings.save_settings({**settings.DEFAULT_SETTINGS,"tts_enabled":"false","stt_enabled":"false","pet_enabled":"false"})
    started=time.perf_counter()
    from PySide6.QtCore import QTimer, QRect, QPoint
    from PySide6.QtWidgets import QApplication
    from .pyside_app import create_application_window
    from .runtime_services import get_runtime_services
    app=QApplication([]);runtime=get_runtime_services();window=create_application_window(runtime,runtime.start());window.show()
    window._run_startup_health_check()
    spatial=None
    spatial=runtime.spatial.set_pair('Chennai','New York')['result']
    window.navigate('spatial');window.routes['spatial'].set_context(runtime.spatial.snapshot())
    geometry=[]
    for maximize in (False,True,False):
        window.showMaximized() if maximize else window.showNormal()
        window.navigate('home');app.processEvents()
        row={'maximized':maximize,'window':window.size().toTuple(),'controls':{}}
        for name in ('input','send_btn'):
            widget=getattr(window,name)
            bounds=QRect(widget.mapTo(window,QPoint()),widget.size())
            screen_bounds=QRect(widget.mapToGlobal(QPoint()),widget.size())
            row['controls'][name]={'visible':widget.isVisible(),'inside_window':window.rect().contains(bounds),'inside_screen':window.screen().availableGeometry().contains(screen_bounds)}
        geometry.append(row)
    from .ui_next.theme_scenes import SCENES
    # Exercise the new production imports, same-database migration and controls
    # from the isolated frozen profile without downloading/loading model weights.
    memory_rows=[{'role':'user','content':'Use the name Project Orion.'},
        *[{'role':'assistant','content':f'History fixture {i}'} for i in range(1000)]]
    runtime.chat_history.save('packaging-memory',memory_rows,merge=True)
    source=runtime.chat_history.search_messages('packaging-memory','Orion',limit=1)[0]
    assert source['sequence']==1
    assert len(runtime.chat_history.open('packaging-memory',recent=100)['messages'])==100
    runtime.desktop.memory.set_personal_enabled(True)
    preference=runtime.desktop.memory.save_preference('For coding tasks prefer detailed steps.')
    assert runtime.desktop.memory.preferences_for('implement a file manager')[0].memory_id==preference.memory_id
    runtime.desktop.memory.delete(preference.memory_id);runtime.desktop.memory.set_personal_enabled(False)
    assert not runtime.desktop.memory.preferences_for('implement an app')
    controls=window.routes['settings']
    assert 'Memory' in controls.categories and controls.fast_model_settings.automatic.isChecked()
    memory_probe={'earliest_message':source['sequence']==1,'bounded_reopen':True,'preference_persist_forget':True,
        'memory_controls':True,'fast_model_controls':True,'weights_loaded':False}
    from PySide6.QtTest import QTest
    from .ui_next.rich_charts import ChartView
    assert not runtime.desktop_automation_enabled and not controls.control_settings.desktop.isChecked()
    window.input.setText('Open memory settings');window.on_send()
    until=time.monotonic()+15
    while window.is_busy and time.monotonic()<until:app.processEvents();QTest.qWait(10)
    assert not window.is_busy and window.active_route=='settings'
    window.navigate('chats')
    from .ui_next.rich_response import RichResponseHost
    analysis='Evaluate a battery-powered tabletop generator.\n| Parameter | Value |\n| --- | --- |\n| Speed | 600 rpm |\n| Input | 2.5 W |'
    assert not window._handle_natural_node_control(analysis)
    window._append_direct_reply(analysis,'The supplied values are assumptions for written analysis.',address=False)
    assert not window.findChildren(RichResponseHost)
    window._append_direct_reply('Plot this actual packaging user data in a linked chart and table; these controlled values are not physical measurements.\nx,y\n1,2\n2,4\n3,9',
        'This chart reads the actual supplied rows.',address=False)
    until=time.monotonic()+15
    while not window.findChildren(ChartView) and time.monotonic()<until:app.processEvents();QTest.qWait(10)
    chart=window.findChildren(ChartView)[-1];assert len(chart.canvas.rows)==3
    chart.style.setCurrentText('scatter');chart.table_toggle.setChecked(True)
    until=time.monotonic()+10
    while chart.table.model.rowCount()!=3 and time.monotonic()<until:app.processEvents();QTest.qWait(10)
    assert chart.canvas.style=='scatter' and chart.table.model.rowCount()==3
    nlui_probe={'desktop_default_off':True,'native_settings_request':True,'actual_chart_rows':3,
        'linked_table_rows':3,'actual_style_change':True,'weights_loaded':False,
        'analysis_without_prompt_data_panel':True,'tabletop_not_tablet':True}
    from .pyside_app import ChatBubble,RichContentView
    reply='# Owned packaged reply\n\n'+r'Force \(F=mg\).'+ '\n\n$$\na=\\frac{F-mg}{m}\n$$'
    before=len(window._message_rows);window.follow_latest=True
    window._on_assistant_stream_delta('owned-package-math',reply[:25])
    bubble=window._stream_bubble
    assert bubble is not None and not bubble.findChildren(RichContentView)
    window._on_assistant_stream_delta('owned-package-math',reply[25:])
    window.history.append({'role':'assistant','content':reply})
    window._on_assistant_stream_finished('owned-package-math',reply);app.processEvents()
    assert len(window._message_rows)==before+1 and window._message_rows[-1].findChild(ChatBubble) is bubble
    math_view=bubble.findChild(RichContentView);assert math_view is not None
    math_state={};until=time.monotonic()+20
    while math_state.get('equations')!=2 and time.monotonic()<until:
        received=[]
        math_view.page().runJavaScript("document.body && JSON.stringify({equations:document.querySelectorAll('.katex').length,errors:document.querySelectorAll('.morice-math-error').length})",received.append)
        deadline=time.monotonic()+2
        while not received and time.monotonic()<deadline:app.processEvents();QTest.qWait(10)
        if received and received[0]:math_state=json.loads(received[0])
        app.processEvents();QTest.qWait(20)
    assert math_state.get('equations')==2 and math_state.get('errors')==0,math_state
    math_probe={**math_state,'same_stream_bubble':True,'copy_text_preserved':bubble.message==reply,'bundled_assets':True}
    scenes=[]
    for preset in SCENES:
        window.theme_engine.update(preset=preset,persist=False)
        field=window.material_backdrop.material()
        scenes.append({'preset':preset,'scene':window.material_backdrop.diagnostics()['scene'],'raster_present':field is not None})
    window.theme_engine.update(preset='GLASS',reduced_motion=False,persist=False)
    window.activateWindow();app.processEvents();initial_phase=window.material_backdrop._phase
    ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(time.perf_counter()));timer.start(25)
    QTimer.singleShot(3000,app.quit);app.exec()
    result={"frozen":bool(getattr(sys,"frozen",False)),"cwd":os.getcwd(),"startup_and_probe_ms":(time.perf_counter()-started)*1000,
        "window_created":True,"ui_ticks":len(ticks),"critical_failures":len(runtime.health_report.critical_failures),
        "health":[{"name":v.name,"status":v.status,"detail":v.detail} for v in runtime.health_report.checks],
        "roles":len(runtime.agents.roles.all()),"runtime_directory":str(runtime.directory)}
    result['ui']='renovated';result['production_window_factory']=True;result['window_class']=type(window).__name__
    result['fast_memory']=memory_probe
    result['nlui_rich_response']=nlui_probe
    result['reply_math']=math_probe
    result['composer_geometry']=geometry;result['theme_scenes']=scenes
    result['ambient_animation']={'phase_advanced':window.material_backdrop._phase!=initial_phase,'raster_count':window.material_backdrop.render_count,'reduced_motion':window.theme_engine.profile.reduced_motion}
    if spatial is not None:result['spatial_result']=spatial
    window.close();runtime.shutdown();result["shutdown"]=runtime.shutdown_report
    result["leases_after"]=len(runtime.kernel.resources.snapshot())
    Path(output).write_text(json.dumps(result,indent=2),encoding="utf-8")
    geometry_ok=all(all(control.values()) for row in geometry for control in row['controls'].values())
    return 0 if result["critical_failures"]==result["leases_after"]==0 and result["ui_ticks"]>10 and result["shutdown"]["clean"] and geometry_ok and all(row['raster_present'] for row in scenes) and result['ambient_animation']['phase_advanced'] else 1
