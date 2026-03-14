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


class RecordTests(unittest.TestCase):
    def test_basic_record(self):
        src = """
let user = record {
    name: "Alice",
    age: 25
}
print(user.name)
"""
        self.assertEqual(run_program(src), ["Alice"])

    def test_field_mutation(self):
        src = """
let user = record {
    age: 20
}
user.age = 21
print(user.age)
"""
        self.assertEqual(run_program(src), ["21.0"])

    def test_nested_records(self):
        src = """
let user = record {
    profile: record {
        name: "Bob"
    }
}
print(user.profile.name)
"""
        self.assertEqual(run_program(src), ["Bob"])

    def test_missing_field(self):
        src = """
let user = record {}
print(user.name)
"""
        with self.assertRaises(lang.LangRuntimeError):
            run_program(src, source_path="main.nd")


if __name__ == "__main__":
    unittest.main()
