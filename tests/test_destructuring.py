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


class DestructuringTests(unittest.TestCase):
    def test_list_destructuring(self):
        src = """
let [a, b] = [1, 2]
print(a)
print(b)
"""
        self.assertEqual(run_program(src), ["1.0", "2.0"])

    def test_record_destructuring(self):
        src = """
let user = record {
    name: "Bob",
    age: 30
}
let {name} = user
print(name)
"""
        self.assertEqual(run_program(src), ["Bob"])

    def test_nested_destructuring(self):
        src = """
let data = record {
    profile: record {
        name: "Sam"
    }
}
let {profile} = data
let {name} = profile
print(name)
"""
        self.assertEqual(run_program(src), ["Sam"])


if __name__ == "__main__":
    unittest.main()
