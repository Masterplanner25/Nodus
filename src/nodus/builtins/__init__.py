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

from nodus.builtins.nodus_builtins import BuiltinInfo


class BuiltinRegistry:
    """Collects builtin function registrations from category modules.

    VM.__init__ instantiates one BuiltinRegistry, calls register_all(vm) which
    delegates to each category module's register(vm, registry) function, then
    merges .entries into self.builtins.
    """

    def __init__(self) -> None:
        self._entries: dict[str, BuiltinInfo] = {}

    def add(self, name: str, arity: int | tuple, fn) -> None:
        """Register a single builtin by name, arity, and callable."""
        self._entries[name] = BuiltinInfo(name, arity, fn)

    @property
    def entries(self) -> dict[str, BuiltinInfo]:
        return self._entries

    def register_all(self, vm) -> None:
        """Register all extracted builtin category groups onto this registry.

        Called by VM.__init__ before execution begins.  Each category module's
        register(vm, registry) is invoked here so all extracted builtins are
        available to the VM.

        Category module imports are deferred (not module-level) to avoid
        circular imports — the category modules reference VM helper types.
        """
        # Populated incrementally as each category module is extracted.
        # Steps 6b-6e will add calls here.
        from nodus.builtins import io as _io
        _io.register(vm, self)
        from nodus.builtins import math as _math_builtins
        _math_builtins.register(vm, self)
        from nodus.builtins import coroutine as _coroutine
        _coroutine.register(vm, self)
        from nodus.builtins import collections as _collections
        _collections.register(vm, self)
