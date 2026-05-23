"""Tests for Task 6.2: --trace flag outputs opcode trace to stderr."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr

from nodus.cli.cli import main


class RunTraceTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def _script(self, src: str) -> str:
        path = os.path.join(self.td, "script.nd")
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        return path

    def test_trace_outputs_to_stderr(self):
        script = self._script("let x = 1\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            exit_code = main(["nodus", "run", "--trace", script])
        self.assertEqual(exit_code, 0)
        stderr = buf.getvalue()
        self.assertIn("[trace]", stderr)

    def test_trace_without_flag_produces_no_trace(self):
        script = self._script("let x = 1\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            exit_code = main(["nodus", "run", script])
        self.assertEqual(exit_code, 0)
        self.assertNotIn("[trace]", buf.getvalue())

    def test_trace_shows_call_context(self):
        script = self._script("fn greet() { return 1 }\ngreet()\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            main(["nodus", "run", "--trace", script])
        stderr = buf.getvalue()
        self.assertIn("[trace]", stderr)
        self.assertTrue(any("fn=" in line for line in stderr.splitlines()), stderr)

    def test_trace_shows_line_numbers(self):
        script = self._script("let x = 42\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            main(["nodus", "run", "--trace", script])
        stderr = buf.getvalue()
        self.assertTrue(any("line " in line for line in stderr.splitlines()), stderr)

    def test_trace_format_padded_opcode(self):
        script = self._script("let x = 1\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            main(["nodus", "run", "--trace", script])
        lines = [line for line in buf.getvalue().splitlines() if line.startswith("[trace]")]
        self.assertTrue(len(lines) > 0)
        for line in lines:
            parts = line.split()
            self.assertEqual(parts[0], "[trace]")
            self.assertGreaterEqual(len(parts), 3)

    def test_trace_no_loc_omits_line(self):
        script = self._script("let x = 1\n")
        buf = io.StringIO()
        with redirect_stderr(buf):
            main(["nodus", "run", "--trace", "--trace-no-loc", script])
        stderr = buf.getvalue()
        self.assertIn("[trace]", stderr)
        self.assertNotIn("line ", stderr)
