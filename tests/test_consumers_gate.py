"""The consumers gate: which non-PyPI consumers a release has left behind.

Stage 6 detects downstream drift by hashing published sdists and wheels against
local source, so anything not on PyPI is invisible to it. Two things are: the VS
Code extension and the GitHub Action, and both have shipped stale with nothing
to notice.

The property that matters most here is that the check **needs no sibling
checkout**. `test_every_keyword_is_highlighted` reads the nodus-vscode grammar
directly, which is honest but means it skips on CI where the checkout is absent
-- and a keyword duly shipped unhighlighted. This gate records the fingerprint
locally instead, so it runs everywhere.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # noqa: E402

from tools.nodus_gate.consumers_phase import run_consumers_phase  # noqa: E402

ROOT = str(Path(__file__).resolve().parent.parent)


class TheRealManifestIsUsableTests(unittest.TestCase):
    def test_every_consumer_declares_something_measurable(self):
        result = run_consumers_phase(ROOT)
        self.assertIsNone(result.error, msg=result.error)
        self.assertGreater(result.checks_run, 0, "manifest declares no consumers")

    def test_each_consumer_says_why_and_how(self):
        """A stale flag with no remedy is a nag. Whoever hits this at 2am should
        not have to go find out what republishing involves."""
        result = run_consumers_phase(ROOT)
        for status in result.statuses:
            with self.subTest(consumer=status.name):
                self.assertTrue(status.why.strip(), "no `why`")
                self.assertTrue(status.republish.strip(), "no `republish`")


class ItRunsWithoutAnySiblingCheckoutTests(unittest.TestCase):
    """The whole design point. This test passes on CI, where none of the consumer
    repos exist -- if it ever needs one, the gate has regressed into the shape it
    was built to replace."""

    def test_no_consumer_path_is_read(self):
        result = run_consumers_phase(ROOT)
        self.assertIsNone(result.error)
        # Nothing outside the repo root should be needed to reach a verdict.
        for status in result.statuses:
            with self.subTest(consumer=status.name):
                self.assertNotEqual(status.actual, "", "no live value measured")


class DriftIsDetectedTests(unittest.TestCase):
    def _manifest(self, tmp: str, tracks: str, fingerprint: str) -> str:
        root = Path(tmp)
        (root / "tools").mkdir(parents=True)
        (root / "tools" / "consumers.json").write_text(
            json.dumps({
                "consumers": [{
                    "name": "example",
                    "repo": "x/y",
                    "kind": "test",
                    "published": "1.0.0",
                    "tracks": tracks,
                    "fingerprint": fingerprint,
                    "why": "because",
                    "republish": "somehow",
                }]
            }),
            encoding="utf-8",
        )
        # The phase measures against the *real* source tree, so point it at ours
        # for the live value while reading the temp manifest.
        return str(root)

    def test_a_matching_fingerprint_is_in_step(self):
        from tools.nodus_gate.consumers_phase import _nodus_version

        current = _nodus_version(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            # The temp root has no src/, so the tracker resolves through the
            # already-imported module -- which is what we want: same live value.
            result = run_consumers_phase(self._manifest(tmp, "nodus_version", current))
            self.assertIsNone(result.error, msg=result.error)
            self.assertEqual([], result.stale)

    def test_a_stale_fingerprint_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_consumers_phase(
                self._manifest(tmp, "nodus_version", "0.0.1-ancient")
            )
            self.assertIsNone(result.error, msg=result.error)
            self.assertEqual(1, len(result.stale))
            self.assertEqual("example", result.stale[0].name)


class ItRefusesRatherThanPassesVacuouslyTests(unittest.TestCase):
    """A check that cannot run must not report success -- that is how a gate
    becomes decorative."""

    def test_a_missing_manifest_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_consumers_phase(tmp)
            self.assertIsNotNone(result.error)
            self.assertIn("manifest not found", result.error)

    def test_malformed_json_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tools").mkdir()
            (Path(tmp) / "tools" / "consumers.json").write_text("{ not json", encoding="utf-8")
            result = run_consumers_phase(tmp)
            self.assertIsNotNone(result.error)
            self.assertIn("not valid JSON", result.error)

    def test_an_unknown_tracks_value_is_an_error(self):
        """Adding a consumer that tracks something the phase cannot measure must
        fail loudly, not be silently skipped into a green tick."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tools").mkdir()
            (Path(tmp) / "tools" / "consumers.json").write_text(
                json.dumps({"consumers": [{"name": "x", "tracks": "vibes"}]}),
                encoding="utf-8",
            )
            result = run_consumers_phase(tmp)
            self.assertIsNotNone(result.error)
            self.assertIn("vibes", result.error)


if __name__ == "__main__":
    unittest.main()
