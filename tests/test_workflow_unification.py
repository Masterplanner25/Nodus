"""Tests for Task 6.3: workflow and graph command unification."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from nodus.cli.cli import main


class WorkflowRunSubcommandTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def _script(self, src: str, name: str = "wf.nd") -> str:
        path = os.path.join(self.td, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        return path

    def test_workflow_run_executes_workflow(self):
        script = self._script("workflow mywf {\n    step s1 { return 42 }\n}\nlet _ = run_workflow(mywf)\n")
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            exit_code = main(["nodus", "workflow", "run", script])
        self.assertEqual(exit_code, 0, err.getvalue())

    def test_workflow_run_missing_file_errors(self):
        err = io.StringIO()
        with redirect_stderr(err):
            exit_code = main(["nodus", "workflow", "run", "/no/such/file.nd"])
        self.assertNotEqual(exit_code, 0)

    def test_workflow_run_no_file_shows_usage(self):
        err = io.StringIO()
        with redirect_stderr(err):
            exit_code = main(["nodus", "workflow", "run"])
        self.assertNotEqual(exit_code, 0)
        self.assertIn("Usage", err.getvalue())

    def test_workflow_help_shows_run_subcommand(self):
        out = io.StringIO()
        with redirect_stdout(out):
            exit_code = main(["nodus", "workflow", "--help"])
        self.assertEqual(exit_code, 0)
        self.assertIn("run", out.getvalue())

    def test_workflow_no_args_shows_usage(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["nodus", "workflow"])
        output = out.getvalue()
        self.assertIn("run", output)


class GraphRunSubcommandTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def _script(self, src: str) -> str:
        path = os.path.join(self.td, "tasks.nd")
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        return path

    def _graph_script(self) -> str:
        return self._script("let t = task(fn() { return 1 }, [])\nplan_graph(graph([t]))\n")

    def test_graph_run_subcommand_accepted(self):
        script = self._graph_script()
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            exit_code = main(["nodus", "graph", "run", script])
        self.assertEqual(exit_code, 0, err.getvalue())

    def test_graph_run_missing_file_errors(self):
        err = io.StringIO()
        with redirect_stderr(err):
            exit_code = main(["nodus", "graph", "run", "/no/such/file.nd"])
        self.assertNotEqual(exit_code, 0)

    def test_graph_run_no_file_shows_usage(self):
        err = io.StringIO()
        with redirect_stderr(err):
            exit_code = main(["nodus", "graph", "run"])
        self.assertNotEqual(exit_code, 0)
        self.assertIn("Usage", err.getvalue())

    def test_graph_help_shows_run_subcommand(self):
        out = io.StringIO()
        with redirect_stdout(out):
            exit_code = main(["nodus", "graph", "--help"])
        self.assertEqual(exit_code, 0)
        self.assertIn("run", out.getvalue())

    def test_graph_direct_file_still_works(self):
        script = self._graph_script()
        out = io.StringIO()
        with redirect_stdout(out):
            exit_code = main(["nodus", "graph", script])
        self.assertEqual(exit_code, 0)

    def test_global_help_shows_graph_run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["nodus", "--help"])
        self.assertIn("graph run", out.getvalue())

    def test_global_help_shows_workflow_run(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["nodus", "--help"])
        # Global help groups workflow commands under "workflow <cmd>"
        self.assertIn("workflow", out.getvalue())
