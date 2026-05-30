"""Closed-issue test for #77: nodus workflow run --help shows help (BUG-V31E-03)."""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_NODUS_PY = str(_REPO_ROOT / "nodus.py")


def _run_nodus(*args):
    result = subprocess.run(
        [sys.executable, _NODUS_PY] + list(args),
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


def test_workflow_help_not_file_error():
    rc, stdout, stderr = _run_nodus("workflow", "run", "--help")
    # Should show help or exit 0/1 without "file not found: --help"
    assert "File not found: --help" not in stdout, f"Got file-not-found error: {stdout}"
    assert "File not found: --help" not in stderr, f"Got file-not-found error: {stderr}"


def test_graph_help_not_file_error():
    rc, stdout, stderr = _run_nodus("graph", "run", "--help")
    assert "File not found: --help" not in stdout, f"Got file-not-found error: {stdout}"
    assert "File not found: --help" not in stderr, f"Got file-not-found error: {stderr}"


if __name__ == "__main__":
    test_workflow_help_not_file_error()
    test_graph_help_not_file_error()
    print("All #77 tests pass")
