"""Collection, string, and JSON builtin functions for the Nodus VM."""

import json

from nodus.vm.runtime_values import is_json_safe


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
            from nodus.vm.vm import Record
            return Record({key: from_json_value(item) for key, item in value.items()})
        vm.runtime_error("runtime", f"Unsupported JSON value: {value!r}")

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
        vm.runtime_error("type", f"json.stringify cannot encode value of type {vm.builtin_type(value)}")

    def builtin_json_parse(text):
        vm.ensure_string(text, "json_parse(text)")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as err:
            vm.runtime_error("runtime", f"json_parse failed: {err.msg}")
        return from_json_value(parsed)

    def builtin_json_stringify(value):
        try:
            return json.dumps(to_json_value(value), ensure_ascii=False)
        except Exception as err:
            from nodus.runtime.diagnostics import LangRuntimeError
            if isinstance(err, LangRuntimeError):
                raise
            vm.runtime_error("runtime", f"json_stringify failed: {err}")

    registry.add("str", 1, lambda x: vm.value_to_string(x, quote_strings=False))
    registry.add("len", 1, builtin_len)
    registry.add("collection_len", 1, builtin_len)
    registry.add("str_upper", 1, builtin_upper)
    registry.add("str_lower", 1, builtin_lower)
    registry.add("str_trim", 1, builtin_trim)
    registry.add("str_split", 2, builtin_split)
    registry.add("str_contains", 2, builtin_contains)
    registry.add("keys", 1, builtin_keys)
    registry.add("values", 1, builtin_values)
    registry.add("list_push", 2, builtin_list_push)
    registry.add("list_pop", 1, builtin_list_pop)
    registry.add("json_parse", 1, builtin_json_parse)
    registry.add("json_stringify", 1, builtin_json_stringify)
