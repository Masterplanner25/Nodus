"""Regression tests for doc 14: len() and related functions return int."""
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


def test_len_string_returns_int():
    stdout, stderr, rc = run_nodus('print(type(len("hello")))\nprint(str(len("hello")))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "int" in stdout
    assert "5" in stdout


def test_len_list_returns_int():
    stdout, stderr, rc = run_nodus("print(type(len([1, 2, 3])))\n")
    assert rc == 0, f"stderr={stderr!r}"
    assert "int" in stdout


def test_len_map_returns_int():
    stdout, stderr, rc = run_nodus('print(type(len({"a": 1, "b": 2})))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "int" in stdout


def test_count_string_returns_int():
    stdout, stderr, rc = run_nodus('print(type(count("hello world", "o")))\nprint(str(count("hello world", "o")))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "int" in stdout
    assert "2" in stdout


def test_count_list_returns_int():
    stdout, stderr, rc = run_nodus("print(str(count([1, 2, 1, 1], 1)))\n")
    assert rc == 0, f"stderr={stderr!r}"
    assert "3" in stdout


def test_index_of_string_returns_int():
    stdout, stderr, rc = run_nodus('print(type(index_of("hello", "ll")))\nprint(str(index_of("hello", "ll")))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "int" in stdout
    assert "2" in stdout


def test_index_of_string_not_found_returns_nil():
    stdout, stderr, rc = run_nodus('print(str(index_of("hello", "xyz")))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "nil" in stdout


def test_index_of_list_returns_int():
    stdout, stderr, rc = run_nodus("print(str(index_of([1, 2, 3], 2)))\n")
    assert rc == 0, f"stderr={stderr!r}"
    assert "1" in stdout


def test_index_of_list_not_found_returns_nil():
    stdout, stderr, rc = run_nodus("print(str(index_of([1, 2, 3], 99)))\n")
    assert rc == 0, f"stderr={stderr!r}"
    assert "nil" in stdout


def test_last_index_of_string_returns_int():
    stdout, stderr, rc = run_nodus('print(str(last_index_of("hello", "l")))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "3" in stdout


def test_last_index_of_not_found_returns_nil():
    stdout, stderr, rc = run_nodus('print(str(last_index_of("hello", "z")))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "nil" in stdout


def test_range_one_arg_produces_ints():
    stdout, stderr, rc = run_nodus("""
let r = range(5)
print(str(len(r)))
print(type(r[0]))
""")
    assert rc == 0, f"stderr={stderr!r}"
    assert "5" in stdout
    assert "int" in stdout


def test_range_two_arg():
    stdout, stderr, rc = run_nodus("""
let r = range(2, 5)
print(str(len(r)))
print(str(r[0]))
""")
    assert rc == 0, f"stderr={stderr!r}"
    assert "3" in stdout
    assert "2" in stdout


def test_range_three_arg():
    stdout, stderr, rc = run_nodus("""
let r = range(0, 10, 2)
print(str(len(r)))
""")
    assert rc == 0, f"stderr={stderr!r}"
    assert "5" in stdout


def test_range_in_for_each():
    stdout, stderr, rc = run_nodus("""
let total = 0i
for x in range(5) {
    total = total + x
}
print(str(total))
""")
    assert rc == 0, f"stderr={stderr!r}"
    assert "10" in stdout


def test_math_floor_returns_int():
    stdout, stderr, rc = run_nodus('import "std:math" as math\nprint(type(math.floor(2.9)))\nprint(str(math.floor(2.9)))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "int" in stdout
    assert "2" in stdout


def test_math_ceil_returns_int():
    stdout, stderr, rc = run_nodus('import "std:math" as math\nprint(type(math.ceil(2.1)))\nprint(str(math.ceil(2.1)))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "int" in stdout
    assert "3" in stdout


def test_math_round_returns_int():
    stdout, stderr, rc = run_nodus('import "std:math" as math\nprint(type(math.round(2.5)))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "int" in stdout


def test_len_arithmetic_with_int_literal():
    """len(x) + 1i produces int (both operands are int)."""
    stdout, stderr, rc = run_nodus('print(type(len([1,2,3]) + 1i))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "int" in stdout


def test_len_arithmetic_with_float_literal():
    """len(x) / 2.0 produces float (mixed int+float division)."""
    stdout, stderr, rc = run_nodus('print(type(len([1,2,3,4]) / 2.0))\n')
    assert rc == 0, f"stderr={stderr!r}"
    assert "float" in stdout
