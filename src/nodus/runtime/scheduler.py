"""Coroutine scheduler and event loop for Nodus."""

from __future__ import annotations

import heapq
import sys
import time
from collections import deque
from typing import Any

from nodus.runtime.coroutine import Coroutine
from nodus.runtime.diagnostics import LangRuntimeError, RuntimeLimitExceeded, format_error
from nodus.runtime.runtime_stats import runtime_time_ms
from nodus.runtime.runtime_events import RuntimeEvent

TASK_STEP_BUDGET = 1000
SLEEP_KEY = "__sleep_ms"
CHANNEL_WAIT_KEY = "__channel_wait"


class SleepRequest:
    def __init__(self, ms: float):
        self.ms = ms


class Scheduler:
    def __init__(self, vm, *, trace: bool = False, trace_output=print):
        self.vm = vm
        self.ready_queue: deque[Any] = deque()
        self.queue = self.ready_queue
        self.timers: list[tuple[float, int, Coroutine]] = []
        self.sleeping_tasks: set[int] = set()
        self.completed_tasks: list[object] = []
        self._completed_ids: set[int] = set()
        self.total_tasks_spawned = 0
        self.total_resumes = 0
        self.tasks: dict[int, object] = {}
        self.current_task: object | None = None
        self._next_id = 1
        self.trace = trace
        # clock_fn returns current time in ms; overridden in test mode for virtual time
        self.clock_fn = runtime_time_ms
        self.trace_output = trace_output
        self._counter = 0
        self.task_ages: dict[int, int] = {}
        self._io_channels: list = []
        self._recv_channels: set = set()
        # #402: channels with senders parked on a full queue, mirroring
        # `_recv_channels`. Keeps the loop alive while a blocked send could
        # still be woken, and feeds the deadlock diagnosis when it cannot.
        self._send_channels: set = set()
        self._run_loop_called: bool = False
        self._spawned_without_loop: int = 0
        self._coroutine_errors: list = []
        # #395/#157: coroutines parked in `wait`, keyed by the id of the task
        # they are waiting on. Kept here rather than on the target so a task
        # that is never resumed still has its waiters reachable for the deadlock
        # report, and so `release_waiters` is one place rather than a branch in
        # every completion path.
        self._waiters: dict[int, list] = {}

    def _trace(self, message: str) -> None:
        if self.trace:
            self.trace_output(message)

    def _emit_event(self, event_type: str, coroutine=None, data: dict | None = None) -> None:
        if not hasattr(self.vm, "event_bus") or self.vm.event_bus is None:
            return
        coroutine_id = None
        name = None
        if coroutine is not None:
            self._ensure_metadata(coroutine)
            coroutine_id = coroutine.id
            name = coroutine.name
        self.vm.event_bus.emit(RuntimeEvent(event_type, runtime_time_ms(), coroutine_id=coroutine_id, name=name, data=data))

    def _owner(self, coroutine):
        """The VM a coroutine runs on — the one that spawned it (#339).

        Identical to ``self.vm`` for everything spawned outside a module.
        """
        return getattr(coroutine, "owner_vm", None) or self.vm

    def _ensure_metadata(self, coroutine) -> None:
        if coroutine.id is None:
            coroutine.id = self._next_id
            self._next_id += 1
            self.total_tasks_spawned += 1
            self.tasks[coroutine.id] = coroutine
            self.task_ages[coroutine.id] = self.total_tasks_spawned
        if coroutine.name is None and getattr(coroutine, "closure", None) is not None:
            coroutine.name = coroutine.closure.function.display_name
        if coroutine.name is None:
            coroutine.name = "<anonymous>"
        if coroutine.module is None and getattr(coroutine, "closure", None) is not None:
            # #339: a coroutine spawned inside a module has an `addr` into that
            # module's chunk, not this VM's. Reading self.vm.code_locs raised
            # "list index out of range" for every module coroutine once the
            # caller's scheduler started driving them.
            owner = self._owner(coroutine)
            addr = coroutine.closure.function.addr
            code_locs = owner.code_locs
            module_path = code_locs[addr][0] if 0 <= addr < len(code_locs) else None
            coroutine.module = module_path or owner.source_path
        if coroutine.created_time is None:
            coroutine.created_time = runtime_time_ms()

    def unrun_task_warning(self) -> str | None:
        """"You spawned and never drove the scheduler" — or None if you did (#675).

        The counter has always lived here; the *sentence* used to live in
        `runtime/embedding.py`, so only `NodusRuntime` callers ever saw it. The
        CLI builds a `VM` directly and never constructs a `NodusRuntime`, so
        `nodus run` on a program that spawns and forgets `run_loop()` printed
        nothing, exited 0, and silently did none of the work. Same runtime, two
        doors, two answers.

        This repo has a deliberate CLI-vs-`NodusRuntime` asymmetry, and it does
        **not** cover this. Deny-by-default splits the two because it is a
        decision about authority over work you did not fully author, and a
        developer running a script they just wrote is not that. A warning that
        the work you spawned never ran is worth exactly the same through both
        doors.

        The decision is here so there is one of it. Delivery necessarily differs
        — the embedding accumulates stderr into a `Result`, the CLI prints it —
        and that difference is real rather than a second answer to this question.
        """
        unrun = self._spawned_without_loop
        if unrun <= 0:
            return None
        noun = "task" if unrun == 1 else "tasks"
        return (
            f"\nWarning: {unrun} spawned {noun} never executed"
            " — call run_loop() after spawn() to run them.\n"
        )

    def run_task_graph(self, graph) -> object:
        return self.vm.builtin_run_graph(graph)

    def spawn(self, coroutine) -> None:
        if coroutine.state == "finished":
            return
        self._ensure_metadata(coroutine)
        self._spawned_without_loop += 1
        self.ready_queue.append(coroutine)
        self._emit_event("coroutine_spawn", coroutine)
        self._trace(f"spawn coroutine #{coroutine.id} {coroutine.name}")
        if coroutine.id is not None:
            self.task_ages[coroutine.id] = self.total_tasks_spawned

    def schedule(self, coroutine) -> None:
        if coroutine.state == "finished":
            return
        self.ready_queue.append(coroutine)
        if coroutine.id is not None:
            self.task_ages[coroutine.id] = self.total_resumes

    def _schedule_sleep(self, coroutine, ms: float) -> None:
        delay = max(0.0, ms) / 1000.0
        self._counter += 1
        heapq.heappush(self.timers, (self.clock_fn() + delay * 1000.0, self._counter, coroutine))
        if coroutine.id is not None:
            self.sleeping_tasks.add(coroutine.id)

    def schedule_delay(self, coroutine, ms: float) -> None:
        if coroutine.state == "finished":
            return
        self._ensure_metadata(coroutine)
        self._schedule_sleep(coroutine, ms)

    def _drain_timers(self) -> None:
        now = self.clock_fn()
        while self.timers and self.timers[0][0] <= now:
            _wake, _seq, coroutine = heapq.heappop(self.timers)
            if coroutine.state != "finished":
                if coroutine.id is not None:
                    self.sleeping_tasks.discard(coroutine.id)
                self.ready_queue.append(coroutine)
                self._emit_event("coroutine_wake", coroutine)

    def _extract_sleep_ms(self, value):
        if isinstance(value, dict) and SLEEP_KEY in value:
            return value[SLEEP_KEY]
        return None

    def _extract_channel_wait(self, value):
        if isinstance(value, dict) and CHANNEL_WAIT_KEY in value:
            return value[CHANNEL_WAIT_KEY]
        return None

    def _mark_completed(self, coroutine) -> None:
        if coroutine.id is None:
            return
        if coroutine.id in self._completed_ids:
            return
        self._completed_ids.add(coroutine.id)
        self.completed_tasks.append(coroutine)
        # Every path that settles a task goes through here, so this is the one
        # place a waiter has to be released from (#157/#395).
        self.release_waiters(coroutine)

    def park_waiter(self, waiter, target) -> None:
        """Suspend *waiter* until *target* settles (#157/#395 D8, inside-a-coroutine case)."""
        waiter.state = "suspended"
        waiter.blocked_on = target
        waiter.blocked_reason = "task_wait"
        self._waiters.setdefault(target.id, []).append(waiter)

    def release_waiters(self, target) -> None:
        """Wake everything parked on *target*, now that it has settled.

        Called from every path that finishes a coroutine — normal return, failure,
        cancellation. Missing one would leave a waiter parked forever on a task
        that is already done, which is the deadlock this makes impossible rather
        than diagnosable.

        The waiter is handed the outcome here: `last_result` on success, or a
        pending error that `resume` delivers into it (D6 — a joined failure is
        raised into the code that asked, and reported once).
        """
        if target.id is None:
            return
        waiters = self._waiters.pop(target.id, [])
        failure = getattr(target, "cancelled_error", None) or getattr(target, "failure", None)
        for waiter in waiters:
            waiter.blocked_on = None
            waiter.blocked_reason = None
            if failure is not None:
                waiter.pending_wait_error = failure
            elif waiter.stack:
                waiter.stack[-1] = target.last_result
            if waiter.state == "suspended":
                self.ready_queue.append(waiter)

    def has_parked_waiters(self) -> bool:
        return any(self._waiters.values())

    def drive_until_settled(self, target) -> None:
        """Run the loop until *target* settles — the top-level `wait` (D8).

        Delegates to `run_loop` with a stopping condition rather than driving
        coroutines itself. Two loops that resume coroutines would be two answers
        to one question, and the second would be the one that forgot the timeout
        check, or the module-context restore, or the error path -- which is the
        defect shape this codebase catalogues. There is one driver.

        A **bounded** drive, not an isolated one, and the distinction is the
        point. It still runs other coroutines, because a task can depend on its
        siblings and refusing to run them would deadlock a join on a queue it
        declined to drain. What it bounds is the *stopping condition*: it returns
        when the target settles rather than when the deque empties, so a library
        function no longer runs its caller's unrelated long-running work to
        completion as the price of waiting for its own.
        """
        self.run_loop(until=lambda: target.state == "finished")

    def unpark(self, coroutine) -> None:
        """Remove *coroutine* from every registry that could later wake it (#395).

        Cancelling a parked coroutine has to unpark it first, and there are five
        places it can be parked: the ready deque, the timer heap, a channel's
        receiver queue, a channel's sender queue, and the thread-backed IO wait.
        An unpark that clears four of five is a cancel that silently hangs on the
        fifth — which is why `BLOCKED_REASONS` exists as a named set (D4) and why
        this is one method rather than a branch at each call site.

        Deliberately total rather than dispatching on `blocked_reason`: the
        reason records *why* it parked, and a coroutine that has been requeued
        may sit in the deque with a stale reason. Clearing everything is cheap
        and cannot be half-right.
        """
        try:
            self.ready_queue.remove(coroutine)
        except ValueError:
            pass

        if self.timers:
            remaining = [entry for entry in self.timers if entry[2] is not coroutine]
            if len(remaining) != len(self.timers):
                self.timers = remaining
                heapq.heapify(self.timers)
        if coroutine.id is not None:
            self.sleeping_tasks.discard(coroutine.id)

        blocked_on = getattr(coroutine, "blocked_on", None)
        if blocked_on is not None:
            receivers = getattr(blocked_on, "waiting_receivers", None)
            if receivers is not None:
                for waiter in [w for w in receivers if w is coroutine]:
                    try:
                        receivers.remove(waiter)
                    except ValueError:  # pragma: no cover - concurrent drain
                        pass
            senders = getattr(blocked_on, "waiting_senders", None)
            if senders is not None:
                for entry in [e for e in senders if e[0] is coroutine]:
                    try:
                        senders.remove(entry)
                    except ValueError:  # pragma: no cover - concurrent drain
                        pass
            # Deregister the channel once nothing is parked on it. Removing the
            # waiter alone leaves the channel in `_recv_channels`/`_send_channels`,
            # so the loop still believes a blocked operation is pending and
            # reports "Deadlock: 0 coroutine(s) blocked on recv()" -- a deadlock
            # of nobody. Found by the test for exactly this case, which is what
            # D4's named set is for: the deque is not the only place a task waits.
            if receivers is not None and not receivers:
                self._recv_channels.discard(blocked_on)
            if senders is not None and not senders:
                self._send_channels.discard(blocked_on)

        coroutine.blocked_on = None
        coroutine.blocked_reason = None

    def _drain_io_channels(self) -> None:
        """Wake coroutines blocked on thread-backed channels that now have data."""
        if not self._io_channels:
            return
        for ch in list(self._io_channels):
            while ch.queue and ch.waiting_receivers:
                value = ch.queue.popleft()
                receiver = ch.waiting_receivers.popleft()
                if getattr(receiver, "state", None) != "suspended":
                    continue
                if receiver.stack:
                    receiver.stack[-1] = value
                receiver.blocked_on = None
                receiver.blocked_reason = None
                self.ready_queue.append(receiver)
            if ch.closed:
                while ch.waiting_receivers:
                    r = ch.waiting_receivers.popleft()
                    if getattr(r, "state", None) == "suspended":
                        if r.stack:
                            r.stack[-1] = None
                        r.blocked_on = None
                        r.blocked_reason = None
                        self.ready_queue.append(r)
                self._io_channels.remove(ch)
                self._recv_channels.discard(ch)
            elif not ch.waiting_receivers:
                self._recv_channels.discard(ch)

    def run_loop(self, on_complete=None, on_error=None, until=None) -> None:
        """Drive coroutines until there is no work, or until `until()` holds.

        `until` is the top-level `wait`'s stopping condition (#157/#395 D8).
        It is a parameter rather than a second loop so there is exactly one
        place that resumes a coroutine, applies its timeout, restores its
        module context and routes its failure.
        """
        self._run_loop_called = True
        self._spawned_without_loop = 0
        stop = False
        # Note: _spawned_without_loop is also reset at the end of this method.
        # Coroutines spawned *during* run_loop (e.g. by task callbacks) go into
        # ready_queue and are drained by the loop below, so they are not unrun.
        while (self.ready_queue or self.timers or self._io_channels
               or self._recv_channels or self._send_channels
               or self.has_parked_waiters()):
            if until is not None and until():
                break
            self._drain_timers()
            self._drain_io_channels()
            if not self.ready_queue:
                if not self.timers and not self._io_channels and not self._recv_channels and not self._send_channels:
                    break
                if self.timers:
                    wake_time = self.timers[0][0]
                    now = self.clock_fn()
                    if wake_time > now:
                        poll = 0.001 if self._io_channels else (wake_time - now) / 1000.0
                        _t0 = time.monotonic()
                        time.sleep(min(poll, (wake_time - now) / 1000.0))
                        if self.vm.deadline is not None:
                            self.vm.deadline += time.monotonic() - _t0
                elif self._io_channels:
                    _t0 = time.monotonic()
                    time.sleep(0.001)
                    if self.vm.deadline is not None:
                        self.vm.deadline += time.monotonic() - _t0
                elif self._recv_channels or self._send_channels:
                    # No runnable coroutines, no timers, no system channels — only blocked
                    # channel operations remain. Nothing can ever wake them: deadlock.
                    # Senders too, since #402 — a send parked on a full channel with no
                    # receiver left is the mirror image of the recv case.
                    def _blocked(reason: str) -> list[str]:
                        return [
                            getattr(c, "name", None) or f"<coroutine #{getattr(c, 'id', '?')}>"
                            for c in self.tasks.values()
                            if getattr(c, "state", None) == "suspended"
                            and getattr(c, "blocked_reason", None) == reason
                        ]

                    recv_names = _blocked("channel_recv")
                    send_names = _blocked("channel_send")
                    parts = []
                    if recv_names or not send_names:
                        detail = f": {', '.join(recv_names)}" if recv_names else ""
                        parts.append(
                            f"{len(recv_names)} coroutine(s) blocked on recv() with no "
                            f"possible sender{detail}"
                        )
                    if send_names:
                        detail = f": {', '.join(send_names)}" if send_names else ""
                        parts.append(
                            f"{len(send_names)} coroutine(s) blocked on send() with no "
                            f"possible receiver{detail}"
                        )
                    raise LangRuntimeError("deadlock", "Deadlock: " + "; ".join(parts))
                self._drain_timers()
                self._drain_io_channels()
                if not self.ready_queue:
                    continue

            coroutine = self.ready_queue.popleft()
            if coroutine.state == "finished":
                continue
            if coroutine.task_timeout_ms is not None and coroutine.task_started_at is not None:
                now = runtime_time_ms()
                if now - coroutine.task_started_at > coroutine.task_timeout_ms:
                    err = LangRuntimeError("timeout", "Task timed out")
                    # #502: unwind before dropping. This used to discard the
                    # coroutine where it stood, so its pending `finally` blocks
                    # never ran -- a step holding a lock or an open transaction
                    # lost its release in exactly the circumstances cleanup exists
                    # for, contradicting runtime invariant I-VM-06.
                    #
                    # Only when there is something to run: a coroutine with no
                    # pending handlers takes the original path untouched, so the
                    # common case gains no extra resume. `cancelling` guards
                    # re-entry, since a `finally` that suspends would otherwise be
                    # timed out again and unwound twice.
                    if coroutine.cancelling is None and any(
                        finally_ip for _h, finally_ip, _s, _f in coroutine.handler_stack
                    ):
                        owner = self._owner(coroutine)
                        owner.task_step_budget = TASK_STEP_BUDGET
                        owner._budget_exceeded = False
                        try:
                            owner.unwind_cancelled_coroutine(coroutine, err)
                        except Exception:
                            # The unwind delivers the timeout, or a `finally` threw
                            # something else. Either way the coroutine is done and
                            # `err` is what the step failed on.
                            pass
                        finally:
                            owner.task_step_budget = None
                            owner._budget_exceeded = False
                    self._mark_completed(coroutine)
                    if coroutine.id is not None:
                        self.sleeping_tasks.discard(coroutine.id)
                    if on_error is not None:
                        stop = bool(on_error(coroutine, err))
                    if stop:
                        break
                    continue
            try:
                self.current_task = coroutine
                self.total_resumes += 1
                coroutine.resume_count += 1
                now = runtime_time_ms()
                coroutine.last_resume = now
                coroutine.last_run_time = now
                if coroutine.task_timeout_ms is not None and coroutine.task_started_at is None:
                    coroutine.task_started_at = now
                self._emit_event("coroutine_resume", coroutine)
                self._trace(f"resume coroutine #{coroutine.id}")
                owner = self._owner(coroutine)
                owner.task_step_budget = TASK_STEP_BUDGET
                owner._budget_exceeded = False
                result = owner.builtin_coroutine_resume(coroutine)
            except RuntimeLimitExceeded:
                # Execution-limit breaches (deadline, step-limit) are not recoverable
                # per-coroutine errors — they must propagate so the host (run_source /
                # run_file / CLI) can return ok=False and a nonzero exit code.
                # Do NOT swallow with the broad except below.
                raise
            except Exception as _e:
                # #395 D6: recorded on the task so a waiter can be handed it.
                # It still goes to _coroutine_errors -- an UNjoined failure keeps
                # today's behaviour byte for byte; `wait` is what removes it from
                # that list, not the failing.
                coroutine.failure = _e
                # D6: reported once. A joined failure belongs to the code that
                # asked for the outcome; duplicating it to stderr and the error
                # list would make one failure look like two.
                if not coroutine.waited_on:
                    self._coroutine_errors.append(_e)
                self.release_waiters(coroutine)
                self._mark_completed(coroutine)
                if coroutine.id is not None:
                    self.sleeping_tasks.discard(coroutine.id)
                if on_error is not None:
                    stop = bool(on_error(coroutine, _e))
                if not getattr(_e, "_retry_pending", False) and not coroutine.waited_on:
                    print(format_error(_e, path=self.vm.source_path), file=sys.stderr)
                if stop:
                    break
                continue
            finally:
                self.current_task = None
                owner = self._owner(coroutine)
                owner.task_step_budget = None
                owner._budget_exceeded = False

            if coroutine.state != "suspended":
                if coroutine.state == "finished":
                    self._mark_completed(coroutine)
                    self._emit_event("coroutine_complete", coroutine)
                    self._trace(f"complete coroutine #{coroutine.id}")
                    if on_complete is not None:
                        stop = bool(on_complete(coroutine)) or stop
                continue

            channel_wait = self._extract_channel_wait(result)
            if channel_wait is not None:
                self._trace(f"block coroutine #{coroutine.id} channel")
                continue

            sleep_ms = self._extract_sleep_ms(result)
            if sleep_ms is not None:
                if isinstance(sleep_ms, bool) or not isinstance(sleep_ms, (int, float)):
                    err = LangRuntimeError("type", "sleep(ms) expects a number")
                    if hasattr(self.vm, "emit_runtime_error"):
                        self.vm.emit_runtime_error(err)
                    print(format_error(err, path=self.vm.source_path), file=sys.stderr)
                    continue
                self._trace(f"sleep coroutine #{coroutine.id} {float(sleep_ms)}")
                self._emit_event("coroutine_sleep", coroutine, {"ms": float(sleep_ms)})
                self._schedule_sleep(coroutine, float(sleep_ms))
                continue

            self._trace(f"yield coroutine #{coroutine.id}")
            self._emit_event("coroutine_yield", coroutine)
            self.ready_queue.append(coroutine)
            if stop:
                break
        # Any coroutines spawned during this run_loop were drained above.
        # Reset so the embedding's unrun-task check only catches spawns that
        # happen after the loop exits (i.e. genuinely unexecuted tasks).
        self._spawned_without_loop = 0
