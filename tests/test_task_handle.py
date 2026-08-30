"""`cancel` and `wait` — the two task verbs (#395, #157).

The design record is `docs/design/v5/06-task-handle.md`; `04-cancellation.md` owns
what cancellation means and `05-async-library-boundary.md` owns `wait`'s contexts.
Both verbs ship together (D5) because `cancel` has to unpark a task and `wait` is
one of the things a task can be parked on — splitting them would mean shipping an
unpark that could not handle every reason.

The verb is `wait`, not `join` as the design record first said. `join` is already
`std:strings.join` and `std:path.join`, and `examples/project_layout_demo/main.nd`
imports one of them by name — so the builtin silently shadowed an explicit import
and the program failed with an arity error naming neither. See
`test_builtins_shadow_imports.py` for the general defect that made a rename the
right answer rather than a taste question.

Three things get source-level or negative coverage rather than a happy-path
assertion, because each is a place a partial implementation still passes:

  * a failure reported *once* — a behavioural test on the raise alone passes on
    an implementation that also prints it to stderr and appends it to the error
    list, which is what D6 forbids;
  * `finally` running and `catch` NOT running under cancellation — asserting only
    that the task stopped passes on an implementation that dropped it where it
    stood, which is the #502 defect;
  * an unjoined failure being byte-identical to today — the compatibility half,
    and the one nobody would notice breaking.
"""

import io
import os
import sys
import unittest
from contextlib import redirect_stderr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.coroutine import BLOCKED_REASON_SET  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def run(source: str) -> dict:
    return NodusRuntime(timeout_ms=None).run_source(source)


def out(source: str) -> str:
    result = run(source)
    assert result["ok"], result.get("error")
    return result.get("stdout") or ""


# closes: #157
class SpawnReturnsTheHandleTests(unittest.TestCase):
    """D2. `spawn` returned nil, and that was the whole mechanical cause of #157:
    the value channel already existed on the coroutine and was unreachable."""

    def test_spawn_returns_something_that_tracks_the_task(self):
        text = out(
            "fn main() {\n"
            "    let t = spawn(coroutine(fn() { return 77i }))\n"
            '    print("before: \\(coroutine_status(t))")\n'
            "    run_loop()\n"
            '    print("after: \\(coroutine_status(t))")\n'
            "}\n"
        )
        self.assertIn("before: created", text)
        self.assertIn("after: finished", text)

    def test_the_handle_is_the_coroutine_not_a_record(self):
        """D1. A record would be a *value*, so its `state` would freeze at spawn
        time — a handle whose most-read field is permanently stale."""
        text = out(
            "fn main() {\n"
            "    let c = coroutine(fn() { return 1i })\n"
            "    let t = spawn(c)\n"
            '    print("same: \\(coroutine_status(c) == coroutine_status(t))")\n'
            "}\n"
        )
        self.assertIn("same: true", text)


# closes: #157
class WaitTests(unittest.TestCase):
    def test_wait_at_top_level_drives_until_the_task_settles(self):
        self.assertIn("77", out(
            "fn main() {\n"
            "    let t = spawn(coroutine(fn() { return 77i }))\n"
            '    print("got \\(wait(t))")\n'
            "}\n"
        ))

    def test_wait_inside_a_coroutine_suspends_and_resumes_with_the_value(self):
        """D8's other context. Parking rather than driving is what keeps a
        library from stealing its caller's scheduler."""
        self.assertIn("got 42", out(
            "fn main() {\n"
            "    let w = spawn(coroutine(fn() { sleep(5i); return 42i }))\n"
            '    spawn(coroutine(fn() { print("got \\(wait(w))") }))\n'
            "    run_loop()\n"
            "}\n"
        ))

    def test_waiting_twice_returns_the_same_value(self):
        """`last_result` persists; there is no consumption. This is what makes
        `wait` safe in a loop (05 §6.5)."""
        text = out(
            "fn main() {\n"
            "    let t = spawn(coroutine(fn() { return 5i }))\n"
            '    print("a \\(wait(t))")\n'
            '    print("b \\(wait(t))")\n'
            "}\n"
        )
        self.assertIn("a 5", text)
        self.assertIn("b 5", text)

    def test_waiting_on_a_finished_task_is_immediate(self):
        self.assertIn("done 9", out(
            "fn main() {\n"
            "    let t = spawn(coroutine(fn() { return 9i }))\n"
            "    run_loop()\n"
            '    print("done \\(wait(t))")\n'
            "}\n"
        ))

    def test_waiting_on_a_never_spawned_task_is_an_error(self):
        """Asymmetric with `cancel`, deliberately: a cancel usually cannot know
        the target's state, but a wait is asking for a value and there is no
        value to invent (05 §6.5)."""
        result = run(
            "fn main() {\n"
            "    let c = coroutine(fn() { return 1i })\n"
            "    print(wait(c))\n"
            "}\n"
        )
        self.assertFalse(result["ok"])
        self.assertIn("never spawned", (result.get("error") or {}).get("message", ""))

    def test_a_task_cannot_wait_on_itself(self):
        result = run(
            "fn main() {\n"
            "    let c = coroutine(fn() { return 1i })\n"
            "    spawn(c)\n"
            "    spawn(coroutine(fn() { wait(c) }))\n"
            "    run_loop()\n"
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))


# closes: #395
class WaitPropagatesFailureTests(unittest.TestCase):
    """D6. Not a new door: `resume(c)` has always raised a task's failure into
    the resumer. `wait` and `resume` ask one question — drive this task, give me
    its outcome — and one raising while the other collected would be that
    question answered in two voices."""

    def test_a_waited_failure_is_raised_into_the_waiter(self):
        self.assertIn("caught: boom", out(
            "fn main() {\n"
            '    let t = spawn(coroutine(fn() { throw "boom" }))\n'
            '    try { wait(t) } catch e { print("caught: \\(e.message)") }\n'
            "}\n"
        ))

    def test_a_waited_failure_is_reported_once(self):
        """The half a behavioural test misses. Asserting only that `wait` raises
        passes on an implementation that ALSO prints the trace to stderr and
        appends to the scheduler's error list — which is exactly what D6 says
        must not happen."""
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            result = run(
                "fn main() {\n"
                '    let t = spawn(coroutine(fn() { throw "boom" }))\n'
                "    try { wait(t) } catch e { print(e.message) }\n"
                "}\n"
            )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertNotIn("boom", buffer.getvalue(),
                         "a waited failure was also reported to stderr")

    def test_an_unwaited_failure_keeps_todays_behaviour(self):
        """The compatibility half. `run_loop()` still returns the error list, the
        run still succeeds, and the sibling still runs — byte-identical to before
        either verb existed."""
        text = out(
            "fn main() {\n"
            '    spawn(coroutine(fn() { throw "unwaited" }))\n'
            '    spawn(coroutine(fn() { print("sibling ran") }))\n'
            "    let errs = run_loop()\n"
            '    print("errors: \\(errs)")\n'
            "}\n"
        )
        self.assertIn("sibling ran", text)
        self.assertIn("unwaited", text)


# closes: #395
class CancelTests(unittest.TestCase):
    def test_cancel_runs_finally_and_not_catch(self):
        """The #502 guarantee, now reachable from a program. Asserting only that
        the task stopped would pass on an implementation that dropped it where it
        stood — losing the lock release that `finally` exists for."""
        text = out(
            "fn main() {\n"
            "    let t = spawn(coroutine(fn() {\n"
            '        try { sleep(20i); print("BODY AFTER SLEEP") }\n'
            '        catch e { print("CATCH RAN") }\n'
            '        finally { print("finally ran") }\n'
            "    }))\n"
            "    spawn(coroutine(fn() { sleep(1i); cancel(t) }))\n"
            "    run_loop()\n"
            "}\n"
        )
        self.assertIn("finally ran", text)
        self.assertNotIn("CATCH RAN", text, "a task swallowed its own cancellation")
        self.assertNotIn("BODY AFTER SLEEP", text, "the task kept running past the cancel")

    def test_cancel_reports_whether_it_did_anything(self):
        text = out(
            "fn main() {\n"
            "    let t = spawn(coroutine(fn() { sleep(20i) }))\n"
            '    print("first: \\(cancel(t))")\n'
            '    print("second: \\(cancel(t))")\n'
            "}\n"
        )
        self.assertIn("first: true", text)
        self.assertIn("second: false", text)

    def test_cancelling_a_finished_task_is_a_no_op_not_an_error(self):
        """04 §6.3. A caller of a cancel usually cannot know the target's state,
        and raising would push every call site into a check-then-act race."""
        text = out(
            "fn main() {\n"
            "    let t = spawn(coroutine(fn() { return 1i }))\n"
            "    run_loop()\n"
            '    print("cancelled: \\(cancel(t))")\n'
            "}\n"
        )
        self.assertIn("cancelled: false", text)

    def test_waiting_on_a_cancelled_task_raises(self):
        """A cancelled task did not produce a value and must not appear to."""
        self.assertIn("Task cancelled", out(
            "fn main() {\n"
            "    let t = spawn(coroutine(fn() { sleep(20i); return 1i }))\n"
            "    spawn(coroutine(fn() { sleep(1i); cancel(t) }))\n"
            "    run_loop()\n"
            '    try { wait(t) } catch e { print(e.message) }\n'
            "}\n"
        ))


# closes: #395
class BlockedReasonSetTests(unittest.TestCase):
    """D4. The set had to land with the first verb that reads it: cancelling a
    parked task means unparking it, and an unpark handling five of six reasons
    is a cancel that hangs on the sixth."""

    def test_task_wait_is_in_the_named_set(self):
        self.assertIn("task_wait", BLOCKED_REASON_SET)

    def test_cancelling_a_task_parked_on_a_channel_still_unparks_it(self):
        """The reason the set is not cosmetic. A task blocked on `recv` is in a
        channel's waiter queue, not the ready deque — a cancel that only cleared
        the deque would leave it there and the loop would never settle."""
        result = run(
            "fn main() {\n"
            "    let ch = channel()\n"
            "    let t = spawn(coroutine(fn() { recv(ch) }))\n"
            "    spawn(coroutine(fn() { sleep(1i); cancel(t) }))\n"
            "    run_loop()\n"
            '    print("status: \\(coroutine_status(t))")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("status: finished", result.get("stdout") or "")


if __name__ == "__main__":
    unittest.main()
