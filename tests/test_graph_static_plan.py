"""`nodus graph` no longer executes the file it is asked to inspect (#400).

The inspection commands are the ones you reach for when you do *not* want to
run something -- a file from an untrusted source, or one an LLM just
generated, inspected to see its shape before deciding to run it. `graph` (and
`graph show`, which inherited the path in 5.2.0) executed the whole module to
obtain `vm.last_graph_plan`, side effects included -- and `graph show` did it
while exiting 0 and printing a diagram.

Now the plan is built by loading **only the flow declarations** (imports and
every other top-level statement are dropped before compilation), then planned
through the same `plan_workflow` / `plan_goal` machinery the executing path
uses -- one plan source, with the execution removed. The old behaviour is
`--execute`, needed only for graphs constructed at runtime.

This also fixes #558's natural spelling: a `plan_workflow(...)` call inside
`main()` no longer matters, because the declaration alone is enough.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.cli.cli import main  # noqa: E402

PROBE_SOURCE = """
import "std:fs" as fs
fs.write("probe.txt", "the file executed")
workflow w { step a { return 1i } step b after a { return 2i } }
let r = run_workflow(w)
"""


class _GraphHarness(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._td.name)
        self.addCleanup(self._restore)

    def _restore(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def _write(self, source: str) -> str:
        path = os.path.join(self._td.name, "wf.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        return path

    def _graph(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["nodus", *argv])
        return code, out.getvalue(), err.getvalue()


# closes: #400
class GraphDoesNotExecuteItsTargetTests(_GraphHarness):
    def test_graph_plans_without_running_the_file(self):
        path = self._write(PROBE_SOURCE)
        code, out, _err = self._graph("graph", path, "--allow-paths", ".")
        self.assertEqual(code, 0)
        payload = json.loads(out.strip())
        self.assertEqual(payload["nodes"], ["a", "b"])
        self.assertEqual(payload["edges"], [["a", "b"]])
        self.assertFalse(
            os.path.exists("probe.txt"),
            "inspecting the file executed it: probe.txt was written",
        )

    def test_graph_show_renders_without_running_the_file(self):
        path = self._write(PROBE_SOURCE)
        code, out, _err = self._graph("graph", "show", path)
        self.assertEqual(code, 0)
        self.assertIn("flowchart TD", out)
        self.assertIn('n0["a"]', out)
        self.assertFalse(os.path.exists("probe.txt"))

    def test_execute_flag_restores_the_old_behaviour(self):
        """The escape hatch is real: --execute runs the file (and, for this
        file, reproduces the old 'No graph plan produced' failure, because it
        calls run_workflow rather than plan_workflow)."""
        path = self._write(PROBE_SOURCE)
        code, _out, err = self._graph("graph", path, "--execute", "--allow-paths", ".")
        self.assertNotEqual(code, 0)
        self.assertIn("No graph plan produced", err)
        self.assertTrue(os.path.exists("probe.txt"))

    def test_runtime_constructed_graph_refuses_and_names_execute(self):
        path = self._write(
            "let t = task(fn() { return 1i }, nil)\nlet p = plan_graph([t])\n"
        )
        code, _out, err = self._graph("graph", path)
        self.assertNotEqual(code, 0)
        self.assertIn("No workflow or goal declaration found", err)
        self.assertIn("--execute", err)

    # closes: #558
    def test_plan_inside_main_is_enough_now(self):
        path = self._write(
            "workflow deploy {\n"
            '    step build { return "ok" }\n'
            '    step notify after build { return "alerted" }\n'
            "}\n"
            "fn main() { let p = plan_workflow(deploy) }\n"
        )
        code, out, _err = self._graph("graph", "show", path)
        self.assertEqual(code, 0)
        self.assertIn('n0["build"]', out)
        self.assertIn("n0 --> n1", out)

    def test_goal_pursuit_file_plans_its_workflow(self):
        path = self._write(
            "workflow tune {\n"
            '    step adjust { checkpoint "good_enough"; return 1i }\n'
            "}\n"
            "goal reach_quality over tune {\n"
            '    until reached("good_enough")\n'
            "    budget { max_iterations: 5, deadline_ms: 30000 }\n"
            "}\n"
        )
        code, out, _err = self._graph("graph", path)
        self.assertEqual(code, 0)
        payload = json.loads(out.strip())
        self.assertEqual(payload["nodes"], ["adjust"])

    def test_syntax_error_still_fails(self):
        path = self._write("workflow w { step a { return 1i } }\nlet x = (\n")
        code, _out, err = self._graph("graph", path)
        self.assertNotEqual(code, 0)
        self.assertNotEqual(err.strip(), "")

    def test_static_and_executed_plans_agree(self):
        """The drift guard for the shared-plan-source requirement: for a file
        whose plan the executing path can produce, both paths must produce the
        same graph."""
        source = (
            "workflow w {\n"
            "    step a { return 1i }\n"
            "    step b after a { return 2i }\n"
            '    step c after a when reached("x") { checkpoint "x"; return 3i }\n'
            "}\n"
            "let p = plan_workflow(w)\n"
        )
        path = self._write(source)
        code_s, out_s, _ = self._graph("graph", path)
        code_x, out_x, _ = self._graph("graph", path, "--execute")
        self.assertEqual(code_s, 0)
        self.assertEqual(code_x, 0)
        static_plan = json.loads(out_s.strip())
        executed_plan = json.loads(out_x.strip())
        for key in ("nodes", "edges", "conditional_edges", "edge_conditions", "levels"):
            self.assertEqual(static_plan[key], executed_plan[key], key)


if __name__ == "__main__":
    unittest.main()
