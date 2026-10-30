"""Actual native shell entry, chat routing, secret entry and source-backed UI."""
from pathlib import Path
import json
from unittest.mock import patch
from test_fast_memory_ui import app,window,pump
from morice.security_lab.recovery import envelope_fixture

def test_native_recovery_receipt_and_transient_password(window,app,tmp_path):
    window.navigate('security');workspace=window.routes['security'];panel=workspace.lab_panel
    workspace.tabs.setCurrentWidget(panel);path=tmp_path/'owned.enc';path.write_bytes(envelope_fixture(b'Owned native recovery output',password='native-fixture-only'))
    panel.path.setText(str(path));panel.password.setText('native-fixture-only');panel.start('recover')
    pump(app,lambda:bool(panel.current) and panel.lab.snapshot(panel.current)['state']=='COMPLETED',timeout=20)
    job=panel.lab.snapshot(panel.current);assert job['status']=='RECOVERED',job
    pump(app,lambda:'RECOVERED' in panel.summary.text())
    assert not panel.password.text() and 'native-fixture-only' not in panel.evidence.toPlainText()
    assert panel.table.topLevelItemCount()>0 and Path(job['artifacts'][0]['path']).read_bytes()==b'Owned native recovery output'

def test_chat_analyze_and_ordinary_text_not_hijacked(window,app,tmp_path):
    window.navigate('security');panel=window.routes['security'].lab_panel
    path=tmp_path/'owned.txt';path.write_text('தமிழ் English العربية',encoding='utf-8');panel.path.setText(str(path))
    window.navigate('chats');window.input.setText('Analyze this file.');window.on_send()
    pump(app,lambda:not window.is_busy and panel.lab.latest is not None,timeout=20)
    job=panel.lab.snapshot();assert job['action']=='inspect' and job['state']=='COMPLETED',job
    assert 'TAMIL' in job['result']['text']['scripts']
    assert not window.runtime.nlui.resolve('Explain how encryption works in a science lesson.',window.nlui_port.context()).matched

def test_native_theme_and_export_existing_file_preserved(window,app,tmp_path):
    window.navigate('security');panel=window.routes['security'].lab_panel
    original=window.theme_engine.profile
    try:
        for preset in ('MORICE','ICE','GLASS'):
            window.theme_engine.update(preset=preset,persist=False);app.processEvents()
            assert panel.palette().color(panel.foregroundRole()).isValid()
    finally:window.theme_engine.apply_profile(original,persist=False)

def test_missing_inputs_are_clarified_without_fake_success(window,app):
    window.navigate('security');panel=window.routes['security'].lab_panel
    panel.path.clear();prepared=panel.prepare_nlui('recover',window._chat_id)
    assert prepared.get('question') and panel.runtime._security_lab is None
