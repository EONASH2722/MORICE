"""Bounded, deterministic function analysis. AST constructors never eval user text.

Exact analysis covers small polynomials/rationals and affine sin/cos/tan/exp/log.
Everything else uses explicitly viewport-only sampled evidence.
"""
from __future__ import annotations
import ast
import math
from dataclasses import dataclass, field, asdict
import sympy as sp
from .numeric_format import format_number, format_point

X = sp.Symbol("x", real=True)


@dataclass
class GraphInsight:
    expression: str
    function_type: str = "general"
    method: str = "numeric viewport approximation"
    domain: str | None = None
    range: str | None = None
    roots: list[dict] = field(default_factory=list)
    root_family: str | None = None
    y_intercept: dict | None = None
    vertex: dict | None = None
    symmetry_axis: str | None = None
    discriminant: str | None = None
    critical_points: list[dict] = field(default_factory=list)
    extrema: list[dict] = field(default_factory=list)
    asymptotes: list[dict] = field(default_factory=list)
    holes: list[dict] = field(default_factory=list)
    amplitude: str | None = None
    period: str | None = None
    phase_shift: str | None = None
    vertical_shift: str | None = None
    behavior: str | None = None
    derivative: str | None = None
    viewport: tuple[float, float] = (-10, 10)
    notes: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _construct(node, exclusions):
    if isinstance(node, ast.Expression):
        return _construct(node.body, exclusions)
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        if not math.isfinite(node.value) or abs(node.value) > 1e12:
            raise ValueError("Number outside analysis bounds")
        return sp.Rational(str(node.value))
    if isinstance(node, ast.Name):
        return {"x": X, "pi": sp.pi, "e": sp.E, "tau": 2 * sp.pi}[node.id]
    if isinstance(node, ast.UnaryOp):
        value = _construct(node.operand, exclusions)
        if isinstance(node.op, ast.USub): return -value
        if isinstance(node.op, ast.UAdd): return value
    if isinstance(node, ast.BinOp):
        left, right = _construct(node.left, exclusions), _construct(node.right, exclusions)
        if isinstance(node.op, ast.Add): return left + right
        if isinstance(node.op, ast.Sub): return left - right
        if isinstance(node.op, ast.Mult): return left * right
        if isinstance(node.op, ast.Div):
            exclusions.append(right)
            return left / right
        if isinstance(node.op, ast.Pow) and right.is_number and abs(float(right)) <= 12:
            if right.is_negative: exclusions.append(left)
            return left ** right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords and len(node.args) == 1:
        functions = {"sin": lambda v: sp.sin(v, evaluate=False), "cos": lambda v: sp.cos(v, evaluate=False), "tan": lambda v: sp.tan(v, evaluate=False), "exp": sp.exp,
                     "log": sp.log, "log10": lambda v: sp.log(v)/sp.log(10),
                     "sqrt": sp.sqrt, "abs": sp.Abs, "sinh": sp.sinh,
                     "cosh": sp.cosh, "tanh": sp.tanh, "asin": sp.asin,
                     "acos": sp.acos, "atan": sp.atan}
        return functions[node.func.id](_construct(node.args[0], exclusions))
    raise ValueError("Unsupported symbolic expression")


def _real_roots(expression):
    poly = sp.Poly(expression, X)
    if poly.degree() > 8 or len(poly.terms()) > 24: raise ValueError("Polynomial analysis bounds exceeded")
    if poly.is_zero: return []
    return sp.polys.polytools.real_roots(poly, multiple=False)


def _point(x, y, **extra):
    return {"x": float(x), "y": float(y), "exact_x": str(x), "exact_y": str(y), **extra}


def analyze_graph(expression, inspection_points=(), viewport=(-10, 10)):
    result = GraphInsight(expression, viewport=viewport)
    try:
        tree = ast.parse(expression.replace("^", "**"), mode="eval")
        if len(expression) > 512 or sum(1 for _ in ast.walk(tree)) > 128:
            raise ValueError("Expression analysis bounds exceeded")
        exclusions = []
        expr = _construct(tree, exclusions)
        if sp.count_ops(expr) > 80: raise ValueError("Analysis bounds exceeded")
        excluded = sorted({root for denominator in exclusions for root, _ in _real_roots(sp.fraction(sp.cancel(denominator))[0])}, key=float)
        simplified = sp.cancel(expr)
        numerator, denominator = sp.fraction(simplified)
        result.derivative = str(sp.diff(expr, X))
        if expr.is_rational_function(X):
            npoly, dpoly = sp.Poly(numerator, X), sp.Poly(denominator, X)
            roots = _real_roots(numerator)
            result.roots = [_point(r, 0, multiplicity=m) for r, m in roots if r not in excluded]
            if 0 not in excluded and expr.subs(X, 0).is_finite:
                result.y_intercept = _point(0, expr.subs(X, 0))
            result.method = "symbolic (real domain)"
            result.domain = "ℝ" + (" except " + ", ".join(str(r) for r in excluded) if excluded else "")
            if dpoly.degree() == 0 and not excluded:
                _polynomial(result, expr, npoly)
            else:
                result.function_type = "rational"
                for r in excluded:
                    if denominator.subs(X, r) != 0:
                        result.holes.append(_point(r, simplified.subs(X, r)))
                    else:
                        result.asymptotes.append({"kind": "vertical", "equation": f"x = {r}"})
                quotient, _ = sp.div(npoly, dpoly)
                if npoly.degree() < dpoly.degree():
                    result.asymptotes.append({"kind": "horizontal", "equation": "y = 0"})
                elif npoly.degree() == dpoly.degree():
                    result.asymptotes.append({"kind": "horizontal", "equation": "y = " + str(npoly.LC()/dpoly.LC())})
                elif quotient.degree() == 1:
                    result.asymptotes.append({"kind": "slant", "equation": "y = " + str(quotient.as_expr())})
                _critical(result, expr, excluded)
                result.notes.append("Range is not established by this bounded analysis.")
            return result
        functions = list(expr.atoms(sp.sin, sp.cos, sp.tan, sp.exp, sp.log))
        if len(functions) == 1:
            atom = functions[0]
            amplitude = sp.expand(expr).coeff(atom)
            shift = sp.simplify(expr - amplitude*atom)
            argument = atom.args[0]
            b = sp.diff(argument, X)
            c = sp.simplify(argument-b*X)
            if any(v.has(X) for v in (amplitude, shift, b, c)) or b == 0 or amplitude == 0:
                raise ValueError("Only affine function transforms have global analysis")
            result.method = "symbolic (real domain)"
            result.vertical_shift, result.phase_shift = str(shift), str(-c/b)
            value = expr.subs(X, 0)
            if value.is_real and value.is_finite: result.y_intercept = _point(0, value)
            if atom.func in {sp.sin, sp.cos, sp.tan}:
                result.function_type = "trigonometric"
                result.period = str(sp.simplify((sp.pi if atom.func == sp.tan else 2*sp.pi)/abs(b)))
                result.domain = "ℝ"
                if atom.func == sp.tan:
                    result.domain = f"ℝ except x = (pi/2 - ({c}) + n*pi)/({b}), n ∈ ℤ"
                    result.range = "ℝ"
                    result.asymptotes.append({"kind":"vertical family", "equation": result.domain[9:]})
                    result.root_family = f"x = (atan({-shift/amplitude}) - ({c}) + n*pi)/({b}), n ∈ ℤ"
                else:
                    result.amplitude = str(abs(amplitude))
                    result.range = f"[{shift-abs(amplitude)}, {shift+abs(amplitude)}]"
                    ratio = -shift/amplitude
                    if abs(float(ratio)) <= 1:
                        if atom.func == sp.sin:
                            angle = sp.asin(ratio)
                            result.root_family = f"x = ({angle} - ({c}) + 2*n*pi)/({b}) or (pi - ({angle}) - ({c}) + 2*n*pi)/({b}), n ∈ ℤ"
                        else:
                            result.root_family = f"x = (±acos({ratio}) - ({c}) + 2*n*pi)/({b}), n ∈ ℤ"
                    else: result.notes.append("No real roots.")
                result.behavior = "Periodic; no finite limit at ±∞."
            elif atom.func == sp.exp:
                result.function_type, result.domain = "exponential", "ℝ"
                result.range = f"({shift}, ∞)" if amplitude > 0 else f"(-∞, {shift})"
                result.asymptotes.append({"kind":"horizontal", "equation":f"y = {shift}"})
                result.behavior = "Increasing" if amplitude*b > 0 else "Decreasing"
                ratio = -shift/amplitude
                if ratio > 0: result.roots = [_point(sp.simplify((sp.log(ratio)-c)/b), 0, multiplicity=1)]
                else: result.notes.append("No real roots.")
            elif atom.func == sp.log:
                result.function_type, result.range = "logarithmic", "ℝ"
                boundary = -c/b
                result.domain = f"({boundary}, ∞)" if b > 0 else f"(-∞, {boundary})"
                result.asymptotes.append({"kind":"vertical", "equation":f"x = {boundary}"})
                result.roots = [_point(sp.simplify((sp.exp(-shift/amplitude)-c)/b), 0, multiplicity=1)]
                result.behavior = "Increasing on its domain" if amplitude*b > 0 else "Decreasing on its domain"
            return result
        raise ValueError("No bounded symbolic classification")
    except (SyntaxError, ValueError, TypeError, KeyError, NotImplementedError, sp.PolynomialError, OverflowError):
        # Do not retain partially established global claims after a failed analysis.
        result = GraphInsight(expression, viewport=viewport)
        result.notes.append(f"Approximate sampled features only within x ∈ [{viewport[0]}, {viewport[1]}]; global domain, range and asymptotes are unknown.")
        for point in inspection_points:
            entry = dict(point, approximate=True)
            kind = str(point.get("kind", point.get("type", ""))).lower()
            if "root" in kind or "x-intercept" in kind: result.roots.append(entry)
            elif "extrem" in kind or "maximum" in kind or "minimum" in kind: result.extrema.append(entry)
        return result


def _critical(result, expr, excluded=()):
    numerator = sp.fraction(sp.cancel(sp.diff(expr, X)))[0]
    if numerator == 0: return
    roots = _real_roots(numerator)
    boundaries = sorted(set([r for r, _ in roots] + list(excluded)), key=lambda value: sp.N(value, 50))
    for root, _ in roots:
        if root in excluded: continue
        value = expr.subs(X, root)
        if not value.is_finite: continue
        # Sign on either side also handles flat repeated extrema (e.g. x**4).
        derivative = sp.diff(expr, X)
        index = boundaries.index(root)
        left = (root+boundaries[index-1])/2 if index else root-1
        right = (root+boundaries[index+1])/2 if index+1 < len(boundaries) else root+1
        before, after = derivative.subs(X, left), derivative.subs(X, right)
        kind = "local minimum" if before < 0 < after else "local maximum" if before > 0 > after else "stationary point"
        point = _point(root, value, kind=kind)
        result.critical_points.append(point)
        if kind != "stationary point": result.extrema.append(point)


def _polynomial(result, expr, poly):
    degree = poly.degree()
    result.function_type = "quadratic" if degree == 2 else "polynomial"
    _critical(result, expr)
    if degree <= 0:
        result.range = "{" + str(expr) + "}"
        if expr == 0: result.root_family = "Every real x"
        result.behavior = "Constant"
    elif degree % 2:
        result.range = "ℝ"
        result.behavior = "x → -∞: y → " + ("-∞" if poly.LC() > 0 else "∞") + "; x → ∞: y → " + ("∞" if poly.LC() > 0 else "-∞")
    else:
        values = [expr.subs(X, root) for root, _ in _real_roots(sp.diff(expr, X))]
        extreme = (min if poly.LC() > 0 else max)(values, key=lambda value: sp.N(value, 50))
        result.range = f"[{sp.simplify(extreme)}, ∞)" if poly.LC() > 0 else f"(-∞, {sp.simplify(extreme)}]"
        result.behavior = "Both ends tend to " + ("∞" if poly.LC() > 0 else "-∞")
    if degree == 2:
        a, b, c = poly.all_coeffs()
        vertex_x = -b/(2*a)
        result.vertex = _point(vertex_x, expr.subs(X, vertex_x))
        result.symmetry_axis = f"x = {vertex_x}"
        result.discriminant = str(b*b-4*a*c)
        result.behavior = ("Opens upward" if a > 0 else "Opens downward") + "; " + result.behavior
    if not result.roots and not result.root_family: result.notes.append("No real roots.")


def summarize_insight(insight):
    parts = [f"{insight.expression}: {insight.function_type}."]
    if insight.roots:
        parts.append("Real roots: " + ", ".join(format_number(p['x']) + (f" (multiplicity {p['multiplicity']})" if p.get('multiplicity',1)>1 else "") for p in insight.roots) + ".")
    if insight.root_family: parts.append("Roots: " + insight.root_family + ".")
    if insight.y_intercept: parts.append("Y-intercept " + format_point(insight.y_intercept['x'], insight.y_intercept['y']) + ".")
    if insight.vertex: parts.append("Vertex " + format_point(insight.vertex['x'], insight.vertex['y']) + f"; symmetry {insight.symmetry_axis}; discriminant {insight.discriminant}.")
    for point in insight.critical_points[:8]: parts.append(point['kind'].capitalize() + " " + format_point(point['x'], point['y']) + ".")
    if insight.domain: parts.append("Domain: " + insight.domain + ".")
    if insight.range: parts.append("Range: " + insight.range + ".")
    if insight.asymptotes: parts.append("Asymptotes: " + "; ".join(p['equation'] for p in insight.asymptotes) + ".")
    if insight.holes: parts.append("Excluded holes: " + ", ".join(format_point(p['x'],p['y']) for p in insight.holes) + ".")
    if insight.period: parts.append(f"Period {insight.period}; phase shift {insight.phase_shift}; vertical shift {insight.vertical_shift}." + (f" Amplitude {insight.amplitude}." if insight.amplitude else ""))
    if insight.behavior: parts.append(insight.behavior + ".")
    parts.extend(insight.notes)
    return " ".join(parts)
