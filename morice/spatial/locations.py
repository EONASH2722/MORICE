"""Indexed legitimate local GeoNames lookup. No invented coordinates or tracking."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import unicodedata
from functools import lru_cache

from .contracts import Coordinate, Location


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c)).split())


@lru_cache(maxsize=256)
def has_local_place(query):
    """Cheap bounded eligibility only; resolution still verifies the real dataset."""
    if not isinstance(query,str) or not 1<=len(query)<=200:return False
    try:
        with LocalGazetteer().connect() as db:
            return db.execute('SELECT 1 FROM aliases WHERE name=? LIMIT 1',(normalized(query),)).fetchone() is not None
    except (OSError,ValueError,sqlite3.Error):return False


class LocalGazetteer:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(__file__).resolve().parents[1] / 'assets/spatial/cities.sqlite3'

    @contextmanager
    def connect(self):
        if not self.path.is_file() or self.path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Local geographic provider unavailable. Use explicit latitude/longitude or install the attributed city dataset.')
        db = sqlite3.connect('file:' + self.path.resolve().as_posix() + '?mode=ro', uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            if db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('Unknown geographic dataset schema.')
            yield db
        finally:
            db.close()

    @staticmethod
    def location(row):
        # GeoNames elevation/DEM is deliberately not turned into supplied altitude.
        return Location('geonames:' + str(row['id']), row['name'], Coordinate(row['lat'], row['lon']),
            'https://www.geonames.org/' + str(row['id']), row['country'], row['region'], row['population'])

    def resolve(self, query, *, country='', region='', limit=30):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200 or not 1 <= limit <= 50:
            raise ValueError('Enter a bounded location name.')
        with self.connect() as db:
            rows = db.execute('SELECT DISTINCT c.* FROM cities c JOIN aliases a ON c.id=a.id WHERE a.name=? AND (?=\'\' OR c.country=?) AND (?=\'\' OR c.region=?) ORDER BY c.population DESC LIMIT ?',
                (normalized(query), country, country, region, region, limit + 1)).fetchall()
            source = dict(db.execute('SELECT key,value FROM metadata').fetchall())
        candidates = [self.location(row).to_dict() for row in rows[:limit]]
        return {'schema': 1, 'query': query, 'status': 'NOT_FOUND' if not candidates else 'RESOLVED' if len(candidates) == 1 else 'AMBIGUOUS',
            'candidates': candidates, 'truncated': len(rows) > limit, 'source': source.get('source'),
            'license': source.get('license'), 'message': 'Choose a candidate; coordinates are not guessed.' if len(candidates) > 1 else ''}

    def get(self, identifier):
        if not isinstance(identifier, str) or not identifier.startswith('geonames:') or not identifier[9:].isdigit():
            raise ValueError('Invalid geographic location identity.')
        with self.connect() as db:
            row = db.execute('SELECT * FROM cities WHERE id=?', (int(identifier[9:]),)).fetchone()
        if row is None:
            raise ValueError('Location is not in the installed provider data.')
        return self.location(row)
