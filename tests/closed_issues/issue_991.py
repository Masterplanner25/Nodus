"""Closed-issue test for #991: COMPATIBILITY.md's timeline is frozen, and says so.

The timeline was meant to get an entry each release. From 5.0.1 on it got none,
so v5.0.0 stayed marked "current" for 22 releases, and an entry for a change
that shipped in 5.2.0 stayed labelled "Unreleased" for fifteen. The decision was
to stop keeping it rather than backfill it. `CHANGELOG.md` is the release
history, and the *Deprecated* section above the timeline is kept current.

A frozen timeline goes wrong in one way: something adds to it again. The old
release skill told every release to add a `(current)` entry, and that
instruction is what kept the drift going. So this checks three things. No entry
claims to be current or unreleased, the section says it ends, and the release
skill no longer tells anyone to add an entry.
"""
import re
import unittest
from pathlib import Path

_ROOT = Path(__file__).parents[2]
_DOC = _ROOT / "docs" / "governance" / "COMPATIBILITY.md"
_SKILL = _ROOT / ".claude" / "commands" / "release-prep.md"


def _timeline() -> str:
    text = _DOC.read_text(encoding="utf-8")
    start = text.index("## Timeline")
    end = text.index("\n## ", start + 1)
    return text[start:end]


# closes: #991
class TheTimelineIsFrozen(unittest.TestCase):
    def test_no_entry_claims_to_be_current_or_unreleased(self):
        entries = [line for line in _timeline().splitlines() if line.startswith("- ")]
        self.assertTrue(entries, "found no timeline entries; the parse is wrong")
        for line in entries:
            with self.subTest(line[:60]):
                self.assertNotRegex(line, r"\bcurrent\)")
                self.assertNotRegex(line, r"^- \*\*Unreleased")

    def test_the_section_says_where_it_ends(self):
        heading = _timeline().splitlines()[0]
        last = re.findall(r"^- \*\*(v[\d.]+)", _timeline(), re.M)[-1]
        self.assertIn(f"ends at {last}", heading)

    def test_the_release_skill_does_not_ask_for_an_entry(self):
        skill = _SKILL.read_text(encoding="utf-8")
        self.assertNotIn("with `(current)`", skill)
        self.assertIn("Do not add a\ntimeline entry", skill)


if __name__ == "__main__":
    unittest.main()
