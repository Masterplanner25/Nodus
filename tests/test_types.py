import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import nodus as lang


def run_program(src: str, source_path: str | None = None) -> list[str]:
    _ast, code, functions, code_locs = lang.compile_source(src, source_path=source_path)
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return buf.getvalue().splitlines()


class TypeTests(unittest.TestCase):
    def test_assignment_mismatch_reports_error(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "bad.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write('let x: int = "hello"\n')
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = lang.main(["nodus", "check", script])
            self.assertEqual(exit_code, 1)
            self.assertIn("Type error", err.getvalue())
            self.assertIn("expected int but got string", err.getvalue())

    def test_function_return_mismatch_reports_error(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "bad_return.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write('fn add(a: int, b: int) -> int { return "hi" }\n')
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = lang.main(["nodus", "check", script])
            self.assertEqual(exit_code, 1)
            self.assertIn("expected int but got string", err.getvalue())

    def test_valid_typed_program_passes_and_runs(self):
        src = """
fn add(a: int, b: int) -> int {
    return a + b
}
print(add(1, 2))
"""
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "ok.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write(src)
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = lang.main(["nodus", "check", script])
            self.assertEqual(exit_code, 0)
            self.assertEqual(err.getvalue(), "")
        self.assertEqual(run_program(src, source_path="main.nd"), ["3.0"])


if __name__ == "__main__":
    unittest.main()
