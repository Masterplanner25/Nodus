"""A return leaves the caller's stack as it found it (#952).

`RETURN` popped the callee's frame and pushed the result, but never cut the
operand stack back to where the frame began. Two constructs leave values there:
a `for ... in` loop keeps its iterator on the stack, and a `match` used as an
operand has that operand pending while an arm runs. A `return` from inside
either left the value behind. The caller then read it in place of its own
operand, silently: `[p, find(xs), q]` came back as `[<Iterator>, 2, "q"]`.

Each `Frame` now records `stack_base`, the depth below which the stack is the
caller's, and every return cuts back to it.

The return held back by a `finally` was a second copy of the return logic, and
it had drifted: it never restored a cross-module frame's module context. Inside
a coroutine, where module functions run on the caller's VM, a module function
returning through `finally` left the caller executing the module's bytecode.
Both returns are now one method, `VM._complete_return`.
"""

import ast
import os
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FIND = (
    "fn find(xs) {\n"
    "    for x in xs {\n"
    "        if (x == 2i) {\n"
    "            return x\n"
    "        }\n"
    "    }\n"
    "    return nil\n"
    "}\n"
)

_MODULE = (
    'let secret = "module"\n'
    "export fn first_even(xs) {\n"
    "    for x in xs {\n"
    "        if (x % 2i == 0i) {\n"
    "            return x\n"
    "        }\n"
    "    }\n"
    "    return nil\n"
    "}\n"
    "export fn guarded() {\n"
    "    try {\n"
    "        return secret\n"
    "    } finally {\n"
    "        let cleanup = 1i\n"
    "    }\n"
    "}\n"
)


def _run(source: str, runtime: NodusRuntime | None = None) -> str:
    runtime = runtime or NodusRuntime(timeout_ms=None)
    result = runtime.run_source(source)
    if not result.get("ok"):
        raise AssertionError(str((result.get("error") or {}).get("message") or result))
    return (result.get("stdout") or "").strip()


# closes: #952
class AReturnDoesNotShiftTheCallersOperands(unittest.TestCase):
    def test_return_from_inside_a_for_loop(self):
        out = _run(_FIND + 'fn c(p, q) {\n    return [p, find([1i, 2i, 3i]), q]\n}\nprint(c("p", "q"))\n')
        self.assertEqual(out, '["p", 2, "q"]')

    def test_the_same_through_a_closure(self):
        # A function value takes a different call path from a named function.
        source = (
            "let finder = fn(xs) {\n"
            "    for x in xs {\n"
            "        return x\n"
            "    }\n"
            "}\n"
            'print(["p", finder([7i]), "q"])\n'
        )
        self.assertEqual(_run(source), '["p", 7, "q"]')

    def test_return_from_nested_loops(self):
        source = (
            "fn pair(xs) {\n"
            "    for a in xs {\n"
            "        for b in xs {\n"
            "            return [a, b]\n"
            "        }\n"
            "    }\n"
            "}\n"
            'print(["p", pair([1i]), "q"])\n'
        )
        self.assertEqual(_run(source), '["p", [1, 1], "q"]')

    def test_return_from_a_match_arm_used_as_an_operand(self):
        source = (
            "fn m(x) {\n"
            "    let y = 1i + match x {\n"
            "        1i => {\n"
            "            return 5i\n"
            "        },\n"
            "        _ => 0i,\n"
            "    }\n"
            "    return y\n"
            "}\n"
            'print(["p", m(1i), "q"])\n'
        )
        self.assertEqual(_run(source), '["p", 5, "q"]')

    def test_return_through_finally_from_inside_a_loop(self):
        # The deferred return, completed at FINALLY_END, is the second path.
        source = (
            "fn f(xs) {\n"
            "    for x in xs {\n"
            "        try {\n"
            "            return x\n"
            "        } finally {\n"
            "            let cleanup = 1i\n"
            "        }\n"
            "    }\n"
            "}\n"
            'print(["p", f([3i]), "q"])\n'
        )
        self.assertEqual(_run(source), '["p", 3, "q"]')

    def test_repeated_calls_do_not_grow_the_stack(self):
        # As a statement the leak changed no visible value, but every call left
        # an iterator behind. Read the depth from the VM itself.
        runtime = NodusRuntime(timeout_ms=None)
        runtime.register_function("depth", lambda: len(runtime.active_vm().stack), arity=0)
        source = (
            _FIND
            + "let before = depth()\n"
            + "let i = 0i\n"
            + "while (i < 100i) {\n"
            + "    find([1i, 2i])\n"
            + "    i = i + 1i\n"
            + "}\n"
            + "print(depth() - before)\n"
        )
        self.assertEqual(_run(source, runtime), "0")


# closes: #952
class InsideACoroutineModuleCallsShareTheStack(unittest.TestCase):
    """In a coroutine, a module function runs on the caller's VM (#105).

    Its frame is built by a different site, and with a shared stack the leak
    reached the caller there too. This is also where the deferred-return copy
    lost the module context.
    """

    def _run_with_module(self, main_source: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "m.nd"), "w", encoding="utf-8") as handle:
                handle.write(_MODULE)
            cwd = os.getcwd()
            os.chdir(directory)
            try:
                result = NodusRuntime(timeout_ms=None).run_source(main_source, filename="main.nd")
            finally:
                os.chdir(cwd)
        if not result.get("ok"):
            raise AssertionError(str((result.get("error") or {}).get("message") or result))
        return (result.get("stdout") or "").strip()

    def test_a_module_function_returning_from_a_loop(self):
        out = self._run_with_module(
            'import "./m.nd" as m\n'
            "spawn(fn() {\n"
            '    print(["p", m.first_even([1i, 3i, 4i]), "q"])\n'
            "})\n"
            "run_loop()\n"
        )
        self.assertEqual(out, '["p", 4, "q"]')

    def test_a_module_function_returning_through_finally_restores_the_caller(self):
        # Before the fix the caller resumed inside the module's bytecode and
        # failed with an error reported against m.nd.
        out = self._run_with_module(
            'import "./m.nd" as m\n'
            'let secret = "main"\n'
            "spawn(fn() {\n"
            "    let r = m.guarded()\n"
            "    print(r)\n"
            "    print(secret)\n"
            "})\n"
            "run_loop()\n"
        )
        self.assertEqual(out.splitlines(), ["module", "main"])


class EveryFrameRecordsItsBase(unittest.TestCase):
    """Asserted on the source: a new Frame site that omits the base leaks again."""

    def test_every_frame_construction_passes_stack_base(self):
        missing = []
        for root, _dirs, files in os.walk(os.path.join(_REPO, "src")):
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                with open(path, "r", encoding="utf-8-sig") as handle:
                    tree = ast.parse(handle.read())
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id == "Frame"
                            and "stack_base" not in {k.arg for k in node.keywords}):
                        missing.append(f"{os.path.relpath(path, _REPO)}:{node.lineno}")
        self.assertEqual(missing, [])

    def test_there_is_one_place_that_completes_a_return(self):
        with open(os.path.join(_REPO, "src/nodus/vm/vm.py"), "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertEqual(source.count("self.ip = frame.return_ip"), 1,
                         "a second copy of the return logic is how the two drifted")

    def test_a_continuation_carries_the_base(self):
        with open(os.path.join(_REPO, "src/nodus/runtime/continuation.py"), "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn('"stack_base": frame.stack_base', source)


if __name__ == "__main__":
    unittest.main()
