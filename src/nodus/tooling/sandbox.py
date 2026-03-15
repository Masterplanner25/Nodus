"""Sandbox enforcement utilities for runner execution."""

from __future__ import annotations

import io
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout

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
def capture_output(*, max_stdout_chars: int | None = MAX_STDOUT_CHARS):
    stdout = LimitedBuffer(max_stdout_chars)
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        yield stdout, stderr
