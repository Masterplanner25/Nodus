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
