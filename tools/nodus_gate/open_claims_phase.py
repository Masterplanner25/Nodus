"""Open-claims phase: a document calling an issue open after it has closed (#931).

A sentence like "the gap is #395", "still open in #380" or "SCHED-002 (#95) open"
is true the day it is written and false the day the issue closes. Closing an issue
touches no document that cites it, so nothing notices. On 2026-11-11 an outside
reader found `LANGUAGE_SPEC.md` saying `spawn` returns a handle in one paragraph
and no handle 26 lines later; following it up found three documents calling #395
"the gap" two and a half months after it closed, through four releases of reviews.

**The whole design is the tense.** A present-tense openness claim ("tracked as
#N", "#N stays open", "the gap is #N") is checked. A past-tense record ("Filed as
#N", "fixed in #N", "#N has been open since...", "until #631 was fixed") is
history, true forever, and left alone. The patterns below accept only the
present-tense forms; when in doubt a phrasing is left out, because a phase that
cries wolf is a phase that gets switched off. Text in double quotes or backticks
is a mention, not a claim, and is not read: this phase's own documentation quotes
the sentences it catches.

**It reads issue states from `tools/issue_states.json` and makes no network call.**
That cache is written only by `python -m tools.refresh_issue_states`. An issue
closed after the last refresh still reads as open, so the miss errs in the quiet
direction; the release sequence refreshes before running this phase `--strict`.

**Scope.** Current documents only: `docs/` without `history/`, `archive/`,
`audits/` and `evals/` (records of what was, by definition), the root Markdown
files, `llms*.txt`, every `CLAUDE.md`, `.claude/commands/` and `skills/`.
`CHANGELOG.md` is read for its `[Unreleased]` section only: a released section is
a record of what shipped, and a "Known issue: #537" in it was true at that
release. `[Unreleased]` becomes the release notes at the next cut, which is where
5.16.0 found four entries still calling #180 open.

**Allowlist.** `.nodusgate-allow` takes `open-claim:<path>#<N>` for a citation
that should keep calling a closed issue open (a quote, or history in a current
document). An entry that matches no claim is reported, so the allowlist cannot
rot into a list of things nobody remembers.

**Advisory by default**, like `--consumers` and `--shapes`: it prints and exits 0.
`--strict` fails on a stale claim or a dead allowlist entry. A cache that cannot
be read is always a failure; the phase may not pass by being unable to run.
A claim citing a number the cache does not know (a pull request, or an issue
filed since the refresh) is reported as unknown and never fails.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CACHE_NAME = "tools/issue_states.json"
ALLOW_PREFIX = "open-claim:"

_SKIP_DOCS = ("docs/history/", "docs/archive/", "docs/audits/", "docs/evals/")

# `#N`, or a Markdown link to it: `[#N](https://...)`.
_N = r"\[?#(\d+)\]?(?:\([^)\s]*\))?"

# Phrase, then the number: "tracked as #N", "the gap is #N", "still open in #N".
_BEFORE = re.compile(
    r"\b(?:tracked (?:as|in|by|on)"
    r"|the gap is"
    r"|(?<!was )(?<!were )still open(?: (?:in|on|as|at))?"
    r"|remains open (?:in|on|as|at)"
    r"|open issue"
    r"|not yet (?:fixed|implemented|shipped|supported)"
    r"|still present\W{0,5}(?:now\s+)?(?:filed|tracked) as"
    r"|still present"
    r"|remains unimplemented"
    r")\b[^\w\n]{0,25}?" + _N,
    re.IGNORECASE,
)

# "Known issue -- #537", "Known CLI wart (not a doc error, filed as #345)": the
# noun is the present-tense claim, so the number may sit further away.
_KNOWN = re.compile(
    r"\bknown (?:\w+ ){0,2}(?:issue|bug|limitation|wart|gap)s?\b[^#\n]{0,40}?" + _N,
    re.IGNORECASE,
)

# The number, then the claim: "#N (open)", "#N (LOW, open)", "(#N) open",
# "#N, still open", "#N, which stays open", "#N stays open", "#N is still open".
_AFTER = re.compile(
    _N
    + r"(?:\s*\((?:[^()\n]{0,30},\s*)?open\)"
    r"|,\s*(?:still\s+)?open\b"
    r"|,\s*which\s+(?:is|remains|stays)\s+(?:still\s+)?open\b"
    r"|\s+(?:is|remains|stays)\s+(?:still\s+)?open\b"
    # "(#95) open" or "[#95](url) open" only. A bare "#N open" is as often a
    # past-tense verb's object ("shipped with #691 open", "still called #180 open").
    r"|(?:\)|(?<=\)))\s+open\b(?!\s+(?:question|design|problem)))",
    re.IGNORECASE,
)

# A quoted phrase is a mention, not a use: documentation about this phase, or a
# doc quoting what another document used to say. Blanked before matching, with
# the length kept so nothing else moves.
_QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”|`[^`\n]*`')


def _unquoted(line: str) -> str:
    return _QUOTED.sub(lambda m: " " * len(m.group(0)), line)

# "until #N is fixed" -- a promise about the future, so present tense.
_UNTIL = re.compile(
    r"\buntil\s+" + _N + r"\s+(?:is\s+(?:fixed|resolved|closed|merged|done)|lands|ships)\b",
    re.IGNORECASE,
)

_PATTERNS = (_BEFORE, _KNOWN, _AFTER, _UNTIL)


@dataclass
class Claim:
    path: str      # repo-relative, forward slashes
    line: int
    issue: int
    text: str      # the matched fragment
    source: str    # the whole line, stripped

    @property
    def allow_key(self) -> str:
        return f"{ALLOW_PREFIX}{self.path}#{self.issue}"


@dataclass
class OpenClaimsResult:
    claims: list[Claim] = field(default_factory=list)
    stale: list[Claim] = field(default_factory=list)
    unknown: list[Claim] = field(default_factory=list)
    allowed: list[Claim] = field(default_factory=list)
    dead_allow: list[str] = field(default_factory=list)
    files_scanned: int = 0
    refreshed: str = ""
    error: str | None = None

    @property
    def has_finding(self) -> bool:
        return bool(self.stale or self.dead_allow)


def load_states(root: str) -> tuple[dict[int, str], str]:
    """Read the cache. Raises ValueError on anything unusable."""
    path = Path(root) / CACHE_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {CACHE_NAME}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{CACHE_NAME} is not valid JSON: {exc}") from exc
    try:
        open_ = [int(n) for n in data["open"]]
        closed = [int(n) for n in data["closed"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{CACHE_NAME} lacks integer 'open'/'closed' lists: {exc}") from exc
    both = set(open_) & set(closed)
    if both:
        raise ValueError(f"{CACHE_NAME} lists issues as both open and closed: {sorted(both)[:5]}")
    if not open_ and not closed:
        raise ValueError(f"{CACHE_NAME} is empty")
    states = {n: "OPEN" for n in open_}
    states.update({n: "CLOSED" for n in closed})
    return states, str(data.get("refreshed", "unknown"))


def documents(root: str) -> list[tuple[Path, str]]:
    """(path, repo-relative path) for every document in scope, sorted."""
    base = Path(root)
    found: dict[str, Path] = {}

    def add(p: Path) -> None:
        if p.is_file():
            found[p.relative_to(base).as_posix()] = p

    for p in base.glob("docs/**/*.md"):
        if not p.relative_to(base).as_posix().startswith(_SKIP_DOCS):
            add(p)
    for p in base.glob("*.md"):
        add(p)
    for name in ("llms.txt", "llms-full.txt"):
        add(base / name)
    for p in base.glob(".claude/commands/*.md"):
        add(p)
    for p in base.glob("skills/*"):
        add(p)
    for sub in ("", "tests", "tools"):
        add(base / sub / "CLAUDE.md")
    for p in base.glob("src/**/CLAUDE.md"):
        add(p)
    return sorted(((p, rel) for rel, p in found.items()), key=lambda t: t[1])


def _unreleased_lines(text: str) -> set[int]:
    """1-based line numbers inside CHANGELOG's `## [Unreleased]` section."""
    keep: set[int] = set()
    inside = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            inside = line.strip().lower().startswith("## [unreleased]")
            continue
        if inside:
            keep.add(i)
    return keep


def find_claims(rel: str, text: str) -> list[Claim]:
    only = _unreleased_lines(text) if rel == "CHANGELOG.md" else None
    out: list[Claim] = []
    for i, line in enumerate(text.splitlines(), 1):
        if only is not None and i not in only:
            continue
        seen: set[int] = set()
        bare = _unquoted(line)
        for rx in _PATTERNS:
            for m in rx.finditer(bare):
                n = int(m.group(1))
                if n in seen:
                    continue
                seen.add(n)
                out.append(Claim(rel, i, n, m.group(0), line.strip()))
    return out


def run_open_claims_phase(root: str, allowlist: set[str] | None = None) -> OpenClaimsResult:
    result = OpenClaimsResult()
    try:
        states, result.refreshed = load_states(root)
    except ValueError as exc:
        result.error = str(exc)
        return result

    allow = {e for e in (allowlist or set()) if e.startswith(ALLOW_PREFIX)}
    used: set[str] = set()
    for path, rel in documents(root):
        result.files_scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for claim in find_claims(rel, text):
            result.claims.append(claim)
            state = states.get(claim.issue)
            if state == "OPEN":
                continue
            if claim.allow_key in allow:
                used.add(claim.allow_key)
                result.allowed.append(claim)
            elif state == "CLOSED":
                result.stale.append(claim)
            else:
                result.unknown.append(claim)
    result.dead_allow = sorted(allow - used)
    return result
