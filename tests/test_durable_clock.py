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
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

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
    rt = NodusRuntime(timeout_ms=None, max_steps=None)
    rt.register_function("crash", crash)
    rt.run_source({program!r})
    os._exit(4)
""")

_DEADLINE = """
import "std:runtime" as runtime
fn worker() {
    sleep(1500i)
    let deadline = runtime.time_ms() + 1000.0
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
        """The first process builds up 1.5 s of uptime, arms a deadline one
        second ahead, checkpoints and dies. The resumed coroutine must wake about
        one second after the checkpoint in wall time. Without D6 it wakes at a
        moment set by the difference between the two processes' uptimes: here,
        immediately, because this test process has been up far longer."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            env = dict(os.environ, DURABLE_DB=str(tmp / "runs.db"))
            proc = subprocess.run(
                [sys.executable, "-c", _SIDE.format(src=str(REPO / "src"), program=_DEADLINE)],
                env=env, cwd=raw, capture_output=True, text=True, timeout=120)
            self.assertEqual(3, proc.returncode, proc.stderr[-1500:])
            time.sleep(0.4)  # the dead process's claim lapses
            woke_at = []
            with _store(tmp) as store:
                checkpoint_wall = store.get_run(run_id_for("deadline")).metadata["clock"]["wall_ms"]
                runtime = NodusRuntime(timeout_ms=None, max_steps=None)
                runtime.register_function("crash", lambda: None)
                runtime.register_function("woke", lambda: woke_at.append(time.time() * 1000.0))
                result = runtime.run_source(_DEADLINE)
            self.assertTrue(result.get("ok"), result)
        self.assertEqual(1, len(woke_at))
        after_checkpoint = woke_at[0] - checkpoint_wall
        # The lower bound is the discriminating one: without the clock offset
        # this long-running test process's clock is far past the old deadline,
        # so the coroutine wakes at once, well under 900 ms. The upper bound only
        # catches "absurdly late", so it is generous: a loaded box can take
        # seconds to restart and rebuild, and that is not what this measures
        # (a 2.5 s bound failed once in a 12-minute run under load).
        self.assertGreaterEqual(after_checkpoint, 900.0)
        self.assertLess(after_checkpoint, 15_000.0)


if __name__ == "__main__":
    unittest.main()
