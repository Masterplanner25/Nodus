"""#931: `nodus_gate --open-claims` reports a document calling a closed issue open.

The phase's whole design is the tense: a present-tense openness claim is checked,
a past-tense record is history and left alone. So the tests come in two halves,
and the second matters as much as the first -- a phase that cries wolf gets
switched off. The positive fixtures include the exact sentences #931 found in the
tree (seven of them, through four releases of reviews).
"""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # noqa: E402

from tools.nodus_gate import cli  # noqa: E402
from tools.nodus_gate.open_claims_phase import (  # noqa: E402
    ALLOW_PREFIX,
    CACHE_NAME,
    find_claims,
    load_states,
    run_open_claims_phase,
)
from tools.refresh_issue_states import render  # noqa: E402

CLOSED = 395
OPEN = 900

# Each must be reported when the issue is closed. The first seven are verbatim
# (issue number normalised) from the documents #931 found.
PRESENT_TENSE = [
    "there is no `cancel` builtin, and the gap is #395.",
    "**Follow-on, still open (#395):** after unification, `goal` is a workflow",
    "F27: STILL PRESENT — now filed as #395. --trace-imports emits nothing once the",
    "Known CLI wart (not a doc error, filed as #395): `nodus test --help` runs discovery",
    "unimplemented -- tracked as #395, not as a test gap.",
    "Tracked as [#395](https://github.com/Masterplanner25/Nodus/issues/395).",
    "Tracked in [#395](https://github.com/Masterplanner25/Nodus/issues/395).",
    "coroutines (#395, which stays open for stage 4: the `checkpoint` statement",
    "coroutines (#395, still open).",
    "SCHED-001 fixed (#94 closed); SCHED-002 (#395) open",
    "- **#395 (LOW, open) — the VS Code grammar does not highlight `match`,",
    "execution until #395 is fixed.",
    "[#395](https://github.com/Masterplanner25/Nodus/issues/395) remains open for",
    "Measure if you need one. The bound itself is still open in #395.",
    "**#395 is open** on stating the rule in the guide",
    "Known issue — #395. An edge means",
    "SCHED-002 ([#395](https://github.com/Masterplanner25/Nodus/issues/395)) open",
    "[#395](https://github.com/Masterplanner25/Nodus/issues/395) open, see the note",
]

# Each must NOT be reported: history, past tense, or not a claim at all.
PAST_OR_NOT_A_CLAIM = [
    "Filed as **#395**.",
    "Fixed in #395, released in 5.8.0.",
    "question #395 has been open on since it was filed",
    "`tests/test_scheduler_fairness.py` was deselected too until #395 was fixed on",
    "workaround is a separate OS process per tenant, and that #395 was the open tracking",
    "#395 — every open design question against the workflow DSL.",
    "#395 showed the unfixed tests passing 5 of 6",
    "the bound was still open in #395 at the time",
    "closed by #395",
    "see #395 for the history",
    # The object of a past-tense verb, not a claim.
    "5.8.0 shipped its GitHub release with #395 open, because",
    "four `[Unreleased]` entries still called #395 open",
    # Quoted: a mention of the sentence, as this phase's own docs make.
    'Sentences like "the gap is #395" or "still open in #395" go stale.',
    "the doc said `tracked as #395` until it was fixed",
]


def _cache(root: Path, open_=(OPEN,), closed=(CLOSED, 94)) -> None:
    (root / "tools").mkdir(parents=True, exist_ok=True)
    states = {n: "OPEN" for n in open_} | {n: "CLOSED" for n in closed}
    (root / CACHE_NAME).write_text(render(states, "2026-11-11"), encoding="utf-8")


def _doc(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


class TenseTests(unittest.TestCase):

    # closes: #931
    def test_every_present_tense_form_is_a_claim(self):
        for line in PRESENT_TENSE:
            with self.subTest(line=line):
                found = [c.issue for c in find_claims("docs/x.md", line)]
                self.assertEqual([CLOSED], found)

    def test_no_past_tense_form_is_a_claim(self):
        for line in PAST_OR_NOT_A_CLAIM:
            with self.subTest(line=line):
                self.assertEqual([], find_claims("docs/x.md", line))

    def test_one_line_citing_one_issue_twice_is_one_claim(self):
        line = "tracked as #395, which stays open"
        self.assertEqual(1, len(find_claims("docs/x.md", line)))


class PhaseTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _cache(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def run_phase(self, allow=None):
        return run_open_claims_phase(str(self.root), allowlist=allow)

    def test_a_closed_issue_called_open_is_stale(self):
        _doc(self.root, "docs/guide/a.md", "The gap is #395.\n")
        result = self.run_phase()
        self.assertEqual(["docs/guide/a.md"], [c.path for c in result.stale])
        self.assertEqual(1, result.stale[0].line)
        self.assertTrue(result.has_finding)

    def test_an_open_issue_called_open_is_fine(self):
        _doc(self.root, "docs/guide/a.md", "The gap is #900.\n")
        result = self.run_phase()
        self.assertEqual([], result.stale)
        self.assertEqual(1, len(result.claims))

    def test_an_issue_the_cache_does_not_know_is_unknown_not_stale(self):
        _doc(self.root, "docs/guide/a.md", "Tracked in #12345.\n")
        result = self.run_phase()
        self.assertEqual([], result.stale)
        self.assertEqual([12345], [c.issue for c in result.unknown])
        self.assertFalse(result.has_finding)

    def test_records_of_what_was_are_out_of_scope(self):
        for sub in ("history", "archive", "audits", "evals/v1.0.0"):
            _doc(self.root, f"docs/{sub}/old.md", "The gap is #395.\n")
        self.assertEqual([], self.run_phase().claims)

    def test_every_documented_surface_is_in_scope(self):
        surfaces = ["README.md", "llms.txt", "CLAUDE.md", "tests/CLAUDE.md",
                    "src/pkg/CLAUDE.md", ".claude/commands/x.md", "skills/nodus.skill",
                    "skills/nodus/references/idioms.md",
                    "docs/design/v5/d.md"]
        for rel in surfaces:
            _doc(self.root, rel, "The gap is #395.\n")
        self.assertEqual(sorted(surfaces), sorted(c.path for c in self.run_phase().stale))

    def test_changelog_is_read_for_unreleased_only(self):
        _doc(self.root, "CHANGELOG.md", """\
            # Changelog

            ## [Unreleased]

            - **Thing.** Stage 2 (#395, which stays open).

            ## [5.0.0] - 2026-08-17

            **Known issue — #395.** True when this shipped.
            """)
        result = self.run_phase()
        self.assertEqual([5], [c.line for c in result.stale])

    def test_an_allowlisted_citation_is_allowed_not_stale(self):
        _doc(self.root, "docs/guide/a.md", "The gap is #395.\n")
        result = self.run_phase({f"{ALLOW_PREFIX}docs/guide/a.md#395"})
        self.assertEqual([], result.stale)
        self.assertEqual(1, len(result.allowed))
        self.assertFalse(result.has_finding)

    def test_an_allowlist_entry_matching_nothing_is_reported(self):
        _doc(self.root, "docs/guide/a.md", "Nothing to see.\n")
        result = self.run_phase({f"{ALLOW_PREFIX}docs/guide/a.md#395", "symbol:other"})
        self.assertEqual([f"{ALLOW_PREFIX}docs/guide/a.md#395"], result.dead_allow)
        self.assertTrue(result.has_finding)

    def test_an_allowlist_entry_is_per_file(self):
        _doc(self.root, "docs/guide/a.md", "The gap is #395.\n")
        _doc(self.root, "docs/guide/b.md", "The gap is #395.\n")
        result = self.run_phase({f"{ALLOW_PREFIX}docs/guide/a.md#395"})
        self.assertEqual(["docs/guide/b.md"], [c.path for c in result.stale])


class CacheTests(unittest.TestCase):

    def test_render_round_trips_through_load(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _cache(root, open_=(3, 1), closed=(2,))
            states, refreshed = load_states(raw)
        self.assertEqual({1: "OPEN", 2: "CLOSED", 3: "OPEN"}, states)
        self.assertEqual("2026-11-11", refreshed)

    def test_an_unusable_cache_is_an_error_not_a_pass(self):
        cases = {
            "missing": None,
            "not json": "{",
            "no lists": json.dumps({"refreshed": "x"}),
            "both": json.dumps({"open": [1], "closed": [1]}),
            "empty": json.dumps({"open": [], "closed": []}),
        }
        for name, body in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as raw:
                if body is not None:
                    (Path(raw) / "tools").mkdir()
                    (Path(raw) / CACHE_NAME).write_text(body, encoding="utf-8")
                result = run_open_claims_phase(raw)
                self.assertIsNotNone(result.error)
                self.assertEqual([], result.claims)


class CliTests(unittest.TestCase):
    """Advisory by default, failing under --strict, always failing on no cache."""

    def _main(self, root: Path, *flags: str) -> int:
        import contextlib
        import io
        import os

        cwd = os.getcwd()
        allow = root / ".nodusgate-allow"
        allow.touch()
        old_root = cli._find_root
        cli._find_root = lambda: str(root)
        os.chdir(root)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                return cli.main(["--open-claims", "--allowlist", str(allow), *flags])
        finally:
            os.chdir(cwd)
            cli._find_root = old_root

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _cache(root)
            _doc(root, "docs/guide/a.md", "The gap is #395.\n")
            self.assertEqual(0, self._main(root))
            self.assertEqual(1, self._main(root, "--strict"))
            (root / CACHE_NAME).unlink()
            self.assertEqual(1, self._main(root))


if __name__ == "__main__":
    unittest.main()
