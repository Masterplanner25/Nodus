"""Tests for the match expression (#308).

Value-matching dispatch with a wildcard catch-all. Covers parsing, all body
forms (expression, block, bare throw/return), statement and expression
positions, integer/string scrutinees, nesting, the no-match runtime error, and
formatter round-trip + idempotency.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.frontend.ast.ast_nodes import Match, MatchArm, Block, Throw  # noqa: E402
from nodus.tooling.formatter import format_source  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _parse(src: str) -> list:
    return Parser(tokenize(src)).parse()


def _run(src: str) -> str:
    result = NodusRuntime(timeout_ms=None).run_source(src)
    assert result["ok"], result.get("error")
    return result.get("stdout", "").strip()


def _run_raw(src: str):
    return NodusRuntime(timeout_ms=None).run_source(src)


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def test_parse_match_node_shape():
    stmts = _parse('let r = match k {\n  "a" => 1i,\n  _ => 0i,\n}\n')
    match = stmts[0].expr
    assert isinstance(match, Match)
    assert len(match.arms) == 2
    assert isinstance(match.arms[0], MatchArm)
    assert match.arms[0].pattern is not None
    assert match.arms[1].pattern is None  # wildcard


def test_parse_block_and_throw_bodies():
    stmts = _parse('let r = match k {\n  "a" => { 1i },\n  _ => throw "no",\n}\n')
    arms = stmts[0].expr.arms
    assert isinstance(arms[0].body, Block)
    assert isinstance(arms[1].body, Throw)


# --------------------------------------------------------------------------
# Behavior
# --------------------------------------------------------------------------

# closes: #308
def test_string_match_expression_arms():
    src = (
        'fn classify(k) {\n'
        '    return match k {\n        "num" => "N",\n        "bin" => "B",\n        _ => "?",\n    }\n}\n'
        'print(classify("num"))\nprint(classify("bin"))\nprint(classify("zzz"))\n'
    )
    assert _run(src).splitlines() == ["N", "B", "?"]


def test_integer_match():
    src = (
        'fn f(n) {\n    return match n {\n        1i => "one",\n        2i => "two",\n        _ => "many",\n    }\n}\n'
        'print(f(1i))\nprint(f(2i))\nprint(f(9i))\n'
    )
    assert _run(src).splitlines() == ["one", "two", "many"]


def test_block_body_yields_final_expression():
    src = (
        'fn f(a, b) {\n    return match "go" {\n        "go" => {\n            let s = a + b\n            s * 2i\n        },\n        _ => 0i,\n    }\n}\n'
        'print(f(3i, 4i))\n'
    )
    assert _run(src) == "14"


def test_throw_arm():
    src = (
        'fn f(op) {\n    return match op {\n        "ok" => 1i,\n        _ => throw "bad op",\n    }\n}\n'
        'try {\n    f("nope")\n} catch e {\n    print(e)\n}\n'
    )
    assert _run(src) == "bad op"


def test_no_match_without_wildcard_is_runtime_error():
    src = 'fn f(n) {\n    return match n {\n        1i => "a",\n        2i => "b",\n    }\n}\ntry {\n    f(3i)\n} catch e {\n    print("caught")\n}\n'
    assert _run(src) == "caught"


def test_match_as_statement_discards_value():
    src = 'fn f(x) {\n    match x {\n        0i => print("zero"),\n        _ => print("nonzero"),\n    }\n}\nf(0i)\nf(7i)\n'
    assert _run(src).splitlines() == ["zero", "nonzero"]


def test_match_as_let_rhs():
    src = 'let r = match 2i {\n    1i => "x",\n    2i => "y",\n    _ => "z",\n}\nprint(r)\n'
    assert _run(src) == "y"


def test_match_inline_as_call_argument():
    # Exercises match in a nested expression position (not a whole statement).
    src = 'fn label(n) { return "v" }\nprint(label(match 1i { 1i => 10i, _ => 0i }))\n'
    assert _run(src) == "v"


def test_nested_match():
    src = (
        'fn f(kind, op) {\n'
        '    return match kind {\n'
        '        "bin" => match op {\n            "plus" => 1i,\n            _ => 0i,\n        },\n'
        '        _ => -1i,\n    }\n}\n'
        'print(f("bin", "plus"))\nprint(f("bin", "x"))\nprint(f("lit", "plus"))\n'
    )
    assert _run(src).splitlines() == ["1", "0", "-1"]


def test_first_match_wins():
    src = 'let r = match 1i {\n    1i => "first",\n    1i => "second",\n    _ => "none",\n}\nprint(r)\n'
    assert _run(src) == "first"


def test_newline_separated_arms_without_commas():
    src = 'let r = match 2i {\n    1i => "a"\n    2i => "b"\n    _ => "c"\n}\nprint(r)\n'
    assert _run(src) == "b"


# --------------------------------------------------------------------------
# Parse-time errors
# --------------------------------------------------------------------------

def test_wildcard_must_be_last():
    result = _run_raw('let r = match 1i {\n    _ => "a",\n    1i => "b",\n}\n')
    assert not result["ok"]
    assert "must be the last arm" in result.get("error", {}).get("message", "")


def test_missing_fat_arrow_is_error():
    result = _run_raw('let r = match 1i { 1i "a" }\n')
    assert not result["ok"]
    assert "'=>'" in result.get("error", {}).get("message", "")


def test_empty_match_is_error():
    result = _run_raw("let r = match 1i {\n}\n")
    assert not result["ok"]
    assert "at least one arm" in result.get("error", {}).get("message", "")


# --------------------------------------------------------------------------
# Formatter
# --------------------------------------------------------------------------

def test_formatter_roundtrips_match():
    src = (
        "fn f(k) {\n"
        "    return match k {\n"
        '        "a" => 1i,\n'
        "        \"b\" => {\n"
        "            let x = 2i\n"
        "            x\n"
        "        },\n"
        '        _ => throw "no",\n'
        "    }\n"
        "}\n"
    )
    assert format_source(src) == src


def test_formatter_match_is_idempotent():
    src = 'let r = match n {\n    1i => "a",\n    _ => "b",\n}\n'
    once = format_source(src)
    assert format_source(once) == once
