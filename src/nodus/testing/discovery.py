"""Test file discovery for the Nodus test runner."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path


def discover_test_files(path: str) -> list[str]:
    """Return sorted list of *_test.nd files under path (recursive)."""
    p = Path(path)
    if p.is_file():
        return [str(p)] if p.name.endswith("_test.nd") else []
    results = []
    for root, dirs, files in os.walk(str(p)):
        # Skip hidden dirs and common non-source dirs
        dirs[:] = [d for d in sorted(dirs) if not d.startswith(".") and d not in {"__pycache__", ".venv", "node_modules"}]
        for name in sorted(files):
            if name.endswith("_test.nd"):
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
