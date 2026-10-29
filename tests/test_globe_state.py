import math
from dataclasses import replace

import numpy as np
import pytest

from morice.ui_next.globe_state import GlobeBoot,BootStage,GlobeDynamics
from morice.ui_next.globe_geometry import build_globe_geometry
from morice.ui_next.appearance_profile import AppearanceProfile


def test_boot_builds_layers_in_order_and_waits_for_services():
    boot=GlobeBoot();stages=[]
    for _ in range(80):
        stages.append(boot.stage);boot.advance(.05)
    assert list(dict.fromkeys(stages))==[BootStage.DORMANT,BootStage.IGNITING,BootStage.PARTICLES_FORMING,
        BootStage.WIREFRAME_FORMING,BootStage.ORBITS_SYNCHRONIZING,BootStage.GLOW_ACTIVATING,BootStage.WAITING_FOR_SERVICES]
    assert boot.elapsed==3 and not boot.ready
    boot.ready=True;assert boot.stage==BootStage.READY_IDLE


def test_skip_does_not_claim_services_ready_and_failures_survive_skip():
    boot=GlobeBoot();boot.skip()
    assert boot.stage==BootStage.WAITING_FOR_SERVICES
    boot.fail('Owned startup failure');boot.ready=True;boot.skip();boot.advance(5)
    assert boot.stage==BootStage.FAILED and boot.error=='Owned startup failure'


def test_ready_services_do_not_bypass_materialization_and_colors_do_not_reset_boot():
    boot=GlobeBoot(ready=True);boot.advance(.9)
    assert boot.stage==BootStage.PARTICLES_FORMING
    first=boot.layer(.35,.7);boot.advance(.9)
    assert boot.layer(.35,.7)>first
    boot.advance(-100);boot.advance(math.inf);assert boot.elapsed==1.8


def test_real_3d_geometry_is_bounded_and_orbit_planes_differ():
    layers=build_globe_geometry()
    assert len(layers)==8 and sum(x.vertices.nbytes for x in layers)<2_000_000
    assert len({x.speed for x in layers})>=6
    for layer in layers:
        assert layer.vertices.shape[1]==5 and np.isfinite(layer.vertices).all()
        assert np.ptp(layer.vertices[:,2])>.05
    assert len(next(x for x in layers if x.points).vertices)>1000


def test_rotation_is_inertial_and_orbit_families_move_independently():
    d=GlobeDynamics();first=d.transforms();d.drag(.2,.1,.1);yaw=d.yaw
    d.advance(.05)
    assert d.yaw>yaw and 0<d.yaw_velocity<5
    assert d.transforms()!=first
    for _ in range(120):d.advance(.05)
    assert abs(d.yaw_velocity)<.001
    assert len({round(a[0]-b[0],4) for a,b in zip(d.transforms(),first)})>4


def test_pointer_click_zoom_and_reset_are_input_driven_and_bounded():
    d=GlobeDynamics();d.move(.3,.2);d.advance(.1)
    assert d.hover>.1 and d.pointer_speed>0
    d.click(.3,.2);assert d.ripple_origin[:2]==(.3,.2)
    assert sum(x*x for x in d.ripple_origin)==pytest.approx(1)
    d.wheel(200);d.advance(.1);assert 1<d.zoom<=1.25
    for _ in range(40):d.wheel(-200)
    assert d.zoom_target==.78
    d.reset();assert d.zoom_target==1 and d.yaw==0


def test_reduced_motion_keeps_explicit_input_and_freezes_decorative_time():
    d=GlobeDynamics();d.advance(.1,reduced=True);assert d.time==0
    d.drag(.1,.1);d.wheel(1);d.advance(.1,reduced=True)
    assert d.yaw>0 and d.zoom>1 and d.time==0


def test_globe_color_channels_are_strict_independent_persistent_data():
    original=AppearanceProfile();first=replace(original,globe_color='#46ceff')
    assert first.globe_glow_color==original.globe_glow_color
    second=replace(first,globe_glow_color='#ff6597')
    assert second.globe_color==first.globe_color
    assert AppearanceProfile.from_dict(second.to_dict())==second
    for value in ('red','url(secret)','#123',None):
        with pytest.raises(ValueError):replace(first,globe_color=value)
