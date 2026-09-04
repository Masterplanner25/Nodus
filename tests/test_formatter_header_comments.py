"""A comment on a `{` line belongs to the brace it opened (#746).

It shares a line with the last token consumed — the `{` — so the parser's line
rule classified it as a *trailing* comment, and the next `bind_comments` handed
it to whatever statement was parsed next. `fn f() { // about f` came back as a
note under `return 1i`.

Probing every brace position rather than the one in the issue turned up three
things the report did not have:

- **It applies to every opening brace**, not just a function's — `if`/`else`,
  `try`/`catch`, `while`, closures, `workflow`, `step`, `goal`, `match`.
- **A workflow's own header comment sank two levels**, into the *step* body,
  where it stacked against the step's — two comments about different constructs,
  adjacent, describing neither.
- **An empty body let the comment escape the construct entirely**:
  `fn f() { // only a comment }` rendered the comment *after* the function.

The comment is rendered at the top of the body rather than back on the brace
line, and that is a deliberate trade. Putting it back would mean every branch
that builds a header string appending it — nine of them, plus the arms of
`if`/`else` and `try`/`catch`/`finally` — and a branch that forgot would drop the
comment silently. One place that cannot be forgotten beats fifteen that can; the
comment still reads as being about that body, which is what it was written about.
"""

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.tooling.formatter import format_source  # noqa: E402

#: Written the way a person writes them — comment on the brace line — paired
#: with where each must end up. Every construct that opens a brace is here,
#: because each one that opens its own is a place the claim can be forgotten.
POSITIONS = {
    "fn": (
        "fn f() { // about f\n    return 1i\n}\n",
        "fn f() {\n    // about f\n    return 1i\n}\n",
    ),
    "if and else": (
        "fn f(x) {\n    if (x) { // then\n        return 1i\n    } else { // else\n        return 2i\n    }\n}\n",
        "fn f(x) {\n    if (x) {\n        // then\n        return 1i\n    } else {\n        // else\n        return 2i\n    }\n}\n",
    ),
    "try and catch": (
        "fn f() {\n    try { // trying\n        return 1i\n    } catch e { // caught\n        return 2i\n    }\n}\n",
        "fn f() {\n    try {\n        // trying\n        return 1i\n    } catch e {\n        // caught\n        return 2i\n    }\n}\n",
    ),
    "while": (
        "fn f() {\n    while (true) { // looping\n        break\n    }\n    return 1i\n}\n",
        "fn f() {\n    while (true) {\n        // looping\n        break\n    }\n    return 1i\n}\n",
    ),
    "closure": (
        "fn f() {\n    let g = fn() { // about g\n        return 1i\n    }\n    return g\n}\n",
        "fn f() {\n    let g = fn() {\n        // about g\n        return 1i\n    }\n    return g\n}\n",
    ),
    "match": (
        'fn f(x) {\n    let r = match x { // about the match\n        1i => "one",\n        _ => "o",\n    }\n    return r\n}\n',
        'fn f(x) {\n    let r = match x {\n        // about the match\n        1i => "one",\n        _ => "o",\n    }\n    return r\n}\n',
    ),
    "goal, plain form": (
        "goal g { // about g\n    step a {\n        return 1i\n    }\n}\n",
        "goal g {\n    // about g\n    step a {\n        return 1i\n    }\n}\n",
    ),
}


class EachCommentStaysWithItsOwnBraceTests(unittest.TestCase):
    # closes: #746
    def test_every_brace_position(self):
        for name, (written, expected) in POSITIONS.items():
            with self.subTest(construct=name):
                self.assertEqual(expected, format_source(written))

    # closes: #746
    def test_a_workflow_and_its_step_keep_their_own(self):
        """The worst case in the report. Both comments used to end up in the
        *step* body, adjacent, describing neither construct."""
        written = (
            "workflow w { // about w\n"
            "    step a { // about a\n"
            "        return 1i\n"
            "    }\n"
            "}\n"
        )
        expected = (
            "workflow w {\n"
            "    // about w\n"
            "    step a {\n"
            "        // about a\n"
            "        return 1i\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual(expected, format_source(written))

    # closes: #746
    def test_a_goal_pursuit_keeps_its_own(self):
        """Its body holds no statements — `until` and `budget` are fields — so
        an unclaimed comment had nothing to attach to and escaped to *after* the
        whole goal."""
        written = (
            "workflow w {\n    step a {\n        checkpoint \"ok\"\n        return 1i\n    }\n}\n"
            "goal g over w { // about the pursuit\n"
            '    until reached("ok")\n'
            "    budget { max_iterations: 2i }\n"
            "}\n"
        )
        formatted = format_source(written)
        body = formatted.split("goal g over w {")[1]
        self.assertIn("// about the pursuit", body)
        self.assertTrue(
            body.index("// about the pursuit") < body.index("until"),
            "it belongs at the top of the body, not after it",
        )


class AnEmptyBodyKeepsItsCommentTests(unittest.TestCase):
    """The case that made the two `FnExpr` shortcuts concrete: both skip
    `format_block`, which is where a header comment is rendered, so either would
    drop it silently. An empty body has no statements at all, so collapsing it to
    `{}` loses the only thing in it."""

    # closes: #746
    def test_an_empty_function_body(self):
        self.assertEqual(
            "fn f() {\n    // only a comment\n}\n",
            format_source("fn f() { // only a comment\n}\n"),
        )

    # closes: #746
    def test_an_empty_closure_body(self):
        written = "fn f() {\n    let g = fn() { // later\n    }\n    return g\n}\n"
        formatted = format_source(written)
        self.assertIn("// later", formatted)
        self.assertNotIn("{}", formatted)
        # And it must not have escaped the closure.
        self.assertLess(
            formatted.index("// later"), formatted.index("return g"),
            "the comment left the closure it was written on",
        )


class TheOutputIsStableAndValidTests(unittest.TestCase):
    # closes: #746
    def test_every_case_is_a_fixed_point_and_reparses(self):
        """A header comment renders on its own line, where re-parsing reads it
        as a *leading* comment rather than a trailing one — two classifications
        for one thing. Claiming only the first printed a file that parsed into a
        different one, which is #739's failure; both are claimed, so the second
        pass reproduces the first."""
        sources = [written for written, _ in POSITIONS.values()]
        sources.append("fn f() { // only a comment\n}\n")
        sources.append("workflow w { // about w\n    step a { // about a\n        return 1i\n    }\n}\n")
        for index, source in enumerate(sources):
            with self.subTest(case=index):
                once = format_source(source)
                self.assertEqual(once, format_source(once), "not a fixed point")
                Parser(tokenize(once)).parse()

    # closes: #746
    def test_it_holds_with_trailing_comments_kept(self):
        """`--keep-trailing` must not pull a header comment onto a statement:
        the two positions are distinct, and merging them is what the #743
        blocker feared."""
        written = "fn f() { // header\n    return 1i\n} // brace\n"
        formatted = format_source(written, keep_trailing_comments=True)
        self.assertIn("} // brace", formatted)
        self.assertIn("    // header", formatted)
        self.assertNotIn("return 1i // header", formatted)
        self.assertEqual(
            formatted, format_source(formatted, keep_trailing_comments=True)
        )


if __name__ == "__main__":
    unittest.main()
