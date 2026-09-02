"""Copying run records between store backends, timestamps intact (#174).

This is the thing that had to exist before the default store could move from
`local` to `sqlite`. Runs recorded in the JSON store are **invisible** to a SQLite
one, so flipping the default without a migration would silently make every
in-flight `waiting` run unresumable at the moment of upgrade — a data-loss bug that
looks like nothing at all until someone waits for a webhook that never lands.

The issue expected the breakage to be *"the JSON file location moves"*. It is not;
it is that the records do not follow.

`test_timestamps_survive_the_move` is the one that constrains the design.
`save_run` stamps `updated_at` to now, which is right for a run that just moved and
wrong for one being copied — and `updated_at` is not decoration: it backs
`workflow runs --updated-after/--updated-before` and orders `_prune_terminal_runs`,
which deletes oldest-first. A migration built on `save_run` passes every other test
in this file and quietly destroys both.
"""

import os
import sys
import unittest
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus_lang_workflow.models import RUN_STATUS_WAITING  # noqa: E402
from nodus_lang_workflow.store import (  # noqa: E402
    LocalWorkflowStore,
    SQLiteWorkflowStore,
    create_workflow_store,
    migrate_workflow_store,
)


class MigrationHarness(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.source = create_workflow_store(
            backend="local", root=os.path.join(self.root, "local")
        )
        self.target = create_workflow_store(
            backend="sqlite", path=os.path.join(self.root, "runs.db")
        )

    def _run(self, run_id, **kw):
        return self.source.create_run(
            run_id=run_id,
            graph_id=kw.pop("graph_id", f"g_{run_id}"),
            workflow_name=kw.pop("workflow_name", "w"),
            execution_kind="workflow",
            **kw,
        )


class MigrationCopiesEverythingTests(MigrationHarness):
    # closes: #174
    def test_every_run_arrives(self):
        for i in range(3):
            self._run(f"r{i}")
        report = migrate_workflow_store(self.source, self.target)
        self.assertEqual(3, report["migrated_count"])
        self.assertEqual(0, report["failed_count"])
        self.assertEqual({"r0", "r1", "r2"}, {r.run_id for r in self.target.list_runs()})

    # closes: #174
    def test_timestamps_survive_the_move(self):
        """The constraint the whole design turns on — see the module docstring."""
        self._run("r1")
        record = self.source.get_run("r1")
        record.created_at = 100_000.0
        record.updated_at = 111_111.0
        self.source.restore_run(record)

        migrate_workflow_store(self.source, self.target)

        moved = self.target.get_run("r1")
        self.assertEqual(100_000.0, moved.created_at)
        self.assertEqual(111_111.0, moved.updated_at)

    # closes: #174
    def test_a_waiting_run_keeps_its_wait_record(self):
        """The population the default flip endangers.

        A `waiting` run whose wait record did not follow is not merely missing —
        it is a run nothing will ever resume, and nothing reports that.
        """
        self._run("r1")
        self.source.register_wait(
            "r1", event_type="webhook", correlation_key="order-7", deadline_ms=None
        )
        report = migrate_workflow_store(self.source, self.target)

        self.assertEqual(["r1"], report["waiting_migrated"])
        moved = self.target.get_run("r1")
        self.assertEqual(RUN_STATUS_WAITING, moved.status)
        self.assertIsNotNone(moved.wait)
        self.assertEqual("webhook", moved.wait.event_type)
        self.assertEqual("order-7", moved.wait.correlation_key)

    # closes: #174
    def test_metadata_survives(self):
        """Run metadata carries the rebuilt program's source (#499) — a run whose
        metadata did not follow is not resumable across processes."""
        self._run("r1", metadata={"workflow_source_code": "workflow w { step a { } }"})
        migrate_workflow_store(self.source, self.target)
        moved = self.target.get_run("r1")
        self.assertEqual(
            "workflow w { step a { } }", moved.metadata.get("workflow_source_code")
        )


class MigrationIsSafeToRunTests(MigrationHarness):
    # closes: #174
    def test_the_source_is_never_modified(self):
        """The old store may hold the only copy of a run someone is waiting on."""
        self._run("r1")
        migrate_workflow_store(self.source, self.target)
        self.assertEqual(["r1"], [r.run_id for r in self.source.list_runs()])

    # closes: #174
    def test_a_dry_run_writes_nothing_but_reports_what_would_move(self):
        self._run("r1")
        report = migrate_workflow_store(self.source, self.target, dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertEqual(1, report["migrated_count"])
        self.assertEqual([], self.target.list_runs())

    # closes: #174
    def test_re_running_skips_what_already_arrived(self):
        """Idempotent, so an interrupted migration is finished by repeating it
        rather than needing the target wiped first."""
        self._run("r1")
        migrate_workflow_store(self.source, self.target)
        again = migrate_workflow_store(self.source, self.target)
        self.assertEqual(0, again["migrated_count"])
        self.assertEqual(["r1"], again["skipped"])

    # closes: #174
    def test_overwrite_replaces_an_existing_record(self):
        self._run("r1")
        migrate_workflow_store(self.source, self.target)
        record = self.source.get_run("r1")
        record.last_error = "changed after the first pass"
        self.source.restore_run(record)

        report = migrate_workflow_store(self.source, self.target, overwrite=True)
        self.assertEqual(1, report["migrated_count"])
        self.assertEqual(
            "changed after the first pass", self.target.get_run("r1").last_error
        )

    # closes: #174
    def test_one_bad_record_does_not_abandon_the_rest(self):
        """A migration that stops at the first failure leaves the operator with two
        partial stores and no report of which records made it."""
        for i in range(3):
            self._run(f"r{i}")

        real_restore = self.target.restore_run

        def explode(record):
            if record.run_id == "r1":
                raise RuntimeError("simulated write failure")
            return real_restore(record)

        self.target.restore_run = explode
        report = migrate_workflow_store(self.source, self.target)

        self.assertEqual(2, report["migrated_count"])
        self.assertEqual(1, report["failed_count"])
        self.assertEqual("r1", report["failed"][0]["run_id"])
        self.assertIn("simulated write failure", report["failed"][0]["error"])


class RestoreRunIsDistinctFromSaveRunTests(MigrationHarness):
    """`restore_run` is a separate verb, and both in-tree stores implement it."""

    # closes: #174
    def test_save_run_stamps_and_restore_run_does_not(self):
        for store in (self.source, self.target):
            with self.subTest(store=type(store).__name__):
                record = store.create_run(
                    run_id="x", graph_id="g", workflow_name="w",
                    execution_kind="workflow",
                )
                record.updated_at = 42.0
                store.save_run(record)
                self.assertNotEqual(42.0, store.get_run("x").updated_at)

                record = store.get_run("x")
                record.updated_at = 42.0
                store.restore_run(record)
                self.assertEqual(42.0, store.get_run("x").updated_at)

    # closes: #174
    def test_the_abc_default_keeps_an_out_of_tree_store_working(self):
        """Concrete on the ABC, not abstract.

        A new *abstract* method breaks any out-of-tree subclass at construction —
        which is exactly how 5.0.3 broke `nodus_sdk` (#185). The default is lossy
        but functional; both in-tree stores override it.
        """
        from nodus_lang_workflow.store import WorkflowStore

        self.assertFalse(getattr(WorkflowStore.restore_run, "__isabstractmethod__", False))
        for cls in (LocalWorkflowStore, SQLiteWorkflowStore):
            with self.subTest(store=cls.__name__):
                self.assertIsNot(cls.restore_run, WorkflowStore.restore_run)


if __name__ == "__main__":
    unittest.main()
