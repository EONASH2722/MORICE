"""Strict data-only appearance contract, usable without loading Qt."""
from dataclasses import asdict, dataclass
import math
import re

PRESETS = {
    'MORICE': ('#000000', '#0b0b10', '#16161e', '#c4a1fa', '#b1a1ed'),
    'GLASS': ('#0b1424', '#23334a', '#2f4560', '#abecff', '#c5b7ff'),
    'OBSIDIAN': ('#0c0e12', '#171a20', '#232730', '#99c8db', '#b5b5cc'),
    'ICE': ('#ffffff', '#ffffff', '#f3f3f6', '#654196', '#64539b'),
    'AMETHYST': ('#100d20', '#1d1832', '#2a2442', '#b9a2ff', '#87dff2'),
    'MIDNIGHT': ('#060a13', '#0e1524', '#192338', '#7cbbff', '#b49aff'),
    'NEON': ('#0c111b', '#141f2e', '#1d2b3e', '#83efcf', '#caa8ff'),
    'MONOCHROME': ('#101113', '#1b1d20', '#292c31', '#e4e7eb', '#bfc5cd'),
    'CUSTOM': ('#0b101b', '#121b2b', '#1b2739', '#85d6ed', '#baa8eb'),
    'ARCTIC': ('#09141b', '#142631', '#203844', '#b1eeef', '#a8b8eb'),
    'SOLAR': ('#17110b', '#281d13', '#392c1c', '#efd098', '#d5abef'),
    'CRIMSON': ('#150b12', '#281722', '#392331', '#f7a4b6', '#b4aff2'),
}
def color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Colors must be six-digit hexadecimal data; stylesheets and paths are not allowed.')
    return value.lower()


@dataclass(frozen=True)
class AppearanceProfile:
    schema: int = 1
    preset: str = 'MORICE'
    primary_accent: str = ''
    secondary_accent: str = ''
    background_tone: str = ''
    surface_tone: str = ''
    glow: float = .35
    glass: float = .55
    blur: float = .25
    border_brightness: float = .35
    radius: int = 16
    font_scale: float = 1.0
    font_family: str = 'Segoe UI'
    density: str = 'comfortable'
    motion_strength: float = .65
    motion_speed: float = 1.0
    cursor_light: bool = True
    cursor_glow: str = 'MINIMAL'
    cursor_trail: bool = False
    magnetic_controls: bool = False
    background_effects: bool = True
    field_palette: str = 'STATE'
    field_intensity: float = .25
    field_motion: float = .45
    core_brightness: float = .7
    core_scale: float = 1.0
    orbital_complexity: int = 3
    globe_color: str = '#c68bff'
    globe_glow_color: str = '#7d35b8'
    particles: str = 'OFF'
    reduced_motion: bool = False
    high_contrast: bool = False
    quality: str = 'BALANCED'

    def __post_init__(self):
        if type(self.schema) is not int or self.schema != 1 or not isinstance(self.preset, str) or self.preset not in PRESETS:
            raise ValueError('Unknown appearance schema or preset.')
        for key in ('globe_color', 'globe_glow_color'):
            color(getattr(self, key))
        for key in ('primary_accent', 'secondary_accent', 'background_tone', 'surface_tone'):
            if not isinstance(getattr(self, key), str): raise ValueError('Appearance colors must be string data.')
            if getattr(self, key): color(getattr(self, key))
        for key in ('glow', 'glass', 'blur', 'border_brightness', 'motion_strength', 'field_intensity', 'field_motion', 'core_brightness'):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Appearance intensity must be finite and within 0…1.')
        if type(self.radius) is not int or not 0 <= self.radius <= 32:
            raise ValueError('Radius must be within 0…32.')
        if type(self.orbital_complexity) is not int or not 1 <= self.orbital_complexity <= 6:
            raise ValueError('Orbital complexity must be within 1…6.')
        if self.field_palette not in {'STATE', 'CYAN', 'VIOLET', 'THEME'}:
            raise ValueError('Unknown energy field palette.')
        if not isinstance(self.font_family, str) or not 1 <= len(self.font_family) <= 100 or not all(character.isalnum() or character in ' _.,-' for character in self.font_family):
            raise ValueError('Font family must be bounded text, without stylesheet syntax or file paths.')
        for value, low, high in ((self.font_scale, .8, 1.8), (self.motion_speed, .5, 2),(self.core_scale,.5,1.5)):
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError('Appearance scale/speed exceeds supported bounds.')
        if self.density not in {'compact', 'comfortable', 'spacious'} or self.quality not in {'LOW', 'BALANCED', 'HIGH', 'ULTRA'}:
            raise ValueError('Unknown appearance density/quality.')
        if self.cursor_glow not in {'OFF', 'MINIMAL', 'NORMAL', 'HIGH'} or self.particles not in {'OFF', 'LOW', 'NORMAL'}:
            raise ValueError('Unknown cursor/particle profile.')
        for key in ('cursor_light', 'cursor_trail', 'magnetic_controls', 'background_effects', 'reduced_motion', 'high_contrast'):
            if type(getattr(self, key)) is not bool: raise ValueError('Appearance switches must be boolean data.')

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise ValueError('Unknown appearance fields; executable content is refused.')
        return cls(**value)

    def to_dict(self):
        return asdict(self)


