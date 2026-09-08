"""Every document under `docs/` must be reachable from an index.

`docs/README.md` is the reader's entry point, and its directory tables had gone
out of step with the tree: `migration/` listed three of six files, and the three
it omitted were the two that matter most now -- the v5.0 deny-by-default guide
and the v6.0 staged-flip guide -- plus `v4.0-to-v4.1.md`. `docs/policy/` and
`docs/architecture/` had no section at all, so `error-surfaces.md` was
unreachable from anywhere the day after it was rewritten.

Twenty documents were named by no index when this was first measured.

**Reachability, not tabulation, is the property.** Some sections deliberately
point at a sub-index rather than restating its contents -- `governance/` points
at `DOCSET_INDEX.md`, `audits/` at `AUDIT_INDEX.md`, `history/` at its own
README. That is the better design where a directory is large or its membership
moves, and a test demanding a table in `docs/README.md` would push against it.
So this checks that *some* index names the file, and the set of indexes is
listed below.

An earlier version of this check reported `audits/` as having "0 listed / 10
present" because it only looked at `docs/README.md`; the section was correct and
the measurement was wrong. Adding an index here is a legitimate fix when a
directory genuinely has its own entry point.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DOCS = _REPO_ROOT / "docs"

#: Documents that index other documents. A file named by any of these is reachable.
_INDEXES = (
    "docs/README.md",
    "docs/governance/DOCSET_INDEX.md",
    "docs/audits/AUDIT_INDEX.md",
    "docs/history/README.md",
    "docs/ecosystem/README.md",
    "docs/guide/getting-started.md",
    "llms.txt",
)

#: Directory prefixes whose contents are addressed as a group, with the reason.
_SKIP_PREFIXES = (
    # Per-release output. `docs/README.md` describes the `vX.Y.Z/` shape rather
    # than naming three files per release forever.
    "docs/evals/v",
    # Dated sweep records, described by `history/README.md` at directory
    # granularity -- deliberately, since their internal paths were left pointing
    # at where files used to be.
    "docs/history/docset-sweep",
    "docs/history/plans/",
    "docs/history/release-notes/",
    # Numbered design records, indexed by their own directory conventions and
    # explicitly not enumerated in CLAUDE.md for the same drift reason.
    "docs/design/",
    # Gitignored working area.
    "docs/archive/",
)


def _named_anywhere() -> set[str]:
    names: set[str] = set()
    for rel in _INDEXES:
        p = _REPO_ROOT / rel
        if p.is_file():
            names |= set(
                re.findall(r"([A-Za-z0-9_. -]+\.md)", p.read_text(encoding="utf-8"))
            )
    return names


def _documents() -> list[str]:
    out = []
    for p in sorted(_DOCS.rglob("*.md")):
        rel = p.relative_to(_REPO_ROOT).as_posix()
        if any(rel.startswith(s) for s in _SKIP_PREFIXES):
            continue
        out.append(rel)
    return out


class DocsAreIndexedTests(unittest.TestCase):
    def test_the_sweep_finds_documents(self):
        """A scan matching nothing would pass forever and check nothing."""
        self.assertGreater(len(_documents()), 40)

    def test_the_indexes_exist(self):
        """A renamed index would silently shrink the reachable set."""
        missing = [rel for rel in _INDEXES if not (_REPO_ROOT / rel).is_file()]
        self.assertEqual([], missing, "an index named here no longer exists")

    def test_every_document_is_named_by_an_index(self):
        named = _named_anywhere()
        unreachable = [rel for rel in _documents() if Path(rel).name not in named]
        self.assertEqual(
            [], unreachable,
            "these documents are named by no index, so a reader entering at "
            "docs/README.md cannot find them; add a row to the relevant table, "
            "or to the sub-index that table points at",
        )


if __name__ == "__main__":
    unittest.main()
