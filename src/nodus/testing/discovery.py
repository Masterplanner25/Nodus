"""Test file discovery for the Nodus test runner."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

#: What `nodus test` considers a test file.  Named once because it was
#: answered in three voices and one of them was wrong (#794): the matcher
#: below, the "no files found" message in `nodus.testing.cli`, and
#: `nodus test --help`, which promised `test_*.nd` as well.  It never worked
#: -- a file named that way was invisible both under a directory scan and
#: when named on the command line.  `tests/test_cli_command_table.py` holds
#: the help to this tuple.
TEST_FILE_PATTERNS: tuple[str, ...] = ("*_test.nd",)


def is_test_file(name: str) -> bool:
    """Does this basename name a test file?"""
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in TEST_FILE_PATTERNS)


def describe_test_patterns() -> str:
    """`*_test.nd` -- for an error message that must not drift from the rule."""
    return " or ".join(TEST_FILE_PATTERNS)


def discover_test_files(path: str) -> list[str]:
    """Return the sorted test files under `path` (recursive)."""
    p = Path(path)
    if p.is_file():
        return [str(p)] if is_test_file(p.name) else []
    results = []
    for root, dirs, files in os.walk(str(p)):
        # Skip hidden dirs and common non-source dirs
        dirs[:] = [d for d in sorted(dirs) if not d.startswith(".") and d not in {"__pycache__", ".venv", "node_modules"}]
        for name in sorted(files):
            if is_test_file(name):
                results.append(os.path.join(root, name))
    return results


def matches_filter(full_name: str, pattern: str) -> bool:
    """Check if a test full_name matches a filter pattern (glob or re:...)."""
    if not pattern:
        return True
    if pattern.startswith("re:"):
        return bool(re.search(pattern[3:], full_name, re.IGNORECASE))
    # Glob match
    return fnmatch.fnmatchcase(full_name.lower(), pattern.lower()) or pattern.lower() in full_name.lower()
