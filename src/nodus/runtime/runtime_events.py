"""Runtime event tracing for the Nodus VM.

**Retention is bounded and VM bookkeeping is opt-in (#522).** The bus used to
append every event to an unbounded list whether or not anything would ever read
it, and the VM emits one event per function call, per return, and per 100
instructions. On a compiler workload that was 206,382 retained objects for a run
that printed one line — 58% of everything the run allocated, and about a third of
its CPU — with no consumer on the default path.

Two changes, and the second is the one that matters:

* history is a bounded `deque`, so an audit log cannot grow without limit;
* the high-volume VM bookkeeping types in :data:`VM_BOOKKEEPING_EVENTS` are
  emitted only when something can observe them — a sink is attached, or a host
  asked for them explicitly.

The aggregate survives either way: `function_calls` and `returns` are counters on
the VM, maintained independently of the bus, and they are what
`get_execution_stats()` has always reported. Nothing that reads the *summary*
changes.

:meth:`RuntimeEventBus.wants` is the single place that decision lives. The VM has
three emit sites for these events and each used to decide on its own, which is
the shape `CLAUDE.md` warns about; they consult `wants()` now rather than
re-implementing it, and `tests/test_runtime_event_retention.py` asserts on the
source that they keep doing so.
"""

from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass
from typing import Any

from nodus.runtime.runtime_stats import runtime_time_ms

#: Per-instruction and per-call VM bookkeeping. High volume, no documented
#: consumer -- `RUNTIME_EVENTS.md` does not list them among the event types it
#: describes -- and fully summarised by the VM's own counters.
VM_BOOKKEEPING_EVENTS = frozenset({"vm_call", "vm_return", "vm_instruction_batch"})

#: How many events the bus keeps. Generous on purpose: the memory problem was
#: bookkeeping volume, not user events, so this bound exists to stop a
#: pathological program rather than to shape ordinary ones.
DEFAULT_HISTORY = 50_000

_ENV_HISTORY = "NODUS_EVENT_HISTORY"
_ENV_VM_EVENTS = "NODUS_TRACE_VM_EVENTS"
_TRUTHY = {"1", "true", "yes", "on"}


def _history_from_env() -> int | None:
    raw = os.environ.get(_ENV_HISTORY)
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    # 0 means "keep nothing"; negative is meaningless, so treat it as unbounded
    # rather than guessing, and let the caller see an explicit None.
    return value if value >= 0 else None


def _vm_events_from_env() -> bool:
    return str(os.environ.get(_ENV_VM_EVENTS, "")).strip().lower() in _TRUTHY


def _normalize_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_value(val) for key, val in value.items()}
    return value


@dataclass
class RuntimeEvent:
    type: str
    timestamp: float
    coroutine_id: int | None = None
    name: str | None = None
    data: dict | None = None
    trace_id: str | None = None
    execution_unit_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "timestamp": float(self.timestamp),
            "coroutine": float(self.coroutine_id) if self.coroutine_id is not None else None,
            "name": self.name,
            "data": _normalize_value(self.data) if self.data is not None else None,
            "trace_id": self.trace_id,
            "execution_unit_id": self.execution_unit_id,
        }


class RuntimeEventBus:
    """Emits runtime events, and keeps a bounded window of them.

    `history=None` restores the old unbounded behaviour for a host that wants it;
    `history=0` keeps nothing and still dispatches to sinks, which is the shape a
    streaming consumer wants.
    """

    def __init__(
        self,
        enabled: bool = True,
        *,
        history: int | None = None,
        record_vm_events: bool | None = None,
    ):
        self._enabled = enabled
        env_history = _history_from_env()
        if history is None and env_history is not None:
            history = env_history
        elif history is None:
            history = DEFAULT_HISTORY
        self._history = history
        self._events: deque[RuntimeEvent] = deque(
            maxlen=history if history and history > 0 else (0 if history == 0 else None)
        )
        self._sinks: list[Any] = []
        self._record_vm_events = (
            _vm_events_from_env() if record_vm_events is None else bool(record_vm_events)
        )

    def wants(self, event_type: str) -> bool:
        """Whether an event of this type is worth building.

        The single retention decision. Everything that emits a
        :data:`VM_BOOKKEEPING_EVENTS` type asks this instead of deciding for
        itself, so the answer cannot drift between the VM's three emit sites.

        Bookkeeping is observable when a sink is attached — which is what
        `--trace-events` and the DAP debugger do — or when a host asked for it
        via `record_vm_events` / `NODUS_TRACE_VM_EVENTS`. A sink attached
        mid-run sees events from that point on, not retroactively.
        """
        if not self._enabled:
            return False
        if event_type in VM_BOOKKEEPING_EVENTS:
            return self._record_vm_events or bool(self._sinks)
        return True

    def emit(self, event: RuntimeEvent) -> None:
        if not self.wants(event.type):
            return
        self._events.append(event)
        for sink in self._sinks:
            if hasattr(sink, "emit"):
                sink.emit(event)
            else:
                sink(event)

    def emit_event(
        self,
        event_type: str,
        *,
        coroutine_id: int | None = None,
        name: str | None = None,
        data: dict | None = None,
        trace_id: str | None = None,
        execution_unit_id: str | None = None,
    ) -> None:
        # Checked before the RuntimeEvent is built. `emit` re-checks, because it
        # is also called directly; this guard is what makes a suppressed event
        # cost nothing rather than cost an allocation that is then dropped.
        if not self.wants(event_type):
            return
        self.emit(
            RuntimeEvent(
                event_type,
                runtime_time_ms(),
                coroutine_id=coroutine_id,
                name=name,
                data=data,
                trace_id=trace_id,
                execution_unit_id=execution_unit_id,
            )
        )

    def events(self) -> list[RuntimeEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def enable_vm_events(self) -> None:
        """Start recording VM bookkeeping for a host that wants the detail."""
        self._record_vm_events = True

    @property
    def records_vm_events(self) -> bool:
        return self._record_vm_events

    @property
    def history_limit(self) -> int | None:
        return self._history

    def add_sink(self, sink) -> None:
        self._sinks.append(sink)


def format_event(event: RuntimeEvent) -> str:
    text = f"[{event.timestamp:.1f}ms] {event.type}"
    if event.coroutine_id is not None:
        text += f" #{event.coroutine_id}"
    if event.name:
        text += f" {event.name}"
    if event.data:
        for key, value in event.data.items():
            text += f" {key}={value}"
    return text


class HumanReadableEventSink:
    def __init__(self, write_line):
        self.write_line = write_line

    def emit(self, event: RuntimeEvent) -> None:
        self.write_line(format_event(event))


class JsonEventSink:
    def __init__(self, write_line):
        self.write_line = write_line

    def emit(self, event: RuntimeEvent) -> None:
        self.write_line(json.dumps(event.to_dict(), separators=(",", ":")))
