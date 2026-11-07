"""Every file in tests/closed_issues/ must run under a plain `pytest`.

They are named `issue_<N>.py` because `nodus_gate --closed-issues` looks them up
by that name, and pytest's default pattern is `test_*.py`, so for months plain
`pytest` skipped the directory. The gate names a file explicitly, but only for
issues in the CHANGELOG section it was asked about, so an issue from an earlier
release was never run again. Two of them rotted unseen: one stopped importing
three days after it was written, and one failed for two months.

This lives outside the directory on purpose. A guard inside it would stop running
at the same moment it stopped being true.
"""

from fnmatch import fnmatch
from pathlib import Path

_CLOSED_ISSUES = Path(__file__).parent / "closed_issues"


def test_every_closed_issue_file_matches_a_collection_pattern(request):
    patterns = request.config.getini("python_files")
    files = sorted(_CLOSED_ISSUES.glob("*.py"))
    assert files, f"found no closed-issue files in {_CLOSED_ISSUES}"
    uncollected = [
        path.name
        for path in files
        if not any(fnmatch(path.name, pattern) for pattern in patterns)
    ]
    assert not uncollected, (
        f"plain pytest would skip {uncollected}: python_files is {patterns}. "
        "Name the file issue_<N>.py, or keep issue_*.py in pyproject.toml."
    )
