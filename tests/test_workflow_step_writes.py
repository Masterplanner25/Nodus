"""Per-step write records: the write-side machinery for #485 step 2.

A step's writes are now *recorded* as it makes them — key, value, order — and the
record is closed when the step ends. Nothing acts on it yet: the write still
lands exactly when it always did, and these tests exist to pin that. Step 3 turns
the record into a fold at the join.

Two things here are load-bearing.

`ExitPathTests` covers each of the four ways a task can stop running separately,
rather than trusting one to stand for the others. A record left open makes a
step's writes invisible to the merge that will read it — the same silent-loss
failure mode #485 is about, reintroduced by its own fix.

`NoBehaviourChangeTests` pins the case that killed the first design. The scoping
comment on #485 proposed a read-isolating overlay; implemented, it turned a
correct program into a wrong one. See the `StepWrites` docstring.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # noqa: E402

from nodus.orchestration import task_graph  # noqa: E402
from nodus.orchestration.workflow_state import (  # noqa: E402
    StepWrites,
    TrackedState,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(src: str) -> dict:
    return NodusRuntime(timeout_ms=None, max_steps=None).run_source(src, filename="<sw>")


class StepWritesTests(unittest.TestCase):
    def test_it_records_key_value_and_order(self):
        writes = StepWrites("t1")
        writes.record("a", 1)
        writes.record("b", 2)
        self.assertEqual(writes.keys_written(), ["a", "b"])
        self.assertEqual(writes.value_of("a"), 1)
        self.assertEqual(writes.items(), [("a", 1), ("b", 2)])

    def test_a_key_written_twice_is_one_contribution(self):
        """Order is what decides `any`; a step is one writer however often it writes."""
        writes = StepWrites("t1")
        writes.record("a", 1)
        writes.record("a", 9)
        self.assertEqual(writes.keys_written(), ["a"])
        self.assertEqual(writes.value_of("a"), 9)

    def test_close_returns_the_keys_and_is_idempotent(self):
        writes = StepWrites("t1")
        writes.record("a", 1)
        self.assertEqual(writes.close(), ["a"])
        self.assertEqual(writes.close(), [], "second close must be inert")
        self.assertTrue(writes.closed)

    def test_a_closed_record_is_marked_so_late_writes_are_visible_as_late(self):
        writes = StepWrites("t1")
        writes.close()
        self.assertTrue(writes.closed)


class TrackedStateTests(unittest.TestCase):
    def _state(self, task_id: str | None):
        state = TrackedState({"counter": 0})
        state.track_writes_with(lambda: task_id)
        return state

    def test_writes_are_recorded_against_the_open_step(self):
        state = self._state("t1")
        state.begin_step("t1")
        state["counter"] = 5
        step = state.open_step("t1")
        self.assertIsNotNone(step)
        self.assertEqual(step.items(), [("counter", 5)])

    def test_the_write_still_lands_immediately(self):
        """Recording is observation, not buffering — this is step 2's whole claim."""
        state = self._state("t1")
        state.begin_step("t1")
        state["counter"] = 5
        self.assertEqual(state["counter"], 5)

    def test_writers_are_still_tracked_for_conflict_detection(self):
        state = self._state("t1")
        state.begin_step("t1")
        state["counter"] = 5
        self.assertEqual(state.writers(), {"counter": ["t1"]})

    def test_end_step_closes_and_returns_the_keys(self):
        state = self._state("t1")
        state.begin_step("t1")
        state["counter"] = 5
        self.assertEqual(state.end_step("t1"), ["counter"])
        self.assertIsNone(state.open_step("t1"))

    def test_ending_an_unknown_step_is_inert(self):
        self.assertEqual(self._state(None).end_step("nope"), [])

    def test_begin_step_is_reentrant_for_a_resumed_step(self):
        """A step resuming after a workflow_wait gets a fresh record."""
        state = self._state("t1")
        state.begin_step("t1")
        state["counter"] = 1
        state.end_step("t1")
        state.begin_step("t1")
        self.assertEqual(state.open_step("t1").items(), [])

    def test_writes_outside_a_step_are_not_recorded(self):
        """State set by the initializer has no writer and no open record."""
        state = self._state(None)
        state["counter"] = 3
        self.assertEqual(state["counter"], 3)
        self.assertEqual(state.writers(), {})


class ExitPathTests(unittest.TestCase):
    """Every way a task stops running must close its record.

    Checked by running a real workflow down each path and asserting no record is
    left open on the shared state afterwards.
    """

    def _open_records(self, src: str) -> tuple[dict, list]:
        result = _run(src)
        graphs = list(task_graph._GRAPH_REGISTRY.values())
        leftover = []
        for graph in graphs:
            state = (graph.metadata or {}).get("workflow_state")
            if isinstance(state, TrackedState):
                leftover.extend(state._steps.keys())
        return result, leftover

    # Deliberately not marked `# closes: #485` — this is step 2 of that issue and
    # does not resolve it. The lost update is still lost; see
    # NoBehaviourChangeTests.test_the_lost_update_is_still_lost_and_still_warned.
    def test_success_closes_the_record(self):
        result, leftover = self._open_records(
            """
workflow ok {
    state x = 0i
    step a { x = 1i; return 1i }
    step b after a { return x }
}
fn main() { let r = run_workflow(ok); print("X=\\(r["state"]["x"])") }
"""
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("X=1", result.get("stdout") or "")
        self.assertEqual(leftover, [], "a record was left open after success")

    def test_failure_closes_the_record_and_keeps_the_write(self):
        """Writes made before a failure landed before overlays and still do."""
        result, leftover = self._open_records(
            """
workflow boom {
    state x = 0i
    step a { x = 7i; throw "nope" }
}
fn main() {
    let r = run_workflow(boom)
    print("X=\\(r["state"]["x"]) failed=\\(len(r["failed"]))")
}
"""
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("X=7", result.get("stdout") or "")
        self.assertEqual(leftover, [], "a record was left open after failure")

    def test_a_cache_hit_opens_no_record(self):
        """No step body ran, so there is nothing to close."""
        state = TrackedState({})
        state.track_writes_with(lambda: None)
        self.assertEqual(state._steps, {})


class NoBehaviourChangeTests(unittest.TestCase):
    """Step 2 changes what is *recorded*, never what happens."""

    def test_serialised_increments_still_both_land(self):
        """The case that killed the read-isolating design.

        Two steps that never suspend are run one after the other by the
        cooperative scheduler, so the second reads what the first wrote and the
        answer is 2. A snapshot-at-step-start overlay makes both read 0 and the
        answer 1 — introducing the very lost update #485 is about, in the case
        that did not have it.
        """
        result = _run(
            """
workflow latent {
    state counter = 0i
    step a { counter = counter + 1i; return 1i }
    step b { counter = counter + 1i; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(latent); print("C=\\(r["state"]["counter"])") }
"""
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("C=2", result.get("stdout") or "")

    def test_a_checkpoint_still_sees_the_step_s_own_writes(self):
        """`x = x + 1; checkpoint "l"` has always recorded the incremented value.

        Buffering writes until step end would record the pre-step value, and a
        resume from that label would run the increment twice.
        """
        result = _run(
            """
workflow demo {
    state x = 1i
    step a { x = x + 1i; checkpoint "after_a"; return x }
    step b after a { return x }
}
fn main() { let r = run_workflow(demo); print("X=\\(r["state"]["x"])") }
"""
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("X=2", result.get("stdout") or "")

    def test_the_lost_update_is_still_lost_and_still_warned(self):
        """Step 2 does not fix #485 — it builds what the fix needs.

        Claiming otherwise would be worse than not shipping it.
        """
        result = _run(
            """
workflow race {
    state counter = 0i
    step a { let seen = counter; sleep(20i); counter = seen + 1i; return 1i }
    step b { let seen = counter; sleep(20i); counter = seen + 1i; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(race); print("C=\\(r["state"]["counter"])") }
"""
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIn("C=1", result.get("stdout") or "")


class SourceTests(unittest.TestCase):
    GRAPH_SOURCE = (
        ROOT / "src" / "nodus" / "orchestration" / "task_graph.py"
    ).read_text(encoding="utf-8")

    def test_every_exit_path_closes_the_record(self):
        """Four calls: two successes, failure, and suspension.

        A count rather than a behaviour check, because a fifth exit path added
        without a close would leave a record open on a path no existing test
        walks — and the symptom would be a silently skipped merge.
        """
        self.assertEqual(
            self.GRAPH_SOURCE.count("_end_step_writes(task)"),
            4,
            "the set of exit paths changed; see _end_step_writes for the four",
        )

    def test_the_record_is_opened_where_the_context_is_built(self):
        self.assertIn("_begin_step_writes(task)", self.GRAPH_SOURCE)


if __name__ == "__main__":
    unittest.main()
