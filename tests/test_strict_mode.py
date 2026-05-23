"""Tests for nodus run --strict mode (Task 2.2)."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr

from nodus.cli.cli import main


class StrictModeTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def _make_project(self) -> str:
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
        entry = os.path.join(self.td, "src", "main.nd")
        with open(entry, "w", encoding="utf-8") as f:
            f.write('print("ok")\n')
        return entry

    def _make_script(self) -> str:
        script = os.path.join(self.td, "script.nd")
        with open(script, "w", encoding="utf-8") as f:
            f.write('print("strict")\n')
        return script

    def test_strict_no_file_prints_error_and_exits_nonzero(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            exit_code = main(["nodus", "run", "--strict"])
        self.assertNotEqual(exit_code, 0)
        stderr = buf.getvalue()
        self.assertIn("--strict mode requires an explicit file path", stderr)
        self.assertIn("Usage: nodus run --strict main.nd", stderr)

    def test_strict_explicit_file_runs_without_project_header(self):
        # Even inside a project directory, --strict with a file should not
        # print the "Running project from:" header.
        self._make_project()
        script = self._make_script()
        buf = io.StringIO()
        orig = os.getcwd()
        try:
            os.chdir(self.td)
            with redirect_stderr(buf):
                exit_code = main(["nodus", "run", "--strict", script])
        finally:
            os.chdir(orig)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("Running project from:", buf.getvalue())

    def test_strict_with_directory_arg_prints_error_and_exits_nonzero(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            exit_code = main(["nodus", "run", "--strict", self.td])
        self.assertNotEqual(exit_code, 0)
        stderr = buf.getvalue()
        self.assertIn("--strict mode requires an explicit file path", stderr)
