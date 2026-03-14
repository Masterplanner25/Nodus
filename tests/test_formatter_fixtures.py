import os
import unittest

from nodus.tooling.formatter import format_source


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "fmt")


def load_fixture(name: str, kind: str) -> str:
    path = os.path.join(FIXTURE_DIR, f"{name}_{kind}.nd")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class FormatterFixtureTests(unittest.TestCase):
    def test_formatter_fixtures(self):
        cases = [
            ("fmt_unary_literals", False),
            ("fmt_unary_grouping", False),
            ("fmt_comment_heavy", False),
            ("fmt_trailing_comments", False),
            ("fmt_trailing_comments_keep", True),
            ("fmt_import_export", False),
            ("fmt_nested_blocks", False),
            ("fmt_import_export_comments", False),
            ("fmt_import_export_comments_keep", True),
        ]
        for name, keep_trailing in cases:
            with self.subTest(name=name, keep_trailing=keep_trailing):
                src = load_fixture(name, "input")
                expected = load_fixture(name, "expected")
                formatted = format_source(src, keep_trailing_comments=keep_trailing)
                self.assertEqual(formatted, expected)
                self.assertEqual(format_source(formatted, keep_trailing_comments=keep_trailing), expected)

    def test_nested_unary_expressions(self):
        src = load_fixture("fmt_unary_grouping", "input")
        formatted = format_source(src)
        self.assertIn("let y = - -3", formatted)
        self.assertIn("let z = - -5", formatted)
        self.assertIn("print(- - -2)", formatted)

    def test_unary_expressions_with_comments(self):
        src = load_fixture("fmt_comment_heavy", "input")
        formatted = format_source(src)
        self.assertIn("let y = -(x + 1)", formatted)
        self.assertIn("# trail y", formatted)

    def test_trailing_comments_near_unary(self):
        src = load_fixture("fmt_trailing_comments", "input")
        formatted = format_source(src)
        self.assertIn("let x = -5", formatted)
        self.assertIn("// trailing unary", formatted)
        self.assertNotIn("let x = -5 // trailing unary", formatted)

        src_keep = load_fixture("fmt_trailing_comments_keep", "input")
        formatted_keep = format_source(src_keep, keep_trailing_comments=True)
        self.assertIn("let x = -5 // trailing unary", formatted_keep)
        self.assertIn("let y = -(x + 1) # grouped unary", formatted_keep)

    def test_numeric_literal_fidelity(self):
        src = load_fixture("fmt_unary_literals", "input")
        formatted = format_source(src)
        self.assertIn("let c = -2.50", formatted)
        self.assertIn("let list = [-1, -2.0, -3.75]", formatted)

    def test_idempotence(self):
        src = load_fixture("fmt_import_export", "input")
        formatted = format_source(src)
        self.assertEqual(format_source(formatted), formatted)


if __name__ == "__main__":
    unittest.main()
