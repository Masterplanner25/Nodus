import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.runner import run_source  # needed for SCHED-003 (sandbox path)


def run_program(src: str, source_path: str | None = None) -> tuple[list[str], str]:
    vm = lang.VM([], {}, code_locs=[], source_path=source_path)
    _loader = ModuleLoader(project_root=None, vm=vm)
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        _loader.load_module_from_source(src, module_name=source_path or "<memory>")
    return out_buf.getvalue().splitlines(), err_buf.getvalue()


class SchedulerTests(unittest.TestCase):
    def test_interleaves_coroutines(self):
        src = """
fn worker(name) {
    print("start " + name)
    yield
    print("resume " + name)
}

let a = coroutine(fn() { worker("A") })
let b = coroutine(fn() { worker("B") })
spawn(a)
spawn(b)
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["start A", "start B", "resume A", "resume B"])
        self.assertEqual(err.strip(), "")

    def test_sleep_allows_other_tasks_to_run(self):
        src = """
import "std:async"

fn sleeper() {
    print("wait")
    sleep(50)
    print("done")
}

fn fast() {
    print("fast")
    yield
    print("fast2")
}

let a = coroutine(fn() { sleeper() })
let b = coroutine(fn() { fast() })
spawn(a)
spawn(b)
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["wait", "fast", "fast2", "done"])
        self.assertEqual(err.strip(), "")

    def test_error_isolation(self):
        src = """
fn bad() {
    throw "boom"
}

fn good() {
    print("ok")
}

spawn(coroutine(bad))
spawn(coroutine(good))
run_loop()
"""
        out, err = run_program(src, source_path="main.nd")
        self.assertEqual(out, ["ok"])
        self.assertIn("boom", err)


class SchedulerSandboxLimitTests(unittest.TestCase):
    """SCHED-003: coverage for the run_source (sandbox) path with an active limit.

    Prior tests used ModuleLoader directly (deadline=None) or virtual clock,
    so RuntimeLimitExceeded propagation through the scheduler was never exercised.
    These tests go through run_source so sandbox limits are active.

    Implementation note on test design:
    - The deadline check fires every _deadline_check_interval (100) instructions,
      so short coroutine bodies complete before it fires.
    - These tests use a CPU tight-loop (no sleep) with a 1ms timeout_ms.
      Module loading takes ~5ms so the deadline is already exceeded by the time
      the coroutine runs; the first 100-instruction batch fires the check.
    - This exactly mirrors the `nodus run` invocation path.

    Pre-fix failure (SCHED-002 confirmed empirically):
      With the `except Exception` handler swallowing RuntimeLimitExceeded in
      scheduler.run_loop, result["ok"] was True even after a limit breach —
      the host had no signal that anything went wrong.
    Post-fix: `except RuntimeLimitExceeded: raise` lets the error propagate
      to run_source's outer handler → ok=False / detectable error message.
    """

    def test_deadline_breach_in_coroutine_propagates_as_ok_false(self):
        """SCHED-002/003: execution-limit breach inside a spawned coroutine must
        yield ok=False, not ok=True.

        Uses a CPU tight-loop inside the coroutine with a 1ms deadline.  Module
        loading takes ~5ms so the deadline is already passed when the coroutine
        starts; the first 100-instruction check fires the RuntimeLimitExceeded.

        Pre-fix verified: with the broad `except Exception` swallowing the error,
        run_loop() returned normally, no more instructions in main script,
        load_module_from_source succeeded → result["ok"] was True.
        Post-fix: RuntimeLimitExceeded propagates → ok=False.
        """
        script = """
let c = coroutine(fn() {
    let i = 0
    while (i < 100000) {
        i = i + 1
    }
    print("should not reach")
})
spawn(c)
run_loop()
"""
        result, _ = run_source(script, filename="limit_test.nd", timeout_ms=1)
        self.assertFalse(
            result["ok"],
            "Expected ok=False when execution limit is breached inside a coroutine, "
            "got ok=True. This is SCHED-002: RuntimeLimitExceeded is swallowed by "
            "the scheduler's broad except Exception handler, and when run_loop() is "
            "the last statement the host cannot detect the breach (exit 0).",
        )
        self.assertNotIn("should not reach", result.get("stdout", ""))

    def test_deadline_breach_error_message_is_detectable(self):
        """After a limit breach the result error must mention the timeout."""
        script = """
let c = coroutine(fn() {
    let i = 0
    while (i < 100000) { i = i + 1 }
})
spawn(c)
run_loop()
"""
        result, _ = run_source(script, filename="limit_test2.nd", timeout_ms=1)
        self.assertFalse(result["ok"])
        err = result.get("error") or {}
        msg = str(err.get("message", "")) if isinstance(err, dict) else str(err)
        self.assertIn("timed out", msg.lower(),
                      f"Expected 'timed out' in error message, got: {msg!r}")

    def test_ordinary_coroutine_throw_does_not_propagate(self):
        """Regular per-coroutine errors must NOT propagate — session continues.
        Only RuntimeLimitExceeded propagates.  Use a generous limit so only the
        throw fires, not the deadline.
        """
        script = """
let c = coroutine(fn() {
    throw "boom from coroutine"
})
spawn(c)
run_loop()
print("after loop")
"""
        result, _ = run_source(
            script, filename="coro_err_test.nd", timeout_ms=10_000,
        )
        # "after loop" must print — session continues past a per-coroutine throw
        self.assertIn(
            "after loop", result.get("stdout", ""),
            "Session should continue after an ordinary coroutine error; "
            "'after loop' was not printed.",
        )


if __name__ == "__main__":
    unittest.main()
