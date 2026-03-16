"""Tests for finally block support in try/catch/finally."""

import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str) -> list[str]:
    loader = ModuleLoader(project_root=None)
    code, functions, code_locs = loader.compile_only(src, module_name="<test>")
    vm = lang.VM(code, functions, code_locs=code_locs)
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return buf.getvalue().splitlines()


class FinallyNormalPathTests(unittest.TestCase):
    """Finally runs when the try block completes without error."""

    def test_finally_runs_on_no_exception(self):
        src = """
try {
    print("try")
} catch err {
    print("catch")
} finally {
    print("finally")
}
"""
        self.assertEqual(run_program(src), ["try", "finally"])

    def test_finally_runs_after_try_body(self):
        src = """
let x = 0
try {
    x = 1
} catch err {
    x = 99
} finally {
    x = x + 10
}
print(x)
"""
        self.assertEqual(run_program(src), ["11.0"])

    def test_code_after_finally_executes(self):
        src = """
try {
    print("a")
} catch err {
    print("b")
} finally {
    print("c")
}
print("d")
"""
        self.assertEqual(run_program(src), ["a", "c", "d"])


class FinallyCaughtExceptionTests(unittest.TestCase):
    """Finally runs after catch handles an exception."""

    def test_finally_runs_after_catch(self):
        src = """
try {
    throw "boom"
} catch err {
    print("caught")
} finally {
    print("finally")
}
"""
        self.assertEqual(run_program(src), ["caught", "finally"])

    def test_finally_after_catch_then_continues(self):
        src = """
try {
    throw "err"
} catch e {
    print("c")
} finally {
    print("f")
}
print("done")
"""
        self.assertEqual(run_program(src), ["c", "f", "done"])

    def test_finally_runs_after_thrown_error(self):
        src = """
try {
    throw "oops"
} catch e {
    print("caught")
} finally {
    print("clean")
}
"""
        self.assertEqual(run_program(src), ["caught", "clean"])

    def test_finally_runs_after_runtime_error_caught(self):
        src = """
try {
    let bad = 1 / 0
} catch err {
    print("div error caught")
} finally {
    print("cleanup done")
}
"""
        self.assertEqual(run_program(src), ["div error caught", "cleanup done"])


class FinallyReturnInsideTryTests(unittest.TestCase):
    """Finally runs when a return statement exits a try block early."""

    def test_finally_runs_on_return_from_try(self):
        src = """
fn go() {
    try {
        return 1
    } catch err {
        return 2
    } finally {
        print("finally")
    }
}
let r = go()
print(r)
"""
        self.assertEqual(run_program(src), ["finally", "1.0"])

    def test_finally_runs_before_function_exits(self):
        src = """
fn work() {
    try {
        print("try")
        return 42
    } catch err {
        print("catch")
    } finally {
        print("finally")
    }
}
let v = work()
print(v)
"""
        self.assertEqual(run_program(src), ["try", "finally", "42.0"])

    def test_deferred_return_value_is_preserved(self):
        src = """
fn compute() {
    try {
        return 100
    } catch err {
        return 0
    } finally {
        print("side effect")
    }
}
print(compute())
"""
        self.assertEqual(run_program(src), ["side effect", "100.0"])


class FinallyNestedTests(unittest.TestCase):
    """Nested try/catch/finally blocks."""

    def test_nested_finally_inner_first(self):
        src = """
try {
    try {
        print("inner try")
    } catch e {
        print("inner catch")
    } finally {
        print("inner finally")
    }
} catch err {
    print("outer catch")
} finally {
    print("outer finally")
}
"""
        self.assertEqual(run_program(src), ["inner try", "inner finally", "outer finally"])

    def test_nested_finally_with_exception(self):
        src = """
try {
    try {
        throw "inner"
    } catch e {
        print("inner caught")
    } finally {
        print("inner finally")
    }
} catch err {
    print("outer catch")
} finally {
    print("outer finally")
}
"""
        self.assertEqual(run_program(src), ["inner caught", "inner finally", "outer finally"])


class FinallyWithoutExceptionTests(unittest.TestCase):
    """Finally with complex control flow."""

    def test_finally_with_variable_mutation(self):
        src = """
let log = []
try {
    log = log + ["try"]
} catch err {
    log = log + ["catch"]
} finally {
    log = log + ["finally"]
}
print(log[0])
print(log[1])
"""
        self.assertEqual(run_program(src), ["try", "finally"])

    def test_try_catch_without_finally_unchanged(self):
        """Existing try/catch behavior is unaffected."""
        src = """
try {
    throw "x"
} catch e {
    print("caught")
}
print("after")
"""
        self.assertEqual(run_program(src), ["caught", "after"])

    def test_finally_in_function_multiple_calls(self):
        src = """
fn cleanup(x) {
    try {
        return x * 2
    } catch err {
        return 0
    } finally {
        print("done")
    }
}
print(cleanup(3))
print(cleanup(5))
"""
        self.assertEqual(run_program(src), ["done", "6.0", "done", "10.0"])
