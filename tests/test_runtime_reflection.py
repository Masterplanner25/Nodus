import unittest
import os

import nodus as lang
from nodus.vm.vm import Record


def run_vm(src: str, source_path: str | None = None) -> lang.VM:
    _ast, code, functions, code_locs = lang.compile_source(
        src,
        source_path=source_path,
        import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
    )
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    vm.run()
    return vm


def get_global(vm: lang.VM, name: str):
    if name in vm.globals:
        return vm.globals[name]
    qualified = [value for key, value in vm.globals.items() if key.endswith(f"__{name}")]
    if len(qualified) == 1:
        return qualified[0]
    raise KeyError(name)


class RuntimeReflectionTests(unittest.TestCase):
    def test_function_reflection(self):
        vm = run_vm(
            """
import "std:runtime" as runtime

fn add(a, b) {
    return a + b
}

let fn_name = runtime.fn_name(add)
let fn_arity = runtime.fn_arity(add)
let fn_module = runtime.fn_module(add)
""",
            source_path="main.nd",
        )
        self.assertEqual(get_global(vm, "fn_name"), "add")
        self.assertEqual(get_global(vm, "fn_arity"), 2.0)
        self.assertEqual(get_global(vm, "fn_module"), os.path.abspath("main.nd"))

    def test_record_reflection(self):
        vm = run_vm(
            """
import "std:runtime" as runtime

let user = record { name: "Alice", age: 30 }
let names = runtime.fields(user)
let has_name = runtime.has(user, "name")
let has_email = runtime.has(user, "email")
""",
            source_path="main.nd",
        )
        self.assertEqual(get_global(vm, "names"), ["name", "age"])
        self.assertIs(get_global(vm, "has_name"), True)
        self.assertIs(get_global(vm, "has_email"), False)

    def test_module_reflection(self):
        vm = run_vm(
            """
import "std:runtime" as runtime
import "std:math" as math

let fields = runtime.module_fields(math)
let has_sqrt = runtime.has(math, "sqrt")
let module_type = runtime.typeof(math)
""",
            source_path="main.nd",
        )
        self.assertIn("sqrt", get_global(vm, "fields"))
        self.assertIn("abs", get_global(vm, "fields"))
        self.assertIs(get_global(vm, "has_sqrt"), True)
        self.assertEqual(get_global(vm, "module_type"), "module")
        self.assertIsInstance(vm.globals["math"], Record)
        self.assertEqual(vm.globals["math"].kind, "module")

    def test_stack_reflection(self):
        vm = run_vm(
            """
import "std:runtime" as runtime

fn inner() {
    return runtime.stack_frame(0)
}

fn outer() {
    return inner()
}

let depth = runtime.stack_depth()
let frame = outer()
""",
            source_path="main.nd",
        )
        self.assertEqual(get_global(vm, "depth"), 0.0)
        frame = get_global(vm, "frame")
        self.assertIsInstance(frame, Record)
        self.assertEqual(frame.fields["name"], "inner")
        self.assertEqual(frame.fields["module"], os.path.abspath("main.nd"))
        self.assertEqual(frame.fields["path"], os.path.abspath("main.nd"))
        self.assertIsInstance(frame.fields["line"], float)
        self.assertIsInstance(frame.fields["column"], float)

    def test_typeof_reflection(self):
        vm = run_vm(
            """
import "std:runtime" as runtime

let int_type = runtime.typeof(10)
let float_type = runtime.typeof(2.5)
let string_type = runtime.typeof("hello")
let bool_type = runtime.typeof(true)
let list_type = runtime.typeof([1, 2])
let record_type = runtime.typeof(record { ok: true })
fn add(a, b) { return a + b }
let function_type = runtime.typeof(add)
let nil_type = runtime.typeof(nil)
""",
            source_path="main.nd",
        )
        self.assertEqual(get_global(vm, "int_type"), "int")
        self.assertEqual(get_global(vm, "float_type"), "float")
        self.assertEqual(get_global(vm, "string_type"), "string")
        self.assertEqual(get_global(vm, "bool_type"), "bool")
        self.assertEqual(get_global(vm, "list_type"), "list")
        self.assertEqual(get_global(vm, "record_type"), "record")
        self.assertEqual(get_global(vm, "function_type"), "function")
        self.assertEqual(get_global(vm, "nil_type"), "nil")


if __name__ == "__main__":
    unittest.main()
