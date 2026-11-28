"""A parked run does not age out of existence (#869).

`LocalWorkflowStore` skipped any file whose mtime was older than
`terminal_max_age_days` *before opening it*, which is the only way to bound the
scan — and which cannot tell a finished run from one parked at `workflow_wait`.
So a run waiting on a human for longer than the bound stopped being findable by
everything that could have rescued it, while `get_run(id)` still returned it,
`waiting`, the whole time:

| Asked | Answer, before |
|---|---|
| `nodus workflow runs` | not listed; `counts.waiting: 0` |
| `list_rehydratable_runs()` → the adoption sweep | skipped |
| `migrate-store --to sqlite` | `migrated=0 skipped=0 failed=0` — not even skipped |
| the #174 "these runs will be stranded at 6.0.0" warning | silent |

The last row is the sharp one. The `default-store-sqlite` flip makes SQLite the
default at 6.0.0 and JSON-store runs are invisible to a SQLite one, so the store
whose parked runs that flip will strand was precisely the store that said
nothing — because everything in it had aged out of the listing the warning reads.

The tree contradicted itself about this in writing: `store.py` called the bound a
*scan-cost* bound, and the prune path documents "Only terminal runs are ever
removed — a waiting or retrying run is live state, whatever the count." The
listing honoured neither, and `SQLiteWorkflowStore` has never filtered at all.

These are end-to-end against the consumers. `test_nodus_workflow_framework.py`
covers the store rule itself.
"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus_lang_workflow import runner as runner_module  # noqa: E402
from nodus_lang_workflow.store import (  # noqa: E402
    LocalWorkflowStore,
    SQLiteWorkflowStore,
    StrandedRunsError,
    create_workflow_store,
    migrate_workflow_store,
    unmigrated_local_runs,
)

FORTY_DAYS = 40 * 86_400


def _parked_store(root: str, run_id: str = "parked", status: str = "waiting"):
    """A store holding one run of *status*, aged forty days past the bound."""
    store = LocalWorkflowStore(root=root)
    store.create_run(
        run_id=run_id, graph_id=run_id, workflow_name="demo", execution_kind="workflow",
    )
    record = store.get_run(run_id)
    record.status = status
    store.restore_run(record)
    path = store._run_path(run_id)
    when = time.time() - FORTY_DAYS
    os.utime(path, (when, when))
    return store


# closes: #869
class AMigrationCarriesAParkedRun(unittest.TestCase):
    """A migration is the one operation that has to be exhaustive."""

    def test_an_aged_parked_run_is_migrated(self):
        with tempfile.TemporaryDirectory() as root:
            source = _parked_store(root)
            target = SQLiteWorkflowStore(path=os.path.join(root, "workflow.sqlite3"))
            report = migrate_workflow_store(source, target)

            self.assertEqual(
                report["migrated_count"], 1,
                f"a parked run was not carried: {report}",
            )
            self.assertIn("parked", report["waiting_migrated"])
            self.assertIsNotNone(target.get_run("parked"))

    def test_an_aged_finished_run_is_migrated_too(self):
        # `list_runs()` may legitimately trim finished history; a migration may
        # not. Before the fix this was reported as neither migrated NOR skipped.
        with tempfile.TemporaryDirectory() as root:
            source = _parked_store(root, run_id="done", status="completed")
            target = SQLiteWorkflowStore(path=os.path.join(root, "workflow.sqlite3"))
            report = migrate_workflow_store(source, target)

            self.assertEqual(report["migrated_count"], 1, str(report))
            self.assertNotIn("done", {r.run_id for r in source.list_runs()})

    def test_the_warning_and_the_migration_count_the_same_runs(self):
        # The disagreement itself: `_unmigrated_local_runs` reads raw files and
        # the migration read a trimmed listing, so the warning named runs the
        # migration could not carry and could never be cleared.
        with tempfile.TemporaryDirectory() as root:
            source = _parked_store(root)
            empty = SQLiteWorkflowStore(path=os.path.join(root, "empty.sqlite3"))
            warned = unmigrated_local_runs(root, empty)
            migrated = [r.run_id for r in source.list_all_runs()]
            self.assertEqual(sorted(warned), sorted(migrated))


# closes: #869
class TheSweepCanStillSeeAParkedRun(unittest.TestCase):
    def test_an_aged_parked_run_is_offered_to_the_adoption_sweep(self):
        with tempfile.TemporaryDirectory() as root:
            store = _parked_store(root)
            self.assertIn(
                "parked", {r.run_id for r in store.list_rehydratable_runs()},
                "the sweep that adopts an orphaned run could not see it",
            )

    def test_an_aged_parked_run_is_counted_by_the_runner(self):
        with tempfile.TemporaryDirectory() as root:
            store = _parked_store(root)
            runner = runner_module.WorkflowFrameworkRunner(store=store)
            self.assertIn("parked", {r.run_id for r in runner.list_runs()})


# closes: #869
class TheStrandedRunsRefusalFires(unittest.TestCase):
    """The row that matters most: silence on the store about to be stranded.

    This was a warning through 5.x; since 6.0.0 (#797) the default store
    refuses instead, so the refusal is what must see an aged parked run.
    """

    def _refusal_for(self, root):
        try:
            create_workflow_store(root=root)
        except StrandedRunsError as exc:
            return exc
        return None

    def test_a_store_holding_only_aged_runs_still_refuses(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            _parked_store(root)
            refusal = self._refusal_for(root)
            self.assertIsNotNone(
                refusal, "the store whose parked run SQLite lacks said nothing"
            )
            self.assertIn("parked", refusal.run_ids)

    def test_the_control_a_fresh_run_refuses_as_well(self):
        # Without this the test above passes for any reason at all, including
        # the refusal having become unconditional.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            store = LocalWorkflowStore(root=root)
            store.create_run(
                run_id="fresh", graph_id="fresh", workflow_name="demo",
                execution_kind="workflow",
            )
            self.assertIsNotNone(self._refusal_for(root))

    def test_an_empty_store_is_not_refused(self):
        # The other direction: the fix must not make the refusal unconditional.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            LocalWorkflowStore(root=root)
            self.assertIsNone(self._refusal_for(root))


# closes: #869
class TheBackendsAgreeOnWhatAStoreHolds(unittest.TestCase):
    """SQLite never filtered. The two disagreeing was the underlying defect."""

    def test_sqlite_and_local_both_list_an_aged_parked_run(self):
        with tempfile.TemporaryDirectory() as root:
            local = _parked_store(root)
            sqlite = SQLiteWorkflowStore(path=os.path.join(root, "workflow.sqlite3"))
            migrate_workflow_store(local, sqlite)
            self.assertEqual(
                {r.run_id for r in local.list_runs()},
                {r.run_id for r in sqlite.list_runs()},
            )


if __name__ == "__main__":
    unittest.main()
