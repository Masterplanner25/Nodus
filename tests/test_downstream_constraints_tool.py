"""The Stage 6 constraint check, tested against the metadata that fooled a human.

`tools/check_downstream_constraints.py` exists because the v5.0.0 Stage 6 sweep
read six ranges by eye, dropped the upper bound on five of them, and recorded
"no companion caps its range" when in fact only one of the six could install
alongside 5.0.0.

A tool written after an incident is worth only as much as its behaviour on the
incident's actual inputs. These are the exact `Requires-Dist` strings that were
published at the time, so this asserts the check would have failed the sweep.

No network: `admits()` is pure, and that is the part that was wrong.
"""

import unittest

from tools.check_downstream_constraints import (
    COMPANIONS,
    UNPUBLISHED_COMPANIONS,
    admits,
)

# Verbatim from PyPI on 2026-08-17, before the companions were republished.
PUBLISHED_AT_V500_RELEASE = {
    "nodus-mcp": "nodus-lang<5.0.0,>=4.0.0",
    "nodus-mcp-server": "nodus-lang<5.0.0,>=4.0.5",
    "nodus-extension": "nodus-lang<5.0.0,>=4.0.0",
    "nodus-sdk": "nodus-lang<5.0.0,>=4.0.0",
    "nodus-native-memory-engine": 'nodus-lang<5.0.0,>=4.0.0; extra == "nodus"',
    "nodus-jupyter": "nodus-lang>=4.0.0",
}


class TestAdmits(unittest.TestCase):
    # closes: #445
    def test_the_capped_companions_are_reported_as_blocking_5_0_0(self):
        """The five that were mis-transcribed. Each must come back False."""
        for name in (
            "nodus-mcp",
            "nodus-mcp-server",
            "nodus-extension",
            "nodus-sdk",
            "nodus-native-memory-engine",
        ):
            with self.subTest(companion=name):
                self.assertFalse(
                    admits(PUBLISHED_AT_V500_RELEASE[name], "5.0.0"),
                    f"{name}'s published cap must be detected as blocking 5.0.0",
                )

    def test_the_uncapped_companion_is_reported_as_fine(self):
        """nodus-jupyter genuinely did admit 5.0.0 — the check must not cry wolf."""
        self.assertTrue(admits(PUBLISHED_AT_V500_RELEASE["nodus-jupyter"], "5.0.0"))

    def test_the_same_caps_still_admit_the_4_x_line(self):
        """The caps were not wrong about 4.x; they were wrong about 5.x. A check
        that flagged them on 4.2.0 too would be noise."""
        for name, req in PUBLISHED_AT_V500_RELEASE.items():
            with self.subTest(companion=name):
                self.assertTrue(admits(req, "4.2.0"))

    def test_an_environment_marker_does_not_defeat_the_check(self):
        """nodus-native-memory-engine declares its dep on an optional extra, so its
        requirement string carries a marker. The specifier is what matters."""
        self.assertFalse(
            admits('nodus-lang<5.0.0,>=4.0.0; extra == "nodus"', "5.0.0")
        )

    def test_prereleases_are_judged_by_the_specifier(self):
        """packaging excludes prereleases by default, which would report a release
        candidate as blocked by a range that plainly admits it."""
        self.assertTrue(admits("nodus-lang>=4.0.0", "5.1.0rc1"))
        self.assertFalse(admits("nodus-lang<5.0.0,>=4.0.0", "5.1.0rc1"))

    def test_companion_list_covers_every_capped_package(self):
        """A package missing from COMPANIONS is invisible to the check."""
        for name in PUBLISHED_AT_V500_RELEASE:
            self.assertIn(name, COMPANIONS)


if __name__ == "__main__":
    unittest.main()


# closes: #93
class UnpublishedCompanionRegisterTests(unittest.TestCase):
    """A companion's nodus-lang range is registered the day it is written.

    The alternative is remembering on the day it is published, and a range
    nobody is checking is what made v5.0.0 unadoptable for a day: five of six
    companions capped `<5.0.0`, the Stage 6 sweep transcribed the ranges by eye
    and dropped the caps, and a downstream team found it rather than us.

    Registering before publication costs one dict entry and makes the gap show
    up on every run instead of living in somebody's head.
    """

    def test_every_unpublished_entry_states_a_floor_and_a_reason(self):
        for name, entry in UNPUBLISHED_COMPANIONS.items():
            with self.subTest(companion=name):
                self.assertTrue(entry.get("floor"), f"{name} declares no floor")
                self.assertTrue(
                    str(entry.get("why", "")).strip(),
                    f"{name} has no stated reason -- an entry without one is a name "
                    f"nobody can act on",
                )

    def test_no_name_is_in_both_registers(self):
        """A published companion is checked against the index; an unpublished one
        is reported. Being in both would mean the fetch is attempted for a
        package that does not exist, which exits non-zero on a question that was
        never real."""
        overlap = set(COMPANIONS) & set(UNPUBLISHED_COMPANIONS)
        self.assertEqual(set(), overlap)

    def test_an_unpublished_floor_is_a_valid_version(self):
        from packaging.version import Version

        for name, entry in UNPUBLISHED_COMPANIONS.items():
            with self.subTest(companion=name):
                Version(entry["floor"])          # raises if it is not one

    def test_no_unpublished_companion_caps_nodus_lang(self):
        """The policy decided 2026-08-17: companions float. A cap turns every
        major into a two-repo release train with consumers frozen between."""
        for name, entry in UNPUBLISHED_COMPANIONS.items():
            with self.subTest(companion=name):
                self.assertNotIn("<", str(entry.get("floor", "")))
