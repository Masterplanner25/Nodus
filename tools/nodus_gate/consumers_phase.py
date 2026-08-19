"""Consumers phase: which non-PyPI consumers a release has left behind.

Stage 6's downstream sweep detects drift by hashing published sdists and wheels
against local source. Anything not on PyPI is invisible to it -- and two things
are: the VS Code extension and the GitHub Action. Both have shipped stale, and
nothing reminded anyone, because the only mechanism that would have looked
structurally cannot see them.

This phase closes that by not looking at them either. It reads no sibling
checkout and makes no network call. Each consumer records, in `tools/consumers.json`,
the fingerprint of whatever it must stay in step with -- measured *here*, at the
moment it was last published. When the live value moves, the consumer is stale
and the gate says which one and why.

That design is deliberate. `test_every_keyword_is_highlighted` in the suite does
the honest thing and reads the nodus-vscode grammar directly, which means it
skips on CI where the checkout is absent -- and a keyword duly shipped
unhighlighted. A check that cannot run where it matters is not a check.

**Advisory by default.** Findings here do not fail the build unless `--strict`.
A stale consumer is a release obligation, not a broken tree, and flagging it two
weeks early is worth more than blocking a merge that has nothing to do with it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConsumerStatus:
    name: str
    kind: str
    published: str
    tracks: str
    expected: str
    actual: str
    why: str
    republish: str

    @property
    def in_step(self) -> bool:
        return self.expected == self.actual


@dataclass
class ConsumersResult:
    statuses: list[ConsumerStatus] = field(default_factory=list)
    error: str | None = None

    @property
    def checks_run(self) -> int:
        return len(self.statuses)

    @property
    def stale(self) -> list[ConsumerStatus]:
        return [s for s in self.statuses if not s.in_step]

    @property
    def passed(self) -> int:
        return self.checks_run - len(self.stale)


def _keyword_fingerprint(root: str) -> str:
    """A stable digest of the language's complete keyword set.

    Sorted, so the digest tracks the *set* rather than declaration order -- a
    keyword moving between the contextual groups is not a reason to republish an
    editor grammar, but a keyword appearing or disappearing is.
    """
    src = str(Path(root) / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from nodus.frontend.lexer import ALL_KEYWORDS

    joined = "\n".join(sorted(ALL_KEYWORDS))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _nodus_version(root: str) -> str:
    src = str(Path(root) / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from nodus.support.version import __version__

    return __version__


_TRACKERS = {
    "keywords": _keyword_fingerprint,
    "nodus_version": _nodus_version,
}


def run_consumers_phase(root: str) -> ConsumersResult:
    manifest_path = Path(root) / "tools" / "consumers.json"
    result = ConsumersResult()

    if not manifest_path.is_file():
        result.error = f"manifest not found: {manifest_path}"
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.error = f"manifest is not valid JSON: {exc}"
        return result

    for entry in manifest.get("consumers", []):
        tracks = entry.get("tracks")
        tracker = _TRACKERS.get(tracks)
        if tracker is None:
            result.error = (
                f"consumer '{entry.get('name')}' tracks '{tracks}', which this phase "
                f"does not know how to measure. Known: {', '.join(sorted(_TRACKERS))}."
            )
            return result
        result.statuses.append(
            ConsumerStatus(
                name=entry.get("name", "?"),
                kind=entry.get("kind", ""),
                published=entry.get("published", "?"),
                tracks=tracks,
                expected=str(entry.get("fingerprint", "")),
                actual=str(tracker(root)),
                why=entry.get("why", ""),
                republish=entry.get("republish", ""),
            )
        )

    return result
