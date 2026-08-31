"""A closure runs against the chunk it was compiled from, wherever it is called (#691).

A ``Closure`` is an address plus its upvalues, and the address is meaningless
without the chunk it indexes. The VM ends up running someone else's chunk in two
different ways, and only one of them ever checked:

  * a **detached module VM** -- ``NodusModule.invoke_function`` builds a fresh VM
    over the module's bytecode and wraps ``Closure`` arguments in
    ``_ClosureProxy`` on the way in, so the callback dispatches back to the
    caller. This is the path a module call takes from ``fn main()``, and it was
    correct.
  * a **cross-module frame in this same VM** -- ``VM._try_enter_module_call``,
    the #105 fast path, swaps the module's code/functions/globals into the
    running VM and jumps. It is taken whenever the call happens inside a
    scheduler-managed coroutine, and **a workflow step body is always one**.
    Nothing was wrapped and nothing was checked there, so ``m.f(fn() { ... })``
    jumped to the callback's caller-chunk address inside the *module's*
    instruction array.

That produced five different symptoms from one construct, depending only on how
long the module's chunk happened to be and what sat at the address:

    module defines one function          -> ran off the end, HALT, step never
                                            recorded: `failed: []`, `steps: {}`
    module defines two functions         -> Stack underflow
    callback is a named top-level `fn`   -> Cannot call non-function: nil
    callback reached through the
      iterator protocol (`run_closure`)  -> Iterator is not supported
    callback wrapped in a coroutine      -> silently never ran

The silent ones are why this survived a full suite, nine gate phases and 83
release probes: every test and probe for `retry.until` -- the feature whose
documented home is a step body -- ran inside `fn main()`, which takes the other
path. A construct documented for use inside a step body must be tested inside a
step body.

The fix names the question once. ``VM._foreign_closure_origin`` answers "which
context does this closure need, if not the one loaded" for every caller, and the
two sites that jump to ``fn.addr`` over a caller-supplied closure --
``call_closure`` and ``run_closure`` -- both consult it. ``builtin_coroutine_create``
and ``builtin_spawn`` had their own version of it (``_is_foreign_closure`` and
then reaching for ``_caller_vm`` directly, which silently assumed the detached VM
was the only way to be running foreign code); they ask the same function now.

`ClosureAddressJumpSitesTests` asserts on the source, because a behaviour test
only ever covers the doors it happens to know about.
"""

import ast
import io
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "src"
NODUS_PY = REPO / "nodus.py"

sys.path.insert(0, str(SRC))

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


# --------------------------------------------------------------------------
# Harness. Every behaviour case runs BOTH under the CLI and embedded: the
# symptoms differed between the two in #339 and again here (a hard error one
# way, a silently successful run the other), so a case verified in one mode
# says nothing about the other.
# --------------------------------------------------------------------------

class _ModuleCallCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, name: str, source: str) -> None:
        (self.tmpdir / name).write_text(textwrap.dedent(source), encoding="utf-8")

    def run_cli(self, source: str) -> str:
        self.write("main.nd", source)
        proc = subprocess.run(
            [sys.executable, str(NODUS_PY), "run", str(self.tmpdir / "main.nd")],
            capture_output=True, text=True, timeout=120,
            cwd=str(self.tmpdir),
            env={"PYTHONPATH": str(SRC), "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        )
        self.assertEqual(proc.returncode, 0,
                         f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
        return proc.stdout

    def run_embedded(self, source: str) -> str:
        rt = NodusRuntime(timeout_ms=None, max_steps=None,
                          allowed_paths=[str(self.tmpdir)])
        result = rt.run_file(str(self._written_main(source)))
        self.assertTrue(result["ok"], result.get("errors") or result)
        return result["stdout"]

    def _written_main(self, source: str) -> pathlib.Path:
        self.write("main.nd", source)
        return self.tmpdir / "main.nd"

    def assertBoth(self, source: str, *expected: str) -> None:
        """The same program, both entry points, same output. Both or neither."""
        for mode, out in (("cli", self.run_cli(source)),
                          ("embedded", self.run_embedded(source))):
            for fragment in expected:
                self.assertIn(fragment, out,
                              f"[{mode}] missing {fragment!r} in:\n{out}")


# closes: #691
class StepBodyCallsAModuleFunctionTests(_ModuleCallCase):

    def test_a_step_body_callback_runs_and_the_step_is_recorded(self):
        """The headline case: it truncated, and the run reported success.

        `steps: {}` with `failed: []` is the part that has to stay dead. A step
        that neither completed nor failed is worse than a step that failed.
        """
        self.write("m.nd", "fn no_loop(f) { return f() }")
        self.assertBoth(
            """
            import "./m.nd" as m
            workflow w {
                step a {
                    print("STEP RAN")
                    let v = m.no_loop(fn() { return 7i })
                    print("got \\(v)")
                    return "ok"
                }
            }
            fn main() {
                let r = run_workflow(w)
                print("failed: \\(r["failed"])")
                print("steps: \\(r["steps"])")
            }
            """,
            "STEP RAN", "got 7", "failed: []", 'steps: {"a": "ok"}',
        )

    def test_a_second_function_in_the_module_does_not_change_the_first(self):
        """`Stack underflow`. A module with only `no_loop` worked, a module with
        only `in_loop` worked, and a module with both failed on `no_loop` -- the
        callback's address simply landed somewhere different in a longer chunk.
        """
        self.write("m.nd", """
            fn no_loop(f) { return f() }
            fn in_loop(f) {
                let n = 0i
                let last = nil
                while (n < 2i) { last = f(); n = n + 1i }
                return last
            }
        """)
        self.assertBoth(
            """
            import "./m.nd" as m
            workflow w {
                step a {
                    print("no_loop: \\(m.no_loop(fn() { return 1i }))")
                    print("in_loop: \\(m.in_loop(fn() { return 2i }))")
                    return "ok"
                }
            }
            fn main() { let r = run_workflow(w); print("failed: \\(r["failed"])") }
            """,
            "no_loop: 1", "in_loop: 2", "failed: []",
        )

    def test_a_named_top_level_function_is_callable_as_a_callback(self):
        """`Cannot call non-function: nil`. A literal closure in the same
        position behaved differently, which is what made this look like a
        problem with named functions rather than with addresses.
        """
        self.write("m.nd", "fn apply_twice(f, v) { let a = f(v); return f(a) }")
        self.assertBoth(
            """
            import "./m.nd" as m
            fn inc(x) { return x + 1i }
            workflow w {
                step s { print("in step: \\(m.apply_twice(inc, 1i))"); return "ok" }
            }
            fn main() {
                print("outside: \\(m.apply_twice(inc, 1i))")
                let r = run_workflow(w)
                print("failed: \\(r["failed"])")
            }
            """,
            "outside: 3", "in step: 3", "failed: []",
        )

    def test_the_callback_still_sees_its_captured_variables(self):
        """Running in the right chunk is not enough if the frame is wrong."""
        self.write("m.nd", "fn call(f) { return f() }")
        self.assertBoth(
            """
            import "./m.nd" as m
            workflow w {
                step a {
                    let base = 40i
                    print("sum: \\(m.call(fn() { return base + 2i }))")
                    return "ok"
                }
            }
            fn main() { let r = run_workflow(w); print("failed: \\(r["failed"])") }
            """,
            "sum: 42", "failed: []",
        )

    def test_a_closure_passed_through_two_modules_runs_in_the_chunk_it_came_from(self):
        """Nearest boundary is the wrong answer, and this is what proves it.

        `main -> outer.forward(f) -> inner.run_it(f)`: the innermost boundary
        saved `outer`, and `f` belongs to `main`. The origin is resolved by
        asking which saved context *owns* the FunctionInfo, so it names the
        right one however many boundaries the value crossed.
        """
        self.write("inner.nd", "fn run_it(f) { return f() + 100i }")
        self.write("outer.nd", """
            import "./inner.nd" as inner
            fn forward(f) { return inner.run_it(f) }
            fn direct(f) { return f() }
        """)
        self.assertBoth(
            """
            import "./outer.nd" as o
            workflow w {
                step a {
                    let base = 5i
                    print("direct: \\(o.direct(fn() { return base + 1i }))")
                    print("nested: \\(o.forward(fn() { return base + 2i }))")
                    return "ok"
                }
            }
            fn main() { let r = run_workflow(w); print("failed: \\(r["failed"])") }
            """,
            "direct: 6", "nested: 107", "failed: []",
        )

    def test_a_callback_nested_in_a_container_is_recognised_too(self):
        """The #339 case, on the path #339 never covered. Nothing wraps these,
        so they are found by ownership rather than by a proxy.
        """
        self.write("m.nd", """
            fn call_first(lst) { return lst[0i]() }
            fn call_field(rec) { return rec["cb"]() }
        """)
        self.assertBoth(
            """
            import "./m.nd" as m
            workflow w {
                step a {
                    print("list: \\(m.call_first([fn() { return 11i }]))")
                    print("map: \\(m.call_field({"cb": fn() { return 12i }}))")
                    return "ok"
                }
            }
            fn main() { let r = run_workflow(w); print("failed: \\(r["failed"])") }
            """,
            "list: 11", "map: 12", "failed: []",
        )

    def test_an_error_thrown_in_the_callback_is_catchable_and_restores_context(self):
        """A context installed for a frame has to come back on the unwind too,
        or the next module call in the same step runs against the wrong chunk.
        """
        self.write("m.nd", "fn call(f) { return f() }")
        self.assertBoth(
            """
            import "./m.nd" as m
            fn boom() { throw "kaboom" }
            workflow w {
                step a {
                    try {
                        print("unreachable \\(m.call(fn() { boom(); return 1i }))")
                    } catch e {
                        print("caught: \\(e)")
                    }
                    print("after: \\(m.call(fn() { return 42i }))")
                    return "ok"
                }
            }
            fn main() { let r = run_workflow(w); print("failed: \\(r["failed"])") }
            """,
            "caught: kaboom", "after: 42", "failed: []",
        )

    def test_a_callback_may_still_suspend(self):
        """The whole reason `_try_enter_module_call` exists (#105/#339) is that
        the callback stays in this loop and can yield. Fixing the address must
        not cost that.
        """
        self.write("m.nd", """
            fn in_loop(f) {
                let n = 0i
                let last = nil
                while (n < 2i) { last = f(); n = n + 1i }
                return last
            }
        """)
        self.assertBoth(
            """
            import "std:async" as async
            import "./m.nd" as m
            workflow w {
                step a {
                    print("slept: \\(m.in_loop(fn() { async.sleep(5i); return 3i }))")
                    return "ok"
                }
            }
            fn main() { let r = run_workflow(w); print("failed: \\(r["failed"])") }
            """,
            "slept: 3", "failed: []",
        )

    def test_retry_until_works_where_its_documentation_puts_it(self):
        """The 5.8.0 feature this blocked. `retry.until` is a `std:retry`
        function whose documented home is a step body; every test and probe
        for it ran in `fn main()`.
        """
        self.assertBoth(
            """
            import "std:retry" as retry
            workflow w {
                step s {
                    let r = retry.until(fn() { return 1i },
                                        fn(v) { return true },
                                        {"max_attempts": 2i})
                    print("value=\\(r["value"])")
                    return "ok"
                }
            }
            fn main() { let r = run_workflow(w); print("failed: \\(r["failed"])") }
            """,
            "value=1", "failed: []",
        )


# closes: #691
class RunClosureCallbackTests(_ModuleCallCase):
    """`run_closure` is the other site that jumps to `fn.addr`.

    Builtins handed a callback reach it with whatever chunk the VM is running:
    `retry_call`, tool handlers, `std:test`, and the iterator protocol. Fixing
    only `call_closure` left this half broken, with its own symptom.
    """

    def test_a_custom_iterator_may_be_consumed_by_a_module_function(self):
        self.write("m.nd", """
            fn sum_all(it) {
                let total = 0i
                for x in it { total = total + x }
                return total
            }
        """)
        self.assertBoth(
            """
            import "./m.nd" as m
            fn make_iter(limit) {
                let n = 0i
                return record {
                    __next__: fn(self) {
                        if (n >= limit) { return nil }
                        n = n + 1i
                        return n
                    }
                }
            }
            workflow w {
                step a { print("sum: \\(m.sum_all(make_iter(4i)))"); return "ok" }
            }
            fn main() { let r = run_workflow(w); print("failed: \\(r["failed"])") }
            """,
            "sum: 10", "failed: []",
        )


# closes: #691
class CoroutineOverAForeignClosureTests(_ModuleCallCase):
    """`coroutine()` and `spawn()` pin the closure's context at creation.

    They asked `_is_foreign_closure` and then reached for `_caller_vm`
    themselves -- correct for the detached VM and wrong for a cross-module
    frame, where the coroutine was created with no context and silently never
    ran.
    """

    def test_a_module_may_spawn_the_callers_closure_from_inside_a_step(self):
        self.write("m.nd", """
            fn run_in_coro(f) {
                let c = coroutine(f)
                spawn(c)
                return "spawned"
            }
            fn other() { return 1i }
        """)
        self.assertBoth(
            """
            import "./m.nd" as m
            workflow w {
                step a {
                    print(m.run_in_coro(fn() { print("callback ran") }))
                    return "ok"
                }
            }
            fn main() { let r = run_workflow(w); print("failed: \\(r["failed"])") }
            """,
            "spawned", "callback ran", "failed: []",
        )


# closes: #691
class StepEntryGuardStillHoldsTests(_ModuleCallCase):
    """#394 must not be reopened by the door this fix widens.

    `call_closure` installs a context before jumping now. It must still refuse
    an unauthorized step body first, or "hand the step's `fn` to a module
    function" becomes the fifth door.
    """

    def test_a_step_closure_handed_to_a_module_function_is_still_refused(self):
        self.write("m.nd", "fn call(f) { return f() }")
        self.assertBoth(
            """
            import "./m.nd" as m
            let log = {"s": ""}
            workflow build {
                step lint { log["s"] = log["s"] + "lint;" return "linted" }
            }
            fn main() {
                try {
                    m.call(build["steps"][0i]["fn"])
                    print("BYPASSED")
                } catch e {
                    print("refused")
                }
                print("log='\\(log["s"])'")
            }
            """,
            "refused", "log=''",
        )



# --------------------------------------------------------------------------
# Source: every jump to a closure's address, and what establishes its context.
# --------------------------------------------------------------------------

# Each entry is (file, enclosing function) -> the token that proves the site
# establishes the chunk it is about to jump into. A site that jumps to a
# `.addr` without one of these runs unrelated instructions, which is #691.
ADDRESS_JUMP_SITES = {
    ("src/nodus/vm/vm.py", "call_closure"): "_foreign_closure_origin",
    ("src/nodus/vm/vm.py", "run_closure"): "_foreign_closure_origin",
    ("src/nodus/vm/vm.py", "_try_enter_foreign_closure"): "_restore_module_ctx",
    # `self.module_ctx(`, not `module_ctx` — the shorter string is a substring
    # of `_capture_module_ctx`, so it would match the unfixed code too and the
    # assertion could not fail (#696).
    ("src/nodus/vm/vm.py", "_try_enter_module_call"): "self.module_ctx(",
    # `_op_call` resolves `fn_name` in `self.functions` -- the table of the
    # chunk it is already running -- so the address is local by construction.
    # There is no caller-supplied closure here to be foreign.
    ("src/nodus/vm/vm.py", "_op_call"): "self.functions",
    # The coroutine's first resume runs under `load_coroutine_context`, which
    # restores the context pinned at `coroutine()`/`spawn()` time.
    ("src/nodus/builtins/coroutine.py", "builtin_coroutine_resume"):
        "load_coroutine_context",
}

_SCANNED = (
    "src/nodus/vm/vm.py",
    "src/nodus/builtins/coroutine.py",
    "src/nodus/runtime/module.py",
    "src/nodus/vm/types.py",
)


def _address_jump_sites() -> dict:
    """Every `<x>.ip = <y>.addr` in the runtime, keyed by (file, function)."""
    found = {}
    for rel in _SCANNED:
        source = io.open(REPO / rel, encoding="utf-8").read()
        tree = ast.parse(source)
        functions = [n for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target, value = node.targets[0], node.value
            if not (isinstance(target, ast.Attribute) and target.attr == "ip"):
                continue
            if not (isinstance(value, ast.Attribute) and value.attr == "addr"):
                continue
            enclosing = None
            for fn in functions:
                if fn.lineno <= node.lineno <= (fn.end_lineno or fn.lineno):
                    if enclosing is None or fn.lineno > enclosing.lineno:
                        enclosing = fn
            key = (rel, enclosing.name if enclosing else "?")
            found[key] = ast.get_source_segment(source, enclosing) or ""
    return found


class ClosureAddressJumpSitesTests(unittest.TestCase):

    def test_the_set_of_address_jump_sites_is_closed(self):
        discovered = set(_address_jump_sites())
        known = set(ADDRESS_JUMP_SITES)
        new = discovered - known
        self.assertFalse(new, (
            f"New site(s) jumping to a closure address: {sorted(new)}. An "
            f"address indexes the chunk the closure was COMPILED against "
            f"(#691); establish that context before jumping, then record the "
            f"site here."
        ))
        gone = known - discovered
        self.assertFalse(
            gone, f"Jump site(s) disappeared, update the map: {sorted(gone)}")

    def test_every_jump_site_establishes_the_chunk_it_jumps_into(self):
        sources = _address_jump_sites()
        for key, token in sorted(ADDRESS_JUMP_SITES.items()):
            with self.subTest(site=key):
                self.assertIn(token, sources.get(key, ""), (
                    f"{key[1]} in {key[0]} jumps to a closure's address without "
                    f"{token!r}. See #691."
                ))

    def test_the_origin_question_is_asked_in_one_place(self):
        """`_is_foreign_closure` used to imply `_caller_vm is not None`, and two
        callers in `coroutine.py` leaned on that implication rather than saying
        so -- which is how the detached VM became "the" way to be running
        foreign code. Nothing outside `_foreign_closure_origin` may pair the two
        again.
        """
        for rel in ("src/nodus/vm/vm.py", "src/nodus/builtins/coroutine.py"):
            source = io.open(REPO / rel, encoding="utf-8").read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name == "_foreign_closure_origin":
                    continue
                body = ast.get_source_segment(source, node) or ""
                if "_is_foreign_closure" not in body:
                    continue
                with self.subTest(site=f"{rel}::{node.name}"):
                    self.assertNotIn("_caller_vm._capture_module_ctx", body, (
                        f"{node.name} decides a closure's origin for itself. "
                        f"Ask VM._foreign_closure_origin instead (#691)."
                    ))

    def test_a_modules_context_is_built_in_one_place(self):
        """#696. `_try_enter_module_call` and `_foreign_closure_origin` both
        need to *be* a module — one on the way in, one for a closure it handed
        back. Two hand-built copies of that tuple would be two answers to one
        question, which is how this file's other entries got here.

        The marker is `module.bytecode` reaching `normalize_bytecode`: that is
        the step that turns a module into something executable, so a second site
        doing it is a second definition.
        """
        source = io.open(REPO / "src/nodus/vm/vm.py", encoding="utf-8").read()
        tree = ast.parse(source)
        builders = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.get_source_segment(source, node) or ""
            if "normalize_bytecode(module.bytecode)" in body:
                builders.append(node.name)
        self.assertEqual(
            ["module_ctx"], sorted(builders),
            "a module's execution context is built somewhere other than "
            "VM.module_ctx (#696)",
        )

if __name__ == "__main__":
    unittest.main()
