"""Tests for nodus status command (Task 2.3)."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from nodus.cli.cli import main


class StatusCommandTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def _make_project(self) -> None:
        manifest = (
            "[package]\n"
            'name = "myproject"\n'
            'version = "0.2.0"\n'
            "\n"
            "[dependencies]\n"
        )
        os.makedirs(os.path.join(self.td, "src"), exist_ok=True)
        with open(os.path.join(self.td, "nodus.toml"), "w", encoding="utf-8") as f:
            f.write(manifest)
        with open(os.path.join(self.td, "src", "main.nd"), "w", encoding="utf-8") as f:
            f.write('print("ok")\n')

    def test_status_from_project_dir_shows_all_fields(self):
        self._make_project()
        buf = io.StringIO()
        orig = os.getcwd()
        try:
            os.chdir(self.td)
            with redirect_stdout(buf):
                exit_code = main(["nodus", "status"])
        finally:
            os.chdir(orig)
        self.assertEqual(exit_code, 0)
        output = buf.getvalue()
        self.assertIn("Project root:", output)
        self.assertIn("Entry:", output)
        self.assertIn("Working dir:", output)
        self.assertIn("main.nd", output)
        self.assertIn(os.path.abspath(self.td), output)

    def test_status_from_non_project_dir_shows_no_project(self):
        empty_dir = os.path.join(self.td, "empty")
        os.makedirs(empty_dir)
        buf = io.StringIO()
        orig = os.getcwd()
        try:
            os.chdir(empty_dir)
            with redirect_stdout(buf):
                exit_code = main(["nodus", "status"])
        finally:
            os.chdir(orig)
        self.assertEqual(exit_code, 0)
        output = buf.getvalue()
        self.assertIn("No project found", output)
        self.assertIn("Working dir:", output)

    def test_status_appears_in_help(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = main(["nodus", "--help"])
        self.assertEqual(exit_code, 0)
        self.assertIn("status", buf.getvalue())
