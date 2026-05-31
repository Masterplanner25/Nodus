"""Execution identity builtins — trace_id, session_id, execution_unit_id."""

from __future__ import annotations


def register(vm, registry) -> None:
    def runtime_trace_id():
        return vm.trace_id

    def runtime_session_id():
        return vm.session_id

    def runtime_execution_unit_id():
        return vm.execution_unit_id

    registry.add("runtime_trace_id", 0, runtime_trace_id)
    registry.add("runtime_session_id", 0, runtime_session_id)
    registry.add("runtime_execution_unit_id", 0, runtime_execution_unit_id)
