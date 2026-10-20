"""Explicit subprocess cases: actual Qt, media scheduler and verified artifacts."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from morice.media_lab.contracts import ModelState
from morice.ui_next.media_view import MediaWorkspace
from test_media_lab import media

class ImmediateBridge(QObject):
    event_arrived=Signal(object)
    def submit(self,title,operation,done,**kwargs):
        try:value={'ok':True,'value':operation()}
        except Exception as exc:value={'ok':False,'error':str(exc)}
        done(value)


@pytest.fixture
def image_view(media):
    app=QApplication.instance() or QApplication([])
    bridge=ImmediateBridge();view=MediaWorkspace(SimpleNamespace(media=media,kernel=media.kernel),bridge,SimpleNamespace(set_load=Mock()))
    yield view,media,app
    view.dispose();view.close();view.deleteLater();app.processEvents()


def test_prompt_only_image_creates_verified_artifact_without_references(image_view):
    view,lab,app=image_view
    assert view.intent.currentData()=='TEXT_TO_IMAGE' and view.reference_options.isHidden()
    view.prompt.setPlainText('CONTROLLED fixture: orange mountain sunset')
    assert view.run.isEnabled() and 'prompt only' in view.generation_hint.text()
    view.references=['this-file-must-never-be-read.png'];view.mask_path='also-unused-mask.png'
    view.submit();assert view.current_generation,view.status.text()
    result=lab._futures[view.current_generation].result(timeout=15)
    assert result.success
    record=lab.history_store.get(view.current_generation)
    assert record['request']['reference_images']==[] and record['request']['mask']==''
    assert Path(record['artifacts'][0]['path']).is_file()


def test_discovered_model_is_inspected_on_generate_and_clear_resets_workflow(image_view):
    view,lab,app=image_view
    model=lab.models.get('fixture');lab.models.register(replace(model,health=ModelState.DISCOVERED))
    view.refresh();view.prompt.setPlainText('CONTROLLED fixture: blue ocean')
    assert view.run.isEnabled()
    original=lab.inspect_model;lab.inspect_model=Mock(wraps=original)
    view.submit();assert view.current_generation,view.status.text()
    lab._futures[view.current_generation].result(timeout=15)
    lab.inspect_model.assert_called_once_with('fixture')
    view.references=['unused.png'];view.mask_path='unused.png'
    view.intent.setCurrentIndex(view.intent.findData('INPAINT'));view.clear_reference()
    assert not view.references and not view.mask_path and view.intent.currentData()=='TEXT_TO_IMAGE'
    assert not view.edit_options.isChecked()


def test_missing_model_reason_is_visible_not_reference_requirement(image_view):
    view,lab,app=image_view
    view._snapshot['models']=[];view.apply_snapshot();view.prompt.setPlainText('A mountain')
    assert not view.run.isEnabled()
    assert 'installed model weights' in view.generation_hint.text()


def test_model_preparation_disables_repeat_submission_and_recovers_on_error(image_view):
    view,lab,app=image_view
    view.prompt.setPlainText('CONTROLLED fixture: mountain')
    pending=[]
    view.bridge.submit=lambda title,operation,done,**kwargs:pending.append((title,operation,done))
    view.submit();view.submit()
    assert len(pending)==1 and view._submitting and not view.run.isEnabled()
    pending[0][2]({'ok':False,'error':'Controlled unavailable model dependency'})
    assert not view._submitting and 'dependency' in view.status.text()
    assert view.run.isEnabled()


def test_initial_model_selection_prefers_compatible_prompt_image_model(image_view):
    view,lab,app=image_view
    image=dict(view._snapshot['models'][0]);video={**image,'model_id':'video','display_name':'Video only','capabilities':['IMAGE_TO_VIDEO']}
    view.model.clear();view._snapshot['models']=[video,image];view.apply_snapshot()
    assert view.model.currentData()==image['model_id']
