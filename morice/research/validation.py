"""Independent model equations and numerical/held-out quality checks."""
from __future__ import annotations

import cmath
import math


def verify_model(tool_id, p, output):
    if tool_id == 'electromagnetic_harvester':
        # Independent force/velocity impedance and circuit phasors, rather
        # than repeating the scalar displacement calculation in the adapter.
        from .harvester import OUTPUT_UNITS
        if set(output)!=set(OUTPUT_UNITS):return False,'Unexpected harvester output fields.'
        w=math.tau*p['frequency'];w0=math.tau*p['resonant_frequency']
        cm=p['mass']*w0/p['mechanical_q'];load=output['load_resistance']
        if not math.isfinite(load) or load<0:return False,'Invalid passive load.'
        if output['travel_limited'] not in (0,1):return False,'Invalid travel-limit flag.'
        ce=p['coupling']**2/(p['coil_resistance']+load)
        force=p['mass']*p['acceleration']
        velocity=force/complex(cm+ce,p['mass']*w-p['mass']*w0*w0/w)
        current=p['coupling']*velocity/(p['coil_resistance']+load)
        power_in=.5*(force*velocity.conjugate()).real
        mechanical=.5*cm*abs(velocity)**2;coil=.5*abs(current)**2*p['coil_resistance']
        ac=.5*abs(current)**2*load;dc=p['efficiency']*ac
        expected={'load_resistance':load,'mechanical_damping':cm,'electrical_damping':ce,
            'loaded_q':p['mass']*w0/(cm+ce),'base_displacement':p['acceleration']/w**2,
            'relative_displacement':abs(velocity)/w,'velocity_amplitude':abs(velocity),
            'emf_peak':p['coupling']*abs(velocity),'load_voltage_peak':abs(current)*load,
            'mechanical_input':power_in,'mechanical_loss':mechanical,'coil_loss':coil,
            'ac_load_power':ac,'dc_potential':dc,'conversion_efficiency':dc/power_in if power_in else 0,
            'travel_limited':output['travel_limited']}
        valid=all(type(output[k]) in (int,float) and math.isfinite(output[k]) and math.isclose(output[k],v,rel_tol=1e-9,abs_tol=1e-14) for k,v in expected.items())
        valid=valid and abs(velocity)/w<=p['displacement_limit']*(1+1e-9)
        valid=valid and math.isclose(power_in,mechanical+coil+ac,rel_tol=1e-9,abs_tol=1e-14)
        if p['load_resistance']>=0:valid=valid and math.isclose(load,p['load_resistance'])
        if output['travel_limited']:valid=valid and math.isclose(abs(velocity)/w,p['displacement_limit'],rel_tol=1e-8)
        if p['load_resistance']==-1 and force:
            # Check local optimality using feasible neighbouring impedances.
            # Passive-load power is unimodal; the feasible set ends at travel.
            for neighbour in (max(0,load-max(1,load)*1e-4),load+max(1,load)*1e-4):
                trial=force/complex(cm+p['coupling']**2/(p['coil_resistance']+neighbour),
                    p['mass']*w-p['mass']*w0*w0/w)
                if abs(trial)/w<=p['displacement_limit']*(1+1e-12):
                    trial_power=.5*abs(p['coupling']*trial/(p['coil_resistance']+neighbour))**2*neighbour
                    valid=valid and trial_power<=ac*(1+1e-10)+1e-15
        return bool(valid),'Independent mechanical/electrical phasors, energy balance and relative travel checked; physical assumptions are unverified.'
    if tool_id == "linear_oscillator":
        w = math.tau*p["frequency"]
        a = abs(p["force"]/complex(p["stiffness"]-p["mass"]*w*w, p["damping"]*w))
        expected = {"amplitude": a, "velocity_amplitude": w*a, "mean_dissipated_power": .5*p["damping"]*w*w*a*a}
    elif tool_id == "thermal_expansion":
        expected = {"expansion_a": p["length"]*p["temperature_change"]*p["alpha_a"],
                    "expansion_b": p["length"]*p["temperature_change"]*p["alpha_b"],
                    "differential_expansion": p["length"]*p["temperature_change"]*(p["alpha_a"]-p["alpha_b"])}
    elif tool_id == "ideal_mixture_density":
        expected = {"density": p["density_a"]*p["density_b"]/(p["fraction_a"]*p["density_b"]+(1-p["fraction_a"])*p["density_a"])}
    elif tool_id == "vacuum_particle":
        t = p["duration"]
        speed_sq = sum((p[v]+p[a]*t)**2 for v,a in (("vx","ax"),("vy","ay")))
        expected = {"x": p["x0"]+t*(p["vx"]+p["ax"]*t/2), "y": p["y0"]+t*(p["vy"]+p["ay"]*t/2),
                    "speed": math.sqrt(speed_sq), "kinetic_energy": p["mass"]*speed_sq/2}
    else:
        return False, "No independent validation contract for this model."
    valid = set(output) == set(expected) and all(type(output[k]) in (int,float) and math.isfinite(output[k]) and math.isclose(output[k], v, rel_tol=1e-9, abs_tol=1e-14) for k,v in expected.items())
    return valid, "Independent equations, finite values and exact output fields; model assumptions remain user responsibilities."


def convergence(values, tolerance):
    if len(values) < 3 or len(values) > 12 or tolerance <= 0 or not all(math.isfinite(v) for v in [*values, tolerance]):
        raise ValueError("Need 3–12 coarse-to-fine values and positive finite absolute tolerance.")
    differences = [abs(b-a) for a,b in zip(values, values[1:])]
    return {"converged": differences[-1] <= tolerance and differences[-1] <= differences[-2],
            "differences": differences, "tolerance": tolerance, "scope": "Successive refinement only; not physical validation."}


def calibration(training_x, training_y, validation_x, validation_y):
    import numpy as np
    from .laboratory import compare_measurements
    if not training_x or not validation_x or len(training_x) != len(training_y) or len(validation_x) != len(validation_y):
        raise ValueError("Separate aligned calibration and validation data are required.")
    if len(training_x) > 10000 or len(validation_x) > 10000 or len(training_x) < 2 or len(set(training_x)) < 2:
        raise ValueError("Calibration needs 2–10,000 nonconstant observations.")
    if set(training_x) & set(validation_x):
        raise ValueError("Held-out x identifiers overlap calibration data; no independent validation claimed.")
    if not all(math.isfinite(v) for v in [*training_x,*training_y,*validation_x,*validation_y]):
        raise ValueError("Calibration data must be finite.")
    slope, intercept = np.linalg.lstsq(np.column_stack((training_x,np.ones(len(training_x)))), training_y, rcond=None)[0]
    predicted = (slope*np.asarray(validation_x)+intercept).tolist()
    return {"slope": float(slope), "intercept": float(intercept), "validation": compare_measurements(predicted, validation_y),
            "calibration_samples": len(training_x), "validation_samples": len(validation_x), "method": "NumPy linear least squares with disjoint held-out x identifiers",
            "limitations": "Linear model; user must review sampling/design and consistent units. No clinical validation."}
