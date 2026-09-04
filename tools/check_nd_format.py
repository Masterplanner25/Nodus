"""Is every `.nd` file formatted? One answer, for CI and the pre-commit hook (#741).

Three things used to answer *"which `.nd` files get format-checked"*, and no two
agreed:

- **CI** globbed the working tree with `find`, excluding `./.venv/` and nothing
  else shaped like it — so run anywhere but CI it also swept every other
  virtualenv, 301 files instead of 61 (#739).
- **The pre-commit hook** claimed in its own header to run "the same command as
  CI" and omitted all four of CI's exclusions, so it blocked commits on
  `tests/fixtures/fmt/`, where an `_input.nd` is deliberately unformatted.
- **`tools/list_fmt_targets.py`** carried a third list, excluded no virtualenv at
  all, and was dead code — nothing had called it since the initial commit.

The duplication is the bug. This module is the single answer, and the hook and CI
both call it.

**It does not reimplement "is this file formatted".** That question belongs to
`nodus fmt --check`, and a second implementation of it would be the same defect
one layer down — so `_format_file` is imported and used directly. The two cannot
disagree about encoding, line endings, or what a syntax error means, because
there is only one of them.

Running in one process rather than one per file is the incidental win, and it is
large: `xargs -I {}` paid a fresh interpreter startup per file, 5m41s for 61
files. Here the formatter is imported once.

    python -m tools.check_nd_format            # every tracked .nd file (CI)
    python -m tools.check_nd_format --staged   # staged files only (the hook)
"""

from __future__ import annotations

import os
import subprocess
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

from nodus.cli.cli import _format_file  # noqa: E402

#: Paths that are `.nd` files but must not be format-checked. Named once, here,
#: because it being named in several places with different contents is the
#: entire reason this module exists.
#:
#: `tests/fixtures/fmt/` holds formatter fixtures: an `_input.nd` is unformatted
#: on purpose — a fixture whose input is already formatted tests nothing — and a
#: `_keep_expected.nd` is the output of a non-default mode, which the default
#: checker naturally disagrees with.
EXCLUDED_PREFIXES: tuple[str, ...] = ("tests/fixtures/fmt/",)


def _git(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{result.stderr}")
    return [line for line in result.stdout.splitlines() if line]


def targets(staged: bool = False) -> list[str]:
    """The `.nd` files to check, as repo-relative paths.

    Both modes read the list from **git** rather than the filesystem. That is
    what makes the answer the same on every machine: gitignored paths — every
    virtualenv, `tmp_demo`, the caches — are absent without having to be
    enumerated, so a tenth virtualenv cannot quietly rejoin the sweep.
    """
    if staged:
        # ACM: added, copied, modified. A deleted file has nothing to check.
        listed = _git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    else:
        listed = _git("ls-files")
    return sorted(
        path
        for path in listed
        if path.endswith(".nd")
        and not path.startswith(EXCLUDED_PREFIXES)
    )


def check(paths: list[str]) -> list[str]:
    """Return the paths that are not formatted, reporting each as it is found."""
    unformatted = []
    for path in paths:
        absolute = os.path.join(_REPO_ROOT, path)
        if not os.path.isfile(absolute):
            continue  # staged then removed from the working tree
        if _format_file(absolute, check_only=True) != 0:
            unformatted.append(path)
    return unformatted


def main(argv: list[str]) -> int:
    staged = "--staged" in argv[1:]
    paths = targets(staged=staged)
    if not paths:
        print("No .nd files to check.")
        return 0

    unformatted = check(paths)
    scope = "staged" if staged else "tracked"
    if not unformatted:
        print(f"All {len(paths)} {scope} .nd file(s) are formatted.")
        return 0

    print()
    print(f"{len(unformatted)} of {len(paths)} {scope} .nd file(s) are not formatted:")
    for path in unformatted:
        print(f"  {path}")
    print()
    print("Run:  python nodus.py fmt " + " ".join(unformatted))
    if staged:
        print("Then re-stage the files and commit again.")
    print()
    # `nodus.exe` is whatever release was last installed into `.venv`; CI loads
    # the formatter from `src/`. Using it writes a format the check rejects.
    print("Do NOT use nodus.exe or a bare 'nodus fmt' — those resolve to the")
    print("installed package, which may be stale. Always 'python nodus.py fmt'.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
