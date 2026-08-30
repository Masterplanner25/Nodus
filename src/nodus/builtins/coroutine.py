"""Coroutine, channel, and scheduler builtin functions for the Nodus VM."""

from nodus.runtime.coroutine import Coroutine
from nodus.runtime.channel import (
    Channel,
    ChannelRecvRequest,
    ChannelSendRequest,
    TaskWaitRequest,
)
from nodus.runtime.diagnostics import LangRuntimeError
from nodus.runtime.scheduler import SleepRequest


def register(vm, registry) -> None:
    """Register coroutine, channel, and sleep builtins onto the registry."""

    def builtin_coroutine_create(value):
        closure = vm.ensure_function(value, "coroutine(fn)")
        if len(closure.function.params) != 0:
            vm.runtime_error("call", "coroutine(fn) expects a zero-argument function")
        coro = Coroutine(closure)
        # ASYNC-MOD-003: a coroutine must run in the context its closure was
        # compiled against. Inside a detached module VM, a closure that arrived
        # from the caller (e.g. nested in the list passed to async.parallel)
        # belongs to the caller's chunk — resuming it against the module's
        # bytecode corrupts execution. Pin the owning context at creation.
        if vm._is_foreign_closure(closure):
            coro.module_ctx = vm._caller_vm._capture_module_ctx()
        return coro

    def builtin_coroutine_status(value):
        coroutine = vm.ensure_coroutine(value, "coroutine_status(coroutine)")
        return coroutine.state

    def builtin_coroutine_resume(value):
        from nodus.vm.types import Frame
        coroutine = vm.ensure_coroutine(value, "resume(coroutine)")
        if coroutine.state == "finished":
            vm.runtime_error("runtime", "Cannot resume finished coroutine")
        if coroutine.state == "running":
            vm.runtime_error("runtime", "Cannot resume running coroutine")
        # #394: door 4 of 4, and the one the graph runner actually uses -- a step
        # runs in its own coroutine (I-WFLOW-03), so the runner's
        # `Coroutine(task.function)` carries authorization and a guest's
        # `coroutine(step_fn)` does not.
        #
        # Placed before *any* state is touched, deliberately. Raising after
        # `state = "running"` and `load_coroutine_context` left the coroutine
        # half-started and the caller's module context unrestored: the scheduler
        # kept re-queueing it and `run_loop()` spun until the execution deadline,
        # so the refusal surfaced as "Execution timed out" instead of the message
        # below. A guard that corrupts what it refuses is worse than no guard.
        vm.guard_step_entry(
            coroutine.closure,
            authorized=getattr(coroutine, "step_authorized", False),
        )

        caller_context = vm.save_execution_context()
        # ASYNC-MOD-001: resuming a coroutine restores ITS module context via
        # load_coroutine_context; save the caller's so a re-entrant resume (e.g.
        # test.flush_async stepping tasks, or in-VM module calls) is not clobbered.
        caller_module_ctx = vm._capture_module_ctx() if hasattr(vm, "_capture_module_ctx") else None
        try:
            if coroutine.state == "created":
                call_path, call_line, call_col = vm.current_loc()
                coroutine.stack = list(coroutine.initial_args or [])
                coroutine.frames = []
                coroutine.handler_stack = []
                coroutine.pending_iter_next = None
                coroutine.pending_get_iter = False
                vm.load_coroutine_context(coroutine)
                coroutine.state = "running"
                fn = coroutine.closure.function
                if vm.max_frames is not None and len(vm.frames) + 1 > vm.max_frames:
                    vm.runtime_error("sandbox", "Call stack overflow")
                coro_frame = Frame(
                    return_ip=None,
                    locals={},
                    fn_name=fn.name,
                    call_line=call_line,
                    call_col=call_col,
                    call_path=call_path,
                    closure=coroutine.closure,
                )
                if fn.local_slots:
                    coro_frame.locals_name_to_slot = fn.local_slots
                vm.frames.append(coro_frame)
                if vm.profiler is not None and vm.profiler.enabled:
                    vm.profiler.enter_function(vm.display_name(fn.name))
                vm.ip = fn.addr
            else:
                vm.load_coroutine_context(coroutine)
                coroutine.state = "running"
                # #395 D6: a task this coroutine joined failed. Deliver it here,
                # where there is a stack to raise into -- the same shape
                # `unwind_cancelled_coroutine` uses. `handle_exception` gives the
                # waiter's own `catch` a chance first, so a joined failure is an
                # ordinary catchable error rather than a special case.
                pending = coroutine.pending_wait_error
                if pending is not None:
                    coroutine.pending_wait_error = None
                    if not vm.handle_exception(pending):
                        raise pending

            try:
                status, result = vm.execute()
            except Exception:
                coroutine.state = "finished"
                coroutine.ip = None
                coroutine.stack = []
                coroutine.frames = []
                coroutine.handler_stack = []
                coroutine.pending_iter_next = None
                coroutine.pending_get_iter = False
                raise
            if status in {"yield", "return"}:
                if status == "return":
                    coroutine.last_result = result
                return result
            return None
        finally:
            vm.restore_execution_context(caller_context)
            if caller_module_ctx is not None:
                vm._restore_module_ctx(caller_module_ctx)

    def builtin_spawn(value):
        coroutine = vm.ensure_coroutine(value, "spawn(coroutine)")
        coro_timeout = getattr(vm, "coroutine_timeout_ms", None)
        if coro_timeout is not None:
            coroutine.task_timeout_ms = coro_timeout
        # ASYNC-MOD-003: a coroutine built in the caller and handed to a module
        # function (async.parallel([c1, c2])) carries no context, and the
        # spawning VM's context is the *module's* — resuming against it
        # corrupts execution. Pin the caller's context when the closure is
        # foreign to this VM.
        if coroutine.module_ctx is None and vm._is_foreign_closure(coroutine.closure):
            coroutine.module_ctx = vm._caller_vm._capture_module_ctx()
        # ASYNC-MOD-001: capture the spawning module context so the coroutine's
        # first resume restores it (not a context another coroutine left behind).
        if coroutine.module_ctx is None and hasattr(vm, "_capture_module_ctx"):
            coroutine.module_ctx = vm._capture_module_ctx()
        # ASYNC-MOD-003 (#339): a coroutine is resumed on the VM that spawned it.
        # For an ordinary spawn that is the scheduler's own VM and nothing
        # changes; for one spawned inside a module it is the module's VM, which
        # is what keeps its builtins, its `functions` table (so a caller closure
        # nested in a container is still recognised as foreign) and its
        # `current_coroutine` consistent while the caller's scheduler drives it.
        coroutine.owner_vm = vm
        vm.scheduler.spawn(coroutine)
        # #395/#157 (D2): return the handle. It used to return nil, and that was
        # the whole mechanical cause of #157 -- the value channel a program needs
        # already existed (`Coroutine.last_result`), it was simply not reachable,
        # so libraries reached for a channel to work around a discarded return.
        #
        # The handle is the coroutine itself, not a new record (D1): a record is
        # a value, so a `state` field on it would freeze at spawn time, and
        # `coroutine_status(c)` already tracks the live object across the spawn.
        return coroutine

    def builtin_cancel(value):
        """Stop a task, running its `finally` blocks and no `catch` (#395).

        The unwind mechanism is #502's and is reused unchanged -- adding a second
        one would be the shape this codebase catalogues. What #395 was actually
        missing is a trigger: the scheduler's timeout check was the only caller.

        Returns `true` when this call moved a live coroutine into unwinding, and
        `false` otherwise. Cancelling something already finished, never spawned,
        or already cancelling is **not** an error: the caller of a cancel usually
        cannot know the target's state, and raising would push every call site
        into a check-then-act race (04 §6.3).
        """
        coroutine = vm.ensure_coroutine(value, "cancel(task)")

        if coroutine.state == "finished":
            return False
        if coroutine.cancelling is not None:
            return False          # already unwinding; do not unwind twice
        if coroutine.id is None:
            return False          # never spawned -- no scheduler state to stop

        scheduler = vm.scheduler
        scheduler.unpark(coroutine)

        err = LangRuntimeError("cancelled", "Task cancelled")
        if coroutine.state == "created":
            # Never entered, so there is nothing to unwind and no `finally` to
            # run. Mark it settled so a waiter is released rather than parked
            # on a task that will never be scheduled.
            coroutine.state = "finished"
            coroutine.cancelled_error = err
            scheduler._mark_completed(coroutine)
            scheduler.release_waiters(coroutine)
            return True

        owner = getattr(coroutine, "owner_vm", None) or vm
        try:
            owner.unwind_cancelled_coroutine(coroutine, err)
        except Exception:
            # The unwind delivered the cancellation, or a `finally` threw
            # something else. Either way the task is done and `err` is what it
            # was cancelled with -- the same handling the timeout path uses.
            pass
        coroutine.state = "finished"
        coroutine.cancelled_error = err
        scheduler._mark_completed(coroutine)
        if coroutine.id is not None:
            scheduler.sleeping_tasks.discard(coroutine.id)
        scheduler.release_waiters(coroutine)
        return True

    def _settled_outcome(coroutine):
        """The value a settled task yields to a waiter, or its failure raised.

        One place, because `wait` reaches it from three directions -- already
        finished, released from a park, and settled during a top-level drive --
        and three answers to "what did this task produce" is the shape.
        """
        failure = coroutine.cancelled_error or coroutine.failure
        if failure is not None:
            raise failure
        return coroutine.last_result

    def builtin_wait(value):
        """Wait for a task and return its value; raise its failure (#157, #395).

        Two contexts (D8). Inside a coroutine `wait` **suspends**, like `recv` --
        there is a coroutine to park, so no reentrancy and no scheduler theft. At
        top level there is nothing to suspend, so it **drives** the scheduler
        until the task settles.

        The top-level drive still runs other coroutines: a task can depend on its
        siblings, so refusing to run them would deadlock `wait` on a queue it
        declined to drain. What it fixes is the *stopping condition* -- it returns
        when the task settles rather than when the whole deque empties, so a
        library no longer runs its caller's unrelated work to completion. That is
        a bounded drive, not an isolated one, and the documentation says so.

        A failure is raised into the waiter (D6). That is not a new door: `resume`
        has always propagated a coroutine's failure into the resumer. `wait` and
        `resume` ask one question -- drive this task, give me its outcome -- and
        one raising while the other collected would be that question answered in
        two voices.
        """
        coroutine = vm.ensure_coroutine(value, "wait(task)")

        if coroutine.id is None:
            # Unlike `cancel`, which no-ops: a join is asking for a value and
            # there is no value to invent (05 §6.5). The asymmetry is deliberate.
            vm.runtime_error(
                "runtime",
                "wait(task) on a task that was never spawned — call spawn(c) first",
            )

        if coroutine.state == "finished":
            return _settled_outcome(coroutine)

        # Claimed before the task can settle, so the scheduler's failure path
        # knows the outcome is spoken for and does not also report it (D6).
        # A task that already failed *before* this call was necessarily reported
        # then; "once" cannot retroactively unsay it, and `wait` still raises.
        coroutine.waited_on = True
        scheduler = vm.scheduler
        # "Am I inside a coroutine the scheduler is driving?" -- and the answer is
        # NOT `vm.current_coroutine is not None`. That attribute can hold an
        # ambient coroutine with `id=None` that no scheduler ever queued, and
        # taking the park path against it suspends onto a loop that will never
        # resume it. `_try_enter_foreign_closure` already asks this question and
        # already answers it by identity against `scheduler.current_task`; asking
        # it a second way here would be the shape.
        waiter = vm.current_coroutine
        if waiter is not None and waiter is getattr(scheduler, "current_task", None):
            if waiter is coroutine:
                vm.runtime_error("runtime", "wait(task) on the task doing the joining")
            vm.stack.append(None)
            vm.save_current_coroutine_state(vm.ip + 1)
            scheduler.park_waiter(waiter, coroutine)
            # The sentinel `call_builtin` converts into a yield, exactly as
            # `recv` does. Returning the ("yield", ...) tuple directly does not
            # suspend -- it is handed back as an ordinary value, and the waiter
            # carries on with a tuple where its result should be. That was the
            # first version of this, and the symptom was a printed tuple.
            return TaskWaitRequest(coroutine)

        scheduler.drive_until_settled(coroutine)
        if coroutine.state != "finished":
            vm.runtime_error(
                "deadlock",
                f"wait(task) cannot complete: task '{coroutine.name or coroutine.id}' "
                "is blocked and nothing can wake it",
            )
        return _settled_outcome(coroutine)

    def builtin_run_loop():
        on_error = getattr(vm, "on_error", None)
        scheduler = vm.scheduler
        scheduler._coroutine_errors = []
        # ASYNC-MOD-001: restore the caller's module context after the loop, in
        # case the last-resumed coroutine left a swapped context behind.
        _caller_ctx = vm._capture_module_ctx() if hasattr(vm, "_capture_module_ctx") else None
        scheduler.run_loop(on_error=on_error)
        if _caller_ctx is not None:
            vm._restore_module_ctx(_caller_ctx)
        errors = scheduler._coroutine_errors
        if errors:
            # Return error list so callers can detect partial failure without
            # crashing the session — coroutine isolation is preserved by design.
            return [str(e) for e in errors]
        return None

    def builtin_sleep(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            vm.runtime_error("type", "sleep(ms) expects a number")
        ms = float(value)
        if ms < 0:
            ms = 0.0
        return SleepRequest(ms)

    def builtin_channel(maxsize=0):
        if not (isinstance(maxsize, int) and not isinstance(maxsize, bool)) or maxsize < 0:
            vm.runtime_error("value", "channel() maxsize must be a non-negative integer")
        return Channel(maxsize=maxsize)

    def builtin_send(channel, value):
        ch = vm.ensure_channel(channel, "send(channel, value)")
        if ch.closed:
            vm.runtime_error("runtime", "send on closed channel")
        sender_id = vm.current_coroutine.id if vm.current_coroutine is not None else None
        sender_name = vm.current_coroutine.name if vm.current_coroutine is not None else None
        if ch.waiting_receivers:
            receiver = ch.waiting_receivers.popleft()
            if receiver.stack:
                receiver.stack[-1] = value
            receiver.blocked_on = None
            receiver.blocked_reason = None
            vm.scheduler.schedule(receiver)
            if not ch.waiting_receivers:
                getattr(vm.scheduler, "_recv_channels", set()).discard(ch)
            vm.event_bus.emit_event(
                "channel_send",
                coroutine_id=sender_id,
                name=sender_name,
                data={"queue_size": float(len(ch.queue)), "waiting_receivers": float(len(ch.waiting_receivers))},
            )
            vm.event_bus.emit_event(
                "channel_recv",
                coroutine_id=receiver.id,
                name=receiver.name,
                data={"from_wait": True},
            )
            vm.event_bus.emit_event("channel_wake", coroutine_id=receiver.id, name=receiver.name)
            return None
        if ch.maxsize > 0 and len(ch.queue) >= ch.maxsize:
            # #402: a bounded channel is a backpressure mechanism, not an
            # assertion about queue depth. A producer outrunning its consumer
            # blocks here until a recv frees a slot -- mirroring the blocking
            # receive path, and finally using the `waiting_senders` deque that
            # was declared for exactly this and never wired up. Outside a
            # coroutine there is nothing to suspend, so the raise remains,
            # with the same guidance recv gives.
            sched_now = getattr(vm, "scheduler", None)
            if (
                vm.current_coroutine is None
                or sched_now is None
                or vm.current_coroutine is not getattr(sched_now, "current_task", None)
            ):
                # Not a schedulable context (top level, or a nested execute
                # loop that cannot suspend) -- same ownership test the async
                # subprocess wait uses.
                vm.runtime_error(
                    "runtime",
                    f"send: channel is full (maxsize={ch.maxsize}) and a "
                    f"blocking send needs a coroutine — wrap your code in "
                    f"spawn(coroutine(fn() {{ ... }})) and call run_loop()",
                )
            coroutine = vm.current_coroutine
            coroutine.state = "suspended"
            coroutine.blocked_on = ch
            coroutine.blocked_reason = "channel_send"
            vm.stack.append(None)  # send's return value once the slot frees
            vm.save_current_coroutine_state(vm.ip + 1)
            ch.waiting_senders.append((coroutine, value))
            sched = getattr(vm, "scheduler", None)
            if sched is not None and hasattr(sched, "_send_channels"):
                sched._send_channels.add(ch)
            vm.event_bus.emit_event(
                "channel_block",
                coroutine_id=coroutine.id,
                name=coroutine.name,
                data={"operation": "send"},
            )
            return ChannelSendRequest(ch)
        ch.queue.append(value)
        vm.event_bus.emit_event(
            "channel_send",
            coroutine_id=sender_id,
            name=sender_name,
            data={"queue_size": float(len(ch.queue)), "waiting_receivers": float(len(ch.waiting_receivers))},
        )
        return None

    def _wake_one_sender(ch):
        """A recv freed a slot: move one parked sender's value in, wake it (#402)."""
        while ch.waiting_senders:
            sender, pending = ch.waiting_senders.popleft()
            if getattr(sender, "state", None) != "suspended":
                continue
            ch.queue.append(pending)
            sender.blocked_on = None
            sender.blocked_reason = None
            vm.scheduler.schedule(sender)
            vm.event_bus.emit_event("channel_wake", coroutine_id=sender.id, name=sender.name)
            vm.event_bus.emit_event(
                "channel_send",
                coroutine_id=sender.id,
                name=sender.name,
                data={"queue_size": float(len(ch.queue)), "from_wait": True},
            )
            break
        if not ch.waiting_senders:
            sched = getattr(vm, "scheduler", None)
            if sched is not None and hasattr(sched, "_send_channels"):
                sched._send_channels.discard(ch)

    def builtin_recv(channel):
        ch = vm.ensure_channel(channel, "recv(channel)")
        if ch.queue:
            value = ch.queue.popleft()
            _wake_one_sender(ch)
            vm.event_bus.emit_event(
                "channel_recv",
                coroutine_id=vm.current_coroutine.id if vm.current_coroutine is not None else None,
                name=vm.current_coroutine.name if vm.current_coroutine is not None else None,
                data={"from_queue": True, "queue_size": float(len(ch.queue))},
            )
            return value
        if ch.closed:
            vm.event_bus.emit_event(
                "channel_recv",
                coroutine_id=vm.current_coroutine.id if vm.current_coroutine is not None else None,
                name=vm.current_coroutine.name if vm.current_coroutine is not None else None,
                data={"closed": True},
            )
            return None
        if vm.current_coroutine is None:
            vm.runtime_error(
                "runtime",
                "recv(channel) outside coroutine — "
                "wrap your code in spawn(coroutine(fn() { ... })) and call run_loop()",
            )
        coroutine = vm.current_coroutine
        coroutine.state = "suspended"
        coroutine.blocked_on = ch
        coroutine.blocked_reason = "channel_recv"
        vm.stack.append(None)
        vm.save_current_coroutine_state(vm.ip + 1)
        ch.waiting_receivers.append(coroutine)
        sched = getattr(vm, "scheduler", None)
        if sched is not None:
            sched._recv_channels.add(ch)
        vm.event_bus.emit_event(
            "channel_block",
            coroutine_id=coroutine.id,
            name=coroutine.name,
            data={"operation": "recv"},
        )
        return ChannelRecvRequest(ch)

    def builtin_close(channel):
        ch = vm.ensure_channel(channel, "close(channel)")
        if ch.closed:
            return None
        ch.closed = True
        # #402: senders parked on a full channel sent *before* the close, so
        # their values are flushed into the queue (a closed channel's queue is
        # still drainable by recv) and the senders wake normally. Note the
        # invariant: senders wait only when the queue is full, so waiting
        # receivers (queue empty) and waiting senders cannot coexist.
        while ch.waiting_senders:
            sender, pending = ch.waiting_senders.popleft()
            ch.queue.append(pending)
            if getattr(sender, "state", None) != "suspended":
                continue
            sender.blocked_on = None
            sender.blocked_reason = None
            vm.scheduler.schedule(sender)
            vm.event_bus.emit_event("channel_wake", coroutine_id=sender.id, name=sender.name)
        sched = getattr(vm, "scheduler", None)
        if sched is not None and hasattr(sched, "_send_channels"):
            sched._send_channels.discard(ch)
        vm.event_bus.emit_event(
            "channel_close",
            coroutine_id=vm.current_coroutine.id if vm.current_coroutine is not None else None,
            name=vm.current_coroutine.name if vm.current_coroutine is not None else None,
            data={"waiting_receivers": float(len(ch.waiting_receivers))},
        )
        while ch.waiting_receivers:
            receiver = ch.waiting_receivers.popleft()
            if getattr(receiver, "state", None) != "suspended":
                continue
            if receiver.stack:
                receiver.stack[-1] = None
            receiver.blocked_on = None
            receiver.blocked_reason = None
            vm.scheduler.schedule(receiver)
            vm.event_bus.emit_event("channel_wake", coroutine_id=receiver.id, name=receiver.name)
            vm.event_bus.emit_event(
                "channel_recv",
                coroutine_id=receiver.id,
                name=receiver.name,
                data={"closed": True},
            )
        getattr(vm.scheduler, "_recv_channels", set()).discard(ch)
        return None

    registry.add("coroutine", 1, builtin_coroutine_create)
    registry.add("resume", 1, builtin_coroutine_resume)
    registry.add("coroutine_status", 1, builtin_coroutine_status)
    registry.add("spawn", 1, builtin_spawn)
    # #395/#157 (D3): two verbs on the coroutine, and no third. `last_result`
    # gets no separate accessor -- a `task_result(c)` beside `wait(c)` would be
    # two answers to one question.
    registry.add("cancel", 1, builtin_cancel)
    registry.add("wait", 1, builtin_wait)
    registry.add("run_loop", 0, builtin_run_loop)
    registry.add("sleep", 1, builtin_sleep)
    registry.add("__sleep", 1, builtin_sleep)
    registry.add("channel", (0, 1), builtin_channel)
    registry.add("send", 2, builtin_send)
    registry.add("recv", 1, builtin_recv)
    registry.add("close", 1, builtin_close)
