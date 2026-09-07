"""Switching to SQLite must not silently hide the runs you already have (#174).

**This is the harm #174 is about, and it is reachable today.** Measured on
5.11.0: park a run at `workflow_wait` under the default local store, set
`NODUS_WORKFLOW_STORE_BACKEND=sqlite`, and `nodus workflow runs` reports **0
runs and exits 0**. The parked run still exists. Nothing says so. As far as
every `nodus workflow` command is concerned it is gone.

At 6.0.0 that switch happens *by default*, which is why the flip carried a long
deprecation clock — a silent failure needs notice in a way a loud one does not.
Making it loud is what shortens the clock rather than waiting it out.

Warning in 5.x, error at 6.0.0. The condition is the same either way — "SQLite
is in effect and these runs are not in it" — so the flip does not need a second
implementation to become a refusal.

The quiet cases matter as much as the loud one. `docs/migration/v6.0-staged-flips.md`
tells people to keep the JSON store until they have checked the new one, so a
populated JSON store after a correct migration is the *expected* state. Warning
then would train people to ignore this.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

PARKED = """workflow approval {
    step analyze {
        return "analyzed"
    }
    step gate after analyze {
        return workflow_wait("approval.granted")
    }
}
"""


class _Project(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        with open(os.path.join(self.dir, "approval.nd"), "w", encoding="utf-8") as handle:
            handle.write(PARKED)

    def nodus(self, *args: str, backend: str | None = None):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO / "src")
        env.pop("NODUS_WORKFLOW_STORE_BACKEND", None)
        env.pop("NODUS_STAGED_FLIP_REPORT", None)
        if backend:
            env["NODUS_WORKFLOW_STORE_BACKEND"] = backend
        return subprocess.run(
            [PYTHON, "-m", "nodus", *args],
            cwd=self.dir, capture_output=True, text=True, env=env, timeout=120,
        )

    def park_a_run(self) -> str:
        """Leave one `waiting` run in the default (local) store."""
        self.nodus("workflow", "run", "approval.nd", "--workflow", "approval")
        runs = Path(self.dir) / ".nodus" / "workflow_framework" / "runs"
        ids = [p.stem for p in runs.glob("*.json")]
        self.assertEqual(len(ids), 1, f"setup: expected one parked run, got {ids}")
        record = json.loads((runs / f"{ids[0]}.json").read_text(encoding="utf-8"))
        self.assertEqual(
            record.get("status"), "waiting",
            "setup: the run must be parked, or this tests the harmless case",
        )
        return ids[0]


class StrandedRunsAreAnnouncedTests(_Project):
    # closes: #797
    def test_switching_to_sqlite_announces_the_runs_it_cannot_see(self):
        run_id = self.park_a_run()
        result = self.nodus("workflow", "runs", backend="sqlite")
        self.assertIn("not in the SQLite store", result.stderr)
        self.assertIn(run_id, result.stderr, "the warning must name what is stranded")
        self.assertIn("migrate-store", result.stderr, "and what to type")

    def test_the_warning_says_it_becomes_an_error_at_the_major(self):
        self.park_a_run()
        result = self.nodus("workflow", "runs", backend="sqlite")
        self.assertIn("error in 6.0.0", result.stderr)

    def test_it_does_not_fail_the_command(self):
        """A warning in 5.x. The refusal is the 6.0.0 half."""
        self.park_a_run()
        result = self.nodus("workflow", "runs", backend="sqlite")
        self.assertEqual(result.returncode, 0)


class QuietCasesTests(_Project):
    """Each of these would make the warning noise, and noise gets ignored."""

    def test_silent_after_a_migration(self):
        """The guide says keep the old store; a correct migration must be quiet."""
        run_id = self.park_a_run()
        self.nodus("workflow", "migrate-store", "--to", "sqlite")
        result = self.nodus("workflow", "runs", backend="sqlite")
        self.assertNotIn("not in the SQLite store", result.stderr)
        self.assertIn(run_id, result.stdout, "the run should now be visible")

    def test_silent_on_the_local_backend(self):
        self.park_a_run()
        result = self.nodus("workflow", "runs", backend="local")
        self.assertNotIn("not in the SQLite store", result.stderr)

    def test_silent_with_no_runs_at_all(self):
        result = self.nodus("workflow", "runs", backend="sqlite")
        self.assertNotIn("not in the SQLite store", result.stderr)

    def test_announced_once_per_process(self):
        self.park_a_run()
        result = self.nodus("workflow", "runs", backend="sqlite")
        self.assertEqual(result.stderr.count("not in the SQLite store"), 1)


class RecordedForReadinessTests(_Project):
    """It joins the staged-flip report, like every other flip (R2)."""

    def test_it_is_recorded_when_a_report_is_configured(self):
        self.park_a_run()
        report = os.path.join(self.dir, "staged.jsonl")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO / "src")
        env["NODUS_WORKFLOW_STORE_BACKEND"] = "sqlite"
        env["NODUS_STAGED_FLIP_REPORT"] = report
        subprocess.run(
            [PYTHON, "-m", "nodus", "workflow", "runs"],
            cwd=self.dir, capture_output=True, text=True, env=env, timeout=120,
        )
        sys.path.insert(0, str(REPO / "src"))
        from nodus.support.staging import read_staged_flip_report

        flips = {r["flip"] for r in read_staged_flip_report(report)}
        self.assertIn("default-store-sqlite", flips)


if __name__ == "__main__":
    unittest.main()
