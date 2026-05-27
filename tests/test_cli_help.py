"""Regression tests for --help on workflow run and graph run subcommands.

Phase 2 fix for BUG-V31E-03 (#77): nodus workflow run --help and
nodus graph run --help were treating --help as a script filename and
producing "File not found: --help" instead of help text.
"""
import subprocess
import os

NODUS_BIN = "C:/dev/Coding Language/.venv/Scripts/nodus.exe"
SRC_PATH = "C:/dev/Coding Language/src"


def run_cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = SRC_PATH
    return subprocess.run(
        [NODUS_BIN, *args], capture_output=True, text=True, env=env, timeout=5
    )


def test_workflow_run_help():
    result = run_cli("workflow", "run", "--help")
    assert result.returncode == 0, \
        f"workflow run --help exited {result.returncode}; stderr={result.stderr!r}"
    combined = result.stdout + result.stderr
    assert "usage" in combined.lower(), \
        f"no help text shown; stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "File not found" not in result.stdout, \
        "regression: --help still being treated as filename"


def test_workflow_run_short_help():
    result = run_cli("workflow", "run", "-h")
    assert result.returncode == 0, \
        f"workflow run -h exited {result.returncode}; stderr={result.stderr!r}"
    assert "File not found" not in result.stdout, \
        "regression: -h still being treated as filename"


def test_graph_run_help():
    result = run_cli("graph", "run", "--help")
    assert result.returncode == 0, \
        f"graph run --help exited {result.returncode}; stderr={result.stderr!r}"
    combined = result.stdout + result.stderr
    assert "usage" in combined.lower(), \
        f"no help text shown; stdout={result.stdout!r}"
    assert "File not found" not in result.stdout, \
        "regression: --help still being treated as filename"


def test_graph_run_short_help():
    result = run_cli("graph", "run", "-h")
    assert result.returncode == 0, \
        f"graph run -h exited {result.returncode}; stderr={result.stderr!r}"
    assert "File not found" not in result.stdout, \
        "regression: -h still being treated as filename"
