"""Tests for v3.0 Python error replacement (BUG-038 / BUG-045).

Covers:
- fs.* functions return io_error err records instead of leaking Python text
- json.parse returns parse_error err record with Nodus-voice message
- json.stringify returns type_error for non-serializable values
- --trace-errors / NODUS_TRACE_ERRORS=1 sends Python details to stderr
"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.runner import run_source
from nodus.vm.vm import VM


def run_program(src: str, *, trace_errors: bool = False) -> list[str]:
    vm = lang.VM([], {}, code_locs=[])
    vm.trace_errors = trace_errors
    loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader.load_module_from_source(src, module_name="<test>")
    return buf.getvalue().splitlines()


def run_program_stderr(src: str, *, trace_errors: bool = False):
    """Run program and return (stdout_lines, stderr_text)."""
    vm = lang.VM([], {}, code_locs=[])
    vm.trace_errors = trace_errors
    loader = ModuleLoader(project_root=None, vm=vm)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        loader.load_module_from_source(src, module_name="<test>")
    return out_buf.getvalue().splitlines(), err_buf.getvalue()


class JsonParseErrorTests(unittest.TestCase):
    """json.parse returns parse_error err records with Nodus-voice messages."""

    def test_bad_json_returns_err_record(self):
        src = 'import "std:json" as j\nlet r = j.parse("{bad")\nprint(type(r))'
        self.assertEqual(run_program(src), ["error"])

    def test_bad_json_kind_is_parse_error(self):
        src = 'import "std:json" as j\nlet r = j.parse("{bad")\nprint(r.kind)'
        self.assertEqual(run_program(src), ["parse_error"])

    def test_bad_json_message_no_python_text(self):
        src = 'import "std:json" as j\nlet r = j.parse("{bad")\nprint(r.message)'
        out = run_program(src)
        self.assertFalse(any("JSONDecodeError" in line for line in out))
        self.assertFalse(any("json module" in line for line in out))

    def test_bad_json_message_is_nodus_voice(self):
        src = 'import "std:json" as j\nlet r = j.parse("{bad")\nprint(r.message)'
        out = run_program(src)
        self.assertTrue(out[0].startswith("invalid JSON at line"))

    def test_bad_json_message_includes_line_col(self):
        src = 'import "std:json" as j\nlet r = j.parse("{bad")\nprint(r.message)'
        out = run_program(src)
        self.assertIn("line 1", out[0])
        self.assertIn("column", out[0])

    def test_expecting_property_name_reason(self):
        src = 'import "std:json" as j\nlet r = j.parse("{1: 2}")\nprint(r.message)'
        out = run_program(src)
        self.assertIn("expected property name", out[0])

    def test_expecting_value_reason(self):
        src = r'import "std:json" as j' + "\n" + r'let r = j.parse("[,]")' + "\n" + r'print(r.message)'
        out = run_program(src)
        self.assertIn("invalid JSON", out[0])

    def test_valid_json_still_works(self):
        src = 'import "std:json" as j\nlet r = j.parse("[1, 2, 3]")\nprint(r[1])'
        self.assertEqual(run_program(src), ["2.0"])

    def test_json_parse_does_not_throw(self):
        """Bad json.parse returns an err record, not a thrown error."""
        src = 'import "std:json" as j\nlet r = j.parse("{bad")\nprint("ok")'
        self.assertEqual(run_program(src), ["ok"])


class JsonStringifyErrorTests(unittest.TestCase):
    """json.stringify returns type_error for non-serializable values."""

    def test_stringify_closure_returns_err(self):
        src = 'import "std:json" as j\nfn f() { return 1 }\nlet r = j.stringify(f)\nprint(type(r))'
        self.assertEqual(run_program(src), ["error"])

    def test_stringify_closure_kind_is_type_error(self):
        src = 'import "std:json" as j\nfn f() { return 1 }\nlet r = j.stringify(f)\nprint(r.kind)'
        self.assertEqual(run_program(src), ["type_error"])

    def test_stringify_closure_message_no_python_text(self):
        src = 'import "std:json" as j\nfn f() { return 1 }\nlet r = j.stringify(f)\nprint(r.message)'
        out = run_program(src)
        self.assertFalse(any("TypeError" in line for line in out))
        self.assertFalse(any("json module" in line for line in out))

    def test_stringify_closure_nodus_voice_message(self):
        src = 'import "std:json" as j\nfn f() { return 1 }\nlet r = j.stringify(f)\nprint(r.message)'
        out = run_program(src)
        self.assertIn("cannot serialize to JSON", out[0])

    def test_stringify_valid_value_still_works(self):
        src = 'import "std:json" as j\nprint(j.stringify([1, 2, 3]))'
        self.assertEqual(run_program(src), ['[1, 2, 3]'])


class FsReadErrorTests(unittest.TestCase):
    """fs.read returns io_error err records for file system failures."""

    def test_missing_file_returns_err_record(self):
        src = 'import "std:fs" as fs\nlet r = fs.read("/nonexistent/path/file.txt")\nprint(type(r))'
        self.assertEqual(run_program(src), ["error"])

    def test_missing_file_kind_is_io_error(self):
        src = 'import "std:fs" as fs\nlet r = fs.read("/nonexistent/path/file.txt")\nprint(r.kind)'
        self.assertEqual(run_program(src), ["io_error"])

    def test_missing_file_message_is_nodus_voice(self):
        src = 'import "std:fs" as fs\nlet r = fs.read("/nonexistent/path/file.txt")\nprint(r.message)'
        out = run_program(src)
        self.assertTrue(out[0].startswith('file not found: "'))

    def test_missing_file_message_no_python_text(self):
        src = 'import "std:fs" as fs\nlet r = fs.read("/nonexistent/path/file.txt")\nprint(r.message)'
        out = run_program(src)
        self.assertFalse(any("Errno" in line for line in out))
        self.assertFalse(any("No such file" in line for line in out))

    def test_missing_file_does_not_throw(self):
        """fs.read for missing file returns err record, script continues."""
        src = 'import "std:fs" as fs\nlet r = fs.read("/nonexistent/path/file.txt")\nprint("ok")'
        self.assertEqual(run_program(src), ["ok"])

    def test_directory_as_file_returns_err(self):
        with tempfile.TemporaryDirectory() as td:
            td_fwd = td.replace("\\", "/")
            src = f'import "std:fs" as fs\nlet r = fs.read("{td_fwd}")\nprint(r.kind)'
            self.assertEqual(run_program(src), ["io_error"])

    def test_directory_as_file_message(self):
        with tempfile.TemporaryDirectory() as td:
            td_fwd = td.replace("\\", "/")
            src = f'import "std:fs" as fs\nlet r = fs.read("{td_fwd}")\nprint(r.message)'
            out = run_program(src)
            self.assertIn("expected a file, got a directory", out[0])


class FsListDirErrorTests(unittest.TestCase):
    """fs.listdir returns io_error err records for directory failures."""

    def test_missing_dir_returns_err(self):
        src = 'import "std:fs" as fs\nlet r = fs.listdir("/nonexistent/dir/path")\nprint(r.kind)'
        self.assertEqual(run_program(src), ["io_error"])

    def test_missing_dir_message(self):
        src = 'import "std:fs" as fs\nlet r = fs.listdir("/nonexistent/dir/path")\nprint(r.message)'
        out = run_program(src)
        self.assertIn("directory not found", out[0])

    def test_file_as_dir_returns_err(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"content")
            path = f.name.replace("\\", "/")
        try:
            src = f'import "std:fs" as fs\nlet r = fs.listdir("{path}")\nprint(r.kind)'
            self.assertEqual(run_program(src), ["io_error"])
            src2 = f'import "std:fs" as fs\nlet r = fs.listdir("{path}")\nprint(r.message)'
            out = run_program(src2)
            self.assertIn("expected a directory, got a file", out[0])
        finally:
            os.unlink(path.replace("/", os.sep))

    def test_missing_dir_no_python_text(self):
        src = 'import "std:fs" as fs\nlet r = fs.listdir("/nonexistent/dir/path")\nprint(r.message)'
        out = run_program(src)
        self.assertFalse(any("Errno" in line for line in out))
        self.assertFalse(any("No such file" in line for line in out))


class FsWriteErrorTests(unittest.TestCase):
    """fs.write returns io_error when parent directory is missing."""

    def test_missing_parent_returns_err(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "nonexistent", "file.txt").replace("\\", "/")
            src = f'import "std:fs" as fs\nlet r = fs.write("{path}", "content")\nprint(type(r))'
            self.assertEqual(run_program(src), ["error"])

    def test_missing_parent_kind_is_io_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "nonexistent", "file.txt").replace("\\", "/")
            src = f'import "std:fs" as fs\nlet r = fs.write("{path}", "content")\nprint(r.kind)'
            self.assertEqual(run_program(src), ["io_error"])

    def test_missing_parent_message(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "nonexistent", "file.txt").replace("\\", "/")
            src = f'import "std:fs" as fs\nlet r = fs.write("{path}", "content")\nprint(r.message)'
            out = run_program(src)
            self.assertIn("cannot write file, parent directory does not exist", out[0])


class TraceErrorsTests(unittest.TestCase):
    """--trace-errors sends Python diagnostic details to stderr."""

    def test_trace_errors_sends_to_stderr(self):
        src = 'import "std:fs" as fs\nfs.read("/nonexistent/trace_test_path.txt")'
        _, stderr = run_program_stderr(src, trace_errors=True)
        self.assertIn("[trace-errors]", stderr)

    def test_trace_errors_stderr_contains_python_exception_name(self):
        src = 'import "std:fs" as fs\nfs.read("/nonexistent/trace_test_path.txt")'
        _, stderr = run_program_stderr(src, trace_errors=True)
        self.assertIn("FileNotFoundError", stderr)

    def test_no_trace_errors_no_stderr(self):
        src = 'import "std:fs" as fs\nfs.read("/nonexistent/trace_test_path.txt")'
        _, stderr = run_program_stderr(src, trace_errors=False)
        self.assertNotIn("[trace-errors]", stderr)

    def test_trace_errors_stdout_unchanged(self):
        """Script stdout behavior is identical with or without trace_errors."""
        src = 'import "std:fs" as fs\nlet r = fs.read("/nonexistent/trace_test_path.txt")\nprint(r.kind)'
        out_normal = run_program(src, trace_errors=False)
        out_traced, _ = run_program_stderr(src, trace_errors=True)
        self.assertEqual(out_normal, out_traced)

    def test_trace_errors_via_cli_run_file(self):
        """run_file(trace_errors=True) propagates trace-errors through run_source."""
        from nodus.cli.cli import run_file
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "t.nd")
            data_path = os.path.join(td, "nonexistent_sub", "file.txt").replace("\\", "/")
            with open(script_path, "w") as f:
                f.write(f'import "std:fs" as fs\nfs.read("{data_path}")')
            err_buf = io.StringIO()
            with redirect_stderr(err_buf):
                run_file(
                    script_path,
                    trace_errors=True,
                    allowed_paths=[td],
                )
            stderr = err_buf.getvalue()
            self.assertIn("[trace-errors]", stderr)


class JsonParseIntV3Tests(unittest.TestCase):
    """json.parse_int error messages match v3.0 voice."""

    def test_scientific_notation_message(self):
        src = 'import "std:json" as j\nlet r = j.parse_int("1e9")\nprint(r.message)'
        self.assertEqual(run_program(src), ['not an integer (scientific notation): "1e9"'])

    def test_invalid_string_message(self):
        src = 'import "std:json" as j\nlet r = j.parse_int("abc")\nprint(r.message)'
        self.assertEqual(run_program(src), ['not a valid integer: "abc"'])


if __name__ == "__main__":
    unittest.main()
