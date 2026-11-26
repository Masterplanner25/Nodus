"""Writing to stdout without crashing on text the console cannot encode (#975).

On Windows, a redirected stdout (a file or a pipe) is encoded with the system
code page, cp1252 here, and a bare `print` of a character that code page lacks
raises `UnicodeEncodeError`. A program's own text reaches stdout through many
CLI paths: its output, its disassembly, its AST, a path, a docstring, a graph
node's name. So `nodus dis` on a file holding `"→"` exited 1 while `nodus run`
on the same file worked, because `run` had this fallback and `dis` did not.

The fallback had been written three times, at three of the places that print,
and the copies had drifted: two of them did not flush the text layer first, so
the bytes could land ahead of text still buffered there. This module is the one
copy. Every stdout write in `nodus.cli`, `nodus.tooling` and `nodus.testing`
goes through `stdout_print` or `write_stdout`, and `tests/closed_issues/issue_975.py`
fails on a bare `print()` to stdout in those packages, so a new command cannot
quietly reintroduce the crash.

The console encoding itself is not changed. Reconfiguring stdout to UTF-8 once,
at entry, was the alternative, and it would change what every Windows console
shows, not only the text that cannot be encoded.
"""

from __future__ import annotations

import sys
from typing import IO, Any


def write_stdout(text: str, stream: IO[str] | None = None) -> None:
    """Write *text* to *stream* (default `sys.stdout`).

    If the stream's encoding cannot represent the text, flush what is already
    buffered and write the text as UTF-8 bytes to the underlying buffer
    instead. A stream with no buffer re-raises, because there is nowhere else
    to put the bytes.
    """
    target = sys.stdout if stream is None else stream
    if target is None:  # pythonw, or a closed stdout: `print` is a no-op too
        return
    try:
        target.write(text)
    except UnicodeEncodeError:
        buffer = getattr(target, "buffer", None)
        if buffer is None:
            raise
        target.flush()
        buffer.write(text.encode("utf-8", errors="replace"))
        buffer.flush()


def stdout_print(*values: Any, sep: str = " ", end: str = "\n") -> None:
    """`print(*values, sep=sep, end=end)` to stdout, through `write_stdout`."""
    write_stdout(sep.join(str(value) for value in values) + end)
