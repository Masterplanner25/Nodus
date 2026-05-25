"""Collection, string, and JSON builtin functions for the Nodus VM."""

import json

from nodus.runtime.error_wrap import print_trace, translate_json_decode_error



def register(vm, registry) -> None:
    """Register collection, string, and JSON builtins onto the registry."""

    def builtin_len(value):
        if isinstance(value, (str, list, dict)):
            return float(len(value))
        vm.runtime_error("type", "len(x) expects string, list, or map")

    def builtin_upper(value):
        vm.ensure_string(value, "upper(x)")
        return value.upper()

    def builtin_lower(value):
        vm.ensure_string(value, "lower(x)")
        return value.lower()

    def builtin_trim(value):
        vm.ensure_string(value, "trim(x)")
        return value.strip()

    def builtin_split(value, delimiter):
        vm.ensure_string(value, "split(x, delimiter)")
        vm.ensure_string(delimiter, "split(x, delimiter)")
        return value.split(delimiter)

    def builtin_contains(value, needle):
        vm.ensure_string(value, "contains(x, needle)")
        vm.ensure_string(needle, "contains(x, needle)")
        return needle in value

    def builtin_replace(value, old, new):
        vm.ensure_string(value, "str_replace(s, old, new)")
        vm.ensure_string(old, "str_replace(s, old, new)")
        vm.ensure_string(new, "str_replace(s, old, new)")
        return value.replace(old, new)

    def builtin_has_key(value, key):
        if not isinstance(value, dict):
            vm.runtime_error("type", "has_key(map, key) expects a map")
        return key in value

    def builtin_keys(value):
        if not isinstance(value, dict):
            vm.runtime_error("type", "keys(x) expects a map")
        return list(value.keys())

    def builtin_values(value):
        if not isinstance(value, dict):
            vm.runtime_error("type", "values(x) expects a map")
        return list(value.values())

    def builtin_list_push(value, item):
        if not isinstance(value, list):
            vm.runtime_error("type", "list_push(list, value) expects a list")
        value.append(item)
        return value

    def builtin_list_pop(value):
        if not isinstance(value, list):
            vm.runtime_error("type", "list_pop(list) expects a list")
        if not value:
            vm.runtime_error("index", "Cannot pop from an empty list")
        return value.pop()

    def from_json_value(value):
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return [from_json_value(item) for item in value]
        if isinstance(value, dict):
            return {key: from_json_value(item) for key, item in value.items()}
        vm.runtime_error("runtime", f"Unsupported JSON value: {value!r}")

    class _JsonTypeError(Exception):
        def __init__(self, nodus_type: str):
            self.nodus_type = nodus_type

    def to_json_value(value):
        from nodus.vm.vm import Record
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if isinstance(value, float) and value.is_integer():
                return int(value)
            return value
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return [to_json_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): to_json_value(item) for key, item in value.items()}
        if isinstance(value, Record):
            return {key: to_json_value(item) for key, item in value.fields.items()}
        raise _JsonTypeError(vm.builtin_type(value))

    def _json_trace(func_name: str, exc: BaseException) -> None:
        if getattr(vm, "trace_errors", False):
            print_trace(func_name, exc)

    def builtin_json_parse(text):
        if not isinstance(text, str):
            return vm.make_err("type_error", f"json.parse expects a string, got {vm.builtin_type(text)}")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            _json_trace("json.parse", exc)
            return vm.make_err("parse_error", translate_json_decode_error(exc))
        except Exception as exc:
            _json_trace("json.parse", exc)
            return vm.make_err("internal_error", "unexpected internal error in json.parse")
        return from_json_value(parsed)

    def builtin_json_stringify(value):
        try:
            return json.dumps(to_json_value(value), ensure_ascii=False)
        except _JsonTypeError as exc:
            return vm.make_err("type_error", f"cannot serialize to JSON: value of type {exc.nodus_type} is not JSON-compatible")
        except Exception as exc:
            _json_trace("json.stringify", exc)
            return vm.make_err("internal_error", "unexpected internal error in json.stringify")

    def builtin_json_parse_int(s):
        vm.ensure_string(s, "json.parse_int(s)")
        # Scientific notation is explicitly rejected with a specific message.
        if "e" in s.lower():
            return vm.make_err("parse_error", f'not an integer (scientific notation): "{s}"')
        try:
            return int(s)
        except ValueError:
            return vm.make_err("parse_error", f'not a valid integer: "{s}"')

    registry.add("str", 1, lambda x: vm.value_to_string(x, quote_strings=False))
    registry.add("len", 1, builtin_len)
    registry.add("collection_len", 1, builtin_len)
    registry.add("str_upper", 1, builtin_upper)
    registry.add("str_lower", 1, builtin_lower)
    registry.add("str_trim", 1, builtin_trim)
    registry.add("str_split", 2, builtin_split)
    registry.add("str_contains", 2, builtin_contains)
    registry.add("str_replace", 3, builtin_replace)
    registry.add("has_key", 2, builtin_has_key)
    registry.add("map_has_key", 2, builtin_has_key)  # internal alias used by std:collections
    registry.add("keys", 1, builtin_keys)
    registry.add("values", 1, builtin_values)
    registry.add("list_push", 2, builtin_list_push)
    registry.add("list_pop", 1, builtin_list_pop)
    registry.add("json_parse", 1, builtin_json_parse)
    registry.add("json_stringify", 1, builtin_json_stringify)
    registry.add("json_parse_int", 1, builtin_json_parse_int)
