"""Closed-issue test for #293: doc-vs-code gate restored to green.

Guards both halves of the fix:
  1. Contract phase imports HandlerContract/VALID_EFFECTS from `nodus_lang_schema`
     (the in-tree ABI package post NAME-COL-001) rather than the stale
     `nodus_schema` name, which now resolves to the unrelated standalone package.
  2. The four real doc-example bugs that were fixed now parse and run:
       - RUNTIME.md used the reserved word `record` as a variable name.
       - standard-library.md std:time example read a non-existent `now.unix`
         field and used `"YYYY-MM-DD"` parse tokens.
       - STYLE_GUIDE.md showed unquoted `import std:strings`.
"""

import os
import sys

# closes: #293

sys.path.insert(0, "C:/dev/Coding Language")  # noqa: E402
sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

from tools.nodus_gate.contracts_phase import run_contracts_phase  # noqa: E402
from tools.nodus_gate.runtime_phase import _run_block_with_timeout  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_contract_phase_passes():
    """HandlerContract resolves from nodus_lang_schema and all 6 checks pass."""
    result = run_contracts_phase(_REPO_ROOT)
    assert result.checks_run == 6, f"expected 6 contract checks, ran {result.checks_run}"
    assert not result.findings, "; ".join(f.message for f in result.findings)


def test_runtime_record_variable_snippet():
    """RUNTIME.md: `record` is reserved; the fixed example uses `let point`."""
    _, _, err = _run_block_with_timeout("let point = {x: 10, y: 20}\nprint(point.x)", 5000)
    assert err is None, err


def test_time_epoch_ms_and_parse_tokens_snippet():
    """standard-library.md std:time: epoch_ms field + yyyy-MM-dd parse tokens run."""
    src = (
        'import "std:time" as time\n'
        "let now = time.now()\n"
        "print(now.epoch_ms)\n"
        'let dt = time.parse("2026-01-15", "yyyy-MM-dd")\n'
        "let diff = time.diff(dt, now)\n"
    )
    _, _, err = _run_block_with_timeout(src, 5000)
    assert err is None, err


def test_style_guide_quoted_import_snippet():
    """STYLE_GUIDE.md: quoted+aliased stdlib imports parse and resolve."""
    src = (
        'import "std:strings" as strings\n'
        "print(strings.trim(strings.lower(\" Alice \")))\n"
    )
    stdout, _, err = _run_block_with_timeout(src, 5000)
    assert err is None, err
    assert "alice" in stdout


if __name__ == "__main__":
    test_contract_phase_passes()
    test_runtime_record_variable_snippet()
    test_time_epoch_ms_and_parse_tokens_snippet()
    test_style_guide_quoted_import_snippet()
    print("All #293 tests pass")
