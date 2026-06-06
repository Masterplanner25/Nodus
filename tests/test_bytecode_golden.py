"""Golden opcode-sequence tests for core language constructs (#114).

Catches unintentional compiler output regressions.  Fixtures live in
tests/fixtures/bytecode/<name>.json as JSON arrays of opcode-name strings
(address-independent — positions shift as code grows but opcode sequences
should be stable across refactors that don't touch the compiler).

Re-generate all goldens:
    NODUS_UPDATE_GOLDEN=1 python -m pytest tests/test_bytecode_golden.py -q
"""

import json
import os
import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.compiler.compiler import normalize_bytecode  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "bytecode")
_UPDATE = os.environ.get("NODUS_UPDATE_GOLDEN") == "1"


def _compile_opcodes(src: str) -> list[str]:
    loader = ModuleLoader(project_root=None)
    code, _fns, _locs = loader.compile_only(src, module_name="golden.nd")
    _version, instrs = normalize_bytecode(code)
    return [instr[0] for instr in instrs]


def _assert_golden(name: str, actual: list[str]) -> None:
    path = os.path.join(_FIXTURES, f"{name}.json")
    if _UPDATE:
        os.makedirs(_FIXTURES, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(actual, fh, indent=2)
        return
    assert os.path.exists(path), (
        f"Golden fixture missing: {path}. "
        "Run with NODUS_UPDATE_GOLDEN=1 to generate."
    )
    with open(path, encoding="utf-8") as fh:
        expected = json.load(fh)
    if actual != expected:
        added = set(actual) - set(expected)
        removed = set(expected) - set(actual)
        detail = []
        if added:
            detail.append(f"new opcodes: {sorted(added)}")
        if removed:
            detail.append(f"removed opcodes: {sorted(removed)}")
        if len(actual) != len(expected):
            detail.append(f"length {len(expected)} → {len(actual)}")
        raise AssertionError(
            f"Opcode sequence diverged from golden ({name}). "
            + ("; ".join(detail) or "order changed")
            + f"\nExpected: {expected}\n  Actual: {actual}"
        )


class GoldenFunctionTests(unittest.TestCase):
    """Function definition and call — verifies FRAME_SIZE/STORE_ARG/CALL opcodes."""

    def test_simple_function_add(self):
        src = "fn add(a, b) { return a + b }\nlet r = add(1, 2)"
        _assert_golden("function_add", _compile_opcodes(src))

    def test_recursive_function(self):
        src = """
fn fact(n) {
    if (n <= 1) { return 1 }
    return n * fact(n - 1)
}
let r = fact(5)
"""
        _assert_golden("function_recursive", _compile_opcodes(src))


class GoldenCoroutineTests(unittest.TestCase):
    """Coroutine creation and yield — verifies YIELD/COROUTINE opcodes."""

    def test_coroutine_yield_sequence(self):
        src = """
let gen = coroutine(fn() {
    yield 1
    yield 2
    yield 3
})
let c = spawn(gen)
"""
        _assert_golden("coroutine_yield", _compile_opcodes(src))


class GoldenWorkflowTests(unittest.TestCase):
    """Workflow with state variable — verifies workflow/state compiler output."""

    def test_workflow_with_state(self):
        src = """
workflow demo {
    state counter = 0

    step a {
        counter = counter + 1
        return counter
    }

    step b after a {
        counter = counter + 10
        return counter
    }
}
let result = run_workflow(demo)
"""
        _assert_golden("workflow_with_state", _compile_opcodes(src))


class GoldenGoalTests(unittest.TestCase):
    """Goal DSL — verifies goal lowering produces the expected opcode pattern."""

    def test_goal_simple(self):
        src = """
goal task {
    step compute {
        return 42
    }
}
let result = run_goal(task)
"""
        _assert_golden("goal_simple", _compile_opcodes(src))

    def test_goal_with_dependency(self):
        src = """
goal pipeline {
    step fetch { return "data" }
    step process after fetch { return fetch }
}
let result = run_goal(pipeline)
"""
        _assert_golden("goal_with_dependency", _compile_opcodes(src))


class GoldenTryCatchFinallyTests(unittest.TestCase):
    """Exception handling — verifies PUSH_HANDLER/POP_HANDLER/FINALLY opcodes."""

    def test_try_catch(self):
        src = """
try {
    let x = 1
} catch e {
    let y = 2
}
"""
        _assert_golden("try_catch", _compile_opcodes(src))

    def test_try_catch_finally(self):
        src = """
let result = nil
try {
    throw "oops"
} catch e {
    result = "caught"
} finally {
    result = result
}
"""
        _assert_golden("try_catch_finally", _compile_opcodes(src))


class GoldenChannelTests(unittest.TestCase):
    """Channel send/recv — verifies channel builtin call pattern."""

    def test_channel_send_recv(self):
        src = """
let ch = channel()
send(ch, 42)
let val = recv(ch)
"""
        _assert_golden("channel_send_recv", _compile_opcodes(src))


if __name__ == "__main__":
    unittest.main()
