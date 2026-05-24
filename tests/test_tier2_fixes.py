"""Tests for v2.1 Tier-2 fixes: run_source ok=False, json.parse maps, workflow print."""

import io
import os
import sys
import tempfile
import unittest

from nodus.tooling.runner import run_source, run_workflow_code
from nodus.vm.vm import VM


def _run(code, **kw):
    result, _ = run_source(code, max_steps=50_000, timeout_ms=5_000, **kw)
    return result


class RunSourceOkFalseTests(unittest.TestCase):
    """BUG-005: NodusRuntime.run_source must return ok=False, not raise."""

    def test_syntax_error_returns_ok_false(self):
        from nodus.runtime.embedding import NodusRuntime
        rt = NodusRuntime()
        result = rt.run_source("let x = ")
        self.assertIsInstance(result, dict)
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_runtime_error_returns_ok_false(self):
        from nodus.runtime.embedding import NodusRuntime
        rt = NodusRuntime()
        result = rt.run_source("let x = 1 / 0")
        self.assertIsInstance(result, dict)
        self.assertFalse(result["ok"])

    def test_success_returns_ok_true(self):
        from nodus.runtime.embedding import NodusRuntime
        rt = NodusRuntime()
        result = rt.run_source('let x = 42')
        self.assertIsInstance(result, dict)
        self.assertTrue(result["ok"])

    def test_stdout_captured_on_success(self):
        from nodus.runtime.embedding import NodusRuntime
        rt = NodusRuntime()
        result = rt.run_source('print("hello")')
        self.assertTrue(result["ok"])
        self.assertIn("hello", result["stdout"])

    def test_stdout_captured_on_runtime_error(self):
        from nodus.runtime.embedding import NodusRuntime
        rt = NodusRuntime()
        result = rt.run_source('print("before")\nlet x = 1/0')
        self.assertFalse(result["ok"])
        self.assertIn("before", result["stdout"])


class JsonParseMapsTests(unittest.TestCase):
    """BUG-018: json.parse must return maps (not records) so field access works."""

    def test_parse_object_field_access_by_index(self):
        r = _run('let d = json_parse("{\\"name\\": \\"nodus\\"}") \nprint(d["name"])')
        self.assertTrue(r["ok"], r)
        self.assertIn("nodus", r["stdout"])

    def test_parse_object_keys_function(self):
        r = _run('let d = json_parse("{\\"a\\": 1}")\nprint(keys(d)[0])')
        self.assertTrue(r["ok"], r)
        self.assertIn("a", r["stdout"])

    def test_parse_nested_object_field_access(self):
        r = _run('let d = json_parse("{\\"outer\\": {\\"inner\\": 42}}")\nprint(d["outer"]["inner"])')
        self.assertTrue(r["ok"], r)
        self.assertIn("42", r["stdout"])

    def test_parse_array_unchanged(self):
        r = _run('let a = json_parse("[1, 2, 3]")\nprint(a[1])')
        self.assertTrue(r["ok"], r)
        self.assertIn("2", r["stdout"])

    def test_parse_object_values_function(self):
        r = _run('let d = json_parse("{\\"x\\": 99}")\nprint(values(d)[0])')
        self.assertTrue(r["ok"], r)
        self.assertIn("99", r["stdout"])


class WorkflowPrintTests(unittest.TestCase):
    """BUG-022: print() inside workflow steps must appear in result stdout."""

    def _workflow_source(self, body: str) -> str:
        return f"""
workflow demo {{
  step greet {{
    {body}
    return "done"
  }}
}}
run_workflow(demo)
"""

    def test_print_in_step_captured_by_run_source(self):
        r = _run(self._workflow_source('print("hello from step")'))
        self.assertTrue(r["ok"], r)
        self.assertIn("hello from step", r["stdout"])

    def test_print_in_step_captured_by_run_workflow_code(self):
        code = self._workflow_source('print("step output")')
        vm = VM([], {}, code_locs=[], source_path=None)
        result, _ = run_workflow_code(vm, code, max_steps=50_000, timeout_ms=5_000)
        self.assertTrue(result["ok"], result)
        self.assertIn("step output", result["stdout"])

    def test_workflow_cli_prints_stdout(self):
        from nodus.cli.cli import main
        code = 'workflow demo {\n  step s {\n    print("cli step output")\n    return "ok"\n  }\n}\nrun_workflow(demo)\n'
        with tempfile.NamedTemporaryFile(suffix=".nd", mode="w", delete=False, encoding="utf-8") as f:
            f.write(code)
            path = f.name
        try:
            buf = io.StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                code_exit = main(["nodus", "workflow", "run", path])
            finally:
                sys.stdout = old
            self.assertEqual(code_exit, 0)
            self.assertIn("cli step output", buf.getvalue())
        finally:
            os.unlink(path)

    def test_multiple_prints_in_step(self):
        r = _run(self._workflow_source('print("line1")\nprint("line2")'))
        self.assertTrue(r["ok"], r)
        self.assertIn("line1", r["stdout"])
        self.assertIn("line2", r["stdout"])


if __name__ == "__main__":
    unittest.main()
