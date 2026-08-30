"""`load_name` and `store_name` must answer one question the same way (#671).

The defect: a function assigning a **module-top-level** `let` silently wrote a
frame-local. The global kept its old value, with no error, no warning and no
diagnostic. When the right-hand side also read the variable, the freshly-created
local was uninitialised, so `g = g + 1i` failed with `Cannot add nil and int` —
a type error naming arithmetic rather than scoping, which is the only signal a
user ever got. Where the RHS did not read the variable there was no signal at all.

Two sites answered *where does this name live*, and disagreed:

1. `SymbolTable._resolve_upvalue_in` returned `None` whenever there was no
   enclosing **function** scope — which is the case for every function declared
   at module level — so a module-level `let` was never found, and the `Assign`
   branch fell through to `symbols.define(name)` and allocated a frame slot.
2. `VM.store_name` wrote into the current frame's `locals` whenever a frame
   existed, while `load_name` walked on to `module_globals`.

Neither fix alone is sufficient, and that is the reason the bug looked
unfixable from either end. This module therefore pins **both** — the behaviour
each site controls, and the source-level property that keeps them from drifting
apart again. A behaviour-only suite would pass on whichever path is already
correct, which is exactly how this survived: reads worked the whole time.
"""

import inspect
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402


def run(source: str) -> dict:
    return NodusRuntime(timeout_ms=None).run_source(source)


def stdout_of(source: str) -> str:
    result = run(source)
    assert result["ok"], result.get("error")
    return result.get("stdout") or ""


# closes: #671
class TopLevelAssignmentTests(unittest.TestCase):
    """The reported defect, one test per surface that reaches it."""

    def test_a_named_function_assigns_a_top_level_let(self):
        out = stdout_of(
            "let g = 7i\n"
            "fn setit() { g = 99i }\n"
            "fn main() { setit(); print(\"g = \\(g)\") }\n"
        )
        self.assertIn("g = 99", out)

    def test_a_closure_assigns_a_top_level_let(self):
        out = stdout_of(
            "let g = 7i\n"
            "let setit = fn() { g = 99i }\n"
            "fn main() { setit(); print(\"g = \\(g)\") }\n"
        )
        self.assertIn("g = 99", out)

    def test_read_modify_write_no_longer_reads_nil(self):
        """The `Cannot add nil and int` case. The old failure named arithmetic,
        which is why nobody diagnosed it as scoping."""
        result = run(
            "let g = 0i\n"
            "let bump = fn() { g = g + 1i }\n"
            "fn main() { bump(); bump(); print(\"g = \\(g)\") }\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("g = 2", result.get("stdout") or "")

    def test_compound_assignment_reaches_the_top_level_binding(self):
        out = stdout_of(
            "let g = 0i\n"
            "fn bump() { g += 5i }\n"
            "fn main() { bump(); bump(); print(\"g = \\(g)\") }\n"
        )
        self.assertIn("g = 10", out)

    def test_a_spawned_coroutine_assigns_a_top_level_let(self):
        out = stdout_of(
            "let g = 0i\n"
            "fn main() {\n"
            "    spawn(coroutine(fn() { g = 42i }))\n"
            "    run_loop()\n"
            "    print(\"g = \\(g)\")\n"
            "}\n"
        )
        self.assertIn("g = 42", out)


# closes: #671
class ShadowingIsStillShadowingTests(unittest.TestCase):
    """The fix must not make every frame-local write escape to module scope.

    `STORE` is emitted at thirteen sites in the compiler, and several are
    legitimately frame-local inside a function — `catch` variables,
    destructuring temps, `match` pattern bindings. A fix that wrote the global
    unconditionally would clobber a same-named module binding from any of them.
    These are the negative half, and they are the reason `store_name` asks
    whether the frame already binds the name before looking outward.
    """

    def test_a_function_local_let_shadows_a_top_level_one(self):
        out = stdout_of(
            "let v = \"global\"\n"
            "fn inner() { let v = \"local\"; return v }\n"
            "fn main() { print(inner()); print(\"after: \\(v)\") }\n"
        )
        self.assertIn("local", out)
        self.assertIn("after: global", out, "a function-local let escaped to module scope")

    def test_a_catch_variable_does_not_clobber_a_same_named_global(self):
        out = stdout_of(
            "let e = \"global-e\"\n"
            "fn risky() { try { throw \"boom\" } catch e { return e.message } }\n"
            "fn main() { print(risky()); print(\"after: \\(e)\") }\n"
        )
        self.assertIn("boom", out)
        self.assertIn("after: global-e", out, "the catch variable escaped to module scope")

    def test_a_parameter_does_not_clobber_a_same_named_global(self):
        out = stdout_of(
            "let x = \"global-x\"\n"
            "fn takes(x) { return x }\n"
            "fn main() { print(takes(\"arg\")); print(\"after: \\(x)\") }\n"
        )
        self.assertIn("arg", out)
        self.assertIn("after: global-x", out)

    def test_a_loop_variable_does_not_clobber_a_same_named_global(self):
        out = stdout_of(
            "let i = \"global-i\"\n"
            "fn loops() { let total = 0i; for i in [1i, 2i] { total = total + i } return total }\n"
            "fn main() { print(loops()); print(\"after: \\(i)\") }\n"
        )
        self.assertIn("3", out)
        self.assertIn("after: global-i", out)


# closes: #671
class FunctionScopedCaptureStillWorksTests(unittest.TestCase):
    """The control. Upvalue mutation was already correct and must stay correct —
    DESIGN-006 (#156) claimed it was broken, which sent readers to an
    unnecessary map workaround for years."""

    def test_an_escaping_counter_closure(self):
        out = stdout_of(
            "fn make_counter() { let n = 0i; return fn() { n = n + 1i; return n } }\n"
            "fn main() { let c = make_counter(); print(c()); print(c()) }\n"
        )
        self.assertIn("1", out)
        self.assertIn("2", out)

    def test_two_closures_share_one_captured_variable(self):
        out = stdout_of(
            "fn main() {\n"
            "    let acc = 0i\n"
            "    let a = fn() { acc = acc + 1i }\n"
            "    let b = fn() { acc = acc + 10i }\n"
            "    a(); b(); print(\"acc = \\(acc)\")\n"
            "}\n"
        )
        self.assertIn("acc = 11", out)

    def test_a_two_level_nested_closure(self):
        out = stdout_of(
            "fn main() {\n"
            "    let deep = 0i\n"
            "    let outer = fn() { let inner = fn() { deep = deep + 100i }; inner() }\n"
            "    outer(); print(\"deep = \\(deep)\")\n"
            "}\n"
        )
        self.assertIn("deep = 100", out)


# closes: #671
class NamespaceAgreementTests(unittest.TestCase):
    """Direct tests of the one rule, at the level it is decided."""

    def _vm(self) -> VM:
        return VM([], {}, code_locs=[], source_path=None)

    def test_a_module_global_is_the_binding_namespace_from_inside_a_frame(self):
        from nodus.vm.types import Frame

        vm = self._vm()
        vm.module_globals["g"] = 7
        vm.frames = [Frame(return_ip=0, locals={}, fn_name="f",
                           call_line=None, call_col=None, call_path=None)]

        self.assertIs(vm.module_globals, vm.binding_namespace("g"))
        vm.store_name("g", 99)
        self.assertEqual(99, vm.module_globals["g"])
        self.assertNotIn("g", vm.frames[-1].locals, "the write was captured by the frame")

    def test_a_frame_local_shadows_the_module_global(self):
        from nodus.vm.types import Frame

        vm = self._vm()
        vm.module_globals["g"] = "global"
        frame = Frame(return_ip=0, locals={"g": "local"}, fn_name="f",
                      call_line=None, call_col=None, call_path=None)
        vm.frames = [frame]

        self.assertIs(frame.locals, vm.binding_namespace("g"))
        vm.store_name("g", "written")
        self.assertEqual("written", frame.locals["g"])
        self.assertEqual("global", vm.module_globals["g"])

    def test_an_unbound_name_is_defined_where_execution_is(self):
        from nodus.vm.types import Frame

        vm = self._vm()
        self.assertIsNone(vm.binding_namespace("fresh"))
        vm.store_name("fresh", 1)
        self.assertEqual(1, vm.module_globals["fresh"])

        framed = self._vm()
        frame = Frame(return_ip=0, locals={}, fn_name="f",
                      call_line=None, call_col=None, call_path=None)
        framed.frames = [frame]
        framed.store_name("fresh", 2)
        self.assertEqual(2, frame.locals["fresh"])
        self.assertNotIn("fresh", framed.module_globals)

    def test_read_and_write_agree_on_every_writable_namespace(self):
        """Bound in exactly one namespace, `load_name` and `store_name` must
        pick the same one. Parameterised so a third writable namespace cannot be
        added to one and forgotten in the other."""
        from nodus.vm.types import Frame

        for namespace in ("locals", "module_globals"):
            with self.subTest(namespace=namespace):
                vm = self._vm()
                frame = Frame(return_ip=0, locals={}, fn_name="f",
                              call_line=None, call_col=None, call_path=None)
                vm.frames = [frame]
                holder = frame.locals if namespace == "locals" else vm.module_globals
                holder["n"] = "before"

                self.assertEqual("before", vm.load_name("n"))
                vm.store_name("n", "after")
                self.assertEqual("after", holder["n"])
                self.assertEqual("after", vm.load_name("n"))


# closes: #671
class SourceLevelAgreementTests(unittest.TestCase):
    """Assert on the source, not only the behaviour.

    Required here more than usual: the defect *was* two implementations of one
    question, and reads were correct throughout — so a behaviour-only suite
    passes on the read path while the write path is broken, which is precisely
    what happened for the whole life of the feature.
    """

    _WRITABLE = ("module_globals",)

    def test_store_name_routes_through_the_shared_rule(self):
        source = inspect.getsource(VM.store_name)
        self.assertIn("binding_namespace", source,
                      "store_name decides the namespace itself again")

    def test_store_name_reaches_every_writable_namespace_load_name_does(self):
        """The drift guard. On the unfixed tree `store_name` never mentioned
        `module_globals` in its write path, which is the whole bug."""
        store_src = inspect.getsource(VM.store_name) + inspect.getsource(VM.binding_namespace)
        load_src = inspect.getsource(VM.load_name)
        for namespace in self._WRITABLE:
            with self.subTest(namespace=namespace):
                self.assertIn(namespace, load_src)
                self.assertIn(namespace, store_src,
                              f"load_name resolves {namespace} and store_name cannot reach it")

    def test_the_upvalue_resolver_does_not_bail_before_module_scope(self):
        """Site 1. `_resolve_upvalue_in` returned None the moment there was no
        enclosing *function* scope, so a top-level function never saw a
        module-level `let`."""
        from nodus.compiler.symbol_table import SymbolTable

        source = inspect.getsource(SymbolTable._resolve_upvalue_in)
        head = source.split("scope = func_scope.parent", 1)[0]
        self.assertNotRegex(
            head,
            r"if enclosing is None:\s*\n\s*return None",
            "the resolver bails before reaching module scope again",
        )
        self.assertIn("671", source, "the reason this branch exists is unrecorded")


# closes: #671
class WarmCacheTests(unittest.TestCase):
    """The bytecode cache is a third path to this question and has been the
    forgotten one three times (#521, #400, #394). A compiler fix that is only
    correct on a cold run is half a fix — and during this investigation the
    site-1 patch appeared inert until `.nodus/` was cleared."""

    def test_the_fix_survives_a_second_run_of_the_same_file(self):
        from nodus.tooling.runner import run_source as cli_run_source

        program = (
            "let g = 7i\n"
            "fn setit() { g = 99i }\n"
            "fn main() { setit(); print(\"g = \\(g)\") }\n"
        )
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "toplevel.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(program)

            first, _ = cli_run_source(program, filename=path, timeout_ms=None,
                                      project_root=root)
            self.assertTrue(
                os.path.isdir(os.path.join(root, ".nodus", "cache")),
                "no cache was written, so run 2 would not exercise the warm path",
            )
            second, _ = cli_run_source(program, filename=path, timeout_ms=None,
                                       project_root=root)

        for label, result in (("cold", first), ("warm", second)):
            with self.subTest(run=label):
                self.assertTrue(result["ok"], result.get("error"))
                self.assertIn("g = 99", result.get("stdout") or "")


if __name__ == "__main__":
    unittest.main()
