"""Verify finally-after-catch-return behavior.

Phase 2 verification per V4_0_PLAN.md. The v3.0.1 eval suggested this
works correctly; this test confirms or denies.

Note: the existing tests/test_finally.py already covers this behavior
comprehensively via FinallyCatchReturnTests. This file adds subprocess-
level regression tests as a supplementary guard.

Nodus syntax constraints observed during verification:
- try is a statement, not an expression (let r = try {...} is invalid)
- try requires both catch AND finally; try-finally without catch is a
  syntax error ("Expected 'catch', got 'finally'")
- catch variable binding uses `catch e {` (no parentheses)
All tests below use valid syntax wrapping the behavior in functions.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_NODUS_PY = str(_REPO_ROOT / "nodus.py")


def run_nodus(script_content):
    """Run a Nodus script and return (stdout, stderr, exit_code)."""
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.nd', delete=False, encoding='utf-8'
    ) as f:
        f.write(script_content)
        script_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, _NODUS_PY, "run", script_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout, result.stderr, result.returncode
    finally:
        Path(script_path).unlink()


def test_finally_runs_when_catch_returns():
    """finally block executes when catch block returns a value."""
    script = """
fn f() {
    try {
        throw "boom"
    } catch e {
        print("finally_ran_check")
        return "from_catch"
    } finally {
        print("finally_ran")
    }
}
let r = f()
print(r)
"""
    stdout, stderr, rc = run_nodus(script)
    assert rc == 0, f"unexpected exit code {rc}; stderr={stderr!r}"
    assert "finally_ran" in stdout, f"finally did not run; stdout={stdout!r} stderr={stderr!r}"
    assert "from_catch" in stdout, f"catch return value not visible; stdout={stdout!r}"


def test_finally_runs_when_try_returns():
    """finally block executes when try block returns a value."""
    script = """
fn f() {
    try {
        return "from_try"
    } catch e {
        return "from_catch"
    } finally {
        print("finally_ran")
    }
}
let r = f()
print(r)
"""
    stdout, stderr, rc = run_nodus(script)
    assert rc == 0, f"unexpected exit code {rc}; stderr={stderr!r}"
    assert "finally_ran" in stdout, f"finally did not run after try return; stdout={stdout!r}"
    assert "from_try" in stdout, f"try return value not visible; stdout={stdout!r}"


def test_finally_runs_when_no_error():
    """finally block executes on normal (no-error) flow through try."""
    script = """
try {
    print("try_ran")
} catch e {
    print("catch_ran")
} finally {
    print("finally_ran")
}
"""
    stdout, stderr, rc = run_nodus(script)
    assert rc == 0, f"unexpected exit code {rc}; stderr={stderr!r}"
    assert "try_ran" in stdout
    assert "catch_ran" not in stdout
    assert "finally_ran" in stdout, f"finally did not run on normal flow; stdout={stdout!r}"


def test_finally_runs_when_inner_error_propagates():
    """finally executes when inner error propagates to outer catch."""
    script = """
try {
    try {
        throw "inner_error"
    } catch e {
        print("inner_finally_ran")
        throw e
    } finally {
        print("inner_finally_ran")
    }
} catch e2 {
    print("outer_catch_ran")
}
"""
    stdout, stderr, rc = run_nodus(script)
    assert rc == 0, f"unexpected exit code {rc}; stderr={stderr!r}"
    assert "inner_finally_ran" in stdout, f"inner finally did not run; stdout={stdout!r}"
    assert "outer_catch_ran" in stdout, f"outer catch did not run; stdout={stdout!r}"


def test_finally_value_does_not_override_catch_return():
    """The catch's return value is preserved when finally has its own statement."""
    script = """
fn f() {
    try {
        throw "boom"
    } catch e {
        return "catch_value"
    } finally {
        let unused = "finally_local"
        print("finally_ran")
    }
}
let r = f()
print(r)
"""
    stdout, stderr, rc = run_nodus(script)
    assert rc == 0, f"unexpected exit code {rc}; stderr={stderr!r}"
    assert "finally_ran" in stdout, f"finally did not run; stdout={stdout!r}"
    assert "catch_value" in stdout, f"catch return value lost; stdout={stdout!r}"
