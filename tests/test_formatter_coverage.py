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


if __name__ == "__main__":
    unittest.main()
