"""Runtime registry and dispatch for agent calls."""

from __future__ import annotations

import threading

from nodus.result import Result, normalize_filename
from nodus.vm.runtime_values import clone_json_value, is_json_safe, payload_keys


AGENT_REGISTRY: dict[str, dict] = {}


def get_registry(vm=None) -> dict:
    """The agent registry that applies to this VM (#185).

    Mirrors `memory_runtime.get_store(vm)`: a VM may carry its own registry, and
    falls back to the process-global one when it does not. Without this, every
    `NodusRuntime` in a process shared one registry — verified before the fix, a
    second runtime could both see *and call* an agent the first had registered,
    which for a multi-tenant host is a cross-tenant capability leak rather than
    merely shared state.
    """
    registry = getattr(vm, "agent_registry", None) if vm is not None else None
    if isinstance(registry, dict):
        return registry
    return AGENT_REGISTRY


def register_agent(name: str, handler, *, description: str | None = None, payload_schema: dict | None = None, registry: dict | None = None) -> None:
    target = AGENT_REGISTRY if registry is None else registry
    target[name] = {
        "handler": handler,
        "spec": {
            "name": name,
            "description": description or f"Agent handler for {name}",
            "parameters": payload_schema or {"type": "object"},
        },
    }


def unregister_agent(name: str, *, registry: dict | None = None) -> None:
    (AGENT_REGISTRY if registry is None else registry).pop(name, None)


def available_agents(vm=None) -> list[str]:
    return sorted(get_registry(vm).keys())


def describe_agent(name: str, vm=None):
    if not isinstance(name, str):
        return None
    entry = get_registry(vm).get(name)
    if entry is None:
        return None
    return dict(entry["spec"])


# Abandoned handler threads, for the operator question "is something stuck?" (#424).
#
# Recorded when a handler outlives its deadline and is left running. Never
# "un-recorded", because there is no reliable moment to observe such a thread
# finishing — that is the whole reason it had to be abandoned.
#
# Deliberately a *bounded* ring plus a total count. An unbounded list would be the
# same defect this issue is about, one level up: a server whose provider hangs on
# every call would accumulate a record per call forever. The count is what tells an
# operator the scale; the recent entries are what tell them which agent.
_ABANDONED_MAX = 100
ABANDONED_AGENT_CALLS: list[dict] = []
_ABANDONED_TOTAL = 0
_ABANDONED_LOCK = threading.Lock()


def _record_abandoned(name: str, timeout_ms: float) -> None:
    global _ABANDONED_TOTAL
    with _ABANDONED_LOCK:
        _ABANDONED_TOTAL += 1
        ABANDONED_AGENT_CALLS.append({"agent": name, "timeout_ms": float(timeout_ms)})
        if len(ABANDONED_AGENT_CALLS) > _ABANDONED_MAX:
            del ABANDONED_AGENT_CALLS[:-_ABANDONED_MAX]


def abandoned_agent_calls() -> list[dict]:
    """The most recent abandoned handlers (at most 100)."""
    with _ABANDONED_LOCK:
        return [dict(entry) for entry in ABANDONED_AGENT_CALLS]


def abandoned_agent_call_count() -> int:
    """How many handlers have been abandoned in this process, in total.

    Not `len(abandoned_agent_calls())` — that list is capped. A host watching for
    "are we leaking threads to a hung provider?" wants this number.
    """
    with _ABANDONED_LOCK:
        return _ABANDONED_TOTAL


def reset_abandoned_agent_calls() -> None:
    """Clear the record. For tests; a host has no reason to call this."""
    global _ABANDONED_TOTAL
    with _ABANDONED_LOCK:
        ABANDONED_AGENT_CALLS.clear()
        _ABANDONED_TOTAL = 0


def _effective_timeout_ms(vm) -> float | None:
    """The deadline that applies to this agent call, in ms, or None for unbounded.

    Two sources, tightest wins (#424):

    - the **step**'s `timeout_ms`, minus what the step has already spent. This is
      the knob users already reach for, and before this it bounded only work in the
      instruction stream: a `timeout_ms: 500` step containing a handler that blocks
      for 3 s ran the full 3 s and *then* reported a timeout. Measured — the same
      option around a pure-Nodus busy loop stopped it at 0.59 s.
    - a runtime-level default (`NodusRuntime(agent_timeout_ms=...)`), for calls made
      outside any step, where no step budget exists to inherit.
    """
    candidates: list[float] = []

    scheduler = getattr(vm, "scheduler", None)
    task = getattr(scheduler, "current_task", None) if scheduler is not None else None
    task_timeout = getattr(task, "task_timeout_ms", None) if task is not None else None
    if isinstance(task_timeout, (int, float)) and task_timeout > 0:
        started = getattr(task, "task_started_at", None)
        if isinstance(started, (int, float)):
            from nodus.runtime.runtime_stats import runtime_time_ms

            remaining = float(task_timeout) - (runtime_time_ms() - float(started))
            # Clamp rather than pass a negative deadline: an already-overrun step
            # should fail fast, not be treated as unbounded.
            candidates.append(max(remaining, 1.0))
        else:
            candidates.append(float(task_timeout))

    default_ms = getattr(vm, "agent_timeout_ms", None)
    if isinstance(default_ms, (int, float)) and default_ms > 0:
        candidates.append(float(default_ms))

    return min(candidates) if candidates else None


def _invoke_handler_bounded(handler, payload, timeout_ms: float | None, *, name: str):
    """Call `handler(payload)`, giving up after `timeout_ms`.

    Returns `(ok, value_or_none, timed_out)`.

    **This stops waiting; it does not stop the handler.** Arbitrary Python cannot be
    preempted — a `time.sleep`, a blocking socket read or a `while True` in a host
    handler is not interruptible from outside. So the handler runs on a daemon
    thread and the caller abandons it at the deadline. The run becomes bounded,
    which is the property that was missing; the thread is not reclaimed, which is
    the price and is recorded in `ABANDONED_AGENT_CALLS`.

    The thread is a **daemon** deliberately: a non-daemon thread stuck in a hung
    provider call would keep the whole process alive at exit, turning a bounded
    request into an unbounded shutdown.
    """
    if timeout_ms is None:
        return True, handler(payload), False

    box: dict = {}
    done = threading.Event()

    def _run() -> None:
        try:
            box["value"] = handler(payload)
        except BaseException as err:  # re-raised on the caller's thread below
            box["error"] = err
        finally:
            done.set()

    worker = threading.Thread(
        target=_run, name=f"nodus-agent:{name}", daemon=True
    )
    worker.start()
    if not done.wait(timeout_ms / 1000.0):
        _record_abandoned(name, timeout_ms)
        return False, None, True
    if "error" in box:
        raise box["error"]
    return True, box.get("value"), False


def call_agent(name, payload, *, vm=None) -> dict:
    filename = normalize_filename(getattr(vm, "source_path", None))
    if not isinstance(name, str) or not name:
        return _agent_error("Agent name must be a non-empty string", filename, name=name)
    if not is_json_safe(payload):
        return _agent_error("Agent payload must be JSON-safe", filename, name=name)

    _emit(vm, "agent_call_start", name=name, payload=payload)
    entry = get_registry(vm).get(name)
    if entry is None:
        result = _agent_error(f"No handler registered for agent '{name}'", filename, name=name)
        _emit(vm, "agent_call_fail", name=name, payload=payload, ok=False, error=_error_message(result))
        return result

    timeout_ms = _effective_timeout_ms(vm)
    try:
        ok, handler_result, timed_out = _invoke_handler_bounded(
            entry["handler"], clone_json_value(payload), timeout_ms, name=name
        )
    except Exception as err:
        result = _agent_error(str(err), filename, name=name)
        _emit(vm, "agent_call_fail", name=name, payload=payload, ok=False, error=_error_message(result))
        return result

    if timed_out:
        # The handler is still running and cannot be stopped; we have stopped
        # waiting for it (#424). Reported as an ordinary agent failure so a step's
        # `retries` and the retry classifier act on it like any other.
        result = _agent_error(
            f"Agent '{name}' timed out after {timeout_ms:.0f}ms; "
            "the handler is still running and cannot be cancelled",
            filename, name=name,
        )
        _emit(vm, "agent_call_timeout", name=name, payload=payload, ok=False,
              error=_error_message(result))
        _emit(vm, "agent_call_fail", name=name, payload=payload, ok=False,
              error=_error_message(result))
        return result
    if not ok:  # defensive: only reachable if the contract above changes
        result = _agent_error(f"Agent '{name}' did not produce a result", filename, name=name)
        _emit(vm, "agent_call_fail", name=name, payload=payload, ok=False, error=_error_message(result))
        return result

    if not is_json_safe(handler_result):
        result = _agent_error("Agent handler returned a non-serializable value", filename, name=name)
        _emit(vm, "agent_call_fail", name=name, payload=payload, ok=False, error=_error_message(result))
        return result

    result = Result.success(
        stage="agent_call",
        filename=filename,
        stdout="",
        stderr="",
        result=clone_json_value(handler_result),
    ).to_dict()
    _emit(vm, "agent_call_complete", name=name, payload=payload, ok=True)
    return result


def _agent_error(message: str, filename: str, *, name: str | None = None) -> dict:
    legacy = {"type": "agent", "message": message, "path": filename}
    if name is not None:
        legacy["agent"] = name
    return Result.failure(
        stage="agent_call",
        filename=filename,
        stdout="",
        stderr="",
        errors=[{"type": "AgentError", "message": message, "agent": name}],
        error=legacy,
    ).to_dict()


def _error_message(result: dict | None) -> str:
    if not isinstance(result, dict):
        return "Agent call failed"
    err = result.get("error")
    if isinstance(err, dict):
        return str(err.get("message", "Agent call failed"))
    return "Agent call failed"


def _emit(vm, event_type: str, *, name: str, payload, ok: bool | None = None, error: str | None = None) -> None:
    if vm is None or getattr(vm, "event_bus", None) is None:
        return
    data = {"payload_keys": payload_keys(payload)}
    if hasattr(vm, "runtime_adapter_event_data"):
        data.update(vm.runtime_adapter_event_data(payload, ok=ok, error=error))
    vm.event_bus.emit_event(event_type, name=name, data=data)
