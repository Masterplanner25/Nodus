"""Tests for v3.0 Batch 2C fixes: BUG-047/048/029/025 and issues #51/#31."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader
from nodus.runtime.diagnostics import format_error


def run_program(src: str) -> list[str]:
    vm = lang.VM([], {}, code_locs=[])
    loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader.load_module_from_source(src, module_name="<test>")
    return buf.getvalue().splitlines()


def run_program_error(src: str):
    """Run program that is expected to raise; return the exception."""
    vm = lang.VM([], {}, code_locs=[])
    loader = ModuleLoader(project_root=None, vm=vm)
    try:
        loader.load_module_from_source(src, module_name="<test>")
    except Exception as e:
        return e
    raise AssertionError("Expected an exception but none was raised")


class ElseIfTests(unittest.TestCase):
    """BUG-029: else if is now valid syntax (sugar for else { if ... })."""

    def test_else_if_basic(self):
        src = """
let score = 72
if (score >= 90) {
    print("A")
} else if (score >= 70) {
    print("B")
} else {
    print("C")
}
"""
        self.assertEqual(run_program(src), ["B"])

    def test_else_if_first_branch(self):
        src = """
let x = 100
if (x >= 90) {
    print("high")
} else if (x >= 50) {
    print("mid")
} else {
    print("low")
}
"""
        self.assertEqual(run_program(src), ["high"])

    def test_else_if_last_branch(self):
        src = """
let x = 10
if (x >= 90) {
    print("high")
} else if (x >= 50) {
    print("mid")
} else {
    print("low")
}
"""
        self.assertEqual(run_program(src), ["low"])

    def test_chained_else_if(self):
        src = """
let n = 2
if (n == 1) {
    print("one")
} else if (n == 2) {
    print("two")
} else if (n == 3) {
    print("three")
} else {
    print("other")
}
"""
        self.assertEqual(run_program(src), ["two"])

    def test_else_if_no_trailing_else(self):
        src = """
let x = 5
if (x > 10) {
    print("big")
} else if (x > 0) {
    print("small")
}
"""
        self.assertEqual(run_program(src), ["small"])

    def test_nested_else_if_unchanged(self):
        """Regression: old nested if-else style still works."""
        src = """
let x = 7
if (x > 10) {
    print("big")
} else {
    if (x > 0) {
        print("small")
    } else {
        print("none")
    }
}
"""
        self.assertEqual(run_program(src), ["small"])


class StackTraceCapTests(unittest.TestCase):
    """BUG-048: stack overflow trace must be capped at 20 frames."""

    def _make_deep_stack(self, depth: int) -> list[str]:
        return ["at recurse (script.nd:2:24)"] * depth + ["at <module> (script.nd:5:1)"]

    def test_format_error_caps_at_20_frames(self):
        from nodus.runtime.diagnostics import LangRuntimeError
        err = LangRuntimeError("sandbox", "Call stack overflow")
        err.stack = self._make_deep_stack(500)
        formatted = format_error(err)
        lines = formatted.splitlines()
        stack_lines = [ln for ln in lines if ln.strip().startswith("at ") or "more frames" in ln]
        self.assertLessEqual(len(stack_lines), 21)  # 20 + summary line

    def test_format_error_shows_elided_count(self):
        from nodus.runtime.diagnostics import LangRuntimeError
        err = LangRuntimeError("sandbox", "Call stack overflow")
        err.stack = self._make_deep_stack(50)
        formatted = format_error(err)
        self.assertIn("more frames", formatted)
        total = 51  # 50 recurse + 1 module
        elided = total - 20
        self.assertIn(str(elided), formatted)

    def test_short_stack_not_truncated(self):
        from nodus.runtime.diagnostics import LangRuntimeError
        err = LangRuntimeError("runtime", "some error")
        err.stack = ["at foo (x.nd:1:1)", "at bar (x.nd:2:1)"]
        formatted = format_error(err)
        self.assertIn("at foo", formatted)
        self.assertIn("at bar", formatted)
        self.assertNotIn("more frames", formatted)


class TraceImportsCacheHitTests(unittest.TestCase):
    """#51: --trace-imports must emit cache-hit messages for repeated imports."""

    def test_trace_emits_cache_hit_for_repeat_import(self):
        src = """
import "std:strings" as s1
import "std:strings" as s2
"""
        trace_msgs = []
        vm = lang.VM([], {}, code_locs=[])
        loader = ModuleLoader(project_root=None, vm=vm, import_trace_fn=trace_msgs.append)
        loader.load_module_from_source(src, module_name="<test>")
        cache_hit_msgs = [m for m in trace_msgs if "Cache hit" in m]
        self.assertTrue(len(cache_hit_msgs) >= 1, f"Expected cache-hit message, got: {trace_msgs}")

    def test_trace_still_emits_resolve_on_first_load(self):
        src = 'import "std:strings" as s'
        trace_msgs = []
        vm = lang.VM([], {}, code_locs=[])
        loader = ModuleLoader(project_root=None, vm=vm, import_trace_fn=trace_msgs.append)
        loader.load_module_from_source(src, module_name="<test>")
        resolve_msgs = [m for m in trace_msgs if "Resolved" in m]
        self.assertTrue(len(resolve_msgs) >= 1, f"Expected Resolved message, got: {trace_msgs}")


class FmtCheckLineEndingTests(unittest.TestCase):
    """BUG-025: fmt --check must not false-negative on CRLF/LF line endings."""

    def test_crlf_file_passes_check(self):
        from nodus.cli.cli import main
        src = "let x = 1 + 2\r\nprint(x)\r\n"
        with tempfile.NamedTemporaryFile(suffix=".nd", mode="wb", delete=False) as f:
            f.write(src.encode("utf-8"))
            path = f.name
        try:
            exit_code = main(["nodus", "fmt", "--check", path])
            self.assertEqual(exit_code, 0, "fmt --check should pass for CRLF file with correct content")
        finally:
            os.unlink(path)

    def test_lf_file_passes_check(self):
        from nodus.cli.cli import main
        src = "let x = 1 + 2\nprint(x)\n"
        with tempfile.NamedTemporaryFile(suffix=".nd", mode="wb", delete=False) as f:
            f.write(src.encode("utf-8"))
            path = f.name
        try:
            exit_code = main(["nodus", "fmt", "--check", path])
            self.assertEqual(exit_code, 0, "fmt --check should pass for LF file with correct content")
        finally:
            os.unlink(path)

    def test_actually_unformatted_file_still_fails(self):
        from nodus.cli.cli import main
        src = "let x=1+2\nprint(x)\n"
        with tempfile.NamedTemporaryFile(suffix=".nd", mode="wb", delete=False) as f:
            f.write(src.encode("utf-8"))
            path = f.name
        try:
            exit_code = main(["nodus", "fmt", "--check", path])
            self.assertEqual(exit_code, 1, "fmt --check must fail for genuinely unformatted file")
        finally:
            os.unlink(path)


class DebugHelpTests(unittest.TestCase):
    """BUG-047: nodus debug --help must print help text, not 'File not found'."""

    def test_debug_help_flag_exits_zero(self):
        from nodus.cli.cli import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = main(["nodus", "debug", "--help"])
        self.assertEqual(exit_code, 0)
        output = buf.getvalue()
        self.assertIn("Usage: nodus debug", output)
        self.assertNotIn("File not found", output)

    def test_debug_h_flag_exits_zero(self):
        from nodus.cli.cli import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = main(["nodus", "debug", "-h"])
        self.assertEqual(exit_code, 0)
        self.assertNotIn("File not found", buf.getvalue())
