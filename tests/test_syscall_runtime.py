"""Tests for Phase 6C — sys.v1.* syscall dispatch."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

import pytest  # noqa: E402


# ---------------------------------------------------------------------------
# Python-level unit tests (no VM needed)
# ---------------------------------------------------------------------------

def setup_function():
    from nodus.services import syscall_runtime
    syscall_runtime._registry_built = False
    syscall_runtime.SYSCALL_REGISTRY.clear()


def test_call_syscall_memory_put_ok():
    from nodus.services.syscall_runtime import call_syscall
    result = call_syscall("sys.v1.memory.put", {"key": "test_sc_put", "value": "hello"})
    assert result["status"] == "ok"
    assert result["data"]["value"] == "hello"
    assert result["error"] is None


def test_call_syscall_memory_get_ok():
    from nodus.services.syscall_runtime import call_syscall
    call_syscall("sys.v1.memory.put", {"key": "test_sc_get", "value": "world"})
    result = call_syscall("sys.v1.memory.get", {"key": "test_sc_get"})
    assert result["status"] == "ok"
    assert result["data"]["value"] == "world"


def test_call_syscall_memory_delete_ok():
    from nodus.services.syscall_runtime import call_syscall
    call_syscall("sys.v1.memory.put", {"key": "test_sc_del", "value": "x"})
    result = call_syscall("sys.v1.memory.delete", {"key": "test_sc_del"})
    assert result["status"] == "ok"
    assert result["data"]["found"] is True


def test_call_syscall_unknown_returns_error():
    from nodus.services.syscall_runtime import call_syscall
    result = call_syscall("sys.v1.unknown.op", {})
    assert result["status"] == "error"
    assert "Unknown syscall" in result["error"]


def test_call_syscall_bad_name_returns_error():
    from nodus.services.syscall_runtime import call_syscall
    result = call_syscall("not_a_syscall", {})
    assert result["status"] == "error"


def test_call_syscall_missing_required_field():
    from nodus.services.syscall_runtime import call_syscall
    result = call_syscall("sys.v1.memory.get", {})
    assert result["status"] == "error"
    assert "key" in result["error"]


def test_envelope_always_has_trace_id_field():
    from nodus.services.syscall_runtime import call_syscall
    result = call_syscall("sys.v1.memory.get", {"key": "probe"})
    assert "trace_id" in result


def test_trace_id_in_envelope_when_vm_has_it():
    from nodus.services.syscall_runtime import call_syscall
    from nodus.vm.vm import VM
    vm = VM([], {}, code_locs=[])
    vm.trace_id = "trace-sys-test"
    result = call_syscall("sys.v1.memory.get", {"key": "probe"}, vm=vm)
    assert result["trace_id"] == "trace-sys-test"


def test_list_syscalls_returns_registered():
    from nodus.services.syscall_runtime import list_syscalls
    syscalls = list_syscalls()
    names = [s["full_name"] for s in syscalls]
    assert "sys.v1.memory.get" in names
    assert "sys.v1.memory.put" in names
    assert "sys.v1.memory.delete" in names
    assert "sys.v1.memory.recall_from" in names


# ---------------------------------------------------------------------------
# .nd stdlib tests
# ---------------------------------------------------------------------------

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _rt():
    return NodusRuntime(timeout_ms=None)


def _run(src):
    rt = _rt()
    result = rt.run_source(src)
    return result.get("stdout", "").strip(), rt


def test_sys_memory_put_via_nd():
    out, _ = _run('''
import "std:sys" as sys
let r = sys.memory_put("snd_put", "value123")
print(r.status)
''')
    assert out == "ok"


def test_sys_memory_get_via_nd():
    out, _ = _run('''
import "std:sys" as sys
sys.memory_put("snd_get", "retrieved")
let g = sys.memory_get("snd_get")
print(g.status)
print(g.data.value)
''')
    lines = out.splitlines()
    assert lines[0] == "ok"
    assert lines[1] == "retrieved"


def test_sys_memory_delete_via_nd():
    out, _ = _run('''
import "std:sys" as sys
sys.memory_put("snd_del", "x")
let d = sys.memory_delete("snd_del")
print(d.status)
print(d.data.found)
''')
    lines = out.splitlines()
    assert lines[0] == "ok"
    assert lines[1] == "true"


def test_sys_call_unknown_returns_error_envelope():
    out, _ = _run('''
import "std:sys" as sys
let r = sys.call("sys.v1.nothing", {})
print(r.status)
''')
    assert out == "error"


def test_sys_call_carries_trace_id():
    rt = _rt()
    rt.set_trace_id("trace-syscall-nd")
    result = rt.run_source('''
import "std:sys" as sys
let r = sys.memory_put("tracekey", "v")
print(r.trace_id)
''')
    out = result.get("stdout", "").strip()
    assert out == "trace-syscall-nd"


def test_syscall_complete_event_emitted():
    rt = _rt()
    rt.run_source('''
import "std:sys" as sys
sys.memory_put("evkey", "ev")
''')
    events = [e for e in rt.last_vm.event_bus.events() if e.type == "syscall_complete"]
    assert events, "expected syscall_complete event"


def test_syscall_error_event_emitted():
    rt = _rt()
    rt.run_source('syscall("sys.v1.bad.op", {})')
    events = [e for e in rt.last_vm.event_bus.events() if e.type == "syscall_error"]
    assert events, "expected syscall_error event for unknown syscall"
