"""Interactive inputs call existing deterministic Research capabilities."""
from __future__ import annotations

import math
import time

from ..kernel import CancellationToken,ExecutionContext


STRATEGIES=('maximum_output','balanced','maximum_efficiency')


def recipe(owner,snapshot):
    source=snapshot.source;research=owner.runtime.research
    if source.kind=='experiment':
        spec=snapshot.data['spec'];tool=research.simulations.get(spec['simulation_engine'])
        parameters={key:research.simulations.quantity(spec['parameters'][key],unit) for key,unit in tool.required_units.items()}
        return {'capability':'research.simulate','tool_id':tool.tool_id,'parameters':parameters,'units':tool.required_units,
            'output_units':tool.supported_outputs,'limitations':tool.limitations}
    if source.kind=='chat_calculation':
        from ..research.harvester import INPUT_UNITS,OUTPUT_UNITS
        spec=snapshot.data['specification'];parameters=dict(spec['parameters'])
        parameters['acceleration']=max(spec['accelerations_g'])*9.80665*(math.sqrt(2) if spec['rms'] else 1)
        return {'capability':'research.simulate','tool_id':'electromagnetic_harvester','parameters':parameters,
            'units':INPUT_UNITS,'output_units':OUTPUT_UNITS,'limitations':snapshot.limitation}
    if source.kind=='research_record' and snapshot.data.get('method')=='research.calculate':
        inputs=snapshot.data['inputs']
        if not isinstance(inputs.get('inputs'),dict) or not isinstance(inputs.get('expression'),str):raise ValueError('Stored calculation has no editable input contract.')
        return {'capability':'research.calculate','expression':inputs['expression'],
            'parameters':{key:value['value'] for key,value in inputs['inputs'].items()},
            'units':{key:value.get('unit','') for key,value in inputs['inputs'].items()},
            'output_unit':inputs.get('output_unit',''),'limitations':'Supplied equation and quantities; dimensional validity does not establish physical accuracy.'}
    raise ValueError('This source has no implemented deterministic calculator binding.')


def calculate(owner,source,changes,*,strategy='',cancellation=None):
    snapshot=owner.resolve(source);definition=recipe(owner,snapshot)
    if not isinstance(changes,dict) or set(changes)-definition['parameters'].keys():raise ValueError('Change only actual parameters of this source model.')
    if any(type(value) not in (int,float) or not math.isfinite(value) or abs(value)>1e12 for value in changes.values()):
        raise ValueError('Calculator inputs must be finite and within model magnitude limits.')
    parameters={**definition['parameters'],**changes};token=cancellation or CancellationToken()
    context=ExecutionContext(conversation_id=owner.conversation_id,cancellation_token=token)
    started=time.perf_counter()

    def execute(values):
        token.raise_if_cancelled()
        args=({'tool_id':definition['tool_id'],'parameters':values} if definition['capability']=='research.simulate' else
            {'expression':definition['expression'],'inputs':{key:{'value':value,'unit':definition['units'][key]} for key,value in values.items()},
                'output_unit':definition['output_unit']})
        result=owner.runtime.research.execute(definition['capability'],args,context=context)
        if not result.success or not result.verification or result.verification.status.value!='verified':
            raise ValueError('; '.join(error.message for error in result.errors) or 'The actual calculation did not verify.')
        if definition['capability']=='research.simulate':return result.output['outputs'],result.output['units']
        return {'result':result.output['result']['value']},{'result':result.output['result']['unit']}

    samples=[]
    if strategy:
        if strategy not in STRATEGIES or definition.get('tool_id')!='electromagnetic_harvester':
            raise ValueError('That strategy selector is unavailable for this source model.')
        rc=parameters['coil_resistance']
        if rc<=0:raise ValueError('Coil resistance must be positive before sampling loads.')
        # These are finite candidates under the SAME supplied conditions, not
        # new device variants or promises of global/hardware optimality.
        loads=[rc*10**(-2+5*index/60) for index in range(61)]
        try:
            optimum,_=execute({**parameters,'load_resistance':-1})
            loads.append(optimum['load_resistance'])
        except ValueError:pass
        for load in sorted(set(loads)):
            token.raise_if_cancelled()
            try:outputs,units=execute({**parameters,'load_resistance':load})
            except ValueError:continue  # Explicitly infeasible candidates are not clipped.
            samples.append({'load_resistance':load,**outputs})
        if not samples:raise ValueError('No feasible sampled passive load meets this model’s displacement limits.')
        maximum_power=max(row['dc_potential'] for row in samples)
        maximum_efficiency=max(row['conversion_efficiency'] for row in samples)
        def score(row):
            if strategy=='maximum_output':return row['dc_potential']
            if strategy=='maximum_efficiency':return row['conversion_efficiency']
            return .5*(row['dc_potential']/maximum_power if maximum_power else 0)+.5*(row['conversion_efficiency']/maximum_efficiency if maximum_efficiency else 0)
        outputs=max(samples,key=score)
        parameters['load_resistance']=outputs['load_resistance']
        units=definition['output_units']
    else:outputs,units=execute(parameters)
    return {'parameters':parameters,'outputs':outputs,'units':units,'strategy':strategy,'samples':samples,
        'verified':True,'provenance':'SIMULATED' if definition['capability']=='research.simulate' else 'CALCULATED',
        'elapsed_ms':(time.perf_counter()-started)*1000,'limitations':definition['limitations'],
        'strategy_note':('Best feasible candidate in the displayed finite load sample. Balanced = equal weights on normalized DC and normalized efficiency. '
            'Minimum mechanical input per recovered joule has the same objective as maximum conversion efficiency here, not a separate invented operating point.' if strategy else '')}
