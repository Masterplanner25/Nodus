"""One list of nodus-lang dependents, and nothing keeps a second copy (#810).

Two gates each kept their own list of "which companions depend on nodus-lang":

* `tools/check_dependent_suites.py` — Gate 10a, runs each suite **before** a
  PyPI upload;
* `tools/check_downstream_constraints.py` — Stage 6, resolves each published
  range **after** one.

They drifted, and the drift was not symmetrical noise. Gate 10a had six names,
Stage 6 had seven, and the true set is **eight**: `nodus-workflow-ai` was missing
from the first and `nodus-a2a-wire` from both. So a published first-party
dependent had neither its suite run before an upload nor its range checked after
one, for every release since it shipped.

`tools/nodus_lang_dependents.json` is the single list and
`tools/nodus_lang_dependents.py` the only reader. These tests assert **on the
source** that neither gate has grown its own copy back, because that is the shape
`nodus_gate --shapes` reports and a behaviour test cannot see it: two lists that
happen to agree today pass every behavioural check there is.

Two further things worth stating, because each was a decision:

* **The criterion is `declares`, not `imports`.** `nodus-workflow-ai` imports
  nothing from nodus-lang — it emits Nodus source — so the old criterion excluded
  it *correctly* and still left a hole. A generator breaks when the syntax it
  emits stops parsing, or when a flag it passes is refused, which is #791's shape
  and shipped in 5.12.0.
* **The sweep for unregistered checkouts is the part that would have found
  `nodus-a2a-wire`.** Reading a hand-maintained list never reveals the entry
  nobody added; only looking beside it does. It is exercised here against
  synthetic directories, since a CI runner has no companion checkouts and a sweep
  over directories that do not exist proves nothing.
"""

import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tools import nodus_lang_dependents as registry

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"


class TheManifestIsWellFormedTests(unittest.TestCase):
    # closes: #810
    def test_every_dependent_has_a_path_and_a_published_flag(self):
        entries = registry.load()
        self.assertGreaterEqual(len(entries), 8)
        for name, entry in entries.items():
            with self.subTest(dependent=name):
                self.assertIsInstance(entry["path"], str)
                self.assertIsInstance(entry["published"], bool)

    def test_the_two_names_this_issue_was_about_are_present(self):
        entries = registry.load()
        self.assertIn("nodus-workflow-ai", entries)
        self.assertIn("nodus-a2a-wire", entries)

    def test_a2a_wire_points_at_the_publishable_checkout(self):
        """`C:\\codev\\nodus-a2a-wire` is a worktree of the *coordinator* repo.

        A standing trap in CLAUDE.md, and a good part of why this dependent was
        missed: the obvious path is the wrong project.
        """
        path = registry.load()["nodus-a2a-wire"]["path"]
        self.assertIn("a2a-wire-pub", path)

    def test_every_ignored_path_states_a_reason(self):
        for path, reason in registry._ignored().items():
            with self.subTest(path=path):
                self.assertTrue(reason.strip())
                self.assertGreater(len(reason), 40, "a reason, not a label")

    def test_a_malformed_manifest_is_an_error_not_a_default(self):
        """A check may not pass by being unable to run."""
        with tempfile.TemporaryDirectory() as td:
            broken = pathlib.Path(td) / "broken.json"
            broken.write_text('{"dependents": {}}', encoding="utf-8")
            with mock.patch.object(registry, "MANIFEST", str(broken)):
                with self.assertRaises(registry.DependentRegistryError):
                    registry.load()

            broken.write_text("not json", encoding="utf-8")
            with mock.patch.object(registry, "MANIFEST", str(broken)):
                with self.assertRaises(registry.DependentRegistryError):
                    registry.load()

            broken.write_text(
                json.dumps({"dependents": {"x": {"path": "/tmp/x"}}}), encoding="utf-8"
            )
            with mock.patch.object(registry, "MANIFEST", str(broken)):
                with self.assertRaises(registry.DependentRegistryError):
                    registry.load()


class NeitherGateKeepsItsOwnListTests(unittest.TestCase):
    """The source assertion. Two lists that agree today pass every behaviour test."""

    def test_gate_10a_reads_the_manifest(self):
        source = (TOOLS / "check_dependent_suites.py").read_text(encoding="utf-8")
        self.assertIn("from tools.nodus_lang_dependents import", source)
        # `assertTrue` rather than `assertNotIn`, which would dump the whole
        # module into the failure message and bury the one sentence that says
        # what to do about it.
        self.assertTrue(
            "DEPENDENTS = {" not in source,
            "check_dependent_suites.py has its own dependent list again. That is "
            "the drift #810 was about — it should read tools/nodus_lang_dependents.json.",
        )

    def test_stage_6_reads_the_manifest(self):
        source = (TOOLS / "check_downstream_constraints.py").read_text(encoding="utf-8")
        self.assertIn("published_names()", source)
        self.assertTrue(
            'COMPANIONS = [\n    "nodus-' not in source,
            "check_downstream_constraints.py has its own companion list again. That "
            "is the drift #810 was about — it should read "
            "tools/nodus_lang_dependents.json.",
        )

    def test_the_two_gates_therefore_see_the_same_set(self):
        from tools.check_dependent_suites import checkouts as gate_10a
        from tools.check_downstream_constraints import COMPANIONS as stage_6

        published = {
            name for name, entry in registry.load().items() if entry["published"]
        }
        self.assertEqual(set(gate_10a()), set(registry.load()))
        self.assertEqual(set(stage_6), published)


class PublishDriftContainsEveryPublishedDependentTests(unittest.TestCase):
    """A larger list, on purpose — but it must not be *missing* one of ours.

    `check_publish_drift` tracks every published companion, not only those
    depending on nodus-lang, so it is legitimately a superset rather than a
    fourth copy. The containment is the part worth checking: it was the only one
    of the three lists that already had both missing names, which is how the true
    set was established.
    """

    def test_every_published_dependent_is_tracked_for_drift(self):
        from tools.check_publish_drift import COMPANIONS as drift

        for name in registry.published_names():
            with self.subTest(dependent=name):
                self.assertIn(name, drift)


class TheSweepFindsAnUnregisteredCheckoutTests(unittest.TestCase):
    """Exercised against synthetic directories: CI has no companion checkouts."""

    def _registry_over(self, root: pathlib.Path, ignored=None):
        manifest = root / "manifest.json"
        registered = root / "registered-pkg"
        registered.mkdir()
        (registered / "pyproject.toml").write_text(
            'name = "registered-pkg"\ndependencies = ["nodus-lang>=5.0.0"]\n',
            encoding="utf-8",
        )
        manifest.write_text(
            json.dumps(
                {
                    "dependents": {
                        "registered-pkg": {"path": str(registered), "published": True}
                    },
                    "ignored": ignored or {},
                }
            ),
            encoding="utf-8",
        )
        return mock.patch.object(registry, "MANIFEST", str(manifest))

    def test_an_unregistered_dependent_beside_a_registered_one_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            stranger = root / "stranger-pkg"
            stranger.mkdir()
            (stranger / "pyproject.toml").write_text(
                'name = "stranger-pkg"\ndependencies = ["nodus-lang>=5.0.0"]\n',
                encoding="utf-8",
            )
            with self._registry_over(root):
                found = registry.unregistered_nearby()
        self.assertEqual([name for name, _ in found], ["stranger-pkg"])

    def test_a_checkout_that_does_not_declare_nodus_lang_is_not_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            unrelated = root / "unrelated-pkg"
            unrelated.mkdir()
            (unrelated / "pyproject.toml").write_text(
                'name = "unrelated-pkg"\ndependencies = ["requests"]\n', encoding="utf-8"
            )
            with self._registry_over(root):
                self.assertEqual(registry.unregistered_nearby(), [])

    def test_an_ignored_path_is_not_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            stranger = root / "stranger-pkg"
            stranger.mkdir()
            (stranger / "pyproject.toml").write_text(
                'name = "stranger-pkg"\ndependencies = ["nodus-lang>=5.0.0"]\n',
                encoding="utf-8",
            )
            reason = {str(stranger): "third party, kept here only as a convenience copy"}
            with self._registry_over(root, ignored=reason):
                self.assertEqual(registry.unregistered_nearby(), [])

    def test_an_ignored_entry_without_a_reason_is_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            with self._registry_over(root, ignored={"C:\\somewhere": "  "}):
                with self.assertRaises(registry.DependentRegistryError):
                    registry.unregistered_nearby()

    def test_readable_roots_says_how_much_of_the_sweep_was_real(self):
        """A sweep over directories that are not there is not evidence."""
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            with self._registry_over(root):
                found, total = registry.readable_roots()
        self.assertEqual((found, total), (1, 1))

        with tempfile.TemporaryDirectory() as td:
            manifest = pathlib.Path(td) / "m.json"
            manifest.write_text(
                json.dumps(
                    {
                        "dependents": {
                            "gone": {
                                "path": str(pathlib.Path(td) / "no-such-root" / "gone"),
                                "published": True,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(registry, "MANIFEST", str(manifest)):
                self.assertEqual(registry.readable_roots(), (0, 1))


if __name__ == "__main__":
    unittest.main()
