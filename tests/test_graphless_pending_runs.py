"""A run that never started can be retired (#734).

`pending` is in neither `REHYDRATABLE_RUN_STATUSES` nor `TERMINAL_RUN_STATUSES`,
so such a record was adopted by nothing and retired by nothing. It leaked, and
`LocalWorkflowStore.list_runs()` is linear in the directory (#380), so leaked
records keep costing.

**The obvious fix does not work, and that is the part worth keeping.** The issue
proposed adding `pending` to `TERMINAL_RUN_STATUSES`. Two things defeat it:

- `workflow cleanup` iterates **graph snapshots**, not run records, and a run
  that never started has no graph — so it would still never be reached.
  `TheCommandWalksGraphsTests` pins that premise, because the whole fix rests on
  it.
- `cancel_run` refuses anything terminal with *"already finished"*, which a run
  that never started plainly has not. `CancellingAPendingRunStillWorksTests`
  pins that, because it is the behaviour a future "just make it terminal" would
  silently break.

The two sets answer *"may this be resumed"* and *"is this finished"*. Whether
cleanup may retire something is a third question, and it is answered separately.
"""

import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.cli.cli import main  # noqa: E402
from nodus_lang_workflow.models import (  # noqa: E402
    REHYDRATABLE_RUN_STATUSES,
    RUN_STATUS_PENDING,
    TERMINAL_RUN_STATUSES,
)
from nodus_lang_workflow.runner import (  # noqa: E402
    get_default_workflow_runner,
    reset_default_workflow_runner,
)

_THIRTY_ONE_DAYS_MS = 31 * 24 * 3600 * 1000


class _StoreHarness(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._td.name)
        self.addCleanup(self._restore)

    def _restore(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def _store(self):
        return get_default_workflow_runner().store

    def _record_path(self, run_id: str) -> str:
        return os.path.join(
            self._td.name, ".nodus", "workflow_framework", "runs", f"{run_id}.json"
        )

    def _make(self, run_id: str, *, status: str = RUN_STATUS_PENDING, age_ms: float = 0.0):
        """Create a record with no graph, optionally backdated.

        Written to disk rather than through `save_run`, which re-stamps
        `updated_at` with the current time — so an in-memory backdate is
        silently undone. That is what `restore_run` exists for (#174), but
        editing the file is the smaller thing to do here.
        """
        store = self._store()
        record = store.create_run(
            run_id=run_id, graph_id=run_id, workflow_name="w", execution_kind="workflow"
        )
        if status != RUN_STATUS_PENDING:
            record.status = status
            store.save_run(record)
        if age_ms:
            path = Path(self._record_path(run_id))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["updated_at"] = time.time() * 1000 - age_ms
            path.write_text(json.dumps(payload), encoding="utf-8")
        return record

    def _cleanup(self, *args: str) -> dict:
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["nodus", "workflow", "cleanup", *args])
        self.assertEqual(0, code)
        return json.loads(out.getvalue().strip())

    def _ids(self) -> list[str]:
        return sorted(record.run_id for record in self._store().list_runs())


class TheCommandWalksGraphsTests(_StoreHarness):
    """The premise the fix rests on, asserted rather than assumed."""

    # closes: #734
    def test_a_pending_run_has_no_graph_snapshot(self):
        """The graph is written when the run starts. A pending run never did, so
        every graph-keyed mechanism is blind to it."""
        from nodus.orchestration import task_graph

        self._make("p1")
        self.assertEqual([], task_graph.list_graph_snapshots_info())

    # closes: #734
    def test_pending_is_in_neither_partition(self):
        """The defect in one line. Kept so that classifying it later — which is
        a reasonable thing to do — has to be a deliberate change here."""
        self.assertNotIn(RUN_STATUS_PENDING, REHYDRATABLE_RUN_STATUSES)
        self.assertNotIn(RUN_STATUS_PENDING, TERMINAL_RUN_STATUSES)

    # closes: #734
    def test_neither_adoption_nor_the_terminal_list_finds_it(self):
        self._make("p1")
        store = self._store()
        self.assertEqual([], [r.run_id for r in store.list_rehydratable_runs()])
        self.assertEqual([], [r.run_id for r in store.list_terminal_runs()])
        self.assertEqual(["p1"], self._ids(), "but the record is there")


class CleanupRetiresAnAbandonedPendingRunTests(_StoreHarness):
    # closes: #734
    def test_an_old_one_is_retired(self):
        self._make("old", age_ms=_THIRTY_ONE_DAYS_MS)
        payload = self._cleanup()
        self.assertEqual(["old"], payload["run_records_removed"])
        self.assertEqual([], self._ids())

    # closes: #734
    def test_a_fresh_one_is_left_alone(self):
        """The window between `create_run` and the flip to `running` is real, so
        a just-created pending record belongs to a run that is starting right
        now. Retention is what separates the two, and it defaults to 30 days."""
        self._make("fresh")
        payload = self._cleanup()
        self.assertEqual([], payload["run_records_removed"])
        self.assertEqual(["fresh"], self._ids())

    # closes: #734
    def test_force_takes_it_regardless_of_age(self):
        self._make("fresh")
        self.assertEqual(["fresh"], self._cleanup("--force")["run_records_removed"])
        self.assertEqual([], self._ids())

    # closes: #734
    def test_only_pending_records_are_touched(self):
        """`running` and `waiting` records without a graph are the same leak by
        another route, and are deliberately out of scope: rehydration *attempts*
        those and records why it failed (#399), so they are visible. These were
        not visible at all."""
        self._make("pend", age_ms=_THIRTY_ONE_DAYS_MS)
        self._make("run", status="running", age_ms=_THIRTY_ONE_DAYS_MS)
        self._make("wait", status="waiting", age_ms=_THIRTY_ONE_DAYS_MS)
        self._cleanup()
        self.assertEqual(["run", "wait"], self._ids())

    # closes: #734
    def test_a_record_predating_the_wall_clock_switch_is_left_alone(self):
        """Before #725 `updated_at` was milliseconds since *process start*, so
        such a number cannot be compared against a wall-clock cutoff. Treated as
        unknown rather than as ancient — the other reading would delete every
        old record on the first run."""
        self._make("legacy")
        path = Path(self._record_path("legacy"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["updated_at"] = 1234.5  # monotonic-since-start, pre-#725
        path.write_text(json.dumps(payload), encoding="utf-8")

        self.assertEqual([], self._cleanup()["run_records_removed"])
        self.assertEqual(["legacy"], self._ids())
        # `--force` still takes it, because that is what force means.
        self.assertEqual(["legacy"], self._cleanup("--force")["run_records_removed"])


class ItWorksOnBothBackendsTests(unittest.TestCase):
    """The retirement pass uses only `WorkflowStore` methods — `list_runs` and
    `delete_run` — so it is backend-independent by construction. Pinned anyway,
    because "by construction" is an argument and this is a measurement, and a
    store is a host-implementable surface.
    """

    def setUp(self):
        self._saved = os.environ.get("NODUS_WORKFLOW_STORE_BACKEND")
        os.environ["NODUS_WORKFLOW_STORE_BACKEND"] = "sqlite"
        self._td = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._td.name)
        reset_default_workflow_runner()
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("NODUS_WORKFLOW_STORE_BACKEND", None)
        else:
            os.environ["NODUS_WORKFLOW_STORE_BACKEND"] = self._saved
        reset_default_workflow_runner()
        os.chdir(self._cwd)
        self._td.cleanup()

    # closes: #734
    def test_sqlite_retires_the_old_one_and_keeps_the_fresh_one(self):
        store = get_default_workflow_runner().store
        self.assertEqual("sqlite", store.store_info().get("backend"))
        for run_id in ("fresh", "old"):
            store.create_run(
                run_id=run_id, graph_id=run_id, workflow_name="w",
                execution_kind="workflow",
            )
        # Backdate through the store rather than the file, since there isn't one.
        record = store.get_run("old")
        record.updated_at = time.time() * 1000 - _THIRTY_ONE_DAYS_MS
        store.restore_run(record)  # #174: writes without re-stamping updated_at

        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(0, main(["nodus", "workflow", "cleanup"]))
        payload = json.loads(out.getvalue().strip())

        self.assertEqual(["old"], payload["run_records_removed"])
        self.assertEqual(
            ["fresh"], sorted(r.run_id for r in get_default_workflow_runner().store.list_runs())
        )


class CancellingAPendingRunStillWorksTests(_StoreHarness):
    """Why `pending` was not simply added to `TERMINAL_RUN_STATUSES`.

    `cancel_run` refuses anything terminal with "already finished". A run that
    never started has not finished, and cancelling it is the reasonable thing to
    want — so the obvious fix would have traded a leak for a lie.
    """

    # closes: #734
    def test_a_pending_run_can_be_cancelled(self):
        self._make("p1")
        result = get_default_workflow_runner().cancel_run("p1")
        self.assertTrue(result.get("ok"), result)
        self.assertEqual("cancelled", self._store().get_run("p1").status)

    # closes: #734
    def test_and_is_then_retired_as_terminal(self):
        """Cancelling puts it in the terminal set, which is where the graph-keyed
        cleanup can already reach it — so the two routes agree on the outcome."""
        self._make("p1")
        get_default_workflow_runner().cancel_run("p1")
        self.assertIn(self._store().get_run("p1").status, TERMINAL_RUN_STATUSES)


if __name__ == "__main__":
    unittest.main()
