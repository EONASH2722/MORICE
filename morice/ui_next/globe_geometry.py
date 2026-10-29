"""Original bounded 3D geometry. Generated once, transformed on the GPU."""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class GlobeLayer:
    name: str
    vertices: np.ndarray
    points: bool
    reveal: tuple[float, float]
    speed: float
    axis: tuple[float, float, float]
    brightness: float


def build_globe_geometry():
    rng = np.random.default_rng(72931)
    layers = []

    def layer(name, paths, reveal, speed, axis, brightness):
        vertices = []
        for index, path in enumerate(paths):
            path = np.asarray(path, dtype=np.float32)
            for j in range(len(path)-1):
                # Per-vertex seed and path reveal position.
                for k in (j,j+1): vertices.append((*path[k], index*.733, k/max(1,len(path)-1)))
        layers.append(GlobeLayer(name,np.asarray(vertices,dtype=np.float32),False,reveal,speed,axis,brightness))

    angle = np.linspace(0, math.tau, 145)
    grid = []
    for latitude in np.linspace(-1.44,1.44,31):
        radius = math.cos(latitude)
        grid.append(np.column_stack((radius*np.cos(angle),np.full(len(angle),math.sin(latitude)),radius*np.sin(angle))))
    for longitude in np.linspace(0,math.pi,24,endpoint=False):
        grid.append(np.column_stack((np.cos(angle)*math.cos(longitude),np.sin(angle),np.cos(angle)*math.sin(longitude))))
    layer('wireframe',grid,(.35,.7),.032,(0,1,.18),.10)

    def orbit(radius, tilt, spin, eccentricity=1., segments=145, portion=1.):
        a=np.linspace(0,math.tau*portion,segments)
        xyz=np.column_stack((radius*np.cos(a),radius*eccentricity*np.sin(a),np.zeros(segments)))
        c,s=math.cos(tilt),math.sin(tilt); c2,s2=math.cos(spin),math.sin(spin)
        matrix=np.array(((c2,-s2*c,s2*s),(s2,c2*c,-c2*s),(0,s,c)))
        return xyz@matrix.T

    for group in range(3):
        paths=[]
        for i in range(13):
            paths.append(orbit(.62+i*.033, .35+group*.63+i*.11, group*1.8+i*.24, .72+.23*math.sin(i*.41)**2))
        layer('orbits-'+str(group),paths,(.61,.89),(.085,-.066,.049)[group],((.2,1,.3),(1,.2,.4),(.3,.4,1))[group],(.46,.29,.24)[group])

    paths=[]
    for i in range(125):
        radius=rng.uniform(.72,1.015)
        path=orbit(radius,rng.uniform(0,math.pi),rng.uniform(0,math.tau),1.,49,rng.uniform(.05,.28))
        paths.append(path)
    layer('segmented-shell',paths,(.4,.77),-.024,(.3,1,.2),.22)

    paths=[]
    for i in range(76):
        a=np.linspace(0,math.tau,97)
        r=.09+i*.0035
        paths.append(np.column_stack((r*np.cos(a)+.035*np.sin(5*a+i),r*np.sin(a)*math.cos(i*.47),r*np.sin(a)*math.sin(i*.47))))
    layer('core-filaments',paths,(.08,.32),.25,(.4,1,.6),.38)

    paths=[]
    for i in range(135):
        normal=rng.normal(size=3);normal/=np.linalg.norm(normal)
        radius=rng.uniform(.65,1.02)
        paths.append(np.array((normal*radius,normal*(radius+rng.uniform(.015,.16)))))
    layer('radial-markers',paths,(.43,.81),.032,(0,1,.18),.28)

    count=1350
    direction=rng.normal(size=(count,3));direction/=np.linalg.norm(direction,axis=1)[:,None]
    radii=np.where(rng.random(count)<.72,rng.uniform(.7,1.,count),rng.uniform(.08,.65,count))
    points=direction*radii[:,None]
    point_data=np.column_stack((points,rng.uniform(0,100,count),rng.uniform(0,1,count))).astype(np.float32)
    layers.append(GlobeLayer('particles',point_data,True,(.2,.52),-.056,(.15,1,.3),.85))
    return tuple(layers)
