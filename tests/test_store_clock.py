"""Persisted timestamps use wall clock, not the process clock (#725).

`runtime_time_ms()` is `(time.monotonic() - _START) * 1000` — milliseconds since
*this* process started. Right for in-process timing, wrong for anything written to
a store, and the workflow package used it for every timestamp it persisted. A wait
registered by one process and swept by another compared two numbers with different
origins, so a deadline meant whatever the sweeper's uptime made it.

`test_a_short_deadline_set_by_an_older_process_is_due` is the bug itself, and it
needs two real processes: inside one, both readings share an origin and the
arithmetic is correct, which is exactly why every existing test passed.

The legacy cases are the other half. Records written before this fix carry
unconvertible values, and **the safe resolution differs by what the value
measures** — a deadline resolves to *not due* (firing early kills work), a
liveness marker to *stale* (honouring it forever strands the run). Both
directions are pinned, because getting either backwards is silent.
"""

import os
import subprocess
import sys
import textwrap
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.runtime_stats import (  # noqa: E402
    STORE_TIME_FLOOR_MS,
    is_store_time,
    store_time_ms,
)
from nodus_lang_workflow.store import create_workflow_store  # noqa: E402


#: A workflow whose only step always fails, so a retry is scheduled and its
#: deadline persisted. Defined at module scope rather than inside the child
#: script, and passed in through the prelude: a newline escape written inside a
#: string that is itself inside a string has to survive two rounds of literal
#: parsing, and getting it wrong produces an IndentationError in the child that
#: reads as a test failure rather than a harness bug.
WORKFLOW_WITH_A_RETRY = """
workflow demo {
    step flaky with { retries: 1, retry_delay_ms: 50 } { throw "fail" }
}
"""


def in_subprocess(cwd: str, body: str) -> subprocess.CompletedProcess:
    # Built by concatenation, not by substituting into a template: dropping a
    # multi-line body into a `{body}` placeholder indents only its first line and
    # leaves the rest where they were, which is an IndentationError in the child
    # and reads as a test failure rather than a harness bug.
    prelude = (
        "import sys, time\n"
        "sys.path.insert(0, %r)\n"
        "WORKFLOW_WITH_A_RETRY = %r\n"
        % (str(_REPO_ROOT / "src"), WORKFLOW_WITH_A_RETRY)
    )
    script = prelude + textwrap.dedent(body).strip() + "\n"
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=cwd, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc


class StoreTimeIsWallClockTests(unittest.TestCase):
    # closes: #725
    def test_store_time_tracks_the_wall_clock(self):
        self.assertAlmostEqual(time.time() * 1000.0, store_time_ms(), delta=2000.0)

    # closes: #725
    def test_a_process_clock_reading_is_not_store_time(self):
        """The discriminator, at both ends of an enormous gap.

        1e12 ms after the epoch is 2001; a process needs 31 years of uptime for
        `runtime_time_ms()` to reach it. Nothing plausible sits between.
        """
        from nodus.runtime.runtime_stats import runtime_time_ms

        self.assertTrue(is_store_time(store_time_ms()))
        self.assertFalse(is_store_time(runtime_time_ms()))
        self.assertFalse(is_store_time(STORE_TIME_FLOOR_MS - 1))
        self.assertTrue(is_store_time(STORE_TIME_FLOOR_MS))
        self.assertFalse(is_store_time(None))
        self.assertFalse(is_store_time("1788375000588"))


class DeadlinesWorkAcrossProcessesTests(unittest.TestCase):
    """The bug, which one process cannot show."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = self._tmp.name

    # closes: #725
    def test_a_short_deadline_set_by_an_older_process_is_due(self):
        """Registered by a process alive ~2s, with a 1ms deadline. Swept by a
        fresh one. Before the fix the fresh process read `now = 516` against
        `expires_at = 4548` and found it not due."""
        in_subprocess(self.cwd, """
            time.sleep(2.0)
            from nodus_lang_workflow.runner import get_default_workflow_runner
            store = get_default_workflow_runner().store
            store.create_run(run_id="late", graph_id="g", workflow_name="w",
                             execution_kind="workflow")
            store.register_wait("late", event_type="e", correlation_key="k",
                                deadline_ms=1.0)
        """)
        proc = in_subprocess(self.cwd, """
            from nodus_lang_workflow.runner import get_default_workflow_runner
            store = get_default_workflow_runner().store
            print([r.run_id for r in store.expire_wait_timeouts()])
        """)
        self.assertIn("late", proc.stdout)

    # closes: #725
    def test_a_long_deadline_set_by_a_fresh_process_is_not_due(self):
        """The failure ran both ways: a long deadline set by a young process used
        to expire instantly under an older one."""
        in_subprocess(self.cwd, """
            from nodus_lang_workflow.runner import get_default_workflow_runner
            store = get_default_workflow_runner().store
            store.create_run(run_id="patient", graph_id="g", workflow_name="w",
                             execution_kind="workflow")
            store.register_wait("patient", event_type="e", correlation_key="k",
                                deadline_ms=600000.0)
        """)
        proc = in_subprocess(self.cwd, """
            time.sleep(1.0)
            from nodus_lang_workflow.runner import get_default_workflow_runner
            store = get_default_workflow_runner().store
            print([r.run_id for r in store.expire_wait_timeouts()])
            print(store.get_run("patient").status)
        """)
        self.assertIn("[]", proc.stdout)
        self.assertIn("waiting", proc.stdout)


class LegacyTimestampsResolveByWhatTheyMeasureTests(unittest.TestCase):
    """Records written before this fix carry unconvertible values."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = create_workflow_store(
            backend="local", root=os.path.join(self._tmp.name, "runs")
        )

    def _run(self, run_id="r1"):
        return self.store.create_run(
            run_id=run_id, graph_id="g", workflow_name="w", execution_kind="workflow"
        )

    # closes: #725
    def test_a_legacy_wait_deadline_is_not_due(self):
        """A deadline is permission to stop work. An uncomparable one resolved as
        *due* kills a run nobody asked to stop."""
        self._run()
        self.store.register_wait(
            "r1", event_type="e", correlation_key="k", deadline_ms=1.0
        )
        record = self.store.get_run("r1")
        record.wait.registered_at = 4547.0  # a pre-#725 process-clock reading
        self.store.restore_run(record)

        self.assertEqual([], self.store.expire_wait_timeouts())
        self.assertEqual("waiting", self.store.get_run("r1").status)

    # closes: #725
    def test_a_legacy_retry_is_not_due(self):
        """Same direction, same reason: firing early discards the backoff the
        retry was scheduled with."""
        self._run()
        self.store.schedule_retry(
            "r1", task_id="t1", step_name="a", attempt=1, max_retries=3,
            delay_ms=1.0, next_attempt_at=store_time_ms() + 1.0,
            classification="transient", last_error="boom",
        )
        record = self.store.get_run("r1")
        record.metadata["retry"]["next_attempt_at"] = 4547.0  # pre-#725
        self.store.restore_run(record)

        self.assertFalse(self.store.retry_due("r1"))
        self.assertEqual([], self.store.list_due_retry_runs())

    # closes: #725
    def test_a_legacy_claim_is_stealable(self):
        """The other direction. A claim is a liveness marker, and one written by a
        process whose clock we cannot read is a process that is gone — honouring
        it forever strands the run, which is the opposite of what claims are for.
        """
        self._run()
        first = self.store.claim_run("r1", owner="gone")
        self.assertIsNotNone(first)
        record = self.store.get_run("r1")
        record.claim.expires_at = 4547.0  # pre-#725
        self.store.restore_run(record)

        self.assertIsNotNone(
            self.store.claim_run("r1", owner="successor"),
            "a legacy claim must not lock a run out forever",
        )


class EveryPersistedDeadlineIsStoreTimeTests(unittest.TestCase):
    """The retry deadline is written **outside** the workflow package.

    The first pass at #725 converted `nodus_lang_workflow` and stopped there, so
    every wait was fixed and every *retry* was still uncomparable across
    processes: `task_graph.py` computes `next_retry_at` and the store merely
    records it. Two framework tests caught it, and the lesson is the one this repo
    keeps relearning — a fix scoped to a package stops at the package boundary,
    and the value crossing that boundary is where the defect survives.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = self._tmp.name

    # closes: #725
    def test_a_scheduled_retry_records_a_wall_clock_deadline(self):
        proc = in_subprocess(self.cwd, """
            from nodus.vm.vm import VM
            from nodus.tooling.runner import run_workflow_code
            from nodus.cli import cli as nodus_cli
            from nodus_lang_workflow.runner import retry_sweeper, get_default_workflow_runner
            import os
            code = WORKFLOW_WITH_A_RETRY
            path = os.path.join(os.getcwd(), "demo.nd")
            open(path, "w", encoding="utf-8").write(code)
            with nodus_cli._project_root_context(os.getcwd()), retry_sweeper():
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None), code,
                    filename=path, project_root=os.getcwd(),
                )
            record = get_default_workflow_runner().get_run(result["result"]["graph_id"])
            print(record.metadata["retry"]["next_attempt_at"])
        """)
        next_attempt_at = float(proc.stdout.strip().splitlines()[-1])
        self.assertTrue(
            is_store_time(next_attempt_at),
            f"a persisted retry deadline must be wall clock, got {next_attempt_at} "
            f"-- that is a process-clock reading, and the sweeping process cannot "
            f"compare it (#725)",
        )


class TheProcessClockIsNotReachedForTests(unittest.TestCase):
    """One question, one clock — asserted on the source.

    The two functions are interchangeable at a glance and only one is right here,
    so behaviour cannot see a regression until two processes disagree. There were
    **17** call sites before this fix; a single one reintroduced is the same bug.
    """

    # closes: #725
    def test_the_workflow_package_never_calls_runtime_time_ms(self):
        offenders = []
        for path in sorted((_REPO_ROOT / "src/nodus_lang_workflow").glob("*.py")):
            if "runtime_time_ms()" in path.read_text(encoding="utf-8"):
                offenders.append(path.name)
        self.assertEqual(
            [], offenders,
            "nodus_lang_workflow persists these timestamps and compares them "
            "across processes, so they must use clock.store_time_ms(). "
            "runtime_time_ms() is milliseconds since *this* process started "
            "(#725).",
        )


if __name__ == "__main__":
    unittest.main()
