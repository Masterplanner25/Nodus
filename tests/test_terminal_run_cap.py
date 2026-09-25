"""`max_terminal_runs` is a hard ceiling on a store's size (#875).

It is documented as exactly that — *"a host that keeps a store for years and
wants a hard ceiling sets this"* — and it was not one. `_prune_terminal_runs`
chose what to delete from the age-bounded listing, which drops terminal runs
older than `terminal_max_age_days`, and terminal is precisely what it deletes.
So the runs it could see were the ones it was least meant to remove:

    max_terminal_runs=2, six finished runs, four aged past the bound
      -> 6 files on disk, and the four survivors were the four oldest

The exact inverse of the intent: prune the recent history, accumulate the old.

**This is a deletion path**, which is why it was filed separately from #869
rather than folded into it — making something delete strictly more is a decision
to take deliberately. The safety property is therefore the centre of this file:
only terminal runs are ever removed, whatever their age, and the cap seeing more
records must not widen what it is allowed to touch.
"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus_lang_workflow.store import LocalWorkflowStore  # noqa: E402

FORTY_DAYS = 40 * 86_400
LIVE_STATUSES = ("waiting", "running", "pending", "retry_scheduled")
FINISHED_STATUSES = ("completed", "failed", "cancelled", "dead_lettered")


class _Harness(unittest.TestCase):
    def _store(self, root, **kwargs):
        return LocalWorkflowStore(root=root, **kwargs)

    def _add(self, store, run_id, status, *, aged=True):
        store.create_run(run_id=run_id, graph_id=run_id, workflow_name="demo",
                         execution_kind="workflow")
        record = store.get_run(run_id)
        record.status = status
        store.restore_run(record)
        if aged:
            when = time.time() - FORTY_DAYS
            os.utime(store._run_path(run_id), (when, when))

    def _files(self, root):
        return sorted(
            os.path.splitext(name)[0]
            for name in os.listdir(os.path.join(root, "runs"))
            if name.endswith(".json")
        )

    def _age_all(self, store, root):
        """Backdate every record that exists *now*.

        Must run after the last `save_run` on those records: `save_run` rewrites
        the file and so resets its mtime. Ageing inside `_add` and then saving
        left every record fresh at prune time, and the headline test passed
        against a deliberately broken build because of it.
        """
        when = time.time() - FORTY_DAYS
        for name in os.listdir(os.path.join(root, "runs")):
            if name.endswith(".json"):
                path = os.path.join(root, "runs", name)
                os.utime(path, (when, when))

    def _trigger_prune(self, store, root):
        """Make the store prune without touching the aged records.

        `_prune_terminal_runs` runs off `save_run`, and saving one of the aged
        records would un-age it. A fresh record does the job.
        """
        self._add(store, "trigger", "completed", aged=False)
        store.save_run(store.get_run("trigger"))


# closes: #875
class TheCeilingHolds(_Harness):
    def _six_aged_finished(self, root, cap=2):
        store = self._store(root, max_terminal_runs=cap)
        for i in range(6):
            self._add(store, f"r{i}", "completed", aged=False)
            store.save_run(store.get_run(f"r{i}"))
        # Aged only now, so the saves above cannot reset the mtimes. Every one
        # of the six is past the bound and was invisible to the cap before this.
        self._age_all(store, root)
        self._trigger_prune(store, root)
        return store

    def test_aged_finished_runs_are_pruned_to_the_cap(self):
        with tempfile.TemporaryDirectory() as root:
            self._six_aged_finished(root)
            self.assertEqual(
                len(self._files(root)), 2,
                f"the ceiling did not hold: {self._files(root)}",
            )

    def test_the_oldest_are_the_ones_removed(self):
        # "oldest deleted first" is the documented order; without this the test
        # above passes on an implementation that keeps an arbitrary two.
        with tempfile.TemporaryDirectory() as root:
            self._six_aged_finished(root)
            self.assertEqual(self._files(root), ["r5", "trigger"])

    def test_an_unset_cap_still_deletes_nothing(self):
        # The default is off, and run records are history a host may rely on.
        with tempfile.TemporaryDirectory() as root:
            store = self._store(root)
            for i in range(5):
                self._add(store, f"r{i}", "completed")
                store.save_run(store.get_run(f"r{i}"))
            self.assertEqual(len(self._files(root)), 5)


# closes: #875
class LiveRunsAreNeverRemoved(_Harness):
    """The safety property. The cap sees more records now; it may not touch more."""

    def test_every_live_status_survives_however_old(self):
        with tempfile.TemporaryDirectory() as root:
            store = self._store(root, max_terminal_runs=1)
            for i, status in enumerate(LIVE_STATUSES + FINISHED_STATUSES):
                self._add(store, f"r{i}-{status}", status)
            store.save_run(store.get_run("r0-waiting"))

            survivors = self._files(root)
            for status in LIVE_STATUSES:
                self.assertTrue(
                    any(name.endswith(status) for name in survivors),
                    f"a {status} run was deleted by the record cap: {survivors}",
                )

    def test_the_control_finished_runs_are_still_pruned_in_the_same_call(self):
        # Without this, the test above passes on a build where the cap deletes
        # nothing at all.
        with tempfile.TemporaryDirectory() as root:
            store = self._store(root, max_terminal_runs=1)
            for i, status in enumerate(LIVE_STATUSES + FINISHED_STATUSES):
                self._add(store, f"r{i}-{status}", status)
            store.save_run(store.get_run("r0-waiting"))

            survivors = self._files(root)
            finished = [
                name for name in survivors
                if any(name.endswith(s) for s in FINISHED_STATUSES)
            ]
            self.assertEqual(
                len(finished), 1,
                f"four finished runs were present and the cap is 1: {survivors}",
            )

    def test_a_live_run_is_kept_even_when_it_is_the_oldest(self):
        with tempfile.TemporaryDirectory() as root:
            store = self._store(root, max_terminal_runs=1)
            self._add(store, "ancient-waiting", "waiting")
            for i in range(3):
                self._add(store, f"recent-{i}", "completed", aged=False)
                store.save_run(store.get_run(f"recent-{i}"))
            self.assertIn("ancient-waiting", self._files(root))


# closes: #875
class TheCapReadsTheUnboundedListing(_Harness):
    """Source-level, because the behaviour above passes on a store whose age
    bound happens to be disabled, and the default is 30 days rather than off."""

    def _body(self):
        """The method's code with its docstring removed.

        Load-bearing: the docstring explains the fix and therefore *contains* the
        strings below. Asserting against the whole source passed on a build where
        the call had been reverted, because the prose still matched — the
        unfalsifiable source assertion this repo keeps re-learning.
        """
        import inspect

        source = inspect.getsource(LocalWorkflowStore._prune_terminal_runs)
        doc = LocalWorkflowStore._prune_terminal_runs.__doc__ or ""
        return source.replace(doc, "")

    def test_prune_enumerates_with_the_age_bound_off(self):
        self.assertIn("_list_runs_unlocked(include_aged_terminal=True)", self._body())

    def test_only_terminal_statuses_are_selected(self):
        # The guarantee is this filter, and it has to survive any future change
        # to which listing feeds it.
        self.assertIn("TERMINAL_RUN_STATUSES", self._body())


if __name__ == "__main__":
    unittest.main()
