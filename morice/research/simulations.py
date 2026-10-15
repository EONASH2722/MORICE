"""Small, explicitly bounded scientific models; no pretend external solvers."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .tools import ScientificTools


@dataclass(frozen=True)
class SimulationTool:
    tool_id: str
    domains: tuple[str, ...]
    required_units: dict[str, str]
    supported_outputs: dict[str, str]
    limitations: str
    method: str
    evaluate: object
    version: str = "1"
    cpu: bool = True
    gpu: bool = False


def oscillator(p):
    if min(p["mass"], p["stiffness"], p["damping"]) <= 0 or p["frequency"] < 0 or p["force"] < 0:
        raise ValueError("Mass, stiffness and damping must be positive; frequency and force nonnegative.")
    omega = 2 * math.pi * p["frequency"]
    amplitude = p["force"] / math.hypot(p["stiffness"] - p["mass"] * omega**2, p["damping"] * omega)
    return {"amplitude": amplitude, "velocity_amplitude": omega * amplitude,
            "mean_dissipated_power": p["damping"] * (omega * amplitude)**2 / 2}


def thermal(p):
    if p["length"] <= 0 or abs(p["alpha_a"] * p["temperature_change"]) > .05 or abs(p["alpha_b"] * p["temperature_change"]) > .05:
        raise ValueError("Positive length and small thermal strain (at most 5%) required by this approximation.")
    a = p["length"] * p["alpha_a"] * p["temperature_change"]
    b = p["length"] * p["alpha_b"] * p["temperature_change"]
    return {"expansion_a": a, "expansion_b": b, "differential_expansion": a - b}


def mixture(p):
    if min(p["density_a"], p["density_b"]) <= 0 or not 0 <= p["fraction_a"] <= 1:
        raise ValueError("Positive component densities and a mass fraction in [0,1] are required.")
    return {"density": 1 / (p["fraction_a"] / p["density_a"] + (1 - p["fraction_a"]) / p["density_b"])}


def particle(p):
    if p["mass"] <= 0 or not 0 <= p["duration"] <= 3600:
        raise ValueError("Positive mass and duration from 0 to 3600 seconds are required.")
    t = p["duration"]
    vx, vy = p["vx"] + p["ax"] * t, p["vy"] + p["ay"] * t
    # Fixed analytic model: no material collisions, radiation or relativistic physics.
    if math.hypot(vx, vy) > 3e6 or math.hypot(p["vx"], p["vy"]) > 3e6:
        raise ValueError("Velocity exceeds this nonrelativistic model's conservative limit.")
    return {"x": p["x0"] + p["vx"] * t + .5 * p["ax"] * t*t,
            "y": p["y0"] + p["vy"] * t + .5 * p["ay"] * t*t,
            "speed": math.hypot(vx, vy), "kinetic_energy": .5 * p["mass"] * (vx*vx + vy*vy)}


class SimulationToolRegistry:
    def __init__(self):
        self.tools = {}
        self.quantities = ScientificTools()
        self.register(SimulationTool(
            "linear_oscillator", ("mechanics",),
            {"mass": "kg", "stiffness": "N/m", "damping": "N*s/m", "force": "N", "frequency": "Hz"},
            {"amplitude": "m", "velocity_amplitude": "m/s", "mean_dissipated_power": "W"},
            "Linear steady-state sinusoidal forcing; positive viscous damping; no transient, nonlinear, electrical or structural-stress model.",
            "A=F/sqrt((k-m*(2*pi*f)^2)^2+(c*2*pi*f)^2)", oscillator))
        self.register(SimulationTool(
            "thermal_expansion", ("thermal", "materials"),
            {"length": "m", "alpha_a": "1/K", "alpha_b": "1/K", "temperature_change": "K"},
            {"expansion_a": "m", "expansion_b": "m", "differential_expansion": "m"},
            "Unconstrained linear expansion with user-supplied constant coefficients; small strains only. Not a chemical, corrosion or structural compatibility score.",
            "delta_L=alpha*L*delta_T", thermal))
        self.register(SimulationTool(
            "ideal_mixture_density", ("materials",),
            {"density_a": "kg/m^3", "density_b": "kg/m^3", "fraction_a": ""}, {"density": "kg/m^3"},
            "Ideal additive volumes, specified mass fraction and constant densities only. No reaction, miscibility, phase, solubility or safety prediction.",
            "rho=1/(w/rho_a+(1-w)/rho_b)", mixture))
        self.register(SimulationTool(
            "vacuum_particle", ("classical_mechanics",),
            {"mass": "kg", "x0": "m", "y0": "m", "vx": "m/s", "vy": "m/s", "ax": "m/s^2", "ay": "m/s^2", "duration": "s"},
            {"x": "m", "y": "m", "speed": "m/s", "kinetic_energy": "J"},
            "Single classical point particle under constant acceleration in vacuum. No material target, impact, penetration, scattering, radiation, drag or relativity.",
            "r(t)=r0+v0*t+a*t^2/2; v(t)=v0+a*t", particle))

    def register(self, tool):
        if tool.tool_id in self.tools:
            raise ValueError("Duplicate simulation tool identifier.")
        self.tools[tool.tool_id] = tool

    def get(self, tool_id):
        if tool_id not in self.tools:
            raise ValueError(f"Simulation tool {tool_id!r} is not integrated. No result has been generated.")
        return self.tools[tool_id]

    def quantity(self, item, unit):
        if not isinstance(item, dict) or "value" not in item or "unit" not in item:
            raise ValueError("Parameters require explicit value and unit fields (use an empty unit for a fraction).")
        value = self.quantities.calculate("x", {"x": item}, unit)["result"]["value"]
        if abs(value) > 1e12:
            raise ValueError("Input exceeds this local laboratory's magnitude limit.")
        return value

    def run(self, tool_id, parameters):
        tool = self.get(tool_id)
        if set(parameters) != set(tool.required_units):
            raise ValueError("Simulation parameters do not match the selected tool.")
        if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v)>1e12 for v in parameters.values()):
            raise ValueError("Simulation inputs must be finite numbers in the tool's declared units.")
        result = tool.evaluate(parameters)
        if set(result) != set(tool.supported_outputs) or any(not math.isfinite(v) or abs(v) > 1e100 for v in result.values()):
            raise ValueError("Simulation returned invalid outputs; result rejected.")
        return result

    def available(self):
        # These adapters are executable local Python models, not a list of installed product names.
        return [{"tool_id": t.tool_id, "version": t.version, "domains": t.domains,
                 "inputs": t.required_units, "outputs": t.supported_outputs, "cpu": True, "gpu": False,
                 "availability": "AVAILABLE", "method": t.method, "limitations": t.limitations} for t in self.tools.values()]

    def fingerprint(self, tool_id):
        """Invalidate saved plans when model implementation or declared contracts change."""
        import hashlib
        import json
        import types
        import platform
        from importlib.metadata import version
        from .experiments import ExperimentCompiler
        def constant(value):
            if isinstance(value,types.CodeType):return signature(value)
            if isinstance(value,frozenset):return {"frozenset":sorted(constant(v) for v in value)}
            if isinstance(value,tuple):return [constant(v) for v in value]
            return repr(value)
        def signature(code):
            return {"bytecode":code.co_code.hex(),"names":code.co_names,"arguments":code.co_varnames,
                    "constants":[constant(c) for c in code.co_consts]}
        tool=self.get(tool_id)
        data={"code":signature(tool.evaluate.__code__),"version":tool.version,"method":tool.method,
              "inputs":tool.required_units,"outputs":tool.supported_outputs,
              "python":platform.python_version(),"pint":version('pint'),
              "normalization":signature(ScientificTools._calculate.__code__),
              "compiler":[signature(m.__code__) for m in (ExperimentCompiler.compile,ExperimentCompiler.plan,ExperimentCompiler._natural)]}
        return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def particle_trajectory(parameters, *, steps=100, method="analytic", cancel=None):
    from .ingestion import checkpoint
    if type(steps) is not int or not 2<=steps<=4096 or method not in {"analytic","euler"}:
        raise ValueError("Trajectory needs 2–4096 steps with analytic or Euler method.")
    particle(parameters)  # Validate endpoints and nonrelativistic bounds.
    duration=parameters["duration"]
    dt=duration/steps
    x,y,vx,vy=(parameters[k] for k in ("x0","y0","vx","vy"))
    rows=[]
    for i in range(steps+1):
        checkpoint(cancel)
        t=i*dt
        if method=="analytic":
            state=particle({**parameters,"duration":t})
        else:
            state={"x":x,"y":y,"speed":math.hypot(vx,vy),"kinetic_energy":parameters["mass"]*(vx*vx+vy*vy)/2}
        rows.append({"time":t,**state})
        x,y,vx,vy=x+vx*dt,y+vy*dt,vx+parameters["ax"]*dt,vy+parameters["ay"]*dt
    exact=particle(parameters)
    return {"rows":rows,"position_error_m":math.hypot(rows[-1]["x"]-exact["x"],rows[-1]["y"]-exact["y"]),
            "steps":steps,"method":method,"units":{"time":"s","x":"m","y":"m","speed":"m/s","kinetic_energy":"J"},
            "provenance":"SIMULATED","limitations":"Constant acceleration in vacuum; no target, collision or material interaction."}


def thermal_compatibility(parameters, allowable_mismatch_m):
    if not math.isfinite(allowable_mismatch_m) or allowable_mismatch_m<=0:
        raise ValueError("Explicit positive allowable differential expansion in metres is required.")
    actual=thermal(parameters)
    mismatch=abs(actual["differential_expansion"])
    return {"metric":"absolute differential expansion / user-defined allowable mismatch",
            "differential_expansion_m":mismatch,"allowable_mismatch_m":allowable_mismatch_m,
            "modeled_mismatch_ratio":mismatch/allowable_mismatch_m,"within_thermal_tolerance":mismatch<=allowable_mismatch_m,
            "provenance":"SIMULATED","limitations":"Thermal dimensional fit only; not chemical, corrosion, strength or physical compatibility certification."}
