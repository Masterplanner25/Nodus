"""Tests for parser depth limiting (BUG-007)."""

import unittest

from nodus.tooling.runner import run_source


def _deeply_nested(depth: int) -> str:
    return "(" * depth + "1" + ")" * depth


class ParserDepthLimitTests(unittest.TestCase):
    def test_shallow_nesting_succeeds(self):
        result, _vm = run_source("let x = " + _deeply_nested(10), max_steps=10_000, timeout_ms=5_000)
        self.assertTrue(result.get("ok"), result)

    def test_moderate_nesting_succeeds(self):
        result, _vm = run_source("let x = " + _deeply_nested(30), max_steps=10_000, timeout_ms=5_000)
        self.assertTrue(result.get("ok"), result)

    def test_deep_nesting_raises_syntax_error_not_recursion_error(self):
        source = "let x = " + _deeply_nested(1000)
        result, _vm = run_source(source, max_steps=100_000, timeout_ms=5_000)
        self.assertFalse(result.get("ok"), "Expected failure on deep nesting")
        error = result.get("error") or {}
        # Must be a LangSyntaxError (parse stage), not an unhandled Python RecursionError
        self.assertIn(result.get("stage", ""), {"parse", "compile", "execute"})
        message = error.get("message", "") if isinstance(error, dict) else ""
        self.assertIn("nested", message.lower(), f"Expected 'nested' in error message, got: {message!r}")

    def test_extreme_nesting_no_python_recursion_error(self):
        """5000 nested parens must not bubble up as a Python RecursionError."""
        source = "let x = " + _deeply_nested(5000)
        try:
            result, _vm = run_source(source, max_steps=100_000, timeout_ms=5_000)
            self.assertFalse(result.get("ok"), "Expected failure on extreme nesting")
        except RecursionError:
            self.fail("Parser raised Python RecursionError instead of LangSyntaxError")


if __name__ == "__main__":
    unittest.main()
