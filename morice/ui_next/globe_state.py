"""Deterministic visual state and input physics, without a renderer or backend."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import random


class OrbRotation:
    """Smooth shuffled cardinal turns; never jump to a random orientation."""
    def __init__(self,seed=None):
        self.rng=random.Random(seed);self.yaw=0.;self.pitch=0.;self.velocity=[0.,0.];self.target=(.12,0.)
        self.remaining=0.;self.directions=[];self.direction='right'

    def advance(self,seconds,*,interactive=False,reduced=False):
        if reduced:return
        dt=min(.1,max(0.,seconds));self.remaining-=dt
        if self.remaining<=0:
            if not self.directions:
                self.directions=['left','right','up','down'];self.rng.shuffle(self.directions)
            self.direction=self.directions.pop();speed=self.rng.uniform(.10,.22)
            self.target={'left':(-speed,0.),'right':(speed,0.),'up':(0.,-speed),'down':(0.,speed)}[self.direction]
            self.remaining=self.rng.uniform(4.,8.)
        target=(0.,0.) if interactive else self.target
        for i in (0,1):self.velocity[i]+=(target[i]-self.velocity[i])*(1-math.exp(-1.8*dt))
        self.yaw=(self.yaw+self.velocity[0]*dt)%math.tau;self.pitch=(self.pitch+self.velocity[1]*dt)%math.tau


class BootStage(str, Enum):
    DORMANT = 'DORMANT'
    IGNITING = 'IGNITING'
    PARTICLES_FORMING = 'PARTICLES_FORMING'
    WIREFRAME_FORMING = 'WIREFRAME_FORMING'
    ORBITS_SYNCHRONIZING = 'ORBITS_SYNCHRONIZING'
    GLOW_ACTIVATING = 'GLOW_ACTIVATING'
    WAITING_FOR_SERVICES = 'WAITING_FOR_SERVICES'
    READY_IDLE = 'READY_IDLE'
    FAILED = 'FAILED'


@dataclass
class GlobeBoot:
    elapsed: float = 0.
    ready: bool = False
    error: str = ''
    skipped: bool = False
    duration: float = 3.

    @property
    def progress(self):
        return 1. if self.skipped else min(1., self.elapsed / self.duration)

    @property
    def stage(self):
        if self.error: return BootStage.FAILED
        p = self.progress
        if p >= 1: return BootStage.READY_IDLE if self.ready else BootStage.WAITING_FOR_SERVICES
        return (BootStage.DORMANT if p < .08 else BootStage.IGNITING if p < .24
            else BootStage.PARTICLES_FORMING if p < .42 else BootStage.WIREFRAME_FORMING if p < .66
            else BootStage.ORBITS_SYNCHRONIZING if p < .86 else BootStage.GLOW_ACTIVATING)

    def advance(self, seconds):
        if math.isfinite(seconds): self.elapsed = min(self.duration, self.elapsed + max(0., seconds))

    def skip(self): self.skipped = True

    def fail(self, detail): self.error = str(detail)[:500] or 'Application initialization failed.'

    def layer(self, start, end):
        x = min(1., max(0., (self.progress - start) / (end - start)))
        return x * x * (3 - 2 * x)


@dataclass
class GlobeDynamics:
    yaw: float = 0.
    pitch: float = -.15
    yaw_velocity: float = 0.
    pitch_velocity: float = 0.
    zoom: float = 1.
    zoom_target: float = 1.
    time: float = 0.
    pointer: tuple[float, float] = (4., 4.)
    hover: float = 0.
    pointer_speed: float = 0.
    dragging: bool = False
    ripple_origin: tuple[float, float, float] = (0., 0., 1.)
    ripple_age: float = 10.
    wake_age: float = 10.

    def advance(self, seconds, *, reduced=False, speed=1.):
        dt = min(.1, max(0., seconds))
        if not reduced: self.time += dt * speed
        if not self.dragging:
            self.yaw += self.yaw_velocity * dt
            self.pitch = min(1.35, max(-1.35, self.pitch + self.pitch_velocity * dt))
            damping = math.exp(-3.8 * dt)
            self.yaw_velocity *= damping; self.pitch_velocity *= damping
        self.zoom += (self.zoom_target - self.zoom) * (1 - math.exp(-14 * dt))
        target = max(0., 1 - max(0., math.hypot(*self.pointer) - .6) / .9)
        self.hover += (target - self.hover) * (1 - math.exp(-10 * dt))
        self.pointer_speed *= math.exp(-7 * dt)
        self.ripple_age += dt; self.wake_age += dt

    def move(self, x, y, seconds=.016):
        previous = self.pointer
        self.pointer = (max(-4., min(4., x)), max(-4., min(4., y)))
        velocity = min(5., math.hypot(x - previous[0], y - previous[1]) / max(.008, seconds))
        self.pointer_speed = .65 * self.pointer_speed + .35 * velocity

    def drag(self, dx, dy, seconds=.016):
        self.yaw += dx * 2.7
        self.pitch = min(1.35, max(-1.35, self.pitch + dy * 2.7))
        dt = max(.012, seconds)
        self.yaw_velocity = max(-5., min(5., dx * 2.7 / dt))
        self.pitch_velocity = max(-5., min(5., dy * 2.7 / dt))

    def wheel(self, steps):
        self.zoom_target = max(.78, min(1.25, self.zoom_target * math.exp(max(-4., min(4., steps)) * .085)))

    def click(self, x, y):
        radius = math.hypot(x, y)
        if radius > 1: x /= radius; y /= radius
        self.ripple_origin = (x, y, math.sqrt(max(0., 1 - x*x - y*y)))
        self.ripple_age = 0.

    def reset(self):
        self.yaw = 0.; self.pitch = -.15
        self.yaw_velocity = self.pitch_velocity = 0.
        self.zoom_target = 1.; self.wake_age = 0.

    def transforms(self):
        return tuple((self.yaw + self.time * rate, self.pitch + math.sin(self.time * .09 + i) * .06)
                     for i, rate in enumerate((.045, -.027, .063, -.042, .11, -.14, .035, .19)))
