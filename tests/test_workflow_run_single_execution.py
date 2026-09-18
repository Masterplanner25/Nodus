"""`workflow run` / `goal run` do not run a flow the program already ran (#858).

`run_workflow_code` executes the submitted program and then runs the workflow
it defines. A program that also calls `run_workflow(w)` itself -- the form the
guide teaches, and what `examples/webhook_bridge` submitted -- therefore ran
every step **twice**, and the response's `graph_id` named the second run. Two
Slack posts per webhook, in the one production-shaped `nodus serve` example.

The VM now records the last flow the program itself ran (`last_run_result`,
set in one place for `run_workflow`, `run_goal` and `goal … over …`), and both
entry points report that run instead of starting another. A program that only
*defines* a flow is run for it exactly as before.

Both entry points and both flow kinds, because the double lived in two
functions and the fix is a shared helper; a case per function is what keeps a
third entry point from reintroducing it.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "src"
NODUS_PY = REPO / "nodus.py"
sys.path.insert(0, str(SRC))

from nodus.services.server import RuntimeService  # noqa: E402

SELF_RUNNING_WORKFLOW = (
    'workflow w { step a { print("step a ran"); return 1i } }\n'
    'let r = run_workflow(w)\n'
    'print("program saw " + r["graph_id"])\n'
)
DEFINITION_ONLY_WORKFLOW = 'workflow w { step a { print("step a ran"); return 1i } }\n'
SELF_RUNNING_GOAL = (
    'goal g { step a { print("goal step ran"); return 1i } }\n'
    'let r = run_goal(g)\n'
    'print("program saw " + r["graph_id"])\n'
)
SELF_RUNNING_PURSUIT = (
    'workflow tune { step a { print("pursuit step ran"); checkpoint "done"; return 1i } }\n'
    'goal reach over tune { until reached("done") budget { max_iterations: 3i } }\n'
    'let r = run_goal(reach)\n'
    'print("program saw " + r["graph_id"])\n'
)


class _Case(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory(prefix="nodus858-")
        os.chdir(self._tmp.name)
        self.svc = RuntimeService()

    def tearDown(self):
        self.svc.close()
        os.chdir(self._cwd)
        self._tmp.cleanup()


# closes: #858
class ServiceRunsTheFlowOnceTests(_Case):

    def test_a_self_running_program_runs_its_workflow_once(self):
        r = self.svc.workflow_run({"code": SELF_RUNNING_WORKFLOW, "filename": "w.nd"})
        self.assertTrue(r["ok"], r.get("error"))
        self.assertEqual(r["stdout"].count("step a ran"), 1, r["stdout"])
        # ... and the response names the run the program saw, not a second one.
        seen = r["stdout"].split("program saw ")[1].strip()
        self.assertEqual(r["graph_id"], seen)
        self.assertEqual(r["result"]["graph_id"], seen)
        self.assertEqual(r["result"]["steps"], {"a": 1.0})

    def test_a_definition_only_program_is_still_run_for(self):
        """The other half: the endpoint's whole reason to exist keeps working."""
        r = self.svc.workflow_run({"code": DEFINITION_ONLY_WORKFLOW, "filename": "w.nd"})
        self.assertTrue(r["ok"], r.get("error"))
        self.assertEqual(r["stdout"].count("step a ran"), 1, r["stdout"])
        self.assertEqual(r["result"]["steps"], {"a": 1.0})
        self.assertTrue(r["graph_id"])

    def test_a_self_running_goal_runs_once(self):
        r = self.svc.goal_run({"code": SELF_RUNNING_GOAL, "filename": "g.nd"})
        self.assertTrue(r["ok"], r.get("error"))
        self.assertEqual(r["stdout"].count("goal step ran"), 1, r["stdout"])
        self.assertEqual(r["graph_id"], r["stdout"].split("program saw ")[1].strip())

    def test_a_self_running_goal_pursuit_runs_once(self):
        """`goal … over …` is the third way a program starts a flow."""
        r = self.svc.goal_run({"code": SELF_RUNNING_PURSUIT, "filename": "p.nd"})
        self.assertTrue(r["ok"], r.get("error"))
        self.assertEqual(r["stdout"].count("pursuit step ran"), 1, r["stdout"])
        self.assertEqual(r["graph_id"], r["stdout"].split("program saw ")[1].strip())

    def test_a_fresh_request_does_not_inherit_an_earlier_run(self):
        """The slot is per run: a definition-only program after a self-running
        one must be run for, not handed the previous request's result."""
        first = self.svc.workflow_run({"code": SELF_RUNNING_WORKFLOW, "filename": "w.nd"})
        second = self.svc.workflow_run({"code": DEFINITION_ONLY_WORKFLOW, "filename": "w.nd"})
        self.assertNotEqual(first["graph_id"], second["graph_id"])
        self.assertEqual(second["stdout"].count("step a ran"), 1)


# closes: #858
class CliRunsTheFlowOnceTests(unittest.TestCase):
    """`nodus workflow run` takes the same path and had the same double."""

    def test_workflow_run_on_a_self_running_file(self):
        with tempfile.TemporaryDirectory(prefix="nodus858-") as tmp:
            path = pathlib.Path(tmp) / "w.nd"
            path.write_text(SELF_RUNNING_WORKFLOW, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(NODUS_PY), "workflow", "run", str(path)],
                capture_output=True, text=True, timeout=120, cwd=tmp,
                env={"PYTHONPATH": str(SRC), "SYSTEMROOT": "C:\\Windows", "PATH": ""},
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.count("step a ran"), 1, proc.stdout)
        seen = proc.stdout.split("program saw ")[1].splitlines()[0].strip()
        payload = json.loads(proc.stdout[proc.stdout.index("{"):])
        self.assertEqual(payload.get("graph_id") or payload["result"]["graph_id"], seen)


if __name__ == "__main__":
    unittest.main()
