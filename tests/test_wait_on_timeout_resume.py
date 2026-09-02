"""A wait whose deadline *resumes* instead of failing — self-scheduling (#176).

`workflow_wait` has always meant "park until this event arrives, and dead-letter
if it does not". That makes a deadline a patience limit. #176 wants the other
reading: park until a *time*, then carry on — which is what lets a workflow
schedule itself across a process boundary without host code.

`on_timeout: "resume"` is that, and it is deliberately the whole feature. A
scheduled run is an ordinary run that parked, so rehydration, resume, the store
and the sweep all work unchanged; nothing new executes anything. The operator's
`nodus workflow sweep` is still the only thing that starts work, which is where
the security boundary was put and where it stays.

`test_the_persisted_wait_carries_the_policy` is the one that earns its place. The
wait record is rebuilt **field by field in four places** between the builtin and
the store, and `on_timeout` was silently dropped at the third on the first pass:
the run parked correctly, the report looked right, and the policy simply was not
there. `schema` was lost the same way when it was added (#472), and the code
comment warning about it is what found this.
"""

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.orchestration.workflow_state import WAIT_TIMEOUT_POLICIES  # noqa: E402
from nodus_lang_workflow.models import WorkflowWaitRecord  # noqa: E402

SCHEDULED = """
workflow deferred {
    step park { return workflow_wait("later", {deadline_ms: %d, on_timeout: "resume"}) }
    step work after park { print("the deferred work ran"); return "done" }
}
fn main() { run_workflow(deferred) }
"""

IMPATIENT = """
workflow deferred {
    step park { return workflow_wait("later", {deadline_ms: %d}) }
    step work after park { return "done" }
}
fn main() { run_workflow(deferred) }
"""


def nodus(cwd: str, *args: str, expect_ok: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
    proc = subprocess.run(
        [sys.executable, "-m", "nodus", *args],
        capture_output=True, text=True, cwd=cwd, env=env, timeout=180,
    )
    if expect_ok:
        assert proc.returncode == 0, proc.stderr
    return proc


def park(cwd: str, source: str, deadline_ms: int) -> None:
    with open(os.path.join(cwd, "flow.nd"), "w", encoding="utf-8") as handle:
        handle.write(source % deadline_ms)
    nodus(cwd, "run", "flow.nd", "--time-limit", "30")


def runs(cwd: str) -> list[dict]:
    proc = nodus(cwd, "workflow", "runs")
    return json.loads(proc.stdout)["runs"]


class SelfSchedulingAcrossAProcessBoundaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = self._tmp.name

    # closes: #176
    def test_a_parked_run_resumes_and_completes_on_a_later_sweep(self):
        """The whole feature, end to end, in three processes.

        One runs and parks; one sweeps; the work runs in the sweeper. Nothing
        auto-started anything -- the sweep is an explicit command.
        """
        park(self.cwd, SCHEDULED, 800)
        self.assertEqual("waiting", runs(self.cwd)[0]["status"])

        time.sleep(1.5)
        report = json.loads(nodus(self.cwd, "workflow", "sweep").stdout)

        self.assertEqual([], report["expired_waits"])
        self.assertEqual(1, len(report["released_schedules"]))
        self.assertTrue(report["released_schedules"][0]["ok"])
        self.assertEqual("completed", runs(self.cwd)[0]["status"])

    # closes: #176
    def test_the_resumed_step_actually_runs(self):
        """Status alone is not evidence: rehydration marks a run `running`
        without executing anything, which is what the first implementation did.
        The step's own output is the proof."""
        park(self.cwd, SCHEDULED, 800)
        time.sleep(1.5)
        report = json.loads(nodus(self.cwd, "workflow", "sweep").stdout)
        self.assertIn("the deferred work ran", report.get("stdout", ""))

    # closes: #176
    def test_program_output_does_not_corrupt_the_report(self):
        """A resumed workflow runs inside the sweep, so its `print`s land on this
        process's stdout. The report is the command's contract with the cron
        calling it, so the output is captured into it rather than emitted around
        it -- `json.loads` above would fail otherwise."""
        park(self.cwd, SCHEDULED, 800)
        time.sleep(1.5)
        stdout = nodus(self.cwd, "workflow", "sweep").stdout
        json.loads(stdout)  # the assertion is that this does not raise
        self.assertTrue(stdout.lstrip().startswith("{"))

    # closes: #176
    def test_the_default_still_dead_letters(self):
        """Unchanged behaviour for every wait written before this existed: a
        deadline that passes is an error, not a schedule."""
        park(self.cwd, IMPATIENT, 800)
        time.sleep(1.5)
        report = json.loads(nodus(self.cwd, "workflow", "sweep").stdout)

        self.assertEqual(1, len(report["expired_waits"]))
        self.assertEqual([], report["released_schedules"])
        self.assertEqual("dead_lettered", runs(self.cwd)[0]["status"])


class ThePolicySurvivesEveryHandOffTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = self._tmp.name

    # closes: #176
    def test_the_persisted_wait_carries_the_policy(self):
        """Between the builtin and the store the wait is rebuilt field by field in
        four places. `on_timeout` was dropped at the third on the first pass --
        the run parked, the report looked right, and the policy was not there.

        This asserts on the **stored record**, which is the only place all four
        hand-offs have already happened.
        """
        park(self.cwd, SCHEDULED, 60_000)
        wait = runs(self.cwd)[0]["wait"]
        self.assertIsNotNone(wait)
        self.assertEqual("resume", wait.get("on_timeout"))

    # closes: #176
    def test_an_unknown_policy_is_refused_where_it_is_written(self):
        """A typo silently meaning "fail" would turn a schedule into a
        dead-letter, and surface hours later as work that never ran."""
        with open(os.path.join(self.cwd, "bad.nd"), "w", encoding="utf-8") as handle:
            handle.write(
                'workflow w {\n'
                '    step a { return workflow_wait("e", {deadline_ms: 10i, on_timeout: "retry"}) }\n'
                '}\n'
                'fn main() { run_workflow(w) }\n'
            )
        proc = nodus(self.cwd, "run", "bad.nd", "--time-limit", "30", expect_ok=False)
        combined = proc.stdout + proc.stderr
        self.assertIn("on_timeout must be one of", combined)
        self.assertIn("fail", combined)
        self.assertIn("resume", combined)


class TheRecordRoundTripsTests(unittest.TestCase):
    # closes: #176
    def test_a_record_written_before_this_feature_reads_as_fail(self):
        restored = WorkflowWaitRecord.from_dict(
            {"event_type": "e", "registered_at": 1.0, "deadline_ms": 2.0}
        )
        self.assertEqual("fail", restored.on_timeout)

    # closes: #176
    def test_the_default_is_omitted_so_old_records_round_trip_unchanged(self):
        """The rule `schema` already follows: a run recorded before the field
        existed must serialise byte-identically afterwards."""
        self.assertNotIn("on_timeout", WorkflowWaitRecord(event_type="e").to_dict())
        self.assertEqual(
            "resume",
            WorkflowWaitRecord(event_type="e", on_timeout="resume").to_dict()["on_timeout"],
        )

    # closes: #176
    def test_an_unknown_stored_value_falls_back_to_fail(self):
        """Hand-edited or written by something newer. `fail` is the safe reading:
        it is what every record predating the field meant."""
        restored = WorkflowWaitRecord.from_dict(
            {"event_type": "e", "on_timeout": "explode"}
        )
        self.assertEqual("fail", restored.on_timeout)

    # closes: #176
    def test_the_vocabulary_is_named_once(self):
        """Defined in core, where the VM, the task graph and the store can all
        read it. A second copy in the workflow package would make `task_graph`
        import it, which is the direction CIRC-001 was fixed to remove."""
        self.assertEqual({"fail", "resume"}, set(WAIT_TIMEOUT_POLICIES))
        for module in ("src/nodus/vm/vm.py", "src/nodus/orchestration/task_graph.py",
                       "src/nodus_lang_workflow/models.py",
                       "src/nodus_lang_workflow/runner.py"):
            with self.subTest(module=module):
                source = (_REPO_ROOT / module).read_text(encoding="utf-8")
                self.assertNotIn(
                    'WAIT_TIMEOUT_POLICIES = ', source,
                    f"{module} defines its own copy; import it from "
                    f"nodus.orchestration.workflow_state instead",
                )


if __name__ == "__main__":
    unittest.main()
