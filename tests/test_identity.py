"""Tests for Phase 6A — execution identity (trace_id, session_id, execution_unit_id)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

import pytest  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402


# ---------------------------------------------------------------------------
# VM-level attribute tests (no compilation needed)
# ---------------------------------------------------------------------------

def _make_vm():
    return VM([], {}, code_locs=[])


def test_vm_execution_unit_id_always_set():
    vm = _make_vm()
    assert isinstance(vm.execution_unit_id, str)
    assert len(vm.execution_unit_id) == 16  # token_hex(8) → 16 hex chars


def test_vm_execution_unit_id_unique():
    vm1 = _make_vm()
    vm2 = _make_vm()
    assert vm1.execution_unit_id != vm2.execution_unit_id


def test_vm_trace_id_none_by_default():
    vm = _make_vm()
    assert vm.trace_id is None


def test_vm_trace_id_settable():
    vm = _make_vm()
    vm.trace_id = "test-trace-abc"
    assert vm.trace_id == "test-trace-abc"


# ---------------------------------------------------------------------------
# Builtin / .nd API tests — use print() + stdout because top-level return
# is not valid in Nodus; the `ok` path captures stdout.
# ---------------------------------------------------------------------------

def _run_stdout(source: str, rt: NodusRuntime | None = None) -> str:
    if rt is None:
        rt = NodusRuntime(timeout_ms=None)
    result = rt.run_source(source)
    return result.get("stdout", "")


def test_execution_unit_id_non_nil():
    out = _run_stdout('import "std:identity" as id\nprint(id.execution_unit_id())')
    assert out.strip() != ""
    assert out.strip() != "nil"
    assert len(out.strip()) == 16


def test_trace_id_nil_when_unset():
    out = _run_stdout('import "std:identity" as id\nprint(id.trace_id())')
    assert out.strip() == "nil"


def test_session_id_nil_outside_session():
    out = _run_stdout('import "std:identity" as id\nprint(id.session_id())')
    assert out.strip() == "nil"


def test_trace_id_set_via_runtime():
    rt = NodusRuntime(timeout_ms=None)
    rt.set_trace_id("trace-xyz-123")
    out = _run_stdout('import "std:identity" as id\nprint(id.trace_id())', rt)
    assert out.strip() == "trace-xyz-123"


def test_trace_id_propagates_to_events():
    rt = NodusRuntime(timeout_ms=None)
    rt.set_trace_id("trace-event-check")
    rt.run_source('emit("test.event", {})')
    vm = rt.last_vm
    events = [e for e in vm.event_bus.events() if e.type == "test.event"]
    assert events, "expected at least one test.event"
    data = events[0].data or {}
    assert data.get("trace_id") == "trace-event-check"


def test_execution_unit_id_in_event_data():
    rt = NodusRuntime(timeout_ms=None)
    rt.run_source('emit("probe.event", {})')
    vm = rt.last_vm
    events = [e for e in vm.event_bus.events() if e.type == "probe.event"]
    assert events
    data = events[0].data or {}
    assert "execution_unit_id" in data
    assert isinstance(data["execution_unit_id"], str)
    assert len(data["execution_unit_id"]) == 16


def test_set_trace_id_persists_across_calls():
    rt = NodusRuntime(timeout_ms=None)
    rt.set_trace_id("persistent-trace")
    out1 = _run_stdout('import "std:identity" as id\nprint(id.trace_id())', rt)
    out2 = _run_stdout('import "std:identity" as id\nprint(id.trace_id())', rt)
    assert out1.strip() == "persistent-trace"
    assert out2.strip() == "persistent-trace"


def test_runtime_event_to_dict_includes_identity_fields():
    from nodus.runtime.runtime_events import RuntimeEvent
    evt = RuntimeEvent("test", 1.0, trace_id="tid-abc", execution_unit_id="eid-xyz")
    d = evt.to_dict()
    assert d["trace_id"] == "tid-abc"
    assert d["execution_unit_id"] == "eid-xyz"


def test_runtime_event_defaults_none():
    from nodus.runtime.runtime_events import RuntimeEvent
    evt = RuntimeEvent("test", 1.0)
    d = evt.to_dict()
    assert d["trace_id"] is None
    assert d["execution_unit_id"] is None
