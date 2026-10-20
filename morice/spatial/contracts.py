from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math

UNITS = {'m': 1.0, 'km': 1000.0, 'miles': 1609.344, 'nautical miles': 1852.0}
MODES = {'GEODESIC', 'CHORD', 'ROUTE'}


@dataclass(frozen=True)
class Coordinate:
    latitude: float
    longitude: float
    altitude: float | None = None
    reference: str = 'WGS84'

    def __post_init__(self):
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (self.latitude, self.longitude)):
            raise ValueError('Coordinates must be finite numbers.')
        if not -90 <= self.latitude <= 90 or abs(self.longitude) > 1e6:
            raise ValueError('Latitude must be within −90…90; longitude is outside supported normalization bounds.')
        if self.reference != 'WGS84':
            raise ValueError('Only WGS84 supplied coordinates are implemented.')
        if self.altitude is not None and (type(self.altitude) not in (int, float) or not math.isfinite(self.altitude) or not -100000 <= self.altitude <= 1e7):
            raise ValueError('Supplied altitude is outside finite supported bounds.')
        object.__setattr__(self, 'longitude', ((float(self.longitude) + 180) % 360) - 180)
        object.__setattr__(self, 'latitude', float(self.latitude))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - {'latitude', 'longitude', 'altitude', 'reference'}:
            raise ValueError('Invalid coordinate fields.')
        return cls(**value)


@dataclass(frozen=True)
class Location:
    identifier: str
    label: str
    coordinate: Coordinate
    source: str
    country: str = ''
    region: str = ''
    population: int = 0
    kind: str = 'city'

    def to_dict(self):
        return asdict(self)


@dataclass
class SpatialContext:
    origin: Location | None = None
    destination: Location | None = None
    markers: dict[str, Location] = field(default_factory=dict)
    selected_marker: str = ''
    mode: str = 'GEODESIC'
    unit: str = 'km'
    viewport: str = 'globe'
    result: dict | None = None
    pending: list[dict] = field(default_factory=list)

    def to_dict(self):
        return {'origin': self.origin.to_dict() if self.origin else None,
            'destination': self.destination.to_dict() if self.destination else None,
            'markers': [item.to_dict() for item in self.markers.values()],
            'selected_marker': self.selected_marker, 'mode': self.mode, 'unit': self.unit,
            'viewport': self.viewport, 'result': self.result, 'pending': self.pending}
