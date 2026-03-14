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


class ClosureTests(unittest.TestCase):
    def test_basic_closure(self):
        src = """
fn outer() {
    let x = 10
    fn inner() {
        return x
    }
    return inner
}
let f = outer()
print(f())
"""
        self.assertEqual(run_program(src), ["10.0"])

    def test_closure_mutation(self):
        src = """
fn counter() {
    let x = 0
    fn inc() {
        x = x + 1
        return x
    }
    return inc
}
let c = counter()
print(c())
print(c())
"""
        self.assertEqual(run_program(src), ["1.0", "2.0"])

    def test_nested_closure(self):
        src = """
fn a() {
    let x = 1
    fn b() {
        fn c() {
            return x
        }
        return c
    }
    return b()
}
print(a()())
"""
        self.assertEqual(run_program(src), ["1.0"])


if __name__ == "__main__":
    unittest.main()
