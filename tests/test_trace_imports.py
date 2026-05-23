"""Tests for Task 3.3: --trace-imports flag."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr

from nodus.cli.cli import main


class TraceImportsTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def _make_project_with_import(self) -> str:
        lib_nd = os.path.join(self.td, "lib.nd")
        main_nd = os.path.join(self.td, "main.nd")
        with open(lib_nd, "w", encoding="utf-8") as f:
            f.write("export let v = 7\n")
        with open(main_nd, "w", encoding="utf-8") as f:
            f.write('import { v } from "./lib.nd"\nprint(v)\n')
        return main_nd

    def test_trace_imports_prints_resolved_line_to_stderr(self):
        script = self._make_project_with_import()
        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            exit_code = main(["nodus", "run", "--trace-imports", script])
        self.assertEqual(exit_code, 0)
        stderr = stderr_buf.getvalue()
        self.assertIn("[import] Resolved", stderr)
        self.assertIn("lib.nd", stderr)

    def test_trace_imports_without_flag_prints_nothing(self):
        script = self._make_project_with_import()
        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            exit_code = main(["nodus", "run", script])
        self.assertEqual(exit_code, 0)
        self.assertNotIn("[import]", stderr_buf.getvalue())

    def test_trace_imports_bare_import_shows_resolved_path(self):
        lib_nd = os.path.join(self.td, "lib.nd")
        main_nd = os.path.join(self.td, "main.nd")
        with open(lib_nd, "w", encoding="utf-8") as f:
            f.write("export let v = 5\n")
        with open(main_nd, "w", encoding="utf-8") as f:
            f.write('import { v } from "lib"\nprint(v)\n')
        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            exit_code = main(["nodus", "run", "--trace-imports", main_nd])
        self.assertEqual(exit_code, 0)
        stderr = stderr_buf.getvalue()
        self.assertIn("[import] Resolved", stderr)
        self.assertIn('"lib"', stderr)

    def test_trace_imports_failed_import_prints_failure_line(self):
        main_nd = os.path.join(self.td, "main.nd")
        with open(main_nd, "w", encoding="utf-8") as f:
            f.write('import { x } from "nonexistent"\n')
        stderr_buf = io.StringIO()
        with redirect_stderr(stderr_buf):
            exit_code = main(["nodus", "run", "--trace-imports", main_nd])
        self.assertNotEqual(exit_code, 0)
        stderr = stderr_buf.getvalue()
        self.assertIn("[import] Failed", stderr)
        self.assertIn('"nonexistent"', stderr)
