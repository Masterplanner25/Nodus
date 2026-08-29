"""Argument and return-shape contracts, shared by every typed boundary.

Two surfaces hand values across a boundary and need the same contract:

- `std:tool` — a tool declared in Nodus, whose handler runs in the VM;
- `NodusRuntime.register_function` — a Python callable running **outside** the
  VM and the sandbox entirely.

These lived in `builtins/tool_module.py` and served only the first, so the host
surface had arity and nothing else: a map reached a parameter meant to be a path
and the call succeeded with a plausible-looking result (#493). The weaker
contract was on the more dangerous side of the boundary.

They live here so both surfaces resolve to **one** validator and report failures
identically. `tool_module` imports these under its former private names, so it is
the same code rather than a copy that can drift — which is the shape this
codebase keeps finding, and the reason a second implementation was not written.
"""

from __future__ import annotations

from nodus.vm.types import Record

#: Nodus type name -> JSON Schema type. The vocabulary a schema may name.
NODUS_TO_JSON_TYPE = {
    "string": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "map": "object",
    "record": "object",
    "list": "array",
    "nil": "null",
}

#: Type names that are real but cannot appear in a schema, and why.
UNSCHEMABLE_TYPES = {
    "function": "a function value does not cross a tool boundary",
}


def as_dict(value):
    if isinstance(value, Record):
        return dict(value.fields)
    if isinstance(value, dict):
        return value
    return None


def normalize_runtime_schema(schema):
    """Normalize simple-form or JSON Schema. Returns (normalized_dict, err_msg_or_None).

    Named apart from `nodus_lang_schema.validation.normalize_schema`, which has
    the same signature and overlapping semantics but is **not** the same
    question. That one serves the syscall/extension ABI and is deliberately
    free of any VM dependency; this one is about values crossing a *runtime*
    boundary, so it understands `Record` and the Nodus type vocabulary
    (`map`, `record`, `nil`, and `function` as explicitly unschemable).
    Merging them would mean giving the ABI package a VM import.
    """
    if not schema:
        return {}, None
    d = as_dict(schema)
    if d is None:
        return None, "schema must be a map"
    # JSON Schema form: has top-level "type": "object"
    if d.get("type") == "object":
        # Deep-convert nested Records in properties so "type" in prop works correctly
        props_raw = as_dict(d.get("properties") or {}) or {}
        props = {k: (as_dict(v) or {} if v is not None else {}) for k, v in props_raw.items()}
        req = list(d.get("required") or [])
        normalized: dict = {"type": "object", "properties": props}
        if req:
            normalized["required"] = req
        return normalized, None
    # Simple form: flat map of param name → Nodus type string
    properties = {}
    required = []
    for param_name, type_name in d.items():
        if type_name == "any":
            properties[param_name] = {}
        else:
            json_type = NODUS_TO_JSON_TYPE.get(type_name)
            if json_type is None:
                reason = UNSCHEMABLE_TYPES.get(type_name)
                if reason:
                    return None, (
                        f"type '{type_name}' cannot appear in a tool schema for "
                        f"parameter '{param_name}': {reason}"
                    )
                allowed = ", ".join(sorted(NODUS_TO_JSON_TYPE) + ["any"])
                return None, (
                    f"unknown type '{type_name}' for parameter '{param_name}' "
                    f"(allowed: {allowed})"
                )
            properties[param_name] = {"type": json_type}
        required.append(param_name)
    return {"type": "object", "properties": properties, "required": required}, None


def validate_args(args, schema: dict):
    """Return error message if args fail schema validation, else None."""
    if not schema or schema.get("type") != "object":
        return None
    args_d = as_dict(args) if args is not None else {}
    if args_d is None:
        return "args must be a map"
    required = schema.get("required", [])
    props = schema.get("properties", {})
    for req in required:
        if req not in args_d:
            return f"missing required argument: '{req}'"
    for key, val in args_d.items():
        if key in props:
            prop = props[key]
            if "type" in prop:
                err = check_json_type(val, prop["type"], key)
                if err:
                    return err
    return None


def check_json_type(val, expected: str, key: str):
    if expected == "string":
        if not isinstance(val, str):
            return f"argument '{key}' must be a string"
    elif expected == "integer":
        if not isinstance(val, int) or isinstance(val, bool):
            return f"argument '{key}' must be an integer"
    elif expected == "number":
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            return f"argument '{key}' must be a number"
    elif expected == "boolean":
        if not isinstance(val, bool):
            return f"argument '{key}' must be a boolean"
    elif expected == "object":
        if not isinstance(val, (dict, Record)):
            return f"argument '{key}' must be a map"
    elif expected == "array":
        if not isinstance(val, list):
            return f"argument '{key}' must be a list"
    elif expected == "null":
        if val is not None:
            return f"argument '{key}' must be nil"
    return None


def validate_return(result, schema: dict):
    """Return error message if result fails returns_schema, else None.

    Only validates object-type schemas (type: object). Returns None if the
    schema is empty or non-object — those cases are not enforced in Phase A.
    """
    if not schema or schema.get("type") != "object":
        return None
    if isinstance(result, Record):
        result_d = dict(result.fields)
    elif isinstance(result, dict):
        result_d = result
    else:
        return f"expected a map return value, got {type(result).__name__!r}"
    return validate_args(result_d, schema)
