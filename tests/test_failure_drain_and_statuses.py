"""A failing step drains the run rather than breaking the scheduler loop, and
every task gets a reported status.

Before this, `_fail_task` returned True, which told `Scheduler.run_loop` to
`break`. That dropped every other coroutine where it stood -- including healthy
independent branches, mid-execution, without unwinding them, so their `finally`
never ran (#502). The tasks that never got a turn were then absent from the
result entirely: `steps` omitted them and `failed` named only the step that
threw, so a failing run reported one of four distinguishable outcomes (#475,
#503).

Each test here was checked against the unfixed tree rather than assumed to be
falsifiable. Restoring `return True` in `_fail_task` fails four of them;
dropping `failed` from `spawn_task`'s refusal guard fails
`test_task_ready_after_failure_is_cancelled`.

That second lever is worth naming precisely, because it is *not* new. "Stop
scheduling new work once a step has failed" was already correct -- `spawn_task`
has refused since long before this change. What was broken was only that the
scheduler loop was torn down as well, so nothing survived to observe it.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> dict:
    """Run a script in its own directory so the graph store stays isolated."""
    with tempfile.TemporaryDirectory() as td:
        cwd = os.getcwd()
        os.chdir(td)
        try:
            rt = NodusRuntime(timeout_ms=None, max_steps=None)
            return rt.run_source(source)
        finally:
            os.chdir(cwd)


class InFlightWorkSurvivesASiblingFailureTests(unittest.TestCase):
    def test_in_flight_sibling_runs_to_completion(self):
        result = _run(
            """
workflow inflight {
    step a { return 1i }
    step slow after a { sleep(60i); print("SLOW-FINISHED"); return 2i }
    step boom after a { sleep(10i); throw "boom" }
}
fn main() {
    let r = run_workflow(inflight)
    let s = r["steps"]
    print("steps=\\(s)")
}
"""
        )
        stdout = result.get("stdout") or ""
        # Pre-fix the scheduler broke here and `slow` was abandoned mid-sleep.
        self.assertIn("SLOW-FINISHED", stdout)
        self.assertIn('"slow": 2', stdout)

    def test_abandoned_step_still_runs_its_finally(self):
        """I-VM-06: `finally` blocks always execute.

        A sibling's failure used to drop an in-flight coroutine without
        unwinding it, so a step holding a resource lost its release in exactly
        the circumstances cleanup exists for. This covers the sibling-failure
        trigger; the `timeout_ms` trigger is still open (#502).
        """
        result = _run(
            """
workflow cleanup {
    step a { return 1i }
    step slow after a {
        try { sleep(60i) } catch e { print("CAUGHT") } finally { print("RELEASED") }
        return 2i
    }
    step boom after a { sleep(10i); throw "boom" }
}
fn main() { let r = run_workflow(cleanup); return nil }
"""
        )
        self.assertIn("RELEASED", result.get("stdout") or "")


class EveryTaskGetsAReportedStatusTests(unittest.TestCase):
    def _statuses(self, source: str) -> dict:
        result = _run(source)
        self.assertIsNone(result.get("error"), msg=result.get("error"))
        line = [ln for ln in (result.get("stdout") or "").splitlines() if ln.startswith("S=")]
        self.assertTrue(line, msg=f"no status line in {result.get('stdout')!r}")
        return line[0]

    def test_failed_and_upstream_failed_are_distinguished(self):
        """A step that threw and a step blocked behind it are different outcomes."""
        rendered = self._statuses(
            """
workflow joinfail {
    step a { return 1i }
    step c { throw "c blew up" }
    step d after a, c { return 4i }
}
fn main() {
    let r = run_workflow(joinfail)
    let st = r["statuses"]
    print("S=\\(st)")
}
"""
        )
        self.assertIn('"c": "failed"', rendered)
        self.assertIn('"d": "upstream_failed"', rendered)
        self.assertIn('"a": "completed"', rendered)

    def test_task_ready_after_failure_is_cancelled(self):
        """New work is not scheduled once a step has failed, and says so.

        `later` only becomes ready when `slow` completes, which happens after
        `boom` has already failed. It is not blocked by the failure -- its own
        dependency succeeded -- so it is `cancelled`, not `upstream_failed`.
        Whether it should run anyway is the open half of #475; naming it makes
        that choice visible rather than silent.
        """
        rendered = self._statuses(
            """
workflow late {
    step boom { sleep(10i); throw "boom" }
    step slow { sleep(60i); return 1i }
    step later after slow { return 2i }
}
fn main() {
    let r = run_workflow(late)
    let st = r["statuses"]
    print("S=\\(st)")
}
"""
        )
        self.assertIn('"boom": "failed"', rendered)
        self.assertIn('"slow": "completed"', rendered)
        self.assertIn('"later": "cancelled"', rendered)

    def test_successful_run_reports_every_step_completed(self):
        rendered = self._statuses(
            """
workflow ok {
    step a { return 1i }
    step b after a { return 2i }
}
fn main() {
    let r = run_workflow(ok)
    let st = r["statuses"]
    print("S=\\(st)")
}
"""
        )
        self.assertIn('"a": "completed"', rendered)
        self.assertIn('"b": "completed"', rendered)

    def test_bare_graph_reports_task_statuses_without_step_names(self):
        """`run_graph` has no step names, so only the task-keyed map applies --
        mirroring how `tasks` is populated and `steps` is not."""
        result = _run(
            """
fn main() {
    let t1 = task(fn() { return 1i }, nil)
    let r = run_graph([t1])
    let ts = r["task_statuses"]
    print("T=\\(ts)")
}
"""
        )
        self.assertIn('"completed"', result.get("stdout") or "")


class FailurePayloadIsFinalisedAtTheEndTests(unittest.TestCase):
    def test_steps_includes_work_completed_after_the_failure(self):
        """`_fail_task` builds the payload when the first step fails, but the run
        keeps draining, so anything captured by value there is stale by the time
        it is returned."""
        result = _run(
            """
workflow drain {
    step a { return 1i }
    step slow after a { sleep(60i); return 99i }
    step boom after a { sleep(10i); throw "boom" }
}
fn main() {
    let r = run_workflow(drain)
    let s = r["steps"]
    let f = r["failed"]
    print("steps=\\(s) failed=\\(f)")
}
"""
        )
        stdout = result.get("stdout") or ""
        # `slow` finished after `boom` failed; a stale snapshot would omit it.
        self.assertIn('"slow": 99', stdout)
        self.assertIn('failed=["boom"]', stdout)


if __name__ == "__main__":
    unittest.main()
