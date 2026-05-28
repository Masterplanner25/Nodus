"""Closed-issues phase: verify CHANGELOG-referenced issues have passing tests."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


_ISSUE_REF_RE = re.compile(r'(?:closes?\s+|#|\()#?(\d+)\)?', re.IGNORECASE)
_CLOSES_MARKER_RE = re.compile(r'#\s*closes:\s*#?(\d+)', re.IGNORECASE)


@dataclass
class IssueStatus:
    issue_number: int
    test_path: str | None   # path to test file or None if not found
    test_function: str | None
    passed: bool | None     # None = not run; True = passed; False = failed
    error_msg: str = ""


@dataclass
class ClosedIssuesResult:
    issues: list[IssueStatus] = field(default_factory=list)
    scanned_section: str = ""
    missing_tests: int = 0
    passed: int = 0
    failed: int = 0


def parse_changelog_issues(changelog_path: str, *, section: str = "Unreleased") -> list[int]:
    """Return list of issue numbers from the specified CHANGELOG section."""
    try:
        with open(changelog_path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []

    # Find the section
    section_re = re.compile(
        rf"##\s*\[{re.escape(section)}\][^\n]*\n(.*?)(?=\n##\s*\[|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = section_re.search(content)
    if not m:
        return []

    body = m.group(1)
    numbers: list[int] = []
    seen: set[int] = set()
    for m2 in _ISSUE_REF_RE.finditer(body):
        n = int(m2.group(1))
        if n not in seen:
            seen.add(n)
            numbers.append(n)
    return numbers


def find_test_for_issue(issue_number: int, tests_root: str) -> tuple[str | None, str | None]:
    """Return (test_file_path, test_function_or_None) for the given issue number."""
    # Convention 1: tests/closed_issues/issue_<N>.py
    candidate = os.path.join(tests_root, "closed_issues", f"issue_{issue_number}.py")
    if os.path.isfile(candidate):
        return candidate, None

    # Convention 2: # closes: #N marker in any test file
    for dirpath, _dirs, files in os.walk(tests_root):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    content = f.read()
            except OSError:
                continue
            for m in _CLOSES_MARKER_RE.finditer(content):
                if int(m.group(1)) == issue_number:
                    # Find the function name after the marker
                    after = content[m.end():]
                    fn_m = re.search(r'def\s+(\w+)', after[:200])
                    fn_name = fn_m.group(1) if fn_m else None
                    return fpath, fn_name

    return None, None


def run_test(
    test_file: str, test_function: str | None, *, use_dev_source: bool = True
) -> tuple[bool, str]:
    """Run a specific test file/function. Return (passed, error_msg)."""
    src_root = str(Path(__file__).parents[2] / "src")
    env = os.environ.copy()
    if use_dev_source:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{src_root}{os.pathsep}{existing}" if existing else src_root

    cmd = [sys.executable, "-m", "pytest", test_file, "-q", "--tb=short", "--no-header"]
    if test_function:
        cmd.append(f"-k={test_function}")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        if proc.returncode == 0:
            return True, ""
        return False, (proc.stdout + proc.stderr)[:2000]
    except subprocess.TimeoutExpired:
        return False, "Test timed out after 60 seconds"
    except Exception as exc:
        return False, str(exc)


def run_closed_issues_phase(
    root: str,
    *,
    section: str = "Unreleased",
    use_dev_source: bool = True,
) -> ClosedIssuesResult:
    """Run the closed-issues phase."""
    result = ClosedIssuesResult(scanned_section=section)

    changelog = os.path.join(root, "CHANGELOG.md")
    issue_numbers = parse_changelog_issues(changelog, section=section)

    tests_root = os.path.join(root, "tests")

    for n in issue_numbers:
        test_path, test_fn = find_test_for_issue(n, tests_root)
        status = IssueStatus(issue_number=n, test_path=test_path, test_function=test_fn, passed=None)

        if test_path is None:
            result.missing_tests += 1
            status.error_msg = (
                f"No test found. Looked for tests/closed_issues/issue_{n}.py "
                f"and '# closes: #{n}' markers."
            )
        else:
            passed, err = run_test(test_path, test_fn, use_dev_source=use_dev_source)
            status.passed = passed
            status.error_msg = err
            if passed:
                result.passed += 1
            else:
                result.failed += 1

        result.issues.append(status)

    return result
