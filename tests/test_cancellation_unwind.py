"""A timed-out step unwinds through its `finally` blocks before it is dropped.

`EXECUTION_INVARIANTS.md` I-VM-06 states that `finally` blocks always execute.
The scheduler used to discard a timed-out coroutine where it stood, so they did
not: a step holding a lock, an open transaction or a spawned subprocess lost its
release in exactly the circumstances cleanup exists for (#502).

`timeout_ms` is the sharper of the two triggers, because it is a documented step
option whose entire purpose is to bound a step that might hang. A user who bounds
a hanging step *and* wraps its resource in `try/finally` has done everything the
documentation asks and still leaked.

The other trigger -- a sibling step failing -- was fixed by draining the run
instead of tearing down the scheduler; see `test_failure_drain_and_statuses.py`.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        cwd = os.getcwd()
        os.chdir(td)
        try:
            return NodusRuntime(timeout_ms=None, max_steps=None).run_source(source)
        finally:
            os.chdir(cwd)


TIMED_OUT_STEP = """
workflow tmo {{
    step slow with {{ timeout_ms: 100 }} {{
        print("ACQUIRED")
        try {{
            sleep(2000i)
            print("FINISHED")
        }} catch e {{
            print("CAUGHT")
        }} finally {{
            print("RELEASED")
        }}
        return 1i
    }}
}}
fn main() {{
    let r = run_workflow(tmo)
    let f = r["failed"]
    print("FAILED=\\(f)")
}}
"""


class ATimedOutStepRunsItsFinallyTests(unittest.TestCase):
    """Falsifiable: reverting the scheduler's timeout branch to drop the coroutine
    (no `unwind_cancelled_coroutine` call) fails the first two of these."""

    def setUp(self):
        self.stdout = _run(TIMED_OUT_STEP.format()).get("stdout") or ""

    def test_the_step_body_started(self):
        self.assertIn("ACQUIRED", self.stdout)

    # closes: #502
    def test_the_finally_block_runs(self):
        self.assertIn("RELEASED", self.stdout)

    def test_the_step_still_fails(self):
        """Cleanup must not rescue the step. A timeout that let the step succeed
        would be worse than one that leaked."""
        self.assertIn('FAILED=["slow"]', self.stdout)

    def test_the_work_after_the_timeout_does_not_run(self):
        self.assertNotIn("FINISHED", self.stdout)


class ACatchCannotSwallowTheDeadlineTests(unittest.TestCase):
    """The design constraint that made this more than a plumbing change.

    Unwinding by throwing an ordinary error into the coroutine would let a
    `catch` absorb it and the step carry on past the deadline that was supposed
    to bound it. `handle_exception` therefore refuses to enter a catch while
    cancelling: `finally` runs, `catch` does not.
    """

    def test_the_catch_block_does_not_run(self):
        stdout = _run(TIMED_OUT_STEP.format()).get("stdout") or ""
        self.assertIn("RELEASED", stdout)
        self.assertNotIn("CAUGHT", stdout)

    def test_a_catch_only_step_still_times_out(self):
        """No `finally` at all: the step must still fail, and the catch must still
        not see the timeout."""
        stdout = _run(
            """
workflow tmo {
    step slow with { timeout_ms: 100 } {
        try { sleep(2000i) } catch e { print("CAUGHT") }
        print("AFTER")
        return 1i
    }
}
fn main() {
    let r = run_workflow(tmo)
    let f = r["failed"]
    print("FAILED=\\(f)")
}
"""
        ).get("stdout") or ""
        self.assertNotIn("CAUGHT", stdout)
        self.assertNotIn("AFTER", stdout)
        self.assertIn('FAILED=["slow"]', stdout)


class NestedFinallysAllRunTests(unittest.TestCase):
    def test_every_pending_finally_runs_innermost_first(self):
        stdout = _run(
            """
workflow tmo {
    step slow with { timeout_ms: 100 } {
        try {
            try {
                sleep(2000i)
            } catch e { print("INNER-CAUGHT") } finally {
                print("INNER")
            }
        } catch e { print("OUTER-CAUGHT") } finally {
            print("OUTER")
        }
        return 1i
    }
}
fn main() { let r = run_workflow(tmo); return nil }
"""
        ).get("stdout") or ""
        self.assertIn("INNER", stdout)
        self.assertIn("OUTER", stdout)
        self.assertLess(stdout.index("INNER"), stdout.index("OUTER"))


class TheCallerSurvivesTheUnwindTests(unittest.TestCase):
    """The unwind swaps the coroutine's stack and frames into the VM, so it has to
    save and restore the caller's first -- skipping that destroyed `main`'s frames
    and the driver silently stopped after the workflow returned."""

    def test_the_caller_keeps_running_after_a_timed_out_step(self):
        stdout = _run(TIMED_OUT_STEP.format()).get("stdout") or ""
        self.assertIn("FAILED=", stdout, "the caller did not resume after the unwind")

    def test_a_second_workflow_runs_after_a_timeout(self):
        stdout = _run(
            """
workflow tmo {
    step slow with { timeout_ms: 100 } {
        try { sleep(2000i) } catch e { print("CAUGHT") } finally { print("RELEASED") }
        return 1i
    }
}
workflow after_it { step ok { print("SECOND"); return 2i } }
fn main() {
    let a = run_workflow(tmo)
    let b = run_workflow(after_it)
    let s = b["steps"]
    print("B=\\(s)")
}
"""
        ).get("stdout") or ""
        self.assertIn("RELEASED", stdout)
        self.assertIn("SECOND", stdout)
        self.assertIn('B={"ok": 2}', stdout)


class StepsWithoutHandlersTakeTheOriginalPathTests(unittest.TestCase):
    """A coroutine with nothing pending is dropped exactly as before -- no extra
    resume, no behaviour change for the common case."""

    def test_a_plain_timed_out_step_still_fails(self):
        stdout = _run(
            """
workflow tmo {
    step slow with { timeout_ms: 100 } { sleep(2000i); return 1i }
}
fn main() {
    let r = run_workflow(tmo)
    let f = r["failed"]
    print("FAILED=\\(f)")
}
"""
        ).get("stdout") or ""
        self.assertIn('FAILED=["slow"]', stdout)


if __name__ == "__main__":
    unittest.main()
