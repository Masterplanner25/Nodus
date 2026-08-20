"""Every assignment form reaches workflow state, not three of the four.

A `state` cell is not a real variable -- the lowering rewrites reads and writes
of it into operations on a hidden map, so a write the rewriter does not
recognise silently resolves as an ordinary local that was never declared:

    step a { counter += 1i }        ->  Type error: Cannot add nil and int

`_StateRewriter` handled `Assign`, `IndexAssign` and `FieldAssign` and had never
heard of `CompoundAssign` (#518). The interesting part is not the missing case;
it is that three of four is the same shape as #487, where three of four name
declaration sites had never heard of `goal ... over ...`. So the guard here is
the same guard: `ASSIGNMENT_FORMS` names the set, and this file demands a worked
sample per member. A fifth form fails the suite until somebody decides what it
means for state.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.ast.ast_nodes import (  # noqa: E402
    ASSIGNMENT_FORMS,
    Assign,
    CompoundAssign,
    FieldAssign,
    IndexAssign,
    Int,
    Var,
)
from nodus.orchestration.workflow_lowering import _StateRewriter  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

CELL = "cell"
STATE = "__state"

# One write to `cell` per assignment form. Keyed by node type so the coverage
# claim below is checkable rather than asserted.
SAMPLES = {
    Assign: lambda: Assign(CELL, Int(1)),
    CompoundAssign: lambda: CompoundAssign(CELL, "+", Int(1)),
    IndexAssign: lambda: IndexAssign(Var(CELL), Int(0), Int(1)),
    FieldAssign: lambda: FieldAssign(Var(CELL), "f", Int(1)),
}


def identifiers(node, found=None):
    """Every name the tree still refers to as an identifier.

    Deliberately not "every `Var`": `CompoundAssign` carries its target as a
    bare `str` field with no `Var` node anywhere, which is exactly why a
    Var-only walk would have passed on the unfixed tree.
    """
    if found is None:
        found = set()
    if isinstance(node, (Var, Assign, CompoundAssign)):
        name = getattr(node, "name", None)
        if isinstance(name, str):
            found.add(name)
    for value in getattr(node, "__dict__", {}).values():
        if isinstance(value, (list, tuple)):
            for item in value:
                identifiers(item, found)
        elif hasattr(value, "__dict__"):
            identifiers(value, found)
    return found


class EveryFormIsCoveredTests(unittest.TestCase):
    def test_a_sample_exists_for_each_assignment_form(self):
        self.assertEqual(
            set(ASSIGNMENT_FORMS),
            set(SAMPLES),
            "a new assignment form was added to ASSIGNMENT_FORMS with no sample "
            "here -- decide what it means for a `state` cell and add one, or the "
            "state rewriter will pass it through untouched the way it did "
            "CompoundAssign (#518)",
        )

    # closes: #518
    def test_no_form_leaves_the_state_name_as_an_identifier(self):
        """After rewriting, `cell` may survive only as a string key on the state
        map. Any form that still refers to it by name resolves to an undeclared
        local at runtime and reads nil."""
        for form, build in SAMPLES.items():
            with self.subTest(form=form.__name__):
                rewriter = _StateRewriter({CELL}, STATE, initial_locals={STATE})
                rewritten = rewriter.rewrite_expr(build())
                self.assertNotIn(
                    CELL,
                    identifiers(rewritten),
                    f"{form.__name__} left `{CELL}` as an identifier -- the "
                    f"rewriter did not recognise this form, so it will resolve "
                    f"as a local that was never declared",
                )

    def test_the_walk_can_actually_see_a_leak(self):
        """The assertion above is only worth having if it fails when it should.
        An unrewritten sample must trip it -- otherwise a rewriter that returned
        its input unchanged would pass every subtest."""
        for form, build in SAMPLES.items():
            with self.subTest(form=form.__name__):
                self.assertIn(CELL, identifiers(build()))


class TheReportedProgramWorksTests(unittest.TestCase):
    """#518 as filed: `+=` accumulating into workflow state."""

    @staticmethod
    def _state(src):
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        result = runtime.run_source(src, filename="compound.nd")
        runtime.shutdown()
        assert result.get("ok"), result.get("error")
        return result

    # closes: #518
    def test_compound_assignment_accumulates_across_steps(self):
        src = """
workflow w {
    state counter = 0i
    step a { counter += 1i; return 1i }
    step b after a { counter += 1i; return 2i }
}
fn main() { let r = run_workflow(w); let s = r["state"]; print("\\(s["counter"])") }
"""
        self.assertEqual("2", self._state(src)["stdout"].strip())

    def test_it_agrees_with_the_form_it_is_documented_as_equivalent_to(self):
        """`x += e` and `x = x + e` differed only inside a step body, and only
        for state. Same program both ways, same answer."""
        template = """
workflow w {{
    state counter = 10i
    step a {{ {write}; return 1i }}
}}
fn main() {{ let r = run_workflow(w); let s = r["state"]; print("\\(s["counter"])") }}
"""
        compound = self._state(template.format(write="counter -= 4i"))["stdout"]
        expanded = self._state(template.format(write="counter = counter - 4i"))["stdout"]
        self.assertEqual("6", compound.strip())
        self.assertEqual(expanded.strip(), compound.strip())

    def test_a_step_local_is_still_a_local(self):
        """The rewrite is scoped to declared cells: a `let` of the same name
        inside the step must keep ordinary compound-assignment semantics and
        must not write through to state."""
        src = """
workflow w {
    state counter = 0i
    step a { let counter = 100i; counter += 5i; return counter }
}
fn main() {
    let r = run_workflow(w)
    let s = r["state"]
    print("state=\\(s["counter"]) returned=\\(r["steps"]["a"])")
}
"""
        self.assertEqual("state=0 returned=105", self._state(src)["stdout"].strip())


if __name__ == "__main__":
    unittest.main()
