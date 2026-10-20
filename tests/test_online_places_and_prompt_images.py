"""Online places and reference-free images use the existing authorities."""
import json
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

import pytest

from morice.kernel import CapabilityKernel
from morice.unified_intelligence import PermissionState
from morice.spatial import SpatialService
from morice.spatial.online import OnlineGeocoder


def place(name, identifier, longitude, latitude, country='IN', kind='city'):
    return {'type':'Feature','geometry':{'type':'Point','coordinates':[longitude,latitude]},
        'properties':{'name':name,'osm_type':'N','osm_id':identifier,'osm_key':'place','osm_value':kind,'countrycode':country}}


class Response:
    def __init__(self, url, features): self.url=url; self.data=json.dumps({'features':features}).encode()
    def __enter__(self): return self
    def __exit__(self,*args): OnlineGeocoder._last_request=0
    def geturl(self): return self.url
    def read(self, size): return self.data[:size]


@pytest.fixture
def online(tmp_path):
    requests=[]
    rows={'Mumbai':[place('Mumbai',1,72.8692035,19.054999)],
        'Gujarat':[place('Gujarat',2,71.745261,22.3850051,kind='state')],
        'Gujrat':[place('Gujrat',3,74.071481,32.5686782,'PK')],
        'Pakistan':[place('Pakistan',4,71.247499,30.3308401,'PK','country')]}
    def fetch(request, **kwargs):
        name=parse_qs(urlsplit(request.full_url).query)['q'][0]; requests.append(name)
        return Response(request.full_url, rows.get(name, []))
    OnlineGeocoder._last_request=0
    provider=OnlineGeocoder(tmp_path/'places.json',transport=fetch)
    kernel=CapabilityKernel();kernel.permissions.controller.set_state('network',PermissionState.GRANTED)
    service=SpatialService(kernel,online=provider)
    yield service,provider,requests
    kernel.shutdown(); assert not kernel.resources.snapshot()


@pytest.mark.parametrize('text,pair', [
    ('show mumbai and pakistan how far?',('mumbai','pakistan')),
    ('show mumbai and gujrat how far?',('mumbai','gujrat')),
    ('How far is it from Mumbai to Gujarat?',('Mumbai','Gujarat')),
    ("What's the distance between Mumbai and Gujarat?",('Mumbai','Gujarat')),
])
def test_pair_parser_strips_question_from_place(text,pair):
    assert SpatialService.parse_pair(text)==pair
    assert SpatialService.is_context_command(text)


def test_generic_locate_requests_stay_with_existing_chat_and_file_router():
    assert not SpatialService.is_context_command('locate my notes.txt')
    assert not SpatialService.is_context_command('locate Paris')
    assert SpatialService.is_context_command('find place Paris')


def test_online_cities_states_countries_and_repeated_cache(online):
    service,provider,requests=online
    result=service.handle_text('Show Mumbai and Gujarat how far?')['context']
    assert result['origin']['label']=='Mumbai' and result['destination']['kind']=='state'
    assert 350000<result['result']['metres']<420000
    assert result['result']['locations'][1]['source'].startswith('https://www.openstreetmap.org/')
    service.handle_text('Show Mumbai and Gujarat how far?')
    assert requests==['Mumbai','Gujarat']
    result=service.handle_text('Show Mumbai and Pakistan how far?')['context']
    assert result['destination']['kind']=='country' and result['destination']['country']=='PK'
    restored=OnlineGeocoder(provider.path,transport=Mock(side_effect=AssertionError('Cached lookup called internet')))
    assert restored.resolve('Pakistan')['cached'] and restored.get('osm:node:4').label=='Pakistan'


def test_healthy_slower_provider_does_not_force_wrong_offline_place(online):
    service,provider,requests=online
    original=provider.transport
    def slower(request,**kwargs):
        if kwargs['timeout']<7.5:raise TimeoutError('Controlled healthy provider needs 7.5 seconds')
        return original(request,**kwargs)
    provider.transport=slower
    result=service.handle_text('Show Mumbai and Gujrat how far?')['context']
    assert result['origin']['identifier'].startswith('osm:')
    assert {v['kind'] for v in result['pending'][0]['candidates']}=={'city','state'}


def test_gujrat_shows_indian_state_and_pakistani_city_without_guessing(online):
    service,provider,requests=online
    result=service.handle_text('Show Mumbai and Gujrat how far?')['context']
    assert result['result'] is None
    candidates=result['pending'][0]['candidates']
    assert {(v['label'],v['kind'],v['country']) for v in candidates}=={('Gujrat','city','PK'),('Gujarat','state','IN')}
    result=service.choose_candidate('destination','osm:node:2')
    assert result['destination']['label']=='Gujarat' and result['result']['metres']>0


def test_same_named_city_and_state_require_explicit_choice(online):
    service,provider,requests=online
    provider.transport=lambda request,**kwargs:Response(request.full_url,[
        place('New York',5,-74.006,40.713,'US','city'),
        place('New York',6,-75.5,43.0,'US','state')])
    result=provider.resolve('New York',country='US')
    assert result['status']=='AMBIGUOUS'
    assert {v['kind'] for v in result['candidates']}=={'city','state'}


def test_online_denial_never_contacts_provider_and_falls_back_offline(online):
    service,provider,requests=online
    service.kernel.permissions.controller.set_state('network',PermissionState.DENIED)
    result=service.handle_text('Show Chennai and New York')['context']
    assert result['origin']['source'].startswith('https://www.geonames.org/') and not requests


def test_online_error_preserves_previous_result_and_exact_query(online):
    service,provider,requests=online
    service.set_pair('Chennai','New York'); before=service.snapshot()
    with pytest.raises(ValueError,match='No matching place found for Nowhere'):
        service.handle_text('Show Mumbai and Nowhere how far?')
    assert service.snapshot()==before and requests==['Mumbai','Nowhere']


def test_slow_network_does_not_hold_snapshot_lock(online):
    service,provider,requests=online
    started=threading.Event(); finish=threading.Event(); errors=[]
    original=provider.transport
    def slow(*args,**kwargs):
        started.set();finish.wait(2);return original(*args,**kwargs)
    provider.transport=slow
    def run():
        try:service.handle_text('Show Mumbai and Gujarat how far?')
        except Exception as exc:errors.append(exc)
    thread=threading.Thread(target=run);thread.start()
    try:
        assert started.wait(2)
        begin=time.monotonic();service.snapshot();elapsed=time.monotonic()-begin
        begin_busy=time.monotonic()
        with pytest.raises(ValueError,match='already running'):
            service.handle_text('Show Mumbai and Gujarat how far?')
        assert time.monotonic()-begin_busy<.1
    finally:
        finish.set();thread.join(5)
    assert elapsed<.1 and not thread.is_alive() and not errors


def test_online_busy_is_immediate_and_bad_coordinate_is_rejected(online):
    service,provider,requests=online
    OnlineGeocoder._requests.acquire()
    try:
        begin=time.monotonic()
        with pytest.raises(OSError,match='running'):provider.resolve('Mumbai')
        assert time.monotonic()-begin<.1
    finally:OnlineGeocoder._requests.release()
    provider.transport=lambda request,**kw:Response(request.full_url,[place('Wrong',10,10000000,10000000)])
    assert provider.resolve('Wrong')['status']=='NOT_FOUND'


# Keep each real Qt control test in an owned subprocess. A shared pytest
# QApplication can retain earlier widgets and stall a later global style change.
@pytest.mark.parametrize('case', ['test_prompt_only_image_creates_verified_artifact_without_references', 'test_discovered_model_is_inspected_on_generate_and_clear_resets_workflow', 'test_missing_model_reason_is_visible_not_reference_requirement', 'test_model_preparation_disables_repeat_submission_and_recovers_on_error', 'test_initial_model_selection_prefers_compatible_prompt_image_model'])
def test_prompt_image_native_case_in_owned_process(case):
    import subprocess,sys
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/run_isolated_tests.py'),
        str(root/'tests/media_prompt_cases.py')+'::'+case,'-q','-o','faulthandler_timeout=30'],
        cwd=root,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert '1 passed' in result.stdout,result.stdout+result.stderr
