import io
import unittest
from contextlib import redirect_stdout

import nodus as lang


def run_program(src: str, source_path: str | None = None) -> list[str]:
    _ast, code, functions, code_locs = lang.compile_source(
        src,
        source_path=source_path,
        import_state={"loaded": set(), "loading": set(), "exports": {}},
    )
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return buf.getvalue().splitlines()


class ExceptionTests(unittest.TestCase):
    def test_try_catch_runtime_error(self):
        src = """
try {
    let x = "a" - 1
} catch err {
    print("error caught")
}
"""
        self.assertEqual(run_program(src), ["error caught"])

    def test_throw_statement(self):
        src = """
try {
    throw "bad"
} catch err {
    print(err)
}
"""
        self.assertEqual(run_program(src), ["bad"])

    def test_uncaught_throw(self):
        with self.assertRaises(lang.LangRuntimeError) as cm:
            run_program('throw "boom"\n', source_path="main.nd")
        self.assertEqual(cm.exception.kind, "runtime")
        self.assertIn("boom", str(cm.exception))

    def test_nested_try_blocks(self):
        src = """
try {
    try {
        throw "inner"
    } catch e {
        print("inner")
    }
} catch e {
    print("outer")
}
"""
        self.assertEqual(run_program(src), ["inner"])


if __name__ == "__main__":
    unittest.main()
