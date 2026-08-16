"""`goal NAME over WORKFLOW { until ... budget ... }` — #409 Part A.

A goal declares the *criteria*; the workflow it names does the work. That gives
`goal` a job `workflow` structurally cannot have — since #393 unified retries,
the original `goal g { step ... }` form is a workflow with a different event
prefix.

Two properties are load-bearing and are tested as such:

1. **The static check is total.** `checkpoint "L"` and `reached("L")` both take
   string literals only, so a goal naming a checkpoint its workflow never records
   is rejected at compile time — always, not usually. This is the concrete answer
   to "what does `goal` gain that a library cannot have": a Python planner can
   observe checkpoints at run time but cannot reject the program.
2. **Budget exhaustion is a failure.** A goal that runs out of iterations has not
   met its objective and must never return a success-shaped result.
"""

import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.cli import cli as nodus_cli  # noqa: E402
from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.runtime.diagnostics import LangSyntaxError  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


class _TempProject:
    """Scratch project root, so runs land in its store and not the repo's (#380)."""

    def __enter__(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = self._td.__enter__()
        self._ctx = nodus_cli._project_root_context(self.root)
        self._ctx.__enter__()
        return self

    def __exit__(self, *exc):
        self._ctx.__exit__(*exc)
        return self._td.__exit__(*exc)


def _parse(source: str):
    return Parser(tokenize(source)).parse()


def _run(source: str):
    with _TempProject():
        return NodusRuntime(timeout_ms=None).run_source(source, filename="g.nd")


# A workflow that advances one step per pass and records "verified" once its
# carried state passes a threshold. `state` survives a checkpoint resume, which
# is what lets successive passes differ.
ADVANCING = """
workflow deploy {
    state tries = 0
    step attempt {
        tries = tries + 1
        let s = workflow_state()
        print("attempt " + str(s["tries"]))
        checkpoint "attempted"
        if (s["tries"] > %(threshold)s) { checkpoint "verified" }
        return s["tries"]
    }
}
"""


def _goal(threshold: int, *, until: str = 'reached("verified")', max_iterations: int = 6,
          retry_from: str | None = None) -> str:
    clause = f'\n    retry from "{retry_from}"' if retry_from else ""
    return (ADVANCING % {"threshold": threshold}) + f"""
goal ship over deploy {{
    until {until}
    budget {{ max_iterations: {max_iterations}, deadline_ms: 30000 }}{clause}
}}
"""


# closes: #409
class StaticCheckIsTotalTests(unittest.TestCase):
    """The compiler rejects a goal whose waypoints do not exist."""

    def test_unknown_checkpoint_is_rejected_at_compile_time(self):
        source = _goal(2, until='reached("nope")')
        with self.assertRaises(LangSyntaxError) as ctx:
            _parse(source)
        message = str(ctx.exception)
        self.assertIn('waits on checkpoint "nope"', message)
        # The message names what IS available, so the fix is obvious.
        self.assertIn('"attempted"', message)
        self.assertIn('"verified"', message)

    def test_the_check_reaches_inside_and_or_and_not(self):
        for until in (
            'reached("verified") && reached("nope")',
            'reached("nope") || reached("verified")',
            '!reached("nope")',
            '(reached("verified") && (reached("nope") || reached("attempted")))',
        ):
            with self.subTest(until=until):
                with self.assertRaises(LangSyntaxError):
                    _parse(_goal(2, until=until))

    def test_retry_from_label_is_checked_too(self):
        with self.assertRaises(LangSyntaxError) as ctx:
            _parse(_goal(2, retry_from="not_a_checkpoint"))
        self.assertIn('waits on checkpoint "not_a_checkpoint"', str(ctx.exception))

    def test_unknown_workflow_is_rejected(self):
        source = _goal(2).replace("goal ship over deploy", "goal ship over nowhere")
        with self.assertRaises(LangSyntaxError) as ctx:
            _parse(source)
        self.assertIn("pursues 'nowhere'", str(ctx.exception))

    def test_a_dynamic_checkpoint_label_cannot_defeat_the_check(self):
        # The check is total only because both halves are literals. If either
        # became an expression it would silently degrade to best-effort, so pin
        # that the language still refuses a computed label.
        with self.assertRaises(LangSyntaxError):
            _parse('workflow w { step a { let l = "x"\ncheckpoint l\nreturn 1i } }')
        with self.assertRaises(LangSyntaxError):
            _parse(
                'workflow w { step a { checkpoint "x"\nreturn 1i } }\n'
                'goal g over w { until reached(some_var)\n'
                'budget { max_iterations: 1, deadline_ms: 1 } }'
            )

    def test_budget_is_mandatory(self):
        source = _goal(2)
        stripped = "\n".join(
            line for line in source.splitlines() if "budget {" not in line
        )
        with self.assertRaises(LangSyntaxError) as ctx:
            _parse(stripped)
        self.assertIn("has no `budget`", str(ctx.exception))

    def test_both_budget_bounds_are_mandatory(self):
        for partial in ("budget { max_iterations: 3 }", "budget { deadline_ms: 100 }"):
            with self.subTest(budget=partial):
                source = _goal(2).replace(
                    "budget { max_iterations: 6, deadline_ms: 30000 }", partial
                )
                with self.assertRaises(LangSyntaxError) as ctx:
                    _parse(source)
                self.assertIn("budget must set", str(ctx.exception))

    def test_until_is_mandatory(self):
        source = "\n".join(
            line for line in _goal(2).splitlines() if not line.strip().startswith("until")
        )
        with self.assertRaises(LangSyntaxError) as ctx:
            _parse(source)
        self.assertIn("has no `until`", str(ctx.exception))

    def test_error_messages_avoid_em_dashes(self):
        # BUG-131: em-dashes mojibake on Windows cp1252 consoles.
        for source in ("\n".join(
            line for line in _goal(2).splitlines() if "budget {" not in line
        ), _goal(2, until='reached("nope")')):
            with self.subTest(source=source[:30]):
                with self.assertRaises(LangSyntaxError) as ctx:
                    _parse(source)
                self.assertNotIn("\u2014", str(ctx.exception))


# closes: #409
class TheLoopTests(unittest.TestCase):
    """Run the workflow until the predicate holds — the verify→replan half of F22."""

    def test_the_goal_iterates_until_its_predicate_holds(self):
        result = _run(_goal(2) + """
let r = run_goal(ship)
print("satisfied=\\(r["goal_satisfied"]) iterations=\\(r["iterations"])")
""")
        self.assertTrue(result.get("ok"), result)
        out = result["stdout"]
        # Three passes: the workflow's carried state advances 1, 2, 3 and only the
        # third records "verified".
        self.assertEqual(out.count("attempt "), 3)
        self.assertIn("satisfied=true", out)
        self.assertIn("iterations=3", out)

    def test_state_carries_between_iterations(self):
        result = _run(_goal(2) + "let r = run_goal(ship)\n")
        out = result["stdout"]
        self.assertIn("attempt 1.0", out)
        self.assertIn("attempt 2.0", out)
        self.assertIn("attempt 3.0", out)

    def test_a_goal_satisfied_on_the_first_pass_does_not_iterate(self):
        result = _run(_goal(0) + """
let r = run_goal(ship)
print("iterations=\\(r["iterations"])")
""")
        self.assertEqual(result["stdout"].count("attempt "), 1)
        self.assertIn("iterations=1", result["stdout"])

    def test_reached_reports_every_checkpoint_seen(self):
        result = _run(_goal(2) + 'let r = run_goal(ship)\nprint(r["reached"])\n')
        self.assertIn("attempted", result["stdout"])
        self.assertIn("verified", result["stdout"])

    def test_retry_from_pins_the_re_entry_point(self):
        result = _run(_goal(1, retry_from="attempted") + """
let r = run_goal(ship)
print("satisfied=\\(r["goal_satisfied"]) iterations=\\(r["iterations"])")
""")
        self.assertIn("satisfied=true", result["stdout"])
        self.assertIn("iterations=2", result["stdout"])


# closes: #409
class BudgetExhaustionIsAFailureTests(unittest.TestCase):
    """A goal that ran out of budget has not met its objective."""

    UNREACHABLE = _goal(999, max_iterations=3)

    def test_exhausting_the_budget_returns_an_error_not_a_result(self):
        result = _run(self.UNREACHABLE + """
let r = run_goal(ship)
print("type=\\(type(r))")
print("kind=\\(r.kind)")
""")
        self.assertTrue(result.get("ok"), result)
        self.assertIn("type=error", result["stdout"])
        self.assertIn("kind=goal_error", result["stdout"])

    def test_the_loop_stops_at_exactly_the_declared_iteration_count(self):
        result = _run(self.UNREACHABLE + "let r = run_goal(ship)\n")
        self.assertEqual(result["stdout"].count("attempt "), 3)

    def test_the_error_payload_explains_what_happened(self):
        result = _run(self.UNREACHABLE + """
let r = run_goal(ship)
let p = r.payload
print("category=\\(p["category"]) iterations=\\(p["iterations"]) reached=\\(p["reached"])")
""")
        out = result["stdout"]
        self.assertIn("category=budget_exhausted", out)
        self.assertIn("iterations=3", out)
        self.assertIn("attempted", out)

    def test_a_goal_whose_workflow_records_no_checkpoint_stops_immediately(self):
        # Without a checkpoint there is nothing to resume from, so another pass
        # would repeat this one exactly. Say so rather than spin to the budget.
        source = """
workflow deploy { step attempt { print("ran"); return 1i } }
goal ship over deploy {
    until reached("never")
    budget { max_iterations: 5, deadline_ms: 30000 }
}
"""
        with self.assertRaises(LangSyntaxError):
            _parse(source)  # "never" is not recorded — caught statically first


# closes: #409
class TheOriginalGoalFormStillWorksTests(unittest.TestCase):
    """`goal g { step ... }` is Mostly Stable (v4.0.5); this feature is additive."""

    def test_a_step_containing_goal_runs_unchanged(self):
        result = _run("""
goal old_style {
    state n = 0
    step a { n = n + 1; return 1i }
    step b after a { return 2i }
}
let g = run_goal(old_style)
print("steps=\\(g["steps"]) goal=\\(g["goal"])")
""")
        self.assertTrue(result.get("ok"), result)
        self.assertIn('"a": 1', result["stdout"])
        self.assertIn("goal=old_style", result["stdout"])

    def test_the_goal_keywords_remain_usable_as_identifiers(self):
        result = _run("""
let over = 1i
let until = 2i
let budget = 3i
let reached = 4i
let retry = 5i
print(over + until + budget + reached + retry)
""")
        self.assertTrue(result.get("ok"), result)
        self.assertIn("15", result["stdout"])


# closes: #409
class ThePredicateIsInspectableTests(unittest.TestCase):
    """The stopping condition is data, not compiled-away code.

    That is what makes a goal auditable before it runs — the property the design
    is built around. A predicate lowered to a closure would be no better than a
    callback.
    """

    def test_the_lowered_goal_shows_its_condition_and_budget(self):
        result = _run(_goal(2) + "print(ship)\n")
        out = result["stdout"]
        self.assertIn('"workflow": "deploy"', out)
        self.assertIn('"op": "reached"', out)
        self.assertIn('"label": "verified"', out)
        self.assertIn('"max_iterations": 6', out)

    def test_a_compound_condition_lowers_to_a_readable_tree(self):
        source = _goal(2, until='reached("attempted") && reached("verified")')
        result = _run(source + "print(ship)\n")
        out = result["stdout"]
        self.assertIn('"op": "and"', out)
        self.assertIn('"attempted"', out)
        self.assertIn('"verified"', out)


# closes: #409
class TheFormatterHandlesTheNewSyntaxTests(unittest.TestCase):
    """CI format-checks every .nd file, so a node the formatter cannot print is a
    crash for anyone who writes one. It raised `Unknown stmt node: GoalPursuit`
    until this was wired up — the standing hazard when adding an AST node."""

    SOURCE = '''workflow w {
    step a { checkpoint "x"
checkpoint "y"
return 1i }
}
goal g over w {
    until (reached("x") && reached("y")) || !reached("x")
    budget { max_iterations: 3, deadline_ms: 10 }
    retry from "x"
}
'''

    def test_formats_round_trips_and_is_idempotent(self):
        from nodus.tooling.formatter import format_source

        once = format_source(self.SOURCE)
        self.assertIn("goal g over w {", once)
        self.assertIn('until (reached("x") && reached("y")) || !reached("x")', once)
        self.assertIn("budget { max_iterations: 3, deadline_ms: 10 }", once)
        self.assertIn('retry from "x"', once)
        self.assertEqual(once, format_source(once), "formatting is not idempotent")
        _parse(once)  # the formatted output must still parse

    def test_a_goal_without_retry_from_does_not_gain_one(self):
        from nodus.tooling.formatter import format_source

        formatted = format_source(_goal(2))
        self.assertNotIn("retry from", formatted)
        _parse(formatted)


# closes: #409
class PredicateEvaluationIsStrictTests(unittest.TestCase):
    """A malformed predicate must not read as "condition not yet met"."""

    def test_an_unknown_operator_raises_rather_than_reading_as_false(self):
        from nodus.vm.vm import VM

        with self.assertRaises(ValueError) as ctx:
            VM._evaluate_goal_predicate({"op": "whenever"}, {"x"})
        self.assertIn("whenever", str(ctx.exception))

    def test_a_non_map_predicate_raises(self):
        from nodus.vm.vm import VM

        with self.assertRaises(ValueError):
            VM._evaluate_goal_predicate("reached", {"x"})

    def test_the_supported_operators_evaluate_correctly(self):
        from nodus.vm.vm import VM

        reached = {"a", "b"}
        cases = [
            ({"op": "reached", "label": "a"}, True),
            ({"op": "reached", "label": "z"}, False),
            ({"op": "not", "operand": {"op": "reached", "label": "z"}}, True),
            ({"op": "and",
              "left": {"op": "reached", "label": "a"},
              "right": {"op": "reached", "label": "b"}}, True),
            ({"op": "and",
              "left": {"op": "reached", "label": "a"},
              "right": {"op": "reached", "label": "z"}}, False),
            ({"op": "or",
              "left": {"op": "reached", "label": "z"},
              "right": {"op": "reached", "label": "b"}}, True),
        ]
        for node, expected in cases:
            with self.subTest(node=node):
                self.assertEqual(VM._evaluate_goal_predicate(node, reached), expected)


if __name__ == "__main__":
    unittest.main()
