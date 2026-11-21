"""The VM's hot-path shortcuts keep the behaviour of the general code they skip.

Several opcode handlers take a shortcut for speed. Each assumes something, and
each assumption is pinned here, because a shortcut that drifts from the general
path changes behaviour without failing anything else:

- **Hot handlers pop `self.stack` directly**, not through `VM.pop()`, to save a
  Python call per operand. An empty stack must still report `Stack underflow`
  from the handler itself (see `test_opcode_semantics_core.py`), so every
  direct pop sits under `except IndexError: self.stack_underflow()`. That is
  checked on the source, for every handler, including ones written later.
- **Local reads and stores test `type(value) is Cell`** rather than
  `isinstance`. That is only equivalent while `Cell` and `LiveBinding` have no
  subclasses.
- **The conditional jumps decide `true`, `false` and `nil` without
  `is_truthy`**, and **`EQ`/`NE` compare two strings directly**. Both must agree
  with the general helpers on every value.
"""

import ast
import inspect
import sys
import textwrap
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.diagnostics import LangRuntimeError  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.module import LiveBinding  # noqa: E402
from nodus.vm import vm as vm_module  # noqa: E402
from nodus.vm.types import Cell, Record  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402


def bare_vm() -> VM:
    return VM([], {}, code_locs=[], source_path=None)


def run(source: str) -> list[str]:
    result = NodusRuntime(timeout_ms=None).run_source(source)
    if not result.get("ok"):
        raise AssertionError(str(result.get("error")))
    return (result.get("stdout") or "").split()


def _is_stack_pop(node: ast.AST) -> bool:
    """`self.stack.pop()` with no argument."""
    return (
        isinstance(node, ast.Call)
        and not node.args
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "pop"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "stack"
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "self"
    )


def _reports_underflow(try_node: ast.Try) -> bool:
    for handler in try_node.handlers:
        if not (isinstance(handler.type, ast.Name) and handler.type.id == "IndexError"):
            continue
        for stmt in handler.body:
            call = getattr(stmt, "value", None)
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "stack_underflow"):
                return True
    return False


class DirectPopsReportUnderflow(unittest.TestCase):
    def _unguarded_pops(self) -> list[str]:
        tree = ast.parse(textwrap.dedent(inspect.getsource(vm_module)))
        vm_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "VM")
        found = []
        for fn in vm_class.body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            guarded: set[int] = set()
            for node in ast.walk(fn):
                if isinstance(node, ast.Try) and _reports_underflow(node):
                    for inner in node.body:
                        for sub in ast.walk(inner):
                            if _is_stack_pop(sub):
                                guarded.add(id(sub))
            for node in ast.walk(fn):
                if _is_stack_pop(node) and id(node) not in guarded:
                    found.append(f"{fn.name}:{node.lineno}")
        return found

    # Handlers whose direct pop cannot underflow, and why.
    EXEMPT = {
        # Refuses an empty stack first ("ITER_NEXT without iterator") and
        # pops only the iterator it has just read from stack[-1].
        "_op_iter_next",
    }

    def test_every_direct_pop_in_a_handler_is_guarded(self):
        unguarded = [site for site in self._unguarded_pops()
                     if site.startswith("_op_") and site.split(":")[0] not in self.EXEMPT]
        self.assertEqual(unguarded, [], "a handler pops self.stack without reporting "
                         "Stack underflow; wrap it, or call self.pop()")

    def test_every_exemption_is_still_needed(self):
        names = {site.split(":")[0] for site in self._unguarded_pops()}
        self.assertEqual(self.EXEMPT - names, set(), "an exempt handler no longer pops directly")

    def test_the_check_finds_the_guarded_pops(self):
        # Not vacuous: the handlers this file is about do pop directly.
        source = inspect.getsource(VM._op_store_local_idx)
        self.assertIn("self.stack.pop()", source)

    def test_hot_handlers_underflow_with_the_usual_message(self):
        for instr in (("STORE_LOCAL_IDX", 0), ("STORE_ARG", "x"), ("POP",), ("ADD",),
                      ("EQ",), ("NE",), ("INDEX",), ("LOAD_FIELD", "f"), ("RETURN",),
                      ("JUMP_IF_FALSE", 0), ("JUMP_IF_TRUE", 0), ("CALL", "len", 1)):
            with self.subTest(op=instr[0]):
                vm = bare_vm()
                with self.assertRaises(LangRuntimeError) as caught:
                    vm._dispatch[instr[0]](instr)
                self.assertIn("Stack underflow", str(caught.exception))


class ExactTypeChecks(unittest.TestCase):
    def test_cell_and_live_binding_have_no_subclasses(self):
        # LOAD_LOCAL_IDX and STORE_LOCAL_IDX test `type(v) is Cell`. A subclass
        # would be read as a plain value: make the check an isinstance first.
        self.assertEqual(Cell.__subclasses__(), [])
        self.assertEqual(LiveBinding.__subclasses__(), [])

    def test_a_captured_local_is_read_and_written_through_its_cell(self):
        source = (
            "fn counter() {\n"
            "    let n = 0i\n"
            "    let bump = fn() { n = n + 1i\n return n }\n"
            "    bump()\n"
            "    n = n + 10i\n"
            "    print(bump())\n"
            "    print(n)\n"
            "}\n"
            "counter()\n"
        )
        self.assertEqual(run(source), ["12", "12"])

    def test_a_captured_parameter_is_bound_through_its_cell(self):
        source = (
            "fn adder(base) {\n"
            "    let add = fn(x) { return base + x }\n"
            "    return add(5i)\n"
            "}\n"
            "print(adder(10i))\n"
        )
        self.assertEqual(run(source), ["15"])


VALUES = [None, False, True, 0, 1, -1, 0.0, 2.5, "", "a", [], [0], {}, {"k": 1},
          Record({}), Record({"a": 1})]


class ConditionalJumpsAgreeWithIsTruthy(unittest.TestCase):
    def test_both_jumps_on_every_kind_of_value(self):
        for value in VALUES:
            for op, jumps_when in (("JUMP_IF_FALSE", False), ("JUMP_IF_TRUE", True)):
                with self.subTest(op=op, value=value):
                    vm = bare_vm()
                    vm.ip = 0
                    vm.stack = [value]
                    vm._dispatch[op]((op, 99))
                    expected = 99 if bare_vm().is_truthy(value) is jumps_when else 1
                    self.assertEqual(vm.ip, expected)


class EqualityAgreesWithNodusEq(unittest.TestCase):
    PAIRS = [("a", "a"), ("a", "b"), ("", ""), ("1", 1), (1, "1"), (1, 1.0), (True, 1),
             (None, None), (None, ""), (2 ** 53 + 1, 2 ** 53), ([1], [1]), ("x", None)]

    def test_eq_and_ne_on_every_pair(self):
        for a, b in self.PAIRS:
            for op in ("EQ", "NE"):
                with self.subTest(op=op, a=a, b=b):
                    vm = bare_vm()
                    vm.stack = [a, b]
                    vm._dispatch[op]((op,))
                    expected = VM._nodus_eq(a, b)
                    self.assertEqual(vm.stack, [expected if op == "EQ" else not expected])


class BuiltinArguments(unittest.TestCase):
    def test_arguments_arrive_in_order(self):
        self.assertEqual(run('print(substring("abcdef", 1i, 3i))'), ["bc"])

    def test_a_builtin_without_arguments(self):
        self.assertEqual(run('let ch = channel()\nprint(type(ch))'), ["channel"])

    def test_the_stack_below_the_arguments_is_left_alone(self):
        self.assertEqual(run('let xs = [1i, 2i]\nprint(len(xs) + len("abc"))'), ["5"])


if __name__ == "__main__":
    unittest.main()
