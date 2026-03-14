"""Compatibility wrapper around Python's stdlib `types` plus Nodus types."""

import os as _os

_stdlib_types_path = _os.path.join(_os.path.dirname(_os.__file__), "types.py")
_stdlib_namespace: dict[str, object] = {"__file__": _stdlib_types_path, "__name__": "_stdlib_types"}
with open(_stdlib_types_path, "r", encoding="utf-8") as _f:
    exec(compile(_f.read(), _stdlib_types_path, "exec"), _stdlib_namespace)

for _name, _value in list(_stdlib_namespace.items()):
    if _name in {"__builtins__", "__doc__", "__file__", "__name__", "__package__", "__spec__"}:
        continue
    globals()[_name] = _value

from nodus.frontend.type_system import ANY, BOOL, FLOAT, FUNCTION, INT, LIST, NIL, RECORD, STRING, FunctionType, NodusType

__all__ = list(_stdlib_namespace.get("__all__", [])) + [
    "NodusType",
    "FunctionType",
    "ANY",
    "INT",
    "FLOAT",
    "STRING",
    "BOOL",
    "LIST",
    "RECORD",
    "FUNCTION",
    "NIL",
]
