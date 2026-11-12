"""#180 stage 4c: a durable coroutine's clock continues across a restart (design 08a, D6).

The scheduler's clock is milliseconds since *this process* started. A durable
coroutine that holds a deadline in a local -- from `runtime.time_ms()`, a
`sleep_until` target, `std:loop` -- holds a plain number, which stage 2 counts
as durable. Without D6 it means something else after a resume: the new process's
clock started near zero, so the deadline lands at an unrelated moment. #778 made
the same mistake by comparing two clocks; a restore would make it again silently.

The fix is per coroutine. Each checkpoint records where the coroutine's clock
stood and the wall time. A restore gives the coroutine an offset so its clock
reads on from there, plus the wall time that passed. Every guest reading goes
through `VM.guest_clock_ms`, and the first test holds that to one place.
"""

import ast
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.runtime import time_source as time_source_module  # noqa: E402
from nodus.runtime.durable import run_id_for  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus_lang_workflow.runner import (  # noqa: E402
    WorkflowFrameworkRunner,
    configure_default_workflow_runner,
    reset_default_workflow_runner,
)
from nodus_lang_workflow.store import SQLiteWorkflowStore  # noqa: E402

GUEST_FACING = ["src/nodus/vm/vm.py", *sorted(
    p.relative_to(REPO).as_posix() for p in (REPO / "src/nodus/builtins").glob("*.py"))]


def _now_ms_reads(source: str) -> list[tuple[str, int]]:
    """(enclosing function, line) of every `<x>.time_source.now_ms()` call."""
    tree = ast.parse(source)
    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "now_ms"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "time_source"):
            enclosing = "?"
            for fn in functions:
                if fn.lineno <= node.lineno <= (fn.end_lineno or fn.lineno):
                    enclosing = fn.name  # innermost wins: functions are walked outer-first
            found.append((enclosing, node.lineno))
    return found


class OneReaderTests(unittest.TestCase):

    def test_the_guest_reads_the_scheduler_clock_in_one_place(self):
        """An offset applied in one reader and missed by another would put two
        timelines in one coroutine: `runtime.time_ms()` and `sleep_until` must
        agree, which #182 made them do and this keeps."""
        readers = []
        for rel in GUEST_FACING:
            for fn, line in _now_ms_reads(io.open(REPO / rel, encoding="utf-8").read()):
                readers.append((rel, fn))
        self.assertEqual([("src/nodus/vm/vm.py", "guest_clock_ms")], readers)

    def test_the_scan_sees_a_reader(self):
        self.assertEqual([("f", 2)], _now_ms_reads(
            "def f(vm):\n    return vm.scheduler.time_source.now_ms()\n"))


@contextmanager
def _store(tmp: Path):
    store = SQLiteWorkflowStore(str(tmp / "runs.db"), claim_ttl_ms=200.0)
    configure_default_workflow_runner(runner=WorkflowFrameworkRunner(store))
    try:
        yield store
    finally:
        reset_default_workflow_runner()


_ARMED = """
import "std:runtime" as runtime
fn worker(label) {
    let armed_at = runtime.time_ms()
    checkpoint "armed"
    stop_here()
    let resumed_at = runtime.time_ms()
    report("\\(label) \\(armed_at) \\(resumed_at)")
    return 1i
}
"""


def _leave_unfinished(store, src: str):
    """Run `src` until `stop_here()`, then abandon the run as a crash would:
    its claim is released and the coroutine discarded, the record left
    `running` with its last checkpoint."""
    runtime = NodusRuntime(timeout_ms=None, max_steps=None)

    class Stop(Exception):
        pass

    def stop_here():
        co = runtime.active_vm().current_coroutine
        binding = co.durable
        binding.lost = True  # this copy writes nothing more
        store.release_claim(binding.run_id, binding.token)
        raise Stop()

    runtime.register_function("stop_here", stop_here)
    runtime.register_function("report", lambda line: None)
    runtime.run_source(textwrap.dedent(src))


class ContinuityTests(unittest.TestCase):

    def _resume(self, src: str) -> list[str]:
        lines = []
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        runtime.register_function("stop_here", lambda: None)
        runtime.register_function("report", lambda line: lines.append(line))
        result = runtime.run_source(textwrap.dedent(src))
        self.assertTrue(result.get("ok"), result)
        return lines

    def test_the_clock_reads_on_from_the_checkpoint(self):
        """Planted: the checkpoint says the coroutine's clock read 10,000,000 ms
        a quarter of a second ago. After the resume it reads about that plus a
        quarter of a second -- far from this process's own clock."""
        src = _ARMED + 'durable_spawn("c1", worker, ["c1"])\nrun_loop()\n'
        with tempfile.TemporaryDirectory() as raw, _store(Path(raw)) as store:
            _leave_unfinished(store, src)
            record = store.get_run(run_id_for("c1"))
            record.metadata = {**record.metadata, "clock": {
                "guest_ms": 10_000_000.0, "wall_ms": time.time() * 1000.0 - 250.0}}
            store.save_run(record)
            (line,) = self._resume(src)
        _label, _armed, resumed_at = line.split()
        self.assertGreaterEqual(float(resumed_at), 10_000_250.0)
        self.assertLess(float(resumed_at), 10_000_250.0 + 5_000.0)

    def test_a_clock_that_ran_backwards_does_not_reverse_the_coroutine(self):
        """Wall time before the checkpoint's: elapsed clamps at zero."""
        src = _ARMED + 'durable_spawn("c2", worker, ["c2"])\nrun_loop()\n'
        with tempfile.TemporaryDirectory() as raw, _store(Path(raw)) as store:
            _leave_unfinished(store, src)
            record = store.get_run(run_id_for("c2"))
            record.metadata = {**record.metadata, "clock": {
                "guest_ms": 5_000_000.0, "wall_ms": time.time() * 1000.0 + 3_600_000.0}}
            store.save_run(record)
            (line,) = self._resume(src)
        resumed_at = float(line.split()[2])
        self.assertGreaterEqual(resumed_at, 5_000_000.0)
        self.assertLess(resumed_at, 5_000_000.0 + 5_000.0)

    def test_each_resumed_coroutine_keeps_its_own_timeline(self):
        """Two runs checkpointed at different times, resumed in one process,
        each continue their own clock; an ordinary coroutine beside them reads
        the scheduler's clock unshifted. One offset for the whole scheduler
        could satisfy at most one of the three."""
        src = (_ARMED + 'durable_spawn("a", worker, ["a"])\ndurable_spawn("b", worker, ["b"])\n'
               'spawn(fn() { report("plain 0 \\(runtime.time_ms())") })\nrun_loop()\n')
        with tempfile.TemporaryDirectory() as raw, _store(Path(raw)) as store:
            # The same program throughout: a restore into any other is refused.
            # `stop_here` abandons each worker as it reaches it.
            _leave_unfinished(store, src)
            now = time.time() * 1000.0
            for key, guest in (("a", 1_000_000.0), ("b", 9_000_000.0)):
                record = store.get_run(run_id_for(key))
                record.metadata = {**record.metadata, "clock": {"guest_ms": guest, "wall_ms": now}}
                store.save_run(record)
            lines = self._resume(src)
        readings = {line.split()[0]: float(line.split()[2]) for line in lines}
        self.assertTrue(1_000_000.0 <= readings["a"] < 1_005_000.0, readings)
        self.assertTrue(9_000_000.0 <= readings["b"] < 9_005_000.0, readings)
        self.assertLess(readings["plain"], 1_000_000.0, readings)


_SIDE = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {src!r})
    from nodus.runtime.embedding import NodusRuntime
    from nodus_lang_workflow.runner import WorkflowFrameworkRunner, configure_default_workflow_runner
    from nodus_lang_workflow.store import SQLiteWorkflowStore
    configure_default_workflow_runner(runner=WorkflowFrameworkRunner(
        SQLiteWorkflowStore(os.environ["DURABLE_DB"], claim_ttl_ms=200.0)))
    def crash():
        os._exit(3)
    def armed(deadline):
        # Straight to a file: the process dies with os._exit, so nothing
        # buffered survives it.
        with open(os.environ["DURABLE_NOTE"], "w", encoding="utf-8") as fh:
            fh.write(repr(float(deadline)))
    rt = NodusRuntime(timeout_ms=None, max_steps=None)
    rt.register_function("crash", crash)
    rt.register_function("armed", armed)
    rt.run_source({program!r})
    os._exit(4)
""")

_DEADLINE = """
import "std:runtime" as runtime
fn worker() {
    sleep(1500i)
    let deadline = runtime.time_ms() + 3000.0
    armed(deadline)
    checkpoint "armed"
    crash()
    sleep_until(deadline)
    woke()
    return 1i
}
durable_spawn("deadline", worker, [])
run_loop()
"""


class AfterARealCrashTests(unittest.TestCase):

    def test_a_deadline_set_before_a_crash_fires_on_time_after_it(self):
        """The first process builds up 1.5 s of uptime, arms a deadline three
        seconds ahead, checkpoints and dies. The resumed coroutine must wake
        when its deadline comes due in wall time. Without D6 it wakes at a
        moment set by the difference between the two processes' uptimes: here,
        as soon as it resumes, because the resuming clock is shifted far ahead.

        The expected wake is computed from the checkpoint's own clock pair, not
        assumed. The deadline is 3 s after the `let`, and the checkpoint comes
        later, by however long capturing the continuation takes. With a fixed
        "wake >= 900 ms after the checkpoint" bound, the wake landed at 727 ms on
        a CI runner (2026-11-12) for a checkpoint that took ~270 ms. That was
        correct behaviour, failing a wrong test."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            note = tmp / "deadline.txt"
            env = dict(os.environ, DURABLE_DB=str(tmp / "runs.db"), DURABLE_NOTE=str(note))
            proc = subprocess.run(
                [sys.executable, "-c", _SIDE.format(src=str(REPO / "src"), program=_DEADLINE)],
                env=env, cwd=raw, capture_output=True, text=True, timeout=120)
            self.assertEqual(3, proc.returncode, proc.stderr[-1500:])
            deadline_guest = float(note.read_text(encoding="utf-8"))
            time.sleep(0.4)  # the dead process's claim lapses
            woke_at = []
            with _store(tmp) as store:
                clock = store.get_run(run_id_for("deadline")).metadata["clock"]
                # When the deadline falls due in wall time, if the resumed clock
                # carries on from the checkpoint (D6).
                due_wall = clock["wall_ms"] + (deadline_guest - clock["guest_ms"])
                resumed_at = time.time() * 1000.0
                runtime = NodusRuntime(timeout_ms=None, max_steps=None)
                runtime.register_function("crash", lambda: None)
                runtime.register_function("armed", lambda deadline: None)
                runtime.register_function("woke", lambda: woke_at.append(time.time() * 1000.0))
                # This process's scheduler clock, a million ms ahead. Without D6
                # the guest deadline (a few seconds of the first process's uptime)
                # is then long past, and the coroutine wakes the moment it
                # resumes, whatever either process's real uptime was. Unshifted,
                # the outcome depended on the two uptimes, and in a lone run they
                # were close enough that the regression woke only 243 ms early.
                real_clock = time_source_module.runtime_time_ms
                with mock.patch.object(time_source_module, "runtime_time_ms",
                                       lambda: real_clock() + 1_000_000.0):
                    result = runtime.run_source(_DEADLINE)
            self.assertTrue(result.get("ok"), result)
        self.assertEqual(1, len(woke_at))
        if resumed_at > due_wall - 1500.0:
            # Without D6 the coroutine wakes as soon as it resumes. If the
            # resume itself started this close to the deadline, the two cases
            # are indistinguishable, and a pass would prove nothing.
            self.skipTest(f"the resume started {due_wall - resumed_at:.0f} ms before "
                          "the deadline; too late to tell D6 from its absence")
        # The discriminating bound. 50 ms covers the host clock's ~16 ms tick and
        # scheduler latency. Without D6 the wake lands at about `resumed_at`,
        # plus the rebuild, and the check above leaves 1.5 s for that rebuild.
        self.assertGreaterEqual(woke_at[0], due_wall - 50.0)
        # Only "absurdly late". A loaded box can take seconds to rebuild, and
        # that is not what this measures.
        self.assertLess(woke_at[0] - due_wall, 15_000.0)


if __name__ == "__main__":
    unittest.main()
