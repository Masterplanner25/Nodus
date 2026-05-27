"""Tests for v3.0 Batch 2B fixes: BUG-035/036/037/034/039/044/032."""

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


class IsBlankTests(unittest.TestCase):
    """BUG-035: strings.is_blank must match whitespace-only strings."""

    def test_empty_string_is_blank(self):
        out = run_program('import "std:strings" as s\nprint(s.is_blank(""))')
        self.assertEqual(out, ["true"])

    def test_whitespace_only_is_blank(self):
        out = run_program('import "std:strings" as s\nprint(s.is_blank("   "))')
        self.assertEqual(out, ["true"])

    def test_tabs_and_newlines_are_blank(self):
        out = run_program('import "std:strings" as s\nprint(s.is_blank("\t\n"))')
        self.assertEqual(out, ["true"])

    def test_non_blank_is_false(self):
        out = run_program('import "std:strings" as s\nprint(s.is_blank("hello"))')
        self.assertEqual(out, ["false"])

    def test_leading_space_content_not_blank(self):
        out = run_program('import "std:strings" as s\nprint(s.is_blank("  x  "))')
        self.assertEqual(out, ["false"])


class PathJoinTests(unittest.TestCase):
    """BUG-036: path.join must accept a list of segments."""

    def test_join_two_segments(self):
        out = run_program('import "std:path" as p\nprint(p.join(["a", "b"]))')
        self.assertIn("a", out[0])
        self.assertIn("b", out[0])

    def test_join_three_segments(self):
        out = run_program('import "std:path" as p\nprint(p.join(["a", "b", "c"]))')
        self.assertIn("a", out[0])
        self.assertIn("c", out[0])

    def test_join_single_segment(self):
        out = run_program('import "std:path" as p\nprint(p.join(["only"]))')
        self.assertEqual(out, ["only"])


class PathExtTests(unittest.TestCase):
    """BUG-037: path.ext must return extension with leading dot."""

    def test_ext_includes_leading_dot(self):
        out = run_program('import "std:path" as p\nprint(p.ext("script.nd"))')
        self.assertEqual(out, [".nd"])

    def test_ext_tar_gz(self):
        out = run_program('import "std:path" as p\nprint(p.ext("archive.tar.gz"))')
        self.assertEqual(out, [".gz"])

    def test_ext_no_extension_returns_empty(self):
        out = run_program('import "std:path" as p\nprint(p.ext("Makefile"))')
        self.assertEqual(out, [""])


class UtilsGetTests(unittest.TestCase):
    """BUG-034: utils.get(map, key, default) for safe map access."""

    def test_get_existing_key(self):
        src = """
import "std:utils" as u
let m = {"a": 1, "b": 2}
print(u.get(m, "a", 99))
"""
        out = run_program(src)
        self.assertEqual(out, ["1.0"])

    def test_get_missing_key_returns_default(self):
        src = """
import "std:utils" as u
let m = {"a": 1}
print(u.get(m, "missing", 42))
"""
        out = run_program(src)
        self.assertEqual(out, ["42.0"])

    def test_get_string_default(self):
        src = """
import "std:utils" as u
let m = {}
print(u.get(m, "host", "localhost"))
"""
        out = run_program(src)
        self.assertEqual(out, ["localhost"])

    def test_get_nil_default(self):
        src = """
import "std:utils" as u
let m = {}
print(u.get(m, "key", nil))
"""
        out = run_program(src)
        self.assertEqual(out, ["nil"])


class MapMultilineTests(unittest.TestCase):
    """BUG-039: map literal value may start on a new line after the colon."""

    def test_list_value_on_next_line(self):
        src = """
let m = {
    "items":
        ["a", "b"]
}
print(m["items"][0])
"""
        out = run_program(src)
        self.assertEqual(out, ["a"])

    def test_nested_map_value_on_next_line(self):
        src = """
let m = {
    "inner":
        {"x": 1}
}
print(m["inner"]["x"])
"""
        out = run_program(src)
        self.assertEqual(out, ["1.0"])

    def test_string_value_on_next_line(self):
        src = """
let m = {
    "greeting":
        "hello"
}
print(m["greeting"])
"""
        out = run_program(src)
        self.assertEqual(out, ["hello"])

    def test_multiline_map_still_works_inline(self):
        """Regression: inline key-value style must still parse correctly."""
        src = """
let m = {"a": 1, "b": 2}
print(m["a"])
"""
        out = run_program(src)
        self.assertEqual(out, ["1.0"])


class ErrFieldsTests(unittest.TestCase):
    """BUG-044: err record path/line/column/stack fields must be accessible."""

    def test_err_has_path_field(self):
        src = """
try {
    let x = 1.0 + "x"
} catch err {
    print(type(err.path))
}
"""
        out = run_program(src)
        self.assertEqual(out, ["string"])

    def test_err_has_line_field(self):
        src = """
try {
    let x = 1.0 + "x"
} catch err {
    print(type(err.line))
}
"""
        out = run_program(src)
        # Phase 3: err.line is a Nodus int (type() returns "int")
        self.assertEqual(out, ["int"])

    def test_err_has_column_field(self):
        src = """
try {
    let x = 1.0 + "x"
} catch err {
    print(type(err.column))
}
"""
        out = run_program(src)
        # Phase 3: err.column is a Nodus int (type() returns "int")
        self.assertEqual(out, ["int"])

    def test_err_has_stack_field(self):
        src = """
try {
    let x = 1.0 + "x"
} catch err {
    print(type(err.stack))
}
"""
        out = run_program(src)
        self.assertEqual(out, ["list"])


class TypeVsTypeofTests(unittest.TestCase):
    """BUG-032: type() and rt.typeof() documented divergence must be consistent."""

    def test_type_returns_number_for_int(self):
        out = run_program("print(type(42))")
        self.assertEqual(out, ["number"])

    def test_type_returns_number_for_float(self):
        out = run_program("print(type(3.14))")
        self.assertEqual(out, ["number"])

    def test_typeof_returns_int_for_whole(self):
        src = 'import "std:runtime" as rt\nprint(rt.typeof(42))'
        out = run_program(src)
        self.assertEqual(out, ["int"])

    def test_typeof_returns_float_for_fractional(self):
        src = 'import "std:runtime" as rt\nprint(rt.typeof(3.14))'
        out = run_program(src)
        self.assertEqual(out, ["float"])
