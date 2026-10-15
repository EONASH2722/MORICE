"""Inspectable experiment compilation and bounded, reproducible run plans."""
from __future__ import annotations

import copy
import itertools
import json
import math
import random
import re
from dataclasses import asdict, dataclass, field

from .simulations import SimulationToolRegistry

MAX_RUNS = 10000
KINDS = {"SINGLE", "PARAMETER_SWEEP", "MONTE_CARLO", "OPTIMIZATION", "SENSITIVITY_ANALYSIS"}


class NeedsExperimentDetails(ValueError):
    pass


@dataclass
class ResearchExperiment:
    title: str
    objective: str
    simulation_engine: str
    parameters: dict
    experiment_type: str = "SINGLE"
    parameter_ranges: dict = field(default_factory=dict)
    samples: int = 1
    seed: int = 0
    metric: str = ""
    direction: str = "maximize"
    constraints: dict = field(default_factory=dict)
    baseline: dict = field(default_factory=dict)
    hypothesis: str = ""
    safety_classification: str = "COMPUTATIONAL_ONLY_BOUNDED_MODEL"
    time_limit_seconds: float = 120
    strategy: str = "grid"
    priority: int = 1
    dependencies: tuple = ()

    def to_dict(self):
        return asdict(self)


class ExperimentCompiler:
    def __init__(self, registry=None):
        self.registry = registry or SimulationToolRegistry()

    def compile(self, request, context=None):
        """JSON or a conservative natural-language template, never executable model code."""
        if isinstance(request, dict):
            spec = copy.deepcopy(request)
        else:
            block = re.search(r"```experiment\s*\n(.*?)```", request, re.S)
            spec = json.loads(block.group(1)) if block else self._natural(request, context)
        allowed = set(ResearchExperiment.__dataclass_fields__)
        if not isinstance(spec, dict) or set(spec) - allowed:
            raise ValueError("Unknown experiment fields; inspect the supported specification.")
        try:
            experiment = ResearchExperiment(**spec)
        except TypeError as exc:
            raise NeedsExperimentDetails("Specify title, objective, simulation_engine and physical parameters.") from exc
        from .safety import check_research_purpose
        check_research_purpose(experiment.objective)
        check_research_purpose(experiment.title)
        check_research_purpose(experiment.hypothesis)
        tool = self.registry.get(experiment.simulation_engine)
        if experiment.experiment_type not in KINDS or experiment.strategy not in {"grid", "random", "coarse_refine"}:
            raise ValueError("Unsupported experiment type or search strategy.")
        if not isinstance(experiment.parameters, dict):
            raise ValueError("Experiment parameters must be an object.")
        missing = set(tool.required_units) - set(experiment.parameters)
        unknown = set(experiment.parameters) - set(tool.required_units)
        if missing:
            raise NeedsExperimentDetails("Missing physical inputs: " + ", ".join(f"{name} [{tool.required_units[name]}]" for name in sorted(missing)))
        if unknown:
            raise ValueError("Unknown physical inputs: " + ", ".join(sorted(unknown)))
        if experiment.metric and experiment.metric not in tool.supported_outputs:
            raise ValueError("Requested output is not supported by this model.")
        experiment.metric = experiment.metric or next(iter(tool.supported_outputs))
        if experiment.direction not in {"maximize", "minimize"}:
            raise ValueError("Optimization direction must be maximize or minimize.")
        if type(experiment.seed) is not int or not 0 <= experiment.seed < 2**32:
            raise ValueError("Seed must be an integer in [0, 2^32).")
        if type(experiment.samples) is not int or not 1 <= experiment.samples <= MAX_RUNS:
            raise ValueError(f"Sample count must be from 1 to {MAX_RUNS}.")
        if not math.isfinite(experiment.time_limit_seconds) or not 0 < experiment.time_limit_seconds <= 300:
            raise ValueError("Each execution slice must have a time limit from 0 to 300 seconds.")
        if experiment.priority not in (0, 1, 2, 3):
            raise ValueError("Priority must be 0 (interactive), 1, 2 or 3 (background).")
        # Validate quantities before creating any run. Unit-bearing inputs remain in the spec.
        parameters = {k: self.registry.quantity(v, tool.required_units[k]) for k, v in experiment.parameters.items()}
        self.registry.run(tool.tool_id, parameters)
        if experiment.experiment_type == "SINGLE" and experiment.parameter_ranges:
            raise ValueError("Use PARAMETER_SWEEP or MONTE_CARLO when specifying ranges.")
        if experiment.experiment_type != "SINGLE" and not experiment.parameter_ranges:
            raise NeedsExperimentDetails("Specify the parameter ranges or distributions to test.")
        if len(experiment.parameter_ranges) > 6:
            raise ValueError("At most six varying parameters are supported.")
        count = 1
        for name, entry in experiment.parameter_ranges.items():
            if name not in parameters or not isinstance(entry, dict):
                raise ValueError("Range must name a parameter used by the selected model.")
            unit = tool.required_units[name]
            low = self.registry.quantity({"value": entry["min"], "unit": entry["unit"]}, unit)
            high = self.registry.quantity({"value": entry["max"], "unit": entry["unit"]}, unit)
            if low >= high:
                raise ValueError("Range minimum must be less than maximum.")
            if entry.get("distribution", "uniform") != "uniform":
                raise ValueError("Only bounded uniform uncertainty distributions are currently implemented.")
            points = entry.get("points", 21)
            if type(points) is not int or not 2 <= points <= MAX_RUNS:
                raise ValueError("Each grid axis needs 2–10,000 points.")
            count *= points
        if experiment.experiment_type == "MONTE_CARLO" or experiment.strategy == "random":
            count = experiment.samples
        elif experiment.experiment_type == "SENSITIVITY_ANALYSIS":
            count = 1 + sum(r.get("points", 21) for r in experiment.parameter_ranges.values())
        if experiment.strategy == "coarse_refine":
            if experiment.experiment_type != "OPTIMIZATION" or len(experiment.parameter_ranges) != 1:
                raise ValueError("Coarse/refine is a one-dimensional optimization strategy.")
            count *= 2
        if count > MAX_RUNS:
            raise ValueError(f"Plan needs {count:,} runs; limit is {MAX_RUNS:,}. Reduce grid sizes or choose random sampling.")
        for name, bounds in experiment.constraints.items():
            if name not in tool.supported_outputs or not isinstance(bounds, dict) or not bounds:
                raise ValueError("Constraints must use available outputs with min/max quantities.")
            if set(bounds) - {"min", "max"}:
                raise ValueError("Constraint supports only min and max bounds.")
            normalized = {side: self.registry.quantity(value, tool.supported_outputs[name]) for side, value in bounds.items()}
            if normalized.get("min", -math.inf) > normalized.get("max", math.inf):
                raise ValueError("Constraint minimum exceeds maximum.")
        if experiment.baseline:
            if set(experiment.baseline) != set(parameters):
                raise ValueError("A baseline must specify every physical input explicitly.")
            self.registry.run(tool.tool_id, {k: self.registry.quantity(v, tool.required_units[k]) for k, v in experiment.baseline.items()})
        return experiment, {"planned_runs": count, "cpu_workers": 1, "gpu_required": False,
                            "runtime_estimate_seconds": None, "runtime_note": "No timing estimate before measurement; progress reports completed runs only.",
                            "max_execution_seconds": experiment.time_limit_seconds,
                            "approximate_result_bytes": count * (1024 + 80 * len(tool.supported_outputs)),
                            "limitations": tool.limitations, "method": tool.method, "tool_version": tool.version,
                            "model_fingerprint": self.registry.fingerprint(tool.tool_id)}

    def plan(self, experiment):
        tool = self.registry.get(experiment.simulation_engine)
        base = {k: self.registry.quantity(v, tool.required_units[k]) for k, v in experiment.parameters.items()}
        axes = {}
        for name, axis in experiment.parameter_ranges.items():
            lo = self.registry.quantity({"value": axis["min"], "unit": axis["unit"]}, tool.required_units[name])
            hi = self.registry.quantity({"value": axis["max"], "unit": axis["unit"]}, tool.required_units[name])
            axes[name] = (lo, hi, axis.get("points", 21))
        if experiment.experiment_type == "MONTE_CARLO" or experiment.strategy == "random":
            rng = random.Random(experiment.seed)
            return [{**base, **{name: rng.uniform(lo, hi) for name, (lo, hi, _) in axes.items()}} for _ in range(experiment.samples)]
        grids = {name: [lo + (hi - lo) * i / (n - 1) for i in range(n)] for name, (lo, hi, n) in axes.items()}
        if experiment.experiment_type == "SENSITIVITY_ANALYSIS":
            return [base] + [{**base, name: value} for name, values in grids.items() for value in values]
        return [{**base, **dict(zip(grids, values))} for values in itertools.product(*grids.values())]

    def _natural(self, text, context):
        # No default mass/material properties invented from names. Unsupported
        # tasks ask for a model/input or report the missing adapter.
        lower = text.casefold()
        if any(word in lower for word in ("radiation", "penetration", "chemical compatibility", "pathogen", "mixing procedure", "multiphysics")):
            raise NeedsExperimentDetails("That domain has no validated laboratory adapter here. No simulation or compatibility score was produced.")
        aliases = {"oscillator": "linear_oscillator", "thermal expansion": "thermal_expansion",
                   "mixture density": "ideal_mixture_density", "vacuum particle": "vacuum_particle"}
        engine = next((value for name, value in aliases.items() if name in lower), "")
        if context and (not engine or engine == context["simulation_engine"]):
            spec = copy.deepcopy(context)
        elif engine:
            spec = {"title": text[:100], "objective": text, "simulation_engine": engine, "parameters": {}}
        else:
            raise NeedsExperimentDetails("Choose an implemented model: oscillator, thermal expansion, mixture density, or vacuum particle; provide its physical inputs. General material-impact and external solver models are not integrated.")
        spec["objective"], spec["title"] = text, text[:100]
        tool = self.registry.get(spec["simulation_engine"])
        number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
        for name in tool.required_units:
            match = re.search(r"\b" + re.escape(name) + r"\s*(?:=|:)\s*(" + number + r")\s*([^,;\n]+)", text, re.I)
            if match:
                spec["parameters"][name] = {"value": float(match[1]), "unit": match[2].strip()}
        change = re.search(r"\b(increase|decrease)\s+(\w+)\s+by\s+(" + number + r")\s*%", text, re.I)
        if change:
            name = change[2].lower()
            if name not in spec["parameters"]:
                raise NeedsExperimentDetails("No previous value exists for " + name)
            multiplier = 1 + float(change[3]) / 100 * (1 if change[1].lower() == "increase" else -1)
            spec["parameters"][name]["value"] *= multiplier
        if "frequency" in tool.required_units and re.search(r"\b(?:test|run)\s+(?:this|it)\s+from\b",text,re.I):
            text=re.sub(r"\b(?:test|run)\s+(?:this|it)\s+from\b","test frequency from",text,flags=re.I)
        sweep = re.search(r"\b(?:sweep|test)\s+(\w+)\s+from\s+(" + number + r")\s+(?:to|through)\s+(" + number + r")\s+([^,;\n]+)", text, re.I)
        if sweep:
            name = sweep[1].lower()
            unit = sweep[4].strip()
            spec["parameter_ranges"] = {name: {"min": float(sweep[2]), "max": float(sweep[3]), "unit": unit, "points": 101}}
            spec["parameters"].setdefault(name, {"value": float(sweep[2]), "unit": unit})
            spec["experiment_type"] = "PARAMETER_SWEEP"
        points = re.search(r"\b(\d+)\s+(?:points|runs|samples)\b", lower)
        if points:
            spec["samples"] = int(points[1])
            for axis in spec.get("parameter_ranges", {}).values():
                axis["points"] = int(points[1])
        seed = re.search(r"\bseed\s*(?:=|:)?\s*(\d+)\b", lower)
        if seed:
            spec["seed"] = int(seed[1])
        if "monte carlo" in lower:
            spec["experiment_type"], spec["strategy"] = "MONTE_CARLO", "random"
        if "optimize" in lower:
            spec["experiment_type"], spec["strategy"] = "OPTIMIZATION", "coarse_refine"
        return spec
