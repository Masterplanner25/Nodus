"""Formatter tests for anonymous function expressions (FnExpr)."""

import unittest

from nodus.tooling.formatter import format_source


class FormatterFnExprTests(unittest.TestCase):
    def test_fn_expr_no_params_empty_body(self):
        # FnExpr must appear in expression context; use let binding
        src = "let f = fn() {}"
        out = format_source(src)
        self.assertIn("fn() {}", out)
        # idempotent
        self.assertEqual(format_source(out), out)

    def test_fn_expr_no_params_single_stmt(self):
        # FnExpr must appear in expression context; use let binding
        src = "let f = fn() { work() }"
        out = format_source(src)
        self.assertIn("fn() { work() }", out)
        self.assertEqual(format_source(out), out)

    def test_fn_expr_as_call_argument(self):
        src = "spawn(fn() { work() })"
        out = format_source(src)
        self.assertIn("spawn(fn() { work() })", out)
        self.assertEqual(format_source(out), out)

    def test_fn_expr_with_params(self):
        src = "let add = fn(a, b) { a + b }"
        out = format_source(src)
        self.assertIn("fn(a, b) { a + b }", out)
        self.assertEqual(format_source(out), out)

    def test_fn_expr_with_return_type(self):
        src = "let inc = fn(a) -> Int { return a + 1 }"
        out = format_source(src)
        self.assertIn("fn(a) -> Int { return a + 1 }", out)
        self.assertEqual(format_source(out), out)

    def test_fn_expr_multi_stmt_body(self):
        src = "let f = fn() {\nlet x = 1\nlet y = 2\nreturn x + y\n}"
        out = format_source(src)
        self.assertIn("fn() {", out)
        self.assertIn("let x = 1", out)
        self.assertIn("let y = 2", out)
        self.assertIn("return x + y", out)
        self.assertEqual(format_source(out), out)

    def test_fn_expr_nested_in_coroutine_spawn(self):
        src = "spawn(coroutine(fn() { sender(ch) }))"
        out = format_source(src)
        self.assertIn("spawn(coroutine(fn() { sender(ch) }))", out)
        self.assertEqual(format_source(out), out)


if __name__ == "__main__":
    unittest.main()
