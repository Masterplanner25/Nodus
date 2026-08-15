"""`LocalWorkflowStore` must not pay per-record syscalls it does not need (#380).

Listing runs cost ~1.3 ms per file, and a background sweeper calls it on a timer:
299 accumulated files took 540 ms, past the 500 ms sweep interval that
deadline-sensitive tests assume. The cause was not parsing — profiling 3,000
records put 1.7 s of 4.2 s in `nt.mkdir` and 1.6 s in `nt.stat`:

- `_runs_root()` called `makedirs` on the root *and* the runs directory, and
  `_run_path()` calls it once per record — 6,000 mkdir syscalls for 3,000 runs;
- `_load_run_unlocked()` did an `os.path.exists` before an `open` that already
  reports a missing file;
- `expire_wait_timeouts()` re-read every record it had just been handed, for
  every run rather than only the waiting ones.

These tests assert the *syscall behaviour*, not elapsed time. A timing assertion
would be flaky on shared CI and would not say which of the three regressed.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus_lang_workflow.store import (  # noqa: E402
    RUN_STATUS_COMPLETED,
    RUN_STATUS_WAITING,
    LocalWorkflowStore,
)


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def make_store(self, **kwargs) -> LocalWorkflowStore:
        return LocalWorkflowStore(root=self.root, **kwargs)

    def seed(self, store: LocalWorkflowStore, count: int, *, status: str | None = None):
        records = []
        for i in range(count):
            record = store.create_run(
                run_id=f"r_{i:04d}", graph_id=f"g_{i:04d}",
                workflow_name="demo", execution_kind="workflow",
            )
            if status is not None:
                record.status = status
                store.save_run(record)
            records.append(record)
        return records


# closes: #380
class ScanDoesNotRepeatSyscallsPerRecordTests(StoreTestCase):
    def test_listing_does_not_mkdir_once_per_record(self):
        store = self.make_store()
        self.seed(store, 25)

        calls = []
        real_makedirs = os.makedirs
        os.makedirs = lambda *a, **kw: (calls.append(a[0]), real_makedirs(*a, **kw))[1]
        try:
            store.list_runs()
        finally:
            os.makedirs = real_makedirs

        # One store, one directory: listing must not re-create it per record.
        self.assertLessEqual(len(calls), 2, f"{len(calls)} makedirs calls for 25 records")

    def test_loading_a_record_opens_the_file_once(self):
        store = self.make_store()
        self.seed(store, 5)

        stats = []
        real_exists = os.path.exists
        os.path.exists = lambda p: (stats.append(p), real_exists(p))[1]
        try:
            store.list_runs()
        finally:
            os.path.exists = real_exists

        # Scoped to this store's own directory: the patch is process-wide, and
        # anything else running concurrently — the graph store writing
        # `.nodus/graphs/*.json`, a background sweep — also calls os.path.exists.
        # Matching on ".json" alone made this fail in CI on an unrelated path.
        run_stats = [p for p in stats
                     if p.endswith(".json") and os.path.abspath(p).startswith(self.root)]
        self.assertEqual([], run_stats,
                         "each record is stat-ed before being opened; the open reports "
                         "a missing file on its own")

    def test_a_missing_record_still_reads_as_none(self):
        # The behaviour the removed exists-check was providing.
        store = self.make_store()
        self.assertIsNone(store.get_run("never_created"))

    def test_the_runs_directory_is_recreated_if_it_disappears(self):
        store = self.make_store()
        self.seed(store, 1)
        import shutil
        shutil.rmtree(os.path.join(self.root, "runs"))
        store._runs_root_cache = None  # what a fresh store would see
        self.assertEqual([], store.list_runs())
        self.assertTrue(os.path.isdir(os.path.join(self.root, "runs")))


# closes: #380
class SweepOnlyTouchesWaitingRunsTests(StoreTestCase):
    def test_expiry_does_not_reread_every_record(self):
        store = self.make_store()
        self.seed(store, 20, status=RUN_STATUS_COMPLETED)

        reads = []
        real_get = store.get_run
        store.get_run = lambda run_id: (reads.append(run_id), real_get(run_id))[1]
        store.expire_wait_timeouts()

        self.assertEqual([], reads,
                         "terminal runs cannot expire; the sweep re-read them anyway")

    def test_waiting_runs_are_still_examined(self):
        store = self.make_store()
        self.seed(store, 3, status=RUN_STATUS_WAITING)

        reads = []
        real_get = store.get_run
        store.get_run = lambda run_id: (reads.append(run_id), real_get(run_id))[1]
        store.expire_wait_timeouts()

        self.assertEqual(3, len(reads), "waiting runs must still be checked for expiry")


# closes: #380
class TerminalRunCapTests(StoreTestCase):
    def test_off_by_default(self):
        store = self.make_store()
        self.seed(store, 12, status=RUN_STATUS_COMPLETED)
        self.assertEqual(12, len(store.list_runs()),
                         "run history must not be deleted unless asked for")

    def test_keeps_the_newest_when_capped(self):
        store = self.make_store(max_terminal_runs=5)
        self.seed(store, 12, status=RUN_STATUS_COMPLETED)
        remaining = store.list_runs()
        self.assertEqual(5, len(remaining))
        self.assertEqual({"r_0007", "r_0008", "r_0009", "r_0010", "r_0011"},
                         {r.run_id for r in remaining})

    def test_never_prunes_live_runs(self):
        store = self.make_store(max_terminal_runs=2)
        self.seed(store, 6, status=RUN_STATUS_WAITING)
        self.assertEqual(6, len(store.list_runs()),
                         "waiting runs are live state, whatever the count")

    def test_a_cap_of_zero_keeps_no_terminal_runs(self):
        store = self.make_store(max_terminal_runs=0)
        self.seed(store, 4, status=RUN_STATUS_COMPLETED)
        self.assertEqual([], store.list_runs())


if __name__ == "__main__":
    unittest.main()
