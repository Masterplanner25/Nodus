import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.compiler.compiler import format_bytecode


def run_program(src: str, optimize: bool = True, source_path: str | None = None) -> list[str]:
    _ast, code, functions, code_locs = lang.compile_source(src, source_path=source_path, optimize=optimize)
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return buf.getvalue().splitlines()


class OptimizerTests(unittest.TestCase):
    def test_constant_folding_rewrites_addition(self):
        src = """
let x = 2 + 3
print(x)
"""
        _ast, code, functions, code_locs = lang.compile_source(src, source_path="main.nd")
        text = format_bytecode(code, code_locs, functions)
        self.assertIn("PUSH_CONST 5.0", text)
        self.assertNotIn("ADD", text)

    def test_dead_code_removed_after_return(self):
        src = """
fn test() {
    return 1
    print("dead")
}
print(test())
"""
        _ast, code, functions, code_locs = lang.compile_source(src, source_path="main.nd")
        text = format_bytecode(code, code_locs, functions)
        lines = text.splitlines()
        start = lines.index("Function test:")
        end = lines.index("Function main:")
        fn_text = "\n".join(lines[start:end])
        self.assertNotIn("dead", fn_text)
        self.assertNotIn("CALL print 1", fn_text)

    def test_optimizer_preserves_semantics(self):
        src = """
fn test() {
    let x = 2 + 3
    return x
    print("dead")
}
print(test())
"""
        self.assertEqual(
            run_program(src, optimize=True, source_path="main.nd"),
            run_program(src, optimize=False, source_path="main.nd"),
        )

    def test_cli_no_opt_preserves_unoptimized_bytecode(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "main.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write('let x = 2 + 3\nprint(x)\n')
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "run", "--no-opt", script, "--dump-bytecode"])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("ADD", output)


if __name__ == "__main__":
    unittest.main()
