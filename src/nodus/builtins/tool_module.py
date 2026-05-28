"""std:tool — Tool registry builtins for Nodus VM (v4.0 Design Doc 06)."""

import re
import sys

from nodus.vm.vm import Closure, Record

_TOOL_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_.\-]*$')
_TOOL_NAME_MAX_LEN = 200

_NODUS_TO_JSON_TYPE = {
    "string": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "map": "object",
    "list": "array",
    "nil": "null",
}


def _as_dict(value):
    if isinstance(value, Record):
        return dict(value.fields)
    if isinstance(value, dict):
        return value
    return None


def _validate_tool_name(name):
    """Return error message if invalid, else None."""
    if not isinstance(name, str) or not name:
        return "tool name must be a non-empty string"
    if "." not in name:
        return f"tool name '{name}' must use dotted namespacing (e.g. 'myapp.tool_name')"
    if not _TOOL_NAME_RE.match(name):
        return f"tool name '{name}' contains invalid characters (allowed: [a-z0-9_.-], must start with letter or digit)"
    return None


def _normalize_schema(schema):
    """Normalize simple-form or JSON Schema. Returns (normalized_dict, err_msg_or_None)."""
    if not schema:
        return {}, None
    d = _as_dict(schema)
    if d is None:
        return None, "schema must be a map"
    # JSON Schema form: has top-level "type": "object"
    if d.get("type") == "object":
        return dict(d), None
    # Simple form: flat map of param name → Nodus type string
    properties = {}
    required = []
    for param_name, type_name in d.items():
        if type_name == "any":
            properties[param_name] = {}
        else:
            json_type = _NODUS_TO_JSON_TYPE.get(type_name)
            if json_type is None:
                return None, (
                    f"unknown type '{type_name}' for parameter '{param_name}' "
                    f"(allowed: string, int, float, bool, map, list, nil, any)"
                )
            properties[param_name] = {"type": json_type}
        required.append(param_name)
    return {"type": "object", "properties": properties, "required": required}, None


def _validate_args(args, schema: dict):
    """Return error message if args fail schema validation, else None."""
    if not schema or schema.get("type") != "object":
        return None
    args_d = _as_dict(args) if args is not None else {}
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
                err = _check_json_type(val, prop["type"], key)
                if err:
                    return err
    return None


def _check_json_type(val, expected: str, key: str):
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


def _to_host_value(value):
    """Translate Nodus runtime value to Python value for Python-callable handlers."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, float):
        # Convert whole-number floats to int (Nodus uses float for numeric literals)
        return int(value) if value.is_integer() else value
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return [_to_host_value(item) for item in value]
    if isinstance(value, Record):
        result = {str(k): _to_host_value(v) for k, v in value.fields.items()}
        if value.kind == "error":
            result["__nodus_err__"] = True
        return result
    if isinstance(value, dict):
        return {str(k): _to_host_value(v) for k, v in value.items()}
    return value


def _to_runtime_value(value):
    """Translate Python value to Nodus runtime value (dicts become Records for dot-access)."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [_to_runtime_value(item) for item in value]
    if isinstance(value, dict):
        return Record({str(k): _to_runtime_value(v) for k, v in value.items()})
    return value


def _root_vm(vm):
    """Follow the _caller_vm chain to the root VM (where tool_registry lives).

    NodusModule.invoke_function() creates a fresh child VM per call and sets
    child._caller_vm = caller_vm.  Stdlib builtins (tool, test, …) close over
    whichever VM was current at registration time.  Since stdlib methods are
    always called via invoke_function, the closing vm is a child VM, not the
    root.  This traversal ensures builtins always mutate the root VM's shared
    registry, not a discarded per-call child VM.
    """
    root = vm
    while True:
        parent = getattr(root, "_caller_vm", None)
        if parent is None:
            return root
        root = parent


def _entry_for_nodus(entry: dict) -> Record:
    """Return entry as a Record safe to return to Nodus (excludes internal-only keys)."""
    fields = {k: v for k, v in entry.items() if not k.startswith("_")}
    return Record(fields, kind="record")


def register(vm, registry) -> None:
    """Register tool_* builtins onto the registry."""

    def builtin_tool_register(meta):
        rvm = _root_vm(vm)
        d = _as_dict(meta)
        if d is None:
            return rvm.make_err("tool_error", "tool.register: metadata must be a map", payload={
                "category": "invalid_metadata", "name": None, "details": "metadata must be a map",
            })
        name = d.get("name")
        name_err = _validate_tool_name(name)
        if name_err:
            category = "invalid_name" if isinstance(name, str) else "invalid_metadata"
            return rvm.make_err("tool_error", f"tool.register: {name_err}", payload={
                "category": category, "name": name, "details": name_err,
            })
        handler = d.get("handler")
        if handler is None:
            return rvm.make_err("tool_error", "tool.register: 'handler' is required", payload={
                "category": "invalid_metadata", "name": name,
                "details": "missing required field 'handler'",
            })
        desc = d.get("description")
        if not isinstance(desc, str) or not desc:
            return rvm.make_err(
                "tool_error",
                "tool.register: 'description' must be a non-empty string",
                payload={
                    "category": "invalid_metadata", "name": name,
                    "details": "missing or invalid 'description'",
                },
            )
        schema_raw = _as_dict(d.get("schema")) or {}
        schema, schema_err = _normalize_schema(schema_raw)
        if schema_err:
            return rvm.make_err("tool_error", f"tool.register: invalid schema: {schema_err}", payload={
                "category": "invalid_metadata", "name": name, "details": schema_err,
            })
        if len(name) > _TOOL_NAME_MAX_LEN:
            print(
                f"Warning: tool name exceeds {_TOOL_NAME_MAX_LEN} characters.",
                file=sys.stderr,
            )
        tags_raw = d.get("tags")
        tags = list(tags_raw) if isinstance(tags_raw, list) else []
        meta_raw = _as_dict(d.get("metadata")) or {}
        entry = {
            "name": name,
            "handler": handler,
            "description": desc,
            "schema": schema,
            "version": d.get("version") or "1.0.0",
            "tags": tags,
            "deprecated": bool(d.get("deprecated", False)),
            "metadata": meta_raw,
        }
        with rvm._tool_registry_lock:
            if name in rvm.tool_registry:
                existing = rvm.tool_registry[name]
                return rvm.make_err(
                    "tool_error",
                    f"Tool '{name}' is already registered",
                    payload={
                        "category": "registration_conflict",
                        "name": name,
                        "details": {
                            "existing_description": existing["description"],
                            "attempted_description": desc,
                        },
                    },
                )
            rvm.tool_registry[name] = entry
        return _entry_for_nodus(entry)

    def builtin_tool_unregister(name):
        rvm = _root_vm(vm)
        if not isinstance(name, str):
            return rvm.make_err("tool_error", "tool.unregister: name must be a string", payload={
                "category": "invalid_metadata", "name": None, "details": "name must be a string",
            })
        with rvm._tool_registry_lock:
            entry = rvm.tool_registry.pop(name, None)
        if entry is None:
            return rvm.make_err("tool_error", f"Tool '{name}' is not registered", payload={
                "category": "tool_not_found", "name": name, "details": None,
            })
        rvm._tool_deprecated_warned.discard(name)
        return _entry_for_nodus(entry)

    def builtin_tool_invoke(name, args=None):
        rvm = _root_vm(vm)
        if not isinstance(name, str):
            return rvm.make_err("tool_error", "tool.invoke: name must be a string", payload={
                "category": "invalid_metadata", "name": None, "details": "name must be a string",
            })
        with rvm._tool_registry_lock:
            entry = rvm.tool_registry.get(name)
        if entry is None:
            return rvm.make_err("tool_error", f"Tool '{name}' is not registered", payload={
                "category": "tool_not_found", "name": name, "details": None,
            })
        if args is None:
            args = {}
        schema = entry.get("schema") or {}
        if schema:
            schema_err = _validate_args(args, schema)
            if schema_err:
                return rvm.make_err(
                    "tool_error",
                    f"Tool '{name}': schema validation failed: {schema_err}",
                    payload={
                        "category": "schema_mismatch", "name": name, "details": schema_err,
                    },
                )
        if entry.get("deprecated") and name not in rvm._tool_deprecated_warned:
            rvm._tool_deprecated_warned.add(name)
            print(
                f"Warning: tool '{name}' is deprecated."
                " (This warning is shown once per VM instance.)",
                file=sys.stderr,
            )
        handler = entry["handler"]
        if isinstance(handler, Closure):
            return rvm.run_closure(handler, [args])
        if callable(handler):
            host_args = _to_host_value(args)
            result = handler(host_args)
            return _to_runtime_value(result)
        return rvm.make_err("tool_error", f"Tool '{name}': handler is not callable", payload={
            "category": "handler_error", "name": name, "details": "handler is not callable",
        })

    def builtin_tool_lookup(name):
        rvm = _root_vm(vm)
        if not isinstance(name, str):
            return rvm.make_err("tool_error", "tool.lookup: name must be a string", payload={
                "category": "invalid_metadata", "name": None, "details": "name must be a string",
            })
        with rvm._tool_registry_lock:
            entry = rvm.tool_registry.get(name)
        if entry is None:
            return rvm.make_err("tool_error", f"Tool '{name}' is not registered", payload={
                "category": "tool_not_found", "name": name, "details": None,
            })
        return _entry_for_nodus(entry)

    def builtin_tool_list(filter_map=None):
        rvm = _root_vm(vm)
        with rvm._tool_registry_lock:
            all_entries = list(rvm.tool_registry.values())
        if filter_map is None:
            return [_entry_for_nodus(e) for e in all_entries]
        f = _as_dict(filter_map)
        if f is None:
            return [_entry_for_nodus(e) for e in all_entries]
        results = []
        for entry in all_entries:
            if "namespace" in f:
                ns = str(f["namespace"])
                if not entry["name"].startswith(ns + "."):
                    continue
            if "tag" in f:
                tag = f["tag"]
                if tag not in entry.get("tags", []):
                    continue
            if "deprecated" in f:
                want = bool(f["deprecated"])
                if bool(entry.get("deprecated", False)) != want:
                    continue
            results.append(_entry_for_nodus(entry))
        return results

    def builtin_tool_has(name):
        rvm = _root_vm(vm)
        if not isinstance(name, str):
            return False
        with rvm._tool_registry_lock:
            return name in rvm.tool_registry

    registry.add("tool_register", 1, builtin_tool_register)
    registry.add("tool_unregister", 1, builtin_tool_unregister)
    registry.add("tool_invoke", (1, 2), builtin_tool_invoke)
    registry.add("tool_lookup", 1, builtin_tool_lookup)
    registry.add("tool_list", (0, 1), builtin_tool_list)
    registry.add("tool_has", 1, builtin_tool_has)
