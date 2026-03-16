"""Regression tests for the LOAD_LOCAL → LOAD_LOCAL_IDX compiler migration.

These tests confirm that the compiler never emits the deprecated LOAD_LOCAL
(name-keyed) instruction for any code pattern that previously had a fallback
path (compiler.py lines 584, 619, 731).  They also serve as guards during
the LOAD_LOCAL VM removal in v1.0.

The three formerly-unreachable fallback paths were:

    Fallback 1 (line 584): Var expression loading a local variable
    Fallback 2 (line 619): Assign expression post-assign reload
    Fallback 3 (line 731): Call whose callee is a local closure variable

Analysis showed all three are unreachable: SymbolTable.define() assigns
symbol.index whenever _current_function_scope() is not None, which is exactly
the same condition as in_function_scope(). So "local + in_function + index is None"
is a logical contradiction and can never be true.
"""

import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def compile_source(src: str) -> list[tuple]:
    """Compile Nodus source and return the flat instruction list."""
    loader = ModuleLoader(project_root=None)
    bytecode, _functions, _locs = loader.compile_only(src, module_name="<test>")
    # compile_only returns a wrapped dict; extract the instruction list.
    if isinstance(bytecode, dict):
        return bytecode["instructions"]
    return bytecode


def run_program(src: str) -> list[str]:
    loader = ModuleLoader(project_root=None)
    code, functions, code_locs = loader.compile_only(src, module_name="<test>")
    vm = lang.VM(code, functions, code_locs=code_locs)
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return buf.getvalue().splitlines()


def load_local_instructions(code: list[tuple]) -> list[tuple]:
    """Return every LOAD_LOCAL (name-keyed) instruction in the bytecode."""
    return [instr for instr in code if instr[0] == "LOAD_LOCAL"]


class LoadLocalReachabilityTests(unittest.TestCase):
    """Confirm the three formerly-fallback compiler paths never emit LOAD_LOCAL."""

    def test_fallback1_var_load_never_emits_load_local(self):
        """Fallback 1: loading a local variable via Var expression."""
        src = """
fn test(x) {
    let y = x + 1
    return y
}
test(1)
"""
        code = compile_source(src)
        self.assertEqual(
            load_local_instructions(code),
            [],
            "Var load of a local variable should emit LOAD_LOCAL_IDX, not LOAD_LOCAL",
        )

    def test_fallback2_assign_reload_never_emits_load_local(self):
        """Fallback 2: post-assign reload in an Assign expression."""
        src = """
fn test(x) {
    let y = x
    y = y + 1
    return y
}
test(5)
"""
        code = compile_source(src)
        self.assertEqual(
            load_local_instructions(code),
            [],
            "Assign post-reload of a local variable should emit LOAD_LOCAL_IDX, not LOAD_LOCAL",
        )

    def test_fallback3_call_local_closure_never_emits_load_local(self):
        """Fallback 3: calling a local variable that holds a closure."""
        src = """
fn test(x) {
    let f = fn(n) { return n * 2 }
    return f(x)
}
test(3)
"""
        code = compile_source(src)
        self.assertEqual(
            load_local_instructions(code),
            [],
            "Call through local closure variable should emit LOAD_LOCAL_IDX, not LOAD_LOCAL",
        )

    def test_all_three_patterns_combined(self):
        """All three fallback patterns in one function — none should emit LOAD_LOCAL."""
        src = """
fn test(x) {
    let y = x + 1
    y = y + 1
    let f = fn(n) { return n * 2 }
    return f(y)
}
test(1)
"""
        code = compile_source(src)
        self.assertEqual(
            load_local_instructions(code),
            [],
            "Combined test: none of the three fallback patterns should emit LOAD_LOCAL",
        )

    def test_catch_variable_never_emits_load_local(self):
        """Catch variable in a try/catch inside a function."""
        src = """
fn test() {
    try {
        throw "oops"
    } catch e {
        return e.message
    }
}
test()
"""
        code = compile_source(src)
        self.assertEqual(load_local_instructions(code), [])

    def test_for_loop_variable_never_emits_load_local(self):
        """ForEach loop variable inside a function."""
        src = """
fn test() {
    let total = 0
    for item in [1, 2, 3] {
        total = total + item
    }
    return total
}
print(test())
"""
        code = compile_source(src)
        self.assertEqual(load_local_instructions(code), [])

    def test_nested_function_locals_never_emit_load_local(self):
        """Locals in both outer and inner (nested) functions."""
        src = """
fn outer(x) {
    let a = x + 1
    let inner = fn(y) {
        let b = y + 1
        return a + b
    }
    return inner(a)
}
outer(1)
"""
        code = compile_source(src)
        self.assertEqual(load_local_instructions(code), [])


class CompilerNeverEmitsLoadLocalTest(unittest.TestCase):
    """Step 4 smoke test: comprehensive program that exercises all formerly-fallback
    patterns, verifying no LOAD_LOCAL appears anywhere in the output bytecode."""

    def test_compiler_never_emits_load_local(self):
        """Comprehensive compilation smoke test — no LOAD_LOCAL in any output."""
        src = """
fn test(x) {
    try {
        let y = x + 1
        y = y * 2
        return y
    } catch e {
        return e.message
    }
}

fn call_closure(x) {
    let f = fn(n) { return n + 1 }
    return f(x)
}

fn loop_sum() {
    let total = 0
    for item in [1, 2, 3] {
        total = total + item
    }
    return total
}

fn nested(x) {
    let a = x + 1
    let inner = fn(y) {
        let b = y + 2
        b = b * 3
        return a + b
    }
    return inner(a)
}

print(test(5))
print(call_closure(10))
print(loop_sum())
print(nested(1))
"""
        code = compile_source(src)
        bad = load_local_instructions(code)
        self.assertEqual(
            bad,
            [],
            f"Compiler emitted {len(bad)} LOAD_LOCAL instruction(s) — "
            f"all locals should use LOAD_LOCAL_IDX: {bad}",
        )

    def test_compiled_programs_produce_correct_output(self):
        """Behavioral check: programs using formerly-fallback patterns run correctly."""
        src = """
fn test(x) {
    let y = x + 1
    y = y + 1
    let f = fn(n) { return n * 2 }
    return f(y)
}
print(test(3))
"""
        self.assertEqual(run_program(src), ["10.0"])

    def test_catch_var_correct_behavior(self):
        src = """
fn safe_div(a, b) {
    try {
        if (b == 0) {
            throw "division by zero"
        }
        return a / b
    } catch e {
        return e.message
    }
}
print(safe_div(10, 2))
print(safe_div(5, 0))
"""
        self.assertEqual(run_program(src), ["5.0", "division by zero"])


if __name__ == "__main__":
    unittest.main()
