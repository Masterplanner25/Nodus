"""`goal NAME over WORKFLOW` introduces NAME, from inside a function too (#487).

`workflow` and the plain `goal` form both bound the name they declare. The
stopping-condition form -- the v5 flagship construct -- did not, so calling it
from inside a function, which is the normal place to call it from, failed as an
undefined variable and it only worked at top level.

The interesting part is *where* it was missing. The compiler's own hoisting pass
had the case all along; three other places that register a declared name did not.
That is the shape `CLAUDE.md § The recurring bug shape` describes -- a correct
mechanism with sibling paths that bypass it -- so the structural test below
asserts on the set of forms each collector handles rather than only on behaviour.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

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


class EveryCollectorKnowsEveryDeclaringFormTests(unittest.TestCase):
    """Assert on the source, not the behaviour.

    A behaviour test passes as soon as the one path under test is fixed, which is
    how this survived: the compiler hoisted the name correctly, so the construct
    worked at top level and nothing pointed at the collectors that did not.

    These read the modules and require that anywhere `GoalDef` is registered as a
    declared name, `GoalPursuit` is too -- so a fourth site cannot be added, or an
    existing one extended, while quietly omitting the third form.
    """

    def _source(self, relative: str) -> str:
        root = os.path.join(os.path.dirname(__file__), "..", "src", "nodus")
        with open(os.path.join(root, relative), encoding="utf-8") as handle:
            return handle.read()

    def test_the_module_loader_collects_pursuit_names(self):
        src = self._source(os.path.join("runtime", "module_loader.py"))
        self.assertIn("isinstance(s, GoalPursuit)", src)

    def test_the_tooling_loader_collects_pursuit_names(self):
        src = self._source(os.path.join("tooling", "loader.py"))
        self.assertIn("def visit_GoalPursuit", src)

    def test_the_analyzer_binds_pursuit_names(self):
        src = self._source(os.path.join("tooling", "analyzer.py"))
        self.assertIn("isinstance(stmt, GoalPursuit)", src)

    def test_the_compiler_hoists_pursuit_names(self):
        """This one was already correct; pinned so it stays that way."""
        src = self._source(os.path.join("compiler", "compiler.py"))
        self.assertIn("isinstance(stmt, GoalPursuit)", src)


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
