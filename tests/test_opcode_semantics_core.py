"""Per-opcode semantic specification for the remaining 39 opcodes (#412 phase 4).

Phase 2 specified the ten opcodes #412's scope note names — the control-flow and
frame-state ones, where every VM bug of the v5 cycle lived. It said, correctly,
that `ADD` and `POP` are not where the bugs were. This module covers the other
39 anyway, for two reasons the phase-2 work turned up rather than assumed.

**The risk register was only 3/16 covered.** Phase 1's census is the ordering
#412 asks for, and of the sixteen opcodes executing fewer than 100 times across
the whole suite, only `POP_TRY`, `FINALLY_END` and `CALL_VALUE` got a spec.
`JUMP_IF_TRUE`, `NOT`, `STORE_UPVALUE` and `TO_BOOL` execute **twice** each.
"Simple" and "exercised" are different properties, and the census measures the
second one.

**Phase 2 found four places the handler and the reference disagreed, in ten
opcodes.** That rate does not obviously fall off for the simple ones: the ratio
of prose to behaviour is what drives it, and a one-line entry describing a
three-branch handler is the shape that goes wrong. This module found more of
them — recorded in `BYTECODE_REFERENCE.md §3`, and each one is a test below
that went red against what the document said.

Same test shape as phase 2, and for the same reason: **construct a known VM
state, execute exactly one instruction, assert the resulting state.** A program
that exercises an opcode passes as long as the program's output is right, which
is how #370 survived.

Each spec states the four things #412 asks be written down: operands consumed,
net stack effect, side effects on frame/`ip`/namespaces, and error behaviour on
a wrong pre-state.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.compiler.compiler import FunctionInfo  # noqa: E402
from nodus.runtime.diagnostics import LangRuntimeError  # noqa: E402
from nodus.builtins.nodus_builtins import BuiltinInfo  # noqa: E402
from nodus.runtime.module import LiveBinding, NodusModule  # noqa: E402
from nodus.vm import types as vm_types  # noqa: E402
from nodus.vm.types import Cell, Closure, Frame, Record  # noqa: E402
from nodus.vm.vm import VM, Iterator  # noqa: E402


# The opcodes this module specifies. Named once so the coverage test drives off
# the tuple rather than a second hand-kept list, and so `nodus_gate --opcodes`
# can read it without importing a test module.
SPECIFIED = (
    "PUSH_CONST",
    "LOAD",
    "STORE",
    "LOAD_LOCAL_IDX",
    "STORE_LOCAL_IDX",
    "STORE_ARG",
    "LOAD_UPVALUE",
    "STORE_UPVALUE",
    "POP",
    "TO_BOOL",
    "NOT",
    "NEG",
    "ADD",
    "SUB",
    "MUL",
    "DIV",
    "MOD",
    "EQ",
    "NE",
    "LT",
    "GT",
    "LE",
    "GE",
    "JUMP",
    "JUMP_IF_FALSE",
    "JUMP_IF_TRUE",
    "HALT",
    "RETURN",
    "GET_ITER",
    "ITER_NEXT",
    "BUILD_LIST",
    "BUILD_MAP",
    "BUILD_RECORD",
    "BUILD_MODULE",
    "INDEX",
    "INDEX_SET",
    "LOAD_FIELD",
    "STORE_FIELD",
    "CALL",
)


def bare_vm() -> VM:
    """A VM with no program, for single-instruction execution.

    `code=[]` is deliberate — see the phase-2 module. A handler that reads
    `self.code` rather than only the instruction it was handed fails loudly here
    instead of quietly doing something plausible.
    """
    return VM([], {}, code_locs=[], source_path=None)


def frame(**kwargs) -> Frame:
    defaults = dict(
        return_ip=0,
        locals={},
        fn_name="f",
        call_line=None,
        call_col=None,
        call_path=None,
        closure=None,
    )
    defaults.update(kwargs)
    return Frame(**defaults)


def fn_info(name: str = "f", params=(), addr: int = 0, upvalues=()) -> FunctionInfo:
    """A `FunctionInfo` with the fields a hand-built closure needs.

    `display_name` is required by the dataclass and is what error messages
    quote, so it is kept equal to `name` rather than left blank.
    """
    return FunctionInfo(
        name=name,
        params=list(params),
        addr=addr,
        upvalues=list(upvalues),
        display_name=name,
    )


def module_with(**exports) -> NodusModule:
    """A minimal `NodusModule` carrying the given exports.

    `exports` maps a name to a `LiveBinding` in a real module; here the value is
    stored directly, which `get_export` returns unchanged. That is the shape a
    host-injected export has, and it keeps the opcode's branch — module vs
    record — the thing under test.
    """
    return NodusModule(
        name="m",
        path="<test>",
        bytecode=[],
        functions={},
        code_locs=[],
        globals=dict(exports),
        exports=dict(exports),
    )


def builtin(fn, arity: int) -> BuiltinInfo:
    """`VM.builtins` holds `BuiltinInfo`, not bare callables — `call_builtin`
    reads `.arity` off it before dispatching."""
    return BuiltinInfo(name=getattr(fn, "__name__", "b"), arity=arity, fn=fn)


def step(vm: VM, instr: tuple):
    """Execute exactly one instruction through the real dispatch table."""
    op = instr[0]
    handler = vm._dispatch.get(op)
    if handler is None:
        raise AssertionError(f"{op} is not in the dispatch table")
    return handler(instr)


class _SpecCase(unittest.TestCase):

    def assertRuntimeError(self, fragment: str, kind: str | None = None):
        """`self.assertRuntimeError("Cannot add")` as a context manager.

        Asserts on the message *and* optionally the `kind`, because `kind` is the
        part downstream embedders contract on (see CLAUDE.md's denial-contract
        note) while the wording is free to change.
        """
        outer = self

        class _Ctx:
            def __enter__(self):
                self._cm = outer.assertRaises(LangRuntimeError)
                self.raised = self._cm.__enter__()
                return self

            def __exit__(self, *exc):
                ok = self._cm.__exit__(*exc)
                if ok:
                    err = self.raised.exception
                    outer.assertIn(fragment, str(err))
                    if kind is not None:
                        outer.assertEqual(kind, err.kind)
                return ok

        return _Ctx()


class DispatchCoverageTests(_SpecCase):

    def test_every_specified_opcode_is_dispatched(self):
        dispatched = set(bare_vm()._dispatch)
        missing = [op for op in SPECIFIED if op not in dispatched]
        self.assertEqual([], missing, "specified opcodes absent from the dispatch table")

    def test_the_specified_set_has_no_duplicates(self):
        self.assertEqual(len(SPECIFIED), len(set(SPECIFIED)))

    def test_this_module_and_phase_2_together_cover_the_whole_dispatch_table(self):
        """The point of phase 4. If an opcode is added, this fails until it is
        specified — which is the same rule `nodus_gate --opcodes` enforces from
        the outside, asserted here too so the suite alone is sufficient."""
        from tests import test_opcode_semantics as phase2  # noqa: PLC0415
        covered = set(SPECIFIED) | set(phase2.SPECIFIED)
        dispatched = set(bare_vm()._dispatch)
        self.assertEqual(set(), dispatched - covered,
                         "dispatched opcode(s) with no semantic spec")
        self.assertEqual(set(), covered - dispatched,
                         "specified opcode(s) the VM does not dispatch")


# --------------------------------------------------------------------------
# Constants and variable access
# --------------------------------------------------------------------------

# closes: #412
class PushConstTests(_SpecCase):
    """PUSH_CONST — operand: the value. Stack: `→ value`. `ip += 1`."""

    def test_it_pushes_the_operand_itself(self):
        vm = bare_vm()
        step(vm, ("PUSH_CONST", 42))
        self.assertEqual([42], vm.stack)
        self.assertEqual(1, vm.ip)

    def test_the_operand_is_pushed_by_identity_not_copied(self):
        """A list constant shared between two executions would alias. The
        compiler only emits scalars and strings here, and this pins that the
        opcode itself does no defensive copying, so a future non-scalar constant
        is a compiler decision rather than a silent VM one."""
        vm = bare_vm()
        shared = ["a"]
        step(vm, ("PUSH_CONST", shared))
        self.assertIs(shared, vm.stack[0])

    def test_it_does_not_read_the_operand_type(self):
        vm = bare_vm()
        for value in (None, True, "s", 1.5):
            vm.stack = []
            step(vm, ("PUSH_CONST", value))
            self.assertEqual([value], vm.stack)


# closes: #412
class LoadTests(_SpecCase):
    """LOAD — operand: name. Stack: `→ value`. `ip += 1`.

    Resolution order is `locals -> module_globals -> functions -> host_globals`,
    first match wins, and each of the four is asserted below including the order
    between them.
    """

    def test_a_local_shadows_a_global_of_the_same_name(self):
        vm = bare_vm()
        vm.module_globals["x"] = "global"
        vm.frames = [frame(locals={"x": "local"})]
        step(vm, ("LOAD", "x"))
        self.assertEqual(["local"], vm.stack)

    def test_a_module_global_is_found_with_no_frame(self):
        vm = bare_vm()
        vm.module_globals["g"] = 7
        step(vm, ("LOAD", "g"))
        self.assertEqual([7], vm.stack)
        self.assertEqual(1, vm.ip)

    def test_a_function_name_resolves_to_a_zero_upvalue_closure(self):
        """Not to the FunctionInfo. This is what makes `let f = g` work, and
        what `CALL_VALUE` then receives."""
        vm = bare_vm()
        fn = fn_info("g", addr=3)
        vm.functions["g"] = fn
        step(vm, ("LOAD", "g"))
        loaded = vm.stack[0]
        self.assertIsInstance(loaded, Closure)
        self.assertIs(fn, loaded.function)
        self.assertEqual([], loaded.upvalues)

    def test_a_host_global_is_the_last_resort(self):
        vm = bare_vm()
        vm.host_globals["h"] = "host"
        vm.functions["h"] = fn_info("h")
        step(vm, ("LOAD", "h"))
        self.assertIsInstance(vm.stack[0], Closure,
                              "functions must be consulted before host_globals")

    def test_a_cell_is_unwrapped(self):
        vm = bare_vm()
        vm.module_globals["c"] = Cell("inner")
        step(vm, ("LOAD", "c"))
        self.assertEqual(["inner"], vm.stack)

    def test_a_live_binding_is_resolved(self):
        """A re-export: the name in this namespace points at another module's,
        and LOAD must read through to it rather than push the binding."""
        vm = bare_vm()
        vm.module_globals["n"] = LiveBinding(module_with(n=5), "n")
        step(vm, ("LOAD", "n"))
        self.assertEqual([5], vm.stack)

    def test_an_unknown_name_is_a_name_error(self):
        vm = bare_vm()
        with self.assertRuntimeError("Undefined variable: nope", kind="name"):
            step(vm, ("LOAD", "nope"))


# closes: #412
class StoreTests(_SpecCase):
    """STORE — operand: name. Stack: `value →`. `ip += 1`.

    The interesting part is *where* it writes, which is `binding_namespace`
    (#671) rather than "the current frame": a function assigning a module-level
    `let` must update the global, and for a long time it did not.
    """

    def test_it_pops_and_writes_a_new_local_inside_a_frame(self):
        vm = bare_vm()
        vm.frames = [frame()]
        vm.stack = ["v"]
        step(vm, ("STORE", "x"))
        self.assertEqual([], vm.stack)
        self.assertEqual({"x": "v"}, vm.frames[0].locals)
        self.assertEqual(1, vm.ip)

    def test_an_unbound_name_at_module_level_becomes_a_global(self):
        vm = bare_vm()
        vm.stack = ["v"]
        step(vm, ("STORE", "x"))
        self.assertEqual("v", vm.module_globals["x"])

    def test_it_writes_through_to_a_module_global_from_inside_a_frame(self):
        """#671. The frame does not bind `g`, so the write belongs to the
        global that does — not to a fresh local shadowing it."""
        vm = bare_vm()
        vm.module_globals["g"] = 7
        vm.frames = [frame()]
        vm.stack = [99]
        step(vm, ("STORE", "g"))
        self.assertEqual(99, vm.module_globals["g"])
        self.assertNotIn("g", vm.frames[0].locals)

    def test_a_local_of_the_same_name_still_shadows(self):
        vm = bare_vm()
        vm.module_globals["g"] = 7
        vm.frames = [frame(locals={"g": 1})]
        vm.stack = [99]
        step(vm, ("STORE", "g"))
        self.assertEqual(99, vm.frames[0].locals["g"])
        self.assertEqual(7, vm.module_globals["g"], "the global must be untouched")

    def test_an_existing_cell_is_updated_in_place(self):
        """Two closures capturing one variable share the Cell. Replacing it
        would break the sharing rather than write through it."""
        vm = bare_vm()
        cell = Cell("old")
        vm.frames = [frame(locals={"x": cell})]
        vm.stack = ["new"]
        step(vm, ("STORE", "x"))
        self.assertIs(cell, vm.frames[0].locals["x"])
        self.assertEqual("new", cell.value)


# closes: #412
class LoadLocalIdxTests(_SpecCase):
    """LOAD_LOCAL_IDX — operand: slot. Stack: `→ value`. `ip += 1`.

    Reads `frames[-1].locals_array[slot]`, unwrapping `Cell` and `LiveBinding`.
    """

    def test_it_reads_the_slot_of_the_innermost_frame(self):
        vm = bare_vm()
        outer, inner = frame(), frame()
        outer.locals_array = ["outer"]
        inner.locals_array = ["inner"]
        vm.frames = [outer, inner]
        step(vm, ("LOAD_LOCAL_IDX", 0))
        self.assertEqual(["inner"], vm.stack)
        self.assertEqual(1, vm.ip)

    def test_a_cell_is_unwrapped(self):
        vm = bare_vm()
        f = frame()
        f.locals_array = [Cell("boxed")]
        vm.frames = [f]
        step(vm, ("LOAD_LOCAL_IDX", 0))
        self.assertEqual(["boxed"], vm.stack)

    def test_a_live_binding_is_resolved(self):
        vm = bare_vm()
        f = frame()
        f.locals_array = [LiveBinding(module_with(n=3), "n")]
        vm.frames = [f]
        step(vm, ("LOAD_LOCAL_IDX", 0))
        self.assertEqual([3], vm.stack)

    def test_a_slot_past_the_end_raises_rather_than_returning_a_value(self):
        """The bound the runtime *does* catch. Its negative twin is the one it
        does not — a negative operand wraps to the far end and returns another
        variable's value, which is why `tests/test_stack_discipline.py` checks
        for negative operands statically (#412 phase 3)."""
        vm = bare_vm()
        f = frame()
        f.locals_array = [None]
        vm.frames = [f]
        with self.assertRaises(IndexError):
            step(vm, ("LOAD_LOCAL_IDX", 5))


# closes: #412
class StoreLocalIdxTests(_SpecCase):
    """STORE_LOCAL_IDX — operand: slot. Stack: `value →`. `ip += 1`.

    Writes `frames[-1].locals_array[slot]`, updating an existing `Cell` in place.
    It deliberately does **not** write `frame.locals`.
    """

    def test_it_pops_and_writes_the_slot(self):
        vm = bare_vm()
        f = frame()
        f.locals_array = [None, None]
        vm.frames = [f]
        vm.stack = ["v"]
        step(vm, ("STORE_LOCAL_IDX", 1))
        self.assertEqual([], vm.stack)
        self.assertEqual([None, "v"], f.locals_array)
        self.assertEqual(1, vm.ip)

    def test_an_existing_cell_is_updated_in_place(self):
        vm = bare_vm()
        cell = Cell("old")
        f = frame()
        f.locals_array = [cell]
        vm.frames = [f]
        vm.stack = ["new"]
        step(vm, ("STORE_LOCAL_IDX", 0))
        self.assertIs(cell, f.locals_array[0], "the Cell must not be replaced")
        self.assertEqual("new", cell.value)

    def test_it_does_not_write_the_locals_dict(self):
        """Stated in the reference and worth pinning: the dict is written only
        by STORE_ARG and by `capture_local`, so a spec that quietly started
        syncing both would make the two paths disagree about staleness."""
        vm = bare_vm()
        f = frame(locals={})
        f.locals_array = [None]
        vm.frames = [f]
        vm.stack = ["v"]
        step(vm, ("STORE_LOCAL_IDX", 0))
        self.assertEqual({}, f.locals)


# closes: #412
class StoreArgTests(_SpecCase):
    """STORE_ARG — operand: parameter name. Stack: `value →`. `ip += 1`.

    Two side effects, not one: it writes `frame.locals[name]` **and** syncs the
    value into `frame.locals_array` at the parameter's slot, so the parameter is
    readable through both `LOAD` and `LOAD_LOCAL_IDX`.
    """

    def test_it_pops_into_the_frame_locals_dict(self):
        vm = bare_vm()
        vm.frames = [frame()]
        vm.stack = ["arg"]
        step(vm, ("STORE_ARG", "p"))
        self.assertEqual([], vm.stack)
        self.assertEqual({"p": "arg"}, vm.frames[0].locals)
        self.assertEqual(1, vm.ip)

    def test_it_also_syncs_the_slot_array(self):
        vm = bare_vm()
        f = frame()
        f.locals_array = [None, None]
        f.locals_name_to_slot = {"p": 1}
        vm.frames = [f]
        vm.stack = ["arg"]
        step(vm, ("STORE_ARG", "p"))
        self.assertEqual([None, "arg"], f.locals_array,
                         "a parameter must be visible to LOAD_LOCAL_IDX")
        self.assertEqual("arg", f.locals["p"],
                         "and to LOAD, which reads the dict")

    def test_a_parameter_with_no_slot_is_written_to_the_dict_only(self):
        vm = bare_vm()
        f = frame()
        f.locals_array = [None]
        f.locals_name_to_slot = {"other": 0}
        vm.frames = [f]
        vm.stack = ["arg"]
        step(vm, ("STORE_ARG", "p"))
        self.assertEqual([None], f.locals_array)
        self.assertEqual("arg", f.locals["p"])

    def test_an_existing_cell_is_updated_in_place(self):
        vm = bare_vm()
        cell = Cell(None)
        vm.frames = [frame(locals={"p": cell})]
        vm.stack = ["arg"]
        step(vm, ("STORE_ARG", "p"))
        self.assertIs(cell, vm.frames[0].locals["p"])
        self.assertEqual("arg", cell.value)

    def test_it_errors_without_a_call_frame(self):
        vm = bare_vm()
        vm.stack = ["arg"]
        with self.assertRuntimeError("STORE_ARG used without a call frame",
                                     kind="runtime"):
            step(vm, ("STORE_ARG", "p"))


# closes: #412
class LoadUpvalueTests(_SpecCase):
    """LOAD_UPVALUE — operand: index. Stack: `→ value`. `ip += 1`."""

    def test_it_reads_the_cell_behind_the_index(self):
        """Two upvalues, and the *second* is read. With one, index 0 and the
        `-1` an off-by-one produces are the same element, so the spec could not
        tell them apart. Found by mutation, not by reading it back."""
        vm = bare_vm()
        first, second = Cell("first"), Cell("second")
        closure = Closure(fn_info("f"), [first, second])
        vm.frames = [frame(closure=closure)]
        step(vm, ("LOAD_UPVALUE", 1))
        self.assertEqual(["second"], vm.stack)
        self.assertEqual(1, vm.ip)

    def test_index_zero_reads_the_first_upvalue(self):
        vm = bare_vm()
        closure = Closure(fn_info("f"), [Cell("first"), Cell("second")])
        vm.frames = [frame(closure=closure)]
        step(vm, ("LOAD_UPVALUE", 0))
        self.assertEqual(["first"], vm.stack)

    def test_it_errors_without_a_frame(self):
        vm = bare_vm()
        with self.assertRuntimeError("LOAD_UPVALUE used without a call frame",
                                     kind="runtime"):
            step(vm, ("LOAD_UPVALUE", 0))

    def test_it_errors_when_the_frame_has_no_closure(self):
        vm = bare_vm()
        vm.frames = [frame(closure=None)]
        with self.assertRuntimeError("Invalid upvalue access", kind="runtime"):
            step(vm, ("LOAD_UPVALUE", 0))

    def test_it_errors_on_an_index_past_the_end(self):
        vm = bare_vm()
        closure = Closure(fn_info("f"), [Cell(1)])
        vm.frames = [frame(closure=closure)]
        with self.assertRuntimeError("Invalid upvalue access", kind="runtime"):
            step(vm, ("LOAD_UPVALUE", 1))


# closes: #412
class StoreUpvalueTests(_SpecCase):
    """STORE_UPVALUE — operand: index. Stack: `value →`. `ip += 1`.

    Executes **twice** in the whole suite (phase 1's census), which is the
    reason it is here rather than in the "simple enough" pile.
    """

    def test_it_pops_and_writes_the_cell_in_place(self):
        vm = bare_vm()
        cell = Cell("old")
        closure = Closure(fn_info("f"), [cell])
        vm.frames = [frame(closure=closure)]
        vm.stack = ["new"]
        step(vm, ("STORE_UPVALUE", 0))
        self.assertEqual([], vm.stack)
        self.assertIs(cell, closure.upvalues[0], "the Cell must not be replaced")
        self.assertEqual("new", cell.value)
        self.assertEqual(1, vm.ip)

    def test_the_write_is_visible_through_every_closure_sharing_the_cell(self):
        """The whole point of Cell boxing, and the property a replaced Cell
        would silently break."""
        vm = bare_vm()
        cell = Cell("old")
        fn = fn_info("f")
        writer, reader = Closure(fn, [cell]), Closure(fn, [cell])
        vm.frames = [frame(closure=writer)]
        vm.stack = ["new"]
        step(vm, ("STORE_UPVALUE", 0))
        self.assertEqual("new", reader.upvalues[0].value)

    def test_it_errors_without_a_frame(self):
        vm = bare_vm()
        vm.stack = ["new"]
        with self.assertRuntimeError("STORE_UPVALUE used without a call frame",
                                     kind="runtime"):
            step(vm, ("STORE_UPVALUE", 0))

    def test_it_errors_on_an_index_past_the_end(self):
        vm = bare_vm()
        closure = Closure(fn_info("f"), [])
        vm.frames = [frame(closure=closure)]
        vm.stack = ["new"]
        with self.assertRuntimeError("Invalid upvalue access", kind="runtime"):
            step(vm, ("STORE_UPVALUE", 0))


# --------------------------------------------------------------------------
# Stack housekeeping, truthiness and unary operators
# --------------------------------------------------------------------------

# closes: #412
class PopTests(_SpecCase):
    """POP — no operands. Stack: `value →`. `ip += 1`."""

    def test_it_discards_exactly_one_value(self):
        vm = bare_vm()
        vm.stack = ["keep", "drop"]
        step(vm, ("POP",))
        self.assertEqual(["keep"], vm.stack)
        self.assertEqual(1, vm.ip)

    def test_it_underflows_on_an_empty_stack(self):
        """`POP` is the reference's "explicit stack-discipline anchor", so the
        empty case has to be an error rather than a silent no-op — otherwise a
        compiler that emits one POP too many is invisible."""
        vm = bare_vm()
        with self.assertRuntimeError("Stack underflow"):
            step(vm, ("POP",))


# closes: #412
class ToBoolTests(_SpecCase):
    """TO_BOOL — no operands. Stack: `value → bool`. `ip += 1`.

    Truthiness: `nil` is false, a `bool` is itself, everything else is Python
    `bool()` — so `0`, `""`, `[]` and `{}` are false.
    """

    def test_it_normalizes_to_a_real_bool(self):
        vm = bare_vm()
        vm.stack = ["non-empty"]
        step(vm, ("TO_BOOL",))
        self.assertIs(True, vm.stack[0])
        self.assertEqual(1, vm.ip)

    def test_the_truthiness_table(self):
        for value, expected in ((None, False), (True, True), (False, False),
                                (0, False), (1, True), (0.0, False),
                                ("", False), ("x", True), ([], False),
                                ([0], True), ({}, False), ({"k": 1}, True)):
            with self.subTest(value=value):
                vm = bare_vm()
                vm.stack = [value]
                step(vm, ("TO_BOOL",))
                self.assertIs(expected, vm.stack[0])

    def test_a_record_is_truthy_even_when_it_has_no_fields(self):
        """`bool(Record)` has no `__len__` to consult, so an empty record is
        true. Worth pinning because the empty *map* beside it is false."""
        vm = bare_vm()
        vm.stack = [Record({})]
        step(vm, ("TO_BOOL",))
        self.assertIs(True, vm.stack[0])


# closes: #412
class NotTests(_SpecCase):
    """NOT — no operands. Stack: `value → bool`. `ip += 1`."""

    def test_it_negates_truthiness_not_the_value(self):
        vm = bare_vm()
        vm.stack = [0]
        step(vm, ("NOT",))
        self.assertIs(True, vm.stack[0])
        self.assertEqual(1, vm.ip)

    def test_it_always_yields_a_bool(self):
        vm = bare_vm()
        vm.stack = ["s"]
        step(vm, ("NOT",))
        self.assertIs(False, vm.stack[0])

    def test_nil_negates_to_true(self):
        vm = bare_vm()
        vm.stack = [None]
        step(vm, ("NOT",))
        self.assertIs(True, vm.stack[0])


# closes: #412
class NegTests(_SpecCase):
    """NEG — no operands. Stack: `value → -value`. `ip += 1`.

    A non-numeric operand is a **Nodus** type error, not the host `TypeError`:
    the reference said "host-language numeric negation errors will surface",
    and the handler converts them.
    """

    def test_it_negates_an_int_and_a_float(self):
        for value, expected in ((5, -5), (2.5, -2.5), (-3, 3)):
            with self.subTest(value=value):
                vm = bare_vm()
                vm.stack = [value]
                step(vm, ("NEG",))
                self.assertEqual([expected], vm.stack)
                self.assertEqual(1, vm.ip)

    def test_a_string_is_a_nodus_type_error(self):
        vm = bare_vm()
        vm.stack = ["s"]
        with self.assertRuntimeError("Cannot negate", kind="type"):
            step(vm, ("NEG",))

    def test_the_error_names_the_nodus_type(self):
        vm = bare_vm()
        vm.stack = [Record({})]
        with self.assertRuntimeError("Cannot negate", kind="type") as ctx:
            step(vm, ("NEG",))
        self.assertNotIn("TypeError", str(ctx.raised.exception))


# --------------------------------------------------------------------------
# Arithmetic
# --------------------------------------------------------------------------

# closes: #412
class AddSubMulTests(_SpecCase):
    """ADD / SUB / MUL — no operands. Stack: `a b → result`. `ip += 1`.

    Operand order matters and is the mutation that catches a swapped pop:
    `b` is popped first, so `a` is the deeper value.
    """

    def test_operand_order_is_a_then_b(self):
        for op, expected in (("ADD", 8), ("SUB", 12), ("MUL", -20)):
            with self.subTest(op=op):
                vm = bare_vm()
                vm.stack = [10, -2]          # a = 10, b = -2
                step(vm, (op,))
                self.assertEqual([expected], vm.stack)
                self.assertEqual(1, vm.ip)

    def test_add_concatenates_strings(self):
        vm = bare_vm()
        vm.stack = ["ab", "cd"]
        step(vm, ("ADD",))
        self.assertEqual(["abcd"], vm.stack)

    def test_multiplying_a_sequence_by_an_int_repeats_it(self):
        """Inherited from the host and reachable from Nodus source, so it is
        recorded rather than left as an accident."""
        for a, b, expected in (("ab", 3, "ababab"), ([0], 3, [0, 0, 0])):
            with self.subTest(a=a):
                vm = bare_vm()
                vm.stack = [a, b]
                step(vm, ("MUL",))
                self.assertEqual([expected], vm.stack)

    def test_add_concatenates_lists(self):
        vm = bare_vm()
        vm.stack = [[1], [2]]
        step(vm, ("ADD",))
        self.assertEqual([[1, 2]], vm.stack)

    def test_a_mixed_pair_is_a_nodus_type_error_naming_the_operation(self):
        for op, verb, pair in (("ADD", "add", [1, "s"]),
                               ("SUB", "subtract", [1, "s"]),
                               # `1 * "s"` is string *repetition* in Python and
                               # raises nothing, so the mixed pair that reaches
                               # MUL's error branch is two strings.
                               ("MUL", "multiply", ["s", "t"])):
            with self.subTest(op=op):
                vm = bare_vm()
                vm.stack = list(pair)
                with self.assertRuntimeError(f"Cannot {verb}", kind="type"):
                    step(vm, (op,))

    def test_nil_operands_are_reported_as_a_type_error_not_an_attribute_error(self):
        """`Cannot add nil and int` is the message a program sees when an
        uninitialised value reaches arithmetic — the symptom #671 produced."""
        vm = bare_vm()
        vm.stack = [None, 1]
        with self.assertRuntimeError("Cannot add", kind="type"):
            step(vm, ("ADD",))


# closes: #412
class DivTests(_SpecCase):
    """DIV — no operands. Stack: `a b → a / b`. `ip += 1`.

    **Three branches, not one.** The reference said "host float division
    behavior", which is wrong in every branch: int / int is *floor* division,
    `bool` is excluded from the int path, and both zero cases raise distinct
    Nodus `math` errors rather than a host `ZeroDivisionError`.
    """

    def test_int_over_int_floors(self):
        vm = bare_vm()
        vm.stack = [7, 2]
        step(vm, ("DIV",))
        self.assertEqual([3], vm.stack)
        self.assertIsInstance(vm.stack[0], int)

    def test_int_floor_division_rounds_toward_negative_infinity(self):
        """`-7 // 2` is `-4`, not `-3`. Python's rule, and it is now stated."""
        vm = bare_vm()
        vm.stack = [-7, 2]
        step(vm, ("DIV",))
        self.assertEqual([-4], vm.stack)

    def test_a_float_operand_makes_it_true_division(self):
        vm = bare_vm()
        vm.stack = [7, 2.0]
        step(vm, ("DIV",))
        self.assertEqual([3.5], vm.stack)

    def test_a_bool_is_not_an_int_here(self):
        """`isinstance(True, int)` is true in Python and false in this handler.
        `4 / true` is float division, giving 4.0 rather than 4."""
        vm = bare_vm()
        vm.stack = [4, True]
        step(vm, ("DIV",))
        self.assertEqual([4.0], vm.stack)
        self.assertIsInstance(vm.stack[0], float)

    def test_integer_division_by_zero_is_its_own_error(self):
        vm = bare_vm()
        vm.stack = [1, 0]
        with self.assertRuntimeError("Integer division by zero", kind="math"):
            step(vm, ("DIV",))

    def test_float_division_by_zero_is_a_different_error(self):
        vm = bare_vm()
        vm.stack = [1.0, 0.0]
        with self.assertRuntimeError("Float division by zero", kind="math"):
            step(vm, ("DIV",))

    def test_a_non_numeric_operand_is_a_type_error(self):
        vm = bare_vm()
        vm.stack = ["s", 2]
        with self.assertRuntimeError("Cannot divide", kind="type"):
            step(vm, ("DIV",))


# closes: #412
class ModTests(_SpecCase):
    """MOD — no operands. Stack: `a b → a % b`. `ip += 1`.

    Same three-branch shape as `DIV`, including the two distinct zero errors.
    """

    def test_int_modulo(self):
        vm = bare_vm()
        vm.stack = [7, 3]
        step(vm, ("MOD",))
        self.assertEqual([1], vm.stack)

    def test_a_negative_left_operand_takes_the_sign_of_the_right(self):
        """`-7 % 3` is `2` here, not `-1` as in C. A reader coming from another
        language will assume the other answer, so it is pinned."""
        vm = bare_vm()
        vm.stack = [-7, 3]
        step(vm, ("MOD",))
        self.assertEqual([2], vm.stack)

    def test_a_float_operand_makes_it_float_modulo(self):
        vm = bare_vm()
        vm.stack = [7.5, 2]
        step(vm, ("MOD",))
        self.assertEqual([1.5], vm.stack)

    def test_integer_modulo_by_zero_is_its_own_error(self):
        vm = bare_vm()
        vm.stack = [1, 0]
        with self.assertRuntimeError("Integer modulo by zero", kind="math"):
            step(vm, ("MOD",))

    def test_float_modulo_by_zero_is_a_different_error(self):
        vm = bare_vm()
        vm.stack = [1.0, 0.0]
        with self.assertRuntimeError("Float modulo by zero", kind="math"):
            step(vm, ("MOD",))

    def test_a_non_numeric_operand_is_a_type_error(self):
        vm = bare_vm()
        vm.stack = [Record({}), 2]
        with self.assertRuntimeError("Cannot modulo", kind="type"):
            step(vm, ("MOD",))


# --------------------------------------------------------------------------
# Comparisons
# --------------------------------------------------------------------------

# closes: #412
class EqNeTests(_SpecCase):
    """EQ / NE — no operands. Stack: `a b → bool`. `ip += 1`.

    **Not Python equality**, which is what the reference claimed. `_nodus_eq`
    coerces int and float to each other and refuses to coerce `bool` to either,
    so `1 == 1.0` is true and `1 == true` is false — the opposite of Python in
    the second case.
    """

    def setUp(self):
        # `Record.__eq__` warns once per process when it finds two records that
        # structural comparison would call equal (#545 staging). Reset the flag
        # so this module neither depends on nor consumes another test's warning.
        self._warned = vm_types._STRUCTURAL_EQ_CHANGE_WARNED
        vm_types._STRUCTURAL_EQ_CHANGE_WARNED = True

    def tearDown(self):
        vm_types._STRUCTURAL_EQ_CHANGE_WARNED = self._warned

    def _eq(self, a, b) -> bool:
        vm = bare_vm()
        vm.stack = [a, b]
        step(vm, ("EQ",))
        self.assertEqual(1, vm.ip)
        return vm.stack[0]

    def test_int_and_float_are_coerced(self):
        self.assertIs(True, self._eq(1, 1.0))

    def test_a_bool_is_not_equal_to_the_int_it_would_be_in_python(self):
        self.assertIs(False, self._eq(True, 1))
        self.assertIs(False, self._eq(False, 0))

    def test_two_bools_compare_normally(self):
        self.assertIs(True, self._eq(True, True))
        self.assertIs(False, self._eq(True, False))

    def test_strings_and_nil_compare_by_value(self):
        self.assertIs(True, self._eq("a", "a"))
        self.assertIs(True, self._eq(None, None))
        self.assertIs(False, self._eq("1", 1))

    def test_lists_and_maps_compare_structurally(self):
        self.assertIs(True, self._eq([1, 2], [1, 2]))
        self.assertIs(True, self._eq({"k": 1}, {"k": 1}))

    def test_two_distinct_records_with_equal_fields_are_not_equal(self):
        """#545, staged to change at 6.0.0. Recorded here as the behaviour the
        opcode has *today*, so the flip is a deliberate edit to this line."""
        self.assertIs(False, self._eq(Record({"x": 1}), Record({"x": 1})))

    def test_the_same_record_is_equal_to_itself(self):
        r = Record({"x": 1})
        self.assertIs(True, self._eq(r, r))

    def test_ne_is_the_negation_of_eq(self):
        for a, b in ((1, 1.0), (True, 1), ("a", "a"), (None, 1),
                     (Record({"x": 1}), Record({"x": 1}))):
            with self.subTest(a=a, b=b):
                vm = bare_vm()
                vm.stack = [a, b]
                step(vm, ("NE",))
                self.assertIs(not self._eq(a, b), vm.stack[0])


# closes: #412
class OrderingComparisonTests(_SpecCase):
    """LT / GT / LE / GE — no operands. Stack: `a b → bool`. `ip += 1`.

    Operand order is `a <op> b` with `b` popped first. A mismatched pair is a
    Nodus `type` error, not the host `TypeError` the reference pointed at.
    """

    def test_operand_order(self):
        for op, expected in (("LT", True), ("GT", False),
                             ("LE", True), ("GE", False)):
            with self.subTest(op=op):
                vm = bare_vm()
                vm.stack = [1, 2]            # a = 1, b = 2
                step(vm, (op,))
                self.assertIs(expected, vm.stack[0])
                self.assertEqual(1, vm.ip)

    def test_the_boundary_between_strict_and_non_strict(self):
        for op, expected in (("LT", False), ("LE", True),
                             ("GT", False), ("GE", True)):
            with self.subTest(op=op):
                vm = bare_vm()
                vm.stack = [2, 2]
                step(vm, (op,))
                self.assertIs(expected, vm.stack[0])

    def test_strings_compare_lexicographically(self):
        vm = bare_vm()
        vm.stack = ["apple", "banana"]
        step(vm, ("LT",))
        self.assertIs(True, vm.stack[0])

    def test_an_incomparable_pair_is_a_nodus_type_error(self):
        for op in ("LT", "GT", "LE", "GE"):
            with self.subTest(op=op):
                vm = bare_vm()
                vm.stack = [1, "s"]
                with self.assertRuntimeError("Cannot compare", kind="type"):
                    step(vm, (op,))

    def test_int_and_float_are_comparable(self):
        vm = bare_vm()
        vm.stack = [1, 1.5]
        step(vm, ("LT",))
        self.assertIs(True, vm.stack[0])


# --------------------------------------------------------------------------
# Branching and control transfer
# --------------------------------------------------------------------------

# closes: #412
class JumpTests(_SpecCase):
    """JUMP — operand: absolute target. No stack change.

    `ip` is *set*, not advanced: a handler that also incremented would land one
    past every target.
    """

    def test_it_sets_ip_to_the_target_absolutely(self):
        vm = bare_vm()
        vm.ip = 100
        step(vm, ("JUMP", 3))
        self.assertEqual(3, vm.ip)

    def test_it_does_not_touch_the_stack(self):
        vm = bare_vm()
        vm.stack = ["a", "b"]
        step(vm, ("JUMP", 0))
        self.assertEqual(["a", "b"], vm.stack)

    def test_a_backward_target_is_ordinary(self):
        """Loop back-edges. Nothing distinguishes them at the opcode level."""
        vm = bare_vm()
        vm.ip = 50
        step(vm, ("JUMP", 10))
        self.assertEqual(10, vm.ip)


# closes: #412
class ConditionalJumpTests(_SpecCase):
    """JUMP_IF_FALSE / JUMP_IF_TRUE — operand: target. Stack: `cond →`.

    Both pop unconditionally, whether or not they jump; a handler that popped
    only on the taken branch would leave the stack unbalanced on the other.
    `JUMP_IF_TRUE` executes **twice** in the whole suite (phase 1's census).
    """

    def test_jump_if_false_jumps_on_a_falsey_condition(self):
        vm = bare_vm()
        vm.ip = 5
        vm.stack = [0]
        step(vm, ("JUMP_IF_FALSE", 42))
        self.assertEqual(42, vm.ip)
        self.assertEqual([], vm.stack)

    def test_jump_if_false_advances_by_one_on_a_truthy_condition(self):
        vm = bare_vm()
        vm.ip = 5
        vm.stack = ["yes"]
        step(vm, ("JUMP_IF_FALSE", 42))
        self.assertEqual(6, vm.ip)
        self.assertEqual([], vm.stack)

    def test_jump_if_true_is_the_mirror(self):
        vm = bare_vm()
        vm.ip = 5
        vm.stack = ["yes"]
        step(vm, ("JUMP_IF_TRUE", 42))
        self.assertEqual(42, vm.ip)
        self.assertEqual([], vm.stack)

        vm = bare_vm()
        vm.ip = 5
        vm.stack = [None]
        step(vm, ("JUMP_IF_TRUE", 42))
        self.assertEqual(6, vm.ip)
        self.assertEqual([], vm.stack)

    def test_both_use_vm_truthiness_rather_than_python_bool(self):
        """An empty record is truthy here and falsey to `bool()` on a container
        — the divergence that makes "uses VM truthiness" load-bearing."""
        vm = bare_vm()
        vm.stack = [Record({})]
        step(vm, ("JUMP_IF_FALSE", 42))
        self.assertEqual(1, vm.ip, "an empty record must be truthy")

    def test_they_underflow_on_an_empty_stack(self):
        for op in ("JUMP_IF_FALSE", "JUMP_IF_TRUE"):
            with self.subTest(op=op):
                vm = bare_vm()
                with self.assertRuntimeError("Stack underflow"):
                    step(vm, (op, 1))


# closes: #412
class HaltTests(_SpecCase):
    """HALT — no operands. No stack change. Returns `("halt", None)`.

    It does **not** advance `ip`, which is how `execute()` can distinguish a
    halted program from one that ran off the end.
    """

    def test_it_returns_the_halt_status(self):
        vm = bare_vm()
        self.assertEqual(("halt", None), step(vm, ("HALT",)))

    def test_it_does_not_advance_ip(self):
        vm = bare_vm()
        vm.ip = 9
        step(vm, ("HALT",))
        self.assertEqual(9, vm.ip)

    def test_it_leaves_the_stack_and_frames_alone(self):
        vm = bare_vm()
        vm.stack = ["v"]
        vm.frames = [frame()]
        step(vm, ("HALT",))
        self.assertEqual(["v"], vm.stack)
        self.assertEqual(1, len(vm.frames))


# closes: #412
class ReturnTests(_SpecCase):
    """RETURN — no operands. Stack: `value →` in the caller's frame.

    **Three exits, and the reference documented one.** In order of precedence:

    1. a `finally` is pending in *this* frame — the return value is deferred and
       `ip` goes to the finally block, with no frame popped;
    2. the frame is a coroutine's outermost (`return_ip is None`) — the
       coroutine is marked finished and `("return", value)` is returned, with
       nothing pushed;
    3. ordinary — pop the frame, push the value, `ip = frame.return_ip`.
    """

    def test_the_ordinary_exit_pops_the_frame_and_pushes_the_value(self):
        vm = bare_vm()
        vm.frames = [frame(return_ip=17)]
        vm.stack = ["ret"]
        self.assertIsNone(step(vm, ("RETURN",)))
        self.assertEqual([], vm.frames)
        self.assertEqual(["ret"], vm.stack)
        self.assertEqual(17, vm.ip)

    def test_a_pending_finally_defers_the_return_instead_of_popping(self):
        """#361's territory. The frame stays, so the finally body runs in it."""
        vm = bare_vm()
        vm.frames = [frame(return_ip=17)]
        vm.handler_stack = [(0, 80, 0, 1)]        # finally_ip=80, frame_depth=1
        vm.stack = ["ret"]
        step(vm, ("RETURN",))
        self.assertEqual(1, len(vm.frames), "the frame must not be popped yet")
        self.assertEqual(80, vm.ip)
        self.assertEqual("ret", vm._deferred_return)
        self.assertEqual([], vm.handler_stack)

    def test_a_handler_without_a_finally_does_not_defer(self):
        """`finally_ip == 0` means try/catch with no finally."""
        vm = bare_vm()
        vm.frames = [frame(return_ip=17)]
        vm.handler_stack = [(5, 0, 0, 1)]
        vm.stack = ["ret"]
        step(vm, ("RETURN",))
        self.assertEqual([], vm.frames)
        self.assertEqual(17, vm.ip)

    def test_a_handler_belonging_to_an_outer_frame_does_not_defer(self):
        """The recorded frame depth must match this frame, or a return would be
        captured by an enclosing function's finally."""
        vm = bare_vm()
        vm.frames = [frame(), frame(return_ip=17)]
        vm.handler_stack = [(0, 80, 0, 1)]        # depth 1, we are at depth 2
        vm.stack = ["ret"]
        step(vm, ("RETURN",))
        self.assertEqual(1, len(vm.frames))
        self.assertEqual(17, vm.ip)

    def test_the_outermost_coroutine_frame_finishes_the_coroutine(self):
        from nodus.runtime.coroutine import Coroutine  # noqa: PLC0415
        vm = bare_vm()
        closure = Closure(fn_info("f"), [])
        coro = Coroutine(closure)
        coro.state = "running"
        vm.current_coroutine = coro
        vm.frames = [frame(return_ip=None)]
        vm.stack = ["ret"]

        self.assertEqual(("return", "ret"), step(vm, ("RETURN",)))
        self.assertEqual("finished", coro.state)
        self.assertEqual([], vm.stack, "nothing is pushed on this exit")

    def test_it_restores_a_cross_module_context_on_the_way_out(self):
        """The mechanism #691's fix installs on the way in. A frame that swapped
        the chunk must swap it back, or the caller resumes in the callee's."""
        vm = bare_vm()
        saved = vm._capture_module_ctx()
        f = frame(return_ip=3)
        f.cross_module_ctx = saved
        vm.frames = [f]
        vm.code = ["someone", "else's", "chunk"]
        vm.stack = ["ret"]
        step(vm, ("RETURN",))
        self.assertEqual([], vm.code, "the caller's chunk must be restored")

    def test_it_drops_handlers_belonging_to_the_popped_frame(self):
        vm = bare_vm()
        vm.frames = [frame(), frame(return_ip=3)]
        vm.handler_stack = [(0, 0, 0, 1), (0, 0, 0, 2)]
        vm.stack = ["ret"]
        step(vm, ("RETURN",))
        self.assertEqual([(0, 0, 0, 1)], vm.handler_stack)

    def test_it_errors_outside_a_frame(self):
        vm = bare_vm()
        vm.stack = ["ret"]
        with self.assertRuntimeError("RETURN outside function", kind="runtime"):
            step(vm, ("RETURN",))


# --------------------------------------------------------------------------
# Iteration
# --------------------------------------------------------------------------

# closes: #412
class GetIterTests(_SpecCase):
    """GET_ITER — no operands. Stack: `iterable → Iterator`. `ip += 1`."""

    def test_a_list_becomes_an_iterator(self):
        vm = bare_vm()
        vm.stack = [[1, 2]]
        step(vm, ("GET_ITER",))
        self.assertIsInstance(vm.stack[0], Iterator)
        self.assertEqual(1, vm.ip)

    def test_the_iterator_walks_the_list_in_order_then_reports_exhaustion(self):
        vm = bare_vm()
        vm.stack = [["a", "b"]]
        step(vm, ("GET_ITER",))
        it = vm.stack[0]
        self.assertEqual(("a", False), it.advance())
        self.assertEqual(("b", False), it.advance())
        self.assertEqual((None, True), it.advance())

    def test_an_empty_list_is_immediately_exhausted(self):
        vm = bare_vm()
        vm.stack = [[]]
        step(vm, ("GET_ITER",))
        self.assertEqual((None, True), vm.stack[0].advance())

    def test_a_record_with_next_is_its_own_iterator(self):
        """And `nil` from `__next__` is what ends it — the record protocol's
        one difference from a list, where `nil` is an ordinary element."""
        vm = bare_vm()
        produced = iter([10, 20, None])
        rec = Record({"__next__": _FakeClosure(lambda _self: next(produced))})
        _patch_run_closure(vm)
        vm.stack = [rec]

        step(vm, ("GET_ITER",))
        it = vm.stack[0]
        self.assertIsInstance(it, Iterator)
        self.assertEqual((10, False), it.advance())
        self.assertEqual((20, False), it.advance())
        self.assertEqual((None, True), it.advance())

    def test_the_next_closure_receives_the_record_as_its_argument(self):
        vm = bare_vm()
        seen = []
        rec = Record({"__next__": _FakeClosure(lambda s: seen.append(s))})
        _patch_run_closure(vm)
        vm.stack = [rec]
        step(vm, ("GET_ITER",))
        vm.stack[0].advance()
        self.assertEqual([rec], seen, "__next__ is called with the record itself")

    def test_a_record_with_iter_returning_a_list_iterates_that_list(self):
        vm = bare_vm()
        rec = Record({"__iter__": _FakeClosure(lambda _self: ["x", "y"])})
        _patch_run_closure(vm)
        vm.stack = [rec]
        step(vm, ("GET_ITER",))
        it = vm.stack[0]
        self.assertEqual(("x", False), it.advance())
        self.assertEqual(("y", False), it.advance())
        self.assertEqual((None, True), it.advance())

    def test_iter_returning_neither_a_list_nor_a_next_record_is_an_error(self):
        vm = bare_vm()
        rec = Record({"__iter__": _FakeClosure(lambda _self: 42)})
        _patch_run_closure(vm)
        vm.stack = [rec]
        with self.assertRuntimeError(
                "__iter__ must return a list or a record with __next__", kind="type"):
            step(vm, ("GET_ITER",))

    def test_iter_is_preferred_over_next_when_a_record_has_both(self):
        vm = bare_vm()
        rec = Record({
            "__iter__": _FakeClosure(lambda _self: ["from __iter__"]),
            "__next__": _FakeClosure(lambda _self: "from __next__"),
        })
        _patch_run_closure(vm)
        vm.stack = [rec]
        step(vm, ("GET_ITER",))
        self.assertEqual(("from __iter__", False), vm.stack[0].advance())

    def test_a_map_gets_its_own_message_rather_than_the_generic_one(self):
        """A reader's first instinct is `for k in m`, so the error names the
        two builtins that do work rather than saying "not iterable"."""
        vm = bare_vm()
        vm.stack = [{"k": 1}]
        with self.assertRuntimeError("maps are not directly iterable", kind="type"):
            step(vm, ("GET_ITER",))

    def test_a_non_iterable_is_a_type_error(self):
        vm = bare_vm()
        vm.stack = [42]
        with self.assertRuntimeError("Value is not iterable", kind="type"):
            step(vm, ("GET_ITER",))

    def test_a_record_without_iter_or_next_is_not_iterable(self):
        vm = bare_vm()
        vm.stack = [Record({"x": 1})]
        with self.assertRuntimeError("Value is not iterable", kind="type"):
            step(vm, ("GET_ITER",))


class _FakeClosure(Closure):
    """A Closure whose body is a Python callable, for driving `run_closure`.

    `GET_ITER`'s record paths call the `__next__` value through `run_closure`,
    which needs a real chunk. Rather than compile one, this subclass carries the
    Python function and `_patch_run_closure` routes to it — the opcode's own
    branch selection is what is under test here, not `run_closure`.
    """

    def __init__(self, fn):
        super().__init__(fn_info("__next__", params=["self"]), [])
        self.python_fn = fn


def _patch_run_closure(vm: VM) -> None:
    original = vm.run_closure

    def run_closure(closure, args, *a, **k):
        fn = getattr(closure, "python_fn", None)
        if fn is not None:
            return fn(*args)
        return original(closure, args, *a, **k)

    vm.run_closure = run_closure  # type: ignore[method-assign]


# closes: #412
class IterNextTests(_SpecCase):
    """ITER_NEXT — operand: end target. The iterator stays on the stack.

    Stack effect differs by branch, which is why the reference's one-line
    "pushes next value or jumps if finished" is worth expanding: on an item it
    is `iter → iter item` and `ip += 1`; on exhaustion it is `iter →` and
    `ip = end`.
    """

    def _iterator_over(self, values):
        vm = bare_vm()
        vm.stack = [list(values)]
        step(vm, ("GET_ITER",))
        return vm

    def test_it_pushes_the_item_and_leaves_the_iterator_underneath(self):
        vm = self._iterator_over(["a"])
        it = vm.stack[0]
        vm.ip = 4
        step(vm, ("ITER_NEXT", 99))
        self.assertEqual(2, len(vm.stack))
        self.assertIs(it, vm.stack[0], "the iterator must survive for the next round")
        self.assertEqual("a", vm.stack[1])
        self.assertEqual(5, vm.ip)

    def test_exhaustion_pops_the_iterator_and_jumps_to_the_end_target(self):
        vm = self._iterator_over([])
        vm.ip = 4
        step(vm, ("ITER_NEXT", 99))
        self.assertEqual([], vm.stack, "the iterator must be cleaned up")
        self.assertEqual(99, vm.ip)

    def test_a_nil_item_is_a_value_not_exhaustion_for_a_list(self):
        """Only the record protocol reads `nil` as "done"; a list containing
        `nil` yields it."""
        vm = self._iterator_over([None])
        step(vm, ("ITER_NEXT", 99))
        self.assertEqual(2, len(vm.stack))
        self.assertIsNone(vm.stack[1])

    def test_an_empty_stack_is_an_error(self):
        vm = bare_vm()
        with self.assertRuntimeError("ITER_NEXT without iterator", kind="runtime"):
            step(vm, ("ITER_NEXT", 99))

    def test_a_non_iterator_on_top_is_a_type_error(self):
        """The message #691 surfaced through the iterator protocol when a
        foreign closure's `__next__` produced something that was not an
        Iterator."""
        vm = bare_vm()
        vm.stack = ["not an iterator"]
        with self.assertRuntimeError("Iterator is not supported", kind="type"):
            step(vm, ("ITER_NEXT", 99))


# --------------------------------------------------------------------------
# Collections and records
# --------------------------------------------------------------------------

# closes: #412
class BuildListTests(_SpecCase):
    """BUILD_LIST — operand: count. Stack: `v1..vn → [v1..vn]`. `ip += 1`."""

    def test_items_come_off_in_reverse_and_are_restored_to_source_order(self):
        vm = bare_vm()
        vm.stack = ["a", "b", "c"]
        step(vm, ("BUILD_LIST", 3))
        self.assertEqual([["a", "b", "c"]], vm.stack)
        self.assertEqual(1, vm.ip)

    def test_it_consumes_only_count_items(self):
        vm = bare_vm()
        vm.stack = ["keep", "a", "b"]
        step(vm, ("BUILD_LIST", 2))
        self.assertEqual(["keep", ["a", "b"]], vm.stack)

    def test_a_zero_count_builds_an_empty_list(self):
        vm = bare_vm()
        step(vm, ("BUILD_LIST", 0))
        self.assertEqual([[]], vm.stack)

    def test_too_few_items_underflows(self):
        vm = bare_vm()
        vm.stack = ["a"]
        with self.assertRuntimeError("Stack underflow"):
            step(vm, ("BUILD_LIST", 2))


# closes: #412
class BuildMapTests(_SpecCase):
    """BUILD_MAP — operand: pair count. Stack: `k1 v1 .. kn vn → {..}`.

    Keys are validated: strings and numbers only, and **`bool` is refused**
    despite being an `int` in Python.
    """

    def test_pairs_are_popped_value_first_and_restored_to_source_order(self):
        vm = bare_vm()
        vm.stack = ["a", 1, "b", 2]
        step(vm, ("BUILD_MAP", 2))
        self.assertEqual([{"a": 1, "b": 2}], vm.stack)
        self.assertEqual(1, vm.ip)

    def test_a_later_duplicate_key_wins(self):
        """Source order matters for this to be well-defined, which is what the
        reverse pass buys."""
        vm = bare_vm()
        vm.stack = ["k", "first", "k", "second"]
        step(vm, ("BUILD_MAP", 2))
        self.assertEqual([{"k": "second"}], vm.stack)

    def test_numeric_keys_are_allowed(self):
        vm = bare_vm()
        vm.stack = [1, "one", 2.5, "two-five"]
        step(vm, ("BUILD_MAP", 2))
        self.assertEqual([{1: "one", 2.5: "two-five"}], vm.stack)

    def test_a_bool_key_is_refused(self):
        vm = bare_vm()
        vm.stack = [True, "v"]
        with self.assertRuntimeError("Map keys must be strings or numbers",
                                     kind="type"):
            step(vm, ("BUILD_MAP", 1))

    def test_a_nil_key_is_refused(self):
        vm = bare_vm()
        vm.stack = [None, "v"]
        with self.assertRuntimeError("Map keys must be strings or numbers",
                                     kind="type"):
            step(vm, ("BUILD_MAP", 1))

    def test_a_zero_count_builds_an_empty_map(self):
        vm = bare_vm()
        step(vm, ("BUILD_MAP", 0))
        self.assertEqual([{}], vm.stack)


# closes: #412
class BuildRecordTests(_SpecCase):
    """BUILD_RECORD — operand: field count. Stack: `k1 v1 .. → Record`."""

    def test_it_builds_a_record_with_kind_record(self):
        vm = bare_vm()
        vm.stack = ["x", 1]
        step(vm, ("BUILD_RECORD", 1))
        built = vm.stack[0]
        self.assertIsInstance(built, Record)
        self.assertEqual({"x": 1}, built.fields)
        self.assertEqual("record", built.kind)
        self.assertEqual(1, vm.ip)

    def test_keys_must_be_strings(self):
        """Stricter than BUILD_MAP, which also takes numbers."""
        vm = bare_vm()
        vm.stack = [1, "v"]
        with self.assertRuntimeError("Record keys must be strings", kind="type"):
            step(vm, ("BUILD_RECORD", 1))

    def test_field_order_follows_source(self):
        vm = bare_vm()
        vm.stack = ["a", 1, "b", 2]
        step(vm, ("BUILD_RECORD", 2))
        self.assertEqual(["a", "b"], list(vm.stack[0].fields))


# closes: #412
class BuildModuleTests(_SpecCase):
    """BUILD_MODULE — operand: field count. Stack: `k1 v1 .. → Record(module)`.

    The one opcode of the frozen 49 that nothing executes and nothing emits
    (#412 phase 1, measured across 895,076 executions). It is specified anyway:
    it is still dispatched, so it is still reachable by hand-built bytecode, and
    "never executed" is a fact about today's compiler rather than about the VM.
    """

    def test_it_builds_a_record_whose_kind_is_module(self):
        vm = bare_vm()
        vm.stack = ["export", 1]
        step(vm, ("BUILD_MODULE", 1))
        built = vm.stack[0]
        self.assertIsInstance(built, Record)
        self.assertEqual("module", built.kind)
        self.assertEqual({"export": 1}, built.fields)
        self.assertEqual(1, vm.ip)

    def test_the_kind_is_the_only_difference_from_build_record(self):
        vm_a, vm_b = bare_vm(), bare_vm()
        vm_a.stack = ["k", "v"]
        vm_b.stack = ["k", "v"]
        step(vm_a, ("BUILD_RECORD", 1))
        step(vm_b, ("BUILD_MODULE", 1))
        self.assertEqual(vm_a.stack[0].fields, vm_b.stack[0].fields)
        self.assertNotEqual(vm_a.stack[0].kind, vm_b.stack[0].kind)

    def test_keys_must_be_strings(self):
        vm = bare_vm()
        vm.stack = [1, "v"]
        with self.assertRuntimeError("Module keys must be strings", kind="type"):
            step(vm, ("BUILD_MODULE", 1))


# closes: #412
class IndexTests(_SpecCase):
    """INDEX — no operands. Stack: `seq idx → value`. `ip += 1`.

    `idx` is popped first, so `seq` is the deeper value.
    """

    def test_a_list_is_indexed_by_position(self):
        vm = bare_vm()
        vm.stack = [["a", "b"], 1]
        step(vm, ("INDEX",))
        self.assertEqual(["b"], vm.stack)
        self.assertEqual(1, vm.ip)

    def test_a_map_is_indexed_by_key(self):
        vm = bare_vm()
        vm.stack = [{"k": "v"}, "k"]
        step(vm, ("INDEX",))
        self.assertEqual(["v"], vm.stack)

    def test_a_string_is_indexed_by_position(self):
        vm = bare_vm()
        vm.stack = ["abc", 1]
        step(vm, ("INDEX",))
        self.assertEqual(["b"], vm.stack)

    def test_a_list_index_out_of_range_is_an_error(self):
        vm = bare_vm()
        vm.stack = [["a"], 5]
        with self.assertRaises(LangRuntimeError):
            step(vm, ("INDEX",))

    def test_a_missing_map_key_is_an_error(self):
        vm = bare_vm()
        vm.stack = [{"k": 1}, "absent"]
        with self.assertRaises(LangRuntimeError):
            step(vm, ("INDEX",))

    def test_a_record_is_not_indexable(self):
        """Records take `.field`, maps take `[key]`. The split is the single
        most common source of confusion in Nodus code, so it is pinned."""
        vm = bare_vm()
        vm.stack = [Record({"k": 1}), "k"]
        with self.assertRaises(LangRuntimeError):
            step(vm, ("INDEX",))


# closes: #412
class IndexSetTests(_SpecCase):
    """INDEX_SET — no operands. Stack: `seq idx value → value`. `ip += 1`.

    Net effect is **-2, not -3**: the assigned value is pushed back, which is
    what makes `xs[i] = v` usable as an expression.
    """

    def test_it_writes_and_pushes_the_assigned_value_back(self):
        vm = bare_vm()
        target = ["a", "b"]
        vm.stack = [target, 1, "new"]
        step(vm, ("INDEX_SET",))
        self.assertEqual(["a", "new"], target)
        self.assertEqual(["new"], vm.stack, "the assigned value is pushed back")
        self.assertEqual(1, vm.ip)

    def test_a_map_key_may_be_created(self):
        vm = bare_vm()
        target = {}
        vm.stack = [target, "k", 1]
        step(vm, ("INDEX_SET",))
        self.assertEqual({"k": 1}, target)

    def test_a_list_index_out_of_range_is_an_error(self):
        vm = bare_vm()
        vm.stack = [["a"], 5, "v"]
        with self.assertRaises(LangRuntimeError):
            step(vm, ("INDEX_SET",))

    def test_the_container_is_mutated_in_place_rather_than_replaced(self):
        """The value on the stack is the assigned element, so nothing else can
        observe the container unless it is the same object."""
        vm = bare_vm()
        target = {"k": "old"}
        vm.stack = [target, "k", "new"]
        step(vm, ("INDEX_SET",))
        self.assertEqual("new", target["k"])


# closes: #412
class LoadFieldTests(_SpecCase):
    """LOAD_FIELD — operand: field name. Stack: `obj → value`. `ip += 1`.

    **A record is not the only valid receiver.** A `NodusModule` is too, and it
    resolves through the export table rather than `fields` — the same gap phase
    2 found in `CALL_METHOD`'s entry, in the sibling opcode.
    """

    def test_it_reads_a_record_field(self):
        vm = bare_vm()
        vm.stack = [Record({"x": 1})]
        step(vm, ("LOAD_FIELD", "x"))
        self.assertEqual([1], vm.stack)
        self.assertEqual(1, vm.ip)

    def test_a_missing_record_field_is_a_key_error(self):
        vm = bare_vm()
        vm.stack = [Record({"x": 1})]
        with self.assertRuntimeError("Missing record field: y", kind="key"):
            step(vm, ("LOAD_FIELD", "y"))

    def test_a_non_record_is_a_type_error(self):
        vm = bare_vm()
        vm.stack = [{"x": 1}]
        with self.assertRuntimeError("Field access is only supported on records",
                                     kind="type"):
            step(vm, ("LOAD_FIELD", "x"))

    def test_a_module_receiver_resolves_through_its_exports(self):
        vm = bare_vm()
        vm.stack = [module_with(exported=5)]
        step(vm, ("LOAD_FIELD", "exported"))
        self.assertEqual([5], vm.stack)

    def test_a_missing_module_export_names_the_export_not_the_field(self):
        vm = bare_vm()
        vm.stack = [module_with(exported=5)]
        with self.assertRuntimeError("Missing module export: absent", kind="key"):
            step(vm, ("LOAD_FIELD", "absent"))


# closes: #412
class StoreFieldTests(_SpecCase):
    """STORE_FIELD — operand: field name. Stack: `obj value → value`.

    Two corrections to what the reference said. It is not `-2`: the assigned
    value is pushed back. And "runtime error if ... field missing" is wrong for
    a record — a missing field is **created**. Only a module receiver requires
    the name to exist already.
    """

    def test_it_writes_and_pushes_the_value_back(self):
        vm = bare_vm()
        rec = Record({"x": 1})
        vm.stack = [rec, 2]
        step(vm, ("STORE_FIELD", "x"))
        self.assertEqual(2, rec.fields["x"])
        self.assertEqual([2], vm.stack, "the assigned value is pushed back")
        self.assertEqual(1, vm.ip)

    def test_a_field_the_record_does_not_have_is_created(self):
        vm = bare_vm()
        rec = Record({})
        vm.stack = [rec, "v"]
        step(vm, ("STORE_FIELD", "new"))
        self.assertEqual({"new": "v"}, rec.fields)

    def test_a_non_record_is_a_type_error(self):
        vm = bare_vm()
        vm.stack = [{"x": 1}, 2]
        with self.assertRuntimeError(
                "Field assignment is only supported on records", kind="type"):
            step(vm, ("STORE_FIELD", "x"))

    def test_a_module_receiver_writes_through_its_exports(self):
        vm = bare_vm()
        mod = module_with(exported=5)
        vm.stack = [mod, 9]
        step(vm, ("STORE_FIELD", "exported"))
        self.assertEqual(9, mod.get_export("exported"))

    def test_a_module_export_that_does_not_exist_is_an_error(self):
        """The asymmetry with records: a module's surface is declared, so a new
        name is a mistake rather than a definition."""
        vm = bare_vm()
        vm.stack = [module_with(exported=5), 9]
        with self.assertRuntimeError("Missing module export: absent", kind="key"):
            step(vm, ("STORE_FIELD", "absent"))





# --------------------------------------------------------------------------
# Calls
# --------------------------------------------------------------------------

# closes: #412
class CallTests(_SpecCase):
    """CALL — operands: function name, arg count.

    Five resolution paths in precedence order, and the reference described two:

    1. the compiler-emitted builtin prefix (#411), checked **first** so a
       program cannot shadow machinery the compiler injected into its own code;
    2. `functions` — pushes a frame and transfers control, pushing nothing;
    3. `builtins` — pops the arguments and pushes the result;
    4. a local or global holding a callable — delegates to `call_closure`, or
       invokes a `ModuleFunction` and pushes its result;
    5. otherwise a `name` error.
    """

    def _fn_vm(self, params=(), addr=9, upvalues=()):
        vm = bare_vm()
        fn = fn_info("g", params=params, addr=addr, upvalues=upvalues)
        vm.functions["g"] = fn
        return vm, fn

    def test_a_user_function_transfers_control_and_pushes_nothing(self):
        vm, fn = self._fn_vm(params=["a"])
        vm.ip = 4
        vm.stack = ["arg"]
        self.assertIsNone(step(vm, ("CALL", "g", 1)))
        self.assertEqual(9, vm.ip)
        self.assertEqual(1, len(vm.frames))
        self.assertEqual(5, vm.frames[0].return_ip, "return_ip is the call site + 1")
        self.assertEqual(["arg"], vm.stack, "arguments stay for STORE_ARG")

    def test_an_arity_mismatch_is_refused_before_the_frame_is_pushed(self):
        vm, _ = self._fn_vm(params=["a", "b"])
        vm.stack = ["only"]
        with self.assertRuntimeError("g expected 2 args, got 1", kind="call"):
            step(vm, ("CALL", "g", 1))
        self.assertEqual([], vm.frames, "no frame may survive a refused call")

    def test_a_function_needing_upvalues_cannot_be_called_by_name(self):
        """`CALL` has no closure to draw upvalues from; the compiler emits
        `MAKE_CLOSURE` + `CALL_VALUE` for those."""
        vm, _ = self._fn_vm(upvalues=[object()])
        with self.assertRuntimeError("requires a closure", kind="call"):
            step(vm, ("CALL", "g", 0))

    def test_the_frame_cap_is_enforced_before_the_frame_is_pushed(self):
        """#394's lesson applied to the cap: a guard that corrupts what it
        refuses is worse than no guard. Checking after the append raises the
        same error and leaves the over-deep frame behind for whatever `catch`
        unwinds through it."""
        vm, _ = self._fn_vm()
        vm.max_frames = 1
        vm.frames = [frame()]
        with self.assertRuntimeError("Call stack overflow", kind="sandbox"):
            step(vm, ("CALL", "g", 0))
        self.assertEqual(1, len(vm.frames),
                         "a refused call must leave the frame stack as it was")

    def test_a_builtin_pops_its_arguments_and_pushes_the_result(self):
        vm = bare_vm()
        vm.builtins["twice"] = builtin(lambda x: x * 2, 1)
        vm.ip = 4
        vm.stack = [21]
        step(vm, ("CALL", "twice", 1))
        self.assertEqual([42], vm.stack)
        self.assertEqual(5, vm.ip)
        self.assertEqual([], vm.frames, "a builtin pushes no frame")

    def test_a_user_function_is_resolved_before_a_builtin_of_the_same_name(self):
        vm, _ = self._fn_vm()
        vm.builtins["g"] = builtin(lambda: "builtin", 0)
        step(vm, ("CALL", "g", 0))
        self.assertEqual(1, len(vm.frames), "the user function must win")

    def test_the_compiler_prefix_is_checked_before_anything_a_program_can_bind(self):
        """#411. A lowering's own call site must not be resolvable through
        normal scoping, or a program can substitute the machinery the compiler
        injected to enforce a guarantee about it."""
        from nodus.vm.vm import BUILTIN_CALL_PREFIX  # noqa: PLC0415
        vm = bare_vm()
        vm.builtins["real"] = builtin(lambda: "builtin", 0)
        vm.functions["real"] = fn_info("real")
        vm.module_globals["real"] = "shadowed"
        step(vm, ("CALL", BUILTIN_CALL_PREFIX + "real", 0))
        self.assertEqual(["builtin"], vm.stack)
        self.assertEqual([], vm.frames)

    def test_a_prefixed_call_to_a_missing_builtin_names_the_builtin(self):
        from nodus.vm.vm import BUILTIN_CALL_PREFIX  # noqa: PLC0415
        vm = bare_vm()
        with self.assertRuntimeError("Undefined function: gone", kind="name") as ctx:
            step(vm, ("CALL", BUILTIN_CALL_PREFIX + "gone", 0))
        self.assertIn("compiler-generated", str(ctx.raised.exception))

    def test_a_global_holding_a_closure_is_called_through_it(self):
        vm = bare_vm()
        target = fn_info("t", params=["a"], addr=12)
        vm.functions["t"] = target
        vm.module_globals["h"] = Closure(target, [])
        vm.globals = vm.module_globals
        vm.stack = ["arg"]
        step(vm, ("CALL", "h", 1))
        self.assertEqual(12, vm.ip)
        self.assertEqual(1, len(vm.frames))

    def test_an_unknown_name_is_a_name_error(self):
        vm = bare_vm()
        with self.assertRuntimeError("Undefined function: nope", kind="name"):
            step(vm, ("CALL", "nope", 0))


if __name__ == "__main__":
    unittest.main()
