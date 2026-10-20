"""Bounded, user-triggered Photon/OSM lookup with a persistent query cache."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .contracts import Coordinate, Location
from .locations import normalized


class OnlineGeocoder:
    _requests = threading.Lock()
    _last_request = 0.

    def __init__(self, cache_path, *, endpoint=None, transport=None):
        self.path = Path(cache_path)
        self.endpoint = endpoint or os.environ.get('MORICE_GEOCODER_URL', 'https://photon.komoot.io/api/')
        parsed = urlsplit(self.endpoint)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('The geocoder must use a configured HTTPS Photon API endpoint.')
        self.transport = transport or urlopen
        self._lock = threading.RLock(); self._queries = {}; self._locations = {}
        try:
            if self.path.stat().st_size <= 4*1024*1024:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('schema') == 1 and data.get('endpoint') == self.endpoint:
                    self._queries = dict(list(data['queries'].items())[-128:])
                    for record in self._queries.values():
                        for candidate in record['result']['candidates']:
                            self._locations[candidate['identifier']] = self._location(candidate)
        except (OSError, ValueError, KeyError, TypeError):
            self._queries = {}; self._locations = {}

    @staticmethod
    def _location(value):
        value = dict(value); value['coordinate'] = Coordinate.from_dict(value['coordinate'])
        return Location(**value)

    def get(self, identifier):
        with self._lock:
            if identifier not in self._locations:
                raise ValueError('Choose a location returned by the online provider.')
            return self._locations[identifier]

    def _fetch(self, query, context):
        if not self._requests.acquire(blocking=False):
            raise OSError('Another location lookup is running. Try again in a moment.')
        try:
            token = context.cancellation_token if context else None
            deadline = context.deadline if context and context.deadline else time.monotonic()+21
            while time.monotonic()-type(self)._last_request < 1:
                if token: token.raise_if_cancelled()
                if time.monotonic() >= deadline: raise TimeoutError('Location lookup deadline reached.')
                # At most one second of cancellable pacing; no resource queue.
                if token: token.wait(.05)
                else: time.sleep(.05)
            type(self)._last_request = time.monotonic()
            url = self.endpoint + ('&' if '?' in self.endpoint else '?') + urlencode({'q': query, 'limit': 10, 'lang': 'en'})
            request = Request(url, headers={'User-Agent': 'MORICE-Spatial/0.9.4 (+https://github.com/EONASH2722/MORICE)', 'Accept': 'application/json'})
            timeout = min(10., deadline-time.monotonic())
            if timeout <= 0: raise TimeoutError('Location lookup deadline reached.')
            with self.transport(request, timeout=timeout) as response:
                final = urlsplit(response.geturl())
                if final.scheme != 'https' or final.hostname != urlsplit(self.endpoint).hostname:
                    raise ValueError('Unexpected geocoder redirect.')
                raw = response.read(256*1024+1)
            if len(raw) > 256*1024: raise ValueError('Geocoder response exceeds the bounded lookup size.')
            value = json.loads(raw)
            if not isinstance(value, dict) or not isinstance(value.get('features'), list):
                raise ValueError('Invalid geographic provider response.')
            return value['features'][:20]
        finally:
            self._requests.release()

    def resolve(self, query, *, country='', region='', context=None):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
            raise ValueError('Enter a place name within 200 characters.')
        key = json.dumps([normalized(query), country.upper(), region], ensure_ascii=True)
        with self._lock:
            cached = self._queries.get(key)
            if cached and 0 <= time.time()-cached['time'] < 86400:
                result = copy.deepcopy(cached['result']); result['cached'] = True; return result
        # Gujrat is also a real Pakistani city. Offer Gujarat, India alongside
        # it rather than silently changing the user's place to another country.
        terms = (query, 'Gujarat') if normalized(query) == 'gujrat' and country.upper() != 'PK' else (query,)
        candidates = {}
        for term in terms:
            for feature in self._fetch(term, context):
                try:
                    properties = feature['properties']; geometry = feature['geometry']
                    if geometry['type'] != 'Point': continue
                    kind = properties.get('osm_value') if properties.get('osm_key') == 'place' else properties.get('type')
                    if kind not in {'city','town','village','hamlet','state','country','county','district','suburb','island','municipality','locality'}: continue
                    code = str(properties.get('countrycode', '')).upper()
                    if country and code != country.upper(): continue
                    if region and normalized(region) != normalized(str(properties.get('state', ''))): continue
                    osm_type = {'N':'node','W':'way','R':'relation'}[properties['osm_type']]
                    identifier = properties['osm_id']
                    if type(identifier) is not int or identifier <= 0: continue
                    label = str(properties.get('name') or term)[:200]
                    if not -180 <= float(geometry['coordinates'][0]) <= 180: continue
                    coordinate = Coordinate(geometry['coordinates'][1], geometry['coordinates'][0])
                    location = Location(f'osm:{osm_type}:{identifier}', label, coordinate,
                        f'https://www.openstreetmap.org/{osm_type}/{identifier}', code,
                        str(properties.get('state', ''))[:200], kind=str(kind))
                    candidates[location.identifier] = location
                except (KeyError, TypeError, ValueError, IndexError): continue
        names = {normalized(term) for term in terms}
        exact = [v for v in candidates.values() if normalized(v.label) in names]
        values = exact or list(candidates.values())
        # A city and state can share an exact name (New York, São Paulo).
        # Preserve both instead of silently choosing administrative coordinates.
        values = values[:12]
        result = {'schema': 1, 'query': query, 'status': 'NOT_FOUND' if not values else 'RESOLVED' if len(values) == 1 else 'AMBIGUOUS',
            'candidates': [v.to_dict() for v in values], 'source': self.endpoint, 'license': 'OpenStreetMap contributors · ODbL',
            'cached': False, 'message': 'Choose the place and country you mean.' if len(values) > 1 else ''}
        with self._lock:
            for value in values: self._locations[value.identifier] = value
            self._queries[key] = {'time': time.time(), 'result': result}
            self._queries = dict(list(self._queries.items())[-128:])
            self._locations = {v['identifier']: self._location(v) for record in self._queries.values() for v in record['result']['candidates']}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'schema': 1, 'endpoint': self.endpoint, 'queries': self._queries}), encoding='utf-8')
            temporary.replace(self.path)
        return copy.deepcopy(result)
