"""Regression tests for doc 09: IEEE 754 float division."""
import subprocess
import tempfile
import os
from pathlib import Path

NODUS_BIN = "C:/dev/Coding Language/.venv/Scripts/nodus.exe"
SRC_PATH = "C:/dev/Coding Language/src"


def run_nodus(script_content):
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.nd', delete=False, encoding='utf-8'
    ) as f:
        f.write(script_content)
        script_path = f.name
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = SRC_PATH
        result = subprocess.run(
            [NODUS_BIN, "run", script_path],
            capture_output=True, text=True, env=env, timeout=10
        )
        return result.stdout, result.stderr, result.returncode
    finally:
        Path(script_path).unlink()


def test_float_div_by_zero_returns_inf():
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(1.0 / 0.0))
print(str(math.is_inf(1.0 / 0.0)))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "inf" in stdout
    assert "true" in stdout


def test_float_neg_div_by_zero_returns_neg_inf():
    stdout, stderr, rc = run_nodus("""
print(str(-1.0 / 0.0))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "-inf" in stdout


def test_float_zero_div_by_zero_returns_nan():
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.is_nan(0.0 / 0.0)))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "true" in stdout


def test_float_mod_by_zero_returns_nan():
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.is_nan(5.0 % 0.0)))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "true" in stdout


def test_int_div_by_zero_returns_err_record():
    stdout, stderr, rc = run_nodus("""
let r = 1i / 0i
print("type:" + type(r))
print("kind:" + r.kind)
print("origin:" + r.origin)
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "type:error" in stdout
    assert "kind:math_error" in stdout
    assert "origin:vm" in stdout


def test_int_mod_by_zero_returns_err_record():
    stdout, stderr, rc = run_nodus("""
let r = 5i % 0i
print("type:" + type(r))
print("kind:" + r.kind)
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "type:error" in stdout
    assert "kind:math_error" in stdout


def test_mixed_int_float_div_by_zero_returns_inf():
    """int / 0.0 and 1.0 / 0i both yield inf via IEEE 754 coercion."""
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.is_inf(1i / 0.0)))
print(str(math.is_inf(1.0 / 0i)))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    lines = [l for l in stdout.splitlines() if l.strip()]
    assert lines[0] == "true"
    assert lines[1] == "true"


def test_nan_not_equal_to_itself():
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.nan == math.nan))
print(str(math.nan != math.nan))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    lines = [l for l in stdout.splitlines() if l.strip()]
    assert lines[0] == "false"
    assert lines[1] == "true"


def test_math_constants():
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.is_nan(math.nan)))
print(str(math.is_inf(math.infinity)))
print(str(math.is_inf(math.neg_infinity)))
print(str(math.infinity > 1000000000.0))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    lines = [l for l in stdout.splitlines() if l.strip()]
    assert lines[0] == "true"
    assert lines[1] == "true"
    assert lines[2] == "true"
    assert lines[3] == "true"


def test_is_nan_is_inf_is_finite():
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.is_nan(1.0)))
print(str(math.is_inf(1.0)))
print(str(math.is_finite(1.0)))
print(str(math.is_finite(math.infinity)))
print(str(math.is_finite(math.nan)))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    lines = [l for l in stdout.splitlines() if l.strip()]
    assert lines[0] == "false"
    assert lines[1] == "false"
    assert lines[2] == "true"
    assert lines[3] == "false"
    assert lines[4] == "false"


def test_nan_comparison_with_non_nan():
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.nan > 1.0))
print(str(math.nan < 1.0))
print(str(math.nan == 1.0))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    lines = [l for l in stdout.splitlines() if l.strip()]
    assert lines[0] == "false"
    assert lines[1] == "false"
    assert lines[2] == "false"


def test_inf_arithmetic():
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.is_inf(math.infinity + 1.0)))
print(str(math.is_nan(math.infinity - math.infinity)))
print(str(math.is_nan(math.nan + 1.0)))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    lines = [l for l in stdout.splitlines() if l.strip()]
    assert lines[0] == "true"
    assert lines[1] == "true"
    assert lines[2] == "true"


def test_int_div_by_zero_err_has_location_fields():
    """Integer division-by-zero err record has doc 13 location fields."""
    stdout, stderr, rc = run_nodus("""
let r = 1i / 0i
print("has_path:" + str(r.path != nil))
print("has_line:" + str(r.line != nil))
print("stack_type:" + type(r.stack))
print("origin:" + r.origin)
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    assert "has_path:true" in stdout
    assert "has_line:true" in stdout
    assert "stack_type:list" in stdout
    assert "origin:vm" in stdout


def test_int_functions_are_always_finite():
    """is_nan/is_inf always false for ints; is_finite always true."""
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.is_nan(5i)))
print(str(math.is_inf(5i)))
print(str(math.is_finite(5i)))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    lines = [l for l in stdout.splitlines() if l.strip()]
    assert lines[0] == "false"
    assert lines[1] == "false"
    assert lines[2] == "true"
