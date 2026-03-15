"""Runtime profiler for Nodus VM."""

from __future__ import annotations

import time


class Profiler:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.opcode_counts: dict[str, int] = {}
        self.function_calls: dict[str, int] = {}
        self.function_time: dict[str, float] = {}
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self._call_stack: list[tuple[str, float]] = []

    def start(self) -> None:
        self.enabled = True
        self.opcode_counts = {}
        self.function_calls = {}
        self.function_time = {}
        self._call_stack = []
        self.start_time = time.perf_counter()
        self.end_time = 0.0

    def stop(self) -> None:
        if self.start_time:
            self.end_time = time.perf_counter()
        self.enabled = False

    def record_opcode(self, opcode: str) -> None:
        if not self.enabled:
            return
        self.opcode_counts[opcode] = self.opcode_counts.get(opcode, 0) + 1

    def record_function_call(self, name: str | None) -> None:
        if not self.enabled or not name:
            return
        self.function_calls[name] = self.function_calls.get(name, 0) + 1

    def enter_function(self, name: str | None) -> None:
        if not self.enabled or not name:
            return
        self._call_stack.append((name, time.perf_counter()))

    def exit_function(self, name: str | None) -> None:
        if not self.enabled or not self._call_stack:
            return
        active_name, start = self._call_stack.pop()
        elapsed = time.perf_counter() - start
        self.function_time[active_name] = self.function_time.get(active_name, 0.0) + elapsed

    def report(self) -> dict:
        if not self.start_time:
            total_ms = 0.0
        else:
            end = self.end_time or time.perf_counter()
            total_ms = max(0.0, (end - self.start_time) * 1000.0)

        names = set(self.function_calls) | set(self.function_time)
        functions = []
        for name in names:
            calls = self.function_calls.get(name, 0)
            time_ms = self.function_time.get(name, 0.0) * 1000.0
            functions.append({"name": name, "calls": calls, "time_ms": time_ms})
        functions.sort(key=lambda item: (-item["time_ms"], -item["calls"], item["name"]))

        return {
            "total_time_ms": total_ms,
            "opcode_counts": dict(self.opcode_counts),
            "functions": functions,
        }
