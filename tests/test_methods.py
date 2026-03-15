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


class MethodTests(unittest.TestCase):
    def test_basic_method(self):
        src = """
let user = record {
    name: "Alice",
    greet: fn(self) {
        return self.name
    }
}
print(user.greet())
"""
        self.assertEqual(run_program(src), ["Alice"])

    def test_method_mutation(self):
        src = """
let obj = record {}
obj.say = fn(self) {
    return 42
}
print(obj.say())
"""
        self.assertEqual(run_program(src), ["42.0"])

    def test_method_modifies_state(self):
        src = """
let counter = record {
    value: 0,
    inc: fn(self) {
        self.value = self.value + 1
    }
}
counter.inc()
counter.inc()
print(counter.value)
"""
        self.assertEqual(run_program(src), ["2.0"])

    def test_non_function_field(self):
        src = """
let user = record {
    age: 10
}
user.age()
"""
        with self.assertRaises(lang.LangRuntimeError):
            run_program(src, source_path="main.nd")


if __name__ == "__main__":
    unittest.main()
