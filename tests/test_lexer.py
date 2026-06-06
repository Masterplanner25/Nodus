import unittest

from nodus.frontend.lexer import tokenize
from nodus.frontend.parser import Parser
from nodus.runtime.diagnostics import LangSyntaxError


class LexerNewlineTests(unittest.TestCase):
    def test_windows_newlines(self):
        src = 'print("hello")\r\nprint("world")\r\n'
        toks = tokenize(src)
        Parser(toks).parse()

    def test_classic_mac_newlines(self):
        src = 'print("hello")\rprint("world")\r'
        toks = tokenize(src)
        Parser(toks).parse()


class IntegerDoubleSuffixTests(unittest.TestCase):
    """BUG-83: 1ii should give a parse error with a helpful message."""

    def _expect_syntax_error(self, src):
        with self.assertRaises(LangSyntaxError) as ctx:
            tokenize(src)
        return str(ctx.exception)

    def test_double_i_suffix_raises_syntax_error(self):
        msg = self._expect_syntax_error("let x = 1ii")
        self.assertIn("1ii", msg)

    def test_double_i_suffix_suggests_correction(self):
        msg = self._expect_syntax_error("let x = 1ii")
        self.assertIn("1i", msg)

    def test_triple_i_suffix_also_errors(self):
        msg = self._expect_syntax_error("let x = 42iii")
        self.assertIn("42iii", msg)

    def test_i_followed_by_identifier_errors(self):
        msg = self._expect_syntax_error("let x = 5ib")
        self.assertIn("5ib", msg)

    def test_single_i_suffix_still_works(self):
        toks = tokenize("let x = 1i")
        kinds = [t.kind for t in toks]
        self.assertIn("NUM_INT", kinds)

    def test_expression_with_valid_ints_still_works(self):
        toks = tokenize("let x = 1i + 2i")
        self.assertEqual(len([t for t in toks if t.kind == "NUM_INT"]), 2)


if __name__ == "__main__":
    unittest.main()
