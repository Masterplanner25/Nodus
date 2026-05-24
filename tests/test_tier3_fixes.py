"""Tests for v2.1 Tier-3 fixes: has_key, throw kind, unclosed string, while hint, em-dash."""

import unittest

from nodus.tooling.runner import run_source


def _run(code, **kw):
    result, _ = run_source(code, max_steps=50_000, timeout_ms=5_000, **kw)
    return result


class HasKeyBuiltinTests(unittest.TestCase):
    """BUG-020: has_key(map, key) builtin — no import required."""

    def test_has_key_present(self):
        r = _run('let m = json_parse("{\\"a\\": 1}")\nprint(has_key(m, "a"))')
        self.assertTrue(r["ok"], r)
        self.assertIn("true", r["stdout"])

    def test_has_key_absent(self):
        r = _run('let m = json_parse("{\\"a\\": 1}")\nprint(has_key(m, "b"))')
        self.assertTrue(r["ok"], r)
        self.assertIn("false", r["stdout"])

    def test_has_key_type_error_on_non_map(self):
        r = _run('has_key([1, 2], "x")')
        self.assertFalse(r["ok"])
        self.assertEqual(r.get("error", {}).get("kind"), "type")

    def test_has_key_no_import_needed(self):
        r = _run('print(has_key({"x": 1}, "x"))')
        self.assertTrue(r["ok"], r)
        self.assertIn("true", r["stdout"])


class ThrowKindTests(unittest.TestCase):
    """BUG-027: throw string/primitive gives err.kind = 'thrown', not 'runtime'."""

    def test_throw_string_kind_is_thrown(self):
        r = _run('try { throw "oops" } catch e { print(e.kind) }')
        self.assertTrue(r["ok"], r)
        self.assertIn("thrown", r["stdout"])

    def test_throw_number_kind_is_thrown(self):
        r = _run('try { throw 42 } catch e { print(e.kind) }')
        self.assertTrue(r["ok"], r)
        self.assertIn("thrown", r["stdout"])

    def test_throw_string_message_preserved(self):
        r = _run('try { throw "bad input" } catch e { print(e.message) }')
        self.assertTrue(r["ok"], r)
        self.assertIn("bad input", r["stdout"])

    def test_throw_record_kind_still_thrown(self):
        r = _run('try { throw record { code: 404 } } catch e { print(e.kind) }')
        self.assertTrue(r["ok"], r)
        self.assertIn("thrown", r["stdout"])


class UnclosedStringTests(unittest.TestCase):
    """BUG-008: unclosed string literal gives 'Unterminated string literal' not 'Unexpected character'."""

    def test_unclosed_string_error_message(self):
        r = _run('let x = "hello')
        self.assertFalse(r["ok"])
        msg = r.get("error", {}).get("message", "")
        self.assertIn("Unterminated string literal", msg)

    def test_unclosed_string_has_location(self):
        r = _run('let x = "hello')
        err = r.get("error", {})
        self.assertIsNotNone(err.get("line"))


class WhileParenHintTests(unittest.TestCase):
    """BUG-026: 'while true' (no parens) gives a helpful hint about parentheses."""

    def test_while_without_parens_error_mentions_parens(self):
        r = _run('while true { }')
        self.assertFalse(r["ok"])
        msg = r.get("error", {}).get("message", "")
        self.assertIn("parentheses", msg)

    def test_while_with_parens_still_works(self):
        r = _run('let i = 0\nwhile (i < 3) { i = i + 1 }\nprint(i)')
        self.assertTrue(r["ok"], r)
        self.assertIn("3", r["stdout"])


class EmDashTests(unittest.TestCase):
    """BUG-009: parser error messages use ASCII hyphens, not em-dashes."""

    def test_incomplete_expression_uses_hyphen(self):
        r = _run('let x = 1 +')
        self.assertFalse(r["ok"])
        msg = r.get("error", {}).get("message", "")
        self.assertNotIn("—", msg)
        self.assertIn("incomplete", msg)

    def test_unexpected_brace_uses_hyphen(self):
        r = _run('let x = }')
        self.assertFalse(r["ok"])
        msg = r.get("error", {}).get("message", "")
        self.assertNotIn("—", msg)


if __name__ == "__main__":
    unittest.main()
