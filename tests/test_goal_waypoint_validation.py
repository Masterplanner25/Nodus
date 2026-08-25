"""A goal's workflow must record a checkpoint on every pass (#500).

A `goal ... over ...` iterates by resuming from the last checkpoint its
workflow reached this pass -- so the natural formulation, checkpoint only when
the condition is met, records nothing on every other pass and halted the goal
after one iteration with its budget untouched. The compiler now refuses that
shape with the remedy; the runtime error (the backstop for shapes the
conservative check accepts, e.g. a waypoint step skipped by an `on:` filter)
names the remedy too.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

BAD = """
workflow tune {
    state tries = 0
    step look {
        tries = tries + 1
        let s = workflow_state()
        if (s["tries"] >= 3) { checkpoint "good_enough" }
        return s["tries"]
    }
}
goal reach over tune {
    until reached("good_enough")
    budget { max_iterations: 5, deadline_ms: 30000 }
}
fn main() { let r = run_goal(reach) }
"""

GOOD = """
workflow tune {
    state tries = 0
    step look {
        tries = tries + 1
        let s = workflow_state()
        checkpoint "looked"
        if (s["tries"] >= 3) { checkpoint "good_enough" }
        return s["tries"]
    }
}
goal reach over tune {
    until reached("good_enough")
    budget { max_iterations: 5, deadline_ms: 30000 }
}
fn main() {
    let r = run_goal(reach)
    let n = r["iterations"]
    print("ITER=\\(n)")
}
"""

GUARDED_WAYPOINT = """
workflow tune {
    step probe { checkpoint "probed"; return 1i }
    step waypoint after probe when reached("probed") { checkpoint "looked"; return 2i }
}
"""

ONLY_GUARDED_WAYPOINT = """
workflow tune {
    step probe { let x = 1i; if (x > 0i) { checkpoint "probed" }; return 1i }
    step waypoint after probe when reached("probed") { checkpoint "looked"; return 2i }
}
"""


# closes: #500
class GoalWaypointValidationTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._td.name)
        self.addCleanup(self._restore)

    def _restore(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def test_checkpoint_only_on_success_is_a_compile_error(self):
        result = NodusRuntime(timeout_ms=None).run_source(BAD)
        self.assertFalse(result["ok"])
        text = str(result)
        self.assertIn("cannot iterate", text)
        self.assertIn("every checkpoint in 'tune' is conditional", text)
        self.assertIn("runs on every pass", text)

    def test_a_workflow_with_a_waypoint_iterates_to_the_condition(self):
        """Falsifiability control: the refusal must not catch the working
        shape, and the goal must actually loop -- the failure it replaces was
        a halt after one pass with the budget untouched."""
        result = NodusRuntime(timeout_ms=None).run_source(GOOD)
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("ITER=3", result.get("stdout") or "")

    def test_a_when_guarded_step_does_not_count_as_unconditional(self):
        """The step itself may never run, so a statement-level checkpoint
        inside it is still conditional. `probe`'s own unconditional
        checkpoint is what makes the first shape acceptable; with only an
        `if`-nested one, the guarded step's waypoint alone must not count."""
        from nodus.frontend.goal_validation import has_unconditional_checkpoint
        from nodus.frontend.lexer import tokenize
        from nodus.frontend.parser import Parser

        def flow(source: str):
            ast = Parser(tokenize(source)).parse()
            return [s for s in ast if type(s).__name__ == "WorkflowDef"][0]

        self.assertTrue(has_unconditional_checkpoint(flow(GUARDED_WAYPOINT)))
        self.assertFalse(has_unconditional_checkpoint(flow(ONLY_GUARDED_WAYPOINT)))

    def test_the_guides_own_examples_still_compile(self):
        """Both §7.1 examples carry the waypoint; the check must accept them."""
        result = NodusRuntime(timeout_ms=None).run_source(GOOD)
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
