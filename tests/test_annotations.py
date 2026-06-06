"""Tests for @annotation syntax — @exactly_once and @retry(...)."""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.frontend.ast.ast_nodes import Annotation, FnDef  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

def _parse(src: str) -> list:
    return Parser(tokenize(src)).parse()


def test_parse_bare_annotation():
    stmts = _parse("@exactly_once\nfn f() {}")
    assert len(stmts) == 1
    fn = stmts[0]
    assert isinstance(fn, FnDef)
    assert fn.name == "f"
    assert len(fn.annotations) == 1
    ann = fn.annotations[0]
    assert isinstance(ann, Annotation)
    assert ann.name == "exactly_once"
    assert ann.args is None


def test_parse_parameterised_annotation():
    stmts = _parse("@retry(max_attempts: 3i, backoff_ms: 500i)\nfn f() {}")
    fn = stmts[0]
    assert isinstance(fn, FnDef)
    assert len(fn.annotations) == 1
    ann = fn.annotations[0]
    assert ann.name == "retry"
    assert ann.args is not None
    keys = [k for k, _ in ann.args]
    assert keys == ["max_attempts", "backoff_ms"]


def test_parse_multiple_annotations():
    stmts = _parse("@exactly_once\n@retry(max_attempts: 2i)\nfn f() {}")
    fn = stmts[0]
    assert len(fn.annotations) == 2
    assert fn.annotations[0].name == "exactly_once"
    assert fn.annotations[1].name == "retry"


def test_unannotated_fn_has_empty_annotations():
    stmts = _parse("fn f() {}")
    fn = stmts[0]
    assert isinstance(fn, FnDef)
    assert fn.annotations == []


# ---------------------------------------------------------------------------
# Compiler / runtime tests
# ---------------------------------------------------------------------------

def _rt():
    return NodusRuntime(timeout_ms=None)


def _run(src: str) -> str:
    rt = _rt()
    result = rt.run_source(src)
    return result.get("stdout", "").strip()


def test_unknown_annotation_raises():
    rt = _rt()
    result = rt.run_source("@unknown_thing\nfn f() {}\nf()")
    assert not result["ok"]
    error_msg = result.get("error", {}).get("message", "")
    assert "Unknown annotation" in error_msg


def test_retry_annotation_succeeds_on_trivial_fn():
    pytest.importorskip("nodus_retry")
    out = _run("""
import "std:retry"

@retry(max_attempts: 3i, backoff_ms: 0i)
fn greet(name) {
    return name
}

print(greet("hello"))
""")
    assert out == "hello"


def test_retry_annotation_returns_correct_value():
    pytest.importorskip("nodus_retry")
    out = _run("""
import "std:retry"

@retry(max_attempts: 2i, backoff_ms: 0i)
fn double(x) {
    return x + x
}

print(double(21))
""")
    assert out == "42.0"


def test_exactly_once_annotation_returns_value():
    pytest.importorskip("nodus_retry")
    out = _run("""
import "std:effects"

@exactly_once
fn add_one(x) {
    return x + 1
}

print(add_one(5))
""")
    assert out == "6.0"


def test_exactly_once_is_idempotent():
    pytest.importorskip("nodus_retry")
    out = _run("""
import "std:effects"

@exactly_once
fn compute(x) {
    return x + 10
}

print(compute(5))
print(compute(5))
""")
    lines = out.splitlines()
    assert len(lines) == 2
    assert lines[0] == lines[1] == "15.0"
