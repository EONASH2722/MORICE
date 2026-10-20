"""Native production-window checks; online searches require explicit --online."""
from __future__ import annotations
import argparse,hashlib,json,os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--online',action='store_true');parser.add_argument('--model-registry',type=Path)
args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='morice-location-image-qa-') as temporary:
    profile=Path(temporary)
    os.environ.update(APPDATA=str(profile/'roaming'),LOCALAPPDATA=str(profile/'local'),MORICE_LOCAL_DATA_DIR=str(profile/'data'),MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_DISABLE_FIRST_RUN='1',MORICE_PRELOAD='0',MORICE_NODE_NETWORK='0',MORICE_REDUCE_MOTION='1',QT_QPA_PLATFORM='windows')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from morice import settings
    from morice.runtime_services import RuntimeServices
    from morice.pyside_app import create_application_window
    from morice.media_lab.contracts import ImageModelDescriptor,ModelState
    from morice.version import VERSION
    app=QApplication([]);report={'version':VERSION,'online_requested':args.online,'screenshots':[],'real_model_generation':False}
    def pump(predicate,timeout=45):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:app.processEvents();QTest.qWait(10)
        assert predicate(),'Native delivery did not settle.'
    with patch('morice.settings._settings_dir',return_value=str(profile/'settings')):
        settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false','pet_enabled':'false','model_path':''})
        runtime=RuntimeServices(profile/'runtime',project_root=ROOT)
        with patch('morice.runtime_services._RUNTIME_SERVICES',runtime):
            if args.model_registry:
                registry=json.loads(args.model_registry.read_text(encoding='utf-8'))
                for value in registry['models']:
                    value=dict(value)
                    if value.pop('kind','image')!='image' or not Path(value['model_path']).exists():continue
                    value['health']=ModelState.DISCOVERED
                    for key in ('capabilities','files','recommended_resolution','maximum_resolution'):
                        value[key]=tuple(value[key])
                    if value.get('maximum_tested_resolution'):value['maximum_tested_resolution']=tuple(value['maximum_tested_resolution'])
                    runtime.media.models.register(ImageModelDescriptor(**value))
            window=create_application_window(runtime,runtime.start());window.resize(1366,840);window.show();app.processEvents()
            def capture(name):
                app.processEvents();QTest.qWait(120);path=output/name;assert window.grab().save(str(path));report['screenshots'].append({'name':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
            try:
                if args.online:
                    window.navigate('spatial');view=window.routes['spatial'];assert view.lookup.currentData() is True
                    view.query.setText('show mumbai and gujrat how far?');view.run.click();pump(lambda:not view._busy)
                    context=runtime.spatial.snapshot();assert context['pending'],view.status.text()
                    capture('01-gujrat-choices.png')
                    for index in range(view.candidates.count()):
                        item=view.candidates.item(index);identifier=item.data(__import__('PySide6.QtCore',fromlist=['Qt']).Qt.UserRole)[1]
                        location=runtime.spatial.get_location(identifier)
                        if location.kind=='state' and location.country=='IN':view.candidates.setCurrentRow(index);break
                    assert view.use_place.isEnabled();view.use_place.click()
                    pump(lambda:bool(runtime.spatial.snapshot()['result']))
                    context=runtime.spatial.snapshot();assert context['destination']['label']=='Gujarat' and context['origin']['label']=='Mumbai'
                    assert 'Representative points' in view.result.text();capture('02-mumbai-gujarat.png')
                    report['mumbai_gujarat']={'metres':context['result']['metres'],'origin':context['origin'],'destination':context['destination']}
                    view.query.setText('show mumbai and pakistan how far?');view.run.click();pump(lambda:not view._busy)
                    context=runtime.spatial.snapshot();assert context['destination']['kind']=='country' and context['destination']['country']=='PK',view.status.text()
                    report['mumbai_pakistan']={'metres':context['result']['metres'],'destination':context['destination']};capture('03-mumbai-pakistan.png')
                window.navigate('media');view=window.routes['media'];pump(lambda:not view._refreshing)
                view.prompt.setPlainText('A warm sunrise over a mountain lake, detailed natural landscape')
                assert view.intent.currentData()=='TEXT_TO_IMAGE' and not view.references and not view.mask_path
                assert not view.reference_options.isVisible() and not view.advanced_settings.isVisible()
                if args.model_registry:assert view.run.isEnabled(),view.generation_hint.text()
                assert not view.run.visibleRegion().isEmpty() and view.run.mapTo(window,view.run.rect().bottomRight()).y()<window.height()
                report['media']={'workflow':view.intent.currentData(),'reference_required':False,'mask_required':False,'generate_enabled':view.run.isEnabled(),'readiness':view.generation_hint.text(),'models':view.model.count(),'scope':'Actual UI with existing local model metadata; no new real-weight inference.'}
                capture('04-prompt-only-image.png')
            finally:
                window.close();app.processEvents();runtime.shutdown()
            assert runtime.shutdown_report['clean']
            h=hashlib.sha256()
            for path in sorted((ROOT/'morice').rglob('*.py')):h.update(str(path.relative_to(ROOT)).encode());h.update(path.read_bytes())
            report.update(source_sha256=h.hexdigest(),shutdown=runtime.shutdown_report,scope='Actual production Qt window; live geographic provider when explicitly enabled; media availability only, not real model inference.')
            (output/'evidence.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
