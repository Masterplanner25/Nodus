"""Compile-to-Python (#173, phase 1): a compiled function is indistinguishable
from the interpreter except in speed.

Every behavioural test runs a program twice, interpreted and with every eligible
function compiled on its first call (`NODUS_COMPILE_FUNCTIONS=always`), and
requires the same result:
- stdout;
- the error's kind, message, line and stack;
- `instructions_executed`;
- the call and return counts the `vm_call` / `vm_return` events come from.

The design is `docs/design/throughput/01-compile-to-python.md`. CI also runs
the whole suite in compile-always mode, which is where most of the coverage
comes from; these tests are the cases that mode would not reach on purpose.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nodus.runtime.capability import BUILTIN_CAPABILITIES, NO_AUTHORITY_BUILTINS  # noqa: E402
from nodus.tooling.runner import run_source  # noqa: E402
from nodus.vm import pycompile  # noqa: E402


def run(src: str, *, compiled: bool, max_steps=None, depth_cap=None):
    env = {"NODUS_COMPILE_FUNCTIONS": "always" if compiled else ""}
    with mock.patch.dict(os.environ, env):
        if depth_cap is not None and compiled:
            with mock.patch.object(pycompile, "DEFAULT_DEPTH_CAP", depth_cap):
                result, vm = run_source(src, filename=None, max_steps=max_steps, timeout_ms=None)
        else:
            result, vm = run_source(src, filename=None, max_steps=max_steps, timeout_ms=None)
    error = result.get("error") or {}
    return {
        "ok": result.get("ok"),
        "stdout": result.get("stdout"),
        "kind": error.get("type") or error.get("kind"),
        "message": error.get("message"),
        "line": error.get("line"),
        "stack": (result.get("errors") or [{}])[0].get("stack"),
        "instructions": vm.instructions_executed if vm is not None else None,
        "calls": getattr(vm, "function_calls", None),
        "returns": getattr(vm, "returns", None),
    }, vm


def compiled_count(vm) -> int:
    state = vm._pycompile
    return state.compiled_count if state is not None else 0


class BothWays(unittest.TestCase):
    def assert_same(self, src, **kwargs):
        plain, _ = run(src, compiled=False, **kwargs)
        fast, vm = run(src, compiled=True, **kwargs)
        self.assertEqual(fast, plain)
        return fast, vm


class Programs(BothWays):
    CASES = {
        "arithmetic and comparison": (
            "fn f(a, b) {\n"
            "    let s = a + b\n    let d = a - b\n    let m = a * b\n"
            "    let q = a / b\n    let r = a % b\n    let n = -a\n"
            "    return [s, d, m, q, r, n, a < b, a > b, a <= b, a >= b, a == b, a != b]\n"
            "}\n"
            "fn g(a, b) { return [a + b, a < b, a == b, a != b] }\n"
            "print(f(7i, 2i))\nprint(f(7.5, 2.0))\nprint(g(\"a\", \"b\"))\n"
        ),
        "records, maps, lists and indexing": (
            "fn f(n) {\n"
            "    let r = record { a: n, b: [n, n + 1i] }\n"
            "    let m = {\"k\": n}\n"
            "    r.a = r.a + 1i\n"
            "    m[\"k\"] = m[\"k\"] * 2i\n"
            "    let xs = r.b\n    xs[0i] = 99i\n"
            "    return [r.a, m[\"k\"], xs, len(xs), has_key(m, \"k\")]\n"
            "}\n"
            "print(f(3i))\n"
        ),
        "control flow and iteration": (
            "fn f(xs) {\n"
            "    let total = 0i\n"
            "    for x in xs {\n"
            "        if (x == 3i) { continue }\n"
            "        if (x > 5i) { break }\n"
            "        total = total + x\n"
            "    }\n"
            "    let i = 0i\n"
            "    while (i < 3i && total != 0i) { i = i + 1i }\n"
            "    return [total, i, !(total == 0i), x_or(total)]\n"
            "}\n"
            "fn x_or(t) { return t == 1i || t == 7i }\n"
            "print(f([1i, 2i, 3i, 4i, 9i, 1i]))\n"
        ),
        "recursion and globals": (
            "let calls = 0i\n"
            "fn fib(n) {\n"
            "    calls = calls + 1i\n"
            "    if (n < 2i) { return n }\n"
            "    return fib(n - 1i) + fib(n - 2i)\n"
            "}\n"
            "print(fib(15i))\nprint(calls)\n"
        ),
        "string building and builtins": (
            "fn f(name) {\n"
            "    let s = \"hi \\(name)!\"\n"
            "    return [s, str_upper(s), substring(s, 0i, 2i), str(42i), type(s)]\n"
            "}\n"
            "print(f(\"there\"))\n"
        ),
    }

    def test_each_program(self):
        for name, src in self.CASES.items():
            with self.subTest(program=name):
                fast, vm = self.assert_same(src)
                self.assertTrue(fast["ok"], fast)
                self.assertGreater(compiled_count(vm), 0, "nothing compiled: the test proves nothing")


class Errors(BothWays):
    CASES = {
        "a missing field, three calls deep": (
            "fn a(r) { return b(r) }\nfn b(r) { return c(r) }\nfn c(r) { return r.missing }\n"
            "print(a(record { x: 1i }))\n"
        ),
        "a type error in arithmetic": "fn f(x) { return x + 1i }\nprint(f(\"s\"))\n",
        "an index out of range": "fn f(xs) { return xs[5i] }\nprint(f([1i]))\n",
        "a thrown string": "fn f() { throw \"bad\" }\nprint(f())\n",
        "a thrown record": "fn f() { throw record { code: 7i } }\nprint(f())\n",
        "a field read on a map": "fn f(m) { return m.k }\nprint(f({\"k\": 1i}))\n",
    }

    def test_each_error(self):
        for name, src in self.CASES.items():
            with self.subTest(error=name):
                fast, _ = self.assert_same(src)
                self.assertFalse(fast["ok"])

    def test_caught_by_an_interpreted_caller(self):
        # `catcher` has a try, so it stays interpreted; the throw is compiled.
        src = (
            "fn thrower(n) { if (n > 2i) { throw \"too big: \\(n)\" }\n return n }\n"
            "fn catcher(n) {\n"
            "    try { return thrower(n) } catch (e) { return \"caught \\(e.message)\" }\n"
            "}\n"
            "for n in [1i, 3i] { print(catcher(n)) }\n"
        )
        fast, vm = self.assert_same(src)
        self.assertIn("caught too big: 3", fast["stdout"])
        self.assertGreater(compiled_count(vm), 0)


class Limits(BothWays):
    def test_a_step_limit_inside_a_compiled_loop(self):
        src = "fn spin() {\n    let i = 0i\n    while (true) { i = i + 1i }\n}\nspin()\n"
        fast, _ = self.assert_same(src, max_steps=5000)
        self.assertEqual(fast["kind"], "sandbox")
        self.assertIn("step limit", fast["message"])

    def test_recursion_past_the_depth_cap(self):
        # With a cap of 5, most of these 300 frames run through the interpreter
        # from inside compiled code (`call_interpreted`), counted so the test
        # cannot pass without reaching it.
        src = "fn down(n) {\n    if (n == 0i) { return 0i }\n    return 1i + down(n - 1i)\n}\nprint(down(300i))\n"
        real = pycompile.call_interpreted
        seen = []

        def counting(*args, **kwargs):
            seen.append(1)
            return real(*args, **kwargs)

        with mock.patch.object(pycompile, "call_interpreted", counting):
            fast, _ = self.assert_same(src, depth_cap=5)
        self.assertEqual(fast["stdout"].strip(), "300")
        self.assertGreater(len(seen), 0, "the depth cap was never reached")

    def test_the_default_cap_follows_a_lowered_recursion_limit(self):
        limit = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(400)
            self.assertEqual(pycompile.CompileState().depth_cap, 80)
        finally:
            sys.setrecursionlimit(limit)

    def test_an_error_past_the_depth_cap(self):
        src = ("fn down(n) {\n    if (n == 0i) { return record { }.nope }\n"
               "    return down(n - 1i)\n}\nprint(down(40i))\n")
        plain, _ = run(src, compiled=False)
        fast, _ = run(src, compiled=True, depth_cap=5)
        for key in ("ok", "kind", "message", "line", "stack", "instructions"):
            self.assertEqual(fast[key], plain[key], key)


class WhenItCompiles(unittest.TestCase):
    def test_not_below_the_threshold(self):
        src = "fn f(x) { return x + 1i }\nprint(f(1i))\n"
        with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": "1"}):
            _, vm = run_source(src, filename=None, max_steps=None, timeout_ms=None)
        self.assertEqual(compiled_count(vm), 0)

    def test_a_function_with_a_loop_compiles_on_its_first_call(self):
        src = "fn total(n) {\n    let t = 0i\n    let i = 0i\n    while (i < n) { t = t + i\n i = i + 1i }\n    return t\n}\nprint(total(10i))\n"
        with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": "1"}):
            _, vm = run_source(src, filename=None, max_steps=None, timeout_ms=None)
        self.assertEqual(compiled_count(vm), 1)

    def test_at_the_threshold(self):
        src = ("fn f(x) { return x + 1i }\nlet i = 0i\n"
               f"while (i < {pycompile.DEFAULT_THRESHOLD + 5}i) {{ i = f(i) }}\nprint(i)\n")
        with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": "1"}):
            _, vm = run_source(src, filename=None, max_steps=None, timeout_ms=None)
        self.assertEqual(compiled_count(vm), 1)

    def test_never_under_the_profiler(self):
        from nodus.runtime.profiler import Profiler
        profiler = Profiler()
        profiler.start()
        src = "fn f(x) { return x + 1i }\nprint(f(1i))\n"
        with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": "always"}):
            _, vm = run_source(src, filename=None, max_steps=None, timeout_ms=None, profiler=profiler)
        profiler.stop()
        self.assertEqual(profiler.function_calls.get("f"), 1, "the call was not seen by the profiler")

    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": ""}):
            _, vm = run_source("print(1i)", filename=None, max_steps=None, timeout_ms=None)
        self.assertIsNone(vm._pycompile)

    def test_the_cli_and_runtime_switches(self):
        from nodus.runtime.embedding import NodusRuntime
        runtime = NodusRuntime(timeout_ms=None, compile_functions=True)
        result = runtime.run_source("print(1i)")
        self.assertTrue(result["ok"])
        self.assertIsNotNone(runtime.active_vm()._pycompile)


class WhatCompiledCodeMayCall(unittest.TestCase):
    def test_the_categories_exist(self):
        for category in pycompile.COMPILABLE_BUILTIN_CATEGORIES:
            self.assertIn(category, NO_AUTHORITY_BUILTINS)

    def test_no_builtin_that_can_suspend(self):
        suspending = {"sleep", "sleep_until", "recv", "wait", "run_loop", "spawn",
                      "__workflow_checkpoint", "workflow_wait", "retry_call", "run_workflow"}
        self.assertEqual(suspending & pycompile.COMPILABLE_BUILTINS, set())
        self.assertEqual(set(NO_AUTHORITY_BUILTINS["in-process concurrency"])
                         & pycompile.COMPILABLE_BUILTINS, set())

    def test_no_builtin_that_carries_a_capability(self):
        self.assertEqual(set(BUILTIN_CAPABILITIES) & pycompile.COMPILABLE_BUILTINS, set())

    def test_a_function_calling_sleep_stays_interpreted(self):
        from nodus.runtime.module_loader import ModuleLoader
        from nodus.vm.vm import VM
        src = "fn nap() { sleep(1i)\n return 1i }\nfn pure(x) { return x + 1i }\n"
        code, functions, _ = ModuleLoader(project_root=None).compile_only(src, module_name="m.nd")
        vm = VM(code["instructions"], functions, code_locs=[], source_path=None)
        reasons = pycompile.eligible_functions(code["instructions"], functions, vm.builtins)
        self.assertIsNotNone(reasons["nap"])
        self.assertIsNone(reasons["pure"])


if __name__ == "__main__":
    unittest.main()
