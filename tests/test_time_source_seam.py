"""The scheduler's clock is a seam that can actually be replaced (#182).

`clock_fn` was injectable before this, and the test harness overrode it — but
the idle path called `time.sleep` directly, so time could be *read* from
somewhere else and never *waited* on somewhere else.

That half-seam is not merely incomplete, it is unsafe. Measured, in
subprocesses, on a coroutine that sleeps 800 ms and is driven by `run_loop()`:

| time source | result |
|---|---|
| host (default) | 926 ms |
| `clock_fn` only — the reading half | **never finishes** |
| `TimeSource` — both halves | 44 ms |

The middle row is the point. Injecting a clock and nothing else makes the idle
path wait for a `now` that never moves, so `run_loop()` spins forever. On a
virtual clock, **waiting is advancing** — a scheduler with nothing runnable and
a timer due at T has nothing to do but arrive at T.

The middle row is also still true on purpose: assigning a bare callable to
`clock_fn` says how to read time and nothing about how to wait, so waiting stays
on the host. Preserving that is deliberate — an old caller should not have its
clock silently made virtual.

**Two clocks remain, and the distinction is stated rather than emergent.**
Event timestamps, `created_time` and `last_resume` still read the host clock:
they answer *when did this really happen*, which a simulated clock would
falsify. None of the three is compared against anything.

The task-timeout comparison was briefly counted among them and was the one that
*was* compared — #778, fixed, with `tests/test_task_timeout_clock.py` as its
regression. The distinction that survives is reported-vs-compared, not
scheduling-vs-fact.
"""

import subprocess
import sys
import textwrap
import time
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.scheduler import Scheduler  # noqa: E402
from nodus.runtime.time_source import (  # noqa: E402
    HostTimeSource,
    TimeSource,
    VirtualTimeSource,
)

SLEEPER = """
fn main() {
    let c = coroutine(fn() { sleep(800i); return 1i })
    spawn(c)
    run_loop()
    print("done")
}
"""


def _run_with_source(install: str, timeout: float = 12.0):
    """Run SLEEPER in a clean interpreter. Returns elapsed ms, or None if it hung.

    A subprocess because the failing case is a spin that never returns; an
    in-process version of this test would hang the suite rather than fail it.
    """
    probe = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(_REPO_ROOT / "src")!r})
        from nodus.runtime.embedding import NodusRuntime
        import nodus.runtime.scheduler as sched
        from nodus.runtime.time_source import VirtualTimeSource
        _orig = sched.Scheduler.__init__
        def _patched(self, *a, **k):
            _orig(self, *a, **k)
            {install}
        sched.Scheduler.__init__ = _patched
        t0 = time.perf_counter()
        res = NodusRuntime(timeout_ms=None, max_steps=None).run_source({SLEEPER!r})
        assert res.get("ok"), res.get("error")
        print("ELAPSED", round((time.perf_counter() - t0) * 1000))
    """)
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        raise AssertionError(result.stderr[-800:])
    fields = result.stdout.split()
    return int(fields[fields.index("ELAPSED") + 1])


class TheSeamHasBothHalvesTests(unittest.TestCase):
    """Reading time and waiting for it are one seam, because splitting them
    describes a clock nothing can idle against."""

    # closes: #182
    def test_a_virtual_source_resolves_a_sleep_without_real_time(self):
        elapsed = _run_with_source("self.time_source = VirtualTimeSource(0.0)")
        self.assertIsNotNone(elapsed, "run_loop hung under a virtual time source")
        self.assertLess(
            elapsed, 400,
            "an 800ms sleep cost real time under a virtual clock, so waiting is "
            "still going to the host",
        )

    # closes: #182
    def test_the_host_source_still_really_waits(self):
        """The control, and it must run. Without it the test above is satisfied
        by a build where `sleep` does nothing at all."""
        elapsed = _run_with_source("pass")
        self.assertIsNotNone(elapsed, "the default source hung")
        self.assertGreater(
            elapsed, 400,
            "an 800ms sleep returned early on the host clock, so the default "
            "source is not actually waiting",
        )

    # closes: #182
    def test_the_reading_half_alone_is_not_a_seam(self):
        """The behaviour that motivated this, pinned so it is not mistaken for
        a regression later: a bare `clock_fn` still waits on the host, so a
        frozen one still spins. An old caller is not silently upgraded."""
        self.assertIsNone(
            _run_with_source("self.clock_fn = lambda: 0.0", timeout=8.0),
            "a frozen clock_fn no longer hangs -- which means assigning a bare "
            "callable now changes how the scheduler waits, and a caller that "
            "only meant to read time got virtual waiting too",
        )


class TheSourceItselfTests(unittest.TestCase):
    # closes: #182
    def test_waiting_on_a_virtual_clock_advances_it(self):
        source = VirtualTimeSource(0.0)
        started = time.perf_counter()
        source.wait(5.0)
        self.assertEqual(5000.0, source.now_ms())
        self.assertLess(time.perf_counter() - started, 1.0, "it actually slept")

    # closes: #182
    def test_a_virtual_clock_refuses_to_go_backwards(self):
        """A scheduler compares timer wake times against `now_ms()`, so a clock
        that moved back would re-fire timers it had already run."""
        source = VirtualTimeSource(100.0)
        source.set(500.0)
        self.assertEqual(500.0, source.now_ms())
        with self.assertRaises(ValueError):
            source.set(499.0)

    # closes: #182
    def test_the_host_source_moves_on_its_own(self):
        source = HostTimeSource()
        first = source.now_ms()
        source.wait(0.02)
        self.assertGreater(source.now_ms(), first)

    # closes: #182
    def test_both_halves_are_required_of_an_implementation(self):
        """A source answering one half is what #182 was."""
        for name in ("now_ms", "wait"):
            with self.subTest(operation=name):
                with self.assertRaises(NotImplementedError):
                    getattr(TimeSource(), name)(*([] if name == "now_ms" else [0.0]))


class TheOldSpellingStillWorksTests(unittest.TestCase):
    """`clock_fn` is assigned from two places in this tree and may be assigned
    from outside it, so it stays a working attribute over one implementation."""

    def _scheduler(self):
        return Scheduler(vm=None)

    # closes: #182
    def test_reading_clock_fn_returns_the_sources_reader(self):
        scheduler = self._scheduler()
        self.assertAlmostEqual(
            scheduler.clock_fn(), scheduler.time_source.now_ms(), delta=50.0
        )

    # closes: #182
    def test_assigning_clock_fn_redirects_reads(self):
        scheduler = self._scheduler()
        scheduler.clock_fn = lambda: 1234.0
        self.assertEqual(1234.0, scheduler.time_source.now_ms())
        self.assertEqual(1234.0, scheduler.clock_fn())

    # closes: #182
    def test_a_scheduler_takes_a_source_at_construction(self):
        source = VirtualTimeSource(42.0)
        self.assertEqual(42.0, Scheduler(vm=None, time_source=source).clock_fn())

    # closes: #182
    def test_the_default_is_the_host(self):
        self.assertIsInstance(self._scheduler().time_source, HostTimeSource)


if __name__ == "__main__":
    unittest.main()
