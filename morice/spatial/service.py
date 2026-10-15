"""Stateful Spatial domain adapter; Kernel owns execution/permissions/verification."""
from __future__ import annotations

import copy
import math
import os
import re
import threading
import uuid

from ..kernel import (CapabilityDescriptor, ExecutionResult, ResourceClaim, ResourceDescriptor, TaskStatus,
    VerificationResult, VerificationStatus)
from . import calculations
from .contracts import Coordinate, Location, SpatialContext, UNITS
from .locations import LocalGazetteer


CAPABILITIES = {
    'spatial.location.resolve': 'Resolve geographic location',
    'spatial.distance.calculate': 'Calculate deterministic geographic distance',
    'spatial.bearing.calculate': 'Calculate geographic bearing',
    'spatial.path.calculate': 'Calculate multi-point geographic path',
    'spatial.area.calculate': 'Calculate geodesic polygon area',
    'spatial.radius.calculate': 'Calculate geodesic radius',
    'spatial.marker.add': 'Add supplied/provider geographic marker',
    'spatial.marker.remove': 'Remove geographic marker',
    'spatial.viewport.focus': 'Focus geographic viewport',
    'spatial.globe.show': 'Show interactive Earth',
    'spatial.map.show': 'Show geographic map',
}


def register_spatial_capabilities(kernel, get_service):
    for capability, title in CAPABILITIES.items():
        if kernel.registry.lookup(capability):
            continue
        computes = '.calculate' in capability
        kernel.registry.register(CapabilityDescriptor(capability, title, category='spatial', inline=True,
            supported_resources=(ResourceClaim('CPU'),) if computes else (), supports_cancellation=True,
            supports_verification=True, timeout=10),
            lambda args, ctx, cap=capability: get_service().execute(cap, args, ctx),
            verifier=lambda result, expected, ctx, cap=capability: get_service().verify(cap, result, ctx))


class SpatialService:
    def __init__(self, kernel, *, gazetteer=None, register=True):
        self.kernel = kernel
        self.gazetteer = gazetteer or LocalGazetteer()
        self.context = SpatialContext()
        self._measurement_next = 'origin'
        self._lock = threading.RLock()
        if kernel.resources.descriptor('CPU') is None:
            kernel.resources.register(ResourceDescriptor('CPU', max(1, min(2, os.cpu_count() or 1))))
        if register:
            register_spatial_capabilities(kernel, lambda: self)

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self.context.to_dict())

    @staticmethod
    def point(value):
        return value if isinstance(value, Coordinate) else Coordinate.from_dict(value)

    def execute(self, capability, args, context):
        if context.cancellation_token:
            context.cancellation_token.raise_if_cancelled()
        if capability == 'spatial.location.resolve':
            value = self.gazetteer.resolve(args['query'], country=args.get('country', ''), region=args.get('region', ''))
        elif capability in {'spatial.distance.calculate', 'spatial.bearing.calculate'}:
            first, second = self.point(args['origin']), self.point(args['destination'])
            value = calculations.distance(first, second, mode=args.get('mode', 'GEODESIC'),
                unit=args.get('unit', 'km'), earth_model=args.get('earth_model', 'WGS84'), samples=args.get('samples', 129))
            value.update(origin=first.to_dict(), destination=second.to_dict())
        elif capability == 'spatial.path.calculate':
            points = [self.point(point) for point in args['points']]
            value = calculations.path_distance(points, mode=args.get('mode', 'GEODESIC'), unit=args.get('unit', 'km'))
            value['points'] = [point.to_dict() for point in points]
        elif capability == 'spatial.area.calculate':
            points = [self.point(point) for point in args['points']]
            value = calculations.area(points); value['points'] = [point.to_dict() for point in points]
        elif capability == 'spatial.radius.calculate':
            value = calculations.radius(self.point(args['center']), args['metres'])
        else:
            with self._lock:
                if capability == 'spatial.marker.add':
                    if len(self.context.markers) >= 128:
                        raise ValueError('Marker limit reached; remove a marker before adding more.')
                    if args.get('location_id'):
                        location = self.gazetteer.get(args['location_id'])
                    else:
                        label = str(args.get('label', 'Supplied coordinate')).strip()[:120]
                        location = Location('coordinate:' + uuid.uuid4().hex, label, self.point(args['coordinate']), 'USER_SUPPLIED')
                    self.context.markers[location.identifier] = location
                    self.context.selected_marker = location.identifier
                    value = {'schema': 1, 'marker': location.to_dict()}
                elif capability == 'spatial.marker.remove':
                    removed = self.context.markers.pop(str(args['marker_id']), None)
                    if removed is not None:
                        if self.context.origin == removed: self.context.origin = None
                        if self.context.destination == removed: self.context.destination = None
                        self.context.result = None
                    if self.context.selected_marker == args['marker_id']: self.context.selected_marker = ''
                    value = {'schema': 1, 'removed': removed is not None, 'marker_id': args['marker_id']}
                elif capability == 'spatial.viewport.focus':
                    if args.get('marker_id') not in self.context.markers:
                        raise ValueError('Select an actual marker before focusing.')
                    self.context.selected_marker = args['marker_id']
                    value = {'schema': 1, 'coordinate': self.context.markers[args['marker_id']].coordinate.to_dict()}
                elif capability in {'spatial.globe.show', 'spatial.map.show'}:
                    self.context.viewport = 'globe' if capability == 'spatial.globe.show' else 'map'
                    value = {'schema': 1, 'view': self.context.viewport}
                else:
                    raise ValueError('Unknown geographic capability.')
        return ExecutionResult(TaskStatus.SUCCEEDED, True, value, verification_required=True)

    def verify(self, capability, result, context):
        try:
            value = result.output
            if value.get('schema') != 1:
                raise ValueError('Unknown spatial result schema.')
            if capability == 'spatial.location.resolve':
                for candidate in value['candidates']:
                    assert self.gazetteer.get(candidate['identifier']).to_dict() == candidate
            elif capability in {'spatial.distance.calculate', 'spatial.bearing.calculate'}:
                first, second = self.point(value['origin']), self.point(value['destination'])
                model = 'SPHERE' if value['earth_model'].startswith('Mean-radius') else 'WGS84'
                assert 2 <= len(value['path']) <= 513
                observed = calculations.distance(first, second, mode=value['mode'], unit=value['unit'], earth_model=model, samples=len(value['path']))
                assert math.isfinite(value['metres']) and abs(value['metres'] - observed['metres']) < 1e-5
                assert abs(value['distance'] - calculations.convert(value['metres'], value['unit'])) < 1e-8
                assert len(value['path']) >= 2 and value['path'][0] == first.to_dict() and value['path'][-1] == second.to_dict()
                for point in value['path']: self.point(point)
                assert value['path'] == observed['path'], 'Route geometry does not match the deterministic geodesic/chord.'
            elif capability == 'spatial.path.calculate':
                observed = calculations.path_distance([self.point(p) for p in value['points']], mode=value['mode'], unit=value['unit'])
                assert abs(value['metres'] - observed['metres']) < 1e-5
                assert value['path'] == observed['path']
            elif capability == 'spatial.area.calculate':
                observed = calculations.area([self.point(p) for p in value['points']])
                assert abs(value['square_metres'] - observed['square_metres']) < 1e-3
            elif capability == 'spatial.radius.calculate':
                center = self.point(value['center'])
                for point in value['path']:
                    observed = calculations.distance(center, self.point(point), samples=2)['metres']
                    assert abs(observed - value['radius_metres']) < .01
            elif capability == 'spatial.marker.add':
                with self._lock:
                    assert self.context.markers[value['marker']['identifier']].to_dict() == value['marker']
            elif capability in {'spatial.globe.show', 'spatial.map.show'}:
                with self._lock:
                    assert self.context.viewport == value['view']
            elif capability == 'spatial.viewport.focus':
                with self._lock:
                    assert self.context.markers[self.context.selected_marker].coordinate.to_dict() == value['coordinate']
            return VerificationResult(VerificationStatus.VERIFIED, message='Geographic coordinates, provider identity and deterministic calculation verified.')
        except Exception as exc:
            return VerificationResult(VerificationStatus.FAILED, message=str(exc)[:300] or 'Spatial result failed independent verification.')

    def _dispatch(self, capability, inputs):
        result = self.kernel.dispatch(capability, inputs)
        if not result.success:
            raise ValueError('; '.join(error.message + (': ' + error.detail if error.detail else '') for error in result.errors))
        return result

    def _resolve_slot(self, query, slot):
        query = query.strip(' .?!\'"')
        fields = query.rsplit(',', 1)
        country = fields[-1].strip().upper() if len(fields) == 2 and len(fields[-1].strip()) == 2 else ''
        if country: query = fields[0].strip()
        result = self._dispatch('spatial.location.resolve', {'query': query, 'country': country}).output
        if result['status'] == 'NOT_FOUND':
            raise ValueError('Location not found in the installed city dataset: ' + query + '. Use an exact city name, country code, or supplied coordinates.')
        if result['status'] == 'AMBIGUOUS':
            self.context.pending.append({'slot': slot, **result})
            return None
        return self.gazetteer.get(result['candidates'][0]['identifier'])

    def choose_candidate(self, slot, identifier):
        with self._lock:
            pending = next((item for item in self.context.pending if item['slot'] == slot), None)
            if pending is None or identifier not in {candidate['identifier'] for candidate in pending['candidates']}:
                raise ValueError('Choose a candidate from the actual unresolved location list.')
            location = self.gazetteer.get(identifier)
            setattr(self.context, slot, location)
            self._remember(location)
            self.context.pending.remove(pending)
            if not self.context.pending and self.context.origin and self.context.destination:
                self.calculate_current()
            return self.snapshot()

    def set_pair(self, origin, destination):
        with self._lock:
            previous = copy.deepcopy(self.context)
            try:
                self.context.pending.clear(); self.context.result = None
                self.context.origin = self._resolve_slot(origin, 'origin')
                self.context.destination = self._resolve_slot(destination, 'destination')
                for location in (self.context.origin, self.context.destination):
                    if location is not None: self._remember(location)
                if not self.context.pending:
                    self.calculate_current()
            except Exception:
                self.context = previous
                raise
            return self.snapshot()

    def _remember(self, location):
        if location.identifier not in self.context.markers and len(self.context.markers) >= 128:
            raise ValueError('Marker limit reached; remove a marker before adding another location.')
        self.context.markers[location.identifier] = location

    def calculate_current(self):
        with self._lock:
            if self.context.pending:
                raise ValueError('Choose the ambiguous location before calculating.')
            if not self.context.origin or not self.context.destination:
                raise ValueError('Select an origin and destination first.')
            self.context.result = self._dispatch('spatial.distance.calculate', {
                'origin': self.context.origin.coordinate.to_dict(), 'destination': self.context.destination.coordinate.to_dict(),
                'mode': self.context.mode, 'unit': self.context.unit}).output
            self.context.result['locations'] = [self.context.origin.to_dict(), self.context.destination.to_dict()]
            return self.context.result

    def select_measurement_point(self, coordinate):
        """A projected click becomes supplied domain state through shared Kernel."""
        with self._lock:
            slot = self._measurement_next
            result = self._dispatch('spatial.marker.add', {'coordinate': coordinate, 'label': 'Point A' if slot == 'origin' else 'Point B'})
            location = self.context.markers[result.output['marker']['identifier']]
            self.context.pending.clear(); setattr(self.context, slot, location); self.context.result = None
            if slot == 'origin':
                self.context.destination = None; self._measurement_next = 'destination'
            else:
                self._measurement_next = 'origin'; self.calculate_current()
            return self.snapshot()

    def measure_selection(self, kind, marker_ids, *, metres=None):
        """Typed advanced measurements reuse existing registered capabilities."""
        with self._lock:
            locations = [self.context.markers[identifier] for identifier in marker_ids]
            points = [location.coordinate.to_dict() for location in locations]
            if kind == 'radius':
                if len(points) != 1: raise ValueError('Select exactly one marker for a radius.')
                result = self._dispatch('spatial.radius.calculate', {'center':points[0], 'metres':metres}).output
            elif kind == 'path':
                result = self._dispatch('spatial.path.calculate', {'points':points,'mode':self.context.mode,'unit':self.context.unit}).output
                result.update(earth_model='WGS84 ellipsoid' if self.context.mode == 'GEODESIC' else 'WGS84 ECEF chord', altitude_note='Surface paths ignore altitude.' if self.context.mode == 'GEODESIC' else 'Chord includes supplied altitude; no terrain elevation is inferred.')
            elif kind == 'area':
                if not 3 <= len(points) <= 63: raise ValueError('Select 3–63 markers in displayed polygon order.')
                result = self._dispatch('spatial.area.calculate', {'points':points}).output
                geometry = self._dispatch('spatial.path.calculate', {'points':points + [points[0]], 'mode':'GEODESIC','unit':'km'}).output
                result['path'] = geometry['path']
            else: raise ValueError('Unknown advanced measurement.')
            self.context.result = result
            return self.snapshot()

    def handle_text(self, text):
        """Deterministic context commands. None means the existing chat router owns it."""
        clean = ' '.join(str(text).strip().split())
        lower = clean.casefold().rstrip('.?!')
        with self._lock:
            if lower in {'show earth', 'open spatial lab', 'show globe', 'open globe'}:
                self._dispatch('spatial.globe.show', {})
                return {'message': 'Opening Spatial Lab.', 'open_spatial': True, 'context': self.snapshot()}
            if lower in {'show map', 'open map', '2d map', 'show 2d map'}:
                self._dispatch('spatial.map.show', {})
                return {'message': 'Showing the 2D map with the current markers and path.', 'open_spatial': True, 'context': self.snapshot()}
            pair = re.fullmatch(r'(?:show|compare|distance between) (.+?) (?:and|to) (.+)', clean, re.I)
            if pair:
                self.set_pair(pair[1], pair[2])
            elif (replacement := re.fullmatch(r'(?:what about|replace (?:it|the destination) with) (.+?)(?: instead)?[.?!]?', clean, re.I)):
                if not self.context.origin:
                    raise ValueError('Choose an origin before replacing the destination.')
                self.context.pending.clear(); self.context.result = None
                self.context.destination = self._resolve_slot(replacement[1], 'destination')
                if self.context.destination:
                    self._remember(self.context.destination)
                    self.calculate_current()
            elif lower in {'how far', "what's the distance as the crow flies", 'what is the distance as the crow flies', 'as the crow flies', 'what is the distance', 'show the path'}:
                if 'crow flies' in lower: self.context.mode = 'GEODESIC'
                self.calculate_current()
            elif lower in {'chord distance', 'straight line distance'} or re.fullmatch(r'show(?: the)? straight[- ]line distance(?: t(?:oo|o))?', lower):
                self.context.mode = 'CHORD'; self.calculate_current()
            elif lower in {'driving distance', 'walking distance', 'cycling distance', 'route distance'}:
                raise ValueError('ROUTE DISTANCE unavailable: no real routing provider is configured. Surface geodesic and chord are available.')
            elif lower in {'in miles', 'give it to me in miles', 'in km', 'in kilometres', 'in kilometers', 'in m', 'in metres', 'in meters', 'in nautical miles'}:
                self.context.unit = 'nautical miles' if 'nautical' in lower else 'miles' if 'miles' in lower else 'm' if lower == 'in m' or lower.endswith(('metres', 'meters')) else 'km'
                self.calculate_current()
            elif (circle := re.fullmatch(r'show (\d+(?:\.\d+)?)\s*(km|miles|m) around (.+)', clean, re.I)):
                location = self._resolve_slot(circle[3], 'origin')
                self.context.origin = location
                if location:
                    self._remember(location)
                    self.context.result = self._dispatch('spatial.radius.calculate', {'center': location.coordinate.to_dict(), 'metres': float(circle[1]) * UNITS[circle[2].casefold()]}).output
            else:
                return None
            value = self.context.result
            message = 'Choose the matching geographic location.' if self.context.pending else f"{value['distance']:,.2f} {value['unit']} · {'Surface geodesic' if value['mode'] == 'GEODESIC' else 'Straight 3D / chord'}" if value and 'distance' in value else 'Geodesic radius computed.'
            return {'message': message, 'open_spatial': True, 'context': self.snapshot()}

    @staticmethod
    def is_context_command(text):
        """Cheap lexical eligibility; ordinary direct actions never queue here."""
        clean = ' '.join(str(text).strip().split()); lower = clean.casefold().rstrip('.?!')
        commands = {'show earth', 'open spatial lab', 'show globe', 'open globe', 'show map', 'open map', '2d map', 'show 2d map',
            'how far', "what's the distance as the crow flies", 'what is the distance as the crow flies', 'as the crow flies', 'what is the distance', 'show the path',
            'chord distance', 'straight line distance', 'driving distance', 'walking distance', 'cycling distance', 'route distance',
            'in miles', 'give it to me in miles', 'in km', 'in kilometres', 'in kilometers', 'in m', 'in metres', 'in meters', 'in nautical miles'}
        return lower in commands or any(re.fullmatch(pattern, clean, re.I) is not None for pattern in (
            r'(?:show|compare|distance between) (.+?) (?:and|to) (.+)',
            r'(?:what about|replace (?:it|the destination) with) (.+?)(?: instead)?[.?!]?',
            r'show(?: the)? straight[- ]line distance(?: t(?:oo|o))?[.?!]?',
            r'show (\d+(?:\.\d+)?)\s*(km|miles|m) around (.+)'))
