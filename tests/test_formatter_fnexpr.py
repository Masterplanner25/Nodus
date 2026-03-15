"""Formatter tests for anonymous function expressions (FnExpr)."""

import pytest
from nodus.tooling.formatter import format_source


def test_fn_expr_no_params_empty_body():
    # FnExpr must appear in expression context; use let binding
    src = "let f = fn() {}"
    out = format_source(src)
    assert "fn() {}" in out
    # idempotent
    assert format_source(out) == out


def test_fn_expr_no_params_single_stmt():
    # FnExpr must appear in expression context; use let binding
    src = "let f = fn() { work() }"
    out = format_source(src)
    assert "fn() { work() }" in out
    assert format_source(out) == out


def test_fn_expr_as_call_argument():
    src = "spawn(fn() { work() })"
    out = format_source(src)
    assert "spawn(fn() { work() })" in out
    assert format_source(out) == out


def test_fn_expr_with_params():
    src = "let add = fn(a, b) { a + b }"
    out = format_source(src)
    assert "fn(a, b) { a + b }" in out
    assert format_source(out) == out


def test_fn_expr_with_return_type():
    src = "let inc = fn(a) -> Int { return a + 1 }"
    out = format_source(src)
    assert "fn(a) -> Int { return a + 1 }" in out
    assert format_source(out) == out


def test_fn_expr_multi_stmt_body():
    src = "let f = fn() {\nlet x = 1\nlet y = 2\nreturn x + y\n}"
    out = format_source(src)
    assert "fn() {" in out
    assert "let x = 1" in out
    assert "let y = 2" in out
    assert "return x + y" in out
    assert format_source(out) == out


def test_fn_expr_nested_in_coroutine_spawn():
    src = "spawn(coroutine(fn() { sender(ch) }))"
    out = format_source(src)
    assert "spawn(coroutine(fn() { sender(ch) }))" in out
    assert format_source(out) == out
