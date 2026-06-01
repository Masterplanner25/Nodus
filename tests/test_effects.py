"""Tests for Phase 6D — EffectStore as language primitive."""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402


def _rt():
    return NodusRuntime(timeout_ms=None)


def _run(rt, src):
    result = rt.run_source(src)
    return result.get("stdout", "").strip()


# ---------------------------------------------------------------------------
# Python-level effect_store tests
# ---------------------------------------------------------------------------

def test_vm_has_effect_store():
    pytest.importorskip("nodus_retry")
    vm = VM([], {}, code_locs=[])
    from nodus_retry.effect import InMemoryEffectStore
    assert isinstance(vm.effect_store, InMemoryEffectStore)


def test_effect_store_resolve_unseen_is_not_done():
    vm = VM([], {}, code_locs=[])
    done, cached = vm.effect_store.resolve("unknown-id")
    assert done is False
    assert cached is None


def test_effect_store_pending_then_complete_success():
    pytest.importorskip("nodus_retry")
    vm = VM([], {}, code_locs=[])
    from nodus_retry.effect import compute_action_id
    aid = compute_action_id("test.op", {"x": 1}, scope="run-1")
    vm.effect_store.pending(aid, "h")
    vm.effect_store.complete(aid, "success", {"result": "ok"})
    done, cached = vm.effect_store.resolve(aid)
    assert done is True
    assert cached == {"result": "ok"}


def test_effect_store_failed_not_cached():
    pytest.importorskip("nodus_retry")
    vm = VM([], {}, code_locs=[])
    from nodus_retry.effect import compute_action_id
    aid = compute_action_id("test.op", {}, scope="run-fail")
    vm.effect_store.pending(aid, "h")
    vm.effect_store.complete(aid, "failed", None)
    done, _ = vm.effect_store.resolve(aid)
    assert done is False


# ---------------------------------------------------------------------------
# .nd API tests
# ---------------------------------------------------------------------------

def test_effect_resolve_unseen_not_done():
    rt = _rt()
    out = _run(rt, '''
import "std:effects" as fx
let r = fx.resolve("unseen-id")
print(r.done)
''')
    assert out == "false"


def test_effect_resolve_after_complete():
    rt = _rt()
    out = _run(rt, '''
import "std:effects" as fx
let id = fx.action_id("op", {}, "scope-abc")
fx.pending(id, "h")
fx.complete(id, "success", {"val": "v"})
let r = fx.resolve(id)
print(r.done)
''')
    assert out == "true"


def test_effect_cached_result_accessible():
    rt = _rt()
    out = _run(rt, '''
import "std:effects" as fx
let id = fx.action_id("op", {}, "scope-xyz")
fx.pending(id, "h")
fx.complete(id, "success", {"val": "hello"})
let r = fx.resolve(id)
print(r.cached.val)
''')
    assert out == "hello"


def test_effect_failed_not_done():
    rt = _rt()
    out = _run(rt, '''
import "std:effects" as fx
let id = fx.action_id("op", {}, "scope-fail")
fx.pending(id, "h")
fx.complete(id, "failed", {})
let r = fx.resolve(id)
print(r.done)
''')
    assert out == "false"


def test_effect_action_id_deterministic():
    rt = _rt()
    out = _run(rt, '''
import "std:effects" as fx
let id1 = fx.action_id("op", {}, "scope")
let id2 = fx.action_id("op", {}, "scope")
print(id1 == id2)
''')
    assert out == "true"


def test_effect_action_id_differs_by_scope():
    rt = _rt()
    out = _run(rt, '''
import "std:effects" as fx
let id1 = fx.action_id("op", {}, "scope-a")
let id2 = fx.action_id("op", {}, "scope-b")
print(id1 == id2)
''')
    assert out == "false"


def test_effect_store_size_increments():
    rt = _rt()
    out = _run(rt, '''
import "std:effects" as fx
print(fx.store_size())
let id = fx.action_id("op", {}, "s1")
fx.pending(id, "h")
print(fx.store_size())
''')
    lines = out.splitlines()
    assert lines[0] == "0"
    assert lines[1] == "1"


def test_idempotent_write_pattern():
    rt = _rt()
    out = _run(rt, '''
import "std:effects" as fx
import "std:memory" as mem

fn safe_write(key, val, run_id) {
    let id = fx.action_id("mem.write", {}, run_id)
    let r = fx.resolve(id)
    if (r.done) {
        print("cached")
        return nil
    }
    fx.pending(id, key)
    mem.put(key, val)
    fx.complete(id, "success", {"saved": val})
    print("stored")
    return nil
}

safe_write("idem_key", "first", "run-001")
safe_write("idem_key", "second", "run-001")
''')
    lines = out.splitlines()
    assert lines[0] == "stored"
    assert lines[1] == "cached"


def test_set_effect_store_python_host():
    pytest.importorskip("nodus_retry")
    from nodus_retry.effect import InMemoryEffectStore
    custom_store = InMemoryEffectStore()
    rt = _rt()
    rt.set_effect_store(custom_store)
    rt.run_source('''
import "std:effects" as fx
let id = fx.action_id("op", {}, "hs-scope")
fx.pending(id, "h")
fx.complete(id, "success", {"result": "done"})
''')
    assert len(custom_store) == 1


def test_std_effects_module_all_functions():
    rt = _rt()
    result = rt.run_source('''
import "std:effects" as fx
let _ = fx.action_id("a", {}, "s")
let _ = fx.store_size()
''')
    assert result.get("ok") is True
