"""Conditional calculations: independent circuit/energy and feasible-load checks."""
import math

import pytest

from morice.kernel import ExecutionContext
from morice.research.harvester import (
    chat_harvester_calculations, electromagnetic_harvester, parse_harvester_table,
)
from morice.research.runtime import ResearchRuntime
from morice.research.validation import verify_model


TABLE = '''Audit an electromagnetic vibration harvester.
| Parameter | Value |
| --- | --- |
| Moving mass | 80 g |
| Natural frequency | 50 Hz |
| Mechanical Q | 30 |
| Coupling coefficient Ke | 6 V/(m/s) |
| Coil resistance | 18 ohm |
| Maximum relative displacement | ±2 mm |
| Converter efficiency | 60% |
| External excitation | 0.1–1 g at 50 Hz |

Compare 0.1 g, 0.25 g, 0.5 g and 1 g with explicit assumptions.
'''


def parameters(**overrides):
    return dict(mass=.08, resonant_frequency=50., frequency=50., mechanical_q=30.,
                coupling=6., coil_resistance=18., displacement_limit=.002,
                acceleration=9.80665, efficiency=.6, load_resistance=-1.) | overrides


@pytest.mark.parametrize('frequency', [35., 50., 68.])
def test_optimal_passive_load_beats_independent_grid_and_conserves_energy(frequency):
    p=parameters(frequency=frequency)
    out=electromagnetic_harvester(p)
    # Direct circuit transfer function, independently swept in logarithmic load.
    w=math.tau*frequency; w0=math.tau*p['resonant_frequency']
    cm=p['mass']*w0/p['mechanical_q']; force=p['mass']*p['acceleration']
    for exponent in range(-40, 161):
        load=10**(exponent/40)
        v=force/complex(cm+p['coupling']**2/(p['coil_resistance']+load),
                        p['mass']*w-p['mass']*w0*w0/w)
        if abs(v)/w<=p['displacement_limit']:
            ac=.5*abs(p['coupling']*v/(p['coil_resistance']+load))**2*load
            assert out['ac_load_power']>=ac*(1-1e-10)
    assert out['mechanical_input']==pytest.approx(out['mechanical_loss']+out['coil_loss']+out['ac_load_power'])
    assert 0<=out['dc_potential']<=out['ac_load_power']<=out['mechanical_input']
    assert verify_model('electromagnetic_harvester',p,out)[0]
    if frequency==50:
        assert out['load_resistance']==pytest.approx(p['coil_resistance']+p['coupling']**2/cm)
        assert out['relative_displacement']>out['base_displacement']


def test_travel_changes_load_and_infeasible_case_is_rejected():
    p=parameters(displacement_limit=.001)
    out=electromagnetic_harvester(p)
    assert out['travel_limited']==1
    assert out['relative_displacement']==pytest.approx(.001)
    assert verify_model('electromagnetic_harvester',p,out)[0]
    with pytest.raises(ValueError,match='fixed load'):
        electromagnetic_harvester(p|{'load_resistance':1000.})
    with pytest.raises(ValueError,match='short circuit'):
        electromagnetic_harvester(p|{'acceleration':1000.})


def test_zero_excitation_and_invalid_inputs():
    assert electromagnetic_harvester(parameters(acceleration=0.))['mechanical_input']==0
    for updates in ({'mechanical_q':0.},{'efficiency':1.1},{'acceleration':-1.},
                    {'coupling':float('nan')},{'load_resistance':-2.}):
        with pytest.raises(ValueError):electromagnetic_harvester(parameters(**updates))


def test_verifier_rejects_wrong_power_and_consistent_nonoptimal_load():
    p=parameters();out=electromagnetic_harvester(p)
    assert not verify_model('electromagnetic_harvester',p,out|{'dc_potential':10.})[0]
    assert not verify_model('electromagnetic_harvester',p,out|{'travel_limited':2.})[0]
    wrong=electromagnetic_harvester(p|{'load_resistance':1.})
    assert not verify_model('electromagnetic_harvester',p,wrong)[0]


def test_parser_converts_units_and_requires_one_unambiguous_complete_table():
    spec=parse_harvester_table(TABLE)
    assert spec['parameters']['mass']==pytest.approx(.08)
    assert spec['parameters']['coupling']==6
    assert spec['parameters']['displacement_limit']==pytest.approx(.002)
    assert spec['parameters']['efficiency']==pytest.approx(.6)
    assert spec['accelerations_g']==[.1,.25,.5,1]
    assert not spec['rms'] and not spec['frequency_assumed']
    for invalid in (TABLE.replace('80 g','80 nonsense_unit'), TABLE.replace('80 g','80 Hz'),
                    TABLE.replace('Mechanical Q','Loaded Q'), TABLE+'\n'+TABLE,
                    TABLE.replace('| Coil resistance | 18 ohm |','')):
        assert parse_harvester_table(invalid) is None
    assert parse_harvester_table('Explain harvester damping.') is None


def test_verified_kernel_report_rms_and_failed_case(tmp_path):
    runtime=ResearchRuntime(tmp_path/'research.db',tmp_path/'research')
    try:
        report=chat_harvester_calculations(TABLE,runtime,ExecutionContext())
        rms=chat_harvester_calculations(TABLE.replace('Compare','RMS acceleration: compare'),runtime,ExecutionContext())
        assert 'UNLOADED MECHANICAL' in report and '| 0.25 |' in report
        assert 'Their sum equals mechanical input' in report
        assert 'Illustrative detuning' in report and 'not a measurement or FEM' in report
        assert 'RMS, converted to peak' in rms and rms!=report
        assert '\n\n| ---' not in report
        failed=chat_harvester_calculations(TABLE.replace('1 g with','100 g with'),runtime,ExecutionContext())
        assert '| 100 | Infeasible/unverified' in failed
        assert 'No clipped-power prediction' in failed
    finally:runtime.close()
