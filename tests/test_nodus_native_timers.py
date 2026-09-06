"""Timers a Nodus program can drive itself (#182).

#182 asks for two things on top of the `TimeSource` seam that shipped in #779:
`sleep_until` and a `std:loop` module, so that the timer is not something only
the host can reason about.

**The prerequisite neither the issue nor the seam noticed** is that a program
could not read the clock its own sleeps run on. `runtime.time_ms()` called
`runtime_time_ms()` directly, so under a `VirtualTimeSource` a coroutine that
slept 800 ms and measured it got **0.0** — the scheduler moved virtual time, the
program's reading did not. That is #778 one level up, in the language surface,
and #182's own seam is what made it reachable.

It is settled by the criterion #778 established: the split that holds between
the two clocks is **reported vs. compared**, and `runtime.time_ms()` exists to be
*subtracted*. Event timestamps and `created_time` stay on the host clock because
they are only ever read out.

Everything here runs under a virtual clock, so the numbers are exact rather than
a measurement of how fast this box is — which is the property the seam was built
for, and it is what lets `test_relative_sleep_drifts_and_sleep_until_does_not`
assert equality on a timing test.
"""

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402


def _run(source: str, *, virtual: bool, timeout: float = 90.0) -> str:
    """Run `source` in a clean interpreter, optionally on a virtual clock.

    A subprocess because installing a virtual clock means patching
    `Scheduler.__init__` process-wide — #769 is the lesson about doing that
    in-process — and because a fresh CWD keeps the bytecode cache, which
    resolves against the *script's* project root, from serving one variant's
    compilation to another.
    """
    install = "self.time_source = VirtualTimeSource(1_000_000.0)" if virtual else "pass"
    probe = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(_REPO_ROOT / "src")!r})
        import nodus.runtime.scheduler as sched
        from nodus.runtime.time_source import VirtualTimeSource
        _orig = sched.Scheduler.__init__
        def _patched(self, *a, **k):
            _orig(self, *a, **k)
            {install}
        sched.Scheduler.__init__ = _patched
        from nodus.runtime.embedding import NodusRuntime
        res = NodusRuntime(timeout_ms=None, max_steps=None).run_source({source!r})
        assert res.get("ok"), res.get("error")
        assert not (res.get("stderr") or "").strip(), res.get("stderr")
        sys.stdout.write("OUT<<" + res["stdout"].strip() + ">>")
    """)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, timeout=timeout,
        cwd=str(_REPO_ROOT / "tests"),
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr[-1500:])
    marker = "OUT<<"
    assert marker in result.stdout, result.stdout
    return result.stdout.split(marker, 1)[1].rsplit(">>", 1)[0]


class AProgramCanReadTheClockItsSleepsRunOnTests(unittest.TestCase):
    """The prerequisite for every absolute-deadline construct below: a deadline
    is meaningless if the program cannot read the clock it will be compared
    against."""

    _MEASURE = """
    import "std:runtime" as runtime

    fn main() {
        spawn(coroutine(fn() {
            let started = runtime.time_ms()
            sleep(800i)
            print("\\(runtime.time_ms() - started)")
            return 1i
        }))
        run_loop()
    }
    """

    # closes: #182
    def test_a_sleep_is_visible_to_the_program_on_a_virtual_clock(self):
        """Before this, the answer was `0.0` — the scheduler advanced virtual
        time by 800 ms and the program's own reading did not move."""
        self.assertEqual(
            "800.0",
            _run(self._MEASURE, virtual=True),
            "a program measured its own 800ms sleep as something other than "
            "800ms on a virtual clock, so `runtime.time_ms()` is not reading "
            "the clock the scheduler advanced",
        )

    # closes: #182
    def test_the_host_clock_still_measures_real_elapsed_time(self):
        """The control, and it must run.

        Without it the test above is equally satisfied by a build where
        `runtime.time_ms()` returns whatever the program asked to sleep for.
        `HostTimeSource.now_ms()` *is* `runtime_time_ms()`, so this path must
        behave exactly as it did before.
        """
        measured = float(_run(self._MEASURE, virtual=False))
        self.assertGreater(
            measured, 400.0,
            "an 800ms sleep measured under 400ms on the host clock, so the "
            "default source is not really waiting",
        )
        self.assertLess(
            measured, 4000.0,
            "an 800ms sleep measured over 4s, which is not host time either",
        )


class SleepUntilTests(unittest.TestCase):
    # closes: #182
    def test_relative_sleep_drifts_and_sleep_until_does_not(self):
        """The whole reason for an absolute form.

        Five iterations of 30ms of work, then a wait. Relative sleeps add the
        work to every period; sleeping to a computed instant absorbs it. Exact
        equality is assertable only because the clock is virtual.
        """
        source = """
        import "std:runtime" as runtime

        fn main() {
            spawn(coroutine(fn() {
                let t0 = runtime.time_ms()
                let i = 0i
                while (i < 5i) {
                    sleep(30i)
                    sleep(100i)
                    i = i + 1i
                }
                print("relative=\\(runtime.time_ms() - t0)")
                return 1i
            }))
            run_loop()
            spawn(coroutine(fn() {
                let t0 = runtime.time_ms()
                let i = 0i
                while (i < 5i) {
                    sleep(30i)
                    i = i + 1i
                    sleep_until(t0 + i * 100i)
                }
                print("absolute=\\(runtime.time_ms() - t0)")
                return 1i
            }))
            run_loop()
        }
        """
        out = _run(source, virtual=True)
        self.assertIn("relative=650.0", out, out)
        self.assertIn("absolute=500.0", out, out)

    # closes: #182
    def test_a_deadline_already_past_yields_rather_than_returning_directly(self):
        """A loop that has fallen behind must still give the scheduler a turn,
        or it starves every other coroutine while 'not sleeping'.

        Asserted as an **interleaving**, not as 'the sibling ran'. The first
        version of this test checked only that both coroutines produced output,
        and a neuter returning directly on a past deadline left it green — the
        sibling runs either way, just last. Under a virtual clock the order is
        deterministic, so the sequence itself is assertable: `b` lands after the
        overdue coroutine's first yield.
        """
        source = """
        import "std:runtime" as runtime

        fn main() {
            spawn(coroutine(fn() {
                let i = 0i
                while (i < 3i) {
                    print("a\(i)")
                    sleep_until(runtime.time_ms() - 10000i)
                    i = i + 1i
                }
                return 1i
            }))
            spawn(coroutine(fn() { print("b"); return 1i }))
            run_loop()
        }
        """
        self.assertEqual(
            ["a0", "b", "a1", "a2"],
            _run(source, virtual=True).split(),
            "an overdue `sleep_until` did not yield: the sibling coroutine got "
            "no turn until the loop had finished, which is the starvation this "
            "clamp exists to prevent",
        )

    # closes: #182
    def test_sleep_until_rejects_a_non_number(self):
        source = """
        fn main() {
            spawn(coroutine(fn() { sleep_until("soon"); return 1i }))
            run_loop()
        }
        """
        with self.assertRaises(AssertionError) as caught:
            _run(source, virtual=True)
        self.assertIn("sleep_until(deadline_ms) expects a number", str(caught.exception))


class StdLoopTests(unittest.TestCase):
    """`std:loop` is written in Nodus over those primitives — the substance of
    #182's Bootstrap-axis claim is that this needs no host code."""

    # closes: #182
    def test_every_holds_a_fixed_period_despite_work_in_the_body(self):
        source = """
        import "std:loop" as loop

        fn main() {
            spawn(coroutine(fn() {
                let t0 = loop.now()
                loop.every(100i, 5i, fn(i) { __sleep(30i) })
                print("every=\\(loop.now() - t0)")
                return 1i
            }))
            run_loop()
        }
        """
        self.assertEqual("every=500.0", _run(source, virtual=True))

    # closes: #182
    def test_at_and_deadline_compose(self):
        source = """
        import "std:loop" as loop

        fn main() {
            spawn(coroutine(fn() {
                let t0 = loop.now()
                loop.at(loop.deadline(250i))
                print("at=\\(loop.now() - t0)")
                return 1i
            }))
            run_loop()
        }
        """
        self.assertEqual("at=250.0", _run(source, virtual=True))

    # closes: #182
    def test_until_repeats_to_an_instant(self):
        source = """
        import "std:loop" as loop

        fn main() {
            spawn(coroutine(fn() {
                let n = loop.until(loop.deadline(500i), 100i, fn(i) { __sleep(10i) })
                print("iterations=\\(n)")
                return 1i
            }))
            run_loop()
        }
        """
        self.assertEqual("iterations=5", _run(source, virtual=True))

    # closes: #182
    def test_run_after_fires_from_inside_a_coroutine(self):
        """The case that made `spawn_after` a builtin.

        Written the obvious way — a module wrapping the caller's closure and
        spawning the wrapper — this failed with `Stack underflow` when called
        from inside a coroutine, because the wrapper runs after its module frame
        has popped and nothing can then say which chunk the captured closure
        belongs to. That defect is real and filed as #783; `run_after` spawns the
        caller's closure *directly*, which never poses the question. This test is
        what would go red if `run_after` were ever rewritten to wrap.
        """
        source = """
        import "std:loop" as loop

        fn main() {
            spawn(coroutine(fn() {
                let t0 = loop.now()
                loop.run_after(400i, fn() { print("fired=\\(loop.now() - t0)") })
                return 1i
            }))
            run_loop()
        }
        """
        self.assertEqual("fired=400.0", _run(source, virtual=True))

    # closes: #182
    def test_spawn_after_defers_the_spawn_itself(self):
        source = """
        import "std:runtime" as runtime

        fn main() {
            let t0 = runtime.time_ms()
            spawn_after(120i, fn() { print("deferred=\\(runtime.time_ms() - t0)") })
            run_loop()
        }
        """
        self.assertEqual("deferred=120.0", _run(source, virtual=True))

    # closes: #182
    def test_spawn_after_rejects_a_non_function(self):
        source = 'fn main() { spawn_after(10i, 42i); run_loop() }'
        with self.assertRaises(AssertionError) as caught:
            _run(source, virtual=True)
        self.assertIn("expects a coroutine or a zero-argument function", str(caught.exception))


class TheNewBuiltinsAreClassifiedTests(unittest.TestCase):
    """A new builtin that nothing classifies is invisible to the capability
    policy — #616's lesson, where "total" was true of the wrong set."""

    # closes: #182
    def test_every_new_builtin_is_named_and_classified(self):
        from nodus.builtins.nodus_builtins import BUILTIN_NAMES
        from nodus.runtime.capability import NO_AUTHORITY_BUILTINS

        classified = {name for group in NO_AUTHORITY_BUILTINS.values() for name in group}
        for name in ("sleep_until", "__sleep_until", "spawn_after", "__spawn_after"):
            with self.subTest(builtin=name):
                self.assertIn(name, BUILTIN_NAMES, f"{name} is not a published builtin name")
                self.assertIn(
                    name, classified,
                    f"{name} reaches the host boundary unclassified — a policy "
                    f"cannot decide about a builtin nothing has categorised",
                )


if __name__ == "__main__":
    unittest.main()
