"""Record owned interactive controls with no new presentation ancestry."""
import json
import argparse
import hashlib
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--output',default='build/phase10-controls-current.json');args=parser.parse_args()
digest=hashlib.sha256()
for path in sorted((ROOT/'morice').rglob('*.py')):
    digest.update(str(path.relative_to(ROOT)).encode());digest.update(path.read_bytes())
with tempfile.TemporaryDirectory(prefix='morice-control-audit-') as directory:
    root=Path(directory)
    os.environ.update(APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local'),MORICE_LOCAL_DATA_DIR=str(root/'data'),
        MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_NODE_NETWORK='0',MORICE_REDUCE_MOTION='1',QT_QPA_PLATFORM='offscreen')
    from PySide6.QtWidgets import QApplication,QWidget,QAbstractButton,QComboBox,QAbstractItemView,QLineEdit,QDialog
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QTimer
    from morice import settings
    import morice.runtime_services as module
    from morice.runtime_services import RuntimeServices
    from morice.pyside_app import create_application_window
    settings.save_settings({**settings.DEFAULT_SETTINGS,'pet_enabled':'false','tts_enabled':'false','stt_enabled':'false','model_path':''})
    app=QApplication([]);runtime=RuntimeServices(root/'runtime',project_root=ROOT);module._RUNTIME_SERVICES=runtime
    window=create_application_window(runtime,runtime.start());window.show();missing=[];mounted=[];dialogs=[]
    try:
        for route in window.navigation.buttons:
            window.navigate(route);QTest.qWait(50)
        for name,widget in vars(window).items():
            if not isinstance(widget,(QAbstractButton,QComboBox,QAbstractItemView,QLineEdit)):continue
            chain=[];parent=widget;in_dialog=False
            while parent is not None:
                chain.append(type(parent).__name__);in_dialog=in_dialog or isinstance(parent,QDialog);parent=parent.parentWidget()
            row={'attribute':name,'class':type(widget).__name__,'parents':chain}
            if window.presentation_root.isAncestorOf(widget):mounted.append(row)
            elif in_dialog:dialogs.append(row)
            else:missing.append(row)
        replacements={
            'node_pair_btn':'Devices / Pairing', 'chat_history_btn':'History route',
            'research_lab_btn':'Research route', 'ambient_btn':'Automations / Connectors / Security routes',
            'changes_minimize_btn':'Projects persistent workspace', 'changes_expand_btn':'Projects persistent workspace',
            'changes_close_btn':'Workspace navigation / Core', 'theme_select':'Settings / Appearance',
            'animation_speed_select':'Settings / Appearance / Motion speed', 'reduced_motion_check':'Settings / Appearance / Reduced Motion',
            'high_contrast_check':'Settings / Appearance / High contrast', 'large_text_check':'Settings / Appearance / Font scale',
            'advanced_settings_btn':'Searchable Settings route', 'personalization_btn':'Settings / Personalization',
            'access_status_btn':'Projects / Access controls and mode status',
        }
        unexpected=[row['attribute'] for row in missing if row['attribute'] not in replacements]
        baseline=json.loads((ROOT/'build/phase10-prerequisites.json').read_text(encoding='utf-8-sig'))
        missing_callbacks=[name for name in baseline['controller_methods'] if not callable(getattr(window,name,None))]
        assert not unexpected and not missing_callbacks,(unexpected,missing_callbacks)
        result={'status':'CLASSIFIED_CONTROL_ACCESS_PASSED','source_sha256':digest.hexdigest(),
            'original_controller_methods_preserved':len(baseline['controller_methods']),
            'replacement_access':{row['attribute']:replacements[row['attribute']] for row in missing},
            'not_mounted':missing,'mounted':mounted,'owned_dialog_controls':dialogs,
            'scope':'Object reachability inventory; no claim that a control callback was exercised.'}
        target=ROOT/args.output;target.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({'not_mounted':[v['attribute'] for v in missing],'mounted':len(mounted),'dialog':len(dialogs)}))
    finally:
        window.close();QTest.qWait(350);app.processEvents()
        active_timers=[{'parent':type(timer.parent()).__name__,'interval_ms':timer.interval(),
                       'single_shot':timer.isSingleShot()} for timer in window.findChildren(QTimer) if timer.isActive()]
        runtime.shutdown()
    result['active_ui_timers_after_close']=active_timers
    result['shutdown']=runtime.shutdown_report
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'active_ui_timers_after_close':active_timers,'shutdown':result['shutdown']}))
    assert not active_timers and result['shutdown']['clean']
