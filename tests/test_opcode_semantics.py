"""Per-opcode semantic specification for the control-flow and frame opcodes (#412 phase 2).

`nodus_gate --opcodes` verifies the **inventory** — that the docs and the VM
dispatch table name the same 49 opcodes. `tests/test_bytecode_golden.py` verifies
**emission** — that the compiler emits the sequences it used to emit. Between
them, nothing verified that any opcode *does what it is documented to do*, and
the three most severe VM bugs of the v5 cycle (#361, #370, #371) were all
opcode-semantics defects on the exception-unwind path.

The test shape the issue asks for, and the reason it is not another end-to-end
program: **construct a known VM state, execute exactly one instruction, assert
the resulting state.** A program that happens to exercise an opcode passes as
long as the *program's* output is right, which is how #370 survived — the
opcode was wrong on a path the program never reached. Here the pre-state is
built by hand, so the path is not a matter of luck.

Scope is the ten opcodes #412 names, not all 49: `SETUP_TRY`, `POP_TRY`,
`FINALLY_END`, `THROW`, `YIELD`, `MAKE_CLOSURE`, `FRAME_SIZE`,
`RESET_LOCAL_IDX`, `CALL_VALUE`, `CALL_METHOD`. `ADD` and `POP` are not where
the bugs were. Phase 1's census (`tools/README_opcode_census.md`) is the ordering
behind that: `POP_TRY` executes 18 times across the whole suite and
`FINALLY_END` 60, which is not an exercised path.

Each spec below states the four things #412 asks be written down and checked:
operands consumed, net stack effect, side effects on frame/`handler_stack`/`ip`/
coroutine state, and error behaviour on a wrong pre-state.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.compiler.compiler import FunctionInfo  # noqa: E402
from nodus.compiler.symbol_table import Upvalue  # noqa: E402
from nodus.runtime.diagnostics import LangRuntimeError  # noqa: E402
from nodus.vm.types import Closure, Frame, Record  # noqa: E402
from nodus.vm.vm import VM, _DEFERRED_NONE, _FINALLY_GATE  # noqa: E402


# The opcodes this module specifies. Named once so the coverage test below drives
# off the tuple rather than a second hand-kept list -- the pattern the recurring
# bug shape section prescribes for exactly this ("name the set once, make a test
# drive off it, so a new member fails the suite until somebody handles it").
SPECIFIED = (
    "SETUP_TRY",
    "POP_TRY",
    "FINALLY_END",
    "THROW",
    "YIELD",
    "MAKE_CLOSURE",
    "FRAME_SIZE",
    "RESET_LOCAL_IDX",
    "CALL_VALUE",
    "CALL_METHOD",
)


def bare_vm() -> VM:
    """A VM with no program, for single-instruction execution.

    `code=[]` is deliberate: nothing here runs a program, so a handler that
    reads `self.code` rather than only the instruction it was handed would fail
    loudly instead of quietly doing something plausible.
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


def step(vm: VM, instr: tuple):
    """Execute exactly one instruction through the real dispatch table.

    Through `_dispatch`, not by calling the handler by name: the table is what
    `execute()` uses, so a handler renamed or rebound without the table moving
    with it is a difference this notices.
    """
    op = instr[0]
    handler = vm._dispatch.get(op)
    if handler is None:
        raise AssertionError(f"{op} is not in the dispatch table")
    return handler(instr)


class DispatchCoverageTests(unittest.TestCase):
    """The specified set must stay a subset of what the VM actually dispatches."""

    def test_every_specified_opcode_is_dispatched(self):
        dispatched = set(bare_vm()._dispatch)
        missing = [op for op in SPECIFIED if op not in dispatched]
        self.assertEqual([], missing, "specified opcodes absent from the dispatch table")

    def test_the_specified_set_has_no_duplicates(self):
        self.assertEqual(len(SPECIFIED), len(set(SPECIFIED)))


# closes: #412
class SetupTryTests(unittest.TestCase):
    """SETUP_TRY — operands `handler_ip`, optional `finally_ip`; no stack change.

    Side effect: pushes the 4-tuple `(handler_ip, finally_ip, stack_depth,
    frame_depth)` onto `handler_stack`. Advances `ip` by one.
    """

    def test_it_pushes_the_documented_four_tuple(self):
        vm = bare_vm()
        vm.stack = ["a", "b", "c"]
        vm.frames = [frame(), frame()]
        vm.ip = 7

        step(vm, ("SETUP_TRY", 40, 90))

        self.assertEqual([(40, 90, 3, 2)], vm.handler_stack)
        self.assertEqual(8, vm.ip)
        self.assertEqual(["a", "b", "c"], vm.stack, "SETUP_TRY must not touch the stack")

    def test_the_finally_operand_is_optional_and_defaults_to_zero(self):
        """A two-element instruction is the `try/catch` form. Zero means "no
        finally", which is what `POP_TRY` tests for."""
        vm = bare_vm()
        step(vm, ("SETUP_TRY", 40))
        self.assertEqual([(40, 0, 0, 0)], vm.handler_stack)

    def test_the_recorded_depths_are_of_the_state_at_setup(self):
        """Not the depths at unwind time. `handle_exception` truncates back to
        these, so recording them late would leave whatever the body pushed."""
        vm = bare_vm()
        vm.stack = ["only"]
        step(vm, ("SETUP_TRY", 1, 0))
        vm.stack.extend(["body", "pushed", "these"])
        self.assertEqual(1, vm.handler_stack[0][2])

    def test_nesting_pushes_rather_than_replaces(self):
        vm = bare_vm()
        step(vm, ("SETUP_TRY", 10, 0))
        step(vm, ("SETUP_TRY", 20, 0))
        self.assertEqual([(10, 0, 0, 0), (20, 0, 0, 0)], vm.handler_stack)


# closes: #412
class PopTryTests(unittest.TestCase):
    """POP_TRY — no operands; no stack change.

    Side effect: pops the top `handler_stack` entry. `ip` goes to that entry's
    `finally_ip` when it is non-zero, else advances by one. Errors when the
    handler stack is empty.
    """

    def test_a_handler_with_no_finally_just_advances(self):
        vm = bare_vm()
        vm.handler_stack = [(40, 0, 0, 0)]
        vm.ip = 12

        step(vm, ("POP_TRY",))

        self.assertEqual([], vm.handler_stack)
        self.assertEqual(13, vm.ip)

    def test_a_finally_target_redirects_instead_of_advancing(self):
        """The documented redirect, and the reason `finally_ip` rides on the
        handler entry rather than on the POP_TRY instruction."""
        vm = bare_vm()
        vm.handler_stack = [(40, 90, 0, 0)]
        vm.ip = 12

        step(vm, ("POP_TRY",))

        self.assertEqual(90, vm.ip)
        self.assertEqual([], vm.handler_stack)

    def test_it_pops_only_the_innermost_handler(self):
        vm = bare_vm()
        vm.handler_stack = [(10, 0, 0, 0), (20, 0, 0, 0)]
        step(vm, ("POP_TRY",))
        self.assertEqual([(10, 0, 0, 0)], vm.handler_stack)

    def test_an_empty_handler_stack_is_a_runtime_error(self):
        vm = bare_vm()
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("POP_TRY",))
        self.assertIn("POP_TRY without handler", str(caught.exception))

    def test_the_stack_is_untouched_on_both_paths(self):
        for finally_ip in (0, 90):
            with self.subTest(finally_ip=finally_ip):
                vm = bare_vm()
                vm.stack = ["x", "y"]
                vm.handler_stack = [(40, finally_ip, 0, 0)]
                step(vm, ("POP_TRY",))
                self.assertEqual(["x", "y"], vm.stack)


# closes: #412
class FinallyEndTests(unittest.TestCase):
    """FINALLY_END — no operands.

    Three distinct exits, only one of which the reference described before this
    module was written:

    1. a **deferred error** is pending (the catch block raised and this finally
       ran on the way out, #361) — resume propagation;
    2. a **deferred return** is pending — perform the return that RETURN parked;
    3. neither — advance `ip` by one.

    In cases 2 and 3 it also pops a `_FINALLY_GATE` sentinel left by
    `handle_exception` on the normal catch-exit path. Case 1 must *not*, because
    `handle_exception` already consumed this region's gate and the top entry then
    belongs to an enclosing catch.
    """

    def test_the_plain_path_advances_and_changes_nothing_else(self):
        vm = bare_vm()
        vm.stack = ["kept"]
        vm.ip = 30

        step(vm, ("FINALLY_END",))

        self.assertEqual(31, vm.ip)
        self.assertEqual(["kept"], vm.stack)
        self.assertEqual([], vm.frames)

    def test_it_consumes_a_finally_gate_left_by_the_catch_exit(self):
        """Not popping it pollutes the *enclosing* handler stack — the state
        error that class of bug is made of."""
        vm = bare_vm()
        vm.handler_stack = [(10, 0, 0, 0), (_FINALLY_GATE, 0, 0, 0)]

        step(vm, ("FINALLY_END",))

        self.assertEqual([(10, 0, 0, 0)], vm.handler_stack)

    def test_it_leaves_a_real_handler_entry_alone(self):
        """Only the sentinel is consumed. Popping unconditionally would disarm a
        live enclosing `try` every time an unrelated finally completed."""
        vm = bare_vm()
        vm.handler_stack = [(10, 0, 0, 0)]

        step(vm, ("FINALLY_END",))

        self.assertEqual([(10, 0, 0, 0)], vm.handler_stack)

    def test_a_deferred_return_pops_the_frame_and_pushes_the_value(self):
        vm = bare_vm()
        vm.frames = [frame(return_ip=99, fn_name="caller")]
        vm._deferred_return = "returned"
        vm.ip = 30

        step(vm, ("FINALLY_END",))

        self.assertEqual([], vm.frames)
        self.assertEqual(["returned"], vm.stack)
        self.assertEqual(99, vm.ip)
        self.assertIs(_DEFERRED_NONE, vm._deferred_return,
                      "the deferred slot must be cleared, or the next FINALLY_END returns again")

    def test_a_deferred_return_with_no_frame_is_a_runtime_error(self):
        vm = bare_vm()
        vm._deferred_return = "orphan"
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("FINALLY_END",))
        self.assertIn("deferred return outside function", str(caught.exception))

    def test_a_deferred_return_drops_handlers_belonging_to_the_popped_frame(self):
        """Frame depth is what scopes a handler. An entry recorded at a deeper
        frame cannot be caught by anything once that frame is gone, and leaving
        it makes the *next* throw unwind into a dead frame."""
        vm = bare_vm()
        vm.frames = [frame(return_ip=99)]
        vm.handler_stack = [(10, 0, 0, 0), (20, 0, 0, 1), (30, 0, 0, 5)]
        vm._deferred_return = "v"

        step(vm, ("FINALLY_END",))

        self.assertEqual([(10, 0, 0, 0)], vm.handler_stack)

    def test_a_deferred_error_with_no_handler_is_re_raised(self):
        """#361: the catch block raised, the finally ran on the way out, and
        propagation resumes here rather than being swallowed. Swallowing it is
        the failure mode — a `try/catch/finally` that quietly discards what its
        catch threw."""
        vm = bare_vm()
        raised = LangRuntimeError("thrown", "from the catch block")
        vm._deferred_error = raised

        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("FINALLY_END",))

        self.assertIs(raised, caught.exception)

    def test_a_deferred_error_is_delivered_to_an_enclosing_handler(self):
        vm = bare_vm()
        vm.handler_stack = [(77, 0, 0, 0)]
        vm._deferred_error = LangRuntimeError("thrown", "boom")

        result = step(vm, ("FINALLY_END",))

        self.assertIsNone(result)
        self.assertEqual(77, vm.ip, "control did not transfer to the enclosing handler")

    def test_a_deferred_error_reaches_an_enclosing_gate_rather_than_being_dropped(self):
        """The ordering the handler's own comment calls load-bearing.

        The deferred re-raise is checked **before** the gate pop, because
        `handle_exception` already consumed this region's gate — so a top entry
        that is still a gate belongs to an *enclosing* catch. Popping it here
        would disarm that catch: the enclosing finally would be skipped and the
        error would leave the region without its cleanup having run, which is
        #361 one level out.

        What must happen instead is that the error is handed to
        `handle_exception`, which jumps into the enclosing finally and re-arms
        the deferral for *its* FINALLY_END. Chained, not dropped.
        """
        vm = bare_vm()
        vm.handler_stack = [(_FINALLY_GATE, 55, 0, 0)]
        raised = LangRuntimeError("thrown", "boom")
        vm._deferred_error = raised

        self.assertIsNone(step(vm, ("FINALLY_END",)))

        self.assertEqual(55, vm.ip, "the enclosing finally was skipped")
        self.assertIs(raised, vm._deferred_error,
                      "the error was not re-armed for the enclosing FINALLY_END")
        self.assertEqual([], vm.handler_stack)

    def test_an_error_takes_precedence_over_a_pending_return(self):
        """Both can be pending. An error that lost to a return would be lost
        entirely — the return would complete and nothing would report it."""
        vm = bare_vm()
        vm.frames = [frame(return_ip=99)]
        vm._deferred_return = "return wins?"
        vm._deferred_error = LangRuntimeError("thrown", "no, the error does")

        with self.assertRaises(LangRuntimeError):
            step(vm, ("FINALLY_END",))

        self.assertEqual([frame(return_ip=99)], vm.frames, "the frame was popped anyway")


# closes: #412
class ThrowTests(unittest.TestCase):
    """THROW — no operands; pops one value and transfers control.

    A string becomes the message; an int/float/bool is stringified into it; any
    other value is preserved in `err.payload` with `kind == "thrown"`.

    A note on where `message` lives, because the reference's wording invites the
    wrong reading: `err.message` is a field of the **Nodus record a `catch` block
    receives**, which `handle_exception` builds as `str(err)`. The Python
    `LangRuntimeError` this opcode raises has `kind`, `payload`, `origin`, and
    the message only through `str()`. Asserting `err.message` on the exception
    is an `AttributeError`, which is how this was found.
    """

    def _throw(self, value):
        vm = bare_vm()
        vm.stack = [value]
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("THROW",))
        return vm, caught.exception

    def test_a_string_becomes_the_message(self):
        _vm, err = self._throw("plain failure")
        self.assertEqual("thrown", err.kind)
        self.assertEqual("plain failure", str(err))
        self.assertIsNone(err.payload)

    def test_a_number_is_stringified_into_the_message(self):
        _vm, err = self._throw(42)
        self.assertEqual("thrown", err.kind)
        self.assertIn("42", str(err))
        self.assertIsNone(err.payload, "a primitive must not also arrive as a payload")

    def test_the_catch_record_carries_the_message_and_payload(self):
        """The contract the reference actually describes, checked on the value a
        program sees rather than on the Python exception.

        Two units, deliberately: THROW always raises — the handler stack is
        consulted by `execute()`'s except clause, not by the opcode — so this
        does what `execute()` does and hands the exception to
        `handle_exception`. Asserting the record without that step is
        impossible, which is itself worth knowing about THROW's stack effect:
        "transfers control to handler" happens one level up.
        """
        vm = bare_vm()
        vm.handler_stack = [(77, 0, 0, 0)]
        payload = Record({"code": 7})
        vm.stack = [payload]

        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("THROW",))
        self.assertTrue(vm.handle_exception(caught.exception))

        record = vm.stack[-1]
        self.assertEqual("error", record.kind)
        self.assertEqual("thrown", record.fields["kind"])
        self.assertIs(payload, record.fields["payload"])
        self.assertEqual("user", record.fields["origin"])

    def test_a_record_is_preserved_as_a_payload(self):
        """The documented structured-throw contract, and the half a stringifying
        implementation silently drops."""
        payload = Record({"code": 7, "why": "quota"})
        _vm, err = self._throw(payload)
        self.assertEqual("thrown", err.kind)
        self.assertIs(payload, err.payload)

    def test_a_list_is_preserved_as_a_payload(self):
        payload = [1, 2, 3]
        _vm, err = self._throw(payload)
        self.assertIs(payload, err.payload)

    def test_it_pops_exactly_one_value(self):
        vm = bare_vm()
        vm.stack = ["below", "thrown value"]
        with self.assertRaises(LangRuntimeError):
            step(vm, ("THROW",))
        self.assertEqual(["below"], vm.stack)

    def test_it_is_attributed_to_the_user_not_the_runtime(self):
        """`origin` is what separates a program's own `throw` from a VM fault in
        error reporting; a THROW reported as runtime origin reads as a bug in
        Nodus rather than in the program."""
        _vm, err = self._throw("mine")
        self.assertEqual("user", getattr(err, "origin", None))


# closes: #412
class YieldTests(unittest.TestCase):
    """YIELD — no operands; pops one value.

    Returns the `("yield", value)` tuple that `execute()` propagates to the
    scheduler, marks the current coroutine suspended, and saves resume state at
    `ip + 1`. Outside a coroutine it is a runtime error.
    """

    def _coroutine(self):
        class _Coro:
            state = "running"
            ip = None
            stack = None
            frames = None
            handler_stack = None
            deferred_return = None
            deferred_return_depth = 0
            deferred_error = None
            deferred_error_depth = 0

        return _Coro()

    def test_it_returns_the_yield_tuple_with_the_popped_value(self):
        vm = bare_vm()
        vm.current_coroutine = self._coroutine()
        vm.stack = ["yielded"]

        self.assertEqual(("yield", "yielded"), step(vm, ("YIELD",)))

    def test_it_suspends_the_coroutine_and_resumes_after_the_yield(self):
        """`ip + 1`, not `ip`. Saving `ip` would re-execute the YIELD on resume
        and suspend forever."""
        vm = bare_vm()
        coro = self._coroutine()
        vm.current_coroutine = coro
        vm.stack = ["v"]
        vm.ip = 15

        step(vm, ("YIELD",))

        self.assertEqual("suspended", coro.state)
        self.assertEqual(16, coro.ip)

    def test_outside_a_coroutine_it_is_a_runtime_error(self):
        vm = bare_vm()
        vm.stack = ["v"]
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("YIELD",))
        self.assertIn("yield outside coroutine", str(caught.exception))

    def test_the_saved_state_is_the_frames_and_handlers_at_the_yield(self):
        vm = bare_vm()
        coro = self._coroutine()
        vm.current_coroutine = coro
        vm.frames = [frame()]
        vm.handler_stack = [(10, 0, 0, 1)]
        vm.stack = ["v"]

        step(vm, ("YIELD",))

        self.assertEqual(vm.frames, coro.frames)
        self.assertEqual([(10, 0, 0, 1)], coro.handler_stack)


# closes: #412
class MakeClosureTests(unittest.TestCase):
    """MAKE_CLOSURE — operand is a function name; pushes one Closure.

    Local upvalues are captured as Cells from the current frame; non-local ones
    are taken by index from the enclosing closure. Both missing-context cases are
    runtime errors rather than silent empty captures.
    """

    def _fn(self, name="g", upvalues=()):
        return FunctionInfo(
            name=name, params=[], addr=0, upvalues=list(upvalues), display_name=name
        )

    def test_it_pushes_a_closure_for_a_known_function(self):
        vm = bare_vm()
        fn = self._fn()
        vm.functions = {"g": fn}
        vm.ip = 4

        step(vm, ("MAKE_CLOSURE", "g"))

        self.assertEqual(1, len(vm.stack))
        closure = vm.stack[0]
        self.assertIsInstance(closure, Closure)
        self.assertIs(fn, closure.function)
        self.assertEqual([], closure.upvalues)
        self.assertEqual(5, vm.ip)

    def test_an_unknown_function_name_is_a_runtime_error(self):
        vm = bare_vm()
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("MAKE_CLOSURE", "nope"))
        self.assertIn("Unknown function for closure", str(caught.exception))

    def test_a_local_capture_shares_a_cell_with_the_frame(self):
        """Sharing is the point — the closure must see later writes to the
        captured variable, which a copy would not."""
        vm = bare_vm()
        vm.functions = {"g": self._fn(upvalues=[Upvalue(name="x", is_local=True, index=0)])}
        vm.frames = [frame(locals={"x": 1})]

        step(vm, ("MAKE_CLOSURE", "g"))

        cell = vm.stack[0].upvalues[0]
        self.assertEqual(1, cell.value)
        cell.value = 2
        self.assertEqual(2, vm.frames[-1].locals["x"].value)

    def test_a_local_capture_without_a_frame_is_a_runtime_error(self):
        vm = bare_vm()
        vm.functions = {"g": self._fn(upvalues=[Upvalue(name="x", is_local=True, index=0)])}
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("MAKE_CLOSURE", "g"))
        self.assertIn("Closure capture without frame", str(caught.exception))

    def test_an_outer_capture_without_an_enclosing_closure_is_a_runtime_error(self):
        vm = bare_vm()
        vm.functions = {"g": self._fn(upvalues=[Upvalue(name="x", is_local=False, index=0)])}
        vm.frames = [frame()]
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("MAKE_CLOSURE", "g"))
        self.assertIn("Closure capture missing outer closure", str(caught.exception))


# closes: #412
class FrameSizeTests(unittest.TestCase):
    """FRAME_SIZE — operand is a slot count; no stack change.

    Allocates the current frame's slot-indexed locals array. Emitted as the first
    instruction of every compiled function body, so it runs with the frame
    already pushed.
    """

    def test_it_allocates_exactly_the_requested_number_of_slots(self):
        vm = bare_vm()
        vm.frames = [frame()]
        vm.ip = 0

        step(vm, ("FRAME_SIZE", 3))

        self.assertEqual([None, None, None], vm.frames[-1].locals_array)
        self.assertEqual(1, vm.ip)

    def test_zero_slots_allocates_an_empty_array_not_none(self):
        """`None` and `[]` are not the same to LOAD_LOCAL_IDX; a function with no
        locals still executes FRAME_SIZE."""
        vm = bare_vm()
        vm.frames = [frame()]
        step(vm, ("FRAME_SIZE", 0))
        self.assertEqual([], vm.frames[-1].locals_array)

    def test_it_targets_the_innermost_frame(self):
        vm = bare_vm()
        outer = frame(fn_name="outer")
        outer.locals_array = ["outer's"]
        vm.frames = [outer, frame(fn_name="inner")]

        step(vm, ("FRAME_SIZE", 2))

        self.assertEqual(["outer's"], vm.frames[0].locals_array, "the caller's slots moved")
        self.assertEqual([None, None], vm.frames[1].locals_array)

    def test_it_does_not_touch_the_stack(self):
        vm = bare_vm()
        vm.frames = [frame()]
        vm.stack = ["a"]
        step(vm, ("FRAME_SIZE", 1))
        self.assertEqual(["a"], vm.stack)


# closes: #412
class ResetLocalIdxTests(unittest.TestCase):
    """RESET_LOCAL_IDX — operand is a slot index; no stack change.

    Writes `None` over the slot so the next MAKE_CLOSURE captures a *fresh* Cell.
    Emitted per loop iteration; without it every iteration's closure would share
    one Cell and all of them would observe the last value.
    """

    def test_it_clears_the_named_slot_only(self):
        vm = bare_vm()
        f = frame()
        f.locals_array = ["a", "b", "c"]
        vm.frames = [f]
        vm.ip = 5

        step(vm, ("RESET_LOCAL_IDX", 1))

        self.assertEqual(["a", None, "c"], f.locals_array)
        self.assertEqual(6, vm.ip)

    def test_it_detaches_a_cell_rather_than_clearing_it(self):
        """The distinction that makes per-iteration capture work: the Cell an
        earlier closure captured must survive with its value; only this frame's
        reference to it is dropped."""
        vm = bare_vm()
        f = frame()
        vm.frames = [f]
        f.locals_array = [None]
        f.locals_name_to_slot = {"i": 0}
        cell = vm.capture_local(f, "i")
        cell.value = "first iteration"

        step(vm, ("RESET_LOCAL_IDX", 0))

        self.assertIsNone(f.locals_array[0])
        self.assertEqual("first iteration", cell.value, "the captured Cell was mutated")


# closes: #412
class CallValueTests(unittest.TestCase):
    """CALL_VALUE — operand is an argument count; pops that many args plus the
    callee, and pushes or transfers per the callee's kind.

    Arguments are popped in reverse and re-ordered before being re-pushed, which
    is the half a hand-written implementation gets wrong: the compiler pushes
    left-to-right, so popping without reversing binds the parameters backwards.

    It transfers control rather than returning a value — `call_closure` pushes a
    frame and sets `ip` to the function's address, and the currently running
    `execute()` loop continues into it. So the post-state to assert is the frame
    and the stack, not a result.

    **A plain Python callable is not a callee.** Only `Closure`,
    `ModuleFunction` and `_ClosureProxy` are; anything else, including a bare
    function, is refused as `Cannot call non-function`. Assuming otherwise is
    how the first draft of this test went red.
    """

    def _closure(self, params, addr=64):
        fn = FunctionInfo(
            name="g", params=list(params), addr=addr, upvalues=[], display_name="g"
        )
        return Closure(fn, [])

    def test_arguments_are_re_pushed_in_source_order(self):
        vm = bare_vm()
        vm.stack = [self._closure(["a", "b", "c"]), "first", "second", "third"]
        vm.ip = 3

        step(vm, ("CALL_VALUE", 3))

        self.assertEqual(["first", "second", "third"], vm.stack)
        self.assertEqual(64, vm.ip, "control did not transfer to the function body")
        self.assertEqual(1, len(vm.frames))
        self.assertEqual(4, vm.frames[-1].return_ip, "the caller resumes after the call")

    def test_zero_arguments_still_pops_the_callee(self):
        vm = bare_vm()
        vm.stack = ["below", self._closure([])]

        step(vm, ("CALL_VALUE", 0))

        self.assertEqual(["below"], vm.stack)
        self.assertEqual(1, len(vm.frames))

    def test_calling_a_non_callable_is_a_runtime_error(self):
        vm = bare_vm()
        vm.stack = [42, "arg"]
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("CALL_VALUE", 1))
        self.assertIn("Cannot call non-function", str(caught.exception))

    def test_a_bare_python_callable_is_refused(self):
        """Not a pedantic case: a host that stores a raw callable in a global
        rather than registering it would otherwise get a call that appears to
        work while bypassing every arity and capability check."""
        vm = bare_vm()
        vm.stack = [lambda: "v"]
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("CALL_VALUE", 0))
        self.assertIn("Cannot call non-function", str(caught.exception))

    def test_an_arity_mismatch_is_a_runtime_error(self):
        vm = bare_vm()
        vm.stack = [self._closure(["a", "b"]), "only one"]
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("CALL_VALUE", 1))
        self.assertIn("expected 2 args, got 1", str(caught.exception))


# closes: #412
class CallMethodTests(unittest.TestCase):
    """CALL_METHOD — operands are a method name and an argument count.

    The receiver must be a `Record` or a `NodusModule`. **A string is not a
    valid receiver** — `"Value".to_upper()` is a type error in Nodus, not a
    method call — which the reference's "runtime error if not a record" states
    correctly and which a reader coming from another language will not expect.

    A `BuiltinMethod` field is invoked directly and its result pushed; an
    ordinary function field is called with the record injected as the first
    argument, which is the implicit `self`.
    """

    def test_a_string_receiver_is_a_type_error(self):
        vm = bare_vm()
        vm.stack = ["a string"]
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("CALL_METHOD", "to_upper", 0))
        self.assertIn("only supported on records", str(caught.exception))

    def test_a_missing_field_is_a_key_error_not_a_nil(self):
        """A silent nil would be indistinguishable from a method that returns
        nothing, which is the worse of the two failures."""
        vm = bare_vm()
        vm.stack = [Record({"present": 1})]
        with self.assertRaises(LangRuntimeError) as caught:
            step(vm, ("CALL_METHOD", "absent", 0))
        self.assertIn("Missing record field: absent", str(caught.exception))

    def test_a_builtin_method_field_is_invoked_and_its_result_pushed(self):
        from nodus.vm.types import BuiltinMethod

        vm = bare_vm()
        seen = []
        vm.stack = [
            Record({"go": BuiltinMethod(lambda a, b: seen.append((a, b)) or "ok")}),
            "first",
            "second",
        ]
        vm.ip = 9

        step(vm, ("CALL_METHOD", "go", 2))

        self.assertEqual([("first", "second")], seen, "arguments arrived out of order")
        self.assertEqual(["ok"], vm.stack)
        self.assertEqual(10, vm.ip)

    def test_a_function_field_receives_the_record_as_its_first_argument(self):
        """The implicit `self` the reference describes. Without it a record
        method cannot read its own fields."""
        receiver = Record({})
        closure = Closure(
            FunctionInfo(name="m", params=["self", "x"], addr=32, upvalues=[],
                         display_name="m"),
            [],
        )
        receiver.fields["m"] = closure

        vm = bare_vm()
        vm.stack = [receiver, "arg"]

        step(vm, ("CALL_METHOD", "m", 1))

        self.assertEqual([receiver, "arg"], vm.stack)
        self.assertEqual(32, vm.ip)


if __name__ == "__main__":
    unittest.main()
