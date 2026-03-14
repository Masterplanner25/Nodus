import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import nodus as lang
from cli import debug_file
from nodus.tooling.debugger import Debugger


def make_input(commands: list[str]):
    queued = list(commands)

    def fake_input(_prompt: str) -> str:
        if not queued:
            raise AssertionError("Debugger requested more commands than expected")
        return queued.pop(0)

    return fake_input


class DebuggerTests(unittest.TestCase):
    def test_breakpoint_pauses_on_line(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "main.nd")
            with open(path, "w", encoding="utf-8") as f:
                f.write("let x = 1\nx = x + 1\nprint(x)\n")

            output: list[str] = []
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = debug_file(
                    path,
                    debugger_input=make_input([f"break {path}:2", "run", "continue"]),
                    debugger_output=output.append,
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(any("Breakpoint set at" in line for line in output))
            self.assertTrue(any("paused (breakpoint)" in line for line in output))
            self.assertEqual(stdout.getvalue().splitlines(), ["2.0"])

    def test_stack_inspection_shows_nested_calls(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "stack.nd")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "fn foo() {\n"
                    "    bar()\n"
                    "}\n"
                    "fn bar() {\n"
                    "    let x = 1\n"
                    "    print(x)\n"
                    "}\n"
                    "foo()\n"
                )

            output: list[str] = []
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = debug_file(
                    path,
                    debugger_input=make_input([f"break {path}:5", "run", "stack", "continue"]),
                    debugger_output=output.append,
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(any("main()" in line for line in output))
            self.assertTrue(any("foo()" in line for line in output))
            self.assertTrue(any("bar()" in line for line in output))
            self.assertEqual(stdout.getvalue().splitlines(), ["1.0"])

    def test_variable_inspection_displays_locals(self):
        src = (
            "fn foo(a) {\n"
            "    let x = a + 1\n"
            "    print(x)\n"
            "}\n"
            "foo(4)\n"
        )
        _ast, code, functions, code_locs = lang.compile_source(src, source_path="main.nd")
        output: list[str] = []
        debugger = Debugger(
            input_fn=make_input(["break main.nd:3", "run", "locals", "print a", "continue"]),
            output_fn=output.append,
            start_paused=True,
        )
        vm = lang.VM(code, functions, code_locs=code_locs, source_path="main.nd", debug=True, debugger=debugger)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            vm.run()

        self.assertTrue(any('a = 4.0' in line for line in output))
        self.assertTrue(any('x = 5.0' in line for line in output))
        self.assertTrue(any('4.0' == line for line in output))
        self.assertEqual(stdout.getvalue().splitlines(), ["5.0"])

    def test_step_execution_pauses_after_instruction(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "step.nd")
            with open(path, "w", encoding="utf-8") as f:
                f.write("let x = 1\nx = x + 1\nprint(x)\n")

            output: list[str] = []
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = debug_file(
                    path,
                    debugger_input=make_input(["step", "continue"]),
                    debugger_output=output.append,
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(any("paused (step)" in line for line in output))
            self.assertEqual(stdout.getvalue().splitlines(), ["2.0"])


if __name__ == "__main__":
    unittest.main()
