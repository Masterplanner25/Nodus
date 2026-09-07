"""Containers at both degenerate ends: empty, and grown large.

Languages break at edges, and the two edges are different failures. An empty
container is where an off-by-one or a "there is always a first element"
assumption surfaces; a large one is where allocation and growth do. Neither end
had much coverage -- `len([])` appears once, in `tests/test_nodus.py:1157`, and
nothing asserted `len({})`, `str("")`, `range(0)`, or iteration over an empty
sequence at all.

**The error cases are the valuable half of the empty end.** `xs[0]` on an empty
list and `m["nope"]` on a map are the two things a program does by accident, and
their messages are what a user reads. Pinning the text means a refactor that
degrades `Missing map key: "nope"` into a Python `KeyError` fails here -- which
is the class of regression #807 was filed for.

Two edges are pinned because they are the ones that surprise people rather than
the ones that are obviously right:

* `str_split("", ",")` returns `[""]`, a list of length **one**, not an empty
  list. Every "split then loop" reader assumes zero.
* `str_contains("abc", "")` is `true`. The empty needle is in every haystack.

**Nothing here asserts on timing.** This box's wall-clock is not a measurement
instrument -- `CLAUDE.md` records suites drifting 7 to 18 minutes with nothing
else running, and `runtime_time_ms()` ticks at ~15.6 ms so a short duration is
noise. The growth tests assert the *result* at size. A genuine quadratic blowup
would surface as the suite hanging, not as a number this file could check; the
throughput question has its own instrument in `tools/benchmark_runtime.py`.

Sizes were chosen by measuring: 1,000 elements costs 23-56 ms per container
kind, and the 10,000-character string 353 ms. That is the budget this file
spends, and it buys the growth path rather than the smoke test.
"""

import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.diagnostics import LangRuntimeError
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None) -> list[str]:
    vm = lang.VM([], {}, code_locs=[], source_path=source_path)
    _loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _loader.load_module_from_source(
            src, module_name=source_path or "<memory>", base_dir=None
        )
    return buf.getvalue().splitlines()


class EmptyContainerTests(unittest.TestCase):
    def test_len_of_every_empty_container_is_zero(self):
        src = """
print(len([]))
print(len({}))
print(len(""))
print(len(range(0)))
print(len(keys({})))
"""
        self.assertEqual(run_program(src), ["0", "0", "0", "0", "0"])

    def test_an_empty_container_prints_as_its_literal(self):
        src = """
print([])
print({})
print(range(0))
print(keys({}))
"""
        self.assertEqual(run_program(src), ["[]", "{}", "[]", "[]"])

    def test_printing_an_empty_string_produces_an_empty_line(self):
        src = """
print(str(""))
"""
        self.assertEqual(run_program(src), [""])

    def test_an_empty_string_interpolates_to_nothing(self):
        src = """
let e = ""
print("[\\(e)]")
"""
        self.assertEqual(run_program(src), ["[]"])

    def test_iterating_an_empty_list_runs_the_body_zero_times(self):
        src = """
let n = 0
for x in [] { n = n + 1 }
print(n)
"""
        self.assertEqual(run_program(src), ["0.0"])

    def test_iterating_the_keys_of_an_empty_map_runs_the_body_zero_times(self):
        src = """
let n = 0
for k in keys({}) { n = n + 1 }
print(n)
"""
        self.assertEqual(run_program(src), ["0.0"])

    def test_has_key_on_an_empty_map_is_false(self):
        src = """
print(has_key({}, "k"))
"""
        self.assertEqual(run_program(src), ["false"])

    def test_json_round_trips_empty_containers(self):
        src = """
import "std:json" as json
print(json.stringify({}))
print(json.stringify([]))
print(len(json.parse("[]")))
"""
        self.assertEqual(run_program(src), ["{}", "[]", "0"])


class EmptyStringEdgeTests(unittest.TestCase):
    """The two that read backwards, pinned because they read backwards."""

    def test_splitting_an_empty_string_yields_one_empty_field(self):
        src = """
let parts = str_split("", ",")
print(len(parts))
print(parts[0] == "")
"""
        self.assertEqual(run_program(src), ["1", "true"])

    def test_every_string_contains_the_empty_string(self):
        src = """
print(str_contains("abc", ""))
"""
        self.assertEqual(run_program(src), ["true"])

    def test_index_of_in_an_empty_string_is_nil(self):
        src = """
print(index_of("", "x"))
"""
        self.assertEqual(run_program(src), ["nil"])

    def test_case_conversion_of_an_empty_string_is_empty(self):
        src = """
print(str_upper("") == "")
print(str_trim("   ") == "")
"""
        self.assertEqual(run_program(src), ["true", "true"])


class EmptyContainerErrorTests(unittest.TestCase):
    """What a program hits by accident, and what it is told.

    The message is the contract here, not just the fact that something was
    raised -- a `LangRuntimeError` carrying a Python `KeyError` repr would pass
    a bare `assertRaises` and be a regression.
    """

    def _error(self, src: str) -> str:
        with self.assertRaises(LangRuntimeError) as caught:
            run_program(src)
        return str(caught.exception)

    def test_indexing_an_empty_list_names_the_index(self):
        self.assertIn(
            "List index out of range: 0",
            self._error("let xs = []\nprint(xs[0])"),
        )

    def test_a_negative_list_index_is_out_of_range(self):
        self.assertIn(
            "List index out of range: -1",
            self._error("let xs = [1, 2]\nprint(xs[-1i])"),
        )

    def test_a_missing_map_key_names_the_key(self):
        self.assertIn(
            'Missing map key: "nope"',
            self._error('let m = {}\nprint(m["nope"])'),
        )

    def test_popping_an_empty_list_says_so(self):
        self.assertIn(
            "Cannot pop from an empty list",
            self._error("let xs = []\nprint(list_pop(xs))"),
        )


class GrowthTests(unittest.TestCase):
    """Build each container kind up to size and check the result, not the clock."""

    def test_a_string_built_one_character_at_a_time(self):
        src = """
let s = ""
let i = 0
while (i < 1000) {
    s = s + "x"
    i = i + 1
}
print(len(s))
print(s[0])
"""
        self.assertEqual(run_program(src), ["1000", "x"])

    def test_a_string_grown_an_order_of_magnitude_further(self):
        """10,000 characters -- the allocation path, not the smoke test."""
        src = """
let s = ""
let i = 0
while (i < 10000) {
    s = s + "x"
    i = i + 1
}
print(len(s))
"""
        self.assertEqual(run_program(src), ["10000"])

    def test_a_list_grown_by_repeated_push(self):
        src = """
let xs = []
let i = 0
while (i < 1000) {
    list_push(xs, i)
    i = i + 1
}
print(len(xs))
print(xs[0])
print(xs[999])
"""
        self.assertEqual(run_program(src), ["1000", "0.0", "999.0"])

    def test_a_map_grown_by_repeated_insert(self):
        """Int loop counter on purpose: `str(0)` is `"0.0"`, so a float one
        builds the key `"k0.0"` and reading back `"k0"` raises. Checking only
        `len(keys(m))` would not have noticed -- the first draft of this test
        did exactly that and passed against the wrong keys."""
        src = """
let m = {}
let i = 0i
while (i < 1000i) {
    m["k" + str(i)] = i
    i = i + 1i
}
print(len(keys(m)))
print(m["k0"])
print(m["k999"])
"""
        self.assertEqual(run_program(src), ["1000", "0", "999"])

    def test_a_grown_list_keeps_every_element_it_was_given(self):
        """Sum the whole thing, so a dropped or duplicated element shows up.

        Checking the ends only would pass on a list that lost its middle.
        """
        src = """
let xs = []
let i = 0
while (i < 1000) {
    list_push(xs, 1)
    i = i + 1
}
let total = 0
let j = 0
while (j < len(xs)) {
    total = total + xs[j]
    j = j + 1
}
print(total)
"""
        self.assertEqual(run_program(src), ["1000.0"])


if __name__ == "__main__":
    unittest.main()
