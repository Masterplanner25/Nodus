"""#545 staging: record `==` flips from identity to structural at 6.0.0.

Until the flip, `Record.__eq__` still answers by identity, and the one
observable divergence -- two distinct records that field-by-field comparison
calls equal -- warns once per process. These tests pin the staging behaviour;
the 6.0.0 flip PR rewrites them into tests of structural equality itself and
keeps the closes-marker for #545 on the rewritten tests. (This docstring once
had to avoid the marker's literal spelling — the gate's scanner matched it
anywhere in the file and bound the issue to whatever `def` followed. #562
made the scan comment-only, so prose is safe now.)

Decision record: docs/design/v6/00-record-equality.md.
"""

import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

import nodus.vm.types as vm_types  # noqa: E402
from nodus.vm.types import Record, structural_eq  # noqa: E402


def _fresh_warn_state():
    vm_types._STRUCTURAL_EQ_CHANGE_WARNED = False


# closes: #545
class TestDivergenceWarning(unittest.TestCase):
    def setUp(self):
        _fresh_warn_state()
        self.addCleanup(_fresh_warn_state)

    def _compare(self, a, b):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = a == b
        return result, err.getvalue()

    def test_equal_fields_compare_false_and_warn_once(self):
        r1 = Record({"x": 1})
        r2 = Record({"x": 1})
        result, err = self._compare(r1, r2)
        self.assertFalse(result)
        self.assertIn("6.0.0", err)
        self.assertIn("#545", err)
        # Once per process: the second divergent comparison is silent.
        result, err = self._compare(r1, r2)
        self.assertFalse(result)
        self.assertEqual(err, "")

    def test_same_record_is_true_and_silent(self):
        r = Record({"x": 1})
        result, err = self._compare(r, r)
        self.assertTrue(result)
        self.assertEqual(err, "")

    def test_different_fields_are_false_and_silent(self):
        result, err = self._compare(Record({"x": 1}), Record({"x": 2}))
        self.assertFalse(result)
        self.assertEqual(err, "")

    def test_nested_record_in_map_warns(self):
        # The divergence propagates outward: a map holding a record compares
        # false for the same reason the record does, and will flip with it.
        m1 = {"r": Record({"x": 1})}
        m2 = {"r": Record({"x": 1})}
        result, err = self._compare(m1, m2)
        self.assertFalse(result)
        self.assertIn("#545", err)

    def test_datetime_carveout_still_true_and_silent(self):
        d1 = Record({"epoch_ms": 5, "zone": "UTC"}, kind="datetime")
        d2 = Record({"epoch_ms": 5, "zone": "America/New_York"}, kind="datetime")
        result, err = self._compare(d1, d2)
        self.assertTrue(result)
        self.assertEqual(err, "")


class TestStructuralPreview(unittest.TestCase):
    """`structural_eq` is the 6.0.0 semantics; pin its sub-decisions now."""

    def test_kind_must_match(self):
        self.assertFalse(
            structural_eq(Record({"x": 1}), Record({"x": 1}, kind="other"))
        )

    def test_fields_recurse(self):
        self.assertTrue(
            structural_eq(
                Record({"x": [1, {"y": Record({"z": 2})}]}),
                Record({"x": [1, {"y": Record({"z": 2})}]}),
            )
        )

    def test_int_float_leaves_coerce_like_nested_maps_do(self):
        self.assertTrue(structural_eq(Record({"x": 1}), Record({"x": 1.0})))

    def test_function_valued_fields_compare_by_identity(self):
        method = object()
        self.assertTrue(
            structural_eq(Record({"f": method}), Record({"f": method}))
        )
        self.assertFalse(
            structural_eq(Record({"f": object()}), Record({"f": object()}))
        )

    def test_datetime_compares_by_instant_not_by_zone(self):
        d1 = Record({"epoch_ms": 5, "zone": "UTC"}, kind="datetime")
        d2 = Record({"epoch_ms": 5, "zone": "America/New_York"}, kind="datetime")
        self.assertTrue(structural_eq(d1, d2))

    def test_record_never_equals_a_map(self):
        self.assertFalse(structural_eq(Record({"x": 1}), {"x": 1}))

    def test_cyclic_records_terminate(self):
        # `r.self = r` is legal; today identity answers instantly, so the
        # staging check must not recurse forever. A pair met again on the
        # comparison path is taken as equal (the coinductive reading).
        r1 = Record({"x": 1})
        r1.fields["self"] = r1
        r2 = Record({"x": 1})
        r2.fields["self"] = r2
        self.assertTrue(structural_eq(r1, r2))
        r3 = Record({"x": 2})
        r3.fields["self"] = r3
        self.assertFalse(structural_eq(r1, r3))


class TestWarningReachesEmbeddedStderr(unittest.TestCase):
    """The warning must surface from `.nd` code, not only from Python `==`."""

    def setUp(self):
        _fresh_warn_state()
        self.addCleanup(_fresh_warn_state)

    def test_run_source_comparison_warns_on_stderr(self):
        from nodus.runtime.embedding import NodusRuntime

        rt = NodusRuntime()
        result = rt.run_source(
            "fn main() { print(record { x: 1i } == record { x: 1i }) }"
        )
        # `run_source` captures the guest's stderr into the result map, so the
        # warning surfaces where an embedder actually looks.
        self.assertTrue(result["ok"])
        # Proof the comparison ran and still answers by identity in 5.x:
        self.assertEqual(result["stdout"], "false\n")
        self.assertIn("#545", result["stderr"])
        self.assertIn("6.0.0", result["stderr"])


if __name__ == "__main__":
    unittest.main()
