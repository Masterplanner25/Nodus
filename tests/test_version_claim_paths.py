"""A version claim that names a path must name one that exists.

Most claims assert a *number*: "5.7.1 is current". A few assert a *path* --
`docs/evals/v5.7.1/CREATOR_VALIDATION.md` -- and for those, comparing the
version inside the path checks only half the sentence.

This is not hypothetical. At the 5.7.1 cut that claim went red for naming the
previous cycle, and the obvious one-line fix -- edit the string to 5.7.1 --
would have passed the gate while pointing at a document that had never been
written, because 5.7.1's eval directory held two of its three release
documents. The number would have agreed and the file would not have existed.

`points_at` closes it, and the effect is that a release cannot satisfy the gate
without writing its Gate 10 record -- which CLAUDE.md already required in prose
("All three eval documents are part of the release, not optional write-ups")
and nothing enforced.

The claim entry is read from `tools/version_claims.json` rather than restated
here. A second copy of a pattern is the shape this repo keeps filing issues
about, and a test carrying its own copy would pass while the live one rotted.
"""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # noqa: E402

from tools.nodus_gate.versions_phase import (  # noqa: E402
    _check_claim,
    _latest_eval_version,
)

ROOT = Path(__file__).resolve().parents[1]


def _path_claims() -> list[dict]:
    data = json.loads((ROOT / "tools" / "version_claims.json").read_text(encoding="utf-8"))
    claims = data["claims"] if isinstance(data, dict) and "claims" in data else data
    return [c for c in claims if c.get("points_at")]


def _latest() -> str:
    version, err = _latest_eval_version(ROOT)
    assert version is not None, err
    return version


class PointsAtTests(unittest.TestCase):
    def setUp(self):
        claims = _path_claims()
        self.assertTrue(claims, "no claim declares points_at; the check is inert")
        self.entry = claims[0]
        self.expectations = {
            "nodus_version": _nodus_version(),
            "latest_eval_version": _latest(),
        }

    def test_every_path_claim_points_at_a_document_that_exists(self):
        for entry in _path_claims():
            with self.subTest(file=entry.get("file")):
                status = _check_claim(ROOT, entry, self.expectations)
                self.assertTrue(status.found, status.text)
                self.assertEqual(status.dangling, "")
                self.assertTrue(status.ok, status.text)

    def test_a_dangling_pointer_is_not_ok(self):
        """The negative case, which is the one that matters.

        Without it, `points_at` could be silently inert -- the failure mode of
        three source assertions written in this repo that could not fail.
        """
        entry = dict(self.entry, points_at="docs/evals/v{value}/NO_SUCH_FILE.md")
        status = _check_claim(ROOT, entry, self.expectations)
        self.assertTrue(status.found)
        self.assertTrue(status.dangling.endswith("NO_SUCH_FILE.md"))
        self.assertFalse(status.ok)

    def test_a_matching_version_alone_does_not_pass(self):
        """The exact 5.7.1 near-miss: right number, absent document."""
        entry = dict(self.entry, points_at="docs/evals/v{value}/ABSENT.md")
        status = _check_claim(ROOT, entry, self.expectations)
        self.assertEqual(status.claimed, status.expected)
        self.assertFalse(status.ok)


class EveryReleaseHasItsGate10RecordTests(unittest.TestCase):
    def test_the_newest_eval_directory_has_all_three_documents(self):
        """A release is three eval documents, not one or two."""
        version = _latest()
        directory = ROOT / "docs" / "evals" / f"v{version}"
        for name in (
            "CREATOR_VALIDATION.md",
            "POSTPUBLISH_EVAL.md",
            "STAGE6_DOWNSTREAM_SWEEP.md",
        ):
            with self.subTest(document=name):
                self.assertTrue(
                    (directory / name).is_file(),
                    f"v{version} is missing {name}",
                )


def _nodus_version() -> str:
    text = (ROOT / "src" / "nodus" / "support" / "version.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise AssertionError("no __version__ in version.py")


if __name__ == "__main__":
    unittest.main()
