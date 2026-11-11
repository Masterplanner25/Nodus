"""#927: the dispatch loop's fast path fires every check on the same instruction.

`VM.execute` used to run `record_instruction` -- the step budget, deadline,
`max_steps`, memory and batch-event checks -- on every instruction. It now runs
it only from `_next_check` on, a count `_next_check_count` derives from the
bounds, and otherwise just counts. That is ~1.6-2x on CPython, and it is only
correct if `_next_check` is never later than the first instruction a check
could fire on.

So these tests do not ask "does a limit still fire" -- a check late by 50
instructions still fires. They ask *where*: one program, run through the fast
loop and through `_execute_instrumented` (the per-instruction loop a debugger,
profiler or trace uses), must hit every check at the same instruction count.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.runtime import runtime_events  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm import vm as vm_module  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402

# Two coroutines long enough to exhaust several 1,000-instruction scheduler
# slices each, so the fairness budget yields mid-loop, plus top-level work.
_PROGRAM = """
fn work(label, n) {
    let i = 0i
    let acc = 0i
    while (i < n) { acc = acc + i; i = i + 1i }
    print("\\(label) \\(acc)")
}
spawn(fn() { work("a", 700i) })
spawn(fn() { work("b", 500i) })
work("main", 300i)
run_loop()
"""

_LOOP = """
let i = 0i
while (i < 5000i) { i = i + 1i }
"""


class _Recorder:
    """Patches the points where each check acts, and records the count at each."""

    def __init__(self):
        self.events = []

    def __enter__(self):
        recorder = self
        self._saved = {
            "save": VM.save_current_coroutine_state,
            "memory": VM._check_memory_limit,
            "time": vm_module.time,
            "wants": runtime_events.RuntimeEventBus.wants,
            "emit": runtime_events.RuntimeEventBus.emit_event,
        }
        original_save = self._saved["save"]
        original_wants = self._saved["wants"]
        original_emit = self._saved["emit"]
        real_time = self._saved["time"]

        def save(vm, next_ip):
            recorder.events.append(("slice", vm.instructions_executed, next_ip))
            return original_save(vm, next_ip)

        def memory(vm):
            recorder.events.append(("memory", vm.instructions_executed))

        class _Clock:
            def __getattr__(self, name):
                return getattr(real_time, name)

            def monotonic(self):
                recorder.events.append(("clock",))
                return real_time.monotonic()

        def wants(bus, event_type):
            return event_type == "vm_instruction_batch" or original_wants(bus, event_type)

        def emit(bus, event_type, *args, **kwargs):
            if event_type == "vm_instruction_batch":
                recorder.events.append(("batch", kwargs["data"]["total"]))
                return None
            return original_emit(bus, event_type, *args, **kwargs)

        VM.save_current_coroutine_state = save
        VM._check_memory_limit = memory
        vm_module.time = _Clock()
        runtime_events.RuntimeEventBus.wants = wants
        runtime_events.RuntimeEventBus.emit_event = emit
        return self

    def __exit__(self, *exc):
        VM.save_current_coroutine_state = self._saved["save"]
        VM._check_memory_limit = self._saved["memory"]
        vm_module.time = self._saved["time"]
        runtime_events.RuntimeEventBus.wants = self._saved["wants"]
        runtime_events.RuntimeEventBus.emit_event = self._saved["emit"]


def _run(source, *, instrumented, **bounds):
    """Run `source`, forcing the per-instruction loop when `instrumented`."""
    saved = VM._instrumented
    if instrumented:
        VM._instrumented = lambda self: True
    try:
        with _Recorder() as recorder:
            rt = NodusRuntime(**bounds)
            result = rt.run_source(source)
            count = rt.get_execution_stats()["instructions_executed"]
    finally:
        VM._instrumented = saved
    return result, count, recorder.events


class EveryCheckFiresOnTheSameInstructionTests(unittest.TestCase):

    # closes: #927
    def test_the_fast_loop_matches_the_per_instruction_loop(self):
        bounds = dict(timeout_ms=10_000_000, max_steps=100_000_000)
        try:
            NodusRuntime(max_memory_mb=1_000_000)
            bounds["max_memory_mb"] = 1_000_000
        except (ValueError, RuntimeError):
            pass  # memory metering unsupported here; the other checks still run
        fast = _run(_PROGRAM, instrumented=False, **bounds)
        slow = _run(_PROGRAM, instrumented=True, **bounds)
        self.assertTrue(fast[0]["ok"], fast[0].get("error"))
        self.assertEqual(slow[0]["stdout"], fast[0]["stdout"])
        self.assertEqual(slow[1], fast[1], "instruction counts differ")
        kinds = {event[0] for event in slow[2]}
        # Each check must actually have acted, or agreeing proves nothing.
        expected = {"slice", "clock", "batch"} | ({"memory"} if "max_memory_mb" in bounds else set())
        self.assertEqual(expected, kinds & expected, f"a check never fired: {kinds}")
        slices = [e for e in slow[2] if e[0] == "slice"]
        self.assertGreaterEqual(len(slices), 3, "the scheduler budget barely fired")
        self.assertEqual(slow[2], fast[2])

    def test_with_no_deadline_the_batch_event_keeps_its_own_cadence(self):
        """The batch and deadline checks share a 100-instruction cadence, so with
        both on, either one's next check covers a mistake in the other's."""
        fast = _run(_PROGRAM, instrumented=False, timeout_ms=None, max_steps=None)
        slow = _run(_PROGRAM, instrumented=True, timeout_ms=None, max_steps=None)
        self.assertIn("batch", {event[0] for event in slow[2]})
        self.assertEqual(slow[2], fast[2])

    def test_max_steps_stops_on_the_same_instruction_at_every_boundary(self):
        """Around each interval the fast path computes a next check from."""
        for limit in (0, 1, 2, 98, 99, 100, 101, 255, 256, 257, 999, 1000, 1001, 1234):
            with self.subTest(max_steps=limit):
                fast = _run(_LOOP, instrumented=False, timeout_ms=None, max_steps=limit)
                slow = _run(_LOOP, instrumented=True, timeout_ms=None, max_steps=limit)
                self.assertFalse(fast[0]["ok"])
                self.assertIn("step limit", fast[0]["error"]["message"])
                self.assertEqual(limit + 1, slow[1])
                self.assertEqual(slow[1], fast[1])

    def test_a_bound_set_mid_run_takes_effect_on_the_next_instruction(self):
        """`inherit_run_bounds` and the scheduler set bounds with `setattr`. The
        fast loop's next check was computed before; the setter must void it."""
        vm = VM([], {}, code_locs=[])
        vm.instructions_executed = 5_000
        for bound, value in (("max_steps", 5_000), ("task_step_budget", 10),
                             ("deadline", 1e18), ("max_memory_bytes", 1 << 40)):
            with self.subTest(bound=bound):
                vm._next_check = 10**9  # as if computed while unbounded
                setattr(vm, bound, value)
                self.assertEqual(0, vm._next_check)
                self.assertEqual(value, getattr(vm, bound))


class ACallsNameIsDisplayedOnlyWhenReadTests(unittest.TestCase):
    """`_op_call` used to compute a display name for every call, for an event
    that is almost never recorded. It now passes the internal name with
    `raw=True`, and the display name is computed only for a reader."""

    _MANGLED = "__mod1__helper"

    def test_a_sink_sees_the_display_name(self):
        vm = VM([], {}, code_locs=[])
        seen = []
        vm.event_bus.add_sink(seen.append)
        vm.record_vm_call(self._MANGLED, "call", raw=True)
        self.assertEqual(["helper"], [e.name for e in seen if e.type == "vm_call"])

    def test_with_no_reader_it_only_counts(self):
        vm = VM([], {}, code_locs=[])
        calls = []
        vm.display_name = lambda name: calls.append(name) or name
        vm.record_vm_call(self._MANGLED, "call", raw=True)
        self.assertEqual(1, vm.function_calls)
        self.assertEqual([], calls, "a display name was computed for nobody")


def _first_acting_count(vm) -> int:
    """Brute force: the count before the first instruction on which
    `record_instruction` would do anything besides count. The model the fast
    path's arithmetic must match, written as the checks themselves read."""
    count = vm.instructions_executed
    while True:
        k = count + 1
        if vm._task_budget_end is not None and k >= vm._task_budget_end:
            return count
        if vm._deadline is not None and k - vm._last_deadline_check >= vm._deadline_check_interval:
            return count
        if vm._max_steps is not None and k > vm._max_steps:
            return count
        if vm._max_memory_bytes is not None and k % vm.MEMORY_CHECK_INTERVAL == 0:
            return count
        if k - vm._last_batch_emit >= vm._instruction_batch_size:
            return count
        count = k


class TheNextCheckIsNeverLateTests(unittest.TestCase):

    def test_it_matches_a_brute_force_model_for_each_bound_alone_and_together(self):
        """One bound at a time as well as all at once: bounds on the same
        cadence hide each other's off-by-one, so only isolating them tests each."""
        import random
        rng = random.Random(927)
        vm = VM([], {}, code_locs=[])
        for _ in range(4000):
            count = rng.randrange(0, 5000)
            vm.instructions_executed = count
            vm._last_batch_emit = count - rng.randrange(0, 100)
            vm._last_deadline_check = count - rng.randrange(0, 400)
            on = {name: rng.random() < 0.5 for name in ("deadline", "steps", "memory", "budget")}
            vm._deadline = 1e18 if on["deadline"] else None
            vm._max_steps = count + rng.randrange(0, 300) if on["steps"] else None
            vm._max_memory_bytes = 1 << 60 if on["memory"] else None
            vm._task_budget_end = count + rng.randrange(-5, 300) if on["budget"] else None
            with self.subTest(state=(count, vm._last_batch_emit, vm._last_deadline_check, on)):
                # Anything at or below the count means "check now" to the loop.
                self.assertEqual(_first_acting_count(vm), max(vm._next_check_count(), count))


if __name__ == "__main__":
    unittest.main()
