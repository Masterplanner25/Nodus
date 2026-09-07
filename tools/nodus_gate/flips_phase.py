"""Flips phase: is the register of what changes at the next major complete?

A staged flip is a promise made to a user *now* about a release that has not
happened -- "this becomes an error in 6.0.0" is printed on stderr, today, by
code that still allows the thing. The promise lives in `src/`; the plan for
honouring it lives in prose. Nothing kept the two in step, and they drifted:

    src/                          five live 6.0.0 promises
    COMPATIBILITY_MODEL.md 5.3    "Three changes are staged" -- named three
    COMPATIBILITY.md              one
    docs/design/v6/00-*.md        said the `worker:` flip had been dropped

Every one of those was hand-maintained, and the two that went missing were the
two whose issues had been *closed* -- the staging work shipped, the issue closed,
and the flip fell out of every register while the code kept promising it. That
is the failure this phase exists to make impossible: not a wrong flip, an
*unregistered* one.

**Why a marker rather than a scan.** Attribution is the whole problem. Two of
these flips live in `orchestration/task_graph.py` and their promise text is
nearly identical -- `"This becomes an error in 6.0.0."` appears twice, ~940 lines
apart, for entirely different flips. No amount of regex separates them. So each
site carries an explicit marker, the same way a regression test carries
`# closes: #N` for `--closed-issues`:

    # v6-flip: worker-dispatcher

A marker covers the `6.0.0` mentions in the `_WINDOW` lines below it, which is
enough for a comment plus the message it introduces and short enough that a new
promise cannot quietly inherit its neighbour's marker.

Three checks, all failing rather than advisory. Every one of them is wrong *now*
with a one-line fix -- an unregistered promise means the register is incomplete
the moment it lands, which is exactly the state this cohort was found in:

1. **Every `6.0.0` mention in `src/` is attributed** to a marker above it.
2. **Every marker names a flip the manifest declares.**
3. **Every declared flip is still promised somewhere.** A flip whose promise has
   vanished has either been honoured -- in which case the entry goes -- or been
   silently retracted, which is the worse case and the one nobody notices.
4. **Every declared flip owns exactly as many promise lines as it says.** Found
   by probing this detector rather than by reading it: a promise added inside an
   existing marker's window is absorbed by that marker, so the register stayed
   green while gaining a site nobody declared.

An unreadable manifest is a failure, never a skip: the check may not pass by
being unable to run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

#: Inside the package, not under `tools/`, because it is not only a gate
#: manifest any more: `nodus check --staged` reads the same file to report
#: a project's exposure, and that command ships. Two copies -- one to gate
#: with and one to ship -- would be the drift this phase exists to catch.
_MANIFEST = Path("src") / "nodus" / "support" / "staged_flips.json"
_SRC = Path("src")

#: How far below a marker its coverage reaches. Long enough for a comment and
#: the multi-line message it introduces (the widest real case is 13 lines);
#: short enough that a promise added later cannot inherit the marker above it.
_WINDOW = 30

_MARKER = re.compile(r"#\s*v6-flip:\s*([a-z0-9-]+)")

#: Required on every manifest entry. `signal` and `warns_since` are here because
#: a flip whose warning nobody sees is not a deprecation by this project's own
#: rule (`COMPATIBILITY_MODEL.md` 5.1), and that fact has to be written down
#: next to the flip rather than rediscovered.
#:
#: `sites` is the count of promise lines the flip owns, and it exists because
#: probing this detector found the hole it closes: a *new* promise added within
#: a marker's window is silently attributed to that marker, so the register
#: stays green while gaining a site nobody declared. `tools/shape_manifest.json`
#: carries `sites` for the identical reason -- a third copy of an already-listed
#: function was invisible to the shape detector until it did.
_REQUIRED = ("issue", "summary", "warns_since", "signal", "why", "sites")


@dataclass
class Unattributed:
    """A `6.0.0` mention with no marker above it."""

    file: str
    line: int
    text: str


@dataclass
class UnknownFlag:
    """A marker naming a flip the manifest does not declare."""

    file: str
    line: int
    flip: str


@dataclass
class SiteCountChanged:
    """A flip owns a different number of promise lines than it declares."""

    flip: str
    declared: int
    found: int
    sites: list


@dataclass
class StaleEntry:
    """A declared flip that nothing in `src/` promises any more."""

    flip: str
    issue: object
    summary: str


@dataclass
class MalformedEntry:
    flip: str
    problem: str


@dataclass
class FlipsResult:
    target: str = ""
    flips: dict = field(default_factory=dict)
    marked: dict = field(default_factory=dict)
    mentions: int = 0
    unattributed: list = field(default_factory=list)
    unknown: list = field(default_factory=list)
    stale: list = field(default_factory=list)
    counts: list = field(default_factory=list)
    malformed: list = field(default_factory=list)
    error: str | None = None

    @property
    def has_failure(self) -> bool:
        return bool(
            self.error
            or self.unattributed
            or self.unknown
            or self.stale
            or self.counts
            or self.malformed
        )


def _load_manifest(root: Path) -> tuple[dict, str | None]:
    path = root / _MANIFEST
    if not path.is_file():
        return {}, f"manifest not found: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"manifest could not be read: {path}: {exc}"
    if not isinstance(data, dict) or "flips" not in data:
        return {}, f"manifest has no 'flips' object: {path}"
    return data, None


def _python_sources(root: Path):
    for path in sorted((root / _SRC).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def run_flips_phase(root: Path) -> FlipsResult:
    """Check that every staged-flip promise in `src/` is registered."""
    result = FlipsResult()
    data, error = _load_manifest(root)
    if error:
        result.error = error
        return result

    result.target = str(data.get("target", "6.0.0"))
    flips = data.get("flips") or {}
    if not isinstance(flips, dict):
        result.error = "manifest 'flips' is not an object"
        return result
    result.flips = flips

    for name, entry in sorted(flips.items()):
        if not isinstance(entry, dict):
            result.malformed.append(MalformedEntry(name, "entry is not an object"))
            continue
        for field_name in _REQUIRED:
            value = entry.get(field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                result.malformed.append(
                    MalformedEntry(name, f"missing or empty '{field_name}'")
                )

    # The target is matched as a whole version token, so a future "16.0.0" or a
    # path fragment does not count as a promise.
    token = re.compile(r"(?<![\d.])" + re.escape(result.target) + r"(?![\d])")

    seen: dict[str, list] = {}
    for path in _python_sources(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        markers: list[tuple[int, str]] = [
            (i, m.group(1))
            for i, line in enumerate(lines)
            for m in [_MARKER.search(line)]
            if m
        ]
        rel = path.relative_to(root).as_posix()
        for i, marker_flip in markers:
            if marker_flip not in flips:
                result.unknown.append(UnknownFlag(rel, i + 1, marker_flip))
        for i, line in enumerate(lines):
            if not token.search(line) or _MARKER.search(line):
                continue
            result.mentions += 1
            covering = [
                flip for (m_line, flip) in markers
                if m_line <= i <= m_line + _WINDOW
            ]
            if not covering:
                result.unattributed.append(Unattributed(rel, i + 1, line.strip()))
                continue
            # Nearest marker above wins when two windows overlap.
            nearest = max(
                (m for m in markers if m[0] <= i <= m[0] + _WINDOW),
                key=lambda m: m[0],
            )[1]
            seen.setdefault(nearest, []).append(f"{rel}:{i + 1}")

    result.marked = seen
    for name, entry in sorted(flips.items()):
        found = seen.get(name)
        if not found:
            result.stale.append(
                StaleEntry(
                    name,
                    (entry or {}).get("issue", "?"),
                    (entry or {}).get("summary", ""),
                )
            )
            continue
        declared = (entry or {}).get("sites")
        if isinstance(declared, int) and declared != len(found):
            result.counts.append(
                SiteCountChanged(name, declared, len(found), found)
            )
    return result
