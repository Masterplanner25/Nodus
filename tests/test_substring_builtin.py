"""`substring(s, start, end)`: part of a string in one call.

Before it, Nodus could only take a string apart one character at a time
(`s[i]`). The bounds follow `s[i]`: an int or a whole-number float, and anything
out of range is an error, never clamped.
"""

import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(source: str) -> str:
    result = NodusRuntime(timeout_ms=None).run_source(source)
    if not result.get("ok"):
        raise AssertionError(str((result.get("error") or {}).get("message") or result))
    return (result.get("stdout") or "").strip()


def _error(source: str) -> dict:
    result = NodusRuntime(timeout_ms=None).run_source(source)
    if result.get("ok"):
        raise AssertionError(f"expected an error, got {result.get('stdout')!r}")
    return result.get("error") or {}


class WhatItReturns(unittest.TestCase):
    def test_a_range(self):
        self.assertEqual(_run('print(substring("hello world", 0i, 5i))'), "hello")

    def test_end_defaults_to_the_length(self):
        self.assertEqual(_run('print(substring("hello world", 6i))'), "world")

    def test_an_empty_range_is_the_empty_string(self):
        self.assertEqual(_run('print(substring("abc", 2i, 2i) == "")'), "true")
        self.assertEqual(_run('print(substring("abc", 3i) == "")'), "true")

    def test_it_counts_characters_not_bytes(self):
        self.assertEqual(_run('print(substring("aβc", 1i, 2i))'), "β")

    def test_a_whole_number_float_is_accepted_as_s_i_accepts_it(self):
        self.assertEqual(_run('print(substring("hello", 1.0, 3))'), "el")

    def test_the_std_strings_wrapper_and_the_alias(self):
        source = (
            'import "std:strings" as strings\n'
            'print(strings.substring("hello", 1i, 3i))\n'
            'print(strings.substring("hello", 3i))\n'
            'print(str_substring("hello", 0i, 1i))\n'
        )
        self.assertEqual(_run(source).split(), ["el", "lo", "h"])


class WhatItRefuses(unittest.TestCase):
    def _assert_index_error(self, call: str):
        error = _error(f"print({call})")
        self.assertEqual(error.get("kind"), "index", error)
        self.assertIn("out of range for a string of length 3", error.get("message", ""))

    def test_a_negative_start(self):
        self._assert_index_error('substring("abc", -1i, 2i)')

    def test_start_after_end(self):
        self._assert_index_error('substring("abc", 2i, 1i)')

    def test_end_past_the_length(self):
        self._assert_index_error('substring("abc", 0i, 4i)')

    def test_a_start_past_the_length_with_no_end(self):
        self._assert_index_error('substring("abc", 4i)')

    def test_a_fractional_or_boolean_bound(self):
        for call in ('substring("abc", 0.5, 1i)', 'substring("abc", true, 1i)',
                     'substring("abc", 0i, "2")'):
            with self.subTest(call):
                error = _error(f"print({call})")
                self.assertEqual(error.get("kind"), "type", error)
                self.assertIn("must be an integer", error.get("message", ""))

    def test_a_value_that_is_not_a_string(self):
        error = _error("print(substring(5i, 0i, 1i))")
        self.assertEqual(error.get("kind"), "type", error)


class ItDoesNotTakeANameFromAProgram(unittest.TestCase):
    def test_a_program_defining_its_own_substring_keeps_it(self):
        # A program written before this builtin existed may define the name.
        source = 'fn substring(s, a, b) {\n    return "mine"\n}\nprint(substring("abc", 0i, 1i))\n'
        self.assertEqual(_run(source), "mine")

    def test_a_parameter_or_local_named_substring_still_works(self):
        source = (
            "fn f(substring) {\n"
            "    let n = len(substring)\n"
            "    return n\n"
            "}\n"
            'print(f("abcd"))\n'
        )
        self.assertEqual(_run(source), "4")


if __name__ == "__main__":
    unittest.main()
