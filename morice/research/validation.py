"""Independent model equations and numerical/held-out quality checks."""
from __future__ import annotations

import cmath
import math


def verify_model(tool_id, p, output):
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
