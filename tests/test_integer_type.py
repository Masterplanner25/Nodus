"""Tests for Phase 3 integer type implementation (design doc 01-integer-type.md)."""

import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str) -> list[str]:
    vm = lang.VM([], {}, code_locs=[])
    loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader.load_module_from_source(src, module_name="<test>")
    return buf.getvalue().splitlines()


def run_error(src: str):
    """Run program expected to raise; return the exception."""
    vm = lang.VM([], {}, code_locs=[])
    loader = ModuleLoader(project_root=None, vm=vm)
    try:
        loader.load_module_from_source(src, module_name="<test>")
    except Exception as e:
        return e
    raise AssertionError("Expected an exception but none was raised")


class IntLiteralLexerTests(unittest.TestCase):
    """Lexer correctly tokenizes integer literals."""

    def test_zero_int(self):
        self.assertEqual(run_program("print(0i)"), ["0"])

    def test_small_int(self):
        self.assertEqual(run_program("print(42i)"), ["42"])

    def test_large_int_exact(self):
        # Value above 2^53 — would lose precision as float
        src = "print(9007199254740993i)"
        self.assertEqual(run_program(src), ["9007199254740993"])

    def test_arbitrary_precision(self):
        src = "print(123456789012345678901234567890i)"
        self.assertEqual(run_program(src), ["123456789012345678901234567890"])

    def test_int_in_expression(self):
        self.assertEqual(run_program("let x = 10i\nprint(x)"), ["10"])

    def test_plain_number_still_float(self):
        # Existing behavior: plain 1 is float, prints as 1.0
        self.assertEqual(run_program("print(1)"), ["1.0"])

    def test_plain_decimal_still_float(self):
        self.assertEqual(run_program("print(1.0)"), ["1.0"])


class IntTypeTagTests(unittest.TestCase):
    """type() returns 'int' for integer values."""

    def test_type_of_int_literal(self):
        self.assertEqual(run_program('print(type(42i))'), ["int"])

    def test_type_of_float_literal(self):
        self.assertEqual(run_program('print(type(42.0))'), ["float"])

    def test_type_of_plain_number(self):
        self.assertEqual(run_program('print(type(42))'), ["float"])

    def test_type_of_zero_int(self):
        self.assertEqual(run_program('print(type(0i))'), ["int"])


class IntArithmeticTests(unittest.TestCase):
    """Arithmetic semantics per design doc §2.3."""

    def test_int_plus_int_is_int(self):
        self.assertEqual(run_program('print(1i + 1i)'), ["2"])

    def test_int_minus_int_is_int(self):
        self.assertEqual(run_program('print(5i - 3i)'), ["2"])

    def test_int_times_int_is_int(self):
        self.assertEqual(run_program('print(3i * 4i)'), ["12"])

    def test_int_div_int_is_int(self):
        # Integer / integer uses floor division, always returns int
        self.assertEqual(run_program('print(1i / 2i)'), ["0"])

    def test_int_div_int_whole_result(self):
        self.assertEqual(run_program('print(4i / 2i)'), ["2"])

    def test_int_mod_int_is_int(self):
        self.assertEqual(run_program('print(7i % 3i)'), ["1"])

    def test_int_plus_float_is_float(self):
        self.assertEqual(run_program('print(1i + 1.0)'), ["2.0"])

    def test_float_plus_int_is_float(self):
        self.assertEqual(run_program('print(1.0 + 1i)'), ["2.0"])

    def test_int_times_float_is_float(self):
        self.assertEqual(run_program('print(3i * 2.0)'), ["6.0"])

    def test_unary_minus_int(self):
        self.assertEqual(run_program('print(-5i)'), ["-5"])

    def test_unary_minus_int_type(self):
        self.assertEqual(run_program('print(type(-5i))'), ["int"])

    def test_large_int_arithmetic_exact(self):
        # Would overflow float precision, stays exact as int
        src = "print(9007199254740992i + 1i)"
        self.assertEqual(run_program(src), ["9007199254740993"])


class IntComparisonTests(unittest.TestCase):
    """Comparison semantics per design doc §2.3."""

    def test_int_eq_int(self):
        self.assertEqual(run_program('print(1i == 1i)'), ["true"])

    def test_int_eq_float_coercion(self):
        # 1i == 1 should be true (coercion per Phase 0 decision 3)
        self.assertEqual(run_program('print(1i == 1)'), ["true"])

    def test_int_eq_float_explicit(self):
        self.assertEqual(run_program('print(1i == 1.0)'), ["true"])

    def test_int_lt_int(self):
        self.assertEqual(run_program('print(1i < 2i)'), ["true"])

    def test_int_gt_int(self):
        self.assertEqual(run_program('print(3i > 2i)'), ["true"])

    def test_large_int_comparison(self):
        # Two large values that aren't float-exact — int comparison stays exact
        src = "print(9007199254740993i > 9007199254740992i)"
        self.assertEqual(run_program(src), ["true"])

    def test_int_ne_int(self):
        self.assertEqual(run_program('print(1i != 2i)'), ["true"])


class IntBooleanCoercionTests(unittest.TestCase):
    """Boolean coercion: 0i is falsy, non-zero int is truthy."""

    def test_zero_int_is_falsy(self):
        src = 'if (0i) { print("yes") } else { print("no") }'
        self.assertEqual(run_program(src), ["no"])

    def test_nonzero_int_is_truthy(self):
        src = 'if (1i) { print("yes") } else { print("no") }'
        self.assertEqual(run_program(src), ["yes"])


class MathParseIntTests(unittest.TestCase):
    """math.parse_int function."""

    def test_parse_valid_integer(self):
        src = 'import "std:math" as m\nprint(m.parse_int("42"))'
        self.assertEqual(run_program(src), ["42"])

    def test_parse_returns_int_type(self):
        src = 'import "std:math" as m\nprint(type(m.parse_int("42")))'
        self.assertEqual(run_program(src), ["int"])

    def test_parse_large_integer(self):
        src = 'import "std:math" as m\nprint(m.parse_int("9007199254740993"))'
        self.assertEqual(run_program(src), ["9007199254740993"])

    def test_parse_negative_integer(self):
        src = 'import "std:math" as m\nprint(m.parse_int("-5"))'
        self.assertEqual(run_program(src), ["-5"])

    def test_parse_invalid_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.parse_int("foo")\nprint(type(r))'
        self.assertEqual(run_program(src), ["error"])

    def test_parse_decimal_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.parse_int("3.14")\nprint(type(r))'
        self.assertEqual(run_program(src), ["error"])

    def test_parse_err_kind(self):
        src = 'import "std:math" as m\nlet r = m.parse_int("bad")\nprint(r.kind)'
        self.assertEqual(run_program(src), ["parse_error"])


class MathToIntTests(unittest.TestCase):
    """math.to_int function."""

    def test_float_to_int_truncates(self):
        src = 'import "std:math" as m\nprint(m.to_int(3.7))'
        self.assertEqual(run_program(src), ["3"])

    def test_float_to_int_negative_truncates_toward_zero(self):
        src = 'import "std:math" as m\nprint(m.to_int(-3.7))'
        self.assertEqual(run_program(src), ["-3"])

    def test_float_to_int_returns_int_type(self):
        src = 'import "std:math" as m\nprint(type(m.to_int(3.7)))'
        self.assertEqual(run_program(src), ["int"])

    def test_int_passthrough(self):
        src = 'import "std:math" as m\nprint(m.to_int(5i))'
        self.assertEqual(run_program(src), ["5"])


class MathToFloatTests(unittest.TestCase):
    """math.to_float function."""

    def test_int_to_float(self):
        src = 'import "std:math" as m\nprint(m.to_float(3i))'
        self.assertEqual(run_program(src), ["3.0"])

    def test_int_to_float_returns_number_type(self):
        src = 'import "std:math" as m\nprint(type(m.to_float(3i)))'
        self.assertEqual(run_program(src), ["float"])


class MathIsIntTests(unittest.TestCase):
    """math.is_int function."""

    def test_int_literal_is_int(self):
        src = 'import "std:math" as m\nprint(m.is_int(3i))'
        self.assertEqual(run_program(src), ["true"])

    def test_float_is_not_int(self):
        src = 'import "std:math" as m\nprint(m.is_int(3.0))'
        self.assertEqual(run_program(src), ["false"])

    def test_plain_number_is_not_int(self):
        src = 'import "std:math" as m\nprint(m.is_int(3))'
        self.assertEqual(run_program(src), ["false"])


class MathIdivTests(unittest.TestCase):
    """math.idiv function."""

    def test_basic_division(self):
        src = 'import "std:math" as m\nprint(m.idiv(7i, 2i))'
        self.assertEqual(run_program(src), ["3"])

    def test_returns_int_type(self):
        src = 'import "std:math" as m\nprint(type(m.idiv(7i, 2i)))'
        self.assertEqual(run_program(src), ["int"])

    def test_truncation_toward_zero_negative(self):
        # -7 / 2 = -3.5 → truncate toward zero = -3
        src = 'import "std:math" as m\nprint(m.idiv(-7i, 2i))'
        self.assertEqual(run_program(src), ["-3"])

    def test_both_negative(self):
        src = 'import "std:math" as m\nprint(m.idiv(-7i, -2i))'
        self.assertEqual(run_program(src), ["3"])

    def test_divide_by_zero_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.idiv(7i, 0i)\nprint(r.kind)'
        self.assertEqual(run_program(src), ["math_error"])

    def test_float_arg_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.idiv(7, 2)\nprint(r.kind)'
        self.assertEqual(run_program(src), ["type_error"])

    def test_first_arg_float_err_message(self):
        src = 'import "std:math" as m\nlet r = m.idiv(7, 2i)\nprint(r.message)'
        self.assertEqual(run_program(src), ["math.idiv requires int args, got float"])

    def test_second_arg_float_err_message(self):
        src = 'import "std:math" as m\nlet r = m.idiv(7i, 2)\nprint(r.message)'
        self.assertEqual(run_program(src), ["math.idiv requires int args, got int and float"])


class JsonParseIntTests(unittest.TestCase):
    """json.parse_int function."""

    def test_parse_large_integer_exact(self):
        src = 'import "std:json" as j\nprint(j.parse_int("9007199254740993"))'
        self.assertEqual(run_program(src), ["9007199254740993"])

    def test_parse_returns_int_type(self):
        src = 'import "std:json" as j\nprint(type(j.parse_int("42")))'
        self.assertEqual(run_program(src), ["int"])

    def test_decimal_string_returns_err(self):
        src = 'import "std:json" as j\nlet r = j.parse_int("3.14")\nprint(r.kind)'
        self.assertEqual(run_program(src), ["parse_error"])

    def test_scientific_notation_returns_err(self):
        src = 'import "std:json" as j\nlet r = j.parse_int("1e9")\nprint(r.kind)'
        self.assertEqual(run_program(src), ["parse_error"])

    def test_scientific_notation_err_message(self):
        src = 'import "std:json" as j\nlet r = j.parse_int("1e9")\nprint(r.message)'
        self.assertEqual(run_program(src), ['not an integer (scientific notation): "1e9"'])

    def test_invalid_string_returns_err(self):
        src = 'import "std:json" as j\nlet r = j.parse_int("abc")\nprint(r.kind)'
        self.assertEqual(run_program(src), ["parse_error"])

    def test_json_parse_unchanged(self):
        # json.parse must still return float for numeric values
        src = 'import "std:json" as j\nlet v = j.parse("42")\nprint(type(v))'
        self.assertEqual(run_program(src), ["float"])


class IntInCollectionTests(unittest.TestCase):
    """Integers work correctly in lists and maps."""

    def test_int_in_list(self):
        self.assertEqual(run_program('let xs = [1i, 2i, 3i]\nprint(xs[0i])'), ["1"])

    def test_int_index_access(self):
        self.assertEqual(run_program('let xs = [10, 20, 30]\nprint(xs[1i])'), ["20.0"])

    def test_int_in_map_value(self):
        self.assertEqual(run_program('let m = {"x": 42i}\nprint(m["x"])'), ["42"])

    def test_int_str_conversion(self):
        self.assertEqual(run_program('print(str(42i))'), ["42"])


class IntStringifyTests(unittest.TestCase):
    """json.stringify produces correct output for int values."""

    def test_int_stringifies_without_decimal(self):
        src = 'import "std:json" as j\nprint(j.stringify(42i))'
        self.assertEqual(run_program(src), ["42"])

    def test_float_stringifies_whole_without_decimal(self):
        # Existing behavior: 1.0 stringifies as "1" (not "1.0")
        src = 'import "std:json" as j\nprint(j.stringify(1.0))'
        self.assertEqual(run_program(src), ["1"])


if __name__ == "__main__":
    unittest.main()
