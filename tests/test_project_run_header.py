"""Tests for execution transparency: project-run stderr header (Task 1.3)."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr

from nodus.cli.cli import main


class ProjectRunHeaderTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def _make_project(self, entry_src: str = 'print("ok")\n') -> None:
        manifest = (
            "[package]\n"
            'name = "test"\n'
            'version = "0.1.0"\n'
            "\n"
            "[dependencies]\n"
        )
        os.makedirs(os.path.join(self.td, "src"), exist_ok=True)
        with open(os.path.join(self.td, "nodus.toml"), "w", encoding="utf-8") as f:
            f.write(manifest)
        with open(os.path.join(self.td, "src", "main.nd"), "w", encoding="utf-8") as f:
            f.write(entry_src)

    def test_project_run_prints_header_to_stderr(self):
        self._make_project()
        buf = io.StringIO()
        orig = os.getcwd()
        try:
            os.chdir(self.td)
            with redirect_stderr(buf):
                exit_code = main(["nodus", "run"])
        finally:
            os.chdir(orig)
        self.assertEqual(exit_code, 0)
        stderr = buf.getvalue()
        self.assertIn("Running project from:", stderr)
        self.assertIn("Entry:", stderr)
        # Entry should be a relative path pointing to src/main.nd
        self.assertIn("main.nd", stderr)

    def test_project_run_from_dir_arg_prints_header(self):
        self._make_project()
        buf = io.StringIO()
        with redirect_stderr(buf):
            exit_code = main(["nodus", "run", self.td])
        self.assertEqual(exit_code, 0)
        stderr = buf.getvalue()
        self.assertIn("Running project from:", stderr)
        self.assertIn("Entry:", stderr)

    def test_single_file_run_does_not_print_header(self):
        script = os.path.join(self.td, "main.nd")
        with open(script, "w", encoding="utf-8") as f:
            f.write('print("ok")\n')
        buf = io.StringIO()
        with redirect_stderr(buf):
            exit_code = main(["nodus", "run", script])
        self.assertEqual(exit_code, 0)
        stderr = buf.getvalue()
        self.assertNotIn("Running project from:", stderr)
        self.assertNotIn("Entry:", stderr)
