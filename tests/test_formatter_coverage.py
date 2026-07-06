"""Tests for formatter coverage of previously-missing AST node handlers."""
import unittest

from nodus.tooling.formatter import format_source


class FormatterCoverageTests(unittest.TestCase):
    def test_yield_no_expr(self):
        src = "fn f() {\n    yield\n}\n"
        self.assertEqual(format_source(src), src)

    def test_yield_with_expr(self):
        src = "fn f() {\n    yield 42\n}\n"
        self.assertEqual(format_source(src), src)

    def test_throw(self):
        src = 'fn f() {\n    throw "error"\n}\n'
        self.assertEqual(format_source(src), src)

    def test_try_catch(self):
        src = 'fn f() {\n    try {\n        throw "oops"\n    } catch err {\n        print(err)\n    }\n}\n'
        self.assertEqual(format_source(src), src)

    def test_destructure_list(self):
        src = "let [a, b] = xs\n"
        self.assertEqual(format_source(src), src)

    def test_destructure_record(self):
        src = "let {x: a, y: b} = pt\n"
        self.assertEqual(format_source(src), src)

    def test_destructure_nested(self):
        src = "let [a, [b, c]] = xs\n"
        self.assertEqual(format_source(src), src)


class FormatterStringEscapeTests(unittest.TestCase):
    """Regression tests for #310: fmt must re-escape the full escape set so
    string literals round-trip idempotently instead of emitting raw control
    bytes (which then fail re-parsing)."""

    def _assert_idempotent(self, src: str) -> None:
        once = format_source(src)
        self.assertEqual(once, src)
        # Idempotent: formatting the output again is a no-op.
        self.assertEqual(format_source(once), once)

    def test_carriage_return_escape(self):
        self._assert_idempotent('let cr = "\\r"\n')

    def test_null_escape(self):
        self._assert_idempotent('let z = "\\0"\n')

    def test_tab_and_newline_still_escape(self):
        self._assert_idempotent('let t = "\\t"\n')
        self._assert_idempotent('let n = "\\n"\n')

    def test_backslash_and_quote(self):
        self._assert_idempotent('let b = "a\\\\b"\n')
        self._assert_idempotent('let q = "say \\"hi\\""\n')

    def test_low_control_char_hex_fallback(self):
        # \x01 has no named escape; fmt must emit \x01, not a raw byte.
        self._assert_idempotent('let c = "\\x01"\n')

    def test_del_char_hex_fallback(self):
        self._assert_idempotent('let d = "\\x7F"\n')

    def test_mixed_escapes_in_one_string(self):
        self._assert_idempotent('let mix = "a\\rb\\tc\\0d"\n')

    def test_printable_unicode_passes_through(self):
        self._assert_idempotent('let g = "αβγ"\n')

    def test_escape_inside_interpolation(self):
        self._assert_idempotent('let s = "row1\\rrow2 = \\(1 + 1)"\n')

    def test_no_raw_control_bytes_emitted(self):
        # The core corruption: output must contain the escape, never the byte.
        out = format_source('let cr = "\\r"\n')
        self.assertNotIn("\r", out)
        self.assertIn("\\r", out)


if __name__ == "__main__":
    unittest.main()
