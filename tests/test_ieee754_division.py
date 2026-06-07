"""Regression tests for doc 09: IEEE 754 float division."""
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


def test_float_div_by_zero_raises():
    stdout, stderr, rc = run_nodus("print(str(1.0 / 0.0))")
    assert rc != 0, f"expected runtime error, got exit {rc}; stdout={stdout!r}"
    assert "zero" in stderr.lower() or "math" in stderr.lower()


def test_float_neg_div_by_zero_raises():
    stdout, stderr, rc = run_nodus("print(str(-1.0 / 0.0))")
    assert rc != 0, f"expected runtime error, got exit {rc}; stdout={stdout!r}"


def test_float_zero_div_by_zero_raises():
    stdout, stderr, rc = run_nodus("print(str(0.0 / 0.0))")
    assert rc != 0, f"expected runtime error, got exit {rc}; stdout={stdout!r}"


def test_float_mod_by_zero_raises():
    stdout, stderr, rc = run_nodus("print(str(5.0 % 0.0))")
    assert rc != 0, f"expected runtime error, got exit {rc}; stdout={stdout!r}"


def test_int_div_by_zero_raises():
    stdout, stderr, rc = run_nodus("let r = 1i / 0i\nprint(r)")
    assert rc != 0, f"expected runtime error, got exit {rc}; stdout={stdout!r}"
    assert "zero" in stderr.lower() or "math" in stderr.lower()


def test_int_mod_by_zero_raises():
    stdout, stderr, rc = run_nodus("let r = 5i % 0i\nprint(r)")
    assert rc != 0, f"expected runtime error, got exit {rc}; stdout={stdout!r}"


def test_mixed_int_float_div_by_zero_raises():
    """int / 0.0 and 1.0 / 0i both raise a math error."""
    _, stderr1, rc1 = run_nodus("print(str(1i / 0.0))")
    _, stderr2, rc2 = run_nodus("print(str(1.0 / 0i))")
    assert rc1 != 0, f"expected error for 1i/0.0, got exit {rc1}"
    assert rc2 != 0, f"expected error for 1.0/0i, got exit {rc2}"


def test_nan_not_equal_to_itself():
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.nan == math.nan))
print(str(math.nan != math.nan))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    lines = [line for line in stdout.splitlines() if line.strip()]
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
    lines = [line for line in stdout.splitlines() if line.strip()]
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
    lines = [line for line in stdout.splitlines() if line.strip()]
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
    lines = [line for line in stdout.splitlines() if line.strip()]
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
    lines = [line for line in stdout.splitlines() if line.strip()]
    assert lines[0] == "true"
    assert lines[1] == "true"
    assert lines[2] == "true"


def test_int_div_by_zero_err_has_message():
    """Integer division-by-zero raises a runtime error with a math message."""
    stdout, stderr, rc = run_nodus("let r = 1i / 0i\nprint(r)")
    assert rc != 0, f"expected runtime error, got exit {rc}; stdout={stdout!r}"
    assert "zero" in stderr.lower() or "math" in stderr.lower()


def test_int_functions_are_always_finite():
    """is_nan/is_inf always false for ints; is_finite always true."""
    stdout, stderr, rc = run_nodus("""
import "std:math" as math
print(str(math.is_nan(5i)))
print(str(math.is_inf(5i)))
print(str(math.is_finite(5i)))
""")
    assert rc == 0, f"exit {rc}; stderr={stderr!r}"
    lines = [line for line in stdout.splitlines() if line.strip()]
    assert lines[0] == "false"
    assert lines[1] == "false"
    assert lines[2] == "true"
