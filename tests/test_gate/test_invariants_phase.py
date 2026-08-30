"""Tests for the nodus_gate invariants phase (#179).

Both halves, as the opcode phase's tests put it: that the real repo is clean, and
that each check actually fires when the ledger drifts. A gate that can only pass
is the failure mode the phase exists to end — `EXECUTION_INVARIANTS.md` recorded
which test covered which invariant in prose, in two different places, maintained
by hand, and nothing noticed when that record went stale.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))  # noqa: E402
sys.path.insert(0, str(_ROOT / "src"))  # noqa: E402

from tools.nodus_gate.invariants_phase import (  # noqa: E402
    _DOC,
    _MANIFEST,
    cited_tests_by_invariant,
    parse_documented_invariants,
    run_invariants_phase,
)

_DOC_PATH = _ROOT / _DOC
_MANIFEST_PATH = _ROOT / _MANIFEST


def _doc_text() -> str:
    return _DOC_PATH.read_text(encoding="utf-8")


class ParserTests(unittest.TestCase):
    def test_every_invariant_heading_is_found(self):
        documented = parse_documented_invariants(_doc_text())
        self.assertEqual(29, len(documented))
        for expected in ("I-VM-01", "I-VM-06", "I-SAND-03", "I-WFLOW-07", "I-CORO-02"):
            self.assertIn(expected, documented)

    def test_titles_are_captured(self):
        documented = parse_documented_invariants(_doc_text())
        self.assertIn("finally", documented["I-VM-06"])

    def test_the_last_invariant_does_not_swallow_the_coverage_section(self):
        """The parse bug this phase was written with, kept as a test.

        Bounding a section on the next `###` alone lets the final invariant run
        to end of file and absorb §8 — which silently credits it with every test
        path in the coverage list. It reads as a pass and is not one.
        """
        cited = cited_tests_by_invariant(_doc_text())
        self.assertEqual(
            set(), cited.get("I-CORO-02", set()),
            "the last invariant absorbed the coverage section's test paths",
        )


# closes: #179
class RealRepoTests(unittest.TestCase):
    def test_the_ledger_is_currently_honest(self):
        result = run_invariants_phase(str(_ROOT))
        self.assertIsNone(result.error)
        self.assertEqual([], [f.message for f in result.findings])

    def test_every_documented_invariant_is_classified(self):
        result = run_invariants_phase(str(_ROOT))
        self.assertEqual(29, result.documented)
        self.assertEqual(29, result.with_tests + result.unrecorded)

    def test_unrecorded_is_reported_rather_than_hidden(self):
        """The count is the point. 23 of 29 invariants have no test tied to
        them, and a phase that reported only failures would render that as
        silence."""
        result = run_invariants_phase(str(_ROOT))
        self.assertGreater(result.unrecorded, 0)
        self.assertGreater(result.with_tests, 0)


# closes: #179
class DriftDetectionTests(unittest.TestCase):
    """Each check must fire when its record drifts, not merely pass when clean."""

    def _fixture(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / _DOC).parent.mkdir(parents=True, exist_ok=True)
        (root / _MANIFEST).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_DOC_PATH, root / _DOC)
        shutil.copyfile(_MANIFEST_PATH, root / _MANIFEST)
        # The ledger names real test files; copy the ones it points at.
        manifest = json.loads((root / _MANIFEST).read_text(encoding="utf-8"))
        for entry in manifest["invariants"].values():
            for rel in entry.get("tests", []) or []:
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text("# stand-in\n", encoding="utf-8")
        return root

    def _write_manifest(self, root: Path, manifest: dict) -> None:
        (root / _MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _manifest(self, root: Path) -> dict:
        return json.loads((root / _MANIFEST).read_text(encoding="utf-8"))

    def test_a_clean_copy_passes(self):
        result = run_invariants_phase(str(self._fixture()))
        self.assertEqual([], [f.message for f in result.findings], result.error)

    def test_a_new_invariant_with_no_ledger_entry_fails(self):
        """The check that makes this phase worth having: adding an invariant to
        the document is not free — it has to be classified."""
        root = self._fixture()
        doc = (root / _DOC).read_text(encoding="utf-8")
        doc = doc.replace(
            "### I-CORO-01:",
            "### I-NEW-01: A newly documented invariant\n\nBody.\n\n### I-CORO-01:",
            1,
        )
        (root / _DOC).write_text(doc, encoding="utf-8")

        result = run_invariants_phase(str(root))
        self.assertTrue(any("no entry in the coverage ledger" in f.message
                            for f in result.findings), [f.message for f in result.findings])
        self.assertIn("I-NEW-01", " ".join(f.detail for f in result.findings))

    def test_a_ledger_entry_for_a_removed_invariant_fails(self):
        root = self._fixture()
        manifest = self._manifest(root)
        manifest["invariants"]["I-GONE-09"] = {"title": "removed", "tests": [],
                                               "reason": "stale entry"}
        self._write_manifest(root, manifest)

        result = run_invariants_phase(str(root))
        self.assertTrue(any("no longer has" in f.message for f in result.findings),
                        [f.message for f in result.findings])
        self.assertIn("I-GONE-09", " ".join(f.detail for f in result.findings))

    def test_a_named_test_that_does_not_exist_fails(self):
        """The rename case — the reason a hand-maintained citation rots."""
        root = self._fixture()
        manifest = self._manifest(root)
        manifest["invariants"]["I-VM-06"]["tests"] = ["tests/test_renamed_away.py"]
        self._write_manifest(root, manifest)

        result = run_invariants_phase(str(root))
        self.assertTrue(any("do not exist" in f.message for f in result.findings),
                        [f.message for f in result.findings])
        self.assertIn("test_renamed_away.py", " ".join(f.detail for f in result.findings))

    def test_an_uncovered_invariant_with_no_reason_fails(self):
        """`unrecorded` has to be a decision, not an omission."""
        root = self._fixture()
        manifest = self._manifest(root)
        manifest["invariants"]["I-VM-01"] = {"title": "t", "tests": []}
        self._write_manifest(root, manifest)

        result = run_invariants_phase(str(root))
        self.assertTrue(any("no stated reason" in f.message for f in result.findings),
                        [f.message for f in result.findings])
        self.assertIn("I-VM-01", " ".join(f.detail for f in result.findings))

    def test_a_blank_reason_does_not_satisfy_the_check(self):
        root = self._fixture()
        manifest = self._manifest(root)
        manifest["invariants"]["I-VM-01"] = {"title": "t", "tests": [], "reason": "   "}
        self._write_manifest(root, manifest)

        result = run_invariants_phase(str(root))
        self.assertTrue(any("no stated reason" in f.message for f in result.findings))

    def test_a_citation_the_ledger_does_not_know_is_advisory_not_fatal(self):
        """Prose may name a test in passing. That is how the two drift apart, so
        it is reported — but it does not fail a build."""
        root = self._fixture()
        manifest = self._manifest(root)
        manifest["invariants"]["I-VM-06"]["tests"] = []
        manifest["invariants"]["I-VM-06"]["reason"] = "deliberately emptied for this test"
        self._write_manifest(root, manifest)

        result = run_invariants_phase(str(root))
        self.assertEqual([], [f.message for f in result.findings])
        self.assertTrue(any("test_finally_rethrow.py" in a.message for a in result.advisories),
                        [a.message for a in result.advisories])


# closes: #179
class UnreadableInputTests(unittest.TestCase):
    """A check may not pass by being unable to run — the rule the shapes and
    consumers phases already follow."""

    def test_a_missing_manifest_is_an_error(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / _DOC).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_DOC_PATH, root / _DOC)

        result = run_invariants_phase(str(root))
        self.assertIsNotNone(result.error)
        self.assertIn("invariant_coverage.json", result.error)

    def test_a_malformed_manifest_is_an_error(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / _DOC).parent.mkdir(parents=True, exist_ok=True)
        (root / _MANIFEST).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_DOC_PATH, root / _DOC)
        (root / _MANIFEST).write_text('{"invariants": []}', encoding="utf-8")

        result = run_invariants_phase(str(root))
        self.assertIsNotNone(result.error)

    def test_a_missing_document_is_an_error(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        result = run_invariants_phase(str(root))
        self.assertIsNotNone(result.error)
        self.assertIn("EXECUTION_INVARIANTS.md", result.error)


if __name__ == "__main__":
    unittest.main()
