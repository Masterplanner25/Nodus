"""Closed-issue test for #474: the positioning clause is one claim, in four files.

D1 in `EXTERNAL_AUDIT_LEDGER.md` decided the wording: *"An orchestration DSL and
embedded runtime for building agentic hosts."*

The reason this needs a test rather than a careful edit is what applying it
found. A **partial** sweep had already run: `pyproject.toml`, `llms.txt` and
`README.md` said *"hosting agentic systems"*, while `llms-full.txt` still said
*"building agentic systems"* — one file out of four, and the one that was not
scanned by `nodus_gate` until #483. A claim spread across four files and checked
in none of them drifts, and had.

`pyproject.toml`'s copy is the **PyPI summary**, and the README is the long
description (`readme = "README.md"`), so both are permanent at tag time. Getting
three of four right is the failure mode with the worst blast radius.
"""

import re

from pathlib import Path

# closes: #474

_REPO_ROOT = Path(__file__).parents[2]

_CLAUSE = "building agentic hosts"

# Every file that states the positioning. Named once, here.
_SITES = [
    "pyproject.toml",
    "llms.txt",
    "llms-full.txt",
    "README.md",
    "src/nodus/llms.txt",  # the packaged copy that ships in the wheel (#605)
]

# What the clause used to say. Any of these surviving means a site was missed.
_SUPERSEDED = ("hosting agentic systems", "building agentic systems")


def test_every_site_states_the_decided_clause():
    missing = [
        site for site in _SITES
        if _CLAUSE not in (_REPO_ROOT / site).read_text(encoding="utf-8")
    ]
    assert not missing, (
        f"the positioning clause {_CLAUSE!r} is absent from: {missing}. "
        "D1 decided one wording; a site that does not carry it is the partial "
        "sweep this test exists to catch."
    )


def test_no_site_still_carries_a_superseded_clause():
    stale = []
    for site in _SITES:
        text = (_REPO_ROOT / site).read_text(encoding="utf-8")
        for phrase in _SUPERSEDED:
            if phrase in text:
                stale.append(f"{site} -> {phrase!r}")
    assert not stale, (
        "a superseded positioning clause survives: " + "; ".join(stale)
    )


def test_the_pypi_summary_carries_it():
    """`pyproject.toml`'s description is the PyPI summary — permanent at tag time."""
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^description = "(.*)"$', text, re.M)
    assert match, "pyproject.toml has no description line"
    assert match.group(1) == (
        "An orchestration DSL and embedded runtime for building agentic hosts"
    ), f"PyPI summary drifted from the D1 decision: {match.group(1)!r}"


# Records of what was true at the time, not claims about now.
_COUNT_RECORD_DIRS = {"evals", "history"}
_COUNT_RECORD_FILES = {"EXTERNAL_AUDIT_LEDGER.md"}
# A count on the same line as the 4.0.0 launch is that launch's count.
_COUNT_RECORD_LINE = re.compile(r"\bv?4\.0\.0\b")
_COUNT = re.compile(r"(\d+)[- ](?:package companion|companion package)")


def _count_sites() -> list[Path]:
    """Every document that could state the count, found rather than listed.

    A named list is what let `docs/guide/ecosystem.md` say 32 while this test
    passed, and two more files kept saying it after that was corrected.
    """
    named = [_REPO_ROOT / site for site in _SITES + ["CLAUDE.md"]]
    docs = [
        path for path in sorted((_REPO_ROOT / "docs").rglob("*.md"))
        if path.name not in _COUNT_RECORD_FILES
        and not _COUNT_RECORD_DIRS.intersection(path.relative_to(_REPO_ROOT).parts)
    ]
    return named + docs


def test_the_companion_count_agrees_across_the_prose():
    """A hand-maintained count in prose is the version-string failure again.

    "32-package companion ecosystem" was wrong in seven places while the live
    count was 35. This does not check the number against PyPI — that needs the
    network — but it does check the prose agrees with itself, which is what
    silently diverged.
    """
    counts: dict[str, set[str]] = {}
    for path in _count_sites():
        found: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not _COUNT_RECORD_LINE.search(line):
                found.update(_COUNT.findall(line))
        if found:
            counts[path.relative_to(_REPO_ROOT).as_posix()] = found
    assert counts, "found no companion count anywhere, so this checked nothing"
    distinct = set().union(*counts.values())
    assert len(distinct) <= 1, (
        "the companion-package count disagrees between files: "
        + "; ".join(f"{k}={sorted(v)}" for k, v in sorted(counts.items()))
    )
