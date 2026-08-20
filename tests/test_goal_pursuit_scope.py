"""`goal NAME over WORKFLOW` introduces NAME, from inside a function too (#487).

`workflow` and the plain `goal` form both bound the name they declare. The
stopping-condition form -- the v5 flagship construct -- did not, so calling it
from inside a function, which is the normal place to call it from, failed as an
undefined variable and it only worked at top level.

The interesting part is *where* it was missing. The compiler's own hoisting pass
had the case all along; three other places that register a declared name did not.
That is the shape `CLAUDE.md § The recurring bug shape` describes -- a correct
mechanism with sibling paths that bypass it.

Adding the missing case to each site fixes the instance and leaves the class: four
places enumerating node types independently drift again the next time a form is
added. They now share one answer to "does this declare a name" --
`FLOW_DECLARATIONS` and `declared_flow_name` in `ast_nodes` -- and the tests here
drive off that tuple, so a new form fails until every site handles it.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.ast.ast_nodes import (  # noqa: E402
    FLOW_DECLARATIONS,
    GoalDef,
    GoalPursuit,
    WorkflowDef,
    declared_flow_name,
)
from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.tooling.loader import collect_module_info  # noqa: E402

PURSUIT = """
workflow tune {
    state passes = 0
    step work {
        passes = passes + 1
        let s = workflow_state()
        checkpoint "adjusted"
        if (s["passes"] >= 2) { checkpoint "good_enough" }
        return s["passes"]
    }
}

goal reach over tune {
    until reached("good_enough")
    budget { max_iterations: 4, deadline_ms: 30000 }
}
"""


def _run(source: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        cwd = os.getcwd()
        os.chdir(td)
        try:
            return NodusRuntime(timeout_ms=None, max_steps=None).run_source(source)
        finally:
            os.chdir(cwd)


class APursuitIsUsableFromInsideAFunctionTests(unittest.TestCase):
    """Falsifiable: dropping the `GoalPursuit` case from either def collector
    restores `Undefined variable: reach` and fails these."""

    # closes: #487
    def test_run_goal_resolves_the_pursuit_name_inside_a_function(self):
        result = _run(
            PURSUIT
            + """
fn main() {
    let r = run_goal(reach)
    print("SATISFIED=\\(r["goal_satisfied"])")
}
"""
        )
        self.assertIsNone(result.get("error"), msg=result.get("error"))
        self.assertIn("SATISFIED=true", result.get("stdout") or "")

    def test_it_still_works_at_top_level(self):
        result = _run(
            PURSUIT
            + """
let r = run_goal(reach)
print("SATISFIED=\\(r["goal_satisfied"])")
"""
        )
        self.assertIsNone(result.get("error"), msg=result.get("error"))
        self.assertIn("SATISFIED=true", result.get("stdout") or "")

    def test_it_resolves_from_a_nested_function(self):
        result = _run(
            PURSUIT
            + """
fn inner() { return run_goal(reach) }
fn main() {
    let r = inner()
    print("SATISFIED=\\(r["goal_satisfied"])")
}
"""
        )
        self.assertIsNone(result.get("error"), msg=result.get("error"))
        self.assertIn("SATISFIED=true", result.get("stdout") or "")

    def test_a_genuinely_undefined_name_is_still_rejected(self):
        """Falsifiability guard: the fix must not have made every name resolve."""
        result = _run(
            PURSUIT
            + """
fn main() { let r = run_goal(no_such_goal); return nil }
"""
        )
        error = result.get("error") or {}
        message = error.get("message", "") if isinstance(error, dict) else str(error)
        self.assertIn("no_such_goal", message)


class EveryDeclaringFormResolvesFromEverySiteTests(unittest.TestCase):
    """Hold every name-declaring form to the same standard, behaviourally.

    Four places answer "does this statement declare a name": the compiler's
    hoisting pass, the module loader's def collector, the tooling loader and the
    analyzer. They agreed on `workflow` and `goal` and three of them had never
    heard of `goal ... over ...`, so the name resolved at top level and nowhere
    else.

    Asserting that each *file* contains a case would pin the current shape of the
    code rather than the property, and would go green the moment someone wrote the
    branch -- correct or not. So this drives off `FLOW_DECLARATIONS` instead and
    exercises the real pipeline: a form added to that tuple fails
    `test_every_declaring_form_is_covered` until someone writes its case here, and
    then fails the resolution test until all four sites handle it.
    """

    SOURCES = {
        WorkflowDef: """
workflow thing { step s { return 1i } }
fn main() { let r = run_workflow(thing); print("OK") }
""",
        GoalDef: """
goal thing { step s { return 1i } }
fn main() { let r = run_goal(thing); print("OK") }
""",
        # Rename only the declaration: a bare `reach` -> `thing` also rewrites
        # `reached("good_enough")` inside the predicate and the goal stops parsing.
        GoalPursuit: (
            PURSUIT.replace("goal reach over", "goal thing over")
            + '\nfn main() { let r = run_goal(thing); print("OK") }\n'
        ),
    }

    def test_every_declaring_form_is_covered(self):
        """The guard that gives the tests below their reach."""
        self.assertEqual(
            set(FLOW_DECLARATIONS),
            set(self.SOURCES),
            "a form was added to FLOW_DECLARATIONS without a case here; add one so "
            "the resolution test below actually exercises it",
        )

    def test_each_form_resolves_from_inside_a_function(self):
        for form, source in self.SOURCES.items():
            with self.subTest(form=form.__name__):
                result = _run(source)
                self.assertIsNone(result.get("error"), msg=result.get("error"))
                self.assertIn("OK", result.get("stdout") or "")

    def test_the_shared_predicate_answers_for_every_form(self):
        """`declared_flow_name` is the single place the four sites now consult."""
        for form in FLOW_DECLARATIONS:
            with self.subTest(form=form.__name__):
                stmts = Parser(tokenize(self.SOURCES[form])).parse()
                declared = [
                    declared_flow_name(s) for s in stmts if isinstance(s, form)
                ]
                self.assertEqual(["thing"], declared)

    def test_it_answers_none_for_anything_else(self):
        stmts = Parser(tokenize("let x = 1i\n")).parse()
        self.assertTrue(all(declared_flow_name(s) is None for s in stmts))

    def test_the_tooling_collector_sees_every_form(self):
        """Covered directly, because the end-to-end tests do not reach it.

        `tooling/loader.py` serves `nodus check`'s diagnostics and the LSP, not
        `run_source` -- so the resolution tests above exercise the compiler and
        the runtime module loader and never touch it. That gap is not
        hypothetical: while consolidating these sites I left `declared_flow_name`
        unimported there, and every test above still passed. Only `ruff` caught
        the NameError, and a linter is not a guarantee that a code path works.
        """
        for form, source in self.SOURCES.items():
            with self.subTest(form=form.__name__):
                stmts = Parser(tokenize(source)).parse()
                info = collect_module_info(stmts, "m", "m")
                self.assertIn("thing", info.defs)


class TheParserProducesThePursuitNodeTests(unittest.TestCase):
    """Cheap guard that the tests above are testing something real -- if the
    parser stopped producing `GoalPursuit`, every assertion here would pass while
    the feature was gone."""

    def test_a_pursuit_parses_to_a_named_node(self):
        stmts = Parser(tokenize(PURSUIT)).parse()
        pursuits = [s for s in stmts if type(s).__name__ == "GoalPursuit"]
        self.assertEqual(1, len(pursuits))
        self.assertEqual("reach", pursuits[0].name)


if __name__ == "__main__":
    unittest.main()
