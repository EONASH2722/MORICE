from pathlib import Path
import json
import os
import subprocess
import sys
import time
import uuid

import pytest

from morice.computer_use import parse_computer_request,requests_desktop_automation
from morice.pc_control import ActionRisk,ControlAction,FastActionRouter,PermissionCategory


@pytest.mark.parametrize('text,verb',[
    ('Show the controls in Notepad','inspect'),
    ('Please inspect the app Calculator','inspect'),
    ('Type "Hello {Ctrl}{A} literally" into Notepad','type'),
    ('Set the field "Fixture input" in My app to "literal text"','set_value'),
    ('Click "Apply" in My app and check for "Applied"','invoke'),
    ('Focus the field "Subject" in My app','focus'),
    ('Scroll "Content" down in My app','scroll'),
])
def test_typed_computer_requests_use_registered_actions(text,verb):
    parsed=parse_computer_request(text)
    assert parsed and parsed[0]==verb
    decision=FastActionRouter().route(text)
    assert decision.action.tool_id=='computer.'+verb
    assert PermissionCategory.DESKTOP_AUTOMATION in decision.action.permissions
    if verb in {'type','set_value','invoke'}:assert decision.action.risk==ActionRisk.DESTRUCTIVE


def test_general_prose_is_not_a_computer_control_instruction():
    assert not parse_computer_request('Explain how accessibility tools work.')
    assert not requests_desktop_automation('Explain why a click can change a UI state.')
    assert not requests_desktop_automation('Type I errors in statistics: explain them.')
    assert not requests_desktop_automation('Press release ideas for a new product.')
    assert requests_desktop_automation('Use Paint to draw a circle.')
    assert requests_desktop_automation('Take control of my PC and open an app.')


@pytest.mark.skipif(os.name!='nt',reason='Actual native Windows accessibility integration')
def test_actual_owned_accessible_app_text_invoke_and_revocation(tmp_path,monkeypatch):
    from morice.runtime_services import RuntimeServices
    from morice import settings
    monkeypatch.setattr(settings,'_settings_dir',lambda:str(tmp_path/'settings'))
    monkeypatch.setenv('MORICE_PRELOAD','0');monkeypatch.setenv('MORICE_NODE_NETWORK','0')
    settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false'})
    fixture=Path(__file__).parent/'fixtures/desktop_control_app.py'
    title='MORICE owned UIA '+uuid.uuid4().hex
    output=tmp_path/'owned-result.json'
    environment={**os.environ,'QT_QPA_PLATFORM':'windows'}
    process=subprocess.Popen([sys.executable,str(fixture),str(output),title],env=environment,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    runtime=None
    try:
        deadline=time.monotonic()+20
        while not output.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.03)
        assert output.exists(),'Owned native fixture did not start.'
        runtime=RuntimeServices(tmp_path/'runtime',project_root=Path(__file__).resolve().parents[1])
        inspect=ControlAction('computer','inspect',title)
        blocked=runtime.pc_control.execute(inspect)
        assert not blocked.success and 'turn on Desktop automation' in blocked.message
        runtime.set_desktop_automation_enabled(True,persist=False)
        observed=runtime.pc_control.execute(inspect)
        assert observed.success and observed.verified,observed.to_dict()
        field=next(c for c in observed.output['controls'] if c['name']=='Fixture input')
        literal='Hello {Ctrl}{A} literally'
        action=ControlAction('computer','set_value',title,{'control_id':field['control_id'],'text':literal},
            permissions=(PermissionCategory.DESKTOP_AUTOMATION,PermissionCategory.SCREEN_ACCESS),
            risk=ActionRisk.DESTRUCTIVE)
        grant=runtime.pc_permissions.request_confirmation(action)
        changed=runtime.pc_control.execute(action,confirmation_token=grant.token)
        assert changed.success and changed.verified,json.dumps(changed.to_dict(),indent=2)
        assert json.loads(output.read_text())['text']==literal
        invoke=ControlAction('computer','invoke',title,{'name':'Apply fixture','expected':{'name':'Applied fixture'}},
            permissions=(PermissionCategory.DESKTOP_AUTOMATION,PermissionCategory.SCREEN_ACCESS),risk=ActionRisk.DESTRUCTIVE)
        grant=runtime.pc_permissions.request_confirmation(invoke)
        invoked=runtime.pc_control.execute(invoke,confirmation_token=grant.token)
        assert invoked.success and invoked.verified,invoked.to_dict()
        assert json.loads(output.read_text())['clicks']==1
        runtime.set_desktop_automation_enabled(False,persist=False)
        assert not runtime.pc_control.execute(inspect).success
    finally:
        if runtime is not None:runtime.shutdown()
        if process.poll() is None:process.terminate()
        try:process.communicate(timeout=8)
        except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=8)
