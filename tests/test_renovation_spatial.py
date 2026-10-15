"""Deterministic domain/provider edge cases, independently verified by Kernel."""
import math
from pathlib import Path

import pytest

from morice.kernel import CapabilityKernel, VerificationStatus
from morice.spatial import Coordinate, SpatialService
from morice.spatial.calculations import area, distance, ecef, path_distance, radius, sphere_distance
from morice.spatial.locations import LocalGazetteer


@pytest.fixture
def service():
    kernel = CapabilityKernel(); value = SpatialService(kernel)
    yield value
    kernel.shutdown()
    assert not kernel.resources.snapshot()


@pytest.mark.parametrize('lat,lon', [(91, 0), (-91, 0), (math.nan, 0), (0, math.inf), (True, 0), (0, 1000001)])
def test_invalid_coordinates_fail(lat, lon):
    with pytest.raises(ValueError): Coordinate(lat, lon)


def test_longitude_normalization_altitude_and_no_terrain_guess():
    assert Coordinate(0, 180).longitude == -180
    assert Coordinate(0, 540).longitude == -180
    assert Coordinate(0, 0).altitude is None
    assert distance(Coordinate(0, 0, 1000), Coordinate(0, 0, 2000), mode='CHORD')['metres'] == pytest.approx(1000)
    with pytest.raises(ValueError): Coordinate(0, 0, math.nan)


@pytest.mark.parametrize('a,b', [(Coordinate(0, 0), Coordinate(0, 0)), (Coordinate(0, 0), Coordinate(0, 180)),
    (Coordinate(89.999, 1), Coordinate(-89.999, 179.999)), (Coordinate(90, 0), Coordinate(-90, 0)),
    (Coordinate(0, 179.9), Coordinate(0, -179.9)), (Coordinate(-41.32, 174.81), Coordinate(40.96, -5.50))])
def test_geodesic_edge_cases_with_second_sphere_formula(a, b):
    result = distance(a, b)
    assert result['metres'] >= 0 and math.isfinite(result['metres'])
    assert result['path'][0] == a.to_dict() and result['path'][-1] == b.to_dict()
    # Independent haversine is a sphere reference, not ellipsoidal accuracy.
    sphere = distance(a, b, earth_model='SPHERE')['metres']
    assert sphere == pytest.approx(sphere_distance(a, b), abs=.2)
    assert abs(result['metres'] - sphere) <= max(1, sphere * .006)


def test_reference_distance_and_equator_chord_crosscheck():
    result = distance(Coordinate(-41.32, 174.81), Coordinate(40.96, -5.50))
    assert result['metres'] == pytest.approx(19959679.267, abs=.001)
    result = distance(Coordinate(0, 0), Coordinate(0, 60), mode='CHORD')
    assert result['metres'] == pytest.approx(2 * 6378137 * math.sin(math.pi / 6), abs=1e-5)
    assert result['metres'] < distance(Coordinate(0, 0), Coordinate(0, 60))['metres']


@pytest.mark.parametrize('unit,factor', [('m', 1), ('km', 1000), ('miles', 1609.344), ('nautical miles', 1852)])
def test_deterministic_units_and_bearings(unit, factor):
    result = distance(Coordinate(0, 0), Coordinate(0, 1), unit=unit)
    assert result['distance'] * factor == pytest.approx(result['metres'])
    assert result['initial_bearing'] == pytest.approx(90)
    assert result['final_bearing'] == pytest.approx(90)


def test_route_is_never_a_geodesic_alias():
    with pytest.raises(ValueError, match='ROUTE DISTANCE is unavailable'):
        distance(Coordinate(0, 0), Coordinate(1, 1), mode='ROUTE')


def test_bounded_multi_point_radius_polygon_area():
    points = [Coordinate(0, 0), Coordinate(0, 1), Coordinate(1, 1)]
    value = path_distance(points)
    assert len(value['legs']) == 2 and value['metres'] == sum(leg['metres'] for leg in value['legs'])
    circle = radius(points[0], 100000)
    assert len(circle['path']) == 73
    for point in circle['path']:
        assert distance(points[0], Coordinate.from_dict(point), samples=2)['metres'] == pytest.approx(100000, abs=.001)
    assert area(points)['square_metres'] > 0
    with pytest.raises(ValueError): path_distance([points[0]] * 65)


def test_shared_kernel_distance_independent_verification(service):
    result = service.kernel.dispatch('spatial.distance.calculate', {'origin': {'latitude': 0, 'longitude': 0}, 'destination': {'latitude': 0, 'longitude': 180}})
    assert result.success and result.verification.status == VerificationStatus.VERIFIED
    result.output['metres'] += 100
    assert service.verify('spatial.distance.calculate', result, None).status == VerificationStatus.FAILED


def test_real_offline_provider_and_ambiguity(service):
    chennai = service.gazetteer.resolve('Chennai')
    assert chennai['status'] == 'RESOLVED' and chennai['candidates'][0]['source'].startswith('https://www.geonames.org/')
    assert service.gazetteer.resolve('Springfield')['status'] == 'AMBIGUOUS'
    assert service.gazetteer.resolve('Los Angeles')['status'] == 'AMBIGUOUS'
    assert service.gazetteer.resolve('A city deliberately not in the geographic extract')['status'] == 'NOT_FOUND'


def test_geocoder_unavailable_offline_coordinates_still_work(tmp_path):
    provider = LocalGazetteer(tmp_path / 'missing.sqlite3')
    with pytest.raises(ValueError, match='unavailable'): provider.resolve('Chennai')
    assert distance(Coordinate(0, 0), Coordinate(0, 1))['metres'] > 0


def test_context_followups_resolve_candidates_and_preserve_origin(service):
    assert service.handle_text('Show Earth.')['open_spatial']
    result = service.handle_text('Show Chennai and Los Angeles.')
    assert result['context']['pending'] and result['context']['result'] is None
    pending = result['context']['pending'][0]
    chosen = next(candidate for candidate in pending['candidates'] if candidate['country'] == 'US' and candidate['region'] == 'CA')
    service.choose_candidate('destination', chosen['identifier'])
    result = service.handle_text("What's the distance as the crow flies?")
    metres = result['context']['result']['metres']; origin = result['context']['origin']
    assert result['context']['result']['mode'] == 'GEODESIC'
    assert service.handle_text('Give it to me in miles.')['context']['result']['distance'] == pytest.approx(metres / 1609.344)
    assert service.handle_text('Show the straight-line distance too.')['context']['result']['metres'] < metres
    updated = service.handle_text('What about New York instead?')['context']
    assert updated['origin'] == origin and updated['destination']['country'] == 'US'
    assert updated['destination']['identifier'] != chosen['identifier']
    assert service.handle_text('Show 2D map.')['context']['markers'] == updated['markers']


def test_bad_pair_preserves_context_and_unknown_candidate_rejected(service):
    service.set_pair('Chennai', 'New York')
    before = service.snapshot()
    with pytest.raises(ValueError): service.set_pair('New York', 'Missing city 123456')
    assert service.snapshot() == before
    with pytest.raises(ValueError): service.choose_candidate('destination', 'geonames:123')


def test_snapshot_cannot_mutate_domain_context(service):
    service.set_pair('Chennai', 'New York')
    value = service.snapshot(); value['result']['metres'] = -1
    assert service.snapshot()['result']['metres'] > 0


def test_recognized_punctuation_and_followup_mode_are_preserved(service):
    service.handle_text("show chennai and los angeles'")
    candidate = next(c for c in service.snapshot()['pending'][0]['candidates'] if c['country'] == 'US')
    service.choose_candidate('destination', candidate['identifier'])
    assert service.handle_text('what is the distance as the crow flies')['context']['result']['mode'] == 'GEODESIC'
    assert service.handle_text('show the straight line distance to')['context']['result']['mode'] == 'CHORD'
    assert service.handle_text('show the path')['context']['result']['mode'] == 'CHORD'


def test_clicked_coordinates_enter_domain_context_for_followups(service):
    assert service.select_measurement_point(Coordinate(0, 0).to_dict())['destination'] is None
    context = service.select_measurement_point(Coordinate(0, 1).to_dict())
    assert context['result']['metres'] == pytest.approx(111319.490793, abs=.00001)
    assert service.handle_text('in miles')['context']['result']['unit'] == 'miles'


def test_advanced_marker_measurements_use_shared_kernel_and_preserve_pair_preferences(service):
    identifiers = []
    for latitude, longitude in ((0,0),(0,1),(1,1)):
        result = service.kernel.dispatch('spatial.marker.add', {'coordinate':Coordinate(latitude,longitude).to_dict(),'label':'Supplied test coordinate'})
        assert result.success and result.verification.status.value == 'verified'
        identifiers.append(result.output['marker']['identifier'])
    measured = service.measure_selection('area', identifiers)['result']
    # A small equatorial one-degree right triangle has about half a
    # 111 km × 111 km cell's area; tolerate ellipsoid curvature in this
    # independent geometric scale check.
    assert 6e9 < measured['square_metres'] < 6.3e9 and measured['path']
    path = service.measure_selection('path', identifiers)['result']
    assert path['metres'] == pytest.approx(221893.879351, abs=.01)
    circle = service.measure_selection('radius', identifiers[:1], metres=1000)['result']
    assert circle['radius_metres'] == 1000 and len(circle['path']) == 73
    assert service.snapshot()['unit'] == 'km' and service.snapshot()['mode'] == 'GEODESIC'
    with pytest.raises(ValueError): service.measure_selection('radius', identifiers, metres=1000)
    removed = service.kernel.dispatch('spatial.marker.remove', {'marker_id':identifiers[-1]})
    assert removed.success and removed.output['removed'] and service.snapshot()['result'] is None
