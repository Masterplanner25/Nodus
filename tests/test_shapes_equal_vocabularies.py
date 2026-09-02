"""`--shapes` species B= : two enumerations of one vocabulary that still agree (#685).

Species B reports a vocabulary that has **already drifted** -- it requires one set
to be a strict subset of the other -- so it is silent on the state that is cheap to
fix and loud only once the bug is reachable. #518 and #487 were both found by a
human after the divergence had shipped.

These tests pin the discriminators, because the detector's value is entirely in its
signal-to-noise: equality alone would report every `{"true","false"}` pair in `src/`
and get the phase switched off.

**The one that matters most is `test_an_alias_is_not_a_finding`.** An alias is the
*fix* for this shape. A detector that still fired after the fix would train people
to silence it in the manifest instead, which is worse than not detecting it.
"""

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # noqa: E402

from tools.nodus_gate.shapes_phase import (  # noqa: E402
    MIN_EQUAL_MEMBERS,
    _name_tokens,
    _species_b_equal,
)


def trees(**sources):
    """`{"a.py": "SRC"}` -> the (rel, tree) pairs the phase consumes."""
    return [(rel, ast.parse(src)) for rel, src in sources.items()]


class EqualVocabularyDetectionTests(unittest.TestCase):
    # closes: #685
    def test_the_motivating_case_fires(self):
        """#685's own example, reconstructed.

        `REHYDRATABLE_RUN_STATUSES` in `store.py` and `_REHYDRATABLE_STATUSES` in
        `runner.py` were two independent definitions of one equal set, and
        `--shapes` reported `0 new` throughout because they agreed. They agreed by
        coincidence: adding a status meant edits in both, and the one you miss is
        silent.
        """
        found = _species_b_equal(trees(**{
            "store.py": (
                'REHYDRATABLE_RUN_STATUSES = frozenset({\n'
                '    "pending", "running", "waiting", "retry_scheduled", "failed",\n'
                '})\n'
            ),
            "runner.py": (
                '_REHYDRATABLE_STATUSES = frozenset({\n'
                '    "pending", "running", "waiting", "retry_scheduled", "failed",\n'
                '})\n'
            ),
        }))
        self.assertEqual(1, len(found), found)
        self.assertEqual("B=", found[0].species)
        self.assertIn("REHYDRATABLE_RUN_STATUSES", found[0].summary)
        self.assertIn("_REHYDRATABLE_STATUSES", found[0].summary)

    # closes: #685
    def test_an_alias_is_not_a_finding(self):
        """The fixed state must be silent, or the fix has no reward.

        This is how the motivating case was actually resolved: one definition, and
        the other name bound to it. The value is an `ast.Name`, not a literal
        collection, so it is never collected.
        """
        self.assertEqual([], _species_b_equal(trees(**{
            "models.py": (
                'REHYDRATABLE_RUN_STATUSES = frozenset({\n'
                '    "pending", "running", "waiting", "retry_scheduled", "failed",\n'
                '})\n'
            ),
            "runner.py": (
                "from models import REHYDRATABLE_RUN_STATUSES\n"
                "_REHYDRATABLE_STATUSES = REHYDRATABLE_RUN_STATUSES\n"
            ),
        })))

    # closes: #685
    def test_unrelated_names_are_not_a_finding(self):
        """Two sets that coincide in members are not two voices on one question.

        Without this the detector reports every pair of equal literals in `src/`.
        """
        self.assertEqual([], _species_b_equal(trees(**{
            "a.py": 'HTTP_IDEMPOTENT = frozenset({"get", "head", "put", "delete"})\n',
            "b.py": 'CACHE_KEYS = frozenset({"get", "head", "put", "delete"})\n',
        })))

    # closes: #685
    def test_a_shared_stem_is_enough_even_across_packages(self):
        """The real pairs differ by a prefix underscore and a dropped word."""
        found = _species_b_equal(trees(**{
            "pkg_a/tool.py": '_VALID_EFFECTS = frozenset({"a", "b", "c", "d"})\n',
            "pkg_b/contracts.py": 'VALID_EFFECTS = frozenset({"a", "b", "c", "d"})\n',
        }))
        self.assertEqual(1, len(found), found)

    # closes: #685
    def test_a_set_below_the_floor_is_not_a_finding(self):
        members = ", ".join(f'"{c}"' for c in "abc")
        self.assertLess(3, MIN_EQUAL_MEMBERS)
        self.assertEqual([], _species_b_equal(trees(**{
            "a.py": f"THING_NAMES = frozenset({{{members}}})\n",
            "b.py": f"_THING_NAMES = frozenset({{{members}}})\n",
        })))

    # closes: #685
    def test_a_local_variable_is_not_a_finding(self):
        """Module scope is the first discriminator: a name bound inside a function
        is a working value, not a declaration that something *is* the set."""
        body = 'def f():\n    VALID_EFFECTS = frozenset({"a", "b", "c", "d"})\n    return VALID_EFFECTS\n'
        self.assertEqual([], _species_b_equal(trees(**{"a.py": body, "b.py": body})))

    # closes: #685
    def test_a_strict_subset_is_left_to_species_b(self):
        """The two detectors must not both report one pair."""
        self.assertEqual([], _species_b_equal(trees(**{
            "a.py": 'STATE_NAMES = frozenset({"a", "b", "c", "d"})\n',
            "b.py": 'STATE_NAMES = frozenset({"a", "b", "c", "d", "e"})\n',
        })))

    # closes: #685
    def test_the_key_does_not_move_when_a_line_does(self):
        """The manifest has to survive an edit above the constant."""
        base = {
            "a.py": '_THING_NAMES = frozenset({"a", "b", "c", "d"})\n',
            "b.py": 'THING_NAMES = frozenset({"a", "b", "c", "d"})\n',
        }
        shifted = dict(base, **{"a.py": "# a new comment\n\n" + base["a.py"]})
        self.assertEqual(
            _species_b_equal(trees(**base))[0].key,
            _species_b_equal(trees(**shifted))[0].key,
        )

    # closes: #685
    def test_a_list_and_a_frozenset_of_the_same_members_still_match(self):
        """Container syntax is not the question; membership is."""
        found = _species_b_equal(trees(**{
            "a.py": 'THING_NAMES = ["a", "b", "c", "d"]\n',
            "b.py": '_THING_NAMES = frozenset({"a", "b", "c", "d"})\n',
        }))
        self.assertEqual(1, len(found), found)


class NameTokenTests(unittest.TestCase):
    # closes: #685
    def test_leading_underscores_and_word_order_do_not_matter(self):
        self.assertEqual(
            _name_tokens("_REHYDRATABLE_STATUSES"),
            _name_tokens("STATUSES_REHYDRATABLE"),
        )

    # closes: #685
    def test_a_dropped_word_leaves_a_subset(self):
        self.assertLess(
            _name_tokens("_REHYDRATABLE_STATUSES"),
            _name_tokens("REHYDRATABLE_RUN_STATUSES"),
        )


if __name__ == "__main__":
    unittest.main()
