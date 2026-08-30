"""The plan-then-act handoff example runs, and means what the guide says (#465).

`examples/plan_then_act.nd` is the deliverable for this issue — the issue's open
question was whether the pattern should be a stdlib function or a worked example,
and the answer was the example, because the property being claimed (a handoff
that is inspectable on disk and resumable) comes from *being a workflow*. A
wrapper function would hide the workflow and take that property with it.

That makes the example a real artifact rather than illustration, so it gets a
test. The guide's copy of the pattern is executed by `nodus_gate --runtime`; the
file under `examples/` is not covered by anything else.

The assertions are on the two properties the guide claims, not merely on the file
running: the plan reaches the second step, and the checkpoint that makes the
handoff resumable is actually recorded.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "plan_then_act.nd"


def _run_example() -> dict:
    return NodusRuntime(timeout_ms=None).run_source(_EXAMPLE.read_text(encoding="utf-8"))


# closes: #465
class ExampleRunsTests(unittest.TestCase):
    def test_the_example_file_exists(self):
        self.assertTrue(_EXAMPLE.is_file(), f"{_EXAMPLE} is the deliverable for #465")

    def test_it_runs_clean(self):
        result = _run_example()
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("failed: []", result.get("stdout") or "")

    def test_the_plan_reaches_the_second_step(self):
        """The handoff itself. Both steps completing is not the claim — the
        claim is that what the first produced is what the second consumed."""
        text = _run_example().get("stdout") or ""
        self.assertIn("applied: 1. rename the symbol", text,
                      "the second step did not consume the first step's plan")

    def test_the_checkpoint_is_recorded(self):
        """What makes the handoff resumable. A run interrupted after planning
        re-enters at `planned` rather than re-planning — and without the
        checkpoint in the result there is nothing to re-enter at."""
        text = _run_example().get("stdout") or ""
        self.assertIn("planned", text)
        self.assertIn("plan_it", text)


# closes: #465
class TheShapeIsAWorkflowTests(unittest.TestCase):
    """The decision the issue asked for, asserted on the source.

    A behavioural test cannot tell a workflow from a helper that produces the
    same output, and the distinction is the whole answer: only the workflow form
    is inspectable on disk and composable with `goal … over …`.
    """

    def test_the_example_declares_a_workflow_with_a_dependency(self):
        source = _EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("workflow plan_then_act", source)
        self.assertIn("after plan_it", source,
                      "the dependency is what orders the handoff")

    def test_no_handoff_helper_was_added_to_the_stdlib(self):
        """The rejected alternative, pinned so it is not quietly added later.

        A `handoff(planner, editor, request)` function would fix the shape at two
        actors and one hop, and hide the workflow that makes the pattern worth
        having.
        """
        stdlib = Path(__file__).resolve().parents[1] / "src" / "nodus" / "stdlib"
        self.assertFalse((stdlib / "handoff.nd").exists())
        self.assertFalse((stdlib / "patterns.nd").exists())


if __name__ == "__main__":
    unittest.main()
