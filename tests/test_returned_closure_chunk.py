"""A closure a module RETURNS runs against its own chunk (#696).

The mirror of #691, split into its own file for a reason that is about the gate
rather than about the code: `nodus_gate --closed-issues` runs one test file per
CHANGELOG issue reference, so a single file carrying `# closes:` markers for two
issues is executed **twice** end to end. With both directions in one file that
was 28 tests and ~68 seconds, run twice — 56 subprocess launches for one file,
and twice the exposure to the subprocess flakiness this box and CI both have.
One issue per file, run once each, is the same coverage for half the work.

The substance is unchanged from when these lived alongside #691's tests. Every
context source #691's fix uses records something a call is still *inside* of — a
`_ClosureProxy` wrapped for an argument, a live cross-module frame, a caller VM.
A **returned** closure is called after all three are gone, so the resolution is
ownership over the modules the VM can reach instead.

The harness is imported rather than copied. Two copies of `assertBoth` would be
two answers to "how do we check both entry points", which is the shape this
project keeps paying for — and the CLI-vs-embedded split is exactly the thing
these tests exist to assert, so it must not drift between the two files.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.compiler.compiler import FunctionInfo  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402

from tests.test_cross_module_closure import _ModuleCallCase  # noqa: E402


# closes: #696
class ClosureReturnedFromAModuleTests(_ModuleCallCase):
    """The same question in the other direction: a closure a module handed back.

    #691 was a closure going *into* a module. This is one coming *out*, and
    every source #691's fix uses records a context a call is still inside of —
    a `_ClosureProxy` wrapped for an argument, a cross-module frame, a caller
    VM. By the time a returned closure is called, the frame has been popped and
    there is no caller VM, so all three are empty and the closure runs at its
    own address in whatever chunk happens to be loaded.

    Same five-way symptom spread, for the same reason: the symptom is whatever
    sits at that address. Measured on the unfixed tree, one repro each —
    `Method calls are only supported on records`, `run_workflow(workflow)
    expects a workflow`, `Cannot add int and string`, `Stack underflow`,
    `'NoneType' object is not subscriptable`, and a silent truncation that
    printed nothing at all.

    The resolution is ownership over the modules the VM can *reach*, so it needs
    no mark at any exit — which matters because closures also leave nested in
    containers, the case #339 found the entry side had missed.
    """

    def _write_factory_module(self) -> None:
        self.write("m.nd", """
            fn plain_maker() { return fn() { return 99i } }
            fn make_adder(n) { return fn(x) { return x + n } }
            fn counter() { let n = 0i; return fn() { n = n + 1i; return n } }
            fn in_list() { return [fn() { return 21i }] }
            fn in_map() { return {"cb": fn() { return 22i }} }
            fn identity(f) { return f }
            fn pad_a() { return 1i }
            fn pad_b() { return 2i }
        """)

    def test_a_returned_closure_runs_at_top_level(self):
        """The headline case. No workflow, no coroutine — one module, one
        factory function, called from `fn main()`."""
        self._write_factory_module()
        self.assertBoth(
            """
            import "./m.nd" as m
            fn main() {
                let f = m.plain_maker()
                print("got \\(f())")
            }
            """,
            "got 99",
        )

    def test_a_returned_closure_runs_inside_a_step_body(self):
        self._write_factory_module()
        self.assertBoth(
            """
            import "./m.nd" as m
            workflow w {
                step a { let f = m.plain_maker(); print("in step: \\(f())"); return "ok" }
            }
            fn main() { let r = run_workflow(w); print("failed: \\(r["failed"])") }
            """,
            "in step: 99", "failed: []",
        )

    def test_a_returned_closure_keeps_the_upvalue_it_captured(self):
        """A factory's whole point. The closure's frame is gone, so the captured
        `n` has to travel in the `Cell` rather than in the module's state."""
        self._write_factory_module()
        self.assertBoth(
            """
            import "./m.nd" as m
            fn main() {
                let g = m.make_adder(3i)
                print("adder: \\(g(10i))")
            }
            """,
            "adder: 13",
        )

    def test_a_returned_closure_may_be_stateful_across_calls(self):
        """Printed nothing at all on the unfixed tree — the silent case."""
        self._write_factory_module()
        self.assertBoth(
            """
            import "./m.nd" as m
            fn main() {
                let c = m.counter()
                print("counter: \\(c()) \\(c()) \\(c())")
            }
            """,
            "counter: 1 2 3",
        )

    def test_a_returned_closure_nested_in_a_container_is_found_too(self):
        """Nothing marks these, which is why the fix resolves rather than
        marks — #339 is the precedent for a container walk being forgotten."""
        self._write_factory_module()
        self.assertBoth(
            """
            import "./m.nd" as m
            fn main() {
                print("list: \\(m.in_list()[0i]())")
                print("map: \\(m.in_map()["cb"]())")
            }
            """,
            "list: 21", "map: 22",
        )

    def test_a_closure_from_a_transitively_imported_module_is_found(self):
        """`main` imports `outer`; only `outer` imports `inner`. The closure
        belongs to `inner`, which `main` never binds — so reachability has to
        walk through the modules it does bind."""
        self.write("inner.nd", """
            fn deep_maker() { return fn() { return 7i } }
            fn pad_i() { return 0i }
        """)
        self.write("outer.nd", """
            import "./inner.nd" as inner
            fn forward_maker() { return inner.deep_maker() }
            fn pad_o1() { return 1i }
            fn pad_o2() { return 2i }
        """)
        self.assertBoth(
            """
            import "./outer.nd" as o
            fn main() { let f = o.forward_maker(); print("nested: \\(f())") }
            """,
            "nested: 7",
        )

    def test_two_modules_with_identically_named_anonymous_functions(self):
        """Both chunks hold an `__anon_1`. Ownership is identity on the
        `FunctionInfo`, not on the name, so the two do not collide — and the
        first one still works after the second has been resolved."""
        self.write("ma.nd", 'fn maker() { return fn() { return "from-A" } }')
        self.write("mb.nd", """
            fn maker() { return fn() { return "from-B" } }
            fn pad1() { return 1i }
            fn pad2() { return 2i }
            fn pad3() { return 3i }
        """)
        self.assertBoth(
            """
            import "./ma.nd" as a
            import "./mb.nd" as b
            fn main() {
                let fa = a.maker()
                let fb = b.maker()
                print("a: \\(fa()) b: \\(fb()) a again: \\(fa())")
            }
            """,
            "a: from-A b: from-B a again: from-A",
        )

    def test_a_closure_the_caller_owns_survives_a_round_trip(self):
        """The control for the resolution: handing a closure in and getting it
        back must not make it foreign. It belongs to the caller's chunk, so
        nothing should be swapped for it."""
        self._write_factory_module()
        self.assertBoth(
            """
            import "./m.nd" as m
            fn mine() { return 5i }
            fn main() {
                print("literal: \\(m.identity(fn() { return 42i })())")
                print("named: \\(m.identity(mine)())")
            }
            """,
            "literal: 42", "named: 5",
        )

    def test_closures_from_two_modules_interleave(self):
        """Each call must install its own chunk. One context left behind would
        make the second closure run in the first's."""
        self.write("inner.nd", "fn deep_maker() { return fn() { return 7i } }")
        self.write("outer.nd", """
            import "./inner.nd" as inner
            fn forward_maker() { return inner.deep_maker() }
            fn counter() { let n = 0i; return fn() { n = n + 1i; return n } }
            fn pad_o1() { return 1i }
        """)
        self.assertBoth(
            """
            import "./outer.nd" as o
            fn main() {
                let f = o.forward_maker()
                let g = o.counter()
                print("interleaved: \\(f()) \\(g()) \\(f()) \\(g())")
            }
            """,
            "interleaved: 7 1 7 2",
        )

    def test_a_std_module_still_works_after_all_this(self):
        """`std:retry` is the feature #691 was filed against; it must keep
        working now that module contexts are also rebuilt from the module."""
        self.assertBoth(
            """
            import "std:retry" as retry
            fn main() {
                let r = retry.until(fn() { return 3i },
                                    fn(v) { return v >= 3i },
                                    {"max_attempts": 2i})
                print("value=\\(r["value"])")
            }
            """,
            "value=3",
        )



class ReturnedClosureResolutionTests(unittest.TestCase):
    """`_module_owning` searches what the VM can *reach*, not a global registry.

    A process-wide "every module ever loaded" table would be the module-scope
    state shape behind #185 and #390 — every participant in the process sharing
    one, and one tenant's VM able to resolve another's chunk. Reachability keeps
    the answer scoped to what the program could have called.
    """

    def test_it_walks_only_modules_reachable_from_this_vm(self):
        from nodus.runtime.module import NodusModule  # noqa: PLC0415

        def module(name, fn_name):
            fn = FunctionInfo(name=fn_name, params=[], addr=0, upvalues=[],
                              display_name=fn_name)
            mod = NodusModule(name=name, path=f"<{name}>", bytecode=[],
                              functions={fn_name: fn}, code_locs=[])
            return mod, fn

        vm = VM([], {}, code_locs=[], source_path=None)
        bound, bound_fn = module("bound", "a")
        nested, nested_fn = module("nested", "b")
        unreachable, unreachable_fn = module("unreachable", "c")
        bound.globals["nested"] = nested
        vm.module_globals["bound"] = bound

        self.assertIs(bound, vm._module_owning(bound_fn))
        self.assertIs(nested, vm._module_owning(nested_fn),
                      "a transitively imported module must be reachable")
        self.assertIsNone(vm._module_owning(unreachable_fn),
                          "a module nothing binds must not be resolvable")

    def test_a_cycle_between_modules_terminates(self):
        from nodus.runtime.module import NodusModule  # noqa: PLC0415

        a = NodusModule(name="a", path="<a>", bytecode=[], functions={}, code_locs=[])
        b = NodusModule(name="b", path="<b>", bytecode=[], functions={}, code_locs=[])
        a.globals["b"] = b
        b.globals["a"] = a
        vm = VM([], {}, code_locs=[], source_path=None)
        vm.module_globals["a"] = a
        absent = FunctionInfo(name="z", params=[], addr=0, upvalues=[],
                              display_name="z")
        self.assertIsNone(vm._module_owning(absent))


if __name__ == "__main__":
    unittest.main()
