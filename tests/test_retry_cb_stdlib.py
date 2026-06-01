"""Tests for Phase 6E — retry and circuit-breaker stdlib bindings."""

import sys
import os
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _rt():
    return NodusRuntime(timeout_ms=None)


def _run(src):
    rt = _rt()
    result = rt.run_source(src)
    return result.get("stdout", "").strip(), rt


# ---------------------------------------------------------------------------
# availability checks
# ---------------------------------------------------------------------------

def test_cb_available_false_when_not_installed():
    import nodus.builtins.circuit_breaker_module as cb_mod
    with patch.object(cb_mod, "_CB_AVAILABLE", False):
        out, _ = _run('import "std:circuit_breaker" as cb\nprint(cb.available())')
    assert out == "false"


def test_retry_available_returns_true():
    pytest.importorskip("nodus_retry")
    out, _ = _run('import "std:retry" as retry\nprint(retry.available())')
    assert out == "true"


def test_cb_available_returns_true():
    pytest.importorskip("nodus_circuit_breaker")
    out, _ = _run('import "std:circuit_breaker" as cb\nprint(cb.available())')
    assert out == "true"


# ---------------------------------------------------------------------------
# Circuit breaker state transitions
# ---------------------------------------------------------------------------

def test_cb_create_and_state():
    pytest.importorskip("nodus_circuit_breaker")
    out, _ = _run('''
import "std:circuit_breaker" as cb
cb.create("test_cb1", 3i, 60i)
print(cb.state("test_cb1"))
''')
    assert out == "closed"


def test_cb_opens_after_threshold():
    pytest.importorskip("nodus_circuit_breaker")
    out, _ = _run('''
import "std:circuit_breaker" as cb
cb.create("fail_cb1", 2i, 60i)
let fail_fn = fn() { throw("fail") }
let _ = cb.call("fail_cb1", fail_fn)
let fail_fn2 = fn() { throw("fail") }
let _ = cb.call("fail_cb1", fail_fn2)
print(cb.state("fail_cb1"))
''')
    assert out == "open"


def test_cb_reset_closes_open_cb():
    pytest.importorskip("nodus_circuit_breaker")
    out, _ = _run('''
import "std:circuit_breaker" as cb
cb.create("reset_cb1", 1i, 60i)
let fail_fn = fn() { throw("fail") }
let _ = cb.call("reset_cb1", fail_fn)
print(cb.state("reset_cb1"))
cb.reset("reset_cb1")
print(cb.state("reset_cb1"))
''')
    lines = out.splitlines()
    assert lines[0] == "open"
    assert lines[1] == "closed"


# ---------------------------------------------------------------------------
# Retry call
# ---------------------------------------------------------------------------

def test_retry_call_success():
    pytest.importorskip("nodus_retry")
    out, _ = _run('''
import "std:retry" as retry
let f = fn() { return "done" }
let result = retry.call(f, {"max_attempts": 3i})
print(result)
''')
    assert out == "done"


def test_retry_call_retries_on_transient_failure():
    pytest.importorskip("nodus_retry")
    rt = _rt()
    result = rt.run_source('''
import "std:retry" as retry
import "std:memory" as mem
mem.put("attempts_6e", 0i)
let f = fn() {
    let n = mem.get("attempts_6e")
    let n2 = n + 1i
    mem.put("attempts_6e", n2)
    if (n2 < 3i) { throw("transient") }
    return "success"
}
let result = retry.call(f, {"max_attempts": 5i, "backoff_ms": 0i})
print(result)
print(mem.get("attempts_6e"))
''')
    out = result.get("stdout", "").strip()
    lines = out.splitlines()
    assert lines[0] == "success"
    assert lines[1] == "3"


# ---------------------------------------------------------------------------
# stdlib module API completeness
# ---------------------------------------------------------------------------

def test_std_retry_module_api():
    result = _rt().run_source('''
import "std:retry" as retry
let _ = retry.available()
''')
    assert result.get("ok") is True


def test_std_circuit_breaker_module_api():
    result = _rt().run_source('''
import "std:circuit_breaker" as cb
let _ = cb.available()
''')
    assert result.get("ok") is True
