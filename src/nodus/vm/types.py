"""Value types shared between the Nodus VM and builtin modules.

Isolating these here breaks the coupling that previously forced every builtin
module to import the entire vm.py (2700+ lines) just to reference Record or
Closure.  vm.py re-exports all names for backward compatibility.
"""

from __future__ import annotations

import sys
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
        # #339: the context the closure was compiled against, captured when it
        # crossed the boundary. `caller_vm.run_closure` runs a *nested* execute
        # loop, which cannot suspend — a worker that calls `async.sleep` dies
        # with "Task yielded during graph execution". With the origin context in
        # hand, a VM already inside a coroutine can instead push a frame and keep
        # running in the same loop, so the closure can suspend like any other
        # code. See `VM._try_enter_foreign_closure`.
        capture = getattr(caller_vm, "_capture_module_ctx", None)
        self.origin_ctx = capture() if capture is not None else None

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
        if self is other:
            return True
        # #545 staging: identity today, structural in 6.0.0. The one observable
        # divergence -- two distinct records that field-by-field comparison
        # calls equal -- warns once per process, so a program relying on `==`
        # telling equal-valued records apart gets a release cycle of notice.
        # The check must never change the program's outcome, so a structure too
        # deep to inspect is treated as not divergent rather than raised.
        if not _STRUCTURAL_EQ_CHANGE_WARNED:
            try:
                divergent = structural_eq(self, other)
            except RecursionError:
                divergent = False
            if divergent:
                _warn_structural_eq_change()
        return False

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


_STRUCTURAL_EQ_CHANGE_WARNED = False


def structural_eq(a, b, _seen: set | None = None) -> bool:
    """What `a == b` returns in 6.0.0 (#545): records compare by `kind` and
    `fields`, recursing with the same equality lists and maps already use.

    Two semantic carve-outs survive the flip, because they are meanings and
    not implementation conveniences: `datetime` compares by instant
    (`epoch_ms` only -- the zone is presentation), and `duration` by length
    (`total_ms` only -- the other fields are derived). Function-valued fields
    compare the way functions compare everywhere else: by identity, so a
    record whose methods are built per-instance is equal only to itself.

    `_seen` tracks container pairs already on the comparison path, so a cyclic
    structure (`r.self = r`) terminates instead of recursing forever -- a pair
    met again is taken as equal, the standard coinductive reading.

    `docs/design/v6/00-record-equality.md` records the decision; until the
    flip, `Record.__eq__` uses this only to detect a comparison whose answer
    is about to change.
    """
    if a is b:
        return True
    a_container = isinstance(a, (Record, list, dict))
    b_container = isinstance(b, (Record, list, dict))
    if a_container and b_container:
        pair = (id(a), id(b))
        if _seen is None:
            _seen = set()
        elif pair in _seen:
            return True
        _seen.add(pair)
    if isinstance(a, Record) and isinstance(b, Record):
        if a.kind == "datetime" and b.kind == "datetime":
            return a.fields["epoch_ms"] == b.fields["epoch_ms"]
        if a.kind == "duration" and b.kind == "duration":
            return a.fields["total_ms"] == b.fields["total_ms"]
        if a.kind != b.kind or a.fields.keys() != b.fields.keys():
            return False
        return all(structural_eq(a.fields[k], b.fields[k], _seen) for k in a.fields)
    if isinstance(a, Record) or isinstance(b, Record):
        return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(structural_eq(x, y, _seen) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(structural_eq(a[k], b[k], _seen) for k in a)
    return a == b


def _warn_structural_eq_change() -> None:
    global _STRUCTURAL_EQ_CHANGE_WARNED
    if _STRUCTURAL_EQ_CHANGE_WARNED:
        return
    _STRUCTURAL_EQ_CHANGE_WARNED = True
    print(
        "warning: two distinct records with equal fields compared as not "
        "equal. Record `==` is identity comparison today; in 6.0.0 it becomes "
        "structural (field by field, like maps and lists) and this comparison "
        "returns true. If you rely on `==` telling equal-valued records "
        "apart, compare a unique field instead. See #545.",
        file=sys.stderr,
    )


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
    # ASYNC-MOD-001 (#105): for a cross-module call frame, the caller's module
    # context to restore when this frame pops. None for ordinary frames.
    cross_module_ctx: object | None = None
