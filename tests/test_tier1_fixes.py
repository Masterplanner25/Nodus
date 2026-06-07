"""Tests for v2.1 Tier-1 fixes: modulo, scientific notation, strings.replace, --help, check output."""

import io
import os
import sys
import unittest

from nodus.tooling.runner import run_source


def _run(code, **kw):
    result, _ = run_source(code, max_steps=50_000, timeout_ms=5_000, **kw)
    return result


class ModuloOperatorTests(unittest.TestCase):
    def test_basic_modulo(self):
        r = _run("print(10 % 3)")
        self.assertTrue(r["ok"], r)
        self.assertIn("1", r["stdout"])

    def test_modulo_zero_remainder(self):
        r = _run("print(9 % 3)")
        self.assertTrue(r["ok"], r)
        self.assertIn("0", r["stdout"])

    def test_modulo_by_zero_raises(self):
        r = _run("print(5 % 0)")
        self.assertFalse(r["ok"], r)

    def test_modulo_in_expression(self):
        r = _run("let x = 17 % 5\nprint(x)")
        self.assertTrue(r["ok"], r)
        self.assertIn("2", r["stdout"])

    def test_modulo_precedence_with_multiply(self):
        r = _run("print(2 * 7 % 5)")
        self.assertTrue(r["ok"], r)
        self.assertIn("4", r["stdout"])


class ScientificNotationTests(unittest.TestCase):
    def test_positive_exponent(self):
        r = _run("print(1e3)")
        self.assertTrue(r["ok"], r)
        self.assertIn("1000", r["stdout"])

    def test_negative_exponent(self):
        r = _run("print(1e-2)")
        self.assertTrue(r["ok"], r)
        self.assertIn("0.01", r["stdout"])

    def test_explicit_positive_exponent(self):
        r = _run("print(2.5e+2)")
        self.assertTrue(r["ok"], r)
        self.assertIn("250", r["stdout"])

    def test_uppercase_e(self):
        r = _run("print(3E4)")
        self.assertTrue(r["ok"], r)
        self.assertIn("30000", r["stdout"])

    def test_sci_in_arithmetic(self):
        r = _run("print(1e2 + 1e1)")
        self.assertTrue(r["ok"], r)
        self.assertIn("110", r["stdout"])


class StringsReplaceTests(unittest.TestCase):
    def test_replace_basic(self):
        r = _run('import "std:strings" as s\nprint(s.replace("hello world", "world", "Nodus"))')
        self.assertTrue(r["ok"], r)
        self.assertIn("hello Nodus", r["stdout"])

    def test_replace_all_occurrences(self):
        r = _run('import "std:strings" as s\nprint(s.replace("aaa", "a", "b"))')
        self.assertTrue(r["ok"], r)
        self.assertIn("bbb", r["stdout"])

    def test_replace_no_match(self):
        r = _run('import "std:strings" as s\nprint(s.replace("hello", "xyz", "abc"))')
        self.assertTrue(r["ok"], r)
        self.assertIn("hello", r["stdout"])

    def test_str_replace_builtin_directly(self):
        r = _run('print(str_replace("foo bar", "bar", "baz"))')
        self.assertTrue(r["ok"], r)
        self.assertIn("foo baz", r["stdout"])


class AstDisHelpTests(unittest.TestCase):
    def _main(self, args):
        from nodus.cli.cli import main
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            code = main(["nodus"] + args)
        finally:
            sys.stdout = old
        return code, buf.getvalue()

    def test_ast_help_exits_zero(self):
        code, out = self._main(["ast", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("Usage", out)

    def test_ast_dash_h_exits_zero(self):
        code, out = self._main(["ast", "-h"])
        self.assertEqual(code, 0)
        self.assertIn("Usage", out)

    def test_dis_help_exits_zero(self):
        code, out = self._main(["dis", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("Usage", out)

    def test_dis_dash_h_exits_zero(self):
        code, out = self._main(["dis", "-h"])
        self.assertEqual(code, 0)
        self.assertIn("Usage", out)


class CheckOutputTests(unittest.TestCase):
    def test_check_prints_ok_on_success(self):
        import tempfile
        from nodus.cli.cli import main
        with tempfile.NamedTemporaryFile(suffix=".nd", mode="w", delete=False, encoding="utf-8") as f:
            f.write('let x = 1\n')
            path = f.name
        try:
            buf = io.StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code = main(["nodus", "check", path])
            finally:
                sys.stdout = old
            self.assertEqual(code, 0)
            self.assertIn("OK", buf.getvalue())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
