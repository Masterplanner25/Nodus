"""`nodus workflow sweep` — one sweep, no server (#176).

`WorkflowFrameworkRunner.sweep()` has always expired due waits, resumed due
retries and adopted orphaned runs. Until now the only thing that called it was
`nodus serve`'s background loop, so the issue's *"all automation that spans
process boundaries requires host code"* was true for a narrow reason: the
mechanism existed and had no door onto it. An external cron calling this command
is the missing half — the run's own `deadline_ms` decides what is due, so the
cron's period bounds latency, not correctness.

**Rehydration stays explicit, and `test_the_default_runner_does_not_rehydrate_on_construction`
is the test that keeps it that way.** The issue asks for a `rehydrate_runs()` call
in the default runner's constructor. Since #499 a run record carries the whole
program source and `.nodus/` is CWD-relative, so that would mean entering a
directory someone else prepared compiles and runs their program, at import time,
with nobody having asked. Requiring an operator to type the command is the guard.
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus_lang_workflow.runner import (  # noqa: E402
    WorkflowFrameworkRunner,
    reset_default_workflow_runner,
)
from nodus_lang_workflow.store import create_workflow_store  # noqa: E402


def sweep_in(cwd: str, *args: str) -> tuple[int, dict]:
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
    proc = subprocess.run(
        [sys.executable, "-m", "nodus", "workflow", "sweep", *args],
        capture_output=True, text=True, cwd=cwd, env=env, timeout=120,
    )
    payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return proc.returncode, payload


class SweepRunsWithoutAServerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = self._tmp.name

    def _stranded_wait(self, run_id: str, deadline_ms: float) -> None:
        """A run left `waiting` by a process that is gone.

        Registered directly. Until #725 this had to go through a subprocess:
        deadlines were stored against a per-process monotonic origin, so a wait
        stamped with pytest's uptime looked "not yet due" to a freshly started
        sweeper. Now that persisted timestamps are wall clock, any process's
        reading is comparable with any other's — which is what makes this two
        lines instead of twenty.
        """
        store = create_workflow_store(
            backend="local", root=os.path.join(self.cwd, ".nodus", "workflow_framework")
        )
        store.create_run(
            run_id=run_id, graph_id=f"g_{run_id}",
            workflow_name="w", execution_kind="workflow",
        )
        store.register_wait(
            run_id, event_type="webhook", correlation_key="k", deadline_ms=deadline_ms
        )

    # closes: #176
    def test_a_due_wait_is_expired_by_a_separate_process(self):
        """The whole point: no server, no host code, a different process.

        Asserts the **outcome**, not which mechanism produced it. The default
        runner auto-starts a daemon that expires wait-timeouts, so an explicit
        sweep can legitimately find the work already done and report an empty
        `expired_waits` — asserting on that list races the daemon. What an
        operator actually needs is that the run is no longer waiting once the
        command returns, and that is true either way.
        """
        self._stranded_wait("stranded", deadline_ms=1.0)
        code, _report = sweep_in(self.cwd)
        self.assertEqual(0, code)
        store = create_workflow_store(
            backend="local", root=os.path.join(self.cwd, ".nodus", "workflow_framework")
        )
        self.assertNotEqual("waiting", store.get_run("stranded").status)

    # closes: #176
    def test_a_wait_that_is_not_due_is_left_alone(self):
        """A sweep that expires everything it sees would make the deadline
        decorative, and an external cron would then decide when work dies."""
        self._stranded_wait("patient", deadline_ms=4_000_000_000_000.0)
        code, report = sweep_in(self.cwd)
        self.assertEqual(0, code)
        self.assertEqual([], report["expired_waits"])

    # closes: #176
    def test_an_empty_store_sweeps_cleanly(self):
        code, report = sweep_in(self.cwd)
        self.assertEqual(0, code)
        # Exact, not "every value is empty": a new bucket appearing in the report
        # is a change to this command's contract with whatever parses it, so it
        # should require a deliberate edit here. #176's `released_schedules` was
        # added that way.
        self.assertEqual(
            {
                "expired_waits": [],
                "released_schedules": [],
                "resumed_retries": [],
                "rehydrated_runs": [],
            },
            report,
        )

    # closes: #176
    def test_min_idle_ms_is_accepted(self):
        """A background caller must be able to gate adoption: it cannot tell an
        orphan from a run someone is in the middle of."""
        self._stranded_wait("stranded", deadline_ms=1.0)
        code, _report = sweep_in(self.cwd, "--min-idle-ms", "60000")
        self.assertEqual(0, code)

    # closes: #176
    def test_a_bad_min_idle_ms_is_refused(self):
        code, _ = sweep_in(self.cwd, "--min-idle-ms", "soon")
        self.assertEqual(1, code)


class RehydrationStaysExplicitTests(unittest.TestCase):
    """The security half of the decision, pinned so it is not "tidied" later."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        reset_default_workflow_runner()
        self.addCleanup(reset_default_workflow_runner)

    # closes: #176
    def test_the_default_runner_does_not_rehydrate_on_construction(self):
        """Constructing a runner must not compile and run store-resident source.

        A run record carries the program's whole source (#499) and `.nodus/` is
        CWD-relative, so auto-rehydration on construction means entering a
        directory someone else prepared executes their program. Asserted on the
        source because the safe behaviour is an *absence*: nothing observable
        happens either way until a malicious store exists, and by then it has run.
        """
        source = (_REPO_ROOT / "src/nodus_lang_workflow/runner.py").read_text(
            encoding="utf-8"
        )
        constructor = source[source.index("def get_default_workflow_runner"):]
        constructor = constructor[: constructor.index("\ndef ")]
        self.assertNotIn(
            "rehydrate_runs(", constructor,
            "get_default_workflow_runner() must not rehydrate: it would compile "
            "and run program source from the CWD's store (#499) with nobody "
            "having asked. `nodus workflow sweep` is the explicit door (#176).",
        )

    # closes: #176
    def test_the_constructor_may_expire_waits_and_may_not_rehydrate(self):
        """The split this feature relies on was already made, and is worth pinning.

        The constructor *does* start a daemon that expires wait-timeouts — safe,
        because expiring a deadline executes nothing. It deliberately does not
        rehydrate, and its own comment says why: *"Full retry/rehydration still
        requires the host to provide a vm_factory and call sweep() explicitly."*

        That is the same allow/refuse line #176 needed, drawn before this command
        existed. An earlier version of the test above forbade the substring
        `sweep(` and tripped over `_start_default_sweep_locked` — the reminder
        that a source assertion has to name the construct, not a word that
        appears in it.
        """
        source = (_REPO_ROOT / "src/nodus_lang_workflow/runner.py").read_text(
            encoding="utf-8"
        )
        constructor = source[source.index("def get_default_workflow_runner"):]
        constructor = constructor[: constructor.index("\ndef ")]
        self.assertIn("_start_default_sweep_locked(", constructor)

    # closes: #176
    def test_sweep_is_a_method_a_caller_must_invoke(self):
        """It takes a `vm_factory`, so the caller supplies the execution context —
        which is what makes 'who decided to run this' answerable."""
        self.assertTrue(callable(WorkflowFrameworkRunner.sweep))
        import inspect

        params = inspect.signature(WorkflowFrameworkRunner.sweep).parameters
        self.assertIn("vm_factory", params)
        self.assertIn("min_idle_ms", params)


if __name__ == "__main__":
    unittest.main()
