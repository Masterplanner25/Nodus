"""Compatibility shim for legacy CLI entrypoint."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nodus.cli.cli import debug_file, main

__all__ = ["main", "debug_file"]


if __name__ == "__main__":
    raise SystemExit(main())
