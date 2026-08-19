"""`step ... when <predicate>` — a guard on the step itself (#471).

Workflow edges were unconditional: `step b after a` meant *b runs when a
completes*, with no way to say *and only if*. Data-dependent branching was
therefore expressible only inside a step body, where it is invisible to the
graph.

The guard uses the restricted predicate grammar a goal's `until` uses, and for
the reason stated in the parser: a general expression would be compiled code,
invisible to `plan_workflow`, and would make the checkpoint check best-effort.
Restricted, it stays data -- so a typo is a compile error rather than a step that
silently never runs.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.lexer import CONTEXTUAL_KEYWORDS, tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.orchestration.task_graph import JOIN_ON_STATES  # noqa: E402
from nodus.runtime.diagnostics import LangSyntaxError  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.tooling.formatter import format_source  # noqa: E402


def _run(source: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        cwd = os.getcwd()
        os.chdir(td)
        try:
            return NodusRuntime(timeout_ms=None, max_steps=None).run_source(source)
        finally:
            os.chdir(cwd)


DEPLOYMENT = """
workflow deployment {{
    state score = 0
    step review {{
        score = {score}
        let s = workflow_state()
        if (s["score"] > 80) {{ checkpoint "approved" }}
        return s["score"]
    }}
    step deploy after review when reached("approved") {{ print("DEPLOY"); return "deployed" }}
    step reject after review when !reached("approved") {{ print("REJECT"); return "rejected" }}
    step notify after deploy{on} {{ print("NOTIFY"); return "notified" }}
}}
fn main() {{
    let r = run_workflow(deployment)
    let st = r["statuses"]
    print("S=\\(st)")
}}
"""


def _statuses(score: int, on: str = "") -> str:
    result = _run(DEPLOYMENT.format(score=score, on=on))
    stdout = result.get("stdout") or ""
    for line in stdout.splitlines():
        if line.startswith("S="):
            return line
    raise AssertionError(f"no status line in {stdout!r} (error={result.get('error')})")


class AGuardSelectsWhichBranchRunsTests(unittest.TestCase):
    """Falsifiable: with `guard_holds` hardwired to True, the skipped branch runs
    and every assertion here about `"skipped"` fails."""

    def test_the_branch_whose_condition_holds_runs(self):
        rendered = _statuses(score=90)
        self.assertIn('"deploy": "completed"', rendered)
        self.assertIn('"reject": "skipped"', rendered)

    def test_negation_selects_the_other_branch(self):
        rendered = _statuses(score=50)
        self.assertIn('"deploy": "skipped"', rendered)
        self.assertIn('"reject": "completed"', rendered)

    def test_only_the_selected_branch_has_an_effect(self):
        result = _run(DEPLOYMENT.format(score=50, on=""))
        stdout = result.get("stdout") or ""
        self.assertIn("REJECT", stdout)
        self.assertNotIn("DEPLOY", stdout)


class ASkipCascadesUnlessDeclaredOtherwiseTests(unittest.TestCase):
    """`after` reads as *needs*, so a step whose dependency never ran should not
    fire with `nil` for it.

    This is Airflow's default rather than Argo's, and it is a departure from what
    I argued on #471 before `on:` existed. Argo treats a skipped upstream as
    satisfying the dependency because it has no way for the downstream task to say
    otherwise; Nodus does, so the safe default plus an explicit escape is
    available and the surprising default is not needed.
    """

    def test_a_step_below_a_skipped_step_is_skipped(self):
        rendered = _statuses(score=50)
        self.assertIn('"deploy": "skipped"', rendered)
        self.assertIn('"notify": "skipped"', rendered)

    def test_it_does_not_cascade_when_the_step_accepts_a_skipped_dependency(self):
        rendered = _statuses(score=50, on=' with { on: ["completed", "skipped"] }')
        self.assertIn('"deploy": "skipped"', rendered)
        self.assertIn('"notify": "completed"', rendered)

    def test_a_skipped_step_is_not_a_broken_graph(self):
        """A step left pending used to fall through to the cycle/missing-dependency
        branch, so the run returned an err record rather than a result."""
        result = _run(DEPLOYMENT.format(score=50, on=""))
        self.assertIsNone(result.get("error"), msg=result.get("error"))

    def test_skipped_is_an_accepted_join_outcome(self):
        self.assertIn("skipped", JOIN_ON_STATES)


class ATypoIsACompileErrorTests(unittest.TestCase):
    """The whole reason the grammar is restricted. A guard naming a checkpoint
    nothing records would never hold, and would look exactly like a condition that
    simply did not apply this run."""

    def _parse(self, source: str):
        return Parser(tokenize(source)).parse()

    def test_a_checkpoint_no_step_records_is_rejected(self):
        with self.assertRaises(LangSyntaxError) as caught:
            self._parse(
                """
workflow w {
    step a { checkpoint "approved"; return 1i }
    step b after a when reached("aproved") { return 2i }
}
"""
            )
        message = str(caught.exception)
        self.assertIn("aproved", message)
        self.assertIn("never records", message)
        self.assertIn('"approved"', message)

    def test_a_checkpoint_that_exists_is_accepted(self):
        self._parse(
            """
workflow w {
    step a { checkpoint "approved"; return 1i }
    step b after a when reached("approved") { return 2i }
}
"""
        )


class TheGuardSurvivesTheFormatterTests(unittest.TestCase):
    """`nodus fmt` used to write output that no longer parsed for nodes it did not
    know (#427). A new step field is exactly that shape."""

    SOURCE = """workflow w {
    step a { checkpoint "ok"; return 1i }
    step b after a when reached("ok") { return 2i }
    step c after a when !reached("ok") { return 3i }
}
"""

    def test_the_guard_is_preserved(self):
        formatted = format_source(self.SOURCE)
        self.assertIn('when reached("ok")', formatted)
        self.assertIn('when !reached("ok")', formatted)

    def test_formatting_is_idempotent_and_still_parses(self):
        once = format_source(self.SOURCE)
        twice = format_source(once)
        self.assertEqual(once, twice)
        Parser(tokenize(once)).parse()


class WhenRemainsUsableAsAnIdentifierTests(unittest.TestCase):
    """Contextual, like the goal keywords. Reserving `when` would break existing
    programs for no gain."""

    def test_when_is_contextual_not_reserved(self):
        self.assertIn("when", CONTEXTUAL_KEYWORDS)

    def test_a_variable_called_when_still_works(self):
        result = _run(
            """
fn main() {
    let when = 42i
    print("when=\\(when)")
}
"""
        )
        self.assertIn("when=42", result.get("stdout") or "")


if __name__ == "__main__":
    unittest.main()
