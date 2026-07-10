"""Closed-issue test for #302: the doc-vs-code gate runs in CI.

Guards the enforcement itself — if the gate step is removed from the CI workflow,
the gate could again ship red undetected (the #293 regression). A grep-level check
is intentional: it fails loudly the moment the invocation disappears.
"""

from pathlib import Path

# closes: #302

_REPO_ROOT = Path(__file__).parents[2]


def test_ci_workflow_invokes_the_full_doc_vs_code_gate():
    ci = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "tools.nodus_gate.cli --all" in ci, (
        "CI workflow must invoke the full doc-vs-code gate "
        "(python -m tools.nodus_gate.cli --all) so it cannot ship red undetected."
    )
