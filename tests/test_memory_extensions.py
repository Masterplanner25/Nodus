"""Tests for Phase 6B — stdlib memory extensions (namespaced KV)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _rt():
    return NodusRuntime(timeout_ms=None)


def _run(rt, src):
    result = rt.run_source(src)
    return result.get("stdout", "").strip()


def _events_of_type(rt, event_type):
    return [e for e in rt._last_vm.event_bus.events() if e.type == event_type]


# ---------------------------------------------------------------------------
# Python-level unit tests (no VM needed for memory_runtime)
# ---------------------------------------------------------------------------

def test_recall_from_python():
    from nodus.services.memory_runtime import share, recall_from
    from nodus.vm.vm import VM
    vm = VM([], {}, code_locs=[])
    share("ns1", "k", "hello", vm=vm)
    assert recall_from("ns1", "k", vm=vm) == "hello"


def test_recall_from_missing_returns_none():
    from nodus.services.memory_runtime import recall_from
    from nodus.vm.vm import VM
    vm = VM([], {}, code_locs=[])
    assert recall_from("ns1", "missing", vm=vm) is None


def test_recall_all_python():
    from nodus.services.memory_runtime import share, recall_all
    from nodus.vm.vm import VM
    vm = VM([], {}, code_locs=[])
    share("grp", "a", 1, vm=vm)
    share("grp", "b", 2, vm=vm)
    result = recall_all("grp", vm=vm)
    assert sorted(result) == [1, 2]


def test_namespace_isolation_python():
    from nodus.services.memory_runtime import share, recall_all
    from nodus.vm.vm import VM
    vm = VM([], {}, code_locs=[])
    share("alpha", "x", 1, vm=vm)
    share("beta", "x", 2, vm=vm)
    assert recall_all("alpha", vm=vm) == [1]
    assert recall_all("beta", vm=vm) == [2]


def test_recall_all_empty_namespace():
    from nodus.services.memory_runtime import recall_all
    from nodus.vm.vm import VM
    vm = VM([], {}, code_locs=[])
    assert recall_all("empty_ns", vm=vm) == []


def test_invalid_namespace_raises():
    from nodus.services.memory_runtime import share
    import pytest
    with pytest.raises(ValueError, match="namespace"):
        share("", "k", 1)
    with pytest.raises(ValueError, match="namespace"):
        share("has::sep", "k", 1)


# ---------------------------------------------------------------------------
# .nd stdlib tests
# ---------------------------------------------------------------------------

def test_share_recall_from_roundtrip():
    rt = _rt()
    out = _run(rt, '''
import "std:memory" as mem
mem.share("ctx", "result", "42")
print(mem.recall_from("ctx", "result"))
''')
    assert out == "42"


def test_recall_all_returns_list():
    rt = _rt()
    out = _run(rt, '''
import "std:memory" as mem
mem.share("items", "a", 1i)
mem.share("items", "b", 2i)
let vals = mem.recall_all("items")
print(len(vals))
''')
    assert out == "2"


def test_namespace_isolation_nd():
    rt = _rt()
    out = _run(rt, '''
import "std:memory" as mem
mem.share("ns1", "k", "one")
mem.share("ns2", "k", "two")
print(mem.recall_from("ns1", "k"))
print(mem.recall_from("ns2", "k"))
''')
    lines = out.splitlines()
    assert lines[0] == "one"
    assert lines[1] == "two"


def test_recall_from_nil_on_missing():
    rt = _rt()
    out = _run(rt, '''
import "std:memory" as mem
print(mem.recall_from("ns", "nope"))
''')
    assert out == "nil"


def test_recall_all_empty():
    rt = _rt()
    out = _run(rt, '''
import "std:memory" as mem
let vals = mem.recall_all("empty")
print(len(vals))
''')
    assert out == "0"


def test_share_emits_event():
    rt = _rt()
    rt.run_source('''
import "std:memory" as mem
mem.share("evtest", "k", "v")
''')
    events = _events_of_type(rt, "memory_share")
    assert events, "expected memory_share event"


def test_recall_from_emits_event():
    rt = _rt()
    rt.run_source('''
import "std:memory" as mem
mem.share("evtest2", "k", "v")
mem.recall_from("evtest2", "k")
''')
    events = _events_of_type(rt, "memory_recall_from")
    assert events, "expected memory_recall_from event"


def test_recall_all_emits_event():
    rt = _rt()
    rt.run_source('''
import "std:memory" as mem
mem.share("evtest3", "k", "v")
mem.recall_all("evtest3")
''')
    events = _events_of_type(rt, "memory_recall_all")
    assert events, "expected memory_recall_all event"


# ---------------------------------------------------------------------------
# Regression guard: original 5 flat memory functions still work
# ---------------------------------------------------------------------------

def test_existing_get_put():
    rt = _rt()
    out = _run(rt, '''
import "std:memory" as mem
mem.put("x", "hello")
print(mem.get("x"))
''')
    assert out == "hello"


def test_existing_delete():
    rt = _rt()
    out = _run(rt, '''
import "std:memory" as mem
mem.put("y", "world")
mem.delete("y")
print(mem.has("y"))
''')
    assert out == "false"


def test_existing_keys():
    rt = _rt()
    out = _run(rt, '''
import "std:memory" as mem
mem.put("k1_test", 1i)
mem.put("k2_test", 2i)
print(mem.has("k1_test"))
print(mem.has("k2_test"))
''')
    lines = out.splitlines()
    assert lines[0] == "true"
    assert lines[1] == "true"


def test_existing_has():
    rt = _rt()
    out = _run(rt, '''
import "std:memory" as mem
mem.put("z", "here")
print(mem.has("z"))
''')
    assert out == "true"
