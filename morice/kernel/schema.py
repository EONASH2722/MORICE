"""Shared existing tool schema validation, also used by native capabilities."""
from __future__ import annotations
import math
import re
from typing import Any


class ToolValidationError(ValueError):
    pass


def validate_schema(value: Any, schema: dict[str, Any], path: str = "arguments") -> None:
    if 'anyOf' in schema:
        for variant in schema['anyOf']:
            try:validate_schema(value,variant,path);break
            except ToolValidationError:pass
        else:raise ToolValidationError(f'{path} must match a declared value type.')
    expected = schema.get("type")
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
    }
    type_matches = expected not in types or isinstance(value, types[expected])
    if expected in {"integer", "number"} and isinstance(value, bool):
        type_matches = False
    if not type_matches:
        raise ToolValidationError(f"{path} must be {expected}.")
    if expected in {'number','integer'}:
        try:finite=math.isfinite(float(value))
        except (OverflowError,ValueError):finite=False
        if not finite:raise ToolValidationError(f"{path} must be finite.")
        if 'minimum' in schema and value<schema['minimum']:raise ToolValidationError(f"{path} is below its supported minimum.")
        if 'maximum' in schema and value>schema['maximum']:raise ToolValidationError(f"{path} exceeds its supported maximum.")
    if expected == "object":
        required = schema.get("required", ())
        for key in required:
            if key not in value:
                raise ToolValidationError(f"{path}.{key} is required.")
        properties = schema.get("properties", {})
        for key, child in value.items():
            if key in properties:
                validate_schema(child, properties[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise ToolValidationError(f"{path}.{key} is not supported.")
    elif expected == "array":
        if len(value)<int(schema.get('minItems',0)):raise ToolValidationError(f"{path} has too few items.")
        if len(value) > int(schema.get("maxItems", 100_000)):
            raise ToolValidationError(f"{path} has too many items.")
        child = schema.get("items")
        if child:
            for index, item in enumerate(value):
                validate_schema(item, child, f"{path}[{index}]")
    elif expected == "string":
        if len(value)<int(schema.get('minLength',0)):raise ToolValidationError(f"{path} is too short.")
        if len(value) > int(schema.get("maxLength", 1_000_000)):
            raise ToolValidationError(f"{path} is too long.")
        if pattern := schema.get("pattern"):
            if not re.fullmatch(pattern, value):
                raise ToolValidationError(f"{path} has an invalid format.")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolValidationError(f"{path} must be one of {schema['enum']}.")
