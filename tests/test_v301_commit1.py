"""v3.0.1 Commit 1 tests — Replace contract completion + parser polish.

Covers:
- BUG-E01: json.parse(non-string) returns type_error err record (#53)
- BUG-E02: math.sqrt(-1) returns value_error err record (#54)
- BUG-E05: math.log and math.pow implemented with Replace wrapping (#57)
- BUG-E06: path.relative and path.absolute implemented (#58)
- BUG-E07: fs.mkdir (strict) and fs.delete exported from std:fs (#59, #65)
- BUG-E10: catch (e) syntax accepted alongside catch e (#62)
"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run(src: str, *, project_root=None) -> list[str]:
    vm = lang.VM([], {}, code_locs=[])
    loader = ModuleLoader(project_root=project_root, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader.load_module_from_source(src, module_name="<test>")
    return buf.getvalue().splitlines()


def run_in_tmp(src: str) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        return run(src, project_root=tmp)


# ---------------------------------------------------------------------------
# BUG-E01: json.parse type check returns err record, does not throw
# ---------------------------------------------------------------------------

class JsonParseTypeCheckTests(unittest.TestCase):
    def test_parse_int_returns_err_not_throw(self):
        src = 'import "std:json" as j\nlet r = j.parse(123)\nprint(type(r))'
        self.assertEqual(run(src), ["error"])

    def test_parse_int_kind_is_type_error(self):
        src = 'import "std:json" as j\nlet r = j.parse(123)\nprint(r.kind)'
        self.assertEqual(run(src), ["type_error"])

    def test_parse_list_returns_err(self):
        src = 'import "std:json" as j\nlet r = j.parse([1, 2])\nprint(r.kind)'
        self.assertEqual(run(src), ["type_error"])

    def test_parse_nil_returns_err(self):
        src = 'import "std:json" as j\nlet r = j.parse(nil)\nprint(r.kind)'
        self.assertEqual(run(src), ["type_error"])

    def test_parse_string_still_works(self):
        src = 'import "std:json" as j\nlet r = j.parse("{\\\"x\\\": 1}")\nprint(r["x"])'
        self.assertEqual(run(src), ["1.0"])


# ---------------------------------------------------------------------------
# BUG-E02: math.sqrt(-1) returns value_error, does not throw
# ---------------------------------------------------------------------------

class MathSqrtErrorTests(unittest.TestCase):
    def test_sqrt_negative_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.sqrt(-1)\nprint(type(r))'
        self.assertEqual(run(src), ["error"])

    def test_sqrt_negative_kind_is_value_error(self):
        src = 'import "std:math" as m\nlet r = m.sqrt(-1)\nprint(r.kind)'
        self.assertEqual(run(src), ["value_error"])

    def test_sqrt_positive_still_works(self):
        src = 'import "std:math" as m\nprint(m.sqrt(4.0))'
        self.assertEqual(run(src), ["2.0"])

    def test_sqrt_zero_works(self):
        src = 'import "std:math" as m\nprint(m.sqrt(0.0))'
        self.assertEqual(run(src), ["0.0"])


# ---------------------------------------------------------------------------
# BUG-E05: math.log and math.pow — implemented
# ---------------------------------------------------------------------------

class MathLogTests(unittest.TestCase):
    def test_log_positive_returns_float(self):
        src = 'import "std:math" as m\nprint(type(m.log(1.0)))'
        self.assertEqual(run(src), ["float"])

    def test_log_one_is_zero(self):
        src = 'import "std:math" as m\nprint(m.log(1.0))'
        self.assertEqual(run(src), ["0.0"])

    def test_log_zero_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.log(0.0)\nprint(r.kind)'
        self.assertEqual(run(src), ["value_error"])

    def test_log_negative_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.log(-5.0)\nprint(r.kind)'
        self.assertEqual(run(src), ["value_error"])

    def test_log_base_valid(self):
        # log_base renamed to log(n, base) in v3.0.2 (BUG-V31E-02 fix)
        src = 'import "std:math" as m\nprint(m.log(8.0, 2.0))'
        self.assertEqual(run(src), ["3.0"])

    def test_log_base_invalid_zero_base_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.log(1.0, 0.0)\nprint(r.kind)'
        self.assertEqual(run(src), ["value_error"])

    def test_log_base_one_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.log(1.0, 1.0)\nprint(r.kind)'
        self.assertEqual(run(src), ["value_error"])


class MathPowTests(unittest.TestCase):
    def test_pow_valid(self):
        src = 'import "std:math" as m\nprint(m.pow(2.0, 8.0))'
        self.assertEqual(run(src), ["256.0"])

    def test_pow_zero_exp(self):
        src = 'import "std:math" as m\nprint(m.pow(5.0, 0.0))'
        self.assertEqual(run(src), ["1.0"])

    def test_pow_negative_base_fractional_exp_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.pow(-1.0, 0.5)\nprint(r.kind)'
        self.assertEqual(run(src), ["math_error"])

    def test_pow_overflow_returns_err(self):
        src = 'import "std:math" as m\nlet r = m.pow(10.0, 10000.0)\nprint(r.kind)'
        self.assertEqual(run(src), ["math_error"])


# ---------------------------------------------------------------------------
# BUG-E06: path.relative and path.absolute
# ---------------------------------------------------------------------------

class PathRelativeTests(unittest.TestCase):
    def test_relative_same_dir(self):
        src = 'import "std:path" as p\nprint(p.relative("a/b/c", "a/b"))'
        self.assertEqual(run(src), ["c"])

    def test_relative_mixing_abs_and_rel_returns_err(self):
        src = 'import "std:path" as p\nlet r = p.relative("/abs/path", "rel/path")\nprint(r.kind)'
        self.assertEqual(run(src), ["path_error"])

    def test_absolute_returns_string(self):
        src = 'import "std:path" as p\nprint(type(p.absolute("some/path")))'
        self.assertEqual(run(src), ["string"])

    def test_absolute_makes_absolute(self):
        src = 'import "std:path" as p\nlet a = p.absolute("foo")\nprint(type(a))'
        self.assertEqual(run(src), ["string"])


# ---------------------------------------------------------------------------
# BUG-E07 / BUG-E13: fs.mkdir (strict) and fs.delete
# ---------------------------------------------------------------------------

def _nd(path: str) -> str:
    """Convert a Windows path to forward-slash form safe for Nodus string literals."""
    return path.replace("\\", "/")


class FsMkdirStrictTests(unittest.TestCase):
    def test_mkdir_creates_new_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = os.path.join(tmp, "newsubdir")
            src = f'import "std:fs" as fs\nlet r = fs.mkdir("{_nd(new_dir)}")\nprint(r)'
            result = run(src, project_root=tmp)
            self.assertEqual(result, ["nil"])
            self.assertTrue(os.path.isdir(new_dir))

    def test_mkdir_existing_returns_err(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = f'import "std:fs" as fs\nlet r = fs.mkdir("{_nd(tmp)}")\nprint(r.kind)'
            result = run(src, project_root=tmp)
            self.assertEqual(result, ["io_error"])

    def test_ensure_dir_still_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = f'import "std:fs" as fs\nfs.ensure_dir("{_nd(tmp)}")\nfs.ensure_dir("{_nd(tmp)}")\nprint("ok")'
            result = run(src, project_root=tmp)
            self.assertEqual(result, ["ok"])


class FsDeleteTests(unittest.TestCase):
    def test_delete_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "todelete.txt")
            with open(fpath, "w") as f:
                f.write("x")
            src = f'import "std:fs" as fs\nlet r = fs.delete("{_nd(fpath)}")\nprint(r)'
            result = run(src, project_root=tmp)
            self.assertEqual(result, ["nil"])
            self.assertFalse(os.path.exists(fpath))

    def test_delete_missing_file_returns_err(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "nosuchfile.txt")
            src = f'import "std:fs" as fs\nlet r = fs.delete("{_nd(fpath)}")\nprint(r.kind)'
            result = run(src, project_root=tmp)
            self.assertEqual(result, ["io_error"])

    def test_delete_directory_returns_err(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = f'import "std:fs" as fs\nlet r = fs.delete("{_nd(tmp)}")\nprint(r.kind)'
            result = run(src, project_root=tmp)
            self.assertEqual(result, ["io_error"])


# ---------------------------------------------------------------------------
# BUG-E10: catch (e) syntax
# ---------------------------------------------------------------------------

class CatchParenSyntaxTests(unittest.TestCase):
    def test_catch_with_parens_accepted(self):
        src = 'try { let x = 1 } catch (e) { print("caught") }\nprint("ok")'
        self.assertEqual(run(src), ["ok"])

    def test_catch_with_parens_binds_variable(self):
        src = 'try { throw "oops" } catch (e) { print(e) }'
        self.assertEqual(run(src), ["oops"])

    def test_catch_without_parens_still_works(self):
        src = 'try { throw "oops" } catch e { print(e) }'
        self.assertEqual(run(src), ["oops"])

    def test_catch_parens_with_finally(self):
        src = 'try { throw "x" } catch (e) { print(e) } finally { print("done") }'
        self.assertEqual(run(src), ["x", "done"])


if __name__ == "__main__":
    unittest.main()
