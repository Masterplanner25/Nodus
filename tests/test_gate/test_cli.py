"""Tests for nodus_gate CLI."""

import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language")  # noqa: E402
sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

from tools.nodus_gate.cli import _parse_args, _load_allowlist, main  # noqa: E402


class ParseArgsTests(unittest.TestCase):

    def test_static_flag(self):
        args = _parse_args(["--static"])
        self.assertTrue(args["--static"])
        self.assertFalse(args["--runtime"])

    def test_all_flag(self):
        args = _parse_args(["--all"])
        self.assertTrue(args["--all"])

    def test_format_with_value(self):
        args = _parse_args(["--format", "json"])
        self.assertEqual(args["--format"], "json")

    def test_format_equals_syntax(self):
        args = _parse_args(["--format=json"])
        self.assertEqual(args["--format"], "json")

    def test_defaults(self):
        args = _parse_args([])
        self.assertFalse(args["--static"])
        self.assertFalse(args["--all"])
        self.assertEqual(args["--format"], "auto")
        self.assertEqual(args["--section"], "Unreleased")

    def test_verbose_quiet_flags(self):
        args = _parse_args(["--verbose", "--quiet"])
        self.assertTrue(args["--verbose"])
        self.assertTrue(args["--quiet"])


class LoadAllowlistTests(unittest.TestCase):

    def test_missing_file_returns_empty(self):
        result = _load_allowlist("/nonexistent/.nodusgate-allow")
        self.assertEqual(result, set())

    def test_loads_entries(self):
        import tempfile
        import os
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".allow", delete=False)
        f.write("# comment\nsymbol:foo\nblock:test.md:42\n")
        f.close()
        try:
            result = _load_allowlist(f.name)
            self.assertIn("symbol:foo", result)
            self.assertIn("block:test.md:42", result)
            self.assertNotIn("# comment", result)
        finally:
            os.unlink(f.name)


class MainCliTests(unittest.TestCase):

    def test_no_flags_returns_exit_2(self):
        rc = main([])
        self.assertEqual(rc, 2)

    def test_json_output_for_static(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["--static", "--format", "json",
                  "--allowlist", "/nonexistent/.nodusgate-allow"])
        output = buf.getvalue()
        self.assertIn("{", output)
        import json
        data = json.loads(output)
        self.assertIn("phases", data)
        self.assertIn("static", data["phases"])

    def test_quiet_flag_accepted(self):
        rc = main(["--static", "--quiet",
                   "--allowlist", "/nonexistent/.nodusgate-allow"])
        self.assertIn(rc, (0, 1))  # passes or fails, but doesn't crash


if __name__ == "__main__":
    unittest.main()
