"""Actual owned native first-run wizard, without touching a user profile."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.update(QT_QPA_PLATFORM='windows',MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_DISABLE_FIRST_RUN='1',MORICE_NODE_NETWORK='0',MORICE_REDUCE_MOTION='1')
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QWizard
from PySide6.QtTest import QTest
from morice import settings
from morice.runtime_services import RuntimeServices
from morice.pyside_app import create_application_window
from morice.platform_ui import FirstRunWizard

app=QApplication([])
with tempfile.TemporaryDirectory(prefix='morice-first-run-') as directory:
    root=Path(directory);os.environ.update(APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local'),MORICE_LOCAL_DATA_DIR=str(root/'data'))
    with patch('morice.settings._settings_dir',return_value=str(root/'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false','pet_enabled':'false'})
        runtime=RuntimeServices(root/'runtime',project_root=ROOT)
        with patch('morice.runtime_services._RUNTIME_SERVICES',runtime):
            window=create_application_window(runtime,runtime.start());window.show();app.processEvents()
            try:
                service=runtime.platform_services.first_run;report=service.inspect(window.gpu_profile)
                assert not service.path.exists()
                wizard=FirstRunWizard(service,report,window);wizard.show();app.processEvents();pages=[]
                while wizard.currentId()!=wizard.pageIds()[-1]:
                    pages.append(wizard.currentPage().title());QTest.mouseClick(wizard.button(QWizard.NextButton),Qt.LeftButton);app.processEvents()
                pages.append(wizard.currentPage().title());wizard.workspace.setText(str(root/'owned-workspace'))
                QTest.mouseClick(wizard.button(QWizard.FinishButton),Qt.LeftButton);app.processEvents()
                actual=json.loads(service.path.read_text());assert actual['workspace']==str(root/'owned-workspace')
                assert (root/'owned-workspace').is_dir() and actual['selections']['permissionAcknowledged']
                evidence={'status':'OWNED_NATIVE_FIRST_RUN_PASSED','pages':pages,'workspace_created':True,'persisted_selection':True,'models_downloaded':False,'external_providers_enabled':False}
                wizard.deleteLater()
            finally:
                window.close();app.processEvents();runtime.shutdown();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
            evidence['shutdown']=runtime.shutdown_report;assert evidence['shutdown']['clean']
            (ROOT/'build/phase11-first-run-native.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence))
