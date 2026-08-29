"""A pass that ended `failed` cannot satisfy a goal's `until` (#642).

`until` is evaluated against the checkpoints a pass recorded, and a checkpoint
recorded *before* a `throw` still counted — so a goal stopped and reported
`goal_satisfied: true` on a run that ended `failed`.

That was not an alternative policy, it was an artefact: the goal loop **already
retries a failed pass** (`test_a_failed_pass_is_still_retried` below), so a goal
stopped only because the `checkpoint` happened to sit before the `throw`. Swap
those two lines and the identical workflow keeps iterating. Termination that
depends on statement order inside a failing step is not a contract anyone chose.

**The trap for anyone changing this: "a failed pass does not satisfy" is not "a
failed pass ends the goal."** Ending the loop on failure passes the bug cases and
breaks the retry case, which is current, correct, and the whole reason this
decision went the way it did. `test_a_failed_pass_is_still_retried` is the guard
against that fix.

Note this is a **behaviour change**: the affected cases now return the
`budget_exhausted` err record rather than a success-shaped result map. That is
consistent with the invariant already stated at that branch — a goal that ran out
of budget has not met its objective and must never return a success-shaped
result.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> str:
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try:
            result = NodusRuntime(timeout_ms=None).run_source(source)
        finally:
            os.chdir(cwd)
    assert result["ok"], result.get("error")
    return result.get("stdout") or ""


GOAL = """
goal reach over tune { until reached("%(label)s") budget { max_iterations: 3 } }
fn main() { let r = run_goal(reach); print("R=\\(r)") }
"""


class AFailedPassDoesNotSatisfyTests(unittest.TestCase):
    # closes: #642
    def test_a_checkpoint_recorded_before_a_throw_does_not_satisfy(self):
        """Case A: the step that recorded the label is the one that threw."""
        out = _run(
            'workflow tune { step attempt { checkpoint "good_enough"; throw "nope" } }\n'
            + GOAL % {"label": "good_enough"}
        )
        self.assertIn("exhausted its budget", out)
        self.assertNotIn("goal_satisfied", out)

    def test_a_later_step_failing_does_not_satisfy(self):
        """Case D: the label's step completed; a downstream step failed.

        The goal wraps a *workflow*, not a step, so the unit that must succeed is
        the run.
        """
        out = _run(
            "workflow tune {\n"
            '    step a { checkpoint "good_enough"; return 1i }\n'
            '    step b after a { throw "nope" }\n'
            "}\n" + GOAL % {"label": "good_enough"}
        )
        self.assertIn("exhausted its budget", out)

    def test_it_spends_its_budget_rather_than_stopping_at_one(self):
        """It keeps trying — the failure is reported after the budget, not instead of it."""
        out = _run(
            'workflow tune { step attempt { checkpoint "good_enough"; throw "nope" } }\n'
            + GOAL % {"label": "good_enough"}
        )
        self.assertIn("after 3 iteration(s)", out)


class WhatMustNotChangeTests(unittest.TestCase):
    def test_a_failed_pass_is_still_retried(self):
        """**The guard.** Fails if someone implements this by ending the goal.

        A workflow that throws on pass 1 and succeeds on pass 2 must still report
        satisfied, at iteration 2. This is what makes the decision above correct
        rather than arbitrary: the loop already treats a failed pass as an
        attempt to re-make.
        """
        out = _run(
            "workflow tune {\n"
            "    state tries = 0i\n"
            "    step attempt {\n"
            "        tries = tries + 1i\n"
            '        checkpoint "progress"\n'
            '        if (tries < 2i) { throw "flaky" }\n'
            '        checkpoint "done"\n'
            "        return 1i\n"
            "    }\n"
            "}\n" + GOAL % {"label": "done"}
        )
        self.assertIn('"goal_satisfied": true', out)
        self.assertIn('"iterations": 2', out)
        self.assertIn('"failed": []', out)

    def test_a_clean_pass_still_satisfies(self):
        out = _run(
            'workflow tune { step attempt { checkpoint "good_enough"; return 1i } }\n'
            + GOAL % {"label": "good_enough"}
        )
        self.assertIn('"goal_satisfied": true', out)

    def test_a_tolerated_failure_still_satisfies(self):
        """`allow_failure` means the run *completes*, so it needs no special case.

        Checked rather than assumed: the gate reads `failed`, which is empty for a
        tolerated failure — the step appears under `tolerated` instead.
        """
        out = _run(
            "workflow tune {\n"
            '    step flaky with { allow_failure: true } { throw "tolerated" }\n'
            '    step ok after flaky with { on: ["failed"] } { checkpoint "good_enough"; return 1i }\n'
            "}\n" + GOAL % {"label": "good_enough"}
        )
        self.assertIn('"goal_satisfied": true', out)
        self.assertIn('"tolerated": ["flaky"]', out)


if __name__ == "__main__":
    unittest.main()
