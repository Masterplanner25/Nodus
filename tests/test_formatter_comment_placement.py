"""A comment stays where it was written (#737).

`nodus fmt` used to move **every** comment inside **any** block to above the
enclosing top-level statement, stacking them in source order. Position and
nesting depth made no difference, so four comments about four different lines
became one block above the function, explaining none of them.

Nothing caught it for a long time, and the reasons are worth keeping:

- The output is always valid and always stable, so the program still ran.
- `tests/test_formatter_round_trip.py` compares the **AST** field by field, and
  comments are not in the AST — the property that protects fields is blind here.
- The fixture corpus could not catch it either, because three of its inputs had
  been generated from the buggy output. An input that is already a hoisted fixed
  point stays one. Only `fmt_import_export_comments_keep`, written by hand, ever
  had a comment inside a body, and it is the fixture that went red on the fix.

The cause was one question — *which statement was this comment written above?* —
answered in `parse()` and nowhere else. `block()` never drained the queue, so a
comment written inside a body stayed on it until the enclosing top-level
statement finished, and was bound to that.

**Four places claim, and they were found one at a time by trying shapes rather
than by reading the parser.** `parse` and `block` are the obvious two; `flow_def`
is a workflow body, its own loop over `step` and `state`; and `goal_pursuit`
claims for the opposite reason — its body has no statements, so it claims to stop
a comment travelling rather than to place one. A grep of `block()`'s thirteen
call sites suggested it covered every body. It did not.

`TheClaimIsMadeWhereTheStatementStartsTests` is the one that earns its place.
The first fix drained in `block()` too, and moved the comments the *other* way:
by the time a body is entered, the comment above the function and the comment
above the body's first statement are both on one queue, and whichever loop
drains first claims both. Binding after the fact cannot separate them; claiming
at the moment a statement starts can, because only one of them exists yet.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.tooling.formatter import format_source  # noqa: E402

# The issue's own reproduction, verbatim.
EVERY_POSITION = """fn demo() {
    // FIRST: the very first thing in the body.
    let a = 1i
    // MIDDLE: after a statement.
    let b = 2i
    if (a == 1i) {
        // FIRST-IN-BLOCK: first thing in a nested block.
        b = 3i
    }
    if (a == 1i) {
        b = 4i
        // MIDDLE-IN-BLOCK: after a statement in a nested block.
        b = 5i
    }
    return b
}
"""

CLOSURES = """fn takes(body) {
    return body
}

let assigned = fn() {
    // C: inside a closure bound to a let.
    return 1i
}
takes(fn() {
    // D: inside a closure passed as a call argument.
    return 2i
})
"""

EDGES = """fn trailing_case() {
    let x = 1i
    // E: the last thing in the body, before the closing brace.
}

fn only_comment() {
    // F: the body is nothing but this comment.
}
"""


class ACommentStaysWhereItWasWrittenTests(unittest.TestCase):
    # closes: #737
    def test_every_position_in_the_issues_reproduction(self):
        """All four positions, and the file comes back byte-identical.

        Byte-identical is the strong form: it says the comments neither moved
        nor changed indent, without enumerating where each one landed.
        """
        self.assertEqual(EVERY_POSITION, format_source(EVERY_POSITION))

    # closes: #737
    def test_a_closure_body_keeps_its_comments(self):
        """Both closure shapes. The call-argument one matters most: every
        `std:test` case is written that way, so a note about one case used to be
        hoisted above the whole `test.suite(...)`."""
        self.assertEqual(CLOSURES, format_source(CLOSURES))

    # closes: #737
    def test_the_last_comment_in_a_body_does_not_escape(self):
        """A comment with no statement after it has nothing to attach to, so it
        becomes a node of its own. Without that it stayed queued and re-attached
        outside the block."""
        self.assertEqual(EDGES, format_source(EDGES))

    # closes: #737
    def test_a_body_that_is_only_a_comment_keeps_its_braces(self):
        """The one place this fix could have produced *invalid* output: a
        one-statement closure body is collapsed onto a single line, and
        `fn() { // x }` comments out the closing brace."""
        source = "let f = fn() {\n    // nothing yet\n}\n"
        formatted = format_source(source)
        self.assertNotIn("{ //", formatted)
        self.assertIn("    // nothing yet", formatted)
        # And it must still parse, which is the assertion that would have caught
        # a collapse regardless of how the string check was worded.
        from nodus.frontend.lexer import tokenize
        from nodus.frontend.parser import Parser

        Parser(tokenize(formatted)).parse()


class TheOuterCommentDoesNotFallIntoTheBodyTests(unittest.TestCase):
    """The other direction, which the first attempt at this fix broke."""

    # closes: #737
    def test_a_comment_above_a_function_stays_above_it(self):
        source = "// about the function\nfn demo() {\n    // about the statement\n    let a = 1i\n}\n"
        formatted = format_source(source)
        self.assertEqual(source, formatted)
        lines = formatted.splitlines()
        self.assertEqual("// about the function", lines[0], "not pulled into the body")
        self.assertEqual("    // about the statement", lines[2], "not pushed out to the header")

    # closes: #737
    def test_two_comments_that_belong_to_different_scopes_stay_apart(self):
        """The failure mode was that they ended up adjacent, and adjacency is
        what makes a hoisted comment misleading rather than merely misplaced."""
        formatted = format_source(
            "// outer\nfn demo() {\n    // inner\n    return 1i\n}\n"
        )
        self.assertNotIn("// outer\n// inner", formatted)

    # closes: #737
    def test_a_comment_above_a_nested_block_does_not_fall_into_it(self):
        """The shape that separates the two orderings, and the only one that
        does.

        Every other case here passes with `block()` claiming *after* it parses,
        because the top-level loop has already taken the outer comment by then.
        It is one level down that the same mistake bites: the comment above the
        `if` and the comment inside it are both queued when the nested block is
        entered, so a late claim binds both to `print(1i)`. Verified by making
        that exact swap — this case went red and the other five stayed green.
        """
        source = (
            "fn outer() {\n"
            "    // A: above the nested block\n"
            "    if (true) {\n"
            "        // B: inside the nested block\n"
            "        print(1i)\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual(source, format_source(source))


class AWorkflowBodyIsItsOwnLoopTests(unittest.TestCase):
    """A workflow body is not a `block()` — it is a bespoke loop over `step` and
    `state` declarations. So it needed its own claim, and the omission was the
    same defect one level in: the comment above a `step` was taken by the step
    body's first statement.

    Found by trying the shape rather than by reading the parser, which is the
    argument for testing each construct that has its own statement loop instead
    of assuming `block()` covers everything.
    """

    # closes: #737
    def test_comments_above_steps_and_state_stay_where_written(self):
        source = (
            "// above the workflow\n"
            "workflow build {\n"
            "    // above the state declaration\n"
            "    state count = 0\n"
            "    // above the first step\n"
            "    step compile {\n"
            "        // inside a step body\n"
            '        checkpoint "ok"\n'
            '        return "compiled"\n'
            "    }\n"
            "    // above the second step\n"
            "    step ship after compile {\n"
            '        return "shipped"\n'
            "    }\n"
            "}\n"
        )
        self.assertEqual(source, format_source(source))


class AConstructWithNoStatementsStillClaimsTests(unittest.TestCase):
    """A `goal … over …` body holds no statements — `until` and `budget` are
    fields — so a comment inside it has nothing of its own to attach to and no
    position to be rendered at.

    It still has to be *claimed*. Left on the queue it is taken by the next
    top-level statement, or flushed to the end of the file if there is none —
    which is strictly worse than the hoisting this issue is about: a comment
    above the goal is coarse, a comment at the end of the file has left its
    subject entirely. Making the main fix caused exactly that, and it was found
    by trying the shape rather than by reasoning about the parser.
    """

    SOURCE = (
        "workflow w {\n"
        "    step a {\n"
        '        checkpoint "ok"\n'
        "        return 1i\n"
        "    }\n"
        "}\n"
        "// above the goal\n"
        "// above until\n"
        "// above budget\n"
        "goal g over w {\n"
        '    until reached("ok")\n'
        "    budget { max_iterations: 3i }\n"
        "}\n"
        "\n"
        "fn main() {\n"
        "    return 1i\n"
        "}\n"
    )

    # closes: #737
    def test_body_comments_land_above_the_goal_and_stay_there(self):
        """Coarse but adjacent, and a fixed point — so `fmt --check` accepts it."""
        self.assertEqual(self.SOURCE, format_source(self.SOURCE))

    # closes: #737
    def test_they_do_not_migrate_to_a_later_statement(self):
        """The failure that mattered: with no claim they travel forward, past
        code that has nothing to do with them."""
        written = (
            "workflow w {\n"
            "    step a {\n"
            '        checkpoint "ok"\n'
            "        return 1i\n"
            "    }\n"
            "}\n"
            "goal g over w {\n"
            "    // written inside the goal\n"
            '    until reached("ok")\n'
            "    budget { max_iterations: 3i }\n"
            "}\n"
            "\n"
            "fn main() {\n"
            "    return 1i\n"
            "}\n"
        )
        formatted = format_source(written)
        before_main, _, after_main = formatted.partition("fn main")
        self.assertIn("// written inside the goal", before_main)
        self.assertNotIn("// written inside the goal", after_main)


class TheClaimIsMadeWhereTheStatementStartsTests(unittest.TestCase):
    """Asserted on the source. Both loops must claim through the same pair of
    helpers, and must claim *before* parsing — draining afterwards is what moved
    the comments in one direction or the other depending on which loop won."""

    def _parser_source(self) -> str:
        return (_REPO_ROOT / "src" / "nodus" / "frontend" / "parser.py").read_text(
            encoding="utf-8"
        )

    # closes: #737
    def test_exactly_these_four_places_claim_comments(self):
        """Four claim, for two different reasons, and both are worth naming.

        **Three parse a sequence of statements** and claim so each comment lands
        on the statement it was written above: `parse`, `block`, and — missed on
        the first pass — `flow_def`, because a workflow body is its own loop over
        `step` and `state` rather than a `block()`.

        **`goal_pursuit` claims for the opposite reason.** Its body has no
        statements at all, so there is nowhere to place a comment; it claims so
        the comment does not *travel*, which is what an unclaimed one does.

        A fifth has to add itself here, and say which of the two it is.
        """
        import ast

        tree = ast.parse(self._parser_source())
        claiming = {
            function.name
            for function in ast.walk(tree)
            if isinstance(function, ast.FunctionDef)
            and any(
                isinstance(node, ast.Call)
                and getattr(node.func, "attr", None) == "take_pending_comments"
                for node in ast.walk(function)
            )
        }
        self.assertEqual({"parse", "block", "flow_def", "goal_pursuit"}, claiming)

    # closes: #737
    def test_the_claim_precedes_the_parse_in_both_loops(self):
        """Ordering, not presence. `take` *after* `stmt()` compiles fine, passes
        every other test in this class, and moves each outer comment into the
        body it precedes — that was the first attempt at this fix.

        Read off the AST rather than by string offsets. The obvious spelling —
        find the nearest `take` textually above each `self.stmt()` — cannot fail:
        with two loops in one file, one loop's claim satisfies the other's
        assertion. Statement order *within each loop body* is the actual claim.
        """
        import ast

        # What each loop calls to produce the statement it is about to bind.
        producers = {"stmt", "flow_step", "flow_state_decl"}
        tree = ast.parse(self._parser_source())
        checked = []
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef):
                continue
            for loop in ast.walk(function):
                if not isinstance(loop, ast.While):
                    continue
                claim = None
                produced = []
                for node in ast.walk(loop):
                    if not isinstance(node, ast.Call):
                        continue
                    name = getattr(node.func, "attr", None)
                    if name == "take_pending_comments":
                        claim = node.lineno
                    elif name in producers:
                        produced.append((name, node.lineno))
                if claim is None or not produced:
                    continue
                checked.append(function.name)
                for name, line in produced:
                    with self.subTest(loop=function.name, produces=name):
                        self.assertLess(
                            claim, line,
                            "the comments must be claimed before the statement is "
                            "parsed, or parsing the body claims the outer comment",
                        )
        self.assertEqual(
            {"parse", "block", "flow_def"},
            set(checked),
            "every claiming loop must have been checked",
        )

    # closes: #737
    def test_a_block_flushes_what_nothing_follows(self):
        source = self._parser_source()
        self.assertEqual(
            2,
            source.count("self.flush_trailing_comments("),
            "end of file and end of block both need it, or the last comment in a "
            "body escapes to the next statement",
        )


class TheFormatterOutputStillRunsTests(unittest.TestCase):
    # closes: #737
    def test_a_formatted_program_with_comments_executes(self):
        """End to end through the CLI: the comments are in the file the runtime
        actually parses, not only in a formatter unit test."""
        program = (
            "fn demo() {\n"
            "    // a comment that must survive\n"
            "    let a = 1i\n"
            "    if (a == 1i) {\n"
            "        // and this one\n"
            "        a = 2i\n"
            "    }\n"
            "    return a\n"
            "}\n"
            "\n"
            "fn main() {\n"
            '    print("demo -> \\(demo())")\n'
            "}\n"
        )
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prog.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(format_source(program))
            env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
            proc = subprocess.run(
                [sys.executable, str(_REPO_ROOT / "nodus.py"), "run", path,
                 "--time-limit", "30"],
                capture_output=True, text=True, env=env, timeout=180,
            )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("demo -> 2", proc.stdout)


if __name__ == "__main__":
    unittest.main()
