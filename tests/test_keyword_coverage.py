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
    COMPENSATION_KEYWORDS,
    EXPRESSION_KEYWORDS,
    EXTERN_KEYWORDS,
    GOAL_KEYWORDS,
    STEP_GUARD_KEYWORDS,
    STEP_MAP_KEYWORDS,
    WORKFLOW_BODY_KEYWORDS,
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
        self.assertEqual(
            LOOP_CONTROL_KEYWORDS
            | EXPRESSION_KEYWORDS
            | GOAL_KEYWORDS
            | STEP_GUARD_KEYWORDS
            | STEP_MAP_KEYWORDS
            | WORKFLOW_BODY_KEYWORDS
            | EXTERN_KEYWORDS
            | COMPENSATION_KEYWORDS,
            CONTEXTUAL_KEYWORDS,
        )

    # closes: #480
    def test_the_parser_recognises_no_word_the_list_does_not_name(self):
        """The missing direction, which is the one that fails (#480).

        Every check here ran list -> parser: each word the list names must
        parse. Nothing ran parser -> list, so a contextual keyword introduced as
        a bare string literal was invisible -- exactly the state #357 fixed and
        exactly how `each` shipped. It was caught by a release gate noticing the
        VS Code fingerprint had *not* moved, which is two steps too late: the
        grammar would have rendered `each` as a plain identifier, which is the
        two-release regression this file exists to prevent.

        Reads the parser's source, because that is where the drift lives. A
        behavioural test cannot see the difference between a word matched from a
        named set and the same word matched from a literal.
        """
        source = Path(_REPO_ROOT / "src/nodus/frontend/parser.py").read_text(encoding="utf-8")
        # `self.peek().val == "word"` and `self.peek(N).val == "word"`.
        literals = set(re.findall(r"""\.val\s*==\s*["'](\w+)["']""", source))
        # `_` is the `match` wildcard: a pattern token, not a word the language
        # reserves, and nothing should highlight it as one.
        exempt = {"_"}
        unnamed = sorted(w for w in literals if w not in ALL_KEYWORDS and w not in exempt)
        self.assertEqual(
            [], unnamed,
            f"parser.py matches {unnamed} as bare token text, but "
            f"lexer.ALL_KEYWORDS does not name them. Editor grammars, docs and "
            f"`nodus_gate --consumers` all read that list, so a word missing "
            f"from it ships unhighlighted.",
        )


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

    # closes: #717
    def test_contextual_keywords_are_still_usable_as_identifiers(self):
        """Every contextual keyword can be bound *and read back*.

        This replaces two tests that asked the same question and disagreed. The
        narrow one covered `GOAL_KEYWORDS` (5 words) and did bind-then-read; the
        wide one covered all of `CONTEXTUAL_KEYWORDS` and only bound, never
        reading the variable back. So the wider test was the weaker one -- and it
        was the wider one whose name stated the property, which is why `match`
        passed it for four minor releases while every read of `match` was a
        syntax error (#717).

        One question, one test. The read is the half that matters: binding is
        what the parser does with a `let` target, and a soft keyword breaks in
        expression position, not in declaration position.
        """
        for word in sorted(CONTEXTUAL_KEYWORDS):
            with self.subTest(keyword=word):
                self.assertTrue(
                    self._parses("let %s = 1i\nprint(%s)" % (word, word)),
                    f"`{word}` is contextual but cannot be read as an "
                    f"identifier; it is reserved in practice",
                )

    # closes: #717
    def test_match_is_readable_as_an_identifier_in_every_position(self):
        """`match` is the only contextual keyword parsed at expression position.

        The generic test above covers one read shape. These are the positions the
        #717 report listed, each of which was a syntax error.
        """
        for expr in (
            "print(match)",
            "let y = match + 1i",
            'print("\\(match)")',
            "let l = [match, 2i]",
            "match = 9i",
            "if (match == 7i) { print(1i) }",
        ):
            with self.subTest(expr=expr):
                self.assertTrue(
                    self._parses("let match = 7i\n%s" % expr),
                    f"`match` should be readable in `{expr}`",
                )

    # closes: #717
    def test_match_expressions_still_parse(self):
        """The fix must not narrow the construct it is disambiguating from.

        A deny-list of value-following tokens can only divert programs that
        raised before, so these cannot regress -- but a later change to
        `_VALUE_FOLLOWERS` could, and this is what would catch it.
        """
        for src in (
            'let r = match 1i { 1i => "one", _ => "other" }',
            'let x = 2i\nlet r = match x { 1i => "one", _ => "other" }',
            'let r = match (1i + 1i) { 2i => "two", _ => "o" }',
            'let r = match "a" { "a" => "A", _ => "z" }',
            'let r = match [1i] { _ => "z" }',
            'let r = match -1i { _ => "z" }',
        ):
            with self.subTest(src=src):
                self.assertTrue(self._parses(src), f"match expression broke: {src}")

    # closes: #717
    def test_the_residual_ambiguity_is_where_it_is_documented(self):
        """Four follower tokens can also begin a scrutinee, so `match` still wins.

        Pinned rather than hidden. `-`, `(`, `[` and `!` each start a valid
        scrutinee (unary minus, a parenthesised or list scrutinee, unary not), so
        one token of lookahead cannot separate `match - 1i` from `match -1i {…}`.
        Resolving these needs unbounded lookahead; reserving the word would break
        the contract #717 exists to enforce. If a later change makes one of these
        work, that is an improvement -- update this test deliberately.
        """
        for expr in ("let y = match - 1i", "let y = match[0i]", "let y = match(1i)"):
            with self.subTest(expr=expr):
                self.assertFalse(
                    self._parses("let match = 7i\n%s" % expr),
                    f"`{expr}` now parses; the ambiguity note in parser.py "
                    f"`_VALUE_FOLLOWERS` needs updating",
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
