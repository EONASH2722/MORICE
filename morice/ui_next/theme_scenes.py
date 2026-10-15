"""Authored theme geometry, with closed, differentiable animation cycles.

These decorative scenes never indicate task completion or capture desktop pixels.
One shared effect clock and the existing field raster budget remain authoritative.
"""
from __future__ import annotations
import math

SCENES = {
    'MORICE': ('Plasma', 'Flowing ribbons orbit the luminous Core.'),
    'GLASS': ('Prismatic glass', 'Floating crystal facets and soft refracted light.'),
    'OBSIDIAN': ('Basalt', 'Sculpted polygon rings turn through quiet geometric shadows.'),
    'ICE': ('Crystal bloom', 'Six-fold frost crystals open and turn gently.'),
    'AMETHYST': ('Petal garden', 'Layered violet rosettes breathe and unfurl.'),
    'MIDNIGHT': ('Star atlas', 'Constellations orbit in a deep, drifting night sky.'),
    'NEON': ('Circuit current', 'Angular circuits carry travelling points of light.'),
    'MONOCHROME': ('Kinetic weave', 'Interlaced diamond lattices sway in counterpoint.'),
    'CUSTOM': ('Harmonic braid', 'A woven Lissajous field follows your custom palette.'),
    'ARCTIC': ('Aurora', 'Curtains of northern light dance across the horizon.'),
    'SOLAR': ('Corona', 'Solar filaments curl around a warm radiant centre.'),
    'CRIMSON': ('Resonance', 'Soft concentric ripples swell and return like a heartbeat.'),
}
LOOP_SECONDS = 24.

def loop_angle(seconds):
    return (seconds % LOOP_SECONDS) / LOOP_SECONDS * math.tau

def scene_points(preset, layer, layers, angle, samples=96):
    """Normalized paths; identical position and velocity at either loop boundary."""
    points = []
    offset = layer * .61
    r = .17 + layer / max(1, layers) * .34
    for index in range(samples + 1):
        u = index / samples; a = u * math.tau
        if preset == 'GLASS':
            # Three-sided facets are rounded by a small harmonic refraction.
            sides = 3 + layer % 3
            polygon = math.cos(math.pi/sides) / math.cos((a % (math.tau/sides)) - math.pi/sides)
            rr = r * polygon * (1 + .08*math.sin(angle + offset))
            turn = a + angle * (-1 if layer % 2 else 1) + offset
            x = .5 + rr*math.cos(turn); y = .5 + rr*math.sin(turn)*.85 + .025*math.sin(angle*2+offset)
        elif preset == 'OBSIDIAN':
            sides = 5 + layer % 3
            turn = a + angle + offset
            rr = r * math.cos(math.pi/sides)/math.cos((a % (math.tau/sides))-math.pi/sides)
            x = .5 + rr*math.cos(turn)*1.15; y = .5 + rr*math.sin(turn)*.78
        elif preset == 'ICE':
            rr = r*(.7+.22*math.cos(6*a))*(1+.08*math.sin(angle+offset))
            turn = a + angle * (-1 if layer%2 else 1)
            x = .5 + rr*math.cos(turn); y = .5 + rr*math.sin(turn)
        elif preset == 'AMETHYST':
            rr = r*(.76+.24*math.cos(5*a+angle+offset))
            turn = a-angle+offset*.16
            x = .5+rr*math.cos(turn)*1.2; y = .5+rr*math.sin(turn)
        elif preset == 'MIDNIGHT':
            turn = a + angle + offset
            x = .5+r*math.cos(turn)*1.3; y = .5+r*math.sin(turn)*(.38+.08*math.sin(angle+offset))
        elif preset == 'NEON':
            # A squared circuit with travelling illumination, never a reset scan.
            turn = a + offset*.2
            rr = r / max(abs(math.cos(a)), abs(math.sin(a)))
            x = .5+rr*math.cos(turn)*.95; y = .5+rr*math.sin(turn)*.7+.024*math.sin(angle+offset)
        elif preset == 'MONOCHROME':
            rr = r/(abs(math.cos(a))+abs(math.sin(a)))
            turn = a + .18*math.sin(angle+offset)
            x = .5+rr*math.cos(turn)*1.28; y = .5+rr*math.sin(turn)*1.1
        elif preset == 'CUSTOM':
            x = .5+r*math.sin(3*a+angle+offset); y = .5+r*math.sin(2*a-angle)*.8
        elif preset == 'ARCTIC':
            x = -.1+u*1.2
            y = .32+layer/max(1,layers)*.34+.12*math.sin(u*math.tau*2+angle+offset)+.04*math.sin(u*math.tau*5-angle*2)
        elif preset == 'SOLAR':
            rr = r*(1+.09*math.sin(9*a+angle*2+offset))
            turn = a + angle + offset
            x = .5+rr*math.cos(turn); y = .5+rr*math.sin(turn)
        elif preset == 'CRIMSON':
            rr = r*(1+.11*math.sin(angle*2+offset)+.035*math.sin(3*a-angle))
            x = .5+rr*math.cos(a)*1.26; y = .5+rr*math.sin(a)*.74
        else:
            rr = r+.055*math.sin(3*a+angle+offset)+.03*math.sin(7*a-angle*2+offset)
            x = .5+rr*math.cos(a)*1.24; y = .48+rr*math.sin(a)*1.08
        points.append((x,y))
    return points

def particle_position(seed, angle):
    x, y, speed, offset = seed
    # A closed orbit around each seed. No edge wrap or top-to-bottom teleport.
    return (x+.018*math.sin(angle+offset), y+.032*math.cos(angle*2+offset))
