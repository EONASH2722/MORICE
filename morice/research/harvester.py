"""Linear electromagnetic harvester calculation, with explicit conditional inputs.

The resistive-load model includes coil loss and electromagnetic back-reaction.
It is not a magnetic-field, converter, nonlinear-impact or fabrication solver.
See https://doi.org/10.3390/mi10120826 for the coupling/load relationship.
"""
from __future__ import annotations

import math
import re


INPUT_UNITS = {
    'mass':'kg', 'resonant_frequency':'Hz', 'frequency':'Hz',
    'mechanical_q':'', 'coupling':'V*s/m', 'coil_resistance':'ohm',
    'displacement_limit':'m', 'acceleration':'m/s^2', 'efficiency':'',
    'load_resistance':'ohm',
}
OUTPUT_UNITS = {
    'load_resistance':'ohm', 'mechanical_damping':'N*s/m',
    'electrical_damping':'N*s/m', 'loaded_q':'',
    'base_displacement':'m', 'relative_displacement':'m',
    'velocity_amplitude':'m/s', 'emf_peak':'V', 'load_voltage_peak':'V',
    'mechanical_input':'W', 'mechanical_loss':'W', 'coil_loss':'W',
    'ac_load_power':'W', 'dc_potential':'W', 'conversion_efficiency':'',
    'travel_limited':'',
}


def electromagnetic_harvester(p):
    positive=('mass','resonant_frequency','frequency','mechanical_q','coupling',
              'coil_resistance','displacement_limit')
    if any(not math.isfinite(p[key]) for key in INPUT_UNITS):
        raise ValueError('Harvester inputs must be finite.')
    if any(p[key]<=0 for key in positive) or p['acceleration']<0 or not 0<=p['efficiency']<=1:
        raise ValueError('Positive mass, frequency, Q, coupling, coil resistance and travel are required; acceleration and efficiency must be nonnegative.')
    if p['load_resistance']<0 and p['load_resistance']!=-1:
        raise ValueError('Load must be nonnegative, or -1 to optimize a passive resistive load.')
    m,ke,rc=p['mass'],p['coupling'],p['coil_resistance']
    w,w0=math.tau*p['frequency'],math.tau*p['resonant_frequency']
    cm=m*w0/p['mechanical_q']; k=m*w0*w0; force=m*p['acceleration']
    detuning=k-m*w*w
    auto=p['load_resistance']==-1
    load=(math.sqrt(rc*rc+(w*w*ke**4+2*w*w*cm*ke*ke*rc)/(detuning*detuning+w*w*cm*cm))
          if auto else p['load_resistance'])
    ce=ke*ke/(rc+load)
    x=force/math.hypot(detuning,w*(cm+ce))
    limited=False
    if x>p['displacement_limit']*(1+1e-12):
        if not auto:
            raise ValueError('Infeasible: the specified fixed load exceeds the relative travel limit in this linear model.')
        required=math.sqrt(max(0,(force/p['displacement_limit'])**2-detuning**2))/w-cm
        if required>ke*ke/rc*(1+1e-12):
            raise ValueError('Infeasible: even a short circuit cannot keep the specified excitation within the travel limit. No clipped-power prediction is supplied.')
        ce=max(ce,required);load=max(0,ke*ke/ce-rc)
        x=force/math.hypot(detuning,w*(cm+ce));limited=True
    velocity=w*x;current=ke*velocity/(rc+load)
    mechanical_loss=.5*cm*velocity**2
    coil_loss=.5*current**2*rc;ac=.5*current**2*load
    mechanical_input=mechanical_loss+coil_loss+ac
    dc=p['efficiency']*ac
    return {'load_resistance':load,'mechanical_damping':cm,'electrical_damping':ce,
            'loaded_q':m*w0/(cm+ce),'base_displacement':p['acceleration']/w**2,
            'relative_displacement':x,'velocity_amplitude':velocity,
            'emf_peak':ke*velocity,'load_voltage_peak':current*load,
            'mechanical_input':mechanical_input,'mechanical_loss':mechanical_loss,
            'coil_loss':coil_loss,'ac_load_power':ac,'dc_potential':dc,
            'conversion_efficiency':dc/mechanical_input if mechanical_input else 0,
            'travel_limited':float(limited)}


_LABELS={
    'mass':r'^(?:moving (?:magnetic assembly|mass)|proof mass|inertial mass|mass)$',
    'resonant_frequency':r'^(?:resonant|natural|resonance) frequency$',
    'mechanical_q':r'^(?:mechanical quality factor(?: q)?|mechanical q|quality factor(?: q)?|q)$',
    'coupling':r'^(?:total )?(?:electromagnetic )?coupling(?: coefficient| constant)?(?: ke| k)?$',
    'coil_resistance':r'^(?:combined |total )?coil resistance$',
    'displacement_limit':r'^(?:maximum relative displacement|relative displacement limit|peak relative displacement|displacement limit)$',
    'efficiency':r'^(?:assumed )?(?:ac[- ]to[- ]dc|conversion|converter) efficiency$',
}
_NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def parse_harvester_table(text):
    """Accept one complete labelled parameter table; never guess from history."""
    if not isinstance(text,str) or len(text)>50000 or not re.search(r'\b(?:harvest\w*|electromagnetic)\b',text,re.I):
        return None
    blocks=[];block=[]
    for line in text.splitlines()+['']:
        if line.strip().startswith('|'):
            block.append(line)
        elif block:
            blocks.append(block);block=[]
    candidates=[]
    for lines in blocks:
        values={};extras={};duplicate=False
        for line in lines:
            cells=[c.strip().strip('*') for c in line.strip().strip('|').split('|')]
            if len(cells)!=2:continue
            label=' '.join(cells[0].casefold().replace('–','-').replace('−','-').split())
            key=next((k for k,pattern in _LABELS.items() if re.fullmatch(pattern,label)),None)
            if key:
                if key in values:duplicate=True
                values[key]=cells[1]
            elif re.fullmatch(r'(?:external |base )?excitation(?: frequency)?|acceleration',label):
                extras[label]=cells[1]
        if not duplicate and set(values)==set(_LABELS):candidates.append((values,extras))
    if len(candidates)!=1:return None
    cells,extras=candidates[0];parameters={}
    from .tools import ScientificTools
    units=ScientificTools()
    for key,cell in cells.items():
        cleaned=cell.replace('±','').replace('+/-','').replace('Ω','ohm').replace('–','-').strip()
        match=re.fullmatch(r'('+_NUMBER+r')\s*(.*?)',cleaned)
        if not match:return None
        value=float(match[1]);unit=match[2].strip()
        if key=='efficiency' and unit=='%':value/=100;unit=''
        if key=='mechanical_q' and unit:return None
        try:parameters[key]=units.calculate('x',{'x':{'value':value,'unit':unit}},INPUT_UNITS[key])['result']['value']
        except (ValueError,TypeError,ArithmeticError,AttributeError,LookupError,ImportError):return None
    if any(not math.isfinite(v) or v<=0 for k,v in parameters.items() if k!='efficiency') or not 0<=parameters['efficiency']<=1:return None
    lists=[]
    for line in text.splitlines():
        matches=re.findall(r'('+_NUMBER+r')\s*g\b',line,re.I)
        if 2<=len(matches)<=16:lists.append(([float(v) for v in matches],line))
    excitation=' '.join(extras.values())
    if lists:
        accelerations,convention=max(lists,key=lambda item:len(item[0]))
    else:
        match=re.search(r'('+_NUMBER+r')\s*[-–]\s*('+_NUMBER+r')\s*g\b',excitation,re.I)
        if not match:return None
        accelerations=[float(match[1]),float(match[2])];convention=excitation
    if not all(math.isfinite(a) and 0<=a<=1000 for a in accelerations):return None
    frequency=re.search(r'('+_NUMBER+r')\s*Hz\b',excitation,re.I)
    parameters['frequency']=float(frequency[1]) if frequency else parameters['resonant_frequency']
    parameters['load_resistance']=-1.0
    return {'parameters':parameters,'accelerations_g':sorted(set(accelerations)),
            'rms':bool(re.search(r'\brms\b',convention+' '+excitation,re.I)),
            'frequency_assumed':frequency is None}


def chat_harvester_calculations(text,runtime,context,*,parsed=None):
    """Ground a matching chat request using the existing verified capability."""
    spec=parsed if parsed is not None else parse_harvester_table(text)
    if spec is None:return None
    from ..kernel import VerificationStatus
    parameters=spec['parameters'];rows=[];errors=[]
    for acceleration in spec['accelerations_g']:
        values={**parameters,'acceleration':acceleration*9.80665*(math.sqrt(2) if spec['rms'] else 1)}
        result=runtime.execute('research.simulate',{'tool_id':'electromagnetic_harvester','parameters':values},context=context)
        if result.success and result.verification and result.verification.status==VerificationStatus.VERIFIED:
            rows.append((acceleration,result.output['outputs'],None))
        else:
            error='; '.join(e.message+': '+e.detail for e in result.errors) or 'Independent calculation verification failed.'
            rows.append((acceleration,None,error))
    lines=['Calculated baseline (conditional analytical model)',
        'Q is treated as the UNLOADED MECHANICAL quality factor. Excitation values are '+('RMS, converted to peak internally.' if spec['rms'] else 'PEAK sinusoidal base acceleration; RMS values would differ.'),
        ('Excitation frequency is assumed equal to the supplied resonant frequency.' if spec['frequency_assumed'] else f"Excitation frequency: {parameters['frequency']:g} Hz."),
        'The model includes mechanical damping, electromagnetic back-reaction, coil loss and a passive resistive load. Input energy is supplied by the imposed base vibration.',
        'Equations: m*z_ddot+(c_m+c_e)*z_dot+k*z=-m*y_ddot; c_m=m*omega_0/Q_m; c_e=Ke^2/(R_coil+R_load); P_load=I_peak^2*R_load/2. At resonance the unconstrained optimum is R_load=R_coil+Ke^2/c_m.',
        '| Vibration (g) | Mechanical input (mW) | Load AC (mW) | Potential DC (mW) | DC/input (%) | DC (J/min) | Relative peak (mm) |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for acceleration,row,error in rows:
        if row is None:
            lines.append(f'| {acceleration:g} | Infeasible/unverified | — | — | — | — | — |')
            errors.append(f'{acceleration:g} g: {error}')
        else:
            lines.append(f"| {acceleration:g} | {row['mechanical_input']*1000:.4g} | {row['ac_load_power']*1000:.4g} | {row['dc_potential']*1000:.4g} | {row['conversion_efficiency']*100:.4g} | {row['dc_potential']*60:.4g} | {row['relative_displacement']*1000:.4g} |")
    valid=[(a,r) for a,r,_ in rows if r is not None]
    lines.extend(errors)
    if valid:
        acceleration,row=valid[-1]
        lines.append(f"At {acceleration:g} g: R_load={row['load_resistance']:.6g} ohm; loaded Q={row['loaded_q']:.6g}; base peak displacement={row['base_displacement']*1000:.6g} mm; relative peak displacement={row['relative_displacement']*1000:.6g} mm; load voltage peak={row['load_voltage_peak']:.6g} V. Base motion and relative resonant motion are different quantities.")
        lines.append(f"Mechanical loss={row['mechanical_loss']*1000:.6g} mW; coil loss={row['coil_loss']*1000:.6g} mW; load power={row['ac_load_power']*1000:.6g} mW. Their sum equals mechanical input.")
        lines += ['Illustrative detuning at the largest feasible excitation, holding its load resistance fixed:',
                  '| Frequency (Hz) | Potential DC (mW) | Relative peak (mm) |',
                  '| --- | --- | --- |']
        for ratio in (.9,.95,1.,1.05,1.1):
            frequency=parameters['resonant_frequency']*ratio
            values={**parameters,'frequency':frequency,'load_resistance':row['load_resistance'],
                    'acceleration':acceleration*9.80665*(math.sqrt(2) if spec['rms'] else 1)}
            result=runtime.execute('research.simulate',{'tool_id':'electromagnetic_harvester','parameters':values},context=context)
            if result.success and result.verification and result.verification.status==VerificationStatus.VERIFIED:
                point=result.output['outputs']
                lines.append(f"| {frequency:.6g} | {point['dc_potential']*1000:.4g} | {point['relative_displacement']*1000:.4g} |")
            else:lines.append(f'| {frequency:.6g} | Infeasible/unverified | — |')
    lines += [
        'Travel limits are enforced by changing the passive load where feasible; an impossible linear case is marked infeasible rather than clipped to an invented output.',
        'Potential DC applies only the supplied conversion-efficiency assumption. Converter startup and quiescent draw are unspecified, so actual net usable power can be anywhere from zero to that value.',
        'Without measured losses, a conservative guaranteed output is zero. The table is the conditional nominal case. Its AC load-power column is also an ideal-converter DC ceiling, not an experimentally justified optimistic prediction.',
        'This is not a measurement or FEM result. It assumes linear motion, constant coupling, negligible coil inductance and maintained base excitation. A supplied coupling constant cannot be declared impossible from its magnitude alone; geometry and flux-gradient measurements/FEM are still required.',
        'If the supplied Q is already the loaded Q, these numbers must not be combined with the same Q as mechanical damping; unloaded damping must be measured or identified.',
        'Reference for the model/coupling relationship: https://doi.org/10.3390/mi10120826 (Mösch and Fischerauer, 2019). It does not experimentally validate this proposed device.',
    ]
    report=[];previous_table=False
    for line in lines:
        table=line.startswith('|')
        report.append(('\n' if table and previous_table else '\n\n')+line)
        previous_table=table
    return ''.join(report).strip()
