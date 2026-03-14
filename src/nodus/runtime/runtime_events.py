"""Runtime event tracing for the Nodus VM."""

from __future__ import annotations

import json
from dataclasses import dataclass

from nodus.runtime.runtime_stats import runtime_time_ms


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

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "timestamp": float(self.timestamp),
            "coroutine": float(self.coroutine_id) if self.coroutine_id is not None else None,
            "name": self.name,
            "data": _normalize_value(self.data) if self.data is not None else None,
        }


class RuntimeEventBus:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._events: list[RuntimeEvent] = []
        self._sinks: list[object] = []

    def emit(self, event: RuntimeEvent) -> None:
        if not self._enabled:
            return
        self._events.append(event)
        for sink in self._sinks:
            sink.emit(event)

    def emit_event(
        self,
        event_type: str,
        *,
        coroutine_id: int | None = None,
        name: str | None = None,
        data: dict | None = None,
    ) -> None:
        self.emit(
            RuntimeEvent(
                event_type,
                runtime_time_ms(),
                coroutine_id=coroutine_id,
                name=name,
                data=data,
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
