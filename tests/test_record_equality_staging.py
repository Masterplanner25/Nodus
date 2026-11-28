"""#545: record `==` is structural since 6.0.0.

Two records are equal when their `kind` and their `fields` are, recursing with
the equality lists and maps use. 5.x compared records by identity and warned
once per process when a comparison's answer was about to change; the flip
deleted the warning. (The file keeps its old name so the closes-marker and its
history stay in one place.)

Decision record: docs/design/v6/00-record-equality.md.
"""

import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.vm.types import Record, structural_eq  # noqa: E402


# closes: #545
class TestStructuralEquality(unittest.TestCase):
    def _compare(self, a, b):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = a == b
        return result, err.getvalue()

    def test_equal_fields_compare_true_and_silently(self):
        result, err = self._compare(Record({"x": 1}), Record({"x": 1}))
        self.assertTrue(result)
        # The 5.x divergence warning is gone, not merely suppressed.
        self.assertEqual(err, "")

    def test_not_equal_is_the_negation(self):
        self.assertFalse(Record({"x": 1}) != Record({"x": 1}))
        self.assertTrue(Record({"x": 1}) != Record({"x": 2}))

    def test_same_record_is_true(self):
        r = Record({"x": 1})
        self.assertTrue(r == r)

    def test_different_fields_are_false(self):
        self.assertFalse(Record({"x": 1}) == Record({"x": 2}))
        self.assertFalse(Record({"x": 1}) == Record({"x": 1, "y": 2}))

    def test_nested_record_in_map_and_list(self):
        # The comparison propagates outward, as it used to propagate `false`.
        self.assertTrue({"r": Record({"x": 1})} == {"r": Record({"x": 1})})
        self.assertTrue([Record({"x": 1})] == [Record({"x": 1})])

    def test_datetime_carveout_compares_by_instant(self):
        d1 = Record({"epoch_ms": 5, "zone": "UTC"}, kind="datetime")
        d2 = Record({"epoch_ms": 5, "zone": "America/New_York"}, kind="datetime")
        self.assertTrue(d1 == d2)

    def test_records_are_unhashable(self):
        # Mutable and compared by value, so a hash could not stay consistent.
        # Records were never valid map keys at the language surface.
        with self.assertRaises(TypeError):
            hash(Record({"x": 1}))

    def test_kind_must_match(self):
        self.assertFalse(Record({"x": 1}) == Record({"x": 1}, kind="other"))

    def test_fields_recurse(self):
        self.assertTrue(
            Record({"x": [1, {"y": Record({"z": 2})}]})
            == Record({"x": [1, {"y": Record({"z": 2})}]})
        )

    def test_int_float_leaves_coerce_like_nested_maps_do(self):
        self.assertTrue(structural_eq(Record({"x": 1}), Record({"x": 1.0})))

    def test_function_valued_fields_compare_by_identity(self):
        method = object()
        self.assertTrue(Record({"f": method}) == Record({"f": method}))
        self.assertFalse(Record({"f": object()}) == Record({"f": object()}))

    def test_record_never_equals_a_map(self):
        self.assertFalse(Record({"x": 1}) == {"x": 1})

    def test_cyclic_records_terminate(self):
        # `r.self = r` is legal. A pair met again on the comparison path is
        # taken as equal (the coinductive reading).
        r1 = Record({"x": 1})
        r1.fields["self"] = r1
        r2 = Record({"x": 1})
        r2.fields["self"] = r2
        self.assertTrue(r1 == r2)
        r3 = Record({"x": 2})
        r3.fields["self"] = r3
        self.assertFalse(r1 == r3)


class TestFromNodusCode(unittest.TestCase):
    """The semantics must hold for `.nd` code, not only for Python `==`."""

    def test_run_source_comparison(self):
        from nodus.runtime.embedding import NodusRuntime

        rt = NodusRuntime()
        result = rt.run_source(
            "fn main() {\n"
            "  let a = record { x: 1i, y: [1i, 2i] }\n"
            "  print(a == record { x: 1i, y: [1i, 2i] })\n"
            "  print(a != record { x: 2i, y: [1i, 2i] })\n"
            "  print({\"r\": a} == {\"r\": record { x: 1i, y: [1i, 2i] }})\n"
            "}"
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["stdout"], "true\ntrue\ntrue\n")
        self.assertNotIn("#545", result["stderr"])


if __name__ == "__main__":
    unittest.main()
