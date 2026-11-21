"""The Nodus frontend written in Nodus agrees with the Python one (#173).

`examples/selfhost/lexer.nd` and `parser.nd` port `nodus.frontend`. They exist to
measure what self-hosting would cost, and a measurement of a port that has
drifted would describe some other program. So this holds them to the Python
frontend on a sample:
- every construct the parser has a branch for, in
  `tests/fixtures/selfhost/constructs.nd`, because the tracked corpus never
  uses half of them;
- the expression compiler example;
- a stdlib module;
- the lexer itself.

The whole corpus takes minutes on CPython, so it is left to
`python -m tools.selfhost_check`.
"""

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO))

from tools.selfhost_check import SelfHosted, check_file, first_difference, to_lists  # noqa: E402

_SAMPLE = (
    "tests/fixtures/selfhost/constructs.nd",
    "examples/expr_compiler.nd",
    "src/nodus/stdlib/loop.nd",
    "examples/selfhost/lexer.nd",
)

_DISAGREEMENTS = ("skipped", "parse_skipped", "lex_error", "lex_diff", "parse_error", "parse_diff")


class TheSelfHostedFrontendAgrees(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sh = SelfHosted()

    def test_tokens_and_ast_match_the_python_frontend(self):
        for relative in _SAMPLE:
            with self.subTest(relative):
                row = check_file(self.sh, _REPO / relative, ("lex", "parse"), measure=False)
                problems = {k: row[k] for k in _DISAGREEMENTS if k in row}
                self.assertEqual(problems, {}, relative)
                self.assertGreater(row["tokens"], 0)

    def test_a_syntax_error_is_reported_not_accepted(self):
        # A port that returned *something* for bad input would agree with nothing
        # and still look healthy on valid files.
        self.sh.source = "let = 1i\n"
        _, _, emitted, error = self.sh.run("ast", "let = 1i\n")
        self.assertIsNone(emitted)
        self.assertIn("Expected identifier", error or "")


class TheComparisonCanFail(unittest.TestCase):
    """The harness is only evidence if a difference reaches its output."""

    def test_a_changed_leaf_is_reported_with_its_path(self):
        self.assertEqual(
            first_difference([["Bool", True]], [["Bool", False]]),
            "[0][1]: expected True, got False",
        )

    def test_a_missing_node_is_reported(self):
        self.assertIn("expected 2 items, got 1", first_difference([1, 2], [1]))

    def test_an_int_and_an_equal_float_agree_but_a_bool_does_not(self):
        # JSON loses the int/float distinction for whole numbers, and the node
        # name already carries it (Int vs Num). A bool is not a number here.
        self.assertEqual(first_difference([1.0], [1]), "")
        self.assertNotEqual(first_difference([1], [True]), "")

    def test_private_fields_are_left_out_of_the_python_tree(self):
        from nodus.frontend.lexer import tokenize
        from nodus.frontend.parser import Parser

        tree = to_lists(Parser(tokenize("let x = 1i\n")).parse())
        self.assertEqual(tree, [["Let", "x", ["Int", 1, "1i"], None, False]])


if __name__ == "__main__":
    unittest.main()
