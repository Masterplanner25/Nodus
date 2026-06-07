"""Tests for compound assignment operators: +=, -=, *=, /=."""

import pytest
from nodus.runtime.embedding import NodusRuntime
from nodus.frontend.lexer import tokenize
from nodus.frontend.parser import Parser
from nodus.frontend.ast.ast_nodes import CompoundAssign, ExprStmt
from nodus.tooling.formatter import format_source
from nodus.runtime.diagnostics import LangSyntaxError


def run(src):
    rt = NodusRuntime(timeout_ms=None)
    result = rt.run_source(src)
    assert result["ok"], result.get("error") or result.get("errors")
    return result["stdout"].strip()


class TestCompoundAssignParsing:
    def test_plus_equals_parses_to_compound_assign(self):
        toks = tokenize("let x = 1i\nx += 2i")
        tree = Parser(toks).parse()
        stmt = tree[1]
        assert isinstance(stmt, ExprStmt)
        assert isinstance(stmt.expr, CompoundAssign)
        assert stmt.expr.name == "x"
        assert stmt.expr.op == "+"

    def test_minus_equals_op(self):
        toks = tokenize("let x = 5i\nx -= 3i")
        tree = Parser(toks).parse()
        assert tree[1].expr.op == "-"

    def test_star_equals_op(self):
        toks = tokenize("let x = 4i\nx *= 2i")
        tree = Parser(toks).parse()
        assert tree[1].expr.op == "*"

    def test_slash_equals_op(self):
        toks = tokenize("let x = 8i\nx /= 2i")
        tree = Parser(toks).parse()
        assert tree[1].expr.op == "/"


class TestCompoundAssignExecution:
    def test_plus_equals(self):
        assert run("let x = 10i\nx += 5i\nprint(x)") == "15"

    def test_minus_equals(self):
        assert run("let x = 10i\nx -= 3i\nprint(x)") == "7"

    def test_star_equals(self):
        assert run("let x = 4i\nx *= 3i\nprint(x)") == "12"

    def test_slash_equals(self):
        assert run("let x = 10i\nx /= 4\nprint(x)") == "2.5"

    def test_chained_compound_assignments(self):
        assert run("let x = 10i\nx += 5i\nx -= 2i\nx *= 3i\nx /= 2\nprint(x)") == "19.5"

    def test_compound_assign_with_expression_rhs(self):
        assert run("let x = 10i\nlet y = 3i\nx += y * 2i\nprint(x)") == "16"

    def test_compound_assign_preserves_type(self):
        assert run("let x = 5i\nx += 10i\nprint(x)") == "15"

    def test_compound_assign_in_loop(self):
        src = """
let total = 0i
let i = 0i
while (i < 5i) {
    total += i
    i += 1i
}
print(total)
"""
        assert run(src) == "10"

    def test_compound_assign_map_index(self):
        src = """
let m = {"val": 10i}
m["val"] += 5i
print(m["val"])
"""
        assert run(src) == "15"

    def test_compound_assign_list_index(self):
        src = """
let lst = [1i, 2i, 3i]
lst[0i] += 10i
print(lst[0i])
"""
        assert run(src) == "11"

    def test_compound_assign_record_field(self):
        src = """
let r = {count: 0i}
r.count += 7i
print(r.count)
"""
        assert run(src) == "7"


class TestCompoundAssignFormatter:
    def test_plus_equals_roundtrip(self):
        src = "let x = 1i\nx += 2i\n"
        assert format_source(src) == src

    def test_minus_equals_roundtrip(self):
        src = "let x = 5i\nx -= 3i\n"
        assert format_source(src) == src

    def test_star_equals_roundtrip(self):
        src = "let x = 4i\nx *= 2i\n"
        assert format_source(src) == src

    def test_slash_equals_roundtrip(self):
        src = "let x = 8i\nx /= 2\n"
        assert format_source(src) == src
