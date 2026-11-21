"""The bytecode optimizer (#964).

From v1.0 until #964 nothing called `optimize_bytecode`, so `--no-opt` and
`optimize=` did nothing and this file's tests passed vacuously: the "with and
without" comparison ran the same program twice. Every test here now either
compares the two settings or asserts on what the optimizer actually produced,
and each was checked to fail against the optimizer as it was.
"""

import dataclasses
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, "C:/dev/Coding Language/src")

import nodus as lang  # noqa: E402
from nodus.compiler.compiler import FunctionInfo, format_bytecode  # noqa: E402
from nodus.compiler.optimizer import optimize_bytecode  # noqa: E402
from nodus.runtime import bytecode_cache  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.module import ModuleBytecode  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402


def compile_with(src: str, optimize: bool, module_name: str = "main.nd"):
    return ModuleLoader(project_root=None).compile_only(src, module_name=module_name, optimize=optimize)


def run_program(src: str, optimize: bool) -> list[str]:
    code, functions, code_locs = compile_with(src, optimize)
    vm = lang.VM(code, functions, code_locs=code_locs, source_path="main.nd")
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return buf.getvalue().splitlines()


def outcome(src: str, optimize: bool) -> tuple:
    """What a program does: its output, or its error's kind, message and line."""
    result = NodusRuntime(timeout_ms=None).run_source(src, optimize=optimize)
    error = result.get("error") or {}
    return (result.get("ok"), result.get("stdout"), error.get("kind") or error.get("type"),
            error.get("message"), error.get("line"))


def opcodes(code) -> list[str]:
    return [instr[0] for instr in code.get("instructions", code) if isinstance(instr, tuple)]


class WhatItDoes(unittest.TestCase):
    def test_constant_folding_rewrites_addition(self):
        code, functions, code_locs = compile_with("let x = 2 + 3\nprint(x)\n", optimize=True)
        text = format_bytecode(code, code_locs, functions)
        self.assertIn("PUSH_CONST 5.0", text)
        self.assertNotIn("ADD", text)

    def test_dead_code_removed_after_return(self):
        src = 'fn test() {\n    return 1\n    print("dead")\n}\nprint(test())\n'
        code, functions, code_locs = compile_with(src, optimize=True)
        text = format_bytecode(code, code_locs, functions)
        lines = text.splitlines()
        fn_text = "\n".join(lines[lines.index("Function test:"):lines.index("Function main:")])
        self.assertNotIn("dead", fn_text)

    def test_an_assignment_statement_does_not_read_its_value_back(self):
        src = "fn f() {\n    let i = 0i\n    i = i + 1i\n    return i\n}\nprint(f())\n"
        plain = opcodes(compile_with(src, optimize=False)[0])
        optimized = opcodes(compile_with(src, optimize=True)[0])
        self.assertEqual(plain.count("POP") - optimized.count("POP"), 1)
        self.assertEqual(plain.count("LOAD_LOCAL_IDX") - optimized.count("LOAD_LOCAL_IDX"), 1)
        self.assertEqual(run_program(src, True), run_program(src, False))

    # closes: #964
    def test_it_runs_by_default_and_no_opt_turns_it_off(self):
        src = "let x = 2i + 3i\n1i\nprint(x)\n"
        stats = {}
        for optimize in (True, False):
            runtime = NodusRuntime(timeout_ms=None)
            result = runtime.run_source(src, optimize=optimize)
            self.assertTrue(result["ok"], result)
            stats[optimize] = runtime.get_execution_stats()["instructions_executed"]
        self.assertLess(stats[True], stats[False])

    def test_cli_no_opt_leaves_the_addition(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "main.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write("let x = 2 + 3\nprint(x)\n")
            dumps = {}
            for flags in ([], ["--no-opt"]):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    exit_code = lang.main(["nodus", "run", *flags, script, "--dump-bytecode"])
                self.assertEqual(exit_code, 0)
                dumps[bool(flags)] = buf.getvalue()
        self.assertIn("ADD", dumps[True])
        self.assertNotIn("ADD", dumps[False])


class FoldingAgreesWithTheVM(unittest.TestCase):
    """A fold runs the VM's handler, so it cannot compute something else.

    The optimizer as it was folded `5i / 2i` to 2.5 (the VM says 2),
    `1i == true` to true (false), and `true + 1i` to 2 (a type error).
    """

    EXPRESSIONS = [
        "5i / 2i", "7i % 3i", "-7i % 3i", "1i == true", "1i == 1.0", '"a" == "a"',
        '"a" != "b"', "-0.0", "0.0 - 0.0", "2.5 * 2i", "1i < 2.5", '"a" < "b"',
        "!0i", '!""', "!nil", "-(3i)", '"ab" + "cd"',
        # Each of these is an error at run time, and must stay one.
        "true + 1i", "1i / 0i", "1.0 / 0.0", '"a" + 1i', '"a" < 1i', "-true", '-"x"',
    ]

    def test_every_expression_behaves_the_same_folded(self):
        for expr in self.EXPRESSIONS:
            src = f"let v = {expr}\nprint(v)\n"
            with self.subTest(expr=expr):
                self.assertEqual(outcome(src, True), outcome(src, False))

    def test_negative_zero_keeps_its_sign(self):
        src = "let z = -0.0\nlet w = 0.0\nprint(z)\nprint(w)\n"
        self.assertEqual(run_program(src, True), ["-0.0", "0.0"])


class CompactionKeepsEverything(unittest.TestCase):
    SRC = (
        "fn typed(a: int, b: string) -> int {\n"
        "    let unused = 2i + 3i\n"
        "    let total = a + 1i\n"
        "    total = total + 1i\n"
        "    return total\n"
        "}\n"
        "fn outer(n) {\n"
        "    let k = 1i + 1i\n"
        "    return fn() { return n + k }\n"
        "}\n"
        "print(typed(1i, \"x\"))\n"
        "print(outer(5i)())\n"
    )

    def test_every_function_info_field_but_addr_survives(self):
        _, plain, _ = compile_with(self.SRC, optimize=False)
        _, optimized, _ = compile_with(self.SRC, optimize=True)
        self.assertEqual(set(plain), set(optimized))
        compared = [f.name for f in dataclasses.fields(FunctionInfo) if f.name != "addr"]
        self.assertIn("local_slots", compared)
        self.assertIn("param_types", compared)
        for name in plain:
            for field in compared:
                with self.subTest(fn=name, field=field):
                    self.assertEqual(getattr(optimized[name], field), getattr(plain[name], field))

    def test_the_addresses_did_move(self):
        # Not vacuous: the compaction happened, so a dropped field would show.
        _, plain, _ = compile_with(self.SRC, optimize=False)
        _, optimized, _ = compile_with(self.SRC, optimize=True)
        self.assertNotEqual({n: f.addr for n, f in plain.items()},
                            {n: f.addr for n, f in optimized.items()})

    def test_the_program_still_runs(self):
        self.assertEqual(run_program(self.SRC, True), ["3", "7"])
        self.assertEqual(run_program(self.SRC, True), run_program(self.SRC, False))

    def test_the_optimizer_never_builds_a_function_info_field_by_field(self):
        import inspect
        from nodus.compiler import optimizer
        source = inspect.getsource(optimizer)
        self.assertNotIn("FunctionInfo(", source)
        self.assertIn("dataclasses.replace(info", source)


class AddressesAfterCompaction(unittest.TestCase):
    def test_try_finally_runs_on_every_exit(self):
        src = (
            "fn f(mode) {\n"
            "    try {\n"
            "        let pad = 1i + 2i + 3i + 4i\n"
            "        if (mode == 1i) { return \"returned\" }\n"
            "        if (mode == 2i) { throw \"thrown\" }\n"
            "    } catch (e) {\n"
            "        let more = 5i + 6i\n"
            "        print(\"caught \\(e)\")\n"
            "    } finally {\n"
            "        let late = 7i * 8i\n"
            "        print(\"finally \\(mode)\")\n"
            "    }\n"
            "    return \"fell through\"\n"
            "}\n"
            "print(f(1i))\nprint(f(2i))\nprint(f(3i))\n"
        )
        self.assertEqual(run_program(src, True), run_program(src, False))
        self.assertEqual(run_program(src, True).count("finally 1"), 1)

    def test_every_address_operand_lands_inside_the_code(self):
        src = (
            "fn f(xs) {\n"
            "    let total = 0i\n"
            "    for x in xs {\n"
            "        if (x == 2i) { continue }\n"
            "        try { total = total + x } finally { total = total + (1i - 1i) }\n"
            "    }\n"
            "    return total\n"
            "}\n"
            "print(f([1i, 2i, 3i]))\n"
        )
        code, _, _ = compile_with(src, optimize=True)
        instrs = code["instructions"]
        for instr in instrs:
            if instr[0] in ("JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE", "ITER_NEXT", "SETUP_TRY"):
                self.assertTrue(0 <= instr[1] <= len(instrs), instr)
                if instr[0] == "SETUP_TRY" and len(instr) > 2 and instr[2]:
                    self.assertTrue(0 < instr[2] < len(instrs), instr)
        self.assertEqual(run_program(src, True), ["4"])

    def test_a_jump_into_removed_code_lands_on_what_follows(self):
        # The `1i` statement after the `if` is a PUSH_CONST; POP pair that the
        # if's exit jump targets.
        src = "fn f(c) {\n    if (c) { print(\"yes\") }\n    1i\n    return \"done\"\n}\nprint(f(true))\nprint(f(false))\n"
        self.assertEqual(run_program(src, True), ["yes", "done", "done"])

    def test_the_finally_block_survives_when_the_try_always_returns(self):
        # Reached only through SETUP_TRY's finally address.
        src = 'fn f() {\n    try {\n        return 1i\n    } finally {\n        print("cleanup")\n    }\n}\nprint(f())\n'
        self.assertEqual(run_program(src, True), ["cleanup", "1"])


class WhereTheSettingComesFrom(unittest.TestCase):
    def test_explicit_wins(self):
        self.assertFalse(ModuleLoader(optimize=False).optimize)
        vm = VM([], {}, code_locs=[], source_path=None)
        vm.optimize_bytecode = False
        self.assertTrue(ModuleLoader(vm=vm, optimize=True).optimize)

    def test_a_loader_follows_its_vm(self):
        # A durable rebuild builds its loader from the VM it resumes.
        vm = VM([], {}, code_locs=[], source_path=None)
        self.assertTrue(ModuleLoader(vm=vm).optimize)
        vm.optimize_bytecode = False
        self.assertFalse(ModuleLoader(vm=vm).optimize)

    def test_a_debugged_load_is_not_optimized(self):
        self.assertFalse(ModuleLoader(debugger=object()).optimize)

    def test_the_default_is_on(self):
        self.assertTrue(ModuleLoader().optimize)


class TheCacheKeepsTheTwoApart(unittest.TestCase):
    def test_an_entry_is_read_only_by_the_setting_that_wrote_it(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "m.nd")
            with open(path, "w", encoding="utf-8") as f:
                f.write("print(1i)\n")
            code, functions, locs = compile_with("print(1i)\n", optimize=True)
            unit = ModuleBytecode(code=code, functions=functions, constants=[], code_locs=locs)
            bytecode_cache.write_cached_bytecode(root, path, unit, optimized=True)
            self.assertIsNotNone(bytecode_cache.load_cached_bytecode(root, path, optimized=True))
            self.assertIsNone(bytecode_cache.load_cached_bytecode(root, path, optimized=False))

    def test_an_entry_from_before_the_flag_is_a_miss(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "m.nd")
            with open(path, "w", encoding="utf-8") as f:
                f.write("print(1i)\n")
            code, functions, locs = compile_with("print(1i)\n", optimize=False)
            unit = ModuleBytecode(code=code, functions=functions, constants=[], code_locs=locs)
            written = bytecode_cache.write_cached_bytecode(root, path, unit, optimized=True)
            # Rewrite it without the field, as an older nodus-lang wrote it.
            with open(written, "rb") as f:
                payload = bytecode_cache._decode_cache_file(f.read())
            del payload["optimized"]
            with open(written, "wb") as f:
                f.write(bytecode_cache._encode_cache_file(payload))
            self.assertIsNone(bytecode_cache.load_cached_bytecode(root, path, optimized=True))


class RawOptimizerApi(unittest.TestCase):
    def test_optimize_bytecode_on_compiler_output(self):
        code, functions, locs = compile_with("let x = 2i * 3i\nprint(x)\n", optimize=False)
        out, _fns, out_locs = optimize_bytecode(code["instructions"], functions, locs)
        self.assertIn(("PUSH_CONST", 6), out)
        self.assertEqual(len(out), len(out_locs))


if __name__ == "__main__":
    unittest.main()
