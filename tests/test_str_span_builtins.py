"""`str_span` and `str_span_until`: find where a run of characters ends.

`str_span(s, start, chars)` is the index after the run of characters in `chars`
starting at `start`, like C's `strspn`. `str_span_until(s, start, chars)` is the
index of the first character in `chars` from `start`, like `strcspn`. Each
returns an index, to pair with `substring`.

They exist because the self-hosted lexer (#173) spent most of its instructions
walking source a character at a time. With them it went from 73.1 to 47.4
instructions per character.
"""

import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> list[str]:
    result = NodusRuntime(timeout_ms=None).run_source(source)
    if not result.get("ok"):
        raise AssertionError(str((result.get("error") or {}).get("message") or result))
    return (result.get("stdout") or "").split()


def _error(source: str) -> dict:
    result = NodusRuntime(timeout_ms=None).run_source(source)
    if result.get("ok"):
        raise AssertionError(f"expected an error, got {result.get('stdout')!r}")
    return result.get("error") or {}


class StrSpan(unittest.TestCase):
    def test_the_end_of_a_run(self):
        self.assertEqual(_run('print(str_span("abc123 x", 3i, "0123456789"))'), ["6"])

    def test_no_run_returns_start(self):
        self.assertEqual(_run('print(str_span("abc123", 0i, "0123456789"))'), ["0"])

    def test_a_run_to_the_end_returns_the_length(self):
        self.assertEqual(_run('print(str_span("aaa", 0i, "a"))'), ["3"])

    def test_start_at_the_length_is_allowed_and_returns_it(self):
        self.assertEqual(_run('print(str_span("abc", 3i, "a"))'), ["3"])

    def test_an_empty_set_matches_nothing(self):
        self.assertEqual(_run('print(str_span("abc", 1i, ""))'), ["1"])

    def test_it_counts_characters_not_bytes(self):
        self.assertEqual(_run('print(str_span("ββx", 0i, "β"))'), ["2"])


class StrSpanUntil(unittest.TestCase):
    def test_the_first_character_in_the_set(self):
        self.assertEqual(_run('print(str_span_until("ab cd", 0i, " "))'), ["2"])

    def test_none_found_returns_the_length(self):
        self.assertEqual(_run('print(str_span_until("abc", 0i, "#"))'), ["3"])

    def test_a_character_in_the_set_at_start_returns_start(self):
        self.assertEqual(_run('print(str_span_until("a#c", 1i, "#"))'), ["1"])

    def test_up_to_the_end_of_the_line(self):
        self.assertEqual(_run('print(str_span_until("// note\\nnext", 0i, "\\n"))'), ["7"])


class TheWrappersAndSubstringTogether(unittest.TestCase):
    def test_std_strings_names(self):
        source = (
            'import "std:strings" as strings\n'
            'print(strings.span("abc123", 3i, "0123456789"))\n'
            'print(strings.span_until("abc123", 0i, "1"))\n'
        )
        self.assertEqual(_run(source), ["6", "3"])

    def test_taking_a_token(self):
        source = (
            'let src = "count = 42i"\n'
            'let end = str_span(src, 0i, "abcdefghijklmnopqrstuvwxyz_")\n'
            "print(substring(src, 0i, end))\n"
        )
        self.assertEqual(_run(source), ["count"])


class WhatTheyRefuse(unittest.TestCase):
    def test_a_start_out_of_range(self):
        for call in ('str_span("abc", 4i, "a")', 'str_span("abc", -1i, "a")',
                     'str_span_until("abc", 4i, "a")'):
            with self.subTest(call):
                error = _error(f"print({call})")
                self.assertEqual(error.get("kind"), "index", error)
                self.assertIn("out of range for a string of length 3", error.get("message", ""))

    def test_a_start_that_is_not_an_integer(self):
        for call in ('str_span("abc", 0.5, "a")', 'str_span_until("abc", true, "a")'):
            with self.subTest(call):
                error = _error(f"print({call})")
                self.assertEqual(error.get("kind"), "type", error)
                self.assertIn("start must be an integer", error.get("message", ""))

    def test_a_set_or_subject_that_is_not_a_string(self):
        for call in ('str_span("abc", 0i, 5i)', 'str_span_until(5i, 0i, "a")'):
            with self.subTest(call):
                self.assertEqual(_error(f"print({call})").get("kind"), "type")


if __name__ == "__main__":
    unittest.main()
