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
            module_path, _line, _col = self.vm.code_locs[coroutine.closure.function.addr]
            coroutine.module = module_path or self.vm.source_path
        if coroutine.created_time is None:
            coroutine.created_time = runtime_time_ms()

    def run_task_graph(self, graph) -> object:
        return self.vm.builtin_run_graph(graph)

    def spawn(self, coroutine) -> None:
        if coroutine.state == "finished":
            return
        self._ensure_metadata(coroutine)
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

    def run_loop(self, on_complete=None, on_error=None) -> None:
        stop = False
        while self.ready_queue or self.timers or self._io_channels or self._recv_channels:
            self._drain_timers()
            self._drain_io_channels()
            if not self.ready_queue:
                if not self.timers and not self._io_channels and not self._recv_channels:
                    break
                if self.timers:
                    wake_time = self.timers[0][0]
                    now = self.clock_fn()
                    if wake_time > now:
                        poll = 0.001 if self._io_channels else (wake_time - now) / 1000.0
                        time.sleep(min(poll, (wake_time - now) / 1000.0))
                elif self._io_channels:
                    time.sleep(0.001)
                elif self._recv_channels:
                    # No runnable coroutines, no timers, no system channels — only blocked
                    # recv() calls remain. Nothing can ever wake them: deadlock.
                    blocked = [
                        c for c in self.tasks.values()
                        if getattr(c, "state", None) == "suspended"
                        and getattr(c, "blocked_reason", None) == "channel_recv"
                    ]
                    names = [
                        getattr(c, "name", None) or f"<coroutine #{getattr(c, 'id', '?')}>"
                        for c in blocked
                    ]
                    detail = f": {', '.join(names)}" if names else ""
                    raise LangRuntimeError(
                        "deadlock",
                        f"Deadlock: {len(blocked)} coroutine(s) blocked on recv() with no "
                        f"possible sender{detail}",
                    )
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
                self._emit_event("coroutine_resume", coroutine)
                self._trace(f"resume coroutine #{coroutine.id}")
                self.vm.task_step_budget = TASK_STEP_BUDGET
                self.vm._budget_exceeded = False
                result = self.vm.builtin_coroutine_resume(coroutine)
            except RuntimeLimitExceeded:
                # Execution-limit breaches (deadline, step-limit) are not recoverable
                # per-coroutine errors — they must propagate so the host (run_source /
                # run_file / CLI) can return ok=False and a nonzero exit code.
                # Do NOT swallow with the broad except below.
                raise
            except Exception as _e:
                print(format_error(_e, path=self.vm.source_path), file=sys.stderr)
                self._mark_completed(coroutine)
                if coroutine.id is not None:
                    self.sleeping_tasks.discard(coroutine.id)
                if on_error is not None:
                    stop = bool(on_error(coroutine, _e))
                if stop:
                    break
                continue
            finally:
                self.current_task = None
                self.vm.task_step_budget = None
                self.vm._budget_exceeded = False

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
