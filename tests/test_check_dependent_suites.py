"""The dependent-suite gate must say what to look at when it goes red (#528).

This gate stands between a build and PyPI. Its one instruction is "do not
publish", and until it named the failing test that instruction could neither be
acted on nor dismissed without leaving the tool and re-running the companion by
hand — the manual step the gate exists to replace.

The load-bearing assertion here is `test_a_recorded_flake_never_turns_red_green`.
Classifying a flake is a triage aid; letting one pass the gate would rebuild
"re-run until green" one level up.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # noqa: E402

from tools.check_dependent_suites import (  # noqa: E402
    DEPENDENTS,
    FLAKES_MANIFEST,
    SuiteResult,
    classify,
    parse_failures,
)

# Verbatim from `pytest -q --tb=short -rfE`, captured on this platform.
PYTEST_FAILED = """\
.FF                                                                      [100%]
=========================== short test summary info ===========================
FAILED test_demo.py::test_bad - assert 1 == 2
FAILED test_demo.py::TestGroup::test_also_bad - ValueError: boom
2 failed, 1 passed in 0.09s
"""

PYTEST_COLLECTION_ERROR = """\
=========================== short test summary info ===========================
ERROR test_broken.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.93s
"""

PYTEST_FIXTURE_ERROR = """\
E                                                                        [100%]
=========================== short test summary info ===========================
ERROR test_fixerr.py::test_uses - RuntimeError: fixture blew up
1 error in 0.04s
"""

PYTEST_CLEAN = """\
...........                                                              [100%]
363 passed in 79.42s
"""


class ParseTests(unittest.TestCase):
    def test_failed_lines_yield_node_ids(self):
        self.assertEqual(
            parse_failures(PYTEST_FAILED),
            ["test_demo.py::test_bad", "test_demo.py::TestGroup::test_also_bad"],
        )

    def test_the_reason_suffix_is_stripped(self):
        for node in parse_failures(PYTEST_FAILED):
            self.assertNotIn(" - ", node)

    def test_collection_errors_are_reported_as_the_file(self):
        """No `::test` to name, and the file that would not import is the point."""
        self.assertEqual(parse_failures(PYTEST_COLLECTION_ERROR), ["test_broken.py"])

    def test_fixture_errors_are_reported(self):
        self.assertEqual(
            parse_failures(PYTEST_FIXTURE_ERROR), ["test_fixerr.py::test_uses"]
        )

    def test_a_clean_run_yields_nothing(self):
        self.assertEqual(parse_failures(PYTEST_CLEAN), [])

    def test_duplicates_are_collapsed(self):
        doubled = PYTEST_FAILED + "FAILED test_demo.py::test_bad - assert 1 == 2\n"
        self.assertEqual(len(parse_failures(doubled)), 2)

    def test_prose_mentioning_failed_is_not_parsed_as_a_node(self):
        noise = "some test FAILED earlier but was retried\n"
        self.assertEqual(parse_failures(noise), [])


class ClassifyTests(unittest.TestCase):
    PATTERNS = [{"match": "test_phase_m.py", "why": "port conflicts"}]

    def test_a_matching_node_is_known(self):
        known, new = classify(["tests/test_phase_m.py::test_x"], self.PATTERNS)
        self.assertEqual(known, ["tests/test_phase_m.py::test_x"])
        self.assertEqual(new, [])

    def test_an_unmatched_node_is_new(self):
        known, new = classify(["tests/test_other.py::test_y"], self.PATTERNS)
        self.assertEqual(known, [])
        self.assertEqual(new, ["tests/test_other.py::test_y"])

    def test_a_mixed_run_splits(self):
        known, new = classify(
            ["tests/test_phase_m.py::test_x", "tests/test_other.py::test_y"],
            self.PATTERNS,
        )
        self.assertEqual(len(known), 1)
        self.assertEqual(len(new), 1)

    def test_an_empty_match_pattern_matches_nothing(self):
        """A blank `match` would otherwise silence the entire suite."""
        known, new = classify(["anything::at_all"], [{"match": "", "why": "oops"}])
        self.assertEqual(known, [])
        self.assertEqual(new, ["anything::at_all"])

    def test_no_patterns_means_everything_is_new(self):
        known, new = classify(["a::b"], [])
        self.assertEqual(known, [])
        self.assertEqual(new, ["a::b"])


class ExitCodeTests(unittest.TestCase):
    """Exit status drives the release decision, so each path is pinned."""

    def _run(self, results: list[SuiteResult]) -> int:
        import tools.check_dependent_suites as mod

        original = mod.run_suite
        queue = list(results)
        mod.run_suite = lambda name, path, patterns, retry=False: queue.pop(0)
        original_deps = dict(mod.DEPENDENTS)
        mod.DEPENDENTS.clear()
        mod.DEPENDENTS.update({r.name: "." for r in results})
        try:
            import contextlib
            import io

            with contextlib.redirect_stdout(io.StringIO()):
                return mod.main([])
        finally:
            mod.run_suite = original
            mod.DEPENDENTS.clear()
            mod.DEPENDENTS.update(original_deps)

    def test_all_passing_exits_zero(self):
        self.assertEqual(self._run([SuiteResult("a", "PASS")]), 0)

    def test_a_new_failure_exits_one(self):
        red = SuiteResult("a", "FAIL", failures=["t::x"], new=["t::x"])
        self.assertEqual(self._run([red]), 1)

    def test_a_missing_checkout_exits_two(self):
        self.assertEqual(self._run([SuiteResult("a", "MISSING")]), 2)

    def test_a_timeout_exits_two(self):
        """An unrun suite is not a passing one."""
        self.assertEqual(self._run([SuiteResult("a", "TIMEOUT")]), 2)

    # closes: #528
    def test_a_recorded_flake_never_turns_red_green(self):
        """Classification changes the advice, never the verdict.

        Exit 3, not 0. A listed test passing the gate would rebuild
        're-run until green' one level up.
        """
        flaky = SuiteResult("a", "FAIL", failures=["t::x"], known=["t::x"])
        self.assertEqual(self._run([flaky]), 3)

    def test_a_new_failure_outranks_a_known_one(self):
        mixed = SuiteResult(
            "a", "FAIL", failures=["t::x", "t::y"], known=["t::x"], new=["t::y"]
        )
        self.assertEqual(self._run([mixed]), 1)

    def test_a_red_suite_naming_no_test_is_treated_as_new(self):
        """Non-zero exit with no FAILED line is a config or collection problem.

        Reporting it as 'no new failures' would be the dangerous direction.
        """
        opaque = SuiteResult("a", "FAIL", failures=[], summary="exited 4")
        self.assertEqual(self._run([opaque]), 1)

    def test_a_new_failure_outranks_a_missing_checkout(self):
        results = [
            SuiteResult("a", "FAIL", failures=["t::x"], new=["t::x"]),
            SuiteResult("b", "MISSING"),
        ]
        self.assertEqual(self._run(results), 1)


class ManifestTests(unittest.TestCase):
    def test_the_shipped_manifest_parses(self):
        payload = json.loads(Path(FLAKES_MANIFEST).read_text(encoding="utf-8"))
        self.assertIn("known_flaky", payload)

    def test_every_entry_names_a_known_companion(self):
        payload = json.loads(Path(FLAKES_MANIFEST).read_text(encoding="utf-8"))
        for name in payload["known_flaky"]:
            self.assertIn(name, DEPENDENTS, f"{name} is not a tracked dependent")

    def test_every_entry_has_a_match_and_a_reason(self):
        """An entry with no stated reason is a way to lose a real break."""
        payload = json.loads(Path(FLAKES_MANIFEST).read_text(encoding="utf-8"))
        for name, entries in payload["known_flaky"].items():
            for entry in entries:
                self.assertTrue(entry.get("match"), f"{name}: entry with no match")
                self.assertTrue(entry.get("why"), f"{name}: {entry['match']} has no why")

    def test_a_missing_manifest_is_not_fatal(self):
        """The gate's job is running suites; a triage aid must not block that."""
        import tools.check_dependent_suites as mod

        original = mod.FLAKES_MANIFEST
        mod.FLAKES_MANIFEST = str(ROOT / "tools" / "does-not-exist.json")
        try:
            self.assertEqual(mod.load_known_flaky(), {})
        finally:
            mod.FLAKES_MANIFEST = original


if __name__ == "__main__":
    unittest.main()
