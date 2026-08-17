"""`action agent` in independent steps runs concurrently (#398).

`plan_graph` identified the concurrent steps and `ready_tasks()` returned them
together — and then they executed strictly serially, because `__action_agent` was
wired to the synchronous `agent_call`. Two 1-second agent calls took 2.44s.

**The issue's stated cause was wrong**, and the correction is why the fix is
small. It said `agent_call_async` "falls back to synchronous whenever it is not
running as the scheduler's own coroutine … A workflow step **is** a graph
context. So the async path is unavailable exactly where the parallelism is
wanted." Measured, the opposite: `spawn_task` runs a step body *as a scheduler
coroutine*, so the guard passes and calling `agent_call_async` from inside a step
already overlapped by a full second. Only the wiring was missing.

The part that needed care was events, not concurrency — see
`GoalActionEventsStayPairedTests`.
"""

import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.services.agent_runtime import AGENT_REGISTRY, register_agent  # noqa: E402


FANOUT = """
workflow fanout {
    step a { return action agent "%(agent)s" with { n: 1i } }
    step b { return action agent "%(agent)s" with { n: 2i } }
    step join after a, b { return "joined" }
}
let r = run_workflow(fanout)
print("join=\(r["steps"]["join"])")
"""


class _Recorder:
    """An agent handler that records when each invocation started and ended."""

    def __init__(self, delay: float):
        self.delay = delay
        self.spans: list[tuple[float, float]] = []
        self._lock = threading.Lock()

    def __call__(self, payload):
        started = time.time()
        time.sleep(self.delay)
        with self._lock:
            self.spans.append((started, time.time()))
        return {"ok": True, "result": "done"}

    def overlap(self) -> float:
        """Seconds the two invocations were in flight at the same time."""
        if len(self.spans) != 2:
            raise AssertionError(f"expected 2 invocations, got {len(self.spans)}")
        (s1, e1), (s2, e2) = sorted(self.spans)
        return min(e1, e2) - max(s1, s2)


class _Sandbox:
    def __enter__(self):
        self._cwd = os.getcwd()
        self._td = tempfile.TemporaryDirectory()
        os.chdir(self._td.__enter__())
        return self

    def __exit__(self, *exc):
        os.chdir(self._cwd)
        return self._td.__exit__(*exc)


def _run_fanout(handler, agent: str = "slowbot"):
    AGENT_REGISTRY.pop(agent, None)
    register_agent(agent, handler)
    with _Sandbox():
        runtime = NodusRuntime(timeout_ms=None)
        started = time.time()
        result = runtime.run_source(FANOUT % {"agent": agent}, filename="fanout.nd")
        return result, time.time() - started


# closes: #398
class ConcurrentAgentStepsOverlapTests(unittest.TestCase):
    """The measurement from the issue, as an assertion."""

    DELAY = 0.6

    def test_two_independent_agent_steps_overlap(self):
        handler = _Recorder(self.DELAY)
        result, _elapsed = _run_fanout(handler)
        self.assertTrue(result.get("ok"), result)

        overlap = handler.overlap()
        # Before the fix this was ~-0.01s: the handlers did not overlap at all.
        # Asserting on overlap rather than wall-clock keeps the test meaningful on
        # a loaded machine, where total elapsed time says more about the machine
        # than about the runtime.
        self.assertGreater(
            overlap,
            self.DELAY / 2,
            f"agent handlers overlapped {overlap:.2f}s of {self.DELAY:.2f}s; "
            f"independent steps calling agents are running serially again (#398)",
        )

    def test_both_steps_still_return_their_results(self):
        # Concurrency must not cost correctness: each step gets its own result.
        result, _ = _run_fanout(_Recorder(0.05))
        self.assertTrue(result.get("ok"), result)
        self.assertIn("join=joined", result["stdout"])

    def test_a_dependent_step_still_waits_for_its_dependency(self):
        # The point is overlap where the graph allows it — not everywhere.
        order = []
        lock = threading.Lock()

        def handler(payload):
            time.sleep(0.05)
            with lock:
                order.append(payload.get("n"))
            return {"ok": True}

        AGENT_REGISTRY.pop("chain", None)
        register_agent("chain", handler)
        source = """
workflow chained {
    step first { return action agent "chain" with { n: 1i } }
    step second after first { return action agent "chain" with { n: 2i } }
}
let r = run_workflow(chained)
"""
        with _Sandbox():
            result = NodusRuntime(timeout_ms=None).run_source(source, filename="c.nd")
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(order, [1.0, 2.0], "a step ran before its dependency")


# closes: #398
class GoalActionEventsStayPairedTests(unittest.TestCase):
    """Completion is emitted when the handler finishes, not when the call suspends.

    This is the part the obvious implementation gets wrong. `_run_goal_action`
    emits its completion event around `fn()` returning — and once the call is
    async, `fn()` returns a *suspension marker*, not the handler's result. Wiring
    `__action_agent` straight through it would fire `goal_action_complete`
    immediately, carrying the marker, and nothing when the value really arrived.
    """

    def _events(self, agent: str, handler):
        AGENT_REGISTRY.pop(agent, None)
        register_agent(agent, handler)
        source = """
goal g {
    step a { return action agent "%s" with { n: 1i } }
}
let r = run_goal(g)
""" % agent
        with _Sandbox():
            runtime = NodusRuntime(timeout_ms=None)
            runtime.run_source(source, filename="g.nd")
            vm = runtime._last_vm
        return [
            e.type
            for e in vm.event_bus.events()
            if e.type.startswith(("goal_action", "agent_call"))
        ]

    def test_a_successful_action_emits_start_then_complete(self):
        events = self._events("good", lambda p: (time.sleep(0.05), {"ok": True})[1])
        self.assertEqual(
            events,
            ["goal_action_start", "agent_call_start", "agent_call_complete", "goal_action_complete"],
        )

    def test_completion_is_emitted_after_the_handler_finishes(self):
        # The ordering is the assertion: `goal_action_complete` must come after
        # `agent_call_complete`. Emitting at suspend time would put it before.
        events = self._events("good", lambda p: (time.sleep(0.05), {"ok": True})[1])
        self.assertLess(
            events.index("agent_call_complete"),
            events.index("goal_action_complete"),
            "goal_action_complete fired before the handler finished — it is being "
            "emitted at suspend time rather than on completion (#398)",
        )

    def test_a_failing_handler_emits_fail_not_complete(self):
        def boom(payload):
            raise RuntimeError("handler blew up")

        events = self._events("bad", boom)
        self.assertIn("goal_action_fail", events)
        self.assertNotIn("goal_action_complete", events)

    def test_on_complete_fires_exactly_once_on_the_synchronous_fallback(self):
        # `_dispatch_agent_async` falls back to a direct call when there is no
        # scheduler coroutine to suspend. The callback must still run, or the
        # completion event would be lost on that path.
        from nodus.vm.vm import VM

        AGENT_REGISTRY.pop("plain", None)
        register_agent("plain", lambda p: {"ok": True, "v": 7})
        seen = []
        vm = VM([], {}, code_locs=[], source_path=None)
        result = vm._dispatch_agent_async("plain", {}, on_complete=seen.append)
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0], result)


if __name__ == "__main__":
    unittest.main()
