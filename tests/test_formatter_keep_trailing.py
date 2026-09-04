"""`--keep-trailing` applies to every statement, not just the simple ones (#743).

`nodus fmt --keep-trailing` is documented as *"Preserve trailing comments in
their original positions"*. It honoured that for `let a = 1 // note` and ignored
it for every **block-bodied** statement — `fn`, `workflow`, `goal`, `if`,
`while`, `for`, `try`, `match` — demoting the comment onto its own line anyway.

One question, *how is a trailing comment rendered?*, answered in thirty-four
places. `_format_stmt` has that many return points: nineteen called
`attach_trailing`, which reads the mode; fifteen called `trailing_lines`
directly, which does not; and two rendered nothing at all. The fifteen were the
block-bodied ones.

Hoisting the answer into `format_stmt` is the fix rather than converting fifteen
call sites, because a thirty-fifth branch would have been written like the
fifteen. The branches no longer see `trailing`.

**The blocker recorded on the issue turned out not to exist**, which is why this
could be fixed rather than designed. I had claimed a comment on a function's
*header* line (`fn f() { // about f`) parses as the `FnDef`'s trailing comment,
making it indistinguishable from one on the closing brace — so routing through
`attach_trailing` would silently move it. Checked instead of assumed: a header
comment never reaches the `FnDef` at all. `TheHeaderLineIsADifferentQuestionTests`
records where it does go, because that is its own defect and not this one.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.tooling.formatter import format_source  # noqa: E402

#: One per branch family that used to bypass the mode. The comment sits on the
#: closing brace in each, which is the only place a block statement's trailing
#: comment can come from — see `TheHeaderLineIsADifferentQuestionTests`.
BLOCK_BODIED = {
    "fn": "fn f() {\n    return 1i\n} // note\n",
    "if": "fn f() {\n    if (true) {\n        return 1i\n    } // note\n    return 2i\n}\n",
    "while": "fn f() {\n    while (false) {\n        return 1i\n    } // note\n    return 2i\n}\n",
    "for": "fn f() {\n    for (let i = 0; i < 2; i = i + 1) {\n        print(i)\n    } // note\n    return 1i\n}\n",
    "try": "fn f() {\n    try {\n        return 1i\n    } catch e {\n        return 2i\n    } // note\n    return 3i\n}\n",
    "workflow step": "workflow w {\n    step a {\n        return 1i\n    } // note\n}\n",
    "goal step": "goal g {\n    step a {\n        return 1i\n    } // note\n}\n",
    "match": 'fn f(x) {\n    let r = match x {\n        1i => "one",\n        _ => "o",\n    } // note\n    return r\n}\n',
    "simple statement": "let a = 1 // note\n",
}


class KeepTrailingKeepsItOnTheLineTests(unittest.TestCase):
    # closes: #743
    def test_every_statement_kind_keeps_its_trailing_comment(self):
        """`// note` must still share a line with something, in every case.

        Asserted as "no line is only the comment" rather than by naming the line
        it lands on, because that differs by construct — the brace for a block,
        the statement itself for a simple one — and the mode's promise is about
        *keeping* it, not about where."""
        for name, source in BLOCK_BODIED.items():
            with self.subTest(statement=name):
                formatted = format_source(source, keep_trailing_comments=True)
                self.assertIn("// note", formatted)
                self.assertNotIn(
                    "\n// note", "\n" + "\n".join(
                        line.strip() for line in formatted.splitlines()
                    ),
                    "the comment was demoted onto a line of its own",
                )

    # closes: #743
    def test_a_block_keeps_it_on_the_closing_brace(self):
        """Named for the `fn` case, because that is the one in the issue."""
        formatted = format_source(BLOCK_BODIED["fn"], keep_trailing_comments=True)
        self.assertIn("} // note", formatted)

    # closes: #743
    def test_the_default_mode_still_demotes(self):
        """The other half of the promise: without the flag, nothing changed.

        A fix that made every mode keep comments in place would satisfy the test
        above and break the documented default."""
        for name, source in BLOCK_BODIED.items():
            with self.subTest(statement=name):
                formatted = format_source(source)
                self.assertIn("// note", formatted)
                self.assertNotIn("} // note", formatted)
                self.assertNotIn("= 1 // note", formatted)

    # closes: #743
    def test_both_modes_reach_a_fixed_point(self):
        """`fmt` writes in place and `fmt --check` compares against one
        formatting, so a mode without a fixed point emits files it then refuses
        (#739)."""
        for name, source in BLOCK_BODIED.items():
            for keep in (False, True):
                with self.subTest(statement=name, keep_trailing=keep):
                    once = format_source(source, keep_trailing_comments=keep)
                    self.assertEqual(
                        once, format_source(once, keep_trailing_comments=keep)
                    )
                    Parser(tokenize(once)).parse()


class TheAnswerIsGivenInOnePlaceTests(unittest.TestCase):
    """Asserted on the source. Behaviour cannot tell a branch that consults the
    mode from one that happens to agree with it today, and the fifteen that did
    not consult it were all written by copying a neighbour."""

    def _formatter_source(self) -> str:
        return (_REPO_ROOT / "src" / "nodus" / "tooling" / "formatter.py").read_text(
            encoding="utf-8"
        )

    # closes: #743
    def test_no_dispatch_branch_renders_a_trailing_comment_itself(self):
        """The durable half of the fix. Converting fifteen call sites would have
        left the thirty-fifth branch free to be written like the fifteen."""
        import ast

        tree = ast.parse(self._formatter_source())
        body = next(
            f for f in ast.walk(tree)
            if isinstance(f, ast.FunctionDef) and f.name == "_format_stmt"
        )
        rendering = {
            name
            for node in ast.walk(body)
            if isinstance(node, ast.Call)
            for name in [getattr(node.func, "id", None)]
            if name in {"attach_trailing", "trailing_lines"}
        }
        self.assertEqual(
            set(), rendering,
            "_format_stmt must not render trailing comments -- format_stmt does "
            "it once, for every branch",
        )

    # closes: #743
    def test_the_wrapper_does_render_them(self):
        """Guard the guard: the assertion above is satisfied just as well by a
        formatter that dropped trailing comments entirely."""
        import ast

        tree = ast.parse(self._formatter_source())
        wrapper = next(
            f for f in ast.walk(tree)
            if isinstance(f, ast.FunctionDef) and f.name == "format_stmt"
        )
        calls = {
            getattr(node.func, "id", None)
            for node in ast.walk(wrapper)
            if isinstance(node, ast.Call)
        }
        self.assertIn("attach_trailing", calls)


class AFlowBodyKeepsItsDanglingCommentTests(unittest.TestCase):
    """A comment above a workflow's closing brace used to escape the workflow.

    `steps` and `states` are typed lists, so a `Comment` node cannot be appended
    the way `block()` appends one — `flow_def` reads `.name` off every entry. So
    nothing claimed it, the next top-level statement's claim did, and `fmt` wrote
    a file `fmt --check` rejected.

    That is #739's symptom in the one statement loop #739's fix did not reach,
    and it was found by probing each construct here rather than by reading the
    code — the same way #737's three gaps were found.
    """

    SOURCE = (
        "workflow w {\n"
        "    step a {\n"
        "        return 1i\n"
        "    }\n"
        "    // dangling\n"
        "}\n"
        "\n"
        "fn main() {\n"
        "    return 1i\n"
        "}\n"
    )

    # closes: #743
    def test_it_stays_inside_the_body(self):
        self.assertEqual(self.SOURCE, format_source(self.SOURCE))

    # closes: #743
    def test_it_does_not_migrate_to_the_next_statement(self):
        formatted = format_source(format_source(self.SOURCE))
        before_main, _, after_main = formatted.partition("fn main")
        self.assertIn("// dangling", before_main)
        self.assertNotIn("// dangling", after_main)

    # closes: #743
    def test_fmt_then_fmt_check_accepts_a_workflow(self):
        """The contract, through the CLI. This is what was failing."""
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "wf.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "workflow w {\n    step a {\n        return 1i\n    } // note\n}\n"
                    "\nfn main() {\n    return 1i\n}\n"
                )
            wrote = subprocess.run(
                [sys.executable, str(_REPO_ROOT / "nodus.py"), "fmt", path],
                capture_output=True, text=True, env=env, timeout=180,
            )
            self.assertEqual(0, wrote.returncode, wrote.stderr)
            checked = subprocess.run(
                [sys.executable, str(_REPO_ROOT / "nodus.py"), "fmt", "--check", path],
                capture_output=True, text=True, env=env, timeout=180,
            )
        self.assertNotIn("not formatted", checked.stdout + checked.stderr)


class TheHeaderLineIsADifferentQuestionTests(unittest.TestCase):
    """A comment on the *opening* line is not the statement's trailing comment.

    This distinction is what makes #743's fix unambiguous, which is why it is
    pinned here rather than only where it was fixed: a block statement's trailing
    comment can **only** have come from its closing brace, so putting one back on
    that brace in `--keep-trailing` mode cannot relocate a header comment.

    When #743 was filed I had asserted the opposite — that both reach the
    `FnDef`, making them indistinguishable and the fix a design question.
    Checking that is what turned up the real defect: the header comment was
    bound to the body's **first statement**, so `fn f() { // about f` came back
    as a note under `return 1i`. Filed as issue 746 and fixed separately; it now
    belongs to the brace it was written on, which
    `tests/test_formatter_header_comments.py` covers.
    """

    # closes: #743
    def test_a_header_comment_never_reaches_the_block_statement(self):
        stmts = Parser(tokenize("fn f() { // about f\n    return 1i\n}\n")).parse()
        self.assertIsNone(getattr(stmts[0], "_trailing_comments", None))

    # closes: #743
    def test_it_belongs_to_the_brace_it_was_written_on(self):
        """Where it goes instead — and not to the first statement, which is what
        it used to do."""
        stmts = Parser(tokenize("fn f() { // about f\n    return 1i\n}\n")).parse()
        self.assertEqual(
            ["// about f"], getattr(stmts[0].body, "_header_comments", None)
        )
        first = stmts[0].body.stmts[0]
        self.assertIsNone(getattr(first, "_trailing_comments", None))

    # closes: #743
    def test_a_brace_comment_does_reach_it(self):
        """The pair that matters: only the closing brace reaches the statement,
        so putting it back there cannot move a header comment."""
        stmts = Parser(tokenize("fn f() {\n    return 1i\n} // done\n")).parse()
        self.assertEqual(["// done"], getattr(stmts[0], "_trailing_comments", None))

    # closes: #743
    def test_the_two_positions_stay_distinct(self):
        """Both at once. If the two ever merged into one list, `--keep-trailing`
        would move the header comment down onto the brace — the exact silent
        relocation the #743 blocker feared."""
        stmts = Parser(
            tokenize("fn f() { // header\n    return 1i\n} // brace\n")
        ).parse()
        self.assertEqual(["// header"], getattr(stmts[0].body, "_header_comments", None))
        self.assertEqual(["// brace"], getattr(stmts[0], "_trailing_comments", None))


if __name__ == "__main__":
    unittest.main()
