"""Regression tests for doc 13: err record location fields.

All err records now have path, line, column, stack, and origin fields.
- Stdlib-returned errs: augmented in call_builtin with origin="stdlib"
- VM-thrown errs: origin="vm" set in build_runtime_error
- User-thrown errs: origin="user" set in _op_throw
"""
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_NODUS_PY = str(_REPO_ROOT / "nodus.py")


def run_nodus(script_content):
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.nd', delete=False, encoding='utf-8'
    ) as f:
        f.write(script_content)
        script_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, _NODUS_PY, "run", script_path],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout, result.stderr, result.returncode
    finally:
        Path(script_path).unlink()


def test_stdlib_err_has_path():
    """Stdlib-returned err record has path field populated."""
    stdout, stderr, rc = run_nodus("""
import "std:json" as json
fn check() {
    let e = json.parse("{bad")
    if (type(e) == "error") {
        print("has_path:" + str(e.path != nil))
        print("origin:" + e.origin)
    }
}
check()
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "has_path:true" in stdout, f"stdout={stdout!r}"
    assert "origin:stdlib" in stdout, f"stdout={stdout!r}"


def test_stdlib_err_has_line_and_column():
    """Stdlib err record has line and column populated from call site."""
    stdout, stderr, rc = run_nodus("""
import "std:json" as json
fn check() {
    let e = json.parse("{bad")
    if (type(e) == "error") {
        print("has_line:" + str(e.line != nil))
        print("has_col:" + str(e.column != nil))
    }
}
check()
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "has_line:true" in stdout, f"stdout={stdout!r}"
    assert "has_col:true" in stdout, f"stdout={stdout!r}"


def test_stdlib_err_has_stack():
    """Stdlib err record has stack field (list)."""
    stdout, stderr, rc = run_nodus("""
import "std:json" as json
fn check() {
    let e = json.parse("{bad")
    if (type(e) == "error") {
        print("stack_type:" + type(e.stack))
    }
}
check()
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "stack_type:list" in stdout, f"stdout={stdout!r}"


def test_vm_thrown_err_has_origin_vm():
    """VM-thrown err (type error) has origin: vm."""
    stdout, stderr, rc = run_nodus("""
try {
    let x = 1.0 + "x"
} catch e {
    print("origin:" + e.origin)
}
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "origin:vm" in stdout, f"stdout={stdout!r}"


def test_user_thrown_err_has_origin_user():
    """User throw produces err with origin: user."""
    stdout, stderr, rc = run_nodus("""
try {
    throw "boom"
} catch e {
    print("origin:" + e.origin)
    print("has_path:" + str(e.path != nil))
}
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "origin:user" in stdout, f"stdout={stdout!r}"
    assert "has_path:true" in stdout, f"stdout={stdout!r}"


def test_user_thrown_record_has_origin_user():
    """Structured throw also gets origin: user."""
    stdout, stderr, rc = run_nodus("""
try {
    throw {kind: "my_error", message: "test_msg"}
} catch e {
    print("origin:" + e.origin)
    print("kind:" + e.kind)
}
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "origin:user" in stdout, f"stdout={stdout!r}"
    assert "kind:thrown" in stdout, f"stdout={stdout!r}"


def test_stdlib_err_stack_nonempty_in_nested_call():
    """Err stack has entries when stdlib call is inside nested functions."""
    stdout, stderr, rc = run_nodus("""
import "std:json" as json
fn inner() {
    return json.parse("{bad")
}
fn outer() {
    return inner()
}
fn check() {
    let e = outer()
    if (type(e) == "error") {
        print("stack_len:" + str(len(e.stack)))
    }
}
check()
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "stack_len:" in stdout, f"stdout={stdout!r}"
    parts = [line for line in stdout.splitlines() if line.startswith("stack_len:")]
    assert parts, f"no stack_len line in stdout={stdout!r}"
    n = int(float(parts[0].split(":")[1]))
    assert n > 0, f"expected non-empty stack, got {n}"


def test_vm_err_has_all_fields():
    """VM-thrown err has all six location fields present."""
    stdout, stderr, rc = run_nodus("""
try {
    let x = 1.0 + "x"
} catch e {
    print("path:" + str(e.path != nil))
    print("line:" + str(e.line != nil))
    print("col:" + str(e.column != nil))
    print("stack:" + type(e.stack))
    print("origin:" + e.origin)
}
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "path:true" in stdout
    assert "line:true" in stdout
    assert "col:true" in stdout
    assert "stack:list" in stdout
    assert "origin:vm" in stdout
