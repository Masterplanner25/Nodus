"""Tests for formatter coverage of previously-missing AST node handlers."""
import pytest
from nodus.tooling.formatter import format_source


def test_yield_no_expr():
    src = "fn f() {\n    yield\n}\n"
    assert format_source(src) == src


def test_yield_with_expr():
    src = "fn f() {\n    yield 42\n}\n"
    assert format_source(src) == src


def test_throw():
    src = 'fn f() {\n    throw "error"\n}\n'
    assert format_source(src) == src


def test_try_catch():
    src = 'fn f() {\n    try {\n        throw "oops"\n    } catch err {\n        print(err)\n    }\n}\n'
    assert format_source(src) == src


def test_destructure_list():
    src = "let [a, b] = xs\n"
    assert format_source(src) == src


def test_destructure_record():
    src = "let {x: a, y: b} = pt\n"
    assert format_source(src) == src


def test_destructure_nested():
    src = "let [a, [b, c]] = xs\n"
    assert format_source(src) == src
