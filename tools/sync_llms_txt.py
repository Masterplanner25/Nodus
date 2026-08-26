"""Copy the repo-root `llms.txt` into the package so the wheel ships it (#605).

`package-data` paths are relative to the package directory, so a file at the repo
root cannot be included from there — it has to exist at `src/nodus/llms.txt`.
That means two copies, which is the shape this repo spends most of its time
fixing.

The copy is therefore **generated, not maintained**: this script writes it, and
`tests/test_llms_txt_shipped.py` fails if the two ever differ. Editing
`src/nodus/llms.txt` by hand is the mistake the test exists to catch — the source
of truth is the one at the repo root, which is what
`https://.../blob/main/llms.txt` serves and what `nodus_gate` scans.

Run after editing `llms.txt`:

    python -m tools.sync_llms_txt
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "llms.txt"
SHIPPED = ROOT / "src" / "nodus" / "llms.txt"


def sync() -> bool:
    """Write the packaged copy. True when it changed."""
    text = SOURCE.read_text(encoding="utf-8")
    if SHIPPED.is_file() and SHIPPED.read_text(encoding="utf-8") == text:
        return False
    SHIPPED.write_text(text, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing source: {SOURCE}", file=sys.stderr)
        return 1
    changed = sync()
    print(f"{SHIPPED.relative_to(ROOT).as_posix()}: "
          f"{'updated' if changed else 'already in step'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
