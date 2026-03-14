"""List .nd/.tl files for formatter checks."""

from __future__ import annotations

import os
import sys


def iter_targets(root: str) -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip VCS and caches
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "tmp_demo"}]
        for name in filenames:
            if name.endswith((".nd", ".tl")):
                out.append(os.path.join(dirpath, name))
    out.sort()
    return out


def main(argv: list[str]) -> int:
    root = argv[1] if len(argv) > 1 else "."
    for path in iter_targets(root):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
