"""Closed-issues phase: verify CHANGELOG-referenced issues have passing tests."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


# Match explicit issue references only: "closes #N", "(#N)", or bare "#N"
# Requires the # sign before digits to avoid matching plain numbers
_ISSUE_REF_RE = re.compile(r'(?:closes?\s+#|(?<!\w)#)(\d+)', re.IGNORECASE)
_CLOSES_MARKER_RE = re.compile(r'#\s*closes:\s*#?(\d+)', re.IGNORECASE)

# A CHANGELOG entry is a list item, and its issue reference is the claim that the
# issue was addressed. Only a claim needs a regression test. Prose *inside* an
# entry cross-references freely — a known issue that shipped unfixed, the
# follow-up tracking the root cause, an older issue of the same shape — and
# demanding a test for each of those makes the honest write-up the thing that
# fails the gate. So: scan list-item lines, skip the paragraphs under them.
_ENTRY_LEAD_RE = re.compile(r'^\s*[-*]\s+\S')

# Regression tests for closed issues are allowed to be slow: several run the real
# CLI in a subprocess, which costs seconds per invocation before any assertion.
# The #348 suite takes ~41s on an unloaded machine, so the previous 60s cap gave
# it 1.4x headroom and it timed out under gate load — reported as a failing
# regression test when nothing had regressed. Same insufficient-headroom trap the
# suite's own flaky tests keep hitting; CLAUDE.md asks for 5-10x.
_TEST_TIMEOUT_S = 300


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
    for line in body.splitlines():
        if not _ENTRY_LEAD_RE.match(line):
            continue  # prose, not a claim — see _ENTRY_LEAD_RE
        for m2 in _ISSUE_REF_RE.finditer(line):
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
            for m in _marker_matches(content):
                if int(m.group(1)) == issue_number:
                    # What the marker is attached to: a test function, or a class
                    # tagging a whole group of them.
                    after = content[m.end():]
                    def_m = re.search(r'\b(class|def)\s+(\w+)', after)
                    if def_m is None:
                        return fpath, None
                    if def_m.group(1) == "class":
                        # Run the whole file. Selecting just this class would skip
                        # the issue's other classes, and the previous behavior was
                        # worse: it matched the first `def` after the marker —
                        # `setUp` — and `-k setUp` selected nothing, so the gate
                        # reported a passing regression suite as a failure.
                        return fpath, None
                    return fpath, def_m.group(2)

    return None, None


def _marker_matches(content: str):
    """Yield `_CLOSES_MARKER_RE` matches that are actual comments (#562).

    A marker is a comment, and matching it anywhere in the file bound issues
    to prose: a docstring *mentioning* the marker convention matched first,
    and the issue was then bound to whatever `def` happened to follow the
    docstring — `-k _fresh_warn_state` selected nothing and a passing suite
    reported as failed. Second false verdict from whole-file matching (the
    first was the `setUp` binding, fixed above), so the scan is now
    tokenizer-backed: only text inside COMMENT tokens can carry a marker. On
    a file that does not tokenize, fall back to whole-file matching — a
    wrong-ish answer beats silently finding no test for the issue.
    """
    import io
    import tokenize as _tokenize

    try:
        comment_spans = []
        for tok in _tokenize.generate_tokens(io.StringIO(content).readline):
            if tok.type == _tokenize.COMMENT:
                start = _line_col_to_offset(content, tok.start)
                comment_spans.append((start, start + len(tok.string)))
    except (SyntaxError, _tokenize.TokenError, ValueError):
        yield from _CLOSES_MARKER_RE.finditer(content)
        return

    for m in _CLOSES_MARKER_RE.finditer(content):
        if any(start <= m.start() < end for start, end in comment_spans):
            yield m


def _line_col_to_offset(content: str, position: tuple[int, int]) -> int:
    line, col = position
    offset = 0
    for _ in range(line - 1):
        offset = content.index("\n", offset) + 1
    return offset + col


def run_test(
    test_file: str, test_function: str | None, *, use_dev_source: bool = True
) -> tuple[bool, str]:
    """Run a specific test file/function. Return (passed, error_msg)."""
    repo_root = str(Path(__file__).parents[2])
    src_root = str(Path(__file__).parents[2] / "src")
    env = os.environ.copy()
    if use_dev_source:
        existing = env.get("PYTHONPATH", "")
        # Both src (for `import nodus`) and the repo root (for `import tools...`)
        # so closed-issue tests resolve portably without hardcoded local paths.
        parts = [src_root, repo_root] + ([existing] if existing else [])
        env["PYTHONPATH"] = os.pathsep.join(parts)

    cmd = [sys.executable, "-m", "pytest", test_file, "-q", "--tb=short", "--no-header"]
    if test_function:
        cmd.append(f"-k={test_function}")

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=_TEST_TIMEOUT_S
        )
        if proc.returncode == 0:
            return True, ""
        return False, (proc.stdout + proc.stderr)[:2000]
    except subprocess.TimeoutExpired:
        return False, f"Test timed out after {_TEST_TIMEOUT_S} seconds"
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
