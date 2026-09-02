"""`max_memory_mb` — the third bound an embedder can set (#160).

`max_steps` bounds instructions and `timeout_ms` bounds wall clock; neither stops
a script growing a list until the host gets a `MemoryError` or the OS kills the
process. SEC-001 is that gap.

**Three of the issue's four proposed approaches were measured and rejected**, and
the numbers are why this reads RSS from the OS instead:

| approach | measured |
|---|---|
| `tracemalloc` | **64x slowdown** (0.026s → 1.681s on a 300k loop), 11.9 µs/read |
| `sys.getallocatedblocks()` | 0.8 µs, but counts **blocks not bytes**, and absent on PyPy |
| RSS via the OS | **4.4 µs**, real megabytes, works on Windows and POSIX |

**What it does not do**, because a memory limit implies more than it delivers:
polling bounds growth *over time*, not a single allocation. A program that asks
for one enormous list gets it, and the check fires afterwards -- if the process
survives. Only an OS-level limit prevents that. Found the hard way: a string
doubling in a loop (`s = s + s`) reached a `MemoryError` between two checks at the
interval this started with, which is what drove the interval down to 256.
"""

import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402
from nodus.runtime.memory import memory_metering_available, rss_bytes  # noqa: E402

#: Allocates steadily with many instructions between allocations -- the shape
#: this bound is for, and the shape of the issue's own reproduction.
GROWS_STEADILY = (
    "fn main() { let acc = []; let i = 0i; "
    "while (true) { acc = push(acc, [i, i, i, i, i, i, i, i]); i = i + 1i } }"
)

STAYS_SMALL = "fn main() { let n = 0i; while (n < 20000i) { n = n + 1i } print(\"\\(n)\") }"


class TheLimitStopsAGrowingProgramTests(unittest.TestCase):
    # closes: #160
    def test_a_steadily_growing_script_is_stopped(self):
        result = NodusRuntime(
            max_steps=None, timeout_ms=None, max_memory_mb=2
        ).run_source(GROWS_STEADILY)
        self.assertFalse(result["ok"])
        self.assertIn("Memory limit exceeded", result["error"]["message"])

    # closes: #160
    def test_the_message_names_both_numbers(self):
        """An operator needs to know what it grew to, not only that it was over."""
        result = NodusRuntime(
            max_steps=None, timeout_ms=None, max_memory_mb=2
        ).run_source(GROWS_STEADILY)
        message = result["error"]["message"]
        self.assertIn("grew the process to", message)
        self.assertIn("MB ceiling", message)

    # closes: #160
    def test_a_small_program_is_not_stopped(self):
        """The false-positive direction. A bound that fires on ordinary work is
        worse than none, because it will be turned off."""
        result = NodusRuntime(
            max_steps=None, timeout_ms=None, max_memory_mb=64
        ).run_source(STAYS_SMALL)
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual("20000\n", result["stdout"])

    # closes: #160
    def test_unset_means_unbounded(self):
        """Off by default, like `max_steps` and `deadline` -- how much memory a
        run may have is host policy."""
        runtime = NodusRuntime()
        self.assertIsNone(runtime.max_memory_mb)

    # closes: #160
    def test_the_limit_is_measured_as_growth_not_absolute_rss(self):
        """An embedded runtime shares a process with its host. An absolute bound
        would make a 100 MB limit fire immediately inside a 2 GB host, before a
        single instruction ran."""
        baseline_hog = [[0] * 100 for _ in range(30000)]  # ~25 MB of host memory
        try:
            result = NodusRuntime(
                max_steps=None, timeout_ms=None, max_memory_mb=64
            ).run_source(STAYS_SMALL)
            self.assertTrue(result["ok"], result.get("error"))
        finally:
            del baseline_hog


class AnUnenforceableLimitIsRefusedTests(unittest.TestCase):
    """Refused at construction, never accepted and quietly ignored.

    A limit that is declared and not enforced is the pattern #473 and #478 were
    both filed for, and it is worse than no limit: it is a security control an
    operator believes they have.
    """

    # closes: #160
    def test_it_is_refused_when_the_platform_cannot_meter(self):
        with mock.patch("nodus.runtime.embedding.memory_metering_available", return_value=False):
            with self.assertRaises(RuntimeError) as caught:
                NodusRuntime(max_memory_mb=64)
        message = str(caught.exception)
        self.assertIn("cannot be enforced on this platform", message)
        self.assertIn("ulimit", message)

    # closes: #160
    def test_an_unmetered_platform_still_allows_no_limit(self):
        """Refusing the *setting* must not refuse the runtime."""
        with mock.patch("nodus.runtime.embedding.memory_metering_available", return_value=False):
            self.assertIsNone(NodusRuntime().max_memory_mb)

    # closes: #160
    def test_a_nonsense_limit_is_refused(self):
        for value in (0, -1, "64"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    NodusRuntime(max_memory_mb=value)


class TheMeterItselfTests(unittest.TestCase):
    # closes: #160
    def test_rss_is_readable_and_grows(self):
        self.assertTrue(memory_metering_available())
        before = rss_bytes()
        self.assertIsInstance(before, int)
        self.assertGreater(before, 1_000_000, "an interpreter under 1 MB is not a reading")
        hog = [[0] * 100 for _ in range(30000)]
        try:
            self.assertGreater(rss_bytes(), before)
        finally:
            del hog

    # closes: #160
    def test_reading_it_is_cheap_enough_to_poll(self):
        """The whole design rests on this. If a read cost what `tracemalloc` costs,
        the feature would have to count allocations instead.

        Generous bound: measured at ~4.4 us, asserted under 200 us so a slow or
        loaded CI box does not fail the build for a property that is really about
        orders of magnitude.
        """
        start = time.perf_counter()
        for _ in range(2000):
            rss_bytes()
        per_call_us = (time.perf_counter() - start) / 2000 * 1e6
        self.assertLess(per_call_us, 200.0, f"{per_call_us:.1f} us/read is too slow to poll")


if __name__ == "__main__":
    unittest.main()
