"""Tests for string interpolation syntax, v4.0 Design Doc 05."""
import io
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

import nodus  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402
from nodus.frontend.lexer import tokenize  # noqa: E402


def _run(src: str) -> list[str]:
    vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
    loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader.load_module_from_source(src, module_name="test.nd")
    return buf.getvalue().splitlines()


def _raises(src: str, fragment: str) -> bool:
    try:
        _run(src)
        return False
    except Exception as e:
        return fragment.lower() in str(e).lower()


class LexerTokenTests(unittest.TestCase):
    """Verify that _lex_string emits the right token sequences."""

    def test_plain_string_emits_str_token(self):
        toks = [t for t in tokenize('"hello"') if t.kind != "EOF"]
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].kind, "STR")
        self.assertEqual(toks[0].val, "hello")

    def test_interpolated_string_emits_five_token_kinds(self):
        toks = [t for t in tokenize('"hi \\(name)!"') if t.kind != "EOF"]
        kinds = [t.kind for t in toks]
        self.assertIn("STRING_START", kinds)
        self.assertIn("STRING_LITERAL", kinds)
        self.assertIn("INTERP_START", kinds)
        self.assertIn("INTERP_END", kinds)
        self.assertIn("STRING_END", kinds)

    def test_interp_start_followed_by_id(self):
        toks = [t for t in tokenize('"\\(x)"') if t.kind != "EOF"]
        kinds = [t.kind for t in toks]
        self.assertEqual(kinds, ["STRING_START", "INTERP_START", "ID", "INTERP_END", "STRING_END"])

    def test_double_backslash_not_interpolation(self):
        # "\\(" in Nodus source is a literal \( in the output
        toks = [t for t in tokenize('"\\\\(hello)"') if t.kind != "EOF"]
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].kind, "STR")
        self.assertEqual(toks[0].val, "\\(hello)")

    def test_adjacent_interpolations_no_empty_literal(self):
        # "\(a)\(b)" — two interpolations, no literal between them
        toks = [t for t in tokenize('"\\(a)\\(b)"') if t.kind != "EOF"]
        # Should NOT have an empty STRING_LITERAL between the two interpolations
        literal_vals = [t.val for t in toks if t.kind == "STRING_LITERAL"]
        self.assertNotIn("", literal_vals)

    def test_escape_sequences_decoded_in_literal_parts(self):
        toks = [t for t in tokenize('"hello\\n\\(x)"') if t.kind != "EOF"]
        literals = [t for t in toks if t.kind == "STRING_LITERAL"]
        self.assertEqual(len(literals), 1)
        self.assertEqual(literals[0].val, "hello\n")

    def test_nested_string_in_interpolation(self):
        # "\("inner")" — nested string inside interpolation
        toks = [t for t in tokenize('"\\("inner")"') if t.kind != "EOF"]
        kinds = [t.kind for t in toks]
        self.assertIn("STR", kinds)


class BasicInterpolationTests(unittest.TestCase):
    """Basic end-to-end interpolation tests."""

    def test_single_variable(self):
        out = _run('let name = "world"\nprint("hello \\(name)!")')
        self.assertEqual(out[0], "hello world!")

    def test_expression_in_interp(self):
        out = _run('let x = 10i\nprint("result: \\(x * 3i)")')
        self.assertEqual(out[0], "result: 30")

    def test_leading_literal(self):
        out = _run('let n = "foo"\nprint("prefix \\(n)")')
        self.assertEqual(out[0], "prefix foo")

    def test_trailing_literal(self):
        out = _run('let n = "bar"\nprint("\\(n) suffix")')
        self.assertEqual(out[0], "bar suffix")

    def test_no_surrounding_literals(self):
        out = _run('let n = "only"\nprint("\\(n)")')
        self.assertEqual(out[0], "only")

    def test_adjacent_interpolations(self):
        out = _run('let a = "foo"\nlet b = "bar"\nprint("\\(a)\\(b)")')
        self.assertEqual(out[0], "foobar")

    def test_multiple_interpolations_with_literals(self):
        out = _run('let x = "X"\nlet y = "Y"\nprint("a\\(x)b\\(y)c")')
        self.assertEqual(out[0], "aXbYc")

    def test_plain_string_unchanged(self):
        out = _run('print("no interpolation here")')
        self.assertEqual(out[0], "no interpolation here")


class StringificationTests(unittest.TestCase):
    """Verify str() coercion for each value type."""

    def test_string_passthrough(self):
        out = _run('let s = "val"\nprint("\\(s)")')
        self.assertEqual(out[0], "val")

    def test_int_stringified(self):
        out = _run('let n = 42i\nprint("\\(n)")')
        self.assertEqual(out[0], "42")

    def test_float_stringified(self):
        out = _run('let f = 3.14\nprint("\\(f)")')
        self.assertIn("3.14", out[0])

    def test_bool_true_stringified(self):
        out = _run('print("\\(true)")')
        self.assertEqual(out[0], "true")

    def test_bool_false_stringified(self):
        out = _run('print("\\(false)")')
        self.assertEqual(out[0], "false")

    def test_nil_stringified(self):
        out = _run('print("\\(nil)")')
        self.assertEqual(out[0], "nil")

    def test_explicit_str_call_inside_interp(self):
        out = _run('let n = 99i\nprint("\\(str(n))")')
        self.assertEqual(out[0], "99")


class ExpressionTests(unittest.TestCase):
    """Verify that arbitrary expressions are supported inside interpolation."""

    def test_arithmetic_expression(self):
        out = _run('print("\\(2i + 3i)")')
        self.assertEqual(out[0], "5")

    def test_function_call_in_interp(self):
        out = _run('fn double(x) { return x * 2i }\nprint("\\(double(5i))")')
        self.assertEqual(out[0], "10")

    def test_ternary_via_fn(self):
        out = _run('fn pick(b) { if (b) { return "yes" } return "no" }\nprint("\\(pick(true))")')
        self.assertEqual(out[0], "yes")

    def test_method_access(self):
        out = _run('let r = {x: 7i}\nprint("\\(r.x)")')
        self.assertEqual(out[0], "7")

    def test_multiline_expression(self):
        out = _run('let v = 5i\nprint("v: \\(\n    v * v\n)")')
        self.assertEqual(out[0], "v: 25")


class EscapeSequenceTests(unittest.TestCase):
    """Verify escape sequences within string interpolation."""

    def test_newline_escape_in_literal_part(self):
        out = _run('let x = "X"\nprint("line1\\nline2 \\(x)")')
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], "line1")
        self.assertEqual(out[1], "line2 X")

    def test_tab_escape_in_literal_part(self):
        out = _run('let x = "X"\nprint("col1\\t\\(x)")')
        self.assertIn("\t", out[0])
        self.assertIn("X", out[0])

    def test_double_backslash_is_literal(self):
        # "\\(" is a literal \( — not interpolation
        out = _run('print("\\\\(not interp)")')
        self.assertEqual(out[0], "\\(not interp)")

    def test_escaped_quote_in_literal(self):
        out = _run('let n = "bob"\nprint("say \\"hi\\" \\(n)")')
        self.assertEqual(out[0], 'say "hi" bob')


class NestedStringTests(unittest.TestCase):
    """Verify strings nested inside interpolations."""

    def test_string_literal_in_interp(self):
        out = _run('print("\\("inner")")')
        self.assertEqual(out[0], "inner")

    def test_nested_concat_in_interp(self):
        out = _run('let n = "bob"\nprint("\\("hello " + n)")')
        self.assertEqual(out[0], "hello bob")

    def test_depth_2_interpolation(self):
        # "\(\("deep"))" — two levels of nesting
        out = _run('let x = "world"\nprint("\\("hello \\(x)")")')
        self.assertEqual(out[0], "hello world")


class ErrorTests(unittest.TestCase):
    """Verify parse errors for malformed interpolation."""

    def test_empty_interpolation_is_error(self):
        self.assertTrue(_raises('print("\\()")', "empty interpolation"))

    def test_format_specifier_reserved(self):
        self.assertTrue(_raises('let x = 3.14\nprint("\\(x:.2f)")', "reserved"))

    def test_unclosed_interpolation_is_error(self):
        self.assertTrue(_raises('print("\\(name")', "unterminated"))

    def test_unclosed_outer_string_is_error(self):
        self.assertTrue(_raises('print("\\(x)', "unclosed") or
                        _raises('print("\\(x)', "unterminated"))

    def test_nested_string_unclosed_is_error(self):
        # Nested string not closed: "\(name + "unclosed)
        self.assertTrue(_raises('print("\\(x + "y)")', "unterminated"))
