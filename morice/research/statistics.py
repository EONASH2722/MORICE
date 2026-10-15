"""Actual NumPy statistics with explicit assumptions, seeds and bounded resampling."""
from __future__ import annotations

import math

from .ingestion import checkpoint


def _array(values):
    import numpy as np
    if not isinstance(values, list) or not 2 <= len(values) <= 10000:
        raise ValueError("Supply 2–10,000 numeric observations; inspect missing data first.")
    if any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e100 for x in values):
        raise ValueError("Statistics require finite numeric observations without silent imputation.")
    return np.asarray(values, dtype=float)


def analyze(spec, cancel=None):
    import numpy as np
    values = _array(spec["values"])
    method = spec.get("method", "descriptive")
    warnings = ["Sampling bias, independence and representativeness cannot be established from numbers alone."]
    if len(values) < 20:
        warnings.append("Small sample; estimates and resampled intervals may be unstable.")
    out = {"count": int(values.size), "mean": float(values.mean()), "median": float(np.median(values)),
           "sample_std": float(values.std(ddof=1)), "min": float(values.min()), "max": float(values.max()),
           "percentiles": [float(v) for v in np.quantile(values, [.05, .25, .75, .95])],
           "unit": spec.get("unit", ""), "method": method, "warnings": warnings,
           "numpy_version": np.__version__, "provenance": "CALCULATED"}
    if method == "descriptive":
        return out
    if method in {"bootstrap_mean", "permutation", "paired_permutation", "regression", "correlation", "anova_permutation"} and spec.get("independent") is not True:
        raise ValueError("Explicit independence/design review is required before inferential statistics.")
    seed, samples = spec.get("seed", 0), spec.get("resamples", 999)
    if type(seed) is not int or not 0 <= seed < 2**32 or type(samples) is not int or not 99 <= samples <= 2048:
        raise ValueError("Specify a valid seed and 99–2048 resamples.")
    rng = np.random.Generator(np.random.PCG64(seed))
    out.update(seed=seed, resamples=samples, generator="NumPy PCG64")
    if method == "bootstrap_mean":
        estimates = []
        for offset in range(0, samples, 32):
            checkpoint(cancel)
            draws = rng.choice(values, size=(min(32, samples-offset), values.size), replace=True)
            estimates.extend(draws.mean(axis=1).tolist())
        out["mean_ci95"] = np.quantile(estimates, [.025, .975]).tolist()
        out["assumptions"] = ["Independent identically distributed observations; percentile bootstrap, not a normality claim."]
    elif method in {"regression", "correlation"}:
        x = _array(spec["x"])
        if len(x) != len(values) or np.ptp(x) == 0 or np.ptp(values) == 0:
            raise ValueError("Paired nonconstant x/y of equal length are required.")
        slope, intercept = np.linalg.lstsq(np.column_stack((x, np.ones(len(x)))), values, rcond=None)[0]
        residuals = values - (slope*x + intercept)
        out.update(slope=float(slope), intercept=float(intercept), pearson_r=float(np.corrcoef(x, values)[0, 1]),
                   residuals=residuals.tolist(), rmse=float(np.sqrt(np.mean(residuals**2))),
                   x_unit=spec.get("x_unit", ""), slope_unit=f"({spec.get('unit', '')})/({spec.get('x_unit', '')})")
        out["warnings"].append("Association is not causality; no normality, homoscedasticity or extrapolation validity established.")
    elif method in {"permutation", "paired_permutation", "anova_permutation"}:
        if method == "anova_permutation":
            groups = [values] + [_array(v) for v in spec.get("groups", [])]
            if not 2 <= len(groups) <= 8 or sum(map(len, groups)) > 10000:
                raise ValueError("ANOVA needs 2–8 reviewed independent groups and at most 10,000 observations.")
            def statistic(parts):
                center = np.concatenate(parts).mean()
                between = sum(len(g)*(g.mean()-center)**2 for g in parts)/(len(parts)-1)
                within = sum(np.sum((g-g.mean())**2) for g in parts)/(sum(map(len, parts))-len(parts))
                if within <= 0: raise ValueError("ANOVA requires positive within-group variance.")
                return float(between/within)
            sizes, pool = np.cumsum([len(g) for g in groups])[:-1], np.concatenate(groups)
            observed = statistic(groups)
            exceed = 0
            for _ in range(samples):
                checkpoint(cancel)
                exceed += statistic(np.split(rng.permutation(pool), sizes)) >= observed
        else:
            other = _array(spec["other"])
            if method == "paired_permutation" and len(other) != len(values):
                raise ValueError("Paired observations must have equal length.")
            observed = abs(float(values.mean()-other.mean()))
            exceed, pool = 0, np.concatenate((values, other))
            for _ in range(samples):
                checkpoint(cancel)
                if method == "paired_permutation":
                    trial = abs(float(np.mean((values-other)*rng.choice([-1, 1], len(values)))))
                else:
                    shuffled = rng.permutation(pool)
                    trial = abs(float(shuffled[:len(values)].mean()-shuffled[len(values):].mean()))
                exceed += trial >= observed
        out.update(statistic=observed, p_value=(exceed+1)/(samples+1), tail="two-sided mean difference" if method != "anova_permutation" else "upper-tail F")
        out["assumptions"] = ["Exchangeability under the null; paired sign flips additionally require symmetric paired differences.",
                              "Multiple comparisons need a prespecified correction; this is one test, not a clinical conclusion."]
    else:
        raise ValueError("No implemented statistical method: " + str(method))
    return out


def pareto(rows, objectives):
    if not rows or len(rows) > 2000 or not objectives or len(objectives) > 4:
        raise ValueError("Pareto analysis requires 1–2000 candidates and 1–4 explicit objectives.")
    if any(direction not in {"minimize", "maximize"} for direction in objectives.values()):
        raise ValueError("Each objective needs minimize or maximize.")
    scores = []
    for row in rows:
        score = [float(row[k]) * (-1 if d == "maximize" else 1) for k, d in objectives.items()]
        if not all(math.isfinite(v) for v in score): raise ValueError("Invalid Pareto value.")
        scores.append(score)
    return [i for i, a in enumerate(scores) if not any(all(x <= y for x,y in zip(b,a)) and any(x < y for x,y in zip(b,a)) for j,b in enumerate(scores) if j != i)]
