"""Regression tests for v3.0.2 fixes.

BUG-V31E-01 (#75): 1I uppercase suffix must give a parse-time syntax error.
BUG-V31E-02 (#76): math.log(value, base) argument order.

Both tests are written BEFORE the fixes are confirmed and committed,
per the test-must-fail-before-fix protocol from the v3.0.2 patch prompt.
"""

import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.frontend.lexer import tokenize
from nodus.runtime.diagnostics import LangSyntaxError
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str) -> list[str]:
    vm = lang.VM([], {}, code_locs=[])
    loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader.load_module_from_source(src, module_name="<test>")
    return buf.getvalue().splitlines()


def run_error(src: str):
    vm = lang.VM([], {}, code_locs=[])
    loader = ModuleLoader(project_root=None, vm=vm)
    try:
        loader.load_module_from_source(src, module_name="<test>")
    except Exception as e:
        return e
    raise AssertionError("Expected an exception but none was raised")


class BugV31E01UppercaseISuffix(unittest.TestCase):
    """BUG-V31E-01 (#75): 1I must be a parse-time syntax error.

    v3.0.1 claimed to ship this fix (BUG-E12 / issue #64) but the
    distributed wheel did not contain it.  This test exercises the
    full pipeline (lexer -> parser -> compiler) end-to-end.

    Expected: LangSyntaxError at parse time with a message explaining
    that the integer suffix must be lowercase 'i'.
    """

    def test_1I_raises_syntax_error(self):
        exc = run_error("let x = 1I")
        self.assertIsInstance(exc, LangSyntaxError,
            f"Expected LangSyntaxError, got {type(exc).__name__}: {exc}")

    def test_1I_error_message_mentions_lowercase(self):
        exc = run_error("let x = 1I")
        msg = str(exc).lower()
        self.assertIn("lowercase", msg,
            f"Error message should mention 'lowercase', got: {exc}")

    def test_1I_error_is_not_name_error(self):
        exc = run_error("let x = 1I")
        # Must NOT be a runtime name error ("undefined variable: I")
        self.assertIsInstance(exc, LangSyntaxError,
            "1I must fail at parse time, not produce a runtime name error")

    def test_1I_error_is_parse_time(self):
        # LangSyntaxError (not LangRuntimeError) confirms parse-time detection
        from nodus.runtime.diagnostics import LangRuntimeError
        exc = run_error("let x = 1I")
        self.assertNotIsInstance(exc, LangRuntimeError,
            "1I must fail at parse time, not runtime")

    def test_lowercase_1i_still_works(self):
        # Regression: valid lowercase suffix must not be broken by the fix
        result = run_program("print(1i)")
        self.assertEqual(result, ["1"])

    def test_lexer_raises_on_1I_directly(self):
        # Direct lexer test: tokenize must raise before AST is built
        with self.assertRaises(LangSyntaxError):
            tokenize("let x = 1I")


class BugV31E02MathLogArgumentOrder(unittest.TestCase):
    """BUG-V31E-02 (#76): math.log(value, base) must return log_base(value).

    The v3.0.1 implementation of math.log ignored the value argument for
    two-arg calls and returned ln(base) instead of log_base(value).
    """

    # ── Two-arg form: must fail before fix ──────────────────────────────────

    def test_log_base_10_of_100_is_2(self):
        result = run_program('import "std:math" as m\nprint(m.log(100, 10))')
        self.assertEqual(result, ["2.0"],
            f"math.log(100, 10) should be 2.0, got {result}")

    def test_log_base_2_of_8_is_3(self):
        result = run_program('import "std:math" as m\nprint(m.log(8, 2))')
        self.assertEqual(result, ["3.0"],
            f"math.log(8, 2) should be 3.0, got {result}")

    def test_log_base_10_of_1000_is_3(self):
        result = run_program('import "std:math" as m\nprint(m.log(1000, 10))')
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(float(result[0]), 3.0, places=10,
            msg=f"math.log(1000, 10) should be ≈3.0, got {result}")

    def test_log_base_10_of_10_is_1(self):
        result = run_program('import "std:math" as m\nprint(m.log(10, 10))')
        self.assertEqual(result, ["1.0"],
            f"math.log(10, 10) should be 1.0, got {result}")

    # ── Single-arg natural log: must pass both before and after fix ──────────

    def test_single_arg_natural_log(self):
        import math as _math
        result = run_program('import "std:math" as m\nprint(m.log(10))')
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(float(result[0]), _math.log(10), places=6,
            msg="math.log(10) should return the natural log of 10")

    def test_single_arg_log_of_1_is_zero(self):
        result = run_program('import "std:math" as m\nprint(m.log(1))')
        self.assertEqual(result, ["0.0"],
            "math.log(1) should be 0.0 (natural log of 1)")

    # ── Error paths: must pass both before and after fix ─────────────────────

    def test_log_of_zero_returns_err(self):
        result = run_program(
            'import "std:math" as m\n'
            'let e = m.log(0)\n'
            'print(e.kind)'
        )
        self.assertEqual(result, ["value_error"])

    def test_log_negative_base_returns_err(self):
        result = run_program(
            'import "std:math" as m\n'
            'let e = m.log(100, -1)\n'
            'print(e.kind)'
        )
        self.assertEqual(result, ["value_error"])

    def test_log_base_one_returns_err(self):
        result = run_program(
            'import "std:math" as m\n'
            'let e = m.log(100, 1)\n'
            'print(e.kind)'
        )
        self.assertEqual(result, ["value_error"])


if __name__ == "__main__":
    unittest.main()
