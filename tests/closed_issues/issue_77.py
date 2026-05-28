"""Closed-issue test for #77: nodus workflow run --help shows help (BUG-V31E-03)."""

import subprocess
from pathlib import Path


def _nodus_exe():
    return str(Path("C:/dev/Coding Language/.venv/Scripts/nodus.exe"))


def _run_nodus(*args):
    env = {"PYTHONPATH": "C:/dev/Coding Language/src"}
    import os
    env.update(os.environ)
    result = subprocess.run(
        [_nodus_exe()] + list(args),
        capture_output=True, text=True, env=env
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
