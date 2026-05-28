"""Tests for v4.0 Design Docs 10 (type naming) and 11 (equality coercion)."""

import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

import nodus  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402
import io
from contextlib import redirect_stdout


def _run(src: str) -> list[str]:
    vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader = ModuleLoader(project_root=None, vm=vm)
        loader.load_module_from_source(src, module_name="test.nd")
    return buf.getvalue().splitlines()


# ---------------------------------------------------------------------------
# Doc 10: type() naming
# ---------------------------------------------------------------------------

class TypeNamingTests(unittest.TestCase):

    def test_float_literal_returns_float(self):
        self.assertEqual(_run('print(type(1.0))'), ["float"])

    def test_float_unadorned_returns_float(self):
        self.assertEqual(_run('print(type(42))'), ["float"])

    def test_int_suffix_returns_int(self):
        self.assertEqual(_run('print(type(1i))'), ["int"])

    def test_zero_int_returns_int(self):
        self.assertEqual(_run('print(type(0i))'), ["int"])

    def test_string_unchanged(self):
        self.assertEqual(_run('print(type("hello"))'), ["string"])

    def test_bool_unchanged(self):
        self.assertEqual(_run('print(type(true))'), ["bool"])

    def test_nil_unchanged(self):
        self.assertEqual(_run('print(type(nil))'), ["nil"])

    def test_list_unchanged(self):
        self.assertEqual(_run('print(type([1i]))'), ["list"])

    def test_record_unchanged(self):
        self.assertEqual(_run('print(type({a: 1i}))'), ["record"])

    def test_nan_is_float(self):
        r = _run('import "std:math" as m\nprint(type(m.nan))')
        self.assertEqual(r, ["float"])

    def test_infinity_is_float(self):
        r = _run('import "std:math" as m\nprint(type(m.infinity))')
        self.assertEqual(r, ["float"])

    def test_no_longer_number(self):
        self.assertNotEqual(_run('print(type(1.0))'), ["number"])


class MathIsNumericTests(unittest.TestCase):

    def test_int_is_numeric(self):
        r = _run('import "std:math" as m\nprint(m.is_numeric(1i))')
        self.assertEqual(r, ["true"])

    def test_float_is_numeric(self):
        r = _run('import "std:math" as m\nprint(m.is_numeric(1.0))')
        self.assertEqual(r, ["true"])

    def test_bool_not_numeric(self):
        r = _run('import "std:math" as m\nprint(m.is_numeric(true))')
        self.assertEqual(r, ["false"])

    def test_string_not_numeric(self):
        r = _run('import "std:math" as m\nprint(m.is_numeric("1"))')
        self.assertEqual(r, ["false"])

    def test_nil_not_numeric(self):
        r = _run('import "std:math" as m\nprint(m.is_numeric(nil))')
        self.assertEqual(r, ["false"])


class MathIsFloatTests(unittest.TestCase):

    def test_float_is_float(self):
        r = _run('import "std:math" as m\nprint(m.is_float(1.0))')
        self.assertEqual(r, ["true"])

    def test_int_not_float(self):
        r = _run('import "std:math" as m\nprint(m.is_float(1i))')
        self.assertEqual(r, ["false"])

    def test_nan_is_float(self):
        r = _run('import "std:math" as m\nprint(m.is_float(m.nan))')
        self.assertEqual(r, ["true"])

    def test_bool_not_float(self):
        r = _run('import "std:math" as m\nprint(m.is_float(true))')
        self.assertEqual(r, ["false"])


class MathIsIntTests(unittest.TestCase):

    def test_int_suffix_is_int(self):
        r = _run('import "std:math" as m\nprint(m.is_int(3i))')
        self.assertEqual(r, ["true"])

    def test_float_not_int(self):
        r = _run('import "std:math" as m\nprint(m.is_int(3.0))')
        self.assertEqual(r, ["false"])

    def test_bool_not_int(self):
        r = _run('import "std:math" as m\nprint(m.is_int(true))')
        self.assertEqual(r, ["false"])


# ---------------------------------------------------------------------------
# Doc 11: equality coercion
# ---------------------------------------------------------------------------

class EqualityCoercionTests(unittest.TestCase):

    # Number family: int ↔ float preserved
    def test_int_eq_float_same_value(self):
        self.assertEqual(_run('print(1i == 1.0)'), ["true"])

    def test_int_eq_float_diff_value(self):
        self.assertEqual(_run('print(1i == 2.0)'), ["false"])

    def test_float_eq_float(self):
        self.assertEqual(_run('print(1.0 == 1.0)'), ["true"])

    def test_int_eq_int(self):
        self.assertEqual(_run('print(2i == 2i)'), ["true"])

    # Cross-family: removed in v4.0
    def test_zero_neq_false(self):
        self.assertEqual(_run('print(0i == false)'), ["false"])

    def test_one_neq_true(self):
        self.assertEqual(_run('print(1i == true)'), ["false"])

    def test_empty_string_neq_false(self):
        self.assertEqual(_run('print("" == false)'), ["false"])

    def test_string_one_neq_int_one(self):
        self.assertEqual(_run('print("1" == 1i)'), ["false"])

    def test_nil_neq_false(self):
        self.assertEqual(_run('print(nil == false)'), ["false"])

    def test_nil_neq_zero(self):
        self.assertEqual(_run('print(nil == 0i)'), ["false"])

    # nil == nil still true
    def test_nil_eq_nil(self):
        self.assertEqual(_run('print(nil == nil)'), ["true"])

    # != operator consistency
    def test_zero_ne_false_is_true(self):
        self.assertEqual(_run('print(0i != false)'), ["true"])

    def test_int_ne_float_same_value_is_false(self):
        self.assertEqual(_run('print(1i != 1.0)'), ["false"])

    # Same-type equality unchanged
    def test_string_eq_string(self):
        self.assertEqual(_run('print("hi" == "hi")'), ["true"])

    def test_bool_eq_bool(self):
        self.assertEqual(_run('print(true == true)'), ["true"])

    def test_bool_neq_bool(self):
        self.assertEqual(_run('print(true == false)'), ["false"])


class TypeEqTests(unittest.TestCase):

    def test_int_eq_int(self):
        self.assertEqual(_run('print(type_eq(1i, 1i))'), ["true"])

    def test_int_neq_float(self):
        self.assertEqual(_run('print(type_eq(1i, 1.0))'), ["false"])

    def test_zero_neq_false(self):
        self.assertEqual(_run('print(type_eq(0i, false))'), ["false"])

    def test_bool_eq_bool(self):
        self.assertEqual(_run('print(type_eq(true, true))'), ["true"])

    def test_string_eq_string(self):
        self.assertEqual(_run('print(type_eq("hi", "hi"))'), ["true"])

    def test_nil_eq_nil(self):
        self.assertEqual(_run('print(type_eq(nil, nil))'), ["true"])

    def test_nil_neq_false(self):
        self.assertEqual(_run('print(type_eq(nil, false))'), ["false"])


class BoolEqualTests(unittest.TestCase):

    def test_true_equals_true(self):
        r = _run('import "std:bool" as b\nprint(b.equal(true, true))')
        self.assertEqual(r, ["true"])

    def test_false_equals_false(self):
        r = _run('import "std:bool" as b\nprint(b.equal(false, false))')
        self.assertEqual(r, ["true"])

    def test_int_one_not_equal_true(self):
        r = _run('import "std:bool" as b\nprint(b.equal(1i, true))')
        self.assertEqual(r, ["false"])

    def test_zero_not_equal_false(self):
        r = _run('import "std:bool" as b\nprint(b.equal(0i, false))')
        self.assertEqual(r, ["false"])

    def test_nil_not_equal_false(self):
        r = _run('import "std:bool" as b\nprint(b.equal(nil, false))')
        self.assertEqual(r, ["false"])

    def test_non_bool_second_arg_returns_err(self):
        r = _run('import "std:bool" as b\nlet e = b.equal(0i, 0i)\nprint(type(e))')
        self.assertEqual(r, ["error"])


if __name__ == "__main__":
    unittest.main()
