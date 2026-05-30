"""Lightweight schema helpers shared across Nodus packages."""

from __future__ import annotations

from typing import Any


SIMPLE_TYPE_ALIASES: dict[str, str] = {
    "string": "string",
    "str": "string",
    "int": "integer",
    "integer": "integer",
    "float": "number",
    "number": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "map": "object",
    "dict": "object",
    "object": "object",
    "list": "array",
    "array": "array",
    "nil": "null",
    "null": "null",
    "any": "any",
}

JSON_TYPE_TO_PYTHON: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
    "null": (type(None),),
}


def normalize_schema(schema: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    """Normalize simple-form or JSON Schema object definitions.

    The supported simple form is a flat map of ``field_name -> type_name``.
    All fields in simple form are treated as required.
    """
    if not schema:
        return {}, None
    if not isinstance(schema, dict):
        return None, "schema must be a map"
    if schema.get("type") == "object":
        return dict(schema), None

    properties: dict[str, Any] = {}
    required: list[str] = []
    for field_name, type_name in schema.items():
        if not isinstance(field_name, str):
            return None, "schema field names must be strings"
        if not isinstance(type_name, str):
            return None, f"schema type for parameter '{field_name}' must be a string"
        canonical_type = SIMPLE_TYPE_ALIASES.get(type_name)
        if canonical_type is None:
            return None, (
                f"unknown type '{type_name}' for parameter '{field_name}' "
                "(allowed: string, str, int, integer, float, number, bool, boolean, "
                "map, dict, object, list, array, nil, null, any)"
            )
        properties[field_name] = {} if canonical_type == "any" else {"type": canonical_type}
        required.append(field_name)
    return {"type": "object", "properties": properties, "required": required}, None


def validate_payload(schema: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    """Validate a payload against a normalized object schema."""
    if not schema:
        return []
    if not isinstance(payload, dict):
        return [f"Payload must be a dict, got {type(payload).__name__!r}"]

    errors: list[str] = []
    required = schema.get("required") or []
    properties = schema.get("properties") or {}

    for field_name in required:
        if field_name not in payload or payload[field_name] is None:
            errors.append(f"Missing required field: {field_name!r}")

    for field_name, spec in properties.items():
        if field_name not in payload or not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        if not expected:
            continue
        expected_types = JSON_TYPE_TO_PYTHON.get(expected)
        if expected_types is None:
            continue
        actual = payload[field_name]
        if expected == "integer":
            valid = isinstance(actual, int) and not isinstance(actual, bool)
        elif expected == "number":
            valid = isinstance(actual, (int, float)) and not isinstance(actual, bool)
        else:
            valid = isinstance(actual, expected_types)
        if not valid:
            errors.append(
                f"Field {field_name!r}: expected type {expected!r}, "
                f"got {type(actual).__name__!r}"
            )

    return errors
