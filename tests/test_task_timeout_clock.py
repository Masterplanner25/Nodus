"""A task's timeout is measured on one clock — the one its sleeps advance (#778).

`Scheduler` gained a `TimeSource` seam in #182, so the *scheduling* clock can be
replaced. A task's sleeps advance that clock. The task-timeout comparison did
not: it read `runtime_time_ms()` directly, as did both of the places that stamped
`task_started_at`. The two therefore agreed with each other and disagreed with
the task — they measured *real* elapsed time while the step spent *virtual*
time, so a step that virtually slept for five seconds had spent about a
millisecond by the only reckoning the timeout could see, and never fired.

Moving one of the three and not the others is worse, not better: a virtual `now`
minus a host-clock start is a large negative number, and a host `now` minus a
virtual start is a large positive one. The first never times out and the second
times out immediately. That is why all of them had to move together, and it is
what `_VIRTUAL_START` below is chosen to expose.

Measured on the workflow below (`timeout_ms: 100`, a 5000 ms sleep, virtual
clock installed on every scheduler):

| | `len(r["failed"])` |
|---|---|
| before | **0** — the step completed |
| after | **1** — the step timed out |

The fix is the one this codebase keeps arriving at: the question is answered in
one place. `mark_task_started` and `task_elapsed_ms` both live on `Scheduler` and
both read `self.time_source`, so a caller cannot supply the other clock — where
before, four sites each chose for themselves and two of them were in other
modules. `test_the_timeout_clock_is_named_in_one_place` is the assertion on the
source that keeps it that way; the behavioural tests alone would pass on a tree
where one of the four had been missed.

**`last_resume`, `created_time` and event timestamps stay on the host clock**,
and that is not the same oversight. Those are *reported*, never compared, and
answer "when did this really happen" — a virtual timestamp would make a trace
unreadable against a log. The task timeout was the one member of that group that
was compared, which is why it is the one that moved.
"""

import ast
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.coroutine import Coroutine  # noqa: E402
from nodus.runtime.scheduler import Scheduler  # noqa: E402
from nodus.runtime.time_source import VirtualTimeSource  # noqa: E402


def _workflow(sleep_ms: int, timeout_ms: int) -> str:
    return textwrap.dedent(
        f"""
        workflow w {{
            step slow with {{ timeout_ms: {timeout_ms} }} {{
                sleep({sleep_ms}i)
                return 1i
            }}
        }}

        fn main() {{
            let r = run_workflow(w)
            print("failed=\\(len(r["failed"]))")
        }}
        """
    )


_VIRTUAL_START = 1_000_000.0
"""Deliberately *ahead* of the host clock, and that is what makes the pair below
discriminating.

Starting at 0 puts virtual time behind real time, so a half-fix — the stamp on
one clock and the comparison on the other — still produces a large positive
elapsed reading and still times out, for the wrong reason. Started ahead, each
of the three wrong combinations is caught by one of the two behavioural tests:
both-on-host reads ~0 elapsed and never fires, stamp-virtual/compare-host reads
a large negative and never fires, and stamp-host/compare-virtual reads ~1e6 and
fires on a step that is nowhere near its deadline.
"""


def _failed_count(source: str, *, virtual: bool, timeout: float = 60.0) -> int:
    """Run `source` in a clean interpreter and report how many steps failed.

    A subprocess for two reasons. Installing a virtual clock means patching
    `Scheduler.__init__` process-wide, which #769 is the lesson about doing
    in-process; and the bytecode cache resolves against the *script's* project
    root, so a fresh CWD keeps one variant's compilation from serving the other.
    """
    install = f"self.time_source = VirtualTimeSource({_VIRTUAL_START})" if virtual else "pass"
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
        sys.stdout.write("RESULT " + res["stdout"].strip())
    """)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(_REPO_ROOT / "tests"),
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr[-1200:])
    marker = "RESULT failed="
    assert marker in result.stdout, result.stdout
    return int(result.stdout.split(marker, 1)[1].split()[0])


class AStepTimesOutOnTheClockItsSleepsAdvanceTests(unittest.TestCase):
    # closes: #778
    def test_a_step_that_virtually_sleeps_past_its_deadline_times_out(self):
        """The repro from the issue. Before the fix this was 0."""
        self.assertEqual(
            1,
            _failed_count(_workflow(sleep_ms=5000, timeout_ms=100), virtual=True),
            "a step slept 5000 virtual ms against a 100 ms timeout and did not "
            "fail, so the comparison is still reading a clock the sleep does "
            "not move",
        )

    # closes: #778
    def test_a_step_within_its_deadline_still_succeeds_on_a_virtual_clock(self):
        """The control, and it must run.

        Without it the test above is equally satisfied by a build that fails
        every step carrying a `timeout_ms` — which is what stamping the start
        on one clock and comparing on another would produce if the sign went
        the other way.
        """
        self.assertEqual(
            0,
            _failed_count(_workflow(sleep_ms=10, timeout_ms=5000), virtual=True),
            "a step well inside its deadline failed, so the timeout now fires "
            "on something other than elapsed time",
        )

    # closes: #778
    def test_the_host_clock_path_is_unchanged(self):
        """The default source is `HostTimeSource`, whose `now_ms` *is*
        `runtime_time_ms()` — so this path must behave exactly as before."""
        self.assertEqual(
            0,
            _failed_count(_workflow(sleep_ms=1, timeout_ms=30000), virtual=False),
        )


class OneClockDecidesTests(unittest.TestCase):
    """Unit-level: the stamp and the comparison come from the same source."""

    def _scheduler(self, start_ms: float = 0.0):
        source = VirtualTimeSource(start_ms)
        return Scheduler(vm=None, time_source=source), source

    # closes: #778
    def test_elapsed_is_measured_against_the_schedulers_own_source(self):
        scheduler, source = self._scheduler(1000.0)
        coroutine = Coroutine(None)
        scheduler.mark_task_started(coroutine)
        self.assertEqual(0.0, scheduler.task_elapsed_ms(coroutine))
        source.advance(250.0)
        self.assertEqual(250.0, scheduler.task_elapsed_ms(coroutine))

    # closes: #778
    def test_an_unstamped_task_has_no_elapsed_time_rather_than_zero(self):
        """`None` and `0.0` must not be conflated: a caller treating an
        unstamped task as having spent no time would give it a full budget
        every time it was asked."""
        scheduler, _source = self._scheduler()
        self.assertIsNone(scheduler.task_elapsed_ms(Coroutine(None)))

    # closes: #778
    def test_replacing_the_source_replaces_the_clock_for_both_halves(self):
        """The property that was missing: swapping the source must move the
        stamp too, or the two disagree."""
        scheduler, _source = self._scheduler()
        scheduler.time_source = VirtualTimeSource(500_000.0)
        coroutine = Coroutine(None)
        scheduler.mark_task_started(coroutine)
        self.assertEqual(500_000.0, coroutine.task_started_at)
        self.assertEqual(0.0, scheduler.task_elapsed_ms(coroutine))


class TheAgentDeadlineReadsTheSameClockTests(unittest.TestCase):
    """`_effective_timeout_ms` subtracts a step's elapsed time from its timeout
    to bound a host agent handler (#424). It read `runtime_time_ms()` directly,
    so on a virtual clock it computed a *larger* remaining budget than the step
    itself had — the two answers to one question disagreeing by however far the
    two clocks had drifted apart."""

    # closes: #778
    def test_remaining_budget_is_computed_on_the_schedulers_clock(self):
        from nodus.services import agent_runtime

        source = VirtualTimeSource(0.0)
        scheduler = Scheduler(vm=None, time_source=source)
        task = Coroutine(None)
        task.task_timeout_ms = 1000.0
        scheduler.mark_task_started(task)
        scheduler.current_task = task
        source.advance(600.0)

        class _VM:
            pass

        vm = _VM()
        vm.scheduler = scheduler
        self.assertAlmostEqual(
            400.0, agent_runtime._effective_timeout_ms(vm), delta=0.001
        )

    # closes: #778
    def test_an_overrun_step_clamps_rather_than_going_unbounded(self):
        from nodus.services import agent_runtime

        source = VirtualTimeSource(0.0)
        scheduler = Scheduler(vm=None, time_source=source)
        task = Coroutine(None)
        task.task_timeout_ms = 100.0
        scheduler.mark_task_started(task)
        scheduler.current_task = task
        source.advance(5000.0)

        class _VM:
            pass

        vm = _VM()
        vm.scheduler = scheduler
        self.assertEqual(1.0, agent_runtime._effective_timeout_ms(vm))


class TheSourceSaysSoTests(unittest.TestCase):
    """The behavioural tests above pass on a tree where one of the four original
    sites was missed — whichever one the workflow path happens not to reach. This
    is the assertion that the question is answered in one place."""

    _ALLOWED = {
        # Where the clock is chosen, for both the stamp and the comparison.
        Path("nodus/runtime/scheduler.py"),
        # The field's declaration on the dataclass.
        Path("nodus/runtime/coroutine.py"),
    }

    # closes: #778
    def test_the_timeout_clock_is_named_in_one_place(self):
        offenders = []
        for path in sorted((_REPO_ROOT / "src").rglob("*.py")):
            relative = path.relative_to(_REPO_ROOT / "src")
            if relative in self._ALLOWED:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == "task_started_at":
                    offenders.append(f"{relative}:{node.lineno}")
                elif (
                    isinstance(node, ast.Constant)
                    and node.value == "task_started_at"
                ):
                    offenders.append(f"{relative}:{node.lineno} (getattr)")
        self.assertEqual(
            [],
            offenders,
            "`task_started_at` is read or written outside the scheduler. Which "
            "clock it is measured on is one decision; a second site is free to "
            "make it differently, which is exactly what #778 was. Go through "
            "`Scheduler.mark_task_started` / `Scheduler.task_elapsed_ms`.",
        )

    # closes: #778
    def test_neither_half_of_the_pair_reads_the_host_clock_directly(self):
        """`runtime_time_ms()` is still imported by `scheduler.py` for the three
        wall-clock facts, so it is reachable from these two methods by accident.
        Read their bodies rather than the module."""
        tree = ast.parse(
            (_REPO_ROOT / "src/nodus/runtime/scheduler.py").read_text(encoding="utf-8-sig")
        )
        checked = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name not in ("mark_task_started", "task_elapsed_ms"):
                continue
            checked.add(node.name)
            names = {
                inner.id for inner in ast.walk(node) if isinstance(inner, ast.Name)
            }
            self.assertNotIn(
                "runtime_time_ms",
                names,
                f"{node.name} reads the host clock directly, so the seam does "
                f"not cover it",
            )
        self.assertEqual(
            {"mark_task_started", "task_elapsed_ms"},
            checked,
            "one of the pair is gone — this test checks nothing until it is back",
        )


if __name__ == "__main__":
    unittest.main()
