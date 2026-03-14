import unittest

from nodus.frontend.lexer import tokenize
from nodus.frontend.parser import Parser


class LexerNewlineTests(unittest.TestCase):
    def test_windows_newlines(self):
        src = 'print("hello")\r\nprint("world")\r\n'
        toks = tokenize(src)
        Parser(toks).parse()

    def test_classic_mac_newlines(self):
        src = 'print("hello")\rprint("world")\r'
        toks = tokenize(src)
        Parser(toks).parse()


if __name__ == "__main__":
    unittest.main()
