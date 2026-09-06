"""A `state` cell can declare that its readers wait for its writers (#578).

`step d after b, c` writes a join on the **step** side, and gets it wrong the
moment a fourth writer is added and the author forgets to name it.
`state total = 0i with { barrier: true }` writes it on the **data** side: every
step that reads the cell waits for every step that writes it, inferred, so
there is nothing to forget.

Three things this file exists to hold still.

**A barrier edge is ordering, not data.** `deps` is also the step's parameter
list -- `step d after b, c` binds `b` and `c` as locals and the runtime requires
one parameter per dep -- so an inferred edge in `deps` would change a step's
signature and reject a body the author wrote correctly. Barrier edges travel as
`order_after` for that reason, and the first version of this feature did put
them in `deps`, which broke every barrier reader with a zero-parameter body.

**Writers must write unconditionally.** That is #578's decided question. A
conditional writer makes the writer set statically unknown, and the two
alternatives are worse: a may-write analysis that guesses, or a reader that
waits forever when the other branch is taken. The definition of "unconditional"
is #500's verbatim -- a direct statement of an unguarded step body.

**Lowering must not mutate the AST.** Writing inferred edges onto `step.deps`
made lowering non-idempotent: a second lowering saw the edges already present,
inferred nothing, and so ran no cycle check -- the edges survived and the error
did not. The CLI lowers twice, so a barrier cycle reached the runtime as a
`Dependency cycle detected` naming a join nobody wrote.
"""

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.runtime.diagnostics import LangSyntaxError  # noqa: E402
from nodus.orchestration import workflow_lowering as WL  # noqa: E402


def _flow(src: str):
    for node in Parser(tokenize(src)).parse():
        if type(node).__name__ == "WorkflowDef":
            return node
    raise AssertionError("no workflow in source")


def _lower(src: str):
    return WL.lower_workflow_ast(_flow(src))


def _step_map(lowered, name: str) -> dict:
    """Pull one step out of the lowered MapLit, as plain data."""
    for key, value in lowered.items:
        if getattr(key, "v", None) != "steps":
            continue
        for step in value.items:
            fields = {k.v: v for k, v in step.items if hasattr(k, "v")}
            if getattr(fields.get("name"), "v", None) == name:
                return fields
    raise AssertionError(f"no step {name!r} in lowered flow")


def _names(list_lit) -> list[str]:
    return [item.v for item in list_lit.items]


def _order_after(step_fields) -> list[str]:
    """The inferred edges, or none.

    Absent rather than empty when a step has no barrier edge: the key would
    otherwise change the lowered shape -- and the bytecode -- of every workflow
    ever written, including those with no barrier in them.
    """
    lit = step_fields.get("order_after")
    return sorted(_names(lit)) if lit is not None else []


TWO_WRITERS = """
workflow w {
    state total = 0i with { barrier: true }
    step a { total = 1i; return "a" }
    step b { total = 2i; return "b" }
    step reader { return total }
}
"""


class TheEdgeIsInferredTests(unittest.TestCase):
    # closes: #578
    def test_a_reader_waits_for_every_writer(self):
        reader = _step_map(_lower(TWO_WRITERS), "reader")
        self.assertEqual(["a", "b"], _order_after(reader))

    # closes: #578
    def test_a_writer_waits_for_nobody(self):
        """The control. Without it the assertion above is satisfied by an
        implementation that makes every step wait for every other."""
        a = _step_map(_lower(TWO_WRITERS), "a")
        self.assertEqual([], _order_after(a))

    # closes: #578
    def test_a_cell_without_the_option_infers_nothing(self):
        """The second control: the edges come from `barrier: true`, not from
        reading a state cell at all."""
        plain = TWO_WRITERS.replace(" with { barrier: true }", "")
        self.assertEqual([], _order_after(_step_map(_lower(plain), "reader")))

    # closes: #578
    def test_an_existing_join_is_not_duplicated(self):
        """Transitive, like #722's check: `after a` where `a` writes the cell
        already orders it, and re-adding the edge would be noise in the graph."""
        src = """
        workflow w {
            state x = 0i with { barrier: true }
            step a { x = 1i; return "a" }
            step r after a { return x }
        }
        """
        self.assertEqual([], _order_after(_step_map(_lower(src), "r")))

    # closes: #578
    def test_a_step_does_not_wait_for_itself(self):
        """`x += 1i` reads and writes the same cell."""
        src = """
        workflow w {
            state x = 0i with { barrier: true }
            step a { x += 1i; return "a" }
        }
        """
        self.assertEqual([], _order_after(_step_map(_lower(src), "a")))


class TheEdgeIsOrderingNotDataTests(unittest.TestCase):
    """`deps` carries parameters; `order_after` carries order. Keeping them
    apart is what lets a barrier reader have a zero-parameter body."""

    # closes: #578
    def test_deps_is_untouched_by_inference(self):
        reader = _step_map(_lower(TWO_WRITERS), "reader")
        self.assertEqual([], _names(reader["deps"]))

    # closes: #578
    def test_a_declared_dep_still_lands_in_deps(self):
        """The control: `order_after` has not quietly replaced `after`."""
        src = """
        workflow w {
            state x = 0i with { barrier: true }
            step a { x = 1i; return "a" }
            step r after a { return 1i }
        }
        """
        self.assertEqual(["a"], _names(_step_map(_lower(src), "r")["deps"]))


class WritersMustWriteUnconditionallyTests(unittest.TestCase):
    """#578's decided question, and the whole of what it decided."""

    def _refused(self, src: str) -> str:
        with self.assertRaises(LangSyntaxError) as caught:
            _lower(src)
        return str(caught.exception)

    # closes: #578
    def test_a_write_inside_an_if_is_refused(self):
        message = self._refused("""
        workflow w {
            state x = 0i with { barrier: true }
            step a { if (true) { x = 1i }; return "a" }
            step r { return x }
        }
        """)
        self.assertIn("not on every pass", message)
        self.assertIn("`if`", message)

    # closes: #578
    def test_a_when_guarded_writer_is_refused(self):
        message = self._refused("""
        workflow w {
            state x = 0i with { barrier: true }
            step gate { checkpoint "go"; return "g" }
            step a after gate when reached("go") { x = 1i; return "a" }
            step r { return x }
        }
        """)
        self.assertIn("`when` guard", message)

    # closes: #578
    def test_an_unconditional_write_is_accepted(self):
        """The control, and it must run: without it every assertion above is
        satisfied by refusing all barrier writers."""
        self.assertEqual(["a", "b"], _order_after(_step_map(_lower(TWO_WRITERS), "reader")))

    # closes: #578
    def test_a_container_write_counts_as_a_write(self):
        """`x["k"] = v` mutates the cell. #518 was an enumeration of assignment
        forms missing a member, so all four are covered rather than the two that
        are obvious."""
        src = """
        workflow w {
            state x = {"n": 0i} with { barrier: true }
            step a { x["n"] = 1i; return "a" }
            step r { return x }
        }
        """
        self.assertEqual(["a"], _order_after(_step_map(_lower(src), "r")))


class TheDeclarationIsCheckedTests(unittest.TestCase):
    # closes: #578
    def test_barrier_must_be_the_literal_true(self):
        """#490's rule: accepted-and-ignored is the worst of the three states.
        A computed value cannot be read at compile time, and `false` should be
        written by omitting the key."""
        for value in ("false", "1i", '"yes"'):
            with self.subTest(value=value):
                with self.assertRaises(LangSyntaxError) as caught:
                    _lower(f"""
                    workflow w {{
                        state x = 0i with {{ barrier: {value} }}
                        step a {{ x = 1i; return "a" }}
                    }}
                    """)
                self.assertIn("literal `true`", str(caught.exception))


class InferenceDoesNotMutateTheAstTests(unittest.TestCase):
    """Lowering the same tree twice must give the same answer."""

    # closes: #578
    def test_lowering_twice_infers_the_same_edges(self):
        flow = _flow(TWO_WRITERS)
        first = _order_after(_step_map(WL.lower_workflow_ast(flow), "reader"))
        second = _order_after(_step_map(WL.lower_workflow_ast(flow), "reader"))
        self.assertEqual(first, second)
        self.assertEqual(["a", "b"], second)

    # closes: #578
    def test_the_declared_deps_are_unchanged_by_lowering(self):
        """The direct form of the same claim, and the one that actually caught
        it: `step.deps` on the AST must still be what the author wrote."""
        flow = _flow(TWO_WRITERS)
        WL.lower_workflow_ast(flow)
        WL.lower_workflow_ast(flow)
        self.assertEqual(
            {"a": [], "b": [], "reader": []},
            {s.name: list(s.deps or []) for s in flow.steps},
        )

    # closes: #578
    def test_a_cycle_is_still_refused_on_a_second_lowering(self):
        """The consequence that made the mutation visible. With the AST mutated,
        the second lowering inferred nothing, skipped the cycle check, and let
        the edges through."""
        src = """
        workflow w {
            state p = 0i with { barrier: true }
            state q = 0i with { barrier: true }
            step a { q = 1i; return p }
            step b { p = 1i; return q }
        }
        """
        flow = _flow(src)
        for attempt in (1, 2):
            with self.subTest(lowering=attempt):
                with self.assertRaises(LangSyntaxError) as caught:
                    WL.lower_workflow_ast(flow)
                self.assertIn("dependency cycle", str(caught.exception))


class ItComposesWithMergeTests(unittest.TestCase):
    """#722 refuses a reader that would see a partial fold; a barrier gives it
    the edges instead. One relation, two responses -- and the ordering between
    them is the whole of how they compose."""

    # closes: #578
    def test_a_folded_barrier_cell_is_not_refused(self):
        src = """
        workflow w {
            state total = 0i with { merge: "sum", barrier: true }
            step a { total += 1i; return "a" }
            step b { total += 2i; return "b" }
            step reader { return total }
        }
        """
        self.assertEqual(["a", "b"], _order_after(_step_map(_lower(src), "reader")))

    # closes: #578
    def test_a_folded_cell_without_barrier_is_still_refused(self):
        """The control. Without it the test above passes against a build that
        simply stopped checking folds."""
        src = """
        workflow w {
            state total = 0i with { merge: "sum" }
            step a { total += 1i; return "a" }
            step b { total += 2i; return "b" }
            step reader { return total }
        }
        """
        with self.assertRaises(LangSyntaxError) as caught:
            _lower(src)
        self.assertIn("partial fold", str(caught.exception))

    # closes: #578
    def test_the_fold_refusal_mentions_the_barrier_option(self):
        """A reader hitting #722's error should learn that declaring the cell a
        barrier is one of the ways out."""
        src = """
        workflow w {
            state total = 0i with { merge: "sum" }
            step a { total += 1i; return "a" }
            step reader { return total }
        }
        """
        with self.assertRaises(LangSyntaxError) as caught:
            _lower(src)
        self.assertIn("barrier: true", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
