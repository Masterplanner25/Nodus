"""Every AST node is either formattable or explicitly declared a non-statement (#427).

`nodus fmt` raises `TypeError: Unknown stmt node: …` for a statement node it does
not handle, and CI format-checks every `.nd` file — so a node with no formatter
case is a crash for whoever writes the new syntax first.

That happened with `GoalPursuit` (#409): it parsed, compiled and ran correctly,
the full suite was green, and `nodus fmt` died with a raw traceback. Nothing
failed, because `tests/test_formatter_*.py` are per-node *examples*
(`test_yield_no_expr`, `test_throw`, …) — a node with no example simply has no
test.

This is the same gap #357 closed for keywords, one layer over: nothing held the
**AST node set** and the **formatter** together.

The rule here is not "the formatter handles everything" — most nodes are
expressions and belong to `format_expr`. It is that **every node is accounted
for**: either `format_stmt` handles it, or it is named below as something else.
Adding a node without doing one or the other fails this test and names the node.
"""

import dataclasses
import inspect
import re
import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

import nodus.frontend.ast.ast_nodes as ast_nodes  # noqa: E402
from nodus.tooling import formatter  # noqa: E402


# Nodes that are not statements, so `format_stmt` is not expected to handle them.
# Grouped by why, because "it is on the list" is not a reason.
NOT_STATEMENTS = {
    # --- expressions: printed by format_expr ---
    "Assign", "Attr", "Bin", "Bool", "Call", "CompoundAssign", "FieldAssign",
    "FnExpr", "Index", "IndexAssign", "InterpolatedString", "Int", "ListLit",
    "MapLit", "Match", "Nil", "Num", "RecordLiteral", "Str", "Unary", "Var",
    # --- fragments of a larger construct, never freestanding ---
    "Annotation",        # attaches to a FnDef
    "InterpolationPart", "StringLiteralPart",   # pieces of InterpolatedString
    "ListPattern", "RecordPattern", "VarPattern",   # destructuring patterns
    "MatchArm",          # part of Match
    "Param",             # part of FnDef/FnExpr
    # --- goal-pursuit sub-nodes (#409): printed by the GoalPursuit case and
    # format_goal_predicate, never as standalone statements ---
    "GoalBudget", "PredicateAnd", "PredicateNot", "PredicateOr", "Reached",
    # --- handled by format_expr's ActionStmt case, not format_stmt: an action
    # reaches the formatter wrapped in an ExprStmt ---
    "ActionStmt",
    # --- not AST at all: module-resolution metadata that happens to live in
    # this module ---
    "ModuleAlias", "ModuleInfo",
    # --- base class, not a node ---
    "Base",
}


def _all_ast_nodes() -> set[str]:
    return {
        name for name, obj in vars(ast_nodes).items()
        if inspect.isclass(obj)
        and dataclasses.is_dataclass(obj)
        and obj.__module__ == ast_nodes.__name__
    }


def _formatter_handles() -> set[str]:
    """Node names the formatter's statement dispatch checks for.

    Read out of the source because the dispatch is a chain of `isinstance`
    checks with no registry to consult. Uglier than a registry and far cheaper
    than constructing a valid instance of every node type.

    **Scanned across the module rather than out of one named function.** It used
    to read `inspect.getsource(formatter.format_stmt)`, on the reasoning that
    reading the dispatch itself cannot drift from the implementation. It drifted
    the first time the dispatch moved: #742 split `format_stmt` into a thin
    wrapper plus `_format_stmt`, and the reader was left looking at three lines
    that check nothing. The tests went red rather than silently passing, which is
    the good outcome — but the fix is to stop naming the function at all, since
    where the chain lives is not the thing being asserted.
    """
    source = inspect.getsource(formatter)
    return set(re.findall(r"isinstance\(stmt,\s*([A-Za-z_][A-Za-z0-9_]*)\)", source))


# closes: #427
class EveryNodeIsAccountedForTests(unittest.TestCase):
    def test_no_node_is_unclassified(self):
        unclassified = _all_ast_nodes() - _formatter_handles() - NOT_STATEMENTS
        self.assertEqual(
            unclassified, set(),
            f"AST nodes {sorted(unclassified)} are neither handled by "
            f"formatter.format_stmt nor listed in NOT_STATEMENTS. If it is a "
            f"statement, give it a formatter case — `nodus fmt` will crash on it "
            f"and CI format-checks every .nd file. If it is not, add it to "
            f"NOT_STATEMENTS with the reason.",
        )

    def test_the_exclusion_list_names_only_real_nodes(self):
        # A stale name in NOT_STATEMENTS would silently excuse a node that no
        # longer exists, and could mask a rename.
        stale = NOT_STATEMENTS - _all_ast_nodes() - {"Base"}
        self.assertEqual(
            stale, set(),
            f"NOT_STATEMENTS names {sorted(stale)}, which are not AST nodes — "
            f"probably renamed or removed",
        )

    def test_the_dispatch_reader_actually_finds_cases(self):
        # Guard the guard: if the regex stopped matching, every check above would
        # pass vacuously by classifying everything as unhandled-but-excluded.
        handled = _formatter_handles()
        self.assertGreater(len(handled), 20, "dispatch extraction found almost nothing")
        for expected in ("Let", "Return", "If", "While", "FnDef"):
            self.assertIn(expected, handled)

    def test_an_excused_node_is_excused_for_a_reason_that_holds(self):
        # `ActionStmt` is excused because `format_expr` handles it. If that ever
        # stopped being true the exclusion would be hiding a crash, so check the
        # claim rather than trusting the comment.
        source = inspect.getsource(formatter.format_expr)
        self.assertIn("ActionStmt", source)

    def test_the_node_reader_actually_finds_nodes(self):
        nodes = _all_ast_nodes()
        self.assertGreater(len(nodes), 40)
        self.assertIn("GoalPursuit", nodes)


# closes: #427
class TheGuardCatchesTheCaseThatMotivatedItTests(unittest.TestCase):
    """`GoalPursuit` is the node that slipped through with the suite green."""

    def test_goal_pursuit_is_handled_rather_than_excused(self):
        self.assertIn("GoalPursuit", _formatter_handles())
        self.assertNotIn("GoalPursuit", NOT_STATEMENTS)

    def test_removing_a_handled_node_would_be_caught(self):
        # Simulate the #409 situation: a statement node with no formatter case
        # and no exclusion. The assertion must name it.
        pretend_handled = _formatter_handles() - {"GoalPursuit"}
        unclassified = _all_ast_nodes() - pretend_handled - NOT_STATEMENTS
        self.assertIn("GoalPursuit", unclassified)


# closes: #427
class WithBlocksRoundTripTests(unittest.TestCase):
    """`nodus fmt` must not write a file that no longer parses.

    Found by this sweep, and worse than the crash it was written for.
    `with { ... }` is parsed by `parse_named_map_literal`, which requires
    **identifier** keys — but the formatter printed the resulting `MapLit`
    through `format_expr`, which quotes them:

        step a with { retries: 2 }   ->   step a with {"retries": 2}
        Syntax error: Expected identifier, got string literal ('retries')

    `nodus fmt` writes in place, so it turned a valid file into a broken one, on
    the headline workflow syntax. The format gate never caught it because no
    `.nd` file in this repo uses `with { }`.
    """

    STEP_OPTIONS = 'workflow w {\n    step a with { retries: 2, retry_delay_ms: 5 } {\n        return 1i\n    }\n}\n'
    ACTION_PAYLOAD = 'workflow w {\n    step a {\n        action agent "bot" with { n: 1i }\n        return 1i\n    }\n}\n'
    GOAL_BUDGET = 'workflow w {\n    step a {\n        checkpoint "done"\n        return 1i\n    }\n}\ngoal g over w {\n    until reached("done")\n    budget { max_iterations: 2, deadline_ms: 10 }\n}\n'

    def _cases(self):
        return {
            "step options": self.STEP_OPTIONS,
            "action payload": self.ACTION_PAYLOAD,
            "goal budget": self.GOAL_BUDGET,
        }

    def test_formatted_output_still_parses(self):
        from nodus.frontend.lexer import tokenize
        from nodus.frontend.parser import Parser
        from nodus.tooling.formatter import format_source

        for label, source in self._cases().items():
            with self.subTest(case=label):
                formatted = format_source(source)
                try:
                    Parser(tokenize(formatted)).parse()
                except Exception as exc:  # noqa: BLE001 — reported, not swallowed
                    self.fail(
                        f"nodus fmt produced unparseable output for {label}: "
                        f"{exc}\n{formatted}"
                    )

    def test_bare_keys_are_preserved(self):
        from nodus.tooling.formatter import format_source

        formatted = format_source(self.STEP_OPTIONS)
        self.assertIn("with { retries: 2, retry_delay_ms: 5 }", formatted)
        self.assertNotIn('"retries"', formatted)

    def test_formatting_is_idempotent(self):
        from nodus.tooling.formatter import format_source

        for label, source in self._cases().items():
            with self.subTest(case=label):
                once = format_source(source)
                self.assertEqual(once, format_source(once))


if __name__ == "__main__":
    unittest.main()
