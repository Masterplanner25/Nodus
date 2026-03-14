"""Compatibility shim for legacy nodus entrypoint."""

from __future__ import annotations

from importlib.util import spec_from_file_location
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
PKG = SRC / "nodus"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

__path__ = [str(PKG)]

spec = spec_from_file_location(__name__, PKG / "__init__.py")
if spec and spec.loader:
    spec.loader.exec_module(sys.modules[__name__])


if __name__ == "__main__":
    raise SystemExit(main())
