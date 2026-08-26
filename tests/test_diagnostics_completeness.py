"""Editor diagnostics are right about the whole language, not most of it (#602).

`_SemanticAnalyzer` powers the undefined/unused/unreachable warnings in
`nodus check` and `nodus lsp`. It had no case for `DestructureLet`, so

    let [alpha, beta] = [1i, 2i]
    print(alpha)

reported **`Undefined variable: alpha`** — a false error on correct code, on
every line reading a destructured name.

That is #401's own failure mode recurring for a different binding form. That
issue fixed "the diagnostics engine never bound *any* block-scoped `let`, so
every function local was a false Undefined variable". Same engine, same symptom,
a form nobody re-checked.

**A false positive is worse than a missing warning.** It teaches people to ignore
the panel, after which the true positives are worth nothing either. So the tests
below carry negative controls throughout: it is not enough that the warnings
appear, they must not appear on valid code.

Six more gaps came out of the completeness check at the bottom — `ActionStmt`,
`GoalPursuit`, `CompoundAssign`, `FieldAssign`, `InterpolatedString` and `Match`
were all unwalked, so a typo in any of them was silently accepted. `print("v=\\(typo)")`
is probably the most common place a name appears in Nodus.
"""

import dataclasses
import inspect
import os
import pathlib
import re
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import nodus.frontend.ast.ast_nodes as ast_nodes  # noqa: E402
from nodus.tooling.diagnostics import (  # noqa: E402
    WorkspaceDiagnosticEngine,
    _SemanticAnalyzer,
)


def _undefined(source: str) -> list[str]:
    """Every "Undefined variable" the engine reports for *source*."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        engine = WorkspaceDiagnosticEngine(project_root=tmp)
        result = engine.analyze(path, source=source)
        return [
            diag.message
            for diags in (result.diagnostics_by_file or {}).values()
            for diag in diags
            if diag.message.startswith("Undefined")
        ]


# closes: #602
class NoFalseUndefinedVariableTests(unittest.TestCase):
    """The headline bug: correct code reported as an error."""

    def test_the_analyzer_still_reports_a_real_undefined_name(self):
        """The positive control. Every silence asserted below is only meaningful
        if the analyzer is still capable of speaking."""
        self.assertEqual(["Undefined variable: undefined_name"],
                         _undefined("let a = undefined_name\nprint(a)\n"))

    def test_a_destructured_list_binds_its_names(self):
        self.assertEqual([], _undefined(
            "let [alpha, beta] = [1i, 2i]\nprint(alpha)\nprint(beta)\n"
        ))

    def test_a_destructured_record_binds_its_names(self):
        self.assertEqual([], _undefined(
            'let {x: taken} = record { x: 1i }\nprint(taken)\n'
        ))

    def test_a_nested_destructure_binds_every_name(self):
        self.assertEqual([], _undefined(
            "let [first, [second]] = [1i, [2i]]\nprint(first)\nprint(second)\n"
        ))

    def test_a_goal_pursuit_binds_its_name(self):
        self.assertEqual([], _undefined(
            'workflow tune { step s { checkpoint "g" return 1i } }\n'
            'goal reach over tune {\n'
            '    until reached("g")\n'
            '    budget { max_iterations: 2i, deadline_ms: 9i }\n'
            '}\n'
            "let r = run_goal(reach)\nprint(r)\n"
        ))


class MissingDiagnosticsTests(unittest.TestCase):
    """The other half: a typo the analyzer accepted in silence.

    Each pairs the error case with a valid one, because a walker that reports
    everything is as useless as one that reports nothing.
    """

    def test_a_typo_in_an_action_payload_is_reported(self):
        self.assertEqual(["Undefined variable: undefined_name"], _undefined(
            'workflow w { step s { action agent "a.b" with { to: undefined_name } } }\n'
            "let r = run_workflow(w)\nprint(r)\n"
        ))

    def test_a_valid_name_in_an_action_payload_is_not(self):
        self.assertEqual([], _undefined(
            'let target = "svc"\n'
            'workflow w { step s { action agent "a.b" with { to: target } } }\n'
            "let r = run_workflow(w)\nprint(r)\n"
        ))

    def test_a_typo_in_a_compound_assignment_is_reported(self):
        self.assertEqual(["Undefined variable: undefined_name"], _undefined(
            "let x = 1i\nx += undefined_name\nprint(x)\n"
        ))

    def test_a_valid_compound_assignment_is_not(self):
        self.assertEqual([], _undefined("let x = 1i\nx += 1i\nprint(x)\n"))

    def test_a_typo_in_a_field_assignment_is_reported(self):
        self.assertEqual(["Undefined variable: undefined_name"], _undefined(
            "let r = record { f: 1i }\nr.f = undefined_name\nprint(r)\n"
        ))

    def test_a_typo_in_a_string_interpolation_is_reported(self):
        """Probably the most common place a name appears, and it was unchecked."""
        self.assertEqual(["Undefined variable: undefined_name"],
                         _undefined('print("v=\\(undefined_name)")\n'))

    def test_a_valid_string_interpolation_is_not(self):
        self.assertEqual([], _undefined('let ok = 1i\nprint("v=\\(ok)")\n'))

    def test_a_typo_in_a_match_scrutinee_is_reported(self):
        self.assertEqual(["Undefined variable: undefined_name"], _undefined(
            'let m = match undefined_name { 1i => "a", _ => "b" }\nprint(m)\n'
        ))

    def test_a_valid_match_is_not(self):
        self.assertEqual([], _undefined(
            'let s = 1i\nlet m = match s { 1i => "a", _ => "b" }\nprint(m)\n'
        ))


class EveryNodeIsAccountedForTests(unittest.TestCase):
    """A new AST node is walked or explicitly declared irrelevant.

    The same rule `tests/test_lsp_step_bodies.py` applies to the LSP indexer and
    `tests/test_formatter_completeness.py` to the formatter. It is what turned
    #602 from three missing cases into seven: per-node example tests cannot fail
    for a node that has no example.
    """

    NOT_WALKED = {
        # --- leaf literals: nothing inside to resolve ---
        "Bool", "Int", "Num",
        # --- leaf statements ---
        # `break`/`continue` carry no children; `checkpoint "label"` holds only a
        # literal, and its label is verified at compile time by goal_validation.
        "Break", "Continue", "CheckpointStmt",
        # --- reached by the duck-typed `items` fallback at the end of _walk_expr ---
        # `ListLit` has an `items` list, so it is walked without being named.
        # Verified by test_a_typo_inside_a_list_is_reported below rather than
        # assumed from reading.
        "ListLit",
        # --- structural: carried by their parent's case ---
        "Param", "WorkflowStep", "GoalStep", "GoalBudget", "MatchArm",
        "InterpolationPart", "StringLiteralPart", "Annotation", "ModuleAlias",
        "ModuleInfo", "ExportList", "ExportFrom",
        "ListPattern", "RecordPattern", "VarPattern",
        # --- the goal predicate tree: data, not code (#409) ---
        # `until reached("good")` lowers to a nested map the runtime walks, and
        # its labels are checked by frontend/goal_validation.py.
        "Reached", "PredicateAnd", "PredicateOr", "PredicateNot",
        # --- base type ---
        "Base",
    }

    def _handled(self) -> set[str]:
        source = (inspect.getsource(_SemanticAnalyzer._walk_stmt)
                  + inspect.getsource(_SemanticAnalyzer._walk_expr))
        found = set()
        for match in re.finditer(
            r"isinstance\([^,]+,\s*\(?([A-Z][A-Za-z]*(?:\s*,\s*[A-Z][A-Za-z]*)*)\)?\)",
            source,
        ):
            found.update(part.strip() for part in match.group(1).split(","))
        return found

    def test_no_node_is_silently_unwalked(self):
        handled = self._handled()
        unaccounted = sorted(
            name for name, obj in vars(ast_nodes).items()
            if inspect.isclass(obj) and dataclasses.is_dataclass(obj)
            and not name.startswith("_")
            and name not in handled and name not in self.NOT_WALKED
        )
        self.assertEqual(
            [], unaccounted,
            "AST node(s) the analyzer neither walks nor declares irrelevant. A "
            "name used inside one is invisible to `nodus check` and to editor "
            "diagnostics — that is #602. Add a case, or add the node to "
            "NOT_WALKED with a reason.",
        )

    def test_the_exemption_list_has_no_dead_entries(self):
        existing = {
            name for name, obj in vars(ast_nodes).items()
            if inspect.isclass(obj) and dataclasses.is_dataclass(obj)
        }
        stale = sorted(self.NOT_WALKED - existing)
        self.assertEqual([], stale, f"NOT_WALKED names nodes that are gone: {stale}")

    def test_a_typo_inside_a_list_is_reported(self):
        """`ListLit` is exempted as "reached by the duck-typed fallback". That is
        a claim about behaviour, so check it rather than trusting the label."""
        self.assertEqual(["Undefined variable: undefined_name"],
                         _undefined("let a = [undefined_name]\nprint(a)\n"))

    def test_the_binding_forms_are_walked_not_exempted(self):
        """The specific regression: these must be *handled*, never listed."""
        handled = self._handled()
        for node in ("DestructureLet", "GoalPursuit", "ActionStmt"):
            self.assertIn(node, handled, f"{node} is not walked (#602)")
            self.assertNotIn(node, self.NOT_WALKED,
                             f"{node} was exempted rather than handled")


class OnePatternNameCollectorTests(unittest.TestCase):
    """There were four, and this fix would have made a fifth (#602).

    The compiler had `Compiler.collect_pattern_names`, the workflow lowering had
    `_collect_pattern_names`, `lsp/server.py` grew `_pattern_names` in #597, and
    the analyzer needed the same thing — for the very bug its missing case
    caused, which would have been the recurring shape answering itself.

    Note *why* three survived: `nodus_gate --shapes` keys species A on name and
    signature, so `collect_pattern_names` and `_collect_pattern_names` never
    collided. A renamed copy is invisible to it, which is a known limit of that
    detector rather than an oversight here.
    """

    def test_every_caller_uses_the_shared_implementation(self):
        from nodus.compiler.compiler import Compiler
        from nodus.frontend.ast.ast_nodes import pattern_names
        from nodus.lsp import server as lsp
        from nodus.orchestration import workflow_lowering
        from nodus.tooling import diagnostics

        for module in (lsp, workflow_lowering, diagnostics):
            with self.subTest(module=module.__name__):
                self.assertIs(getattr(module, "pattern_names", None), pattern_names)

        self.assertEqual(["a", "b"], Compiler.collect_pattern_names(
            None, ast_nodes.ListPattern([ast_nodes.VarPattern("a"),
                                         ast_nodes.VarPattern("b")])
        ))

    def test_no_module_defines_its_own_copy(self):
        for rel in ("src/nodus/lsp/server.py",
                    "src/nodus/orchestration/workflow_lowering.py",
                    "src/nodus/tooling/diagnostics.py"):
            source = (REPO / rel).read_text(encoding="utf-8")
            with self.subTest(module=rel):
                for name in ("_pattern_names", "_collect_pattern_names",
                             "collect_pattern_names"):
                    # Any indentation. Matching only `\ndef name(` missed a copy
                    # added as a *method* — a mutation run caught the assertion
                    # passing against a tree that had the duplication back.
                    self.assertIsNone(
                        re.search(rf"^\s*def {re.escape(name)}\(", source, re.M),
                        f"{rel} defines its own pattern collector again",
                    )


if __name__ == "__main__":
    unittest.main()
