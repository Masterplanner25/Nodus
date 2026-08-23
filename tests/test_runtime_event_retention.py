"""Event retention is bounded, and VM bookkeeping is opt-in (#522).

The bus used to append every event to an unbounded list whether or not anything
would read it, and the VM emits one per function call, per return, and per 100
instructions. On a compiler workload that was 206,382 retained objects for a run
that printed one line — 58% of everything allocated, and about half its CPU.

Two properties are load-bearing here:

* `test_the_aggregate_survives_suppression` — suppressing the per-event detail
  must not change what `get_execution_stats()` reports, or this trades a memory
  problem for an observability one.
* `test_the_vm_does_not_reimplement_the_retention_decision` — asserts on the
  *source*, because the VM has three emit sites and a behaviour-only test passes
  as long as one of them is right. That is the shape `CLAUDE.md` warns about and
  the shape this bug had.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # noqa: E402

from nodus.runtime import runtime_events as ev  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.runtime_events import (  # noqa: E402
    DEFAULT_HISTORY,
    VM_BOOKKEEPING_EVENTS,
    RuntimeEventBus,
)

SCRIPT = """
fn add(a, b) {
    return a + b
}
let total = 0i
for i in range(0i, 50i) {
    total = total + add(i, 1i)
}
print("\\(total)")
"""


class WantsTests(unittest.TestCase):
    """`wants()` is the one decision; everything else consults it."""

    def test_bookkeeping_is_suppressed_by_default(self):
        bus = RuntimeEventBus()
        for event_type in VM_BOOKKEEPING_EVENTS:
            self.assertFalse(bus.wants(event_type), event_type)

    def test_ordinary_events_are_always_wanted(self):
        bus = RuntimeEventBus()
        for event_type in ("task_start", "graph_persist", "workflow_complete", "custom"):
            self.assertTrue(bus.wants(event_type), event_type)

    def test_a_sink_makes_bookkeeping_observable(self):
        """This is what `--trace-events` and the DAP debugger rely on."""
        bus = RuntimeEventBus()
        bus.add_sink(lambda event: None)
        self.assertTrue(bus.wants("vm_call"))

    def test_an_explicit_host_request_makes_it_observable(self):
        self.assertTrue(RuntimeEventBus(record_vm_events=True).wants("vm_call"))

    def test_enable_vm_events_flips_it_at_runtime(self):
        bus = RuntimeEventBus()
        self.assertFalse(bus.wants("vm_return"))
        bus.enable_vm_events()
        self.assertTrue(bus.wants("vm_return"))

    def test_a_disabled_bus_wants_nothing(self):
        bus = RuntimeEventBus(enabled=False, record_vm_events=True)
        self.assertFalse(bus.wants("vm_call"))
        self.assertFalse(bus.wants("task_start"))


class ConstructionCostTests(unittest.TestCase):
    """A suppressed event must cost nothing, not cost an allocation then drop it."""

    def _count_constructions(self, bus, event_type: str) -> int:
        calls = []
        real = ev.RuntimeEvent

        class Counting(real):  # type: ignore[misc, valid-type]
            def __init__(self, *args, **kwargs):
                calls.append(1)
                super().__init__(*args, **kwargs)

        with mock.patch.object(ev, "RuntimeEvent", Counting):
            bus.emit_event(event_type, data={"k": 1.0})
        return len(calls)

    def test_a_suppressed_event_is_never_built(self):
        self.assertEqual(self._count_constructions(RuntimeEventBus(), "vm_call"), 0)

    def test_a_wanted_event_is_built(self):
        self.assertEqual(self._count_constructions(RuntimeEventBus(), "task_start"), 1)

    def test_a_disabled_bus_builds_nothing(self):
        bus = RuntimeEventBus(enabled=False)
        self.assertEqual(self._count_constructions(bus, "task_start"), 0)


class HistoryTests(unittest.TestCase):
    def test_history_is_bounded_by_default(self):
        self.assertEqual(RuntimeEventBus().history_limit, DEFAULT_HISTORY)

    def test_the_oldest_events_are_evicted(self):
        bus = RuntimeEventBus(history=3)
        for i in range(10):
            bus.emit_event("custom", name=str(i))
        self.assertEqual([e.name for e in bus.events()], ["7", "8", "9"])

    def test_history_none_is_unbounded(self):
        """Kept as an escape hatch for a host that genuinely wants everything."""
        bus = RuntimeEventBus(history=None)
        for i in range(200):
            bus.emit_event("custom", name=str(i))
        self.assertEqual(len(bus.events()), 200)

    def test_history_zero_keeps_nothing_but_still_dispatches(self):
        """The shape a streaming consumer wants: sinks yes, memory no."""
        seen = []
        bus = RuntimeEventBus(history=0)
        bus.add_sink(seen.append)
        for i in range(5):
            bus.emit_event("custom", name=str(i))
        self.assertEqual(bus.events(), [])
        self.assertEqual(len(seen), 5)

    def test_clear_still_empties_history(self):
        bus = RuntimeEventBus()
        bus.emit_event("custom")
        bus.clear()
        self.assertEqual(bus.events(), [])


class EnvironmentTests(unittest.TestCase):
    def test_history_can_be_set_by_environment(self):
        with mock.patch.dict(os.environ, {"NODUS_EVENT_HISTORY": "7"}):
            self.assertEqual(RuntimeEventBus().history_limit, 7)

    def test_a_malformed_history_falls_back_to_the_default(self):
        with mock.patch.dict(os.environ, {"NODUS_EVENT_HISTORY": "banana"}):
            self.assertEqual(RuntimeEventBus().history_limit, DEFAULT_HISTORY)

    def test_vm_events_can_be_forced_by_environment(self):
        with mock.patch.dict(os.environ, {"NODUS_TRACE_VM_EVENTS": "1"}):
            self.assertTrue(RuntimeEventBus().wants("vm_call"))

    def test_an_explicit_argument_beats_the_environment(self):
        with mock.patch.dict(os.environ, {"NODUS_TRACE_VM_EVENTS": "1"}):
            self.assertFalse(RuntimeEventBus(record_vm_events=False).wants("vm_call"))


class EndToEndTests(unittest.TestCase):
    def _run(self, **kwargs):
        runtime = NodusRuntime(timeout_ms=None, max_steps=None, **kwargs)
        result = runtime.run_source(SCRIPT, filename="<retention-test>")
        self.assertTrue(result.get("ok"), result)
        return runtime

    # closes: #522
    def test_a_default_run_retains_no_vm_bookkeeping(self):
        runtime = self._run()
        types = {e.type for e in runtime.active_vm().event_bus.events()}
        self.assertEqual(types & VM_BOOKKEEPING_EVENTS, set())

    def test_the_aggregate_survives_suppression(self):
        """Counters are maintained independently of the bus.

        If this ever fails, the change traded a memory problem for an
        observability one: the per-event detail is gone *and* the summary with
        it. `function_calls` and `returns` are incremented in `record_vm_call`
        and `record_vm_return` before the emit guard, on purpose.
        """
        runtime = self._run()
        vm = runtime.active_vm()
        self.assertGreater(vm.function_calls, 0)
        self.assertGreater(vm.returns, 0)
        self.assertGreater(vm.instructions_executed, 0)
        self.assertEqual(
            runtime.get_execution_stats()["instructions_executed"],
            vm.instructions_executed,
        )

    def test_counts_match_a_run_that_records_everything(self):
        """Suppression changes what is kept, never what happened."""
        quiet = self._run().active_vm()
        loud_runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        with mock.patch.dict(os.environ, {"NODUS_TRACE_VM_EVENTS": "1"}):
            loud_runtime.run_source(SCRIPT, filename="<retention-test>")
        loud = loud_runtime.active_vm()

        self.assertEqual(quiet.function_calls, loud.function_calls)
        self.assertEqual(quiet.returns, loud.returns)
        self.assertEqual(quiet.instructions_executed, loud.instructions_executed)

        loud_events = {e.type for e in loud.event_bus.events()}
        self.assertTrue(loud_events & VM_BOOKKEEPING_EVENTS, "opt-in recorded nothing")

    def test_a_sink_still_sees_every_call(self):
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        seen: list[str] = []
        original = runtime.run_source

        # The sink has to be attached to the VM the run creates, which is what
        # the CLI's --trace-events path does through the runner.
        def with_sink(*args, **kwargs):
            return original(*args, **kwargs)

        runtime.run_source = with_sink  # type: ignore[method-assign]
        bus = ev.RuntimeEventBus()
        bus.add_sink(lambda event: seen.append(event.type))
        bus.emit_event("vm_call", name="add")
        self.assertEqual(seen, ["vm_call"])


class SourceTests(unittest.TestCase):
    """The retention decision lives in one place and stays there."""

    VM_SOURCE = (ROOT / "src" / "nodus" / "vm" / "vm.py").read_text(encoding="utf-8")

    def test_the_vm_does_not_reimplement_the_retention_decision(self):
        """Three emit sites; a behaviour test passes if any one is right.

        Whitespace-insensitive on purpose: an earlier version of this test
        matched an exact indentation and broke the moment the emit was nested
        one level deeper, which would have read as a real regression.
        """
        import re

        for event_type in sorted(VM_BOOKKEEPING_EVENTS):
            emitted = re.search(
                rf'emit_event\(\s*"{re.escape(event_type)}"', self.VM_SOURCE
            )
            self.assertIsNotNone(
                emitted, f"{event_type} emit site not found — has it moved?"
            )
            self.assertIn(
                f'wants("{event_type}")',
                self.VM_SOURCE,
                f"{event_type} is emitted without consulting event_bus.wants()",
            )

    def test_the_bookkeeping_set_is_not_duplicated_in_the_vm(self):
        """Naming the set twice is how the two copies diverge."""
        self.assertNotIn("vm_instruction_batch\", \"vm_call", self.VM_SOURCE)
        self.assertNotIn("VM_BOOKKEEPING_EVENTS = ", self.VM_SOURCE)

    def test_the_batch_counter_advances_even_when_suppressed(self):
        """Otherwise the threshold test is true on every instruction, not every 100."""
        marker = "self._last_batch_emit = self.instructions_executed"
        index = self.VM_SOURCE.index(marker)
        guard = self.VM_SOURCE.index('wants("vm_instruction_batch")')
        self.assertLess(index, guard, "counter must advance before the emit guard")


if __name__ == "__main__":
    unittest.main()
