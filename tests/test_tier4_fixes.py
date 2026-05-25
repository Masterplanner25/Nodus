"""Tests for v2.1 Tier-4 fixes: docstring encoding, trace whitespace, init message, REPL docs, stdlib stack traces."""

import unittest

from nodus.tooling.runner import run_source


def _run(code, **kw):
    result, _ = run_source(code, max_steps=50_000, timeout_ms=5_000, **kw)
    return result


class StdlibStackTraceTests(unittest.TestCase):
    """BUG-015: errors from stdlib functions report the user call site, not the stdlib file."""

    def test_stdlib_type_error_points_to_user_call(self):
        # math.sqrt("bad") throws a type error; the error path must not point into stdlib
        src = 'import "std:math" as m\nm.sqrt("bad")'
        r = _run(src)
        self.assertFalse(r["ok"])
        err = r.get("error", {})
        path = err.get("path") or ""
        self.assertNotIn("stdlib", path.replace("\\", "/"))

    def test_stdlib_error_line_is_user_call_line(self):
        # math.sqrt("bad") is on line 2; error must report line 2, not inside math.nd
        src = 'import "std:math" as m\nm.sqrt("bad")'
        r = _run(src)
        err = r.get("error", {})
        # Line must be 2 (user call) not something inside math.nd
        self.assertEqual(err.get("line"), 2)

    def test_stdlib_strings_error_points_to_user_call(self):
        src = 'import "std:strings" as s\nlet x = 1\ns.upper(x)'
        r = _run(src)
        self.assertFalse(r["ok"])
        err = r.get("error", {})
        path = err.get("path") or ""
        self.assertNotIn("stdlib", path.replace("\\", "/"))

    def test_non_stdlib_error_location_unchanged(self):
        # Errors in user code should still report the correct user line
        src = 'let x = 1\nlet y = x + "bad"'
        r = _run(src)
        self.assertFalse(r["ok"])
        err = r.get("error", {})
        self.assertEqual(err.get("line"), 2)


if __name__ == "__main__":
    unittest.main()
