"""Phase 9 contract tests, with clearly labelled controlled subprocess fixtures."""
from __future__ import annotations

import json,struct,sys,time,threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import psutil
from PIL import Image

from morice.agent_runtime import AgentCoordinator
from morice.kernel import CapabilityKernel,ExecutionContext,ResourceClaim,TaskNode,Priority,EventType
from morice.unified_intelligence import PermissionState
from morice.media_lab.contracts import ImageRequest,VideoRequest,ImageModelDescriptor,VideoModelDescriptor,MediaSettings,ModelState,Quality
from morice.media_lab.hardware import HardwareSnapshot
from morice.media_lab.runtime import MediaLab
from morice.media_lab.process import OwnedMediaProcesses
from morice.media_lab.providers import validate_workflow,ComfyUIProvider
from morice.media_lab.planner import MediaResourcePlanner
from morice.media_lab.registry import inspect_safetensors
from morice.media_lab.artifacts import verify_image,verify_video,atomic_export
from morice.media_lab.storage import atomic_json,MediaHistory,file_hash


class FixtureProvider:
    def __init__(self):
        self.processes=OwnedMediaProcesses()
        self.host_available_mb=12288  # Same controlled capacity as hardware().
    def health(self,model=None):return {'available':True,'version':'controlled-fixture-v1','reason':'CONTROLLED fixture only.'}
    def generate(self,identifier,model,request,plan,directory,context,progress):
        path=Path(directory)/'request.json';atomic_json(path,{'request':request.to_dict(),'output_directory':str(directory)})
        worker=Path(__file__).parent/'fixtures'/'media_worker.py'
        memory=psutil.virtual_memory()
        available=self.host_available_mb*2**20
        controlled=memory._replace(total=16384*2**20,available=available,free=available,
                                  used=(16384-self.host_available_mb)*2**20,
                                  percent=100*(16384-self.host_available_mb)/16384)
        # Only this labelled tiny fixture worker uses controlled host capacity.
        # Process-tree RSS, process cleanup and the default 2 GB guard are real.
        with patch.object(psutil,'virtual_memory',return_value=controlled):
            return self.processes.run(identifier,[sys.executable,'-I',str(worker),'--job',str(path)],directory,context,progress=progress)
    def close(self):self.processes.close()


def hardware(**values):
    return replace(HardwareSnapshot(gpu_name='CONTROLLED RTX fixture',total_vram_mb=6144,free_vram_mb=5500,used_vram_mb=644,driver='fixture',ram_total_mb=16384,ram_available_mb=12288,cpu_count=4,disk_free_mb=40000),**values)


@pytest.fixture
def media(tmp_path):
    kernel=CapabilityKernel();agents=AgentCoordinator(kernel);provider=FixtureProvider()
    lab=MediaLab(kernel,agents,tmp_path,providers={'test':provider},hardware_probe=hardware)
    folder=tmp_path/'models'/'image'/'fixture';folder.mkdir(parents=True,exist_ok=True)
    header=json.dumps({'weight':{'dtype':'F32','shape':[1],'data_offsets':[0,4]}}).encode()
    (folder/'fixture.safetensors').write_bytes(struct.pack('<Q',len(header))+header+b'\0'*4)
    model=ImageModelDescriptor('fixture','CONTROLLED fixture','controlled','test',str(folder),estimated_vram_mb=128,estimated_ram_mb=128,minimum_vram_mb=64,maximum_resolution=(1024,1024),capabilities=('TEXT_TO_IMAGE','IMAGE_TO_IMAGE','IMAGE_VARIATION','INPAINT','OUTPAINT'),default_steps=2,maximum_steps=4)
    lab.models.register(model);assert lab.inspect_model('fixture').health==ModelState.UNBENCHMARKED
    yield lab
    lab.close();agents.shutdown();kernel.shutdown()
    assert not provider.processes.snapshot()
    assert not kernel.resources.snapshot()


def request(prompt='controlled concept',**kwargs):return ImageRequest(prompt,model_id='fixture',width=64,height=64,**kwargs)


def run(media,prompt='controlled concept',**kwargs):
    identifier,future=media.submit(request(prompt,**kwargs));result=future.result(timeout=12)
    return identifier,result


def wait_until(predicate,timeout=5):
    deadline=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>deadline:raise AssertionError('Condition did not become true.')
        time.sleep(.01)


def test_shared_authorities_and_decoded_actual_subprocess_image(media):
    identifier,result=run(media)
    assert result.success and result.verification.status.value=='verified'
    artifact=media.artifact(identifier)
    assert verify_image(artifact['path'],64,64)['sha256']==artifact['sha256']
    assert media.result(identifier)['status']=='SUCCEEDED'
    assert not media.providers['test'].processes.snapshot() and not media.kernel.resources.snapshot()
    assert not (media.directory/'temp'/identifier).exists()
    assert media.models.get('fixture').health==ModelState.AVAILABLE
    assert media.agents.kernel is media.kernel
    assert media.kernel.registry.lookup('media.model.inspect.fixture')


def test_status_poll_never_scans_slow_path_and_explicit_probe_is_cached(media):
    with patch('morice.media_lab.runtime.shutil.which', side_effect=AssertionError('Status must not scan PATH')):
        assert media.status()['diagnostics']['encoder_probe']=='NOT_CHECKED'
    with patch('morice.media_lab.runtime.shutil.which', side_effect=lambda name:'CONTROLLED-'+name) as probe:
        actual=media.probe_encoder_tools();assert probe.call_count==2
    with patch('morice.media_lab.runtime.shutil.which', side_effect=AssertionError('Use the diagnostic cache')):
        diagnostics=media.status()['diagnostics']
        assert diagnostics['encoder_probe']=='CHECKED' and diagnostics['ffmpeg']==actual['ffmpeg']


@pytest.mark.parametrize('prompt',['crash','oom','wrong-size','corrupt'])
def test_failures_never_publish_success_and_next_job_recovers(media,prompt):
    identifier,result=run(media,prompt)
    assert not result.success and media.result(identifier)['status']=='FAILED'
    assert not (media.directory/'outputs'/identifier).exists()
    assert not media.kernel.resources.snapshot() and not media.providers['test'].processes.snapshot()
    assert run(media)[1].success


def test_cancel_running_reaps_owned_process_and_cleans_partial(media):
    identifier,future=media.submit(request('slow'))
    wait_until(lambda:media.providers['test'].processes.snapshot())
    started=time.perf_counter();assert media.cancel(identifier)
    result=future.result(timeout=5)
    assert result.status.value=='cancelled' and time.perf_counter()-started<3
    assert media.result(identifier)['status']=='CANCELLED'
    assert not media.providers['test'].processes.snapshot() and not media.kernel.resources.snapshot()
    assert not (media.directory/'temp'/identifier).exists()


def test_host_ram_margin_stops_fixture_and_reaps_without_publishing_output(media):
    provider=media.providers['test'];provider.host_available_mb=1024
    identifier,result=run(media,'slow')
    assert not result.success and 'Host RAM safety margin' in result.errors[0].detail
    assert media.result(identifier)['status']=='FAILED'
    assert not (media.directory/'outputs'/identifier).exists()
    assert not provider.processes.snapshot() and not media.kernel.resources.snapshot()


def test_ram_guard_measures_windows_launcher_descendants(media):
    provider=media.providers['test']
    original=provider.processes.run
    def bounded(*args,**kwargs):return original(*args,**kwargs,ram_limit_mb=48)
    with patch.object(provider.processes,'run',side_effect=bounded):
        identifier,result=run(media,'ram')
    assert not result.success
    assert 'RAM budget' in result.errors[0].detail
    assert not provider.processes.snapshot() and not media.kernel.resources.snapshot()
    assert media.result(identifier)['status']=='FAILED'


def test_authorized_oom_retries_once_with_actual_smaller_artifact(media):
    identifier,future=media.submit(ImageRequest('oom-fallback',model_id='fixture',width=128,height=128,allow_fallback=True))
    result=future.result(timeout=12)
    assert result.success
    record=media.result(identifier)
    assert record['request']['width']==128 and record['settings']['width']==96
    assert media.artifact(identifier)['width']==96 and record['warnings']
    assert any(p['status']=='OOM' for p in media.profiles)
    assert not media.kernel.resources.snapshot()


def test_gpu_wait_does_not_occupy_shared_workers_and_fast_action_runs(media):
    resources=media.kernel.resources
    assert resources.acquire('active-chat',(ResourceClaim('LOCAL_MODEL'),ResourceClaim('GPU',exclusive=True)))
    try:
        identifier,future=media.submit(request())
        wait_until(lambda:media.result(identifier)['status']=='WAITING_FOR_RESOURCES')
        assert not future.done() and not media.providers['test'].processes.snapshot()
        from morice.kernel.adapters import register_echo
        register_echo(media.kernel);started=time.perf_counter()
        assert media.kernel.dispatch('kernel.echo',{'value':3}).success
        assert time.perf_counter()-started<.2
        assert media.agents.workers._active==0
    finally:resources.release('active-chat')
    settled=future.result(timeout=10)
    assert settled.success, settled.errors


def test_queued_cancel_and_bounded_global_queue(media):
    assert media.kernel.resources.acquire('active-chat',(ResourceClaim('GPU',exclusive=True),))
    try:
        media.kernel.scheduler.max_deferred=2
        a,fa=media.submit(request());b,fb=media.submit(request('other'))
        with pytest.raises(ValueError,match='queue'):media.submit(request('third'))
        assert media.cancel(a) and media.cancel(b)
        assert fa.result(timeout=3).status.value=='cancelled' and fb.result(timeout=3).status.value=='cancelled'
    finally:media.kernel.resources.release('active-chat')


def test_queue_priority_and_aging(media):
    assert media.kernel.resources.acquire('block',(ResourceClaim('GPU',exclusive=True),))
    events=[];subscription=media.kernel.events.subscribe(lambda e:events.append(e.task_id) if e.event_type==EventType.MEDIA_STARTED else None)
    scheduler=media.kernel.scheduler
    admit=threading.Event();drive=scheduler._drive_deferred
    def after_both_are_queued():
        if not admit.wait(30):raise AssertionError('Queue fixture was not released.')
        drive()
    try:
        # Compare equal-age requests in one actual admission pass. A fixed
        # sleep can release the GPU during a stale pass, and slow submission
        # can legitimately age background work ahead of a newer preview.
        queued_at=time.monotonic()
        with patch.object(scheduler,'_drive_deferred',after_both_are_queued):
            with patch('morice.kernel.scheduler.time',SimpleNamespace(monotonic=lambda:queued_at,time=time.time)):
                background,fb=media.submit(request('background'),priority=Priority.BACKGROUND)
                interactive,fi=media.submit(request('preview'),priority=Priority.INTERACTIVE)
            media.kernel.resources.release('block');admit.set()
            assert fi.result(timeout=10).success and fb.result(timeout=10).success
            assert events[:2]==[interactive,background]
    finally:admit.set();media.kernel.resources.release('block');media.kernel.events.unsubscribe(subscription)


def test_model_corruption_and_unsafe_files_rejected(media):
    model=media.models.get('fixture');path=Path(model.model_path)/'fixture.safetensors'
    path.write_bytes(b'broken')
    assert media.inspect_model('fixture').health==ModelState.FAILED_HEALTH
    with pytest.raises(ValueError,match='health'):media.submit(request())


def test_hash_change_after_inspection_fails_without_generation(media):
    path=Path(media.models.get('fixture').model_path)/'fixture.safetensors'
    data=path.read_bytes();path.write_bytes(data[:-1]+b'X')
    identifier,result=run(media)
    assert not result.success and 'changed' in result.errors[0].detail.lower()
    assert not media.providers['test'].processes.snapshot()


def test_no_weights_in_source_or_model_deletion(media):
    with pytest.raises(ValueError,match='outside'):media.models.register(replace(media.models.get('fixture'),model_path=str(Path(__file__).parent)))
    path=Path(media.models.get('fixture').model_path)/'fixture.safetensors'
    sha=file_hash(path);run(media,'oom')
    assert path.exists() and file_hash(path)==sha


@pytest.mark.parametrize('workflow',[
    {'1':{'class_type':'ExecutePython','inputs':{'code':'bad'}}},
    {'1':{'class_type':'LoadImage','inputs':{'image':'../../outside.png'}}},
    {'1':{'class_type':'KSampler','inputs':{'model':['missing',0]}}},
    {'1':{'class_type':'KSampler','inputs':{'model':['1',0]}}},
])
def test_invalid_and_custom_workflows_rejected(workflow):
    with pytest.raises(ValueError):validate_workflow(workflow)


def test_comfy_remote_url_requires_mesh():
    with pytest.raises(ValueError,match='Mesh'):ComfyUIProvider('http://192.168.1.4:8188',dedicated=True)
    assert not ComfyUIProvider('http://127.0.0.1:8188').health()['available']


def test_physical_memory_change_refuses_before_load(media):
    media._hardware_probe=lambda:hardware(free_vram_mb=100)
    identifier,result=run(media)
    assert not result.success and not media.providers['test'].processes.snapshot()
    assert media.result(identifier)['status']=='FAILED'


def test_idle_owned_model_can_be_released_before_final_ram_measurement(media):
    model=media.models.get('fixture');low=hardware(ram_available_mb=1024)
    assert media.planner.plan(model,request(),low).decision=='UNSUPPORTED'
    assert media.planner.plan(model,request(),low,allow_unload=True).decision=='UNLOAD_IDLE_MODEL_THEN_RUN'


def test_restart_temp_cleanup_requires_dead_owned_pid_identity(media):
    import os,psutil
    from morice.media_lab.process import recover_owned_temp
    dead='d'*32;live='e'*32;unknown='f'*32
    for identifier in (dead,live,unknown):
        path=media.directory/'temp'/identifier;path.mkdir();(path/'partial.png').write_bytes(b'partial')
        media.history_store.save(identifier,{'generation_id':identifier,'status':'INTERRUPTED'})
    atomic_json(media.directory/'temp'/dead/'worker-owner.json',{'schema':1,'generation_id':dead,'processes':[{'pid':os.getpid(),'created_at':0}]}) # same PID reused: original identity is gone
    atomic_json(media.directory/'temp'/live/'worker-owner.json',{'schema':1,'generation_id':live,'processes':[{'pid':os.getpid(),'created_at':psutil.Process().create_time()}]})
    result=recover_owned_temp(media.directory/'temp',media.history_store)
    assert result['removed']==[dead] and set(result['quarantined'])=={live,unknown}
    assert (media.directory/'temp'/live).exists() and (media.directory/'temp'/unknown).exists()


def test_maximum_that_fits_requires_actual_current_profile(media):
    planner=media.planner;model=media.models.get('fixture');r=request(quality=Quality.MAXIMUM_THAT_FITS)
    assert planner.plan(model,r,hardware()).decision=='UNSUPPORTED'
    profile={'model_hash':model.sha256,'hardware_fingerprint':hardware().fingerprint,'backend_version':'v1','status':'SUCCEEDED','peak_vram_mb':128,'peak_ram_mb':128,'settings':{'width':64,'height':64,'steps':2,'intent':'TEXT_TO_IMAGE'},'mode':'direct'}
    assert planner.plan(model,r,hardware(),profiles=[profile],backend_version='v1').decision=='RUN_DIRECT'
    assert planner.plan(model,r,hardware(driver='new'),profiles=[profile],backend_version='v1').decision=='UNSUPPORTED'


def test_oversized_request_reduces_only_with_user_policy(media):
    model=replace(media.models.get('fixture'),estimated_vram_mb=5000,estimated_ram_mb=128,supports_cpu_offload=False,supports_low_vram=False)
    planner=MediaResourcePlanner(MediaSettings(max_resolution=1024));r=replace(request(),width=1024,height=1024,allow_fallback=True)
    plan=planner.plan(model,r,hardware());assert plan.decision=='REDUCE_RESOLUTION' and plan.request['width']<1024
    assert planner.plan(model,replace(r,allow_fallback=False),hardware()).decision=='UNSUPPORTED'


def test_reference_permissions_and_no_scan_of_library(media,tmp_path):
    reference=tmp_path/'ref.png';Image.new('RGB',(64,64),(80,120,30)).save(reference)
    r=request(intent='IMAGE_TO_IMAGE',reference_images=(str(reference),))
    identifier,future=media.submit(r);assert not future.result(timeout=5).success
    identifier,future=media.submit(r,ExecutionContext(active_files=(str(reference),)))
    assert future.result(timeout=10).success
    media.kernel.permissions.controller.set_state('file_read',PermissionState.DENIED)
    identifier,future=media.submit(r,ExecutionContext(active_files=(str(reference),)))
    assert not future.result(timeout=5).success


def test_reproducibility_batch_selection_and_no_overwrite(media,tmp_path):
    a,ra=run(media,count=2,seed=100);b,rb=run(media,count=2,seed=100)
    assert ra.success and rb.success
    assert [x['sha256'] for x in ra.artifacts]==[x['sha256'] for x in rb.artifacts]
    assert ra.artifacts[0]['sha256']!=ra.artifacts[1]['sha256']
    media.kernel.permissions.controller.set_state('file_write',PermissionState.GRANTED)
    destination=tmp_path/'chosen.png'
    assert media.export(a,destination,index=1).success
    assert not media.export(a,destination,index=0).success
    assert file_hash(destination)==ra.artifacts[1]['sha256']


def test_corrupt_and_constant_images_never_verify(tmp_path):
    p=tmp_path/'black.png';Image.new('RGB',(64,64)).save(p)
    with pytest.raises(ValueError,match='constant'):verify_image(p,64,64)
    assert verify_image(p,64,64,allow_constant=True)['decoded']
    p.write_bytes(b'partial')
    with pytest.raises(Exception):verify_image(p)


def test_controlled_video_decodes_and_static_motion_is_rejected(media,tmp_path):
    base=media.models.get('fixture')
    model=VideoModelDescriptor(**{k:v for k,v in base.__dict__.items() if k!='capabilities'},capabilities=('IMAGE_TO_VIDEO',))
    model=replace(model,model_id='video-fixture');media.models.register(model);media.inspect_model(model.model_id)
    source=tmp_path/'key.png';Image.new('RGB',(64,64),(20,70,90)).save(source)
    r=VideoRequest('controlled motion',model.model_id,reference_images=(str(source),),width=64,height=64,frames=8,fps=8,output_format='GIF',motion='move')
    identifier,future=media.submit(r,ExecutionContext(active_files=(str(source),)));result=future.result(timeout=12)
    assert result.success and result.artifacts[0]['decoded'] and result.artifacts[0]['frames']==8
    assert not media.providers['test'].processes.snapshot()


def test_restart_preserves_completed_and_never_replays_interrupted(media):
    identifier,result=run(media);media.history_store.save('interrupted',{'status':'GENERATING','request':request().to_dict(),'generation_id':'interrupted'})
    store=MediaHistory(media.directory/'metadata')
    assert store.get(identifier)['status']=='SUCCEEDED' and store.get('interrupted')['status']=='INTERRUPTED'
    assert not media.providers['test'].processes.snapshot()


def test_history_bound_and_temp_cleanup(media):
    media.history_store.max_history=3
    for i in range(8):assert run(media,prompt='small '+str(i))[1].success
    assert len(media.history(100))==3 and not list((media.directory/'temp').iterdir())


def test_lazy_registration_no_heavy_import_or_subprocess():
    kernel=CapabilityKernel()
    from morice.media_lab.capabilities import register_media_capabilities
    with patch('subprocess.Popen') as process:
        register_media_capabilities(kernel,lambda:(_ for _ in ()).throw(AssertionError('eager initialization')))
        process.assert_not_called()
    assert kernel.registry.lookup('media.image.generate') and 'torch' not in sys.modules and 'diffusers' not in sys.modules
    kernel.shutdown()


def test_benchmark_uses_shared_queue_and_records_factual_profiles(media):
    result=media.kernel.dispatch('media.model.benchmark',{'model_ids':['fixture'],'resolutions':[64,128],'modes':['direct']})
    assert result.success
    wait_until(lambda:getattr(media,'_benchmark_active',None) is None,timeout=15)
    payload=json.loads(Path(result.output['json_path']).read_text())
    assert payload['status']=='COMPLETED' and len(payload['rows'])==2 and all(row['status']=='SUCCEEDED' for row in payload['rows'])
    assert all(row['peak_vram_mb']==0 for row in payload['rows']) # fixture, not a GPU benchmark
    assert not media.kernel.resources.snapshot()


def test_contact_sheet_and_cache_clear_preserve_outputs_and_foreign_files(media):
    a,result=run(media);assert result.success
    b,result=run(media,seed=17);assert result.success
    preview=media.contact_sheet([a,b]);assert preview.success
    assert verify_image(preview.output['path'])['sha256']==preview.output['sha256']
    assert media.storage_stats()['outputs']['files']>=4
    foreign=media.directory/'cache'/'user.png';foreign.write_bytes(b'user-owned')
    assert media.clear_derived_cache().success
    assert not Path(preview.output['path']).exists() and foreign.read_bytes()==b'user-owned'
    assert media.artifact(a)['decoded'] and media.artifact(b)['decoded']


def test_retained_cleanup_never_silently_releases_resource():
    kernel=CapabilityKernel();resources=kernel.resources
    assert resources.acquire('owned',(ResourceClaim('FOREGROUND_UI'),))
    resources.retain('owned','Unconfirmed physical cleanup.');resources.release('owned')
    assert resources.snapshot() and not resources.acquire('next',(ResourceClaim('FOREGROUND_UI'),))
    resources.confirm_cleanup('owned');assert not resources.snapshot();kernel.shutdown()


def test_no_unsafe_generation_identifier(media):
    result=media.kernel.dispatch('media.image.generate',{'request':request().to_dict(),'generation_id':'../../escape'})
    assert not result.success and not media.providers['test'].processes.snapshot()


def test_explicit_remote_pin_never_falls_back(media):
    with pytest.raises(ValueError,match='pinning'):media.submit(replace(request(),node_id='absent-peer'))


def test_unimplemented_upscale_not_advertised(media):
    media._refresh_capabilities()
    assert media.kernel.registry.health('media.image.upscale').status.value=='unavailable'
    with pytest.raises(ValueError,match='implement'):media.submit(request(intent='UPSCALE'))
