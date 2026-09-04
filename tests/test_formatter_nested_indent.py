"""A closure body is indented for where it sits (#742).

`format_expr` renders a multi-line closure against column 0, because an
expression is never told how deep it is — the signature is
`format_expr(expr, parent_prec)`. So every multi-line closure body came out at
one level from the left margin and its closing brace at column 0, wherever the
closure actually was:

    fn f() {
        let g = fn() {
        let a = 1i          <- should be 8 spaces
        return a
    }                       <- should be 4
        return g
    }

Stable and parseable, so `fmt --check` accepted it and nothing failed. It got
worse with depth: a three-level nest put every inner body at the same column.

The fix shifts the lines once, on the way out of `format_stmt`, which is the
first place that knows the depth. It composes with nesting instead of counting
levels — each statement fixes up whatever multi-line text it was handed relative
to its own indent.

**#737 is what made this worth fixing.** Before it, a comment inside a short
closure body was hoisted out, leaving one statement, and the body collapsed onto
a single line — the multi-line branch was rarely taken. Once comments stayed put,
bodies stopped collapsing and the bad indentation started showing up in ordinary
code. Five tracked `.nd` files were reformatted by this change, `std:async`
among them.
"""

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.tooling.formatter import format_source  # noqa: E402

TWO_LEVELS = """fn f() {
    let g = fn() {
        let a = 1i
        return a
    }
    return g
}
"""

THREE_LEVELS = """fn f() {
    let g = fn() {
        let h = fn() {
            let a = 1i
            return a
        }
        return h
    }
    return g
}
"""

CALL_ARGUMENT = """fn takes(body) {
    return body
}

fn f() {
    takes(fn() {
        let a = 1i
        return a
    })
}
"""

# The shape this actually shows up in: `std:test` suites, and `spawn(coroutine(
# fn() { ... }))` in `std:async` — both a closure inside a call inside a block.
SUITE = """import "std:test" as test

test.suite("a suite", fn() {
    test.case("a case", fn() {
        let a = 1i
        test.assert(a == 1i, "one")
    })
})
"""


class AClosureBodyIsIndentedForWhereItSitsTests(unittest.TestCase):
    """Byte-identical is the assertion: the input is written the way a person
    would, so anything the formatter moves shows up."""

    # closes: #742
    def test_one_closure_inside_a_function(self):
        self.assertEqual(TWO_LEVELS, format_source(TWO_LEVELS))

    # closes: #742
    def test_a_closure_inside_a_closure(self):
        """Depth is where the old behaviour was worst — every inner body landed
        at the same column, so nesting was invisible in the output."""
        self.assertEqual(THREE_LEVELS, format_source(THREE_LEVELS))

    # closes: #742
    def test_a_closure_passed_as_a_call_argument(self):
        self.assertEqual(CALL_ARGUMENT, format_source(CALL_ARGUMENT))

    # closes: #742
    def test_the_shape_it_actually_appears_in(self):
        self.assertEqual(SUITE, format_source(SUITE))

    # closes: #742
    def test_the_closing_brace_lines_up_with_the_line_that_opened_it(self):
        """Stated as its own assertion because it is the specific symptom: the
        brace was emitted at column 0 regardless of depth, so it did not line up
        with anything."""
        lines = format_source(THREE_LEVELS).splitlines()
        opens = [line for line in lines if line.rstrip().endswith("{")]
        closes = [line for line in lines if line.strip() == "}"]
        self.assertEqual(3, len(opens), "three nested openers")
        self.assertEqual(
            [0, 4, 8],
            [len(line) - len(line.lstrip()) for line in opens],
            "openers step in by one level each",
        )
        self.assertEqual(
            [8, 4, 0],
            [len(line) - len(line.lstrip()) for line in closes],
            "closers step back out to match, innermost first",
        )


INLINE_MATCH = """fn f(x) {
    let r = match x {
        1i => "one",
        _ => "other",
    }
    return r
}
"""


class TheSameFixCoveredInlineMatchTests(unittest.TestCase):
    """`format_expr`'s `Match` fallback carried a comment saying its closing
    brace landed at column 0, "same limitation as inline fn expressions".

    It was the same limitation, so one change fixed both: neither construct ever
    needed to know its own depth, and neither has to now. Pinned because the
    comment was the only record that they were the same problem, and it has been
    rewritten."""

    # closes: #742
    def test_a_match_in_a_nested_expression_position_is_indented(self):
        self.assertEqual(INLINE_MATCH, format_source(INLINE_MATCH))


class TheOutputIsStillValidTests(unittest.TestCase):
    # closes: #742
    def test_every_case_reparses_and_is_a_fixed_point(self):
        for name, source in (
            ("two levels", TWO_LEVELS),
            ("three levels", THREE_LEVELS),
            ("call argument", CALL_ARGUMENT),
            ("suite", SUITE),
            ("inline match", INLINE_MATCH),
        ):
            with self.subTest(case=name):
                formatted = format_source(source)
                Parser(tokenize(formatted)).parse()
                self.assertEqual(
                    formatted, format_source(formatted), "not a fixed point"
                )


class MultiLineExpressionsAreSplitIntoLinesTests(unittest.TestCase):
    """The other half of the fix, and the reason the single-line collapse in the
    `FnExpr` branch behaves.

    A statement whose rendering spans lines used to come back as one list entry
    with newlines inside it, so `len(body_lines) == 1` read a four-line closure
    as a one-liner and inlined it.
    """

    # closes: #742
    def test_a_statement_containing_a_closure_yields_one_entry_per_line(self):
        from nodus.tooling.formatter import format_stmt

        stmts = Parser(tokenize(TWO_LEVELS)).parse()
        produced = format_stmt(stmts[0], indent=0)
        self.assertEqual(
            [], [line for line in produced if "\n" in line],
            "no entry may still contain an embedded newline",
        )
        self.assertEqual(7, len(produced), "one entry per rendered line")


if __name__ == "__main__":
    unittest.main()
