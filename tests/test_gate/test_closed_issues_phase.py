"""Tests for nodus_gate closed-issues phase."""

import sys
import tempfile
import os
import shutil
import unittest

sys.path.insert(0, "C:/dev/Coding Language")  # noqa: E402
sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

from tools.nodus_gate.closed_issues_phase import (  # noqa: E402
    parse_changelog_issues, find_test_for_issue, run_closed_issues_phase
)


def _make_changelog(content: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix="CHANGELOG.md", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


class ParseChangelogTests(unittest.TestCase):

    def test_parses_unreleased_issues(self):
        content = """# Changelog

## [Unreleased]

- Fix for issue (#75)
- closes #76
- BUG-V31E-01 (#77)

## [1.0.0]

- Old issue #50
"""
        path = _make_changelog(content)
        try:
            issues = parse_changelog_issues(path)
            self.assertIn(75, issues)
            self.assertIn(76, issues)
            self.assertIn(77, issues)
            # Old section not included
            self.assertNotIn(50, issues)
        finally:
            os.unlink(path)

    def test_no_issues_returns_empty(self):
        content = "## [Unreleased]\n\nNo issues referenced.\n"
        path = _make_changelog(content)
        try:
            issues = parse_changelog_issues(path)
            self.assertEqual(issues, [])
        finally:
            os.unlink(path)

    def test_deduplicates_issues(self):
        content = "## [Unreleased]\n\n- (#75) and closes #75 again\n"
        path = _make_changelog(content)
        try:
            issues = parse_changelog_issues(path)
            self.assertEqual(issues.count(75), 1)
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_empty(self):
        issues = parse_changelog_issues("/nonexistent/CHANGELOG.md")
        self.assertEqual(issues, [])

    def test_prose_under_an_entry_is_not_a_claim(self):
        """Only the entry itself claims an issue was fixed; its prose may cite anything.

        An entry that ships a defect downgraded, or names the follow-up tracking
        the root cause, is doing exactly what it should. Scanning that prose made
        the gate demand a regression test for an issue nobody claimed to have
        fixed — so writing the honest note was what failed the gate (#376/#390).
        """
        content = """## [Unreleased]

### Fixes

- **#75: the thing was broken.** Three causes, all fixed.

  **Known issue.** #76 is closed but not proven zero, and the root cause is
  tracked separately as **#77** — the same shape as #78.
"""
        path = _make_changelog(content)
        try:
            issues = parse_changelog_issues(path)
            self.assertEqual([75], issues)
        finally:
            os.unlink(path)

    def test_a_nested_bullet_is_still_an_entry(self):
        """Sub-bullets break a multi-cause entry down; each one is still a claim."""
        content = """## [Unreleased]

- **#75: several things.**

  - the first, which also fixed #76
"""
        path = _make_changelog(content)
        try:
            self.assertEqual([75, 76], parse_changelog_issues(path))
        finally:
            os.unlink(path)

    def test_specific_section(self):
        content = """## [Unreleased]

- (#99)

## [2.0.0]

- (#42)
"""
        path = _make_changelog(content)
        try:
            issues = parse_changelog_issues(path, section="2.0.0")
            self.assertIn(42, issues)
            self.assertNotIn(99, issues)
        finally:
            os.unlink(path)


class FindTestTests(unittest.TestCase):

    def setUp(self):
        self.tests_root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tests_root, ignore_errors=True)

    def test_convention1_file_per_issue(self):
        closed_dir = os.path.join(self.tests_root, "closed_issues")
        os.makedirs(closed_dir)
        issue_file = os.path.join(closed_dir, "issue_75.py")
        with open(issue_file, "w") as f:
            f.write("def test_issue_75(): pass\n")

        path, fn = find_test_for_issue(75, self.tests_root)
        self.assertEqual(path, issue_file)
        self.assertIsNone(fn)

    def test_convention2_marker_comment(self):
        test_file = os.path.join(self.tests_root, "test_something.py")
        with open(test_file, "w") as f:
            f.write("# closes: #76\ndef test_the_fix():\n    pass\n")

        path, fn = find_test_for_issue(76, self.tests_root)
        self.assertEqual(path, test_file)
        self.assertEqual(fn, "test_the_fix")

    def test_marker_on_a_class_runs_the_whole_file(self):
        # A marker tagging a class used to resolve to the first `def` after it —
        # `setUp` — and `-k setUp` selected nothing, so the gate reported a
        # passing regression suite as FAIL with "12 deselected" (#339).
        test_file = os.path.join(self.tests_root, "test_class_marker.py")
        with open(test_file, "w") as f:
            f.write(
                "# closes: #77\n"
                "class SomeTests(unittest.TestCase):\n"
                '    """Docstring long enough to push setUp past the old window."""\n'
                "    def setUp(self):\n        pass\n"
                "    def test_the_fix(self):\n        pass\n"
            )

        path, fn = find_test_for_issue(77, self.tests_root)
        self.assertEqual(path, test_file)
        self.assertIsNone(fn, "a class marker must not select a single function")

    def test_marker_on_a_function_still_selects_it(self):
        test_file = os.path.join(self.tests_root, "test_fn_marker.py")
        with open(test_file, "w") as f:
            f.write("# closes: #78\ndef test_only_this_one():\n    pass\n")

        path, fn = find_test_for_issue(78, self.tests_root)
        self.assertEqual(path, test_file)
        self.assertEqual(fn, "test_only_this_one")

    def test_missing_issue_returns_none(self):
        path, fn = find_test_for_issue(9999, self.tests_root)
        self.assertIsNone(path)
        self.assertIsNone(fn)


class ClosedIssuesPhaseTests(unittest.TestCase):

    def _make_root(self, changelog: str, tests: dict) -> str:
        root = tempfile.mkdtemp()
        cl_path = os.path.join(root, "CHANGELOG.md")
        with open(cl_path, "w", encoding="utf-8") as f:
            f.write(changelog)
        tests_dir = os.path.join(root, "tests")
        closed_dir = os.path.join(tests_dir, "closed_issues")
        os.makedirs(closed_dir)
        for name, content in tests.items():
            with open(os.path.join(closed_dir, name), "w") as f:
                f.write(content)
        return root

    def test_missing_test_reported(self):
        root = self._make_root(
            "## [Unreleased]\n\n- Fix (#99)\n",
            {}
        )
        try:
            result = run_closed_issues_phase(root)
            self.assertEqual(result.missing_tests, 1)
            self.assertEqual(result.issues[0].issue_number, 99)
            self.assertIsNone(result.issues[0].test_path)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_passing_test_counted(self):
        root = self._make_root(
            "## [Unreleased]\n\n- Fix (#100)\n",
            {"issue_100.py": "def test_something():\n    assert 1 + 1 == 2\n"}
        )
        try:
            result = run_closed_issues_phase(root)
            self.assertEqual(result.passed, 1)
            self.assertEqual(result.failed, 0)
            self.assertEqual(result.missing_tests, 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_failing_test_counted(self):
        root = self._make_root(
            "## [Unreleased]\n\n- Fix (#101)\n",
            {"issue_101.py": "def test_broken():\n    assert 1 == 2\n"}
        )
        try:
            result = run_closed_issues_phase(root)
            self.assertEqual(result.failed, 1)
            self.assertEqual(result.passed, 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_no_issues_in_section(self):
        root = self._make_root("## [Unreleased]\n\nNo issues.\n", {})
        try:
            result = run_closed_issues_phase(root)
            self.assertEqual(len(result.issues), 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
