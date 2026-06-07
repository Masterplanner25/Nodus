"""Value types shared between the Nodus VM and builtin modules.

Isolating these here breaks the coupling that previously forced every builtin
module to import the entire vm.py (2700+ lines) just to reference Record or
Closure.  vm.py re-exports all names for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from nodus.compiler.compiler import FunctionInfo

if TYPE_CHECKING:
    from nodus.vm.vm import VM


class Cell:
    def __init__(self, value=None):
        self.value = value


class Closure:
    def __init__(self, function: FunctionInfo, upvalues: list[Cell]):
        self.function = function
        self.upvalues = upvalues


class _ClosureProxy(Closure):
    """Wraps a Closure so it can be called from a foreign-bytecode VM context.

    When a module function receives a user-defined closure as an argument and
    calls it via CALL_VALUE, the closure's ``fn.addr`` refers to an instruction
    index in the *caller's* bytecode — not the module's.  Wrapping the closure
    in a ``_ClosureProxy`` lets ``_op_call_value`` dispatch the call back
    through ``caller_vm.run_closure`` instead of executing at the wrong
    address in the module VM.

    Inherits from ``Closure`` so that ``isinstance(proxy, Closure)`` checks
    in the VM's reflection builtins behave transparently.
    """

    def __init__(self, closure: Closure, caller_vm: VM):
        super().__init__(closure.function, closure.upvalues)
        self._proxied_closure = closure
        self.caller_vm = caller_vm

    def __call__(self, *args):
        return self.caller_vm.run_closure(self._proxied_closure, list(args))


class Record:
    def __init__(self, fields: dict[str, object], kind: str = "record"):
        self.fields = fields
        self.kind = kind

    def __repr__(self) -> str:
        inner = ", ".join(f"{k}: {v!r}" for k, v in self.fields.items())
        return f"Record({{{inner}}})"

    def __eq__(self, other):
        if not isinstance(other, Record):
            return NotImplemented
        if self.kind == "datetime" and other.kind == "datetime":
            return self.fields["epoch_ms"] == other.fields["epoch_ms"]
        if self.kind == "duration" and other.kind == "duration":
            return self.fields["total_ms"] == other.fields["total_ms"]
        return self is other

    def __hash__(self):
        return id(self)

    def _cmp_key(self, other):
        if self.kind == "datetime" and isinstance(other, Record) and other.kind == "datetime":
            return self.fields["epoch_ms"], other.fields["epoch_ms"]
        if self.kind == "duration" and isinstance(other, Record) and other.kind == "duration":
            return self.fields["total_ms"], other.fields["total_ms"]
        raise TypeError(f"unorderable types: {self.kind} and {getattr(other, 'kind', type(other).__name__)}")

    def __lt__(self, other):
        a, b = self._cmp_key(other)
        return a < b

    def __le__(self, other):
        a, b = self._cmp_key(other)
        return a <= b

    def __gt__(self, other):
        a, b = self._cmp_key(other)
        return a > b

    def __ge__(self, other):
        a, b = self._cmp_key(other)
        return a >= b


class BuiltinMethod:
    """Wraps a Python callable for use as a method field on a Record."""
    def __init__(self, fn):
        self._fn = fn


@dataclass
class Frame:
    return_ip: int | None
    locals: dict
    fn_name: str
    call_line: int | None
    call_col: int | None
    call_path: str | None
    closure: Closure | None = None
    locals_array: list | None = None
    locals_name_to_slot: dict | None = None
