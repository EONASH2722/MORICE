"""WGS84 GeographicLib calculations; no Qt, language model or geocoder."""
from __future__ import annotations

import math
from geographiclib.geodesic import Geodesic
from .contracts import Coordinate, UNITS

EARTH = Geodesic.WGS84
SPHERE_RADIUS_M = 6371008.8


def convert(metres, unit):
    if unit not in UNITS or not math.isfinite(metres):
        raise ValueError('Choose m, km, miles or nautical miles for a finite distance.')
    return metres / UNITS[unit]


def sphere_distance(a: Coordinate, b: Coordinate):
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    delta_lat = lat2 - lat1; delta_lon = math.radians(b.longitude - a.longitude)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * SPHERE_RADIUS_M * math.asin(math.sqrt(max(0, min(1, value))))


def ecef(point: Coordinate):
    lat, lon = math.radians(point.latitude), math.radians(point.longitude)
    eccentricity = EARTH.f * (2 - EARTH.f)
    normal = EARTH.a / math.sqrt(1 - eccentricity * math.sin(lat) ** 2)
    height = point.altitude or 0
    return ((normal + height) * math.cos(lat) * math.cos(lon),
        (normal + height) * math.cos(lat) * math.sin(lon),
        (normal * (1 - eccentricity) + height) * math.sin(lat))


def distance(a: Coordinate, b: Coordinate, *, mode='GEODESIC', unit='km', earth_model='WGS84', samples=129):
    if mode not in {'GEODESIC', 'CHORD'}:
        raise ValueError('ROUTE DISTANCE is unavailable: configure a real routing provider. Geodesic is not a driving route.')
    if earth_model not in {'WGS84', 'SPHERE'} or type(samples) is not int or not 2 <= samples <= 513:
        raise ValueError('Invalid Earth model or path sampling budget.')
    inverse = EARTH.Inverse(a.latitude, a.longitude, b.latitude, b.longitude)
    if mode == 'CHORD':
        first, second = ecef(a), ecef(b)
        metres = math.sqrt(sum((x - y) ** 2 for x, y in zip(first, second)))
        path = [a.to_dict(), b.to_dict()]
        model = 'WGS84 ECEF chord; supplied altitude, otherwise ellipsoid surface'
    else:
        geod = EARTH if earth_model == 'WGS84' else Geodesic(SPHERE_RADIUS_M, 0)
        inverse = geod.Inverse(a.latitude, a.longitude, b.latitude, b.longitude)
        metres = inverse['s12']
        line = geod.InverseLine(a.latitude, a.longitude, b.latitude, b.longitude)
        path = []
        for i in range(samples):
            value = line.Position(metres * i / (samples - 1))
            path.append(Coordinate(value['lat2'], value['lon2']).to_dict())
        # Preserve exact input endpoints instead of floating-point round-off.
        path[0], path[-1] = a.to_dict(), b.to_dict()
        model = 'WGS84 ellipsoid' if earth_model == 'WGS84' else 'Mean-radius sphere approximation'
    if not math.isfinite(metres) or metres < 0 or any(not math.isfinite(p[key]) for p in path for key in ('latitude', 'longitude')):
        raise ValueError('Geographic result failed finite-value verification.')
    return {'schema': 1, 'mode': mode, 'earth_model': model, 'metres': metres,
        'distance': convert(metres, unit), 'unit': unit,
        'initial_bearing': inverse['azi1'] % 360 if metres > 1e-8 else None,
        'final_bearing': inverse['azi2'] % 360 if metres > 1e-8 else None,
        'path': path, 'provenance': 'COMPUTED', 'algorithm': 'WGS84 ECEF Euclidean chord' if mode == 'CHORD' else 'GeographicLib WGS84' if earth_model == 'WGS84' else 'GeographicLib sphere',
        'bearing_reference': 'Shortest surface direction on the selected reference ellipsoid/sphere',
        'altitude_note': 'Surface geodesic ignores altitude.' if mode == 'GEODESIC' else 'No terrain elevation is inferred.'}


def path_distance(points, *, mode='GEODESIC', unit='km'):
    if not 2 <= len(points) <= 64:
        raise ValueError('A path needs 2–64 supplied points.')
    legs = [distance(a, b, mode=mode, unit=unit) for a, b in zip(points, points[1:])]
    total = sum(leg['metres'] for leg in legs)
    return {'schema': 1, 'legs': legs, 'metres': total, 'distance': convert(total, unit), 'unit': unit,
        'mode': mode, 'path': [point for leg in legs for point in leg['path']], 'provenance': 'COMPUTED'}


def radius(center, metres, *, samples=73):
    if type(metres) not in (float, int) or not math.isfinite(metres) or not 0 < metres <= 10000000:
        raise ValueError('Radius must be finite and within 0…10,000 km.')
    if type(samples) is not int or not 9 <= samples <= 361:
        raise ValueError('Radius geometry exceeds its sample budget.')
    points = []
    for i in range(samples):
        value = EARTH.Direct(center.latitude, center.longitude, 360 * i / (samples - 1), metres)
        points.append(Coordinate(value['lat2'], value['lon2']).to_dict())
    return {'schema': 1, 'center': center.to_dict(), 'radius_metres': metres, 'path': points, 'earth_model': 'WGS84 ellipsoid', 'provenance': 'COMPUTED'}


def area(points):
    if not 3 <= len(points) <= 256:
        raise ValueError('A geodesic polygon needs 3–256 supplied points.')
    polygon = EARTH.Polygon()
    for point in points:
        polygon.AddPoint(point.latitude, point.longitude)
    count, perimeter, signed = polygon.Compute(False, True)
    return {'schema': 1, 'vertices': count, 'square_metres': abs(signed), 'signed_square_metres': signed,
        'perimeter_metres': perimeter, 'earth_model': 'WGS84 ellipsoid', 'provenance': 'COMPUTED'}
