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

import ast
import os
import pathlib
import sys
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[1]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nodus.runtime.capability import (  # noqa: E402
    BUILTIN_CAPABILITIES,
    MAY_SUSPEND_BUILTINS,
    NO_AUTHORITY_BUILTINS,
)
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


class Closures(BothWays):
    """Phase 3 (#173): functions that capture, closures themselves, and calls
    through values."""

    CASES = {
        "closures made in a loop capture each iteration": (
            "fn make() {\n"
            "    let fns = []\n"
            "    for i in [1i, 2i, 3i] {\n"
            "        let k = i * 10i\n"
            "        push(fns, fn() { return i + k })\n"
            "    }\n"
            "    return fns\n"
            "}\n"
            "fn run_all(fns) {\n    let out = []\n    for f in fns { push(out, f()) }\n    return out\n}\n"
            "print(run_all(make()))\n"
        ),
        "a counter mutates what it captured": (
            "fn counter() {\n    let n = 0i\n    return fn() { n = n + 1i\n return n }\n}\n"
            "fn drive(c, times) {\n    let last = 0i\n    let i = 0i\n"
            "    while (i < times) { last = c()\n i = i + 1i }\n    return last\n}\n"
            "let c = counter()\nprint(drive(c, 5i))\nprint(c())\n"
        ),
        "two levels of capture": (
            "fn outer(a) {\n"
            "    let b = a * 2i\n"
            "    return fn(x) { return fn(y) { return a + b + x + y } }\n"
            "}\n"
            "fn use(n) { return outer(n)(1i)(2i) }\n"
            "print(use(1i))\nprint(use(5i))\n"
        ),
        "higher-order functions and named functions as values": (
            "fn double(x) { return x * 2i }\n"
            "fn apply_all(f, xs) {\n    let out = []\n    for x in xs { push(out, f(x)) }\n    return out\n}\n"
            "fn main() {\n"
            "    let offset = 100i\n"
            "    print(apply_all(double, [1i, 2i, 3i]))\n"
            "    print(apply_all(fn(x) { return x + offset }, [1i, 2i]))\n"
            "}\nmain()\n"
        ),
        "the maker reads and writes what a closure changed": (
            # After capture, `n` is a Cell in the maker's slot: its own reads
            # must unwrap it and its own writes must go into it.
            "fn f() {\n"
            "    let n = 1i\n"
            "    let add = fn() { n = n + 10i }\n"
            "    add()\n"
            "    let seen = n * 2i\n"
            "    n = n + 100i\n"
            "    add()\n"
            "    return [seen, n]\n"
            "}\nprint(f())\n"
        ),
        "a recursive local closure": (
            "fn f(n) {\n"
            "    let fact = fn(m) { if (m <= 1i) { return 1i }\n return m * fact(m - 1i) }\n"
            "    return fact(n)\n"
            "}\nprint(f(10i))\n"
        ),
    }

    def test_each_case(self):
        for name, src in self.CASES.items():
            with self.subTest(case=name):
                fast, vm = self.assert_same(src)
                self.assertTrue(fast["ok"], fast)
                compiled = [n for chunk in vm._pycompile._chunks.values() for n in chunk.compiled]
                self.assertTrue(any(n.startswith("__anon") for n in compiled),
                                f"no closure body compiled: {compiled}")

    def test_a_closure_with_try_stays_interpreted_and_behaves_the_same(self):
        src = (
            "fn risky(x) {\n    if (x == 2i) { throw \"two\" }\n    return x\n}\n"
            "fn each(f, xs) {\n    let out = []\n    for x in xs { push(out, f(x)) }\n    return out\n}\n"
            "fn main() {\n"
            "    print(each(fn(x) { try { return risky(x) } catch (e) { return \"caught \\(e.message)\" } }, [1i, 2i, 3i]))\n"
            "    try { print(each(fn(x) { return risky(x) }, [1i, 2i])) } catch (e) { print(\"outer \\(e.message)\") }\n"
            "}\nmain()\n"
        )
        fast, _ = self.assert_same(src)
        self.assertIn("caught two", fast["stdout"])
        self.assertIn("outer two", fast["stdout"])

    def test_an_error_inside_a_compiled_closure(self):
        src = ("fn make() { return fn(r) { return r.missing } }\n"
               "fn call_it(f) { return f(record { a: 1i }) }\nprint(call_it(make()))\n")
        fast, _ = self.assert_same(src)
        self.assertEqual(fast["kind"], "runtime")

    def test_inside_a_coroutine(self):
        # Dynamic functions stay interpreted where something could suspend.
        src = (
            "fn each(f, xs) {\n    let out = []\n    for x in xs { push(out, f(x)) }\n    return out\n}\n"
            "fn worker(ch) {\n    sleep(1i)\n    send(ch, each(fn(x) { return x * 3i }, [1i, 2i]))\n}\n"
            "let ch = channel()\nspawn(coroutine(fn() { worker(ch) }))\nrun_loop()\nprint(recv_now(ch))\n"
        ).replace("recv_now(ch)", "\"done\"")
        self.assert_same(src)


class FunctionBodies(unittest.TestCase):
    """A function's body is what it can reach, not an address range (phase 3)."""

    def test_a_function_that_makes_a_closure_is_eligible(self):
        # The closure's body sits inside the parent's code, behind a JUMP. An
        # address range cut the parent off at the closure and made its JUMP look
        # like control leaving the function.
        from nodus.runtime.module_loader import ModuleLoader
        from nodus.vm.vm import VM
        src = "fn make(n) {\n    let k = n * 2i\n    let f = fn(x) { return x + k }\n    return f(1i)\n}\n"
        code, functions, _ = ModuleLoader(project_root=None).compile_only(src, module_name="m.nd")
        vm = VM(code["instructions"], functions, code_locs=[], source_path=None)
        reasons = pycompile.eligible_functions(code["instructions"], functions, vm.builtins)
        self.assertEqual(reasons, {name: None for name in functions})


class DynamicTaint(unittest.TestCase):
    def test_a_call_through_a_value_taints_its_callers(self):
        from nodus.runtime.module_loader import ModuleLoader
        from nodus.vm.vm import VM
        src = ("fn call(f) { return f(1i) }\nfn above(f) { return call(f) }\n"
               "fn pure(x) { return x + 1i }\n")
        code, functions, _ = ModuleLoader(project_root=None).compile_only(src, module_name="m.nd")
        vm = VM(code["instructions"], functions, code_locs=[], source_path=None)
        reasons, dynamic = pycompile.analyze(code["instructions"], functions, vm.builtins)
        self.assertIsNone(reasons["call"])
        self.assertEqual(dynamic, {"call", "above"})


MODULE = (
    "fn total(xs) {\n    let t = 0i\n    for x in xs { t = t + double(x) }\n    return t\n}\n"
    "fn double(x) { return x * 2i }\n"
    "fn broken(r) { return r.missing }\n"
    "fn each(f, xs) {\n    let out = []\n    for x in xs { push(out, f(x)) }\n    return out\n}\n"
)
# Two named functions, then a closure: its generated name, `__anon_1__fn2`, is
# the one the first closure of a main program shaped the same way gets.
ADDER = "fn ident(x) { return x }\nfn adder(n) { return fn(x) { return x + n } }\n"


class ImportedModules(unittest.TestCase):
    """The switches an embedder and a CLI user actually have reach imported code.

    A call into a module runs on a child VM. Before the fix that VM got
    compilation only from `NODUS_COMPILE_FUNCTIONS`, so the runtime flag and
    `--compile` compiled the entry chunk and nothing it imported; and the
    function a module call enters runs through `run_closure`, which skipped the
    compile hook even with the variable set. These run with the variable unset.
    """

    def setUp(self):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        (self.dir / "m.nd").write_text(MODULE, encoding="utf-8")
        (self.dir / "adder.nd").write_text(ADDER, encoding="utf-8")

    def run_program(self, body: str, *, compiled: bool):
        main = self.dir / "main.nd"
        src = 'import "./m.nd" as m\n' + body
        main.write_text(src, encoding="utf-8")
        with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": ""}):
            result, vm = run_source(src, filename=str(main), max_steps=None, timeout_ms=None,
                                    compile_functions=compiled)
        error = result.get("error") or {}
        names = set()
        if vm is not None and vm._pycompile is not None:
            names = {n for chunk in vm._pycompile._chunks.values() for n in chunk.compiled}
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
        }, names

    def assert_same(self, body: str):
        plain, _ = self.run_program(body, compiled=False)
        fast, names = self.run_program(body, compiled=True)
        self.assertEqual(fast, plain)
        return fast, names

    def test_a_module_function_with_a_loop_compiles(self):
        fast, names = self.assert_same("print(m.total([1i, 2i, 3i]))\nprint(m.total([10i]))\n")
        self.assertEqual(fast["stdout"], "12\n20\n")
        # `total` is what the module call enters; `double` is what it calls.
        self.assertIn("total", names)
        self.assertIn("double", names)

    def test_an_error_in_a_compiled_module_entry(self):
        fast, _ = self.assert_same("fn main() { print(m.broken(record { a: 1i })) }\nmain()\n")
        self.assertFalse(fast["ok"])
        self.assertIn("missing", fast["message"])

    def test_a_module_function_calling_back_into_the_caller(self):
        fast, _ = self.assert_same(
            "fn main() {\n    let k = 5i\n    print(m.each(fn(x) { return x + k }, [1i, 2i]))\n}\nmain()\n")
        self.assertEqual(fast["stdout"], "[6, 7]\n")

    def test_another_modules_closure_with_a_compiled_name_of_ours(self):
        # A closure from `adder.nd` carries the same generated name as `mine`,
        # which is compiled in this chunk by then. A call through it from
        # compiled code must run the module's function, not ours by name.
        body = ('import "./adder.nd" as a\n'
                "fn apply_all(f, xs) {\n    let out = []\n    for x in xs { push(out, f(x)) }\n    return out\n}\n"
                "fn main() {\n    let mine = fn(x) { return x * 100i }\n"
                "    print(apply_all(mine, [1i, 2i]))\n    print(apply_all(a.adder(5i), [1i, 2i]))\n}\nmain()\n")
        fast, names = self.assert_same(body)
        self.assertEqual(fast["stdout"], "[100, 200]\n[6, 7]\n")
        self.assertIn("__anon_1__fn2", names, "the names no longer collide: the test proves nothing")

    def test_the_child_vm_shares_the_callers_state(self):
        from nodus.runtime.capability import derive_child_vm
        from nodus.vm.vm import VM
        parent = VM([("HALT",)], {}, code_locs=[], source_path=None)
        state = pycompile.enable(parent)
        child = VM([("HALT",)], {}, code_locs=[], source_path=None)
        derive_child_vm(child, parent)
        self.assertIs(child._pycompile, state)

    def test_two_modules_with_the_same_function_name_count_separately(self):
        state = pycompile.CompileState(threshold=2)

        class FakeVM:
            def __init__(self, code, functions):
                self.code, self.functions, self.builtins = code, functions, {}
                self.task_step_budget = None
                self.current_coroutine = None

            def _instrumented(self):
                return False

        from nodus.runtime.module_loader import ModuleLoader
        a_code, a_fns, _ = ModuleLoader(project_root=None).compile_only(
            "fn peek(x) { return x + 1i }\n", module_name="a.nd")
        b_code, b_fns, _ = ModuleLoader(project_root=None).compile_only(
            "fn peek(x) { return x + 2i }\n", module_name="b.nd")
        a = FakeVM(a_code["instructions"], a_fns)
        b = FakeVM(b_code["instructions"], b_fns)
        self.assertIsNone(state.target(a, "peek", a_fns["peek"]))
        # One call in another module must not push a's `peek` over the threshold.
        self.assertIsNone(state.target(b, "peek", b_fns["peek"]))


class InlineCalls(BothWays):
    """Calls from compiled code are generated inline: to an eligible user
    function through a frame maker per call site, and to a builtin without
    authority straight to its function. Each case is something the inline path
    must still do exactly as the interpreter does."""

    def test_a_builtins_error_record_gets_the_callers_location(self):
        # `finish_builtin_value`'s job, done inline: an error record from
        # `json_parse` carries the path, line and stack of the call.
        fast, _ = self.assert_same(
            "fn parse(s) {\n    return json_parse(s)\n}\n"
            "fn main() {\n    let r = parse(\"{bad\")\n    print(r.line)\n    print(r.stack)\n}\nmain()\n")
        self.assertIn("2", fast["stdout"])

    def test_a_builtins_arity_error(self):
        fast, _ = self.assert_same("fn f(xs) { return len(xs, 1i) }\nprint(f([1i]))\n")
        self.assertIn("expected 1 args, got 2", fast["message"])

    def test_the_frame_limit_through_an_inlined_call(self):
        # 40 frames is far below the depth cap (200), so the overflow happens
        # in a frame made by `make_call_frame`, not in the interpreter.
        from nodus.runtime.embedding import NodusRuntime
        src = "fn down(n) {\n    if (n == 0i) { return 0i }\n    return down(n - 1i) + 1i\n}\nprint(down(100i))\n"
        out = []
        for compiled in (False, True):
            with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": "always" if compiled else ""}):
                rt = NodusRuntime(max_frames=40, max_steps=None, timeout_ms=None)
                result = rt.run_source(src)
            error = result.get("error") or {}
            out.append((result.get("ok"), error.get("message"), error.get("line"),
                        rt.get_execution_stats()["instructions_executed"]))
        self.assertEqual(out[0][:2], (False, "Call stack overflow"))
        self.assertEqual(out[1], out[0])

    def test_call_events_when_a_host_listens(self):
        # With nothing listening the inline path only counts; with a listener
        # it must emit the same events, in the same order, with the same names.
        src = ("fn inc(x) { return x + 1i }\n"
               "fn main() {\n    let t = 0i\n    let i = 0i\n"
               "    while (i < 3i) { t = inc(t)\n i = i + 1i }\n    print(len([t]))\n}\nmain()\n")
        seen = []
        for compiled in (False, True):
            env = {"NODUS_COMPILE_FUNCTIONS": "always" if compiled else "",
                   "NODUS_TRACE_VM_EVENTS": "1"}
            with mock.patch.dict(os.environ, env):
                result, vm = run_source(src, filename=None, max_steps=None, timeout_ms=None)
            self.assertTrue(result["ok"], result)
            seen.append([(e.type, e.name) for e in vm.event_bus.events()
                         if e.type in ("vm_call", "vm_return")])
            if compiled:
                self.assertGreater(compiled_count(vm), 0)
        self.assertIn(("vm_call", "inc"), seen[0])
        self.assertIn(("vm_call", "len"), seen[0])
        self.assertEqual(seen[1], seen[0])

    def test_the_frame_maker_builds_the_frame_build_call_frame_builds(self):
        import dataclasses

        from nodus.runtime.module_loader import ModuleLoader
        from nodus.vm.vm import VM
        src = "fn g(a, b) {\n    let c = a + b\n    return c\n}\nfn f(x) {\n    return g(x, 2i)\n}\nprint(f(1i))\n"
        code, functions, locs = ModuleLoader(project_root=None).compile_only(src, module_name="m.nd")
        # Real locations: with none, every site looks alike and a maker that
        # read the wrong instruction's location would pass.
        self.assertGreater(len({loc for loc in locs if loc[1] is not None}), 3)
        vm = VM(code["instructions"], functions, code_locs=locs, source_path="m.nd")
        sites = [i for i, ins in enumerate(vm.code) if ins[0] == "CALL" and ins[1] == "g"]
        self.assertTrue(sites)
        for ip in sites:
            vm.ip = ip
            expected = vm.build_call_frame("g", functions["g"], 0)
            made = vm.call_frame_maker("g", functions["g"], ip)(len(vm.stack), {})
            self.assertEqual(
                {f.name: getattr(made, f.name) for f in dataclasses.fields(made)},
                {f.name: getattr(expected, f.name) for f in dataclasses.fields(expected)})


class InlineValueCalls(BothWays):
    """A call through a value (`CALL_VALUE`) from compiled code to a compiled
    closure of the same chunk is generated inline too. Its frame still comes
    from `VM.build_closure_frame`, so the arity check, the #394 step-entry
    guard and the frame limit have one copy. Each case runs the inline path:
    the helper it replaces is counted, so a case that never left it fails."""

    def _run_counting_the_helper(self, src, **kwargs):
        real = pycompile.CompileState._value_call
        helper_calls = []

        def counting(state, vm, chunk):
            call = real(state, vm, chunk)

            def wrapped(vm, callee, args):
                helper_calls.append(1)
                return call(vm, callee, args)
            return wrapped
        with mock.patch.object(pycompile.CompileState, "_value_call", counting):
            fast, vm = self.assert_same(src, **kwargs)
        return fast, vm, len(helper_calls)

    def test_most_calls_skip_the_helper(self):
        # The helper still takes each closure's first call, which compiles it.
        src = ("fn each(f, xs) {\n    let out = []\n    for x in xs { push(out, f(x)) }\n    return out\n}\n"
               "fn main() {\n    let k = 3i\n    print(each(fn(x) { return x * k }, range(0i, 50i)))\n}\nmain()\n")
        fast, vm, helper = self._run_counting_the_helper(src)
        self.assertTrue(fast["ok"], fast)
        self.assertLessEqual(helper, 1)

    def test_a_step_body_through_a_value_is_refused(self):
        # #394 door 1 from compiled code. A step body is never compiled (it is
        # ineligible), so the call takes the helper and the VM's own handler;
        # the inline path's own frame goes through `build_closure_frame`,
        # pinned by the source test below. Both walls are checked here.
        src = ("let log = {\"s\": \"\"}\n"
               "workflow build {\n"
               "    step lint { log[\"s\"] = log[\"s\"] + \"lint;\" return \"linted\" }\n"
               "    step test after lint { log[\"s\"] = log[\"s\"] + \"test;\" return \"tested\" }\n"
               "}\n"
               "fn call_it(f, x) { return f(x) }\n"
               "fn main() {\n    run_workflow(build)\n    print(call_it(build[\"steps\"][1][\"fn\"], nil))\n}\nmain()\n")
        fast, vm, _ = self._run_counting_the_helper(src)
        self.assertFalse(fast["ok"])
        self.assertIn("cannot be called directly", fast["message"])
        self.assertIn("call_it", {n for chunk in vm._pycompile._chunks.values() for n in chunk.compiled})
        steps = [n for n, fn in vm.functions.items() if fn.step_owner]
        self.assertTrue(steps)
        for chunk in vm._pycompile._chunks.values():
            for name in steps:
                self.assertEqual(chunk.reasons.get(name), "a workflow step body")
                self.assertNotIn(name, chunk.compiled)

    def test_an_arity_mismatch_through_a_value(self):
        src = ("fn call_one(f) { return f(1i) }\nfn call_two(f) { return f(1i, 2i) }\n"
               "fn main() {\n    let g = fn(x) { return x }\n    print(call_one(g))\n    print(call_two(g))\n}\nmain()\n")
        fast, _, helper = self._run_counting_the_helper(src)
        self.assertIn("expected 1 args, got 2", fast["message"])
        self.assertLessEqual(helper, 1)

    def test_the_frame_limit_through_a_value(self):
        from nodus.runtime.embedding import NodusRuntime
        src = ("fn main() {\n"
               "    let down = fn(n) { if (n == 0i) { return 0i }\n return down(n - 1i) + 1i }\n"
               "    print(down(100i))\n}\nmain()\n")
        out = []
        for compiled in (False, True):
            with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": "always" if compiled else ""}):
                rt = NodusRuntime(max_frames=40, max_steps=None, timeout_ms=None)
                result = rt.run_source(src)
            error = result.get("error") or {}
            out.append((result.get("ok"), error.get("message"), error.get("line"),
                        rt.get_execution_stats()["instructions_executed"]))
        self.assertEqual(out[0][:2], (False, "Call stack overflow"))
        self.assertEqual(out[1], out[0])

    def test_call_events_when_a_host_listens(self):
        src = ("fn each(f, xs) {\n    let out = []\n    for x in xs { push(out, f(x)) }\n    return out\n}\n"
               "fn main() {\n    let double = fn(x) { return x * 2i }\n    print(each(double, [1i, 2i, 3i]))\n}\nmain()\n")
        seen = []
        for compiled in (False, True):
            env = {"NODUS_COMPILE_FUNCTIONS": "always" if compiled else "",
                   "NODUS_TRACE_VM_EVENTS": "1"}
            with mock.patch.dict(os.environ, env):
                result, vm = run_source(src, filename=None, max_steps=None, timeout_ms=None)
            self.assertTrue(result["ok"], result)
            seen.append([(e.type, e.name, (e.data or {}).get("call_type")) for e in vm.event_bus.events()
                         if e.type in ("vm_call", "vm_return")])
        self.assertTrue(any(t == "call_value" for _, _, t in seen[0]))
        self.assertEqual(seen[1], seen[0])

    def test_an_error_inside_keeps_the_interpreters_stack(self):
        # It fails on the third call, so a frame an earlier inline call left
        # behind would show in the stack.
        src = ("fn each(f, xs) {\n    let out = []\n    for x in xs { push(out, f(x)) }\n    return out\n}\n"
               "fn main() {\n    let pick = fn(r) { return r.b }\n"
               "    print(each(pick, [record { b: 1i }, record { b: 2i }, record { a: 3i }]))\n}\nmain()\n")
        fast, _, helper = self._run_counting_the_helper(src)
        self.assertFalse(fast["ok"])
        self.assertTrue(fast["stack"])
        self.assertLessEqual(helper, 1)

    def test_the_inline_path_builds_its_frame_through_build_closure_frame(self):
        # The source half of the #394 guarantee; the step-body case above is
        # the behavioural half.
        out = []
        pycompile._emit_value_call(out, "", 2, 1)
        body = "\n".join(out)
        self.assertIn("vm.build_closure_frame(cv, 1, args_on_stack=False)", body)
        self.assertNotIn("Frame(", body)


class MethodCalls(BothWays):
    """`CALL_METHOD` compiles (#173): the VM's own handler runs each call,
    synchronously, and a function that reaches one is dynamic, so it runs
    compiled only outside a coroutine. Every case requires the function holding
    the method call to have compiled, or it proves nothing."""

    CASES = {
        "a stdlib module function": (
            'import "std:strings" as s\n'
            "fn words(line) { return s.split(line, \" \") }\n"
            "fn count(lines) {\n    let n = 0i\n    for l in lines { n = n + len(words(l)) }\n    return n\n}\n"
            "print(count([\"a b c\", \"d e\"]))\n", "count", True),
        "a builtin method on a returned record": (
            'import "std:hash" as hash\n'
            "fn digest(x) { return hash.sha256(x).to_hex() }\nprint(digest(\"abc\"))\n", "digest", True),
        "a record holding a closure": (
            # A closure method is passed the record as its first argument.
            "fn make() {\n    let n = 0i\n    return record { inc: fn(self) { n = n + 1i\n return n } }\n}\n"
            "fn drive(c) {\n    c.inc()\n    c.inc()\n    return c.inc()\n}\nprint(drive(make()))\n", "drive", True),
        "a closure method reads the record through `self`": (
            "fn make() { return record { v: 5i, get: fn(self) { return self.v } } }\n"
            "fn read(r) { return r.get() }\nprint(read(make()))\n", "read", True),
        "a call nested in an expression and a loop": (
            'import "std:strings" as s\n'
            "fn shout(xs) {\n    let out = []\n    for x in xs { push(out, s.upper(x) + \"!\") }\n    return out\n}\n"
            "print(shout([\"a\", \"b\"]))\n", "shout", True),
        "a missing module export": (
            'import "std:strings" as s\nfn f(x) { return s.nope(x) }\nprint(f(\"a\"))\n', "f", False),
        "a missing record field": (
            "fn f(r) { return r.nope() }\nprint(f(record { a: 1i }))\n", "f", False),
        "a method on something that is not a record": (
            "fn f(x) { return x.len() }\nprint(f([1i]))\n", "f", False),
        "a closure method without a `self` parameter": (
            "fn make() { return record { get: fn() { return 1i } } }\n"
            "fn f(r) { return r.get() }\nprint(f(make()))\n", "f", False),
        "an error inside the method": (
            "fn make() { return record { bad: fn(self) { return record { }.missing } } }\n"
            "fn f(r) { return r.bad() }\nprint(f(make()))\n", "f", False),
    }

    def test_each_case(self):
        for name, (src, holder, ok) in self.CASES.items():
            with self.subTest(case=name):
                fast, vm = self.assert_same(src)
                self.assertEqual(fast["ok"], ok, fast)
                compiled = {n for chunk in vm._pycompile._chunks.values() for n in chunk.compiled}
                self.assertIn(holder, compiled, f"{holder} did not compile, so the case proves nothing")

    def test_a_try_around_a_compiled_caller_catches_a_method_error(self):
        src = ("fn make() { return record { bad: fn(self) { throw \"inner\" } } }\n"
               "fn f(r) { return r.bad() }\n"
               "fn main() {\n    try { print(f(make())) } catch (e) { print(\"caught \\(e.message)\") }\n}\nmain()\n")
        fast, vm = self.assert_same(src)
        self.assertIn("caught inner", fast["stdout"])

    def test_inside_a_coroutine_it_stays_interpreted(self):
        src = ('import "std:strings" as s\n'
               "fn up(x) { return s.upper(x) }\n"
               "print(up(\"z\"))\n"  # compiled here, outside a coroutine
               "let ch = channel()\n"
               "spawn(coroutine(fn() {\n    sleep(1i)\n    send(ch, up(\"a\"))\n}))\n"
               "spawn(coroutine(fn() { print(recv(ch)) }))\nrun_loop()\n")
        real = pycompile.CompileState.allowed
        refused = []

        def watching(state, vm, chunk, name):
            ok = real(state, vm, chunk, name)
            if name == "up" and not ok and vm.current_coroutine is not None:
                refused.append(name)
            return ok
        with mock.patch.object(pycompile.CompileState, "allowed", watching):
            fast, vm = self.assert_same(src)
        self.assertEqual(fast["stdout"], "Z\nA\n")
        self.assertIn("up", {n for chunk in vm._pycompile._chunks.values() for n in chunk.compiled})
        self.assertTrue(refused, "`up` was never refused inside the coroutine")

    def test_a_method_call_makes_its_callers_dynamic(self):
        from nodus.runtime.module_loader import ModuleLoader
        src = ("fn leaf(r) { return r.get() }\nfn mid(r) { return leaf(r) }\n"
               "fn plain(x) { return x + 1i }\n")
        code, functions, _ = ModuleLoader(project_root=None).compile_only(src, module_name="m.nd")
        reasons, dynamic = pycompile.analyze(code["instructions"], functions, {})
        self.assertIsNone(reasons["leaf"])
        self.assertEqual({"leaf", "mid"}, dynamic & {"leaf", "mid", "plain"})


class Arithmetic(BothWays):
    """`*`, `/`, `%` and unary minus are generated inline (#173): `*` and minus
    as the handler does them, `/` and `%` only for two ints with a non-zero
    divisor, the handler doing the rest. Each case compares the two ways, and
    each runs inside a compiled function."""

    VALUES = ["7i", "-7i", "2i", "-2i", "0i", "7.5", "-2.0", "0.0", "true", "false",
              "\"ab\"", "[1i]", "nil"]
    OPS = ["*", "/", "%"]

    def test_every_pair_of_operands(self):
        # 13 x 13 x 3 = 507 cases, each its own program, since an error ends
        # one. The interpreter decides what each should be; nothing is assumed.
        for op in self.OPS:
            for a in self.VALUES:
                for b in self.VALUES:
                    with self.subTest(expr=f"{a} {op} {b}"):
                        fast, vm = self.assert_same(
                            f"fn f(a, b) {{ return a {op} b }}\nprint(f({a}, {b}))\n")
                        self.assertEqual(compiled_count(vm), 1)

    def test_negation(self):
        for v in self.VALUES:
            with self.subTest(value=v):
                fast, vm = self.assert_same(f"fn f(a) {{ return -a }}\nprint(f({v}))\n")
                self.assertEqual(compiled_count(vm), 1)

    def test_large_ints_and_mixed_chains(self):
        fast, _ = self.assert_same(
            "fn f(n) {\n    let x = n * n * n\n    return [x / 7i, x % 7i, -x % 5i, (x * 2.5) / 3i, -(-n)]\n}\n"
            "print(f(123456789i))\n")
        self.assertTrue(fast["ok"], fast)


class TheCodeCache(unittest.TestCase):
    SRC ="fn total(n) {\n    let t = 0i\n    for i in range(n) { t = t + i }\n    return t\n}\nprint(total(5i))\n"

    def test_a_second_vm_reuses_the_compiled_code(self):
        compiles = []
        real = compile

        def counting(*args, **kwargs):
            if str(args[1]).startswith("<nodus compiled"):
                compiles.append(args[1])
            return real(*args, **kwargs)

        pycompile._CODE_CACHE.clear()
        with mock.patch("builtins.compile", counting):
            first, _ = run(self.SRC, compiled=True)
            second, _ = run(self.SRC, compiled=True)
        self.assertEqual(first["stdout"], second["stdout"])
        self.assertEqual(len(compiles), 1, compiles)

    def test_different_bytecode_is_not_shared(self):
        pycompile._CODE_CACHE.clear()
        run(self.SRC, compiled=True)
        run(self.SRC.replace("t + i", "t + i + 1i"), compiled=True)
        self.assertEqual(len(pycompile._CODE_CACHE), 2)


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

    def test_capability_builtins_compile_only_if_they_cannot_suspend(self):
        # Phase 2 (#173): synchronous capability builtins are compilable; the
        # ones that can pause are not.
        capable = set(BUILTIN_CAPABILITIES)
        self.assertEqual(capable & pycompile.COMPILABLE_BUILTINS, capable - set(MAY_SUSPEND_BUILTINS))
        self.assertIn("http_get", pycompile.COMPILABLE_BUILTINS)
        self.assertNotIn("http_get_async", pycompile.COMPILABLE_BUILTINS)

    def test_a_function_calling_sleep_stays_interpreted(self):
        from nodus.runtime.module_loader import ModuleLoader
        from nodus.vm.vm import VM
        src = "fn nap() { sleep(1i)\n return 1i }\nfn pure(x) { return x + 1i }\n"
        code, functions, _ = ModuleLoader(project_root=None).compile_only(src, module_name="m.nd")
        vm = VM(code["instructions"], functions, code_locs=[], source_path=None)
        reasons = pycompile.eligible_functions(code["instructions"], functions, vm.builtins)
        self.assertIsNotNone(reasons["nap"])
        self.assertIsNone(reasons["pure"])


# --- which builtins can suspend: derived from the source ------------------------

def _request_class_names() -> set:
    """The classes `VM.call_builtin` treats as a pause, subclasses included."""
    from nodus.runtime.channel import ChannelRecvRequest
    from nodus.runtime.scheduler import CheckpointRequest, SleepRequest

    out, todo = set(), [SleepRequest, CheckpointRequest, ChannelRecvRequest]
    while todo:
        cls = todo.pop()
        if cls.__name__ not in out:
            out.add(cls.__name__)
            todo.extend(cls.__subclasses__())
    return out


def _call_name(node):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
    return None


def _returning_functions() -> set:
    """Names of functions in src/nodus whose `return` can hand back a suspend
    request: a new one, the result of a function that returns one, or a local
    bound to either. A fixed point, resolving calls by name, so a name shared by
    two functions counts if either returns one (conservative)."""
    markers = _request_class_names()
    functions = []
    for path in sorted((REPO / "src" / "nodus").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        functions.extend((n.name, n) for n in ast.walk(tree)
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))

    def own_nodes(fn):
        stack = list(ast.iter_child_nodes(fn))
        while stack:
            node = stack.pop()
            yield node
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                stack.extend(ast.iter_child_nodes(node))

    returners = set(markers)
    changed = True
    while changed:
        changed = False
        for name, fn in functions:
            if name in returners:
                continue
            bound = {t.id for n in own_nodes(fn) if isinstance(n, ast.Assign)
                     and _call_name(n.value) in returners
                     for t in n.targets if isinstance(t, ast.Name)}
            for node in own_nodes(fn):
                if not (isinstance(node, ast.Return) and node.value is not None):
                    continue
                values = ([node.value.body, node.value.orelse]
                          if isinstance(node.value, ast.IfExp) else [node.value])
                if any(_call_name(v) in returners or (isinstance(v, ast.Name) and v.id in bound)
                       for v in values):
                    returners.add(name)
                    changed = True
                    break
    return returners - markers


def _suspending_builtins() -> set:
    from nodus.vm.vm import VM
    vm = VM([], {}, code_locs=[], source_path=None)
    returners = _returning_functions()
    out = set()
    for name, info in vm.builtins.items():
        fn = getattr(info.fn, "__func__", info.fn)
        fname = getattr(fn, "__name__", "")
        if fname in returners or (fname == "<lambda>" and set(fn.__code__.co_names) & returners):
            out.add(name)
    return out


class WhichBuiltinsCanSuspend(unittest.TestCase):
    """`MAY_SUSPEND_BUILTINS` is declared; this derives the same set from the
    source, so a builtin that learns to suspend fails here until it is listed."""

    def test_the_analysis_finds_the_known_ones(self):
        found = _suspending_builtins()
        for name in ("sleep", "recv", "send", "wait", "__workflow_checkpoint",
                     "http_get_async", "subprocess_run_async", "agent_call_async"):
            self.assertIn(name, found)

    def test_it_flags_nothing_synchronous(self):
        found = _suspending_builtins()
        for name in ("len", "str", "read_file", "http_get", "subprocess_run", "agent_call", "env_get"):
            self.assertNotIn(name, found)

    def test_the_declared_set_is_exactly_what_can_suspend(self):
        self.assertEqual(_suspending_builtins(), set(MAY_SUSPEND_BUILTINS))

    def test_compiled_code_never_calls_one(self):
        self.assertEqual(set(MAY_SUSPEND_BUILTINS) & pycompile.COMPILABLE_BUILTINS, set())


def run_runtime(src: str, *, compiled: bool, **runtime_kwargs):
    from nodus.runtime.embedding import NodusRuntime
    env = {"NODUS_COMPILE_FUNCTIONS": "always" if compiled else ""}
    with mock.patch.dict(os.environ, env):
        runtime = NodusRuntime(timeout_ms=None, **runtime_kwargs)
        result = runtime.run_source(src)
    error = result.get("error") or {}
    vm = runtime.active_vm()
    return {
        "ok": result.get("ok"),
        "stdout": result.get("stdout"),
        "kind": error.get("kind") or error.get("type"),
        "message": error.get("message"),
        "line": error.get("line"),
        "instructions": runtime.get_execution_stats()["instructions_executed"],
    }, vm


class CapabilityBuiltinsInCompiledCode(unittest.TestCase):
    """Phase 2: capability-bearing builtins that cannot suspend are called from
    compiled code through the same `invoke_builtin`, so allowing and denying
    behave identically."""

    ENV = ('fn read(k) { return env_get(k) }\n'
           'fn main() {\n    let i = 0i\n    while (i < 2i) { print(read("NODUS_PHASE2_PROBE"))\n i = i + 1i }\n}\n'
           'main()\n')

    def both(self, src, **kwargs):
        plain, _ = run_runtime(src, compiled=False, **kwargs)
        fast, vm = run_runtime(src, compiled=True, **kwargs)
        self.assertEqual(fast, plain)
        self.assertGreater(compiled_count(vm), 0, "nothing compiled: the test proves nothing")
        return fast

    def test_an_allowed_call(self):
        with mock.patch.dict(os.environ, {"NODUS_PHASE2_PROBE": "seen"}):
            fast = self.both(self.ENV, allow_env=True)
        self.assertTrue(fast["ok"], fast)
        self.assertEqual(fast["stdout"].split(), ["seen", "seen"])

    def test_a_denied_call(self):
        fast = self.both(self.ENV, allow_env=False)
        self.assertFalse(fast["ok"])
        self.assertEqual(fast["kind"], "sandbox")
        self.assertIn("allow_env", fast["message"])

    def test_a_file_inside_and_outside_the_allowed_paths(self):
        import tempfile
        with tempfile.TemporaryDirectory() as inside, tempfile.TemporaryDirectory() as outside:
            for folder, text in ((inside, "in"), (outside, "out")):
                with open(os.path.join(folder, "f.txt"), "w", encoding="utf-8") as f:
                    f.write(text)
            for folder, allowed in ((inside, True), (outside, False)):
                path = os.path.join(folder, "f.txt").replace("\\", "/")
                src = (f'fn load(p) {{ return read_file(p) }}\n'
                       f'fn main() {{\n    for k in [1i, 2i] {{ print(load("{path}")) }}\n}}\nmain()\n')
                with self.subTest(allowed=allowed):
                    fast = self.both(src, allowed_paths=[inside])
                    self.assertEqual(fast["ok"], allowed, fast)

    def test_a_function_calling_an_async_builtin_stays_interpreted(self):
        from nodus.runtime.module_loader import ModuleLoader
        from nodus.vm.vm import VM
        src = 'fn fetch(u) { return http_get_async(u) }\nfn plain(u) { return http_get(u) }\n'
        code, functions, _ = ModuleLoader(project_root=None).compile_only(src, module_name="m.nd")
        vm = VM(code["instructions"], functions, code_locs=[], source_path=None)
        reasons = pycompile.eligible_functions(code["instructions"], functions, vm.builtins)
        self.assertIsNotNone(reasons["fetch"])
        self.assertIsNone(reasons["plain"])


if __name__ == "__main__":
    unittest.main()
