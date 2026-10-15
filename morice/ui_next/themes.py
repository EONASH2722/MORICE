"""Data-only appearance profiles, semantic tokens and crash-safe preferences."""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..media_lab.storage import atomic_json
from .appearance_profile import PRESETS, AppearanceProfile, color
from .theme_scenes import SCENES

COLORS = {'success': '#73d7ad', 'warning': '#efc47b', 'error': '#f7939d', 'info': '#94cfff',
    'research': '#a49ce9', 'builder': '#86cfc4', 'device': '#8cb8f1', 'security': '#efbd7c', 'media': '#bca2ef', 'spatial': '#79cedc'}


def luminance(value):
    channels = [int(color(value)[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))


def contrast(first, second):
    first, second = sorted((luminance(first), luminance(second)))
    return (second + .05) / (first + .05)


def foreground(background):
    return max(('#101723', '#f5f8fc'), key=lambda candidate: contrast(candidate, background))


def mix(first, second, fraction):
    values = [round(int(first[i:i + 2], 16) * (1 - fraction) + int(second[i:i + 2], 16) * fraction) for i in (1, 3, 5)]
    return '#' + ''.join(f'{value:02x}' for value in values)


@dataclass(frozen=True)
class DesignTokens:
    colors: dict[str, str]
    radius_small: int
    radius_medium: int
    radius_large: int
    spacing: int
    body_size: int
    title_size: int
    display_size: int
    control_height: int
    glow: float
    glass: float
    blur: float
    font_family: str
    scene: str

    def __getitem__(self, name):
        return self.colors[name]


def tokens(profile):
    base, surface, raised, primary, secondary = PRESETS[profile.preset]
    base = profile.background_tone or base; surface = profile.surface_tone or surface
    primary = profile.primary_accent or primary; secondary = profile.secondary_accent or secondary
    text = foreground(surface); background_text = foreground(base)
    if profile.surface_tone: raised = mix(surface, text, .06)
    material = mix(surface, base, profile.glass * .1) if contrast(text, base) >= 4.5 else surface
    def legible(candidate, background, target=4.5):
        endpoint = foreground(background)
        for _ in range(64):
            if contrast(candidate, background) >= target: return candidate
            candidate = mix(candidate, endpoint, .12)
        return endpoint
    muted = legible(mix(surface, text, .68), surface)
    primary_hover = legible(mix(primary, foreground(primary), .08), foreground(primary))
    primary_pressed = legible(mix(primary, foreground(primary), .14), foreground(primary))
    colors = {'background': base, 'surface': surface, 'surface_elevated': raised,
        'surface_glass': material, 'surface_hover': mix(surface, text, .08),
        'surface_pressed': mix(surface, text, .14), 'surface_selected': mix(surface, primary, .14),
        'border': mix(surface, text, .11 + profile.border_brightness * .18),
        'border_hover': legible(primary, surface, 3), 'text_primary': text, 'text_secondary': muted, 'text_muted': muted,
        'text_background': background_text, 'text_secondary_background': legible(mix(base, background_text, .68), base),
        'accent_primary': primary, 'accent_secondary': secondary, 'accent_text': foreground(primary),
        'primary_hover': primary_hover, 'primary_pressed': primary_pressed,
        'focus': legible(primary, surface, 3), **COLORS}
    # Custom bright surfaces get legible status colors, rather than pale neon text.
    for key in COLORS:
        colors[key] = legible(colors[key], surface)
    if profile.high_contrast:
        colors.update(border=text, text_secondary=text, text_muted=text)
    density = {'compact': .85, 'comfortable': 1, 'spacious': 1.15}[profile.density]
    shape = {'OBSIDIAN':.35,'ICE':.6,'NEON':.35,'MONOCHROME':.15,'AMETHYST':1.35,'SOLAR':1.2,'CRIMSON':1.3,'GLASS':1.25}.get(profile.preset,1.)
    radius = min(32,round(profile.radius*shape))
    return DesignTokens(colors, max(2, radius // 3), radius, min(32, radius + 8),
        round(12 * density), round(14 * profile.font_scale), round(24 * profile.font_scale),
        round(42 * profile.font_scale), round(38 * density * profile.font_scale), profile.glow, profile.glass, profile.blur, profile.font_family, profile.preset)


def stylesheet(t):
    material=t['surface_glass']
    if t.scene=='GLASS':
        channels=[int(material[i:i+2],16) for i in (1,3,5)]
        material=f'rgba({channels[0]}, {channels[1]}, {channels[2]}, {round(235-65*t.glass)})'
    return f'''
    QWidget {{ background: transparent; color: {t['text_background']}; font-family: "{t.font_family}"; font-size: {t.body_size}px; }}
    QWidget#RenovatedShell {{ background: {t['background']}; }}
    QFrame[role="surface"], QFrame#NavigationRail, QFrame#ComposerSurface {{ background: {material}; border: 1px solid {t['border']}; border-radius: {t.radius_medium}px; }}
    QFrame#ActionDeck {{ background: {material}; border: 1px solid {t['border']}; border-radius: {t.radius_medium}px; }}
    QFrame#ActionDeck QPushButton {{ background: transparent; border-color: transparent; padding: 6px; }}
    QFrame#ActionDeck QPushButton:hover {{ background: {t['surface_hover']}; border-color: {t['border_hover']}; }}
    QFrame#ActionDeck QPushButton:checked {{ background: {t['surface_selected']}; border-color: {t['border_hover']}; }}
    QFrame#ActionDeck QPushButton:focus {{ border: 2px solid {t['focus']}; }}
    QFrame[role="surface"] QLabel, QFrame#NavigationRail QLabel, QFrame#ComposerSurface QLabel {{ color: {t['text_primary']}; }}
    QLabel[role="secondary"] {{ color: {t['text_secondary_background']}; }}
    QLabel[role="title"] {{ font-size: {t.title_size}px; font-weight: 600; }}
    QLabel[role="display"] {{ font-size: {t.display_size}px; font-weight: 600; }}
    QPushButton#ActionCard QLabel {{ color: {t['text_primary']}; }}
    QPushButton#ActionCard QLabel[role="secondary"] {{ color: {t['text_secondary']}; }}
    QPushButton#ActionCard QLabel[role="card-title"] {{ font-weight: 600; font-size: {t.body_size+2}px; }}
    QPushButton, QToolButton {{ background: {t['surface_elevated']}; color: {t['text_primary']}; border: 1px solid {t['border']}; border-radius: {t.radius_small}px; padding: 8px 12px; min-height: {max(20, t.control_height-18)}px; }}
    QPushButton[icon_only="true"], QToolButton[icon_only="true"] {{ padding: 6px; min-width: 0; }}
    QPushButton#MessageAction {{ padding: 4px; min-width: 0; min-height: 0; }}
    QPushButton:hover, QToolButton:hover {{ background: {t['surface_hover']}; border-color: {t['border_hover']}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {t['surface_pressed']}; }}
    QFrame#NavigationRail QPushButton[role="navigation"] {{ background: transparent; border-color: transparent; text-align: left; padding: 8px 12px; }}
    QFrame#NavigationRail QPushButton[role="navigation"]:hover {{ background: {t['surface_hover']}; }}
    QFrame#NavigationRail QPushButton[role="navigation"]:checked {{ background: {t['surface_selected']}; border-color: {t['border_hover']}; font-weight: 600; }}
    QFrame#NavigationRail QPushButton[role="navigation"]:focus {{ border-color: {t['focus']}; }}
    QFrame#NavigationRail QPushButton[compact="true"] {{ text-align: center; padding: 8px 4px; min-width: 0; }}
    QPushButton:focus, QToolButton:focus, QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 2px solid {t['focus']}; }}
    QPushButton[role="primary"] {{ background: {t['accent_primary']}; color: {t['accent_text']}; font-weight: 600; }}
    QPushButton[role="primary"]:hover {{ background: {t['primary_hover']}; color: {t['accent_text']}; }}
    QPushButton[role="primary"]:pressed {{ background: {t['primary_pressed']}; color: {t['accent_text']}; }}
    QPushButton:disabled, QPushButton[role="primary"]:disabled {{ background: {t['surface_elevated']}; color: {t['text_muted']}; border-color: {t['border']}; }}
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {t['surface']}; color: {t['text_primary']}; border: 1px solid {t['border']}; border-radius: {t.radius_small}px; padding: 8px; selection-background-color: {t['accent_secondary']}; selection-color: {foreground(t['accent_secondary'])}; }}
    QListWidget, QTreeWidget, QTableWidget, QTextBrowser {{ background: {t['surface']}; color: {t['text_primary']}; border: 1px solid {t['border']}; border-radius: {t.radius_small}px; }}
    QListWidget::item, QTreeWidget::item {{ padding: 9px; }}
    QListWidget::item:selected, QTreeWidget::item:selected {{ background: {t['surface_pressed']}; border-left: 3px solid {t['accent_primary']}; }}
    QTabWidget::pane {{ border: 1px solid {t['border']}; border-radius: {t.radius_small}px; }}
    QTabBar::tab {{ background: {t['surface']}; color: {t['text_primary']}; padding: 10px 16px; }}
    QTabBar::tab:selected {{ color: {t['accent_primary']}; border-bottom: 2px solid {t['accent_primary']}; }}
    QHeaderView::section {{ background: {t['surface_elevated']}; color: {t['text_primary']}; padding: 8px; border: none; }}
    QScrollBar:vertical {{ width: 10px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: {t['border']}; min-height: 24px; border-radius: 5px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QProgressBar {{ background: {t['surface_elevated']}; border: 1px solid {t['border']}; border-radius: {t.radius_small}px; text-align: center; }}
    QProgressBar::chunk {{ background: {t['accent_primary']}; border-radius: {t.radius_small}px; }}
    QToolTip, QMenu {{ background: {t['surface_elevated']}; color: {t['text_primary']}; border: 1px solid {t['border']}; padding: 6px; }}
    QMenu::item:selected {{ background: {t['surface_pressed']}; }}
    QCheckBox, QRadioButton {{ spacing: 9px; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 20px; height: 20px; }}
    QComboBox::drop-down {{ width: 28px; border: none; }}
    QComboBox::down-arrow {{ image: none; width: 16px; height: 16px; }}
    QSlider::groove:horizontal {{ height: 5px; background: {t['border']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {t['accent_primary']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {t['accent_primary']}; border: 2px solid {t['surface']}; width: 15px; margin: -6px 0; border-radius: 8px; }}
    '''


class AppearanceStore:
    def __init__(self, directory):
        self.path = Path(directory) / 'appearance.json'; self.error = ''

    def load(self, legacy=None):
        if self.path.exists():
            try:
                if self.path.stat().st_size > 32768: raise ValueError('Appearance data too large.')
                return AppearanceProfile.from_dict(json.loads(self.path.read_text(encoding='utf-8')))
            except (OSError, ValueError, TypeError) as exc:
                self.error = str(exc); return AppearanceProfile()
        legacy = legacy or {}
        preset = {'light': 'ICE', 'midnight': 'MIDNIGHT', 'dark': 'MORICE', 'glass': 'GLASS', 'custom': 'CUSTOM'}.get(str(legacy.get('theme', '')).lower(), 'MORICE')
        try:
            return AppearanceProfile(preset=preset, font_scale=max(.8, min(1.8, float(legacy.get('ui_scale', 1)))), font_family=legacy.get('font_family', 'Segoe UI') or 'Segoe UI',
                reduced_motion=str(legacy.get('reduced_motion', '')).lower() in {'true', '1'},
                high_contrast=str(legacy.get('high_contrast', '')).lower() in {'true', '1'})
        except (ValueError, TypeError): return AppearanceProfile()

    def save(self, profile):
        atomic_json(self.path, profile.to_dict()); self.error = ''

    @staticmethod
    def import_file(path):
        path = Path(path)
        if path.stat().st_size > 32768: raise ValueError('Theme data exceeds its import budget.')
        return AppearanceProfile.from_dict(json.loads(path.read_text(encoding='utf-8')))


class ThemeEngine(QObject):
    changed = Signal(object)

    def __init__(self, directory, legacy=None, parent=None):
        super().__init__(parent)
        self.store = AppearanceStore(directory); self.profile = self.store.load(legacy)
        self.tokens = tokens(self.profile)

    def update(self, *, persist=True, **changes):
        updated = replace(self.profile, **changes)
        if updated == self.profile:
            if persist:self.store.save(updated)
            return
        self.profile = updated; self.tokens = tokens(updated)
        if persist: self.store.save(updated)
        self.changed.emit(self.tokens)

    def apply_profile(self, profile, *, persist=True):
        self.profile = AppearanceProfile.from_dict(profile.to_dict()); self.tokens = tokens(self.profile)
        if persist: self.store.save(self.profile)
        self.changed.emit(self.tokens)
