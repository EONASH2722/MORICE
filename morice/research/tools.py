"""Deterministic, unit-aware research computation without Python eval/exec."""
from __future__ import annotations

import ast
import math
import operator
from importlib.metadata import version

from .ingestion import checkpoint


class ScientificTools:
    capabilities = ("unit_calculation", "parameter_sweep", "dataset_profile")

    def __init__(self):
        self._units = None

    def calculate(self, expression, inputs, output_unit="", cancel=None):
        checkpoint(cancel)
        if not isinstance(expression, str) or len(expression) > 1000 or len(inputs) > 64:
            raise ValueError("Calculation exceeds expression/input limits.")
        if self._units is None:
            from pint import UnitRegistry
            self._units = UnitRegistry()
        units = self._units
        variables = {}
        for name, item in inputs.items():
            if not name.isidentifier() or not isinstance(item, dict):
                raise ValueError("Each input must have an identifier, numeric value and unit.")
            value = float(item["value"])
            if not math.isfinite(value) or abs(value) > 1e100:
                raise ValueError("Inputs must be finite and bounded.")
            variables[name] = units.Quantity(value, str(item.get("unit", "")))
        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 150:
            raise ValueError("Expression is too complex.")

        def evaluate(node):
            checkpoint(cancel)
            if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
                if not math.isfinite(node.value) or abs(node.value) > 1e100:
                    raise ValueError("Numeric literal exceeds calculation limits.")
                return units.Quantity(float(node.value))
            if isinstance(node, ast.Name) and node.id in variables:
                return variables[node.id]
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                return evaluate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            if isinstance(node, ast.BinOp):
                left, right = evaluate(node.left), evaluate(node.right)
                if isinstance(node.op, ast.Pow):
                    exponent = right.to("").magnitude
                    if abs(exponent) > 12:
                        raise ValueError("Exponent must be between -12 and 12.")
                    value = left ** exponent
                else:
                    operation = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}.get(type(node.op))
                    if operation is None:
                        raise ValueError("Unsupported calculation operator.")
                    value = operation(left, right)
                if not math.isfinite(value.magnitude) or abs(value.magnitude) > 1e100:
                    raise ValueError("Calculation overflow or non-finite result.")
                return value
            raise ValueError("Only input names, numbers and + - * / ** are permitted.")

        answer = evaluate(tree.body)
        answer = answer.to(output_unit) if output_unit else answer.to_base_units()
        return {"inputs": inputs, "method": "Bounded AST arithmetic with Pint dimensional validation",
                "expression": expression, "result": {"value": float(answer.magnitude), "unit": str(answer.units)},
                "assumptions": ["Input units and equation supplied by user; dimensional consistency does not establish physical validity."],
                "tool_version": version("pint"), "requested_unit": output_unit}

    def sweep(self, expression, inputs, parameter, values, output_unit="", cancel=None):
        if parameter not in inputs or not 1 <= len(values) <= 1000:
            raise ValueError("Sweep needs an existing parameter and 1–1000 values.")
        rows = []
        for value in values:
            checkpoint(cancel)
            varied = {name: dict(item) for name, item in inputs.items()}
            varied[parameter]["value"] = value
            result = self.calculate(expression, varied, output_unit, cancel)
            rows.append({"parameter": value, **result["result"]})
        return {"inputs": inputs, "method": "Deterministic parameter sweep", "expression": expression,
                "parameter": parameter, "result": rows, "requested_unit": output_unit}
