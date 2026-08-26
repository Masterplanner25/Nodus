"""A host agent handler cannot hang the run forever (#424).

Every bound this runtime offers is a property of the **instruction stream**, and a
host handler is not in it. Measured before the fix, with the same step option and
the same value:

    step timeout_ms: 500  +  pure-Nodus busy loop   -> 0.59s   bounded
    step timeout_ms: 500  +  blocking agent handler -> 3.76s   not bounded

Worse than simply absent: the blocked step *did* fail as timed-out — but only
after the handler ran to completion. The bound was reported and not enforced.

**What the fix can and cannot do.** Arbitrary Python cannot be preempted; a
`time.sleep`, a blocking socket read or a `while True` in a handler is not
interruptible from outside. So the handler runs on a daemon thread and the caller
stops waiting at the deadline. The *run* becomes bounded, which is the property
that was missing. The thread is not reclaimed, which is the price — recorded, and
asserted below, so it stays a known cost rather than a surprise.
"""

import threading
import time
import unittest

from nodus.runtime.embedding import NodusRuntime
from nodus.services.agent_runtime import (
    abandoned_agent_call_count,
    abandoned_agent_calls,
    register_agent,
    reset_abandoned_agent_calls,
    unregister_agent,
)

BLOCK_S = 3


class AgentTimeoutTests(unittest.TestCase):
    def setUp(self):
        reset_abandoned_agent_calls()
        self.calls = []
        register_agent("t.slow", self._slow)
        register_agent("t.fast", lambda p: {"ok": True, "quick": True})

    def tearDown(self):
        unregister_agent("t.slow")
        unregister_agent("t.fast")
        reset_abandoned_agent_calls()

    def _slow(self, payload):
        self.calls.append(1)
        time.sleep(BLOCK_S)
        return {"ok": True}

    def _run(self, src, **kw):
        rt = NodusRuntime(timeout_ms=None, max_steps=None, **kw)
        try:
            start = time.perf_counter()
            result = rt.run_source(src, filename="t.nd")
            return result, time.perf_counter() - start
        finally:
            rt.shutdown()

    # closes: #424
    def test_a_runtime_default_bounds_a_blocking_handler(self):
        result, elapsed = self._run(
            'let r = agent_call("t.slow", {})\nprint(r["error"]["message"])\n',
            agent_timeout_ms=300,
        )
        self.assertTrue(result.get("ok"), result)
        self.assertLess(
            elapsed, BLOCK_S,
            f"the run took {elapsed:.2f}s; the handler blocks {BLOCK_S}s and the "
            "deadline was 300ms, so the call was not bounded",
        )
        self.assertIn("timed out", result["stdout"])
        self.assertEqual(len(self.calls), 1, "the handler should still have been invoked")

    # closes: #424
    def test_a_step_timeout_bounds_a_blocking_handler(self):
        _result, elapsed = self._run(
            'workflow w {\n'
            '  step s with { timeout_ms: 300 } { action agent "t.slow" with { } }\n'
            '}\n'
            'let r = run_workflow(w)\n'
        )
        self.assertLess(
            elapsed, BLOCK_S,
            f"the run took {elapsed:.2f}s; the step's own timeout_ms did not reach "
            "the handler",
        )

    def test_the_timeout_is_reported_as_an_ordinary_agent_failure(self):
        """So a step's `retries` and the retry classifier act on it like any other."""
        result, _ = self._run(
            'let r = agent_call("t.slow", {})\nprint(r["ok"])\n', agent_timeout_ms=200
        )
        self.assertIn("false", result["stdout"])

    def test_an_abandoned_handler_is_recorded(self):
        """The cost of the approach, made visible rather than hidden."""
        self._run('let r = agent_call("t.slow", {})\n', agent_timeout_ms=200)
        self.assertEqual(abandoned_agent_call_count(), 1)
        self.assertEqual(abandoned_agent_calls()[0]["agent"], "t.slow")

    def test_the_abandoned_record_is_bounded(self):
        """An unbounded record would be this same bug one level up: a server whose
        provider hangs on every call would accumulate a row per call forever."""
        from nodus.services.agent_runtime import _ABANDONED_MAX, _record_abandoned

        for _ in range(_ABANDONED_MAX + 25):
            _record_abandoned("t.slow", 100.0)
        self.assertEqual(len(abandoned_agent_calls()), _ABANDONED_MAX)
        self.assertEqual(abandoned_agent_call_count(), _ABANDONED_MAX + 25)

    # --- controls: the bound must not change anything else -------------------

    def test_no_bound_configured_leaves_behaviour_unchanged(self):
        """Backwards compatible: unbounded stays unbounded unless a host asks."""
        result, elapsed = self._run('let r = agent_call("t.slow", {})\nprint(r["ok"])\n')
        self.assertIn("true", result["stdout"])
        self.assertGreaterEqual(elapsed, BLOCK_S - 0.5)
        self.assertEqual(abandoned_agent_call_count(), 0)

    def test_a_fast_handler_is_untouched_by_a_bound(self):
        result, elapsed = self._run(
            'let r = agent_call("t.fast", {})\nprint(r["result"]["quick"])\n',
            agent_timeout_ms=5000,
        )
        self.assertIn("true", result["stdout"])
        self.assertLess(elapsed, 2.0)
        self.assertEqual(abandoned_agent_call_count(), 0)

    def test_a_handler_that_raises_still_reports_its_own_error(self):
        """The worker thread must re-raise on the caller's side, not swallow."""
        register_agent("t.boom", lambda p: (_ for _ in ()).throw(ValueError("kaboom")))
        try:
            result, _ = self._run(
                'let r = agent_call("t.boom", {})\nprint(r["error"]["message"])\n',
                agent_timeout_ms=5000,
            )
            self.assertIn("kaboom", result["stdout"])
        finally:
            unregister_agent("t.boom")


if __name__ == "__main__":
    unittest.main()


# closes: #596
class TheStepBudgetIsReadWhereItIsKnowableTests(unittest.TestCase):
    """`action agent` must be bounded too, not just a synchronous `agent_call`.

    #398 made `action agent` dispatch its handler off the scheduler thread so
    independent steps overlap. #424 then bounded agent handlers by reading the
    step budget from `vm.scheduler.current_task` — which the scheduler sets just
    before a coroutine resume and clears in the matching `finally`, so it is
    readable only *on that thread, inside that resume*. The worker runs after the
    coroutine suspends, so it read `None` and the bound never applied.

    It appeared to work because of a race: the worker thread often called
    `_effective_timeout_ms` before the scheduler cleared `current_task`. Locally
    the worker usually won; on CI under coverage it did not, and the run took the
    handler's full block every time.

    That race is why these tests assert on **thread identity** rather than on
    elapsed time. Which thread reads the budget is deterministic; whether it wins
    the race is not, and a timing assertion here would pass on this machine while
    the bound stayed broken on another.
    """

    def setUp(self):
        reset_abandoned_agent_calls()
        self.slow_calls = []
        register_agent("t.slow596", self._slow)

    def tearDown(self):
        unregister_agent("t.slow596")
        reset_abandoned_agent_calls()

    def _slow(self, payload):
        self.slow_calls.append(1)
        time.sleep(BLOCK_S)
        return {"ok": True}

    def test_the_budget_is_never_read_from_a_worker_thread(self):
        """The property the fix establishes, stated without reference to timing."""
        from nodus.services import agent_runtime as ar
        from nodus.vm import vm as vm_mod

        main_thread = threading.current_thread().ident
        threads_that_read = []
        original = ar._effective_timeout_ms

        def _spy(vm):
            threads_that_read.append(threading.current_thread().ident)
            return original(vm)

        # Both bindings. `vm.py` does `from ... import _effective_timeout_ms`, so
        # it holds its own reference and patching the agent_runtime attribute
        # alone reaches neither call site that matters -- which the vacuity guard
        # below caught rather than letting the test pass on an empty list.
        ar._effective_timeout_ms = _spy
        vm_mod._effective_timeout_ms = _spy
        try:
            rt = NodusRuntime(timeout_ms=None, max_steps=None)
            try:
                rt.run_source(
                    'workflow w {\n'
                    '  step s with { timeout_ms: 300 } { action agent "t.slow596" with { } }\n'
                    '}\n'
                    'let r = run_workflow(w)\n',
                    filename="t.nd",
                )
            finally:
                rt.shutdown()
        finally:
            ar._effective_timeout_ms = original
            vm_mod._effective_timeout_ms = original

        self.assertTrue(threads_that_read,
                        "the budget was never consulted, so this proves nothing")
        off_thread = [t for t in threads_that_read if t != main_thread]
        self.assertEqual(
            [], off_thread,
            "the step budget was read on a worker thread, where "
            "`scheduler.current_task` has already been cleared — so whether the "
            "bound applies is a race (#596)",
        )

    def test_an_explicitly_captured_deadline_is_honoured(self):
        """The seam the fix needs: a caller that already knows the budget can hand
        it over, and `None` still means unbounded rather than 'not supplied'."""
        from nodus.services.agent_runtime import call_agent

        started = time.perf_counter()
        result = call_agent("t.slow596", {}, vm=None, timeout_ms=200)
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, BLOCK_S,
                        "an explicitly passed deadline was ignored")
        self.assertFalse(result.get("ok"))
        self.assertEqual(1, len(self.slow_calls),
                         "the handler should still have been invoked")

    def test_the_deadline_is_captured_before_the_worker_starts(self):
        """Assert on the source, because a behaviour test here is a race.

        Ordering is the whole fix: past `_dispatch_agent_async`'s guard the budget
        is readable by construction, and after the thread starts it is not.
        """
        import ast
        import inspect
        from nodus.vm.vm import VM

        source = inspect.getsource(VM._dispatch_agent_async)
        tree = ast.parse(source.lstrip())
        capture_line = thread_line = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "id", None) == "_effective_timeout_ms":
                capture_line = node.lineno if capture_line is None else capture_line
            if (isinstance(node.func, ast.Attribute) and node.func.attr == "start"):
                thread_line = node.lineno if thread_line is None else thread_line

        self.assertIsNotNone(capture_line,
                             "_dispatch_agent_async no longer captures the budget; "
                             "the worker would compute it after suspension (#596)")
        self.assertIsNotNone(thread_line, "no worker thread is started any more")
        self.assertLess(capture_line, thread_line,
                        "the budget must be captured before the worker starts")
