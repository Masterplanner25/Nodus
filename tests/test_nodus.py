import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from nodus.tooling.formatter import format_source
import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, input_values: list[str] | None = None, source_path: str | None = None) -> list[str]:
    queued = list(input_values or [])

    def fake_input(prompt: str) -> str:
        if not queued:
            raise RuntimeError(f"No fake input available for prompt: {prompt!r}")
        return queued.pop(0)

    module_name = source_path or "<memory>"
    base_dir = os.path.dirname(os.path.abspath(source_path)) if source_path else None
    vm = lang.VM([], {}, code_locs=[], input_fn=fake_input, source_path=source_path)
    _loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _loader.load_module_from_source(src, module_name=module_name, base_dir=base_dir)
    return buf.getvalue().splitlines()


class LanguageFeatureTests(unittest.TestCase):
    def test_logical_operators_and_short_circuit(self):
        src = """
fn boom() {
    print(999)
    return true
}
print(false && boom())
print(true || boom())
print(!false)
"""
        self.assertEqual(run_program(src), ["false", "true", "true"])

    def test_unary_minus_runtime_behavior(self):
        src = """
let x = -5
let y = -(x + 1)
print(x)
print(y)
print(-(-3))
"""
        self.assertEqual(run_program(src), ["-5.0", "4.0", "3.0"])

    def test_strings_literals_escapes_and_concat(self):
        src = """
let a = "hello"
let b = "world"
print(a + " " + b)
print("quote: \\\"ok\\\"")
print("line1\\nline2")
"""
        self.assertEqual(
            run_program(src),
            [
                "hello world",
                "quote: \"ok\"",
                "line1",
                "line2",
            ],
        )

    def test_nil_truthiness_and_default_return(self):
        src = """
fn f() {
    let x = 1
}
print(nil)
print(nil == nil)
if (nil) {
    print(1)
} else {
    print(2)
}
print(f() == nil)
"""
        self.assertEqual(run_program(src), ["nil", "true", "2.0", "true"])

    def test_builtins_clock_type_str_and_user_override(self):
        src = """
print(type(clock()))
print(str(nil))
print(str(true))
"""
        self.assertEqual(run_program(src), ["number", "nil", "true"])

    def test_user_defined_function_can_override_builtin(self):
        src = """
fn str(x) {
    return "user"
}
print(str(nil))
print(str(true))
print(str(123))
"""
        self.assertEqual(run_program(src), ["user", "user", "user"])

    def test_lists_literals_indexing_and_print(self):
        src = """
let nums = [1, 2, 3]
print(nums[0])
print(nums[1] + nums[2])
print([1, "x", nil, true])
"""
        self.assertEqual(run_program(src), ["1.0", "5.0", "[1.0, \"x\", nil, true]"])

    def test_list_index_errors(self):
        src = """
let nums = [10, 20]
print(nums[1.5])
"""
        with self.assertRaises(lang.LangRuntimeError):
            run_program(src)

    def test_comments_hash_and_double_slash(self):
        src = """
# full line comment
let x = 1 // trailing comment
let y = 2 # trailing hash comment
print(x + y)
"""
        self.assertEqual(run_program(src), ["3.0"])

    def test_list_assignment(self):
        src = """
let nums = [10, 20, 30]
nums[1] = 99
print(nums[1])
print(nums)
"""
        self.assertEqual(run_program(src), ["99.0", "[10.0, 99.0, 30.0]"])

    def test_list_assignment_bounds_and_type_checks(self):
        with self.assertRaises(lang.LangRuntimeError):
            run_program("let nums = [1]\nnums[2] = 5")
        with self.assertRaises(lang.LangRuntimeError):
            run_program("let nums = [1]\nnums[\"x\"] = 5")

    def test_map_literals_indexing_and_print(self):
        src = """
let user = {"name": "alice", "age": 30}
print(user["name"])
print(user["age"])
print(user)
"""
        self.assertEqual(run_program(src), ["alice", "30.0", "{\"name\": \"alice\", \"age\": 30.0}"])

    def test_map_assignment(self):
        src = """
let user = {"name": "alice"}
user["name"] = "bob"
user["age"] = 33
print(user["name"])
print(user["age"])
"""
        self.assertEqual(run_program(src), ["bob", "33.0"])

    def test_map_key_type_restriction(self):
        with self.assertRaises(lang.LangRuntimeError):
            run_program("let bad = {true: 1}")

    def test_new_builtins_len_keys_values_input_and_print(self):
        src = """
let m = {"a": 1, "b": 2}
print(len(m))
print(keys(m))
print(values(m))
let n = input("name? ")
print(n)
let z = print("side")
print(type(z))
"""
        self.assertEqual(
            run_program(src, input_values=["sam"]),
            [
                "2.0",
                "[\"a\", \"b\"]",
                "[1.0, 2.0]",
                "sam",
                "side",
                "nil",
            ],
        )

    def test_for_loop(self):
        src = """
for (let i = 0; i < 5; i = i + 1) {
    print(i)
}
"""
        self.assertEqual(run_program(src), ["0.0", "1.0", "2.0", "3.0", "4.0"])

    def test_error_messages_include_line_col(self):
        with self.assertRaises(lang.LangSyntaxError) as cm:
            _l = ModuleLoader(project_root=None)
            _l.compile_only("let x =", module_name="<memory>")
        self.assertIsNotNone(cm.exception.line)
        self.assertIsNotNone(cm.exception.col)

        with self.assertRaises(lang.LangRuntimeError) as cm2:
            run_program("print(missing)")
        self.assertEqual(cm2.exception.kind, "name")
        self.assertIsNotNone(cm2.exception.line)

    def test_runtime_stack_trace_contains_call_chain(self):
        src = """
fn c() {
    print(missing)
}
fn b() {
    c()
}
fn a() {
    b()
}
a()
"""
        with self.assertRaises(lang.LangRuntimeError) as cm:
            run_program(src, source_path="stack.nd")
        msg = lang.format_error(cm.exception, path="stack.nd")
        self.assertIn("Stack trace", msg)
        self.assertIn("at c", msg)
        self.assertIn("called from b", msg)
        self.assertIn("called from a", msg)

    def test_import_executes_once_and_shares_globals(self):
        with tempfile.TemporaryDirectory() as td:
            mod_path = os.path.join(td, "mod.nd")
            main_path = os.path.join(td, "main.nd")
            with open(mod_path, "w", encoding="utf-8") as f:
                f.write('let counter = 0\ncounter = counter + 1\nfn hello() { return "ok" }\n')
            with open(main_path, "w", encoding="utf-8") as f:
                f.write('import "mod.nd"\nimport "mod.nd"\nprint(counter)\nprint(hello())\n')

            with open(main_path, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main_path), ["1.0", "ok"])

    def test_import_nested(self):
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.nd")
            b = os.path.join(td, "b.nd")
            c = os.path.join(td, "c.nd")
            with open(c, "w", encoding="utf-8") as f:
                f.write('let z = 7\n')
            with open(b, "w", encoding="utf-8") as f:
                f.write('import "c.nd"\nlet y = z + 1\n')
            with open(a, "w", encoding="utf-8") as f:
                f.write('import "b.nd"\nprint(y)\n')

            with open(a, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=a), ["8.0"])

    def test_import_namespace_alias(self):
        with tempfile.TemporaryDirectory() as td:
            mod = os.path.join(td, "mod.nd")
            main = os.path.join(td, "main.nd")
            with open(mod, "w", encoding="utf-8") as f:
                f.write('let v = 41\nfn inc(x) { return x + 1 }\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import "mod.nd" as m\nprint(m.v)\nprint(m.inc(1))\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main), ["41.0", "2.0"])

    def test_std_alias_imports(self):
        src = """
import { repeat } from "std:strings"
print(repeat("ha", 3))
"""
        self.assertEqual(run_program(src, source_path="main.nd"), ["hahaha"])

    def test_std_alias_namespace_import(self):
        src = """
import "std:strings" as s
print(s.repeat("ha", 2))
"""
        self.assertEqual(run_program(src, source_path="main.nd"), ["haha"])

    def test_relative_import_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            mod_dir = os.path.join(td, "modules")
            os.makedirs(mod_dir, exist_ok=True)
            mod = os.path.join(mod_dir, "greet.nd")
            main = os.path.join(td, "main.nd")
            with open(mod, "w", encoding="utf-8") as f:
                f.write('export fn greet() { return "hi" }\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import { greet } from "./modules/greet.nd"\nprint(greet())\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main), ["hi"])

    def test_project_root_imports_prefer_nd(self):
        with tempfile.TemporaryDirectory() as td:
            mod_nd = os.path.join(td, "mod.nd")
            mod_tl = os.path.join(td, "mod.tl")
            main = os.path.join(td, "main.nd")
            with open(mod_nd, "w", encoding="utf-8") as f:
                f.write('export let v = 1\n')
            with open(mod_tl, "w", encoding="utf-8") as f:
                f.write('export let v = 2\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import { v } from "mod"\nprint(v)\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main), ["1.0"])

    def test_legacy_tl_fallback_when_nd_missing(self):
        with tempfile.TemporaryDirectory() as td:
            mod_tl = os.path.join(td, "mod.tl")
            main = os.path.join(td, "main.nd")
            with open(mod_tl, "w", encoding="utf-8") as f:
                f.write('export let v = 7\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import { v } from "mod"\nprint(v)\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main), ["7.0"])

    def test_duplicate_import_caching_same_file(self):
        with tempfile.TemporaryDirectory() as td:
            mod = os.path.join(td, "mod.nd")
            main = os.path.join(td, "main.nd")
            with open(mod, "w", encoding="utf-8") as f:
                f.write('let counter = 0\ncounter = counter + 1\nexport { counter }\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import "mod.nd"\nimport "./mod.nd"\nprint(counter)\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main), ["1.0"])

    def test_nested_imports_with_std_and_relative(self):
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.nd")
            b = os.path.join(td, "b.nd")
            main = os.path.join(td, "main.nd")
            with open(a, "w", encoding="utf-8") as f:
                f.write('import { repeat } from "std:strings"\nexport fn boom() { return repeat("x", 2) }\n')
            with open(b, "w", encoding="utf-8") as f:
                f.write('import { boom } from "./a.nd"\nexport fn go() { return boom() + "!" }\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import { go } from "./b.nd"\nprint(go())\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main), ["xx!"])

    def test_invalid_std_alias_usage(self):
        with self.assertRaises(lang.LangRuntimeError) as cm:
            run_program('import "std:"\n', source_path="main.nd")
        self.assertIn("Invalid std import", str(cm.exception))

    def test_import_error_message_includes_attempts(self):
        with self.assertRaises(lang.LangRuntimeError) as cm:
            run_program('import "missing"\n', source_path="main.nd")
        self.assertIn("Import not found", str(cm.exception))

    def test_exports_private_and_plain_import(self):
        with tempfile.TemporaryDirectory() as td:
            mod = os.path.join(td, "mod.nd")
            main = os.path.join(td, "main.nd")
            with open(mod, "w", encoding="utf-8") as f:
                f.write('let secret = 9\nexport fn add(a, b) { return a + b }\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import "mod.nd"\nprint(add(1, 2))\nprint(secret)\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            with self.assertRaises((lang.LangSyntaxError, lang.LangRuntimeError)):
                run_program(src, source_path=main)

    def test_selective_imports(self):
        with tempfile.TemporaryDirectory() as td:
            mod = os.path.join(td, "mod.nd")
            main = os.path.join(td, "main.nd")
            with open(mod, "w", encoding="utf-8") as f:
                f.write('export fn add(a, b) { return a + b }\nexport fn sub(a, b) { return a - b }\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import { add } from "mod.nd"\nprint(add(5, 2))\nprint(sub(5, 2))\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            with self.assertRaises((lang.LangSyntaxError, lang.LangRuntimeError)):
                run_program(src, source_path=main)

    def test_import_missing_export_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            mod = os.path.join(td, "mod.nd")
            main = os.path.join(td, "main.nd")
            with open(mod, "w", encoding="utf-8") as f:
                f.write('export let x = 1\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import { y } from "mod.nd"\nprint(y)\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            with self.assertRaises(lang.LangRuntimeError):
                run_program(src, source_path=main)

    def test_namespace_only_exports(self):
        with tempfile.TemporaryDirectory() as td:
            mod = os.path.join(td, "mod.nd")
            main = os.path.join(td, "main.nd")
            with open(mod, "w", encoding="utf-8") as f:
                f.write('export let pub = 3\nlet priv = 7\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import "mod.nd" as m\nprint(m.pub)\nprint(m.priv)\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            with self.assertRaises((lang.LangSyntaxError, lang.LangRuntimeError)):
                run_program(src, source_path=main)

    def test_legacy_exports_if_no_export_decls(self):
        with tempfile.TemporaryDirectory() as td:
            mod = os.path.join(td, "mod.nd")
            main = os.path.join(td, "main.nd")
            with open(mod, "w", encoding="utf-8") as f:
                f.write('let x = 5\nfn inc(y) { return y + x }\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import "mod.nd"\nprint(x)\nprint(inc(1))\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main), ["5.0", "6.0"])

    def test_nested_imports_with_exports(self):
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.nd")
            b = os.path.join(td, "b.nd")
            c = os.path.join(td, "c.nd")
            with open(c, "w", encoding="utf-8") as f:
                f.write('export let z = 7\n')
            with open(b, "w", encoding="utf-8") as f:
                f.write('import { z } from "c.nd"\nexport let y = z + 1\n')
            with open(a, "w", encoding="utf-8") as f:
                f.write('import { y } from "b.nd"\nprint(y)\n')
            with open(a, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=a), ["8.0"])

    def test_file_io_builtins(self):
        with tempfile.TemporaryDirectory() as td:
            out_path = os.path.join(td, "out.txt").replace("\\", "/")
            src = f'''\nwrite_file("{out_path}", "hello")\nprint(read_file("{out_path}"))\n'''
            self.assertEqual(run_program(src), ["hello"])

    def test_file_util_builtins(self):
        with tempfile.TemporaryDirectory() as td:
            dir_path = os.path.join(td, "d").replace("\\", "/")
            out_path = os.path.join(td, "d", "out.txt").replace("\\", "/")
            src = f"""
mkdir("{dir_path}")
print(exists("{dir_path}"))
append_file("{out_path}", "a")
append_file("{out_path}", "b")
print(read_file("{out_path}"))
"""
            self.assertEqual(run_program(src), ["true", "ab"])

    def test_cli_subcommands_and_backward_compat(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(1)\n")
            self.assertEqual(lang.main(["nodus", "--version"]), 0)
            self.assertEqual(lang.main(["nodus", "run", script]), 0)
            self.assertEqual(lang.main(["language", "run", script]), 0)
            self.assertEqual(lang.main(["nodus", script]), 0)
            self.assertEqual(lang.main(["language", script]), 0)

    def test_cli_help_mentions_check_and_flags(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = lang.main(["nodus", "--help"])
        output = buf.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("nodus check", output)
        self.assertIn("nodus fmt", output)
        self.assertIn("--trace", output)
        self.assertIn("--trace-limit", output)
        self.assertIn("--project-root", output)

    def test_version_consistency(self):
        self.assertTrue(lang.VERSION.startswith("Nodus "))
        self.assertIn(lang.__version__, lang.VERSION)

    def test_cli_check_success(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(1)\n")
            exit_code = lang.main(["nodus", "check", script])
            self.assertEqual(exit_code, 0)

    def test_cli_check_syntax_failure(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "bad.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("let x =\n")
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = lang.main(["nodus", "check", script])
            self.assertEqual(exit_code, 1)
            self.assertIn("Syntax error", err.getvalue())

    def test_cli_check_import_failure(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "bad.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write('import "missing"\n')
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = lang.main(["nodus", "check", script])
            self.assertEqual(exit_code, 1)
            self.assertIn("Import not found", err.getvalue())

    def test_cli_check_compile_boundary_failure(self):
        with tempfile.TemporaryDirectory() as td:
            mod = os.path.join(td, "mod.nd")
            main = os.path.join(td, "main.nd")
            with open(mod, "w", encoding="utf-8") as f:
                f.write('let secret = 9\nexport fn add(a, b) { return a + b }\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import "mod.nd"\nprint(secret)\n')
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = lang.main(["nodus", "check", main])
            self.assertEqual(exit_code, 1)
            self.assertIn("Syntax error", err.getvalue())

    def test_trace_no_loc_and_limit(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(1)\nprint(2)\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "run", script, "--trace", "--trace-no-loc", "--trace-limit", "2"])
            output = buf.getvalue().splitlines()
            self.assertEqual(exit_code, 0)
            trace_lines = [line for line in output if line.startswith("[trace]")]
            self.assertEqual(len(trace_lines), 2)
            for line in trace_lines:
                self.assertNotIn("(", line)

    def test_trace_filter(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(1)\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "run", script, "--trace", "--trace-filter", "PUSH_CONST"])
            output = buf.getvalue().splitlines()
            self.assertEqual(exit_code, 0)
            trace_lines = [line for line in output if line.startswith("[trace]")]
            self.assertTrue(trace_lines)
            for line in trace_lines:
                self.assertIn("PUSH_CONST", line)

    def test_check_rejects_trace_flags(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(1)\n")
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = lang.main(["nodus", "check", script, "--trace"])
            self.assertEqual(exit_code, 2)
            self.assertIn("Trace flags", err.getvalue())

    def test_tl_warning_emitted(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.tl")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(1)\n")
            err = io.StringIO()
            with redirect_stderr(err):
                exit_code = lang.main(["nodus", "run", script])
            self.assertEqual(exit_code, 0)
            self.assertIn("legacy .tl", err.getvalue())

    def test_fmt_simple_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write('import {b,a} from "m.nd"\nfn add(a,b){return a+b}\n')
            exit_code = lang.main(["nodus", "fmt", script])
            self.assertEqual(exit_code, 0)
            with open(script, "r", encoding="utf-8") as f:
                formatted = f.read()
            expected = (
                'import { b, a } from "m.nd"\n'
                '\n'
                'fn add(a, b) {\n'
                '    return a + b\n'
                '}\n'
            )
            self.assertEqual(formatted, expected)
            exit_code = lang.main(["nodus", "fmt", script])
            self.assertEqual(exit_code, 0)
            with open(script, "r", encoding="utf-8") as f:
                formatted2 = f.read()
            self.assertEqual(formatted2, expected)

    def test_fmt_preserves_integer_looking_literals(self):
        src = (
            "let x=1\n"
            "let y=[2,3]\n"
            "let z={\"a\":4,\"b\":5}\n"
            "print(x+y[0]+z[\"a\"])\n"
        )
        expected = (
            "let x = 1\n"
            "let y = [2, 3]\n"
            "let z = {\"a\": 4, \"b\": 5}\n"
            "print(x + y[0] + z[\"a\"])\n"
        )
        formatted = format_source(src)
        self.assertEqual(formatted, expected)
        self.assertEqual(format_source(formatted), expected)

    def test_fmt_preserves_float_literals(self):
        src = "let x=1.0\nlet y=[2.5,3.0]\nprint(x+y[0]+y[1])\n"
        expected = (
            "let x = 1.0\n"
            "let y = [2.5, 3.0]\n"
            "print(x + y[0] + y[1])\n"
        )
        formatted = format_source(src)
        self.assertEqual(formatted, expected)
        self.assertEqual(format_source(formatted), expected)

    def test_fmt_preserves_negative_literals_and_grouped_unary(self):
        src = "let x=-5\nlet y=-(a+1)\nprint(-(-3))\n"
        expected = (
            "let x = -5\n"
            "let y = -(a + 1)\n"
            "print(- -3)\n"
        )
        formatted = format_source(src)
        self.assertEqual(formatted, expected)
        self.assertEqual(format_source(formatted), expected)

    def test_fmt_unary_comments_regression(self):
        src = (
            "# heading\n"
            "let x=-5 // trailing unary\n"
            "let y=-(x+1) # grouped unary\n"
        )
        expected = (
            "# heading\n"
            "let x = -5\n"
            "// trailing unary\n"
            "let y = -(x + 1)\n"
            "# grouped unary\n"
        )
        formatted = format_source(src)
        self.assertEqual(formatted, expected)
        self.assertEqual(format_source(formatted), expected)

    def test_fmt_keep_trailing_comments_with_unary(self):
        src = "let x=-5 // trailing unary\nlet y=-(x+1) # grouped unary\n"
        expected = "let x = -5 // trailing unary\nlet y = -(x + 1) # grouped unary\n"
        formatted = format_source(src, keep_trailing_comments=True)
        self.assertEqual(formatted, expected)
        self.assertEqual(format_source(formatted, keep_trailing_comments=True), expected)

    def test_fmt_check(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("let x=1\n")
            exit_code = lang.main(["nodus", "fmt", script, "--check"])
            self.assertEqual(exit_code, 1)
            lang.main(["nodus", "fmt", script])
            exit_code = lang.main(["nodus", "fmt", script, "--check"])
            self.assertEqual(exit_code, 0)

    def test_fmt_blocks_and_literals(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write('if(true){print([1,2,3])}else{print({"a":1,"b":2})}\n')
            exit_code = lang.main(["nodus", "fmt", script])
            self.assertEqual(exit_code, 0)
            with open(script, "r", encoding="utf-8") as f:
                formatted = f.read()
            self.assertIn("if (true) {", formatted)
            self.assertIn("[1, 2, 3]", formatted)
            self.assertIn("{\"a\": 1, \"b\": 2}", formatted)

    def test_fmt_comments_removed(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("# comment\nlet x = 1 // trailing\n")
            exit_code = lang.main(["nodus", "fmt", script])
            self.assertEqual(exit_code, 0)
            with open(script, "r", encoding="utf-8") as f:
                formatted = f.read()
            self.assertIn("# comment", formatted)
            self.assertIn("// trailing", formatted)
            self.assertNotIn("let x = 1 // trailing", formatted)
            self.assertIn("let x = 1\n// trailing\n", formatted)

    def test_fmt_keep_trailing_comments(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("let x = 1 // trailing\n")
            exit_code = lang.main(["nodus", "fmt", script, "--keep-trailing"])
            self.assertEqual(exit_code, 0)
            with open(script, "r", encoding="utf-8") as f:
                formatted = f.read()
            self.assertIn("let x = 1 // trailing", formatted)

    def test_fmt_exports_and_for(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write('export fn add(a,b){return a+b}\nexport let x=1\nfor(let i=0;i<3;i=i+1){print(i)}\n')
            exit_code = lang.main(["nodus", "fmt", script])
            self.assertEqual(exit_code, 0)
            with open(script, "r", encoding="utf-8") as f:
                formatted = f.read()
            self.assertIn("export fn add(a, b)", formatted)
            self.assertIn("export let x = 1", formatted)
            self.assertIn("for (let i = 0; i < 3; i = i + 1)", formatted)

    def test_cli_project_root_override(self):
        with tempfile.TemporaryDirectory() as td:
            proj_root = os.path.join(td, "project")
            os.makedirs(os.path.join(proj_root, "lib"), exist_ok=True)
            os.makedirs(os.path.join(proj_root, "app"), exist_ok=True)
            mod_path = os.path.join(proj_root, "lib", "mod.nd")
            main_path = os.path.join(proj_root, "app", "main.nd")
            with open(mod_path, "w", encoding="utf-8") as f:
                f.write('export let v = 7\n')
            with open(main_path, "w", encoding="utf-8") as f:
                f.write('import { v } from "lib/mod"\nprint(v)\n')

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "run", main_path, "--project-root", proj_root])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("7.0", output)

    def test_env_project_root_override(self):
        with tempfile.TemporaryDirectory() as td:
            proj_root = os.path.join(td, "project")
            os.makedirs(os.path.join(proj_root, "lib"), exist_ok=True)
            os.makedirs(os.path.join(proj_root, "app"), exist_ok=True)
            mod_path = os.path.join(proj_root, "lib", "mod.nd")
            main_path = os.path.join(proj_root, "app", "main.nd")
            with open(mod_path, "w", encoding="utf-8") as f:
                f.write('export let v = 11\n')
            with open(main_path, "w", encoding="utf-8") as f:
                f.write('import { v } from "lib/mod"\nprint(v)\n')

            old_root = os.environ.get("NODUS_PROJECT_ROOT")
            os.environ["NODUS_PROJECT_ROOT"] = proj_root
            try:
                with open(main_path, "r", encoding="utf-8") as f:
                    src = f.read()
                self.assertEqual(run_program(src, source_path=main_path), ["11.0"])
            finally:
                if old_root is None:
                    os.environ.pop("NODUS_PROJECT_ROOT", None)
                else:
                    os.environ["NODUS_PROJECT_ROOT"] = old_root

    def test_invalid_project_root_diagnostic(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(1)\n")
            buf = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(err):
                exit_code = lang.main(["nodus", "run", script, "--project-root", os.path.join(td, "nope")])
            self.assertEqual(exit_code, 1)
            self.assertIn("Invalid project root", err.getvalue())

    def test_reexport_from_module(self):
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.nd")
            b = os.path.join(td, "b.nd")
            main = os.path.join(td, "main.nd")
            with open(a, "w", encoding="utf-8") as f:
                f.write('export let x = 3\n')
            with open(b, "w", encoding="utf-8") as f:
                f.write('export { x } from "./a.nd"\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import { x } from "./b.nd"\nprint(x)\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main), ["3.0"])

    def test_reexport_non_exported_error(self):
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.nd")
            b = os.path.join(td, "b.nd")
            with open(a, "w", encoding="utf-8") as f:
                f.write('export let y = 1\nlet x = 3\n')
            with open(b, "w", encoding="utf-8") as f:
                f.write('export { x } from "./a.nd"\n')
            with open(b, "r", encoding="utf-8") as f:
                src = f.read()
            with self.assertRaises(lang.LangRuntimeError) as cm:
                run_program(src, source_path=b)
            self.assertIn("Re-export failed", str(cm.exception))

    def test_package_index_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            pkg_dir = os.path.join(td, "utils")
            os.makedirs(pkg_dir, exist_ok=True)
            index_path = os.path.join(pkg_dir, "index.nd")
            main = os.path.join(td, "main.nd")
            with open(index_path, "w", encoding="utf-8") as f:
                f.write('export let v = 2\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import { v } from "./utils"\nprint(v)\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main), ["2.0"])

    def test_package_resolution_prefers_file_over_index(self):
        with tempfile.TemporaryDirectory() as td:
            pkg_dir = os.path.join(td, "utils")
            os.makedirs(pkg_dir, exist_ok=True)
            file_path = os.path.join(td, "utils.nd")
            index_path = os.path.join(pkg_dir, "index.nd")
            main = os.path.join(td, "main.nd")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write('export let v = 1\n')
            with open(index_path, "w", encoding="utf-8") as f:
                f.write('export let v = 9\n')
            with open(main, "w", encoding="utf-8") as f:
                f.write('import { v } from "./utils"\nprint(v)\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main), ["1.0"])

    def test_import_error_lists_package_candidates(self):
        with tempfile.TemporaryDirectory() as td:
            main = os.path.join(td, "main.nd")
            with open(main, "w", encoding="utf-8") as f:
                f.write('import "./missing"\n')
            with open(main, "r", encoding="utf-8") as f:
                src = f.read()
            with self.assertRaises(lang.LangRuntimeError) as cm:
                run_program(src, source_path=main)
            msg = str(cm.exception)
            self.assertIn("index.nd", msg)
            self.assertIn("index.tl", msg)

    def test_cross_module_stack_trace_locations(self):
        with tempfile.TemporaryDirectory() as td:
            mod_path = os.path.join(td, "mod.nd")
            main_path = os.path.join(td, "main.nd")
            with open(mod_path, "w", encoding="utf-8") as f:
                f.write(
                    "fn boom() {\n"
                    "    let nums = [1]\n"
                    "    print(nums[9])\n"
                    "}\n"
                )
            with open(main_path, "w", encoding="utf-8") as f:
                f.write('import { boom } from "mod.nd"\nboom()\n')

            with open(main_path, "r", encoding="utf-8") as f:
                src = f.read()
            with self.assertRaises(lang.LangRuntimeError) as cm:
                run_program(src, source_path=main_path)
            msg = lang.format_error(cm.exception, path=main_path)
            self.assertIn("Stack trace", msg)
            self.assertIn(mod_path, msg)

    def test_cli_dump_bytecode(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(-1)\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "run", script, "--dump-bytecode"])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("Function main:", output)
            self.assertIn("PUSH_CONST", output)
            self.assertIn("NEG", output)
            self.assertIn("CALL print", output)

    def test_cli_ast_output_structure(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write(
                    'import "std:strings" as s\n'
                    "fn add(a, b) { return a + b }\n"
                    "let result = add(1, 2)\n"
                )
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "ast", script])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("Module", output)
            self.assertIn("Import", output)
            self.assertIn("FnDef", output)
            self.assertIn("Let", output)
            self.assertIn("Return", output)
            self.assertIn("Binary op=+", output)

    def test_cli_ast_compact_mode(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("fn add(a, b) { return a + b }\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "ast", script, "--compact"])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("Module", output)
            self.assertIn("FnDef", output)
            self.assertIn("Binary op=+", output)

    def test_cli_dis_output_contains_opcodes(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(1 + 2)\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "dis", script])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("Function main:", output)
            self.assertIn("PUSH_CONST", output)
            self.assertIn("ADD", output)

    def test_cli_dis_with_locations(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(1 + 2)\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "dis", script, "--loc"])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("[", output)

    def test_cli_dis_multiple_functions(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write(
                    "fn add(a, b) { return a + b }\n"
                    "fn sub(a, b) { return a - b }\n"
                    "print(add(3, 1))\n"
                )
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "dis", script])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("Function add:", output)
            self.assertIn("Function sub:", output)
            self.assertIn("Function main:", output)

    def test_cli_trace_mode(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "x.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print(1)\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "run", script, "--trace"])
            output = buf.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("[trace]", output)
            self.assertIn("1.0", output)

    def test_calling_non_function_error_message(self):
        src = """
let f = 123
f()
"""
        with self.assertRaises(lang.LangRuntimeError) as cm:
            run_program(src, source_path="main.nd")
        self.assertIn("Cannot call non-function", str(cm.exception))

    def test_std_strings_and_collections_helpers(self):
        src = """
import "std:strings" as s
import "std:collections" as c
let items = ["a", "b", "c"]
print(s.join(items, ","))
print(c.first(items))
print(c.last(items))
let more = c.push(items, "d")
print(s.join(more, "-"))
let m = {"a": 1, "b": 2}
print(c.has_key(m, "b"))
print(c.has_key(m, "z"))
"""
        self.assertEqual(
            run_program(src, source_path="main.nd"),
            ["a,b,c", "a", "c", "a-b-c-d", "true", "false"],
        )

    def test_std_fs_and_path_helpers(self):
        with tempfile.TemporaryDirectory() as td:
            td_norm = td.replace("\\", "/")
            expected_path = os.path.join(td_norm, "note.txt")
            expected_dir = os.path.dirname(expected_path)
            src = f"""
import "std:fs" as fs
import "std:path" as p
let dir = "{td_norm}"
let file_path = p.join(dir, "note.txt")
fs.write(file_path, "hello")
print(fs.read(file_path))
print(p.basename(file_path))
print(p.ext(file_path))
print(p.stem(file_path))
print(p.dirname(file_path))
print(fs.exists_path(file_path))
"""
            output = run_program(src, source_path="main.nd")
            self.assertEqual(output[0], "hello")
            self.assertEqual(output[1], "note.txt")
            self.assertEqual(output[2], "txt")
            self.assertEqual(output[3], "note")
            self.assertEqual(output[4], expected_dir)
            self.assertEqual(output[5], "true")

    def test_project_layout_demo_example_runs(self):
        main_path = os.path.abspath(os.path.join("examples", "project_layout_demo", "main.nd"))
        with open(main_path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertEqual(
            run_program(src, source_path=main_path),
            [
                "-- sum: 10.0",
                "-- square: 25.0",
                "ready -> set -> run",
            ],
        )


if __name__ == "__main__":
    unittest.main()
