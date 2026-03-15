import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None) -> list[str]:
    _loader = ModuleLoader(project_root=None)
    code, functions, code_locs = _loader.compile_only(
        src,
        module_name=source_path or "<memory>",
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

    def test_catch_exposes_error_fields(self):
        src = """
try {
    let x = "a" - 1
} catch err {
    print(err.kind)
    print(err.message)
}
"""
        out = run_program(src)
        self.assertEqual(out[0], "type")
        self.assertIn("Cannot subtract", out[1])

    def test_throw_record_preserves_structure(self):
        src = """
try {
    throw record { code: 404, msg: "not found" }
} catch err {
    print(err.kind)
    print(err.payload.code)
}
"""
        out = run_program(src)
        self.assertEqual(out[0], "thrown")
        self.assertEqual(out[1], "404.0")

    def test_throw_string_still_works(self):
        src = """
try {
    throw "bad input"
} catch err {
    print(err.kind)
    print(err.message)
}
"""
        out = run_program(src)
        self.assertEqual(out[0], "runtime")
        self.assertEqual(out[1], "bad input")

    def test_throw_number(self):
        src = """
try {
    throw 42
} catch err {
    print(err.message)
}
"""
        out = run_program(src)
        self.assertEqual(out[0], "42.0")

    def test_anonymous_function_names_unique(self):
        code = """
fn a() {
    let f = fn() { return 1 }
}

fn b() {
    let f = fn() { return 2 }
}
"""
        _loader = ModuleLoader(project_root=None)
        bytecode, functions, _code_locs = _loader.compile_only(code, module_name="main.nd")
        display_names = sorted(
            info.display_name for info in functions.values() if info.display_name and info.display_name.startswith("__anon_")
        )
        self.assertGreaterEqual(len(display_names), 2)
        self.assertEqual(len(display_names), len(set(display_names)))


if __name__ == "__main__":
    unittest.main()
