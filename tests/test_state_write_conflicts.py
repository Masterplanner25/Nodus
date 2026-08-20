"""Concurrent writes to one state key are reported instead of silently losing one.

Two fan-out branches that read a state key, yield, and write it back lose one of
the writes. The run reports `ok`, nothing appears in `failed`, and the value is
wrong (#485). The read-modify-write window is opened by *any* suspension, so the
cooperative scheduler makes the obvious test pass — a step body that never yields
is serialised — and teaches you that concurrent state writes are safe. They are
safe until a step does something real.

This does not repair the lost write. Repairing it means changing what a state
write *is*, so a branch contributes a value the runtime applies at the join
rather than assigning into a slot another branch is halfway through reading —
a state-model change that wants deciding alongside the type (#479) and durability
(#498) axes on the same declaration. Reporting is the half that is cheap now.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.orchestration.workflow_state import (  # noqa: E402
    TrackedState,
    concurrent_write_conflicts,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        cwd = os.getcwd()
        os.chdir(td)
        try:
            return NodusRuntime(timeout_ms=None, max_steps=None).run_source(source)
        finally:
            os.chdir(cwd)


RACE = """
workflow race {
    state counter = 0i
    step a { let seen = counter; sleep(20i); counter = seen + 1i; return 1i }
    step b { let seen = counter; sleep(20i); counter = seen + 1i; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(race); let s = r["state"]; print("STATE=\\(s)") }
"""


class TheLostUpdateIsAnnouncedTests(unittest.TestCase):
    """Falsifiable: without the `TrackedState` wrap the run is silent, and the
    only evidence of a lost write is a wrong number nobody is looking at."""

    def setUp(self):
        self.result = _run(RACE)

    def test_the_write_is_still_lost(self):
        """Recorded deliberately. This reports; it does not repair, and a later
        change that starts repairing should fail here and be looked at."""
        self.assertIn('STATE={"counter": 1}', self.result.get("stdout") or "")

    def test_a_warning_names_both_steps_and_the_winner(self):
        stderr = self.result.get("stderr") or ""
        self.assertIn("both wrote state 'counter'", stderr)
        self.assertIn("a", stderr)
        self.assertIn("b", stderr)
        self.assertIn("write survives", stderr)

    def test_the_run_still_succeeds(self):
        """A warning, not a failure. Two branches writing one key can be
        deliberate when the author knows they agree, and there is currently no
        way to say so — refusing would break correct workflows to catch
        incorrect ones."""
        self.assertIsNone(self.result.get("error"))
        self.assertNotIn('"counter"', (self.result.get("stdout") or "").split("STATE=")[0])


class OrderedStepsAreNotReportedTests(unittest.TestCase):
    """The false positive that drove the design.

    A first attempt compared recorded start/finish timings and flagged a plain
    sequential `a -> b -> c` writing one key: those steps are instant, so their
    millisecond timestamps are identical and every interval overlaps. Wall-clock
    cannot separate "sequential and fast" from "concurrent"; dependency order can.
    """

    def test_a_sequential_chain_writing_one_key_is_silent(self):
        result = _run(
            """
workflow sequential {
    state log = ""
    step a { log = log + "a"; return 1i }
    step b after a { log = log + "b"; return 2i }
    step c after b { log = log + "c"; return 3i }
}
fn main() { let r = run_workflow(sequential); let s = r["state"]; print("STATE=\\(s)") }
"""
        )
        self.assertIn('STATE={"log": "abc"}', result.get("stdout") or "")
        self.assertNotIn("both wrote state", result.get("stderr") or "")

    def test_transitive_ordering_counts(self):
        """`c` is ordered after `a` through `b`, not directly."""
        result = _run(
            """
workflow chain {
    state v = 0i
    step a { v = 1i; return 1i }
    step b after a { return 2i }
    step c after b { v = 3i; return 3i }
}
fn main() { let r = run_workflow(chain); return nil }
"""
        )
        self.assertNotIn("both wrote state", result.get("stderr") or "")

    def test_concurrent_steps_writing_different_keys_are_silent(self):
        result = _run(
            """
workflow disjoint {
    state x = 0i
    state y = 0i
    step a { sleep(20i); x = 1i; return 1i }
    step b { sleep(20i); y = 2i; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(disjoint); let s = r["state"]; print("STATE=\\(s)") }
"""
        )
        self.assertIn('"x": 1', result.get("stdout") or "")
        self.assertNotIn("both wrote state", result.get("stderr") or "")


class ItWarnsBeforeTheBugHappensTests(unittest.TestCase):
    """Two independent steps that happen to be serialised — because neither
    yielded — are still declared concurrent, and are still reported.

    That is the point rather than an accident. The scheduler serialises a step
    body with no suspension, so the obvious test passes and the author concludes
    concurrent writes are safe. The warning has to arrive before the step grows
    its first `sleep` or agent call, because that is the only moment it is cheap
    to act on.
    """

    def test_a_race_with_no_yield_is_still_reported(self):
        result = _run(
            """
workflow latent {
    state counter = 0i
    step a { counter = counter + 1i; return 1i }
    step b { counter = counter + 1i; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(latent); let s = r["state"]; print("STATE=\\(s)") }
"""
        )
        # No yield, so both increments actually land -- the answer is right today.
        self.assertIn('STATE={"counter": 2}', result.get("stdout") or "")
        self.assertIn("both wrote state 'counter'", result.get("stderr") or "")


class TheDetectorItselfTests(unittest.TestCase):
    def test_it_ignores_a_plain_dict(self):
        self.assertEqual([], concurrent_write_conflicts({}, lambda a, b: False))

    def test_one_writer_is_never_a_conflict(self):
        state = TrackedState()
        state.track_writes_with(lambda: "task_1")
        state["k"] = 1
        state["k"] = 2
        self.assertEqual([], concurrent_write_conflicts(state, lambda a, b: False))

    def test_writes_outside_a_step_have_no_writer(self):
        """State set by the initializer runs with no task in scope, and must not
        become a phantom party to a conflict."""
        state = TrackedState()
        state["k"] = 0                      # no writer injected yet
        state.track_writes_with(lambda: "task_1")
        state["k"] = 1
        self.assertEqual({"k": ["task_1"]}, state.writers())


if __name__ == "__main__":
    unittest.main()
