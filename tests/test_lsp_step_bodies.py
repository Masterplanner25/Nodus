"""The editor sees inside a step body (#597).

`_DocumentIndexer` builds the definitions, references and scopes that power
hover, go-to-definition and completions. It had no case for `WorkflowDef` or
`GoalDef`, so everything inside a step was invisible to it — in exactly the place
orchestration logic and generated code live. The workflow's *name* was indexed by
`_predeclare`, which is why the gap read as "the editor half-works" rather than as
an outage.

#401 found two walkers skipping step bodies — the type analyzer and the
diagnostics engine — and fixed both. This was the third, in the same file as one
of them, and it stayed broken for another four releases.

So the behaviour tests below are the smaller half. The durable half is
`EveryStatementNodeIsAccountedForTests`, which drives off the AST node list the
way `tests/test_formatter_completeness.py` does for the formatter: a new
statement node the indexer does not handle fails a test that names it, instead of
being discovered by a user whose editor goes quiet.
"""

import dataclasses
import inspect
import pathlib
import re
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import nodus.frontend.ast.ast_nodes as ast_nodes  # noqa: E402
from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.lsp import server as lsp  # noqa: E402


def _index(source: str):
    tokens = tokenize(source)
    parsed = Parser(tokens).parse()
    stmts = parsed if isinstance(parsed, list) else getattr(parsed, "stmts", parsed)
    indexer = lsp._DocumentIndexer(
        server=None, path="doc.nd", uri="file:///doc.nd",
        text=source, tokens=tokens, ast=stmts,
    )
    indexer.build()
    return indexer


def _names(indexer) -> set[str]:
    return {d.name for d in indexer.definitions}


# closes: #597
class TheIndexerEntersStepBodiesTests(unittest.TestCase):

    def test_an_ordinary_function_local_is_indexed(self):
        """The positive control. Before the fix this passed while every
        assertion below failed, which is what made the gap look like nothing."""
        names = _names(_index("fn helper(x) { let plain = x return plain }\n"))
        self.assertIn("helper", names)
        self.assertIn("plain", names)

    def test_a_workflow_step_local_is_indexed(self):
        names = _names(_index(
            "workflow build {\n"
            "    step lint { let inside_step = 42i return inside_step }\n"
            "}\n"
        ))
        self.assertIn("build", names, "the flow name was already indexed")
        self.assertIn("inside_step", names,
                      "hover and go-to-definition are blind inside step bodies")

    def test_a_goal_step_local_is_indexed(self):
        names = _names(_index(
            "goal ship {\n"
            "    step deploy { let artifact = \"x\" return artifact }\n"
            "}\n"
        ))
        self.assertIn("artifact", names)

    def test_a_state_cell_is_indexed(self):
        """Steps read cells bare, so they bind in a scope wrapping every step."""
        names = _names(_index(
            "workflow build {\n"
            "    state total = 0i\n"
            "    step a { total = total + 1i return total }\n"
            "}\n"
        ))
        self.assertIn("total", names)

    def test_every_step_is_walked_not_only_the_first(self):
        names = _names(_index(
            "workflow build {\n"
            "    step a { let first = 1i return first }\n"
            "    step b after a { let second = 2i return second }\n"
            "    step c after b { let third = 3i return third }\n"
            "}\n"
        ))
        for want in ("first", "second", "third"):
            self.assertIn(want, names)

    def test_a_step_option_expression_is_walked(self):
        """`with { timeout_ms: n }` is code too — a name used there is a reference."""
        indexer = _index(
            "let budget = 100i\n"
            "workflow build {\n"
            "    step a with { timeout_ms: budget } { return 1i }\n"
            "}\n"
        )
        referenced = {r.name for r in indexer.references}
        self.assertIn("budget", referenced,
                      "a name used in a step's options was never resolved")

    def test_a_name_used_in_an_action_payload_is_resolved(self):
        """`action agent … with { … }` is the commonest thing in a step body.

        Walking step bodies without this would have indexed the `let`s and
        skipped the actions — half a fix that every behaviour test above would
        still have passed. It is handled in `_walk_expr`, not `_walk_stmt`:
        `action …` parses as an expression wrapped in `ExprStmt`, so a statement
        case for it is dead code, which the first version of this fix was.
        """
        indexer = _index(
            'let target = "svc"\n'
            "workflow w {\n"
            '    step s { action agent "a.b" with { to: target } }\n'
            "}\n"
        )
        self.assertIn("target", {r.name for r in indexer.references})

    def test_a_destructuring_let_binds_every_name(self):
        """Not step-body-specific, but the same walker and the same kind of gap:
        found by the completeness test below, not by anyone reading the code."""
        names = _names(_index("let [alpha, beta] = [1i, 2i]\nprint(alpha)\n"))
        self.assertIn("alpha", names)
        self.assertIn("beta", names)

    def test_a_goal_pursuit_declares_its_name(self):
        names = _names(_index(
            'workflow tune { step s { checkpoint "good" return 1i } }\n'
            "goal reach over tune {\n"
            '    until reached("good")\n'
            "    budget { max_iterations: 3i, deadline_ms: 1000i }\n"
            "}\n"
        ))
        self.assertIn("reach", names, "go-to-definition on a goal pursuit went nowhere")

    def test_a_step_body_does_not_leak_its_locals_outward(self):
        """Scoping, not just visibility: a step local must not resolve after the
        flow, or completions would offer names that do not exist there."""
        indexer = _index(
            "workflow build {\n"
            "    step a { let scoped = 1i return scoped }\n"
            "}\n"
        )
        self.assertIsNone(indexer._lookup("scoped"),
                          "a step body's local escaped into the outer scope")


class EveryStatementNodeIsAccountedForTests(unittest.TestCase):
    """A new statement node is handled or explicitly declared not-a-statement.

    The same rule `tests/test_formatter_completeness.py` applies to the
    formatter, for the same reason: per-node example tests cannot fail for a node
    that has no example. #597 is precisely that failure — `WorkflowDef` had no
    case and no test, so nothing was red for four releases.
    """

    # Not statements, so `_walk_stmt` is not expected to name them. Grouped by
    # why, because "it is on the list" is not a reason.
    NOT_STATEMENTS = {
        # --- expressions: reached through _walk_expr ---
        "Assign", "Attr", "Bin", "Bool", "Call", "CompoundAssign", "FieldAssign",
        "FnExpr", "Index", "IndexAssign", "InterpolatedString", "Int", "ListLit",
        "MapLit", "Match", "Nil", "Num", "RecordLiteral", "Str", "Unary", "Var",
        "InterpolationPart", "StringLiteralPart", "MatchArm",
        # --- structural: carried by their parent's case, never visited alone ---
        "Param", "WorkflowStep", "GoalStep", "Annotation", "ModuleAlias",
        "ModuleInfo", "ListPattern", "RecordPattern", "VarPattern",
        "ExportList", "ExportFrom",
        # --- leaf statements with nothing to resolve ---
        # Each was checked, not assumed: `break`/`continue` carry no children,
        # `checkpoint "label"` and `comment` hold only a literal.
        "Break", "Continue", "CheckpointStmt", "Comment",
        # --- the goal predicate tree: data, not code (#409) ---
        # `until reached("good")` is lowered to a nested map the runtime walks,
        # and its labels are verified at compile time by
        # `frontend/goal_validation.py`. There is no name here to resolve.
        "Reached", "PredicateAnd", "PredicateOr", "PredicateNot",
        # `GoalBudget` is reached through its GoalPursuit's case, which walks the
        # expressions it holds.
        "GoalBudget",
        # --- base/marker types ---
        "Base",
    }

    def _handled_names(self) -> set[str]:
        # BOTH walkers. The question is "does the indexer handle this node", not
        # "does `_walk_stmt`" -- `ActionStmt` parses as an expression wrapped in
        # `ExprStmt`, so a statement case for it is dead code. The first version
        # of the #597 fix added exactly that dead case and changed nothing.
        source = (inspect.getsource(lsp._DocumentIndexer._walk_stmt)
                  + inspect.getsource(lsp._DocumentIndexer._walk_expr))
        found = set()
        for match in re.finditer(
            r"isinstance\([^,]+,\s*\(?([A-Z][A-Za-z]*(?:\s*,\s*[A-Z][A-Za-z]*)*)\)?\)",
            source,
        ):
            found.update(part.strip() for part in match.group(1).split(","))
        return found

    def test_no_statement_node_is_silently_unhandled(self):
        handled = self._handled_names()
        declared = self.NOT_STATEMENTS

        unaccounted = []
        for name, obj in vars(ast_nodes).items():
            if not (inspect.isclass(obj) and dataclasses.is_dataclass(obj)):
                continue
            if name.startswith("_") or name in handled or name in declared:
                continue
            unaccounted.append(name)

        self.assertEqual(
            [], sorted(unaccounted),
            "AST node(s) the LSP indexer neither handles nor declares a "
            "non-statement. Editor features go quiet for whatever they contain — "
            "that is #597. Add a `_walk_stmt` case, or add the node to "
            "NOT_STATEMENTS with a reason.",
        )

    def test_the_exemption_list_has_no_dead_entries(self):
        """An exemption for a node that no longer exists is a lie left behind."""
        existing = {
            name for name, obj in vars(ast_nodes).items()
            if inspect.isclass(obj) and dataclasses.is_dataclass(obj)
        }
        stale = sorted(self.NOT_STATEMENTS - existing)
        self.assertEqual([], stale, f"NOT_STATEMENTS names nodes that are gone: {stale}")

    def test_flow_declarations_are_handled_not_exempted(self):
        """The specific regression: they must be *walked*, never listed above."""
        handled = self._handled_names()
        for node in ("WorkflowDef", "GoalDef"):
            self.assertIn(node, handled,
                          f"{node} is not walked by the LSP indexer (#597)")
            self.assertNotIn(node, self.NOT_STATEMENTS,
                             f"{node} was exempted rather than handled")


if __name__ == "__main__":
    unittest.main()
