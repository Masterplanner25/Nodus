"""`RESET_LOCAL_IDX` is dropped where no closure captures the slot.

The compiler emits a reset before every `let` store and every `for` variable
store in a function, so that a closure made in a loop captures a fresh `Cell`
each iteration. A reset only detaches a `Cell`, and only `MAKE_CLOSURE`
capturing a slot puts one there. So a reset of a slot that no closure in the
function captures does nothing. The compiler lists those
(`Compiler.uncaptured_resets`) and the optimizer removes them.

The risk is all on one side: removing a reset that a capture needs makes every
closure made in a loop share one variable. So every behaviour here is checked
with the optimizer on and off, and the cases are the ways a capture can be
indirect.
"""

import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.compiler.optimizer import drop_uncaptured_resets  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402


def run(src: str, optimize: bool) -> list[str]:
    result = NodusRuntime(timeout_ms=None).run_source(src, optimize=optimize)
    if not result.get("ok"):
        raise AssertionError(str(result.get("error")))
    return (result.get("stdout") or "").split()


def resets(src: str, optimize: bool) -> int:
    code, _fns, _locs = ModuleLoader(project_root=None).compile_only(
        src, module_name="main.nd", optimize=optimize)
    return sum(1 for instr in code["instructions"] if instr[0] == "RESET_LOCAL_IDX")


class Removed(unittest.TestCase):
    def test_a_function_without_closures_keeps_no_resets(self):
        src = (
            "fn f(xs) {\n"
            "    let total = 0i\n"
            "    for x in xs {\n"
            "        let doubled = x * 2i\n"
            "        total = total + doubled\n"
            "    }\n"
            "    return total\n"
            "}\n"
            "print(f([1i, 2i, 3i]))\n"
        )
        self.assertEqual(resets(src, optimize=False), 3)
        self.assertEqual(resets(src, optimize=True), 0)
        self.assertEqual(run(src, True), ["12"])

    def test_only_the_captured_slot_keeps_its_reset(self):
        src = (
            "fn f() {\n"
            "    let fns = []\n"
            "    for i in [1i, 2i, 3i] {\n"
            "        let unused = i + 100i\n"
            "        push(fns, fn() { return i })\n"
            "    }\n"
            "    return fns\n"
            "}\n"
            "for g in f() { print(g()) }\n"
        )
        # `fns` and `unused` lose theirs; `i`, which the closure captures, keeps its.
        self.assertEqual(resets(src, optimize=False), 3)
        self.assertEqual(resets(src, optimize=True), 1)


class CapturesStillGetAFreshCellEachIteration(unittest.TestCase):
    CASES = {
        "for variable": (
            "fn f() {\n"
            "    let fns = []\n"
            "    for i in [1i, 2i, 3i] { push(fns, fn() { return i }) }\n"
            "    return fns\n"
            "}\n"
            "for g in f() { print(g()) }\n",
            ["1", "2", "3"],
        ),
        "let in a while loop": (
            "fn f() {\n"
            "    let fns = []\n"
            "    let n = 0i\n"
            "    while (n < 3i) {\n"
            "        n = n + 1i\n"
            "        let k = n * 10i\n"
            "        push(fns, fn() { return k })\n"
            "    }\n"
            "    return fns\n"
            "}\n"
            "for g in f() { print(g()) }\n",
            ["10", "20", "30"],
        ),
        "captured through a nested closure": (
            # The inner fn captures `k` from two levels out; the middle closure
            # carries the is_local upvalue.
            "fn f() {\n"
            "    let fns = []\n"
            "    for i in [1i, 2i] {\n"
            "        let k = i\n"
            "        push(fns, fn() { return fn() { return k } })\n"
            "    }\n"
            "    return fns\n"
            "}\n"
            "for g in f() { print(g()()) }\n",
            ["1", "2"],
        ),
        "a slot shared by sibling blocks": (
            # `a` and `b` live in sibling blocks and may share a slot; only one
            # is captured.
            "fn f() {\n"
            "    let fns = []\n"
            "    for i in [1i, 2i] {\n"
            "        if (true) { let a = i * 100i\n push(fns, fn() { return a }) }\n"
            "        if (true) { let b = i\n print(b) }\n"
            "    }\n"
            "    return fns\n"
            "}\n"
            "for g in f() { print(g()) }\n",
            ["1", "2", "100", "200"],
        ),
        "a recursive local function": (
            "fn f() {\n"
            "    let out = []\n"
            "    for n in [3i, 4i] {\n"
            "        let fact = fn(m) { if (m <= 1i) { return 1i }\n return m * fact(m - 1i) }\n"
            "        push(out, fact(n))\n"
            "    }\n"
            "    return out\n"
            "}\n"
            "for v in f() { print(v) }\n",
            ["6", "24"],
        ),
        "a named nested function": (
            "fn f() {\n"
            "    let fns = []\n"
            "    for i in [5i, 6i] {\n"
            "        fn get() { return i }\n"
            "        push(fns, get)\n"
            "    }\n"
            "    return fns\n"
            "}\n"
            "for g in f() { print(g()) }\n",
            ["5", "6"],
        ),
    }

    def test_every_case_with_and_without_the_optimizer(self):
        for name, (src, expected) in self.CASES.items():
            with self.subTest(case=name):
                self.assertEqual(run(src, False), expected)
                self.assertEqual(run(src, True), expected)


class TheCompilersBookkeeping(unittest.TestCase):
    def test_an_upvalue_without_a_slot_keeps_every_reset(self):
        # VM.capture_local finds such a slot by name, so the compiler cannot
        # say which slot is captured.
        from nodus.compiler.compiler import Compiler
        from nodus.compiler.symbol_table import Upvalue

        compiler = Compiler(module_infos={}, module_defs_index={}, builtin_names=set())
        compiler._reset_frames.append(([(7, 0), (9, 1)], set()))   # the outer function
        compiler._reset_frames.append(([], set()))                 # the closure
        compiler._close_reset_frame([Upvalue(name="x", is_local=True, index=None)])
        compiler._close_reset_frame([])
        self.assertEqual(compiler.uncaptured_resets, set())

    def test_an_upvalue_with_a_slot_keeps_only_that_reset(self):
        from nodus.compiler.compiler import Compiler
        from nodus.compiler.symbol_table import Upvalue

        compiler = Compiler(module_infos={}, module_defs_index={}, builtin_names=set())
        compiler._reset_frames.append(([(7, 0), (9, 1)], set()))
        compiler._reset_frames.append(([], set()))
        compiler._close_reset_frame([Upvalue(name="x", is_local=True, index=1)])
        compiler._close_reset_frame([])
        self.assertEqual(compiler.uncaptured_resets, {7})

    def test_the_optimizer_refuses_an_index_that_is_not_a_reset(self):
        code = [("PUSH_CONST", 1), ("POP",), ("HALT",)]
        with self.assertRaises(ValueError):
            drop_uncaptured_resets(code, {}, [(None, None, None)] * 3, {1})


if __name__ == "__main__":
    unittest.main()
