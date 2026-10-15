"""Prepare bounded, attributed public geographic DATA; never model/code weights."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import unicodedata
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'morice/assets/spatial'
DEST.mkdir(parents=True, exist_ok=True)


def fetch(url, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'MORICE-Phase10-geographic-data/0.8'})
    with urllib.request.urlopen(request, timeout=45) as response:
        if not response.geturl().startswith('https://'):
            raise ValueError('Only HTTPS data sources are allowed.')
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Geographic data exceeds its download budget.')
    return data


def normalize(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c)).split())


sources = []
readme_url = 'https://download.geonames.org/export/dump/readme.txt'
readme = fetch(readme_url, 128 * 1024)
(DEST / 'GEONAMES-README.txt').write_bytes(readme)
city_url = 'https://download.geonames.org/export/dump/cities15000.zip'
data = fetch(city_url, 16 * 1024 * 1024)
archive_path = ROOT / 'build/phase10-geonames-cities15000.zip'
archive_path.write_bytes(data)
database = DEST / 'cities.sqlite3'
if database.exists():
    raise FileExistsError('Existing geographic database preserved; inspect it before rebuilding.')
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    assert archive.testzip() is None and 'cities15000.txt' in archive.namelist()
    member = archive.getinfo('cities15000.txt')
    assert member.file_size < 128 * 1024 * 1024
    with sqlite3.connect(database) as db:
        db.executescript('CREATE TABLE cities(id INTEGER PRIMARY KEY,name TEXT,lat REAL,lon REAL,country TEXT,region TEXT,population INTEGER,modified TEXT); CREATE TABLE aliases(name TEXT,id INTEGER); CREATE INDEX aliases_name ON aliases(name); CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);')
        cities = []; aliases = []; count = 0
        with archive.open(member) as stream:
            for raw in stream:
                if len(raw) > 65536:
                    raise ValueError('Oversized geographic record.')
                row = raw.decode('utf-8').rstrip('\r\n').split('\t')
                if len(row) != 19:
                    raise ValueError('Unknown GeoNames schema.')
                identifier = int(row[0]); lat, lon = float(row[4]), float(row[5])
                assert -90 <= lat <= 90 and -180 <= lon <= 180
                cities.append((identifier, row[1], lat, lon, row[8], row[10], int(row[14]), row[18]))
                for name in {normalize(name) for name in [row[1], row[2], *row[3].split(',')[:160]] if name}:
                    aliases.append((name, identifier))
                count += 1
                if count > 100000:
                    raise ValueError('City inventory exceeds its bound.')
                if len(cities) >= 500:
                    db.executemany('INSERT INTO cities VALUES(?,?,?,?,?,?,?,?)', cities)
                    db.executemany('INSERT INTO aliases VALUES(?,?)', aliases)
                    cities.clear(); aliases.clear()
        db.executemany('INSERT INTO cities VALUES(?,?,?,?,?,?,?,?)', cities)
        db.executemany('INSERT INTO aliases VALUES(?,?)', aliases)
        db.executemany('INSERT INTO metadata VALUES(?,?)', [('schema', '1'), ('source', city_url), ('license', 'CC BY 4.0; attribution GeoNames'), ('source_sha256', hashlib.sha256(data).hexdigest()), ('rows', str(count))])
        db.execute('PRAGMA user_version=1')
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
sources.append({'url': city_url, 'sha256': hashlib.sha256(data).hexdigest(), 'download_bytes': len(data), 'records': count, 'license': 'CC BY 4.0, GeoNames', 'output': str(database)})

land_url = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_land.geojson'
land_data = fetch(land_url, 2 * 1024 * 1024)
land = json.loads(land_data)
assert land['type'] == 'FeatureCollection' and 1 <= len(land['features']) <= 1000
rings = []
for feature in land['features']:
    geometry = feature['geometry']
    polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else []
    for polygon in polygons:
        for ring in polygon:
            if len(ring) > 20000:
                raise ValueError('Land ring exceeds geometry budget.')
            assert all(len(point) >= 2 and -180 <= point[0] <= 180 and -90 <= point[1] <= 90 for point in ring)
            rings.append([[point[0], point[1]] for point in ring])
assert sum(map(len, rings)) <= 50000
geometry_path = DEST / 'earth-land.json'
geometry_path.write_text(json.dumps({'schema': 1, 'source': land_url, 'license': 'Public domain; Natural Earth', 'source_sha256': hashlib.sha256(land_data).hexdigest(), 'rings': rings}, separators=(',', ':')), encoding='utf-8')
sources.append({'url': land_url, 'sha256': hashlib.sha256(land_data).hexdigest(), 'download_bytes': len(land_data), 'vertices': sum(map(len, rings)), 'license': 'Public domain, Natural Earth', 'output': str(geometry_path)})
(DEST / 'ATTRIBUTION.txt').write_text('City names/coordinates: GeoNames, https://www.geonames.org/, Creative Commons Attribution 4.0, https://creativecommons.org/licenses/by/4.0/. Full cities15000 extract; city coverage is intentionally bounded to that published dataset. Data accuracy/completeness is not guaranteed.\nEarth land geometry: Natural Earth 1:110m land v5.1.2, public domain, https://www.naturalearthdata.com/about/terms-of-use/. Made with Natural Earth.\n', encoding='utf-8')
receipt = {'schema': 1, 'created_utc': datetime.now(timezone.utc).isoformat(), 'sources': sources,
    'assets': [{'path': str(path), 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(DEST.iterdir()) if path.is_file()]}
(ROOT / 'build/phase10-geodata.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
