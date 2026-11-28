"""Switching to SQLite must not silently hide the runs you already have (#174).

**This is the harm #174 is about.** Measured on 5.11.0: park a run at
`workflow_wait` under the local store, set `NODUS_WORKFLOW_STORE_BACKEND=sqlite`,
and `nodus workflow runs` reported **0 runs and exited 0**. The parked run still
existed. Nothing said so.

Since 6.0.0 (#797) SQLite is the default, and the case splits by who chose it.
Nothing chosen: the default store refuses (`StrandedRunsError`, exit 1), which
`test_default_store_backend.py` covers. SQLite chosen explicitly: the host
chose the switch, so it is warned, naming the runs, and not stopped. That half
is here.

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
        """Leave one `waiting` run in the JSON store, as a 5.x project has."""
        self.nodus("workflow", "run", "approval.nd", "--workflow", "approval", backend="local")
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

    def test_it_does_not_fail_the_command(self):
        """Chosen explicitly, so a warning. Nothing chosen is the refusal."""
        self.park_a_run()
        result = self.nodus("workflow", "runs", backend="sqlite")
        self.assertEqual(result.returncode, 0)
        self.assertIn("warning: ", result.stderr)
        self.assertNotIn("6.0.0", result.stderr)

    def test_with_nothing_chosen_it_is_refused(self):
        run_id = self.park_a_run()
        result = self.nodus("workflow", "runs")
        self.assertEqual(result.returncode, 1)
        self.assertIn(run_id, result.stderr)


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


if __name__ == "__main__":
    unittest.main()
