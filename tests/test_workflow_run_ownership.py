"""A workflow run has an owner, and nothing may take it from them (#376).

Four defects sat behind one intermittent failure whose signature was a resume
returning ``ok: true`` with the result keys missing. All four were fixed across
PRs #388 and #389 with no dedicated regression test — the tests those PRs touched
were assertion improvements on existing cases, which is exactly the shape that
lets a fix rot silently. This file pins the four behaviours.

Each test is written so it fails against the code as it was before the fix, and
the two gating tests carry their own positive control in the same test, because a
"nothing happened" assertion passes just as happily when the setup was wrong.

The four:

1. ``sweep()`` must not adopt a run that was touched moments ago. Rehydration
   exists for runs whose owner is *gone*; a background sweeper cannot tell an
   orphan from a run someone is mid-way through, and guessing wrong corrupts the
   live one.
2. ``rehydrate_run()`` must claim before adopting. It is not read-only — it
   rebinds the process-global registry entry to its own VM.
3. ``list_runs()`` must hold the store lock. Lock-free scans held a file open
   across another thread's ``os.replace``, which Windows refuses.
4. Resuming must not run under the 200 ms budget sized for executing a script.

See also ``test_workflow_store_isolation.py`` (#380) and issue #390, which tracks
the root all four share: workflow state is process-global with no owner.
"""

import inspect
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.support.config import EXECUTION_TIMEOUT_MS, RESUME_TIMEOUT_MS  # noqa: E402
from nodus.tooling.runner import resume_workflow, resume_workflow_in_vm  # noqa: E402
from nodus_lang_workflow.runner import WorkflowFrameworkRunner  # noqa: E402
from nodus_lang_workflow.store import (  # noqa: E402
    RUN_STATUS_RUNNING,
    LocalWorkflowStore,
)


class _FakeVM:
    """The minimum a sweep's ``vm_factory`` result has to look like."""

    def _rebuild_workflow_graph(self, *args, **kwargs):  # pragma: no cover - not reached
        raise AssertionError("the sweep should not have got this far")


def _running_run(store: LocalWorkflowStore, run_id: str = "g_owned"):
    """A run in a status the sweeper considers rehydratable, updated just now."""
    record = store.create_run(
        run_id=run_id,
        graph_id=run_id,
        workflow_name="w",
        execution_kind="workflow",
    )
    record.status = RUN_STATUS_RUNNING
    return store.save_run(record)


class SweepOwnershipTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = LocalWorkflowStore(root=self._tmp.name)
        self.runner = WorkflowFrameworkRunner(store=self.store)

    # closes: #376
    def test_sweep_leaves_a_run_that_was_touched_moments_ago(self):
        """A background sweeper must not adopt a run someone is still on.

        `RuntimeService` sweeps every 500 ms. Before the fix `sweep()` adopted
        every non-terminal run in the store regardless of how recently it had been
        written, including runs the service never created.
        """
        record = _running_run(self.store)
        self.assertIn(
            record.run_id,
            {r.run_id for r in self.runner.list_rehydratable_runs()},
            "setup: the run must be visible to the sweep, or this proves nothing",
        )

        offered: list[str] = []

        def vm_factory(rec):
            offered.append(rec.run_id)
            return None  # stop before the real adoption; being offered is the tell

        # A live run, and a horizon far longer than the age of that run.
        self.runner.sweep(vm_factory, min_idle_ms=30_000.0)
        self.assertEqual([], offered, "sweep adopted a run that was just written")

        # Positive control: the *only* thing changed is the idle horizon.
        self.runner.sweep(vm_factory, min_idle_ms=0.0)
        self.assertEqual(
            [record.run_id], offered, "setup: the run was never adoptable at all"
        )

    def test_default_sweep_still_adopts_immediately(self):
        """`min_idle_ms` defaults to 0: explicit callers are unchanged.

        The gate is for background sweepers that cannot tell an orphan from a live
        run. A caller that asks for a sweep directly has already decided.
        """
        _running_run(self.store)
        offered: list[str] = []
        self.runner.sweep(lambda rec: offered.append(rec.run_id))
        self.assertEqual(["g_owned"], offered)


class RehydrateClaimTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = LocalWorkflowStore(root=self._tmp.name)
        self.runner = WorkflowFrameworkRunner(store=self.store)
        self.adopted: list[str] = []
        # The delegation seam. Whether the *body* of rehydration runs is the
        # question; what it then does is covered by the workflow DSL tests.
        self.runner._rehydrate_run_claimed = (
            lambda vm, run_id, *, rebuild_graph: self.adopted.append(run_id)
        )

    def test_rehydrate_skips_a_run_another_owner_holds(self):
        """Rehydration rebinds the global registry entry — it must claim first.

        `resume_workflow()` has always claimed. `rehydrate_run()` did not, so the
        two could rebind the same run concurrently and the loser's resume returned
        `ok: true` with empty steps.
        """
        record = _running_run(self.store)
        claim = self.store.claim_run(record.run_id, owner="someone-else")
        self.assertIsNotNone(claim, "setup: the run must be claimable to be claimed")

        result = self.runner.rehydrate_run(
            _FakeVM(), record.run_id, rebuild_graph=lambda *a, **k: None
        )
        self.assertIsNone(result, "rehydrate adopted a run another owner held")
        self.assertEqual([], self.adopted)

        # Positive control: released, the same call goes through.
        self.store.release_claim(record.run_id, claim.token)
        self.runner.rehydrate_run(
            _FakeVM(), record.run_id, rebuild_graph=lambda *a, **k: None
        )
        self.assertEqual([record.run_id], self.adopted)

    def test_rehydrate_releases_its_claim_afterwards(self):
        """Otherwise one adoption locks the run out for the claim TTL (30 s)."""
        record = _running_run(self.store)
        self.runner.rehydrate_run(
            _FakeVM(), record.run_id, rebuild_graph=lambda *a, **k: None
        )
        self.assertIsNone(
            self.store.get_run(record.run_id).claim,
            "rehydrate held its claim after finishing",
        )


class _CountingLock:
    """A lock that records how often it was entered."""

    def __init__(self):
        self._inner = threading.Lock()
        self.entered = 0

    def __enter__(self):
        self._inner.acquire()
        self.entered += 1
        return self

    def __exit__(self, *exc):
        self._inner.release()
        return False

    def acquire(self, *a, **k):
        return self._inner.acquire(*a, **k)

    def release(self):
        return self._inner.release()


class StoreReadLockingTests(unittest.TestCase):
    """#376 cause 3: lock-free reads vs. Windows `os.replace`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = LocalWorkflowStore(root=self._tmp.name)

    def test_list_runs_scans_under_the_store_lock(self):
        """Instrumented rather than timed — a race test that sleeps proves nothing.

        On Windows, replacing a file another thread has open fails with
        `[WinError 5] Access is denied` and the run record is lost. POSIX permits
        it, which is why this never showed up on CI.
        """
        _running_run(self.store)
        counting = _CountingLock()
        self.store._lock = counting

        before = counting.entered
        self.store.list_runs()
        self.assertGreater(
            counting.entered, before, "list_runs() scanned without the store lock"
        )

    def test_atomic_write_retries_a_sharing_violation(self):
        """A scanner or indexer can hold a handle for a few ms; waiting is enough.

        The in-process case is fixed by the lock above. This covers the rest.
        """
        src = os.path.join(self._tmp.name, "src.tmp")
        dst = os.path.join(self._tmp.name, "dst.json")
        with open(src, "w", encoding="utf-8") as handle:
            handle.write("{}")

        real_replace = os.replace
        calls = {"n": 0}

        def flaky_replace(a, b):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError(5, "Access is denied")
            return real_replace(a, b)

        os.replace = flaky_replace
        try:
            LocalWorkflowStore._replace_with_retry(src, dst)
        finally:
            os.replace = real_replace

        self.assertEqual(3, calls["n"], "the replace was not retried")
        self.assertTrue(os.path.isfile(dst), "the record was lost to a transient denial")

    def test_atomic_write_gives_up_rather_than_hanging(self):
        """A retry loop with no end is a worse bug than the one it fixes."""
        src = os.path.join(self._tmp.name, "src2.tmp")
        with open(src, "w", encoding="utf-8") as handle:
            handle.write("{}")

        real_replace = os.replace

        def always_denied(a, b):
            raise PermissionError(5, "Access is denied")

        os.replace = always_denied
        try:
            with self.assertRaises(PermissionError):
                LocalWorkflowStore._replace_with_retry(
                    src, os.path.join(self._tmp.name, "dst2.json")
                )
        finally:
            os.replace = real_replace


class ResumeBudgetTests(unittest.TestCase):
    """#376 cause 4: resume charged against a script-execution budget."""

    def test_resume_does_not_use_the_script_execution_budget(self):
        """A resume reads state from disk and recompiles the workflow first.

        None of that is step execution, and all of it was charged to
        `EXECUTION_TIMEOUT_MS` (200 ms). Under load the resume died with
        "Execution timed out" instead of returning.
        """
        for fn in (resume_workflow_in_vm, resume_workflow):
            default = inspect.signature(fn).parameters["timeout_ms"].default
            self.assertEqual(
                RESUME_TIMEOUT_MS,
                default,
                f"{fn.__name__} does not use the resume budget",
            )
            self.assertNotEqual(
                EXECUTION_TIMEOUT_MS,
                default,
                f"{fn.__name__} is back on the script-execution budget",
            )

    def test_the_resume_budget_is_bounded_but_proportionate(self):
        """Bounded — `None` here would be an unbounded host-side hang (cf. #350)."""
        self.assertIsNotNone(RESUME_TIMEOUT_MS)
        self.assertGreaterEqual(RESUME_TIMEOUT_MS, 5_000)


if __name__ == "__main__":
    unittest.main()
