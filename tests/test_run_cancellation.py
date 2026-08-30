"""Run-level cancellation, and the run-status vocabulary (#395 §7).

The coroutine verbs (`cancel(t)` / `wait(t)`) stop one task. This is the other
half — stopping a *run* — and it is the one an embedder asked for: "cancel a
workflow run in progress".

Two things are pinned here that a happy-path test would miss:

  * **the vocabulary is named once.** `REHYDRATABLE` was defined independently in
    `store.py` and `runner.py` and was equal by coincidence, with the members
    listed a third time as `_KNOWN_RUN_STATUSES`. Adding an eighth status is
    exactly when that costs something: four edits, and the one you miss is
    silent. The sets are now derived from one tuple and this asserts they stay
    partitioned.
  * **`cancelled` is terminal and NOT rehydratable.** A cancelled run that comes
    back on the next sweep has un-cancelled itself, and nothing about the record
    would say so.

`nodus_gate --shapes` did not catch the duplication: its species-B detector looks
for one literal collection being a strict *subset* of another, and these were
equal. Recorded because it is a real hole in the detector, not because the
duplication was excusable.
"""

import os
import sys
import tempfile
import unittest

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(_ROOT, "src"))  # noqa: E402
sys.path.insert(0, _ROOT)  # noqa: E402

from nodus_lang_workflow.models import (  # noqa: E402
    REHYDRATABLE_RUN_STATUSES,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_PENDING,
    RUN_STATUS_RUNNING,
    RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    WorkflowRunRecord,
)
from nodus_lang_workflow.runner import WorkflowFrameworkRunner  # noqa: E402
from nodus_lang_workflow.store import LocalWorkflowStore  # noqa: E402


def _runner(root: str) -> WorkflowFrameworkRunner:
    return WorkflowFrameworkRunner(store=LocalWorkflowStore(root))


def _record(run_id: str, status: str = RUN_STATUS_RUNNING) -> WorkflowRunRecord:
    return WorkflowRunRecord(
        run_id=run_id, graph_id=run_id, workflow_name="w", status=status
    )


# closes: #395
class RunStatusVocabularyTests(unittest.TestCase):
    def test_there_are_eight_statuses_and_they_are_unique(self):
        self.assertEqual(8, len(RUN_STATUSES))
        self.assertEqual(len(RUN_STATUSES), len(set(RUN_STATUSES)))

    def test_every_status_is_terminal_or_not_and_never_both(self):
        """The partition. A status in neither set is one nothing knows how to
        retire or resume; a status in both is a contradiction."""
        overlap = REHYDRATABLE_RUN_STATUSES & TERMINAL_RUN_STATUSES
        self.assertEqual(frozenset(), overlap)
        for status in RUN_STATUSES:
            with self.subTest(status=status):
                self.assertIn(status, set(RUN_STATUSES))

    def test_cancelled_is_terminal(self):
        """Or `workflow cleanup` never retires one and they accumulate forever."""
        self.assertIn(RUN_STATUS_CANCELLED, TERMINAL_RUN_STATUSES)

    def test_cancelled_is_not_rehydratable(self):
        """The one that would be silent. A cancelled run picked up by the next
        sweep has un-cancelled itself, and the record would not say so."""
        self.assertNotIn(RUN_STATUS_CANCELLED, REHYDRATABLE_RUN_STATUSES)

    def test_the_sets_are_defined_once(self):
        """`store.py` and `runner.py` each had their own rehydratable set, equal
        by coincidence. Identity, not equality — equality is what they already
        had, and it is what let them drift apart unnoticed for as long as they
        happened to agree."""
        from nodus_lang_workflow import runner as runner_mod
        from nodus_lang_workflow import store as store_mod

        self.assertIs(REHYDRATABLE_RUN_STATUSES, store_mod.REHYDRATABLE_RUN_STATUSES)
        self.assertIs(REHYDRATABLE_RUN_STATUSES, runner_mod._REHYDRATABLE_STATUSES)
        self.assertIs(TERMINAL_RUN_STATUSES, store_mod.TERMINAL_RUN_STATUSES)
        self.assertEqual(set(RUN_STATUSES), set(runner_mod._KNOWN_RUN_STATUSES))


# closes: #395
class CancelRunTests(unittest.TestCase):
    def test_cancelling_a_running_run_marks_it_cancelled(self):
        with tempfile.TemporaryDirectory() as root:
            runner = _runner(root)
            runner.store.save_run(_record("r1"))

            result = runner.cancel_run("r1")

            self.assertTrue(result["ok"], result)
            self.assertEqual(RUN_STATUS_CANCELLED, result["status"])
            self.assertEqual(RUN_STATUS_RUNNING, result["cancelled_from"])
            self.assertEqual(RUN_STATUS_CANCELLED, runner.store.get_run("r1").status)

    def test_the_previous_status_is_recorded(self):
        """An operator asking "what was it doing when it was stopped" has one
        place to look. Overwriting the status without keeping it loses the only
        thing that distinguishes a cancelled queue entry from a cancelled
        in-flight run."""
        with tempfile.TemporaryDirectory() as root:
            runner = _runner(root)
            runner.store.save_run(_record("r2", RUN_STATUS_PENDING))
            runner.cancel_run("r2")
            record = runner.store.get_run("r2")
            self.assertEqual(RUN_STATUS_PENDING, record.metadata["cancelled_from"])
            self.assertIn("cancelled_at", record.metadata)

    def test_cancelling_a_finished_run_is_a_no_op_that_says_so(self):
        """Matches `cancel(task)`: not an error, because the caller usually
        cannot know the target's state, and raising would push every call site
        into a check-then-act race."""
        with tempfile.TemporaryDirectory() as root:
            runner = _runner(root)
            runner.store.save_run(_record("r3", RUN_STATUS_COMPLETED))

            result = runner.cancel_run("r3")

            self.assertFalse(result["ok"])
            self.assertEqual("already finished", result["reason"])
            self.assertEqual(RUN_STATUS_COMPLETED, runner.store.get_run("r3").status,
                             "a finished run was overwritten")

    def test_cancelling_an_unknown_run_reports_not_found(self):
        with tempfile.TemporaryDirectory() as root:
            result = _runner(root).cancel_run("nope")
            self.assertFalse(result["ok"])
            self.assertEqual("not found", result["reason"])

    def test_the_claim_is_released(self):
        """A cancelled run holding a claim is a run no other process may touch,
        which is the opposite of what cancelling it was for."""
        with tempfile.TemporaryDirectory() as root:
            runner = _runner(root)
            record = _record("r4")
            runner.store.save_run(record)
            runner.cancel_run("r4")
            self.assertIsNone(runner.store.get_run("r4").claim)


# closes: #395
class CooperativeObservationTests(unittest.TestCase):
    """The cross-process half. A CLI cannot reach into the scheduler of whichever
    process owns a running run, so it marks the store and that process asks."""

    def test_run_is_cancelled_reads_the_store(self):
        with tempfile.TemporaryDirectory() as root:
            runner = _runner(root)
            runner.store.save_run(_record("r5"))
            self.assertFalse(runner.run_is_cancelled("r5"))

            # Stand-in for another process: a second runner over the same store.
            _runner(root).cancel_run("r5")

            self.assertTrue(runner.run_is_cancelled("r5"),
                            "a cancellation marked elsewhere was not observed")

    def test_an_unknown_run_is_not_reported_cancelled(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(_runner(root).run_is_cancelled("absent"))


if __name__ == "__main__":
    unittest.main()
