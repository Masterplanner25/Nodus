"""Releasing a schedule and resuming the run are one operation (#733).

`on_timeout: "resume"` (#176) turns a wait's deadline into a schedule. Settling
one clears the wait record and marks the run `running` — which destroys the only
handle anything has on it. `expire_wait_timeouts` finds waiting runs, and a
released run is not waiting; adoption finds rehydratable runs, and adopting one
only registers its graph. So a caller that releases a schedule and cannot then
resume it strands the run **permanently and silently**: `running`, steps
`pending`, work never done, no error anywhere.

Four callers released. Two resumed. The two that did not were the worst possible
pair — a background thread that is **on by default** in any process holding the
default runner, and the orphan-adoption path that a bare `rehydrate_runs()` and
every mid-sweep arming goes through.

The fix is a default, not a check: `release_schedules` defaults to False, so a
caller that has not thought about it leaves the wait in place and the next sweep
settles it. That trades a sweep of latency for the work itself, which is the only
direction worth failing in.

`ThePermissionIsNarrowTests` is the one that earns its place. Behaviour cannot
tell a correct caller from a lucky one until they drift, and the drift here is
invisible by construction — a stranded run reports success. So the set of callers
allowed to release is asserted on the source, and a third one has to justify
itself by showing it resumes.
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

from nodus_lang_workflow.store import create_workflow_store  # noqa: E402

SCHEDULED = """
workflow deferred {
    step park { return workflow_wait("later", {deadline_ms: 1i, on_timeout: "resume"}) }
    step work after park { print("the deferred work ran"); return "done" }
}
fn main() { run_workflow(deferred) }
"""

# A schedule that arms its successor from the step the sweep resumed. The new run
# is created *during* the sweep, after the release partition has been computed --
# so adoption is the only thing left that can reach it, and adoption is exactly
# the path that used to strand it.
PERPETUAL = """
workflow tick {
    step park { return workflow_wait("next", {deadline_ms: 1i, on_timeout: "resume"}) }
    step work after park {
        print("fired")
        let next = run_workflow(tick)
        return "rearmed"
    }
}
fn main() { run_workflow(tick) }
"""


def nodus(cwd: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
    proc = subprocess.run(
        [sys.executable, "-m", "nodus", *args],
        capture_output=True, text=True, cwd=cwd, env=env, timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    return proc


def park(cwd: str, source: str) -> None:
    with open(os.path.join(cwd, "flow.nd"), "w", encoding="utf-8") as handle:
        handle.write(source)
    # A CLI subprocess that imports is racing the 200 ms default budget, which
    # nothing in the test mentions (#711).
    nodus(cwd, "run", "flow.nd", "--time-limit", "30")


def sweep(cwd: str) -> dict:
    return json.loads(nodus(cwd, "workflow", "sweep").stdout)


def runs(cwd: str) -> list[dict]:
    return json.loads(nodus(cwd, "workflow", "runs").stdout)["runs"]


class _TempCwd(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = self._tmp.name


class TheStoreWillNotReleaseUnasked(unittest.TestCase):
    """Both backends, because a store is a host-implementable surface and the
    two concrete implementations of this method are byte-identical copies."""

    def _waiting_schedule(self, backend: str, root: str):
        store = create_workflow_store(
            backend=backend,
            root=root,
            path=os.path.join(root, "runs.sqlite3"),
        )
        store.create_run(
            run_id="r1", graph_id="r1", workflow_name="w", execution_kind="workflow"
        )
        store.register_wait(
            "r1", event_type="later", deadline_ms=1.0, on_timeout="resume"
        )
        time.sleep(0.05)  # the deadline is 1 ms; make it unambiguously past
        return store

    # closes: #733
    def test_the_default_leaves_a_due_schedule_waiting(self):
        for backend in ("local", "sqlite"):
            with self.subTest(backend=backend), TemporaryDirectory() as root:
                store = self._waiting_schedule(backend, root)
                self.assertEqual([], store.expire_wait_timeouts())
                record = store.get_run("r1")
                self.assertEqual("waiting", record.status)
                self.assertIsNotNone(
                    record.wait, "the wait record is the only handle on the run"
                )

    # closes: #733
    def test_asking_releases_it(self):
        """The permission is real, not decorative -- the same call with it set
        releases, which is what keeps the sweep working."""
        for backend in ("local", "sqlite"):
            with self.subTest(backend=backend), TemporaryDirectory() as root:
                store = self._waiting_schedule(backend, root)
                released = store.expire_wait_timeouts(release_schedules=True)
                self.assertEqual(["r1"], [r.run_id for r in released])
                self.assertEqual("running", store.get_run("r1").status)

    # closes: #733
    def test_a_patience_limit_still_dead_letters_either_way(self):
        """`release_schedules` gates schedules only. A plain wait running out of
        patience is unrelated, and making it conditional would turn a
        dead-letter into a run that hangs forever."""
        for backend in ("local", "sqlite"):
            with self.subTest(backend=backend), TemporaryDirectory() as root:
                store = create_workflow_store(
                    backend=backend,
                    root=root,
                    path=os.path.join(root, "runs.sqlite3"),
                )
                store.create_run(
                    run_id="r1", graph_id="r1", workflow_name="w",
                    execution_kind="workflow",
                )
                store.register_wait("r1", event_type="later", deadline_ms=1.0)
                time.sleep(0.05)
                self.assertEqual(
                    ["r1"], [r.run_id for r in store.expire_wait_timeouts()]
                )
                self.assertEqual("dead_lettered", store.get_run("r1").status)


class TheBackgroundSweepDoesNotEatSchedules(_TempCwd):
    """`_auto_sweep_loop` runs every 30 s in any process holding the default
    runner, discards what it settles, and cannot resume anything. It was
    releasing schedules -- so a scheduled task was silently dropped by the mere
    passage of time in `nodus serve`, the deployment #176 was built for."""

    # closes: #733
    def test_a_schedule_survives_the_auto_sweep_tick(self):
        park(self.cwd, SCHEDULED)
        probe = os.path.join(self.cwd, "probe.py")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write(
                "import sys, time, json\n"
                "import nodus_lang_workflow.runner as R\n"
                "R._DEFAULT_SWEEP_INTERVAL_S = 0.2\n"
                "runner = R.get_default_workflow_runner()\n"
                "time.sleep(1.5)\n"
                "print(json.dumps([[r.run_id, r.status, r.wait is not None]\n"
                "                  for r in runner.store.list_runs()]))\n"
            )
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
        proc = subprocess.run(
            [sys.executable, "probe.py"],
            capture_output=True, text=True, cwd=self.cwd, env=env, timeout=180,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        observed = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(1, len(observed))
        _run_id, status, has_wait = observed[0]
        self.assertEqual("waiting", status)
        self.assertTrue(has_wait, "the auto-sweep cleared the wait it cannot resume")

    # closes: #733
    def test_and_the_work_still_runs_afterwards(self):
        """The point of leaving it alone: an explicit sweep still does the job.
        Without this, the test above passes for a store that simply lost the
        run."""
        park(self.cwd, SCHEDULED)
        report = sweep(self.cwd)
        self.assertEqual(1, len(report["released_schedules"]))
        self.assertIn("the deferred work ran", report.get("stdout", ""))
        self.assertEqual("completed", runs(self.cwd)[0]["status"])


class AdoptionIsNotResumption(_TempCwd):
    """Rehydration registers a graph so somebody can carry a run on; it
    deliberately executes nothing, because a run record carries the program's
    whole source (#499) and running it on adoption is the boundary #176 refused
    to cross. Which is exactly why it may not release a schedule."""

    # closes: #733
    def test_rehydrating_a_due_schedule_leaves_it_waiting(self):
        park(self.cwd, SCHEDULED)
        probe = os.path.join(self.cwd, "adopt.py")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write(
                "import json\n"
                "from nodus.vm.vm import VM\n"
                "from nodus_lang_workflow.runner import get_default_workflow_runner\n"
                "runner = get_default_workflow_runner()\n"
                "def factory(_record):\n"
                "    vm = VM([], {}, code_locs=[], source_path=None)\n"
                "    vm.workflow_runner = runner\n"
                "    return vm\n"
                "runner.rehydrate_runs(factory)\n"
                "print(json.dumps([[r.run_id, r.status, r.wait is not None]\n"
                "                  for r in runner.store.list_runs()]))\n"
            )
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
        proc = subprocess.run(
            [sys.executable, "adopt.py"],
            capture_output=True, text=True, cwd=self.cwd, env=env, timeout=180,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        observed = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual([True], [entry[2] for entry in observed])
        self.assertEqual(["waiting"], [entry[1] for entry in observed])

        # And the sweep after it still does the work, which is the half that
        # says the run was left recoverable rather than merely untouched.
        self.assertIn("the deferred work ran", sweep(self.cwd).get("stdout", ""))

    # closes: #733
    def test_a_run_armed_during_a_sweep_survives_to_the_next_one(self):
        """Self-perpetuation -- the shape a recurring schedule needs.

        The successor is created after the sweep's release partition is fixed,
        so the same sweep's adoption pass is the only thing that reaches it. That
        pass used to release the new run's wait and then only adopt it, so the
        chain fired exactly once and the second run was stranded forever. Two
        fires is the whole assertion.
        """
        park(self.cwd, PERPETUAL)
        for index in range(2):
            report = sweep(self.cwd)
            with self.subTest(sweep=index):
                self.assertEqual(1, len(report["released_schedules"]))
                self.assertIn("fired", report.get("stdout", ""))

        statuses = sorted(record["status"] for record in runs(self.cwd))
        self.assertEqual(
            ["completed", "completed", "waiting"],
            statuses,
            "two runs fired and the third is armed, with none left stranded",
        )


class ThePermissionIsNarrowTests(unittest.TestCase):
    """Asserted on the source. A stranded run reports success, so behaviour
    cannot distinguish a caller that may release from one that got away with it
    until something is already lost."""

    def _expiry_calls(self) -> dict[str, bool]:
        """Every call to an expiry method in `runner.py`, keyed by the function
        it sits in, valued by whether it asks to release schedules.

        Parsed rather than grepped. The first version of this counted the string
        `release_schedules=True` and was tripped by a *comment* saying the words
        "no `release_schedules=True` here" -- an assertion aimed at a word
        instead of at a construct, which is the failure mode this file exists to
        catch in the code it tests.
        """
        import ast

        source = (_REPO_ROOT / "src" / "nodus_lang_workflow" / "runner.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        found: dict[str, bool] = {}
        for enclosing in ast.walk(tree):
            if not isinstance(enclosing, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(enclosing):
                if not isinstance(node, ast.Call):
                    continue
                attribute = getattr(node.func, "attr", None)
                if attribute not in {"expire_wait_timeout", "expire_wait_timeouts"}:
                    continue
                releases = any(
                    keyword.arg == "release_schedules"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in node.keywords
                )
                # A function holding two such calls keeps the permissive answer:
                # asking anywhere is what has to be justified.
                found[enclosing.name] = found.get(enclosing.name, False) or releases
        return found

    # closes: #733
    def test_only_the_two_resuming_callers_release_schedules(self):
        """`sweep()` resumes each released schedule in the loop below its call,
        and `resume_workflow` is a resume by name. Nothing else may ask.

        Named, not counted: a count is satisfied by any two, including the wrong
        two. A third caller is not forbidden -- it has to show that it resumes
        what it releases, and then add itself here deliberately.
        """
        releasing = {name for name, releases in self._expiry_calls().items() if releases}
        self.assertEqual(
            {"sweep", "resume_workflow"},
            releasing,
            "a caller that releases a schedule must resume it, or it strands the "
            "run permanently -- see #733",
        )

    # closes: #733
    def test_the_paths_that_cannot_resume_are_still_there_and_still_silent(self):
        """The other half: these two must keep calling, at the default.

        Asserting only on the releasing set would pass if someone deleted the
        expiry call from adoption altogether -- which would stop dead-lettering
        an over-patience wait, a different bug in the same place.
        """
        calls = self._expiry_calls()
        for caller in ("_auto_sweep_loop", "_rehydrate_run_claimed"):
            with self.subTest(caller=caller):
                self.assertIn(caller, calls, "this path must still settle waits")
                self.assertFalse(
                    calls[caller], "this path cannot resume, so it may not release"
                )

    # closes: #733
    def test_the_release_is_refused_at_one_place(self):
        """One gate, in the record helper both backends share, rather than a
        check per store. The two concrete `expire_wait_timeout` bodies are
        identical copies; a check written in them would be the duplicated
        question this codebase keeps finding.
        """
        store_source = (
            _REPO_ROOT / "src" / "nodus_lang_workflow" / "store.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            1,
            store_source.count("if not release_schedules:"),
            "the refusal belongs in _expire_wait_timeout_on_record alone",
        )


if __name__ == "__main__":
    unittest.main()
