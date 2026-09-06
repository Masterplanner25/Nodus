"""Where the scheduler gets "now", and how it waits for the next timer (#182).

The scheduler had **half** a seam. `clock_fn` was injectable and the test
harness overrode it, but the idle path called `time.sleep` directly — so time
could be *read* from somewhere else and never *waited* on somewhere else.

That half-seam is not merely incomplete, it is unsafe. Installing a virtual
clock and calling `run_loop()` hangs: the idle path sees `wake_time > now`,
sleeps a little, and finds `now` unchanged, forever. Measured — a coroutine
sleeping 800 ms finishes in 885 ms on the host clock and does not finish at all
on a frozen one.

The fix is to make **waiting** part of the seam, because on a virtual clock
waiting *is* advancing:

- `HostTimeSource` waits by sleeping. Real time passes on its own.
- `VirtualTimeSource` waits by moving the clock forward. Nothing blocks, the
  next timer is due immediately, and the run is deterministic — discrete-event
  simulation, which is what a virtual clock has to mean if the scheduler is
  ever to idle under one.

This is the seam #182 needs before Nodus can host its own timer. It does not
make the timer Nodus-native: that still wants `sleep_until` and a `std:loop`
driver, and both are additions on top of this rather than changes to it.
"""
from __future__ import annotations

import time

from nodus.runtime.runtime_stats import runtime_time_ms


class TimeSource:
    """Two operations, deliberately together.

    Splitting them is what produced the hang: a reader with no matching waiter
    describes a clock nothing can idle against. Anything implementing this
    answers both halves or neither.
    """

    def now_ms(self) -> float:
        """Milliseconds on this source's clock. Monotonic within a run."""
        raise NotImplementedError

    def wait(self, seconds: float) -> None:
        """Wait until roughly `seconds` have passed on this source's clock.

        A host implementation blocks; a virtual one advances. Either way the
        postcondition is the same: `now_ms()` has moved forward by about
        `seconds * 1000`, and the caller may re-check its timers.
        """
        raise NotImplementedError


class HostTimeSource(TimeSource):
    """The default, and byte-for-byte what the scheduler did before #182."""

    __slots__ = ()

    def now_ms(self) -> float:
        return runtime_time_ms()

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


class VirtualTimeSource(TimeSource):
    """Time moves only when something moves it, and waiting is one of those things.

    `advance` is the explicit form the test harness drives (`test.advance_clock`).
    `wait` is the implicit one: a scheduler with nothing runnable and a timer due
    at T has nothing to do *but* arrive at T, so it does, instantly.

    That makes a sleeping coroutine resolve with no real time passing, and makes
    the result independent of how fast the box is — which is the property a test
    asserting on ordering actually wants, and the one a wall clock cannot give
    (`runtime_time_ms` ticks at ~15.6 ms here, so two adjacent events routinely
    share a timestamp).
    """

    __slots__ = ("_now_ms",)

    def __init__(self, start_ms: float = 0.0) -> None:
        self._now_ms = float(start_ms)

    def now_ms(self) -> float:
        return self._now_ms

    def advance(self, ms: float) -> float:
        """Move the clock forward by `ms`, and report where it now is."""
        self._now_ms += float(ms)
        return self._now_ms

    def set(self, ms: float) -> None:
        """Place the clock at an absolute reading.

        Never backwards: a scheduler comparing a timer's wake time against
        `now_ms()` would re-fire timers it had already run.
        """
        target = float(ms)
        if target < self._now_ms:
            raise ValueError(
                f"a virtual clock cannot go backwards: {self._now_ms} -> {target}"
            )
        self._now_ms = target

    def wait(self, seconds: float) -> None:
        self._now_ms += max(0.0, float(seconds)) * 1000.0


class _CallableTimeSource(TimeSource):
    """Adapter for the older `scheduler.clock_fn = ...` spelling.

    Kept because that attribute is assigned from two places in this tree and may
    be assigned from outside it; a bare callable says how to *read* time and
    nothing about how to wait, so waiting falls back to the host. That is the
    pre-#182 behaviour exactly, which is the point — the adapter preserves it
    rather than quietly making an old caller's clock virtual.
    """

    __slots__ = ("_now",)

    def __init__(self, now_fn) -> None:
        self._now = now_fn

    def now_ms(self) -> float:
        return self._now()

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)
