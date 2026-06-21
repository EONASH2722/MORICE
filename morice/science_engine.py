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
class GraphArtifact:
    title: str
    instruction: dict
    series: list[GraphSeries]
    x_range: tuple[float, float] = (-10.0, 10.0)
    y_range: tuple[float, float] = (-10.0, 10.0)


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    mass: float
    color: str


@dataclass
class PhysicsArtifact:
    title: str
    instruction: dict
    simulation_type: str
    particles: list[Particle]
    gravity: float = 180.0
    friction: float = 0.995
    bounds: tuple[float, float] = (640.0, 380.0)
    stats: dict = field(default_factory=dict)


@dataclass
class ScienceArtifact:
    kind: str
    title: str
    instruction: dict
    graph: GraphArtifact | None = None
    physics: PhysicsArtifact | None = None


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
    }

    def generic_visit(self, node):
        if type(node) not in self.allowed_nodes:
            raise UnsafeExpression(f"Unsupported expression node: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id not in {"x", "t", "theta", *SAFE_FUNCTIONS.keys(), *SAFE_CONSTANTS.keys()}:
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
    return any(marker in lowered for marker in {"plot", "graph", "chart", "curve", "function"}) and (
        "=" in lowered or "sin" in lowered or "cos" in lowered or "x" in lowered
    )


def wants_physics(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in {"simulate", "simulation", "physics", "particle", "projectile"}) and any(
        marker in lowered
        for marker in {
            "ball",
            "collision",
            "collisions",
            "fluid",
            "force",
            "gravity",
            "motion",
            "particle",
            "projectile",
            "rigid",
            "spring",
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
        r"\.\s*(?:show|include|including|with|also|then|and|local|graph|derivative|area|inflection)\b",
        clean,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    clean = re.split(
        r"\s+(?:show|include|including|with|also\s+show|then\s+show)\b",
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
    for match in re.finditer(r"y\s*=\s*([^,;\n]+)", raw, flags=re.IGNORECASE):
        candidate = _clean_expression_candidate(match.group(1))
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


def _graph_inspection_points(expression: str, x_values: np.ndarray, y_values: np.ndarray) -> list[dict]:
    points: list[dict] = []
    finite = np.isfinite(y_values)
    if not finite.any():
        return points

    for index in range(len(x_values) - 1):
        y0 = y_values[index]
        y1 = y_values[index + 1]
        if not math.isfinite(float(y0)) or not math.isfinite(float(y1)):
            continue
        if y0 == 0:
            root_x = float(x_values[index])
        elif y0 * y1 < 0:
            x0 = float(x_values[index])
            x1 = float(x_values[index + 1])
            root_x = x0 - float(y0) * (x1 - x0) / (float(y1) - float(y0))
        else:
            continue
        if all(abs(root_x - float(existing["x"])) > 0.08 for existing in points if existing["kind"] == "x-intercept"):
            points.append({"kind": "x-intercept", "label": "x-intercept", "x": root_x, "y": 0.0})
        if len([point for point in points if point["kind"] == "x-intercept"]) >= 6:
            break

    try:
        y_at_zero = float(_evaluate_expression(expression, np.asarray([0.0]))[0])
    except Exception:
        y_at_zero = float("nan")
    if math.isfinite(y_at_zero):
        points.append({"kind": "y-intercept", "label": "y-intercept", "x": 0.0, "y": y_at_zero})

    clipped_indices = np.where(finite & (np.abs(y_values) < 1_000))[0]
    if clipped_indices.size:
        local = y_values[clipped_indices]
        min_index = int(clipped_indices[int(np.nanargmin(local))])
        max_index = int(clipped_indices[int(np.nanargmax(local))])
        if np.nanmin(local) < 0 < np.nanmax(local) or len(points) <= 1:
            points.append(
                {
                    "kind": "minimum",
                    "label": "minimum",
                    "x": float(x_values[min_index]),
                    "y": float(y_values[min_index]),
                }
            )
        elif abs(float(y_values[max_index])) < 1_000:
            points.append(
                {
                    "kind": "maximum",
                    "label": "maximum",
                    "x": float(x_values[max_index]),
                    "y": float(y_values[max_index]),
                }
            )

    return points[:10]


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


def build_graph_artifact(text: str) -> ScienceArtifact | None:
    if not wants_graph(text):
        return None
    lowered = (text or "").lower()
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
    y_min = math.inf
    y_max = -math.inf
    for index, expression in enumerate(expressions):
        try:
            y_values = _evaluate_expression(expression, x_values)
        except Exception:
            continue
        finite = y_values[np.isfinite(y_values)]
        if finite.size:
            clipped = finite[np.abs(finite) < 1_000]
            if clipped.size:
                y_min = min(y_min, float(np.nanmin(clipped)))
                y_max = max(y_max, float(np.nanmax(clipped)))
        series.append(
            GraphSeries(
                label=f"y = {expression}",
                expression=expression,
                x=[float(v) for v in x_values],
                y=[float(v) if math.isfinite(float(v)) else float("nan") for v in y_values],
                color=palette[index % len(palette)],
                inspection_points=_graph_inspection_points(expression, x_values, y_values),
            )
        )
    if not series:
        return None
    if not math.isfinite(y_min) or not math.isfinite(y_max) or abs(y_min - y_max) < 1e-9:
        y_min, y_max = -10.0, 10.0
    padding = max(1.0, (y_max - y_min) * 0.12)
    title = _clean_title(text, "Generated Graph")
    instruction = {
        "simulationType": "graph",
        "equations": [item.expression for item in series],
        "parameters": {"domain": [-10, 10], "samples": len(x_values), "interactive": True},
    }
    graph = GraphArtifact(title, instruction, series, (-10.0, 10.0), (y_min - padding, y_max + padding))
    return ScienceArtifact("graph", title, instruction, graph=graph)


def _seed_from_text(text: str) -> int:
    value = 2166136261
    for ch in text or "":
        value ^= ord(ch)
        value = (value * 16777619) & 0xFFFFFFFF
    return value or 7


def _particle_count(text: str) -> int:
    match = re.search(r"(\d{2,5})\s*(?:particles|balls|bodies)", text or "", flags=re.IGNORECASE)
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

    if "projectile" in lowered:
        count = 1
        particles.append(Particle(60.0, height - 60.0, 245.0, -310.0, 10.0, 1.0, "#7cf7b5"))
        gravity = 260.0
        simulation_type = "projectile-2d"
    else:
        gravity = 90.0 if "zero" not in lowered else 0.0
        simulation_type = "particle-2d"
        if "3d" in lowered or "three" in lowered:
            simulation_type = "particle-3d-projected"
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
            "bounds": [width, height],
            "deterministic": True,
        },
    }
    physics = PhysicsArtifact(
        title=title,
        instruction=instruction,
        simulation_type=simulation_type,
        particles=particles,
        gravity=gravity,
        bounds=(width, height),
        stats={"particles": count, "fps": 60, "collisionsPerSecond": 0},
    )
    return ScienceArtifact("physics", title, instruction, physics=physics)


def build_science_artifact(text: str) -> ScienceArtifact | None:
    graph = build_graph_artifact(text)
    if graph:
        return graph
    return build_physics_artifact(text)
