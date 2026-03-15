"""Coroutine, channel, and scheduler builtin functions for the Nodus VM."""

from nodus.runtime.coroutine import Coroutine
from nodus.runtime.channel import Channel, ChannelRecvRequest
from nodus.runtime.scheduler import SleepRequest


def register(vm, registry) -> None:
    """Register coroutine, channel, and sleep builtins onto the registry."""

    def builtin_coroutine_create(value):
        closure = vm.ensure_function(value, "coroutine(fn)")
        if len(closure.function.params) != 0:
            vm.runtime_error("call", "coroutine(fn) expects a zero-argument function")
        return Coroutine(closure)

    def builtin_coroutine_status(value):
        coroutine = vm.ensure_coroutine(value, "coroutine_status(coroutine)")
        return coroutine.state

    def builtin_coroutine_resume(value):
        from nodus.vm.vm import Frame
        coroutine = vm.ensure_coroutine(value, "resume(coroutine)")
        if coroutine.state == "finished":
            vm.runtime_error("runtime", "Cannot resume finished coroutine")
        if coroutine.state == "running":
            vm.runtime_error("runtime", "Cannot resume running coroutine")

        caller_context = vm.save_execution_context()
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

    def builtin_spawn(value):
        coroutine = vm.ensure_coroutine(value, "spawn(coroutine)")
        vm.scheduler.spawn(coroutine)
        return None

    def builtin_run_loop():
        vm.scheduler.run_loop()
        return None

    def builtin_sleep(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            vm.runtime_error("type", "sleep(ms) expects a number")
        ms = float(value)
        if ms < 0:
            ms = 0.0
        return SleepRequest(ms)

    def builtin_channel():
        return Channel()

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
        ch.queue.append(value)
        vm.event_bus.emit_event(
            "channel_send",
            coroutine_id=sender_id,
            name=sender_name,
            data={"queue_size": float(len(ch.queue)), "waiting_receivers": float(len(ch.waiting_receivers))},
        )
        return None

    def builtin_recv(channel):
        ch = vm.ensure_channel(channel, "recv(channel)")
        if ch.queue:
            value = ch.queue.popleft()
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
            vm.runtime_error("runtime", "recv(channel) outside coroutine")
        coroutine = vm.current_coroutine
        coroutine.state = "suspended"
        coroutine.blocked_on = ch
        coroutine.blocked_reason = "channel_recv"
        vm.stack.append(None)
        vm.save_current_coroutine_state(vm.ip + 1)
        ch.waiting_receivers.append(coroutine)
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
        return None

    registry.add("coroutine", 1, builtin_coroutine_create)
    registry.add("resume", 1, builtin_coroutine_resume)
    registry.add("coroutine_status", 1, builtin_coroutine_status)
    registry.add("spawn", 1, builtin_spawn)
    registry.add("run_loop", 0, builtin_run_loop)
    registry.add("sleep", 1, builtin_sleep)
    registry.add("__sleep", 1, builtin_sleep)
    registry.add("channel", 0, builtin_channel)
    registry.add("send", 2, builtin_send)
    registry.add("recv", 1, builtin_recv)
    registry.add("close", 1, builtin_close)
