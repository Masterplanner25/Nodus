"""The versions gate: prose that quotes the version files must still agree.

Three release cycles shipped a stale version string in prose. CLAUDE.md named
the failure in writing and it kept happening, because the response was a list to
check by hand. These tests cover the gate that replaces the list.

Most run against a synthetic tree so they can assert on failure as well as
success. The last class runs against the real repo, which makes the manifest's
own accuracy a suite obligation rather than a release-day discovery.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # noqa: E402

from tools.nodus_gate.versions_phase import (  # noqa: E402
    _latest_eval_version,
    _read_version_py,
    run_versions_phase,
)

VERSION_PY = 'VERSION = f"Nodus {__version__}"\n__version__ = "{v}"\n'


def _tree(tmp: Path, *, version: str = "9.9.9", pyproject: str | None = None) -> Path:
    """A minimal repo the phase can run against."""
    root = tmp
    (root / "src" / "nodus" / "support").mkdir(parents=True)
    (root / "src" / "nodus" / "support" / "version.py").write_text(
        f'"""v."""\n\n__version__ = "{version}"\nVERSION = f"Nodus {{__version__}}"\n',
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "nodus-lang"\nversion = "{pyproject or version}"\n',
        encoding="utf-8",
    )
    (root / "tools").mkdir()
    (root / "docs" / "evals" / f"v{version}").mkdir(parents=True)
    return root


def _manifest(root: Path, payload: dict) -> None:
    (root / "tools" / "version_claims.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


class SyncTests(unittest.TestCase):
    def test_matching_version_files_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp))
            _manifest(root, {"claims": []})
            result = run_versions_phase(str(root))
        self.assertTrue(result.sync.in_sync)
        self.assertFalse(result.has_failure)

    def test_mismatched_version_files_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), version="9.9.9", pyproject="9.9.8")
            _manifest(root, {"claims": []})
            result = run_versions_phase(str(root))
        self.assertFalse(result.sync.in_sync)
        self.assertTrue(result.has_failure)
        self.assertEqual(result.sync.version_py, "9.9.9")
        self.assertEqual(result.sync.pyproject, "9.9.8")

    def test_missing_authority_is_an_error_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text('version = "1.0.0"\n', encoding="utf-8")
            result = run_versions_phase(str(root))
        self.assertIsNotNone(result.error)
        self.assertTrue(result.has_failure)


class ClaimTests(unittest.TestCase):
    def _run(self, body: str, claims: list[dict], version: str = "9.9.9"):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), version=version)
            (root / "DOC.md").write_text(body, encoding="utf-8")
            _manifest(root, {"claims": claims})
            return run_versions_phase(str(root))

    def test_a_matching_claim_passes(self):
        result = self._run(
            "The current version is 9.9.9 today.\n",
            [{"file": "DOC.md", "pattern": r"current version is (\d+\.\d+\.\d+)"}],
        )
        self.assertFalse(result.has_failure)
        self.assertTrue(result.claims[0].ok)
        self.assertEqual(result.claims[0].line, 1)

    def test_a_stale_claim_fails_and_reports_both_values(self):
        result = self._run(
            "The current version is 5.0.1 today.\n",
            [{"file": "DOC.md", "pattern": r"current version is (\d+\.\d+\.\d+)"}],
        )
        self.assertTrue(result.has_failure)
        claim = result.claims[0]
        self.assertFalse(claim.ok)
        self.assertEqual(claim.claimed, "5.0.1")
        self.assertEqual(claim.expected, "9.9.9")

    def test_a_pattern_matching_nothing_fails(self):
        """A claim site that moved is exactly what this exists to catch."""
        result = self._run(
            "Nothing quotable here.\n",
            [{"file": "DOC.md", "pattern": r"current version is (\d+\.\d+\.\d+)"}],
        )
        self.assertTrue(result.has_failure)
        self.assertFalse(result.claims[0].found)
        self.assertIn("matched nothing", _render(result))

    def test_a_missing_file_fails(self):
        result = self._run(
            "x\n", [{"file": "GONE.md", "pattern": r"(\d+\.\d+\.\d+)"}]
        )
        self.assertTrue(result.has_failure)
        self.assertIn("file not found", result.claims[0].text)

    def test_after_anchors_the_search_past_repeated_prose(self):
        """The real file repeats '**Current version:** X' once per package."""
        body = (
            "## Assessment: other\n"
            "**Current version:** 0.1.0\n"
            "## Assessment: nodus-lang (core)\n"
            "**Current version:** 9.9.9\n"
        )
        result = self._run(
            body,
            [
                {
                    "file": "DOC.md",
                    "after": "## Assessment: nodus-lang (core)",
                    "pattern": r"\*\*Current version:\*\* (\d+\.\d+\.\d+)",
                }
            ],
        )
        self.assertFalse(result.has_failure)
        self.assertEqual(result.claims[0].line, 4)
        self.assertEqual(result.claims[0].claimed, "9.9.9")

    def test_a_missing_anchor_is_reported_rather_than_silently_skipped(self):
        result = self._run(
            "**Current version:** 9.9.9\n",
            [
                {
                    "file": "DOC.md",
                    "after": "## Assessment: nodus-lang (core)",
                    "pattern": r"\*\*Current version:\*\* (\d+\.\d+\.\d+)",
                }
            ],
        )
        self.assertTrue(result.has_failure)
        self.assertIn("anchor not found", result.claims[0].text)


class LatestEvalTests(unittest.TestCase):
    def test_eval_versions_sort_numerically_not_lexically(self):
        with tempfile.TemporaryDirectory() as tmp:
            evals = Path(tmp) / "docs" / "evals"
            for name in ("v5.0.10", "v5.1.0", "v4.9.9"):
                (evals / name).mkdir(parents=True)
            latest, err = _latest_eval_version(Path(tmp))
        self.assertIsNone(err)
        # Lexically "v5.0.10" > "v5.1.0"; numerically it is not.
        self.assertEqual(latest, "5.1.0")

    def test_non_version_directories_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            evals = Path(tmp) / "docs" / "evals"
            (evals / "v1.0.0").mkdir(parents=True)
            (evals / "scratch").mkdir()
            latest, err = _latest_eval_version(Path(tmp))
        self.assertIsNone(err)
        self.assertEqual(latest, "1.0.0")


class DiscoveryTests(unittest.TestCase):
    def _run(self, body: str, *, ignore=None, claims=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp))
            (root / "DOC.md").write_text(body, encoding="utf-8")
            _manifest(
                root,
                {
                    "claims": claims or [],
                    "ignore": ignore or [],
                    "scan": {
                        "files": ["DOC.md"],
                        "currency_markers": ["current version", "most recent"],
                    },
                },
            )
            return run_versions_phase(str(root))

    def test_an_unregistered_currency_claim_is_reported(self):
        result = self._run("The current version is 1.2.3.\n")
        self.assertEqual(len(result.unregistered), 1)
        self.assertEqual(result.unregistered[0].line, 1)

    def test_discovery_alone_does_not_fail_the_gate(self):
        """Advisory: it suggests, it does not decide."""
        result = self._run("The current version is 1.2.3.\n")
        self.assertTrue(result.unregistered)
        self.assertFalse(result.has_failure)

    def test_a_historical_mention_is_not_flagged(self):
        """'as of X' does not go stale; only 'X is current' does."""
        result = self._run("Fixed in 5.0.3, and again in 5.0.4.\n")
        self.assertEqual(result.unregistered, [])

    def test_a_currency_word_without_a_version_is_not_flagged(self):
        result = self._run("The current version is whatever main says.\n")
        self.assertEqual(result.unregistered, [])

    def test_a_registered_claim_is_not_also_reported_as_unregistered(self):
        result = self._run(
            "The current version is 9.9.9.\n",
            claims=[{"file": "DOC.md", "pattern": r"current version is (\d+\.\d+\.\d+)"}],
        )
        self.assertFalse(result.has_failure)
        self.assertEqual(result.unregistered, [])

    def test_ignore_suppresses_a_named_line(self):
        result = self._run(
            "The current version is 1.2.3.\n",
            ignore=[{"file": "DOC.md", "contains": "current version is 1.2.3"}],
        )
        self.assertEqual(result.unregistered, [])

    def test_ignore_is_per_line_not_per_file(self):
        """A new claim in an already-noisy file must still surface."""
        result = self._run(
            "The current version is 1.2.3.\nThe current version is 4.5.6.\n",
            ignore=[{"file": "DOC.md", "contains": "1.2.3"}],
        )
        self.assertEqual(len(result.unregistered), 1)
        self.assertEqual(result.unregistered[0].line, 2)


class AuthorityIsReadAsTextTests(unittest.TestCase):
    """The gate must not import nodus to learn its version.

    An installed `nodus-lang` shadowing the checkout would make the gate compare
    the docs against the wrong version, silently and in the direction that hides
    a real mismatch. That shadowing is a live hazard here -- it is what
    `nodus doctor` exists for.
    """

    def test_the_phase_does_not_import_the_package(self):
        """Checked against the AST, not the text.

        The module docstring quotes the import it refuses to use, so a substring
        search reports a violation that is really an explanation. Only actual
        import nodes count.
        """
        import ast

        source = (ROOT / "tools" / "nodus_gate" / "versions_phase.py").read_text(
            encoding="utf-8"
        )
        imported: list[str] = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        offenders = [m for m in imported if m == "nodus" or m.startswith("nodus.")]
        self.assertEqual(offenders, [], f"phase imports the package: {offenders}")

    def test_version_is_parsed_from_a_synthetic_file(self):
        """Proves the reader works on text alone, with no package present."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "src" / "nodus" / "support"
            target.mkdir(parents=True)
            (target / "version.py").write_text('__version__ = "7.7.7"\n', encoding="utf-8")
            version, err = _read_version_py(root)
        self.assertIsNone(err)
        self.assertEqual(version, "7.7.7")


class RealRepoTests(unittest.TestCase):
    """Runs against this repo, so the manifest's accuracy is a suite obligation.

    If this fails, either a version string went stale or a claim site moved and
    its pattern needs re-anchoring. Both are the point.
    """

    def test_the_repo_passes_its_own_versions_gate(self):
        result = run_versions_phase(str(ROOT))
        self.assertIsNone(result.error)
        detail = "\n".join(
            f"{c.file}:{c.line} says {c.claimed!r}, expected {c.expected!r} — {c.text}"
            for c in result.failures
        )
        self.assertTrue(result.sync.in_sync, f"version files disagree: {result.sync}")
        self.assertEqual(result.failures, [], detail)

    def test_every_registered_claim_resolves_to_a_line(self):
        result = run_versions_phase(str(ROOT))
        unlocatable = [c.file for c in result.claims if not c.found]
        self.assertEqual(unlocatable, [], f"patterns matched nothing: {unlocatable}")

    def test_every_ignore_entry_still_matches_something(self):
        """A suppression for a line that no longer exists is dead weight."""
        manifest = json.loads(
            (ROOT / "tools" / "version_claims.json").read_text(encoding="utf-8")
        )
        dead = []
        for entry in manifest.get("ignore", []):
            path = ROOT / entry["file"]
            if not path.is_file():
                dead.append(entry)
                continue
            if entry["contains"] not in path.read_text(encoding="utf-8"):
                dead.append(entry)
        self.assertEqual(dead, [], f"ignore entries matching nothing: {dead}")

    def test_every_ignore_entry_states_a_reason(self):
        manifest = json.loads(
            (ROOT / "tools" / "version_claims.json").read_text(encoding="utf-8")
        )
        for entry in manifest.get("ignore", []):
            self.assertTrue(entry.get("why"), f"ignore entry with no reason: {entry}")


def _render(result) -> str:
    from tools.nodus_gate.output import format_versions

    return format_versions(result, use_color=False, verbose=False, quiet=False)


if __name__ == "__main__":
    unittest.main()
