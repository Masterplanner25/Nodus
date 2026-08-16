"""The keyword list is the source of truth for tooling (#357).

`match`, `break` and `continue` shipped in v4.1.0 and the VS Code grammar did not
highlight them for two releases. A reader following the Control Flow docs writes
a `match` expression, sees it render as a plain identifier, and reasonably
concludes the feature is not real yet — on the most externally visible surface
the language has.

The reason it went unnoticed is that nothing listed those three words anywhere a
tool could read them. They are *contextual* keywords: the parser recognises them
from identifier tokens rather than the lexer reserving them, so they were string
literals at two `if` statements in `parser.py` and nowhere else.

`lexer.ALL_KEYWORDS` is now that list, and the parser reads its own recognition
sets from it. These tests hold the two ends together:

- the parser accepts every contextual keyword the list names, and
- the shipped VS Code grammar highlights every keyword in the list.

The grammar lives in the `nodus-vscode` repo, which this repo's CI cannot see, so
that check skips when the repo is not present locally. It is deliberately a
`skip` and not a silent pass — an unrunnable check should say so.
"""

import json
import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.frontend.lexer import (  # noqa: E402
    ALL_KEYWORDS,
    CONTEXTUAL_KEYWORDS,
    EXPRESSION_KEYWORDS,
    GOAL_KEYWORDS,
    KEYWORDS,
    LOOP_CONTROL_KEYWORDS,
)
from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402

_VSCODE_GRAMMAR = Path("C:/dev/nodus-vscode/syntaxes/nodus.tmLanguage.json")


def _grammar_patterns(node, out: list) -> list:
    if isinstance(node, dict):
        if isinstance(node.get("match"), str):
            out.append(node["match"])
        for value in node.values():
            _grammar_patterns(value, out)
    elif isinstance(node, list):
        for value in node:
            _grammar_patterns(value, out)
    return out


def words_matched_by(grammar_path: Path) -> set[str]:
    """Every bare word a TextMate grammar highlights via a \\b-delimited pattern."""
    patterns = _grammar_patterns(
        json.loads(grammar_path.read_text(encoding="utf-8")), []
    )
    words: set[str] = set()
    for pattern in patterns:
        # "\b(a|b|c)\b" — an alternation of literal words.
        for m in re.finditer(r"\\b\(([^)]*)\)\\b", pattern):
            words |= {w for w in m.group(1).split("|") if w.isidentifier()}
        # "\bword\b" — a single literal word.
        for m in re.finditer(r"\\b([A-Za-z_]+)\\b", pattern):
            words.add(m.group(1))
    return words


class KeywordListTests(unittest.TestCase):
    def test_all_keywords_is_the_union(self):
        self.assertEqual(KEYWORDS | CONTEXTUAL_KEYWORDS, ALL_KEYWORDS)

    def test_contextual_keywords_are_not_reserved(self):
        # The point of a contextual keyword: still usable as a name.
        self.assertEqual(set(), CONTEXTUAL_KEYWORDS & KEYWORDS)

    def test_contextual_keywords_are_split_by_where_they_parse(self):
        self.assertEqual(LOOP_CONTROL_KEYWORDS | EXPRESSION_KEYWORDS | GOAL_KEYWORDS,
                         CONTEXTUAL_KEYWORDS)


# closes: #357
class ParserRecognisesEveryContextualKeywordTests(unittest.TestCase):
    """The list cannot drift from what the parser actually accepts."""

    def _parses(self, source: str) -> bool:
        try:
            Parser(tokenize(source)).parse()
            return True
        except Exception:
            return False

    def test_loop_control_keywords_parse_inside_a_loop(self):
        for word in sorted(LOOP_CONTROL_KEYWORDS):
            with self.subTest(keyword=word):
                self.assertTrue(
                    self._parses("while (true) { %s }" % word),
                    f"parser does not accept `{word}` but the keyword list names it",
                )

    def test_goal_keywords_parse_inside_a_goal_pursuit(self):
        source = """
workflow w { step a { checkpoint "done"; return 1i } }
goal g over w {
    until reached("done")
    budget { max_iterations: 2, deadline_ms: 10 }
    retry from "done"
}
"""
        self.assertTrue(
            self._parses(source),
            "parser does not accept the goal-pursuit form but GOAL_KEYWORDS names its words",
        )
        for word in sorted(GOAL_KEYWORDS):
            with self.subTest(keyword=word):
                self.assertIn(word, source, f"`{word}` is listed but unused by the check above")

    def test_goal_keywords_are_still_usable_as_variable_names(self):
        # Contextual, not reserved: making `until` or `budget` a hard keyword
        # would break existing programs for no benefit.
        for word in sorted(GOAL_KEYWORDS):
            with self.subTest(keyword=word):
                self.assertTrue(
                    self._parses("let %s = 1i\nprint(%s)" % (word, word)),
                    f"`{word}` should remain usable as an identifier",
                )

    def test_expression_keywords_parse_as_expressions(self):
        for word in sorted(EXPRESSION_KEYWORDS):
            with self.subTest(keyword=word):
                self.assertTrue(
                    self._parses('let r = %s (1i) { 1i => "one", _ => "other" }' % word),
                    f"parser does not accept `{word}` but the keyword list names it",
                )

    def test_reserved_keywords_are_rejected_as_identifiers(self):
        # Distinguishes the two sets by behaviour rather than by declaration.
        for word in ("let", "fn", "return"):
            with self.subTest(keyword=word):
                self.assertFalse(self._parses("let %s = 1i" % word))

    def test_contextual_keywords_are_still_usable_as_names(self):
        for word in sorted(CONTEXTUAL_KEYWORDS):
            with self.subTest(keyword=word):
                self.assertTrue(
                    self._parses("let %s = 1i" % word),
                    f"`{word}` is reserved; it should be contextual",
                )


# closes: #357
class VsCodeGrammarCoversEveryKeywordTests(unittest.TestCase):
    """The shipped grammar highlights every keyword the language has.

    Skipped when the `nodus-vscode` checkout is not present — this repo's CI does
    not have it. The extension repo runs the same check from `npm run package`,
    which is the step that builds the artifact.
    """

    def setUp(self):
        if not _VSCODE_GRAMMAR.is_file():
            self.skipTest(f"nodus-vscode checkout not present at {_VSCODE_GRAMMAR}")

    def test_every_keyword_is_highlighted(self):
        missing = sorted(ALL_KEYWORDS - words_matched_by(_VSCODE_GRAMMAR))
        self.assertEqual(
            [], missing,
            "keywords the VS Code grammar does not highlight — add them to "
            "syntaxes/nodus.tmLanguage.json and republish the extension",
        )

    def test_the_v4_1_0_keywords_specifically(self):
        # The three this issue is about, named so a regression is unambiguous.
        highlighted = words_matched_by(_VSCODE_GRAMMAR)
        for word in ("match", "break", "continue"):
            with self.subTest(keyword=word):
                self.assertIn(word, highlighted)


class GrammarExtractionTests(unittest.TestCase):
    """The extraction above is what the coverage check trusts; pin its behaviour."""

    def test_reads_alternations_and_single_words(self):
        import tempfile

        grammar = {
            "repository": {
                "keywords": {"patterns": [
                    {"match": "\\b(alpha|beta)\\b"},
                    {"match": "\\bgamma\\b"},
                    {"match": "==|!="},
                ]}
            }
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "g.json"
            path.write_text(json.dumps(grammar), encoding="utf-8")
            self.assertEqual({"alpha", "beta", "gamma"}, words_matched_by(path))


if __name__ == "__main__":
    unittest.main()
