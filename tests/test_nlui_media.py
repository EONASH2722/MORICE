"""Real controlled Media Lab jobs and exact source/export permissions."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from morice.nlui.contracts import ActiveContext
from morice.nlui.runtime import NaturalLanguageController
from morice.unified_intelligence import PermissionState
from test_media_lab import media,run,wait_until


def test_reference_variations_use_actual_artifact_then_deny_without_requeue(media,tmp_path):
    source,result=run(media);assert result.success
    controller=NaturalLanguageController(SimpleNamespace(kernel=media.kernel,media=media))
    port=Mock(window_id='w');port.execute.return_value={'confirmed':True};controller.attach_window(port)
    context=ActiveContext('chat','w',selected=({'kind':'generation','id':source},))
    resolution=controller.resolve('Make three variations of this image',context)
    result=controller.execute(resolution,context)
    assert result.status=='completed',result.message
    generated=result.executions[0]['output']['generation_id']
    wait_until(lambda:media.result(generated)['status'] in {'SUCCEEDED','FAILED'})
    record=media.result(generated);assert record['status']=='SUCCEEDED'
    assert record['request']['reference_images']==[media.artifact(source)['path']]
    assert record['request']['count']==3 and record['request']['intent']=='IMAGE_VARIATION'
    media.kernel.permissions.controller.set_state('file_read',PermissionState.DENIED)
    before=len(media.history());denied=controller.execute(resolution,context)
    assert denied.status=='failed' and len(media.history())==before
    media.kernel.permissions.controller.set_state('file_write',PermissionState.ASK)
    destination=tmp_path/'selected-export.png';port.execute.return_value={'destination':str(destination)}
    exported=controller.execute(controller.resolve('Save this image',context),context)
    assert exported.status=='completed',exported.message
    assert destination.read_bytes()==Path(media.artifact(source)['path']).read_bytes()
    media.kernel.permissions.controller.set_state('file_write',PermissionState.DENIED);port.execute.reset_mock()
    assert controller.execute(controller.resolve('Save this image',context),context).status=='failed'
    port.execute.assert_not_called()


def test_missing_animation_workflow_is_reported_before_queue_or_confirmation(media):
    source,result=run(media);assert result.success
    controller=NaturalLanguageController(SimpleNamespace(kernel=media.kernel,media=media))
    port=Mock(window_id='w');controller.attach_window(port)
    context=ActiveContext('chat','w',selected=({'kind':'generation','id':source},))
    before=len(media.history());result=controller.execute(controller.resolve('Animate this image',context),context)
    assert result.status=='failed' and 'PROVIDER UNAVAILABLE' in result.message
    assert len(media.history())==before;port.execute.assert_not_called()
