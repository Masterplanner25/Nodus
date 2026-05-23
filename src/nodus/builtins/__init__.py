"""Builtin function registry for the Nodus VM.

Builtin functions are organised into category modules:
  - io.py          — print, input, filesystem, path operations
  - math.py        — numeric/math operations
  - coroutine.py   — coroutine, channel, and scheduler operations
  - collections.py — list, map, string, and JSON operations

To add a new builtin:
1. Implement it in the appropriate category module (or create a new one).
2. Call registry.add(name, arity, fn) in that module's register(vm, registry).
3. Add the name to BUILTIN_NAMES in nodus_builtins.py.
"""

from nodus.builtins.registry import BuiltinRegistry  # noqa: F401
