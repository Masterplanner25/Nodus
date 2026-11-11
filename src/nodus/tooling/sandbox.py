"""Sandbox enforcement utilities for runner execution."""

from __future__ import annotations

import io
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from typing import Any

from nodus.support.config import EXECUTION_TIMEOUT_MS, MAX_STEPS, MAX_STDOUT_CHARS, MAX_STACK_DEPTH
from nodus.runtime.diagnostics import RuntimeLimitExceeded


class LimitedBuffer(io.StringIO):
    def __init__(self, max_chars: int | None):
        super().__init__()
        self.max_chars = max_chars
        self._count = 0

    def write(self, s: str) -> int:
        if self.max_chars is not None and self._count + len(s) > self.max_chars:
            raise RuntimeLimitExceeded("stdout limit exceeded")
        self._count += len(s)
        return super().write(s)


class StreamingLimitedWriter(io.TextIOBase):
    """Pass output straight through to `target`, enforcing the same limit (#907).

    `nodus run` used to collect a program's whole stdout in a `LimitedBuffer`
    and print it when the program ended. A long-running program showed no
    progress, a killed one lost everything it had printed, and its stdout
    landed after its stderr. This writes each piece as it arrives instead, and
    flushes at every newline, so the order survives a pipe or a redirect (where
    Python would otherwise block-buffer stdout until exit). The character
    count, and the `RuntimeLimitExceeded` past it, are `LimitedBuffer`'s.

    `getvalue()` is empty: what was written has already been delivered, so a
    caller that prints the captured text afterwards prints nothing twice.
    """

    def __init__(self, target, max_chars: int | None = None):
        super().__init__()
        self._target = target
        self.max_chars = max_chars
        self._count = 0

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if self.max_chars is not None and self._count + len(s) > self.max_chars:
            raise RuntimeLimitExceeded("stdout limit exceeded")
        self._count += len(s)
        try:
            self._target.write(s)
        except UnicodeEncodeError:
            # A console that cannot encode the text: the same fallback the CLI
            # used when it printed captured output after the run.
            buffer = getattr(self._target, "buffer", None)
            if buffer is None:
                raise
            self._target.flush()
            buffer.write(s.encode("utf-8", errors="replace"))
        if "\n" in s:
            self._target.flush()
        return len(s)

    def flush(self) -> None:
        self._target.flush()

    def getvalue(self) -> str:
        return ""


def configure_vm_limits(
    vm,
    *,
    max_steps: int | None = MAX_STEPS,
    timeout_ms: int | None = EXECUTION_TIMEOUT_MS,
) -> None:
    vm.max_steps = max_steps
    if timeout_ms is None:
        vm.deadline = None
    else:
        vm.deadline = time.monotonic() + (timeout_ms / 1000.0)
    vm.max_frames = MAX_STACK_DEPTH


@contextmanager
def capture_output(*, max_stdout_chars: int | None = MAX_STDOUT_CHARS, stream: bool = False):
    """Redirect a program's output for the duration of a run.

    By default it is collected, for callers that return it as a value (an
    embedded `NodusRuntime`, `nodus serve`). With `stream=True` it goes straight
    to the stdout and stderr that were current on entry (#907). The limit
    applies either way.
    """
    stdout: Any
    stderr: Any
    if stream:
        stdout = StreamingLimitedWriter(sys.stdout, max_stdout_chars)
        stderr = StreamingLimitedWriter(sys.stderr)
    else:
        stdout = LimitedBuffer(max_stdout_chars)
        stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            yield stdout, stderr
        finally:
            if stream:
                stdout.flush()
                stderr.flush()
