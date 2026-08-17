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

from tools.check_downstream_constraints import COMPANIONS, admits

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
