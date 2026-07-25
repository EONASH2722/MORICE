from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field

import numpy as np


SAFE_FUNCTIONS = {
    "abs": np.abs,
    "acos": np.arccos,
    "asin": np.arcsin,
    "atan": np.arctan,
    "cos": np.cos,
    "cosh": np.cosh,
    "exp": np.exp,
    "log": np.log,
    "log10": np.log10,
    "piecewise": np.where,
    "sin": np.sin,
    "sinh": np.sinh,
    "sqrt": np.sqrt,
    "tan": np.tan,
    "tanh": np.tanh,
}

SAFE_CONSTANTS = {
    "e": math.e,
    "pi": math.pi,
    "tau": math.tau,
}


@dataclass
class GraphSeries:
    label: str
    expression: str
    x: list[float]
    y: list[float]
    color: str
    inspection_points: list[dict] = field(default_factory=list)


@dataclass
class GraphSurface:
    label: str
    expression: str
    x: list[float]
    y: list[float]
    z: list[list[float]]
    z_range: tuple[float, float]


@dataclass
class GraphArtifact:
    title: str
    instruction: dict
    series: list[GraphSeries]
    x_range: tuple[float, float] = (-10.0, 10.0)
    y_range: tuple[float, float] = (-10.0, 10.0)
    surface: GraphSurface | None = None


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    mass: float
    color: str
    z: float = 0.0
    vz: float = 0.0


@dataclass
class PhysicsArtifact:
    title: str
    instruction: dict
    simulation_type: str
    particles: list[Particle]
    gravity: float = 180.0
    friction: float = 0.995
    restitution: float = 0.94
    bounds: tuple[float, float] = (640.0, 380.0)
    stats: dict = field(default_factory=dict)


@dataclass
class ScienceArtifact:
    kind: str
    title: str
    instruction: dict
    graph: GraphArtifact | None = None
    physics: PhysicsArtifact | None = None
    chemistry: object | None = None
    diagram: object | None = None


class UnsafeExpression(ValueError):
    pass


class _ExpressionGuard(ast.NodeVisitor):
    allowed_nodes = {
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Call,
        ast.Load,
        ast.Name,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.USub,
        ast.UAdd,
        ast.Compare,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Eq,
        ast.NotEq,
    }

    def generic_visit(self, node):
        if type(node) not in self.allowed_nodes:
            raise UnsafeExpression(f"Unsupported expression node: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id not in {"x", "y", "t", "theta", *SAFE_FUNCTIONS.keys(), *SAFE_CONSTANTS.keys()}:
            raise UnsafeExpression(f"Unsupported symbol: {node.id}")

    def visit_Call(self, node: ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCTIONS:
            raise UnsafeExpression("Only known math functions are allowed.")
        if node.keywords:
            raise UnsafeExpression("Keyword arguments are not allowed.")
        self.generic_visit(node)


def is_science_request(text: str) -> bool:
    lowered = (text or "").lower()
    return wants_graph(text) or wants_physics(text) or any(
        marker in lowered
        for marker in {
            "equation",
            "particle",
            "particles",
            "projectile",
            "pendulum",
            "wave",
            "circular motion",
            "gas",
            "spring",
            "collision",
            "collisions",
            "gravity",
            "orbit",
            "simulate",
            "simulation",
        }
    )


def wants_graph(text: str) -> bool:
    lowered = (text or "").lower()
    if "polar" in lowered or "parametric" in lowered or re.search(r"\br\s*=", text or "", flags=re.IGNORECASE):
        return True
    if re.search(r"\b(?:y|f\s*\(\s*x\s*\))\s*=", text or "", flags=re.IGNORECASE):
        return True
    if re.search(r"\bz\s*=", text or "", flags=re.IGNORECASE):
        return True
    return any(marker in lowered for marker in {"plot", "graph", "chart", "curve", "function"}) and (
        "=" in lowered or "sin" in lowered or "cos" in lowered or "x" in lowered
    )


def wants_physics(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        marker in lowered
        for marker in {"animate", "simulate", "simulation", "physics", "particle", "projectile"}
    ) and any(
        marker in lowered
        for marker in {
            "ball",
            "collision",
            "collisions",
            "fluid",
            "force",
            "gravity",
            "gas",
            "motion",
            "orbit",
            "particle",
            "pendulum",
            "projectile",
            "rigid",
            "solar system",
            "spring",
            "wave",
        }
    )


def _clean_title(text: str, fallback: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    stop = {"a", "an", "and", "for", "graph", "make", "me", "of", "plot", "please", "show", "simulate", "the"}
    useful = [word for word in words if word.lower() not in stop]
    if not useful:
        return fallback
    return " ".join(useful[:7])[:80]


def _normalize_expression(expr: str, variable: str = "x") -> str:
    clean = (expr or "").strip()
    clean = clean.replace("^", "**").replace("\u2212", "-")
    clean = re.sub(r"\be\s*\^\s*([A-Za-z0-9_.()+\-*/]+)", r"exp(\1)", clean)
    clean = re.sub(rf"(?<=\d)(?={re.escape(variable)}\b)", "*", clean)
    clean = re.sub(rf"(?<=\))(?={re.escape(variable)}\b)", "*", clean)
    clean = re.sub(rf"\b{re.escape(variable)}(?=\()", f"{variable}*", clean)
    return clean


def _clean_expression_candidate(candidate: str) -> str:
    clean = (candidate or "").strip()
    clean = clean.replace("\u00b2", "^2").replace("\u00b3", "^3").replace("\u2212", "-")
    clean = re.sub(r"^(?:y|f\s*\(\s*x\s*\))\s*=\s*", "", clean, flags=re.IGNORECASE).strip()
    clean = re.split(
        r"\.\s*(?:show|mark|display|include|including|with|also|then|and|local|graph|derivative|area|inflection)\b",
        clean,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    clean = re.split(
        r"\s+(?:(?:and|also|then)\s+)?"
        r"(?:show|mark|display|include|including|with|label|highlight|identify)\b",
        clean,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    clean = re.sub(r"^(?:plot|graph|draw|show)\s+", "", clean, flags=re.IGNORECASE).strip()
    clean = clean.strip(" \t\r\n.;:,!?")
    return re.sub(r"\s+", " ", clean)


def _extract_equations(text: str) -> list[str]:
    raw = (text or "").strip()
    raw = raw.replace("\u00b2", "^2").replace("\u00b3", "^3")
    pieces: list[str] = []
    assignment_pattern = re.compile(
        r"(?:\by|f\s*\(\s*x\s*\))\s*=\s*",
        flags=re.IGNORECASE,
    )
    for match in assignment_pattern.finditer(raw):
        depth = 0
        end = match.end()
        while end < len(raw):
            character = raw[end]
            if character in "([{":
                depth += 1
            elif character in ")]}":
                depth = max(0, depth - 1)
            elif depth == 0 and character in ",;\n":
                break
            end += 1
        candidate = _clean_expression_candidate(raw[match.end() : end])
        if candidate:
            pieces.append(candidate)
    if pieces:
        return pieces[:6]

    after = re.sub(r"^(?:plot|graph|draw|show)\s+", "", raw, flags=re.IGNORECASE).strip()
    split = re.split(r"\s+(?:and|plus)\s+|[,;]", after)
    for piece in split:
        candidate = piece.strip()
        if not candidate:
            continue
        candidate = _clean_expression_candidate(candidate)
        if re.search(r"\bx\b|sin|cos|tan|log|sqrt|exp|\^", candidate, flags=re.IGNORECASE):
            pieces.append(candidate)
    return pieces[:6] or ["x^2"]


def _evaluate_expression(expression: str, x_values: np.ndarray, variable: str = "x") -> np.ndarray:
    clean = _normalize_expression(expression, variable)
    tree = ast.parse(clean, mode="eval")
    _ExpressionGuard().visit(tree)
    compiled = compile(tree, "<morice-graph>", "eval")
    scope = dict(SAFE_FUNCTIONS)
    scope.update(SAFE_CONSTANTS)
    scope[variable] = x_values
    if variable == "theta":
        scope["t"] = x_values
    result = eval(compiled, {"__builtins__": {}}, scope)  # noqa: S307 - guarded AST and empty builtins
    if np.isscalar(result):
        result = np.full_like(x_values, float(result), dtype=float)
    arr = np.asarray(result, dtype=float)
    return np.where(np.isfinite(arr), arr, np.nan)


def _evaluate_surface_expression(
    expression: str,
    x_values: np.ndarray,
    y_values: np.ndarray,
) -> np.ndarray:
    clean = _normalize_expression(expression, "x")
    clean = _normalize_expression(clean, "y")
    tree = ast.parse(clean, mode="eval")
    _ExpressionGuard().visit(tree)
    compiled = compile(tree, "<morice-surface>", "eval")
    scope = dict(SAFE_FUNCTIONS)
    scope.update(SAFE_CONSTANTS)
    scope["x"] = x_values
    scope["y"] = y_values
    result = eval(compiled, {"__builtins__": {}}, scope)  # noqa: S307 - guarded AST and empty builtins
    if np.isscalar(result):
        result = np.full_like(x_values, float(result), dtype=float)
    arr = np.asarray(result, dtype=float)
    if arr.shape != x_values.shape:
        arr = np.broadcast_to(arr, x_values.shape).astype(float)
    return np.where(np.isfinite(arr), arr, np.nan)


def _evaluate_scalar(expression: str, x_value: float) -> float:
    return float(_evaluate_expression(expression, np.asarray([x_value], dtype=float))[0])


def _bisect_zero(function, left: float, right: float, iterations: int = 64) -> float | None:
    try:
        left_value = float(function(left))
        right_value = float(function(right))
    except Exception:
        return None
    if not math.isfinite(left_value) or not math.isfinite(right_value):
        return None
    if abs(left_value) < 1e-12:
        return left
    if abs(right_value) < 1e-12:
        return right
    if left_value * right_value > 0:
        return None
    for _ in range(iterations):
        midpoint = (left + right) / 2
        try:
            midpoint_value = float(function(midpoint))
        except Exception:
            return None
        if not math.isfinite(midpoint_value):
            return None
        if abs(midpoint_value) < 1e-11:
            return midpoint
        if left_value * midpoint_value <= 0:
            right = midpoint
            right_value = midpoint_value
        else:
            left = midpoint
            left_value = midpoint_value
    return (left + right) / 2


def _append_unique_point(points: list[dict], kind: str, x: float, y: float, tolerance: float = 0.025) -> None:
    if not math.isfinite(x) or not math.isfinite(y):
        return
    if any(point["kind"] == kind and abs(float(point["x"]) - x) <= tolerance for point in points):
        return
    points.append({"kind": kind, "label": kind, "x": x, "y": y})


def _graph_inspection_points(
    expression: str,
    x_values: np.ndarray,
    y_values: np.ndarray,
    *,
    include_inflections: bool = False,
) -> list[dict]:
    points: list[dict] = []
    finite = np.isfinite(y_values)
    if not finite.any():
        return points

    for index in range(len(x_values) - 1):
        y0 = float(y_values[index])
        y1 = float(y_values[index + 1])
        if not math.isfinite(float(y0)) or not math.isfinite(float(y1)):
            continue
        if abs(y0) < 1e-12:
            root_x = float(x_values[index])
        elif y0 * y1 < 0:
            x0 = float(x_values[index])
            x1 = float(x_values[index + 1])
            root_x = _bisect_zero(lambda value: _evaluate_scalar(expression, value), x0, x1)
            if root_x is None:
                continue
        else:
            continue
        try:
            residual = abs(_evaluate_scalar(expression, root_x))
        except Exception:
            continue
        local_scale = max(1.0, abs(y0), abs(y1))
        if residual <= max(1e-7, local_scale * 1e-6):
            _append_unique_point(points, "x-intercept", root_x, 0.0, tolerance=0.04)
        if len([point for point in points if point["kind"] == "x-intercept"]) >= 6:
            break

    try:
        y_at_zero = float(_evaluate_expression(expression, np.asarray([0.0]))[0])
    except Exception:
        y_at_zero = float("nan")
    if math.isfinite(y_at_zero):
        _append_unique_point(points, "y-intercept", 0.0, y_at_zero)

    step = float(abs(x_values[1] - x_values[0])) if len(x_values) > 1 else 0.025

    def derivative_at(value: float) -> float:
        h = max(1e-5, step * 0.08, abs(value) * 1e-6)
        return (_evaluate_scalar(expression, value + h) - _evaluate_scalar(expression, value - h)) / (2 * h)

    def second_derivative_at(value: float) -> float:
        h = max(2e-4, step * 0.35, abs(value) * 1e-5)
        center = _evaluate_scalar(expression, value)
        return (
            _evaluate_scalar(expression, value + h)
            - 2 * center
            + _evaluate_scalar(expression, value - h)
        ) / (h * h)

    derivative = np.gradient(y_values, x_values)
    valid_derivative = finite & np.isfinite(derivative) & (np.abs(y_values) < 1_000_000)
    for index in range(1, len(x_values)):
        if not valid_derivative[index - 1] or not valid_derivative[index]:
            continue
        left_slope = float(derivative[index - 1])
        right_slope = float(derivative[index])
        if left_slope == 0:
            critical_x = float(x_values[index - 1])
        elif left_slope * right_slope < 0:
            critical_x = _bisect_zero(
                derivative_at,
                float(x_values[index - 1]),
                float(x_values[index]),
            )
            if critical_x is None:
                continue
        else:
            continue
        try:
            critical_y = _evaluate_scalar(expression, critical_x)
            curvature = second_derivative_at(critical_x)
        except Exception:
            continue
        if abs(curvature) < 1e-5:
            continue
        if abs(critical_y) <= 1e-6:
            _append_unique_point(points, "x-intercept", critical_x, 0.0, tolerance=max(0.04, step * 2))
        kind = "minimum" if curvature > 0 else "maximum"
        _append_unique_point(points, kind, critical_x, critical_y, tolerance=max(0.04, step * 2))
        if len([point for point in points if point["kind"] in {"minimum", "maximum"}]) >= 6:
            break

    if include_inflections:
        second_derivative = np.gradient(derivative, x_values)
        valid_second = valid_derivative & np.isfinite(second_derivative)
        for index in range(1, len(x_values)):
            if not valid_second[index - 1] or not valid_second[index]:
                continue
            left_curve = float(second_derivative[index - 1])
            right_curve = float(second_derivative[index])
            if left_curve * right_curve >= 0:
                continue
            inflection_x = _bisect_zero(
                second_derivative_at,
                float(x_values[index - 1]),
                float(x_values[index]),
            )
            if inflection_x is None:
                continue
            try:
                inflection_y = _evaluate_scalar(expression, inflection_x)
            except Exception:
                continue
            _append_unique_point(
                points,
                "inflection",
                inflection_x,
                inflection_y,
                tolerance=max(0.05, step * 3),
            )
            if len([point for point in points if point["kind"] == "inflection"]) >= 4:
                break

    return points[:14]


def _graph_view_y_range(series: list[GraphSeries]) -> tuple[float, float]:
    point_values = [
        float(point["y"])
        for item in series
        for point in item.inspection_points
        if math.isfinite(float(point.get("y", float("nan"))))
    ]
    if point_values:
        low = min(0.0, min(point_values))
        high = max(0.0, max(point_values))
        if low >= -10.0 and high <= 10.0:
            return -10.0, 10.0
        span = max(10.0, high - low)
        padding = max(2.0, span * 0.16)
        return low - padding, high + padding

    visible_values = np.asarray(
        [
            y
            for item in series
            for y in item.y
            if math.isfinite(y) and abs(y) < 1_000_000
        ],
        dtype=float,
    )
    if not visible_values.size:
        return -10.0, 10.0
    low, high = (float(value) for value in np.nanpercentile(visible_values, [10, 90]))
    if low >= -10.0 and high <= 10.0:
        return -10.0, 10.0
    span = max(10.0, high - low)
    padding = max(2.0, span * 0.16)
    return low - padding, high + padding


def _graph_bounds(series: list[GraphSeries]) -> tuple[tuple[float, float], tuple[float, float]]:
    x_min = math.inf
    x_max = -math.inf
    y_min = math.inf
    y_max = -math.inf
    for item in series:
        x_arr = np.asarray(item.x, dtype=float)
        y_arr = np.asarray(item.y, dtype=float)
        finite = np.isfinite(x_arr) & np.isfinite(y_arr) & (np.abs(x_arr) < 1_000) & (np.abs(y_arr) < 1_000)
        if not finite.any():
            continue
        x_min = min(x_min, float(np.nanmin(x_arr[finite])))
        x_max = max(x_max, float(np.nanmax(x_arr[finite])))
        y_min = min(y_min, float(np.nanmin(y_arr[finite])))
        y_max = max(y_max, float(np.nanmax(y_arr[finite])))
    if not all(math.isfinite(value) for value in (x_min, x_max, y_min, y_max)):
        return (-10.0, 10.0), (-10.0, 10.0)
    if abs(x_max - x_min) < 1e-9:
        x_min -= 1.0
        x_max += 1.0
    if abs(y_max - y_min) < 1e-9:
        y_min -= 1.0
        y_max += 1.0
    x_pad = max(1.0, (x_max - x_min) * 0.12)
    y_pad = max(1.0, (y_max - y_min) * 0.12)
    return (x_min - x_pad, x_max + x_pad), (y_min - y_pad, y_max + y_pad)


def _build_polar_artifact(text: str) -> ScienceArtifact | None:
    matches = re.findall(r"r\s*=\s*([^,;\n]+)", text, flags=re.IGNORECASE)
    if not matches:
        return None
    theta_values = np.linspace(0, math.tau * 2, 1000)
    palette = ["#64d8ff", "#a77cff", "#7cf7b5", "#ff8db3", "#ffd166", "#f97068"]
    series: list[GraphSeries] = []
    for index, expression in enumerate(matches[:6]):
        try:
            r_values = _evaluate_expression(expression, theta_values, variable="theta")
        except Exception:
            continue
        x_values = r_values * np.cos(theta_values)
        y_values = r_values * np.sin(theta_values)
        series.append(
            GraphSeries(
                label=f"r = {expression.strip()}",
                expression=expression.strip(),
                x=[float(v) if math.isfinite(float(v)) else float("nan") for v in x_values],
                y=[float(v) if math.isfinite(float(v)) else float("nan") for v in y_values],
                color=palette[index % len(palette)],
                inspection_points=[],
            )
        )
    if not series:
        return None
    x_range, y_range = _graph_bounds(series)
    title = _clean_title(text, "Polar Graph")
    instruction = {
        "simulationType": "graph",
        "equations": [item.label for item in series],
        "parameters": {"coordinateSystem": "polar", "thetaRange": [0, math.tau * 2], "samples": len(theta_values)},
    }
    graph = GraphArtifact(title, instruction, series, x_range, y_range)
    return ScienceArtifact("graph", title, instruction, graph=graph)


def _build_parametric_artifact(text: str) -> ScienceArtifact | None:
    x_match = re.search(r"\bx\s*(?:\(t\))?\s*=\s*([^,;\n]+)", text, flags=re.IGNORECASE)
    y_match = re.search(r"\by\s*(?:\(t\))?\s*=\s*([^,;\n]+)", text, flags=re.IGNORECASE)
    if not x_match or not y_match:
        return None
    x_expression = x_match.group(1).strip()
    y_expression = y_match.group(1).strip()
    t_values = np.linspace(0, math.tau, 800)
    try:
        x_values = _evaluate_expression(x_expression, t_values, variable="t")
        y_values = _evaluate_expression(y_expression, t_values, variable="t")
    except Exception:
        return None
    series = [
        GraphSeries(
            label=f"x={x_expression}, y={y_expression}",
            expression=f"x={x_expression}; y={y_expression}",
            x=[float(v) if math.isfinite(float(v)) else float("nan") for v in x_values],
            y=[float(v) if math.isfinite(float(v)) else float("nan") for v in y_values],
            color="#64d8ff",
            inspection_points=[],
        )
    ]
    x_range, y_range = _graph_bounds(series)
    title = _clean_title(text, "Parametric Graph")
    instruction = {
        "simulationType": "graph",
        "equations": [series[0].expression],
        "parameters": {"coordinateSystem": "parametric", "tRange": [0, math.tau], "samples": len(t_values)},
    }
    graph = GraphArtifact(title, instruction, series, x_range, y_range)
    return ScienceArtifact("graph", title, instruction, graph=graph)


def _build_surface_artifact(text: str) -> ScienceArtifact | None:
    match = re.search(r"\bz\s*=\s*([^;\n]+)", text or "", flags=re.IGNORECASE)
    if not match:
        return None
    expression = re.split(
        r"\s+(?:as|rendered\s+as)\s+(?:an?\s+)?(?:interactive\s+)?(?:2d|3d|surface|graph)\b",
        match.group(1),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    expression = _clean_expression_candidate(expression)
    if not expression:
        return None
    samples = 45
    axis = np.linspace(-6.0, 6.0, samples)
    x_grid, y_grid = np.meshgrid(axis, axis)
    try:
        z_grid = _evaluate_surface_expression(expression, x_grid, y_grid)
    except Exception:
        return None
    finite = z_grid[np.isfinite(z_grid)]
    if finite.size < 4:
        return None
    # The renderer labels this range, so use the true sampled extrema. Camera
    # projection clamps only display coordinates and never changes the data.
    low, high = float(np.min(finite)), float(np.max(finite))
    if math.isclose(float(low), float(high), abs_tol=1e-9):
        padding = max(1.0, abs(float(low)) * 0.1)
        low -= padding
        high += padding
    title = f"z = {expression}"
    instruction = {
        "simulationType": "surface-3d",
        "equations": [expression],
        "parameters": {
            "xDomain": [-6.0, 6.0],
            "yDomain": [-6.0, 6.0],
            "samples": samples,
            "interactive": True,
            "views": ["2d", "3d"],
            "deterministic": True,
            "units": "canvas-units",
        },
    }
    surface = GraphSurface(
        label=title,
        expression=expression,
        x=[float(value) for value in axis],
        y=[float(value) for value in axis],
        z=[
            [float(value) if math.isfinite(float(value)) else float("nan") for value in row]
            for row in z_grid
        ],
        z_range=(float(low), float(high)),
    )
    graph = GraphArtifact(
        title,
        instruction,
        [],
        (-6.0, 6.0),
        (-6.0, 6.0),
        surface=surface,
    )
    return ScienceArtifact("graph", title, instruction, graph=graph)


def _build_implicit_artifact(text: str) -> ScienceArtifact | None:
    raw = (text or "").replace("²", "^2").replace("³", "^3").replace("−", "-")
    if re.search(r"\b(?:y|z|r)\s*=", raw, flags=re.IGNORECASE):
        return None
    match = re.search(
        r"(?:plot|graph|draw|show|render)?\s*"
        r"([A-Za-z0-9_.()+\-*/^ ]*[xy][A-Za-z0-9_.()+\-*/^ ]*)"
        r"\s*=\s*"
        r"([A-Za-z0-9_.()+\-*/^ ]+)",
        raw,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    left = _clean_expression_candidate(match.group(1))
    right = _clean_expression_candidate(match.group(2))
    if not left or not right or not {"x", "y"}.issubset(set((left + right).lower())):
        return None
    expression = f"({left})-({right})"
    samples = 181
    axis = np.linspace(-10.0, 10.0, samples)
    x_grid, y_grid = np.meshgrid(axis, axis)
    try:
        values = _evaluate_surface_expression(expression, x_grid, y_grid)
    except Exception:
        return None
    if np.count_nonzero(np.isfinite(values)) < 16:
        return None

    def interpolate(
        first_point: tuple[float, float],
        second_point: tuple[float, float],
        first_value: float,
        second_value: float,
    ) -> tuple[float, float]:
        denominator = first_value - second_value
        amount = 0.5 if abs(denominator) < 1e-14 else first_value / denominator
        amount = max(0.0, min(1.0, amount))
        return (
            first_point[0] + (second_point[0] - first_point[0]) * amount,
            first_point[1] + (second_point[1] - first_point[1]) * amount,
        )

    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for row in range(samples - 1):
        y0, y1 = float(axis[row]), float(axis[row + 1])
        for column in range(samples - 1):
            x0, x1 = float(axis[column]), float(axis[column + 1])
            corners = (
                ((x0, y0), float(values[row, column])),
                ((x1, y0), float(values[row, column + 1])),
                ((x1, y1), float(values[row + 1, column + 1])),
                ((x0, y1), float(values[row + 1, column])),
            )
            if not all(math.isfinite(value) for _point, value in corners):
                continue
            edge_pairs = ((0, 1), (1, 2), (2, 3), (3, 0))
            intersections: list[tuple[int, tuple[float, float]]] = []
            for edge_index, (first_index, second_index) in enumerate(edge_pairs):
                first_point, first_value = corners[first_index]
                second_point, second_value = corners[second_index]
                if first_value == 0.0 and second_value == 0.0:
                    continue
                if first_value == 0.0 or second_value == 0.0 or (first_value < 0) != (second_value < 0):
                    intersections.append(
                        (
                            edge_index,
                            interpolate(
                                first_point,
                                second_point,
                                first_value,
                                second_value,
                            ),
                        )
                    )
            unique: list[tuple[int, tuple[float, float]]] = []
            for edge_index, point in intersections:
                if not any(
                    math.hypot(point[0] - existing[1][0], point[1] - existing[1][1])
                    < 1e-10
                    for existing in unique
                ):
                    unique.append((edge_index, point))
            if len(unique) == 2:
                segments.append((unique[0][1], unique[1][1]))
            elif len(unique) == 4:
                center_value = sum(value for _point, value in corners) / 4.0
                ordered = {edge_index: point for edge_index, point in unique}
                pairs = (
                    ((0, 3), (1, 2))
                    if (corners[0][1] < 0) == (center_value < 0)
                    else ((0, 1), (2, 3))
                )
                for first_edge, second_edge in pairs:
                    segments.append((ordered[first_edge], ordered[second_edge]))
    if not segments:
        return None

    x_values: list[float] = []
    y_values: list[float] = []
    for first, second in segments:
        x_values.extend((first[0], second[0], float("nan")))
        y_values.extend((first[1], second[1], float("nan")))
    label = f"{left} = {right}"
    series = [
        GraphSeries(
            label=label,
            expression=expression,
            x=x_values,
            y=y_values,
            color="#64d8ff",
            inspection_points=[],
        )
    ]
    instruction = {
        "simulationType": "graph",
        "equations": [label],
        "parameters": {
            "coordinateSystem": "implicit",
            "xDomain": [-10.0, 10.0],
            "yDomain": [-10.0, 10.0],
            "gridSamples": samples,
            "segments": len(segments),
            "deterministic": True,
        },
    }
    graph = GraphArtifact(
        label,
        instruction,
        series,
        (-10.0, 10.0),
        (-10.0, 10.0),
    )
    return ScienceArtifact("graph", label, instruction, graph=graph)


def build_graph_artifact(text: str) -> ScienceArtifact | None:
    if not wants_graph(text):
        return None
    implicit = _build_implicit_artifact(text)
    if implicit:
        return implicit
    lowered = (text or "").lower()
    if re.search(r"\bz\s*=", text, flags=re.IGNORECASE):
        surface = _build_surface_artifact(text)
        if surface:
            return surface
    if "polar" in lowered or re.search(r"\br\s*=", text, flags=re.IGNORECASE):
        polar = _build_polar_artifact(text)
        if polar:
            return polar
    if "parametric" in lowered or re.search(r"\bx\s*(?:\(t\))?\s*=", text, flags=re.IGNORECASE):
        parametric = _build_parametric_artifact(text)
        if parametric:
            return parametric
    expressions = _extract_equations(text)
    x_values = np.linspace(-10, 10, 800)
    palette = ["#64d8ff", "#a77cff", "#7cf7b5", "#ff8db3", "#ffd166", "#f97068"]
    series: list[GraphSeries] = []
    for index, expression in enumerate(expressions):
        try:
            y_values = _evaluate_expression(expression, x_values)
        except Exception:
            continue
        series.append(
            GraphSeries(
                label=f"y = {expression}",
                expression=expression,
                x=[float(v) for v in x_values],
                y=[float(v) if math.isfinite(float(v)) else float("nan") for v in y_values],
                color=palette[index % len(palette)],
                inspection_points=_graph_inspection_points(
                    expression,
                    x_values,
                    y_values,
                    include_inflections="inflection" in lowered,
                ),
            )
        )
    if not series:
        return None
    y_range = _graph_view_y_range(series)
    title = (
        f"y = {series[0].expression}"
        if len(series) == 1
        else f"Graph: {len(series)} equations"
    )
    instruction = {
        "simulationType": "graph",
        "equations": [item.expression for item in series],
        "parameters": {"domain": [-10, 10], "samples": len(x_values), "interactive": True},
    }
    graph = GraphArtifact(title, instruction, series, (-10.0, 10.0), y_range)
    return ScienceArtifact("graph", title, instruction, graph=graph)


def _seed_from_text(text: str) -> int:
    value = 2166136261
    for ch in text or "":
        value ^= ord(ch)
        value = (value * 16777619) & 0xFFFFFFFF
    return value or 7


def _particle_count(text: str) -> int:
    match = re.search(
        r"(\d{1,5})\s*(?:particles|balls|bodies|objects)",
        text or "",
        flags=re.IGNORECASE,
    )
    if match:
        return max(8, min(1600, int(match.group(1))))
    lowered = (text or "").lower()
    if "fluid" in lowered or "sph" in lowered:
        return 420
    if "many" in lowered or "swarm" in lowered:
        return 260
    return 80


def build_physics_artifact(text: str) -> ScienceArtifact | None:
    if not wants_physics(text):
        return None
    lowered = (text or "").lower()
    width, height = 640.0, 380.0
    count = _particle_count(text)
    rng = np.random.default_rng(_seed_from_text(text))
    palette = ["#64d8ff", "#a77cff", "#7cf7b5", "#ff8db3", "#ffd166"]
    particles: list[Particle] = []

    restitution = 1.0 if "elastic" in lowered else 0.94
    friction = 1.0 if "frictionless" in lowered or "elastic" in lowered else 0.997

    # These require solvers that are not present in the deterministic desktop
    # engine yet. Fail closed so MORICE never substitutes ordinary particles
    # while claiming that SPH, soft bodies, or rigid constraints were rendered.
    if any(
        marker in lowered
        for marker in {
            "fluid",
            "sph",
            "soft body",
            "soft-body",
            "rigid body",
            "rigid-body",
            "double pendulum",
        }
    ):
        return None

    if "projectile" in lowered:
        count = 1
        speed_match = re.search(r"(?:speed|velocity)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)", lowered)
        angle_match = re.search(r"(?:angle|at)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:degrees?|deg|\u00b0)?", lowered)
        speed = float(speed_match.group(1)) * 5.0 if speed_match else 395.0
        angle = math.radians(float(angle_match.group(1)) if angle_match else 52.0)
        particles.append(
            Particle(
                60.0,
                height - 60.0,
                speed * math.cos(angle),
                -speed * math.sin(angle),
                10.0,
                1.0,
                "#7cf7b5",
            )
        )
        gravity = 49.05
        simulation_type = "projectile-2d"
    elif "pendulum" in lowered:
        count = 1
        gravity = 9.81
        simulation_type = "pendulum-2d"
        length = 142.0
        angle_match = re.search(
            r"(?:angle|release(?:d)? at)\s*(?:of|=|:)?\s*(-?\d+(?:\.\d+)?)",
            lowered,
        )
        initial_angle = math.radians(float(angle_match.group(1)) if angle_match else 38.0)
        anchor_x, anchor_y = width * 0.5, 72.0
        particles.append(
            Particle(
                anchor_x + math.sin(initial_angle) * length,
                anchor_y + math.cos(initial_angle) * length,
                0.0,
                0.0,
                13.0,
                1.0,
                "#7cf7b5",
            )
        )
    elif "spring" in lowered:
        count = 1
        gravity = 0.0
        simulation_type = "spring-2d"
        particles.append(Particle(width * 0.72, height * 0.5, 0.0, 95.0, 12.0, 1.0, "#a77cff"))
    elif "wave" in lowered or "ripple" in lowered:
        count = max(32, min(240, count))
        gravity = 0.0
        friction = 1.0
        restitution = 1.0
        simulation_type = "wave-2d"
        for index in range(count):
            x = 30.0 + index * (width - 60.0) / max(1, count - 1)
            particles.append(
                Particle(
                    x=x,
                    y=height * 0.5,
                    vx=0.0,
                    vy=0.0,
                    radius=2.5,
                    mass=1.0,
                    color=palette[index % len(palette)],
                )
            )
    elif "circular motion" in lowered or "uniform circular" in lowered:
        count = 1
        gravity = 0.0
        friction = 1.0
        restitution = 1.0
        simulation_type = "circular-motion-2d"
        orbit_radius = 118.0
        angular_speed = 1.4
        particles.append(
            Particle(
                x=width * 0.5 + orbit_radius,
                y=height * 0.5,
                vx=0.0,
                vy=orbit_radius * angular_speed,
                radius=10.0,
                mass=1.0,
                color="#64d8ff",
            )
        )
    elif "orbit" in lowered or "solar system" in lowered:
        count = max(1, min(count, 24))
        gravity = 0.0
        simulation_type = "orbit-2d"
        center_x, center_y = width / 2, height / 2
        for index in range(count):
            radius_from_center = 55.0 + (index % 12) * 11.0
            angle = math.tau * index / max(1, count)
            orbital_speed = math.sqrt(900_000.0 / radius_from_center)
            particles.append(
                Particle(
                    x=center_x + math.cos(angle) * radius_from_center,
                    y=center_y + math.sin(angle) * radius_from_center,
                    vx=-math.sin(angle) * orbital_speed,
                    vy=math.cos(angle) * orbital_speed,
                    radius=3.5 + (index % 3),
                    mass=1.0,
                    color=palette[index % len(palette)],
                )
            )
    else:
        gas_mode = bool(re.search(r"\b(?:gas|ideal gas)\b", lowered))
        gravity = (
            0.0
            if gas_mode or re.search(r"\b(?:zero|no|without)\s+gravity\b", lowered)
            else 90.0
        )
        simulation_type = "particle-2d"
        if re.search(r"\b3d\b|three[- ]dimensional", lowered):
            simulation_type = "particle-3d"
        for index in range(count):
            radius = float(rng.uniform(2.2, 6.5))
            particles.append(
                Particle(
                    x=float(rng.uniform(40, width - 40)),
                    y=float(rng.uniform(30, height - 80)),
                    vx=float(rng.uniform(-85, 85)),
                    vy=float(rng.uniform(-45, 75)),
                    radius=radius,
                    mass=max(0.8, radius / 3),
                    color=palette[index % len(palette)],
                    z=float(rng.uniform(35, height - 35)) if simulation_type == "particle-3d" else 0.0,
                    vz=float(rng.uniform(-70, 70)) if simulation_type == "particle-3d" else 0.0,
                )
            )

    title = _clean_title(text, "Physics Simulation")
    instruction = {
        "simulationType": simulation_type,
        "equations": [],
        "parameters": {
            "particles": count,
            "gravity": gravity,
            "collisions": True,
            "restitution": restitution,
            "showVelocityVectors": "velocity" in lowered or "vectors" in lowered,
            "showTrails": "trail" in lowered or "trajectory" in lowered,
            "showKineticEnergy": "kinetic" in lowered or "energy" in lowered,
            "bounds": [width, height],
            "depth": height if simulation_type == "particle-3d" else 0.0,
            "views": (
                ["2d", "3d"]
                if simulation_type in {
                    "particle-3d",
                    "orbit-2d",
                    "circular-motion-2d",
                }
                else ["2d"]
            ),
            "deterministic": True,
        },
    }
    if simulation_type == "pendulum-2d":
        instruction["parameters"].update(
            {
                "anchor": [width * 0.5, 72.0],
                "length": 142.0,
                "angleRadians": initial_angle,
                "angularVelocity": 0.0,
                "physicalGravity": 9.81,
            }
        )
    elif simulation_type == "wave-2d":
        instruction["parameters"].update(
            {
                "amplitude": 68.0,
                "wavelength": 180.0,
                "angularFrequency": math.tau * 0.7,
                "phase": 0.0,
            }
        )
    elif simulation_type == "circular-motion-2d":
        instruction["parameters"].update(
            {
                "center": [width * 0.5, height * 0.5],
                "radius": orbit_radius,
                "angleRadians": 0.0,
                "angularSpeed": angular_speed,
            }
        )
    physics = PhysicsArtifact(
        title=title,
        instruction=instruction,
        simulation_type=simulation_type,
        particles=particles,
        gravity=gravity,
        friction=friction,
        restitution=restitution,
        bounds=(width, height),
        stats={"particles": count, "fps": 60, "collisionsPerSecond": 0},
    )
    return ScienceArtifact("physics", title, instruction, physics=physics)


def build_science_artifact(text: str) -> ScienceArtifact | None:
    graph = build_graph_artifact(text)
    if graph:
        return graph
    return build_physics_artifact(text)
