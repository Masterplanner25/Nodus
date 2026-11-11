"""#920: a resume or replay that fails exits non-zero.

`nodus workflow resume`, `workflow replay`, `goal-resume` and the legacy
`workflow-resume` get a two-level result. The outer level says the command
executed; the inner one is the workflow runner's answer, and a run that does not
exist, cannot be rebuilt or is not a workflow comes back as an inner
`{"ok": false, ...}`. The CLI exited by the outer level, so it printed the
failure and returned 0.

Each door is driven through a real subprocess, since an exit code is a process's
answer. The success half -- a resume that works still exits 0 -- is pinned by
`test_resume_rebuild.py::ResumeAfterReadingTheResultTests`.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_DOORS = {
    "workflow resume": ["workflow", "resume", "g_nope"],
    "workflow replay": ["workflow", "replay", "g_nope"],
    "workflow-resume (legacy)": ["workflow-resume", "g_nope"],
    "goal-resume": ["goal-resume", "g_nope"],
}


class AFailedResumeExitsNonZeroTests(unittest.TestCase):

    # closes: #920
    def test_every_door_exits_1_and_still_prints_the_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
            for name, argv in _DOORS.items():
                with self.subTest(name):
                    proc = subprocess.run(
                        [sys.executable, str(REPO / "nodus.py"), *argv],
                        cwd=tmp, env=env, capture_output=True, text=True, timeout=120)
                    self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
                    answer = json.loads(proc.stdout)
                    self.assertIs(False, answer["ok"])
                    self.assertIn("not found", answer["error"])


if __name__ == "__main__":
    unittest.main()
