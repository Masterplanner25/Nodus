"""Closed-issue test for #998: `std:strings.join` is linear, not quadratic.

`join` built its result one `out + ...` at a time, and each step copied
everything built so far: 300,000 items took 16 s. It now calls `str_join`, a
builtin doing one `sep.join`, and costs a handful of instructions whatever the
length, where it cost about 25 per item.

What `join` returned is kept for every input that worked. Each item goes
through `str()`; a string's characters are its items; with fewer than two items
`sep` is never used, so it is not checked.
"""
import inspect
import os
import re
import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_STRINGS_ND = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "src", "nodus", "stdlib", "strings.nd")


def _run(source, **limits):
    limits.setdefault("timeout_ms", None)
    return NodusRuntime(**limits).run_source(source)


def _out(source, **limits):
    result = _run(source, **limits)
    if not result.get("ok"):
        raise AssertionError((result.get("error") or {}).get("message") or result)
    return result["stdout"]


def _join(items, sep):
    return _out(f'import "std:strings" as s\nprint(s.join({items}, {sep}))\n').rstrip("\n")


def _error(source):
    result = _run(source)
    if result.get("ok"):
        raise AssertionError(f"expected an error, got {result.get('stdout')!r}")
    return result.get("error") or {}


# closes: #998
class JoinCostsTheSameWhateverTheLength(unittest.TestCase):
    def test_a_long_join_fits_a_budget_a_loop_could_not(self):
        # The loop took about 25 instructions an item: 2,500,000 for these.
        out = _out('import "std:strings" as s\nprint(len(s.join(["ab"] * 100000i, ",")))\n',
                   max_steps=500)
        self.assertEqual(out, "299999\n")

    def test_the_builtin_alone(self):
        self.assertEqual(_out('print(str_join(["a", "b", "c"], ", "))\n'), "a, b, c\n")


class JoinReturnsWhatItDid(unittest.TestCase):
    def test_each_item_goes_through_str(self):
        self.assertEqual(_join('[1, 2.5, "x", true, nil, [1, 2], {"a": 1}]', '","'),
                         '1.0,2.5,x,true,nil,[1.0, 2.0],{"a": 1.0}')

    def test_sep_only_between_items(self):
        self.assertEqual(_join('["a", "b"]', '"--"'), "a--b")
        self.assertEqual(_join('["a", "b"]', '""'), "ab")

    def test_an_empty_list_is_the_empty_string(self):
        self.assertEqual(_out('import "std:strings" as s\nprint(s.join([], ",") == "")\n'), "true\n")

    def test_fewer_than_two_items_do_not_check_sep(self):
        self.assertEqual(_join("[]", "nil"), "")
        self.assertEqual(_join('["a"]', "5"), "a")
        self.assertEqual(_join("[7i]", "nil"), "7")

    def test_a_string_s_characters_are_its_items(self):
        self.assertEqual(_join('"abc"', '","'), "a,b,c")

    def test_a_separator_that_is_not_a_string_is_a_type_error(self):
        error = _error('import "std:strings" as s\nprint(s.join(["a", "b"], 1))\n')
        self.assertEqual(error.get("kind"), "type")

    def test_items_that_are_not_a_list_or_string(self):
        error = _error('import "std:strings" as s\nprint(s.join({"a": 1, "b": 2}, ","))\n')
        self.assertEqual(error.get("kind"), "type")
        self.assertIn("must be a list or a string", error.get("message", ""))
        self.assertEqual(_error('import "std:strings" as s\nprint(s.join(5, ","))\n').get("kind"),
                         "type")


class ItDoesNotTakeANameFromAProgram(unittest.TestCase):
    def test_a_program_defining_its_own_str_join_keeps_it(self):
        source = 'fn str_join(a, b) {\n    return "mine"\n}\nprint(str_join([1], ","))\n'
        self.assertEqual(_out(source), "mine\n")

    def test_and_std_strings_join_still_uses_the_builtin(self):
        source = ('import "std:strings" as s\n'
                  'fn str_join(a, b) {\n    return "mine"\n}\n'
                  'print(s.join(["a", "b"], ","))\n')
        self.assertEqual(_out(source), "a,b\n")


class JoinHasNoLoop(unittest.TestCase):
    def test_join_calls_the_builtin_and_does_not_loop(self):
        with open(_STRINGS_ND, encoding="utf-8") as handle:
            text = handle.read()
        body = re.search(r"\nfn join\(items, sep\) \{\n(.*?)\n\}\n", text, re.S)
        self.assertIsNotNone(body)
        self.assertIn("str_join(items, sep)", body.group(1))
        self.assertNotIn("while", body.group(1))
        self.assertNotIn("for ", body.group(1))

    def test_the_builtin_is_one_sep_join(self):
        from nodus.builtins import collections as module
        source = inspect.getsource(module)
        self.assertIn('registry.add("str_join", 2, builtin_str_join)', source)


if __name__ == "__main__":
    unittest.main()
