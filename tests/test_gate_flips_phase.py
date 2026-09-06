"""The staged-flip register agrees with the code, in both directions.

A staged flip is a promise made to a user *now* about a release that has not
happened. Five of them live in `src/` and print or imply "this becomes an error
in 6.0.0"; the plan for honouring them lives in prose. Nothing kept the two in
step and they drifted — `COMPATIBILITY_MODEL.md` said three, `COMPATIBILITY.md`
said one, a design doc said a fourth had been dropped, and the two that went
missing were the two whose issues had been *closed*.

These tests run the phase against synthetic trees rather than the real one, so
they assert what the detector *can* catch rather than what happens to be true
today. The real tree is checked by `nodus_gate --flips` in the release gates.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from tools.nodus_gate.flips_phase import run_flips_phase  # noqa: E402

ENTRY = {
    "issue": 1,
    "summary": "a flip",
    "warns_since": "5.0.0",
    "signal": "ok",
    "why": "because",
    "sites": 1,
}


class _Tree:
    """A throwaway repo root with a manifest and one source file."""

    def __init__(self, flips: dict, source: str, *, filename: str = "mod.py"):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tools").mkdir()
        (self.root / "tools" / "v6_flips.json").write_text(
            json.dumps({"target": "6.0.0", "flips": flips}), encoding="utf-8"
        )
        pkg = self.root / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / filename).write_text(source, encoding="utf-8")

    def run(self):
        return run_flips_phase(self.root)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._tmp.cleanup()


class AttributionTests(unittest.TestCase):
    def test_a_marked_promise_passes(self):
        with _Tree({"a-flip": ENTRY}, "# v6-flip: a-flip\nX = 1  # error in 6.0.0\n") as t:
            result = t.run()
        self.assertFalse(result.has_failure, result)
        self.assertEqual(result.mentions, 1)

    # closes: #796
    def test_an_unmarked_promise_fails(self):
        """The whole point: a promise nothing registered."""
        with _Tree({"a-flip": ENTRY}, "X = 1  # becomes an error in 6.0.0\n") as t:
            result = t.run()
        self.assertTrue(result.has_failure)
        self.assertEqual(len(result.unattributed), 1)
        self.assertEqual(result.unattributed[0].line, 1)

    def test_a_marker_naming_an_undeclared_flip_fails(self):
        with _Tree({"a-flip": ENTRY}, "# v6-flip: other\nX = 1  # 6.0.0\n") as t:
            result = t.run()
        self.assertTrue(result.has_failure)
        self.assertEqual([u.flip for u in result.unknown], ["other"])

    def test_a_promise_beyond_the_window_is_not_absorbed(self):
        """A marker's reach is bounded, or a distant promise inherits it."""
        source = "# v6-flip: a-flip\nX = 1  # 6.0.0\n" + ("\n" * 60) + "Y = 2  # 6.0.0\n"
        with _Tree({"a-flip": ENTRY}, source) as t:
            result = t.run()
        self.assertTrue(result.has_failure)
        self.assertEqual(len(result.unattributed), 1)

    def test_the_marker_line_itself_is_not_a_promise(self):
        """`# v6-flip: x` next to a version token must not count as a mention."""
        with _Tree({"a-flip": ENTRY}, "# v6-flip: a-flip\nX = 1  # 6.0.0\n") as t:
            result = t.run()
        self.assertEqual(result.mentions, 1)

    def test_a_longer_version_is_not_the_target(self):
        """`16.0.0` and `6.0.0.1` are not promises about 6.0.0."""
        with _Tree({"a-flip": ENTRY}, "# v6-flip: a-flip\nX = 1  # 6.0.0\nY = 2  # 16.0.0\n") as t:
            result = t.run()
        self.assertEqual(result.mentions, 1)
        self.assertFalse(result.has_failure, result)


class RegisterTests(unittest.TestCase):
    def test_a_declared_flip_with_no_promise_fails(self):
        """Honoured, or retracted in silence — the second is why this fails."""
        with _Tree({"a-flip": ENTRY}, "X = 1\n") as t:
            result = t.run()
        self.assertTrue(result.has_failure)
        self.assertEqual([s.flip for s in result.stale], ["a-flip"])

    # closes: #796
    def test_a_new_promise_inside_an_existing_window_fails(self):
        """The hole probing this detector found.

        A promise added near an existing marker is absorbed by it, so the
        register stays green while gaining a site nobody declared. `sites` is
        what closes it, exactly as `shape_manifest.json` does for a third copy
        of an already-listed function.
        """
        source = "# v6-flip: a-flip\nX = 1  # 6.0.0\nY = 2  # also 6.0.0\n"
        with _Tree({"a-flip": ENTRY}, source) as t:
            result = t.run()
        self.assertTrue(result.has_failure)
        self.assertEqual(len(result.counts), 1)
        self.assertEqual((result.counts[0].declared, result.counts[0].found), (1, 2))

    def test_every_required_field_is_required(self):
        for missing in ("issue", "summary", "warns_since", "signal", "why", "sites"):
            entry = {k: v for k, v in ENTRY.items() if k != missing}
            with self.subTest(field=missing):
                with _Tree({"a-flip": entry}, "# v6-flip: a-flip\nX = 1  # 6.0.0\n") as t:
                    result = t.run()
                self.assertTrue(result.has_failure, f"{missing} was not required")
                self.assertIn(missing, " ".join(m.problem for m in result.malformed))


class ManifestTests(unittest.TestCase):
    def test_an_unreadable_manifest_is_a_failure_not_a_skip(self):
        """The check may not pass by being unable to run."""
        with _Tree({"a-flip": ENTRY}, "X = 1\n") as t:
            (t.root / "tools" / "v6_flips.json").write_text("{not json", encoding="utf-8")
            result = t.run()
        self.assertTrue(result.has_failure)
        self.assertIsNotNone(result.error)

    def test_a_missing_manifest_is_a_failure(self):
        with _Tree({"a-flip": ENTRY}, "X = 1\n") as t:
            (t.root / "tools" / "v6_flips.json").unlink()
            result = t.run()
        self.assertTrue(result.has_failure)
        self.assertIn("not found", result.error or "")


class RealTreeTests(unittest.TestCase):
    """The one assertion about this repo: the register is complete."""

    # closes: #796
    def test_the_checked_in_register_agrees_with_src(self):
        root = Path(__file__).resolve().parents[1]
        result = run_flips_phase(root)
        self.assertFalse(
            result.has_failure,
            "unattributed="
            f"{[(u.file, u.line) for u in result.unattributed]} "
            f"unknown={[(u.file, u.flip) for u in result.unknown]} "
            f"stale={[s.flip for s in result.stale]} "
            f"counts={[(c.flip, c.declared, c.found) for c in result.counts]} "
            f"malformed={[(m.flip, m.problem) for m in result.malformed]} "
            f"error={result.error}",
        )
        self.assertGreater(result.mentions, 0, "no promises found at all — is the scan working?")


if __name__ == "__main__":
    unittest.main()
