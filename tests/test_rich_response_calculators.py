"""Interactive scenarios use real guarded model calculations and preserve stored inputs."""
import math
from types import SimpleNamespace

import pytest

from morice.kernel import CancellationToken,CancelledError
from morice.research.runtime import ResearchRuntime
from morice.rich_response import SourceRef
from morice.rich_response.calculators import calculate,recipe
from morice.rich_response.sources import ResponseSources


@pytest.fixture
def owner(tmp_path):
    research=ResearchRuntime(tmp_path/'data.db',tmp_path/'research')
    try:yield ResponseSources(SimpleNamespace(research=research),'chat'),research
    finally:research.close()


def test_parameter_change_recalculates_with_actual_units_and_preserves_saved_specification(owner):
    sources,research=owner
    row=research.laboratory.prepare({'title':'Actual unit fixture','objective':'Explore ideal additive mixture density',
        'simulation_engine':'ideal_mixture_density','parameters':{'density_a':{'value':1,'unit':'g/cm^3'},
            'density_b':{'value':2,'unit':'g/cm^3'},'fraction_a':{'value':.5,'unit':''}}})
    source=SourceRef('experiment',row['id'],scope='chat')
    definition=recipe(sources,sources.resolve(source))
    assert definition['parameters']['density_a']==pytest.approx(1000)
    assert definition['units']['density_a']=='kg/m^3'
    result=calculate(sources,source,{'fraction_a':.25})
    assert result['verified'] and result['outputs']['density']==pytest.approx(1600)
    assert result['units']['density']=='kg/m^3'
    assert research.laboratory.get(row['id'])['spec']['parameters']['fraction_a']['value']==.5
    with pytest.raises(ValueError):calculate(sources,source,{'fraction_a':2})
    with pytest.raises(ValueError):calculate(sources,source,{'made_up_input':2})
    assert not research.kernel.resources.snapshot()


def test_stored_unit_calculation_is_recomputed_as_work_without_changing_original(owner):
    sources,research=owner;project=research.create('Owned work calculation')
    recorded=research.run_recorded(project,'research.calculate',{'expression':'force*distance',
        'inputs':{'force':{'value':3,'unit':'N'},'distance':{'value':2,'unit':'m'}},'output_unit':'J'})
    source=SourceRef('research_record',project+':'+recorded['record_id'],scope='chat')
    result=calculate(sources,source,{'force':5})
    assert result['outputs']['result']==10 and result['units']['result']=='joule'


def test_strategy_results_are_actual_feasible_samples_and_energy_balances(owner):
    sources,research=owner
    from morice.research.harvester import INPUT_UNITS
    parameters={'mass':.24,'resonant_frequency':60,'frequency':60,'mechanical_q':40,'coupling':18,
        'coil_resistance':16.55,'displacement_limit':.00145,'acceleration':9.80665,'efficiency':.75,'load_resistance':-1}
    row=research.laboratory.prepare({'title':'Owned conditional harvester','objective':'Compare passive loads under supplied vibration conditions',
        'simulation_engine':'electromagnetic_harvester','parameters':{key:{'value':value,'unit':INPUT_UNITS[key]} for key,value in parameters.items()}})
    source=SourceRef('experiment',row['id'],scope='chat')
    results=[calculate(sources,source,{},strategy=strategy) for strategy in ('maximum_output','balanced','maximum_efficiency')]
    assert results[0]['outputs']['dc_potential']>=max(r['outputs']['dc_potential'] for r in results)-1e-12
    assert results[2]['outputs']['conversion_efficiency']>=max(r['outputs']['conversion_efficiency'] for r in results)-1e-12
    for result in results:
        output=result['outputs']
        assert result['verified'] and result['samples']
        assert output['relative_displacement']<=parameters['displacement_limit']*(1+1e-10)
        assert output['mechanical_input']==pytest.approx(output['mechanical_loss']+output['coil_loss']+output['ac_load_power'])
        assert 'finite load sample' in result['strategy_note']
        assert math.isfinite(output['dc_potential'])
    token=CancellationToken();token.cancel()
    with pytest.raises(CancelledError):calculate(sources,source,{},cancellation=token)
    assert not research.kernel.resources.snapshot()
